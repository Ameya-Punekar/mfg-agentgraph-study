# mypy: disable-error-code="misc,no-untyped-call,no-untyped-def"

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Mapping
from copy import deepcopy
from dataclasses import FrozenInstanceError
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SH, XSD

from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.stage_instrumentation import StageErrorCode, StageName, TerminalStatus

EX = Namespace("http://example.org/")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
FIXTURE = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
ACTION = EX.CandidateAction_Pump12_Repaired_001
REPORT = EX.ValidationReport_Pump12_001
RUN_ID = "run-issue-19-pump-12"

EXPECTED_FAILURES = {
    "no_target": (
        "TargetAssetExactlyOneShape",
        "Recommended action must name exactly one target asset.",
    ),
    "multiple_targets": (
        "TargetAssetExactlyOneShape",
        "Recommended action must name exactly one target asset.",
    ),
    "unknown_target": ("TargetAssetModeledShape", "Target asset must be modeled as mfg:Asset."),
    "no_support": (
        "SupportEvidenceMinCountShape",
        "Recommended action must cite at least one support reference.",
    ),
    "unmodeled_support": (
        "SupportEvidenceModeledShape",
        "Each support reference must be modeled as mfg:SupportEvidence.",
    ),
    "observation_target_mismatch": (
        "ObservationConcernsTargetShape",
        "Supported observations must concern the recommended target asset.",
    ),
    "before_window": (
        "ObservationWithinAnomalyWindowShape",
        "Supported observation timestamps must fall inside the inclusive anomaly window.",
    ),
    "after_window": (
        "ObservationWithinAnomalyWindowShape",
        "Supported observation timestamps must fall inside the inclusive anomaly window.",
    ),
    "procedure_type_mismatch": (
        "ProcedureAppliesToTargetTypeShape",
        "Recommended procedure must apply to the target asset type.",
    ),
    "missing_support_observation_link": (
        "ObservationSupportRequiredShape",
        "Recommended action must cite at least one support reference linked to an observation.",
    ),
    "untyped_support_observation": (
        "ObservationTypedShape",
        "Each linked support observation must be typed as sosa:Observation.",
    ),
    "missing_observation_feature_of_interest": (
        "ObservationFeatureOfInterestRequiredShape",
        "Supported observations must identify a feature of interest.",
    ),
    "missing_observation_result_time": (
        "ObservationResultTimeRequiredShape",
        "Supported observations must include exactly one result timestamp.",
    ),
    "missing_action_window_start": (
        "ActionAnomalyWindowStartRequiredShape",
        "Recommended action must include exactly one anomaly window start timestamp.",
    ),
    "missing_action_window_end": (
        "ActionAnomalyWindowEndRequiredShape",
        "Recommended action must include exactly one anomaly window end timestamp.",
    ),
    "missing_support_procedure_link": (
        "ProcedureSupportRequiredShape",
        "Recommended action must cite at least one support reference linked to a procedure.",
    ),
    "untyped_support_procedure": (
        "ProcedureTypedShape",
        "Each linked support procedure must be typed as mfg:Procedure.",
    ),
    "missing_target_asset_type": (
        "TargetAssetTypeRequiredShape",
        "Target asset must include exactly one asset type.",
    ),
    "missing_procedure_applicable_asset_type": (
        "ProcedureApplicableAssetTypeRequiredShape",
        "Recommended procedure must include exactly one applicable asset type.",
    ),
}


def _module():
    return import_module("mfg_agentgraph.shacl_validation")


@pytest.fixture()
def shacl_validation():
    return _module()


@pytest.fixture()
def scenario() -> dict[str, Any]:
    loaded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return cast("dict[str, Any]", loaded)


def _uri(curie: str) -> URIRef:
    assert curie.startswith("ex:")
    return URIRef(str(EX) + curie.removeprefix("ex:"))


def _literal_dt(value: str) -> Literal:
    return Literal(value, datatype=XSD.dateTime)


def _asset_type_uri(scenario: Mapping[str, Any]) -> URIRef:
    asset_type = scenario["asset"]["type"]
    assert asset_type == "centrifugal_pump"
    return MFG.CentrifugalPump


def _scenario_uri(scenario: Mapping[str, Any], *path: str) -> URIRef:
    value: Any = scenario
    for key in path:
        value = value[key]
    assert isinstance(value, str)
    return _uri(value)


