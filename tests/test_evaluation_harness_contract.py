import json
from dataclasses import FrozenInstanceError

import pytest

from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationArtifact,
    EvaluationError,
    EvaluationResult,
    EvaluationRunConfiguration,
    EvaluationRunManifest,
    EvaluationStrategy,
)

DATASET_SHA256 = "ab" * 32


@pytest.mark.parametrize("strategy", list(EvaluationStrategy))
def test_every_strategy_emits_one_comparable_json_safe_result_schema(
    strategy: EvaluationStrategy,
) -> None:
    configuration = EvaluationRunConfiguration(
        strategy=strategy,
        dataset_id="mimii-pump-v1",
        query_set_id="anomaly-triage-v1",
        model_configuration_id="local-model-v1",
        retrieval_configuration_id="retrieval-profile-v1",
        random_seed=42,
        parameters={"temperature": 0},
    )
    always_present = {ArtifactKind.ANSWER, ArtifactKind.RETRIEVED_CONTEXT}
    artifacts = tuple(
        EvaluationArtifact(
            kind=kind,
            applicability=(
                ArtifactApplicability.PRESENT
                if strategy is EvaluationStrategy.S4 or kind in always_present
                else ArtifactApplicability.NOT_APPLICABLE
            ),
            value=(
                {"id": kind.value}
                if strategy is EvaluationStrategy.S4 or kind in always_present
                else None
            ),
            reason=(
                None
                if strategy is EvaluationStrategy.S4 or kind in always_present
                else "strategy does not produce this artifact"
            ),
        )
        for kind in ArtifactKind
    )
    result = EvaluationResult(
        configuration=configuration,
        manifest=EvaluationRunManifest(
            run_id=f"run-{strategy.value}",
            repository_revision="e830f76",
            harness_version="v1",
            dataset_sha256=DATASET_SHA256,
        ),
        query_id="pump-12-cavitation-001",
        raw_output={"answer": "Inspect the pump inlet."},
        errors=(),
        artifacts=artifacts,
    )

    payload = json.loads(result.to_json())

    assert set(payload) == {
        "artifacts",
        "configuration",
        "errors",
        "manifest",
        "query_id",
        "raw_output",
        "schema_version",
    }
    assert payload["configuration"]["strategy"] == strategy.value
    assert payload["configuration"]["dataset_id"] == "mimii-pump-v1"
    assert payload["manifest"] == {
        "dataset_sha256": DATASET_SHA256,
        "harness_version": "v1",
        "repository_revision": "e830f76",
        "run_id": f"run-{strategy.value}",
    }
    assert payload["errors"] == []
    assert payload["raw_output"] == {"answer": "Inspect the pump inlet."}
    assert [artifact["kind"] for artifact in payload["artifacts"]] == [
        kind.value for kind in ArtifactKind
    ]
    assert all("applicability" in artifact for artifact in payload["artifacts"])
    assert json.loads(result.to_json()) == payload


def _artifacts_for(strategy: EvaluationStrategy) -> tuple[EvaluationArtifact, ...]:
    return tuple(
        EvaluationArtifact(
            kind=kind,
            applicability=(
                ArtifactApplicability.PRESENT
                if strategy is EvaluationStrategy.S4
                or kind in {ArtifactKind.ANSWER, ArtifactKind.RETRIEVED_CONTEXT}
                else ArtifactApplicability.NOT_APPLICABLE
            ),
            value=(
                {"id": kind.value}
                if strategy is EvaluationStrategy.S4
                or kind in {ArtifactKind.ANSWER, ArtifactKind.RETRIEVED_CONTEXT}
                else None
            ),
            reason=(
                None
                if strategy is EvaluationStrategy.S4
                or kind in {ArtifactKind.ANSWER, ArtifactKind.RETRIEVED_CONTEXT}
                else "strategy does not produce this artifact"
            ),
        )
        for kind in ArtifactKind
    )


