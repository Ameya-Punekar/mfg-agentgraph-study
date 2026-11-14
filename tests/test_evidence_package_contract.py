# mypy: disable-error-code="arg-type,no-untyped-def"

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import FrozenInstanceError, replace
from typing import cast, overload

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SH, XSD

from mfg_agentgraph.bounded_repair import BoundedRepairOutcome
from mfg_agentgraph.candidate_action import CandidateAction
from mfg_agentgraph.evidence_reference import (
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.rdf_action_mapper import MFG, map_candidate_action_to_rdf
from mfg_agentgraph.shacl_validation import ShaclValidationResult, validate_recommended_action
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

EX = Namespace("http://example.org/")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
ACTION = EX.CandidateAction_Pump12_Repaired_001
ASSET = EX.Pump_12
KG_EVIDENCE = EX.EvidenceEdge_001
DOC_EVIDENCE = EX.SOP_Chunk_7
OBSERVATION = EX.Observation_Pump12_001
PROCEDURE = EX.Procedure_Pump12_001
REPORT = EX.ValidationReport_Pump12_001
PACKAGE = EX.EvidencePackage_Pump12_001
RUN_ID = "run-issue-21-pump-12"


def _dt(value: str) -> Literal:
    return Literal(value, datatype=XSD.dateTime)


def _reference(stable_id: str, kind: EvidenceKind, rank: int) -> EvidenceReference:
    return EvidenceReference(
        kind=kind,
        source="pump-12-fixture",
        stable_id=stable_id,
        retrieval=RetrievalMetadata(
            retrieval_run_id="retrieval-run-issue-21",
            query_id="query-pump-12",
            retriever_name="stage-9-contract-fixture",
            rank=rank,
            score=0.91,
        ),
        validation_status=EvidenceValidationStatus.VALIDATED,
    )


def _candidate_action() -> CandidateAction:
    return CandidateAction(
        rank=1,
        action="Inspect Pump 12 seal and review SOP isolation procedure",
        target_asset="ex:Pump_12",
        support_evidence=(
            _reference("ex:EvidenceEdge_001", EvidenceKind.KG_EDGE, 1),
            _reference("ex:SOP_Chunk_7", EvidenceKind.DOCUMENT_CHUNK, 2),
        ),
    )


def _resource_iris() -> dict[str, URIRef]:
    return {
        "ex:Pump_12": ASSET,
        "ex:EvidenceEdge_001": KG_EVIDENCE,
        "ex:SOP_Chunk_7": DOC_EVIDENCE,
    }


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


def _action_graph(action: CandidateAction | None = None) -> Graph:
    graph = map_candidate_action_to_rdf(
        action or _candidate_action(), action_iri=ACTION, resource_iris=_resource_iris()
    )
    graph.add((ACTION, MFG.anomalyWindowStart, _dt("2026-05-18T14:00:00Z")))
    graph.add((ACTION, MFG.anomalyWindowEnd, _dt("2026-05-18T14:10:00Z")))
    return graph


def _validation(
    action_graph: Graph | None = None, report: URIRef = REPORT
) -> ShaclValidationResult:
    result = validate_recommended_action(
        action_graph or _action_graph(),
        action_uri=ACTION,
        support_graph=_support_graph(),
        report_uri=report,
        run_id=RUN_ID,
    )
    assert result.conforms is True
    return result


def _outcome(validation: ShaclValidationResult | None = None) -> BoundedRepairOutcome:
    final = validation or _validation()
    return BoundedRepairOutcome(
        final_validation=final,
        final_status=TerminalStatus.PASSED,
        events=(
            StageEvent(
                stage=StageName.BOUNDED_REPAIR,
                run_id=RUN_ID,
                status=TerminalStatus.PASSED,
                input_ids=(str(ACTION), final.report_id),
                output_ids=(final.report_id,),
            ),
        ),
        initial_failure_count=0,
    )


def _assemble(**overrides: object):
    from mfg_agentgraph.evidence_package import assemble_evidence_package

    values: dict[str, object] = {
        "action": _candidate_action(),
        "action_id": str(ACTION),
        "action_graph": _action_graph(),
        "validation": _validation(),
        "outcome": _outcome(),
        "package_id": str(PACKAGE),
        "resource_iris": _resource_iris(),
        "typed_kg_evidence_ids": (str(KG_EVIDENCE),),
        "document_evidence_ids": (str(DOC_EVIDENCE),),
    }
    values.update(overrides)
    if "outcome" not in overrides:
        values["outcome"] = _outcome(cast(ShaclValidationResult, values["validation"]))
    return assemble_evidence_package(**values)


def test_package_accepts_explicit_mapping_for_non_curie_stable_ids() -> None:
    action = replace(
        _candidate_action(),
        target_asset="asset-pump-12",
        support_evidence=(
            _reference("kg-edge-001", EvidenceKind.KG_EDGE, 1),
            _reference("doc-chunk-7", EvidenceKind.DOCUMENT_CHUNK, 2),
        ),
    )
    resource_iris = {
        "asset-pump-12": ASSET,
        "kg-edge-001": KG_EVIDENCE,
        "doc-chunk-7": DOC_EVIDENCE,
    }
    graph = map_candidate_action_to_rdf(action, action_iri=ACTION, resource_iris=resource_iris)
    graph.add((ACTION, MFG.anomalyWindowStart, _dt("2026-05-18T14:00:00Z")))
    graph.add((ACTION, MFG.anomalyWindowEnd, _dt("2026-05-18T14:10:00Z")))
    validation = _validation(graph)

    result = _assemble(
        action=action, action_graph=graph, validation=validation, resource_iris=resource_iris
    )

    assert result.package is not None
    assert result.package.target_asset_id == str(ASSET)
    assert result.package.typed_kg_evidence_ids == (str(KG_EVIDENCE),)
    assert result.package.document_evidence_ids == (str(DOC_EVIDENCE),)


@pytest.mark.parametrize(
    ("resource_iris", "field"),
    [
        (None, "resource_iris"),
        ({"ex:Pump_12": ASSET}, "support_evidence"),
        ({**_resource_iris(), "ex:SOP_Chunk_7": KG_EVIDENCE}, "action_graph"),
    ],
)
def test_invalid_resource_mapping_fails_closed(resource_iris: object, field: str) -> None:
    _assert_fail_closed(_assemble(resource_iris=resource_iris), field)


def _assert_fail_closed(result, field: str) -> None:
    assert result.package is None
    event = result.stage_event
    assert event.stage is StageName.EVIDENCE_PACKAGE_ASSEMBLY
    assert event.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert event.run_id == RUN_ID
    assert event.errors
    assert event.errors[0].field == field
    assert event.errors[0].code is StageErrorCode.INVALID_EVIDENCE_PACKAGE


def test_assembles_stage9_package_from_real_mapped_action_graph_and_shacl_report() -> None:
    action = _candidate_action()
    action_graph = _action_graph(action)
    validation = _validation(action_graph)
    result = _assemble(action=action, action_graph=action_graph, validation=validation)

    assert result.package is not None
    package = result.package
    assert package.package_id == str(PACKAGE)
    assert package.run_id == RUN_ID
    assert package.action_id == str(ACTION)
    assert package.target_asset_id == str(ASSET)
    assert package.validation_report_id == str(REPORT)
    assert package.terminal_status is TerminalStatus.PASSED
    assert package.support_evidence_ids == (str(KG_EVIDENCE), str(DOC_EVIDENCE))
    assert package.typed_kg_evidence_ids == (str(KG_EVIDENCE),)
    assert package.document_evidence_ids == (str(DOC_EVIDENCE),)
    assert set(package.action_graph_evidence) == set(action_graph)
    assert package.action_graph_evidence != tuple(action_graph)
    assert not hasattr(package, "provenance_trace_id")
    assert not hasattr(package, "released_recommendation_id")
    assert result.stage_event.stage is StageName.EVIDENCE_PACKAGE_ASSEMBLY
    assert result.stage_event.status is TerminalStatus.PASSED
    assert result.stage_event.input_ids == (str(ACTION), str(REPORT))
    assert result.stage_event.output_ids == (str(PACKAGE),)
    with pytest.raises(FrozenInstanceError):
        package.package_id = "mutated"


def test_caller_supplied_package_id_is_stable_across_repeated_calls() -> None:
    first = _assemble(package_id=str(PACKAGE))
    second = _assemble(package_id=str(PACKAGE))

    assert first.package is not None
    assert second.package is not None
    assert first.package.package_id == str(PACKAGE)
    assert second.package == first.package


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda v: {"validation": object(), "outcome": _outcome()}, "validation"),
        (lambda v: {"outcome": object()}, "outcome"),
        (lambda v: {"action": object()}, "action"),
        (lambda v: {"action_id": 42}, "action_id"),
        (lambda v: {"package_id": " "}, "package_id"),
        (lambda v: {"resource_iris": {"ex:Pump_12": "not-an-iri"}}, "resource_iris"),
        (lambda v: {"typed_kg_evidence_ids": "not-a-sequence"}, "typed_kg_evidence_ids"),
        (lambda v: {"document_evidence_ids": None}, "document_evidence_ids"),
        (
            lambda v: {
                "typed_kg_evidence_ids": (str(KG_EVIDENCE),),
                "document_evidence_ids": (str(KG_EVIDENCE),),
            },
            "support_evidence",
        ),
        (lambda v: {"action_graph": object()}, "action_graph"),
        (
            lambda v: {
                "action": replace(
                    _candidate_action(),
                    support_evidence=(
                        _reference("ex:EvidenceEdge_001", EvidenceKind.KG_EDGE, 1),
                        _reference("ex:EvidenceEdge_001", EvidenceKind.KG_EDGE, 2),
                    ),
                )
            },
            "support_evidence",
        ),
        (
            lambda v: {
                "action": replace(
                    _candidate_action(),
                    support_evidence=(
                        _reference("ex:EvidenceEdge_001", EvidenceKind.KG_EDGE, 1),
                        _reference("ex:SOP_Chunk_7", EvidenceKind.KG_EDGE, 2),
                    ),
                )
            },
            "support_evidence",
        ),
    ],
)
def test_direct_constructed_malformed_inputs_fail_closed_without_package(
    mutation: Callable[[object], dict[str, object]], field: str
) -> None:
    result = _assemble(**mutation(None))

    _assert_fail_closed(result, field)


