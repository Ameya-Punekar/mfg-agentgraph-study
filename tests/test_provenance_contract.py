from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, overload

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from mfg_agentgraph.evidence_package import EvidencePackage
from mfg_agentgraph.fuseki_provenance_store import (
    DispatchState,
    FusekiProvenanceStore,
    FusekiProvenanceStoreConfig,
    FusekiProvenanceTransportError,
)
from mfg_agentgraph.provenance import PROV, ProvenanceWriteResult, write_provenance_trace
from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

TRACE = "https://example.org/provenance/trace-22"
RECOMMENDATION = "https://example.org/action/recommendation-22"
PACKAGE = "https://example.org/evidence/package-22"
ASSET = "https://example.org/asset/Pump_12"
REPORT = "https://example.org/validation/report-22"
KG_EVIDENCE = "https://example.org/evidence/kg-edge-001"
DOC_EVIDENCE = "https://example.org/evidence/sop-chunk-7"
AGENT = "https://example.org/agent/s4"
PROMPT = "https://example.org/prompt/pump-12"
MODEL = "https://example.org/model/fixture"
RUN_ID = "run-issue-22"
RECORDED_AT = datetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC)
FUSEKI_UPDATE = "http://127.0.0.1:3030/update"
FUSEKI_QUERY = "http://127.0.0.1:3030/query"
FUSEKI_GRAPH_BASE = "https://example.org/provenance"


def _package(**overrides: object) -> EvidencePackage:
    values: dict[str, Any] = {
        "package_id": PACKAGE,
        "run_id": RUN_ID,
        "action_id": RECOMMENDATION,
        "target_asset_id": ASSET,
        "validation_report_id": REPORT,
        "terminal_status": TerminalStatus.PASSED,
        "support_evidence_ids": (KG_EVIDENCE, DOC_EVIDENCE),
        "typed_kg_evidence_ids": (KG_EVIDENCE,),
        "document_evidence_ids": (DOC_EVIDENCE,),
        "action_graph_evidence": ((URIRef(RECOMMENDATION), RDF.type, MFG.RecommendedAction),),
    }
    values.update(overrides)
    return EvidencePackage(**values)


def _event(
    stage: StageName,
    *,
    run_id: str = RUN_ID,
    status: TerminalStatus = TerminalStatus.PASSED,
    errors: tuple[StageError, ...] = (),
) -> StageEvent:
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    if stage is StageName.STRUCTURED_RETRIEVAL:
        input_ids = (ASSET,)
        output_ids = ("https://example.org/observation/1", KG_EVIDENCE)
    elif stage is StageName.PROCEDURAL_RETRIEVAL:
        input_ids = (ASSET,)
        output_ids = (DOC_EVIDENCE,)
    elif stage is StageName.CANDIDATE_GENERATION:
        input_ids = (ASSET, KG_EVIDENCE, DOC_EVIDENCE)
        output_ids = (RECOMMENDATION,)
    elif stage is StageName.SHACL_VALIDATION:
        input_ids = (RECOMMENDATION,)
        output_ids = (REPORT,)
    elif stage is StageName.BOUNDED_REPAIR:
        input_ids = (RECOMMENDATION, REPORT)
        output_ids = (REPORT,)
    elif stage is StageName.EVIDENCE_PACKAGE_ASSEMBLY:
        input_ids = (RECOMMENDATION, REPORT)
        output_ids = (PACKAGE,)
    else:
        raise AssertionError(f"Unexpected test stage: {stage}")
    return StageEvent(
        stage=stage,
        run_id=run_id,
        status=status,
        input_ids=input_ids,
        output_ids=output_ids,
        errors=errors,
    )


def _events() -> tuple[StageEvent, ...]:
    return tuple(
        _event(stage)
        for stage in (
            StageName.STRUCTURED_RETRIEVAL,
            StageName.PROCEDURAL_RETRIEVAL,
            StageName.CANDIDATE_GENERATION,
            StageName.SHACL_VALIDATION,
            StageName.BOUNDED_REPAIR,
            StageName.EVIDENCE_PACKAGE_ASSEMBLY,
        )
    )


def _write(**overrides: object) -> ProvenanceWriteResult:
    values: dict[str, Any] = {
        "evidence_package": _package(),
        "provenance_id": TRACE,
        "recommendation_id": RECOMMENDATION,
        "agent_id": AGENT,
        "prompt_id": PROMPT,
        "model_id": MODEL,
        "recorded_at": RECORDED_AT,
        "stage_events": _events(),
        "persist_trace": lambda graph: None,
    }
    values.update(overrides)
    return write_provenance_trace(**values)


