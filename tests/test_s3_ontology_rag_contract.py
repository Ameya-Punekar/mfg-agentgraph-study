"""Consumer-visible S3 retrieval, harness, and post-hoc validation contracts."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from rdflib import URIRef

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, load_query_set
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationStrategy,
)
from mfg_agentgraph.evaluation_metrics import MetricApplicability, MetricName, compute_query_metrics
from mfg_agentgraph.procedural_retrieval import ProceduralRetriever
from mfg_agentgraph.s3_ontology_rag import (
    S3Fact,
    S3FactualBlock,
    S3QueryEvaluation,
    build_s3_run_configuration,
    check_s3_candidate_post_hoc,
    retrieve_ontology_grounded,
    run_s3_query,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus
from mfg_agentgraph.structured_retrieval import StructuredRetriever

ROOT = Path(__file__).resolve().parents[1]
QUERY_SET = load_query_set(ROOT / "evaluation/anomaly_triage/query-set-v1.json")
SCENARIO = json.loads((ROOT / "tests/fixtures/pump_12/scenario.json").read_text(encoding="utf-8"))
ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
PROCEDURE = "ex:Procedure_InspectInletCavitation_Pump12"


def _query() -> QueryRecord:
    return next(query for query in QUERY_SET.queries if query.query_id == "atq-013")


def _run(
    *, query: QueryRecord | None = None, scenario: dict[str, Any] | None = None
) -> S3QueryEvaluation:
    selected_query = _query() if query is None else query
    source = SCENARIO if scenario is None else scenario
    run_id = f"run:s3:{selected_query.query_id}"
    return run_s3_query(
        selected_query,
        build_s3_run_configuration(QUERY_SET),
        scenario=source,
        structured_result=StructuredRetriever().retrieve(
            resolved_asset=ASSET,
            scenario=source,
            retrieval_run_id=run_id,
            query_id=selected_query.query_id,
        ),
        procedural_result=ProceduralRetriever().retrieve(
            resolved_asset=ASSET,
            scenario=source,
            retrieval_run_id=run_id,
            query_id=selected_query.query_id,
        ),
        harness_version="v1",
        repository_revision="504af16",
    )


def _block(
    name: str,
    facts: tuple[S3Fact, ...],
    *,
    asset: str = "ex:Pump_12",
    procedure: str = PROCEDURE,
) -> S3FactualBlock:
    return S3FactualBlock(name, asset, procedure, facts, (f"ex:KG_{name}", f"ex:DOC_{name}"))


def test_s3_emits_actual_hybrid_support_without_s4_release_claims() -> None:
    evaluation = _run()
    payload = json.loads(evaluation.result.to_json())
    assert payload["configuration"]["strategy"] == "s3"
    assert payload["manifest"]["dataset_sha256"] == QUERY_SET.document_sha256
    assert payload["raw_output"]["recommendation"] == (
        "Inspect the pump inlet of Pump_12 for cavitation"
    )
    assert payload["raw_output"]["terminal_status"] == "passed"
    assert payload["raw_output"]["constraint_validated"] is False
    assert payload["raw_output"]["provenance_id"] is None
    artifacts = {item.kind: item for item in evaluation.result.artifacts}
    context = artifacts[ArtifactKind.RETRIEVED_CONTEXT].to_dict()["value"]
    assert isinstance(context, dict)
    assert context["evidence_ids"] == ["ex:EvidenceEdge_001", "ex:SOP_Chunk_7"]
    assert artifacts[ArtifactKind.VALIDATION_REPORT].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    assert artifacts[ArtifactKind.PROVENANCE_TRACE].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    metrics = compute_query_metrics(evaluation.observation, _query())
    assert metrics[MetricName.EVIDENCE_SUPPORT_COVERAGE].value == 1.0
    for name in (
        MetricName.INITIAL_SHACL_PASS,
        MetricName.FINAL_SHACL_PASS,
        MetricName.REPAIR_ITERATIONS,
        MetricName.PROVENANCE_COMPLETENESS,
    ):
        assert metrics[name].applicability is MetricApplicability.NOT_APPLICABLE


def test_greedy_coverage_prefers_one_covering_block_and_breaks_ties_by_identity() -> None:
    inlet, sound = S3Fact("inlet", "cavitation"), S3Fact("sound", "anomalous")
    single = _block("0-single", (inlet,))
    joint_b = _block("b-joint", (inlet, sound))
    joint_a = _block("a-joint", (sound, inlet))
    blocks = (single, joint_b, joint_a)
    query_text = "inlet sound cavitation anomalous"

    selected = retrieve_ontology_grounded(
        blocks, query_text, asset_id=ASSET.asset_id, top_k=3, max_blocks=3
    )
    reversed_selected = retrieve_ontology_grounded(
        tuple(reversed(blocks)), query_text, asset_id=ASSET.asset_id, top_k=3, max_blocks=3
    )

    # The joint block covers two relevant facts, so it is selected before the single one.
    assert selected[0] is joint_a
    assert selected == (joint_a, single)
    assert reversed_selected == selected
    assert retrieve_ontology_grounded(
        blocks, query_text, asset_id=ASSET.asset_id, top_k=3, max_blocks=1
    ) == (joint_a,)


def test_key_and_value_rankings_both_contribute_and_context_is_bounded() -> None:
    by_key = _block("a", (S3Fact("cavitation", "inspect"),))
    by_value = _block("b", (S3Fact("symptom", "cavitation"),))
    irrelevant = _block("c", (S3Fact("bearing", "grease"),))
    assert retrieve_ontology_grounded(
        (irrelevant, by_value, by_key),
        "cavitation",
        asset_id=ASSET.asset_id,
        top_k=1,
        max_blocks=2,
    ) == (by_key, by_value)
    assert retrieve_ontology_grounded(
        (by_value, by_key),
        "cavitation",
        asset_id=ASSET.asset_id,
        top_k=1,
        max_blocks=1,
    ) == (by_key,)


def test_ontology_applicability_filters_before_relevance_ranking() -> None:
    fact = (S3Fact("inlet", "cavitation"),)
    valid = _block("z-valid", fact)
    wrong_asset = _block("a-wrong", fact, asset="ex:Pump_99")
    wrong_procedure = _block("b-wrong", fact, procedure="ex:Lubricate")
    assert retrieve_ontology_grounded(
        (wrong_asset, wrong_procedure, valid),
        "cavitation",
        asset_id=ASSET.asset_id,
        procedure_id=PROCEDURE,
    ) == (valid,)


@pytest.mark.parametrize("text", ["unrelated gearbox grease", "the and of", "   "])
def test_no_relevant_facts_returns_no_context(text: str) -> None:
    assert (
        retrieve_ontology_grounded(
            (_block("inlet", (S3Fact("inlet", "cavitation"),)),),
            text,
            asset_id=ASSET.asset_id,
        )
        == ()
    )


@pytest.mark.parametrize("missing", ["kg_evidence", "document_evidence"])
def test_missing_hybrid_support_is_countable_and_does_not_generate(missing: str) -> None:
    scenario = copy.deepcopy(SCENARIO)
    scenario.pop(missing)
    evaluation = _run(scenario=scenario)
    assert evaluation.candidate is None
    assert evaluation.observation.terminal_status is not TerminalStatus.PASSED
    assert evaluation.observation.predicted_answer == ""
    assert evaluation.observation.cited_evidence_refs == ()
    assert evaluation.result.errors


def test_wrong_asset_and_unrelated_queries_do_not_borrow_fixture_answer() -> None:
    wrong_asset = _run(query=replace(_query(), asset_id="ex:Pump_99"))
    unrelated = _run(query=replace(_query(), text="Lubricate the gearbox gears"))
    for evaluation in (wrong_asset, unrelated):
        assert evaluation.observation.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
        assert evaluation.observation.predicted_answer == ""
        assert evaluation.observation.cited_evidence_refs == ()


def test_gold_labels_do_not_drive_generation() -> None:
    original = _run()
    changed_labels = _run(
        query=replace(
            _query(),
            expected_action="Replace an unrelated gearbox",
            expected_evidence_refs=("ex:Other",),
        )
    )
    assert changed_labels.result.to_json() == original.result.to_json()
    assert changed_labels.observation == original.observation


def test_post_hoc_failure_does_not_gate_or_relabel_original_s3_output() -> None:
    evaluation = _run()
    before = evaluation.result.to_json()
    resources = {
        identifier: URIRef("https://example.org/" + identifier.removeprefix("ex:"))
        for identifier in (
            "ex:Pump_12",
            "ex:Observation_Pump12_2026-05-18T14:03:00Z",
            PROCEDURE,
            "ex:EvidenceEdge_001",
            "ex:SOP_Chunk_7",
        )
    }
    report = check_s3_candidate_post_hoc(
        evaluation,
        action_iri=URIRef("https://example.org/S3Action"),
        resource_iris=resources,
        anomaly_window_start="2026-05-18T15:00:00Z",
        anomaly_window_end="2026-05-18T15:10:00Z",
        report_uri=URIRef("https://example.org/PostHocReport"),
    )
    assert report.conforms is False
    assert report.violations
    assert evaluation.result.to_json() == before
    assert evaluation.observation.terminal_status is TerminalStatus.PASSED
    assert evaluation.observation.final_shacl_passed is None


@pytest.mark.parametrize("top_k,max_blocks", [(0, 1), (1, 0), (True, 1), (1, True)])
def test_retrieval_bounds_reject_invalid_values(top_k: int, max_blocks: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        retrieve_ontology_grounded(
            (), "inlet", asset_id=ASSET.asset_id, top_k=top_k, max_blocks=max_blocks
        )


def test_duplicate_block_identity_is_rejected_instead_of_ambiguous_attribution() -> None:
    first = _block("same", (S3Fact("inlet", "cavitation"),))
    second = _block("same", (S3Fact("bearing", "grease"),))
    with pytest.raises(ValueError, match="duplicate"):
        retrieve_ontology_grounded((first, second), "inlet", asset_id=ASSET.asset_id)


def test_configuration_strategy_tampering_is_rejected() -> None:
    query = _query()
    run_id = f"run:s3:{query.query_id}"
    with pytest.raises(ValueError, match="S3"):
        run_s3_query(
            query,
            replace(build_s3_run_configuration(QUERY_SET), strategy=EvaluationStrategy.S4),
            scenario=SCENARIO,
            structured_result=StructuredRetriever().retrieve(
                resolved_asset=ASSET,
                scenario=SCENARIO,
                retrieval_run_id=run_id,
                query_id=query.query_id,
            ),
            procedural_result=ProceduralRetriever().retrieve(
                resolved_asset=ASSET,
                scenario=SCENARIO,
                retrieval_run_id=run_id,
                query_id=query.query_id,
            ),
            harness_version="v1",
            repository_revision="504af16",
        )


def _evaluation_with_config(configuration: object) -> S3QueryEvaluation:
    query = _query()
    run_id = f"run:s3:{query.query_id}"
    return run_s3_query(
        query,
        configuration,  # type: ignore[arg-type]
        scenario=SCENARIO,
        structured_result=StructuredRetriever().retrieve(
            resolved_asset=ASSET,
            scenario=SCENARIO,
            retrieval_run_id=run_id,
            query_id=query.query_id,
        ),
        procedural_result=ProceduralRetriever().retrieve(
            resolved_asset=ASSET,
            scenario=SCENARIO,
            retrieval_run_id=run_id,
            query_id=query.query_id,
        ),
        harness_version="v1",
        repository_revision="504af16",
    )


def test_restricted_context_cannot_release_an_over_citing_candidate() -> None:
    restricted = build_s3_run_configuration(QUERY_SET, max_blocks=1)

    evaluation = _evaluation_with_config(restricted)

    assert evaluation.candidate is None
    assert evaluation.observation.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert [error.field for error in evaluation.result.errors] == ["support_evidence"]


@pytest.mark.parametrize(
    ("factory", "error"),
    [
        (lambda: S3Fact(1, "x"), TypeError),  # type: ignore[arg-type]
        (lambda: S3Fact(" ", "x"), ValueError),
        (lambda: S3Fact("k", " "), ValueError),
        (lambda: S3Fact("k", "x" * 1_000_001), ValueError),
        (lambda: S3Fact("k" * 1_025, "x"), ValueError),
    ],
)
def test_fact_validation_fails_closed(factory: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        factory()


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"facts": "not-a-sequence"}, TypeError),
        ({"facts": ()}, ValueError),
        ({"facts": ("not-a-fact",)}, TypeError),
        ({"evidence_ids": "ex:One"}, TypeError),
        ({"evidence_ids": ()}, ValueError),
        ({"evidence_ids": ("ex:One", "ex:One")}, ValueError),
        ({"name": " "}, ValueError),
    ],
)
def test_factual_block_validation_fails_closed(
    kwargs: dict[str, Any], error: type[Exception]
) -> None:
    arguments: dict[str, Any] = {
        "name": "block",
        "asset_id": "ex:Pump_12",
        "procedure_id": PROCEDURE,
        "facts": (S3Fact("inlet", "cavitation"),),
        "evidence_ids": ("ex:One",),
    }
    arguments.update(kwargs)
    with pytest.raises(error):
        S3FactualBlock(**arguments)


def test_retrieval_rejects_invalid_inputs_and_foreign_scopes() -> None:
    block = _block("block", (S3Fact("inlet", "cavitation"),))
    with pytest.raises(TypeError, match="blocks"):
        retrieve_ontology_grounded("block", "inlet", asset_id=ASSET.asset_id)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="S3FactualBlock"):
        retrieve_ontology_grounded((block, "block"), "inlet", asset_id=ASSET.asset_id)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="asset_id"):
        retrieve_ontology_grounded((block,), "inlet", asset_id=" ")
    with pytest.raises(ValueError, match="procedure_id"):
        retrieve_ontology_grounded((block,), "inlet", asset_id=ASSET.asset_id, procedure_id=" ")
    with pytest.raises(TypeError, match="query_text"):
        retrieve_ontology_grounded((block,), 7, asset_id=ASSET.asset_id)  # type: ignore[arg-type]

    assert retrieve_ontology_grounded((block,), "inlet", asset_id="ex:Pump_99") == ()


def test_configuration_and_evaluation_guards() -> None:
    evaluation = _run()
    with pytest.raises(TypeError, match="query_set"):
        build_s3_run_configuration("query-set")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="max_blocks"):
        build_s3_run_configuration(QUERY_SET, max_blocks=0)
    with pytest.raises(TypeError, match="top_k"):
        build_s3_run_configuration(QUERY_SET, top_k=True)

    valid = {
        "result": evaluation.result,
        "observation": evaluation.observation,
        "candidate": evaluation.candidate,
        "structured_result": evaluation.structured_result,
        "procedural_result": evaluation.procedural_result,
    }
    for field_name, value in (
        ("result", "record"),
        ("observation", "observation"),
        ("candidate", "candidate"),
        ("structured_result", "structured"),
        ("procedural_result", "procedural"),
    ):
        with pytest.raises(TypeError):
            S3QueryEvaluation(**{**valid, field_name: value})  # type: ignore[arg-type]


def test_run_s3_query_rejects_invalid_inputs() -> None:
    query = _query()
    configuration = build_s3_run_configuration(QUERY_SET)
    run_id = f"run:s3:{query.query_id}"
    structured = StructuredRetriever().retrieve(
        resolved_asset=ASSET, scenario=SCENARIO, retrieval_run_id=run_id, query_id=query.query_id
    )
    procedural = ProceduralRetriever().retrieve(
        resolved_asset=ASSET, scenario=SCENARIO, retrieval_run_id=run_id, query_id=query.query_id
    )
    arguments: dict[str, Any] = {
        "scenario": SCENARIO,
        "structured_result": structured,
        "procedural_result": procedural,
        "harness_version": "v1",
        "repository_revision": "504af16",
    }

    with pytest.raises(TypeError, match="query"):
        run_s3_query("atq-013", configuration, **arguments)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="configuration"):
        run_s3_query(query, "config", **arguments)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="S3"):
        run_s3_query(
            query,
            replace(configuration, strategy=EvaluationStrategy.S1),
            **arguments,
        )
    with pytest.raises(TypeError, match="scenario"):
        run_s3_query(query, configuration, **{**arguments, "scenario": []})
    with pytest.raises(TypeError, match="structured_result"):
        run_s3_query(query, configuration, **{**arguments, "structured_result": "x"})
    with pytest.raises(TypeError, match="procedural_result"):
        run_s3_query(query, configuration, **{**arguments, "procedural_result": "x"})


def test_post_hoc_requires_a_recorded_candidate() -> None:
    failed = copy.deepcopy(SCENARIO)
    failed.pop("kg_evidence")
    evaluation = _run(scenario=failed)
    resources = {"ex:Pump_12": URIRef("https://example.org/Pump_12")}

    with pytest.raises(TypeError, match="evaluation"):
        check_s3_candidate_post_hoc(
            "evaluation",  # type: ignore[arg-type]
            action_iri=URIRef("https://example.org/Action"),
            resource_iris=resources,
            anomaly_window_start="2026-05-18T14:00:00Z",
            anomaly_window_end="2026-05-18T14:10:00Z",
            report_uri=URIRef("https://example.org/Report"),
        )
    with pytest.raises(ValueError, match="no candidate"):
        check_s3_candidate_post_hoc(
            evaluation,
            action_iri=URIRef("https://example.org/Action"),
            resource_iris=resources,
            anomaly_window_start="2026-05-18T14:00:00Z",
            anomaly_window_end="2026-05-18T14:10:00Z",
            report_uri=URIRef("https://example.org/Report"),
        )
