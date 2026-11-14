"""Versioned synthetic-reference label artifact for the anomaly-triage query set.

Issue #79 asked for independent human gold annotation. That requirement is unmet and stays
recorded as unmet: a single author cannot supply two independent annotators, and no agent,
model, or author may substitute for them.

What this module provides instead is narrower and mechanically checkable. It records, for
every query, the reference label the frozen scenario fixtures entail as far as identifiers go,
and whether each cited identifier resolves against those fixtures. The artifact explicitly
declares that it is not independently validated, is not benchmark gold, and carries no
inter-annotator agreement.

It answers "can this citation be resolved in a frozen artefact?" It does not answer "is this
label correct?" or "does the fixture's record actually settle this query?" — neither is
machine-checkable here, and neither is claimed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from mfg_agentgraph.annotation_sources import SourceManifest, canonical_json
from mfg_agentgraph.anomaly_triage_dataset import (
    QueryCategory,
    QueryRecord,
    QuerySet,
    reject_duplicate_json_keys,
    require_text,
)
from mfg_agentgraph.evaluation_harness import EvaluationRunManifest
from mfg_agentgraph.stage_instrumentation import TerminalStatus

SYNTHETIC_REFERENCE_CONTRACT_VERSION = "mfg-agentgraph-synthetic-reference-v2"

# Fixture identifiers are IRIs, not the narrower citation vocabulary the annotation-source
# manifest allows: ``ex:Observation_Pump12_2026-05-18T14:03:00Z`` is a legitimate fixture
# resource but could never be cited as an annotation evidence reference.
_EVIDENCE_PATTERN = re.compile(r"^ex:\S+$")
_IRI_FORBIDDEN = frozenset('<>"{}|\\^`')

_AUTHORING: Mapping[str, object] = {
    "human_expert_review": False,
    "independent_annotation": False,
    "inter_annotator_agreement": None,
    "label_origin": "thesis author, with AI assistance, against frozen scenario fixtures",
}

_SCOPE = (
    "A reference for reproducibility only: it records which labels the frozen scenario "
    "fixtures can resolve by identifier. It is not benchmark gold, not independently "
    "validated, not expert reviewed, and carries no inter-annotator agreement. A claim the "
    "fixtures do not establish is not assessable here and must not be scored as a false "
    "answer."
)

_ORIGINAL_REQUIREMENT_STATUS = (
    "unmet: the original requirement was two independent human annotators with reported "
    "inter-annotator agreement; no independent human annotation exists"
)


class ReferenceStrength(StrEnum):
    """How far a reference label is anchored in the frozen fixtures."""

    FIXTURE_ANCHORED = "fixture_anchored"
    UNANCHORED = "unanchored"
    # An empty citation set has nothing to resolve, so calling it anchored would be vacuous.
    NOT_APPLICABLE = "not_applicable"


def load_scenario_fixture(path: Path) -> dict[str, object]:
    """Load one frozen scenario fixture with strict duplicate-key handling."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys
    )
    if not isinstance(payload, Mapping):
        raise TypeError("scenario fixture must be a mapping")
    return cast(dict[str, object], dict(payload))


def _check_iri(value: str) -> str:
    candidate = require_text(value, "fixture identifier").strip()
    if not _EVIDENCE_PATTERN.fullmatch(candidate) or _IRI_FORBIDDEN & set(candidate):
        raise ValueError(f"fixture identifier is not a canonical IRI: {value!r}")
    return candidate