def _graph(result: ProvenanceWriteResult) -> Graph:
    graph = Graph()
    for triple in result.trace_graph_evidence:
        graph.add(triple)
    return graph


def _assert_failed(result: ProvenanceWriteResult, field: str) -> None:
    assert result.provenance_id is None
    assert result.recommendation_id is None
    assert result.trace_graph_evidence == ()
    event = result.stage_event
    assert event.stage is StageName.PROV_O_TRACE_WRITING
    assert event.status is TerminalStatus.PROVENANCE_FAILED_CLOSED
    assert event.output_ids == ()
    assert event.errors == (StageError(StageErrorCode.PROVENANCE_WRITE_FAILED, field=field),)


def test_success_returns_stable_release_ids_graph_and_stage_event() -> None:
    result = _write()

    assert result.provenance_id == TRACE
    assert result.recommendation_id == RECOMMENDATION
    assert result.trace_graph_evidence
    assert result.stage_event == StageEvent(
        stage=StageName.PROV_O_TRACE_WRITING,
        run_id=RUN_ID,
        status=TerminalStatus.PASSED,
        input_ids=(PACKAGE,),
        output_ids=(TRACE, RECOMMENDATION),
    )
    with pytest.raises(FrozenInstanceError):
        result.provenance_id = "https://evil.example/trace"  # type: ignore[misc]


def test_fuseki_persist_bound_method_is_a_stage10_callback_and_releases_both_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FusekiProvenanceStore(
        FusekiProvenanceStoreConfig(FUSEKI_UPDATE, FUSEKI_QUERY, FUSEKI_GRAPH_BASE)
    )
    calls: list[str] = []

    def update(
        self: FusekiProvenanceStore,
        prepared: object,
        *,
        deadline: float | None = None,
    ) -> None:
        del self, prepared, deadline
        calls.append("update")

    def readback(
        self: FusekiProvenanceStore,
        prepared: object,
        deadline: float,
        expected_graph: bytes,
        *,
        state_floor: DispatchState = DispatchState.NOT_DISPATCHED,
    ) -> Graph:
        del self, prepared, deadline, state_floor
        calls.append("readback")
        graph = Graph()
        graph.parse(data=expected_graph.decode("utf-8"), format="nt")
        return graph

    monkeypatch.setattr(FusekiProvenanceStore, "_dispatch_prepared", update)
    monkeypatch.setattr(FusekiProvenanceStore, "_dispatch_query", readback)

    result = _write(persist_trace=store.persist)

    assert calls == ["update", "readback"]
    assert result.provenance_id == TRACE
    assert result.recommendation_id == RECOMMENDATION
    assert result.trace_graph_evidence


