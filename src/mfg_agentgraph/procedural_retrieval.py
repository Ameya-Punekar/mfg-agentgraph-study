"""Dependency-free deterministic procedural retrieval for the Pump 12 fixture.

This module intentionally models only the minimal Issue #16 contract: validate the
resolved Pump 12 asset against the fixture-shaped mapping, verify procedure
applicability, and expose the SOP document chunk as procedural support evidence.
It is not a production vector/Qdrant retriever.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)

DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME = "deterministic_procedural_fixture"
QDRANT_PROCEDURAL_RETRIEVER_NAME = "qdrant_vector"
DEFAULT_PROCEDURAL_RETRIEVAL_SOURCE = "tests/fixtures/pump_12/scenario.json"
_EXPECTED_ASSET_ID = "ex:Pump_12"
_EXPECTED_ASSET_TYPE = "centrifugal_pump"
_EXPECTED_DOCUMENT_EVIDENCE_ID = "ex:SOP_Chunk_7"
_EXPECTED_DOCUMENT_EVIDENCE_TYPE = "document_chunk"
_EXPECTED_DOCUMENT = "SOP-PUMP-OPS-2026"
_EXPECTED_CHUNK_INDEX = 7
_EXPECTED_PROCEDURE_ID = "ex:Procedure_InspectInletCavitation_Pump12"
_EXPECTED_TEXT = (
    "For anomalous sound at Pump_12, inspect the pump inlet for cavitation before "
    "recommending corrective action."
)
_EXPECTED_SOURCE_PATH = "tests/fixtures/sop/pump12-sop.txt"
_EXPECTED_START_LINE = 1
_EXPECTED_END_LINE = 1
_EXPECTED_SOURCE_SHA256 = "3e538364b4d6a61f92e3bfd0976134865130063bdbcadd607cb203862957eecf"
_EXPECTED_INDEX_CONTRACT_VERSION = "mfg-agentgraph-procedural-index-v1"
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_ABSOLUTE = re.compile(r"[A-Za-z]:/")
_MAX_IDENTIFIER_BYTES = 1_024
_MAX_EVIDENCE_ID_BYTES = 8_192
_MAX_CHUNK_CHARS = 1_000_000


@dataclass(frozen=True, slots=True)
class ProceduralSupportRecord:
    """Validated SOP document chunk support returned by the procedural retriever."""

    evidence_id: str
    document: str
    chunk_index: int
    related_procedure: str
    text: str
    applicable_asset_id: str
    applicable_asset_type: str
    source_path: str
    start_line: int
    end_line: int
    source_sha256: str
    index_contract_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_nonblank(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "document", _require_nonblank(self.document, "document"))
        if not _is_non_bool_int(self.chunk_index):
            raise TypeError("chunk_index must be an int")
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be nonnegative")
        object.__setattr__(
            self,
            "related_procedure",
            _require_nonblank(self.related_procedure, "related_procedure"),
        )
        object.__setattr__(self, "text", _require_chunk_text(self.text))
        object.__setattr__(
            self,
            "applicable_asset_id",
            _require_nonblank(self.applicable_asset_id, "applicable_asset_id"),
        )
        object.__setattr__(
            self,
            "applicable_asset_type",
            _require_nonblank(self.applicable_asset_type, "applicable_asset_type"),
        )
        object.__setattr__(self, "source_path", _require_source_path(self.source_path))
        _require_positive_int(self.start_line, "start_line")
        _require_positive_int(self.end_line, "end_line")
        if self.start_line > self.end_line:
            raise ValueError("start_line must not exceed end_line")
        object.__setattr__(self, "source_sha256", _require_digest(self.source_sha256))
        object.__setattr__(
            self,
            "index_contract_version",
            _require_nonblank(self.index_contract_version, "index_contract_version"),
        )


@dataclass(frozen=True, slots=True)
class ProceduralRetrievalResult:
    """Immutable procedural retrieval outcome and instrumentation event."""

    status: TerminalStatus
    asset: KnownAsset
    event: StageEvent
    support_records: Sequence[ProceduralSupportRecord] = field(default_factory=tuple)
    evidence_references: Sequence[EvidenceReference] = field(default_factory=tuple)
    evidence_catalog: EvidenceCatalog = field(default_factory=EvidenceCatalog)

    def __post_init__(self) -> None:
        if not isinstance(self.status, TerminalStatus):
            raise TypeError("status must be a TerminalStatus")
        if not isinstance(self.asset, KnownAsset):
            raise TypeError("asset must be a KnownAsset")
        object.__setattr__(
            self,
            "support_records",
            _normalize_sequence(self.support_records, ProceduralSupportRecord, "support_records"),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _normalize_sequence(self.evidence_references, EvidenceReference, "evidence_references"),
        )
        if not isinstance(self.evidence_catalog, EvidenceCatalog):
            raise TypeError("evidence_catalog must be an EvidenceCatalog")
        if not isinstance(self.event, StageEvent):
            raise TypeError("event must be a StageEvent")
        _validate_result_invariants(self)


@dataclass(frozen=True, slots=True)
class ProceduralRetriever:
    """Deterministic fixture-backed procedural retriever."""

    source: str = DEFAULT_PROCEDURAL_RETRIEVAL_SOURCE
    retriever_name: str = field(default=DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _require_nonblank(self.source, "source"))

    def retrieve(
        self,
        *,
        resolved_asset: KnownAsset,
        scenario: Mapping[str, Any],
        retrieval_run_id: str,
        query_id: str,
    ) -> ProceduralRetrievalResult:
        """Return procedural support for a resolved asset, failing closed on mismatch."""

        _validate_asset(resolved_asset)
        _validate_mapping(scenario, "scenario")
        run_id = _require_strict_nonblank(retrieval_run_id, "retrieval_run_id")
        normalized_query_id = _require_strict_nonblank(query_id, "query_id")
        input_ids = (resolved_asset.asset_id, normalized_query_id)

        support_result = _extract_valid_support(scenario, resolved_asset)
        if isinstance(support_result, StageError):
            return _failure(resolved_asset, run_id, input_ids, support_result)
        support = support_result

        reference = EvidenceReference(
            kind=EvidenceKind.DOCUMENT_CHUNK,
            source=self.source,
            stable_id=support.evidence_id,
            retrieval=RetrievalMetadata(
                retrieval_run_id=run_id,
                query_id=normalized_query_id,
                retriever_name=self.retriever_name,
                rank=1,
                score=1.0,
            ),
            validation_status=EvidenceValidationStatus.VALIDATED,
        )
        references = (reference,)
        event = StageEvent(
            stage=StageName.PROCEDURAL_RETRIEVAL,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            duration_ms=0,
            input_ids=input_ids,
            output_ids=(support.evidence_id,),
        )
        return ProceduralRetrievalResult(
            status=TerminalStatus.PASSED,
            asset=resolved_asset,
            support_records=(support,),
            evidence_references=references,
            evidence_catalog=EvidenceCatalog(references),
            event=event,
        )


def retrieve_procedural_support(
    *,
    resolved_asset: KnownAsset,
    scenario: Mapping[str, Any],
    retrieval_run_id: str,
    query_id: str,
    source: str = DEFAULT_PROCEDURAL_RETRIEVAL_SOURCE,
) -> ProceduralRetrievalResult:
    """Convenience wrapper around :class:`ProceduralRetriever`."""

    return ProceduralRetriever(source=source).retrieve(
        resolved_asset=resolved_asset,
        scenario=scenario,
        retrieval_run_id=retrieval_run_id,
        query_id=query_id,
    )


def _extract_valid_support(
    scenario: Mapping[str, Any], resolved_asset: KnownAsset
) -> ProceduralSupportRecord | StageError:
    if resolved_asset.asset_id != _EXPECTED_ASSET_ID:
        return _unsupported(
            "resolved_asset.asset_id",
            f"expected {_EXPECTED_ASSET_ID}, got {resolved_asset.asset_id!r}",
        )

    asset = scenario.get("asset")
    if not isinstance(asset, Mapping):
        return _unsupported("asset", "required Pump 12 asset record is missing")
    asset_id = _string_or_none(asset.get("id"))
    if asset_id != resolved_asset.asset_id:
        return _unsupported("asset.id", f"expected {resolved_asset.asset_id}, got {asset_id!r}")
    asset_type = _string_or_none(asset.get("type"))
    if asset_type != _EXPECTED_ASSET_TYPE:
        return _unsupported("asset.type", f"expected {_EXPECTED_ASSET_TYPE}, got {asset_type!r}")

    procedure = scenario.get("procedure")
    if not isinstance(procedure, Mapping):
        return _unsupported("procedure", "required procedure record is missing")
    procedure_id = _string_or_none(procedure.get("id"))
    if procedure_id != _EXPECTED_PROCEDURE_ID:
        return _unsupported(
            "procedure.id", f"expected {_EXPECTED_PROCEDURE_ID}, got {procedure_id!r}"
        )
    applicable_asset = _string_or_none(procedure.get("applicable_asset"))
    if applicable_asset != resolved_asset.asset_id:
        return _unsupported(
            "procedure.applicable_asset",
            f"expected {resolved_asset.asset_id}, got {applicable_asset!r}",
        )

    document_evidence = scenario.get("document_evidence")
    if not isinstance(document_evidence, Mapping):
        return _unsupported(
            "document_evidence",
            f"required document evidence {_EXPECTED_DOCUMENT_EVIDENCE_ID} is missing",
        )
    evidence_id = _string_or_none(document_evidence.get("id"))
    if evidence_id != _EXPECTED_DOCUMENT_EVIDENCE_ID:
        return _unsupported(
            "document_evidence.id",
            f"expected {_EXPECTED_DOCUMENT_EVIDENCE_ID}, got {evidence_id!r}",
        )
    evidence_type = _string_or_none(document_evidence.get("type"))
    if evidence_type != _EXPECTED_DOCUMENT_EVIDENCE_TYPE:
        return _unsupported(
            "document_evidence.type",
            f"expected {_EXPECTED_DOCUMENT_EVIDENCE_TYPE}, got {evidence_type!r}",
        )
    document = _string_or_none(document_evidence.get("document"))
    if document != _EXPECTED_DOCUMENT:
        return _unsupported(
            "document_evidence.document", f"expected {_EXPECTED_DOCUMENT}, got {document!r}"
        )
    chunk_index = document_evidence.get("chunk_index")
    if chunk_index != _EXPECTED_CHUNK_INDEX or not _is_non_bool_int(chunk_index):
        return _unsupported(
            "document_evidence.chunk_index",
            f"expected {_EXPECTED_CHUNK_INDEX}, got {chunk_index!r}",
        )
    related_procedure = _string_or_none(document_evidence.get("related_procedure"))
    if related_procedure != procedure_id:
        return _unsupported(
            "document_evidence.related_procedure",
            f"expected {procedure_id}, got {related_procedure!r}",
        )
    text = _string_or_none(document_evidence.get("text"))
    if text != _EXPECTED_TEXT:
        return _unsupported("document_evidence.text", "document chunk text does not match fixture")
    citation_values: tuple[tuple[str, object, object], ...] = (
        ("source_path", document_evidence.get("source_path"), _EXPECTED_SOURCE_PATH),
        ("start_line", document_evidence.get("start_line"), _EXPECTED_START_LINE),
        ("end_line", document_evidence.get("end_line"), _EXPECTED_END_LINE),
        ("source_sha256", document_evidence.get("source_sha256"), _EXPECTED_SOURCE_SHA256),
        (
            "index_contract_version",
            document_evidence.get("index_contract_version"),
            _EXPECTED_INDEX_CONTRACT_VERSION,
        ),
    )
    for field_name, actual, expected in citation_values:
        if actual != expected or type(actual) is not type(expected):
            return _unsupported(
                f"document_evidence.{field_name}",
                f"document citation {field_name} does not match fixture",
            )

    return ProceduralSupportRecord(
        evidence_id=evidence_id,
        document=document,
        chunk_index=chunk_index,
        related_procedure=related_procedure,
        text=text,
        applicable_asset_id=applicable_asset,
        applicable_asset_type=asset_type,
        source_path=_EXPECTED_SOURCE_PATH,
        start_line=_EXPECTED_START_LINE,
        end_line=_EXPECTED_END_LINE,
        source_sha256=_EXPECTED_SOURCE_SHA256,
        index_contract_version=_EXPECTED_INDEX_CONTRACT_VERSION,
    )


def _failure(
    asset: KnownAsset,
    run_id: str,
    input_ids: tuple[str, ...],
    error: StageError,
) -> ProceduralRetrievalResult:
    event = StageEvent(
        stage=StageName.PROCEDURAL_RETRIEVAL,
        run_id=run_id,
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        duration_ms=0,
        input_ids=input_ids,
        output_ids=(),
        errors=(error,),
    )
    return ProceduralRetrievalResult(
        status=TerminalStatus.UNSUPPORTED_LOWER_RANK,
        asset=asset,
        support_records=(),
        evidence_references=(),
        evidence_catalog=EvidenceCatalog(()),
        event=event,
    )


def _unsupported(field: str, detail: str) -> StageError:
    return StageError(
        StageErrorCode.UNSUPPORTED_LOWER_RANK,
        field=field,
        detail=_bounded_error_detail(detail),
    )


def _bounded_error_detail(detail: str) -> str:
    encoded = detail.encode("utf-8")
    if len(encoded) <= _MAX_IDENTIFIER_BYTES:
        return detail
    prefix = encoded[: _MAX_IDENTIFIER_BYTES - 3].decode("utf-8", errors="ignore")
    return f"{prefix}..."


def _validate_asset(value: object) -> None:
    if not isinstance(value, KnownAsset):
        raise TypeError("resolved_asset must be a KnownAsset")


def _validate_mapping(value: object, field_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")


def _validate_result_invariants(result: ProceduralRetrievalResult) -> None:
    if result.event.stage is not StageName.PROCEDURAL_RETRIEVAL:
        raise ValueError("event.stage must be procedural_retrieval")
    if result.status != result.event.status:
        raise ValueError("status must match event.status")
    if result.status not in {TerminalStatus.PASSED, TerminalStatus.UNSUPPORTED_LOWER_RANK}:
        raise ValueError("status must be passed or unsupported_lower_rank")

    if result.status is TerminalStatus.PASSED:
        _validate_passed_result(result)
        return
    _validate_unsupported_result(result)


def _validate_passed_result(result: ProceduralRetrievalResult) -> None:
    if len(result.support_records) != 1:
        raise ValueError("passed result must contain exactly one support record")
    if len(result.evidence_references) != 1:
        raise ValueError("passed result must contain exactly one evidence reference")
    if result.event.errors:
        raise ValueError("passed result must not contain event errors")
    if result.evidence_catalog.references != result.evidence_references:
        raise ValueError("evidence catalog references must equal evidence_references")

    support = result.support_records[0]
    reference = result.evidence_references[0]
    if reference.kind is not EvidenceKind.DOCUMENT_CHUNK:
        raise ValueError("passed evidence reference must be a document chunk")
    if reference.validation_status is not EvidenceValidationStatus.VALIDATED:
        raise ValueError("passed evidence reference must be validated")
    if support.evidence_id != _EXPECTED_DOCUMENT_EVIDENCE_ID:
        raise ValueError(
            "support evidence_id must equal evidence reference stable_id; "
            "support evidence_id must equal canonical document evidence ID"
        )
    if reference.stable_id != _EXPECTED_DOCUMENT_EVIDENCE_ID:
        raise ValueError("evidence reference stable_id must equal canonical document evidence ID")
    if support.evidence_id != reference.stable_id:
        raise ValueError("support evidence_id must equal evidence reference stable_id")
    if support.document != _EXPECTED_DOCUMENT:
        raise ValueError("support document must equal canonical Pump 12 SOP")
    if support.chunk_index != _EXPECTED_CHUNK_INDEX:
        raise ValueError("support chunk_index must equal canonical Pump 12 chunk")
    if support.related_procedure != _EXPECTED_PROCEDURE_ID:
        raise ValueError("support related_procedure must equal canonical Pump 12 procedure")
    if support.text != _EXPECTED_TEXT:
        raise ValueError("support text must equal canonical Pump 12 fixture text")
    if (
        support.applicable_asset_id != result.asset.asset_id
        or support.applicable_asset_id != _EXPECTED_ASSET_ID
    ):
        raise ValueError(
            "support applicable_asset_id must equal result asset and canonical Pump 12 asset"
        )
    if support.applicable_asset_type != _EXPECTED_ASSET_TYPE:
        raise ValueError("support applicable_asset_type must equal canonical Pump 12 asset type")
    if support.source_path != _EXPECTED_SOURCE_PATH:
        raise ValueError("support source_path must equal canonical Pump 12 source path")
    if support.start_line != _EXPECTED_START_LINE or support.end_line != _EXPECTED_END_LINE:
        raise ValueError("support line range must equal canonical Pump 12 citation")
    if support.source_sha256 != _EXPECTED_SOURCE_SHA256:
        raise ValueError("support source_sha256 must equal canonical Pump 12 source digest")
    if support.index_contract_version != _EXPECTED_INDEX_CONTRACT_VERSION:
        raise ValueError("support index_contract_version must equal canonical index contract")
    if result.event.run_id != reference.retrieval.retrieval_run_id:
        raise ValueError("passed event.run_id must equal retrieval run ID")
    if result.event.input_ids != (result.asset.asset_id, reference.retrieval.query_id):
        raise ValueError("passed event.input_ids must equal asset and query IDs")
    retriever_name = reference.retrieval.retriever_name
    if retriever_name not in {
        DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME,
        QDRANT_PROCEDURAL_RETRIEVER_NAME,
    }:
        raise ValueError(
            "retrieval retriever_name must equal deterministic procedural retriever "
            "or Qdrant vector retriever"
        )
    if reference.retrieval.rank != 1:
        raise ValueError("retrieval rank must equal deterministic top rank")
    if (
        retriever_name == DETERMINISTIC_PROCEDURAL_RETRIEVER_NAME
        and reference.retrieval.score != 1.0
    ):
        raise ValueError("retrieval score must equal deterministic exact score")
    if retriever_name == QDRANT_PROCEDURAL_RETRIEVER_NAME and reference.retrieval.score is None:
        raise ValueError("Qdrant retrieval score must be present")
    if result.event.output_ids != (_EXPECTED_DOCUMENT_EVIDENCE_ID,):
        raise ValueError(
            "passed event.output_ids must equal document evidence ID; "
            "passed event.output_ids must equal canonical document evidence ID"
        )


def _validate_unsupported_result(result: ProceduralRetrievalResult) -> None:
    if result.support_records:
        raise ValueError("unsupported result must not contain support records")
    if result.evidence_references:
        raise ValueError("unsupported result must not contain evidence references")
    if result.evidence_catalog.references:
        raise ValueError("unsupported result must have an empty evidence catalog")
    if not result.event.errors:
        raise ValueError("unsupported result must contain event errors")
    if any(
        error.code is not StageErrorCode.UNSUPPORTED_LOWER_RANK for error in result.event.errors
    ):
        raise ValueError("unsupported event errors must all be unsupported_lower_rank")
    if result.event.output_ids:
        raise ValueError("unsupported event.output_ids must be empty")
    if (
        len(result.event.input_ids) != 2
        or result.event.input_ids[0] != result.asset.asset_id
        or not _is_nonblank_string(result.event.input_ids[1])
    ):
        raise ValueError("unsupported event.input_ids must be asset/query shaped")


def _require_nonblank(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonblank")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{field_name} must not contain control characters")
    if any(unicodedata.category(character) == "Cs" for character in value):
        raise ValueError(f"{field_name} must contain only Unicode scalar values")
    byte_limit = _MAX_EVIDENCE_ID_BYTES if field_name == "evidence_id" else _MAX_IDENTIFIER_BYTES
    if len(value.encode("utf-8")) > byte_limit:
        raise ValueError(f"{field_name} exceeds the identifier byte limit")
    return value


def _require_chunk_text(value: object) -> str:
    if type(value) is not str:
        raise TypeError("text must be a string")
    if "\x00" in value:
        raise ValueError("text must not contain NUL")
    if not value.strip():
        raise ValueError("text must be nonblank")
    if len(value) > _MAX_CHUNK_CHARS:
        raise ValueError("text exceeds the chunk character limit")
    return value


def _require_source_path(value: object) -> str:
    path = _require_nonblank(value, "source_path")
    segments = path.split("/")
    if (
        path.startswith("/")
        or _WINDOWS_ABSOLUTE.match(path)
        or "\\" in path
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError("source_path must be a repository-relative POSIX path")
    return path


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_digest(value: object) -> str:
    if type(value) is not str:
        raise TypeError("source_sha256 must be a string")
    if not _LOWER_SHA256.fullmatch(value):
        raise ValueError("source_sha256 must be lowercase 64-hex")
    return value


def _require_strict_nonblank(value: object, field_name: str) -> str:
    return _require_nonblank(value, field_name)


def _is_non_bool_int(value: object) -> bool:
    return type(value) is int


def _string_or_none(value: object) -> str | None:
    return value if type(value) is str else None


def _is_nonblank_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_sequence(
    values: Sequence[object], expected_type: type[Any], field_name: str
) -> tuple[Any, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    normalized: list[Any] = []
    for value in values:
        if not isinstance(value, expected_type):
            raise TypeError(f"{field_name} must contain {expected_type.__name__} instances")
        normalized.append(value)
    return tuple(normalized)
