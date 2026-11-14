"""Behavior contract for the S4 strategy registered in the shared harness."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rdflib import Graph

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, QuerySet, load_query_set
from mfg_agentgraph.entity_resolution import AssetCatalog, KnownAsset
from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationStrategy,
)
from mfg_agentgraph.evaluation_metrics import (
    REQUIRED_PROVENANCE_COMPONENTS,
    MetricName,
    compute_query_metrics,
)
from mfg_agentgraph.s4_evaluation_strategy import (
    S4QueryEvaluation,
    build_s4_run_configuration,
    build_stable_ids,
    count_terminal_statuses,
    run_s4_query,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation" / "anomaly_triage" / "query-set-v1.json"
)
SCENARIO = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "pump_12" / "scenario.json").read_text(
        encoding="utf-8"
    )
)
CATALOG = AssetCatalog((KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),))
RECORDED_AT = datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC)


def _query_set() -> QuerySet:
    return load_query_set(DATASET_PATH)


def _query(query_id: str = "atq-013") -> QueryRecord:
    query_set = _query_set()
    return next(query for query in query_set.queries if query.query_id == query_id)


def _persist(_graph: Graph) -> None:
    return None


def _run(query: QueryRecord | None = None, **overrides: object) -> S4QueryEvaluation:
    arguments: dict[str, object] = {
        "scenario": SCENARIO,
        "asset_catalog": CATALOG,
        "recorded_at": RECORDED_AT,
        "persist_trace": _persist,
        "harness_version": "v1",
        "repository_revision": "6ee628c",
    }
    arguments.update(overrides)
    return run_s4_query(
        _query() if query is None else query,
        build_s4_run_configuration(_query_set()),
        **arguments,  # type: ignore[arg-type]
    )


def test_released_run_emits_one_comparable_record_and_full_observation() -> None:
    evaluation = _run(latency_ms=12.5, peak_memory_mb=640.0)

    result = evaluation.result
    payload = json.loads(result.to_json())

    assert result.configuration.strategy is EvaluationStrategy.S4
    assert payload["configuration"]["dataset_id"] == "mimii-pump12"
    assert payload["configuration"]["query_set_id"] == "anomaly-triage-v1"
    assert payload["manifest"]["dataset_sha256"] == _query_set().document_sha256
    assert payload["query_id"] == "atq-013"
    assert payload["raw_output"]["terminal_status"] == "passed"
    assert {artifact["kind"] for artifact in payload["artifacts"]} == {
        kind.value for kind in ArtifactKind
    }
    assert all(artifact["applicability"] == "present" for artifact in payload["artifacts"])
    assert result.errors == ()

    observation = evaluation.observation
    assert observation.terminal_status is TerminalStatus.PASSED
    assert observation.cited_evidence_refs == ("ex:EvidenceEdge_001", "ex:SOP_Chunk_7")
    assert observation.initial_shacl_passed is True
    assert observation.final_shacl_passed is True
    assert observation.repair_iterations == 0
    assert observation.latency_ms == 12.5
    assert observation.peak_memory_mb == 640.0
    assert set(observation.provenance_components or ()) >= set(REQUIRED_PROVENANCE_COMPONENTS)
    assert compute_query_metrics(observation, _query())[
        MetricName.PROVENANCE_COMPLETENESS
    ].value == pytest.approx(1.0)


def test_resolution_failure_is_recorded_and_counted_not_omitted() -> None:
    unknown_asset = replace(_query(), asset_id="ex:Pump_99")

    evaluation = _run(unknown_asset)

    raw_output = json.loads(evaluation.result.to_json())["raw_output"]
    assert raw_output["terminal_status"] == (TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED.value)
    assert raw_output["released"] is False
    assert evaluation.observation.terminal_status is (
        TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED
    )
    assert evaluation.observation.predicted_answer == ""
    assert evaluation.observation.cited_evidence_refs == ()
    assert evaluation.observation.initial_shacl_passed is None
    assert evaluation.observation.final_shacl_passed is None
    assert evaluation.observation.provenance_components is None
    artifacts = {artifact.kind: artifact for artifact in evaluation.result.artifacts}
    assert artifacts[ArtifactKind.ANSWER].applicability is ArtifactApplicability.PRESENT
    assert artifacts[ArtifactKind.VALIDATION_REPORT].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    assert artifacts[ArtifactKind.PROVENANCE_TRACE].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    assert [error.code for error in evaluation.result.errors] == [
        "operator_disambiguation_required"
    ]


def test_provenance_failure_fails_closed_and_keeps_validation_evidence() -> None:
    def failing_persist(_graph: Graph) -> None:
        raise RuntimeError("store unavailable")

    evaluation = _run(persist_trace=failing_persist)

    assert evaluation.observation.terminal_status is TerminalStatus.PROVENANCE_FAILED_CLOSED
    assert evaluation.observation.initial_shacl_passed is True
    assert evaluation.observation.final_shacl_passed is True
    assert evaluation.observation.provenance_components is None
    assert evaluation.observation.predicted_answer == ""
    artifacts = {artifact.kind: artifact for artifact in evaluation.result.artifacts}
    assert artifacts[ArtifactKind.VALIDATION_REPORT].applicability is (
        ArtifactApplicability.PRESENT
    )
    assert artifacts[ArtifactKind.PROVENANCE_TRACE].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    assert "provenance_write_failed" in {error.code for error in evaluation.result.errors}


def test_terminal_status_counts_include_every_fail_closed_path() -> None:
    def failing_persist(_graph: Graph) -> None:
        raise RuntimeError("store unavailable")

    evaluations = (
        _run(),
        _run(replace(_query(), asset_id="ex:Pump_99")),
        _run(persist_trace=failing_persist),
    )

    assert count_terminal_statuses(evaluations) == {
        TerminalStatus.PASSED: 1,
        TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED: 1,
        TerminalStatus.PROVENANCE_FAILED_CLOSED: 1,
    }
    assert count_terminal_statuses(()) == {}


def test_stable_ids_are_deterministic_and_unique_per_query() -> None:
    queries = _query_set().queries

    first = [build_stable_ids(query.query_id) for query in queries]
    second = [build_stable_ids(query.query_id) for query in queries]

    assert first == second
    # The deterministic generation contract fixes the candidate action identity, so every
    # run names the same fixture action while run-scoped identities stay unique.
    assert {ids.action_id for ids in first} == {"ex:CandidateAction_Pump12_Repaired_001"}
    assert len({ids.validation_report_id for ids in first}) == len(queries)
    assert len({ids.provenance_id for ids in first}) == len(queries)
    assert len({ids.evidence_package_id for ids in first}) == len(queries)
    with pytest.raises(ValueError, match="query_id"):
        build_stable_ids(" ")


def test_registration_rejects_mismatched_inputs() -> None:
    configuration = build_s4_run_configuration(_query_set())
    assert configuration.to_dict()["strategy"] == "s4"

    with pytest.raises(TypeError, match="query"):
        run_s4_query(
            "atq-013",  # type: ignore[arg-type]
            configuration,
            scenario=SCENARIO,
            asset_catalog=CATALOG,
            recorded_at=RECORDED_AT,
            persist_trace=_persist,
            harness_version="v1",
            repository_revision="6ee628c",
        )
    with pytest.raises(ValueError, match="S4"):
        run_s4_query(
            _query(),
            replace(configuration, strategy=EvaluationStrategy.S1),
            scenario=SCENARIO,
            asset_catalog=CATALOG,
            recorded_at=RECORDED_AT,
            persist_trace=_persist,
            harness_version="v1",
            repository_revision="6ee628c",
        )
    with pytest.raises(TypeError, match="persist_trace"):
        _run(persist_trace="not-callable")


def test_evaluation_record_is_immutable() -> None:
    evaluation = _run()

    assert not hasattr(evaluation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        evaluation.observation = evaluation.observation  # type: ignore[misc]


def test_registration_helpers_reject_wrong_types_and_patterns() -> None:
    with pytest.raises(TypeError, match="query_id"):
        build_stable_ids(13)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="atq-NNN"):
        build_stable_ids("query-13")
    with pytest.raises(TypeError, match="query_set"):
        build_s4_run_configuration("query-set")  # type: ignore[arg-type]

    configuration = build_s4_run_configuration(_query_set())
    evaluation = _run()
    with pytest.raises(TypeError, match="result"):
        S4QueryEvaluation(result="record", observation=evaluation.observation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="observation"):
        S4QueryEvaluation(result=evaluation.result, observation="observation")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="configuration"):
        run_s4_query(
            _query(),
            "configuration",  # type: ignore[arg-type]
            scenario=SCENARIO,
            asset_catalog=CATALOG,
            recorded_at=RECORDED_AT,
            persist_trace=_persist,
            harness_version="v1",
            repository_revision="6ee628c",
        )
    with pytest.raises(TypeError, match="scenario"):
        _run(scenario="scenario")
    with pytest.raises(TypeError, match="asset_catalog"):
        _run(asset_catalog="catalog")
    with pytest.raises(TypeError, match="recorded_at"):
        _run(recorded_at="2026-05-18")
    with pytest.raises(TypeError, match="S4QueryEvaluation"):
        count_terminal_statuses(["not-an-evaluation"])  # type: ignore[list-item]
    assert configuration.parameters.get("dataset_sha256") == _query_set().document_sha256