@pytest.mark.parametrize("invalid_report_id", [None, 42])
def test_malformed_validation_report_id_fails_closed_without_exception(
    invalid_report_id: object,
) -> None:
    validation = replace(_validation(), report_id=invalid_report_id)

    result = _assemble(validation=validation, outcome=_outcome())

    _assert_fail_closed(result, "validation")


class _FlippingSupport(Sequence[EvidenceReference]):
    def __init__(
        self,
        first: Sequence[EvidenceReference],
        second: Sequence[EvidenceReference],
    ) -> None:
        self._first = tuple(first)
        self._second = tuple(second)
        self._calls = 0

    def __len__(self) -> int:
        return len(self._first)

    @overload
    def __getitem__(self, index: int) -> EvidenceReference: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[EvidenceReference, ...]: ...

    def __getitem__(self, index: int | slice) -> EvidenceReference | tuple[EvidenceReference, ...]:
        return self._first[index]

    def __iter__(self) -> Iterator[EvidenceReference]:
        self._calls += 1
        return iter(self._first if self._calls == 1 else self._second)


class _FlippingResourceMap(Mapping[str, URIRef]):
    def __init__(self, values: Mapping[str, URIRef]) -> None:
        self._values = dict(values)
        self._calls = 0

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __getitem__(self, key: str) -> URIRef:
        self._calls += 1
        if self._calls > 7 and key == "ex:SOP_Chunk_7":
            return URIRef("http://evil.example/EvilDoc")
        return self._values[key]

    def items(self):
        return self._values.items()


