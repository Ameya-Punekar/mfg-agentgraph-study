"""Bounded SHACL repair policy/controller for Architecture V1 S4.

This module intentionally orchestrates only the policy boundary. The injected
callback owns any future resolver, retrieval, or regeneration work and must
return a freshly validated ``ShaclValidationResult``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from mfg_agentgraph.diagnostics import (
    DiagnosticCode,
    DiagnosticComponent,
    DiagnosticOperation,
    emit_diagnostic,
)
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import ShaclValidationResult, ShaclViolation
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

RepairAttempt = Callable[["BoundedRepairRequest"], ShaclValidationResult]


@dataclass(frozen=True, slots=True)
class BoundedRepairRequest:
    """Immutable request passed to an injected repair attempt callback."""

    attempt_index: int
    run_id: str
    action_id: str
    previous_report_id: str
    repair_class: str
    repair_intent: str
    shape_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_positive_int(self.attempt_index, "attempt_index")
        object.__setattr__(self, "run_id", _require_nonblank(self.run_id, "run_id"))
        object.__setattr__(self, "action_id", _require_nonblank(self.action_id, "action_id"))
        object.__setattr__(
            self,
            "previous_report_id",
            _require_nonblank(self.previous_report_id, "previous_report_id"),
        )
        object.__setattr__(
            self, "repair_class", _require_nonblank(self.repair_class, "repair_class")
        )
        object.__setattr__(
            self, "repair_intent", _require_nonblank(self.repair_intent, "repair_intent")
        )
        object.__setattr__(self, "shape_ids", _normalize_shape_ids(self.shape_ids))


@dataclass(frozen=True, slots=True)
class BoundedRepairOutcome:
    """Immutable controller result with aggregation-ready per-run metrics."""

    final_validation: ShaclValidationResult
    final_status: TerminalStatus
    events: tuple[StageEvent, ...]
    initial_validation_count: int = 1
    initial_failure_count: int = 0
    repair_count: int = 0
    retry_count: int = 0
    self_correction_success_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.final_validation, ShaclValidationResult):
            raise TypeError("final_validation must be a ShaclValidationResult")
        if not isinstance(self.final_status, TerminalStatus):
            raise TypeError("final_status must be a TerminalStatus")
        object.__setattr__(self, "events", _normalize_events(self.events))
        _require_exact_one(self.initial_validation_count, "initial_validation_count")
        _require_zero_or_one(self.initial_failure_count, "initial_failure_count")
        _require_nonnegative_int(self.repair_count, "repair_count")
        _require_nonnegative_int(self.retry_count, "retry_count")
        _require_zero_or_one(self.self_correction_success_count, "self_correction_success_count")


@dataclass(frozen=True, slots=True)
class _Policy:
    repair_class: str
    repair_intent: str
    fallback_status: TerminalStatus
    fallback_error_code: StageErrorCode


_TARGET_SHAPES: Final[frozenset[str]] = frozenset(
    str(MFG[name])
    for name in (
        "TargetAssetExactlyOneShape",
        "TargetAssetModeledShape",
        "TargetAssetTypeRequiredShape",
    )
)
_OBSERVATION_SHAPES: Final[frozenset[str]] = frozenset(
    str(MFG[name])
    for name in (
        "ObservationSupportRequiredShape",
        "ObservationTypedShape",
        "ObservationFeatureOfInterestRequiredShape",
        "ObservationResultTimeRequiredShape",
        "ObservationConcernsTargetShape",
        "ObservationWithinAnomalyWindowShape",
        "ActionAnomalyWindowStartRequiredShape",
        "ActionAnomalyWindowEndRequiredShape",
    )
)
_PROCEDURE_SHAPES: Final[frozenset[str]] = frozenset(
    str(MFG[name])
    for name in (
        "ProcedureSupportRequiredShape",
        "ProcedureTypedShape",
        "ProcedureApplicableAssetTypeRequiredShape",
        "ProcedureAppliesToTargetTypeShape",
    )
)
_AMBIGUOUS_FAIL_CLOSED_SHAPES: Final[frozenset[str]] = frozenset(
    str(MFG[name]) for name in ("SupportEvidenceMinCountShape", "SupportEvidenceModeledShape")
)

_POLICIES: Final[tuple[tuple[frozenset[str], _Policy], ...]] = (
    (
        _TARGET_SHAPES,
        _Policy(
            repair_class="TARGET",
            repair_intent="resolve target + regenerate",
            fallback_status=TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED,
            fallback_error_code=StageErrorCode.OPERATOR_DISAMBIGUATION_REQUIRED,
        ),
    ),
    (
        _OBSERVATION_SHAPES,
        _Policy(
            repair_class="OBSERVATION",
            repair_intent="retrieve asset/time-window graph + regenerate",
            fallback_status=TerminalStatus.INSUFFICIENT_EVIDENCE,
            fallback_error_code=StageErrorCode.INSUFFICIENT_EVIDENCE,
        ),
    ),
    (
        _PROCEDURE_SHAPES,
        _Policy(
            repair_class="PROCEDURE",
            repair_intent="ontology-filtered procedural retrieval + regenerate",
            fallback_status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
            fallback_error_code=StageErrorCode.UNSUPPORTED_LOWER_RANK,
        ),
    ),
)


def run_bounded_repair(
    initial_validation: ShaclValidationResult,
    *,
    retry_budget: int,
    repair_attempt: RepairAttempt,
) -> BoundedRepairOutcome:
    """Run deterministic bounded repair over a failed SHACL validation result."""

    if not isinstance(initial_validation, ShaclValidationResult):
        raise TypeError("initial_validation must be a ShaclValidationResult")
    _require_nonnegative_int(retry_budget, "retry_budget")
    if not callable(repair_attempt):
        raise TypeError("repair_attempt must be callable")
    structural_field = _malformed_validation_field(initial_validation)
    if structural_field is not None:
        raise ValueError(f"initial_validation {structural_field}")
    run_id, action_id = _validation_identity(initial_validation)
    identity_field = _malformed_validation_field(
        initial_validation,
        expected_run_id=run_id,
        expected_action_id=action_id,
    )
    if identity_field is not None:
        raise ValueError(f"initial_validation {identity_field}")

    if initial_validation.conforms:
        event = StageEvent(
            stage=StageName.BOUNDED_REPAIR,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            input_ids=(action_id, initial_validation.report_id),
            output_ids=(initial_validation.report_id,),
        )
        return BoundedRepairOutcome(
            final_validation=initial_validation,
            final_status=TerminalStatus.PASSED,
            events=(event,),
            initial_failure_count=0,
        )

    current = initial_validation
    seen_report_ids = {current.report_id}
    repair_count = 0
    retry_count = 0

    policy = _classify(current)
    if policy is None:
        return _fail_closed_outcome(
            initial_validation,
            final_validation=current,
            run_id=run_id,
            action_id=action_id,
            repair_count=0,
            retry_count=0,
            bounded_error=StageError(
                StageErrorCode.VALIDATION_CONSTRAINT_FAILED, field="shape_policy"
            ),
        )

    while repair_count < retry_budget:
        request = BoundedRepairRequest(
            attempt_index=repair_count + 1,
            run_id=run_id,
            action_id=action_id,
            previous_report_id=current.report_id,
            repair_class=policy.repair_class,
            repair_intent=policy.repair_intent,
            shape_ids=_shape_ids(current),
        )
        repair_count += 1
        try:
            fresh = repair_attempt(request)
        except Exception:
            emit_diagnostic(
                diagnostic_code=DiagnosticCode.BOUNDED_REPAIR_ATTEMPT_ERROR,
                component=DiagnosticComponent.BOUNDED_REPAIR,
                operation=DiagnosticOperation.REPAIR_ATTEMPT,
                run_id=run_id,
                attempt_index=repair_count,
            )
            return _repair_failure_outcome(
                initial_validation=initial_validation,
                final_validation=current,
                run_id=run_id,
                action_id=action_id,
                repair_count=repair_count,
                retry_count=retry_count,
                field="repair_attempt",
            )

        malformed_field = _malformed_validation_field(
            fresh,
            expected_run_id=run_id,
            expected_action_id=action_id,
            seen_report_ids=seen_report_ids,
        )
        if malformed_field is not None:
            return _repair_failure_outcome(
                initial_validation=initial_validation,
                final_validation=current,
                run_id=run_id,
                action_id=action_id,
                repair_count=repair_count,
                retry_count=retry_count,
                field=malformed_field,
            )

        assert isinstance(fresh, ShaclValidationResult)  # narrowed by validation above
        seen_report_ids.add(fresh.report_id)
        retry_count += 1
        if fresh.conforms:
            event = StageEvent(
                stage=StageName.BOUNDED_REPAIR,
                run_id=run_id,
                status=TerminalStatus.PASSED,
                input_ids=(action_id, initial_validation.report_id),
                output_ids=(fresh.report_id,),
                retry_count=retry_count,
                repair_count=repair_count,
            )
            return BoundedRepairOutcome(
                final_validation=fresh,
                final_status=TerminalStatus.PASSED,
                events=(event,),
                initial_failure_count=1,
                repair_count=repair_count,
                retry_count=retry_count,
                self_correction_success_count=1,
            )
        fresh_policy = _classify(fresh)
        if fresh_policy is None:
            return _fail_closed_outcome(
                initial_validation,
                final_validation=current,
                run_id=run_id,
                action_id=action_id,
                repair_count=repair_count,
                retry_count=retry_count,
                bounded_error=StageError(
                    StageErrorCode.VALIDATION_CONSTRAINT_FAILED, field="shape_policy"
                ),
            )
        current = fresh
        policy = fresh_policy

    return _exhausted_outcome(
        initial_validation=initial_validation,
        final_validation=current,
        run_id=run_id,
        action_id=action_id,
        repair_count=repair_count,
        retry_count=retry_count,
        policy=policy,
    )


def _exhausted_outcome(
    *,
    initial_validation: ShaclValidationResult,
    final_validation: ShaclValidationResult,
    run_id: str,
    action_id: str,
    repair_count: int,
    retry_count: int,
    policy: _Policy,
) -> BoundedRepairOutcome:
    error = StageError(policy.fallback_error_code, field="shacl_report")
    bounded = StageEvent(
        stage=StageName.BOUNDED_REPAIR,
        run_id=run_id,
        status=policy.fallback_status,
        input_ids=(action_id, initial_validation.report_id),
        output_ids=(final_validation.report_id,),
        errors=(error,),
        retry_count=retry_count,
        repair_count=repair_count,
    )
    fallback = StageEvent(
        stage=StageName.EXPLICIT_FALLBACK,
        run_id=run_id,
        status=policy.fallback_status,
        input_ids=(action_id, final_validation.report_id),
        output_ids=(final_validation.report_id,),
        errors=(error,),
        retry_count=retry_count,
        repair_count=repair_count,
    )
    return BoundedRepairOutcome(
        final_validation=final_validation,
        final_status=policy.fallback_status,
        events=(bounded, fallback),
        initial_failure_count=1,
        repair_count=repair_count,
        retry_count=retry_count,
    )


def _fail_closed_outcome(
    initial_validation: ShaclValidationResult,
    *,
    final_validation: ShaclValidationResult,
    run_id: str,
    action_id: str,
    repair_count: int,
    retry_count: int,
    bounded_error: StageError,
) -> BoundedRepairOutcome:
    fallback_error = StageError(StageErrorCode.VALIDATION_CONSTRAINT_FAILED, field="shacl_report")
    bounded = StageEvent(
        stage=StageName.BOUNDED_REPAIR,
        run_id=run_id,
        status=TerminalStatus.VALIDATION_FAILED_CLOSED,
        input_ids=(action_id, initial_validation.report_id),
        output_ids=(final_validation.report_id,),
        errors=(bounded_error,),
        retry_count=retry_count,
        repair_count=repair_count,
    )
    fallback = StageEvent(
        stage=StageName.EXPLICIT_FALLBACK,
        run_id=run_id,
        status=TerminalStatus.VALIDATION_FAILED_CLOSED,
        input_ids=(action_id, final_validation.report_id),
        output_ids=(final_validation.report_id,),
        errors=(fallback_error,),
        retry_count=retry_count,
        repair_count=repair_count,
    )
    return BoundedRepairOutcome(
        final_validation=final_validation,
        final_status=TerminalStatus.VALIDATION_FAILED_CLOSED,
        events=(bounded, fallback),
        initial_failure_count=1,
        repair_count=repair_count,
        retry_count=retry_count,
    )


def _repair_failure_outcome(
    *,
    initial_validation: ShaclValidationResult,
    final_validation: ShaclValidationResult,
    run_id: str,
    action_id: str,
    repair_count: int,
    retry_count: int,
    field: str,
) -> BoundedRepairOutcome:
    return _fail_closed_outcome(
        initial_validation,
        final_validation=final_validation,
        run_id=run_id,
        action_id=action_id,
        repair_count=repair_count,
        retry_count=retry_count,
        bounded_error=StageError(StageErrorCode.REPAIR_ATTEMPT_FAILED, field=field),
    )


def _classify(validation: ShaclValidationResult) -> _Policy | None:
    shapes = frozenset(_shape_ids(validation))
    if not shapes:
        return None
    if shapes <= _AMBIGUOUS_FAIL_CLOSED_SHAPES:
        return None
    matches: list[_Policy] = []
    for known_shapes, policy in _POLICIES:
        if shapes <= known_shapes:
            matches.append(policy)
    if len(matches) != 1:
        return None
    return matches[0]


def _shape_ids(validation: ShaclValidationResult) -> tuple[str, ...]:
    return tuple(sorted({violation.shape_id for violation in validation.violations}))


def _validation_identity(validation: ShaclValidationResult) -> tuple[str, str]:
    event = validation.stage_event
    if event.stage is not StageName.SHACL_VALIDATION:
        raise ValueError("initial_validation stage_event must be SHACL_VALIDATION")
    if len(event.input_ids) != 1:
        raise ValueError("initial_validation.stage_event.input_ids must equal (action_id,)")
    if tuple(event.output_ids) != (validation.report_id,):
        raise ValueError("initial_validation stage_event output_ids must equal report_id")
    if not _report_identity_matches(validation, event.run_id, event.input_ids[0]):
        raise ValueError("initial_validation report_graph must match stage identity")
    return event.run_id, event.input_ids[0]


def _malformed_validation_field(
    fresh: object,
    *,
    expected_run_id: str | None = None,
    expected_action_id: str | None = None,
    seen_report_ids: set[str] | None = None,
) -> str | None:
    if not isinstance(fresh, ShaclValidationResult):
        return "repair_attempt"
    if type(fresh.conforms) is not bool:
        return "conforms"
    if not isinstance(fresh.report_id, str) or not fresh.report_id.strip():
        return "report_id"
    if seen_report_ids is not None and fresh.report_id in seen_report_ids:
        return "report_id"
    if not isinstance(fresh.violations, tuple):
        return "violations"
    if any(not _valid_violation(violation) for violation in fresh.violations):
        return "violations"
    if fresh.conforms is (len(fresh.violations) > 0):
        return "conforms"
    if not isinstance(fresh.report_graph, Graph):
        return "report_graph"
    event = fresh.stage_event
    if not isinstance(event, StageEvent):
        return "stage_event"
    if event.stage is not StageName.SHACL_VALIDATION:
        return "stage_event"
    expected_status = (
        TerminalStatus.PASSED if fresh.conforms else TerminalStatus.VALIDATION_FAILED_CLOSED
    )
    if event.status is not expected_status:
        return "stage_event"
    if expected_run_id is None or expected_action_id is None:
        return None
    if event.run_id != expected_run_id:
        return "run_id"
    if tuple(event.input_ids) != (expected_action_id,):
        return "action_id"
    if any(violation.focus_node != expected_action_id for violation in fresh.violations):
        return "violations"
    if tuple(event.output_ids) != (fresh.report_id,):
        return "report_id"
    if not _report_graph_matches(fresh, expected_run_id, expected_action_id):
        return "report_graph"
    return None


def _valid_violation(violation: object) -> bool:
    if not isinstance(violation, ShaclViolation):
        return False
    required_values = (
        violation.result_node,
        violation.shape_id,
        violation.focus_node,
        violation.message,
    )
    if any(not isinstance(value, str) or not value.strip() for value in required_values):
        return False
    optional_values = (violation.source_constraint_component, violation.path)
    return all(
        value is None or (isinstance(value, str) and bool(value.strip()))
        for value in optional_values
    )


def _report_graph_matches(
    validation: ShaclValidationResult, expected_run_id: str, expected_action_id: str
) -> bool:
    try:
        if not _report_identity_matches(validation, expected_run_id, expected_action_id):
            return False
        return _report_result_nodes_match(validation, URIRef(validation.report_id))
    except Exception:
        return False


def _report_identity_matches(
    validation: ShaclValidationResult, expected_run_id: str, expected_action_id: str
) -> bool:
    report_uri = URIRef(validation.report_id)
    action_uri = URIRef(expected_action_id)
    run_id_literal = Literal(expected_run_id)
    try:
        report_types = tuple(validation.report_graph.objects(report_uri, RDF.type))
        conforms_values = tuple(validation.report_graph.objects(report_uri, SH.conforms))
        focus_actions = tuple(validation.report_graph.objects(report_uri, MFG.focusAction))
        run_ids = tuple(validation.report_graph.objects(report_uri, MFG.runId))
        if report_types != (SH.ValidationReport,):
            return False
        if len(conforms_values) != 1 or type(conforms_values[0]) is not Literal:
            return False
        conforms_value = conforms_values[0].toPython()
        if type(conforms_value) is not type(validation.conforms):
            return False
        return (
            conforms_value == validation.conforms
            and focus_actions == (action_uri,)
            and run_ids == (run_id_literal,)
        )
    except Exception:
        return False


def _report_result_nodes_match(validation: ShaclValidationResult, report_uri: URIRef) -> bool:
    result_node_values = tuple(URIRef(violation.result_node) for violation in validation.violations)
    result_nodes = frozenset(result_node_values)
    sh_result_values = tuple(validation.report_graph.objects(report_uri, SH.result))
    mfg_violation_values = tuple(validation.report_graph.objects(report_uri, MFG.violation))
    typed_result_values = tuple(validation.report_graph.subjects(RDF.type, SH.ValidationResult))
    if len(result_nodes) != len(result_node_values):
        return False
    if len(sh_result_values) != len(result_nodes) or len(mfg_violation_values) != len(result_nodes):
        return False
    if len(typed_result_values) != len(result_nodes):
        return False
    if frozenset(typed_result_values) != result_nodes:
        return False
    if (
        frozenset(sh_result_values) != result_nodes
        or frozenset(mfg_violation_values) != result_nodes
    ):
        return False
    return all(
        _result_node_matches_violation(validation, violation) for violation in validation.violations
    )


def _result_node_matches_violation(
    validation: ShaclValidationResult, violation: ShaclViolation
) -> bool:
    result_node = URIRef(violation.result_node)
    graph = validation.report_graph
    expected_predicates = {
        RDF.type,
        SH.sourceShape,
        SH.focusNode,
        SH.resultMessage,
    }
    if violation.source_constraint_component is not None:
        expected_predicates.add(SH.sourceConstraintComponent)
    if violation.path is not None:
        expected_predicates.add(SH.resultPath)
    predicate_values = tuple(graph.predicates(result_node))
    if len(predicate_values) != len(expected_predicates):
        return False
    if frozenset(predicate_values) != frozenset(expected_predicates):
        return False
    return (
        tuple(graph.objects(result_node, RDF.type)) == (SH.ValidationResult,)
        and tuple(graph.objects(result_node, SH.sourceShape)) == (URIRef(violation.shape_id),)
        and tuple(graph.objects(result_node, SH.focusNode)) == (URIRef(violation.focus_node),)
        and tuple(graph.objects(result_node, SH.resultMessage)) == (Literal(violation.message),)
        and _optional_uri_objects_match(
            validation,
            result_node,
            SH.sourceConstraintComponent,
            violation.source_constraint_component,
        )
        and _optional_uri_objects_match(validation, result_node, SH.resultPath, violation.path)
    )


def _optional_uri_objects_match(
    validation: ShaclValidationResult,
    subject: URIRef,
    predicate: URIRef,
    expected_value: str | None,
) -> bool:
    objects = tuple(validation.report_graph.objects(subject, predicate))
    if expected_value is None:
        return objects == ()
    return objects == (URIRef(expected_value),)


def _normalize_shape_ids(shape_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(shape_ids, str):
        raise TypeError("shape_ids must be a sequence of strings")
    normalized: list[str] = []
    for shape_id in shape_ids:
        normalized.append(_require_nonblank(shape_id, "shape_ids"))
    return tuple(normalized)


def _normalize_events(events: Sequence[StageEvent]) -> tuple[StageEvent, ...]:
    if isinstance(events, str):
        raise TypeError("events must be a sequence of StageEvent instances")
    normalized: list[StageEvent] = []
    for event in events:
        if not isinstance(event, StageEvent):
            raise TypeError("events must contain StageEvent instances")
        normalized.append(event)
    return tuple(normalized)


def _require_nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be nonblank")
    return stripped


def _require_nonnegative_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")


def _require_positive_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_zero_or_one(value: object, field_name: str) -> None:
    _require_nonnegative_int(value, field_name)
    if value not in (0, 1):
        raise ValueError(f"{field_name} must be 0 or 1")


def _require_exact_one(value: object, field_name: str) -> None:
    _require_nonnegative_int(value, field_name)
    if value != 1:
        raise ValueError(f"{field_name} must be 1")
