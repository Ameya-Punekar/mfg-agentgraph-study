"""Versioned anomaly-triage query set with gold labels and trap cases."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import cast

from mfg_agentgraph.stage_instrumentation import TerminalStatus

CONTRACT_VERSION = "mfg-agentgraph-anomaly-triage-dataset-v1"

_MAX_IDENTIFIER_BYTES = 1_024
_MAX_TEXT_BYTES = 8_192
_QUERY_ID_PATTERN = re.compile(r"^atq-\d{3}$")
_DOCUMENT_KEYS = frozenset({"contract_version", "dataset_id", "query_set_id", "version", "queries"})
_QUERY_KEYS = frozenset(
    {
        "query_id",
        "category",
        "text",
        "asset_id",
        "expected_evidence_refs",
        "expected_action",
        "expected_terminal_status",
        "gold_rubric",
    }
)


class QueryCategory(StrEnum):
    """Evaluation difficulty and trap classes used by every S1-S4 strategy."""

    SINGLE_HOP = "single_hop"
    MULTI_HOP = "multi_hop"
    ACTION_PLAN = "action_plan"
    COUNTERFACTUAL = "counterfactual"
    PROVENANCE = "provenance"
    TRAP_UNSUPPORTED = "trap_unsupported"
    TRAP_UNSAFE = "trap_unsafe"


TRAP_CATEGORIES: frozenset[QueryCategory] = frozenset(
    {QueryCategory.TRAP_UNSUPPORTED, QueryCategory.TRAP_UNSAFE}
)

TRAP_TERMINAL_STATUS: Mapping[QueryCategory, TerminalStatus] = MappingProxyType(
    {
        QueryCategory.TRAP_UNSUPPORTED: TerminalStatus.INSUFFICIENT_EVIDENCE,
        QueryCategory.TRAP_UNSAFE: TerminalStatus.VALIDATION_FAILED_CLOSED,
    }
)

EXPECTED_CATEGORY_COUNTS: Mapping[QueryCategory, int] = MappingProxyType(
    {
        QueryCategory.SINGLE_HOP: 6,
        QueryCategory.MULTI_HOP: 6,
        QueryCategory.ACTION_PLAN: 6,
        QueryCategory.COUNTERFACTUAL: 5,
        QueryCategory.PROVENANCE: 3,
        QueryCategory.TRAP_UNSUPPORTED: 2,
        QueryCategory.TRAP_UNSAFE: 2,
    }
)


def require_text(
    value: object, field_name: str, *, maximum_bytes: int = _MAX_IDENTIFIER_BYTES
) -> str:
    """Return stripped nonblank text, rejecting wrong types and oversized values."""
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field_name} exceeds {maximum_bytes} UTF-8 bytes")
    return normalized


def _require_category(value: object) -> QueryCategory:
    if isinstance(value, QueryCategory):
        return value
    if type(value) is not str:
        raise TypeError("category must be a string")
    try:
        return QueryCategory(value)
    except ValueError as error:
        raise ValueError(
            "category must be one of: " + ", ".join(category.value for category in QueryCategory)
        ) from error


def _require_terminal_status(value: object, field_name: str) -> TerminalStatus | None:
    if value is None:
        return None
    if not isinstance(value, TerminalStatus):
        if type(value) is not str:
            raise TypeError(f"{field_name} must be a string or None")
        try:
            return TerminalStatus(value)
        except ValueError as error:
            raise ValueError(
                f"{field_name} must be one of: "
                + ", ".join(status.value for status in TerminalStatus)
            ) from error
    return value


def _require_evidence_refs(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings")
    normalized = tuple(
        require_text(item, field_name, maximum_bytes=_MAX_TEXT_BYTES) for item in value
    )
    seen: set[str] = set()
    for identifier in normalized:
        if identifier in seen:
            raise ValueError(f"{field_name} must not contain duplicate identifier {identifier!r}")
        seen.add(identifier)
    return normalized


@dataclass(frozen=True, slots=True)
class QueryRecord:
    """One versioned anomaly-triage query with its gold and evidence labels."""

    query_id: str
    category: QueryCategory
    text: str
    asset_id: str
    expected_evidence_refs: Sequence[str]
    expected_action: str | None
    expected_terminal_status: TerminalStatus | None
    gold_rubric: str

    def __post_init__(self) -> None:
        query_id = require_text(self.query_id, "query_id")
        if not _QUERY_ID_PATTERN.fullmatch(query_id):
            raise ValueError("query_id must match the atq-NNN pattern")
        object.__setattr__(self, "query_id", query_id)
        object.__setattr__(self, "category", _require_category(self.category))
        object.__setattr__(
            self, "text", require_text(self.text, "text", maximum_bytes=_MAX_TEXT_BYTES)
        )
        object.__setattr__(self, "asset_id", require_text(self.asset_id, "asset_id"))
        evidence_refs = _require_evidence_refs(
            self.expected_evidence_refs, "expected_evidence_refs"
        )
        expected_action = self.expected_action
        if expected_action is not None:
            expected_action = require_text(
                expected_action, "expected_action", maximum_bytes=_MAX_TEXT_BYTES
            )
        terminal_status = _require_terminal_status(
            self.expected_terminal_status, "expected_terminal_status"
        )
        object.__setattr__(
            self,
            "gold_rubric",
            require_text(self.gold_rubric, "gold_rubric", maximum_bytes=_MAX_TEXT_BYTES),
        )

        if self.category in TRAP_CATEGORIES:
            expected = TRAP_TERMINAL_STATUS[self.category]
            if terminal_status is not expected:
                raise ValueError(
                    "expected_terminal_status must be "
                    f"{expected.value!r} for {self.category.value} queries"
                )
            if expected_action is not None:
                raise ValueError("expected_action must be absent for trap queries")
            if evidence_refs:
                raise ValueError("expected_evidence_refs must be empty for trap queries")
        else:
            if terminal_status is not None:
                raise ValueError("expected_terminal_status must be absent for non-trap queries")
            if not evidence_refs:
                raise ValueError("expected_evidence_refs must not be empty for non-trap queries")

        object.__setattr__(self, "expected_evidence_refs", evidence_refs)
        object.__setattr__(self, "expected_action", expected_action)
        object.__setattr__(self, "expected_terminal_status", terminal_status)

    def to_document(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "category": self.category.value,
            "expected_action": self.expected_action,
            "expected_evidence_refs": list(self.expected_evidence_refs),
            "expected_terminal_status": (
                None
                if self.expected_terminal_status is None
                else self.expected_terminal_status.value
            ),
            "gold_rubric": self.gold_rubric,
            "query_id": self.query_id,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class QuerySet:
    """One immutable, hash-addressed anomaly-triage query set."""

    dataset_id: str
    query_set_id: str
    version: str
    queries: Sequence[QueryRecord]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", require_text(self.dataset_id, "dataset_id"))
        object.__setattr__(self, "query_set_id", require_text(self.query_set_id, "query_set_id"))
        object.__setattr__(self, "version", require_text(self.version, "version"))
        if isinstance(self.queries, (str, bytes, bytearray)) or not isinstance(
            self.queries, Sequence
        ):
            raise TypeError("queries must be a sequence of QueryRecord instances")
        queries = tuple(self.queries)
        if not all(isinstance(query, QueryRecord) for query in queries):
            raise TypeError("queries must be a sequence of QueryRecord instances")
        if not queries:
            raise ValueError("queries must not be empty")

        query_ids = [query.query_id for query in queries]
        seen: set[str] = set()
        for query_id in query_ids:
            if query_id in seen:
                raise ValueError(f"duplicate query_id {query_id!r}")
            seen.add(query_id)
        if query_ids != sorted(query_ids):
            raise ValueError("queries must be ordered by ascending query_id")

        observed_counts = {category: 0 for category in QueryCategory}
        for query in queries:
            observed_counts[query.category] += 1
        if observed_counts != dict(EXPECTED_CATEGORY_COUNTS):
            raise ValueError(
                "category counts do not match the approved composition: "
                f"expected {dict(EXPECTED_CATEGORY_COUNTS)!r}, observed {observed_counts!r}"
            )
        object.__setattr__(self, "queries", queries)

    def to_document(self) -> dict[str, object]:
        return {
            "contract_version": CONTRACT_VERSION,
            "dataset_id": self.dataset_id,
            "queries": [query.to_document() for query in self.queries],
            "query_set_id": self.query_set_id,
            "version": self.version,
        }

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the canonical document bytes."""
        canonical = json.dumps(
            self.to_document(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


def reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key {key!r}")
        document[key] = value
    return document


def _parse_query(payload: object) -> QueryRecord:
    if not isinstance(payload, Mapping):
        raise TypeError("queries must be a sequence of query mappings")
    keys = set(payload)
    missing = _QUERY_KEYS - keys
    if missing:
        raise ValueError(f"query is missing required key: {sorted(missing)[0]}")
    unknown = keys - _QUERY_KEYS
    if unknown:
        raise ValueError(f"query contains unknown key: {sorted(unknown)[0]}")
    document = cast(Mapping[str, object], payload)
    return QueryRecord(
        query_id=document["query_id"],  # type: ignore[arg-type]
        category=document["category"],  # type: ignore[arg-type]
        text=document["text"],  # type: ignore[arg-type]
        asset_id=document["asset_id"],  # type: ignore[arg-type]
        expected_evidence_refs=document["expected_evidence_refs"],  # type: ignore[arg-type]
        expected_action=document["expected_action"],  # type: ignore[arg-type]
        expected_terminal_status=document["expected_terminal_status"],  # type: ignore[arg-type]
        gold_rubric=document["gold_rubric"],  # type: ignore[arg-type]
    )


def parse_query_set_document(payload: object) -> QuerySet:
    """Validate one parsed query-set document and return its immutable form."""
    if not isinstance(payload, Mapping):
        raise TypeError("query set document must be a mapping")
    document = cast(Mapping[str, object], payload)
    missing = _DOCUMENT_KEYS - set(document)
    if missing:
        raise ValueError(f"query set document is missing required key: {sorted(missing)[0]}")
    unknown = set(document) - _DOCUMENT_KEYS
    if unknown:
        raise ValueError(f"query set document contains unknown key: {sorted(unknown)[0]}")

    contract_version = require_text(document["contract_version"], "contract_version")
    if contract_version != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION!r}")
    queries = document["queries"]
    if isinstance(queries, (str, bytes, bytearray)) or not isinstance(queries, Sequence):
        raise TypeError("queries must be a sequence of query mappings")
    return QuerySet(
        dataset_id=document["dataset_id"],  # type: ignore[arg-type]
        query_set_id=document["query_set_id"],  # type: ignore[arg-type]
        version=document["version"],  # type: ignore[arg-type]
        queries=[_parse_query(query) for query in queries],
    )


def load_query_set(path: Path) -> QuerySet:
    """Load and validate a query-set JSON file with strict duplicate-key handling."""
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys
    )
    return parse_query_set_document(payload)
