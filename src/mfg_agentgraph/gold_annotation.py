"""Independent human gold annotation for the anomaly-triage benchmark query set.

The packet blinds annotators to the author-authored gold fields so that labels can be
collected independently; the agreement report is computed before any adjudication.
Nothing here can verify that annotators really were independent humans, so agreement
figures remain unverified collection evidence until the protocol is attested.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from pathlib import Path
from typing import cast

from mfg_agentgraph.annotation_sources import (
    SourceManifest,
    canonical_json,
    require_source_text,
    sha256_of,
)
from mfg_agentgraph.anomaly_triage_dataset import (
    QuerySet,
    reject_duplicate_json_keys,
    require_text,
)

PACKET_CONTRACT_VERSION = "mfg-agentgraph-annotation-packet-v2"
ANNOTATION_CONTRACT_VERSION = "mfg-agentgraph-gold-annotation-v2"

_MAX_TEXT_BYTES = 8_192
_QUERY_ID_PATTERN = re.compile(r"^atq-\d{3}$")
_EVIDENCE_REF_PATTERN = re.compile(r"^ex:[A-Za-z0-9_]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_SUBMISSION_KEYS = frozenset(
    {
        "annotator_id",
        "contract_version",
        "judgments",
        "manifest_sha256",
        "packet_sha256",
        "query_set_sha256",
    }
)
_JUDGMENT_KEYS = frozenset({"action", "evidence_refs", "query_id", "rubric", "support"})


class SupportJudgment(StrEnum):
    """Whether the primary sources support, cannot answer, or forbid the request."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNSAFE_REQUEST = "unsafe_request"


SUPPORT_JUDGMENTS: tuple[SupportJudgment, ...] = tuple(SupportJudgment)


def _require_sha256(value: object, field_name: str) -> str:
    digest = require_text(value, field_name)
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return digest


def _require_mapping_keys(
    payload: object, field_name: str, required: frozenset[str]
) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    document = cast(Mapping[str, object], payload)
    for key in document:
        if type(key) is not str:
            raise TypeError(f"{field_name} keys must be strings")
    keys = set(document)
    missing = required - keys
    if missing:
        raise ValueError(f"{field_name} is missing required key: {sorted(missing)[0]}")
    unknown = keys - required
    if unknown:
        raise ValueError(f"{field_name} contains unknown key: {sorted(unknown)[0]}")
    return document


def _require_query_id(value: object) -> str:
    query_id = require_text(value, "query_id")
    if not _QUERY_ID_PATTERN.fullmatch(query_id):
        raise ValueError("query_id must match the atq-NNN pattern")
    return query_id


def _require_support(value: object) -> SupportJudgment:
    if isinstance(value, SupportJudgment):
        return value
    if type(value) is not str:
        raise TypeError("support must be a string")
    try:
        return SupportJudgment(value)
    except ValueError as error:
        raise ValueError("support must be one of: " + ", ".join(SUPPORT_JUDGMENTS)) from error


def _require_evidence_refs(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("evidence_refs must be a sequence of canonical evidence identifiers")
    refs: list[str] = []
    for item in value:
        reference = require_text(item, "evidence_refs")
        if not _EVIDENCE_REF_PATTERN.fullmatch(reference):
            raise ValueError(f"evidence_refs must be canonical ex: identifiers, got {reference!r}")
        refs.append(reference)
    if len(set(refs)) != len(refs):
        raise ValueError("evidence_refs must not contain duplicate identifiers")
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True)
class AnnotationQuery:
    """One blinded query as an annotator sees it: identifier and text only."""

    query_id: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_id", _require_query_id(self.query_id))
        object.__setattr__(
            self, "text", require_text(self.text, "text", maximum_bytes=_MAX_TEXT_BYTES)
        )

    def to_document(self) -> dict[str, object]:
        return {"query_id": self.query_id, "text": self.text}


@dataclass(frozen=True, slots=True)
class AnnotationSourceView:
    """One frozen primary source exactly as an annotator is allowed to read it."""

    evidence_id: str
    text: str

    def __post_init__(self) -> None:
        evidence_id = require_text(self.evidence_id, "evidence_id")
        if not _EVIDENCE_REF_PATTERN.fullmatch(evidence_id):
            raise ValueError(f"evidence_id must be a canonical ex: identifier, got {evidence_id!r}")
        object.__setattr__(self, "evidence_id", evidence_id)
        # Preserve whitespace: the packet displays the bytes its manifest digest binds.
        object.__setattr__(self, "text", require_source_text(self.text))

    def to_document(self) -> dict[str, object]:
        return {"evidence_id": self.evidence_id, "text": self.text}