def _action_graph(scenario: Mapping[str, Any]) -> Graph:
    graph = Graph()
    graph.bind("mfg", MFG)
    graph.bind("ex", EX)
    action = _scenario_uri(scenario, "candidate_actions", "repaired", "id")
    target = _scenario_uri(scenario, "candidate_actions", "repaired", "target")
    graph.add((action, RDF.type, MFG.RecommendedAction))
    graph.add((action, MFG.targetAsset, target))
    for evidence_ref in scenario["candidate_actions"]["repaired"]["evidence_refs"]:
        graph.add((action, MFG.hasSupportEvidence, _uri(evidence_ref)))
    return graph


def _support_graph(scenario: Mapping[str, Any]) -> Graph:
    graph = Graph()
    graph.bind("mfg", MFG)
    graph.bind("sosa", SOSA)
    graph.bind("ex", EX)
    action = _scenario_uri(scenario, "candidate_actions", "repaired", "id")
    asset = _scenario_uri(scenario, "asset", "id")
    observation = _scenario_uri(scenario, "observation", "id")
    procedure = _scenario_uri(scenario, "procedure", "id")
    kg_evidence = _scenario_uri(scenario, "kg_evidence", "id")
    doc_evidence = _scenario_uri(scenario, "document_evidence", "id")

    graph.add((asset, RDF.type, MFG.Asset))
    graph.add((asset, MFG.assetType, _asset_type_uri(scenario)))
    graph.add((observation, RDF.type, SOSA.Observation))
    graph.add((observation, SOSA.hasFeatureOfInterest, asset))
    graph.add((observation, SOSA.resultTime, _literal_dt(scenario["observation"]["observed_at"])))
    graph.add((kg_evidence, RDF.type, MFG.SupportEvidence))
    graph.add((kg_evidence, MFG.observation, observation))
    graph.add((doc_evidence, RDF.type, MFG.SupportEvidence))
    graph.add((doc_evidence, MFG.procedure, procedure))
    graph.add((procedure, RDF.type, MFG.Procedure))
    graph.add((procedure, MFG.applicableAssetType, _asset_type_uri(scenario)))
    graph.add(
        (action, MFG.anomalyWindowStart, _literal_dt(scenario["anomaly_window"]["started_at"]))
    )
    graph.add((action, MFG.anomalyWindowEnd, _literal_dt(scenario["anomaly_window"]["ended_at"])))
    return graph


def _validate(
    shacl_validation, action_graph: Graph, support_graph: Graph, *, action: URIRef = ACTION
):
    return shacl_validation.validate_recommended_action(
        action_graph,
        action_uri=action,
        support_graph=support_graph,
        report_uri=REPORT,
        run_id=RUN_ID,
    )


def _assert_marker_not_retained(
    value: object, marker: str, *, seen: set[int] | None = None
) -> None:
    if seen is None:
        seen = set()
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, str):
        assert marker not in value
        return
    if isinstance(value, bytes):
        assert marker.encode() not in value
        return
    if isinstance(value, BaseException):
        _assert_marker_not_retained(value.args, marker, seen=seen)
        for attr in ("__cause__", "__context__", "__notes__"):
            retained = getattr(value, attr, None)
            if retained is not None:
                _assert_marker_not_retained(retained, marker, seen=seen)
        if hasattr(value, "__dict__"):
            _assert_marker_not_retained(vars(value), marker, seen=seen)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_marker_not_retained(key, marker, seen=seen)
            _assert_marker_not_retained(item, marker, seen=seen)
        return
    if isinstance(value, Collection) and not isinstance(value, str | bytes):
        for item in value:
            _assert_marker_not_retained(item, marker, seen=seen)


def test_package_resource_loading(shacl_validation) -> None:
    graph = shacl_validation.load_recommended_action_shapes()

    assert isinstance(graph, Graph)
    assert (MFG.RecommendedActionShape, RDF.type, SH.NodeShape) in graph
    assert (MFG.TargetAssetExactlyOneShape, SH.path, MFG.targetAsset) in graph
    assert len(graph) > 20


