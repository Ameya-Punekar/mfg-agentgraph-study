# mypy: disable-error-code="misc,no-untyped-call,no-untyped-def"

from collections.abc import Collection, Mapping
from copy import deepcopy
from dataclasses import FrozenInstanceError
from importlib import import_module

import pytest

from mfg_agentgraph.candidate_action import CandidateAction
from mfg_agentgraph.evidence_reference import (
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)

EX = "http://example.org/"


def _rdflib():
    return import_module("rdflib")


def _mapper():
    return import_module("mfg_agentgraph.rdf_action_mapper")


@pytest.fixture()
def rdflib_module():
    return _rdflib()


@pytest.fixture()
def rdf_mapper():
    return _mapper()


def _reference(stable_id: str, *, kind: EvidenceKind, rank: int) -> EvidenceReference:
    return EvidenceReference(
        kind=kind,
        source="pump-12-fixture",
        stable_id=stable_id,
        retrieval=RetrievalMetadata(
            retrieval_run_id="retrieval-run-issue-18",
            query_id="query-pump-12",
            retriever_name="issue-18-contract-fixture",
            rank=rank,
            score=0.91,
        ),
        validation_status=EvidenceValidationStatus.VALIDATED,
    )


def _canonical_action() -> CandidateAction:
    return CandidateAction(
        rank=1,
        action="Inspect Pump 12 seal and review SOP isolation procedure",
        target_asset="ex:Pump_12",
        support_evidence=(
            _reference("ex:EvidenceEdge_001", kind=EvidenceKind.KG_EDGE, rank=1),
            _reference("ex:SOP_Chunk_7", kind=EvidenceKind.DOCUMENT_CHUNK, rank=2),
        ),
    )


def _resource_iris(rdflib_module) -> dict[str, object]:
    return {
        "ex:Pump_12": rdflib_module.URIRef(f"{EX}Pump_12"),
        "ex:EvidenceEdge_001": rdflib_module.URIRef(f"{EX}EvidenceEdge_001"),
        "ex:SOP_Chunk_7": rdflib_module.URIRef(f"{EX}SOP_Chunk_7"),
    }


def _assert_marker_not_retained(
    value: object,
    marker: str,
    *,
    seen: set[int] | None = None,
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
        for attr in getattr(value, "__slots__", ()):
            if hasattr(value, attr):
                _assert_marker_not_retained(getattr(value, attr), marker, seen=seen)
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


def _assert_mapping_error(
    rdf_mapper, call, *, code_name: str, field: str, marker: str | None = None
) -> None:
    with pytest.raises(rdf_mapper.RdfActionMappingError) as exc_info:
        call()

    error = exc_info.value
    assert error.code is getattr(rdf_mapper.RdfActionMappingErrorCode, code_name)
    assert error.field == field
    assert error.__cause__ is None
    assert error.__context__ is None
    if marker is not None:
        _assert_marker_not_retained(error, marker)


def test_exports_intended_public_api(rdf_mapper) -> None:
    assert hasattr(rdf_mapper, "MFG")
    assert hasattr(rdf_mapper, "RdfActionMappingError")
    assert hasattr(rdf_mapper, "RdfActionMappingErrorCode")
    assert hasattr(rdf_mapper, "map_candidate_action_to_rdf")
    assert rdf_mapper.RdfActionMappingErrorCode.UNKNOWN_RESOURCE_ID.value == "unknown_resource_id"
    assert (
        rdf_mapper.RdfActionMappingErrorCode.INVALID_MAPPING_INPUT.value == "invalid_mapping_input"
    )


def test_maps_candidate_action_to_structural_rdf_graph(rdflib_module, rdf_mapper) -> None:
    action = _canonical_action()
    action_iri = rdflib_module.URIRef(f"{EX}Action_001")
    resource_iris = _resource_iris(rdflib_module)

    graph = rdf_mapper.map_candidate_action_to_rdf(
        action,
        action_iri=action_iri,
        resource_iris=resource_iris,
    )

    assert isinstance(graph, rdflib_module.Graph)
    assert (action_iri, rdflib_module.RDF.type, rdf_mapper.MFG.RecommendedAction) in graph
    assert (action_iri, rdflib_module.RDFS.label, rdflib_module.Literal(action.action)) in graph
    assert list(graph.objects(action_iri, rdf_mapper.MFG.targetAsset)) == [
        resource_iris["ex:Pump_12"]
    ]
    assert (
        action_iri,
        rdf_mapper.MFG.rank,
        rdflib_module.Literal(action.rank, datatype=rdflib_module.XSD.integer),
    ) in graph
    assert set(graph.objects(action_iri, rdf_mapper.MFG.hasSupportEvidence)) == {
        resource_iris["ex:EvidenceEdge_001"],
        resource_iris["ex:SOP_Chunk_7"],
    }
    assert len(list(graph.objects(action_iri, rdf_mapper.MFG.hasSupportEvidence))) == 2


def test_unknown_target_fails_closed_without_retaining_marker(rdflib_module, rdf_mapper) -> None:
    marker = "ISSUE18_UNKNOWN_TARGET_SECRET_DO_NOT_RETAIN"
    action = CandidateAction(
        rank=1,
        action="Inspect Pump 12 seal",
        target_asset=marker,
        support_evidence=_canonical_action().support_evidence,
    )
    resources = _resource_iris(rdflib_module)

    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            action,
            action_iri=rdflib_module.URIRef(f"{EX}Action_UnknownTarget"),
            resource_iris=resources,
        ),
        code_name="UNKNOWN_RESOURCE_ID",
        field="target_asset",
        marker=marker,
    )