def _configuration() -> EvaluationRunConfiguration:
    return EvaluationRunConfiguration(
        strategy=EvaluationStrategy.S1,
        dataset_id="mimii-pump-v1",
        query_set_id="anomaly-triage-v1",
        model_configuration_id="local-model-v1",
        retrieval_configuration_id="retrieval-profile-v1",
        random_seed=42,
        parameters={"nested": {"values": [1, True, None]}},
    )


def _manifest() -> EvaluationRunManifest:
    return EvaluationRunManifest(
        run_id="run-s1",
        repository_revision="e830f76",
        harness_version="v1",
        dataset_sha256=DATASET_SHA256,
    )


def test_configuration_snapshots_json_parameters_and_rejects_invalid_inputs() -> None:
    parameters = {"nested": {"values": [1]}}
    configuration = EvaluationRunConfiguration(
        strategy=EvaluationStrategy.S1,
        dataset_id=" dataset ",
        query_set_id=" query-set ",
        model_configuration_id=" model ",
        retrieval_configuration_id=" retrieval ",
        random_seed=0,
        parameters=parameters,
    )
    parameters["nested"]["values"].append(2)

    assert configuration.to_dict()["parameters"] == {"nested": {"values": [1]}}
    assert configuration.dataset_id == "dataset"
    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        configuration.dataset_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError, match="strategy"):
        EvaluationRunConfiguration(
            strategy="s1",  # type: ignore[arg-type]
            dataset_id="dataset",
            query_set_id="query-set",
            model_configuration_id="model",
            retrieval_configuration_id="retrieval",
            random_seed=0,
            parameters={},
        )
    with pytest.raises(ValueError, match="random_seed"):
        EvaluationRunConfiguration(
            strategy=EvaluationStrategy.S1,
            dataset_id="dataset",
            query_set_id="query-set",
            model_configuration_id="model",
            retrieval_configuration_id="retrieval",
            random_seed=-1,
            parameters={},
        )
    with pytest.raises(ValueError, match="non-finite"):
        EvaluationRunConfiguration(
            strategy=EvaluationStrategy.S1,
            dataset_id="dataset",
            query_set_id="query-set",
            model_configuration_id="model",
            retrieval_configuration_id="retrieval",
            random_seed=0,
            parameters={"temperature": float("nan")},
        )


def test_artifacts_make_absence_explicit_and_result_requires_canonical_set() -> None:
    with pytest.raises(ValueError, match="present artifact"):
        EvaluationArtifact(
            kind=ArtifactKind.ANSWER,
            applicability=ArtifactApplicability.PRESENT,
            value={"answer": "inspect"},
            reason="unexpected",
        )
    with pytest.raises(ValueError, match="not-applicable artifact"):
        EvaluationArtifact(
            kind=ArtifactKind.PROVENANCE_TRACE,
            applicability=ArtifactApplicability.NOT_APPLICABLE,
            value={"id": "trace"},
            reason="not used",
        )
    with pytest.raises(ValueError, match="canonical order"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_manifest(),
            query_id="query-001",
            raw_output={},
            errors=(),
            artifacts=tuple(reversed(_artifacts_for(EvaluationStrategy.S1))),
        )