def test_canonical_pump12_action_conforms_and_annotates_stable_report(
    shacl_validation, scenario: Mapping[str, Any]
) -> None:
    result = _validate(shacl_validation, _action_graph(scenario), _support_graph(scenario))

    assert result.conforms is True
    assert result.report_id == str(REPORT)
    assert result.violations == ()
    assert (REPORT, SH.conforms, Literal(True)) in result.report_graph
    assert (REPORT, MFG.focusAction, ACTION) in result.report_graph
    assert (REPORT, MFG.runId, Literal(RUN_ID)) in result.report_graph
    assert result.stage_event.stage is StageName.SHACL_VALIDATION
    assert result.stage_event.status is TerminalStatus.PASSED
    assert result.stage_event.input_ids == (str(ACTION),)
    assert result.stage_event.output_ids == (str(REPORT),)
    assert result.stage_event.errors == ()
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.conforms = False


def test_unrelated_malformed_recommended_action_does_not_poison_requested_action(
    shacl_validation, scenario: Mapping[str, Any]
) -> None:
    action_graph = _action_graph(scenario)
    support_graph = _support_graph(scenario)
    unrelated_action = EX.UnrelatedIncompleteAction
    action_graph.add((unrelated_action, RDF.type, MFG.RecommendedAction))

    result = _validate(shacl_validation, action_graph, support_graph)

    assert result.conforms is True
    assert result.violations == ()
    assert (REPORT, SH.conforms, Literal(True)) in result.report_graph
    assert (REPORT, MFG.focusAction, ACTION) in result.report_graph
    assert result.stage_event.status is TerminalStatus.PASSED


def test_report_graph_is_readable_turtle(shacl_validation, scenario: Mapping[str, Any]) -> None:
    result = _validate(shacl_validation, _action_graph(scenario), _support_graph(scenario))

    serialized = result.report_graph.serialize(format="turtle")
    reparsed = Graph().parse(data=serialized, format="turtle")

    assert (REPORT, MFG.focusAction, ACTION) in reparsed
    assert (REPORT, SH.conforms, Literal(True)) in reparsed


@pytest.mark.parametrize(
    ("variant", "shape_suffix", "message"), [(k, *v) for k, v in EXPECTED_FAILURES.items()]
)
def test_single_fault_variants_fail_closed_with_stable_shape_ids_and_messages(
    shacl_validation,
    scenario: Mapping[str, Any],
    variant: str,
    shape_suffix: str,
    message: str,
) -> None:
    action_graph = _action_graph(scenario)
    support_graph = _support_graph(scenario)
    observation = _scenario_uri(scenario, "observation", "id")
    procedure = _scenario_uri(scenario, "procedure", "id")
    kg_evidence = _scenario_uri(scenario, "kg_evidence", "id")
    doc_evidence = _scenario_uri(scenario, "document_evidence", "id")
    target = _scenario_uri(scenario, "asset", "id")
    if variant == "no_target":
        action_graph.remove((ACTION, MFG.targetAsset, None))
    elif variant == "multiple_targets":
        action_graph.add((ACTION, MFG.targetAsset, EX.BackupPump_99))
        support_graph.add((EX.BackupPump_99, RDF.type, MFG.Asset))
    elif variant == "unknown_target":
        action_graph.set((ACTION, MFG.targetAsset, EX.UnmodeledPump))
    elif variant == "no_support":
        action_graph.remove((ACTION, MFG.hasSupportEvidence, None))
    elif variant == "unmodeled_support":
        support_graph.remove((doc_evidence, RDF.type, MFG.SupportEvidence))
    elif variant == "observation_target_mismatch":
        support_graph.set((observation, SOSA.hasFeatureOfInterest, EX.OtherPump))
        support_graph.add((EX.OtherPump, RDF.type, MFG.Asset))
    elif variant == "before_window":
        support_graph.set(
            (
                observation,
                SOSA.resultTime,
                _literal_dt("2026-05-18T13:59:59Z"),
            )
        )
    elif variant == "after_window":
        support_graph.set(
            (
                observation,
                SOSA.resultTime,
                _literal_dt("2026-05-18T14:10:01Z"),
            )
        )
    elif variant == "procedure_type_mismatch":
        support_graph.set((procedure, MFG.applicableAssetType, MFG.Fan))
    elif variant == "missing_support_observation_link":
        support_graph.remove((kg_evidence, MFG.observation, None))
    elif variant == "untyped_support_observation":
        support_graph.remove((observation, RDF.type, SOSA.Observation))
    elif variant == "missing_observation_feature_of_interest":
        support_graph.remove((observation, SOSA.hasFeatureOfInterest, None))
    elif variant == "missing_observation_result_time":
        support_graph.remove((observation, SOSA.resultTime, None))
    elif variant == "missing_action_window_start":
        support_graph.remove((ACTION, MFG.anomalyWindowStart, None))
    elif variant == "missing_action_window_end":
        support_graph.remove((ACTION, MFG.anomalyWindowEnd, None))
    elif variant == "missing_support_procedure_link":
        support_graph.remove((doc_evidence, MFG.procedure, None))
    elif variant == "untyped_support_procedure":
        support_graph.remove((procedure, RDF.type, MFG.Procedure))
    elif variant == "missing_target_asset_type":
        support_graph.remove((target, MFG.assetType, None))
    elif variant == "missing_procedure_applicable_asset_type":
        support_graph.remove((procedure, MFG.applicableAssetType, None))
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(variant)

    result = _validate(shacl_validation, action_graph, support_graph)

    assert result.conforms is False
    assert tuple(v.shape_id for v in result.violations) == (str(MFG[shape_suffix]),)
    assert tuple(v.message for v in result.violations) == (message,)
    assert tuple(v.focus_node for v in result.violations) == (str(ACTION),)
    assert (REPORT, SH.conforms, Literal(False)) in result.report_graph
    assert (REPORT, MFG.focusAction, ACTION) in result.report_graph
    assert (REPORT, MFG.runId, Literal(RUN_ID)) in result.report_graph
    assert result.violations[0].source_constraint_component is not None
    assert (REPORT, SH.result, URIRef(result.violations[0].result_node)) in result.report_graph
    assert result.stage_event.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.stage_event.errors[0].code is StageErrorCode.VALIDATION_CONSTRAINT_FAILED
    assert result.stage_event.input_ids == (str(ACTION),)
    assert result.stage_event.output_ids == (str(REPORT),)


