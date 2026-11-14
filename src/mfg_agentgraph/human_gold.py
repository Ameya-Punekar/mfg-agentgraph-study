"""Versioned human-gold artifact for the anomaly-triage benchmark query set.

The recorded label is always the annotator consensus or an explicit adjudication. Author
labels, which were derived from the knowledge graph, appear only in a cross-check field, so a
disagreement between the two is reported as a finding instead of being treated as a
correction.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from mfg_agentgraph.annotation_sources import canonical_json, sha256_of
from mfg_agentgraph.anomaly_triage_dataset import (
    TRAP_CATEGORIES,
    QueryCategory,
    QueryRecord,
    QuerySet,
    reject_duplicate_json_keys,
    require_text,
)
from mfg_agentgraph.gold_annotation import (
    AgreementReport,
    AnnotationJudgment,
    AnnotationPacket,
    AnnotationSubmission,
    SupportJudgment,
    build_agreement_report,
)

HUMAN_GOLD_CONTRACT_VERSION = "mfg-agentgraph-human-gold-v1"
ADJUDICATION_CONTRACT_VERSION = "mfg-agentgraph-annotation-adjudication-v1"

_ADJUDICATION_KEYS = frozenset({"adjudicator_id", "contract_version", "decisions"})
_DECISION_KEYS = frozenset({"action", "evidence_refs", "query_id", "rationale", "support"})

_STATUS_UNANIMOUS = "unanimous"
_STATUS_ADJUDICATED = "adjudicated"


def _require_mapping(payload: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    document = cast(Mapping[str, object], payload)
    for key in document:
        if type(key) is not str:
            raise TypeError(f"{field_name} keys must be strings")
    return document


def _require_exact_keys(
    document: Mapping[str, object], field_name: str, required: frozenset[str]
) -> None:
    missing = required - set(document)
    if missing:
        raise ValueError(f"{field_name} is missing required key: {sorted(missing)[0]}")
    unknown = set(document) - required
    if unknown:
        raise ValueError(f"{field_name} contains unknown key: {sorted(unknown)[0]}")


@dataclass(frozen=True, slots=True)
class AdjudicationDecision:
    """One human resolution of a query the annotators did not agree on."""

    query_id: str
    support: SupportJudgment
    evidence_refs: Sequence[str]
    action: str | None
    rationale: str

    def __post_init__(self) -> None:
        validated = AnnotationJudgment(
            query_id=self.query_id,
            support=self.support,
            evidence_refs=self.evidence_refs,
            action=self.action,
            rubric=self.rationale,
        )
        object.__setattr__(self, "query_id", validated.query_id)
        object.__setattr__(self, "support", validated.support)
        object.__setattr__(self, "evidence_refs", tuple(validated.evidence_refs))
        object.__setattr__(self, "action", validated.action)
        object.__setattr__(self, "rationale", validated.rubric)

    def to_document(self) -> dict[str, object]:
        return {
            "action": self.action,
            "evidence_refs": list(self.evidence_refs),
            "query_id": self.query_id,
            "rationale": self.rationale,
            "support": self.support.value,
        }


@dataclass(frozen=True, slots=True)
class AdjudicationRecord:
    """One adjudicator's decisions, recorded separately from the original submissions."""

    adjudicator_id: str
    decisions: Sequence[AdjudicationDecision]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "adjudicator_id", require_text(self.adjudicator_id, "adjudicator_id")
        )
        if isinstance(self.decisions, (str, bytes, bytearray)) or not isinstance(
            self.decisions, Sequence
        ):
            raise TypeError("decisions must be a sequence of AdjudicationDecision instances")
        decisions = tuple(self.decisions)
        if not all(isinstance(decision, AdjudicationDecision) for decision in decisions):
            raise TypeError("decisions must be a sequence of AdjudicationDecision instances")
        query_ids = [decision.query_id for decision in decisions]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("decisions must not contain duplicate query_id values")
        object.__setattr__(self, "decisions", decisions)

    def decision_map(self) -> dict[str, AdjudicationDecision]:
        """Return the decisions keyed by query identifier."""
        return {decision.query_id: decision for decision in self.decisions}


