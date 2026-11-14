"""Behavior contract for the deterministic RQ metric suite."""

from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, load_query_set
from mfg_agentgraph.evaluation_metrics import (
    DEFERRED_METRICS,
    METRIC_RQ,
    REQUIRED_PROVENANCE_COMPONENTS,
    MetricApplicability,
    MetricName,
    MetricObservation,
    MetricSummary,
    MetricValue,
    ResearchQuestion,
    compute_query_metrics,
    summarize_run,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation" / "anomaly_triage" / "query-set-v1.json"
)
EXPECTED_ACTION = "Inspect Pump 12 inlet for cavitation according to SOP section 7"


def _query(query_id: str) -> QueryRecord:
    query_set = load_query_set(DATASET_PATH)
    return next(query for query in query_set.queries if query.query_id == query_id)


def _observation(**overrides: object) -> MetricObservation:
    payload: dict[str, object] = {
        "query_id": "atq-013",
        "predicted_answer": EXPECTED_ACTION,
        "cited_evidence_refs": ["ex:EvidenceEdge_001", "ex:SOP_Chunk_7"],
        "terminal_status": TerminalStatus.PASSED,
    }
    payload.update(overrides)
    return MetricObservation(**payload)  # type: ignore[arg-type]


def _metric(observation: MetricObservation, query: QueryRecord, name: MetricName) -> MetricValue:
    return compute_query_metrics(observation, query)[name]


def test_fully_supported_answer_scores_one_on_every_applicable_metric() -> None:
    observation = _observation()
    query = _query("atq-013")

    metrics = compute_query_metrics(observation, query)

    assert metrics[MetricName.HITS_AT_ANY].value == 1.0
    assert metrics[MetricName.EVIDENCE_SUPPORT_COVERAGE].value == 1.0
    assert metrics[MetricName.EVIDENCE_CITATION_PRECISION].value == 1.0
    assert metrics[MetricName.ANSWER_ACTION_EXACT_MATCH].value == 1.0
    assert metrics[MetricName.ANSWER_ACTION_TOKEN_F1].value == 1.0
    assert metrics[MetricName.TERMINAL_STATUS_MATCH].value == 1.0
    assert {
        name
        for name, value in metrics.items()
        if value.applicability is MetricApplicability.PRESENT
    } == {
        MetricName.HITS_AT_ANY,
        MetricName.EVIDENCE_SUPPORT_COVERAGE,
        MetricName.EVIDENCE_CITATION_PRECISION,
        MetricName.ANSWER_ACTION_EXACT_MATCH,
        MetricName.ANSWER_ACTION_TOKEN_F1,
        MetricName.TERMINAL_STATUS_MATCH,
    }


def test_partial_evidence_and_paraphrased_answer_score_proportionally() -> None:
    observation = _observation(
        predicted_answer="Inspect the pump inlet for cavitation",
        cited_evidence_refs=["ex:SOP_Chunk_7", "ex:Other_Edge"],
    )
    query = _query("atq-013")

    metrics = compute_query_metrics(observation, query)

    assert metrics[MetricName.EVIDENCE_SUPPORT_COVERAGE].value == 0.5
    assert metrics[MetricName.EVIDENCE_CITATION_PRECISION].value == 0.5
    assert metrics[MetricName.HITS_AT_ANY].value == 1.0
    assert metrics[MetricName.ANSWER_ACTION_EXACT_MATCH].value == 0.0
    assert metrics[MetricName.ANSWER_ACTION_TOKEN_F1].value == pytest.approx(10 / 17, abs=1e-6)