def test_violation_order_is_deterministic(shacl_validation, scenario: Mapping[str, Any]) -> None:
    action_graph = _action_graph(scenario)
    support_graph = _support_graph(scenario)
    action_graph.remove((ACTION, MFG.targetAsset, None))
    action_graph.remove((ACTION, MFG.hasSupportEvidence, None))

    first = _validate(shacl_validation, action_graph, support_graph).violations
    second = _validate(shacl_validation, action_graph, support_graph).violations

    assert first == second
    assert tuple(v.shape_id for v in first) == (
        str(MFG.SupportEvidenceMinCountShape),
        str(MFG.TargetAssetExactlyOneShape),
    )


def test_input_graphs_are_not_mutated(shacl_validation, scenario: Mapping[str, Any]) -> None:
    action_graph = _action_graph(scenario)
    support_graph = _support_graph(scenario)
    before_action = set(deepcopy(tuple(action_graph)))
    before_support = set(deepcopy(tuple(support_graph)))

    _validate(shacl_validation, action_graph, support_graph)

    assert set(action_graph) == before_action
    assert set(support_graph) == before_support


@pytest.mark.parametrize(
    ("action_graph", "action_uri", "support_graph", "report_uri", "run_id", "field"),
    [
        (object(), ACTION, Graph(), REPORT, RUN_ID, "action_graph"),
        (Graph(), "not-a-uri", Graph(), REPORT, RUN_ID, "action_uri"),
        (Graph(), ACTION, object(), REPORT, RUN_ID, "support_graph"),
        (Graph(), ACTION, Graph(), "not-a-uri", RUN_ID, "report_uri"),
        (Graph(), ACTION, Graph(), REPORT, " ", "run_id"),
    ],
)
def test_bad_inputs_fail_closed_without_partial_report(
    shacl_validation,
    action_graph: object,
    action_uri: object,
    support_graph: object,
    report_uri: object,
    run_id: object,
    field: str,
) -> None:
    with pytest.raises(shacl_validation.ShaclValidationError) as exc_info:
        shacl_validation.validate_recommended_action(
            action_graph,
            action_uri=action_uri,
            support_graph=support_graph,
            report_uri=report_uri,
            run_id=run_id,
        )

    assert exc_info.value.code is shacl_validation.ShaclValidationErrorCode.INVALID_INPUT
    assert exc_info.value.field == field


