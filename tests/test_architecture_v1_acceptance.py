import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from mfg_agentgraph.candidate_action import parse_candidate_actions
from mfg_agentgraph.entity_resolution import AssetCatalog, KnownAsset
from mfg_agentgraph.evidence_package import EvidencePackage
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.fixture_model_adapter import (
    FixtureModelVariant,
    generate_fixture_candidate_actions,
)
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.provenance import write_provenance_trace
from mfg_agentgraph.pump12_orchestrator import (
    Pump12OrchestrationResult,
    Pump12StableIds,
    run_pump12_orchestrator,
)
from mfg_agentgraph.rdf_action_mapper import MFG, map_candidate_action_to_rdf
from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf
from mfg_agentgraph.shacl_validation import validate_recommended_action
from mfg_agentgraph.stage_instrumentation import (
    CANONICAL_S4_STAGE_NAMES,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import retrieve_structured_support

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _architecture_gap(*follow_up_issues: int) -> None:
    issue_list = ", ".join(f"#{issue}" for issue in follow_up_issues)
    pytest.fail(f"Architecture V1 behavior is not implemented; tracked by {issue_list}")


def _issue23_orchestration_result(
    *,
    asset_hint: str = "Pump_12",
    asset_catalog: AssetCatalog | None = None,
    scenario: dict[str, object] | None = None,
) -> Pump12OrchestrationResult:
    selected_scenario = scenario
    if selected_scenario is None:
        loaded_scenario = json.loads(
            (_REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json").read_text(
                encoding="utf-8"
            )
        )
        assert isinstance(loaded_scenario, dict)
        selected_scenario = loaded_scenario
    catalog = asset_catalog or AssetCatalog((KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),))
    return run_pump12_orchestrator(
        {
            "query_text": "What should I inspect after the anomalous sound?",
            "timestamp": "2026-05-18T14:03:30Z",
            "run_id": "run:pump12:architecture-acceptance",
            "asset_hints": [asset_hint],
        },
        scenario=selected_scenario,
        asset_catalog=catalog,
        query_id="query:pump12:architecture-acceptance",
        stable_ids=Pump12StableIds(
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
        ),
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        persist_trace=lambda graph: None,
    )


def test_all_ten_pipeline_stages_are_present_and_instrumented() -> None:
    result = _issue23_orchestration_result()

    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES
    assert {event.run_id for event in result.events} == {"run:pump12:architecture-acceptance"}
    assert all(event.status is TerminalStatus.PASSED for event in result.events)


def test_entity_resolution_can_request_operator_disambiguation() -> None:
    result = _issue23_orchestration_result(
        asset_hint="shared-pump",
        asset_catalog=AssetCatalog(
            (
                KnownAsset("ex:Pump_12", "Pump 12", ("shared-pump",)),
                KnownAsset("ex:Pump_13", "Pump 13", ("shared-pump",)),
            )
        ),
    )

    assert result.terminal_status is TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    assert tuple(event.stage for event in result.events) == (StageName.ENTITY_ASSET_RESOLUTION,)
    assert result.events[0].output_ids == ("ex:Pump_12", "ex:Pump_13")
    assert result.released_action is None


@pytest.mark.xfail(strict=True, reason="Pending stable evidence identifiers in #12 and retrievers")
def test_sparql_and_vector_evidence_have_stable_identifiers() -> None:
    _architecture_gap(12, 15, 16, 27, 28)


