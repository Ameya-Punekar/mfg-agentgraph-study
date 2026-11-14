import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

import mfg_agentgraph.pump12_orchestrator as orchestrator_module
from mfg_agentgraph.bounded_repair import BoundedRepairRequest, run_bounded_repair
from mfg_agentgraph.entity_resolution import AssetCatalog, KnownAsset
from mfg_agentgraph.evidence_package import assemble_evidence_package
from mfg_agentgraph.fixture_model_adapter import generate_fixture_candidate_actions
from mfg_agentgraph.pump12_orchestrator import (
    Pump12OrchestrationResult,
    Pump12StableIds,
    run_pump12_orchestrator,
)
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import validate_recommended_action
from mfg_agentgraph.stage_instrumentation import (
    CANONICAL_S4_STAGE_NAMES,
    StageErrorCode,
    StageName,
    TerminalStatus,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOSA = Namespace("http://www.w3.org/ns/sosa/")


def _scenario() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            (_REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def _request(*, asset_hint: str = "Pump_12") -> dict[str, object]:
    return {
        "query_text": "What should I inspect after the anomalous sound?",
        "timestamp": "2026-05-18T14:03:30Z",
        "run_id": "run:pump12:issue23",
        "asset_hints": [asset_hint],
        "sensor_hints": ["anomalous_sound"],
    }


def _catalog() -> AssetCatalog:
    return AssetCatalog((KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),))


def _stable_ids() -> Pump12StableIds:
    return Pump12StableIds(
        action_id="ex:CandidateAction_Pump12_Repaired_001",
        validation_report_id="ex:ValidationReport_Pump12_001",
        evidence_package_id="ex:EvidencePackage_Pump12_001",
        provenance_id="ex:ProvenanceTrace_Pump12_001",
        agent_id="ex:Agent_S4",
        prompt_id="ex:Prompt_Pump12_001",
        model_id="ex:FixtureModel_Pump12_001",
        asset_id="ex:Pump_12",
        observation_id="ex:Observation_Pump12_2026-05-18T14:03:00Z",
        procedure_id="ex:Procedure_InspectInletCavitation_Pump12",
        kg_evidence_id="ex:EvidenceEdge_001",
        document_evidence_id="ex:SOP_Chunk_7",
    )


def _run(persist_trace: Callable[[Graph], object]) -> Pump12OrchestrationResult:
    return run_pump12_orchestrator(
        _request(),
        scenario=_scenario(),
        asset_catalog=_catalog(),
        query_id="query:pump12:issue23",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=persist_trace,
    )


def test_success_composes_real_components_in_exact_ten_stage_order() -> None:
    persisted: list[Graph] = []

    def persist_trace(graph: Graph) -> None:
        persisted.append(graph)

    result = _run(persist_trace)

    assert result.terminal_status is TerminalStatus.PASSED
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES
    assert {event.run_id for event in result.events} == {"run:pump12:issue23"}
    assert all(event.status is TerminalStatus.PASSED for event in result.events)
    assert result.released_action is not None
    assert result.released_action.target_asset == "ex:Pump_12"
    assert result.evidence_package is not None
    assert result.evidence_package.package_id == "ex:EvidencePackage_Pump12_001"
    assert result.evidence_package.action_id == "ex:CandidateAction_Pump12_Repaired_001"
    assert result.evidence_package.validation_report_id == "ex:ValidationReport_Pump12_001"
    assert result.provenance_id == "ex:ProvenanceTrace_Pump12_001"
    assert result.recommendation_id == result.evidence_package.action_id
    assert result.trace_graph_evidence
    assert len(persisted) == 1
    assert set(persisted[0]) == set(result.trace_graph_evidence)

    fallback_event = result.events[7]
    assert fallback_event.stage is StageName.EXPLICIT_FALLBACK
    assert fallback_event.input_ids == (
        "ex:CandidateAction_Pump12_Repaired_001",
        "ex:ValidationReport_Pump12_001",
    )
    assert fallback_event.output_ids == ("ex:ValidationReport_Pump12_001",)
    assert fallback_event.retry_count == 0
    assert fallback_event.repair_count == 0
    assert fallback_event.errors == ()


def test_repeated_runs_are_deterministic_and_results_are_frozen() -> None:
    first = _run(lambda graph: None)
    second = _run(lambda graph: None)

    assert first == second
    assert isinstance(first.events, tuple)
    assert isinstance(first.trace_graph_evidence, tuple)
    with pytest.raises(FrozenInstanceError):
        first.terminal_status = TerminalStatus.INSUFFICIENT_EVIDENCE  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type"),
    [("action_id", " ", ValueError), ("model_id", object(), TypeError)],
)
def test_stable_ids_reject_non_strict_values(
    field_name: str, invalid_value: object, error_type: type[Exception]
) -> None:
    valid = _stable_ids()
    values: dict[str, object] = {
        field.name: getattr(valid, field.name) for field in fields(Pump12StableIds)
    }
    values[field_name] = invalid_value

    with pytest.raises(error_type):
        Pump12StableIds(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_field", ["asset_catalog", "stable_ids"])
def test_orchestrator_rejects_wrong_boundary_object_types(invalid_field: str) -> None:
    values: dict[str, object] = {
        "scenario": _scenario(),
        "asset_catalog": _catalog(),
        "query_id": "query:pump12:issue23",
        "stable_ids": _stable_ids(),
        "recorded_at": datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        "persist_trace": lambda graph: None,
    }
    values[invalid_field] = object()

    with pytest.raises(TypeError):
        run_pump12_orchestrator(_request(), **values)  # type: ignore[arg-type]


def test_ambiguous_entity_resolution_returns_only_stage_one_and_no_release() -> None:
    catalog = AssetCatalog(
        (
            KnownAsset("ex:Pump_12", "Pump 12", ("shared-pump",)),
            KnownAsset("ex:Pump_13", "Pump 13", ("shared-pump",)),
        )
    )
    persisted: list[Graph] = []

    result = run_pump12_orchestrator(
        _request(asset_hint="shared-pump"),
        scenario=_scenario(),
        asset_catalog=catalog,
        query_id="query:pump12:issue23",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: persisted.append(graph),
    )

    assert result.terminal_status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert len(result.events) == 1
    event = result.events[0]
    assert event.stage is StageName.ENTITY_ASSET_RESOLUTION
    assert event.status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert event.output_ids == ("ex:Pump_12", "ex:Pump_13")
    assert len(event.errors) == 1
    assert event.errors[0].code is StageErrorCode.OPERATOR_DISAMBIGUATION_REQUIRED
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert persisted == []


@pytest.mark.parametrize(
    ("missing_key", "expected_status", "expected_stages", "expected_error"),
    [
        (
            "observation",
            TerminalStatus.INSUFFICIENT_EVIDENCE,
            (StageName.ENTITY_ASSET_RESOLUTION, StageName.STRUCTURED_RETRIEVAL),
            StageErrorCode.INSUFFICIENT_EVIDENCE,
        ),
        (
            "document_evidence",
            TerminalStatus.UNSUPPORTED_LOWER_RANK,
            (
                StageName.ENTITY_ASSET_RESOLUTION,
                StageName.STRUCTURED_RETRIEVAL,
                StageName.PROCEDURAL_RETRIEVAL,
            ),
            StageErrorCode.UNSUPPORTED_LOWER_RANK,
        ),
    ],
)
def test_retrieval_failure_stops_at_exact_event_prefix_and_blocks_release(
    missing_key: str,
    expected_status: TerminalStatus,
    expected_stages: tuple[StageName, ...],
    expected_error: StageErrorCode,
) -> None:
    scenario = deepcopy(_scenario())
    del scenario[missing_key]
    persisted: list[Graph] = []

    result = run_pump12_orchestrator(
        _request(),
        scenario=scenario,
        asset_catalog=_catalog(),
        query_id="query:pump12:issue24",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: persisted.append(graph),
    )

    assert result.terminal_status is expected_status
    assert tuple(event.stage for event in result.events) == expected_stages
    assert {event.run_id for event in result.events} == {"run:pump12:issue23"}
    assert result.events[-1].status is expected_status
    assert tuple(error.code for error in result.events[-1].errors) == (expected_error,)
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert persisted == []


def test_unknown_candidate_evidence_fails_at_stage_four_without_payload_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_generate = generate_fixture_candidate_actions

    def generate_with_unknown_evidence(**kwargs: Any) -> object:
        generation = real_generate(**kwargs)
        payload = json.loads(generation.raw_json)
        evidence = payload["ranked_actions"][0]["support_evidence"]
        evidence.append({"id": "ex:Unknown_Evidence_999", "type": "document_chunk"})
        return replace(generation, raw_json=json.dumps(payload, sort_keys=True))

    monkeypatch.setattr(
        orchestrator_module,
        "generate_fixture_candidate_actions",
        generate_with_unknown_evidence,
    )
    persisted: list[Graph] = []

    result = run_pump12_orchestrator(
        _request(),
        scenario=_scenario(),
        asset_catalog=_catalog(),
        query_id="query:pump12:issue24",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: persisted.append(graph),
    )

    assert result.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES[:4]
    failed_event = result.events[-1]
    assert failed_event.status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert failed_event.input_ids == ("ex:CandidateAction_Pump12_Repaired_001",)
    assert failed_event.output_ids == ()
    assert len(failed_event.errors) == 1
    assert failed_event.errors[0].code is StageErrorCode.INSUFFICIENT_EVIDENCE
    assert failed_event.errors[0].field == "support_evidence"
    assert failed_event.errors[0].detail is None
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert persisted == []


def test_unsupported_shacl_policy_stops_after_real_fallback_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_validate = validate_recommended_action

    def validate_without_support_types(
        action_graph: Graph,
        *,
        action_uri: URIRef,
        support_graph: Graph,
        report_uri: URIRef,
        run_id: str,
    ) -> object:
        corrupted_support = Graph()
        for triple in support_graph:
            corrupted_support.add(triple)
        for support_id in action_graph.objects(action_uri, MFG.hasSupportEvidence):
            corrupted_support.remove((support_id, RDF.type, MFG.SupportEvidence))
        return real_validate(
            action_graph,
            action_uri=action_uri,
            support_graph=corrupted_support,
            report_uri=report_uri,
            run_id=run_id,
        )

    def reject_stage_nine(**kwargs: Any) -> object:
        raise AssertionError("Stage 9 must not run after unsupported SHACL policy")

    monkeypatch.setattr(
        orchestrator_module,
        "validate_recommended_action",
        validate_without_support_types,
    )
    monkeypatch.setattr(orchestrator_module, "assemble_evidence_package", reject_stage_nine)
    persisted: list[Graph] = []

    result = run_pump12_orchestrator(
        _request(),
        scenario=_scenario(),
        asset_catalog=_catalog(),
        query_id="query:pump12:issue24",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: persisted.append(graph),
    )

    assert result.terminal_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES[:8]
    assert {event.run_id for event in result.events} == {"run:pump12:issue23"}
    assert result.events[5].status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.events[5].output_ids == ("ex:ValidationReport_Pump12_001",)
    assert tuple(event.status for event in result.events[6:]) == (
        TerminalStatus.VALIDATION_FAILED_CLOSED,
        TerminalStatus.VALIDATION_FAILED_CLOSED,
    )
    assert tuple(error.field for error in result.events[6].errors) == ("shape_policy",)
    assert tuple(error.field for error in result.events[7].errors) == ("shacl_report",)
    assert all(event.retry_count == 0 for event in result.events[6:])
    assert all(event.repair_count == 0 for event in result.events[6:])
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert persisted == []


def test_repair_exhaustion_stops_after_two_real_failed_validations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_validate = validate_recommended_action
    real_run_bounded_repair = run_bounded_repair
    captured: dict[str, object] = {}
    attempts: list[BoundedRepairRequest] = []

    def validate_without_observation_time(
        action_graph: Graph,
        *,
        action_uri: URIRef,
        support_graph: Graph,
        report_uri: URIRef,
        run_id: str,
    ) -> object:
        corrupted_support = Graph()
        for triple in support_graph:
            corrupted_support.add(triple)
        for observation in tuple(corrupted_support.subjects(RDF.type, _SOSA.Observation)):
            corrupted_support.remove((observation, _SOSA.resultTime, None))
        captured.update(
            action_graph=action_graph,
            action_uri=action_uri,
            support_graph=corrupted_support,
            run_id=run_id,
        )
        return real_validate(
            action_graph,
            action_uri=action_uri,
            support_graph=corrupted_support,
            report_uri=report_uri,
            run_id=run_id,
        )

    def exhaust_real_repair(
        initial_validation: object,
        *,
        retry_budget: int,
        repair_attempt: object,
    ) -> object:
        del retry_budget, repair_attempt

        def still_invalid(request: BoundedRepairRequest) -> object:
            attempts.append(request)
            return real_validate(
                cast(Graph, captured["action_graph"]),
                action_uri=cast(URIRef, captured["action_uri"]),
                support_graph=cast(Graph, captured["support_graph"]),
                report_uri=URIRef(f"ex:ValidationReport_Pump12_Repair_{request.attempt_index}"),
                run_id=cast(str, captured["run_id"]),
            )

        return real_run_bounded_repair(
            initial_validation,  # type: ignore[arg-type]
            retry_budget=2,
            repair_attempt=still_invalid,  # type: ignore[arg-type]
        )

    def reject_stage_nine(**kwargs: Any) -> object:
        raise AssertionError("Stage 9 must not run after repair exhaustion")

    monkeypatch.setattr(
        orchestrator_module,
        "validate_recommended_action",
        validate_without_observation_time,
    )
    monkeypatch.setattr(orchestrator_module, "run_bounded_repair", exhaust_real_repair)
    monkeypatch.setattr(orchestrator_module, "assemble_evidence_package", reject_stage_nine)
    persisted: list[Graph] = []

    result = run_pump12_orchestrator(
        _request(),
        scenario=_scenario(),
        asset_catalog=_catalog(),
        query_id="query:pump12:issue24",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: persisted.append(graph),
    )

    assert [request.attempt_index for request in attempts] == [1, 2]
    assert result.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES[:8]
    assert {event.run_id for event in result.events} == {"run:pump12:issue23"}
    assert result.events[5].status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.events[5].output_ids == ("ex:ValidationReport_Pump12_001",)
    for event in result.events[6:]:
        assert event.status is TerminalStatus.INSUFFICIENT_EVIDENCE
        assert event.retry_count == 2
        assert event.repair_count == 2
        assert event.output_ids == ("ex:ValidationReport_Pump12_Repair_2",)
        assert tuple(error.code for error in event.errors) == (
            StageErrorCode.INSUFFICIENT_EVIDENCE,
        )
    assert result.events[6].input_ids == (
        "ex:CandidateAction_Pump12_Repaired_001",
        "ex:ValidationReport_Pump12_001",
    )
    assert result.events[7].input_ids == (
        "ex:CandidateAction_Pump12_Repaired_001",
        "ex:ValidationReport_Pump12_Repair_2",
    )
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert persisted == []


def test_evidence_package_rejection_stops_at_stage_nine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_assemble = assemble_evidence_package

    def assemble_with_invalid_package_id(**kwargs: Any) -> object:
        return real_assemble(**{**kwargs, "package_id": " "})

    monkeypatch.setattr(
        orchestrator_module,
        "assemble_evidence_package",
        assemble_with_invalid_package_id,
    )
    persisted: list[Graph] = []

    result = run_pump12_orchestrator(
        _request(),
        scenario=_scenario(),
        asset_catalog=_catalog(),
        query_id="query:pump12:issue24",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: persisted.append(graph),
    )

    assert result.terminal_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES[:9]
    assert {event.run_id for event in result.events} == {"run:pump12:issue23"}
    failed_event = result.events[-1]
    assert failed_event.stage is StageName.EVIDENCE_PACKAGE_ASSEMBLY
    assert failed_event.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert failed_event.input_ids == (
        "ex:CandidateAction_Pump12_Repaired_001",
        "ex:ValidationReport_Pump12_001",
    )
    assert failed_event.output_ids == ()
    assert tuple(error.code for error in failed_event.errors) == (
        StageErrorCode.INVALID_EVIDENCE_PACKAGE,
    )
    assert tuple(error.field for error in failed_event.errors) == ("package_id",)
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert persisted == []


@pytest.mark.parametrize("failure_mode", ["exception", "non_none"])
def test_provenance_failure_keeps_stage_prefix_but_blocks_every_release_field(
    failure_mode: str,
) -> None:
    def fail_trace(graph: Graph) -> object:
        if failure_mode == "exception":
            raise OSError("simulated persistence failure")
        return object()

    result = _run(fail_trace)

    assert result.terminal_status is TerminalStatus.PROVENANCE_FAILED_CLOSED
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES
    assert all(event.status is TerminalStatus.PASSED for event in result.events[:9])
    assert result.events[-1].status is TerminalStatus.PROVENANCE_FAILED_CLOSED
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
