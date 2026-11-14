"""Behavior contract for scoring a strategy run against the synthetic reference.

The scorer is a consumer, not a second metric implementation: it reuses the deterministic
metric engine, gates reference-dependent metrics on citation anchoring, and reports the
single-author scope alongside the numbers.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mfg_agentgraph.annotation_sources import load_source_manifest
from mfg_agentgraph.anomaly_triage_dataset import QuerySet, load_query_set
from mfg_agentgraph.evaluation_harness import EvaluationRunConfiguration
from mfg_agentgraph.evaluation_metrics import (
    MetricApplicability,
    MetricName,
    MetricObservation,
    compute_query_metrics,
    summarize_run,
)
from mfg_agentgraph.s1_naive_rag import (
    S1Index,
    build_s1_index_from_document,
    build_s1_run_configuration,
    run_s1_query,
)
from mfg_agentgraph.synthetic_evaluation import (
    REFERENCE_DEPENDENT_METRICS,
    REFERENCE_SCORE_CONTRACT_VERSION,
    ReferenceScore,
    score_reference_run,
)
from mfg_agentgraph.synthetic_reference import (
    ReferenceStrength,
    SyntheticReference,
    build_synthetic_reference,
    load_scenario_fixture,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "query-set-v1.json"
SOURCES_PATH = REPOSITORY_ROOT / "evaluation" / "anomaly_triage" / "sources-v1.json"
SCENARIO_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "pump_12" / "scenario.json"
SOP_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "sop" / "pump12-sop.txt"


def _query_set() -> QuerySet:
    return load_query_set(DATASET_PATH)


def _reference(query_set: QuerySet | None = None) -> SyntheticReference:
    return build_synthetic_reference(
        query_set=_query_set() if query_set is None else query_set,
        scenario=load_scenario_fixture(SCENARIO_PATH),
        source_manifest=load_source_manifest(SOURCES_PATH, root=REPOSITORY_ROOT),
    )


def _configuration() -> EvaluationRunConfiguration:
    return build_s1_run_configuration(_query_set())


def _sop_index() -> S1Index:
    return build_s1_index_from_document(
        SOP_PATH.read_text(encoding="utf-8"),
        document="SOP-PUMP-OPS-2026",
        first_chunk_index=7,
    )


def _observations(query_ids: list[str] | None = None) -> tuple[MetricObservation, ...]:
    configuration = _configuration()
    index = _sop_index()
    query_set = _query_set()
    selected = [
        query for query in query_set.queries if query_ids is None or query.query_id in query_ids
    ]
    return tuple(
        run_s1_query(
            query, configuration, index=index, harness_version="v1", repository_revision="test"
        ).observation
        for query in selected
    )


def test_score_reuses_the_metric_engine_instead_of_reimplementing_it() -> None:
    query_set = _query_set()
    reference = _reference()
    observations = _observations()

    score = score_reference_run(
        configuration=_configuration(),
        query_set=query_set,
        reference=reference,
        observations=observations,
    )

    assert score.contract_version == REFERENCE_SCORE_CONTRACT_VERSION
    assert set(score.per_query) == {query.query_id for query in query_set.queries}
    for observation in observations:
        query = next(item for item in query_set.queries if item.query_id == observation.query_id)
        expected = compute_query_metrics(observation, query)
        assert score.per_query[observation.query_id] == dict(expected)

    expected_summary = summarize_run(observations, query_set.queries)
    assert {name: value.to_dict() for name, value in score.summary.items()} == {
        name: value.to_dict() for name, value in expected_summary.items()
    }


def test_score_reports_the_single_author_scope_and_reference_digest() -> None:
    reference = _reference()
    score = score_reference_run(
        configuration=_configuration(),
        query_set=_query_set(),
        reference=reference,
        observations=_observations(["atq-013", "atq-027"]),
    )

    document = score.to_document()
    assert document["reference_sha256"] == reference.document_sha256
    assert document["query_set_sha256"] == reference.query_set_sha256
    assert document["scenario_sha256"] == reference.scenario_sha256
    authoring = document["authoring"]
    assert isinstance(authoring, dict)
    assert authoring["independent_annotation"] is False
    requirement_status = document["original_requirement_status"]
    assert isinstance(requirement_status, str)
    assert requirement_status.startswith("unmet")
    assert "two independent human annotators" in requirement_status
    scope = document["scope"]
    assert isinstance(scope, str)
    assert "not independently validated" in scope


def test_a_partial_run_scores_only_what_was_observed() -> None:
    """Issue #39 is a five-query pilot, so absence of the other queries must stay explicit."""
    score = score_reference_run(
        configuration=_configuration(),
        query_set=_query_set(),
        reference=_reference(),
        observations=_observations(["atq-013", "atq-014"]),
    )

    assert set(score.per_query) == {"atq-013", "atq-014"}
    document = score.to_document()
    assert document["observed_query_count"] == 2
    not_evaluated = document["not_evaluated_query_ids"]
    assert isinstance(not_evaluated, list)
    assert "atq-001" not in score.per_query
    assert set(not_evaluated) == {query.query_id for query in _query_set().queries} - {
        "atq-013",
        "atq-014",
    }


