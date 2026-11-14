"""Stage-9 evidence package assembly contract.

This module assembles an immutable in-memory evidence package only. It does not
persist provenance and does not release recommendations; those are later stages.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF, RDFS, SH, XSD
from rdflib.term import Node

from mfg_agentgraph.bounded_repair import BoundedRepairOutcome
from mfg_agentgraph.candidate_action import CandidateAction
from mfg_agentgraph.evidence_reference import (
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
)
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import ShaclValidationResult
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)


@dataclass(frozen=True, slots=True)
class EvidencePackage:
    """Immutable Stage-9 package linking action, evidence, and validation report."""

    package_id: str
    run_id: str
    action_id: str
    target_asset_id: str
    validation_report_id: str
    terminal_status: TerminalStatus
    support_evidence_ids: tuple[str, ...]
    typed_kg_evidence_ids: tuple[str, ...]
    document_evidence_ids: tuple[str, ...]
    action_graph_evidence: tuple[tuple[Node, Node, Node], ...]


@dataclass(frozen=True, slots=True)
class EvidencePackageAssemblyResult:
    """Stage-9 value result; package is absent on any fail-closed condition."""

    package: EvidencePackage | None
    stage_event: StageEvent


def assemble_evidence_package(
    *,
    action: CandidateAction,
    action_id: str,
    action_graph: Graph,
    validation: ShaclValidationResult,
    outcome: BoundedRepairOutcome,
    package_id: str,
    resource_iris: Mapping[str, URIRef],
    typed_kg_evidence_ids: Sequence[str],
    document_evidence_ids: Sequence[str],
) -> EvidencePackageAssemblyResult:
    """Assemble a Stage-9 evidence package or fail closed with a typed event."""

    run_id = _best_run_id(validation, outcome)
    action_graph_snapshot = _snapshot_graph_or_none(action_graph)
    resource_iris_snapshot = _snapshot_resource_iris_or_none(resource_iris)
    kg_ids = _normalize_ids_or_none(typed_kg_evidence_ids)
    doc_ids = _normalize_ids_or_none(document_evidence_ids)

    invalid_field = _invalid_field(
        action=action,
        action_id=action_id,
        action_graph=action_graph_snapshot,
        validation=validation,
        outcome=outcome,
        package_id=package_id,
        resource_iris=resource_iris_snapshot,
        typed_kg_evidence_ids=kg_ids,
        document_evidence_ids=doc_ids,
    )
    if invalid_field is not None:
        return _failure(run_id, invalid_field, action_id, validation)

    assert isinstance(action, CandidateAction)
    assert isinstance(action_graph_snapshot, Graph)
    assert isinstance(validation, ShaclValidationResult)
    assert isinstance(outcome, BoundedRepairOutcome)
    normalized_package_id = _require_nonblank_or_none(package_id)
    assert normalized_package_id is not None
    assert resource_iris_snapshot is not None
    assert kg_ids is not None
    assert doc_ids is not None
    identity = _identity(validation)
    assert identity is not None
    run_id, expected_action_id = identity
    target_id = _single_uri_object(
        action_graph_snapshot, URIRef(expected_action_id), MFG.targetAsset
    )
    assert target_id is not None

    support_ids = tuple(
        str(resource_iris_snapshot[reference.stable_id]) for reference in action.support_evidence
    )
    package = EvidencePackage(
        package_id=normalized_package_id,
        run_id=run_id,
        action_id=expected_action_id,
        target_asset_id=str(target_id),
        validation_report_id=validation.report_id,
        terminal_status=TerminalStatus.PASSED,
        support_evidence_ids=support_ids,
        typed_kg_evidence_ids=kg_ids,
        document_evidence_ids=doc_ids,
        action_graph_evidence=tuple(
            sorted(
                tuple(action_graph_snapshot),
                key=lambda triple: tuple((type(node).__name__, node.n3()) for node in triple),
            )
        ),
    )
    return EvidencePackageAssemblyResult(
        package=package,
        stage_event=StageEvent(
            stage=StageName.EVIDENCE_PACKAGE_ASSEMBLY,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(expected_action_id, validation.report_id),
            output_ids=(normalized_package_id,),
        ),
    )


def _invalid_field(
    *,
    action: object,
    action_id: object,
    action_graph: object,
    validation: object,
    outcome: object,
    package_id: object,
    resource_iris: object,
    typed_kg_evidence_ids: object,
    document_evidence_ids: object,
) -> str | None:
    if not isinstance(validation, ShaclValidationResult):
        return "validation"
    if not isinstance(outcome, BoundedRepairOutcome):
        return "outcome"
    if type(action) is not CandidateAction:
        return "action"
    if not isinstance(action.rank, int) or isinstance(action.rank, bool) or action.rank < 1:
        return "action"
    if (
        not isinstance(action.action, str)
        or not action.action.strip()
        or action.action != action.action.strip()
    ):
        return "action"
    if (
        not isinstance(action.target_asset, str)
        or not action.target_asset.strip()
        or action.target_asset != action.target_asset.strip()
    ):
        return "action"
    if _require_nonblank_or_none(action_id) is None:
        return "action_id"
    if _require_nonblank_or_none(package_id) is None:
        return "package_id"
    if not isinstance(resource_iris, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, URIRef)
        for key, value in resource_iris.items()
    ):
        return "resource_iris"
    kg_ids = _normalize_ids_or_none(typed_kg_evidence_ids)
    if kg_ids is None:
        return "typed_kg_evidence_ids"
    doc_ids = _normalize_ids_or_none(document_evidence_ids)
    if doc_ids is None:
        return "document_evidence_ids"
    if _duplicate_values(kg_ids + doc_ids):
        return "support_evidence"
    if not isinstance(action_graph, Graph):
        return "action_graph"
    if any(isinstance(node, BNode) for triple in action_graph for node in triple):
        return "action_graph"
    identity_field = _validation_identity_field(validation, action_id)
    if identity_field is not None:
        return identity_field
    if validation.action_graph_digest != _graph_digest(action_graph):
        return "action_graph"
    if outcome.final_validation != validation or outcome.final_status is not TerminalStatus.PASSED:
        return "outcome"
    if (
        not isinstance(outcome.events, tuple)
        or len(outcome.events) != 1
        or any(
            not isinstance(event, StageEvent)
            or event.stage is not StageName.BOUNDED_REPAIR
            or event.status is not TerminalStatus.PASSED
            or event.run_id != validation.stage_event.run_id
            or len(event.input_ids) != 2
            or event.input_ids[0] != action_id
            or not _repair_event_report_chain_matches(event, outcome, validation)
            or tuple(event.output_ids) != (validation.report_id,)
            or event.errors
            for event in outcome.events
        )
    ):
        return "outcome"
    if not validation.conforms:
        return "validation"
    if validation.violations != ():
        return "validation"
    support_field = _action_support_field(
        action, action_id, action_graph, resource_iris, kg_ids, doc_ids
    )
    if support_field is not None:
        return support_field
    return None


def _validation_identity_field(validation: ShaclValidationResult, action_id: object) -> str | None:
    if type(validation.conforms) is not bool:
        return "validation"
    if not isinstance(validation.report_id, str) or not validation.report_id.strip():
        return "validation"
    event = validation.stage_event
    if not isinstance(event, StageEvent):
        return "stage_event"
    if event.stage is not StageName.SHACL_VALIDATION:
        return "stage_event"
    expected_status = (
        TerminalStatus.PASSED if validation.conforms else TerminalStatus.VALIDATION_FAILED_CLOSED
    )
    if event.status is not expected_status:
        return "stage_event"
    expected_action_id = _require_nonblank_or_none(action_id)
    if expected_action_id is None:
        return "action_id"
    if tuple(event.input_ids) != (expected_action_id,):
        return "action_id"
    report_run_id = _single_report_run_id(validation)
    if report_run_id is not None and report_run_id != event.run_id:
        return "run_id"
    if tuple(event.output_ids) != (validation.report_id,):
        return "validation"
    if not _report_graph_matches(validation, event.run_id, expected_action_id):
        return "report_graph"
    if validation.action_graph_digest is None:
        return "action_graph"
    return None


def _report_graph_matches(
    validation: ShaclValidationResult, expected_run_id: str, expected_action_id: str
) -> bool:
    if not isinstance(validation.report_graph, Graph):
        return False
    report_uri = URIRef(validation.report_id)
    try:
        base_matches = (
            tuple(validation.report_graph.objects(report_uri, RDF.type)) == (SH.ValidationReport,)
            and tuple(validation.report_graph.objects(report_uri, SH.conforms))
            == (Literal(validation.conforms),)
            and tuple(validation.report_graph.objects(report_uri, MFG.focusAction))
            == (URIRef(expected_action_id),)
            and tuple(validation.report_graph.objects(report_uri, MFG.runId))
            == (Literal(expected_run_id),)
        )
        if not base_matches:
            return False
        return not (
            validation.conforms
            and (
                tuple(validation.report_graph.objects(report_uri, SH.result))
                or tuple(validation.report_graph.objects(report_uri, MFG.violation))
                or tuple(validation.report_graph.subjects(RDF.type, SH.ValidationResult))
            )
        )
    except Exception:
        return False


def _single_report_run_id(validation: object) -> str | None:
    if not isinstance(validation, ShaclValidationResult) or not isinstance(
        validation.report_graph, Graph
    ):
        return None
    try:
        values = tuple(validation.report_graph.objects(URIRef(validation.report_id), MFG.runId))
    except Exception:
        return None
    if len(values) != 1 or not isinstance(values[0], Literal):
        return None
    value = str(values[0]).strip()
    return value or None


def _repair_event_report_chain_matches(
    event: StageEvent,
    outcome: BoundedRepairOutcome,
    validation: ShaclValidationResult,
) -> bool:
    if event.retry_count != outcome.retry_count or event.repair_count != outcome.repair_count:
        return False
    initial_report_id = event.input_ids[1]
    if outcome.initial_failure_count == 0:
        return (
            initial_report_id == validation.report_id
            and outcome.repair_count == 0
            and outcome.retry_count == 0
            and outcome.self_correction_success_count == 0
        )
    return (
        outcome.initial_failure_count == 1
        and initial_report_id != validation.report_id
        and bool(initial_report_id.strip())
        and outcome.repair_count >= 1
        and 1 <= outcome.retry_count <= outcome.repair_count
        and outcome.self_correction_success_count == 1
    )


def _action_support_field(
    action: CandidateAction,
    action_id: object,
    graph: Graph,
    resource_iris: Mapping[str, URIRef],
    kg_ids: tuple[str, ...],
    doc_ids: tuple[str, ...],
) -> str | None:
    expected_action_id = _require_nonblank_or_none(action_id)
    if expected_action_id is None:
        return "action_id"
    action_uri = URIRef(expected_action_id)
    if (action_uri, RDF.type, MFG.RecommendedAction) not in graph:
        return "action_graph"
    if tuple(graph.objects(action_uri, RDFS.label)) != (Literal(action.action),):
        return "action_graph"
    if tuple(graph.objects(action_uri, MFG.rank)) != (Literal(action.rank, datatype=XSD.integer),):
        return "action_graph"
    target = _single_uri_object(graph, action_uri, MFG.targetAsset)
    if target is None:
        return "action_graph"
    if not isinstance(action.target_asset, str) or resource_iris.get(action.target_asset) != target:
        return "action_graph"
    if type(action.support_evidence) is not tuple:
        return "support_evidence"
    references = action.support_evidence
    if not references or any(
        not isinstance(reference, EvidenceReference) for reference in references
    ):
        return "support_evidence"
    support_ids = tuple(reference.stable_id for reference in references)
    if not support_ids:
        return "support_evidence"
    if _duplicate_values(support_ids):
        return "support_evidence"
    if any(stable_id not in resource_iris for stable_id in support_ids):
        return "support_evidence"
    for reference in references:
        if reference.validation_status is not EvidenceValidationStatus.VALIDATED:
            return "support_evidence"
    expected_graph_support = frozenset(str(resource_iris[stable_id]) for stable_id in support_ids)
    observed_graph_support = frozenset(
        str(node) for node in graph.objects(action_uri, MFG.hasSupportEvidence)
    )
    if observed_graph_support != expected_graph_support:
        return "action_graph"
    expected_kg = tuple(
        str(resource_iris[reference.stable_id])
        for reference in references
        if reference.kind in (EvidenceKind.KG_EDGE, EvidenceKind.KG_RESOURCE)
    )
    expected_doc = tuple(
        str(resource_iris[reference.stable_id])
        for reference in references
        if reference.kind is EvidenceKind.DOCUMENT_CHUNK
    )
    if not expected_kg or not expected_doc:
        return "support_evidence"
    if expected_kg != kg_ids:
        return "typed_kg_evidence_ids"
    if expected_doc != doc_ids:
        return "document_evidence_ids"
    return None


def _identity(validation: object) -> tuple[str, str] | None:
    if not isinstance(validation, ShaclValidationResult):
        return None
    event = validation.stage_event
    if not isinstance(event, StageEvent) or len(event.input_ids) != 1:
        return None
    return event.run_id, event.input_ids[0]


def _best_run_id(validation: object, outcome: object) -> str:
    identity = _identity(validation)
    if identity is not None:
        report_run_id = _single_report_run_id(validation)
        if report_run_id is not None:
            return report_run_id
        return identity[0]
    if isinstance(outcome, BoundedRepairOutcome):
        identity = _identity(outcome.final_validation)
        if identity is not None:
            return identity[0]
    return "unknown-run"


def _failure(
    run_id: str, field: str, action_id: object, validation: object
) -> EvidencePackageAssemblyResult:
    input_ids: tuple[str, ...] = ()
    normalized_action_id = _require_nonblank_or_none(action_id)
    if normalized_action_id is not None:
        normalized_report_id = (
            _require_nonblank_or_none(validation.report_id)
            if isinstance(validation, ShaclValidationResult)
            else None
        )
        if normalized_report_id is not None:
            input_ids = (normalized_action_id, normalized_report_id)
        else:
            input_ids = (normalized_action_id,)
    return EvidencePackageAssemblyResult(
        package=None,
        stage_event=StageEvent(
            stage=StageName.EVIDENCE_PACKAGE_ASSEMBLY,
            run_id=run_id,
            status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            input_ids=input_ids,
            output_ids=(),
            errors=(StageError(StageErrorCode.INVALID_EVIDENCE_PACKAGE, field=field),),
        ),
    )


def _single_uri_object(graph: Graph, subject: URIRef, predicate: URIRef) -> URIRef | None:
    objects = tuple(graph.objects(subject, predicate))
    if len(objects) != 1 or not isinstance(objects[0], URIRef):
        return None
    return objects[0]


def _require_nonblank_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _snapshot_graph_or_none(value: object) -> Graph | None:
    if not isinstance(value, Graph):
        return None
    snapshot = Graph()
    try:
        for triple in tuple(value):
            snapshot.add(triple)
    except Exception:
        return None
    return snapshot


def _snapshot_resource_iris_or_none(value: object) -> dict[str, URIRef] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        items = tuple(value.items())
        snapshot = dict(items)
    except Exception:
        return None
    if len(snapshot) != len(items):
        return None
    return snapshot


def _normalize_ids_or_none(values: object) -> tuple[str, ...] | None:
    if isinstance(values, str) or not isinstance(values, Sequence):
        return None
    normalized: list[str] = []
    for value in values:
        text = _require_nonblank_or_none(value)
        if text is None:
            return None
        normalized.append(text)
    return tuple(normalized)


def _graph_digest(graph: Graph) -> str:
    return f"{to_isomorphic(graph).graph_digest():064x}"  # type: ignore[no-untyped-call]


def _duplicate_values(values: Sequence[str]) -> bool:
    return len(frozenset(values)) != len(tuple(values))