@pytest.mark.parametrize("failure_point", ["update", "readback"])
def test_fuseki_persist_failure_blocks_ids_and_trace_evidence(
    monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    store = FusekiProvenanceStore(
        FusekiProvenanceStoreConfig(FUSEKI_UPDATE, FUSEKI_QUERY, FUSEKI_GRAPH_BASE)
    )

    def fail_update(
        self: FusekiProvenanceStore, prepared: object, *, deadline: float | None = None
    ) -> None:
        del self, prepared, deadline
        if failure_point == "update":
            raise FusekiProvenanceTransportError(
                fuseki_store._TransportPhase.DISPATCH, DispatchState.DISPATCHED_UNKNOWN
            )

    def fail_readback(
        self: FusekiProvenanceStore,
        prepared: object,
        deadline: float,
        expected_graph: bytes,
        *,
        state_floor: DispatchState = DispatchState.NOT_DISPATCHED,
    ) -> Graph:
        del self, prepared, deadline, expected_graph, state_floor
        raise FusekiProvenanceTransportError(
            fuseki_store._TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN
        )

    import mfg_agentgraph.fuseki_provenance_store as fuseki_store

    monkeypatch.setattr(FusekiProvenanceStore, "_dispatch_prepared", fail_update)
    monkeypatch.setattr(FusekiProvenanceStore, "_dispatch_query", fail_readback)

    _assert_failed(_write(persist_trace=store.persist), "persistence")


def test_graph_models_required_prov_entities_activities_agent_and_lineage() -> None:
    graph = _graph(_write())
    trace = URIRef(TRACE)
    recommendation = URIRef(RECOMMENDATION)
    package = URIRef(PACKAGE)
    report = URIRef(REPORT)
    agent = URIRef(AGENT)
    prompt = URIRef(PROMPT)
    model = URIRef(MODEL)
    model_activity = URIRef(f"{TRACE}/activities/model-invocation")
    validation_activity = URIRef(f"{TRACE}/activities/shacl-validation")
    assembly_activity = URIRef(f"{TRACE}/activities/evidence-assembly")
    writing_activity = URIRef(f"{TRACE}/activities/provenance-writing")

    assert (trace, RDF.type, PROV.Entity) in graph
    assert (trace, RDF.type, MFG.ProvenanceTrace) in graph
    assert (trace, MFG.runId, Literal(RUN_ID)) in graph
    assert (trace, MFG.recordedAt, Literal(RECORDED_AT, datatype=XSD.dateTime)) in graph
    assert (trace, MFG.recommendation, recommendation) in graph
    assert (trace, MFG.evidencePackage, package) in graph
    assert (agent, RDF.type, PROV.SoftwareAgent) in graph
    assert (prompt, RDF.type, PROV.Entity) in graph
    assert (model, RDF.type, PROV.Entity) in graph
    assert (URIRef(KG_EVIDENCE), RDF.type, PROV.Entity) in graph
    assert (URIRef(DOC_EVIDENCE), RDF.type, PROV.Entity) in graph
    assert (model_activity, PROV.used, prompt) in graph
    assert (model_activity, PROV.used, model) in graph
    assert (recommendation, PROV.wasGeneratedBy, model_activity) in graph
    assert (validation_activity, PROV.used, recommendation) in graph
    assert (report, PROV.wasGeneratedBy, validation_activity) in graph
    assert (package, PROV.wasGeneratedBy, assembly_activity) in graph
    assert (writing_activity, PROV.used, package) in graph
    assert (trace, PROV.wasGeneratedBy, writing_activity) in graph
    assert (writing_activity, PROV.wasAssociatedWith, agent) in graph
    assert (writing_activity, PROV.wasInformedBy, assembly_activity) in graph


def test_repeated_writes_are_deterministic() -> None:
    assert _write() == _write()


def test_callback_receives_copy_and_mutation_cannot_change_result() -> None:
    observed_size = 0

    def mutate(graph: Graph) -> None:
        nonlocal observed_size
        observed_size = len(graph)
        graph.remove((None, None, None))

    result = _write(persist_trace=mutate)

    assert observed_size > 0
    assert len(result.trace_graph_evidence) == observed_size


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provenance_id", ""),
        ("provenance_id", "relative/trace"),
        ("recommendation_id", "https://example.org/action/other"),
        ("agent_id", " agent "),
        ("prompt_id", 42),
        ("model_id", "not-an-iri"),
    ],
)
def test_invalid_or_drifted_identity_fails_closed(field: str, value: object) -> None:
    _assert_failed(_write(**{field: value}), field)


@pytest.mark.parametrize("recorded_at", [None, True, datetime(2026, 5, 18, 14, 11, 15)])
def test_invalid_or_naive_recorded_time_fails_closed(recorded_at: object) -> None:
    _assert_failed(_write(recorded_at=recorded_at), "recorded_at")


@pytest.mark.parametrize(
    "package",
    [
        object(),
        _package(run_id=" "),
        _package(terminal_status=TerminalStatus.VALIDATION_FAILED_CLOSED),
        _package(package_id="relative"),
        _package(typed_kg_evidence_ids=()),
        _package(document_evidence_ids=()),
        _package(support_evidence_ids=(KG_EVIDENCE,)),
        _package(action_graph_evidence=((URIRef(RECOMMENDATION), RDF.type, object()),)),
    ],
)
def test_malformed_direct_constructed_package_fails_closed(package: object) -> None:
    _assert_failed(_write(evidence_package=package), "evidence_package")


@pytest.mark.parametrize(
    "events",
    [
        None,
        "not-events",
        _events()[:-1],
        _events() + (_events()[-1],),
        tuple(reversed(_events())),
        (_event(StageName.STRUCTURED_RETRIEVAL), object(), *_events()[2:]),
    ],
)
def test_missing_extra_duplicate_reordered_or_malformed_events_fail_closed(
    events: object,
) -> None:
    _assert_failed(_write(stage_events=events), "stage_events")