class _FlippingIds(Sequence[str]):
    def __init__(self, first: Sequence[str], second: Sequence[str]) -> None:
        self._first = tuple(first)
        self._second = tuple(second)
        self._calls = 0

    def __len__(self) -> int:
        return len(self._first)

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[str, ...]: ...

    def __getitem__(self, index: int | slice) -> str | tuple[str, ...]:
        return self._first[index]

    def __iter__(self) -> Iterator[str]:
        self._calls += 1
        return iter(self._first if self._calls == 1 else self._second)


def test_stateful_support_sequence_cannot_change_after_validation() -> None:
    base = _candidate_action()
    extra = _reference("ex:ExtraEvidence", EvidenceKind.KG_EDGE, 3)
    action = replace(
        base,
        support_evidence=_FlippingSupport(
            base.support_evidence,
            base.support_evidence + (extra,),
        ),
    )
    resource_iris = {**_resource_iris(), "ex:ExtraEvidence": EX.ExtraEvidence}

    result = _assemble(action=action, resource_iris=resource_iris)

    _assert_fail_closed(result, "support_evidence")


def test_stateful_resource_mapping_is_snapshotted_before_validation() -> None:
    result = _assemble(resource_iris=_FlippingResourceMap(_resource_iris()))

    assert result.package is not None
    assert result.package.support_evidence_ids == (str(KG_EVIDENCE), str(DOC_EVIDENCE))
    assert "http://evil.example/EvilDoc" not in result.package.support_evidence_ids