def test_model_output_is_schema_validated_and_reified_as_rdf() -> None:
    scenario = json.loads(
        (_REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json").read_text(
            encoding="utf-8"
        )
    )
    repaired = scenario["candidate_actions"]["repaired"]
    evidence_type_by_id = {
        scenario["kg_evidence"]["id"]: scenario["kg_evidence"]["type"],
        scenario["document_evidence"]["id"]: scenario["document_evidence"]["type"],
    }
    parser_payload = {
        "ranked_actions": [
            {
                "rank": 1,
                "action": repaired["label"],
                "target_asset": repaired["target"],
                "support_evidence": [
                    {"type": evidence_type_by_id[stable_id], "id": stable_id}
                    for stable_id in repaired["evidence_refs"]
                ],
            }
        ]
    }
    evidence_catalog = EvidenceCatalog(
        (
            EvidenceReference(
                kind=EvidenceKind(scenario["kg_evidence"]["type"]),
                source="pump-12-fixture-kg",
                stable_id=scenario["kg_evidence"]["id"],
                retrieval=RetrievalMetadata(
                    retrieval_run_id="acceptance-issue-18-kg",
                    query_id="acceptance-issue-18-pump-12",
                    retriever_name="deterministic_architecture_v1_acceptance_fixture",
                    rank=1,
                    score=1.0,
                ),
                validation_status=EvidenceValidationStatus.VALIDATED,
            ),
            EvidenceReference(
                kind=EvidenceKind(scenario["document_evidence"]["type"]),
                source="pump-12-fixture-documents",
                stable_id=scenario["document_evidence"]["id"],
                retrieval=RetrievalMetadata(
                    retrieval_run_id="acceptance-issue-18-document",
                    query_id="acceptance-issue-18-pump-12",
                    retriever_name="deterministic_architecture_v1_acceptance_fixture",
                    rank=2,
                    score=1.0,
                ),
                validation_status=EvidenceValidationStatus.VALIDATED,
            ),
        )
    )

    plan = parse_candidate_actions(
        json.dumps(parser_payload, sort_keys=True),
        known_assets={scenario["asset"]["id"]},
        evidence_catalog=evidence_catalog,
    )
    action = plan.ranked_actions[0]
    action_iri = URIRef(repaired["id"])
    resource_iris = {
        scenario["asset"]["id"]: URIRef(scenario["asset"]["id"]),
        scenario["kg_evidence"]["id"]: URIRef(scenario["kg_evidence"]["id"]),
        scenario["document_evidence"]["id"]: URIRef(scenario["document_evidence"]["id"]),
    }

    graph = map_candidate_action_to_rdf(
        action,
        action_iri=action_iri,
        resource_iris=resource_iris,
    )

    assert (action_iri, RDF.type, MFG.RecommendedAction) in graph
    assert (action_iri, RDFS.label, Literal(repaired["label"])) in graph
    assert list(graph.objects(action_iri, MFG.targetAsset)) == [
        resource_iris[scenario["asset"]["id"]]
    ]
    assert (action_iri, MFG.rank, Literal(1, datatype=XSD.integer)) in graph
    assert set(graph.objects(action_iri, MFG.hasSupportEvidence)) == {
        resource_iris[scenario["kg_evidence"]["id"]],
        resource_iris[scenario["document_evidence"]["id"]],
    }
    assert len(tuple(graph.objects(action_iri, MFG.hasSupportEvidence))) == 2


def test_shacl_gates_every_s4_recommendation() -> None:
    result = _issue23_orchestration_result()

    validation_event = result.events[5]
    assert validation_event.stage is StageName.SHACL_VALIDATION
    assert validation_event.status is TerminalStatus.PASSED
    assert validation_event.output_ids == ("ex:ValidationReport_Pump12_001",)
    assert result.released_action is not None
    assert result.provenance_id is not None


def test_issue72_product_assembly_feeds_canonical_recommendation_to_shacl_gate() -> None:
    scenario = json.loads(
        (_REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json").read_text(
            encoding="utf-8"
        )
    )
    asset = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
    query_id = "acceptance-issue-72-pump-12"
    structured = retrieve_structured_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id="acceptance-issue-72-structured",
        query_id=query_id,
    )
    procedural = retrieve_procedural_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id="acceptance-issue-72-procedural",
        query_id=query_id,
    )
    generation = generate_fixture_candidate_actions(
        scenario=scenario,
        structured_result=structured,
        procedural_result=procedural,
        generation_run_id="acceptance-issue-72-generation",
        query_id=query_id,
        variant=FixtureModelVariant.REPAIRED,
    )
    plan = parse_candidate_actions(
        generation.raw_json,
        known_assets={scenario["asset"]["id"]},
        evidence_catalog=generation.evidence_catalog,
    )
    resource_iris = {
        stable_id: URIRef(stable_id.replace("ex:", "http://example.org/", 1))
        for stable_id in (
            scenario["asset"]["id"],
            scenario["observation"]["id"],
            scenario["procedure"]["id"],
            scenario["kg_evidence"]["id"],
            scenario["document_evidence"]["id"],
        )
    }
    action_iri = URIRef(
        scenario["candidate_actions"]["repaired"]["id"].replace("ex:", "http://example.org/", 1)
    )

    assembled = assemble_recommended_action_rdf(
        plan.ranked_actions[0],
        action_iri=action_iri,
        resource_iris=resource_iris,
        anomaly_window_start=scenario["anomaly_window"]["started_at"],
        anomaly_window_end=scenario["anomaly_window"]["ended_at"],
        structured_result=structured,
        procedural_result=procedural,
    )
    result = validate_recommended_action(
        assembled.action_graph,
        action_uri=action_iri,
        support_graph=assembled.support_graph,
        report_uri=URIRef("http://example.org/ValidationReport_Issue72_Acceptance"),
        run_id="acceptance-issue-72-validation",
    )

    assert result.conforms is True
    assert result.violations == ()


