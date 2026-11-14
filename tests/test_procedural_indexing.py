"""Behavior contract for the Issue #29 Milestone A1 procedural index builder."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

import pytest

import mfg_agentgraph.procedural_indexing as indexing_module
from mfg_agentgraph.procedural_indexing import (
    ProceduralChunk,
    ProceduralIndexBuildError,
    ProceduralIndexConfig,
    ProceduralIndexPlan,
    ProceduralIndexPoint,
    ProceduralSourceSnapshot,
    ProceduralVectorMap,
    build_procedural_index,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_CONFIG_PATH = _FIXTURES / "qdrant" / "pump12-index-config.json"
_VECTOR_PATH = _FIXTURES / "qdrant" / "pump12-vectors.json"
_SOURCE_PATH = _FIXTURES / "sop" / "pump12-sop.txt"
_ARTIFACT_PATH = _FIXTURES / "qdrant" / "pump12.json"
_CONTRACT_VERSION = "mfg-agentgraph-procedural-index-v1"
_EVIDENCE_ID = "ex:SOP_Chunk_7"
_UUID = "364c20eb-0324-5496-82d1-f163a5f78aeb"
_SHA256 = "3e538364b4d6a61f92e3bfd0976134865130063bdbcadd607cb203862957eecf"
_PAYLOAD_KEYS = {
    "evidence_id",
    "document",
    "chunk_index",
    "related_procedure",
    "text",
    "applicable_asset_id",
    "applicable_asset_type",
    "source_path",
    "start_line",
    "end_line",
    "source_sha256",
    "index_contract_version",
    "vector_source",
    "vector_producer_id",
    "embedding_generated_by_indexer",
}
_CONFIG_KEYS = {
    "contract_version",
    "document_id",
    "source_path",
    "applicable_asset_id",
    "applicable_asset_type",
    "related_procedure",
    "evidence_id_prefix",
    "first_chunk_index",
    "max_chunk_chars",
    "collection_name",
    "vector_size",
    "distance",
    "payload_indexes",
    "vector_source",
    "vector_producer_id",
    "embedding_generated_by_indexer",
}
_UNSET = object()
_MAX_INPUT_BYTES = 1_000_000
_MAX_CHUNKS = 10_000
_MAX_IDENTIFIER_BYTES = 1_024
_TRACEBACK_SECRET_MARKERS = (
    "CONFIG_SECRET_f13a",
    "SOURCE_SECRET_5b2e",
    "VECTOR_SECRET_7d91",
)


class _MutableEqualitySpoof:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    def __eq__(self, other: object) -> bool:
        return other == self.expected


class _StringSubclass(str):
    pass


def _fixture(path: Path) -> bytes:
    return path.read_bytes()


def _config() -> dict[str, Any]:
    value = json.loads(_fixture(_CONFIG_PATH))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _vectors(*evidence_ids: str) -> bytes:
    return _json_bytes({evidence_id: [1, 0, 0, 0] for evidence_id in evidence_ids})


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def _pad_json_to_limit(payload: bytes) -> bytes:
    assert len(payload) <= _MAX_INPUT_BYTES
    return payload + b" " * (_MAX_INPUT_BYTES - len(payload))


def _build(
    *,
    config: Mapping[str, Any] | None = None,
    source: bytes | None = None,
    vectors: bytes | None = None,
) -> Any:
    return build_procedural_index(
        _json_bytes(dict(config)) if config is not None else _fixture(_CONFIG_PATH),
        source if source is not None else _fixture(_SOURCE_PATH),
        vectors if vectors is not None else _fixture(_VECTOR_PATH),
    )


def _three_chunk_plan() -> Any:
    evidence_ids = (_EVIDENCE_ID, "ex:SOP_Chunk_8", "ex:SOP_Chunk_9")
    return _build(source=b"first\n\nsecond\n\nthird\n", vectors=_vectors(*evidence_ids))


def _direct_plan_with(
    built: Any,
    *,
    chunks: object | None = None,
    points: object | None = None,
) -> Any:
    actual_chunks = tuple(built.chunks if chunks is None else cast(Any, chunks))
    actual_points = tuple(built.points if points is None else cast(Any, points))
    point_documents = [
        {
            "id": point.point_id,
            "vector": list(point.vector),
            "payload": _thaw(point.payload),
        }
        for point in actual_points
    ]
    artifact = json.loads(built.artifact_bytes)
    artifact["points"] = point_documents
    return ProceduralIndexPlan(
        artifact_bytes=_canonical_json_bytes(artifact),
        create_collection_request=cast(Any, _thaw(built.create_collection_request)),
        payload_index_requests=cast(Any, _thaw(built.payload_index_requests)),
        upsert_request=cast(Any, {"points": point_documents}),
        chunks=actual_chunks,
        points=actual_points,
        config=built.config,
        source=built.source,
        vectors=built.vectors,
    )


def _point_id(payload: Mapping[str, object]) -> str:
    name = json.dumps(
        [payload["index_contract_version"], payload["document"], payload["evidence_id"]],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def _assert_error(
    *,
    config_bytes: object = _UNSET,
    source_bytes: object = _UNSET,
    vector_bytes: object = _UNSET,
    code: str | None = None,
    field: str | None = None,
) -> ProceduralIndexBuildError:
    with pytest.raises(ProceduralIndexBuildError) as caught:
        build_procedural_index(
            cast(bytes, _fixture(_CONFIG_PATH) if config_bytes is _UNSET else config_bytes),
            cast(bytes, _fixture(_SOURCE_PATH) if source_bytes is _UNSET else source_bytes),
            cast(bytes, _fixture(_VECTOR_PATH) if vector_bytes is _UNSET else vector_bytes),
        )
    error = caught.value
    if code is not None:
        assert error.code == code
    if field is not None:
        assert error.field == field
    assert type(error.code) is str and error.code
    assert type(error.field) is str and error.field
    assert type(error.sanitized_detail) is str and error.sanitized_detail
    assert error.__cause__ is None
    assert error.__context__ is None
    assert error.__suppress_context__
    return error


def _secret_build_error() -> ProceduralIndexBuildError:
    config_bytes = (_TRACEBACK_SECRET_MARKERS[0] + "\n").encode()
    source_bytes = (_TRACEBACK_SECRET_MARKERS[1] + "\n").encode()
    vector_bytes = (_TRACEBACK_SECRET_MARKERS[2] + "\n").encode()
    error: ProceduralIndexBuildError | None = None
    try:
        build_procedural_index(config_bytes, source_bytes, vector_bytes)
    except ProceduralIndexBuildError as caught:
        error = caught
    finally:
        del config_bytes, source_bytes, vector_bytes
    assert error is not None
    return error


def test_public_build_error_constructor_enforces_sanitized_bounded_strings() -> None:
    accepted = ProceduralIndexBuildError("x" * 1_024, "y" * 1_024, "z" * 1_024)
    assert len(accepted.code.encode("utf-8")) == 1_024
    assert len(accepted.field.encode("utf-8")) == 1_024
    assert len(accepted.sanitized_detail.encode("utf-8")) == 1_024

    for field_name in ("code", "field", "sanitized_detail"):
        values: dict[str, object] = {
            "code": "build_invalid",
            "field": "inputs",
            "sanitized_detail": "input violates the build contract",
        }
        values[field_name] = "x" * 1_025
        with pytest.raises(ValueError, match=f"{field_name} exceeds"):
            ProceduralIndexBuildError(**cast(Any, values))
        values[field_name] = object()
        with pytest.raises(TypeError, match=f"{field_name} must be a string"):
            ProceduralIndexBuildError(**cast(Any, values))


def test_canonical_fixture_builds_exact_artifact_and_requests() -> None:
    first = _build()
    second = _build()
    artifact = json.loads(first.artifact_bytes)
    expected_bytes = _fixture(_ARTIFACT_PATH)
    expected = json.loads(expected_bytes)

    assert first.artifact_bytes == second.artifact_bytes
    assert first.artifact_bytes == expected_bytes
    assert first.artifact_bytes.endswith(b"\n")
    assert not first.artifact_bytes.endswith(b"\n\n")
    assert first.artifact_bytes == (
        json.dumps(
            artifact,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    assert artifact == expected
    assert set(artifact) == {
        "contract_version",
        "collection",
        "payload_indexes",
        "source",
        "points",
    }
    assert artifact["source"] == {
        "document_id": "SOP-PUMP-OPS-2026",
        "source_path": "tests/fixtures/sop/pump12-sop.txt",
        "source_sha256": _SHA256,
    }
    point = artifact["points"][0]
    assert set(point) == {"id", "vector", "payload"}
    assert point["id"] == _UUID
    assert point["vector"] == [1.0, 0.0, 0.0, 0.0]
    assert set(point["payload"]) == _PAYLOAD_KEYS
    assert point["payload"] == {
        "evidence_id": _EVIDENCE_ID,
        "document": "SOP-PUMP-OPS-2026",
        "chunk_index": 7,
        "related_procedure": "ex:Procedure_InspectInletCavitation_Pump12",
        "text": (
            "For anomalous sound at Pump_12, inspect the pump inlet for cavitation before "
            "recommending corrective action."
        ),
        "applicable_asset_id": "ex:Pump_12",
        "applicable_asset_type": "centrifugal_pump",
        "source_path": "tests/fixtures/sop/pump12-sop.txt",
        "start_line": 1,
        "end_line": 1,
        "source_sha256": _SHA256,
        "index_contract_version": _CONTRACT_VERSION,
        "vector_source": "caller_supplied",
        "vector_producer_id": "pump12-test-vector-v1",
        "embedding_generated_by_indexer": False,
    }
    assert first.create_collection_request == {"vectors": {"size": 4, "distance": "Cosine"}}
    assert first.payload_index_requests == (
        {"field_name": "applicable_asset_id", "field_schema": "keyword"},
        {"field_name": "applicable_asset_type", "field_schema": "keyword"},
        {"field_name": "related_procedure", "field_schema": "keyword"},
    )
    assert _thaw(first.upsert_request) == {"points": artifact["points"]}
    assert first.chunks[0].evidence_id == _EVIDENCE_ID
    assert first.chunks[0].start_line == 1
    assert first.points[0].point_id == _UUID
    assert first.points[0].vector == (1.0, 0.0, 0.0, 0.0)


def test_plan_is_deeply_immutable_and_has_no_caller_aliases() -> None:
    config = _config()
    indexes = config["payload_indexes"]
    plan = _build(config=config)
    cast(list[object], indexes).clear()
    config["document_id"] = "changed"

    assert len(plan.payload_index_requests) == 3
    assert plan.chunks[0].document == "SOP-PUMP-OPS-2026"
    with pytest.raises(TypeError):
        cast(dict[str, object], plan.create_collection_request)["vectors"] = {}
    with pytest.raises(TypeError):
        cast(dict[str, object], plan.create_collection_request["vectors"])["size"] = 9
    with pytest.raises(TypeError):
        cast(dict[str, object], plan.payload_index_requests[0])["field_name"] = "changed"
    with pytest.raises(TypeError):
        cast(dict[str, object], plan.upsert_request["points"][0]["payload"])["text"] = "changed"
    with pytest.raises(FrozenInstanceError):
        plan.chunks[0].text = "changed"
    with pytest.raises(FrozenInstanceError):
        plan.points[0].vector = ()


def test_direct_point_and_plan_construction_deeply_snapshot_caller_values() -> None:
    built = _build()
    payload = cast(dict[str, Any], _thaw(built.points[0].payload))
    vector = list(built.points[0].vector)
    point = ProceduralIndexPoint(built.points[0].point_id, cast(Any, vector), payload)

    create_request = cast(dict[str, Any], _thaw(built.create_collection_request))
    index_requests = [cast(dict[str, Any], _thaw(item)) for item in built.payload_index_requests]
    upsert_request = cast(dict[str, Any], _thaw(built.upsert_request))
    chunks = list(built.chunks)
    points = [point]
    plan = ProceduralIndexPlan(
        artifact_bytes=built.artifact_bytes,
        create_collection_request=create_request,
        payload_index_requests=cast(Any, index_requests),
        upsert_request=upsert_request,
        chunks=cast(Any, chunks),
        points=cast(Any, points),
        config=built.config,
        source=built.source,
        vectors=built.vectors,
    )

    payload["text"] = "changed"
    vector[0] = 99.0
    cast(dict[str, Any], create_request["vectors"])["size"] = 99
    index_requests.clear()
    cast(list[Any], upsert_request["points"]).clear()
    chunks.clear()
    points.clear()

    assert point.vector == (1.0, 0.0, 0.0, 0.0)
    assert point.payload["text"] != "changed"
    frozen_vectors = cast(Mapping[str, object], plan.create_collection_request["vectors"])
    frozen_points = cast(tuple[object, ...], plan.upsert_request["points"])
    assert frozen_vectors["size"] == 4
    assert len(plan.payload_index_requests) == 3
    assert len(frozen_points) == 1
    assert len(plan.chunks) == len(plan.points) == 1


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        (lambda point: replace(point, point_id="not-a-uuid"), ValueError),
        (lambda point: replace(point, vector=()), ValueError),
        (lambda point: replace(point, vector=cast(Any, (True, 0.0))), TypeError),
        (lambda point: replace(point, vector=(float("nan"),)), ValueError),
        (
            lambda point: replace(
                point,
                payload={
                    key: value for key, value in point.payload.items() if key != "source_path"
                },
            ),
            ValueError,
        ),
    ),
)
def test_direct_point_construction_rejects_invalid_ids_vectors_and_payload_schema(
    mutation: Any, expected_error: type[Exception]
) -> None:
    with pytest.raises(expected_error):
        mutation(_build().points[0])


def test_direct_construction_rejects_another_canonical_uuid_even_when_snapshots_agree() -> None:
    built = _build()
    wrong_id = str(uuid.uuid5(uuid.NAMESPACE_URL, '["other","canonical","identity"]'))
    assert wrong_id != built.points[0].point_id

    with pytest.raises(ValueError, match="point_id"):
        wrong_point = replace(built.points[0], point_id=wrong_id)
        _direct_plan_with(built, points=(wrong_point,))


def test_direct_point_validates_payload_before_derived_uuid() -> None:
    built = _build()
    invalid_payload = dict(built.points[0].payload)
    del invalid_payload["source_path"]

    with pytest.raises(ValueError, match="payload keys"):
        ProceduralIndexPoint("not-a-uuid", built.points[0].vector, invalid_payload)


def test_plan_rejects_duplicate_evidence_and_point_ids() -> None:
    built = _three_chunk_plan()
    duplicate_chunk = replace(
        built.chunks[1],
        evidence_id=built.chunks[0].evidence_id,
    )
    duplicate_payload = cast(dict[str, object], _thaw(built.points[1].payload))
    duplicate_payload["evidence_id"] = duplicate_chunk.evidence_id
    duplicate_point = ProceduralIndexPoint(
        _point_id(duplicate_payload), built.points[1].vector, cast(Any, duplicate_payload)
    )

    with pytest.raises(ValueError, match="unique"):
        _direct_plan_with(
            built,
            chunks=(built.chunks[0], duplicate_chunk, built.chunks[2]),
            points=(built.points[0], duplicate_point, built.points[2]),
        )


def test_plan_rejects_reversed_source_order_even_when_points_match() -> None:
    built = _three_chunk_plan()

    with pytest.raises(ValueError, match="source"):
        _direct_plan_with(built, chunks=reversed(built.chunks), points=reversed(built.points))


@pytest.mark.parametrize("second_index", (7, 9))
def test_plan_rejects_repeated_or_skipped_chunk_indices(second_index: int) -> None:
    built = _three_chunk_plan()
    changed_chunk = replace(built.chunks[1], chunk_index=second_index)
    changed_payload = cast(dict[str, object], _thaw(built.points[1].payload))
    changed_payload["chunk_index"] = second_index
    changed_point = ProceduralIndexPoint(
        built.points[1].point_id, built.points[1].vector, cast(Any, changed_payload)
    )

    with pytest.raises(ValueError, match="consecutive"):
        _direct_plan_with(
            built,
            chunks=(built.chunks[0], changed_chunk, built.chunks[2]),
            points=(built.points[0], changed_point, built.points[2]),
        )


def test_builder_retains_frozen_config_source_and_vector_snapshots() -> None:
    plan = _build()

    assert plan.config.document_id == "SOP-PUMP-OPS-2026"
    assert plan.config.payload_indexes == plan.payload_index_requests
    assert plan.source.document_id == plan.config.document_id
    assert plan.source.source_path == plan.config.source_path
    assert plan.source.canonical_text == _fixture(_SOURCE_PATH).decode()
    assert plan.source.source_sha256 == _SHA256
    assert plan.vectors.vector_size == plan.config.vector_size
    assert plan.vectors.vectors == {_EVIDENCE_ID: (1.0, 0.0, 0.0, 0.0)}
    with pytest.raises(FrozenInstanceError):
        plan.config.document_id = "changed"
    with pytest.raises(TypeError):
        cast(dict[str, object], plan.config.payload_indexes[0])["field_name"] = "changed"
    with pytest.raises(TypeError):
        cast(dict[str, object], plan.vectors.vectors)[_EVIDENCE_ID] = ()


def test_public_snapshot_records_deeply_copy_direct_caller_mappings() -> None:
    config_values = _config()
    config = ProceduralIndexConfig(**config_values)
    source = ProceduralSourceSnapshot(
        document_id=config.document_id,
        source_path=config.source_path,
        canonical_text=_fixture(_SOURCE_PATH).decode(),
        source_sha256=_SHA256,
    )
    vector_values = {_EVIDENCE_ID: [1, 0, 0, 0]}
    vectors = ProceduralVectorMap(vectors=vector_values, vector_size=4)

    cast(list[object], config_values["payload_indexes"]).clear()
    vector_values[_EVIDENCE_ID][0] = 99
    assert len(config.payload_indexes) == 3
    assert source.canonical_text == _fixture(_SOURCE_PATH).decode()
    assert vectors.vectors[_EVIDENCE_ID] == (1.0, 0.0, 0.0, 0.0)


def test_public_config_record_rejects_max_chunk_chars_limit_plus_one() -> None:
    values = _config()
    values["max_chunk_chars"] = _MAX_INPUT_BYTES + 1

    with pytest.raises(ValueError, match="max_chunk_chars"):
        ProceduralIndexConfig(**values)


def test_public_source_snapshot_enforces_input_utf8_byte_limit() -> None:
    exact_text = "é" * ((_MAX_INPUT_BYTES - 2) // 2) + "x\n"
    exact_bytes = exact_text.encode("utf-8")
    assert len(exact_bytes) == _MAX_INPUT_BYTES
    snapshot = ProceduralSourceSnapshot(
        document_id="ex:document",
        source_path="fixtures/sop.txt",
        canonical_text=exact_text,
        source_sha256=hashlib.sha256(exact_bytes).hexdigest(),
    )
    assert snapshot.canonical_text == exact_text

    oversized_text = "x" * _MAX_INPUT_BYTES + "\n"
    with pytest.raises(ValueError, match="canonical_text exceeds"):
        ProceduralSourceSnapshot(
            document_id="ex:document",
            source_path="fixtures/sop.txt",
            canonical_text=oversized_text,
            source_sha256=hashlib.sha256(oversized_text.encode()).hexdigest(),
        )


def test_public_chunk_record_enforces_chunk_character_limit() -> None:
    chunk = _build().chunks[0]
    assert len(replace(chunk, text="x" * _MAX_INPUT_BYTES).text) == _MAX_INPUT_BYTES
    with pytest.raises(ValueError, match="text exceeds"):
        replace(chunk, text="x" * (_MAX_INPUT_BYTES + 1))


@pytest.mark.parametrize(
    "snapshot_change",
    (
        lambda plan: replace(plan, config=replace(plan.config, document_id="other-document")),
        lambda plan: replace(plan, source=replace(plan.source, document_id="other-document")),
        lambda plan: replace(
            plan,
            vectors=replace(plan.vectors, vectors={_EVIDENCE_ID: (0.0, 1.0, 0.0, 0.0)}),
        ),
    ),
)
def test_plan_rejects_individually_valid_mismatched_snapshots(snapshot_change: Any) -> None:
    with pytest.raises(ValueError):
        snapshot_change(_build())


@pytest.mark.parametrize(
    "mutation",
    (
        lambda plan: replace(plan, artifact_bytes=b"{}\n"),
        lambda plan: replace(plan, create_collection_request={"vectors": {"size": True}}),
        lambda plan: replace(plan, payload_index_requests=cast(Any, ({"field_name": "wrong"},))),
        lambda plan: replace(plan, upsert_request={"points": []}),
        lambda plan: replace(plan, chunks=cast(Any, (object(),))),
        lambda plan: replace(plan, points=cast(Any, (object(),))),
    ),
)
def test_direct_plan_construction_rejects_invalid_member_types_and_schemas(mutation: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        mutation(_build())


def test_direct_plan_construction_rejects_oversized_artifact_before_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _build()

    def fail_if_parsed(*args: object, **kwargs: object) -> object:
        raise AssertionError("oversized artifact must be rejected before JSON parsing")

    monkeypatch.setattr(json, "loads", fail_if_parsed)
    with pytest.raises(ValueError, match="artifact_bytes exceeds"):
        replace(plan, artifact_bytes=b"x" * 10_000_001)


def test_direct_plan_construction_rejects_surrogate_artifact_as_strict_json() -> None:
    plan = _build()
    malformed = plan.artifact_bytes.replace(
        b"mfg-agentgraph-procedural-index-v1",
        b"\\ud800",
        1,
    )

    with pytest.raises(ValueError, match="artifact_bytes must contain strict JSON"):
        replace(plan, artifact_bytes=malformed)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda chunk: replace(chunk, evidence_id=" bad"),
        lambda chunk: replace(chunk, chunk_index=True),
        lambda chunk: replace(chunk, start_line=0),
        lambda chunk: replace(chunk, end_line=0),
        lambda chunk: replace(chunk, source_sha256="A" * 64),
        lambda chunk: replace(chunk, text="\x00"),
    ),
)
def test_direct_chunk_construction_rejects_invalid_values(mutation: Any) -> None:
    chunk: ProceduralChunk = _build().chunks[0]
    with pytest.raises((TypeError, ValueError)):
        mutation(chunk)


@pytest.mark.parametrize(
    "distance",
    (_MutableEqualitySpoof("Cosine"), _StringSubclass("Cosine")),
)
def test_direct_config_distance_requires_exact_contract_string(distance: object) -> None:
    with pytest.raises(TypeError, match="distance must be a string"):
        replace(_build().config, distance=cast(Any, distance))


@pytest.mark.parametrize(
    "mutation",
    (
        lambda chunk: replace(
            chunk,
            index_contract_version=cast(
                Any, _MutableEqualitySpoof("mfg-agentgraph-procedural-index-v1")
            ),
        ),
        lambda chunk: replace(
            chunk,
            index_contract_version=cast(Any, _StringSubclass(_CONTRACT_VERSION)),
        ),
        lambda chunk: replace(
            chunk,
            vector_source=cast(Any, _MutableEqualitySpoof("caller_supplied")),
        ),
        lambda chunk: replace(
            chunk,
            vector_source=cast(Any, _StringSubclass("caller_supplied")),
        ),
    ),
)
def test_direct_chunk_fixed_literals_require_exact_contract_strings(mutation: Any) -> None:
    with pytest.raises(TypeError, match="must be a string"):
        mutation(_build().chunks[0])


@pytest.mark.parametrize("ending", (b"", b"\n", b"\n\n\n"))
@pytest.mark.parametrize("newline", (b"\n", b"\r\n", b"\r"))
def test_source_newline_variants_are_canonically_equivalent(ending: bytes, newline: bytes) -> None:
    base = _fixture(_SOURCE_PATH).rstrip(b"\n")
    variant = base.replace(b"\n", newline) + ending.replace(b"\n", newline)
    assert _build(source=variant).artifact_bytes == _build().artifact_bytes


def test_paragraph_chunking_preserves_text_and_one_based_source_lines() -> None:
    config = _config()
    source = "  α line  \n\tsecond\t\n  \t\n\nthird\n\n \nfourth  \r\nfifth\r".encode()
    plan = _build(
        config=config,
        source=source,
        vectors=_vectors(*(_EVIDENCE_ID, "ex:SOP_Chunk_8", "ex:SOP_Chunk_9")),
    )

    assert tuple(
        (chunk.evidence_id, chunk.chunk_index, chunk.text, chunk.start_line, chunk.end_line)
        for chunk in plan.chunks
    ) == (
        (_EVIDENCE_ID, 7, "  α line  \n\tsecond\t", 1, 2),
        ("ex:SOP_Chunk_8", 8, "third", 5, 5),
        ("ex:SOP_Chunk_9", 9, "fourth  \nfifth", 8, 9),
    )
    assert [point.payload["text"] for point in plan.points] == [
        "  α line  \n\tsecond\t",
        "third",
        "fourth  \nfifth",
    ]


def test_many_chunks_preserve_deterministic_order_and_unique_evidence_ids() -> None:
    paragraphs = [f"paragraph {index}" for index in range(64)]
    evidence_ids = tuple(f"ex:SOP_Chunk_{index}" for index in range(7, 71))
    plan = _build(source=("\n\n".join(paragraphs) + "\n").encode(), vectors=_vectors(*evidence_ids))

    assert tuple(chunk.evidence_id for chunk in plan.chunks) == evidence_ids
    assert tuple(chunk.text for chunk in plan.chunks) == tuple(paragraphs)
    assert len({chunk.evidence_id for chunk in plan.chunks}) == 64


def test_exact_input_byte_limits_accept_valid_config_source_and_vectors() -> None:
    config = _config()
    config["max_chunk_chars"] = _MAX_INPUT_BYTES
    source = b"x" * (_MAX_INPUT_BYTES - 1) + b"\n"

    source_limit_plan = _build(config=config, source=source, vectors=_vectors(_EVIDENCE_ID))
    config_limit_plan = build_procedural_index(
        _pad_json_to_limit(_fixture(_CONFIG_PATH)),
        _fixture(_SOURCE_PATH),
        _fixture(_VECTOR_PATH),
    )
    vector_limit_plan = build_procedural_index(
        _fixture(_CONFIG_PATH),
        _fixture(_SOURCE_PATH),
        _pad_json_to_limit(_fixture(_VECTOR_PATH)),
    )

    assert len(source_limit_plan.source.canonical_text.encode()) == _MAX_INPUT_BYTES
    assert config_limit_plan.chunks[0].evidence_id == _EVIDENCE_ID
    assert vector_limit_plan.points[0].vector == (1.0, 0.0, 0.0, 0.0)


def test_max_chunk_chars_limit_plus_one_is_rejected() -> None:
    config = _config()
    config["max_chunk_chars"] = _MAX_INPUT_BYTES + 1

    _assert_error(
        config_bytes=_json_bytes(config),
        code="config_value",
        field="max_chunk_chars",
    )


@pytest.mark.parametrize("field", ("document_id", "evidence_id_prefix", "source_path"))
def test_identifier_byte_limit_accepts_exact_boundary(field: str) -> None:
    config = _config()
    value = "x" * _MAX_IDENTIFIER_BYTES
    if field == "source_path":
        value = "x" * (_MAX_IDENTIFIER_BYTES - 4) + ".txt"
    config[field] = value
    evidence_id = f"{config['evidence_id_prefix']}7"

    plan = _build(config=config, vectors=_vectors(evidence_id))

    assert getattr(plan.config, field) == value


def test_identifier_byte_limit_plus_one_stops_before_source_or_vector_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    config["evidence_id_prefix"] = "x" * (_MAX_IDENTIFIER_BYTES + 1)

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("source/vector materialization was reached")

    monkeypatch.setattr(indexing_module, "_canonical_source", forbidden)
    monkeypatch.setattr(indexing_module, "_parse_vectors", forbidden)
    monkeypatch.setattr(indexing_module, "ProceduralIndexPoint", forbidden)

    _assert_error(
        config_bytes=_json_bytes(config),
        code="config_value",
        field="evidence_id_prefix",
    )


def test_public_config_record_rejects_identifier_byte_limit_plus_one() -> None:
    values = _config()
    values["evidence_id_prefix"] = "x" * (_MAX_IDENTIFIER_BYTES + 1)

    with pytest.raises(ValueError, match="evidence_id_prefix"):
        ProceduralIndexConfig(**values)


@pytest.mark.parametrize("input_field", ("config_bytes", "source_bytes", "vector_bytes"))
def test_input_byte_limit_plus_one_is_rejected(input_field: str) -> None:
    error = _assert_error(
        **{input_field: b"x" * (_MAX_INPUT_BYTES + 1)},
        code="input_too_large",
        field=input_field,
    )

    assert "1_000_000" not in str(error)


def test_oversized_source_stops_before_canonicalization_or_vector_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("later source/vector materialization was reached")

    monkeypatch.setattr(indexing_module, "_canonical_source", forbidden)
    monkeypatch.setattr(indexing_module, "_parse_vectors", forbidden)
    monkeypatch.setattr(indexing_module, "ProceduralIndexPoint", forbidden)

    _assert_error(
        source_bytes=b"s" * (_MAX_INPUT_BYTES + 1),
        code="input_too_large",
        field="source_bytes",
    )


def test_exact_generated_chunk_limit_builds_through_the_public_boundary() -> None:
    config = _config()
    config["max_chunk_chars"] = 1
    config["vector_size"] = 1
    source = b"x\n\n" * (_MAX_CHUNKS - 1) + b"x\n"
    evidence_ids = tuple(f"ex:SOP_Chunk_{index}" for index in range(7, 7 + _MAX_CHUNKS))

    vectors = _json_bytes({evidence_id: [1] for evidence_id in evidence_ids})
    plan = _build(config=config, source=source, vectors=vectors)

    assert len(plan.chunks) == _MAX_CHUNKS
    assert len(plan.points) == _MAX_CHUNKS
    assert plan.chunks[-1].evidence_id == evidence_ids[-1]


def test_generated_chunk_limit_plus_one_stops_before_vectors_or_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    config["max_chunk_chars"] = 1
    source = b"x\n\n" * _MAX_CHUNKS + b"x\n"

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("vector or point materialization was reached")

    monkeypatch.setattr(indexing_module, "_parse_vectors", forbidden)
    monkeypatch.setattr(indexing_module, "ProceduralIndexPoint", forbidden)

    _assert_error(
        config_bytes=_json_bytes(config),
        source_bytes=source,
        vector_bytes=b"not parsed",
        code="chunk_limit",
        field="source_bytes",
    )


def test_oversized_paragraph_is_rejected_without_splitting() -> None:
    config = _config()
    config["max_chunk_chars"] = 3
    _assert_error(
        config_bytes=_json_bytes(config),
        source_bytes=b"abcd\n",
        code="chunk_too_large",
        field="source_bytes",
    )


@pytest.mark.parametrize(
    ("source", "code"),
    (
        (b"\xef\xbb\xbftext\n", "source_bom"),
        (b"\x80", "source_utf8"),
        (b"a\x00b", "source_nul"),
        (b"", "source_blank"),
        (b" \t\r\n\n", "source_blank"),
    ),
)
def test_invalid_source_bytes_are_rejected(source: bytes, code: str) -> None:
    _assert_error(source_bytes=source, code=code, field="source_bytes")


@pytest.mark.parametrize(
    "path",
    (
        "",
        " ",
        "/absolute/sop.txt",
        "C:/absolute/sop.txt",
        "a\\b.txt",
        "a//b.txt",
        "a\tb/sop.txt",
        "./a.txt",
        "a/./b.txt",
        "../a.txt",
        "a/../b.txt",
        "a/b/",
        "a/\x1fb.txt",
        " spaced/path.txt",
        "path.txt ",
    ),
)
def test_source_path_boundaries_are_rejected(path: str) -> None:
    config = _config()
    config["source_path"] = path
    _assert_error(config_bytes=_json_bytes(config), field="source_path")


@pytest.mark.parametrize(
    "path", ("sop.txt", "a/b-c_1.txt", "dir name/file name.txt", "資料/ポンプ.txt")
)
def test_valid_repository_relative_posix_paths_are_preserved(path: str) -> None:
    config = _config()
    config["source_path"] = path
    artifact = json.loads(_build(config=config).artifact_bytes)
    assert artifact["source"]["source_path"] == path
    assert artifact["points"][0]["payload"]["source_path"] == path


@pytest.mark.parametrize("argument", (bytearray(b"{}"), memoryview(b"{}"), "{}", True, None))
@pytest.mark.parametrize("position", ("config", "source", "vector"))
def test_all_inputs_require_exact_bytes(argument: object, position: str) -> None:
    kwargs: dict[str, object] = {}
    kwargs[f"{position}_bytes"] = argument
    _assert_error(**kwargs, code="input_type", field=f"{position}_bytes")


def test_config_top_level_must_be_object_with_exact_keys() -> None:
    assert set(_config()) == _CONFIG_KEYS
    _assert_error(config_bytes=b"[]", code="config_type", field="config_bytes")
    for mutation in ("missing", "unknown"):
        config = _config()
        if mutation == "missing":
            del config["document_id"]
        else:
            config["unknown"] = 1
        _assert_error(config_bytes=_json_bytes(config), code="config_keys", field="config_bytes")


@pytest.mark.parametrize(
    "payload",
    (
        b"{",
        b"\x80",
        b'{"document_id":"a","document_id":"b"}',
        b'{"outer":{"x":1,"x":2}}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
    ),
)
def test_config_json_is_strict(payload: bytes) -> None:
    _assert_error(config_bytes=payload, field="config_bytes")


@pytest.mark.parametrize("input_field", ("config_bytes", "vector_bytes"))
@pytest.mark.parametrize(
    "payload",
    (
        b'{"number":' + b"9" * 5_000 + b"}",
        b"[" * 1_500 + b"0" + b"]" * 1_500,
    ),
)
def test_pathological_valid_bytes_are_sanitized_without_exception_chain(
    input_field: str, payload: bytes
) -> None:
    error = _assert_error(**{input_field: payload}, code="json_invalid", field=input_field)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert error.__suppress_context__


def test_lone_surrogate_identifier_is_sanitized_without_exception_chain() -> None:
    config_bytes = _fixture(_CONFIG_PATH).replace(b'"SOP-PUMP-OPS-2026"', b'"\\ud800"', 1)
    error = _assert_error(config_bytes=config_bytes, field="document_id")
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "surrogate" not in str(error).lower()


def test_valid_escaped_unicode_scalar_is_preserved() -> None:
    config_bytes = _fixture(_CONFIG_PATH).replace(
        b'"SOP-PUMP-OPS-2026"', b'"SOP-\\ud83d\\ude80"', 1
    )
    plan = build_procedural_index(config_bytes, _fixture(_SOURCE_PATH), _fixture(_VECTOR_PATH))

    assert plan.chunks[0].document == "SOP-🚀"
    assert json.loads(plan.artifact_bytes)["source"]["document_id"] == "SOP-🚀"


@pytest.mark.parametrize("field", ("first_chunk_index", "max_chunk_chars", "vector_size"))
@pytest.mark.parametrize("value", (True, False, 0, -1, 1.0, "1", None))
def test_positive_integer_config_fields_are_exact_nonboolean_ints(
    field: str, value: object
) -> None:
    config = _config()
    config[field] = value
    _assert_error(config_bytes=_json_bytes(config), code="config_value", field=field)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("contract_version", "other"),
        ("distance", "Dot"),
        ("vector_source", "indexer"),
        ("embedding_generated_by_indexer", True),
        ("embedding_generated_by_indexer", 0),
    ),
)
def test_fixed_config_values_are_exact(field: str, value: object) -> None:
    config = _config()
    config[field] = value
    _assert_error(config_bytes=_json_bytes(config), code="config_value", field=field)


@pytest.mark.parametrize(
    "indexes",
    (
        [],
        [
            {"field_name": "applicable_asset_type", "field_schema": "keyword"},
            {"field_name": "applicable_asset_id", "field_schema": "keyword"},
            {"field_name": "related_procedure", "field_schema": "keyword"},
        ],
        [
            {"field_name": "applicable_asset_id", "field_schema": "text"},
            {"field_name": "applicable_asset_type", "field_schema": "keyword"},
            {"field_name": "related_procedure", "field_schema": "keyword"},
        ],
        [
            {"field_name": "applicable_asset_id", "field_schema": "keyword", "extra": 1},
            {"field_name": "applicable_asset_type", "field_schema": "keyword"},
            {"field_name": "related_procedure", "field_schema": "keyword"},
        ],
        "not-a-list",
    ),
)
def test_payload_indexes_require_the_exact_ordered_schema(indexes: object) -> None:
    config = _config()
    config["payload_indexes"] = indexes
    _assert_error(config_bytes=_json_bytes(config), code="config_value", field="payload_indexes")


@pytest.mark.parametrize(
    "field",
    (
        "contract_version",
        "document_id",
        "source_path",
        "applicable_asset_id",
        "applicable_asset_type",
        "related_procedure",
        "evidence_id_prefix",
        "collection_name",
        "vector_source",
        "vector_producer_id",
    ),
)
@pytest.mark.parametrize("value", ("", " ", " leading", "trailing ", "a\nb", 7, True, None))
def test_identifier_and_citation_strings_are_strict(field: str, value: object) -> None:
    config = _config()
    config[field] = value
    _assert_error(config_bytes=_json_bytes(config), field=field)


@pytest.mark.parametrize("name", ("bad/name", ".", "name space", "é", "a.b"))
def test_collection_name_uses_the_safe_exact_grammar(name: str) -> None:
    config = _config()
    config["collection_name"] = name
    _assert_error(config_bytes=_json_bytes(config), code="config_value", field="collection_name")


@pytest.mark.parametrize(
    "payload",
    (
        b"{",
        b"\x80",
        b"[]",
        b'{"ex:SOP_Chunk_7":[1,0,0,0],"ex:SOP_Chunk_7":[0,1,0,0]}',
        b'{"ex:SOP_Chunk_7":[1,NaN,0,0]}',
        b'{"ex:SOP_Chunk_7":[1,Infinity,0,0]}',
        b'{"ex:SOP_Chunk_7":[1,-Infinity,0,0]}',
    ),
)
def test_vector_json_is_strict(payload: bytes) -> None:
    _assert_error(vector_bytes=payload, field="vector_bytes")


@pytest.mark.parametrize(
    "value",
    (
        [],
        [1, 0, 0],
        [1, 0, 0, 0, 0],
        [True, 0, 0, 0],
        ["1", 0, 0, 0],
        [None, 0, 0, 0],
        {"0": 1},
    ),
)
def test_vectors_require_arrays_of_exact_finite_numeric_dimension(value: object) -> None:
    _assert_error(vector_bytes=_json_bytes({_EVIDENCE_ID: value}), field="vectors.items")


@pytest.mark.parametrize(
    "vectors",
    ({}, {"wrong": [1, 0, 0, 0]}, {_EVIDENCE_ID: [1, 0, 0, 0], "extra": [1, 0, 0, 0]}),
)
def test_vector_keys_equal_the_generated_nonempty_evidence_id_set(vectors: object) -> None:
    _assert_error(vector_bytes=_json_bytes(vectors), code="vector_ids", field="vector_bytes")


def test_identity_transitions_match_the_frozen_contract() -> None:
    baseline = _build()
    baseline_point = baseline.points[0]

    changed_source = _build(source=b"Changed source text.\n")
    config = _config()
    config["source_path"] = "other/path.txt"
    changed_path = _build(config=config)
    assert changed_source.chunks[0].evidence_id == baseline_point.payload["evidence_id"]
    assert changed_source.points[0].point_id == baseline_point.point_id
    assert changed_path.points[0].point_id == baseline_point.point_id
    assert changed_source.points[0].payload["source_sha256"] != _SHA256

    config = _config()
    config["document_id"] = "SOP-PUMP-OPS-2027"
    changed_document = _build(config=config)
    assert changed_document.chunks[0].evidence_id == _EVIDENCE_ID
    assert changed_document.points[0].point_id != baseline_point.point_id

    config = _config()
    config["evidence_id_prefix"] = "ex:Other_"
    changed_prefix = _build(config=config, vectors=_vectors("ex:Other_7"))
    assert changed_prefix.chunks[0].evidence_id == "ex:Other_7"
    assert changed_prefix.points[0].point_id != baseline_point.point_id

    config = _config()
    config["first_chunk_index"] = 8
    changed_index = _build(config=config, vectors=_vectors("ex:SOP_Chunk_8"))
    assert changed_index.chunks[0].evidence_id == "ex:SOP_Chunk_8"
    assert changed_index.points[0].point_id != baseline_point.point_id


def test_all_reported_build_errors_are_sanitized_and_unchained() -> None:
    marker = "SECRET_RAW_VALUE_9f82"
    config = _config()
    config["document_id"] = marker + "\n"
    error = _assert_error(config_bytes=_json_bytes(config), field="document_id")
    assert marker not in error.sanitized_detail
    assert marker not in str(error)

    utf8_error = _assert_error(config_bytes=b'"SECRET_RAW_VALUE_9f82\x80"', field="config_bytes")
    assert marker not in utf8_error.sanitized_detail
    assert utf8_error.__suppress_context__
    assert utf8_error.__context__ is None


def test_build_error_retains_no_raw_input_marker_anywhere_in_exception_surface() -> None:
    error = _secret_build_error()
    assert error.field == "config_bytes"

    surfaces: list[object] = [
        error,
        str(error),
        repr(error),
        error.args,
        vars(error),
        error.__cause__,
        error.__context__,
    ]
    traceback = error.__traceback__
    product_frames: list[str] = []
    while traceback is not None:
        surfaces.append(traceback.tb_frame.f_locals)
        if traceback.tb_frame.f_globals.get("__name__") == indexing_module.__name__:
            product_frames.append(traceback.tb_frame.f_code.co_name)
        traceback = traceback.tb_next

    assert product_frames == ["build_procedural_index"]
    rendered = "\n".join(repr(surface) for surface in surfaces)
    for marker in _TRACEBACK_SECRET_MARKERS:
        assert marker not in rendered
