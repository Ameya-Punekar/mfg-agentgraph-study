"""S4 evaluation strategy: the production orchestrator behind the shared harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rdflib import Graph, Node, URIRef

from mfg_agentgraph.anomaly_triage_dataset import QueryRecord, QuerySet
from mfg_agentgraph.entity_resolution import AssetCatalog
from mfg_agentgraph.evaluation_harness import (
    ArtifactApplicability,
    ArtifactKind,
    EvaluationArtifact,
    EvaluationResult,
    EvaluationRunConfiguration,
    EvaluationRunManifest,
    EvaluationStrategy,
    dataset_sha256_from_configuration,
    errors_from_events,
)
from mfg_agentgraph.evaluation_metrics import MetricObservation
from mfg_agentgraph.pump12_orchestrator import (
    Pump12OrchestrationResult,
    Pump12StableIds,
    run_pump12_orchestrator,
)
from mfg_agentgraph.stage_instrumentation import StageEvent, StageName, TerminalStatus

PROV_NAMESPACE = "http://www.w3.org/ns/prov#"
_PROV_COMPONENT_BY_TERM: Mapping[str, str] = {
    "Activity": "activity",
    "Agent": "agent",
    "Entity": "entity",
    "SoftwareAgent": "agent",
    "used": "used",
    "wasAssociatedWith": "wasAssociatedWith",
    "wasGeneratedBy": "wasGeneratedBy",
}
_FIXTURE_ACTION_ID = "ex:CandidateAction_Pump12_Repaired_001"
_MODEL_CONFIGURATION_ID = "fixture-model-pump12-v1"
_RETRIEVAL_CONFIGURATION_ID = "fixture-retrieval-pump12-v1"


def build_stable_ids(query_id: str) -> Pump12StableIds:
    """Derive deterministic, per-query stable identities for one S4 run."""
    if type(query_id) is not str:
        raise TypeError("query_id must be a string")
    normalized = query_id.strip()
    if not normalized:
        raise ValueError("query_id must be nonblank")
    if not normalized.startswith("atq-") or not normalized[4:].isdigit():
        raise ValueError("query_id must match the atq-NNN pattern")
    suffix = normalized[4:]
    return Pump12StableIds(
        action_id=_FIXTURE_ACTION_ID,
        validation_report_id=f"ex:ValidationReport_S4_{suffix}",
        evidence_package_id=f"ex:EvidencePackage_S4_{suffix}",
        provenance_id=f"ex:ProvenanceTrace_S4_{suffix}",
        agent_id="ex:Agent_S4",
        prompt_id=f"ex:Prompt_S4_{suffix}",
        model_id="ex:FixtureModel_Pump12_001",
        asset_id="ex:Pump_12",
        observation_id="ex:Observation_Pump12_2026-05-18T14:03:00Z",
        procedure_id="ex:Procedure_InspectInletCavitation_Pump12",
        kg_evidence_id="ex:EvidenceEdge_001",
        document_evidence_id="ex:SOP_Chunk_7",
    )


def build_s4_run_configuration(
    query_set: QuerySet, *, random_seed: int = 0
) -> EvaluationRunConfiguration:
    """Build the controlled configuration shared by every S4 query run."""
    if not isinstance(query_set, QuerySet):
        raise TypeError("query_set must be a QuerySet")
    return EvaluationRunConfiguration(
        strategy=EvaluationStrategy.S4,
        dataset_id=query_set.dataset_id,
        query_set_id=query_set.query_set_id,
        model_configuration_id=_MODEL_CONFIGURATION_ID,
        retrieval_configuration_id=_RETRIEVAL_CONFIGURATION_ID,
        random_seed=random_seed,
        parameters={
            "dataset_sha256": query_set.document_sha256,
            "dataset_version": query_set.version,
        },
    )


@dataclass(frozen=True, slots=True)
class S4QueryEvaluation:
    """One S4 query: the comparable record and its metric observation."""

    result: EvaluationResult
    observation: MetricObservation

    def __post_init__(self) -> None:
        if not isinstance(self.result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        if not isinstance(self.observation, MetricObservation):
            raise TypeError("observation must be a MetricObservation")


def _provenance_components(triples: Sequence[tuple[Node, Node, Node]]) -> tuple[str, ...]:
    components: set[str] = set()
    for triple in triples:
        for node in triple:
            if not isinstance(node, URIRef):
                continue
            text = str(node)
            if not text.startswith(PROV_NAMESPACE):
                continue
            component = _PROV_COMPONENT_BY_TERM.get(text[len(PROV_NAMESPACE) :])
            if component is not None:
                components.add(component)
    return tuple(sorted(components))


def _validation_state(
    events: Sequence[StageEvent],
) -> tuple[bool | None, bool | None, int | None]:
    validation_event = next(
        (event for event in events if event.stage is StageName.SHACL_VALIDATION), None
    )
    repair_events = [event for event in events if event.stage is StageName.BOUNDED_REPAIR]
    repair_iterations = (
        max(event.repair_count for event in repair_events) if repair_events else None
    )
    if validation_event is None:
        return None, None, repair_iterations
    initial_passed = validation_event.status is TerminalStatus.PASSED
    final_passed = (
        repair_events[-1].status is TerminalStatus.PASSED if repair_events else initial_passed
    )
    return initial_passed, final_passed, repair_iterations


def _artifacts(
    orchestration: Pump12OrchestrationResult,
    evidence_ids: tuple[str, ...],
    provenance_components: tuple[str, ...],
) -> tuple[EvaluationArtifact, ...]:
    released_action = orchestration.released_action
    answer_text = (
        released_action.action
        if released_action is not None
        else orchestration.terminal_status.value
    )
    initial_passed, final_passed, repair_iterations = _validation_state(orchestration.events)
    if initial_passed is None:
        validation_artifact = EvaluationArtifact(
            kind=ArtifactKind.VALIDATION_REPORT,
            applicability=ArtifactApplicability.NOT_APPLICABLE,
            value=None,
            reason="run failed closed before SHACL validation",
        )
    else:
        validation_artifact = EvaluationArtifact(
            kind=ArtifactKind.VALIDATION_REPORT,
            applicability=ArtifactApplicability.PRESENT,
            value={
                "final_passed": final_passed,
                "initial_passed": initial_passed,
                "repair_iterations": repair_iterations,
            },
            reason=None,
        )
    if orchestration.provenance_id is None:
        provenance_artifact = EvaluationArtifact(
            kind=ArtifactKind.PROVENANCE_TRACE,
            applicability=ArtifactApplicability.NOT_APPLICABLE,
            value=None,
            reason="run failed closed before the provenance write",
        )
    else:
        provenance_artifact = EvaluationArtifact(
            kind=ArtifactKind.PROVENANCE_TRACE,
            applicability=ArtifactApplicability.PRESENT,
            value={
                "components": list(provenance_components),
                "provenance_id": orchestration.provenance_id,
            },
            reason=None,
        )
    return (
        EvaluationArtifact(
            kind=ArtifactKind.ANSWER,
            applicability=ArtifactApplicability.PRESENT,
            value={"released": released_action is not None, "text": answer_text},
            reason=None,
        ),
        EvaluationArtifact(
            kind=ArtifactKind.RETRIEVED_CONTEXT,
            applicability=ArtifactApplicability.PRESENT,
            value={"evidence_ids": list(evidence_ids)},
            reason=None,
        ),
        validation_artifact,
        provenance_artifact,
    )


def run_s4_query(
    query: QueryRecord,
    configuration: EvaluationRunConfiguration,
    *,
    scenario: Mapping[str, Any],
    asset_catalog: AssetCatalog,
    recorded_at: datetime,
    persist_trace: Callable[[Graph], None],
    harness_version: str,
    repository_revision: str,
    latency_ms: float | None = None,
    peak_memory_mb: float | None = None,
) -> S4QueryEvaluation:
    """Run one query through the production S4 orchestrator and record it."""
    if not isinstance(query, QueryRecord):
        raise TypeError("query must be a QueryRecord")
    if not isinstance(configuration, EvaluationRunConfiguration):
        raise TypeError("configuration must be an EvaluationRunConfiguration")
    if configuration.strategy is not EvaluationStrategy.S4:
        raise ValueError("configuration must target the S4 strategy")
    if not isinstance(scenario, Mapping):
        raise TypeError("scenario must be a mapping")
    if not isinstance(asset_catalog, AssetCatalog):
        raise TypeError("asset_catalog must be an AssetCatalog")
    if not isinstance(recorded_at, datetime):
        raise TypeError("recorded_at must be a datetime")
    if not callable(persist_trace):
        raise TypeError("persist_trace must be callable")

    stable_ids = build_stable_ids(query.query_id)
    asset_hint = query.asset_id.removeprefix("ex:")
    orchestration = run_pump12_orchestrator(
        {
            "query_text": query.text,
            "timestamp": recorded_at.isoformat(),
            "run_id": f"run:s4:{query.query_id}",
            "asset_hints": [asset_hint],
            "sensor_hints": ["anomalous_sound"],
        },
        scenario=scenario,
        asset_catalog=asset_catalog,
        query_id=query.query_id,
        stable_ids=stable_ids,
        recorded_at=recorded_at,
        persist_trace=persist_trace,
    )

    package = orchestration.evidence_package
    evidence_ids = (
        (*package.typed_kg_evidence_ids, *package.document_evidence_ids)
        if package is not None
        else ()
    )
    provenance_components = _provenance_components(orchestration.trace_graph_evidence)
    initial_passed, final_passed, repair_iterations = _validation_state(orchestration.events)
    released_action = orchestration.released_action

    result = EvaluationResult(
        configuration=configuration,
        manifest=EvaluationRunManifest(
            run_id=f"run:s4:{query.query_id}",
            repository_revision=repository_revision,
            harness_version=harness_version,
            dataset_sha256=dataset_sha256_from_configuration(configuration),
        ),
        query_id=query.query_id,
        raw_output={
            "evidence_package_id": package.package_id if package is not None else None,
            "provenance_id": orchestration.provenance_id,
            "recommendation": released_action.action if released_action is not None else None,
            "released": released_action is not None,
            "stage_count": len(orchestration.events),
            "terminal_status": orchestration.terminal_status.value,
        },
        errors=errors_from_events(orchestration.events),
        artifacts=_artifacts(orchestration, evidence_ids, provenance_components),
    )
    observation = MetricObservation(
        query_id=query.query_id,
        predicted_answer=released_action.action if released_action is not None else "",
        cited_evidence_refs=evidence_ids,
        terminal_status=orchestration.terminal_status,
        initial_shacl_passed=initial_passed,
        final_shacl_passed=final_passed,
        repair_iterations=repair_iterations,
        provenance_components=(
            provenance_components if orchestration.provenance_id is not None else None
        ),
        latency_ms=latency_ms,
        peak_memory_mb=peak_memory_mb,
    )
    return S4QueryEvaluation(result=result, observation=observation)


def count_terminal_statuses(
    evaluations: Sequence[S4QueryEvaluation],
) -> Mapping[TerminalStatus, int]:
    """Count recorded terminal statuses so fail-closed runs stay visible."""
    counts: dict[TerminalStatus, int] = {}
    for evaluation in evaluations:
        if not isinstance(evaluation, S4QueryEvaluation):
            raise TypeError("evaluations must contain S4QueryEvaluation instances")
        status = evaluation.observation.terminal_status
        counts[status] = counts.get(status, 0) + 1
    return counts