def test_trap_query_metrics_keep_absence_explicit() -> None:
    observation = _observation(
        query_id="atq-027",
        predicted_answer="The corpus does not cover grease intervals.",
        cited_evidence_refs=[],
        terminal_status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        initial_shacl_passed=None,
        final_shacl_passed=None,
        repair_iterations=None,
        provenance_components=None,
    )
    query = _query("atq-027")

    metrics = compute_query_metrics(observation, query)

    assert metrics[MetricName.HITS_AT_ANY].value == 0.0
    assert metrics[MetricName.TERMINAL_STATUS_MATCH].value == 1.0
    coverage = metrics[MetricName.EVIDENCE_SUPPORT_COVERAGE]
    assert coverage.value is None
    assert coverage.applicability is MetricApplicability.NOT_APPLICABLE
    assert coverage.reason is not None and "trap" in coverage.reason
    assert metrics[MetricName.ANSWER_ACTION_EXACT_MATCH].applicability is (
        MetricApplicability.NOT_APPLICABLE
    )
    assert metrics[MetricName.ANSWER_ACTION_TOKEN_F1].value is None
    assert metrics[MetricName.PROVENANCE_COMPLETENESS].value is None


def test_validation_and_repair_metrics_track_the_gate_outcome() -> None:
    repaired = _observation(
        initial_shacl_passed=False,
        final_shacl_passed=True,
        repair_iterations=2,
    )
    metrics = compute_query_metrics(repaired, _query("atq-013"))

    assert metrics[MetricName.INITIAL_SHACL_PASS].value == 0.0
    assert metrics[MetricName.FINAL_SHACL_PASS].value == 1.0
    assert metrics[MetricName.REPAIR_ITERATIONS].value == 2.0
    assert metrics[MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE].value == 1.0

    already_valid = _observation(initial_shacl_passed=True, final_shacl_passed=True)
    valid_metrics = compute_query_metrics(already_valid, _query("atq-013"))
    repaired_metric = valid_metrics[MetricName.REPAIR_SUCCEEDED_AFTER_FAILURE]
    assert repaired_metric.value is None
    assert repaired_metric.applicability is MetricApplicability.NOT_APPLICABLE
    assert repaired_metric.reason is not None and "already passed" in repaired_metric.reason

    unvalidated = _observation()
    unvalidated_metrics = compute_query_metrics(unvalidated, _query("atq-013"))
    for name in (
        MetricName.INITIAL_SHACL_PASS,
        MetricName.FINAL_SHACL_PASS,
        MetricName.REPAIR_ITERATIONS,
    ):
        assert unvalidated_metrics[name].applicability is MetricApplicability.NOT_APPLICABLE


def test_provenance_completeness_counts_required_components_only() -> None:
    observation = _observation(provenance_components=["agent", "activity", "entity", "used"])

    value = compute_query_metrics(observation, _query("atq-013"))[
        MetricName.PROVENANCE_COMPLETENESS
    ]

    assert value.value == pytest.approx(4 / len(REQUIRED_PROVENANCE_COMPONENTS))
    assert value.value == pytest.approx(0.8)


def test_summarize_run_reports_means_percentiles_and_peak_memory() -> None:
    queries = [_query("atq-013"), _query("atq-014"), _query("atq-015")]
    observations = [
        _observation(query_id="atq-013", latency_ms=10.0, peak_memory_mb=512.0),
        _observation(query_id="atq-014", latency_ms=20.0, peak_memory_mb=640.0),
        _observation(query_id="atq-015", latency_ms=100.0, peak_memory_mb=600.0),
    ]

    summary = summarize_run(observations, queries)

    assert summary[MetricName.LATENCY_P50_MS].value == 20.0
    assert summary[MetricName.LATENCY_P95_MS].value == 100.0
    assert summary[MetricName.PEAK_MEMORY_MB].value == 640.0
    assert summary[MetricName.HITS_AT_ANY].value == 1.0
    assert summary[MetricName.HITS_AT_ANY].applicable_count == 3
    assert summary[MetricName.HITS_AT_ANY].undefined_count == 0
    assert summary[MetricName.LATENCY_P50_MS].applicable_count == 3