def test_stateful_evidence_id_sequence_is_snapshotted_before_validation() -> None:
    result = _assemble(
        typed_kg_evidence_ids=_FlippingIds(
            (str(KG_EVIDENCE),),
            ("http://evil.example/EvilKg",),
        )
    )

    assert result.package is not None
    assert result.package.typed_kg_evidence_ids == (str(KG_EVIDENCE),)


@pytest.mark.parametrize("invalid_support", [None, 42, "ex:SOP_Chunk_7", (object(),)])
def test_malformed_support_evidence_fails_closed_without_payload_leakage(
    invalid_support: object,
) -> None:
    action = replace(_candidate_action(), support_evidence=invalid_support)

    result = _assemble(action=action)

    _assert_fail_closed(result, "support_evidence")
    assert "object object" not in repr(result)


@pytest.mark.parametrize(
    ("references", "kg_ids", "doc_ids"),
    [
        (
            (
                _reference("ex:EvidenceEdge_001", EvidenceKind.KG_EDGE, 1),
                _reference("ex:SOP_Chunk_7", EvidenceKind.KG_RESOURCE, 2),
            ),
            (str(KG_EVIDENCE), str(DOC_EVIDENCE)),
            (),
        ),
        (
            (
                _reference("ex:EvidenceEdge_001", EvidenceKind.DOCUMENT_CHUNK, 1),
                _reference("ex:SOP_Chunk_7", EvidenceKind.DOCUMENT_CHUNK, 2),
            ),
            (),
            (str(KG_EVIDENCE), str(DOC_EVIDENCE)),
        ),
    ],
)
def test_support_evidence_must_include_at_least_one_kg_and_one_document_reference(
    references: tuple[EvidenceReference, ...], kg_ids: tuple[str, ...], doc_ids: tuple[str, ...]
) -> None:
    action = replace(_candidate_action(), support_evidence=references)
    action_graph = _action_graph(action)
    validation = _validation(action_graph)

    result = _assemble(
        action=action,
        action_graph=action_graph,
        validation=validation,
        typed_kg_evidence_ids=kg_ids,
        document_evidence_ids=doc_ids,
    )

    _assert_fail_closed(result, "support_evidence")


@pytest.mark.parametrize(
    ("mutate", "field"),
    [
        (
            lambda validation: replace(
                validation, stage_event=replace(validation.stage_event, run_id="other-run")
            ),
            "run_id",
        ),
        (
            lambda validation: replace(
                validation,
                stage_event=replace(validation.stage_event, input_ids=(str(EX.OtherAction),)),
            ),
            "action_id",
        ),
        (
            lambda validation: replace(
                validation,
                stage_event=replace(
                    validation.stage_event, status=TerminalStatus.VALIDATION_FAILED_CLOSED
                ),
            ),
            "stage_event",
        ),
        (
            lambda validation: replace(
                validation,
                report_graph=_with_extra_report_value(validation, MFG.runId, Literal("other-run")),
            ),
            "report_graph",
        ),
        (
            lambda validation: replace(
                validation,
                report_graph=_with_extra_report_value(validation, MFG.focusAction, EX.OtherAction),
            ),
            "report_graph",
        ),
        (
            lambda validation: replace(
                validation,
                report_graph=_with_extra_report_value(validation, SH.conforms, Literal(False)),
            ),
            "report_graph",
        ),
    ],
)
def test_report_graph_run_action_and_status_identities_are_exact(
    mutate: Callable[[ShaclValidationResult], ShaclValidationResult], field: str
) -> None:
    validation = mutate(_validation())
    result = _assemble(validation=validation, outcome=_outcome(validation))

    _assert_fail_closed(result, field)


def _with_extra_report_value(
    validation: ShaclValidationResult, predicate: URIRef, value: object
) -> Graph:
    graph = Graph()
    for triple in validation.report_graph:
        graph.add(triple)
    graph.add((URIRef(validation.report_id), predicate, value))
    return graph


def test_outcome_must_match_final_passing_validation() -> None:
    validation = _validation()
    other_validation = _validation(report=EX.ValidationReport_Other)

    mismatch = _assemble(outcome=_outcome(other_validation))
    _assert_fail_closed(mismatch, "outcome")

    failed = _assemble(
        outcome=replace(_outcome(validation), final_status=TerminalStatus.INSUFFICIENT_EVIDENCE)
    )
    _assert_fail_closed(failed, "outcome")