@dataclass(frozen=True, slots=True)
class AnnotationPacket:
    """One immutable, hash-addressed blinded annotation packet."""

    dataset_id: str
    query_set_id: str
    query_set_sha256: str
    manifest_sha256: str
    sources: Sequence[AnnotationSourceView]
    queries: Sequence[AnnotationQuery]

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", require_text(self.dataset_id, "dataset_id"))
        object.__setattr__(self, "query_set_id", require_text(self.query_set_id, "query_set_id"))
        object.__setattr__(
            self, "query_set_sha256", _require_sha256(self.query_set_sha256, "query_set_sha256")
        )
        object.__setattr__(
            self, "manifest_sha256", _require_sha256(self.manifest_sha256, "manifest_sha256")
        )
        if isinstance(self.sources, (str, bytes, bytearray)) or not isinstance(
            self.sources, Sequence
        ):
            raise TypeError("sources must be a sequence of AnnotationSourceView instances")
        sources = tuple(self.sources)
        if not sources:
            raise ValueError("sources must not be empty")
        if not all(isinstance(source, AnnotationSourceView) for source in sources):
            raise TypeError("sources must be a sequence of AnnotationSourceView instances")
        source_ids = [source.evidence_id for source in sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("sources must not contain duplicate evidence_id values")
        object.__setattr__(self, "sources", sources)
        if isinstance(self.queries, (str, bytes, bytearray)) or not isinstance(
            self.queries, Sequence
        ):
            raise TypeError("queries must be a sequence of AnnotationQuery instances")
        queries = tuple(self.queries)
        if not queries:
            raise ValueError("queries must not be empty")
        if not all(isinstance(query, AnnotationQuery) for query in queries):
            raise TypeError("queries must be a sequence of AnnotationQuery instances")
        query_ids = [query.query_id for query in queries]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("queries must not contain duplicate query_id values")
        if query_ids != sorted(query_ids):
            raise ValueError("queries must be ordered by ascending query_id")
        object.__setattr__(self, "queries", queries)

    @property
    def allowed_evidence_refs(self) -> frozenset[str]:
        """Return every evidence identifier this packet permits."""
        return frozenset(source.evidence_id for source in self.sources)

    def to_document(self) -> dict[str, object]:
        return {
            "contract_version": PACKET_CONTRACT_VERSION,
            "dataset_id": self.dataset_id,
            "manifest_sha256": self.manifest_sha256,
            "queries": [query.to_document() for query in self.queries],
            "query_set_id": self.query_set_id,
            "query_set_sha256": self.query_set_sha256,
            "sources": [source.to_document() for source in self.sources],
        }

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the canonical packet bytes."""
        return sha256_of(self.to_document())

    def to_json(self) -> str:
        """Return the canonical packet JSON written for annotators."""
        return canonical_json(self.to_document())


def build_annotation_packet(query_set: QuerySet, *, manifest: SourceManifest) -> AnnotationPacket:
    """Return the blinded packet bound to the frozen sources and one query set."""
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    if not isinstance(manifest, SourceManifest):
        raise TypeError("manifest must be a SourceManifest")
    return AnnotationPacket(
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        query_set_sha256=query_set.document_sha256,
        manifest_sha256=manifest.document_sha256,
        sources=[
            AnnotationSourceView(evidence_id=source.evidence_id, text=source.text)
            for source in manifest.sources
        ],
        queries=[
            AnnotationQuery(query_id=query.query_id, text=query.text) for query in query_set.queries
        ],
    )


@dataclass(frozen=True, slots=True)
class AnnotationJudgment:
    """One annotator's independent judgment for exactly one query."""

    query_id: str
    support: SupportJudgment
    evidence_refs: Sequence[str]
    action: str | None
    rubric: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_id", _require_query_id(self.query_id))
        support = _require_support(self.support)
        object.__setattr__(self, "support", support)
        evidence_refs = _require_evidence_refs(self.evidence_refs)
        action = self.action
        if action is not None:
            action = require_text(action, "action", maximum_bytes=_MAX_TEXT_BYTES)
        rubric = require_text(self.rubric, "rubric", maximum_bytes=_MAX_TEXT_BYTES)

        if support is SupportJudgment.SUPPORTED:
            if not evidence_refs:
                raise ValueError("evidence_refs must not be empty for supported judgments")
        else:
            if evidence_refs:
                raise ValueError("evidence_refs must be empty for unsupported or unsafe judgments")
            if action is not None:
                raise ValueError("action must be absent for unsupported or unsafe judgments")

        object.__setattr__(self, "evidence_refs", evidence_refs)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "rubric", rubric)

    def to_document(self) -> dict[str, object]:
        return {
            "action": self.action,
            "evidence_refs": list(self.evidence_refs),
            "query_id": self.query_id,
            "rubric": self.rubric,
            "support": self.support.value,
        }