def test_repair_is_bounded_and_exposes_terminal_states() -> None:
    from mfg_agentgraph.bounded_repair import BoundedRepairRequest, run_bounded_repair
    from mfg_agentgraph.shacl_validation import ShaclValidationResult, validate_recommended_action
    from mfg_agentgraph.stage_instrumentation import StageName, TerminalStatus

    run_id = "architecture-v1-bounded-repair"
    action_uri = URIRef("http://example.org/CandidateAction_Pump12_Repaired_001")
    asset_uri = URIRef("http://example.org/Pump_12")
    evidence_uri = URIRef("http://example.org/KgEvidence_Pump12_001")
    procedure_evidence_uri = URIRef("http://example.org/DocumentEvidence_Pump12_001")
    observation_uri = URIRef("http://example.org/Observation_Pump12_001")
    procedure_uri = URIRef("http://example.org/Procedure_Pump12_001")

    action_graph = Graph()
    action_graph.add((action_uri, RDF.type, MFG.RecommendedAction))
    action_graph.add((action_uri, MFG.targetAsset, asset_uri))
    action_graph.add((action_uri, MFG.hasSupportEvidence, evidence_uri))
    action_graph.add((action_uri, MFG.hasSupportEvidence, procedure_evidence_uri))
    action_graph.add(
        (
            action_uri,
            MFG.anomalyWindowStart,
            Literal("2026-05-18T14:00:00Z", datatype=XSD.dateTime),
        )
    )
    action_graph.add(
        (
            action_uri,
            MFG.anomalyWindowEnd,
            Literal("2026-05-18T14:10:00Z", datatype=XSD.dateTime),
        )
    )

    support_graph = Graph()
    support_graph.add((asset_uri, RDF.type, MFG.Asset))
    support_graph.add((asset_uri, MFG.assetType, MFG.CentrifugalPump))
    support_graph.add((evidence_uri, RDF.type, MFG.SupportEvidence))
    support_graph.add((evidence_uri, MFG.observation, observation_uri))
    support_graph.add((procedure_evidence_uri, RDF.type, MFG.SupportEvidence))
    support_graph.add((procedure_evidence_uri, MFG.procedure, procedure_uri))
    support_graph.add((observation_uri, RDF.type, URIRef("http://www.w3.org/ns/sosa/Observation")))
    support_graph.add(
        (
            observation_uri,
            URIRef("http://www.w3.org/ns/sosa/hasFeatureOfInterest"),
            asset_uri,
        )
    )
    support_graph.add((procedure_uri, RDF.type, MFG.Procedure))
    support_graph.add((procedure_uri, MFG.applicableAssetType, MFG.CentrifugalPump))
    # Intentionally omit sosa:resultTime so the real SHACL validator returns
    # ObservationResultTimeRequiredShape and bounded repair exhausts to observation fallback.

    def validation(report_suffix: str) -> ShaclValidationResult:
        result = validate_recommended_action(
            action_graph,
            action_uri=action_uri,
            support_graph=support_graph,
            report_uri=URIRef(f"http://example.org/report-{report_suffix}"),
            run_id=run_id,
        )
        assert result.conforms is False
        assert {violation.shape_id for violation in result.violations} == {
            str(MFG.ObservationResultTimeRequiredShape)
        }
        return result

    initial = validation("initial")
    attempts: list[BoundedRepairRequest] = []

    def repair(request: BoundedRepairRequest) -> ShaclValidationResult:
        attempts.append(request)
        return validation(f"attempt-{request.attempt_index}")

    outcome = run_bounded_repair(initial, retry_budget=2, repair_attempt=repair)

    assert [request.attempt_index for request in attempts] == [1, 2]
    assert outcome.initial_validation_count == 1
    assert outcome.initial_failure_count == 1
    assert outcome.repair_count == 2
    assert outcome.retry_count == 2
    assert outcome.self_correction_success_count == 0
    assert outcome.final_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert tuple(event.stage for event in outcome.events) == (
        StageName.BOUNDED_REPAIR,
        StageName.EXPLICIT_FALLBACK,
    )
    assert outcome.events[-1].status is TerminalStatus.INSUFFICIENT_EVIDENCE


def test_invalid_or_unsupported_recommendations_fail_closed() -> None:
    scenario = json.loads(
        (_REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json").read_text(
            encoding="utf-8"
        )
    )
    del scenario["document_evidence"]

    result = _issue23_orchestration_result(scenario=scenario)

    assert result.terminal_status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert tuple(event.stage for event in result.events) == CANONICAL_S4_STAGE_NAMES[:3]
    assert result.released_action is None
    assert result.evidence_package is None
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()


