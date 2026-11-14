"""SHACL validation adapter for recommended action graphs.

MFG is the package's internal Architecture V1 namespace. The terms used by this
module and by ``shapes/recommended_action.ttl`` are stable for package contracts
but are not a published ontology.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources

from pyshacl import validate as _pyshacl_validate
from rdflib import Graph, Literal, URIRef
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from mfg_agentgraph.diagnostics import (
    DiagnosticCode,
    DiagnosticComponent,
    DiagnosticOperation,
    emit_diagnostic,
)
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

ValidationEngine = Callable[..., tuple[bool, Graph, str]]

_RESULT_COPY_PREDICATES = (
    SH.sourceShape,
    SH.focusNode,
    SH.resultMessage,
    SH.sourceConstraintComponent,
    SH.resultPath,
)


class ShaclValidationErrorCode(StrEnum):
    """Stable machine-readable adapter failure codes."""

    INVALID_INPUT = "invalid_input"
    ENGINE_ERROR = "engine_error"


class ShaclValidationError(ValueError):
    """Deterministic adapter error without rejected content or engine details."""

    __slots__ = ("code", "field")

    def __init__(self, code: ShaclValidationErrorCode, field: str) -> None:
        if not isinstance(code, ShaclValidationErrorCode):
            raise TypeError("code must be a ShaclValidationErrorCode")
        self.code = code
        self.field = field
        super().__init__(f"{code.value}: {field}")


@dataclass(frozen=True, slots=True)
class ShaclViolation:
    """Structured, deterministic view of one SHACL validation result."""

    result_node: str
    shape_id: str
    focus_node: str
    message: str
    source_constraint_component: str | None = None
    path: str | None = None


@dataclass(frozen=True, slots=True)
class ShaclValidationResult:
    """Typed result returned by the recommended-action SHACL gate."""

    conforms: bool
    report_id: str
    violations: tuple[ShaclViolation, ...]
    report_graph: Graph
    stage_event: StageEvent
    action_graph_digest: str | None = None


@dataclass(frozen=True, slots=True)
class _RawResultRow:
    sort_key: tuple[str, str, str, str | None, str | None, str | None, str]
    result_node: Node


def load_recommended_action_shapes() -> Graph:
    """Load package-owned SHACL shapes for recommended actions."""

    shapes = Graph()
    shape_text = (
        resources.files("mfg_agentgraph")
        .joinpath("shapes", "recommended_action.ttl")
        .read_text(encoding="utf-8")
    )
    shapes.parse(data=shape_text, format="turtle")
    return shapes


def _recommended_action_shapes_for(action_uri: URIRef) -> Graph:
    """Return invocation-local shapes scoped to the requested action node."""

    package_shapes = load_recommended_action_shapes()
    shapes = Graph()
    for prefix, namespace in package_shapes.namespaces():
        shapes.bind(prefix, namespace)
    for triple in package_shapes:
        shapes.add(triple)
    for shape in tuple(shapes.subjects(SH.targetClass, MFG.RecommendedAction)):
        shapes.remove((shape, SH.targetClass, MFG.RecommendedAction))
        shapes.add((shape, SH.targetNode, action_uri))
    return shapes


def validate_recommended_action(
    action_graph: Graph,
    *,
    action_uri: URIRef,
    support_graph: Graph,
    report_uri: URIRef,
    run_id: str,
    validation_engine: ValidationEngine = _pyshacl_validate,
) -> ShaclValidationResult:
    """Validate a complete recommended-action graph and return a stable report.

    ``action_graph`` is the RDF action mapper output. ``support_graph`` is the
    caller-supplied evidence subgraph for assets, support evidence, observations,
    anomaly windows, and procedures. Both inputs are copied before validation.
    """

    _validate_inputs(action_graph, action_uri, support_graph, report_uri, run_id)
    data_graph = Graph()
    for triple in action_graph:
        data_graph.add(triple)
    for triple in support_graph:
        data_graph.add(triple)

    engine_failed = False
    try:
        conforms_raw, raw_report_graph, _report_text = validation_engine(
            data_graph=data_graph,
            shacl_graph=_recommended_action_shapes_for(action_uri),
            inference="none",
            abort_on_first=False,
            meta_shacl=False,
            advanced=True,
        )
    except Exception:
        emit_diagnostic(
            diagnostic_code=DiagnosticCode.SHACL_VALIDATION_ENGINE_ERROR,
            component=DiagnosticComponent.SHACL_VALIDATION,
            operation=DiagnosticOperation.VALIDATE_RECOMMENDED_ACTION,
            run_id=run_id,
        )
        engine_failed = True
    if engine_failed:
        raise ShaclValidationError(
            ShaclValidationErrorCode.ENGINE_ERROR, "validation_engine"
        ) from None

    if not isinstance(conforms_raw, bool) or not isinstance(raw_report_graph, Graph):
        raise ShaclValidationError(ShaclValidationErrorCode.ENGINE_ERROR, "validation_engine")

    violations = _extract_violations(raw_report_graph, report_uri)
    conforms = conforms_raw and not violations
    stable_report = _stable_report_graph(
        raw_report_graph,
        report_uri=report_uri,
        action_uri=action_uri,
        run_id=run_id,
        conforms=conforms,
        violations=violations,
    )
    return ShaclValidationResult(
        conforms=conforms,
        report_id=str(report_uri),
        violations=violations,
        report_graph=stable_report,
        stage_event=_stage_event(
            conforms=conforms,
            action_uri=action_uri,
            report_uri=report_uri,
            run_id=run_id,
        ),
        action_graph_digest=_action_graph_digest(action_graph),
    )


def _action_graph_digest(action_graph: Graph) -> str:
    return f"{to_isomorphic(action_graph).graph_digest():064x}"  # type: ignore[no-untyped-call]


def _validate_inputs(
    action_graph: object,
    action_uri: object,
    support_graph: object,
    report_uri: object,
    run_id: object,
) -> None:
    if not isinstance(action_graph, Graph):
        raise ShaclValidationError(ShaclValidationErrorCode.INVALID_INPUT, "action_graph")
    if not isinstance(action_uri, URIRef):
        raise ShaclValidationError(ShaclValidationErrorCode.INVALID_INPUT, "action_uri")
    if not isinstance(support_graph, Graph):
        raise ShaclValidationError(ShaclValidationErrorCode.INVALID_INPUT, "support_graph")
    if not isinstance(report_uri, URIRef):
        raise ShaclValidationError(ShaclValidationErrorCode.INVALID_INPUT, "report_uri")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ShaclValidationError(ShaclValidationErrorCode.INVALID_INPUT, "run_id")
    if (action_uri, RDF.type, MFG.RecommendedAction) not in action_graph:
        raise ShaclValidationError(ShaclValidationErrorCode.INVALID_INPUT, "action_uri")


def _extract_violations(report_graph: Graph, report_uri: URIRef) -> tuple[ShaclViolation, ...]:
    rows = _sorted_raw_result_rows(report_graph)
    violations: list[ShaclViolation] = []
    for index, row in enumerate(rows, start=1):
        shape_id, focus_node, message, source_constraint_component, path, _value_node, _raw_node = (
            row.sort_key
        )
        violations.append(
            ShaclViolation(
                result_node=f"{report_uri}#violation-{index}",
                shape_id=shape_id,
                focus_node=focus_node,
                message=message,
                source_constraint_component=source_constraint_component,
                path=path,
            )
        )
    return tuple(violations)


def _sorted_raw_result_rows(report_graph: Graph) -> tuple[_RawResultRow, ...]:
    rows: list[_RawResultRow] = []
    for result_node in report_graph.subjects(RDF.type, SH.ValidationResult):
        rows.append(
            _RawResultRow(
                sort_key=(
                    _one_str(report_graph, result_node, SH.sourceShape),
                    _one_str(report_graph, result_node, SH.focusNode),
                    _one_literal_str(report_graph, result_node, SH.resultMessage),
                    _optional_str(report_graph, result_node, SH.sourceConstraintComponent),
                    _optional_str(report_graph, result_node, SH.resultPath),
                    _optional_str(report_graph, result_node, SH.value),
                    str(result_node),
                ),
                result_node=result_node,
            )
        )
    return tuple(sorted(rows, key=lambda row: row.sort_key))


def _one_str(graph: Graph, subject: Node, predicate: URIRef) -> str:
    values = tuple(graph.objects(subject, predicate))
    if not values:
        return ""
    return str(values[0])


def _optional_str(graph: Graph, subject: Node, predicate: URIRef) -> str | None:
    values = tuple(graph.objects(subject, predicate))
    if not values:
        return None
    return str(values[0])


def _one_literal_str(graph: Graph, subject: Node, predicate: URIRef) -> str:
    values = tuple(graph.objects(subject, predicate))
    if not values:
        return ""
    value = values[0]
    if isinstance(value, Literal):
        return str(value)
    return str(value)


def _stable_report_graph(
    raw_report_graph: Graph,
    *,
    report_uri: URIRef,
    action_uri: URIRef,
    run_id: str,
    conforms: bool,
    violations: tuple[ShaclViolation, ...],
) -> Graph:
    graph = Graph()
    graph.bind("mfg", MFG)
    graph.bind("sh", SH)
    graph.add((report_uri, RDF.type, SH.ValidationReport))
    graph.add((report_uri, SH.conforms, Literal(conforms)))
    graph.add((report_uri, MFG.focusAction, action_uri))
    graph.add((report_uri, MFG.runId, Literal(run_id)))
    raw_rows = _sorted_raw_result_rows(raw_report_graph)
    for index, violation in enumerate(violations):
        result_node = URIRef(violation.result_node)
        graph.add((report_uri, SH.result, result_node))
        graph.add((report_uri, MFG.violation, result_node))
        graph.add((result_node, RDF.type, SH.ValidationResult))
        if index < len(raw_rows):
            raw_result_node = raw_rows[index].result_node
            for predicate in _RESULT_COPY_PREDICATES:
                for value in raw_report_graph.objects(raw_result_node, predicate):
                    graph.add((result_node, predicate, value))
        else:
            graph.add((result_node, SH.sourceShape, URIRef(violation.shape_id)))
            graph.add((result_node, SH.focusNode, URIRef(violation.focus_node)))
            graph.add((result_node, SH.resultMessage, Literal(violation.message)))
            if violation.source_constraint_component is not None:
                graph.add(
                    (
                        result_node,
                        SH.sourceConstraintComponent,
                        URIRef(violation.source_constraint_component),
                    )
                )
            if violation.path is not None:
                graph.add((result_node, SH.resultPath, URIRef(violation.path)))
    return graph


def _stage_event(
    *,
    conforms: bool,
    action_uri: URIRef,
    report_uri: URIRef,
    run_id: str,
) -> StageEvent:
    if conforms:
        return StageEvent(
            stage=StageName.SHACL_VALIDATION,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(str(action_uri),),
            output_ids=(str(report_uri),),
        )
    return StageEvent(
        stage=StageName.SHACL_VALIDATION,
        run_id=run_id,
        status=TerminalStatus.VALIDATION_FAILED_CLOSED,
        input_ids=(str(action_uri),),
        output_ids=(str(report_uri),),
        errors=(
            StageError(
                code=StageErrorCode.VALIDATION_CONSTRAINT_FAILED,
                field="shacl_report",
            ),
        ),
    )