@dataclass(frozen=True, slots=True)
class AnnotationSubmission:
    """One annotator's complete submission, bound to an exact dataset and packet."""

    annotator_id: str
    query_set_sha256: str
    manifest_sha256: str
    packet_sha256: str
    judgments: Sequence[AnnotationJudgment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "annotator_id", require_text(self.annotator_id, "annotator_id"))
        object.__setattr__(
            self, "query_set_sha256", _require_sha256(self.query_set_sha256, "query_set_sha256")
        )
        object.__setattr__(
            self, "manifest_sha256", _require_sha256(self.manifest_sha256, "manifest_sha256")
        )
        object.__setattr__(
            self, "packet_sha256", _require_sha256(self.packet_sha256, "packet_sha256")
        )
        if isinstance(self.judgments, (str, bytes, bytearray)) or not isinstance(
            self.judgments, Sequence
        ):
            raise TypeError("judgments must be a sequence of AnnotationJudgment instances")
        judgments = tuple(self.judgments)
        if not judgments:
            raise ValueError("judgments must not be empty")
        if not all(isinstance(judgment, AnnotationJudgment) for judgment in judgments):
            raise TypeError("judgments must be a sequence of AnnotationJudgment instances")
        seen: set[str] = set()
        for judgment in judgments:
            if judgment.query_id in seen:
                raise ValueError(f"duplicate judgment for query_id {judgment.query_id!r}")
            seen.add(judgment.query_id)
        object.__setattr__(self, "judgments", judgments)

    def judgment_map(self) -> dict[str, AnnotationJudgment]:
        """Return the judgments keyed by query identifier."""
        return {judgment.query_id: judgment for judgment in self.judgments}

    def to_document(self) -> dict[str, object]:
        return {
            "annotator_id": self.annotator_id,
            "contract_version": ANNOTATION_CONTRACT_VERSION,
            "judgments": [judgment.to_document() for judgment in self.judgments],
            "manifest_sha256": self.manifest_sha256,
            "packet_sha256": self.packet_sha256,
            "query_set_sha256": self.query_set_sha256,
        }

    def to_json(self) -> str:
        """Return the canonical submission JSON written for agreement reporting."""
        return canonical_json(self.to_document())


def _parse_judgment(payload: object) -> AnnotationJudgment:
    document = _require_mapping_keys(payload, "judgment", _JUDGMENT_KEYS)
    return AnnotationJudgment(
        query_id=document["query_id"],  # type: ignore[arg-type]
        support=document["support"],  # type: ignore[arg-type]
        evidence_refs=document["evidence_refs"],  # type: ignore[arg-type]
        action=document["action"],  # type: ignore[arg-type]
        rubric=document["rubric"],  # type: ignore[arg-type]
    )


def _validate_coverage(packet: AnnotationPacket, query_ids: Sequence[str]) -> None:
    expected = [query.query_id for query in packet.queries]
    expected_set = set(expected)
    for query_id in query_ids:
        if query_id not in expected_set:
            raise ValueError(f"submission contains unknown query_id {query_id!r}")
    seen: set[str] = set()
    for query_id in query_ids:
        if query_id in seen:
            raise ValueError(f"submission contains duplicate judgment for query_id {query_id!r}")
        seen.add(query_id)
    missing = [query_id for query_id in expected if query_id not in seen]
    if missing:
        raise ValueError(f"submission is missing a judgment for query_id {missing[0]!r}")


def _validate_evidence_membership(
    packet: AnnotationPacket, submission: AnnotationSubmission
) -> None:
    allowed = packet.allowed_evidence_refs
    for judgment in submission.judgments:
        for reference in judgment.evidence_refs:
            if reference not in allowed:
                raise ValueError(
                    f"evidence_refs {reference!r} is not in the frozen source manifest; "
                    f"allowed: {', '.join(sorted(allowed))}"
                )