def test_summarize_run_counts_undefined_metrics_separately() -> None:
    queries = [_query("atq-013"), _query("atq-014")]
    observations = [
        _observation(query_id="atq-013", latency_ms=10.0, initial_shacl_passed=False),
        _observation(query_id="atq-014", latency_ms=None, initial_shacl_passed=True),
    ]

    summary = summarize_run(observations, queries)

    assert summary[MetricName.LATENCY_P50_MS].value == 10.0
    assert summary[MetricName.LATENCY_P50_MS].applicable_count == 1
    assert summary[MetricName.LATENCY_P50_MS].undefined_count == 1
    assert summary[MetricName.INITIAL_SHACL_PASS].value == 0.5
    assert summary[MetricName.INITIAL_SHACL_PASS].applicable_count == 2
    assert summary[MetricName.PEAK_MEMORY_MB].value is None
    assert summary[MetricName.PEAK_MEMORY_MB].reason is not None


def test_summarize_run_rejects_mismatched_or_empty_inputs() -> None:
    with pytest.raises(ValueError, match="query_id"):
        summarize_run([_observation(query_id="atq-014")], [_query("atq-013")])
    with pytest.raises(ValueError, match="at least one"):
        summarize_run([], [])
    with pytest.raises(ValueError, match="duplicate"):
        summarize_run(
            [_observation(query_id="atq-013"), _observation(query_id="atq-013")],
            [_query("atq-013"), _query("atq-014")],
        )


def test_metric_names_map_to_research_questions_and_deferred_metrics_are_explicit() -> None:
    assert set(METRIC_RQ) == set(MetricName)
    assert set(METRIC_RQ.values()) == set(ResearchQuestion)
    assert METRIC_RQ[MetricName.PROVENANCE_COMPLETENESS] is ResearchQuestion.RQ3
    assert METRIC_RQ[MetricName.LATENCY_P95_MS] is ResearchQuestion.RQ4
    assert METRIC_RQ[MetricName.FINAL_SHACL_PASS] is ResearchQuestion.RQ2
    assert METRIC_RQ[MetricName.ANSWER_ACTION_TOKEN_F1] is ResearchQuestion.RQ1
    assert "ragas_faithfulness" in DEFERRED_METRICS
    assert all(reason.strip() for reason in DEFERRED_METRICS.values())