def test_passing_outcome_without_bounded_repair_event_fails_closed() -> None:
    validation = _validation()
    _assert_fail_closed(
        _assemble(validation=validation, outcome=replace(_outcome(validation), events=())),
        "outcome",
    )


def test_blank_node_action_graph_fails_closed_without_unstable_package_evidence() -> None:
    graph = _action_graph()
    anonymous = BNode("annotation")
    graph.add((ACTION, EX.debugNode, anonymous))
    graph.add((anonymous, RDFS.label, Literal("anonymous annotation")))
    validation = _validation(graph)

    _assert_fail_closed(_assemble(action_graph=graph, validation=validation), "action_graph")


def test_outcome_passed_status_rejects_failed_bounded_repair_event() -> None:
    validation = _validation()
    failed_repair_event = StageEvent(
        stage=StageName.BOUNDED_REPAIR,
        run_id=RUN_ID,
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        input_ids=(str(ACTION), validation.report_id),
        output_ids=(),
        errors=(StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field="repair"),),
    )
    outcome = BoundedRepairOutcome(
        final_validation=validation,
        final_status=TerminalStatus.PASSED,
        events=(failed_repair_event,),
        initial_failure_count=1,
        repair_count=1,
    )

    result = _assemble(validation=validation, outcome=outcome)

    _assert_fail_closed(result, "outcome")


@pytest.mark.parametrize(
    ("run_id", "action_id", "report_id"),
    [
        ("other-run", str(ACTION), str(REPORT)),
        (RUN_ID, str(EX.OtherAction), str(REPORT)),
        (RUN_ID, str(ACTION), str(EX.OtherReport)),
    ],
)
def test_passed_repair_event_must_match_final_validation_identity(
    run_id: str, action_id: str, report_id: str
) -> None:
    validation = _validation()
    event = StageEvent(
        stage=StageName.BOUNDED_REPAIR,
        run_id=run_id,
        status=TerminalStatus.PASSED,
        input_ids=(action_id, validation.report_id),
        output_ids=(report_id,),
    )
    outcome = replace(_outcome(validation), events=(event,))

    _assert_fail_closed(_assemble(validation=validation, outcome=outcome), "outcome")


def test_validation_digest_must_match_supplied_action_graph() -> None:
    original_action_graph = _action_graph()
    validation = _validation(original_action_graph)
    changed_action_graph = _action_graph()
    changed_action_graph.set((ACTION, MFG.anomalyWindowStart, _dt("2026-05-18T14:01:00Z")))

    result = _assemble(action_graph=changed_action_graph, validation=validation)

    _assert_fail_closed(result, "action_graph")


@pytest.mark.parametrize(
    "action",
    [
        replace(_candidate_action(), action="Shutdown Pump 12 immediately"),
        replace(_candidate_action(), rank=99),
    ],
)
def test_candidate_action_must_match_validated_graph_label_and_rank(
    action: CandidateAction,
) -> None:
    result = _assemble(action=action)

    _assert_fail_closed(result, "action_graph")


@pytest.mark.parametrize("invalid_rank", ["1", b"1", True, 0])
def test_malformed_candidate_rank_fails_closed_before_rdf_comparison(
    invalid_rank: object,
) -> None:
    result = _assemble(action=replace(_candidate_action(), rank=invalid_rank))

    _assert_fail_closed(result, "action")


@pytest.mark.parametrize("invalid_action", [42, b"secret", "   ", " padded action "])
def test_malformed_candidate_action_text_fails_closed_before_rdf_comparison(
    invalid_action: object,
) -> None:
    action = replace(_candidate_action(), action=invalid_action)
    action_graph = _action_graph(action)
    validation = _validation(action_graph)

    result = _assemble(action=action, action_graph=action_graph, validation=validation)

    _assert_fail_closed(result, "action")


