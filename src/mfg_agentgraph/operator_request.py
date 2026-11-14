"""Operator request normalization contract."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class RequestValidationCode(StrEnum):
    """Stable machine-readable request validation failure codes."""

    NOT_MAPPING = "not_mapping"
    MISSING_FIELD = "missing_field"
    INVALID_FIELD_TYPE = "invalid_field_type"
    BLANK_FIELD = "blank_field"
    MALFORMED_TIMESTAMP = "malformed_timestamp"
    NAIVE_TIMESTAMP = "naive_timestamp"
    INVALID_HINT_CONTAINER = "invalid_hint_container"
    INVALID_HINT_VALUE = "invalid_hint_value"
    BLANK_HINT = "blank_hint"


@dataclass(frozen=True, slots=True)
class RequestValidationFailure:
    """Typed request validation failure."""

    code: RequestValidationCode
    field: str | None


@dataclass(frozen=True, slots=True)
class NormalizedOperatorRequest:
    """Validated operator request normalized for S4 entry points."""

    query_text: str
    timestamp: datetime
    run_id: str
    asset_hints: tuple[str, ...]
    sensor_hints: tuple[str, ...]


def _required_text(
    request: Mapping[object, object],
    field: str,
) -> str | RequestValidationFailure:
    if field not in request:
        return RequestValidationFailure(RequestValidationCode.MISSING_FIELD, field)
    value = request[field]
    if not isinstance(value, str):
        return RequestValidationFailure(RequestValidationCode.INVALID_FIELD_TYPE, field)
    normalized = value.strip()
    if not normalized:
        return RequestValidationFailure(RequestValidationCode.BLANK_FIELD, field)
    return normalized


def _required_timestamp(
    request: Mapping[object, object],
) -> datetime | RequestValidationFailure:
    field = "timestamp"
    if field not in request:
        return RequestValidationFailure(RequestValidationCode.MISSING_FIELD, field)
    value = request[field]
    if not isinstance(value, str):
        return RequestValidationFailure(RequestValidationCode.INVALID_FIELD_TYPE, field)
    normalized = value.strip()
    if not normalized:
        return RequestValidationFailure(RequestValidationCode.BLANK_FIELD, field)
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        return RequestValidationFailure(RequestValidationCode.MALFORMED_TIMESTAMP, field)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return RequestValidationFailure(RequestValidationCode.NAIVE_TIMESTAMP, field)
    return timestamp.astimezone(UTC)


def _normalize_hints(
    request: Mapping[object, object],
    field: str,
) -> tuple[str, ...] | RequestValidationFailure:
    if field not in request:
        return ()
    value = request[field]
    if isinstance(value, str) or not isinstance(value, Sequence):
        return RequestValidationFailure(RequestValidationCode.INVALID_HINT_CONTAINER, field)
    normalized_hints: list[str] = []
    for hint in value:
        if not isinstance(hint, str):
            return RequestValidationFailure(RequestValidationCode.INVALID_HINT_VALUE, field)
        normalized = hint.strip()
        if not normalized:
            return RequestValidationFailure(RequestValidationCode.BLANK_HINT, field)
        normalized_hints.append(normalized)
    return tuple(normalized_hints)


def normalize_operator_request(
    raw: object,
) -> NormalizedOperatorRequest | RequestValidationFailure:
    """Normalize an operator request or return the first typed validation failure."""

    if not isinstance(raw, Mapping):
        return RequestValidationFailure(RequestValidationCode.NOT_MAPPING, None)

    query_text = _required_text(raw, "query_text")
    if isinstance(query_text, RequestValidationFailure):
        return query_text

    timestamp = _required_timestamp(raw)
    if isinstance(timestamp, RequestValidationFailure):
        return timestamp

    run_id = _required_text(raw, "run_id")
    if isinstance(run_id, RequestValidationFailure):
        return run_id

    asset_hints = _normalize_hints(raw, "asset_hints")
    if isinstance(asset_hints, RequestValidationFailure):
        return asset_hints

    sensor_hints = _normalize_hints(raw, "sensor_hints")
    if isinstance(sensor_hints, RequestValidationFailure):
        return sensor_hints

    return NormalizedOperatorRequest(
        query_text=query_text,
        timestamp=timestamp,
        run_id=run_id,
        asset_hints=asset_hints,
        sensor_hints=sensor_hints,
    )
