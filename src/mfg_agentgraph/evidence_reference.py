"""Stable evidence reference contract for KG and document support."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

_MAX_IDENTIFIER_BYTES = 1_024
_MAX_EVIDENCE_ID_BYTES = 8_192


class EvidenceKind(StrEnum):
    """Typed evidence sources that later S4 contracts may cite."""

    KG_RESOURCE = "kg_resource"
    KG_EDGE = "kg_edge"
    DOCUMENT_CHUNK = "document_chunk"


class EvidenceValidationStatus(StrEnum):
    """Validation states separating lookup from support selection."""

    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    INVALID = "invalid"


class EvidenceReferenceResolutionCode(StrEnum):
    """Stable machine-readable evidence catalog failure codes."""

    DUPLICATE_EVIDENCE_ID = "duplicate_evidence_id"
    UNKNOWN_EVIDENCE_ID = "unknown_evidence_id"
    EVIDENCE_NOT_VALIDATED = "evidence_not_validated"


def _require_nonblank(
    value: object,
    field_name: str,
    *,
    max_bytes: int = _MAX_IDENTIFIER_BYTES,
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be nonblank")
    if len(stripped.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} exceeds the identifier byte limit")
    return stripped


def _is_non_bool_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _normalize_requested_ids(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings")
    return tuple(
        _require_nonblank(value, field_name, max_bytes=_MAX_EVIDENCE_ID_BYTES) for value in values
    )


class EvidenceReferenceResolutionError(ValueError):
    """Deterministic fail-closed evidence catalog resolution error."""

    __slots__ = ("code", "stable_id")

    def __init__(self, code: EvidenceReferenceResolutionCode, stable_id: str) -> None:
        if not isinstance(code, EvidenceReferenceResolutionCode):
            raise TypeError("code must be an EvidenceReferenceResolutionCode")
        normalized_stable_id = _require_nonblank(
            stable_id,
            "stable_id",
            max_bytes=_MAX_EVIDENCE_ID_BYTES,
        )
        self.code = code
        self.stable_id = normalized_stable_id
        super().__init__(f"{self.code.value}: {self.stable_id}")


@dataclass(frozen=True, slots=True)
class RetrievalMetadata:
    """Minimal stable retrieval context carried by an evidence reference."""

    retrieval_run_id: str
    query_id: str
    retriever_name: str
    rank: int
    score: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "retrieval_run_id",
            _require_nonblank(self.retrieval_run_id, "retrieval_run_id"),
        )
        object.__setattr__(self, "query_id", _require_nonblank(self.query_id, "query_id"))
        object.__setattr__(
            self,
            "retriever_name",
            _require_nonblank(self.retriever_name, "retriever_name"),
        )
        if not _is_non_bool_int(self.rank):
            raise TypeError("rank must be an int")
        if self.rank < 1:
            raise ValueError("rank must be positive")
        if self.score is not None:
            if not isinstance(self.score, int | float) or isinstance(self.score, bool):
                raise TypeError("score must be a finite float or None")
            normalized_score = float(self.score)
            if not isfinite(normalized_score):
                raise ValueError("score must be finite")
            object.__setattr__(self, "score", normalized_score)


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Immutable reference to one known KG resource, KG edge, or document chunk."""

    kind: EvidenceKind
    source: str
    stable_id: str
    retrieval: RetrievalMetadata
    validation_status: EvidenceValidationStatus

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EvidenceKind):
            raise TypeError("kind must be an EvidenceKind")
        object.__setattr__(self, "source", _require_nonblank(self.source, "source"))
        object.__setattr__(
            self,
            "stable_id",
            _require_nonblank(
                self.stable_id,
                "stable_id",
                max_bytes=_MAX_EVIDENCE_ID_BYTES,
            ),
        )
        if not isinstance(self.retrieval, RetrievalMetadata):
            raise TypeError("retrieval must be RetrievalMetadata")
        if not isinstance(self.validation_status, EvidenceValidationStatus):
            raise TypeError("validation_status must be an EvidenceValidationStatus")


@dataclass(frozen=True, slots=True)
class EvidenceCatalog:
    """Explicit tuple-backed catalog for resolving stable evidence identifiers."""

    references: Sequence[EvidenceReference] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.references, str) or not isinstance(self.references, Sequence):
            raise TypeError("references must be a sequence of EvidenceReference instances")
        normalized: list[EvidenceReference] = []
        seen: set[str] = set()
        for reference in self.references:
            if not isinstance(reference, EvidenceReference):
                raise TypeError("references must contain EvidenceReference instances")
            if reference.stable_id in seen:
                raise EvidenceReferenceResolutionError(
                    EvidenceReferenceResolutionCode.DUPLICATE_EVIDENCE_ID,
                    reference.stable_id,
                )
            seen.add(reference.stable_id)
            normalized.append(reference)
        object.__setattr__(self, "references", tuple(normalized))

    def resolve(self, stable_ids: Sequence[str]) -> tuple[EvidenceReference, ...]:
        """Resolve known evidence IDs in caller-requested order."""

        requested_ids = _normalize_requested_ids(stable_ids, "stable_ids")
        resolved: list[EvidenceReference] = []
        for stable_id in requested_ids:
            reference = self._find(stable_id)
            if reference is None:
                raise EvidenceReferenceResolutionError(
                    EvidenceReferenceResolutionCode.UNKNOWN_EVIDENCE_ID,
                    stable_id,
                )
            resolved.append(reference)
        return tuple(resolved)

    def resolve_validated_support(self, stable_ids: Sequence[str]) -> tuple[EvidenceReference, ...]:
        """Resolve IDs only when each reference is validated support."""

        references = self.resolve(stable_ids)
        for reference in references:
            if reference.validation_status is not EvidenceValidationStatus.VALIDATED:
                raise EvidenceReferenceResolutionError(
                    EvidenceReferenceResolutionCode.EVIDENCE_NOT_VALIDATED,
                    reference.stable_id,
                )
        return references

    def _find(self, stable_id: str) -> EvidenceReference | None:
        for reference in self.references:
            if reference.stable_id == stable_id:
                return reference
        return None