def test_engine_error_fails_closed_without_sensitive_content(
    caplog: pytest.LogCaptureFixture,
    shacl_validation,
    scenario: Mapping[str, Any],
) -> None:
    marker = "ISSUE19_ENGINE_SECRET_DO_NOT_RETAIN"

    def explode(**_kwargs: object) -> tuple[bool, Graph, str]:
        raise RuntimeError(marker)

    with (
        caplog.at_level(logging.ERROR, logger="mfg_agentgraph.diagnostics"),
        pytest.raises(shacl_validation.ShaclValidationError) as exc_info,
    ):
        shacl_validation.validate_recommended_action(
            _action_graph(scenario),
            action_uri=ACTION,
            support_graph=_support_graph(scenario),
            report_uri=REPORT,
            run_id=RUN_ID,
            validation_engine=explode,
        )

    error = exc_info.value
    assert error.code is shacl_validation.ShaclValidationErrorCode.ENGINE_ERROR
    assert error.field == "validation_engine"
    assert error.__cause__ is None
    assert error.__context__ is None
    _assert_marker_not_retained(error, marker)

    error_records = [
        record
        for record in caplog.records
        if getattr(record, "diagnostic_code", None) == "shacl_validation_engine_error"
    ]
    assert len(error_records) == 1
    record = error_records[0]
    fields = vars(record)
    assert record.levelno == logging.ERROR
    assert record.name == "mfg_agentgraph.diagnostics"
    assert fields["diagnostic_code"] == "shacl_validation_engine_error"
    assert fields["component"] == "shacl_validation"
    assert fields["operation"] == "validate_recommended_action"
    assert fields["run_id"] == RUN_ID
    assert not hasattr(record, "attempt_index")
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.args == ()
    assert marker not in record.getMessage()
    assert marker not in str(record.msg)
    assert marker not in repr(record.args)
    assert marker not in repr(fields)
    assert marker not in logging.Formatter(
        "%(message)s %(diagnostic_code)s %(component)s %(operation)s %(run_id)s"
    ).format(record)


def test_expected_validation_results_emit_no_engine_diagnostic(
    caplog: pytest.LogCaptureFixture,
    shacl_validation,
    scenario: Mapping[str, Any],
) -> None:
    with caplog.at_level(logging.ERROR, logger="mfg_agentgraph.diagnostics"):
        passing = _validate(shacl_validation, _action_graph(scenario), _support_graph(scenario))
        action_graph = _action_graph(scenario)
        action_graph.remove((ACTION, MFG.targetAsset, None))
        failing = _validate(shacl_validation, action_graph, _support_graph(scenario))

    assert passing.conforms is True
    assert failing.conforms is False
    assert not any(
        getattr(record, "diagnostic_code", None) == "shacl_validation_engine_error"
        for record in caplog.records
    )


def test_logging_handler_failure_does_not_replace_engine_error(
    shacl_validation, scenario: Mapping[str, Any]
) -> None:
    marker = "ISSUE74_HOSTILE_HANDLER_SECRET"

    class HostileHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            del record
            raise RuntimeError(marker)

    def explode(**_kwargs: object) -> tuple[bool, Graph, str]:
        raise RuntimeError("engine detail must remain hidden")

    logger = logging.getLogger("mfg_agentgraph.diagnostics")
    handler = HostileHandler()
    logger.addHandler(handler)
    try:
        with pytest.raises(shacl_validation.ShaclValidationError) as exc_info:
            shacl_validation.validate_recommended_action(
                _action_graph(scenario),
                action_uri=ACTION,
                support_graph=_support_graph(scenario),
                report_uri=REPORT,
                run_id=RUN_ID,
                validation_engine=explode,
            )
    finally:
        logger.removeHandler(handler)

    assert exc_info.value.code is shacl_validation.ShaclValidationErrorCode.ENGINE_ERROR
    assert exc_info.value.field == "validation_engine"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_marker_not_retained(exc_info.value, marker)


