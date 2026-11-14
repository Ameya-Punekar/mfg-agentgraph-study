"""Typed S4 stage instrumentation contract.

This module defines the immutable event shape that later orchestration code can emit.
It intentionally does not perform orchestration, persistence, timing, or evidence-ID validation.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

_MAX_IDENTIFIER_BYTES = 1_024
_MAX_EVIDENCE_ID_BYTES = 8_192
_MAX_SIGNED_INT64 = 9_223_372_036_854_775_807


class StageName(StrEnum):
    """Canonical Architecture V1 S4 pipeline stage names."""

    ENTITY_ASSET_RESOLUTION = "entity_asset_resolution"
    STRUCTURED_RETRIEVAL = "structured_retrieval"
    PROCEDURAL_RETRIEVAL = "procedural_retrieval"
    CANDIDATE_GENERATION = "candidate_generation"
    RDF_REIFICATION = "rdf_reification"
    SHACL_VALIDATION = "shacl_validation"
    BOUNDED_REPAIR = "bounded_repair"
    EXPLICIT_FALLBACK = "explicit_fallback"
    EVIDENCE_PACKAGE_ASSEMBLY = "evidence_package_assembly"
    PROV_O_TRACE_WRITING = "prov_o_trace_writing"


class TerminalStatus(StrEnum):
    """Typed terminal/fallback statuses exposed by bounded S4 execution."""

    PASSED = "passed"
    OPERATOR_DISAMBIGUATION_REQUIRED = "operator_disambiguation_required"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED_LOWER_RANK = "unsupported_lower_rank"
    VALIDATION_FAILED_CLOSED = "validation_failed_closed"
    PROVENANCE_FAILED_CLOSED = "provenance_failed_closed"


class StageErrorCode(StrEnum):
    """Stable machine-readable stage error categories."""

    INVALID_STAGE_EVENT = "invalid_stage_event"
    CANDIDATE_GENERATION_FAILED = "candidate_generation_failed"
    OPERATOR_DISAMBIGUATION_REQUIRED = "operator_disambiguation_required"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED_LOWER_RANK = "unsupported_lower_rank"
    VALIDATION_CONSTRAINT_FAILED = "validation_constraint_failed"
    REPAIR_ATTEMPT_FAILED = "repair_attempt_failed"
    INVALID_EVIDENCE_PACKAGE = "invalid_evidence_package"
    PROVENANCE_WRITE_FAILED = "provenance_write_failed"


CANONICAL_S4_STAGE_NAMES: tuple[StageName, ...] = tuple(StageName)
TERMINAL_STATUSES: tuple[TerminalStatus, ...] = tuple(TerminalStatus)


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


def _normalize_ids(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    if not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings")
    normalized: list[str] = []
    for value in values:
        normalized.append(_require_nonblank(value, field_name, max_bytes=_MAX_EVIDENCE_ID_BYTES))
    return tuple(normalized)


def _is_non_bool_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class StageError:
    """Typed error attached to an immutable stage event."""

    code: StageErrorCode
    field: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, StageErrorCode):
            raise TypeError("code must be a StageErrorCode")
        if self.field is not None:
            object.__setattr__(self, "field", _require_nonblank(self.field, "field"))
        if self.detail is not None:
            object.__setattr__(self, "detail", _require_nonblank(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class StageEvent:
    """Immutable typed event for one canonical S4 pipeline stage."""

    stage: StageName
    run_id: str
    status: TerminalStatus
    duration_ms: int | None = None
    input_ids: Sequence[str] = field(default_factory=tuple)
    output_ids: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[StageError] = field(default_factory=tuple)
    retry_count: int = 0
    repair_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.stage, StageName):
            raise TypeError("stage must be a StageName")
        if not isinstance(self.status, TerminalStatus):
            raise TypeError("status must be a TerminalStatus")
        object.__setattr__(self, "run_id", _require_nonblank(self.run_id, "run_id"))
        if self.duration_ms is not None:
            if not _is_non_bool_int(self.duration_ms):
                raise TypeError("duration_ms must be an int or None")
            if self.duration_ms < 0:
                raise ValueError("duration_ms must be nonnegative")
            if self.duration_ms > _MAX_SIGNED_INT64:
                raise ValueError("duration_ms exceeds signed 64-bit maximum")
        object.__setattr__(self, "input_ids", _normalize_ids(self.input_ids, "input_ids"))
        object.__setattr__(self, "output_ids", _normalize_ids(self.output_ids, "output_ids"))
        object.__setattr__(self, "errors", self._normalize_errors(self.errors))
        self._validate_nonnegative_counter(self.retry_count, "retry_count")
        self._validate_nonnegative_counter(self.repair_count, "repair_count")

    @staticmethod
    def _normalize_errors(errors: Sequence[StageError]) -> tuple[StageError, ...]:
        if isinstance(errors, str) or not isinstance(errors, Sequence):
            raise TypeError("errors must be a sequence of StageError instances")
        normalized: list[StageError] = []
        for error in errors:
            if not isinstance(error, StageError):
                raise TypeError("errors must contain StageError instances")
            normalized.append(error)
        return tuple(normalized)

    @staticmethod
    def _validate_nonnegative_counter(value: int, field_name: str) -> None:
        if not _is_non_bool_int(value):
            raise TypeError(f"{field_name} must be an int")
        if value < 0:
            raise ValueError(f"{field_name} must be nonnegative")
        if value > _MAX_SIGNED_INT64:
            raise ValueError(f"{field_name} exceeds signed 64-bit maximum")
