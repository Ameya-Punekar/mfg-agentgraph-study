from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any

import pytest

from mfg_agentgraph.operator_request import (
    NormalizedOperatorRequest,
    RequestValidationCode,
    RequestValidationFailure,
    normalize_operator_request,
)


def test_valid_request_returns_immutable_normalized_request() -> None:
    result = normalize_operator_request(
        {
            "query_text": "What caused Pump 12 vibration?",
            "timestamp": "2026-08-23T18:45:00+00:00",
            "run_id": "run-001",
        }
    )

    assert result == NormalizedOperatorRequest(
        query_text="What caused Pump 12 vibration?",
        timestamp=datetime(2026, 8, 23, 18, 45, tzinfo=UTC),
        run_id="run-001",
        asset_hints=(),
        sensor_hints=(),
    )


def test_normalizes_whitespace_timezone_and_ordered_hints_without_mutating_input() -> None:
    raw = {
        "query_text": "  Why did Pump 12   vibrate?  ",
        "timestamp": "  2026-08-23T20:15:00+02:00  ",
        "run_id": "  operator-run  ",
        "asset_hints": [" Pump_12 ", " Bearing_A "],
        "sensor_hints": [" vib_x ", " temp_y "],
    }
    original = {
        "query_text": "  Why did Pump 12   vibrate?  ",
        "timestamp": "  2026-08-23T20:15:00+02:00  ",
        "run_id": "  operator-run  ",
        "asset_hints": [" Pump_12 ", " Bearing_A "],
        "sensor_hints": [" vib_x ", " temp_y "],
    }

    result = normalize_operator_request(raw)

    assert result == NormalizedOperatorRequest(
        query_text="Why did Pump 12   vibrate?",
        timestamp=datetime(2026, 8, 23, 18, 15, tzinfo=UTC),
        run_id="operator-run",
        asset_hints=("Pump_12", "Bearing_A"),
        sensor_hints=("vib_x", "temp_y"),
    )
    assert raw == original


@pytest.mark.parametrize(
    ("raw", "expected_code", "expected_field"),
    [
        ([], RequestValidationCode.NOT_MAPPING, None),
        (
            {"timestamp": "2026-08-23T18:45:00+00:00", "run_id": "run-001"},
            RequestValidationCode.MISSING_FIELD,
            "query_text",
        ),
        (
            {"query_text": 12, "timestamp": "2026-08-23T18:45:00+00:00", "run_id": "run-001"},
            RequestValidationCode.INVALID_FIELD_TYPE,
            "query_text",
        ),
        (
            {"query_text": "   ", "timestamp": "2026-08-23T18:45:00+00:00", "run_id": "run-001"},
            RequestValidationCode.BLANK_FIELD,
            "query_text",
        ),
        (
            {"query_text": "Query", "run_id": "run-001"},
            RequestValidationCode.MISSING_FIELD,
            "timestamp",
        ),
        (
            {"query_text": "Query", "timestamp": 12, "run_id": "run-001"},
            RequestValidationCode.INVALID_FIELD_TYPE,
            "timestamp",
        ),
        (
            {"query_text": "Query", "timestamp": "", "run_id": "run-001"},
            RequestValidationCode.BLANK_FIELD,
            "timestamp",
        ),
        (
            {"query_text": "Query", "timestamp": "not-a-timestamp", "run_id": "run-001"},
            RequestValidationCode.MALFORMED_TIMESTAMP,
            "timestamp",
        ),
        (
            {"query_text": "Query", "timestamp": "2026-08-23T18:45:00", "run_id": "run-001"},
            RequestValidationCode.NAIVE_TIMESTAMP,
            "timestamp",
        ),
        (
            {"query_text": "Query", "timestamp": "2026-08-23T18:45:00+00:00"},
            RequestValidationCode.MISSING_FIELD,
            "run_id",
        ),
        (
            {"query_text": "Query", "timestamp": "2026-08-23T18:45:00+00:00", "run_id": 12},
            RequestValidationCode.INVALID_FIELD_TYPE,
            "run_id",
        ),
        (
            {"query_text": "Query", "timestamp": "2026-08-23T18:45:00+00:00", "run_id": ""},
            RequestValidationCode.BLANK_FIELD,
            "run_id",
        ),
        (
            {
                "query_text": "Query",
                "timestamp": "2026-08-23T18:45:00+00:00",
                "run_id": "run-001",
                "asset_hints": "Pump_12",
            },
            RequestValidationCode.INVALID_HINT_CONTAINER,
            "asset_hints",
        ),
        (
            {
                "query_text": "Query",
                "timestamp": "2026-08-23T18:45:00+00:00",
                "run_id": "run-001",
                "asset_hints": ["Pump_12", "  "],
            },
            RequestValidationCode.BLANK_HINT,
            "asset_hints",
        ),
        (
            {
                "query_text": "Query",
                "timestamp": "2026-08-23T18:45:00+00:00",
                "run_id": "run-001",
                "sensor_hints": ["vib_x", 12],
            },
            RequestValidationCode.INVALID_HINT_VALUE,
            "sensor_hints",
        ),
    ],
)
def test_malformed_requests_return_typed_first_failure(
    raw: object,
    expected_code: RequestValidationCode,
    expected_field: str | None,
) -> None:
    result = normalize_operator_request(raw)

    assert result == RequestValidationFailure(code=expected_code, field=expected_field)


def test_validation_order_returns_first_required_failure() -> None:
    raw: dict[str, Any] = {
        "query_text": "",
        "timestamp": "not-a-timestamp",
        "run_id": "",
        "asset_hints": "Pump_12",
    }

    result = normalize_operator_request(raw)

    assert result == RequestValidationFailure(
        code=RequestValidationCode.BLANK_FIELD,
        field="query_text",
    )


def _try_assign_attribute(instance: object, field: str) -> None:
    setattr(instance, field, "changed")


def test_normalized_request_and_failure_are_frozen_and_slotted() -> None:
    request = normalize_operator_request(
        {
            "query_text": "Query",
            "timestamp": "2026-08-23T18:45:00+00:00",
            "run_id": "run-001",
        }
    )
    failure = normalize_operator_request([])

    assert isinstance(request, NormalizedOperatorRequest)
    assert isinstance(failure, RequestValidationFailure)
    assert not hasattr(request, "__dict__")
    assert not hasattr(failure, "__dict__")
    with pytest.raises(FrozenInstanceError):
        _try_assign_attribute(request, "run_id")
    with pytest.raises(FrozenInstanceError):
        _try_assign_attribute(failure, "field")