def test_result_captures_errors_and_rejects_noncanonical_containers() -> None:
    error = EvaluationError(code="service_failure", message="connection refused", field="endpoint")
    result = EvaluationResult(
        configuration=_configuration(),
        manifest=_manifest(),
        query_id="query-001",
        raw_output=["unparsed", "response"],
        errors=[error],
        artifacts=_artifacts_for(EvaluationStrategy.S1),
    )

    assert result.to_dict()["errors"] == [
        {"code": "service_failure", "field": "endpoint", "message": "connection refused"}
    ]
    assert result.to_dict()["raw_output"] == ["unparsed", "response"]
    assert result.errors == (error,)
    with pytest.raises(TypeError, match="errors"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_manifest(),
            query_id="query-001",
            raw_output={},
            errors=error,  # type: ignore[arg-type]
            artifacts=_artifacts_for(EvaluationStrategy.S1),
        )
    with pytest.raises(TypeError, match="artifacts"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_manifest(),
            query_id="query-001",
            raw_output={},
            errors=(),
            artifacts={"not-an-artifact": "value"},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: EvaluationRunConfiguration(
                strategy=EvaluationStrategy.S1,
                dataset_id="dataset",
                query_set_id="query-set",
                model_configuration_id="model",
                retrieval_configuration_id="retrieval",
                random_seed=True,
                parameters={},
            ),
            "random_seed",
        ),
        (
            lambda: EvaluationRunConfiguration(
                strategy=EvaluationStrategy.S1,
                dataset_id="dataset",
                query_set_id="query-set",
                model_configuration_id="model",
                retrieval_configuration_id="retrieval",
                random_seed=0,
                parameters=[],  # type: ignore[arg-type]
            ),
            "parameters",
        ),
        (
            lambda: EvaluationRunConfiguration(
                strategy=EvaluationStrategy.S1,
                dataset_id="dataset",
                query_set_id="query-set",
                model_configuration_id="model",
                retrieval_configuration_id="retrieval",
                random_seed=0,
                parameters={"key": 1, " key ": 2},
            ),
            "duplicate",
        ),
        (
            lambda: EvaluationRunManifest(
                run_id=" ",
                repository_revision="revision",
                harness_version="v1",
                dataset_sha256=DATASET_SHA256,
            ),
            "run_id",
        ),
        (
            lambda: EvaluationError(code="error", message=" ", field=None),
            "message",
        ),
        (
            lambda: EvaluationArtifact(
                kind="answer",  # type: ignore[arg-type]
                applicability=ArtifactApplicability.PRESENT,
                value={},
                reason=None,
            ),
            "kind",
        ),
        (
            lambda: EvaluationArtifact(
                kind=ArtifactKind.ANSWER,
                applicability="present",  # type: ignore[arg-type]
                value={},
                reason=None,
            ),
            "applicability",
        ),
    ],
)
def test_contract_rejects_invalid_scalar_and_enum_inputs(factory: object, message: str) -> None:
    assert callable(factory)
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


@pytest.mark.parametrize(
    "digest",
    ["", "ab" * 31, "AB" * 32, "zz" * 32, "ab" * 32 + "ab"],
)
def test_manifest_requires_a_lowercase_sha256_dataset_digest(digest: str) -> None:
    with pytest.raises((TypeError, ValueError), match="dataset_sha256"):
        EvaluationRunManifest(
            run_id="run-s1",
            repository_revision="e830f76",
            harness_version="v1",
            dataset_sha256=digest,
        )


def test_manifest_serializes_the_dataset_digest() -> None:
    assert _manifest().to_dict()["dataset_sha256"] == DATASET_SHA256


def test_result_rejects_invalid_dependencies_raw_output_and_sequence_members() -> None:
    with pytest.raises(TypeError, match="configuration"):
        EvaluationResult(
            configuration=_manifest(),  # type: ignore[arg-type]
            manifest=_manifest(),
            query_id="query-001",
            raw_output={},
            errors=(),
            artifacts=_artifacts_for(EvaluationStrategy.S1),
        )
    with pytest.raises(TypeError, match="manifest"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_configuration(),  # type: ignore[arg-type]
            query_id="query-001",
            raw_output={},
            errors=(),
            artifacts=_artifacts_for(EvaluationStrategy.S1),
        )
    with pytest.raises(TypeError, match="raw_output"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_manifest(),
            query_id="query-001",
            raw_output={"unsupported"},
            errors=(),
            artifacts=_artifacts_for(EvaluationStrategy.S1),
        )
    with pytest.raises(TypeError, match="errors"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_manifest(),
            query_id="query-001",
            raw_output={},
            errors=["not-an-error"],  # type: ignore[list-item]
            artifacts=_artifacts_for(EvaluationStrategy.S1),
        )
    with pytest.raises(TypeError, match="artifacts"):
        EvaluationResult(
            configuration=_configuration(),
            manifest=_manifest(),
            query_id="query-001",
            raw_output={},
            errors=(),
            artifacts=["not-an-artifact"],  # type: ignore[list-item]
        )