def parse_annotation_submission(
    payload: object, *, packet: AnnotationPacket
) -> AnnotationSubmission:
    """Validate one submission against the exact packet it was collected from."""
    if not isinstance(packet, AnnotationPacket):
        raise TypeError("packet must be an AnnotationPacket")
    document = _require_mapping_keys(payload, "annotation submission", _SUBMISSION_KEYS)
    contract_version = require_text(document["contract_version"], "contract_version")
    if contract_version != ANNOTATION_CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {ANNOTATION_CONTRACT_VERSION!r}")

    raw_judgments = document["judgments"]
    if isinstance(raw_judgments, (str, bytes, bytearray)) or not isinstance(
        raw_judgments, Sequence
    ):
        raise TypeError("judgments must be a sequence of judgment mappings")
    judgments = tuple(_parse_judgment(item) for item in raw_judgments)
    if not judgments:
        raise ValueError("judgments must not be empty")
    _validate_coverage(packet, [judgment.query_id for judgment in judgments])

    submission = AnnotationSubmission(
        annotator_id=document["annotator_id"],  # type: ignore[arg-type]
        query_set_sha256=document["query_set_sha256"],  # type: ignore[arg-type]
        manifest_sha256=document["manifest_sha256"],  # type: ignore[arg-type]
        packet_sha256=document["packet_sha256"],  # type: ignore[arg-type]
        judgments=judgments,
    )
    if submission.query_set_sha256 != packet.query_set_sha256:
        raise ValueError("query_set_sha256 does not match the annotated query set")
    if submission.manifest_sha256 != packet.manifest_sha256:
        raise ValueError("manifest_sha256 does not match the annotation packet")
    if submission.packet_sha256 != packet.document_sha256:
        raise ValueError("packet_sha256 does not match the annotation packet")
    _validate_evidence_membership(packet, submission)
    return submission


@dataclass(frozen=True, slots=True)
class PairwiseAgreement:
    """Pre-adjudication agreement between two annotators."""

    annotator_ids: tuple[str, str]
    query_count: int
    support_agreement_count: int
    support_agreement_rate: float
    cohen_kappa: float | None
    cohen_kappa_undefined_reason: str | None
    evidence_exact_match_rate: float
    evidence_mean_jaccard: float
    disagreement_query_ids: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "annotator_ids": list(self.annotator_ids),
            "cohen_kappa": self.cohen_kappa,
            "cohen_kappa_undefined_reason": self.cohen_kappa_undefined_reason,
            "disagreement_query_ids": list(self.disagreement_query_ids),
            "evidence_exact_match_rate": self.evidence_exact_match_rate,
            "evidence_mean_jaccard": self.evidence_mean_jaccard,
            "query_count": self.query_count,
            "support_agreement_count": self.support_agreement_count,
            "support_agreement_rate": self.support_agreement_rate,
        }


def _jaccard(first: Sequence[str], second: Sequence[str]) -> float:
    first_set = set(first)
    second_set = set(second)
    union = first_set | second_set
    if not union:
        return 1.0
    return len(first_set & second_set) / len(union)


def compare_annotation_submissions(
    first: AnnotationSubmission, second: AnnotationSubmission
) -> PairwiseAgreement:
    """Compare two distinct-annotator submissions; never resolve disagreements here."""
    for name, submission in (("first", first), ("second", second)):
        if not isinstance(submission, AnnotationSubmission):
            raise TypeError(f"{name} submission must be an AnnotationSubmission")
    if first.annotator_id == second.annotator_id:
        raise ValueError("annotator_id values must be distinct across submissions")
    if first.query_set_sha256 != second.query_set_sha256:
        raise ValueError("submissions must share one query_set_sha256")
    if first.packet_sha256 != second.packet_sha256:
        raise ValueError("submissions must share one packet_sha256")

    first_map = first.judgment_map()
    second_map = second.judgment_map()
    if set(first_map) != set(second_map):
        raise ValueError("submissions must cover exactly the same query_id values")
    query_ids = sorted(first_map)

    agreements = 0
    evidence_matches = 0
    jaccard_total = 0.0
    disagreements: list[str] = []
    first_counts = dict.fromkeys(SUPPORT_JUDGMENTS, 0)
    second_counts = dict.fromkeys(SUPPORT_JUDGMENTS, 0)
    for query_id in query_ids:
        left = first_map[query_id]
        right = second_map[query_id]
        first_counts[left.support] += 1
        second_counts[right.support] += 1
        support_matches = left.support is right.support
        evidence_matches_exactly = tuple(left.evidence_refs) == tuple(right.evidence_refs)
        if support_matches:
            agreements += 1
        if evidence_matches_exactly:
            evidence_matches += 1
        jaccard_total += _jaccard(left.evidence_refs, right.evidence_refs)
        if not support_matches or not evidence_matches_exactly:
            disagreements.append(query_id)

    query_count = len(query_ids)
    observed = agreements / query_count
    expected = sum(
        (first_counts[judgment] / query_count) * (second_counts[judgment] / query_count)
        for judgment in SUPPORT_JUDGMENTS
    )
    if expected >= 1.0:
        kappa: float | None = None
        reason: str | None = (
            "expected agreement is 1.0 because both annotators used a single support "
            "judgment, so Cohen's kappa is undefined"
        )
    else:
        kappa = (observed - expected) / (1.0 - expected)
        reason = None

    return PairwiseAgreement(
        annotator_ids=(first.annotator_id, second.annotator_id),
        query_count=query_count,
        support_agreement_count=agreements,
        support_agreement_rate=observed,
        cohen_kappa=kappa,
        cohen_kappa_undefined_reason=reason,
        evidence_exact_match_rate=evidence_matches / query_count,
        evidence_mean_jaccard=jaccard_total / query_count,
        disagreement_query_ids=tuple(disagreements),
    )


