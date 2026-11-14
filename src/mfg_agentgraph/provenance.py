"""Deterministic Architecture V1 Stage-10 PROV-O trace boundary.

This module constructs and submits one local RDF trace. It does not implement a
persistent store, an orchestrator, retention enforcement, or recommendation safety.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from rdflib.term import Node

from mfg_agentgraph.evidence_package import EvidencePackage
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

PROV: Final = Namespace("http://www.w3.org/ns/prov#")

_EXPECTED_STAGES: Final = (
    StageName.STRUCTURED_RETRIEVAL,
    StageName.PROCEDURAL_RETRIEVAL,
    StageName.CANDIDATE_GENERATION,
    StageName.SHACL_VALIDATION,
    StageName.BOUNDED_REPAIR,
    StageName.EVIDENCE_PACKAGE_ASSEMBLY,
)
_ACTIVITY_SUFFIXES: Final = {
    StageName.STRUCTURED_RETRIEVAL: "structured-retrieval",
    StageName.PROCEDURAL_RETRIEVAL: "procedural-retrieval",
    StageName.CANDIDATE_GENERATION: "model-invocation",
    StageName.SHACL_VALIDATION: "shacl-validation",
    StageName.BOUNDED_REPAIR: "bounded-repair",
    StageName.EVIDENCE_PACKAGE_ASSEMBLY: "evidence-assembly",
}
_ABSOLUTE_IRI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:[^\s]+$")


@dataclass(frozen=True, slots=True)
class ProvenanceWriteResult:
    """Immutable Stage-10 result; release identifiers exist only after a successful write."""

    provenance_id: str | None
    recommendation_id: str | None
    trace_graph_evidence: tuple[tuple[Node, Node, Node], ...]
    stage_event: StageEvent


PersistTrace = Callable[[Graph], object]


def write_provenance_trace(
    *,
    evidence_package: EvidencePackage,
    provenance_id: str,
    recommendation_id: str,
    agent_id: str,
    prompt_id: str,
    model_id: str,
    recorded_at: datetime,
    stage_events: Sequence[StageEvent],
    persist_trace: PersistTrace,
) -> ProvenanceWriteResult:
    """Construct and submit one deterministic PROV-O trace or fail closed."""

    run_id = _best_run_id(evidence_package)
    event_snapshot = _snapshot_events(stage_events)
    try:
        invalid_field = _invalid_field(
            evidence_package=evidence_package,
            provenance_id=provenance_id,
            recommendation_id=recommendation_id,
            agent_id=agent_id,
            prompt_id=prompt_id,
            model_id=model_id,
            recorded_at=recorded_at,
            stage_events=event_snapshot,
            persist_trace=persist_trace,
        )
    except Exception:
        invalid_field = "input"
    if invalid_field is not None:
        return _failure(run_id, invalid_field)

    assert type(evidence_package) is EvidencePackage
    assert event_snapshot is not None
    try:
        trace_graph = _build_trace_graph(
            evidence_package=evidence_package,
            provenance_id=provenance_id,
            recommendation_id=recommendation_id,
            agent_id=agent_id,
            prompt_id=prompt_id,
            model_id=model_id,
            recorded_at=recorded_at,
            stage_events=event_snapshot,
        )
        graph_evidence = _sorted_triples(trace_graph)
    except Exception:
        return _failure(run_id, "input")
    callback_graph = Graph()
    for triple in graph_evidence:
        callback_graph.add(triple)

    try:
        callback_result = persist_trace(callback_graph)
    except Exception:
        return _failure(run_id, "persistence")
    if callback_result is not None:
        return _failure(run_id, "persistence")

    return ProvenanceWriteResult(
        provenance_id=provenance_id,
        recommendation_id=recommendation_id,
        trace_graph_evidence=graph_evidence,
        stage_event=StageEvent(
            stage=StageName.PROV_O_TRACE_WRITING,
            run_id=evidence_package.run_id,
            status=TerminalStatus.PASSED,
            input_ids=(evidence_package.package_id,),
            output_ids=(provenance_id, recommendation_id),
        ),
    )


def _invalid_field(
    *,
    evidence_package: object,
    provenance_id: object,
    recommendation_id: object,
    agent_id: object,
    prompt_id: object,
    model_id: object,
    recorded_at: object,
    stage_events: object,
    persist_trace: object,
) -> str | None:
    if type(evidence_package) is not EvidencePackage:
        return "evidence_package"
    package_field = _package_field(evidence_package)
    if package_field is not None:
        return package_field
    for field_name, value in (
        ("provenance_id", provenance_id),
        ("recommendation_id", recommendation_id),
        ("agent_id", agent_id),
        ("prompt_id", prompt_id),
        ("model_id", model_id),
    ):
        if not _is_absolute_iri(value):
            return field_name
    if recommendation_id != evidence_package.action_id:
        return "recommendation_id"
    if (
        type(recorded_at) is not datetime
        or recorded_at.tzinfo is None
        or recorded_at.utcoffset() is None
    ):
        return "recorded_at"
    if stage_events is None:
        return "stage_events"
    event_snapshot = cast(tuple[StageEvent, ...], stage_events)
    event_field = _stage_event_field(evidence_package, event_snapshot)
    if event_field is not None:
        return event_field
    if not callable(persist_trace):
        return "persist_trace"
    return None


def _package_field(package: EvidencePackage) -> str | None:
    if not _is_nonblank(package.run_id):
        return "evidence_package"
    for value in (
        package.package_id,
        package.action_id,
        package.target_asset_id,
        package.validation_report_id,
    ):
        if not _is_absolute_iri(value):
            return "evidence_package"
    if package.terminal_status is not TerminalStatus.PASSED:
        return "evidence_package"
    if type(package.support_evidence_ids) is not tuple:
        return "evidence_package"
    if type(package.typed_kg_evidence_ids) is not tuple:
        return "evidence_package"
    if type(package.document_evidence_ids) is not tuple:
        return "evidence_package"
    if type(package.action_graph_evidence) is not tuple:
        return "evidence_package"
    support = package.support_evidence_ids
    kg = package.typed_kg_evidence_ids
    documents = package.document_evidence_ids
    if not kg or not documents or not support:
        return "evidence_package"
    if any(not _is_absolute_iri(value) for value in support + kg + documents):
        return "evidence_package"
    if len(set(support)) != len(support) or len(set(kg + documents)) != len(kg + documents):
        return "evidence_package"
    if set(support) != set(kg + documents):
        return "evidence_package"
    for triple in package.action_graph_evidence:
        if (
            type(triple) is not tuple
            or len(triple) != 3
            or any(not isinstance(node, Node) or isinstance(node, BNode) for node in triple)
        ):
            return "evidence_package"
    return None


def _snapshot_events(value: object) -> tuple[StageEvent, ...] | None:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return None
    try:
        return tuple(value)
    except Exception:
        return None


def _stage_event_field(package: EvidencePackage, events: tuple[StageEvent, ...]) -> str | None:
    if len(events) != len(_EXPECTED_STAGES):
        return "stage_events"
    if any(type(event) is not StageEvent for event in events):
        return "stage_events"
    if any(not _event_structure_is_valid(event) for event in events):
        return "stage_events"
    if tuple(event.stage for event in events) != _EXPECTED_STAGES:
        return "stage_events"
    if any(
        event.status is not TerminalStatus.PASSED or event.run_id != package.run_id or event.errors
        for event in events
    ):
        return "stage_events"

    structured, procedural, generation, validation, repair, assembly = events
    if not set(package.typed_kg_evidence_ids) <= set(structured.output_ids):
        return "stage_events"
    if not set(package.document_evidence_ids) <= set(procedural.output_ids):
        return "stage_events"
    if not set(package.support_evidence_ids) <= set(generation.input_ids):
        return "stage_events"
    if tuple(generation.output_ids) != (package.action_id,):
        return "stage_events"
    if tuple(validation.input_ids) != (package.action_id,):
        return "stage_events"
    if tuple(validation.output_ids) != (package.validation_report_id,):
        return "stage_events"
    if tuple(repair.input_ids) != (package.action_id, package.validation_report_id):
        return "stage_events"
    if tuple(repair.output_ids) != (package.validation_report_id,):
        return "stage_events"
    if tuple(assembly.input_ids) != (package.action_id, package.validation_report_id):
        return "stage_events"
    if tuple(assembly.output_ids) != (package.package_id,):
        return "stage_events"
    return None


def _event_structure_is_valid(event: StageEvent) -> bool:
    return (
        isinstance(event.stage, StageName)
        and isinstance(event.status, TerminalStatus)
        and _is_nonblank(event.run_id)
        and type(event.input_ids) is tuple
        and type(event.output_ids) is tuple
        and type(event.errors) is tuple
        and all(_is_nonblank(value) for value in event.input_ids + event.output_ids)
        and all(type(error) is StageError for error in event.errors)
        and isinstance(event.retry_count, int)
        and not isinstance(event.retry_count, bool)
        and event.retry_count >= 0
        and isinstance(event.repair_count, int)
        and not isinstance(event.repair_count, bool)
        and event.repair_count >= 0
    )


def _build_trace_graph(
    *,
    evidence_package: EvidencePackage,
    provenance_id: str,
    recommendation_id: str,
    agent_id: str,
    prompt_id: str,
    model_id: str,
    recorded_at: datetime,
    stage_events: tuple[StageEvent, ...],
) -> Graph:
    graph = Graph()
    trace = URIRef(provenance_id)
    recommendation = URIRef(recommendation_id)
    package = URIRef(evidence_package.package_id)
    report = URIRef(evidence_package.validation_report_id)
    agent = URIRef(agent_id)
    prompt = URIRef(prompt_id)
    model = URIRef(model_id)
    activities = {
        event.stage: URIRef(f"{provenance_id}/activities/{_ACTIVITY_SUFFIXES[event.stage]}")
        for event in stage_events
    }
    write_activity = URIRef(f"{provenance_id}/activities/provenance-writing")

    graph.add((trace, RDF.type, PROV.Entity))
    graph.add((trace, RDF.type, MFG.ProvenanceTrace))
    graph.add((trace, MFG.runId, Literal(evidence_package.run_id)))
    graph.add((trace, MFG.recordedAt, Literal(recorded_at, datatype=XSD.dateTime)))
    graph.add((trace, MFG.recommendation, recommendation))
    graph.add((trace, MFG.evidencePackage, package))
    graph.add((agent, RDF.type, PROV.SoftwareAgent))

    entity_ids = (
        prompt_id,
        model_id,
        evidence_package.action_id,
        evidence_package.validation_report_id,
        evidence_package.package_id,
        *evidence_package.support_evidence_ids,
    )
    for entity_id in entity_ids:
        graph.add((URIRef(entity_id), RDF.type, PROV.Entity))

    for activity in (*activities.values(), write_activity):
        graph.add((activity, RDF.type, PROV.Activity))
        graph.add((activity, PROV.wasAssociatedWith, agent))

    structured = activities[StageName.STRUCTURED_RETRIEVAL]
    procedural = activities[StageName.PROCEDURAL_RETRIEVAL]
    generation = activities[StageName.CANDIDATE_GENERATION]
    validation = activities[StageName.SHACL_VALIDATION]
    repair = activities[StageName.BOUNDED_REPAIR]
    assembly = activities[StageName.EVIDENCE_PACKAGE_ASSEMBLY]

    for evidence_id in evidence_package.typed_kg_evidence_ids:
        graph.add((URIRef(evidence_id), PROV.wasGeneratedBy, structured))
    for evidence_id in evidence_package.document_evidence_ids:
        graph.add((URIRef(evidence_id), PROV.wasGeneratedBy, procedural))
    graph.add((generation, PROV.used, prompt))
    graph.add((generation, PROV.used, model))
    for evidence_id in evidence_package.support_evidence_ids:
        graph.add((generation, PROV.used, URIRef(evidence_id)))
    graph.add((recommendation, PROV.wasGeneratedBy, generation))
    graph.add((validation, PROV.used, recommendation))
    graph.add((report, PROV.wasGeneratedBy, validation))
    graph.add((repair, PROV.used, recommendation))
    graph.add((repair, PROV.used, report))
    graph.add((assembly, PROV.used, recommendation))
    graph.add((assembly, PROV.used, report))
    for evidence_id in evidence_package.support_evidence_ids:
        graph.add((assembly, PROV.used, URIRef(evidence_id)))
    graph.add((package, PROV.wasGeneratedBy, assembly))
    graph.add((write_activity, PROV.used, package))
    graph.add((trace, PROV.wasGeneratedBy, write_activity))

    chain = (structured, procedural, generation, validation, repair, assembly, write_activity)
    for current, previous in zip(chain[1:], chain, strict=False):
        graph.add((current, PROV.wasInformedBy, previous))
    return graph


def _sorted_triples(graph: Graph) -> tuple[tuple[Node, Node, Node], ...]:
    return tuple(
        sorted(
            tuple(graph),
            key=lambda triple: tuple((type(node).__name__, node.n3()) for node in triple),
        )
    )


def _failure(run_id: str, field: str) -> ProvenanceWriteResult:
    return ProvenanceWriteResult(
        provenance_id=None,
        recommendation_id=None,
        trace_graph_evidence=(),
        stage_event=StageEvent(
            stage=StageName.PROV_O_TRACE_WRITING,
            run_id=run_id,
            status=TerminalStatus.PROVENANCE_FAILED_CLOSED,
            errors=(StageError(StageErrorCode.PROVENANCE_WRITE_FAILED, field=field),),
        ),
    )


def _best_run_id(value: object) -> str:
    if type(value) is EvidencePackage and _is_nonblank(value.run_id):
        return value.run_id
    return "unknown-run"


def _is_nonblank(value: object) -> bool:
    return type(value) is str and bool(value.strip()) and value == value.strip()


def _is_absolute_iri(value: object) -> bool:
    return type(value) is str and value == value.strip() and bool(_ABSOLUTE_IRI.fullmatch(value))