def test_unknown_support_evidence_fails_closed_without_retaining_marker(
    rdflib_module, rdf_mapper
) -> None:
    marker = "ISSUE18_UNKNOWN_EVIDENCE_SECRET_DO_NOT_RETAIN"
    action = CandidateAction(
        rank=1,
        action="Inspect Pump 12 seal",
        target_asset="ex:Pump_12",
        support_evidence=(_reference(marker, kind=EvidenceKind.KG_EDGE, rank=1),),
    )
    resources = _resource_iris(rdflib_module)

    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            action,
            action_iri=rdflib_module.URIRef(f"{EX}Action_UnknownEvidence"),
            resource_iris=resources,
        ),
        code_name="UNKNOWN_RESOURCE_ID",
        field="support_evidence",
        marker=marker,
    )


@pytest.mark.parametrize(
    ("bad_action", "field"),
    [
        (object(), "action"),
        (None, "action"),
        ("not-a-candidate-action", "action"),
    ],
)
def test_rejects_wrong_action_input(
    rdflib_module, rdf_mapper, bad_action: object, field: str
) -> None:
    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            bad_action,
            action_iri=rdflib_module.URIRef(f"{EX}Action_BadInput"),
            resource_iris=_resource_iris(rdflib_module),
        ),
        code_name="INVALID_MAPPING_INPUT",
        field=field,
    )


@pytest.mark.parametrize("bad_action_iri", [f"{EX}Action_String", object(), None])
def test_rejects_wrong_action_iri_input(rdflib_module, rdf_mapper, bad_action_iri: object) -> None:
    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            _canonical_action(),
            action_iri=bad_action_iri,
            resource_iris=_resource_iris(rdflib_module),
        ),
        code_name="INVALID_MAPPING_INPUT",
        field="action_iri",
    )


@pytest.mark.parametrize("bad_resource_iris", [None, object(), "ex:Pump_12"])
def test_rejects_wrong_resource_iris_input(
    rdflib_module, rdf_mapper, bad_resource_iris: object
) -> None:
    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            _canonical_action(),
            action_iri=rdflib_module.URIRef(f"{EX}Action_BadResources"),
            resource_iris=bad_resource_iris,
        ),
        code_name="INVALID_MAPPING_INPUT",
        field="resource_iris",
    )


@pytest.mark.parametrize(
    ("resources", "field"),
    [
        ({1: None}, "resource_iris"),
        ({"ex:Pump_12": f"{EX}Pump_12"}, "resource_iris"),
    ],
)
def test_rejects_wrong_resource_mapping_keys_and_values(
    rdflib_module, rdf_mapper, resources: object, field: str
) -> None:
    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            _canonical_action(),
            action_iri=rdflib_module.URIRef(f"{EX}Action_BadResourceEntries"),
            resource_iris=resources,
        ),
        code_name="INVALID_MAPPING_INPUT",
        field=field,
    )


def test_inputs_are_not_mutated_and_mapping_is_deterministic(rdflib_module, rdf_mapper) -> None:
    action = _canonical_action()
    action_iri = rdflib_module.URIRef(f"{EX}Action_Deterministic")
    resources = _resource_iris(rdflib_module)
    original_action = deepcopy(action)
    original_resources = dict(resources)

    first = rdf_mapper.map_candidate_action_to_rdf(
        action,
        action_iri=action_iri,
        resource_iris=resources,
    )
    second = rdf_mapper.map_candidate_action_to_rdf(
        action,
        action_iri=action_iri,
        resource_iris=resources,
    )

    assert action == original_action
    assert resources == original_resources
    assert set(first) == set(second)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        action.support_evidence = ()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        action.support_evidence[0].stable_id = "ex:Mutated"


def test_resolves_all_identifiers_before_graph_construction(
    rdflib_module, rdf_mapper, monkeypatch
) -> None:
    action = CandidateAction(
        rank=1,
        action="Inspect Pump 12 seal",
        target_asset="ex:Pump_12",
        support_evidence=(
            _reference("ex:EvidenceEdge_001", kind=EvidenceKind.KG_EDGE, rank=1),
            _reference("ex:MissingEvidence_999", kind=EvidenceKind.DOCUMENT_CHUNK, rank=2),
        ),
    )
    resources = _resource_iris(rdflib_module)
    action_iri = rdflib_module.URIRef(f"{EX}Action_AllOrNothing")
    original_graph = rdf_mapper.Graph
    graph_calls = 0

    def graph_spy(*args, **kwargs):
        nonlocal graph_calls
        graph_calls += 1
        return original_graph(*args, **kwargs)

    monkeypatch.setattr(rdf_mapper, "Graph", graph_spy)

    _assert_mapping_error(
        rdf_mapper,
        lambda: rdf_mapper.map_candidate_action_to_rdf(
            action,
            action_iri=action_iri,
            resource_iris=resources,
        ),
        code_name="UNKNOWN_RESOURCE_ID",
        field="support_evidence",
    )

    assert graph_calls == 0


def test_mapping_error_rejects_non_enum_code_without_retaining_marker(rdf_mapper) -> None:
    marker = "ISSUE18_INVALID_ERROR_CODE_SECRET_DO_NOT_RETAIN"

    with pytest.raises(TypeError) as exc_info:
        rdf_mapper.RdfActionMappingError(marker, "code")

    _assert_marker_not_retained(exc_info.value, marker)
