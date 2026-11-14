"""Behavior contract for the S1 naive-RAG baseline."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, QuerySet, load_query_set
from mfg_agentgraph.evaluation_harness import (
    ArtifactKind,
    EvaluationStrategy,
)
from mfg_agentgraph.evaluation_metrics import MetricApplicability, MetricName, compute_query_metrics
from mfg_agentgraph.s1_naive_rag import (
    S1Chunk,
    S1Index,
    S1QueryEvaluation,
    build_s1_index,
    build_s1_index_from_document,
    build_s1_run_configuration,
    retrieve_naive,
    run_s1_query,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation" / "anomaly_triage" / "query-set-v1.json"
)
SOP_PATH = Path(__file__).resolve().parent / "fixtures" / "sop" / "pump12-sop.txt"
SOP_TEXT = SOP_PATH.read_text(encoding="utf-8")


def _query_set() -> QuerySet:
    return load_query_set(DATASET_PATH)


def _query(query_id: str = "atq-013") -> QueryRecord:
    query_set = _query_set()
    return next(query for query in query_set.queries if query.query_id == query_id)


def _sop_index() -> S1Index:
    return build_s1_index_from_document(SOP_TEXT, document="SOP-PUMP-OPS-2026", first_chunk_index=7)


def _run(index: S1Index | None = None, **overrides: object) -> S1QueryEvaluation:
    arguments: dict[str, object] = {
        "index": _sop_index() if index is None else index,
        "harness_version": "v1",
        "repository_revision": "2a75d4c",
    }
    arguments.update(overrides)
    query_set = _query_set()
    return run_s1_query(
        _query(),
        build_s1_run_configuration(query_set),
        **arguments,  # type: ignore[arg-type]
    )


def test_s1_record_matches_the_shared_schema_and_cites_the_retrieved_chunk() -> None:
    evaluation = _run(latency_ms=4.0, peak_memory_mb=128.0)

    payload = json.loads(evaluation.result.to_json())

    assert payload["configuration"]["strategy"] == "s1"
    assert payload["configuration"]["dataset_id"] == "mimii-pump12"
    assert payload["manifest"]["dataset_sha256"] == _query_set().document_sha256
    assert payload["raw_output"]["terminal_status"] == "passed"
    artifacts = {artifact["kind"]: artifact for artifact in payload["artifacts"]}
    assert artifacts[ArtifactKind.ANSWER.value]["applicability"] == "present"
    assert artifacts[ArtifactKind.RETRIEVED_CONTEXT.value]["value"]["evidence_ids"] == [
        "ex:SOP_Chunk_7"
    ]
    assert artifacts[ArtifactKind.VALIDATION_REPORT.value]["applicability"] == "not_applicable"
    assert "SHACL" in artifacts[ArtifactKind.VALIDATION_REPORT.value]["reason"]
    assert artifacts[ArtifactKind.PROVENANCE_TRACE.value]["applicability"] == "not_applicable"

    observation = evaluation.observation
    assert observation.terminal_status is TerminalStatus.PASSED
    assert observation.cited_evidence_refs == ("ex:SOP_Chunk_7",)
    assert observation.initial_shacl_passed is None
    assert observation.final_shacl_passed is None
    assert observation.provenance_components is None
    assert observation.latency_ms == 4.0
    assert observation.predicted_answer
    assert "inspect" in observation.predicted_answer.lower()


def test_s1_scores_against_the_dataset_gold_labels() -> None:
    evaluation = _run()
    metrics = compute_query_metrics(evaluation.observation, _query())

    assert metrics[MetricName.HITS_AT_ANY].value == 1.0
    # atq-013 expects the KG edge and the SOP chunk; S1 can only ever cite the chunk.
    assert metrics[MetricName.EVIDENCE_SUPPORT_COVERAGE].value == 0.5
    assert metrics[MetricName.EVIDENCE_CITATION_PRECISION].value == 1.0
    assert metrics[MetricName.TERMINAL_STATUS_MATCH].value == 1.0
    assert metrics[MetricName.INITIAL_SHACL_PASS].applicability is (
        MetricApplicability.NOT_APPLICABLE
    )
    assert metrics[MetricName.PROVENANCE_COMPLETENESS].applicability is (
        MetricApplicability.NOT_APPLICABLE
    )


def test_retrieval_is_deterministic_ranked_and_bounded() -> None:
    index = build_s1_index(
        (
            S1Chunk("ex:SOP_Chunk_1", "SOP-A", "Inspect the inlet for cavitation."),
            S1Chunk("ex:SOP_Chunk_2", "SOP-B", "Replace the bearing grease."),
            S1Chunk("ex:SOP_Chunk_3", "SOP-C", "Inspect the inlet filter daily."),
        )
    )

    first = retrieve_naive(index, "inspect the inlet for cavitation", top_k=3)
    second = retrieve_naive(index, "inspect the inlet for cavitation", top_k=3)

    assert [ranked.chunk.evidence_id for ranked in first] == [
        "ex:SOP_Chunk_1",
        "ex:SOP_Chunk_3",
    ]
    assert first == second
    assert retrieve_naive(index, "inspect the inlet for cavitation", top_k=1)[
        0
    ].chunk.evidence_id == ("ex:SOP_Chunk_1")
    assert all(0.0 < ranked.score <= 1.0 for ranked in first)


def test_zero_overlap_abstains_with_a_typed_error() -> None:
    index = build_s1_index((S1Chunk("ex:SOP_Chunk_9", "SOP-X", "Lubricate gearboxes annually."),))

    evaluation = _run(index)

    assert evaluation.observation.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert evaluation.observation.predicted_answer == ""
    assert evaluation.observation.cited_evidence_refs == ()
    assert [error.code for error in evaluation.result.errors] == ["insufficient_evidence"]
    payload = json.loads(evaluation.result.to_json())
    artifacts = {artifact["kind"]: artifact for artifact in payload["artifacts"]}
    assert artifacts["retrieved_context"]["value"] == {"evidence_ids": []}
    assert artifacts["answer"]["applicability"] == "present"


def test_minimum_score_can_force_abstention() -> None:
    strict = run_s1_query(
        _query(),
        build_s1_run_configuration(_query_set(), minimum_score=0.99),
        index=_sop_index(),
        harness_version="v1",
        repository_revision="2a75d4c",
    )

    assert strict.observation.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE


def test_index_and_configuration_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_s1_index(
            (
                S1Chunk("ex:SOP_Chunk_7", "SOP", "Inspect the inlet."),
                S1Chunk("ex:SOP_Chunk_7", "SOP", "Inspect the filter."),
            )
        )
    with pytest.raises(ValueError, match="text"):
        S1Chunk("ex:SOP_Chunk_7", "SOP", " ")
    with pytest.raises(TypeError, match="chunks"):
        build_s1_index("not-a-sequence")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="first_chunk_index"):
        build_s1_index_from_document("text", document="SOP", first_chunk_index=0)
    with pytest.raises(ValueError, match="top_k"):
        retrieve_naive(_sop_index(), "inspect inlet", top_k=0)
    with pytest.raises(ValueError, match="minimum_score"):
        retrieve_naive(_sop_index(), "inspect inlet", minimum_score=1.5)
    with pytest.raises(TypeError, match="index"):
        retrieve_naive("index", "inspect inlet")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="random_seed"):
        build_s1_run_configuration(_query_set(), random_seed=-1)
    with pytest.raises(TypeError, match="query_set"):
        build_s1_run_configuration("query-set")  # type: ignore[arg-type]

    configuration = build_s1_run_configuration(_query_set())
    assert configuration.parameters.get("dataset_sha256") == _query_set().document_sha256
    with pytest.raises(ValueError, match="S1"):
        run_s1_query(
            _query(),
            replace(configuration, strategy=EvaluationStrategy.S4),
            index=_sop_index(),
            harness_version="v1",
            repository_revision="2a75d4c",
        )
    with pytest.raises(TypeError, match="query"):
        run_s1_query(
            "atq-013",  # type: ignore[arg-type]
            configuration,
            index=_sop_index(),
            harness_version="v1",
            repository_revision="2a75d4c",
        )


def test_s1_evaluation_is_immutable() -> None:
    evaluation = _run()

    assert not hasattr(evaluation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        evaluation.observation = evaluation.observation  # type: ignore[misc]


def test_s1_chunk_and_index_validation_fails_closed() -> None:
    with pytest.raises(TypeError, match="evidence_id"):
        S1Chunk(7, "SOP", "Inspect the inlet.")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="document"):
        S1Chunk("ex:SOP_Chunk_7", " ", "Inspect the inlet.")
    with pytest.raises(ValueError, match="text"):
        S1Chunk("ex:SOP_Chunk_7", "SOP", "x" * 8_193)
    with pytest.raises(TypeError, match="chunks"):
        S1Index(("not-a-chunk",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="first_chunk_index"):
        build_s1_index_from_document(
            "text",
            document="SOP",
            first_chunk_index=True,
        )
    with pytest.raises(TypeError, match="top_k"):
        retrieve_naive(_sop_index(), "inspect inlet", top_k=True)
    with pytest.raises(TypeError, match="minimum_score"):
        retrieve_naive(_sop_index(), "inspect inlet", minimum_score="0.5")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="minimum_score"):
        build_s1_run_configuration(_query_set(), minimum_score=float("nan"))
    with pytest.raises(TypeError, match="top_k"):
        build_s1_run_configuration(_query_set(), top_k=True)


def test_run_s1_query_rejects_tampered_configuration_parameters() -> None:
    configuration = build_s1_run_configuration(_query_set())
    with pytest.raises(ValueError, match="top_k"):
        run_s1_query(
            _query(),
            replace(configuration, parameters={}),
            index=_sop_index(),
            harness_version="v1",
            repository_revision="2a75d4c",
        )
    with pytest.raises(TypeError, match="top_k"):
        run_s1_query(
            _query(),
            replace(
                configuration,
                parameters={
                    "dataset_sha256": _query_set().document_sha256,
                    "minimum_score": 0.0,
                    "top_k": "3",
                },
            ),
            index=_sop_index(),
            harness_version="v1",
            repository_revision="2a75d4c",
        )
    with pytest.raises(TypeError, match="minimum_score"):
        run_s1_query(
            _query(),
            replace(
                configuration,
                parameters={
                    "dataset_sha256": _query_set().document_sha256,
                    "minimum_score": "0",
                    "top_k": 3,
                },
            ),
            index=_sop_index(),
            harness_version="v1",
            repository_revision="2a75d4c",
        )
    with pytest.raises(TypeError, match="dataset_sha256"):
        run_s1_query(
            _query(),
            replace(
                configuration,
                parameters={"dataset_sha256": 1, "minimum_score": 0.0, "top_k": 3},
            ),
            index=_sop_index(),
            harness_version="v1",
            repository_revision="2a75d4c",
        )
    with pytest.raises(TypeError, match="index"):
        run_s1_query(
            _query(),
            configuration,
            index="index",  # type: ignore[arg-type]
            harness_version="v1",
            repository_revision="2a75d4c",
        )