def test_query_metrics_are_deterministic_and_canonically_ordered() -> None:
    observation = _observation(
        initial_shacl_passed=False,
        final_shacl_passed=True,
        repair_iterations=1,
        provenance_components=list(REQUIRED_PROVENANCE_COMPONENTS),
    )
    query = _query("atq-013")

    first = compute_query_metrics(observation, query)
    second = compute_query_metrics(observation, query)

    assert list(first) == list(MetricName)[: len(first)]
    assert [value.to_dict() for value in first.values()] == [
        value.to_dict() for value in second.values()
    ]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"repair_iterations": -1}, "repair_iterations"),
        ({"repair_iterations": True}, "repair_iterations"),
        ({"latency_ms": math.inf}, "latency_ms"),
        ({"peak_memory_mb": -1.0}, "peak_memory_mb"),
        ({"cited_evidence_refs": ["ex:EvidenceEdge_001", "ex:EvidenceEdge_001"]}, "cited"),
        ({"cited_evidence_refs": "ex:EvidenceEdge_001"}, "cited"),
        ({"terminal_status": "passed"}, "terminal_status"),
        ({"query_id": " "}, "query_id"),
        ({"provenance_components": ["agent", "agent"]}, "provenance_components"),
    ],
)
def test_observation_rejects_invalid_inputs(overrides: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _observation(**overrides)


def test_metric_values_and_summaries_enforce_their_invariants() -> None:
    with pytest.raises(ValueError, match="present metric"):
        MetricValue(
            metric=MetricName.HITS_AT_ANY,
            value=None,
            applicability=MetricApplicability.PRESENT,
            reason=None,
        )
    with pytest.raises(ValueError, match="not-applicable metric"):
        MetricValue(
            metric=MetricName.HITS_AT_ANY,
            value=1.0,
            applicability=MetricApplicability.NOT_APPLICABLE,
            reason="ignored",
        )
    with pytest.raises(ValueError, match="reason"):
        MetricValue(
            metric=MetricName.HITS_AT_ANY,
            value=None,
            applicability=MetricApplicability.NOT_APPLICABLE,
            reason=None,
        )
    value = MetricValue(
        metric=MetricName.HITS_AT_ANY,
        value=1.0,
        applicability=MetricApplicability.PRESENT,
        reason=None,
    )
    assert json.loads(json.dumps(value.to_dict())) == {
        "applicability": "present",
        "metric": "hits_at_any",
        "reason": None,
        "value": 1.0,
    }
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.value = 0.0  # type: ignore[misc]
    with pytest.raises(ValueError, match="reason"):
        MetricSummary(
            metric=MetricName.HITS_AT_ANY,
            rq=ResearchQuestion.RQ1,
            value=None,
            applicable_count=0,
            undefined_count=1,
            reason=None,
        )


def test_metric_value_rejects_wrong_enums_and_non_finite_values() -> None:
    with pytest.raises(TypeError, match="MetricName"):
        MetricValue(
            metric="hits_at_any",  # type: ignore[arg-type]
            value=1.0,
            applicability=MetricApplicability.PRESENT,
            reason=None,
        )
    with pytest.raises(TypeError, match="MetricApplicability"):
        MetricValue(
            metric=MetricName.HITS_AT_ANY,
            value=1.0,
            applicability="present",  # type: ignore[arg-type]
            reason=None,
        )
    with pytest.raises(ValueError, match="finite"):
        MetricValue(
            metric=MetricName.HITS_AT_ANY,
            value=math.nan,
            applicability=MetricApplicability.PRESENT,
            reason=None,
        )


def test_metric_summary_rejects_wrong_enums_counts_and_reasons() -> None:
    with pytest.raises(TypeError, match="MetricName"):
        MetricSummary(
            metric="hits_at_any",  # type: ignore[arg-type]
            rq=ResearchQuestion.RQ1,
            value=1.0,
            applicable_count=1,
            undefined_count=0,
            reason=None,
        )
    with pytest.raises(TypeError, match="ResearchQuestion"):
        MetricSummary(
            metric=MetricName.HITS_AT_ANY,
            rq="RQ1",  # type: ignore[arg-type]
            value=1.0,
            applicable_count=1,
            undefined_count=0,
            reason=None,
        )
    with pytest.raises(TypeError, match="applicable_count"):
        MetricSummary(
            metric=MetricName.HITS_AT_ANY,
            rq=ResearchQuestion.RQ1,
            value=1.0,
            applicable_count=True,
            undefined_count=0,
            reason=None,
        )
    with pytest.raises(ValueError, match="undefined_count"):
        MetricSummary(
            metric=MetricName.HITS_AT_ANY,
            rq=ResearchQuestion.RQ1,
            value=1.0,
            applicable_count=1,
            undefined_count=-1,
            reason=None,
        )
    with pytest.raises(ValueError, match="finite"):
        MetricSummary(
            metric=MetricName.HITS_AT_ANY,
            rq=ResearchQuestion.RQ1,
            value=math.inf,
            applicable_count=1,
            undefined_count=0,
            reason=None,
        )
    with pytest.raises(ValueError, match="must not include a reason"):
        MetricSummary(
            metric=MetricName.HITS_AT_ANY,
            rq=ResearchQuestion.RQ1,
            value=1.0,
            applicable_count=1,
            undefined_count=0,
            reason="unexpected",
        )


def test_observation_rejects_wrong_optional_types_and_oversized_text() -> None:
    with pytest.raises(TypeError, match="initial_shacl_passed"):
        _observation(initial_shacl_passed="yes")
    with pytest.raises(TypeError, match="provenance_components"):
        _observation(provenance_components="agent")
    with pytest.raises(TypeError, match="latency_ms"):
        _observation(latency_ms="1200")
    with pytest.raises(ValueError, match="predicted_answer"):
        _observation(predicted_answer="x" * 8_193)


def test_summarize_run_requires_an_observation_for_every_query() -> None:
    with pytest.raises(ValueError, match="no observation"):
        summarize_run(
            [_observation(query_id="atq-013")],
            [_query("atq-013"), _query("atq-014")],
        )
