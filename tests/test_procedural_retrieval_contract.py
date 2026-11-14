"""Focused contract tests for Issue #16 deterministic procedural retrieval."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

import pytest

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReferenceResolutionError,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.procedural_retrieval import (
    DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME,
    ProceduralRetrievalResult,
    ProceduralRetriever,
    ProceduralSupportRecord,
    retrieve_procedural_support,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json"
RUN_ID = "run-issue-16"
QUERY_ID = "query-pump-12-sop-cavitation"
ASSET = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
DOCUMENT_EVIDENCE_ID = "ex:SOP_Chunk_7"
DOCUMENT_ID = "SOP-PUMP-OPS-2026"
CHUNK_INDEX = 7
PROCEDURE_ID = "ex:Procedure_InspectInletCavitation_Pump12"
EXPECTED_TEXT = (
    "For anomalous sound at Pump_12, inspect the pump inlet for cavitation before "
    "recommending corrective action."
)
SOURCE_PATH = "tests/fixtures/sop/pump12-sop.txt"
SOURCE_SHA256 = "3e538364b4d6a61f92e3bfd0976134865130063bdbcadd607cb203862957eecf"
INDEX_CONTRACT_VERSION = "mfg-agentgraph-procedural-index-v1"
MAX_IDENTIFIER_BYTES = 1_024


class _StringSubclass(str):
    pass


def _scenario() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _retrieve(scenario: dict[str, Any] | None = None) -> ProceduralRetrievalResult:
    return retrieve_procedural_support(
        resolved_asset=ASSET,
        scenario=scenario if scenario is not None else _scenario(),
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )


def test_valid_pump_12_result_contains_validated_document_chunk_support() -> None:
    scenario = _scenario()
    scenario_before = copy.deepcopy(scenario)

    result = _retrieve(scenario)

    assert scenario == scenario_before
    assert result.status is TerminalStatus.PASSED
    assert result.asset == ASSET
    assert len(result.support_records) == 1
    support = result.support_records[0]
    assert support.evidence_id == DOCUMENT_EVIDENCE_ID
    assert support.document == DOCUMENT_ID
    assert support.chunk_index == CHUNK_INDEX
    assert support.related_procedure == PROCEDURE_ID
    assert support.text == EXPECTED_TEXT
    assert support.applicable_asset_id == ASSET.asset_id
    assert support.applicable_asset_type == "centrifugal_pump"
    assert support.source_path == SOURCE_PATH
    assert support.start_line == 1
    assert support.end_line == 1
    assert support.source_sha256 == SOURCE_SHA256
    assert support.index_contract_version == INDEX_CONTRACT_VERSION

    assert tuple(ref.stable_id for ref in result.evidence_references) == (DOCUMENT_EVIDENCE_ID,)
    reference = result.evidence_references[0]
    assert reference.kind is EvidenceKind.DOCUMENT_CHUNK
    assert reference.source == "tests/fixtures/pump_12/scenario.json"
    assert reference.validation_status is EvidenceValidationStatus.VALIDATED
    assert reference.retrieval.retrieval_run_id == RUN_ID
    assert reference.retrieval.query_id == QUERY_ID
    assert reference.retrieval.retriever_name == DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME
    assert reference.retrieval.rank == 1
    assert reference.retrieval.score == 1.0

    assert isinstance(result.evidence_catalog, EvidenceCatalog)
    assert (
        result.evidence_catalog.resolve_validated_support((DOCUMENT_EVIDENCE_ID,))
        == result.evidence_references
    )
    with pytest.raises(EvidenceReferenceResolutionError):
        result.evidence_catalog.resolve_validated_support((PROCEDURE_ID,))


def test_procedural_retriever_rejects_custom_retriever_name_at_construction() -> None:
    with pytest.raises(TypeError, match="retriever_name"):
        cast(Any, ProceduralRetriever)(retriever_name="alternate_retriever")


def test_procedural_retriever_preserves_custom_source_with_deterministic_name() -> None:
    retriever = ProceduralRetriever(source="custom/source.json")

    assert retriever.source == "custom/source.json"
    assert retriever.retriever_name == DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME


def test_valid_stage_event_is_procedural_retrieval_and_traces_document_chunk() -> None:
    result = _retrieve()

    assert result.event.stage is StageName.PROCEDURAL_RETRIEVAL
    assert result.event.run_id == RUN_ID
    assert result.event.status is TerminalStatus.PASSED
    assert result.event.duration_ms == 0
    assert result.event.retry_count == 0
    assert result.event.repair_count == 0
    assert result.event.errors == ()
    assert result.event.input_ids == (ASSET.asset_id, QUERY_ID)
    assert result.event.output_ids == (DOCUMENT_EVIDENCE_ID,)


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    (
        ("document_evidence", None),
        ("document_evidence.id", "ex:DifferentChunk"),
        ("document_evidence.type", "kg_edge"),
        ("document_evidence.document", "SOP-OTHER"),
        ("document_evidence.chunk_index", 8),
        ("document_evidence.related_procedure", "ex:UnexpectedProcedure"),
        ("procedure", None),
        ("procedure.id", "ex:UnexpectedProcedure"),
        ("procedure.applicable_asset", "ex:OtherPump"),
        ("asset.type", None),
        ("asset.type", "reciprocating_pump"),
    ),
)
def test_invalid_fixture_boundary_fails_closed_without_support_or_evidence(
    field_path: str, bad_value: object
) -> None:
    scenario = _scenario()
    if field_path in {"document_evidence", "procedure"}:
        scenario.pop(field_path)
    else:
        parent_name, child_name = field_path.split(".")
        scenario[parent_name] = copy.deepcopy(scenario[parent_name])
        scenario[parent_name][child_name] = bad_value

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.stage is StageName.PROCEDURAL_RETRIEVAL
    assert result.event.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert result.event.output_ids == ()
    assert len(result.event.errors) == 1
    assert result.event.errors[0].code is StageErrorCode.UNSUPPORTED_LOWER_RANK
    assert result.event.errors[0].field == field_path


@pytest.mark.parametrize(
    "field_name",
    ("source_path", "start_line", "end_line", "source_sha256", "index_contract_version"),
)
def test_missing_citation_field_fails_closed(field_name: str) -> None:
    scenario = _scenario()
    del scenario["document_evidence"][field_name]

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert result.support_records == ()
    assert result.event.errors[0].field == f"document_evidence.{field_name}"


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("source_path", "wrong/path.txt"),
        ("source_path", "tests/fixtures/sop/pump12-sop.txt\n"),
        ("source_path", 7),
        ("start_line", 0),
        ("start_line", True),
        ("end_line", 2),
        ("end_line", "1"),
        ("source_sha256", "A" * 64),
        ("source_sha256", "0" * 64),
        ("source_sha256", None),
        ("index_contract_version", "other"),
        ("index_contract_version", "mfg-agentgraph-procedural-index-v1\x1f"),
        ("index_contract_version", False),
    ),
)
def test_wrong_citation_field_fails_closed(field_name: str, bad_value: object) -> None:
    scenario = _scenario()
    scenario["document_evidence"][field_name] = bad_value

    result = _retrieve(scenario)

    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert result.support_records == ()
    assert result.event.errors[0].field == f"document_evidence.{field_name}"


def _support_values() -> dict[str, object]:
    return {
        "evidence_id": DOCUMENT_EVIDENCE_ID,
        "document": DOCUMENT_ID,
        "chunk_index": CHUNK_INDEX,
        "related_procedure": PROCEDURE_ID,
        "text": EXPECTED_TEXT,
        "applicable_asset_id": ASSET.asset_id,
        "applicable_asset_type": "centrifugal_pump",
        "source_path": SOURCE_PATH,
        "start_line": 1,
        "end_line": 1,
        "source_sha256": SOURCE_SHA256,
        "index_contract_version": INDEX_CONTRACT_VERSION,
    }


def test_direct_support_record_preserves_exact_non_nul_text() -> None:
    values = _support_values()
    values["text"] = " \tExact text\x1f \n"

    support = ProceduralSupportRecord(**cast(Any, values))

    assert support.text == " \tExact text\x1f \n"


def test_direct_support_record_enforces_chunk_character_limit() -> None:
    values = _support_values()
    values["text"] = "x" * 1_000_000
    support = ProceduralSupportRecord(**cast(Any, values))
    assert len(support.text) == 1_000_000

    values["text"] = "x" * 1_000_001
    with pytest.raises(ValueError, match="text exceeds"):
        ProceduralSupportRecord(**cast(Any, values))


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_error"),
    (
        ("evidence_id", " ex:SOP_Chunk_7", ValueError),
        ("document", "SOP\x1f", ValueError),
        ("chunk_index", True, TypeError),
        ("chunk_index", -1, ValueError),
        ("text", " ", ValueError),
        ("text", "bad\x00text", ValueError),
        ("applicable_asset_id", 7, TypeError),
        ("source_path", " path", ValueError),
        ("start_line", 0, ValueError),
        ("start_line", True, TypeError),
        ("end_line", 0, ValueError),
        ("end_line", "1", TypeError),
        ("source_sha256", "A" * 64, ValueError),
        ("source_sha256", "0" * 63, ValueError),
        ("index_contract_version", "version\n", ValueError),
    ),
)
def test_direct_support_record_rejects_invalid_schema(
    field_name: str, bad_value: object, expected_error: type[Exception]
) -> None:
    values = _support_values()
    values[field_name] = bad_value

    with pytest.raises(expected_error):
        ProceduralSupportRecord(**cast(Any, values))


def test_direct_support_record_rejects_reversed_line_range() -> None:
    values = _support_values()
    values["start_line"] = 2

    with pytest.raises(ValueError, match="start_line must not exceed end_line"):
        ProceduralSupportRecord(**cast(Any, values))


@pytest.mark.parametrize(
    "source_path",
    (
        _StringSubclass("tests/fixtures/sop/pump12-sop.txt"),
        "",
        " ",
        "a\tb/sop.txt",
        "a\x1fb/sop.txt",
        "/absolute/sop.txt",
        "C:/absolute/sop.txt",
        "c:/absolute/sop.txt",
        "a\\b.txt",
        "a//b.txt",
        "./a.txt",
        "a/./b.txt",
        "../a.txt",
        "a/../b.txt",
        "a/b/",
    ),
)
def test_direct_support_record_rejects_non_repository_relative_posix_source_path(
    source_path: object,
) -> None:
    values = _support_values()
    values["source_path"] = source_path

    with pytest.raises((TypeError, ValueError), match="source_path"):
        ProceduralSupportRecord(**cast(Any, values))


@pytest.mark.parametrize(
    "source_path", ("sop.txt", "a/b-c_1.txt", "dir name/file name.txt", "資料/ポンプ.txt")
)
def test_direct_support_record_accepts_unicode_repository_relative_posix_source_path(
    source_path: str,
) -> None:
    values = _support_values()
    values["source_path"] = source_path

    support = ProceduralSupportRecord(**cast(Any, values))

    assert support.source_path == source_path


def test_resolved_asset_rebinding_stable_document_chunk_fails_closed() -> None:
    other_asset = KnownAsset("ex:OtherPump", "Other Pump", ("OtherPump",))
    scenario = _scenario()
    scenario["asset"] = copy.deepcopy(scenario["asset"])
    scenario["procedure"] = copy.deepcopy(scenario["procedure"])
    scenario["asset"]["id"] = other_asset.asset_id
    scenario["procedure"]["applicable_asset"] = other_asset.asset_id

    result = retrieve_procedural_support(
        resolved_asset=other_asset,
        scenario=scenario,
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )

    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    assert result.support_records == ()
    assert result.evidence_references == ()
    assert result.evidence_catalog.references == ()
    assert result.event.output_ids == ()
    assert result.event.errors[0].code is StageErrorCode.UNSUPPORTED_LOWER_RANK
    assert result.event.errors[0].field == "resolved_asset.asset_id"
    detail = result.event.errors[0].detail
    assert detail is not None
    assert "ex:Pump_12" in detail
    assert other_asset.asset_id in detail


def test_oversized_fixture_identifier_fails_closed_with_bounded_detail() -> None:
    scenario = _scenario()
    scenario["asset"] = dict(scenario["asset"])
    scenario["asset"]["id"] = "x" * 2_000

    result = retrieve_procedural_support(
        resolved_asset=ASSET,
        scenario=scenario,
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )

    assert result.status is TerminalStatus.UNSUPPORTED_LOWER_RANK
    detail = result.event.errors[0].detail
    assert detail is not None
    assert len(detail.encode("utf-8")) <= 1_024


def test_input_validation_is_typed_and_fail_fast() -> None:
    scenario = _scenario()
    with pytest.raises(TypeError, match="resolved_asset must be a KnownAsset"):
        retrieve_procedural_support(
            resolved_asset=cast(Any, "ex:Pump_12"),
            scenario=scenario,
            retrieval_run_id=RUN_ID,
            query_id=QUERY_ID,
        )
    with pytest.raises(TypeError, match="scenario must be a mapping"):
        retrieve_procedural_support(
            resolved_asset=ASSET,
            scenario=cast(Any, []),
            retrieval_run_id=RUN_ID,
            query_id=QUERY_ID,
        )
    with pytest.raises(ValueError, match="retrieval_run_id must be nonblank"):
        retrieve_procedural_support(
            resolved_asset=ASSET,
            scenario=scenario,
            retrieval_run_id=" ",
            query_id=QUERY_ID,
        )
    with pytest.raises(ValueError, match="query_id must be nonblank"):
        retrieve_procedural_support(
            resolved_asset=ASSET,
            scenario=scenario,
            retrieval_run_id=RUN_ID,
            query_id="",
        )


@pytest.mark.parametrize("field_name", ("retrieval_run_id", "query_id"))
@pytest.mark.parametrize("affixed_value", (" leading", "trailing ", " both "))
def test_retrieval_run_and_query_ids_reject_surrounding_whitespace(
    field_name: str, affixed_value: str
) -> None:
    kwargs = {
        "resolved_asset": ASSET,
        "scenario": _scenario(),
        "retrieval_run_id": RUN_ID,
        "query_id": QUERY_ID,
    }
    kwargs[field_name] = affixed_value

    with pytest.raises(ValueError, match=f"{field_name} must not contain surrounding whitespace"):
        cast(Any, retrieve_procedural_support)(**kwargs)


@pytest.mark.parametrize("field_name", ("retrieval_run_id", "query_id"))
def test_retrieval_run_and_query_ids_enforce_utf8_byte_limit(field_name: str) -> None:
    kwargs = {
        "resolved_asset": ASSET,
        "scenario": _scenario(),
        "retrieval_run_id": RUN_ID,
        "query_id": QUERY_ID,
    }
    kwargs[field_name] = "é" * (MAX_IDENTIFIER_BYTES // 2)
    result = cast(Any, retrieve_procedural_support)(**kwargs)
    assert getattr(result.event, "run_id" if field_name == "retrieval_run_id" else "input_ids")

    kwargs[field_name] = "é" * (MAX_IDENTIFIER_BYTES // 2 + 1)
    with pytest.raises(ValueError, match=f"{field_name} exceeds"):
        cast(Any, retrieve_procedural_support)(**kwargs)


def test_result_records_are_immutable_and_tuple_backed() -> None:
    result = _retrieve()

    assert isinstance(result.support_records, tuple)
    assert isinstance(result.evidence_references, tuple)
    with pytest.raises(FrozenInstanceError):
        result.status = TerminalStatus.UNSUPPORTED_LOWER_RANK  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.support_records[0].text = "changed"


def test_catalog_resolution_is_independent_of_unrelated_catalog_order() -> None:
    retriever = ProceduralRetriever(source="tests/fixtures/pump_12/scenario.json")
    result = retriever.retrieve(
        resolved_asset=ASSET,
        scenario=_scenario(),
        retrieval_run_id=RUN_ID,
        query_id=QUERY_ID,
    )
    unrelated_reference = replace(
        result.evidence_references[0],
        stable_id="ex:AnotherValidatedChunk",
    )
    catalog = EvidenceCatalog((unrelated_reference, result.evidence_references[0]))

    assert catalog.resolve_validated_support((DOCUMENT_EVIDENCE_ID,)) == result.evidence_references


def test_direct_passed_result_rejects_non_procedural_stage_event() -> None:
    result = _retrieve()
    event = replace(result.event, stage=StageName.STRUCTURED_RETRIEVAL)

    with pytest.raises(ValueError, match="event.stage must be procedural_retrieval"):
        replace(result, event=event)


def test_direct_result_rejects_status_mismatch_and_unsupported_status() -> None:
    result = _retrieve()

    with pytest.raises(ValueError, match="status must match event.status"):
        replace(result, status=TerminalStatus.UNSUPPORTED_LOWER_RANK)

    unsupported_event = replace(result.event, status=TerminalStatus.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValueError, match="status must be passed or unsupported_lower_rank"):
        replace(result, status=TerminalStatus.INSUFFICIENT_EVIDENCE, event=unsupported_event)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    (
        ("support_records", (), "passed result must contain exactly one support record"),
        ("evidence_references", (), "passed result must contain exactly one evidence reference"),
        (
            "evidence_catalog",
            EvidenceCatalog(()),
            "evidence catalog references must equal evidence_references",
        ),
    ),
)
def test_direct_passed_result_rejects_cardinality_and_catalog_contradictions(
    field_name: str, bad_value: object, message: str
) -> None:
    result = _retrieve()

    with pytest.raises(ValueError, match=message):
        cast(Any, replace)(result, **{field_name: bad_value})


def test_direct_passed_result_rejects_event_errors() -> None:
    result = _retrieve()
    event = replace(
        result.event,
        errors=(StageError(StageErrorCode.INVALID_STAGE_EVENT),),
    )

    with pytest.raises(ValueError, match="passed result must not contain event errors"):
        replace(result, event=event)


def test_direct_passed_result_rejects_output_id_contradiction() -> None:
    result = _retrieve()
    event = replace(result.event, output_ids=(PROCEDURE_ID, DOCUMENT_EVIDENCE_ID))

    with pytest.raises(
        ValueError,
        match="passed event.output_ids must equal document evidence ID",
    ):
        replace(result, event=event)


@pytest.mark.parametrize(
    ("field_name", "message"),
    (
        ("support.evidence_id", "support evidence_id must equal canonical document evidence ID"),
        (
            "reference.stable_id",
            "evidence reference stable_id must equal canonical document evidence ID",
        ),
        ("event.output_ids", "passed event.output_ids must equal canonical document evidence ID"),
        ("coordinated_ids", "support evidence_id must equal canonical document evidence ID"),
    ),
)
def test_direct_passed_result_rejects_noncanonical_document_evidence_ids(
    field_name: str, message: str
) -> None:
    result = _retrieve()
    noncanonical_id = "ex:DifferentChunk"
    support = result.support_records[0]
    reference = result.evidence_references[0]
    event = result.event

    if field_name in {"support.evidence_id", "coordinated_ids"}:
        support = replace(support, evidence_id=noncanonical_id)
    if field_name in {"reference.stable_id", "coordinated_ids"}:
        reference = replace(reference, stable_id=noncanonical_id)
    if field_name in {"event.output_ids", "coordinated_ids"}:
        event = replace(event, output_ids=(noncanonical_id,))

    with pytest.raises(ValueError, match=message):
        replace(
            result,
            support_records=(support,),
            evidence_references=(reference,),
            evidence_catalog=EvidenceCatalog((reference,)),
            event=event,
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    (
        (
            "retriever_name",
            "alternate_retriever",
            "retrieval retriever_name must equal deterministic procedural retriever",
        ),
        ("rank", 2, "retrieval rank must equal deterministic top rank"),
        ("score", 0.5, "retrieval score must equal deterministic exact score"),
        ("score", None, "retrieval score must equal deterministic exact score"),
    ),
)
def test_direct_passed_result_rejects_noncanonical_retrieval_metadata(
    field_name: str, bad_value: object, message: str
) -> None:
    result = _retrieve()
    reference = replace(
        result.evidence_references[0],
        retrieval=cast(Any, replace)(
            result.evidence_references[0].retrieval,
            **{field_name: bad_value},
        ),
    )

    with pytest.raises(ValueError, match=message):
        replace(
            result,
            evidence_references=(reference,),
            evidence_catalog=EvidenceCatalog((reference,)),
        )


def test_direct_passed_result_rejects_non_document_chunk_evidence_reference() -> None:
    result = _retrieve()
    kg_reference = replace(result.evidence_references[0], kind=EvidenceKind.KG_EDGE)

    with pytest.raises(ValueError, match="passed evidence reference must be a document chunk"):
        replace(
            result,
            evidence_references=(kg_reference,),
            evidence_catalog=EvidenceCatalog((kg_reference,)),
        )


def test_direct_passed_result_rejects_unvalidated_evidence_reference() -> None:
    result = _retrieve()
    unvalidated_reference = replace(
        result.evidence_references[0],
        validation_status=EvidenceValidationStatus.UNVALIDATED,
    )

    with pytest.raises(ValueError, match="passed evidence reference must be validated"):
        replace(
            result,
            evidence_references=(unvalidated_reference,),
            evidence_catalog=EvidenceCatalog((unvalidated_reference,)),
        )


def test_direct_passed_result_rejects_support_evidence_contradiction() -> None:
    result = _retrieve()
    support = replace(result.support_records[0], evidence_id="ex:DifferentEvidence")

    with pytest.raises(
        ValueError,
        match="support evidence_id must equal evidence reference stable_id",
    ):
        replace(result, support_records=(support,))


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    (
        ("document", "SOP-OTHER", "support document must equal canonical Pump 12 SOP"),
        ("chunk_index", 8, "support chunk_index must equal canonical Pump 12 chunk"),
        (
            "related_procedure",
            "ex:UnexpectedProcedure",
            "support related_procedure must equal canonical Pump 12 procedure",
        ),
        (
            "text",
            "Inspect something else.",
            "support text must equal canonical Pump 12 fixture text",
        ),
        (
            "applicable_asset_id",
            "ex:OtherPump",
            "support applicable_asset_id must equal result asset and canonical Pump 12 asset",
        ),
        (
            "applicable_asset_type",
            "reciprocating_pump",
            "support applicable_asset_type must equal canonical Pump 12 asset type",
        ),
    ),
)
def test_direct_passed_result_rejects_canonical_support_field_contradictions(
    field_name: str, bad_value: object, message: str
) -> None:
    result = _retrieve()
    support = cast(Any, replace)(result.support_records[0], **{field_name: bad_value})

    with pytest.raises(ValueError, match=message):
        replace(result, support_records=(support,))


def test_direct_passed_result_rejects_support_asset_id_even_when_matching_result_asset() -> None:
    result = _retrieve()
    other_asset = KnownAsset("ex:OtherPump", "Other Pump", ("OtherPump",))
    support = replace(result.support_records[0], applicable_asset_id=other_asset.asset_id)
    event = replace(result.event, input_ids=(other_asset.asset_id, QUERY_ID))

    with pytest.raises(
        ValueError,
        match="support applicable_asset_id must equal result asset and canonical Pump 12 asset",
    ):
        replace(result, asset=other_asset, support_records=(support,), event=event)


@pytest.mark.parametrize(
    ("event_kwargs", "message"),
    (
        (
            {"input_ids": ("ex:OtherPump", QUERY_ID)},
            "passed event.input_ids must equal asset and query IDs",
        ),
        (
            {"input_ids": (ASSET.asset_id, "query-other")},
            "passed event.input_ids must equal asset and query IDs",
        ),
        ({"run_id": "run-other"}, "passed event.run_id must equal retrieval run ID"),
    ),
)
def test_direct_passed_result_rejects_trace_contradictions(
    event_kwargs: dict[str, object], message: str
) -> None:
    result = _retrieve()
    event = cast(Any, replace)(result.event, **event_kwargs)

    with pytest.raises(ValueError, match=message):
        replace(result, event=event)


def test_direct_passed_result_rejects_same_id_but_different_catalog_reference() -> None:
    result = _retrieve()
    different_reference = replace(
        result.evidence_references[0],
        retrieval=RetrievalMetadata(
            retrieval_run_id=RUN_ID,
            query_id=QUERY_ID,
            retriever_name=DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME,
            rank=2,
        ),
    )

    with pytest.raises(
        ValueError,
        match="evidence catalog references must equal evidence_references",
    ):
        replace(result, evidence_catalog=EvidenceCatalog((different_reference,)))


def test_direct_unsupported_result_rejects_support_and_evidence_and_missing_errors() -> None:
    passed = _retrieve()
    event = StageEvent(
        stage=StageName.PROCEDURAL_RETRIEVAL,
        run_id=RUN_ID,
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        input_ids=(ASSET.asset_id, QUERY_ID),
        output_ids=(),
        errors=(StageError(StageErrorCode.UNSUPPORTED_LOWER_RANK, field="document_evidence"),),
    )
    unsupported = ProceduralRetrievalResult(
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        asset=ASSET,
        event=event,
    )

    with pytest.raises(ValueError, match="unsupported result must not contain support records"):
        replace(unsupported, support_records=passed.support_records)
    with pytest.raises(ValueError, match="unsupported result must not contain evidence references"):
        replace(unsupported, evidence_references=passed.evidence_references)
    with pytest.raises(ValueError, match="unsupported result must have an empty evidence catalog"):
        replace(unsupported, evidence_catalog=passed.evidence_catalog)
    with pytest.raises(ValueError, match="unsupported result must contain event errors"):
        replace(unsupported, event=replace(event, errors=()))
    with pytest.raises(ValueError, match="unsupported event.output_ids must be empty"):
        replace(unsupported, event=replace(event, output_ids=(DOCUMENT_EVIDENCE_ID,)))


def test_direct_unsupported_result_rejects_non_unsupported_event_error_code() -> None:
    event = StageEvent(
        stage=StageName.PROCEDURAL_RETRIEVAL,
        run_id=RUN_ID,
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        input_ids=(ASSET.asset_id, QUERY_ID),
        output_ids=(),
        errors=(
            StageError(StageErrorCode.UNSUPPORTED_LOWER_RANK, field="document_evidence"),
            StageError(StageErrorCode.INVALID_STAGE_EVENT, field="event"),
        ),
    )

    with pytest.raises(
        ValueError, match="unsupported event errors must all be unsupported_lower_rank"
    ):
        ProceduralRetrievalResult(
            status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
            asset=ASSET,
            event=event,
        )


@pytest.mark.parametrize(
    "input_ids",
    (
        (),
        (ASSET.asset_id,),
        ("ex:OtherPump", QUERY_ID),
    ),
)
def test_direct_unsupported_result_rejects_non_asset_query_input_ids(
    input_ids: tuple[str, ...],
) -> None:
    event = StageEvent(
        stage=StageName.PROCEDURAL_RETRIEVAL,
        run_id=RUN_ID,
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        input_ids=input_ids,
        output_ids=(),
        errors=(StageError(StageErrorCode.UNSUPPORTED_LOWER_RANK, field="document_evidence"),),
    )

    with pytest.raises(ValueError, match="unsupported event.input_ids must be asset/query shaped"):
        ProceduralRetrievalResult(
            status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
            asset=ASSET,
            event=event,
        )
