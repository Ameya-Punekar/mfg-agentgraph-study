"""Focused contract tests for Issue #15 deterministic structured retrieval."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

import pytest

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReferenceResolutionError,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import (
    DETERMINISTIC_STRUCTURED_RETRIEVER_NAME,
    StructuredRetrievalResult,
    StructuredRetriever,
    StructuredSupportRecord,
    retrieve_structured_support,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
RUN_ID = "run-issue-15"
QUERY_ID = "query-pump-12-anomalous-sound"
ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
OBSERVATION_ID = "ex:Observation_Pump12_2026-05-18T14:03:00Z"
KG_EDGE_ID = "ex:EvidenceEdge_001"
PROCEDURE_ID = "ex:Procedure_InspectInletCavitation_Pump12"


def _scenario() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _retrieve(scenario: dict[str, Any] | None = None) -> StructuredRetrievalResult:
    return retrieve_structured_support(
        resolved_asset=ASSET,
        scenario=scenario if scenario is not None else _scenario(),
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )


def test_valid_pump_12_result_contains_only_validated_kg_edge_support() -> None:
    result = _retrieve()

    assert result.status is TerminalStatus.PASSED
    assert result.asset == ASSET
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.observation_id == OBSERVATION_ID
    assert observation.observed_asset == ASSET.asset_id
    assert observation.observed_at == "2026-05-18T14:03:00Z"
    assert observation.signal == "anomalous_sound"
    assert observation.anomaly == "anomalous_sound"
    assert "Anomalous sound" in observation.description

    assert len(result.support_records) == 1
    support = result.support_records[0]
    assert support.evidence_id == KG_EDGE_ID
    assert support.subject == ASSET.asset_id
    assert support.predicate == "ex:hasRecommendedProcedure"
    assert support.procedure_id == PROCEDURE_ID
    assert support.required_observation_id == OBSERVATION_ID

    assert tuple(ref.stable_id for ref in result.evidence_references) == (KG_EDGE_ID,)
    reference = result.evidence_references[0]
    assert reference.kind is EvidenceKind.KG_EDGE
    assert reference.source == "tests/fixtures/pump_12/scenario.json"
    assert reference.validation_status is EvidenceValidationStatus.VALIDATED
    assert reference.retrieval.retrieval_run_id == RUN_ID
    assert reference.retrieval.query_id == QUERY_ID
    assert reference.retrieval.retriever_name == DETERMINISTIC_STRUCTURED_RETRIEVER_NAME
    assert reference.retrieval.rank == 1
    assert reference.retrieval.score == 1.0

    assert isinstance(result.evidence_catalog, EvidenceCatalog)
    assert (
        result.evidence_catalog.resolve_validated_support((KG_EDGE_ID,))
        == result.evidence_references
    )
    with pytest.raises(EvidenceReferenceResolutionError):
        result.evidence_catalog.resolve_validated_support((OBSERVATION_ID,))


def test_structured_support_record_enforces_identifier_utf8_byte_limits() -> None:
    record = StructuredSupportRecord(
        evidence_id="é" * 4_096,
        subject="é" * 512,
        predicate="ex:predicate",
        procedure_id="ex:procedure",
        required_observation_id="ex:observation",
    )
    assert len(record.evidence_id.encode("utf-8")) == 8_192
    assert len(record.subject.encode("utf-8")) == 1_024

    with pytest.raises(ValueError, match="evidence_id exceeds"):
        replace(record, evidence_id="é" * 4_097)
    with pytest.raises(ValueError, match="subject exceeds"):
        replace(record, subject="é" * 513)


def test_valid_stage_event_is_structured_retrieval_and_traces_observation() -> None:
    result = _retrieve()

    assert result.event.stage is StageName.STRUCTURED_RETRIEVAL
    assert result.event.run_id == RUN_ID
    assert result.event.status is TerminalStatus.PASSED
    assert result.event.duration_ms == 0
    assert result.event.retry_count == 0
    assert result.event.repair_count == 0
    assert result.event.errors == ()
    assert result.event.input_ids == (ASSET.asset_id, QUERY_ID)
    assert result.event.output_ids == (OBSERVATION_ID, PROCEDURE_ID, KG_EDGE_ID)


def test_missing_required_observation_fails_closed_without_support_or_evidence() -> None:
    scenario = _scenario()
    scenario.pop("observation")

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.observations == ()
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.event.output_ids == ()
    assert len(result.event.errors) == 1
    assert result.event.errors[0].code is StageErrorCode.INSUFFICIENT_EVIDENCE
    assert result.event.errors[0].field == "observation"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert OBSERVATION_ID in detail


def test_observation_asset_mismatch_fails_closed() -> None:
    scenario = _scenario()
    scenario["observation"] = copy.deepcopy(scenario["observation"])
    scenario["observation"]["observed_asset"] = "ex:OtherPump"

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.observations == ()
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.event.errors[0].field == "observation.observed_asset"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert "ex:OtherPump" in detail


def test_oversized_fixture_identifier_fails_closed_with_bounded_detail() -> None:
    scenario = _scenario()
    scenario["asset"] = dict(scenario["asset"])
    scenario["asset"]["id"] = "x" * 2_000

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    detail = result.event.errors[0].detail
    assert detail is not None
    assert len(detail.encode("utf-8")) <= 1_024


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (("signal", "temperature"), ("anomaly", "normal_operation")),
)
def test_observation_signal_and_anomaly_mismatch_fail_closed(
    field_name: str, field_value: str
) -> None:
    scenario = _scenario()
    scenario["observation"] = copy.deepcopy(scenario["observation"])
    scenario["observation"][field_name] = field_value

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.observations == ()
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.output_ids == ()
    assert len(result.event.errors) == 1
    assert result.event.errors[0].code is StageErrorCode.INSUFFICIENT_EVIDENCE
    assert result.event.errors[0].field == f"observation.{field_name}"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert field_value in detail


def test_resolved_asset_rebinding_stable_kg_edge_id_fails_closed() -> None:
    other_asset = KnownAsset("ex:OtherPump", "Other Pump", ("OtherPump",))
    scenario = _scenario()
    scenario["observation"] = copy.deepcopy(scenario["observation"])
    scenario["procedure"] = copy.deepcopy(scenario["procedure"])
    scenario["kg_evidence"] = copy.deepcopy(scenario["kg_evidence"])
    scenario["observation"]["observed_asset"] = other_asset.asset_id
    scenario["procedure"]["applicable_asset"] = other_asset.asset_id
    scenario["kg_evidence"]["subject"] = other_asset.asset_id

    result = retrieve_structured_support(
        resolved_asset=other_asset,
        scenario=scenario,
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.observations == ()
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.output_ids == ()
    assert len(result.event.errors) == 1
    assert result.event.errors[0].code is StageErrorCode.INSUFFICIENT_EVIDENCE
    assert result.event.errors[0].field == "resolved_asset.asset_id"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert "ex:Pump_12" in detail
    assert other_asset.asset_id in detail


def test_missing_kg_edge_fails_closed_after_observation_trace() -> None:
    scenario = _scenario()
    scenario.pop("kg_evidence")

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert tuple(obs.observation_id for obs in result.observations) == (OBSERVATION_ID,)
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.output_ids == (OBSERVATION_ID,)
    assert result.event.errors[0].field == "kg_evidence"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert KG_EDGE_ID in detail


def test_kg_edge_subject_mismatch_fails_closed() -> None:
    scenario = _scenario()
    scenario["kg_evidence"] = copy.deepcopy(scenario["kg_evidence"])
    scenario["kg_evidence"]["subject"] = "ex:OtherPump"

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.event.output_ids == (OBSERVATION_ID,)
    assert result.event.errors[0].field == "kg_evidence.subject"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert "ex:OtherPump" in detail


def test_kg_edge_procedure_mismatch_fails_closed() -> None:
    scenario = _scenario()
    scenario["kg_evidence"] = copy.deepcopy(scenario["kg_evidence"])
    scenario["kg_evidence"]["object"] = "ex:UnexpectedProcedure"

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.event.output_ids == (OBSERVATION_ID,)
    assert result.event.errors[0].field == "kg_evidence.object"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert "ex:UnexpectedProcedure" in detail


def test_input_validation_is_typed_and_fail_fast() -> None:
    scenario = _scenario()
    with pytest.raises(TypeError, match="resolved_asset must be a KnownAsset"):
        retrieve_structured_support(
            resolved_asset=cast(Any, "ex:Pump_12"),
            scenario=scenario,
            retrieval_run_id=RUN_ID,
            query_id=QUERY_ID,
        )
    with pytest.raises(TypeError, match="scenario must be a mapping"):
        retrieve_structured_support(
            resolved_asset=ASSET,
            scenario=cast(Any, []),
            retrieval_run_id=RUN_ID,
            query_id=QUERY_ID,
        )
    with pytest.raises(ValueError, match="retrieval_run_id must be nonblank"):
        retrieve_structured_support(
            resolved_asset=ASSET,
            scenario=scenario,
            retrieval_run_id=" ",
            query_id=QUERY_ID,
        )
    with pytest.raises(ValueError, match="query_id must be nonblank"):
        retrieve_structured_support(
            resolved_asset=ASSET,
            scenario=scenario,
            retrieval_run_id=RUN_ID,
            query_id="",
        )


@pytest.mark.parametrize("field_name", ("retrieval_run_id", "query_id"))
@pytest.mark.parametrize("affixed_value", (" leading", "trailing ", " both "))
def test_retrieval_run_and_query_ids_reject_surrounding_whitespace(
    field_name: str, affixed_value: str
) -> None:
    kwargs = {
        "resolved_asset": ASSET,
        "scenario": _scenario(),
        "retrieval_run_id": RUN_ID,
        "query_id": QUERY_ID,
    }
    kwargs[field_name] = affixed_value

    with pytest.raises(ValueError, match=f"{field_name} must not contain surrounding whitespace"):
        cast(Any, retrieve_structured_support)(**kwargs)


def test_result_records_are_immutable_and_tuple_backed() -> None:
    result = _retrieve()

    assert isinstance(result.observations, tuple)
    assert isinstance(result.support_records, tuple)
    assert isinstance(result.evidence_references, tuple)
    with pytest.raises(FrozenInstanceError):
        result.status = TerminalStatus.INSUFFICIENT_EVIDENCE  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.observations[0].anomaly = "changed"
    with pytest.raises(FrozenInstanceError):
        result.support_records[0].procedure_id = "changed"


def test_catalog_resolution_is_independent_of_unrelated_catalog_order() -> None:
    retriever = StructuredRetriever(source="tests/fixtures/pump_12/scenario.json")
    result = retriever.retrieve(
        resolved_asset=ASSET,
        scenario=_scenario(),
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )
    unrelated_reference = replace(
        result.evidence_references[0],
        stable_id="ex:AnotherValidatedEdge",
    )
    catalog = EvidenceCatalog((unrelated_reference, result.evidence_references[0]))

    assert catalog.resolve_validated_support((KG_EDGE_ID,)) == result.evidence_references


def test_direct_passed_result_rejects_non_structured_stage_event() -> None:
    result = _retrieve()
    event = replace(result.event, stage=StageName.CANDIDATE_GENERATION)

    with pytest.raises(ValueError, match="event.stage must be structured_retrieval"):
        replace(result, event=event)


def test_direct_result_rejects_status_mismatch_and_unsupported_status() -> None:
    result = _retrieve()

    with pytest.raises(ValueError, match="status must match event.status"):
        replace(result, status=TerminalStatus.INSUFFICIENT_EVIDENCE)

    unsupported_event = replace(result.event, status=TerminalStatus.VALIDATION_FAILED_CLOSED)
    with pytest.raises(ValueError, match="status must be passed or insufficient_evidence"):
        replace(result, status=TerminalStatus.VALIDATION_FAILED_CLOSED, event=unsupported_event)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    (
        ("observations", (), "passed result must contain exactly one observation"),
        ("support_records", (), "passed result must contain exactly one support record"),
        ("evidence_references", (), "passed result must contain exactly one evidence reference"),
        (
            "evidence_catalog",
            EvidenceCatalog(()),
            "evidence catalog references must equal evidence_references",
        ),
    ),
)
def test_direct_passed_result_rejects_cardinality_and_catalog_contradictions(
    field_name: str, bad_value: object, message: str
) -> None:
    result = _retrieve()

    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(result, **{field_name: bad_value})


def test_direct_passed_result_rejects_event_errors() -> None:
    result = _retrieve()
    event = replace(
        result.event,
        errors=(StageError(StageErrorCode.INVALID_STAGE_EVENT),),
    )

    with pytest.raises(ValueError, match="passed result must not contain event errors"):
        replace(result, event=event)


def test_direct_passed_result_rejects_output_id_contradiction() -> None:
    result = _retrieve()
    event = replace(result.event, output_ids=(OBSERVATION_ID, KG_EDGE_ID))

    with pytest.raises(
        ValueError,
        match="passed event.output_ids must equal observation, procedure, and evidence IDs",
    ):
        replace(result, event=event)


def test_direct_passed_result_rejects_support_evidence_contradiction() -> None:
    result = _retrieve()
    support = replace(result.support_records[0], evidence_id="ex:DifferentEvidence")

    with pytest.raises(
        ValueError,
        match="support evidence_id must equal evidence reference stable_id",
    ):
        replace(result, support_records=(support,))


def test_direct_passed_result_rejects_support_observation_contradiction() -> None:
    result = _retrieve()
    support = replace(
        result.support_records[0],
        required_observation_id="ex:DifferentObservation",
    )

    with pytest.raises(
        ValueError,
        match="support required_observation_id must equal observation_id",
    ):
        replace(result, support_records=(support,))


def test_direct_passed_result_rejects_same_id_but_different_catalog_reference() -> None:
    result = _retrieve()
    different_reference = replace(
        result.evidence_references[0],
        retrieval=RetrievalMetadata(
            retrieval_run_id=RUN_ID,
            query_id=QUERY_ID,
            retriever_name=DETERMINISTIC_STRUCTURED_RETRIEVER_NAME,
            rank=2,
        ),
    )

    with pytest.raises(
        ValueError,
        match="evidence catalog references must equal evidence_references",
    ):
        replace(result, evidence_catalog=EvidenceCatalog((different_reference,)))


def test_direct_passed_result_rejects_document_chunk_evidence_reference() -> None:
    result = _retrieve()
    document_reference = replace(
        result.evidence_references[0],
        kind=EvidenceKind.DOCUMENT_CHUNK,
    )

    with pytest.raises(
        ValueError,
        match="passed evidence reference must be a KG edge",
    ):
        replace(
            result,
            evidence_references=(document_reference,),
            evidence_catalog=EvidenceCatalog((document_reference,)),
        )


def test_direct_passed_result_rejects_unvalidated_evidence_reference() -> None:
    result = _retrieve()
    unvalidated_reference = replace(
        result.evidence_references[0],
        validation_status=EvidenceValidationStatus.UNVALIDATED,
    )

    with pytest.raises(
        ValueError,
        match="passed evidence reference must be validated",
    ):
        replace(
            result,
            evidence_references=(unvalidated_reference,),
            evidence_catalog=EvidenceCatalog((unvalidated_reference,)),
        )


def _insufficient_result_with_observation() -> StructuredRetrievalResult:
    result = _retrieve()
    event = StageEvent(
        stage=StageName.STRUCTURED_RETRIEVAL,
        run_id=RUN_ID,
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        output_ids=(OBSERVATION_ID,),
        errors=(StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field="kg_evidence"),),
    )
    return StructuredRetrievalResult(
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        asset=ASSET,
        observations=result.observations,
        event=event,
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    (
        (
            "support_records",
            lambda result: result.support_records,
            "insufficient evidence result must not contain support records",
        ),
        (
            "evidence_references",
            lambda result: result.evidence_references,
            "insufficient evidence result must not contain evidence references",
        ),
        (
            "evidence_catalog",
            lambda result: result.evidence_catalog,
            "insufficient evidence result must have an empty evidence catalog",
        ),
    ),
)
def test_direct_insufficient_evidence_result_rejects_support_and_evidence(
    field_name: str, bad_value: Any, message: str
) -> None:
    passed = _retrieve()
    insufficient = _insufficient_result_with_observation()

    with pytest.raises(ValueError, match=message):
        replace(insufficient, **{field_name: bad_value(passed)})


def test_direct_insufficient_evidence_result_rejects_missing_errors() -> None:
    insufficient = _insufficient_result_with_observation()
    event = replace(insufficient.event, errors=())

    with pytest.raises(ValueError, match="insufficient evidence result must contain event errors"):
        replace(insufficient, event=event)


def test_direct_insufficient_evidence_result_rejects_non_observation_output_ids() -> None:
    insufficient = _insufficient_result_with_observation()
    event = replace(insufficient.event, output_ids=(OBSERVATION_ID, KG_EDGE_ID))

    with pytest.raises(
        ValueError,
        match="insufficient evidence event.output_ids must equal observation IDs",
    ):
        replace(insufficient, event=event)
