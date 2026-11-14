from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from typing import NoReturn, cast

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SH, XSD

from mfg_agentgraph.bounded_repair import BoundedRepairRequest, RepairAttempt
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import (
    ShaclValidationResult,
    ShaclViolation,
    validate_recommended_action,
)
from mfg_agentgraph.stage_instrumentation import (
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

EX = Namespace("http://example.org/")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
ACTION = EX.CandidateAction_Pump12_Repaired_001
ASSET = EX.Pump_12
KG_EVIDENCE = EX.KgEvidence_Pump12_001
DOC_EVIDENCE = EX.DocumentEvidence_Pump12_001
OBSERVATION = EX.Observation_Pump12_001
PROCEDURE = EX.Procedure_Pump12_001
RUN_ID = "run-issue-20-pump-12"
SENSITIVE_EXTRA_OUTPUT_ID = "http://example.org/SECRET_EXTRA_OUTPUT_SHOULD_NOT_LEAK"

TARGET_POLICY_SHAPES = (
    "TargetAssetExactlyOneShape",
    "TargetAssetModeledShape",
    "TargetAssetTypeRequiredShape",
)
OBSERVATION_POLICY_SHAPES = (
    "ObservationSupportRequiredShape",
    "ObservationTypedShape",
    "ObservationFeatureOfInterestRequiredShape",
    "ObservationResultTimeRequiredShape",
    "ObservationConcernsTargetShape",
    "ObservationWithinAnomalyWindowShape",
    "ActionAnomalyWindowStartRequiredShape",
    "ActionAnomalyWindowEndRequiredShape",
)
PROCEDURE_POLICY_SHAPES = (
    "ProcedureSupportRequiredShape",
    "ProcedureTypedShape",
    "ProcedureApplicableAssetTypeRequiredShape",
    "ProcedureAppliesToTargetTypeShape",
)
GENERIC_SUPPORT_FAIL_CLOSED_SHAPES = (
    "SupportEvidenceMinCountShape",
    "SupportEvidenceModeledShape",
)


def _dt(value: str) -> Literal:
    return Literal(value, datatype=XSD.dateTime)


def _action_graph() -> Graph:
    graph = Graph()
    graph.bind("mfg", MFG)
    graph.bind("ex", EX)
    graph.add((ACTION, RDF.type, MFG.RecommendedAction))
    graph.add((ACTION, MFG.targetAsset, ASSET))
    graph.add((ACTION, MFG.hasSupportEvidence, KG_EVIDENCE))
    graph.add((ACTION, MFG.hasSupportEvidence, DOC_EVIDENCE))
    return graph


def _support_graph() -> Graph:
    graph = Graph()
    graph.bind("mfg", MFG)
    graph.bind("sosa", SOSA)
    graph.bind("ex", EX)
    graph.add((ASSET, RDF.type, MFG.Asset))
    graph.add((ASSET, MFG.assetType, MFG.CentrifugalPump))
    graph.add((KG_EVIDENCE, RDF.type, MFG.SupportEvidence))
    graph.add((KG_EVIDENCE, MFG.observation, OBSERVATION))
    graph.add((DOC_EVIDENCE, RDF.type, MFG.SupportEvidence))
    graph.add((DOC_EVIDENCE, MFG.procedure, PROCEDURE))
    graph.add((OBSERVATION, RDF.type, SOSA.Observation))
    graph.add((OBSERVATION, SOSA.hasFeatureOfInterest, ASSET))
    graph.add((OBSERVATION, SOSA.resultTime, _dt("2026-05-18T14:03:00Z")))
    graph.add((PROCEDURE, RDF.type, MFG.Procedure))
    graph.add((PROCEDURE, MFG.applicableAssetType, MFG.CentrifugalPump))
    graph.add((ACTION, MFG.anomalyWindowStart, _dt("2026-05-18T14:00:00Z")))
    graph.add((ACTION, MFG.anomalyWindowEnd, _dt("2026-05-18T14:10:00Z")))
    return graph


def _validate(
    action_graph: Graph, support_graph: Graph, report_suffix: str
) -> ShaclValidationResult:
    return validate_recommended_action(
        action_graph,
        action_uri=ACTION,
        support_graph=support_graph,
        report_uri=EX[f"ValidationReport_Pump12_{report_suffix}"],
        run_id=RUN_ID,
    )


def _failing_result(variant: str, report_suffix: str = "initial") -> ShaclValidationResult:
    action_graph = _action_graph()
    support_graph = _support_graph()
    if variant == "target":
        action_graph.remove((ACTION, MFG.targetAsset, None))
    elif variant == "observation":
        support_graph.remove((OBSERVATION, SOSA.resultTime, None))
    elif variant == "procedure":
        support_graph.remove((PROCEDURE, MFG.applicableAssetType, None))
    elif variant == "generic_support":
        action_graph.remove((ACTION, MFG.hasSupportEvidence, None))
    elif variant == "cross_class":
        action_graph.remove((ACTION, MFG.targetAsset, None))
        support_graph.remove((OBSERVATION, SOSA.resultTime, None))
    else:
        raise AssertionError(variant)
    result = _validate(action_graph, support_graph, report_suffix)
    assert result.conforms is False
    return result


def _passing_result(report_suffix: str) -> ShaclValidationResult:
    result = _validate(_action_graph(), _support_graph(), report_suffix)
    assert result.conforms is True
    return result


def _unknown_shape_result(report_suffix: str = "unknown-base") -> ShaclValidationResult:
    return _synthetic_validation_result(
        shape_id=str(MFG.UnknownFutureShape), report_suffix=report_suffix
    )


def _assert_marker_absent(marker: str, value: object) -> None:
    assert marker not in repr(value)
    assert marker not in str(value)


class _HostileObjectsGraph(Graph):
    def __init__(self, marker: str) -> None:
        super().__init__()
        self._marker = marker

    def objects(self, subject: object = None, predicate: object = None, unique: bool = False):  # type: ignore[no-untyped-def]
        raise RuntimeError(self._marker)


class _HostileConformsLiteral(Literal):
    _marker: str

    def __new__(cls, value: bool, marker: str) -> _HostileConformsLiteral:
        instance = cast(_HostileConformsLiteral, super().__new__(cls, value))
        instance._marker = marker
        return instance

    def toPython(self) -> NoReturn:
        raise RuntimeError(self._marker)


def _unexpected_repair(_request: BoundedRepairRequest) -> NoReturn:
    raise AssertionError("repair callback must not be invoked")


def _synthetic_validation_result(
    *,
    shape_id: str,
    report_suffix: str,
    conforms: bool = False,
    run_id: str = RUN_ID,
    action_id: str = str(ACTION),
) -> ShaclValidationResult:
    report_uri = EX[f"ValidationReport_Pump12_{report_suffix}"]
    report_id = str(report_uri)
    action_uri = URIRef(action_id)
    report_graph = Graph()
    report_graph.add((report_uri, RDF.type, SH.ValidationReport))
    report_graph.add((report_uri, SH.conforms, Literal(conforms)))
    report_graph.add((report_uri, MFG.focusAction, action_uri))
    report_graph.add((report_uri, MFG.runId, Literal(run_id)))
    violations: tuple[ShaclViolation, ...] = ()
    status = TerminalStatus.PASSED
    if not conforms:
        violations = (
            ShaclViolation(
                result_node=f"{report_id}#violation-1",
                shape_id=shape_id,
                focus_node=action_id,
                message="synthetic coherent violation for exhaustive policy coverage",
            ),
        )
        status = TerminalStatus.VALIDATION_FAILED_CLOSED
        result_node = URIRef(violations[0].result_node)
        report_graph.add((report_uri, SH.result, result_node))
        report_graph.add((report_uri, MFG.violation, result_node))
        report_graph.add((result_node, RDF.type, SH.ValidationResult))
        report_graph.add((result_node, SH.sourceShape, URIRef(shape_id)))
        report_graph.add((result_node, SH.focusNode, action_uri))
        report_graph.add((result_node, SH.resultMessage, Literal(violations[0].message)))
    return ShaclValidationResult(
        conforms=conforms,
        report_id=report_id,
        violations=violations,
        report_graph=report_graph,
        stage_event=StageEvent(
            stage=StageName.SHACL_VALIDATION,
            run_id=run_id,
            status=status,
            input_ids=(action_id,),
            output_ids=(report_id,),
        ),
    )


def _with_rebuilt_report_results(
    result: ShaclValidationResult, violations: tuple[ShaclViolation, ...]
) -> ShaclValidationResult:
    report_uri = URIRef(result.report_id)
    report_graph = Graph()
    for triple in result.report_graph:
        report_graph.add(triple)
    report_graph.remove((report_uri, SH.result, None))
    report_graph.remove((report_uri, MFG.violation, None))
    for violation in result.violations:
        old_result_node = URIRef(violation.result_node)
        report_graph.remove((old_result_node, None, None))
    for violation in violations:
        result_node = URIRef(violation.result_node)
        report_graph.add((report_uri, SH.result, result_node))
        report_graph.add((report_uri, MFG.violation, result_node))
        report_graph.add((result_node, RDF.type, SH.ValidationResult))
        report_graph.add((result_node, SH.sourceShape, URIRef(violation.shape_id)))
        report_graph.add((result_node, SH.focusNode, URIRef(violation.focus_node)))
        report_graph.add((result_node, SH.resultMessage, Literal(violation.message)))
        if violation.source_constraint_component is not None:
            report_graph.add(
                (
                    result_node,
                    SH.sourceConstraintComponent,
                    URIRef(violation.source_constraint_component),
                )
            )
        if violation.path is not None:
            report_graph.add((result_node, SH.resultPath, URIRef(violation.path)))
    return replace(result, violations=violations, report_graph=report_graph)


def test_conforming_initial_result_is_noop_and_exposes_metrics() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _passing_result("initial")
    outcome = run_bounded_repair(initial, retry_budget=3, repair_attempt=_unexpected_repair)
    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.PASSED
    assert outcome.initial_validation_count == 1
    assert outcome.initial_failure_count == 0
    assert outcome.repair_count == 0
    assert outcome.retry_count == 0
    assert outcome.self_correction_success_count == 0
    assert tuple(event.stage for event in outcome.events) == (StageName.BOUNDED_REPAIR,)
    assert outcome.events[0].status is TerminalStatus.PASSED


@pytest.mark.parametrize(
    ("variant", "repair_class", "intent"),
    [
        ("target", "TARGET", "resolve target + regenerate"),
        ("observation", "OBSERVATION", "retrieve asset/time-window graph + regenerate"),
        ("procedure", "PROCEDURE", "ontology-filtered procedural retrieval + regenerate"),
    ],
)
def test_each_repair_class_invokes_callback_with_immutable_request_and_stops_on_success(
    variant: str, repair_class: str, intent: str
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result(variant)
    seen: list[BoundedRepairRequest] = []

    def repair(request: BoundedRepairRequest) -> ShaclValidationResult:
        seen.append(request)
        with pytest.raises(FrozenInstanceError):
            request.attempt_index = 99  # type: ignore[misc]
        return _passing_result("attempt-1")

    outcome = run_bounded_repair(initial, retry_budget=2, repair_attempt=repair)

    assert len(seen) == 1
    assert seen[0].attempt_index == 1
    assert seen[0].run_id == RUN_ID
    assert seen[0].action_id == str(ACTION)
    assert seen[0].previous_report_id == initial.report_id
    assert seen[0].repair_class == repair_class
    assert seen[0].repair_intent == intent
    assert seen[0].shape_ids == tuple(sorted(set(v.shape_id for v in initial.violations)))
    assert outcome.final_validation.conforms is True
    assert outcome.final_status is TerminalStatus.PASSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 1
    assert outcome.self_correction_success_count == 1
    assert outcome.events == (
        StageEvent(
            stage=StageName.BOUNDED_REPAIR,
            run_id=RUN_ID,
            status=TerminalStatus.PASSED,
            input_ids=(str(ACTION), initial.report_id),
            output_ids=(outcome.final_validation.report_id,),
            retry_count=1,
            repair_count=1,
        ),
    )


def test_same_class_bundles_are_deduplicated_and_sorted_in_one_request() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("observation")
    shuffled_violations = (
        ShaclViolation(
            f"{initial.report_id}#synthetic-node-3",
            str(MFG.ObservationTypedShape),
            str(ACTION),
            "typed",
        ),
        initial.violations[0],
        ShaclViolation(
            f"{initial.report_id}#synthetic-node-2",
            str(MFG.ObservationTypedShape),
            str(ACTION),
            "typed duplicate",
        ),
    )
    shuffled = _with_rebuilt_report_results(initial, shuffled_violations)
    requests: list[BoundedRepairRequest] = []

    def repair(request: BoundedRepairRequest) -> ShaclValidationResult:
        requests.append(request)
        return _passing_result("attempt-1")

    outcome = run_bounded_repair(
        shuffled,
        retry_budget=1,
        repair_attempt=repair,
    )

    assert outcome.final_status is TerminalStatus.PASSED
    assert len(requests) == 1
    assert requests[0].shape_ids == tuple(sorted({v.shape_id for v in shuffled.violations}))


@pytest.mark.parametrize(
    ("retry_budget", "expected_calls", "expected_status"),
    [
        (0, 0, TerminalStatus.INSUFFICIENT_EVIDENCE),
        (1, 1, TerminalStatus.INSUFFICIENT_EVIDENCE),
        (2, 2, TerminalStatus.INSUFFICIENT_EVIDENCE),
    ],
)
def test_retry_budget_exactly_bounds_attempts_and_exhaustion_uses_policy_fallback(
    retry_budget: int, expected_calls: int, expected_status: TerminalStatus
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    attempts: list[int] = []

    def still_failing(request: BoundedRepairRequest) -> ShaclValidationResult:
        attempts.append(request.attempt_index)
        return _failing_result("observation", f"attempt-{request.attempt_index}")

    outcome = run_bounded_repair(
        _failing_result("observation"), retry_budget=retry_budget, repair_attempt=still_failing
    )

    assert attempts == list(range(1, expected_calls + 1))
    assert outcome.repair_count == expected_calls
    assert outcome.retry_count == expected_calls
    assert outcome.self_correction_success_count == 0
    assert outcome.final_status is expected_status
    assert outcome.events[-1].stage is StageName.EXPLICIT_FALLBACK
    assert outcome.events[-1].status is expected_status
    assert outcome.events[-1].errors[0].code is StageErrorCode.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    ("variant", "expected_status", "expected_error_code"),
    [
        (
            "target",
            TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED,
            StageErrorCode.OPERATOR_DISAMBIGUATION_REQUIRED,
        ),
        (
            "observation",
            TerminalStatus.INSUFFICIENT_EVIDENCE,
            StageErrorCode.INSUFFICIENT_EVIDENCE,
        ),
        (
            "procedure",
            TerminalStatus.UNSUPPORTED_LOWER_RANK,
            StageErrorCode.UNSUPPORTED_LOWER_RANK,
        ),
    ],
)
def test_direct_exhaustion_uses_class_specific_terminal_status_and_error_code(
    variant: str, expected_status: TerminalStatus, expected_error_code: StageErrorCode
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    attempts: list[int] = []

    def still_failing(request: BoundedRepairRequest) -> ShaclValidationResult:
        attempts.append(request.attempt_index)
        return _failing_result(variant, f"attempt-{request.attempt_index}")

    outcome = run_bounded_repair(
        _failing_result(variant), retry_budget=2, repair_attempt=still_failing
    )

    assert attempts == [1, 2]
    assert outcome.repair_count == 2
    assert outcome.retry_count == 2
    assert outcome.self_correction_success_count == 0
    assert outcome.final_status is expected_status
    assert tuple(event.status for event in outcome.events) == (expected_status, expected_status)
    assert tuple(event.errors[0].code for event in outcome.events) == (
        expected_error_code,
        expected_error_code,
    )


@pytest.mark.parametrize(
    ("initial", "expected_shapes"),
    [
        (_failing_result("generic_support"), (str(MFG.SupportEvidenceMinCountShape),)),
        (_unknown_shape_result(), (str(MFG.UnknownFutureShape),)),
        (_failing_result("cross_class"), None),
    ],
)
def test_generic_unknown_and_cross_class_fail_closed_without_callback(
    initial: ShaclValidationResult, expected_shapes: tuple[str, ...] | None
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    outcome = run_bounded_repair(
        initial,
        retry_budget=2,
        repair_attempt=_unexpected_repair,
    )
    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.initial_failure_count == 1
    assert outcome.events == (
        StageEvent(
            stage=StageName.BOUNDED_REPAIR,
            run_id=RUN_ID,
            status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            input_ids=(str(ACTION), initial.report_id),
            output_ids=(initial.report_id,),
            errors=outcome.events[0].errors,
        ),
        StageEvent(
            stage=StageName.EXPLICIT_FALLBACK,
            run_id=RUN_ID,
            status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            input_ids=(str(ACTION), initial.report_id),
            output_ids=(initial.report_id,),
            errors=outcome.events[1].errors,
        ),
    )
    assert outcome.events[0].errors[0].code is StageErrorCode.VALIDATION_CONSTRAINT_FAILED
    if expected_shapes is not None:
        assert tuple(v.shape_id for v in initial.violations) == expected_shapes


@pytest.mark.parametrize(
    ("shape_name", "expected_class", "expected_intent"),
    [
        *[(name, "TARGET", "resolve target + regenerate") for name in TARGET_POLICY_SHAPES],
        *[
            (name, "OBSERVATION", "retrieve asset/time-window graph + regenerate")
            for name in OBSERVATION_POLICY_SHAPES
        ],
        *[
            (name, "PROCEDURE", "ontology-filtered procedural retrieval + regenerate")
            for name in PROCEDURE_POLICY_SHAPES
        ],
    ],
)
def test_every_actionable_source_shape_id_routes_to_policy_contract(
    shape_name: str, expected_class: str, expected_intent: str
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    requests: list[BoundedRepairRequest] = []
    initial = _synthetic_validation_result(
        shape_id=str(MFG[shape_name]), report_suffix=f"initial_{shape_name}"
    )

    def repair(request: BoundedRepairRequest) -> ShaclValidationResult:
        requests.append(request)
        return _synthetic_validation_result(
            shape_id=str(MFG[shape_name]),
            report_suffix=f"attempt_{shape_name}",
            conforms=True,
        )

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=repair)

    assert outcome.final_status is TerminalStatus.PASSED
    assert len(requests) == 1
    assert requests[0].repair_class == expected_class
    assert requests[0].repair_intent == expected_intent
    assert requests[0].shape_ids == (str(MFG[shape_name]),)


@pytest.mark.parametrize("shape_name", GENERIC_SUPPORT_FAIL_CLOSED_SHAPES)
def test_every_generic_support_shape_fails_closed_without_repair_callback(shape_name: str) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _synthetic_validation_result(
        shape_id=str(MFG[shape_name]), report_suffix=f"initial_{shape_name}"
    )
    outcome = run_bounded_repair(
        initial,
        retry_budget=1,
        repair_attempt=_unexpected_repair,
    )
    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.events[0].errors[0].code is StageErrorCode.VALIDATION_CONSTRAINT_FAILED


def test_root_recommended_action_shape_is_delegate_not_report_source_shape() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _synthetic_validation_result(
        shape_id=str(MFG.RecommendedActionShape), report_suffix="root_delegate"
    )

    outcome = run_bounded_repair(
        initial,
        retry_budget=1,
        repair_attempt=_unexpected_repair,
    )
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.events[0].errors[0].code is StageErrorCode.VALIDATION_CONSTRAINT_FAILED


@pytest.mark.parametrize(
    ("replacement", "field"),
    [
        (lambda fresh: True, "repair_attempt"),
        (lambda fresh: replace(fresh, report_id=EX.ValidationReport_Pump12_initial), "report_id"),
        (lambda fresh: replace(fresh, report_id=_failing_result("target").report_id), "report_id"),
        (
            lambda fresh: replace(
                fresh,
                stage_event=replace(fresh.stage_event, run_id="different-run"),
            ),
            "run_id",
        ),
        (
            lambda fresh: replace(
                fresh,
                stage_event=replace(fresh.stage_event, input_ids=(str(EX.OtherAction),)),
            ),
            "action_id",
        ),
        (
            lambda fresh: replace(
                fresh,
                stage_event=replace(fresh.stage_event, stage=StageName.BOUNDED_REPAIR),
            ),
            "stage_event",
        ),
    ],
)
def test_callback_must_return_fresh_consistent_validation_result(
    replacement: Callable[[ShaclValidationResult], object], field: str
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    def malformed(_request: BoundedRepairRequest) -> object:
        return replacement(_passing_result("attempt-1"))

    outcome = run_bounded_repair(
        _failing_result("target"),
        retry_budget=1,
        repair_attempt=cast(RepairAttempt, malformed),
    )

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.self_correction_success_count == 0
    assert outcome.events[0].stage is StageName.BOUNDED_REPAIR
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == field
    assert outcome.events[-1].stage is StageName.EXPLICIT_FALLBACK


def test_callback_reusing_initial_report_id_string_fails_closed() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        return replace(fresh, report_id=initial.report_id)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_id"


def test_callback_report_graph_focus_identity_drift_fails_closed() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        drifted_graph = Graph()
        for triple in fresh.report_graph:
            drifted_graph.add(triple)
        report_uri = URIRef(fresh.report_id)
        drifted_graph.remove((report_uri, MFG.focusAction, None))
        drifted_graph.add((report_uri, MFG.focusAction, EX.OtherAction))
        return replace(fresh, report_graph=drifted_graph)

    outcome = run_bounded_repair(
        _failing_result("target"), retry_budget=1, repair_attempt=malformed
    )

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"


def test_callback_report_graph_additive_focus_identity_conflict_fails_closed_without_marker() -> (
    None
):
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_EXTRA_FOCUS_ACTION_SHOULD_NOT_LEAK"

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        conflicting_graph = Graph()
        for triple in fresh.report_graph:
            conflicting_graph.add(triple)
        conflicting_graph.add(
            (URIRef(fresh.report_id), MFG.focusAction, URIRef(f"http://example.org/{marker}"))
        )
        return replace(fresh, report_graph=conflicting_graph)

    initial = _failing_result("target")
    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    assert marker not in repr(outcome)
    assert marker not in str(outcome.events)


def test_initial_report_graph_additive_focus_identity_conflict_is_rejected_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_EXTRA_FOCUS_ACTION_SHOULD_NOT_LEAK"
    initial = _failing_result("target")
    conflicting_graph = Graph()
    for triple in initial.report_graph:
        conflicting_graph.add(triple)
    conflicting_graph.add(
        (URIRef(initial.report_id), MFG.focusAction, URIRef(f"http://example.org/{marker}"))
    )
    malformed = replace(initial, report_graph=conflicting_graph)

    with pytest.raises(ValueError) as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("attempt-1"),
        )

    assert "report_graph" in str(exc_info.value)
    assert marker not in str(exc_info.value)
    assert marker not in repr(exc_info.value)


def test_initial_violation_focus_identity_drift_is_rejected_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_FOREIGN_FOCUS_SHOULD_NOT_LEAK"
    initial = _failing_result("target")
    malformed = replace(
        initial,
        violations=(
            replace(initial.violations[0], focus_node=f"http://example.org/{marker}"),
            *initial.violations[1:],
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("attempt-1"),
        )

    assert exc_info.value.__cause__ is None
    assert "violations" in str(exc_info.value)
    _assert_marker_absent(marker, exc_info.value)


def test_callback_violation_focus_identity_drift_fails_closed_without_retaining_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_CALLBACK_FOREIGN_FOCUS_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _failing_result("target", "attempt-1")
        return replace(
            fresh,
            violations=(
                replace(fresh.violations[0], focus_node=f"http://example.org/{marker}"),
                *fresh.violations[1:],
            ),
        )

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "violations"
    _assert_marker_absent(marker, outcome)


@pytest.mark.parametrize("predicate", [SH.result, MFG.violation])
def test_callback_violation_result_links_must_exactly_match_violations(
    predicate: URIRef,
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _failing_result("target", "attempt-1")
        mismatched_graph = Graph()
        for triple in fresh.report_graph:
            mismatched_graph.add(triple)
        mismatched_graph.remove(
            (URIRef(fresh.report_id), predicate, URIRef(fresh.violations[0].result_node))
        )
        return replace(fresh, report_graph=mismatched_graph)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"


def test_callback_violation_result_triples_must_exactly_match_violations() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_CALLBACK_RESULT_MESSAGE_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _failing_result("target", "attempt-1")
        mismatched_graph = Graph()
        for triple in fresh.report_graph:
            mismatched_graph.add(triple)
        result_node = URIRef(fresh.violations[0].result_node)
        mismatched_graph.remove((result_node, SH.resultMessage, None))
        mismatched_graph.add((result_node, SH.resultMessage, Literal(marker)))
        return replace(fresh, report_graph=mismatched_graph)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    _assert_marker_absent(marker, outcome)


def test_initial_duplicate_violation_result_identity_is_rejected() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("target")
    malformed = _with_rebuilt_report_results(
        initial,
        (initial.violations[0], initial.violations[0]),
    )

    with pytest.raises(ValueError, match="report_graph"):
        run_bounded_repair(
            malformed,
            retry_budget=0,
            repair_attempt=_unexpected_repair,
        )


def test_callback_duplicate_violation_result_identity_fails_closed() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _failing_result("target", "attempt-1")
        return _with_rebuilt_report_results(
            fresh,
            (fresh.violations[0], fresh.violations[0]),
        )

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"


def _with_hidden_validation_result(
    result: ShaclValidationResult,
    marker: str,
) -> ShaclValidationResult:
    report_graph = Graph()
    for triple in result.report_graph:
        report_graph.add(triple)
    hidden = URIRef(f"{result.report_id}#hidden-{marker}")
    report_graph.add((hidden, RDF.type, SH.ValidationResult))
    report_graph.add((hidden, SH.sourceShape, MFG.UnknownFutureShape))
    report_graph.add((hidden, SH.focusNode, EX.OtherAction))
    report_graph.add((hidden, SH.resultMessage, Literal(marker)))
    return replace(result, report_graph=report_graph)


def test_initial_unlinked_validation_result_is_rejected_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_UNLINKED_RESULT_SHOULD_NOT_LEAK"
    malformed = _with_hidden_validation_result(_passing_result("initial-hidden"), marker)

    with pytest.raises(ValueError, match="report_graph") as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=0,
            repair_attempt=_unexpected_repair,
        )

    _assert_marker_absent(marker, exc_info.value)


def test_callback_unlinked_validation_result_fails_closed_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_CALLBACK_UNLINKED_RESULT_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        return _with_hidden_validation_result(_passing_result("attempt-hidden"), marker)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    _assert_marker_absent(marker, outcome)


def _with_extra_result_value(
    result: ShaclValidationResult,
    marker: str,
) -> ShaclValidationResult:
    report_graph = Graph()
    for triple in result.report_graph:
        report_graph.add(triple)
    report_graph.add((URIRef(result.violations[0].result_node), SH.value, Literal(marker)))
    return replace(result, report_graph=report_graph)


def test_initial_extra_result_node_triple_is_rejected_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_EXTRA_RESULT_VALUE_SHOULD_NOT_LEAK"
    malformed = _with_extra_result_value(_failing_result("target"), marker)

    with pytest.raises(ValueError, match="report_graph") as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=0,
            repair_attempt=_unexpected_repair,
        )

    _assert_marker_absent(marker, exc_info.value)


def test_callback_extra_result_node_triple_fails_closed_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_CALLBACK_EXTRA_RESULT_VALUE_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        return _with_extra_result_value(_failing_result("target", "attempt-extra"), marker)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    _assert_marker_absent(marker, outcome)


def test_initial_report_graph_conforms_mismatch_is_rejected() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("target")
    mismatched_graph = Graph()
    for triple in initial.report_graph:
        mismatched_graph.add(triple)
    report_uri = URIRef(initial.report_id)
    mismatched_graph.remove((report_uri, SH.conforms, None))
    mismatched_graph.add((report_uri, SH.conforms, Literal(True)))

    with pytest.raises(ValueError, match="report_graph"):
        run_bounded_repair(
            replace(initial, report_graph=mismatched_graph),
            retry_budget=0,
            repair_attempt=_unexpected_repair,
        )


def test_callback_report_graph_conforms_mismatch_fails_closed() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        mismatched_graph = Graph()
        for triple in fresh.report_graph:
            mismatched_graph.add(triple)
        report_uri = URIRef(fresh.report_id)
        mismatched_graph.remove((report_uri, SH.conforms, None))
        mismatched_graph.add((report_uri, SH.conforms, Literal(False)))
        return replace(fresh, report_graph=mismatched_graph)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"


def test_initial_hostile_report_graph_objects_exception_is_sanitized() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_OBJECTS_EXCEPTION_SHOULD_NOT_LEAK"
    initial = replace(_failing_result("target"), report_graph=_HostileObjectsGraph(marker))

    with pytest.raises(ValueError) as exc_info:
        run_bounded_repair(
            initial,
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("attempt-1"),
        )

    assert exc_info.value.__cause__ is None
    assert "report_graph" in str(exc_info.value)
    assert marker not in str(exc_info.value)
    assert marker not in repr(exc_info.value)


def test_callback_hostile_report_graph_objects_exception_fails_closed_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_CALLBACK_OBJECTS_EXCEPTION_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        return replace(fresh, report_graph=_HostileObjectsGraph(marker))

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    _assert_marker_absent(marker, outcome)
    for event in outcome.events:
        _assert_marker_absent(marker, event.errors)


def test_initial_hostile_conforms_literal_exception_is_sanitized() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_LITERAL_EXCEPTION_SHOULD_NOT_LEAK"
    initial = _failing_result("target")
    hostile_graph = Graph()
    for triple in initial.report_graph:
        hostile_graph.add(triple)
    report_uri = URIRef(initial.report_id)
    hostile_graph.remove((report_uri, SH.conforms, None))
    hostile_graph.add((report_uri, SH.conforms, _HostileConformsLiteral(False, marker)))

    with pytest.raises(ValueError) as exc_info:
        run_bounded_repair(
            replace(initial, report_graph=hostile_graph),
            retry_budget=1,
            repair_attempt=_unexpected_repair,
        )

    assert exc_info.value.__cause__ is None
    assert "report_graph" in str(exc_info.value)
    _assert_marker_absent(marker, exc_info.value)


def test_callback_hostile_conforms_literal_exception_fails_closed_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_CALLBACK_LITERAL_EXCEPTION_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        hostile_graph = Graph()
        for triple in fresh.report_graph:
            hostile_graph.add(triple)
        report_uri = URIRef(fresh.report_id)
        hostile_graph.remove((report_uri, SH.conforms, None))
        hostile_graph.add((report_uri, SH.conforms, _HostileConformsLiteral(True, marker)))
        return replace(fresh, report_graph=hostile_graph)

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    _assert_marker_absent(marker, outcome)


@pytest.mark.parametrize(
    ("malformed", "field"),
    [
        (lambda result: replace(result, conforms="yes"), "conforms"),
        (lambda result: replace(result, conforms=True, violations=result.violations), "conforms"),
        (lambda result: replace(result, conforms=False, violations=()), "conforms"),
        (lambda result: replace(result, violations=list(result.violations)), "violations"),
        (lambda result: replace(result, violations=(object(),)), "violations"),
        (
            lambda result: replace(
                result,
                violations=(replace(result.violations[0], shape_id="   "),),
            ),
            "violations",
        ),
        (
            lambda result: replace(
                result,
                violations=(replace(result.violations[0], source_constraint_component="   "),),
            ),
            "violations",
        ),
        (
            lambda result: replace(
                result,
                stage_event=replace(
                    result.stage_event,
                    status=TerminalStatus.INSUFFICIENT_EVIDENCE,
                ),
            ),
            "stage_event",
        ),
        (lambda result: replace(result, report_graph="not a graph"), "report_graph"),
    ],
)
def test_initial_validation_structural_defects_are_rejected_generically(
    malformed: Callable[[ShaclValidationResult], ShaclValidationResult], field: str
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    with pytest.raises((TypeError, ValueError), match=field) as exc_info:
        run_bounded_repair(
            malformed(_failing_result("target")),
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("attempt-1"),
        )

    assert "SECRET" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("malformed", "field"),
    [
        (lambda result: replace(result, conforms="yes"), "conforms"),
        (lambda result: replace(result, conforms=True, violations=result.violations), "conforms"),
        (lambda result: replace(result, conforms=False, violations=()), "conforms"),
        (lambda result: replace(result, violations=list(result.violations)), "violations"),
        (lambda result: replace(result, violations=(object(),)), "violations"),
        (
            lambda result: replace(
                result,
                violations=(replace(result.violations[0], message="   "),),
            ),
            "violations",
        ),
        (
            lambda result: replace(
                result,
                stage_event=replace(
                    result.stage_event,
                    status=TerminalStatus.INSUFFICIENT_EVIDENCE,
                ),
            ),
            "stage_event",
        ),
        (lambda result: replace(result, report_graph="not a graph"), "report_graph"),
    ],
)
def test_fresh_validation_structural_defects_fail_closed_without_retaining_marker(
    malformed: Callable[[ShaclValidationResult], ShaclValidationResult], field: str
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_FRESH_STRUCTURAL_DEFECT_SHOULD_NOT_LEAK"
    initial = _failing_result("target")

    def repair(_request: object) -> ShaclValidationResult:
        fresh = _failing_result("target", "attempt-1")
        broken = malformed(fresh)
        return replace(broken, report_id=broken.report_id.replace("attempt-1", marker))

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=repair)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == field
    _assert_marker_absent(marker, outcome)


@pytest.mark.parametrize(
    "fresh",
    [
        _failing_result("generic_support", "fresh-generic-support"),
        _unknown_shape_result("fresh-unknown"),
        _failing_result("cross_class", "fresh-cross-class"),
    ],
)
def test_fresh_unsupported_reclassification_fails_closed_without_retaining_callback_result(
    fresh: ShaclValidationResult,
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_UNSUPPORTED_RECLASSIFICATION_SHOULD_NOT_LEAK"
    initial = _failing_result("target")
    marked_violation = replace(fresh.violations[0], message=marker)
    marked_fresh = _with_rebuilt_report_results(fresh, (marked_violation, *fresh.violations[1:]))

    def repair(_request: object) -> ShaclValidationResult:
        return marked_fresh

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=repair)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 1
    assert outcome.events[0].errors[0].code is StageErrorCode.VALIDATION_CONSTRAINT_FAILED
    assert outcome.events[0].errors[0].field == "shape_policy"
    _assert_marker_absent(marker, outcome)
    _assert_marker_absent(marker, outcome.final_validation)


def test_callback_report_graph_run_identity_drift_fails_closed() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        drifted_graph = Graph()
        for triple in fresh.report_graph:
            drifted_graph.add(triple)
        report_uri = URIRef(fresh.report_id)
        drifted_graph.remove((report_uri, MFG.runId, None))
        drifted_graph.add((report_uri, MFG.runId, Literal("different-run")))
        return replace(fresh, report_graph=drifted_graph)

    outcome = run_bounded_repair(
        _failing_result("target"), retry_budget=1, repair_attempt=malformed
    )

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"


def test_callback_report_graph_additive_run_identity_conflict_fails_closed_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_EXTRA_RUN_ID_SHOULD_NOT_LEAK"

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        conflicting_graph = Graph()
        for triple in fresh.report_graph:
            conflicting_graph.add(triple)
        conflicting_graph.add((URIRef(fresh.report_id), MFG.runId, Literal(marker)))
        return replace(fresh, report_graph=conflicting_graph)

    initial = _failing_result("target")
    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_graph"
    assert marker not in repr(outcome)
    assert marker not in str(outcome.events)


def test_initial_report_graph_additive_run_identity_conflict_is_rejected_without_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_INITIAL_EXTRA_RUN_ID_SHOULD_NOT_LEAK"
    initial = _failing_result("target")
    conflicting_graph = Graph()
    for triple in initial.report_graph:
        conflicting_graph.add(triple)
    conflicting_graph.add((URIRef(initial.report_id), MFG.runId, Literal(marker)))
    malformed = replace(initial, report_graph=conflicting_graph)

    with pytest.raises(ValueError) as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("attempt-1"),
        )

    assert "report_graph" in str(exc_info.value)
    assert marker not in str(exc_info.value)
    assert marker not in repr(exc_info.value)


def test_callback_wrong_type_return_is_sanitized_and_marker_not_retained() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_WRONG_TYPE_SHOULD_NOT_APPEAR"

    class WrongType:
        def __repr__(self) -> str:
            return marker

    def wrong_type(_request: BoundedRepairRequest) -> object:
        return WrongType()

    outcome = run_bounded_repair(
        _failing_result("target"),
        retry_budget=1,
        repair_attempt=cast(RepairAttempt, wrong_type),
    )

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "repair_attempt"
    assert marker not in repr(outcome)
    assert marker not in str(outcome.events)


def test_initial_shacl_output_identity_must_equal_report_id_tuple_without_leaking_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = SENSITIVE_EXTRA_OUTPUT_ID
    initial = _failing_result("target")
    malformed = replace(
        initial,
        stage_event=replace(initial.stage_event, output_ids=(initial.report_id, marker)),
    )

    with pytest.raises(ValueError) as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("attempt-1"),
        )

    assert "output_ids" in str(exc_info.value)
    assert marker not in str(exc_info.value)
    assert marker not in repr(exc_info.value)


def test_initial_validation_rejects_extra_input_identity_without_retaining_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "INITIAL_EXTRA_INPUT_SECRET_7d09"
    initial = _failing_result("generic_support", "initial_extra_input")
    malformed = replace(
        initial,
        stage_event=replace(
            initial.stage_event,
            input_ids=(initial.stage_event.input_ids[0], marker),
        ),
    )

    with pytest.raises(ValueError, match="stage_event.input_ids") as exc_info:
        run_bounded_repair(
            malformed,
            retry_budget=1,
            repair_attempt=_unexpected_repair,
        )

    _assert_marker_absent(marker, exc_info.value)


def test_fresh_shacl_output_identity_must_equal_report_id_tuple_and_drops_extra_marker() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = SENSITIVE_EXTRA_OUTPUT_ID
    initial = _failing_result("target")

    def malformed(_request: BoundedRepairRequest) -> ShaclValidationResult:
        fresh = _passing_result("attempt-1")
        return replace(
            fresh,
            stage_event=replace(fresh.stage_event, output_ids=(fresh.report_id, marker)),
        )

    outcome = run_bounded_repair(initial, retry_budget=1, repair_attempt=malformed)

    assert outcome.final_validation is initial
    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert outcome.events[0].errors[0].field == "report_id"
    assert marker not in repr(outcome)
    assert marker not in str(outcome.events)


def test_callback_exception_is_sanitized_and_marker_not_retained(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "SECRET_MARKER_SHOULD_NOT_APPEAR"

    def exploding(_request: BoundedRepairRequest) -> NoReturn:
        raise RuntimeError(f"engine leaked {marker}")

    with caplog.at_level(logging.ERROR, logger="mfg_agentgraph.diagnostics"):
        outcome = run_bounded_repair(
            _failing_result("target"), retry_budget=1, repair_attempt=exploding
        )

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert marker not in repr(outcome)
    assert marker not in str(outcome.events)
    assert marker not in str(outcome.events[0].errors[0])
    error_records = [
        record
        for record in caplog.records
        if getattr(record, "diagnostic_code", None) == "bounded_repair_attempt_error"
    ]
    assert len(error_records) == 1
    record = error_records[0]
    fields = vars(record)
    assert record.levelno == logging.ERROR
    assert record.name == "mfg_agentgraph.diagnostics"
    assert fields["diagnostic_code"] == "bounded_repair_attempt_error"
    assert fields["component"] == "bounded_repair"
    assert fields["operation"] == "repair_attempt"
    assert fields["run_id"] == RUN_ID
    assert fields["attempt_index"] == 1
    assert isinstance(fields["attempt_index"], int)
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.args == ()
    assert marker not in record.getMessage()
    assert marker not in str(record.msg)
    assert marker not in repr(record.args)
    assert marker not in repr(fields)
    assert marker not in logging.Formatter(
        "%(message)s %(diagnostic_code)s %(component)s %(operation)s %(run_id)s %(attempt_index)d"
    ).format(record)


def test_expected_repair_paths_emit_no_attempt_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    with caplog.at_level(logging.ERROR, logger="mfg_agentgraph.diagnostics"):
        no_op = run_bounded_repair(
            _passing_result("no-op"), retry_budget=1, repair_attempt=_unexpected_repair
        )
        repaired = run_bounded_repair(
            _failing_result("target"),
            retry_budget=1,
            repair_attempt=lambda _request: _passing_result("repaired"),
        )

    assert no_op.final_status is TerminalStatus.PASSED
    assert repaired.final_status is TerminalStatus.PASSED
    assert not any(
        getattr(record, "diagnostic_code", None) == "bounded_repair_attempt_error"
        for record in caplog.records
    )


def test_logging_handler_failure_does_not_replace_repair_failure() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    marker = "ISSUE74_REPAIR_HANDLER_SECRET"

    class HostileHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            del record
            raise RuntimeError(marker)

    def exploding(_request: BoundedRepairRequest) -> NoReturn:
        raise RuntimeError("repair detail must remain hidden")

    logger = logging.getLogger("mfg_agentgraph.diagnostics")
    handler = HostileHandler()
    logger.addHandler(handler)
    try:
        outcome = run_bounded_repair(
            _failing_result("target"), retry_budget=1, repair_attempt=exploding
        )
    finally:
        logger.removeHandler(handler)

    assert outcome.final_status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert outcome.repair_count == 1
    assert outcome.retry_count == 0
    assert outcome.events[0].errors[0].code is StageErrorCode.REPAIR_ATTEMPT_FAILED
    assert marker not in repr(outcome)
    assert marker not in str(outcome.events)


@pytest.mark.parametrize("bad_budget", [-1, True, 1.5, "1"])
def test_retry_budget_rejects_bool_negative_and_invalid_values(bad_budget: object) -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    with pytest.raises((TypeError, ValueError), match="retry_budget"):
        run_bounded_repair(
            _passing_result("initial"),
            retry_budget=cast(int, bad_budget),
            repair_attempt=_unexpected_repair,
        )


def test_records_are_frozen_slotted_and_initial_validation_is_not_mutated() -> None:
    from mfg_agentgraph.bounded_repair import BoundedRepairOutcome, run_bounded_repair

    initial = _failing_result("target")
    before = initial.violations
    outcome = run_bounded_repair(
        initial, retry_budget=1, repair_attempt=lambda _request: _passing_result("attempt-1")
    )

    assert isinstance(outcome, BoundedRepairOutcome)
    assert not hasattr(outcome, "__dict__")
    with pytest.raises(FrozenInstanceError):
        outcome.repair_count = 999  # type: ignore[misc]
    assert initial.violations == before
    assert initial.conforms is False


def test_failed_attempts_are_reclassified_before_second_attempt() -> None:
    from mfg_agentgraph.bounded_repair import run_bounded_repair

    requests: list[BoundedRepairRequest] = []

    def repair(request: BoundedRepairRequest) -> ShaclValidationResult:
        requests.append(request)
        if request.attempt_index == 1:
            return _failing_result("procedure", "attempt-1")
        return _passing_result("attempt-2")

    outcome = run_bounded_repair(_failing_result("target"), retry_budget=2, repair_attempt=repair)

    assert outcome.final_status is TerminalStatus.PASSED
    assert tuple(request.repair_class for request in requests) == ("TARGET", "PROCEDURE")
    assert requests[1].previous_report_id.endswith("attempt-1")