def test_foreign_run_failed_or_error_bearing_event_fails_closed() -> None:
    foreign = (_event(StageName.STRUCTURED_RETRIEVAL, run_id="foreign"), *_events()[1:])
    _assert_failed(_write(stage_events=foreign), "stage_events")

    failed = (
        *_events()[:3],
        _event(StageName.SHACL_VALIDATION, status=TerminalStatus.VALIDATION_FAILED_CLOSED),
        *_events()[4:],
    )
    _assert_failed(_write(stage_events=failed), "stage_events")

    with_error = (
        _event(
            StageName.STRUCTURED_RETRIEVAL,
            errors=(StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field="support"),),
        ),
        *_events()[1:],
    )
    _assert_failed(_write(stage_events=with_error), "stage_events")


def test_event_identity_linkage_drift_fails_closed() -> None:
    events = list(_events())
    events[2] = replace(events[2], output_ids=("https://example.org/action/other",))
    _assert_failed(_write(stage_events=tuple(events)), "stage_events")


def test_tampered_event_containers_fail_closed_without_exception() -> None:
    events = list(_events())
    object.__setattr__(events[3], "input_ids", object())

    _assert_failed(_write(stage_events=tuple(events)), "stage_events")


class _ExplodingDatetime(datetime):
    def utcoffset(self) -> Any:
        raise RuntimeError("PRIVATE-DATETIME-MARKER")


def test_hostile_datetime_subclass_fails_closed_without_marker_leakage() -> None:
    hostile = _ExplodingDatetime(2026, 5, 18, 14, 11, 15, tzinfo=UTC)

    result = _write(recorded_at=hostile)

    _assert_failed(result, "recorded_at")
    assert "PRIVATE-DATETIME-MARKER" not in repr(result)


class _ExplodingTimezone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta:
        raise RuntimeError("PRIVATE-TIMEZONE-MARKER")

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "EXPLODING"


def test_hostile_timezone_validation_exception_fails_closed() -> None:
    hostile = datetime(2026, 5, 18, 14, 11, 15, tzinfo=_ExplodingTimezone())

    result = _write(recorded_at=hostile)

    _assert_failed(result, "input")
    assert "PRIVATE-TIMEZONE-MARKER" not in repr(result)


class _StatefulTimezone(tzinfo):
    def __init__(self) -> None:
        self.calls = 0

    def utcoffset(self, dt: datetime | None) -> timedelta:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("PRIVATE-BUILD-MARKER")
        return timedelta(0)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "STATEFUL"


def test_trace_build_exception_fails_closed_without_marker_leakage() -> None:
    stateful = datetime(2026, 5, 18, 14, 11, 15, tzinfo=_StatefulTimezone())

    result = _write(recorded_at=stateful)

    _assert_failed(result, "input")
    assert "PRIVATE-BUILD-MARKER" not in repr(result)


class _FlippingEvents(Sequence[StageEvent]):
    def __init__(self) -> None:
        self.calls = 0
        self.first = _events()
        self.second = tuple(reversed(self.first))

    def __len__(self) -> int:
        return len(self.first)

    @overload
    def __getitem__(self, index: int) -> StageEvent: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[StageEvent, ...]: ...

    def __getitem__(self, index: int | slice) -> StageEvent | tuple[StageEvent, ...]:
        return self.first[index]

    def __iter__(self) -> Iterator[StageEvent]:
        self.calls += 1
        return iter(self.first if self.calls == 1 else self.second)


def test_stateful_event_sequence_is_snapshotted_once() -> None:
    events = _FlippingEvents()

    result = _write(stage_events=events)

    assert result.stage_event.status is TerminalStatus.PASSED
    assert events.calls == 1


def test_callback_exception_is_sanitized_and_blocks_release() -> None:
    marker = "PRIVATE-PERSISTENCE-MARKER"

    def fail(graph: Graph) -> None:
        raise RuntimeError(marker)

    result = _write(persist_trace=fail)

    _assert_failed(result, "persistence")
    assert marker not in repr(result)


def test_non_none_callback_result_is_rejected() -> None:
    _assert_failed(_write(persist_trace=lambda graph: "claimed-success"), "persistence")


def test_non_callable_persistence_port_fails_closed() -> None:
    _assert_failed(_write(persist_trace=object()), "persist_trace")
