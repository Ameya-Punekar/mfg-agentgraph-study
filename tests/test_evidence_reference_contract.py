from dataclasses import FrozenInstanceError
from math import inf, nan

import pytest

from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceReferenceResolutionCode,
    EvidenceReferenceResolutionError,
    EvidenceValidationStatus,
    RetrievalMetadata,
)


def _metadata(**overrides: object) -> RetrievalMetadata:
    values = {
        "retrieval_run_id": "retrieval-run-001",
        "query_id": "query-001",
        "retriever_name": "fixture-retriever",
        "rank": 1,
        "score": 0.83,
    }
    values.update(overrides)
    return RetrievalMetadata(**values)  # type: ignore[arg-type]


def _reference(
    stable_id: str = "ex:EvidenceEdge_001",
    *,
    kind: EvidenceKind = EvidenceKind.KG_EDGE,
    validation_status: EvidenceValidationStatus = EvidenceValidationStatus.VALIDATED,
) -> EvidenceReference:
    return EvidenceReference(
        kind=kind,
        source="fixture-kg",
        stable_id=stable_id,
        retrieval=_metadata(),
        validation_status=validation_status,
    )


def test_typed_vocabularies_are_stable_and_complete() -> None:
    assert tuple(kind.value for kind in EvidenceKind) == (
        "kg_resource",
        "kg_edge",
        "document_chunk",
    )
    assert tuple(status.value for status in EvidenceValidationStatus) == (
        "unvalidated",
        "validated",
        "invalid",
    )


def test_evidence_reference_is_immutable_hashable_and_deterministic() -> None:
    left = _reference()
    right = _reference()

    assert left == right
    assert hash(left) == hash(right)
    assert left.retrieval == right.retrieval
    assert not hasattr(left, "__dict__")
    assert not hasattr(left.retrieval, "__dict__")
    with pytest.raises(FrozenInstanceError):
        left.stable_id = "changed"  # type: ignore[misc]


def test_reference_can_be_embedded_as_immutable_tuple_for_later_contracts() -> None:
    support_refs = (
        _reference("ex:EvidenceEdge_001"),
        _reference("ex:SOP_Chunk_7", kind=EvidenceKind.DOCUMENT_CHUNK),
    )

    assert support_refs[0].kind is EvidenceKind.KG_EDGE
    assert support_refs[1].kind is EvidenceKind.DOCUMENT_CHUNK
    with pytest.raises(TypeError):
        support_refs[0] = _reference("ex:Other")  # type: ignore[index]


@pytest.mark.parametrize("blank", ["", "   "])
def test_retrieval_metadata_rejects_blank_strings(blank: str) -> None:
    with pytest.raises(ValueError, match="retrieval_run_id"):
        _metadata(retrieval_run_id=blank)
    with pytest.raises(ValueError, match="query_id"):
        _metadata(query_id=blank)
    with pytest.raises(ValueError, match="retriever_name"):
        _metadata(retriever_name=blank)


@pytest.mark.parametrize("bad_value", [0, -1])
def test_retrieval_metadata_rejects_nonpositive_rank(bad_value: int) -> None:
    with pytest.raises(ValueError, match="rank"):
        _metadata(rank=bad_value)


@pytest.mark.parametrize("bad_value", [True, 1.2, "1"])
def test_retrieval_metadata_rejects_non_integer_rank_and_bool(bad_value: object) -> None:
    with pytest.raises(TypeError, match="rank"):
        _metadata(rank=bad_value)


@pytest.mark.parametrize("bad_score", [True, nan, inf, -inf])
def test_retrieval_metadata_rejects_bool_and_non_finite_score(bad_score: object) -> None:
    with pytest.raises((TypeError, ValueError), match="score"):
        _metadata(score=bad_score)


def test_retrieval_metadata_accepts_absent_score_without_inventing_one() -> None:
    metadata = _metadata(score=None)

    assert metadata.score is None


@pytest.mark.parametrize("field", ("retrieval_run_id", "query_id", "retriever_name"))
def test_retrieval_metadata_enforces_identifier_utf8_byte_limit(field: str) -> None:
    assert getattr(_metadata(**{field: "é" * 512}), field) == "é" * 512
    with pytest.raises(ValueError, match=f"{field} exceeds"):
        _metadata(**{field: "é" * 513})