@pytest.mark.parametrize("invalid_target", ["   ", " ex:Pump_12 "])
def test_malformed_candidate_target_fails_closed_before_graph_binding(
    invalid_target: str,
) -> None:
    action = replace(_candidate_action(), target_asset=invalid_target)
    resource_iris = {**_resource_iris(), invalid_target: ASSET}
    action_graph = map_candidate_action_to_rdf(
        action, action_iri=ACTION, resource_iris=resource_iris
    )
    action_graph.add((ACTION, MFG.anomalyWindowStart, _dt("2026-05-18T14:00:00Z")))
    action_graph.add((ACTION, MFG.anomalyWindowEnd, _dt("2026-05-18T14:10:00Z")))
    validation = _validation(action_graph)

    result = _assemble(
        action=action,
        action_graph=action_graph,
        validation=validation,
        resource_iris=resource_iris,
    )

    _assert_fail_closed(result, "action")


def test_no_repair_outcome_must_name_final_report_as_its_initial_report() -> None:
    validation = _validation()
    event = replace(
        _outcome(validation).events[0],
        input_ids=(str(ACTION), str(EX.ForeignInitialReport)),
    )
    outcome = replace(_outcome(validation), events=(event,))

    result = _assemble(validation=validation, outcome=outcome)

    _assert_fail_closed(result, "outcome")


def test_repaired_outcome_binds_distinct_initial_and_final_reports() -> None:
    validation = _validation()
    event = replace(
        _outcome(validation).events[0],
        input_ids=(str(ACTION), str(EX.InitialFailedReport)),
        retry_count=1,
        repair_count=1,
    )
    outcome = replace(
        _outcome(validation),
        events=(event,),
        initial_failure_count=1,
        retry_count=1,
        repair_count=1,
        self_correction_success_count=1,
    )

    result = _assemble(validation=validation, outcome=outcome)

    assert result.package is not None
    assert result.package.validation_report_id == validation.report_id
    assert result.stage_event.status is TerminalStatus.PASSED


def test_conforming_report_graph_rejects_embedded_validation_results() -> None:
    validation = _validation()
    graph = Graph()
    for triple in validation.report_graph:
        graph.add(triple)
    result_node = URIRef(f"{validation.report_id}#unexpected-result")
    graph.add((URIRef(validation.report_id), SH.result, result_node))
    graph.add((URIRef(validation.report_id), MFG.violation, result_node))
    graph.add((result_node, RDF.type, SH.ValidationResult))

    result = _assemble(validation=replace(validation, report_graph=graph))

    _assert_fail_closed(result, "report_graph")


def test_action_graph_evidence_order_is_stable_for_equal_text_different_rdf_terms() -> None:
    evidence: list[tuple[tuple[object, object, object], ...]] = []
    for reverse in (False, True):
        graph = _action_graph()
        annotation = [
            (ACTION, EX.same, URIRef("http://example.org/collide")),
            (ACTION, EX.same, Literal("http://example.org/collide")),
        ]
        for triple in reversed(annotation) if reverse else annotation:
            graph.add(triple)
        validation = _validation(graph)
        result = _assemble(action_graph=graph, validation=validation)
        assert result.package is not None
        evidence.append(result.package.action_graph_evidence)

    assert evidence[0] == evidence[1]


def test_failed_validation_produces_no_package() -> None:
    action_graph = _action_graph()
    action_graph.remove((ACTION, MFG.hasSupportEvidence, None))
    validation = validate_recommended_action(
        action_graph,
        action_uri=ACTION,
        support_graph=_support_graph(),
        report_uri=REPORT,
        run_id=RUN_ID,
    )
    assert validation.conforms is False

    result = _assemble(
        action_graph=action_graph, validation=validation, outcome=_outcome(validation)
    )

    _assert_fail_closed(result, "validation")


def test_action_graph_evidence_must_equal_action_support_and_target() -> None:
    action_graph = _action_graph()
    action_graph.add((ACTION, MFG.hasSupportEvidence, EX.ExtraEvidence))

    extra = _assemble(action_graph=action_graph, validation=_validation())
    _assert_fail_closed(extra, "action_graph")

    missing_target = _action_graph()
    missing_target.remove((ACTION, MFG.targetAsset, ASSET))
    result = _assemble(action_graph=missing_target)
    _assert_fail_closed(result, "action_graph")


def test_error_surface_does_not_retain_sensitive_malformed_values() -> None:
    marker = "SECRET_STAGE9_CONFLICTING_ID_SHOULD_NOT_LEAK"
    validation = _validation()
    graph = _with_extra_report_value(
        validation, MFG.focusAction, URIRef(f"http://example.org/{marker}")
    )

    result = _assemble(validation=replace(validation, report_graph=graph))

    _assert_fail_closed(result, "report_graph")
    assert marker not in repr(result)
    assert marker not in str(result.stage_event.errors)
