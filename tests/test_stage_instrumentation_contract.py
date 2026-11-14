from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from mfg_agentgraph.stage_instrumentation import (
    CANONICAL_S4_STAGE_NAMES,
    TERMINAL_STATUSES,
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

_MAX_SIGNED_INT64 = 9_223_372_036_854_775_807

_EXPECTED_STAGE_VALUES = (
    "entity_asset_resolution",
    "structured_retrieval",
    "procedural_retrieval",
    "candidate_generation",
    "rdf_reification",
    "shacl_validation",
    "bounded_repair",
    "explicit_fallback",
    "evidence_package_assembly",
    "prov_o_trace_writing",
)

_EXPECTED_TERMINAL_VALUES = (
    "passed",
    "operator_disambiguation_required",
    "insufficient_evidence",
    "unsupported_lower_rank",
    "validation_failed_closed",
    "provenance_failed_closed",
)


def test_all_six_terminal_statuses_are_typed_and_enumerated() -> None:
    assert tuple(status.value for status in TerminalStatus) == _EXPECTED_TERMINAL_VALUES
    assert tuple(TerminalStatus) == TERMINAL_STATUSES
    assert all(isinstance(status, TerminalStatus) for status in TERMINAL_STATUSES)


@pytest.mark.parametrize("status", list(TerminalStatus))
def test_each_terminal_status_can_be_recorded_on_an_immutable_stage_event(
    status: TerminalStatus,
) -> None:
    event = StageEvent(
        stage=StageName.EXPLICIT_FALLBACK,
        run_id="run-001",
        status=status,
        input_ids=("operator-request-001",),
        output_ids=("terminal-response-001",),
    )

    assert event.status is status
    assert event.stage is StageName.EXPLICIT_FALLBACK
    assert event.run_id == "run-001"
    with pytest.raises(FrozenInstanceError):
        event.status = TerminalStatus.PASSED  # type: ignore[misc]


def test_candidate_generation_failed_error_code_is_stable() -> None:
    assert StageErrorCode.CANDIDATE_GENERATION_FAILED.value == "candidate_generation_failed"


def test_all_ten_canonical_s4_stages_are_typed_and_representable() -> None:
    assert tuple(stage.value for stage in StageName) == _EXPECTED_STAGE_VALUES
    assert tuple(StageName) == CANONICAL_S4_STAGE_NAMES

    events = tuple(
        StageEvent(
            stage=stage,
            run_id=f"run-{index}",
            status=TerminalStatus.PASSED,
            output_ids=(f"{stage.value}-event",),
        )
        for index, stage in enumerate(CANONICAL_S4_STAGE_NAMES, start=1)
    )

    assert tuple(event.stage for event in events) == CANONICAL_S4_STAGE_NAMES
    assert all(event.status is TerminalStatus.PASSED for event in events)
    assert StageErrorCode.REPAIR_ATTEMPT_FAILED.value == "repair_attempt_failed"


def test_stage_event_keeps_ids_errors_duration_and_counters_typed_and_immutable() -> None:
    error = StageError(
        code=StageErrorCode.VALIDATION_CONSTRAINT_FAILED,
        field="shacl_report",
        detail="missing validation report",
    )
    event = StageEvent(
        stage=StageName.SHACL_VALIDATION,
        run_id="run-001",
        status=TerminalStatus.VALIDATION_FAILED_CLOSED,
        duration_ms=None,
        input_ids=["candidate-action-001", "support-graph-001"],
        output_ids=["shacl-report-001"],
        errors=[error],
        retry_count=1,
        repair_count=1,
    )

    assert event.input_ids == ("candidate-action-001", "support-graph-001")
    assert event.output_ids == ("shacl-report-001",)
    assert event.errors == (error,)
    assert event.duration_ms is None
    assert event.retry_count == 1
    assert event.repair_count == 1
    assert not hasattr(event, "__dict__")
    assert not hasattr(error, "__dict__")
    with pytest.raises(FrozenInstanceError):
        error.field = "changed"  # type: ignore[misc]


def test_stage_event_enforces_utf8_byte_limits_on_public_ids() -> None:
    event = StageEvent(
        stage=StageName.PROCEDURAL_RETRIEVAL,
        run_id="é" * 512,
        status=TerminalStatus.PASSED,
        input_ids=("é" * 4_096,),
        output_ids=("é" * 4_096,),
    )
    assert len(event.run_id.encode("utf-8")) == 1_024

    with pytest.raises(ValueError, match="run_id exceeds"):
        StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id="é" * 513,
            status=TerminalStatus.PASSED,
        )
    with pytest.raises(ValueError, match="input_ids exceeds"):
        StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            input_ids=("é" * 4_097,),
        )