def test_evidence_reference_enforces_source_and_stable_id_byte_limits() -> None:
    reference = EvidenceReference(
        kind=EvidenceKind.DOCUMENT_CHUNK,
        source="x" * 1_024,
        stable_id="é" * 4_096,
        retrieval=_metadata(),
        validation_status=EvidenceValidationStatus.VALIDATED,
    )
    assert len(reference.source.encode("utf-8")) == 1_024
    assert len(reference.stable_id.encode("utf-8")) == 8_192

    with pytest.raises(ValueError, match="source exceeds"):
        EvidenceReference(
            kind=EvidenceKind.KG_RESOURCE,
            source="x" * 1_025,
            stable_id="ex:item",
            retrieval=_metadata(),
            validation_status=EvidenceValidationStatus.VALIDATED,
        )
    with pytest.raises(ValueError, match="stable_id exceeds"):
        _reference("é" * 4_097)


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("kind", "kg_edge", TypeError),
        ("source", " ", ValueError),
        ("stable_id", " ", ValueError),
        ("retrieval", None, TypeError),
        ("validation_status", "validated", TypeError),
    ],
)
def test_reference_rejects_wrong_enums_blank_strings_and_bad_retrieval(
    field: str,
    value: object,
    error_type: type[Exception],
) -> None:
    kwargs: dict[str, object] = {
        "kind": EvidenceKind.KG_EDGE,
        "source": "fixture-kg",
        "stable_id": "ex:EvidenceEdge_001",
        "retrieval": _metadata(),
        "validation_status": EvidenceValidationStatus.VALIDATED,
    }
    kwargs[field] = value

    with pytest.raises(error_type):
        EvidenceReference(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_container", [{_reference()}, "ex:EvidenceEdge_001", None])
def test_catalog_rejects_invalid_reference_containers(bad_container: object) -> None:
    with pytest.raises(TypeError, match="references"):
        EvidenceCatalog(bad_container)  # type: ignore[arg-type]


def test_catalog_rejects_duplicate_stable_ids_deterministically() -> None:
    with pytest.raises(EvidenceReferenceResolutionError) as exc_info:
        EvidenceCatalog((_reference("ex:dup"), _reference("ex:dup")))

    assert exc_info.value.code is EvidenceReferenceResolutionCode.DUPLICATE_EVIDENCE_ID
    assert exc_info.value.stable_id == "ex:dup"


def test_catalog_preserves_requested_order_when_resolving_known_ids() -> None:
    edge = _reference("ex:EvidenceEdge_001")
    chunk = _reference("ex:SOP_Chunk_7", kind=EvidenceKind.DOCUMENT_CHUNK)
    resource = _reference("ex:Pump_12", kind=EvidenceKind.KG_RESOURCE)
    catalog = EvidenceCatalog((edge, chunk, resource))

    resolved = catalog.resolve(("ex:SOP_Chunk_7", "ex:EvidenceEdge_001"))

    assert resolved == (chunk, edge)
    assert catalog.references == (edge, chunk, resource)


@pytest.mark.parametrize("bad_ids", [{"ex:EvidenceEdge_001"}, "ex:EvidenceEdge_001", None])
def test_catalog_rejects_invalid_id_containers(bad_ids: object) -> None:
    catalog = EvidenceCatalog((_reference(),))

    with pytest.raises(TypeError, match="stable_ids"):
        catalog.resolve(bad_ids)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_id", ["", "  ", 12])
def test_catalog_rejects_blank_or_non_string_requested_ids(bad_id: object) -> None:
    catalog = EvidenceCatalog((_reference(),))

    with pytest.raises((TypeError, ValueError)):
        catalog.resolve((bad_id,))  # type: ignore[arg-type]


def test_unknown_evidence_id_raises_typed_error_and_returns_no_support() -> None:
    catalog = EvidenceCatalog((_reference("ex:known"),))

    with pytest.raises(EvidenceReferenceResolutionError) as exc_info:
        catalog.resolve_validated_support(("ex:known", "ex:unknown"))

    assert exc_info.value.code is EvidenceReferenceResolutionCode.UNKNOWN_EVIDENCE_ID
    assert exc_info.value.stable_id == "ex:unknown"


@pytest.mark.parametrize(
    "status",
    [EvidenceValidationStatus.UNVALIDATED, EvidenceValidationStatus.INVALID],
)
def test_unvalidated_or_invalid_references_cannot_be_returned_as_valid_support(
    status: EvidenceValidationStatus,
) -> None:
    catalog = EvidenceCatalog((_reference("ex:not-valid", validation_status=status),))

    with pytest.raises(EvidenceReferenceResolutionError) as exc_info:
        catalog.resolve_validated_support(("ex:not-valid",))

    assert exc_info.value.code is EvidenceReferenceResolutionCode.EVIDENCE_NOT_VALIDATED
    assert exc_info.value.stable_id == "ex:not-valid"


def test_lookup_can_return_unvalidated_reference_without_calling_it_valid_support() -> None:
    ref = _reference("ex:review-needed", validation_status=EvidenceValidationStatus.UNVALIDATED)
    catalog = EvidenceCatalog((ref,))

    assert catalog.resolve(("ex:review-needed",)) == (ref,)


def test_resolution_error_is_typed_slotted_and_deterministic() -> None:
    error = EvidenceReferenceResolutionError(
        EvidenceReferenceResolutionCode.UNKNOWN_EVIDENCE_ID,
        "ex:missing",
    )

    assert error.code is EvidenceReferenceResolutionCode.UNKNOWN_EVIDENCE_ID
    assert error.stable_id == "ex:missing"
    assert str(error) == "unknown_evidence_id: ex:missing"
    assert error.args == ("unknown_evidence_id: ex:missing",)
