"""Immutable shared S1–S4 evaluation-harness contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias, cast

from mfg_agentgraph.stage_instrumentation import StageEvent

_MAX_IDENTIFIER_BYTES = 1_024
_MAX_ERROR_MESSAGE_BYTES = 8_192
_MAX_SIGNED_INT64 = 9_223_372_036_854_775_807
_SHA256_HEX_LENGTH = 64
_LOWERCASE_HEX = frozenset("0123456789abcdef")

FrozenJsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | tuple["FrozenJsonValue", ...]
    | Mapping[str, "FrozenJsonValue"]
)


class EvaluationStrategy(StrEnum):
    """Architecture V1 strategies that share one evaluation record schema."""

    S1 = "s1"
    S2 = "s2"
    S3 = "s3"
    S4 = "s4"


class ArtifactKind(StrEnum):
    """Cross-strategy artifacts whose availability must be explicit."""

    ANSWER = "answer"
    RETRIEVED_CONTEXT = "retrieved_context"
    VALIDATION_REPORT = "validation_report"
    PROVENANCE_TRACE = "provenance_trace"


class ArtifactApplicability(StrEnum):
    """Whether a strategy produced a standard artifact."""

    PRESENT = "present"
    NOT_APPLICABLE = "not_applicable"


def _require_text(
    value: object, field_name: str, *, maximum_bytes: int = _MAX_IDENTIFIER_BYTES
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field_name} exceeds {maximum_bytes} UTF-8 bytes")
    return normalized


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if value > _MAX_SIGNED_INT64:
        raise ValueError(f"{field_name} exceeds signed 64-bit maximum")
    return value


def _freeze_json(value: object, field_name: str) -> FrozenJsonValue:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must not contain a non-finite number")
        return value
    if isinstance(value, Mapping):
        frozen_items: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            normalized_key = _require_text(key, f"{field_name} key")
            if normalized_key in frozen_items:
                raise ValueError(
                    f"{field_name} contains duplicate normalized key {normalized_key!r}"
                )
            frozen_items[normalized_key] = _freeze_json(item, f"{field_name}.{normalized_key}")
        return MappingProxyType(dict(sorted(frozen_items.items())))
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(_freeze_json(item, field_name) for item in value)
    raise TypeError(f"{field_name} must be JSON-safe")


def _json_data(value: FrozenJsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EvaluationRunConfiguration:
    """Controlled configuration common to every S1–S4 run."""

    strategy: EvaluationStrategy
    dataset_id: str
    query_set_id: str
    model_configuration_id: str
    retrieval_configuration_id: str
    random_seed: int
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, EvaluationStrategy):
            raise TypeError("strategy must be an EvaluationStrategy")
        for field_name in (
            "dataset_id",
            "query_set_id",
            "model_configuration_id",
            "retrieval_configuration_id",
        ):
            object.__setattr__(
                self, field_name, _require_text(getattr(self, field_name), field_name)
            )
        object.__setattr__(self, "random_seed", _require_int(self.random_seed, "random_seed"))
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        frozen = _freeze_json(self.parameters, "parameters")
        if not isinstance(frozen, Mapping):  # pragma: no cover - narrowed from Mapping input above.
            raise TypeError("parameters must be a mapping")
        object.__setattr__(self, "parameters", frozen)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "model_configuration_id": self.model_configuration_id,
            "parameters": _json_data(cast(FrozenJsonValue, self.parameters)),
            "query_set_id": self.query_set_id,
            "random_seed": self.random_seed,
            "retrieval_configuration_id": self.retrieval_configuration_id,
            "strategy": self.strategy.value,
        }


@dataclass(frozen=True, slots=True)
class EvaluationRunManifest:
    """Immutable provenance for one comparable evaluation run."""

    run_id: str
    repository_revision: str
    harness_version: str
    dataset_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("run_id", "repository_revision", "harness_version"):
            object.__setattr__(
                self, field_name, _require_text(getattr(self, field_name), field_name)
            )
        digest = _require_text(self.dataset_sha256, "dataset_sha256")
        if len(digest) != _SHA256_HEX_LENGTH or any(
            character not in _LOWERCASE_HEX for character in digest
        ):
            raise ValueError("dataset_sha256 must be 64 lowercase hexadecimal characters")
        object.__setattr__(self, "dataset_sha256", digest)

    def to_dict(self) -> dict[str, str]:
        return {
            "dataset_sha256": self.dataset_sha256,
            "harness_version": self.harness_version,
            "repository_revision": self.repository_revision,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class EvaluationError:
    """Typed, serializable evaluation failure captured in a result record."""

    code: str
    message: str
    field: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_text(self.code, "code"))
        object.__setattr__(
            self,
            "message",
            _require_text(self.message, "message", maximum_bytes=_MAX_ERROR_MESSAGE_BYTES),
        )
        if self.field is not None:
            object.__setattr__(self, "field", _require_text(self.field, "field"))

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "field": self.field, "message": self.message}


@dataclass(frozen=True, slots=True)
class EvaluationArtifact:
    """One standard artifact, explicitly present or not applicable."""

    kind: ArtifactKind
    applicability: ArtifactApplicability
    value: object | None
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ArtifactKind):
            raise TypeError("kind must be an ArtifactKind")
        if not isinstance(self.applicability, ArtifactApplicability):
            raise TypeError("applicability must be an ArtifactApplicability")
        if self.applicability is ArtifactApplicability.PRESENT:
            if self.reason is not None:
                raise ValueError("present artifact must not include a reason")
            object.__setattr__(self, "value", _freeze_json(self.value, "value"))
            return
        if self.value is not None:
            raise ValueError("not-applicable artifact must not include a value")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))

    def to_dict(self) -> dict[str, object]:
        return {
            "applicability": self.applicability.value,
            "kind": self.kind.value,
            "reason": self.reason,
            "value": _json_data(cast(FrozenJsonValue, self.value))
            if self.value is not None
            else None,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """One strategy result using the canonical shared S1–S4 schema."""

    configuration: EvaluationRunConfiguration
    manifest: EvaluationRunManifest
    query_id: str
    raw_output: object
    errors: Sequence[EvaluationError]
    artifacts: Sequence[EvaluationArtifact]
    schema_version: str = "mfg-agentgraph-evaluation-result-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, EvaluationRunConfiguration):
            raise TypeError("configuration must be an EvaluationRunConfiguration")
        if not isinstance(self.manifest, EvaluationRunManifest):
            raise TypeError("manifest must be an EvaluationRunManifest")
        object.__setattr__(self, "query_id", _require_text(self.query_id, "query_id"))
        object.__setattr__(self, "raw_output", _freeze_json(self.raw_output, "raw_output"))
        object.__setattr__(
            self, "schema_version", _require_text(self.schema_version, "schema_version")
        )
        object.__setattr__(self, "errors", self._normalize_errors(self.errors))
        object.__setattr__(self, "artifacts", self._normalize_artifacts(self.artifacts))

    @staticmethod
    def _normalize_errors(values: Sequence[EvaluationError]) -> tuple[EvaluationError, ...]:
        if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
            raise TypeError("errors must be a sequence of EvaluationError instances")
        normalized = tuple(values)
        if not all(isinstance(value, EvaluationError) for value in normalized):
            raise TypeError("errors must be a sequence of EvaluationError instances")
        return normalized

    @staticmethod
    def _normalize_artifacts(
        values: Sequence[EvaluationArtifact],
    ) -> tuple[EvaluationArtifact, ...]:
        if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
            raise TypeError("artifacts must be a sequence of EvaluationArtifact instances")
        normalized = tuple(values)
        if not all(isinstance(value, EvaluationArtifact) for value in normalized):
            raise TypeError("artifacts must be a sequence of EvaluationArtifact instances")
        if tuple(artifact.kind for artifact in normalized) != tuple(ArtifactKind):
            raise ValueError(
                "artifacts must contain each ArtifactKind exactly once in canonical order"
            )
        return normalized

    def to_dict(self) -> dict[str, object]:
        return {
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "configuration": self.configuration.to_dict(),
            "errors": [error.to_dict() for error in self.errors],
            "manifest": self.manifest.to_dict(),
            "query_id": self.query_id,
            "raw_output": _json_data(cast(FrozenJsonValue, self.raw_output)),
            "schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        """Return canonical JSON for persisted comparison records."""
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def errors_from_events(events: Sequence[StageEvent]) -> tuple[EvaluationError, ...]:
    """Convert stage-event errors into typed record errors shared by every strategy."""
    collected: list[EvaluationError] = []
    for event in events:
        for stage_error in event.errors:
            detail = stage_error.detail
            message = detail if detail else f"{event.stage.value}: {stage_error.code.value}"
            collected.append(
                EvaluationError(
                    code=stage_error.code.value,
                    field=stage_error.field,
                    message=message,
                )
            )
    return tuple(collected)


def dataset_sha256_from_configuration(configuration: EvaluationRunConfiguration) -> str:
    """Return the required dataset digest recorded in one controlled configuration."""
    if not isinstance(configuration, EvaluationRunConfiguration):
        raise TypeError("configuration must be an EvaluationRunConfiguration")
    value = configuration.parameters.get("dataset_sha256")
    if value is None:
        raise ValueError("configuration parameters must include a dataset_sha256 digest")
    if type(value) is not str:
        raise TypeError("dataset_sha256 parameter must be a string")
    if not value:
        raise ValueError("configuration parameters must include a dataset_sha256 digest")
    return value