def test_stage_event_rejects_non_sequence_id_containers() -> None:
    with pytest.raises(TypeError, match="^input_ids must be a sequence of strings$"):
        StageEvent(
            stage=StageName.STRUCTURED_RETRIEVAL,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            input_ids={"asset-001", "asset-002"},  # type: ignore[arg-type]
        )


def test_stage_event_rejects_single_error_as_error_container() -> None:
    error = StageError(code=StageErrorCode.VALIDATION_CONSTRAINT_FAILED)

    with pytest.raises(TypeError, match="^errors must be a sequence of StageError instances$"):
        StageEvent(
            stage=StageName.SHACL_VALIDATION,
            run_id="run-001",
            status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            errors=error,  # type: ignore[arg-type]
        )


def test_stage_event_rejects_none_as_error_container() -> None:
    with pytest.raises(TypeError, match="^errors must be a sequence of StageError instances$"):
        StageEvent(
            stage=StageName.SHACL_VALIDATION,
            run_id="run-001",
            status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            errors=None,  # type: ignore[arg-type]
        )


def test_stage_event_rejects_bool_duration() -> None:
    with pytest.raises(TypeError, match="duration_ms"):
        StageEvent(
            stage=StageName.CANDIDATE_GENERATION,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            duration_ms=True,
        )


def test_stage_event_rejects_bool_retry_count() -> None:
    with pytest.raises(TypeError, match="retry_count"):
        StageEvent(
            stage=StageName.CANDIDATE_GENERATION,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            retry_count=True,
        )


def test_stage_event_rejects_bool_repair_count() -> None:
    with pytest.raises(TypeError, match="repair_count"):
        StageEvent(
            stage=StageName.CANDIDATE_GENERATION,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            repair_count=True,
        )


def test_terminal_status_rejects_free_text_only_values() -> None:
    with pytest.raises(ValueError):
        TerminalStatus("needs human help")

    with pytest.raises(TypeError):
        StageEvent(
            stage=StageName.EXPLICIT_FALLBACK,
            run_id="run-001",
            status="needs human help",  # type: ignore[arg-type]
        )


def test_runtime_invariants_reject_blank_ids_blank_errors_and_negative_numbers() -> None:
    with pytest.raises(ValueError, match="run_id"):
        StageEvent(
            stage=StageName.ENTITY_ASSET_RESOLUTION,
            run_id="  ",
            status=TerminalStatus.PASSED,
        )

    with pytest.raises(ValueError, match="input_ids"):
        StageEvent(
            stage=StageName.STRUCTURED_RETRIEVAL,
            run_id="run-001",
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            input_ids=("asset-001", " "),
        )

    with pytest.raises(ValueError, match="duration_ms"):
        StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            duration_ms=-1,
        )

    with pytest.raises(ValueError, match="retry_count"):
        StageEvent(
            stage=StageName.BOUNDED_REPAIR,
            run_id="run-001",
            status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
            retry_count=-1,
        )

    with pytest.raises(ValueError, match="^detail must be nonblank$"):
        StageError(code=StageErrorCode.VALIDATION_CONSTRAINT_FAILED, field="field", detail=" ")

    with pytest.raises(TypeError, match="stage"):
        StageEvent(
            stage="entity_asset_resolution",  # type: ignore[arg-type]
            run_id="run-001",
            status=TerminalStatus.PASSED,
        )


def test_stage_event_enforces_signed_64_bit_maximum_for_duration_and_counters() -> None:
    for field_name in ("duration_ms", "retry_count", "repair_count"):
        event_kwargs: dict[str, Any] = {field_name: _MAX_SIGNED_INT64}
        event = StageEvent(
            stage=StageName.CANDIDATE_GENERATION,
            run_id="run-001",
            status=TerminalStatus.PASSED,
            **event_kwargs,
        )
        assert getattr(event, field_name) == _MAX_SIGNED_INT64

        error_kwargs: dict[str, Any] = {field_name: _MAX_SIGNED_INT64 + 1}
        with pytest.raises(ValueError, match=f"^{field_name} exceeds signed 64-bit maximum$"):
            StageEvent(
                stage=StageName.CANDIDATE_GENERATION,
                run_id="run-001",
                status=TerminalStatus.PASSED,
                **error_kwargs,
            )
