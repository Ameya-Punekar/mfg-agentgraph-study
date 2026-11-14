"""Deterministic ten-stage Pump_12 S4 orchestration boundary.

The orchestrator composes the existing service-free component contracts. It does
not perform network I/O, generate identities, or provide durable persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rdflib import URIRef
from rdflib.term import Node

from mfg_agentgraph.bounded_repair import BoundedRepairRequest, run_bounded_repair
from mfg_agentgraph.candidate_action import (
    CandidateAction,
    CandidateActionError,
    CandidateActionErrorCode,
    parse_candidate_actions,
)
from mfg_agentgraph.entity_resolution import AssetCatalog
from mfg_agentgraph.evidence_package import EvidencePackage, assemble_evidence_package
from mfg_agentgraph.fixture_model_adapter import (
    FixtureModelVariant,
    generate_fixture_candidate_actions,
)
from mfg_agentgraph.operator_request import (
    NormalizedOperatorRequest,
    normalize_operator_request,
)
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.provenance import PersistTrace, write_provenance_trace
from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf
from mfg_agentgraph.shacl_validation import ShaclValidationResult, validate_recommended_action
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import retrieve_structured_support


@dataclass(frozen=True, slots=True)
class Pump12StableIds:
    """Caller-owned stable identities used by the deterministic Pump_12 run."""

    action_id: str
    validation_report_id: str
    evidence_package_id: str
    provenance_id: str
    agent_id: str
    prompt_id: str
    model_id: str
    asset_id: str
    observation_id: str
    procedure_id: str
    kg_evidence_id: str
    document_evidence_id: str

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value.strip() or value != value.strip():
                raise ValueError(f"{field_name} must be a strict nonblank string")

    def resource_iris(self) -> dict[str, URIRef]:
        """Map canonical fixture stable IDs to caller-owned RDF identities."""
        return {
            "ex:Pump_12": URIRef(self.asset_id),
            "ex:Observation_Pump12_2026-05-18T14:03:00Z": URIRef(self.observation_id),
            "ex:Procedure_InspectInletCavitation_Pump12": URIRef(self.procedure_id),
            "ex:EvidenceEdge_001": URIRef(self.kg_evidence_id),
            "ex:SOP_Chunk_7": URIRef(self.document_evidence_id),
        }


@dataclass(frozen=True, slots=True)
class Pump12OrchestrationResult:
    """Immutable orchestration result; release fields are all-or-nothing."""

    terminal_status: TerminalStatus
    released_action: CandidateAction | None
    evidence_package: EvidencePackage | None
    provenance_id: str | None
    recommendation_id: str | None
    trace_graph_evidence: tuple[tuple[Node, Node, Node], ...]
    events: tuple[StageEvent, ...]


def run_pump12_orchestrator(
    raw_request: object,
    *,
    scenario: Mapping[str, Any],
    asset_catalog: AssetCatalog,
    query_id: str,
    stable_ids: Pump12StableIds,
    recorded_at: datetime,
    persist_trace: PersistTrace,
) -> Pump12OrchestrationResult:
    """Run the deterministic Pump_12 path and release only after Stage 10 succeeds."""
    normalized = normalize_operator_request(raw_request)
    if not isinstance(normalized, NormalizedOperatorRequest):
        raise ValueError("raw_request must satisfy the normalized operator request contract")
    if not isinstance(asset_catalog, AssetCatalog):
        raise TypeError("asset_catalog must be an AssetCatalog")
    if not isinstance(stable_ids, Pump12StableIds):
        raise TypeError("stable_ids must be Pump12StableIds")
    if len(normalized.asset_hints) != 1:
        raise ValueError("raw_request must contain exactly one asset hint")
    resolution = asset_catalog.resolve(normalized.asset_hints[0])
    candidate_ids = tuple(candidate.asset.asset_id for candidate in resolution.candidates)
    if resolution.status is not TerminalStatus.PASSED or resolution.selected_asset is None:
        resolution_event = StageEvent(
            stage=StageName.ENTITY_ASSET_RESOLUTION,
            run_id=normalized.run_id,
            status=TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED,
            input_ids=(query_id, normalized.asset_hints[0]),
            output_ids=candidate_ids,
            errors=(
                StageError(
                    StageErrorCode.OPERATOR_DISAMBIGUATION_REQUIRED,
                    field="asset_hints",
                ),
            ),
        )
        return _blocked_result(
            TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED,
            (resolution_event,),
        )
    asset = resolution.selected_asset
    resolution_event = StageEvent(
        stage=StageName.ENTITY_ASSET_RESOLUTION,
        run_id=normalized.run_id,
        status=TerminalStatus.PASSED,
        input_ids=(query_id, normalized.asset_hints[0]),
        output_ids=(asset.asset_id,),
    )
    structured = retrieve_structured_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id=normalized.run_id,
        query_id=query_id,
    )
    if structured.status is not TerminalStatus.PASSED:
        return _blocked_result(
            structured.status,
            (resolution_event, structured.event),
        )
    procedural = retrieve_procedural_support(
        resolved_asset=asset,
        scenario=scenario,
        retrieval_run_id=normalized.run_id,
        query_id=query_id,
    )
    if procedural.status is not TerminalStatus.PASSED:
        return _blocked_result(
            procedural.status,
            (resolution_event, structured.event, procedural.event),
        )
    generation = generate_fixture_candidate_actions(
        scenario=scenario,
        structured_result=structured,
        procedural_result=procedural,
        generation_run_id=normalized.run_id,
        query_id=query_id,
        variant=FixtureModelVariant.REPAIRED,
    )
    try:
        plan = parse_candidate_actions(
            generation.raw_json,
            known_assets={asset.asset_id},
            evidence_catalog=generation.evidence_catalog,
        )
    except CandidateActionError as exc:
        if exc.code is not CandidateActionErrorCode.UNKNOWN_EVIDENCE_ID:
            raise
        candidate_event = StageEvent(
            stage=StageName.CANDIDATE_GENERATION,
            run_id=normalized.run_id,
            status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            input_ids=(generation.candidate_id,),
            errors=(StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field=exc.field),),
        )
        return _blocked_result(
            TerminalStatus.INSUFFICIENT_EVIDENCE,
            (resolution_event, structured.event, procedural.event, candidate_event),
        )
    action = plan.ranked_actions[0]
    resource_iris = stable_ids.resource_iris()
    action_uri = URIRef(stable_ids.action_id)
    anomaly_window = scenario["anomaly_window"]
    if not isinstance(anomaly_window, Mapping):
        raise ValueError("scenario.anomaly_window must be a mapping")
    assembled = assemble_recommended_action_rdf(
        action,
        action_iri=action_uri,
        resource_iris=resource_iris,
        anomaly_window_start=_scenario_text(anomaly_window, "started_at"),
        anomaly_window_end=_scenario_text(anomaly_window, "ended_at"),
        structured_result=structured,
        procedural_result=procedural,
    )
    rdf_event = StageEvent(
        stage=StageName.RDF_REIFICATION,
        run_id=normalized.run_id,
        status=TerminalStatus.PASSED,
        input_ids=(generation.candidate_id,),
        output_ids=(stable_ids.action_id,),
    )
    validation = validate_recommended_action(
        assembled.action_graph,
        action_uri=action_uri,
        support_graph=assembled.support_graph,
        report_uri=URIRef(stable_ids.validation_report_id),
        run_id=normalized.run_id,
    )
    outcome = run_bounded_repair(
        validation,
        retry_budget=0,
        repair_attempt=_unexpected_repair,
    )
    if outcome.final_status is not TerminalStatus.PASSED:
        return _blocked_result(
            outcome.final_status,
            (
                resolution_event,
                structured.event,
                procedural.event,
                generation.event,
                rdf_event,
                validation.stage_event,
                *outcome.events,
            ),
        )
    final_validation = outcome.final_validation
    fallback_event = StageEvent(
        stage=StageName.EXPLICIT_FALLBACK,
        run_id=normalized.run_id,
        status=TerminalStatus.PASSED,
        input_ids=(stable_ids.action_id, final_validation.report_id),
        output_ids=(final_validation.report_id,),
    )
    package_result = assemble_evidence_package(
        action=action,
        action_id=stable_ids.action_id,
        action_graph=assembled.action_graph,
        validation=final_validation,
        outcome=outcome,
        package_id=stable_ids.evidence_package_id,
        resource_iris=resource_iris,
        typed_kg_evidence_ids=(stable_ids.kg_evidence_id,),
        document_evidence_ids=(stable_ids.document_evidence_id,),
    )
    if package_result.package is None:
        return _blocked_result(
            package_result.stage_event.status,
            (
                resolution_event,
                structured.event,
                procedural.event,
                generation.event,
                rdf_event,
                validation.stage_event,
                *outcome.events,
                fallback_event,
                package_result.stage_event,
            ),
        )
    package = package_result.package
    provenance = write_provenance_trace(
        evidence_package=package,
        provenance_id=stable_ids.provenance_id,
        recommendation_id=stable_ids.action_id,
        agent_id=stable_ids.agent_id,
        prompt_id=stable_ids.prompt_id,
        model_id=stable_ids.model_id,
        recorded_at=recorded_at,
        stage_events=(
            structured.event,
            procedural.event,
            generation.event,
            validation.stage_event,
            outcome.events[0],
            package_result.stage_event,
        ),
        persist_trace=persist_trace,
    )
    events = (
        resolution_event,
        structured.event,
        procedural.event,
        generation.event,
        rdf_event,
        validation.stage_event,
        outcome.events[0],
        fallback_event,
        package_result.stage_event,
        provenance.stage_event,
    )
    if provenance.stage_event.status is not TerminalStatus.PASSED:
        return _blocked_result(provenance.stage_event.status, events)
    return Pump12OrchestrationResult(
        terminal_status=TerminalStatus.PASSED,
        released_action=action,
        evidence_package=package,
        provenance_id=provenance.provenance_id,
        recommendation_id=provenance.recommendation_id,
        trace_graph_evidence=provenance.trace_graph_evidence,
        events=events,
    )


def _blocked_result(
    status: TerminalStatus,
    events: tuple[StageEvent, ...],
) -> Pump12OrchestrationResult:
    return Pump12OrchestrationResult(
        terminal_status=status,
        released_action=None,
        evidence_package=None,
        provenance_id=None,
        recommendation_id=None,
        trace_graph_evidence=(),
        events=events,
    )


def _scenario_text(mapping: Mapping[object, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"scenario.anomaly_window.{key} must be a nonblank string")
    return value


def _unexpected_repair(_request: BoundedRepairRequest) -> ShaclValidationResult:
    raise RuntimeError("repair callback must not run for the conforming Issue #23 path")