def test_unanchored_entries_suppress_reference_metrics_but_keep_measured_ones() -> None:
    query_set = _query_set()
    broken = replace(
        query_set,
        queries=tuple(
            replace(query, expected_evidence_refs=("ex:InventedEdge",))
            if query.query_id == "atq-013"
            else query
            for query in query_set.queries
        ),
    )
    reference = _reference(broken)
    entry = next(item for item in reference.entries if item.query_id == "atq-013")
    assert entry.strength is ReferenceStrength.UNANCHORED

    score = score_reference_run(
        configuration=build_s1_run_configuration(broken),
        query_set=broken,
        reference=reference,
        observations=_observations(["atq-013"]),
    )

    metrics = score.per_query["atq-013"]
    for name in REFERENCE_DEPENDENT_METRICS:
        value = metrics[name]
        assert value.applicability is MetricApplicability.NOT_APPLICABLE, name
        assert value.value is None
        assert value.reason is not None and "not anchored" in value.reason

    # The expected terminal status comes from the dataset contract, not from the citation, so
    # an unanchored citation must not erase a match the run genuinely produced.
    expected_status = next(query for query in _query_set().queries if query.query_id == "atq-013")
    assert expected_status.expected_terminal_status is None
    status_metric = metrics[MetricName.TERMINAL_STATUS_MATCH]
    assert status_metric.value == 1.0
    assert status_metric.applicability is MetricApplicability.PRESENT


def test_score_refuses_a_run_that_claims_a_different_dataset() -> None:
    other_configuration = replace(
        _configuration(),
        parameters={"dataset_sha256": "0" * 64},
    )

    with pytest.raises(ValueError, match="dataset_sha256"):
        score_reference_run(
            configuration=other_configuration,
            query_set=_query_set(),
            reference=_reference(),
            observations=_observations(["atq-013"]),
        )


def test_score_rejects_wrong_input_types_and_unknown_queries() -> None:
    with pytest.raises(TypeError, match="configuration must be an EvaluationRunConfiguration"):
        score_reference_run(
            configuration={"strategy": "s1"},  # type: ignore[arg-type]
            query_set=_query_set(),
            reference=_reference(),
            observations=_observations(["atq-013"]),
        )

    with pytest.raises(ValueError, match="has no matching query"):
        score_reference_run(
            configuration=_configuration(),
            query_set=_query_set(),
            reference=_reference(),
            observations=(replace(_observations(["atq-013"])[0], query_id="atq-999"),),
        )


def test_score_value_object_fails_closed_on_inconsistent_coverage() -> None:
    reference = _reference()
    score = score_reference_run(
        configuration=_configuration(),
        query_set=_query_set(),
        reference=reference,
        observations=_observations(["atq-013", "atq-014"]),
    )
    assert score.to_json().startswith('{"authoring":')
    assert score.document_sha256 == score.document_sha256

    base: dict[str, object] = {
        "strategy": score.strategy,
        "query_set_id": score.query_set_id,
        "model_configuration_id": score.model_configuration_id,
        "retrieval_configuration_id": score.retrieval_configuration_id,
        "random_seed": score.random_seed,
        "reference_sha256": score.reference_sha256,
        "query_set_sha256": score.query_set_sha256,
        "scenario_sha256": score.scenario_sha256,
        "authoring": score.authoring,
        "original_requirement_status": score.original_requirement_status,
        "per_query": score.per_query,
        "summary": score.summary,
        "observed_query_ids": ("atq-013",),
        "not_evaluated_query_ids": ("atq-014",),
        "suppressed_query_ids": (),
    }

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        ReferenceScore(**{**base, "scenario_sha256": "short"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="per_query must not be empty"):
        ReferenceScore(**{**base, "per_query": {}})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="both observed and not evaluated"):
        ReferenceScore(
            **{**base, "not_evaluated_query_ids": ("atq-013",)}  # type: ignore[arg-type]
        )