@dataclass(frozen=True, slots=True)
class AgreementReport:
    """Pre-adjudication agreement across every annotator pair."""

    annotator_ids: tuple[str, ...]
    query_set_sha256: str
    manifest_sha256: str
    packet_sha256: str
    query_count: int
    pairs: tuple[PairwiseAgreement, ...]
    unanimous_support_query_count: int
    unanimous_evidence_query_count: int

    def to_document(self) -> dict[str, object]:
        return {
            "annotator_ids": list(self.annotator_ids),
            "contract_version": ANNOTATION_CONTRACT_VERSION,
            "manifest_sha256": self.manifest_sha256,
            "packet_sha256": self.packet_sha256,
            "pairs": [pair.to_document() for pair in self.pairs],
            "query_count": self.query_count,
            "query_set_sha256": self.query_set_sha256,
            "unanimous_evidence_query_count": self.unanimous_evidence_query_count,
            "unanimous_support_query_count": self.unanimous_support_query_count,
        }

    def to_json(self) -> str:
        """Return the canonical agreement-report JSON for the issued evidence record."""
        return canonical_json(self.to_document())


def build_agreement_report(
    submissions: Sequence[AnnotationSubmission], *, packet: AnnotationPacket
) -> AgreementReport:
    """Report every annotator pair, after binding each submission to the exact packet."""
    if not isinstance(packet, AnnotationPacket):
        raise TypeError("packet must be an AnnotationPacket")
    if isinstance(submissions, (str, bytes, bytearray)) or not isinstance(submissions, Sequence):
        raise TypeError("submissions must be a sequence of AnnotationSubmission instances")
    ordered = tuple(submissions)
    if not all(isinstance(submission, AnnotationSubmission) for submission in ordered):
        raise TypeError("submissions must be a sequence of AnnotationSubmission instances")
    if len(ordered) < 2:
        raise ValueError("agreement reporting requires at least two submissions")
    annotator_ids = tuple(submission.annotator_id for submission in ordered)
    if len(set(annotator_ids)) != len(annotator_ids):
        raise ValueError("annotator_id values must be distinct across submissions")
    for submission in ordered:
        if submission.query_set_sha256 != packet.query_set_sha256:
            raise ValueError("query_set_sha256 does not match the annotation packet")
        if submission.manifest_sha256 != packet.manifest_sha256:
            raise ValueError("manifest_sha256 does not match the annotation packet")
        if submission.packet_sha256 != packet.document_sha256:
            raise ValueError("packet_sha256 does not match the annotation packet")
        _validate_coverage(packet, [judgment.query_id for judgment in submission.judgments])
        _validate_evidence_membership(packet, submission)

    pairs = tuple(
        compare_annotation_submissions(first, second) for first, second in combinations(ordered, 2)
    )
    maps = [submission.judgment_map() for submission in ordered]
    query_ids = sorted(maps[0])
    unanimous_support = 0
    unanimous_evidence = 0
    for query_id in query_ids:
        supports = {judgments[query_id].support for judgments in maps}
        evidences = {tuple(judgments[query_id].evidence_refs) for judgments in maps}
        if len(supports) == 1:
            unanimous_support += 1
        if len(evidences) == 1:
            unanimous_evidence += 1

    return AgreementReport(
        annotator_ids=annotator_ids,
        query_set_sha256=ordered[0].query_set_sha256,
        manifest_sha256=ordered[0].manifest_sha256,
        packet_sha256=ordered[0].packet_sha256,
        query_count=len(query_ids),
        pairs=pairs,
        unanimous_support_query_count=unanimous_support,
        unanimous_evidence_query_count=unanimous_evidence,
    )


def load_annotation_submission(path: Path, *, packet: AnnotationPacket) -> AnnotationSubmission:
    """Load one submission JSON file with strict duplicate-key handling."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys
    )
    return parse_annotation_submission(payload, packet=packet)
