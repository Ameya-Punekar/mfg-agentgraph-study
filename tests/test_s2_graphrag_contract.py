"""Consumer-visible S2 GraphRAG-style index build, query, and cost contracts."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, load_query_set
from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationStrategy,
)
from mfg_agentgraph.evaluation_metrics import MetricApplicability, MetricName, compute_query_metrics
from mfg_agentgraph.s1_naive_rag import (
    S1Chunk,
    build_s1_index_from_document,
    split_sentences,
)
from mfg_agentgraph.s2_graphrag import (
    S2Claim,
    S2Community,
    S2Entity,
    S2Index,
    S2IndexBuildCost,
    S2QueryEvaluation,
    build_s2_index,
    build_s2_run_configuration,
    run_s2_query,
    summarize_index_build,
)
from mfg_agentgraph.stage_instrumentation import TerminalStatus

ROOT = Path(__file__).resolve().parents[1]
QUERY_SET = load_query_set(ROOT / "evaluation/anomaly_triage/query-set-v1.json")
SOP_TEXT = (ROOT / "tests/fixtures/sop/pump12-sop.txt").read_text(encoding="utf-8")


def _chunks() -> tuple[S1Chunk, ...]:
    index = build_s1_index_from_document(
        SOP_TEXT, document="SOP-PUMP-OPS-2026", first_chunk_index=7
    )
    return tuple(index.chunks)


def _query(query_id: str = "atq-013") -> QueryRecord:
    return next(query for query in QUERY_SET.queries if query.query_id == query_id)


def _index(**overrides: Any) -> S2Index:
    arguments: dict[str, Any] = {"build_duration_ms": 12.5}
    arguments.update(overrides)
    return build_s2_index(_chunks(), **arguments)


def _run(
    index: S2Index | None = None, query: QueryRecord | None = None, **overrides: Any
) -> S2QueryEvaluation:
    selected = _index() if index is None else index
    arguments: dict[str, Any] = {
        "index": selected,
        "harness_version": "v1",
        "repository_revision": "f0f4d59",
        "latency_ms": 3.0,
        "peak_memory_mb": 64.0,
    }
    arguments.update(overrides)
    return run_s2_query(
        _query() if query is None else query,
        build_s2_run_configuration(QUERY_SET, selected),
        **arguments,
    )


def _synthetic_chunks() -> tuple[S1Chunk, ...]:
    return (
        S1Chunk("ex:SOP_Chunk_1", "SOP-A", "Inspect the inlet valve for cavitation damage."),
        S1Chunk("ex:SOP_Chunk_2", "SOP-B", "Replace the bearing grease during routine servicing."),
        S1Chunk("ex:SOP_Chunk_3", "SOP-C", "Rotate the coupling guard after bearing replacement."),
    )


def _synthetic_index(**overrides: Any) -> S2Index:
    arguments: dict[str, Any] = {"build_duration_ms": 4.0}
    arguments.update(overrides)
    return build_s2_index(_synthetic_chunks(), **arguments)


def test_index_is_rebuilt_from_documented_inputs_with_a_stable_digest() -> None:
    first = _index()
    second = _index()

    assert first.contract_version == "mfg-agentgraph-s2-index-v1"
    assert first.entities == second.entities
    assert first.claims == second.claims
    assert first.edges == second.edges
    assert first.communities == second.communities
    assert first.index_sha256 == second.index_sha256
    assert len(first.index_sha256) == 64
    assert first.index_bytes == second.index_bytes
    assert first.cost.entity_count == len(first.entities)
    assert first.cost.claim_count == len(first.claims)
    assert first.cost.edge_count == len(first.edges)
    assert first.cost.community_count == len(first.communities)
    assert first.cost.build_duration_ms == 12.5

    changed = build_s2_index(
        (S1Chunk("ex:SOP_Chunk_7", "SOP", "Lubricate the gearbox annually."),),
        build_duration_ms=1.0,
    )
    assert changed.index_sha256 != first.index_sha256


def test_communities_partition_terms_and_summaries_cite_only_their_members() -> None:
    index = _synthetic_index()
    members = [term for community in index.communities for term in community.entity_terms]

    assert len(members) == len(set(members))
    assert set(members) == {entity.term for entity in index.entities}
    assert len(index.communities) == 2

    chunk_text = {chunk.evidence_id: chunk.text for chunk in _synthetic_chunks()}
    for community in index.communities:
        assert community.evidence_ids
        assert set(community.evidence_ids) <= set(chunk_text)
        sentences = {
            sentence
            for evidence_id in community.evidence_ids
            for sentence in split_sentences(chunk_text[evidence_id])
        }
        assert set(community.summary_sentences) <= sentences


def test_cooccurrence_edges_are_canonical_and_weighted() -> None:
    index = _synthetic_index()

    assert index.edges
    for left, right, weight in index.edges:
        assert left < right
        assert weight >= 1
        assert left in {entity.term for entity in index.entities}
        assert right in {entity.term for entity in index.entities}
    assert len({(left, right) for left, right, _ in index.edges}) == len(index.edges)


def test_broad_query_selects_several_communities_and_cites_only_their_chunks() -> None:
    index = _synthetic_index()
    evaluation = _run(
        index=index,
        query=replace(_query(), text="inspect cavitation and replace grease"),
    )

    payload = json.loads(evaluation.result.to_json())
    artifacts = {artifact["kind"]: artifact for artifact in payload["artifacts"]}
    evidence_ids = artifacts[ArtifactKind.RETRIEVED_CONTEXT]["value"]["evidence_ids"]

    assert evaluation.observation.terminal_status is TerminalStatus.PASSED
    assert artifact_kinds(payload) == [kind.value for kind in ArtifactKind]
    assert "ex:SOP_Chunk_1" in evidence_ids
    assert "ex:SOP_Chunk_2" in evidence_ids
    assert len(payload["raw_output"]["selected_community_ids"]) >= 2
    assert payload["raw_output"]["index_build_duration_ms"] == 4.0
    assert payload["raw_output"]["index_sha256"] == index.index_sha256
    assert payload["raw_output"]["constraint_validated"] is False
    assert payload["raw_output"]["provenance_id"] is None


def artifact_kinds(payload: dict[str, Any]) -> list[str]:
    return [artifact["kind"] for artifact in payload["artifacts"]]


def test_answer_comes_from_the_retrieved_communities() -> None:
    evaluation = _run()
    observation = evaluation.observation

    assert observation.terminal_status is TerminalStatus.PASSED
    assert observation.predicted_answer
    assert "inspect" in observation.predicted_answer.lower()
    assert observation.cited_evidence_refs == ("ex:SOP_Chunk_7",)
    assert observation.initial_shacl_passed is None
    assert observation.final_shacl_passed is None
    assert observation.repair_iterations is None
    assert observation.provenance_components is None


def test_index_build_cost_is_recorded_separately_from_query_latency() -> None:
    index = _index(build_duration_ms=987.5)

    evaluation = _run(index=index, latency_ms=2.25)
    raw_output = json.loads(evaluation.result.to_json())["raw_output"]

    assert raw_output["index_build_duration_ms"] == 987.5
    assert raw_output["index_bytes"] == index.index_bytes
    assert raw_output["index_entity_count"] == index.cost.entity_count
    assert raw_output["index_community_count"] == index.cost.community_count
    assert evaluation.observation.latency_ms == 2.25
    assert raw_output["query_latency_ms"] == 2.25


def test_record_marks_absent_capabilities_and_undefined_metrics() -> None:
    evaluation = _run()
    artifacts = {artifact.kind: artifact for artifact in evaluation.result.artifacts}

    assert artifacts[ArtifactKind.VALIDATION_REPORT].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    assert artifacts[ArtifactKind.PROVENANCE_TRACE].applicability is (
        ArtifactApplicability.NOT_APPLICABLE
    )
    metrics = compute_query_metrics(evaluation.observation, _query())
    assert metrics[MetricName.EVIDENCE_SUPPORT_COVERAGE].value == 0.5
    assert metrics[MetricName.EVIDENCE_CITATION_PRECISION].value == 1.0
    for name in (
        MetricName.INITIAL_SHACL_PASS,
        MetricName.FINAL_SHACL_PASS,
        MetricName.REPAIR_ITERATIONS,
        MetricName.PROVENANCE_COMPLETENESS,
    ):
        assert metrics[name].applicability is MetricApplicability.NOT_APPLICABLE


def test_no_community_overlap_abstains_with_a_typed_error() -> None:
    evaluation = _run(
        index=_synthetic_index(),
        query=replace(_query(), text="gearbox lubrication schedule"),
    )

    assert evaluation.observation.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert evaluation.observation.predicted_answer == ""
    assert evaluation.observation.cited_evidence_refs == ()
    assert [error.code for error in evaluation.result.errors] == ["insufficient_evidence"]
    artifacts = {artifact.kind: artifact for artifact in evaluation.result.artifacts}
    assert artifacts[ArtifactKind.RETRIEVED_CONTEXT].applicability is (
        ArtifactApplicability.PRESENT
    )


def test_gold_labels_do_not_drive_the_index_or_the_answer() -> None:
    index = _index()
    original = _run(index=index)
    relabelled = _run(
        index=index,
        query=replace(
            _query(),
            expected_action="Replace an unrelated gearbox",
            expected_evidence_refs=("ex:Other",),
        ),
    )

    assert relabelled.result.to_json() == original.result.to_json()
    assert relabelled.observation == original.observation


def test_a_configuration_bound_to_another_index_is_rejected() -> None:
    index = _index()
    other = _synthetic_index()

    with pytest.raises(ValueError, match="index_sha256"):
        run_s2_query(
            _query(),
            build_s2_run_configuration(QUERY_SET, index),
            index=other,
            harness_version="v1",
            repository_revision="f0f4d59",
        )


def test_configuration_and_index_validation_fail_closed() -> None:
    index = _index()

    with pytest.raises(ValueError, match="S2"):
        run_s2_query(
            _query(),
            replace(
                build_s2_run_configuration(QUERY_SET, index),
                strategy=EvaluationStrategy.S3,
            ),
            index=index,
            harness_version="v1",
            repository_revision="f0f4d59",
        )
    with pytest.raises(TypeError, match="query"):
        run_s2_query(
            "atq-013",  # type: ignore[arg-type]
            build_s2_run_configuration(QUERY_SET, index),
            index=index,
            harness_version="v1",
            repository_revision="f0f4d59",
        )
    with pytest.raises(TypeError, match="index"):
        run_s2_query(
            _query(),
            build_s2_run_configuration(QUERY_SET, index),
            index="index",  # type: ignore[arg-type]
            harness_version="v1",
            repository_revision="f0f4d59",
        )
    with pytest.raises(TypeError, match="query_set"):
        build_s2_run_configuration("query-set", index)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="index"):
        build_s2_run_configuration(QUERY_SET, "index")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="communities"):
        build_s2_run_configuration(QUERY_SET, index, top_k_communities=0)
    with pytest.raises(ValueError, match="sentences"):
        build_s2_run_configuration(QUERY_SET, index, max_sentences=0)

    with pytest.raises(TypeError, match="chunks"):
        build_s2_index("chunks")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="chunks"):
        build_s2_index(())
    with pytest.raises(TypeError, match="S1Chunk"):
        build_s2_index(("not-a-chunk",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="build_duration_ms"):
        build_s2_index(_chunks(), build_duration_ms=-1.0)
    with pytest.raises(TypeError, match="build_duration_ms"):
        build_s2_index(_chunks(), build_duration_ms="1.0")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="build_duration_ms"):
        build_s2_index(_chunks(), build_duration_ms=float("nan"))


def test_index_and_evaluation_are_immutable() -> None:
    index = _index()
    community = index.communities[0]
    evaluation = _run(index=index)

    assert not hasattr(index, "__dict__")
    assert isinstance(community, S2Community)
    with pytest.raises(FrozenInstanceError):
        index.index_sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        evaluation.observation = evaluation.observation  # type: ignore[misc]


def test_index_record_validation_fails_closed() -> None:
    index = _index()

    with pytest.raises(TypeError):
        S2Entity(7, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        S2Entity(" ", 1)
    with pytest.raises(ValueError):
        S2Entity("term", 0)
    with pytest.raises(TypeError):
        S2Claim(1, 0, "text", ())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        S2Claim("ex:A", True, "text", ())
    with pytest.raises(ValueError):
        S2Claim("ex:A", -1, "text", ())
    with pytest.raises(ValueError):
        S2Claim("ex:A", 0, " ", ())
    with pytest.raises(TypeError):
        S2Claim("ex:A", 0, "text", "terms")
    with pytest.raises(ValueError):
        S2Community("c0", (), ("text",), ("ex:A",))
    with pytest.raises(ValueError):
        S2Community("c0", ("term",), (), ("ex:A",))
    with pytest.raises(ValueError):
        S2Community("c0", ("term",), ("text",), ())
    with pytest.raises(TypeError):
        S2Community(7, ("term",), ("text",), ("ex:A",))  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        replace(index, index_sha256="x")
    with pytest.raises(ValueError):
        replace(index, index_bytes=index.index_bytes + 1)
    with pytest.raises(TypeError, match="edges"):
        replace(index, edges=(("a", "b"),))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="chunks"):
        replace(index, chunks="chunks")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="entities"):
        replace(index, entities=(1,))  # type: ignore[arg-type]


def test_build_cost_validation_fails_closed() -> None:
    with pytest.raises(TypeError):
        S2IndexBuildCost("1.0", 1, 1, 1, 1, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        S2IndexBuildCost(float("nan"), 1, 1, 1, 1, 1)
    with pytest.raises(ValueError):
        S2IndexBuildCost(-1.0, 1, 1, 1, 1, 1)
    with pytest.raises(TypeError):
        S2IndexBuildCost(1.0, "1", 1, 1, 1, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        S2IndexBuildCost(1.0, -1, 1, 1, 1, 1)


def test_summary_vocabulary_match_without_a_supporting_claim_abstains() -> None:
    chunks = (
        S1Chunk("ex:SOP_Chunk_9", "SOP", "Use oil on the shaft seal. Inspect the shaft weekly."),
    )
    index = build_s2_index(chunks, build_duration_ms=2.0)
    evaluation = run_s2_query(
        replace(_query(), text="use oil"),
        build_s2_run_configuration(QUERY_SET, index),
        index=index,
        harness_version="v1",
        repository_revision="f0f4d59",
    )

    assert json.loads(evaluation.result.to_json())["raw_output"]["selected_community_ids"] == [
        "community-000"
    ]
    assert evaluation.observation.terminal_status is TerminalStatus.INSUFFICIENT_EVIDENCE
    assert evaluation.observation.predicted_answer == ""


def test_missing_configuration_parameters_are_rejected() -> None:
    index = _index()
    configuration = build_s2_run_configuration(QUERY_SET, index)

    with pytest.raises(ValueError, match="index_sha256"):
        run_s2_query(
            _query(),
            replace(configuration, parameters={"dataset_sha256": QUERY_SET.document_sha256}),
            index=index,
            harness_version="v1",
            repository_revision="f0f4d59",
        )
    with pytest.raises(ValueError, match="top_k_communities"):
        run_s2_query(
            _query(),
            replace(
                configuration,
                parameters={
                    "dataset_sha256": QUERY_SET.document_sha256,
                    "index_sha256": index.index_sha256,
                },
            ),
            index=index,
            harness_version="v1",
            repository_revision="f0f4d59",
        )


def test_build_summary_exposes_cost_separately() -> None:
    index = _index(build_duration_ms=42.5)

    summary = summarize_index_build(index)

    assert summary["index_build_duration_ms"] == 42.5
    assert summary["index_bytes"] == index.index_bytes
    assert summary["index_entity_count"] == index.cost.entity_count
    with pytest.raises(TypeError, match="index"):
        summarize_index_build("index")  # type: ignore[arg-type]


def test_measured_build_duration_and_remaining_guards() -> None:
    measured = build_s2_index(_chunks())
    assert measured.cost.build_duration_ms >= 0.0

    index = _index()
    with pytest.raises(ValueError):
        S2Entity("x" * 257, 1)
    with pytest.raises(TypeError):
        S2Entity("term", "1")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="index_bytes"):
        replace(index, index_bytes="1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="index_bytes"):
        replace(index, index_bytes=-1)
    with pytest.raises(TypeError, match="cost"):
        replace(index, cost="cost")  # type: ignore[arg-type]

    evaluation = _run(index=index)
    with pytest.raises(TypeError, match="result"):
        S2QueryEvaluation(result="record", observation=evaluation.observation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="observation"):
        S2QueryEvaluation(result=evaluation.result, observation="observation")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="configuration"):
        run_s2_query(
            _query(),
            "configuration",  # type: ignore[arg-type]
            index=index,
            harness_version="v1",
            repository_revision="f0f4d59",
        )


def test_weaker_claim_inside_one_community_is_not_selected() -> None:
    chunks = (
        S1Chunk(
            "ex:SOP_Chunk_1",
            "SOP",
            "Inspect the inlet valve for cavitation damage. Inspect the inlet filter weekly.",
        ),
    )
    index = build_s2_index(chunks, build_duration_ms=1.0)
    evaluation = run_s2_query(
        replace(_query(), text="inspect inlet valve cavitation damage"),
        build_s2_run_configuration(QUERY_SET, index),
        index=index,
        harness_version="v1",
        repository_revision="f0f4d59",
    )

    raw_output = json.loads(evaluation.result.to_json())["raw_output"]
    assert raw_output["answer"] == "Inspect the inlet valve for cavitation damage."
    assert raw_output["evidence_ids"] == ["ex:SOP_Chunk_1"]


def test_two_communities_in_one_chunk_cite_it_once() -> None:
    chunks = (
        S1Chunk(
            "ex:SOP_Chunk_1",
            "SOP",
            "Inspect the inlet valve for cavitation damage. "
            "Replace the bearing grease during servicing.",
        ),
    )
    index = build_s2_index(chunks, build_duration_ms=1.0)
    evaluation = run_s2_query(
        replace(_query(), text="inspect cavitation replace grease"),
        build_s2_run_configuration(QUERY_SET, index),
        index=index,
        harness_version="v1",
        repository_revision="f0f4d59",
    )

    observation = evaluation.observation
    assert len(index.communities) == 2
    assert observation.terminal_status is TerminalStatus.PASSED
    assert observation.cited_evidence_refs == ("ex:SOP_Chunk_1",)
    assert "Inspect" in observation.predicted_answer
    assert "Replace" in observation.predicted_answer