def test_fixture_graph_builders_use_scenario_identifiers(scenario: Mapping[str, Any]) -> None:
    action_graph = _action_graph(scenario)
    support_graph = _support_graph(scenario)
    action = _scenario_uri(scenario, "candidate_actions", "repaired", "id")
    target = _scenario_uri(scenario, "asset", "id")
    observation = _scenario_uri(scenario, "observation", "id")
    procedure = _scenario_uri(scenario, "procedure", "id")
    kg_evidence = _scenario_uri(scenario, "kg_evidence", "id")
    doc_evidence = _scenario_uri(scenario, "document_evidence", "id")

    assert action == ACTION
    assert (action, MFG.targetAsset, target) in action_graph
    assert (action, MFG.hasSupportEvidence, kg_evidence) in action_graph
    assert (action, MFG.hasSupportEvidence, doc_evidence) in action_graph
    assert (action, MFG.observation, observation) not in action_graph
    assert (action, MFG.procedure, procedure) not in action_graph
    assert tuple(support_graph.objects(target, MFG.assetType)) == (_asset_type_uri(scenario),)
    assert isinstance(next(support_graph.objects(target, MFG.assetType)), URIRef)
    assert tuple(support_graph.objects(procedure, MFG.applicableAssetType)) == (
        _asset_type_uri(scenario),
    )
    assert isinstance(next(support_graph.objects(procedure, MFG.applicableAssetType)), URIRef)
    assert (kg_evidence, MFG.observation, observation) in support_graph
    assert (doc_evidence, MFG.procedure, procedure) in support_graph
    assert (observation, RDF.type, SOSA.Observation) in support_graph


def test_absent_action_uri_fails_invalid_input(
    shacl_validation, scenario: Mapping[str, Any]
) -> None:
    action_graph = _action_graph(scenario)
    action_graph.remove((ACTION, RDF.type, MFG.RecommendedAction))

    with pytest.raises(shacl_validation.ShaclValidationError) as exc_info:
        _validate(shacl_validation, action_graph, _support_graph(scenario))

    assert exc_info.value.code is shacl_validation.ShaclValidationErrorCode.INVALID_INPUT
    assert exc_info.value.field == "action_uri"


def test_stable_report_contains_only_normalized_validation_results(
    shacl_validation, scenario: Mapping[str, Any]
) -> None:
    action_graph = _action_graph(scenario)
    action_graph.remove((ACTION, MFG.targetAsset, None))

    result = _validate(shacl_validation, action_graph, _support_graph(scenario))

    validation_results = set(result.report_graph.subjects(RDF.type, SH.ValidationResult))
    stable_result = URIRef(result.violations[0].result_node)
    assert validation_results == {stable_result}
    assert not any(isinstance(node, BNode) for node in validation_results)
    assert (REPORT, RDF.type, SH.ValidationReport) in result.report_graph
    assert (REPORT, SH.result, stable_result) in result.report_graph
    assert tuple(result.report_graph.objects(REPORT, SH.result)) == (stable_result,)
    assert tuple(result.report_graph.objects(stable_result, SH.sourceShape)) == (
        MFG.TargetAssetExactlyOneShape,
    )
    assert tuple(result.report_graph.objects(stable_result, SH.focusNode)) == (ACTION,)
    assert tuple(result.report_graph.objects(stable_result, SH.resultMessage)) == (
        Literal("Recommended action must name exactly one target asset."),
    )
    assert tuple(result.report_graph.objects(stable_result, SH.sourceConstraintComponent)) == (
        SH.MinCountConstraintComponent,
    )


@pytest.mark.parametrize(
    ("mutation", "shape_suffix", "message"),
    [
        (
            "multiple_observation_result_times",
            "ObservationResultTimeRequiredShape",
            "Supported observations must include exactly one result timestamp.",
        ),
        (
            "multiple_target_asset_types",
            "TargetAssetTypeRequiredShape",
            "Target asset must include exactly one asset type.",
        ),
        (
            "multiple_procedure_applicable_asset_types",
            "ProcedureApplicableAssetTypeRequiredShape",
            "Recommended procedure must include exactly one applicable asset type.",
        ),
        (
            "malformed_observation_result_time",
            "ObservationWithinAnomalyWindowShape",
            "Supported observation timestamps must fall inside the inclusive anomaly window.",
        ),
        (
            "inverted_anomaly_window",
            "ObservationWithinAnomalyWindowShape",
            "Supported observation timestamps must fall inside the inclusive anomaly window.",
        ),
    ],
)
def test_single_fault_edge_cases_fail_closed_with_truthful_shape_messages(
    shacl_validation,
    scenario: Mapping[str, Any],
    mutation: str,
    shape_suffix: str,
    message: str,
) -> None:
    action_graph = _action_graph(scenario)
    support_graph = _support_graph(scenario)
    target = _scenario_uri(scenario, "asset", "id")
    observation = _scenario_uri(scenario, "observation", "id")
    procedure = _scenario_uri(scenario, "procedure", "id")

    if mutation == "multiple_observation_result_times":
        support_graph.add((observation, SOSA.resultTime, _literal_dt("2026-05-18T14:04:00Z")))
    elif mutation == "multiple_target_asset_types":
        support_graph.add((target, MFG.assetType, MFG.BackupPumpType))
    elif mutation == "multiple_procedure_applicable_asset_types":
        support_graph.add((procedure, MFG.applicableAssetType, MFG.BackupPumpType))
    elif mutation == "malformed_observation_result_time":
        support_graph.set((observation, SOSA.resultTime, Literal("not-a-dateTime")))
    elif mutation == "inverted_anomaly_window":
        support_graph.set((ACTION, MFG.anomalyWindowStart, _literal_dt("2026-05-18T14:10:00Z")))
        support_graph.set((ACTION, MFG.anomalyWindowEnd, _literal_dt("2026-05-18T14:00:00Z")))
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(mutation)

    result = _validate(shacl_validation, action_graph, support_graph)

    assert result.conforms is False
    assert tuple(v.shape_id for v in result.violations) == (str(MFG[shape_suffix]),)
    assert tuple(v.message for v in result.violations) == (message,)
    assert tuple(v.focus_node for v in result.violations) == (str(ACTION),)