def _issue22_provenance_inputs() -> tuple[EvidencePackage, tuple[StageEvent, ...]]:
    run_id = "architecture-v1-issue-22"
    action = "https://example.org/action/Pump12"
    report = "https://example.org/report/Pump12"
    package_id = "https://example.org/package/Pump12"
    kg_evidence = "https://example.org/evidence/KgEdge001"
    document_evidence = "https://example.org/evidence/SopChunk7"
    package = EvidencePackage(
        package_id=package_id,
        run_id=run_id,
        action_id=action,
        target_asset_id="https://example.org/asset/Pump12",
        validation_report_id=report,
        terminal_status=TerminalStatus.PASSED,
        support_evidence_ids=(kg_evidence, document_evidence),
        typed_kg_evidence_ids=(kg_evidence,),
        document_evidence_ids=(document_evidence,),
        action_graph_evidence=((URIRef(action), RDF.type, MFG.RecommendedAction),),
    )
    events = (
        StageEvent(
            stage=StageName.STRUCTURED_RETRIEVAL,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            output_ids=(kg_evidence,),
        ),
        StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            output_ids=(document_evidence,),
        ),
        StageEvent(
            stage=StageName.CANDIDATE_GENERATION,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(kg_evidence, document_evidence),
            output_ids=(action,),
        ),
        StageEvent(
            stage=StageName.SHACL_VALIDATION,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(action,),
            output_ids=(report,),
        ),
        StageEvent(
            stage=StageName.BOUNDED_REPAIR,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(action, report),
            output_ids=(report,),
        ),
        StageEvent(
            stage=StageName.EVIDENCE_PACKAGE_ASSEMBLY,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(action, report),
            output_ids=(package_id,),
        ),
    )
    return package, events


def test_released_recommendation_has_evidence_package_and_provenance_id() -> None:
    package, events = _issue22_provenance_inputs()

    result = write_provenance_trace(
        evidence_package=package,
        provenance_id="https://example.org/provenance/Pump12",
        recommendation_id=package.action_id,
        agent_id="https://example.org/agent/S4",
        prompt_id="https://example.org/prompt/Pump12",
        model_id="https://example.org/model/Fixture",
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        stage_events=events,
        persist_trace=lambda graph: None,
    )

    assert result.provenance_id == "https://example.org/provenance/Pump12"
    assert result.recommendation_id == package.action_id
    assert result.stage_event.input_ids == (package.package_id,)
    assert result.trace_graph_evidence


def test_provenance_write_failure_blocks_recommendation_release() -> None:
    package, events = _issue22_provenance_inputs()

    def fail_write(graph: Graph) -> None:
        raise OSError("simulated persistence failure")

    result = write_provenance_trace(
        evidence_package=package,
        provenance_id="https://example.org/provenance/Pump12",
        recommendation_id=package.action_id,
        agent_id="https://example.org/agent/S4",
        prompt_id="https://example.org/prompt/Pump12",
        model_id="https://example.org/model/Fixture",
        recorded_at=datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC),
        stage_events=events,
        persist_trace=fail_write,
    )

    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    assert result.stage_event.status is TerminalStatus.PROVENANCE_FAILED_CLOSED


def test_pump_station_vertical_slice_passes_deterministic_tests() -> None:
    first_success = _issue23_orchestration_result()
    second_success = _issue23_orchestration_result()
    failed_scenario = json.loads(
        (_REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json").read_text(
            encoding="utf-8"
        )
    )
    del failed_scenario["observation"]
    failure = _issue23_orchestration_result(scenario=failed_scenario)

    assert first_success == second_success
    assert first_success.terminal_status is TerminalStatus.PASSED
    assert tuple(event.stage for event in first_success.events) == CANONICAL_S4_STAGE_NAMES
    assert first_success.released_action is not None
    assert first_success.evidence_package is not None
    assert first_success.provenance_id is not None
    assert failure.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert tuple(event.stage for event in failure.events) == CANONICAL_S4_STAGE_NAMES[:2]
    assert failure.released_action is None
    assert failure.evidence_package is None
    assert failure.provenance_id is None


@pytest.mark.xfail(
    strict=True,
    reason="Shared result schema delivered by #32; runnable strategies remain pending #35-#39",
)
def test_s1_to_s4_run_through_one_comparable_harness() -> None:
    _architecture_gap(32, 35, 36, 37, 38, 39)


def test_architecture_v1_deviations_are_recorded_not_silent() -> None:
    pull_request_template = (_REPOSITORY_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    issue_workflow = (_REPOSITORY_ROOT / "docs" / "implementation-v1-issue-workflow.md").read_text(
        encoding="utf-8"
    )

    assert "### Drift guardrail" in pull_request_template
    assert "was silently weakened" in pull_request_template
    assert "Do not silently alter Architecture V1" in issue_workflow
    assert "implementation-decisions.md" in issue_workflow