def inspect_scenario_identifiers(
    scenario: Mapping[str, object],
) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(declared, referenced)`` identifiers from the frozen scenario fixture.

    ``declared`` holds resources the fixture actually defines, taken from ``id`` fields.
    ``referenced`` holds every other identifier-shaped string, such as a predicate name or a
    dangling pointer. Only declared resources and manifest-declared sources may anchor a
    citation: a query citing a predicate name must not resolve merely because the string
    happens to appear somewhere in the fixture.
    """
    if not isinstance(scenario, Mapping):
        raise TypeError("scenario must be a mapping")
    declared: set[str] = set()
    referenced: set[str] = set()

    def collect(node: object, *, is_declaration: bool) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key == "id":
                    # A blank ``id`` would make the fixture look anchored while naming nothing.
                    require_text(value, "fixture id")
                collect(value, is_declaration=key == "id")
        elif isinstance(node, (list, tuple)):
            for value in node:
                collect(value, is_declaration=False)
        elif isinstance(node, str) and node.startswith("ex:"):
            identifier = _check_iri(node)
            (declared if is_declaration else referenced).add(identifier)

    collect(scenario, is_declaration=False)
    if not declared:
        raise ValueError("scenario fixture declares no evidence identifiers")
    return frozenset(declared), frozenset(referenced - declared)


@dataclass(frozen=True, slots=True)
class SyntheticReferenceEntry:
    """One query's reference label with its mechanical fixture anchoring."""

    query_id: str
    category: QueryCategory
    reference_evidence_refs: Sequence[str]
    reference_action: str | None
    reference_terminal_status: TerminalStatus | None
    strength: ReferenceStrength
    unresolved_evidence_refs: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_id", require_text(self.query_id, "query_id"))
        if not isinstance(self.category, QueryCategory):
            raise TypeError("category must be a QueryCategory")
        for field_name in ("reference_evidence_refs", "unresolved_evidence_refs"):
            value = getattr(self, field_name)
            if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
                raise TypeError(f"{field_name} must be a sequence of identifiers")
            object.__setattr__(
                self, field_name, tuple(require_text(item, field_name) for item in value)
            )
        if not isinstance(self.strength, ReferenceStrength):
            raise TypeError("strength must be a ReferenceStrength")

    def to_document(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "query_id": self.query_id,
            "reference_action": self.reference_action,
            "reference_evidence_refs": list(self.reference_evidence_refs),
            "reference_terminal_status": (
                None
                if self.reference_terminal_status is None
                else self.reference_terminal_status.value
            ),
            "strength": self.strength.value,
            "unresolved_evidence_refs": list(self.unresolved_evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SyntheticReference:
    """One immutable, hash-addressed synthetic-reference artifact."""

    dataset_id: str
    query_set_id: str
    query_set_sha256: str
    source_manifest_sha256: str
    scenario_sha256: str
    declared_fixture_identifiers: Sequence[str]
    fixture_reference_only_identifiers: Sequence[str]
    resolvable_identifiers: Sequence[str]
    entries: Sequence[SyntheticReferenceEntry]

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "query_set_id"):
            object.__setattr__(
                self, field_name, require_text(getattr(self, field_name), field_name)
            )
        for field_name in ("query_set_sha256", "source_manifest_sha256", "scenario_sha256"):
            digest = require_text(getattr(self, field_name), field_name)
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
            object.__setattr__(self, field_name, digest)
        for field_name in (
            "declared_fixture_identifiers",
            "fixture_reference_only_identifiers",
            "resolvable_identifiers",
        ):
            value = getattr(self, field_name)
            if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
                raise TypeError(f"{field_name} must be a sequence of identifiers")
            object.__setattr__(
                self, field_name, tuple(sorted(require_text(item, field_name) for item in value))
            )
        entries = self.entries
        if isinstance(entries, (str, bytes, bytearray)) or not isinstance(entries, Sequence):
            raise TypeError("entries must be a sequence of SyntheticReferenceEntry instances")
        frozen_entries = tuple(entries)
        if not frozen_entries:
            raise ValueError("entries must not be empty")
        if not all(isinstance(entry, SyntheticReferenceEntry) for entry in frozen_entries):
            raise TypeError("entries must be a sequence of SyntheticReferenceEntry instances")
        query_ids = [entry.query_id for entry in frozen_entries]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("entries must not contain duplicate query_id values")
        allowed = frozenset(self.resolvable_identifiers)
        for entry in frozen_entries:
            # A deserialized artifact must not be able to claim provenance its own declared
            # identifier set does not support.
            unresolved = tuple(sorted(set(entry.reference_evidence_refs) - allowed))
            if tuple(entry.unresolved_evidence_refs) != unresolved:
                offending = ", ".join(unresolved) or "none"
                raise ValueError(
                    f"entry {entry.query_id!r} lists unresolved evidence refs that do not "
                    f"match its citations; expected {offending}"
                )
            expected_strength = _strength(tuple(entry.reference_evidence_refs), unresolved)
            if entry.strength is not expected_strength:
                raise ValueError(
                    f"entry {entry.query_id!r} strength {entry.strength.value!r} does not "
                    f"match its citations; expected {expected_strength.value!r}"
                )
        object.__setattr__(self, "entries", frozen_entries)

    @property
    def authoring(self) -> Mapping[str, object]:
        """Return the recorded authoring provenance for this artifact."""
        return dict(_AUTHORING)

    @property
    def original_requirement_status(self) -> str:
        """Return the recorded status of the original independent-annotation requirement."""
        return _ORIGINAL_REQUIREMENT_STATUS

    @property
    def strength_counts(self) -> dict[str, int]:
        """Return how many entries fall in each strength class."""
        counts = {strength.value: 0 for strength in ReferenceStrength}
        for entry in self.entries:
            counts[entry.strength.value] += 1
        return counts

    def to_document(self) -> dict[str, object]:
        return {
            "authoring": self.authoring,
            "contract_version": SYNTHETIC_REFERENCE_CONTRACT_VERSION,
            "dataset_id": self.dataset_id,
            "declared_fixture_identifiers": list(self.declared_fixture_identifiers),
            "entries": [entry.to_document() for entry in self.entries],
            "fixture_reference_only_identifiers": list(self.fixture_reference_only_identifiers),
            "original_requirement_status": self.original_requirement_status,
            "query_count": len(self.entries),
            "query_set_id": self.query_set_id,
            "query_set_sha256": self.query_set_sha256,
            "resolvable_identifiers": list(self.resolvable_identifiers),
            "scenario_sha256": self.scenario_sha256,
            "scope": _SCOPE,
            "source_manifest_sha256": self.source_manifest_sha256,
            "strength_counts": self.strength_counts,
        }

    def to_json(self) -> str:
        """Return the canonical artifact JSON."""
        return canonical_json(self.to_document())

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the canonical artifact bytes."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


def _strength(cited: tuple[str, ...], unresolved: tuple[str, ...]) -> ReferenceStrength:
    if unresolved:
        return ReferenceStrength.UNANCHORED
    if not cited:
        # Trap queries cite nothing by contract, so there is nothing to anchor.
        return ReferenceStrength.NOT_APPLICABLE
    return ReferenceStrength.FIXTURE_ANCHORED


def _entry_for(query: QueryRecord, resolvable: frozenset[str]) -> SyntheticReferenceEntry:
    cited = tuple(query.expected_evidence_refs)
    unresolved = tuple(sorted(reference for reference in cited if reference not in resolvable))
    return SyntheticReferenceEntry(
        query_id=query.query_id,
        category=query.category,
        reference_evidence_refs=cited,
        reference_action=query.expected_action,
        reference_terminal_status=query.expected_terminal_status,
        strength=_strength(cited, unresolved),
        unresolved_evidence_refs=unresolved,
    )


def build_synthetic_reference(
    *,
    query_set: QuerySet,
    scenario: Mapping[str, object],
    source_manifest: SourceManifest,
) -> SyntheticReference:
    """Build the artifact, resolving every citation against the frozen artefacts.

    The scenario's own content is bound by digest as well as its identifiers, so editing the
    fixture's substance cannot leave the artifact digest unchanged.
    """
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    if not isinstance(scenario, Mapping):
        raise TypeError("scenario must be a mapping")
    if not isinstance(source_manifest, SourceManifest):
        raise TypeError("source_manifest must be a SourceManifest")
    declared, reference_only = inspect_scenario_identifiers(scenario)
    resolvable = frozenset(declared) | source_manifest.allowed_evidence_refs
    return SyntheticReference(
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        query_set_sha256=query_set.document_sha256,
        source_manifest_sha256=source_manifest.document_sha256,
        scenario_sha256=hashlib.sha256(canonical_json(scenario).encode("utf-8")).hexdigest(),
        declared_fixture_identifiers=tuple(declared),
        fixture_reference_only_identifiers=tuple(reference_only),
        resolvable_identifiers=tuple(resolvable),
        entries=tuple(_entry_for(query, resolvable) for query in query_set.queries),
    )


def require_reference_matches_run(
    reference: SyntheticReference, manifest: EvaluationRunManifest
) -> None:
    """Fail when a scored run claims a reference describing a different query set."""
    if not isinstance(reference, SyntheticReference):
        raise TypeError("reference must be a SyntheticReference")
    if not isinstance(manifest, EvaluationRunManifest):
        raise TypeError("manifest must be an EvaluationRunManifest")
    if manifest.dataset_sha256 != reference.query_set_sha256:
        raise ValueError(
            "run dataset_sha256 does not match the reference query set: "
            f"run {manifest.dataset_sha256}, reference {reference.query_set_sha256}"
        )