def test_stable_report_omits_sensitive_values_and_preserves_safe_rdf_terms(
    shacl_validation, scenario: Mapping[str, Any]
) -> None:
    marker = "ISSUE19_LITERAL_SECRET_DO_NOT_RETAIN"
    raw_result = BNode()
    raw_path = BNode()
    literal_value = Literal(f"literal sh:value contains {marker}")

    def synthetic_engine(**_kwargs: object) -> tuple[bool, Graph, str]:
        raw = Graph()
        raw.add((REPORT, RDF.type, SH.ValidationReport))
        raw.add((REPORT, SH.conforms, Literal(False)))
        raw.add((REPORT, SH.result, raw_result))
        raw.add((raw_result, RDF.type, SH.ValidationResult))
        raw.add((raw_result, SH.sourceShape, MFG.TargetAssetExactlyOneShape))
        raw.add((raw_result, SH.focusNode, ACTION))
        raw.add((raw_result, SH.resultMessage, Literal("synthetic literal value violation")))
        raw.add((raw_result, SH.sourceConstraintComponent, SH.MinCountConstraintComponent))
        raw.add((raw_result, SH.resultPath, raw_path))
        raw.add((raw_result, SH.value, literal_value))
        return False, raw, "synthetic"

    result = shacl_validation.validate_recommended_action(
        _action_graph(scenario),
        action_uri=ACTION,
        support_graph=_support_graph(scenario),
        report_uri=REPORT,
        run_id=RUN_ID,
        validation_engine=synthetic_engine,
    )

    stable_results = tuple(result.report_graph.subjects(RDF.type, SH.ValidationResult))
    assert stable_results == (URIRef(f"{REPORT}#violation-1"),)
    stable_result = stable_results[0]
    assert (raw_result, RDF.type, SH.ValidationResult) not in result.report_graph
    assert tuple(result.report_graph.triples((None, SH.value, None))) == ()
    assert not any(marker in str(value) for value in result.report_graph.objects(None, SH.value))
    assert marker not in result.report_graph.serialize(format="turtle")
    assert marker not in repr(result.violations)
    assert marker not in repr(result.stage_event)
    _assert_marker_not_retained(result.violations, marker)
    _assert_marker_not_retained(result.stage_event, marker)
    assert tuple(result.report_graph.objects(stable_result, SH.resultPath)) == (raw_path,)
    assert isinstance(next(result.report_graph.objects(stable_result, SH.resultPath)), BNode)
    assert tuple(result.report_graph.objects(stable_result, SH.focusNode)) == (ACTION,)
    assert isinstance(next(result.report_graph.objects(stable_result, SH.focusNode)), URIRef)
    assert tuple(result.report_graph.objects(stable_result, SH.sourceShape)) == (
        MFG.TargetAssetExactlyOneShape,
    )
    assert isinstance(next(result.report_graph.objects(stable_result, SH.sourceShape)), URIRef)
    assert tuple(result.report_graph.objects(stable_result, SH.sourceConstraintComponent)) == (
        SH.MinCountConstraintComponent,
    )
    assert isinstance(
        next(result.report_graph.objects(stable_result, SH.sourceConstraintComponent)), URIRef
    )