def parse_adjudication_record(payload: object) -> AdjudicationRecord:
    """Validate one adjudication document, rejecting unknown fields and duplicates."""
    document = _require_mapping(payload, "adjudication record")
    _require_exact_keys(document, "adjudication record", _ADJUDICATION_KEYS)
    contract_version = require_text(document["contract_version"], "contract_version")
    if contract_version != ADJUDICATION_CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {ADJUDICATION_CONTRACT_VERSION!r}")
    raw_decisions = document["decisions"]
    if isinstance(raw_decisions, (str, bytes, bytearray)) or not isinstance(
        raw_decisions, Sequence
    ):
        raise TypeError("decisions must be a sequence of decision mappings")
    decisions: list[AdjudicationDecision] = []
    for entry in raw_decisions:
        decision = _require_mapping(entry, "decision")
        _require_exact_keys(decision, "decision", _DECISION_KEYS)
        decisions.append(
            AdjudicationDecision(
                query_id=decision["query_id"],  # type: ignore[arg-type]
                support=decision["support"],  # type: ignore[arg-type]
                evidence_refs=decision["evidence_refs"],  # type: ignore[arg-type]
                action=decision["action"],  # type: ignore[arg-type]
                rationale=decision["rationale"],  # type: ignore[arg-type]
            )
        )
    return AdjudicationRecord(
        adjudicator_id=document["adjudicator_id"],  # type: ignore[arg-type]
        decisions=decisions,
    )


def load_adjudication_record(path: Path) -> AdjudicationRecord:
    """Load one adjudication document with strict duplicate-key handling."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys
    )
    return parse_adjudication_record(payload)


def author_support_cross_check(query: QueryRecord) -> SupportJudgment:
    """Derive the author view of one query for cross-checking only.

    This reads the author-authored, KG-derived labels. It never supplies a gold label.
    """
    if query.category in TRAP_CATEGORIES:
        return (
            SupportJudgment.UNSAFE_REQUEST
            if query.category is QueryCategory.TRAP_UNSAFE
            else SupportJudgment.UNSUPPORTED
        )
    return SupportJudgment.SUPPORTED


@dataclass(frozen=True, slots=True)
class HumanGoldQuery:
    """One query's human label plus its recorded cross-check against the author view."""

    query_id: str
    support: SupportJudgment
    evidence_refs: Sequence[str]
    action: str | None
    status: str
    author_support_cross_check: SupportJudgment

    def to_document(self) -> dict[str, object]:
        return {
            "action": self.action,
            "author_support_cross_check": self.author_support_cross_check.value,
            "evidence_refs": list(self.evidence_refs),
            "query_id": self.query_id,
            "status": self.status,
            "support": self.support.value,
        }


