import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

import mfg_agentgraph.pump12_orchestrator as orchestrator_module
from mfg_agentgraph.bounded_repair import BoundedRepairRequest, run_bounded_repair
from mfg_agentgraph.entity_resolution import AssetCatalog, KnownAsset
from mfg_agentgraph.fixture_model_adapter import generate_fixture_candidate_actions
from mfg_agentgraph.pump12_orchestrator import (
    Pump12OrchestrationResult,
    Pump12StableIds,
    run_pump12_orchestrator,
)
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import validate_recommended_action
from mfg_agentgraph.stage_instrumentation import TerminalStatus

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = _REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12"
_SCENARIO_PATH = _FIXTURE_ROOT / "scenario.json"
_SOSA = Namespace("http://www.w3.org/ns/sosa/")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fixture_file:
        data = json.load(fixture_file)
    assert isinstance(data, dict)
    return data


def _canonical_scenario() -> dict[str, Any]:
    return _load_json(_SCENARIO_PATH)


def _request() -> dict[str, object]:
    return {
        "query_text": "What should I inspect after the anomalous sound?",
        "timestamp": "2026-05-18T14:03:30Z",
        "run_id": "run:pump12:issue24-acceptance",
        "asset_hints": ["Pump_12"],
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


def _run(
    *,
    scenario: dict[str, Any] | None = None,
    persist_trace: Any = lambda graph: None,
) -> Pump12OrchestrationResult:
    return run_pump12_orchestrator(
        _request(),
        scenario=_canonical_scenario() if scenario is None else scenario,
        asset_catalog=_catalog(),
        query_id="query:pump12:issue24-acceptance",
        stable_ids=_stable_ids(),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=persist_trace,
    )


def _assert_fails_closed(
    result: Pump12OrchestrationResult, expected_status: TerminalStatus
) -> None:
    assert result.terminal_status is expected_status
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()


def test_validation_failure_fails_closed_without_released_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        return validate_recommended_action(
            action_graph,
            action_uri=action_uri,
            support_graph=corrupted_support,
            report_uri=report_uri,
            run_id=run_id,
        )

    monkeypatch.setattr(
        orchestrator_module,
        "validate_recommended_action",
        validate_without_support_types,
    )

    _assert_fails_closed(_run(), TerminalStatus.VALIDATION_FAILED_CLOSED)


def test_repair_exhaustion_does_not_release_unsupported_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        return validate_recommended_action(
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
            return validate_recommended_action(
                cast(Graph, captured["action_graph"]),
                action_uri=cast(URIRef, captured["action_uri"]),
                support_graph=cast(Graph, captured["support_graph"]),
                report_uri=URIRef(f"ex:AcceptanceRepairReport_{request.attempt_index}"),
                run_id=cast(str, captured["run_id"]),
            )

        return run_bounded_repair(
            initial_validation,  # type: ignore[arg-type]
            retry_budget=2,
            repair_attempt=still_invalid,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(
        orchestrator_module,
        "validate_recommended_action",
        validate_without_observation_time,
    )
    monkeypatch.setattr(orchestrator_module, "run_bounded_repair", exhaust_real_repair)

    result = _run()

    assert [attempt.attempt_index for attempt in attempts] == [1, 2]
    _assert_fails_closed(result, TerminalStatus.INSUFFICIENT_EVIDENCE)


def test_unknown_evidence_fails_closed_without_released_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def generate_with_unknown_evidence(**kwargs: Any) -> object:
        generation = generate_fixture_candidate_actions(**kwargs)
        payload = json.loads(generation.raw_json)
        payload["ranked_actions"][0]["support_evidence"].append(
            {"id": "ex:Unknown_Evidence_999", "type": "document_chunk"}
        )
        return replace(generation, raw_json=json.dumps(payload, sort_keys=True))

    monkeypatch.setattr(
        orchestrator_module,
        "generate_fixture_candidate_actions",
        generate_with_unknown_evidence,
    )

    _assert_fails_closed(_run(), TerminalStatus.INSUFFICIENT_EVIDENCE)


def test_provenance_write_failure_fails_closed_without_released_recommendation() -> None:
    def fail_write(graph: Graph) -> None:
        raise OSError("simulated persistence failure")

    _assert_fails_closed(
        _run(persist_trace=fail_write),
        TerminalStatus.PROVENANCE_FAILED_CLOSED,
    )