def test_score_guards_reject_bad_types_duplicates_and_mismatched_query_set() -> None:
    with pytest.raises(TypeError, match="query_set must be a QuerySet"):
        score_reference_run(
            configuration=_configuration(),
            query_set={"queries": ()},  # type: ignore[arg-type]
            reference=_reference(),
            observations=_observations(["atq-013"]),
        )
    with pytest.raises(TypeError, match="reference must be a SyntheticReference"):
        score_reference_run(
            configuration=_configuration(),
            query_set=_query_set(),
            reference={"entries": ()},  # type: ignore[arg-type]
            observations=_observations(["atq-013"]),
        )
    with pytest.raises(TypeError, match="observations must be a sequence"):
        score_reference_run(
            configuration=_configuration(),
            query_set=_query_set(),
            reference=_reference(),
            observations="atq-013",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="at least one observation"):
        score_reference_run(
            configuration=_configuration(),
            query_set=_query_set(),
            reference=_reference(),
            observations=(),
        )

    observation = _observations(["atq-013"])[0]
    with pytest.raises(ValueError, match="duplicate observation"):
        score_reference_run(
            configuration=_configuration(),
            query_set=_query_set(),
            reference=_reference(),
            observations=(observation, observation),
        )

    # A query set the reference does not describe must be refused, not silently scored.
    query_set = _query_set()
    other = replace(
        query_set,
        queries=tuple(
            replace(query, text=f"{query.text} (edited)") if query.query_id == "atq-013" else query
            for query in query_set.queries
        ),
    )
    with pytest.raises(ValueError, match="query set does not match the reference"):
        score_reference_run(
            configuration=_configuration(),
            query_set=other,
            reference=_reference(),
            observations=_observations(["atq-013"]),
        )


def test_summary_never_publishes_suppressed_label_metrics() -> None:
    """Per-query suppression is worthless if the aggregate still reports a number."""
    query_set = _query_set()
    broken = replace(
        query_set,
        queries=tuple(
            replace(query, expected_evidence_refs=("ex:InventedEdge",))
            if query.query_id == "atq-013"
            else query
            for query in query_set.queries
        ),
    )
    reference = _reference(broken)

    score = score_reference_run(
        configuration=build_s1_run_configuration(broken),
        query_set=broken,
        reference=reference,
        observations=_observations(["atq-013", "atq-014"]),
    )

    assert score.suppressed_query_ids == ("atq-013",)
    # Label-derived aggregates cover only the anchored query, and say so by coverage counts.
    for name in REFERENCE_DEPENDENT_METRICS:
        summary = score.summary[name]
        assert summary.applicable_count <= 1, name
        if summary.value is not None:
            assert summary.applicable_count == 1, name
    assert score.summary[MetricName.HITS_AT_ANY].value == 1.0
    assert score.summary[MetricName.HITS_AT_ANY].applicable_count == 1
    # Run-measured metrics keep covering every observed query, including the suppressed one.
    assert MetricName.HITS_AT_ANY in score.summary
    assert score.summary[MetricName.TERMINAL_STATUS_MATCH].applicable_count == 2


def test_summary_reports_absence_when_no_observed_query_is_anchored() -> None:
    query_set = _query_set()
    broken = replace(
        query_set,
        queries=tuple(
            replace(query, expected_evidence_refs=("ex:InventedEdge",))
            if query.query_id == "atq-013"
            else query
            for query in query_set.queries
        ),
    )
    reference = _reference(broken)

    score = score_reference_run(
        configuration=build_s1_run_configuration(broken),
        query_set=broken,
        reference=reference,
        observations=_observations(["atq-013"]),
    )

    for name in REFERENCE_DEPENDENT_METRICS:
        summary = score.summary[name]
        assert summary.value is None, name
        assert summary.applicable_count == 0, name
        assert summary.reason is not None and "no observed query has an anchored" in summary.reason
    # The run-measured metric the run genuinely produced is still reported.
    assert score.summary[MetricName.TERMINAL_STATUS_MATCH].value == 1.0