@dataclass(frozen=True, slots=True)
class HumanGold:
    """One immutable, hash-addressed human-gold artifact."""

    annotator_ids: tuple[str, ...]
    dataset_id: str
    query_set_id: str
    query_set_sha256: str
    manifest_sha256: str
    packet_sha256: str
    queries: Sequence[HumanGoldQuery]
    agreement: AgreementReport
    adjudication_id: str | None
    adjudication_decisions: Sequence[AdjudicationDecision]

    def to_document(self) -> dict[str, object]:
        agreement_count = sum(
            1 for query in self.queries if query.support is query.author_support_cross_check
        )
        return {
            "adjudication": [
                {"adjudicator_id": self.adjudication_id, **decision.to_document()}
                for decision in self.adjudication_decisions
            ],
            "agreement": self.agreement.to_document(),
            "annotator_ids": list(self.annotator_ids),
            "author_label_cross_check": {
                "agreement_count": agreement_count,
                "disagreement_query_ids": [
                    query.query_id
                    for query in self.queries
                    if query.support is not query.author_support_cross_check
                ],
                "note": "author labels are KG-derived and are never the gold label",
            },
            "contract_version": HUMAN_GOLD_CONTRACT_VERSION,
            "dataset_id": self.dataset_id,
            "label_scope": (
                "support verdicts are relative to the frozen annotation source pack; a claim "
                "the pack cannot address is not assessable from it and must not be scored as "
                "a false answer"
            ),
            "manifest_sha256": self.manifest_sha256,
            "packet_sha256": self.packet_sha256,
            "queries": [query.to_document() for query in self.queries],
            "query_count": len(self.queries),
            "query_set_id": self.query_set_id,
            "query_set_sha256": self.query_set_sha256,
        }

    def to_json(self) -> str:
        """Return the canonical human-gold JSON."""
        return canonical_json(self.to_document())

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the canonical human-gold bytes."""
        return sha256_of(self.to_document())


def _disputed_query_ids(
    packet: AnnotationPacket, submissions: Sequence[AnnotationSubmission]
) -> tuple[tuple[str, ...], dict[str, tuple[SupportJudgment, tuple[str, ...], str | None]]]:
    maps = [submission.judgment_map() for submission in submissions]
    disputed: list[str] = []
    consensus: dict[str, tuple[SupportJudgment, tuple[str, ...], str | None]] = {}
    for query in packet.queries:
        verdicts = {
            (
                judgments[query.query_id].support,
                tuple(judgments[query.query_id].evidence_refs),
                judgments[query.query_id].action,
            )
            for judgments in maps
        }
        if len(verdicts) == 1:
            consensus[query.query_id] = verdicts.pop()
        else:
            disputed.append(query.query_id)
    return tuple(disputed), consensus


def build_human_gold(
    *,
    query_set: QuerySet,
    packet: AnnotationPacket,
    submissions: Sequence[AnnotationSubmission],
    adjudication: AdjudicationRecord | None = None,
) -> HumanGold:
    """Build the versioned gold artifact, refusing to emit while any dispute is unresolved."""
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    if not isinstance(packet, AnnotationPacket):
        raise TypeError("packet must be an AnnotationPacket")
    if adjudication is not None and not isinstance(adjudication, AdjudicationRecord):
        raise TypeError("adjudication must be an AdjudicationRecord")
    report = build_agreement_report(submissions, packet=packet)
    if packet.query_set_sha256 != query_set.document_sha256:
        raise ValueError("packet query_set_sha256 does not match the supplied query set")

    disputed_ids, consensus = _disputed_query_ids(packet, submissions)
    decisions = {} if adjudication is None else adjudication.decision_map()
    allowed = packet.allowed_evidence_refs
    for query_id, decision in decisions.items():
        if query_id not in disputed_ids:
            raise ValueError(f"adjudication decision for query {query_id!r} is not disputed")
        for reference in decision.evidence_refs:
            if reference not in allowed:
                raise ValueError(
                    f"evidence_refs {reference!r} is not in the frozen source manifest; "
                    f"allowed: {', '.join(sorted(allowed))}"
                )
    unresolved = [query_id for query_id in disputed_ids if query_id not in decisions]
    if unresolved:
        raise ValueError(
            "human gold cannot be emitted with unadjudicated queries: " + ", ".join(unresolved)
        )

    records: list[HumanGoldQuery] = []
    for query in query_set.queries:
        if query.query_id in decisions:
            decision = decisions[query.query_id]
            support, evidence_refs, action = (
                decision.support,
                tuple(decision.evidence_refs),
                decision.action,
            )
            status = _STATUS_ADJUDICATED
        else:
            support, evidence_refs, action = consensus[query.query_id]
            status = _STATUS_UNANIMOUS
        records.append(
            HumanGoldQuery(
                query_id=query.query_id,
                support=support,
                evidence_refs=evidence_refs,
                action=action,
                status=status,
                author_support_cross_check=author_support_cross_check(query),
            )
        )

    return HumanGold(
        annotator_ids=report.annotator_ids,
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        query_set_sha256=packet.query_set_sha256,
        manifest_sha256=packet.manifest_sha256,
        packet_sha256=packet.document_sha256,
        queries=tuple(records),
        agreement=report,
        adjudication_id=None if adjudication is None else adjudication.adjudicator_id,
        adjudication_decisions=() if adjudication is None else adjudication.decisions,
    )
