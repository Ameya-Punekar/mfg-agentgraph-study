"""Immutable preparation of a deterministic request for a local Ollama model."""

from __future__ import annotations

import http.client
import json
from dataclasses import dataclass, field
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
from math import isfinite
from typing import Any, cast
from urllib.parse import urlsplit

from mfg_agentgraph.candidate_action import (
    CandidateAction,
    CandidateActionError,
    CandidateActionPlan,
    parse_candidate_actions,
)
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.procedural_retrieval import ProceduralRetrievalResult, ProceduralSupportRecord
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import (
    StructuredObservation,
    StructuredRetrievalResult,
    StructuredSupportRecord,
)

OLLAMA_PROMPT_ID = "ollama-prompt:candidate-action-v1"
OLLAMA_SCHEMA_ID = "candidate-action-schema:v1"
_MAX_IDENTIFIER_BYTES = 1_024
_MAX_SEED = 2_147_483_647
_MAX_NUM_PREDICT = 4_096
_MAX_EVIDENCE_BYTES = 8_192
_MAX_PROMPT_BYTES = 32_768
_MAX_REQUEST_BYTES = 65_536
_MAX_SIGNED_INT64 = 9_223_372_036_854_775_807
_SYSTEM_TEXT = (
    "Return only candidate-action JSON matching the supplied schema. Use only the supplied "
    "asset and evidence identifiers; do not invent identifiers."
)
_PREPARATION_ERROR = "invalid Ollama request prerequisites"
_GENERATION_RESULT_ERROR = "invalid Ollama generation result"
_GENERATION_INPUT_ERROR = "invalid Ollama generation input"
_MAX_RAW_CANDIDATE_BYTES = 262_144
_MAX_ACTION_CHARS = 2_048
_MAX_ACTION_BYTES = 4_096
_MAX_METADATA_BYTES = 256
_METADATA_KEYS = (
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
)


class _PreparationError(ValueError):
    """The sole public preparation failure."""

    __slots__ = ("category",)

    def __init__(
        self, message: str = _PREPARATION_ERROR, category: OllamaFailureCategory | None = None
    ) -> None:
        self.category = category or OllamaFailureCategory.PREREQUISITE
        super().__init__(message)


class _RequestPreparationError(ValueError):
    """A sanitized preparation failure caused by request construction bounds."""


class OllamaFailureCategory(StrEnum):
    """Stable failure categories for the Ollama generation boundary."""

    PREREQUISITE = "prerequisite"
    REQUEST = "request"
    TRANSPORT = "transport"
    HTTP_STATUS = "http_status"
    RESPONSE_HEADERS = "response_headers"
    RESPONSE_SIZE = "response_size"
    RESPONSE_ENCODING = "response_encoding"
    RESPONSE_JSON = "response_json"
    RESPONSE_ENVELOPE = "response_envelope"
    CANDIDATE_SCHEMA = "candidate_schema"
    CANDIDATE_VALIDATION = "candidate_validation"
    INTERNAL = "internal"


class _AdapterFailure(Exception):
    """Sanitized private failure at the Ollama transport boundary."""

    __slots__ = ("category",)

    def __init__(self, category: OllamaFailureCategory) -> None:
        if type(category) is not OllamaFailureCategory:
            raise TypeError("category must be an OllamaFailureCategory")
        self.category = category
        super().__init__(category.value)

    def __repr__(self) -> str:
        return "_AdapterFailure(<redacted>)"

    def __str__(self) -> str:
        return self.category.value


@dataclass(frozen=True, slots=True)
class _OllamaEnvelope:
    content: str
    metadata: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class OllamaCandidateGenerationResult:
    """Immutable, fully correlated terminal result of candidate generation."""

    status: TerminalStatus
    plan: CandidateActionPlan | None
    raw_json: str | None
    evidence_catalog: EvidenceCatalog | None
    evidence_references: tuple[EvidenceReference, ...]
    model_id: str
    runtime_id: str
    prompt_id: str
    schema_id: str
    metadata: tuple[tuple[str, int], ...]
    event: StageEvent

    def __post_init__(self) -> None:
        failed = False
        try:
            self._validate()
        except (TypeError, ValueError, UnicodeError):
            failed = True
        if failed:
            raise ValueError(_GENERATION_RESULT_ERROR) from None

    def _validate(self) -> None:
        if type(self.status) is not TerminalStatus:
            _result_fail()
        if type(self.prompt_id) is not str or self.prompt_id != OLLAMA_PROMPT_ID:
            _result_fail()
        if type(self.schema_id) is not str or self.schema_id != OLLAMA_SCHEMA_ID:
            _result_fail()
        _result_text(self.model_id, _MAX_IDENTIFIER_BYTES)
        _result_text(self.runtime_id, _MAX_IDENTIFIER_BYTES)
        if type(self.evidence_references) is not tuple:
            _result_fail()
        _result_metadata(self.metadata)
        _result_event(self.event, self.status)
        if self.status is TerminalStatus.PASSED:
            _result_passed(self)
        elif self.status is TerminalStatus.VALIDATION_FAILED_CLOSED:
            _result_failed(self)
        else:
            _result_fail()


def _result_fail() -> None:
    raise ValueError(_GENERATION_RESULT_ERROR)


def _result_text(value: object, limit: int) -> None:
    if type(value) is not str:
        _result_fail()
    value = cast(str, value)
    if not value or value != value.strip():
        _result_fail()
    if any(
        ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF for char in value
    ):
        _result_fail()
    if len(value.encode("utf-8")) > limit:
        _result_fail()


def _result_candidate_text(value: object, limit: int) -> None:
    if type(value) is not str or not value.strip():
        _result_fail()
    value = cast(str, value)
    try:
        if len(value.encode("utf-8")) > limit:
            _result_fail()
        _scan_json(value, max_depth=5, max_tokens=512)
    except (UnicodeError, ValueError):
        _result_fail()


def _result_metadata(value: object) -> None:
    if type(value) is not tuple:
        _result_fail()
    value = cast(tuple[object, ...], value)
    keys: list[str] = []
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            _result_fail()
        key, metric = cast(tuple[object, object], item)
        if type(key) is not str or key not in _METADATA_KEYS:
            _result_fail()
        if type(metric) is not int or metric < 0 or metric > _MAX_SIGNED_INT64:
            _result_fail()
        keys.append(cast(str, key))
    if keys != [key for key in _METADATA_KEYS if key in keys] or len(set(keys)) != len(keys):
        _result_fail()
    try:
        encoded = json.dumps(
            dict(cast(tuple[tuple[str, int], ...], value)),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError):
        _result_fail()
    if len(encoded) > _MAX_METADATA_BYTES:
        _result_fail()


def _result_event(value: object, status: TerminalStatus) -> None:
    if type(value) is not StageEvent:
        _result_fail()
    event = cast(StageEvent, value)
    if (
        type(event.stage) is not StageName
        or event.stage is not StageName.CANDIDATE_GENERATION
        or event.status is not status
        or event.duration_ms is not None
        or type(event.run_id) is not str
        or type(event.input_ids) is not tuple
        or type(event.output_ids) is not tuple
        or type(event.errors) is not tuple
        or type(event.retry_count) is not int
        or type(event.repair_count) is not int
        or event.retry_count != 0
        or event.repair_count != 0
    ):
        _result_fail()
    _result_text(event.run_id, _MAX_IDENTIFIER_BYTES)
    for identifier in (*event.input_ids, *event.output_ids):
        _result_text(identifier, _MAX_EVIDENCE_BYTES)


def _result_passed(result: OllamaCandidateGenerationResult) -> None:
    if type(result.plan) is not CandidateActionPlan or type(result.raw_json) is not str:
        _result_fail()
    if type(result.evidence_catalog) is not EvidenceCatalog:
        _result_fail()
    _result_candidate_text(result.raw_json, _MAX_RAW_CANDIDATE_BYTES)
    refs = result.evidence_references
    if len(refs) != 2 or any(type(ref) is not EvidenceReference for ref in refs):
        _result_fail()
    assert result.evidence_catalog is not None
    if (
        type(result.evidence_catalog.references) is not tuple
        or result.evidence_catalog.references is not refs
    ):
        _result_fail()
    if refs[0].kind is not EvidenceKind.KG_EDGE or refs[1].kind is not EvidenceKind.DOCUMENT_CHUNK:
        _result_fail()
    if any(ref.validation_status is not EvidenceValidationStatus.VALIDATED for ref in refs):
        _result_fail()
    for ref in refs:
        if type(ref.retrieval) is not RetrievalMetadata:
            _result_fail()
        _result_text(ref.stable_id, _MAX_EVIDENCE_BYTES)
        _result_text(ref.source, _MAX_IDENTIFIER_BYTES)
        _result_text(ref.retrieval.retrieval_run_id, _MAX_IDENTIFIER_BYTES)
        _result_text(ref.retrieval.query_id, _MAX_IDENTIFIER_BYTES)
        _result_text(ref.retrieval.retriever_name, _MAX_IDENTIFIER_BYTES)
        if (
            type(ref.retrieval.rank) is not int
            or ref.retrieval.rank < 1
            or ref.retrieval.rank > _MAX_SIGNED_INT64
        ):
            _result_fail()
        if ref.retrieval.score is not None and (
            type(ref.retrieval.score) is not float or not isfinite(ref.retrieval.score)
        ):
            _result_fail()
    plan = cast(CandidateActionPlan, result.plan)
    actions = plan.ranked_actions
    if type(actions) is not tuple or not 1 <= len(actions) <= 8:
        _result_fail()
    if any(type(action) is not CandidateAction for action in actions):
        _result_fail()
    targets: list[str] = []
    used_refs: set[int] = set()
    for expected_rank, action in enumerate(actions, 1):
        if type(action.rank) is not int or action.rank != expected_rank:
            _result_fail()
        _result_text(action.action, _MAX_ACTION_BYTES)
        if len(action.action) > _MAX_ACTION_CHARS:
            _result_fail()
        _result_text(action.target_asset, _MAX_IDENTIFIER_BYTES)
        if type(action.support_evidence) is not tuple or not action.support_evidence:
            _result_fail()
        action_ref_ids: set[int] = set()
        for ref in action.support_evidence:
            if ref is not refs[0] and ref is not refs[1]:
                _result_fail()
            reference_id = id(ref)
            if reference_id in action_ref_ids:
                _result_fail()
            action_ref_ids.add(reference_id)
            used_refs.add(reference_id)
        targets.append(action.target_asset)
    if len(set(targets)) != 1:
        _result_fail()
    if used_refs != {id(refs[0]), id(refs[1])}:
        _result_fail()
    query_id = refs[0].retrieval.query_id
    if refs[1].retrieval.query_id != query_id:
        _result_fail()
    event = result.event
    if event.input_ids != (targets[0], query_id, refs[0].stable_id, refs[1].stable_id):
        _result_fail()
    if event.output_ids != tuple(f"candidate-action-rank:{action.rank}" for action in actions):
        _result_fail()
    if event.errors:
        _result_fail()


def _result_failed(result: OllamaCandidateGenerationResult) -> None:
    if (
        result.plan is not None
        or result.raw_json is not None
        or result.evidence_catalog is not None
    ):
        _result_fail()
    if result.evidence_references or result.metadata:
        _result_fail()
    event = result.event
    if len(event.input_ids) != 1 or event.output_ids:
        _result_fail()
    if len(event.errors) != 1 or type(event.errors[0]) is not StageError:
        _result_fail()
    error = event.errors[0]
    if (
        error.code is not StageErrorCode.CANDIDATE_GENERATION_FAILED
        or type(error.field) is not str
        or error.field not in {category.value for category in OllamaFailureCategory}
        or error.detail is not None
    ):
        _result_fail()


@dataclass(frozen=True, slots=True)
class _PreparedOllamaRequest:
    endpoint: str
    request_line: bytes
    serialized_body: bytes
    headers: tuple[tuple[str, str], ...]
    asset_id: str
    observation_id: str
    procedure_id: str
    generation_run_id: str
    query_id: str
    evidence_references: tuple[EvidenceReference, EvidenceReference] = field(repr=False)
    evidence_catalog: EvidenceCatalog = field(repr=False)


@dataclass(frozen=True, slots=True)
class _ObservationSnapshot:
    observation_id: str
    observed_asset: str
    observed_at: str
    signal: str
    anomaly: str
    description: str


@dataclass(frozen=True, slots=True)
class _StructuredSnapshot:
    evidence_id: str
    subject: str
    predicate: str
    procedure_id: str
    required_observation_id: str


@dataclass(frozen=True, slots=True)
class _ProceduralSnapshot:
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


@dataclass(frozen=True, slots=True)
class _EvidenceSnapshot:
    kind: EvidenceKind
    source: str
    stable_id: str
    retrieval_run_id: str
    query_id: str
    retriever_name: str
    rank: int
    score: float | None
    validation_status: EvidenceValidationStatus


@dataclass(frozen=True, slots=True)
class _CatalogSnapshot:
    references: tuple[EvidenceReference, ...]
    evidence: tuple[_EvidenceSnapshot, ...]


@dataclass(frozen=True, slots=True)
class _EventSnapshot:
    stage: StageName
    run_id: str
    status: TerminalStatus
    duration_ms: int | None
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    errors: tuple[StageError, ...]
    retry_count: int
    repair_count: int


@dataclass(frozen=True, slots=True)
class OllamaModelAdapterConfig:
    """Validated, immutable configuration for the local Ollama adapter."""

    base_url: str
    model_id: str
    runtime_id: str
    timeout_seconds: float = 30.0
    seed: int = 0
    num_predict: int = 512
    _transport_endpoint: tuple[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        endpoint = _parse_transport_endpoint(self.base_url)
        model_id = _validate_text(self.model_id, "model_id")
        runtime_id = _validate_text(self.runtime_id, "runtime_id")
        if type(self.timeout_seconds) is not float:
            raise TypeError("timeout_seconds must be an exact built-in float")
        if not isfinite(self.timeout_seconds) or not 0.1 <= self.timeout_seconds <= 120.0:
            raise ValueError("timeout_seconds must be finite and between 0.1 and 120.0")
        if type(self.seed) is not int:
            raise TypeError("seed must be an exact built-in int")
        if not 0 <= self.seed <= _MAX_SEED:
            raise ValueError("seed must be between 0 and 2147483647")
        if type(self.num_predict) is not int:
            raise TypeError("num_predict must be an exact built-in int")
        if not 1 <= self.num_predict <= _MAX_NUM_PREDICT:
            raise ValueError("num_predict must be between 1 and 4096")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "runtime_id", runtime_id)
        object.__setattr__(self, "_transport_endpoint", endpoint)


@dataclass(frozen=True, slots=True)
class OllamaCandidateAdapter:
    """Minimal immutable adapter shell for a validated Ollama configuration."""

    config: OllamaModelAdapterConfig

    def __post_init__(self) -> None:
        if type(self.config) is not OllamaModelAdapterConfig:
            raise TypeError("config must be an OllamaModelAdapterConfig")

    def generate(
        self,
        structured_result: StructuredRetrievalResult,
        procedural_result: ProceduralRetrievalResult,
        generation_run_id: str,
        query_id: str,
    ) -> OllamaCandidateGenerationResult:
        """Generate and strictly accept one bounded local candidate response."""
        try:
            generation_run_id = _strict_text(generation_run_id, _MAX_IDENTIFIER_BYTES)
            query_id = _strict_text(query_id, _MAX_IDENTIFIER_BYTES)
        except (TypeError, ValueError, UnicodeError):
            raise ValueError(_GENERATION_INPUT_ERROR) from None

        try:
            prepared = self._prepare_request(
                structured_result, procedural_result, generation_run_id, query_id
            )
        except _PreparationError as exc:
            return self._failed_result(generation_run_id, query_id, exc.category)
        except Exception:
            return self._failed_result(generation_run_id, query_id, OllamaFailureCategory.INTERNAL)

        try:
            envelope = self._exchange(prepared)
        except _AdapterFailure as exc:
            return self._failed_result(generation_run_id, query_id, exc.category)
        except Exception:
            return self._failed_result(generation_run_id, query_id, OllamaFailureCategory.INTERNAL)

        try:
            _validate_candidate_shape(envelope.content)
        except _AdapterFailure as exc:
            return self._failed_result(generation_run_id, query_id, exc.category)
        except Exception:
            return self._failed_result(
                generation_run_id, query_id, OllamaFailureCategory.CANDIDATE_SCHEMA
            )

        try:
            plan = parse_candidate_actions(
                envelope.content,
                known_assets=(prepared.asset_id,),
                evidence_catalog=prepared.evidence_catalog,
            )
        except _AdapterFailure:
            raise
        except CandidateActionError:
            return self._failed_result(
                generation_run_id, query_id, OllamaFailureCategory.CANDIDATE_VALIDATION
            )
        except Exception:
            return self._failed_result(generation_run_id, query_id, OllamaFailureCategory.INTERNAL)

        try:
            return OllamaCandidateGenerationResult(
                status=TerminalStatus.PASSED,
                plan=plan,
                raw_json=envelope.content,
                evidence_catalog=prepared.evidence_catalog,
                evidence_references=prepared.evidence_references,
                model_id=self.config.model_id,
                runtime_id=self.config.runtime_id,
                prompt_id=OLLAMA_PROMPT_ID,
                schema_id=OLLAMA_SCHEMA_ID,
                metadata=envelope.metadata,
                event=StageEvent(
                    StageName.CANDIDATE_GENERATION,
                    generation_run_id,
                    TerminalStatus.PASSED,
                    input_ids=(
                        prepared.asset_id,
                        query_id,
                        prepared.evidence_references[0].stable_id,
                        prepared.evidence_references[1].stable_id,
                    ),
                    output_ids=tuple(
                        f"candidate-action-rank:{action.rank}" for action in plan.ranked_actions
                    ),
                ),
            )
        except Exception:
            return self._failed_result(generation_run_id, query_id, OllamaFailureCategory.INTERNAL)

    def _failed_result(
        self, generation_run_id: str, query_id: str, category: OllamaFailureCategory
    ) -> OllamaCandidateGenerationResult:
        return OllamaCandidateGenerationResult(
            status=TerminalStatus.VALIDATION_FAILED_CLOSED,
            plan=None,
            raw_json=None,
            evidence_catalog=None,
            evidence_references=(),
            model_id=self.config.model_id,
            runtime_id=self.config.runtime_id,
            prompt_id=OLLAMA_PROMPT_ID,
            schema_id=OLLAMA_SCHEMA_ID,
            metadata=(),
            event=StageEvent(
                StageName.CANDIDATE_GENERATION,
                generation_run_id,
                TerminalStatus.VALIDATION_FAILED_CLOSED,
                input_ids=(query_id,),
                errors=(StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, category.value),),
            ),
        )

    def _prepare_request(
        self,
        structured_result: StructuredRetrievalResult,
        procedural_result: ProceduralRetrievalResult,
        generation_run_id: str,
        query_id: str,
    ) -> _PreparedOllamaRequest:
        result: _PreparedOllamaRequest | None = None
        failed = False
        category = OllamaFailureCategory.PREREQUISITE
        try:
            result = self._prepare_request_impl(
                structured_result, procedural_result, generation_run_id, query_id
            )
        except _RequestPreparationError:
            failed = True
            category = OllamaFailureCategory.REQUEST
        except Exception:
            failed = True
        if failed or result is None:
            raise _PreparationError(_PREPARATION_ERROR, category) from None
        return result

    def _prepare_request_impl(
        self,
        structured_result: StructuredRetrievalResult,
        procedural_result: ProceduralRetrievalResult,
        generation_run_id: str,
        query_id: str,
    ) -> _PreparedOllamaRequest:
        if type(structured_result) is not StructuredRetrievalResult:
            _fail()
        if type(procedural_result) is not ProceduralRetrievalResult:
            _fail()
        generation_run_id = _strict_text(generation_run_id, _MAX_IDENTIFIER_BYTES)
        query_id = _strict_text(query_id, _MAX_IDENTIFIER_BYTES)

        sr_status = structured_result.status
        sr_asset = structured_result.asset
        sr_event = structured_result.event
        sr_observations = _tuple_field(structured_result.observations, 1)
        sr_support = _tuple_field(structured_result.support_records, 1)
        sr_refs = _tuple_field(structured_result.evidence_references, 1)
        sr_catalog = _catalog_snapshot(structured_result.evidence_catalog, sr_refs)
        pr_status = procedural_result.status
        pr_asset = procedural_result.asset
        pr_event = procedural_result.event
        pr_support = _tuple_field(procedural_result.support_records, 1)
        pr_refs = _tuple_field(procedural_result.evidence_references, 1)
        pr_catalog = _catalog_snapshot(procedural_result.evidence_catalog, pr_refs)

        asset = _asset_snapshot(sr_asset, pr_asset)
        observation = _observation_snapshot(sr_observations[0])
        structure = _structured_snapshot(sr_support[0])
        procedure = _procedural_snapshot(pr_support[0])
        kg = _evidence_snapshot(sr_refs[0])
        document = _evidence_snapshot(pr_refs[0])
        structured_event = _event_snapshot(sr_event, 2, 3)
        procedural_event = _event_snapshot(pr_event, 2, 1)
        _validate_coherence(
            sr_status,
            pr_status,
            asset,
            observation,
            structure,
            procedure,
            kg,
            document,
            sr_catalog,
            pr_catalog,
            structured_event,
            procedural_event,
            query_id,
        )

        user_object = {
            "asset": {"id": asset[0], "type": procedure.applicable_asset_type},
            "evidence": [
                {"id": kg.stable_id, "type": kg.kind.value},
                {"id": document.stable_id, "type": document.kind.value},
            ],
            "observation": {"id": observation.observation_id, "signal": observation.signal},
            "procedure": {"id": structure.procedure_id},
        }
        user_text = _serialize(user_object)
        prompt_bytes = len(_SYSTEM_TEXT.encode("utf-8")) + len(user_text.encode("utf-8"))
        if prompt_bytes > _MAX_PROMPT_BYTES:
            _request_fail()
        body = {
            "model": self.config.model_id,
            "messages": [
                {"role": "system", "content": _SYSTEM_TEXT},
                {"role": "user", "content": user_text},
            ],
            "format": _ollama_schema(),
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {
                "temperature": 0,
                "seed": self.config.seed,
                "num_predict": self.config.num_predict,
            },
        }
        serialized_body = _serialize_bytes(body)
        host, port = self.config._transport_endpoint
        host_header = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        headers = (
            ("Host", host_header),
            ("Content-Type", "application/json"),
            ("Accept", "application/json"),
            ("Content-Length", str(len(serialized_body))),
            ("Connection", "close"),
        )
        request_line = b"POST /api/chat HTTP/1.1\r\n"
        wire_size = (
            len(request_line)
            + sum(
                len(name.encode("ascii")) + 2 + len(value.encode("latin-1")) + 2
                for name, value in headers
            )
            + 2
            + len(serialized_body)
        )
        if wire_size > _MAX_REQUEST_BYTES:
            _request_fail()
        references = (sr_refs[0], pr_refs[0])
        catalog = EvidenceCatalog(references)
        object.__setattr__(catalog, "references", references)
        return _PreparedOllamaRequest(
            endpoint=f"{self.config.base_url}/api/chat",
            request_line=request_line,
            serialized_body=serialized_body,
            headers=headers,
            asset_id=asset[0],
            observation_id=observation.observation_id,
            procedure_id=structure.procedure_id,
            generation_run_id=generation_run_id,
            query_id=query_id,
            evidence_references=references,
            evidence_catalog=catalog,
        )

    def _exchange(self, prepared: _PreparedOllamaRequest) -> _OllamaEnvelope:
        """Perform one bounded HTTP exchange and validate only Ollama's envelope."""
        if type(prepared) is not _PreparedOllamaRequest:
            raise _AdapterFailure(OllamaFailureCategory.REQUEST) from None
        host, port = self.config._transport_endpoint
        connection: http.client.HTTPConnection | None = None
        failure: _AdapterFailure | None = None
        result: _OllamaEnvelope | None = None
        try:
            connection = http.client.HTTPConnection(host, port, timeout=self.config.timeout_seconds)
            connection.putrequest("POST", "/api/chat", skip_host=True, skip_accept_encoding=True)
            for name, value in prepared.headers:
                connection.putheader(name, value)
            connection.endheaders(prepared.serialized_body)
            response = connection.getresponse()
            if type(response.status) is not int or response.status != 200:
                failure = _AdapterFailure(OllamaFailureCategory.HTTP_STATUS)
            else:
                declared = _response_headers(response)
                raw = response.read(1_000_001)
                if type(raw) is not bytes:
                    failure = _AdapterFailure(OllamaFailureCategory.TRANSPORT)
                elif len(raw) > 1_000_000:
                    failure = _AdapterFailure(OllamaFailureCategory.RESPONSE_SIZE)
                elif declared is not None and len(raw) != declared:
                    failure = _AdapterFailure(OllamaFailureCategory.RESPONSE_HEADERS)
                else:
                    result = _parse_envelope(raw, self.config.model_id)
        except _AdapterFailure as exc:
            failure = _AdapterFailure(exc.category)
        except (TimeoutError, OSError, http.client.HTTPException):
            failure = _AdapterFailure(OllamaFailureCategory.TRANSPORT)
        except Exception:
            failure = _AdapterFailure(OllamaFailureCategory.INTERNAL)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except (TimeoutError, OSError, http.client.HTTPException):
                    if failure is None:
                        failure = _AdapterFailure(OllamaFailureCategory.TRANSPORT)
                except Exception:
                    if failure is None:
                        failure = _AdapterFailure(OllamaFailureCategory.INTERNAL)
        if failure is not None:
            raise _AdapterFailure(failure.category) from None
        if result is not None:
            return result
        raise _AdapterFailure(OllamaFailureCategory.INTERNAL) from None


def _candidate_scalar(value: object, limit: int) -> str:
    if type(value) is not str or not value:
        raise ValueError
    assert type(value) is str
    if any(
        ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF for char in value
    ):
        raise ValueError
    if len(value.encode("utf-8")) > limit:
        raise ValueError
    return value


def _validate_candidate_shape(content: str) -> None:
    """Apply only fixed resource/shape checks before the authoritative parser."""
    value = _decode_json(content)
    if type(value) is not dict or set(value) != {"ranked_actions"}:
        raise ValueError
    actions = value["ranked_actions"]
    if type(actions) is not list or not 1 <= len(actions) <= 8:
        raise ValueError
    for action in actions:
        if type(action) is not dict or set(action) != {
            "rank",
            "action",
            "target_asset",
            "support_evidence",
        }:
            raise ValueError
        rank = action["rank"]
        if type(rank) is not int or not 1 <= rank <= 8:
            raise ValueError
        action_text = _candidate_scalar(action["action"], _MAX_ACTION_BYTES)
        if len(action_text) > _MAX_ACTION_CHARS:
            raise ValueError
        _candidate_scalar(action["target_asset"], 1024)
        support = action["support_evidence"]
        if type(support) is not list or not 1 <= len(support) <= 16:
            raise ValueError
        for reference in support:
            if type(reference) is not dict or set(reference) != {"type", "id"}:
                raise ValueError
            if type(reference["type"]) is not str or reference["type"] not in {
                EvidenceKind.KG_EDGE.value,
                EvidenceKind.DOCUMENT_CHUNK.value,
            }:
                raise ValueError
            _candidate_scalar(reference["id"], _MAX_EVIDENCE_BYTES)


def _ollama_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ranked_actions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "rank": {"type": "integer", "minimum": 1, "maximum": 8},
                        "action": {"type": "string", "minLength": 1},
                        "target_asset": {"type": "string", "minLength": 1},
                        "support_evidence": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 16,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["kg_edge", "document_chunk"],
                                    },
                                    "id": {"type": "string", "minLength": 1},
                                },
                                "required": ["type", "id"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["rank", "action", "target_asset", "support_evidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["ranked_actions"],
        "additionalProperties": False,
    }


def _response_headers(response: Any) -> int | None:
    failed = False
    declared: int | None = None
    try:
        headers = response.getheaders()
        if type(headers) is not list or len(headers) > 32:
            raise ValueError
        total = 2
        content_types: list[str] = []
        lengths: list[str] = []
        for pair in headers:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError
            name, value = pair
            if type(name) is not str or type(value) is not str or not name:
                raise ValueError
            if any(
                ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF
                for c in name + value
            ):
                raise ValueError
            total += len(name.encode("ascii")) + 2 + len(value.encode("latin-1")) + 2
            if total > 32_768:
                raise ValueError
            lowered = name.lower()
            if lowered in {"transfer-encoding", "content-encoding"}:
                raise ValueError
            if lowered == "content-type":
                content_types.append(value)
            elif lowered == "content-length":
                lengths.append(value)
        if len(content_types) != 1:
            raise ValueError
        if content_types[0] not in {"application/json", "application/json; charset=utf-8"}:
            raise ValueError
        if len(lengths) > 1:
            raise ValueError
        if lengths:
            length = lengths[0]
            if (
                not length
                or any(c < "0" or c > "9" for c in length)
                or (length != "0" and length.startswith("0"))
            ):
                raise ValueError
            declared = int(length)
            if declared > 1_000_000:
                raise ValueError
    except Exception:
        failed = True
    if failed:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_HEADERS) from None
    return declared


def _scan_json(text: str, *, max_depth: int, max_tokens: int) -> None:
    depth = tokens = index = 0
    stack: list[str] = []
    while index < len(text):
        char = text[index]
        if char == '"':
            index += 1
            while index < len(text):
                char = text[index]
                if ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF:
                    raise ValueError
                if char == '"':
                    break
                if char == "\\":
                    index += 1
                    if index >= len(text) or text[index] not in '"\\/bfnrtu':
                        raise ValueError
                    if text[index] == "u":
                        digits = text[index + 1 : index + 5]
                        if len(digits) != 4 or any(
                            c not in "0123456789abcdefABCDEF" for c in digits
                        ):
                            raise ValueError
                        codepoint = int(digits, 16)
                        if (
                            codepoint < 32
                            or 127 <= codepoint <= 159
                            or 0xD800 <= codepoint <= 0xDFFF
                        ):
                            raise ValueError
                        index += 4
                index += 1
            else:
                raise ValueError
        elif ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF:
            if char not in "\t\n\r":
                raise ValueError
        elif char in "[{":
            stack.append("]" if char == "[" else "}")
            depth += 1
            tokens += 1
            if depth > max_depth:
                raise ValueError
        elif char in "]}":
            if not stack or stack.pop() != char:
                raise ValueError
            depth -= 1
            tokens += 1
        elif char in ",:":
            tokens += 1
        index += 1
    if stack or depth or tokens > max_tokens:
        raise ValueError


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _decode_json(text: str) -> Any:
    value: Any = None
    failed = False
    try:
        value = json.loads(
            text,
            object_pairs_hook=_json_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except Exception:
        failed = True
    if failed:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_JSON) from None
    return value


def _valid_response_text(value: object, limit: int, *, nonblank: bool = True) -> str:
    if type(value) is not str or (nonblank and not value.strip()):
        raise ValueError
    assert type(value) is str
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError
    if len(value.encode("utf-8")) > limit:
        raise ValueError
    return value


def _valid_candidate_content(value: object, limit: int) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError
    assert type(value) is str
    if len(value.encode("utf-8")) > limit:
        raise ValueError
    return value


def _parse_envelope(raw: bytes, model_id: str) -> _OllamaEnvelope:
    text: str | None = None
    encoding_failed = False
    json_failed = False
    try:
        text = raw.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise UnicodeError
        _valid_response_text(text, 1_000_000)
        _scan_json(text, max_depth=3, max_tokens=512)
    except UnicodeError:
        encoding_failed = True
    except Exception:
        json_failed = True
    if encoding_failed:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_ENCODING) from None
    if json_failed or text is None:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_JSON) from None
    value = _decode_json(text)
    if type(value) is not dict:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_ENVELOPE) from None
    required = {"model", "created_at", "message", "done", "done_reason"}
    if set(value) - (required | set(_METADATA_KEYS)) or not required.issubset(value):
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_ENVELOPE) from None
    envelope_failed = False
    content: str | None = None
    metadata: list[tuple[str, int]] = []
    try:
        if type(value["model"]) is not str or value["model"] != model_id:
            raise ValueError
        _valid_response_text(value["model"], 1024)
        _valid_response_text(value["created_at"], 64)
        if (
            value["done"] is not True
            or type(value["done_reason"]) is not str
            or value["done_reason"] != "stop"
        ):
            raise ValueError
        message = value["message"]
        if (
            type(message) is not dict
            or set(message) != {"role", "content"}
            or type(message["role"]) is not str
            or message["role"] != "assistant"
        ):
            raise ValueError
        if (
            type(message["content"]) is str
            and len(message["content"].encode("utf-8")) > _MAX_RAW_CANDIDATE_BYTES
        ):
            raise _AdapterFailure(OllamaFailureCategory.RESPONSE_SIZE) from None
        content = _valid_candidate_content(message["content"], _MAX_RAW_CANDIDATE_BYTES)
        metadata = []
        for key in _METADATA_KEYS:
            if key in value:
                metric = value[key]
                if type(metric) is not int or not 0 <= metric <= _MAX_SIGNED_INT64:
                    raise ValueError
                metadata.append((key, metric))
        if (
            len(
                json.dumps(
                    dict(metadata),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            )
            > _MAX_METADATA_BYTES
        ):
            raise ValueError
    except _AdapterFailure:
        raise
    except Exception:
        envelope_failed = True
    if envelope_failed or content is None:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_ENVELOPE) from None
    content_scan_failed = False
    try:
        _scan_json(content, max_depth=5, max_tokens=512)
    except Exception:
        content_scan_failed = True
    if content_scan_failed:
        raise _AdapterFailure(OllamaFailureCategory.RESPONSE_JSON) from None
    return _OllamaEnvelope(content, tuple(metadata))


def _fail() -> None:
    raise ValueError("invalid")


def _request_fail() -> None:
    raise _RequestPreparationError


def _validate_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact built-in str")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be nonblank")
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise ValueError(f"{field_name} contains a control character")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError(f"{field_name} contains a surrogate")
    if len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(f"{field_name} exceeds {_MAX_IDENTIFIER_BYTES} UTF-8 bytes")
    return value


def _validate_scalar_text(value: object, limit: int) -> str:
    if type(value) is not str or not value or not value.strip():
        _fail()
    assert type(value) is str
    if value != value.strip() or any(
        ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value
    ):
        _fail()
    if len(value.encode("utf-8")) > limit:
        _fail()
    return value


def _strict_text(value: object, limit: int) -> str:
    try:
        return _validate_scalar_text(value, limit)
    except (UnicodeError, TypeError, ValueError):
        _fail()
    raise AssertionError("unreachable")


def _parse_transport_endpoint(value: object) -> tuple[str, int]:
    base_url = _validate_text(value, "base_url")
    if not base_url.startswith("http://"):
        raise ValueError("base_url must use the canonical HTTP scheme")
    malformed = False
    try:
        parsed = urlsplit(base_url)
    except ValueError:
        malformed = True
        parsed = None
    if malformed or parsed is None:
        raise ValueError("base_url is not a valid URL")
    if parsed.scheme != "http" or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("base_url must be an HTTP loopback root URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not contain userinfo")
    hostname = parsed.hostname
    if hostname == "127.0.0.1" and parsed.netloc.count(":") == 1:
        host, port_text = hostname, parsed.netloc.rsplit(":", 1)[1]
        if type(ip_address(host)) is not IPv4Address:
            raise ValueError("invalid host")
    elif hostname == "::1" and parsed.netloc.startswith("[::1]:"):
        host, port_text = hostname, parsed.netloc[len("[::1]:") :]
        if type(ip_address(host)) is not IPv6Address:
            raise ValueError("invalid host")
    else:
        raise ValueError("base_url must target loopback")
    if not port_text or not port_text.isdecimal() or str(int(port_text)) != port_text:
        raise ValueError("base_url must include a canonical decimal port")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError("invalid port")
    expected = f"{host}:{port}" if host == "127.0.0.1" else f"[{host}]:{port}"
    if parsed.netloc != expected or base_url != f"http://{expected}":
        raise ValueError("base_url must use canonical loopback syntax")
    return host, port


def _tuple_field(value: object, cardinality: int) -> tuple[Any, ...]:
    if type(value) is not tuple or len(value) != cardinality:
        _fail()
    assert type(value) is tuple
    return tuple(value)


def _validate_signed_int(value: object, *, lower: int = 0) -> int:
    if type(value) is not int or value < lower or value > _MAX_SIGNED_INT64:
        _fail()
    assert type(value) is int
    return value


def _catalog_snapshot(value: object, expected: tuple[Any, ...]) -> _CatalogSnapshot:
    if type(value) is not EvidenceCatalog:
        _fail()
    assert type(value) is EvidenceCatalog
    refs = _tuple_field(value.references, len(expected))
    for actual, required in zip(refs, expected, strict=True):
        if actual is not required:
            _fail()
    return _CatalogSnapshot(refs, tuple(_evidence_snapshot(ref) for ref in refs))


def _asset_snapshot(first: object, second: object) -> tuple[str, str, tuple[str, ...]]:
    if type(first) is not KnownAsset or type(second) is not KnownAsset:
        _fail()
    first_snapshot = _single_asset_snapshot(first)
    second_snapshot = _single_asset_snapshot(second)
    if first_snapshot != second_snapshot:
        _fail()
    return first_snapshot


def _single_asset_snapshot(value: object) -> tuple[str, str, tuple[str, ...]]:
    if type(value) is not KnownAsset:
        _fail()
    assert type(value) is KnownAsset
    asset_id = _validate_scalar_text(value.asset_id, _MAX_IDENTIFIER_BYTES)
    primary = _validate_scalar_text(value.primary_label, _MAX_IDENTIFIER_BYTES)
    raw_aliases = value.aliases
    if type(raw_aliases) is not tuple:
        _fail()
    aliases = _tuple_field(raw_aliases, len(raw_aliases))
    for alias in aliases:
        _validate_scalar_text(alias, _MAX_IDENTIFIER_BYTES)
    return asset_id, primary, aliases


def _observation_snapshot(value: object) -> _ObservationSnapshot:
    if type(value) is not StructuredObservation:
        _fail()
    assert type(value) is StructuredObservation
    values = tuple(
        _validate_scalar_text(getattr(value, name), _MAX_IDENTIFIER_BYTES)
        for name in (
            "observation_id",
            "observed_asset",
            "observed_at",
            "signal",
            "anomaly",
            "description",
        )
    )
    return _ObservationSnapshot(*values)


def _structured_snapshot(value: object) -> _StructuredSnapshot:
    if type(value) is not StructuredSupportRecord:
        _fail()
    assert type(value) is StructuredSupportRecord
    values = tuple(
        _validate_scalar_text(
            getattr(value, name),
            _MAX_EVIDENCE_BYTES if name == "evidence_id" else _MAX_IDENTIFIER_BYTES,
        )
        for name in (
            "evidence_id",
            "subject",
            "predicate",
            "procedure_id",
            "required_observation_id",
        )
    )
    return _StructuredSnapshot(*values)


def _procedural_snapshot(value: object) -> _ProceduralSnapshot:
    if type(value) is not ProceduralSupportRecord:
        _fail()
    assert type(value) is ProceduralSupportRecord
    text_fields = (
        "evidence_id",
        "document",
        "related_procedure",
        "text",
        "applicable_asset_id",
        "applicable_asset_type",
        "source_path",
        "source_sha256",
        "index_contract_version",
    )
    vals = {name: getattr(value, name) for name in text_fields}
    _validate_scalar_text(vals["evidence_id"], _MAX_EVIDENCE_BYTES)
    for name in text_fields[1:]:
        _validate_scalar_text(vals[name], 1_000_000 if name == "text" else _MAX_IDENTIFIER_BYTES)
    if "\x00" in vals["text"]:
        _fail()
    source_path = vals["source_path"]
    if (
        source_path.startswith("/")
        or "\\" in source_path
        or any(part in {"", ".", ".."} for part in source_path.split("/"))
        or (len(source_path) >= 3 and source_path[1:3] == ":/")
    ):
        _fail()
    chunk_index = value.chunk_index
    start_line = value.start_line
    end_line = value.end_line
    for number in (chunk_index, start_line, end_line):
        _validate_signed_int(number)
    if chunk_index < 0 or start_line <= 0 or end_line <= 0 or start_line > end_line:
        _fail()
    if len(vals["source_sha256"]) != 64 or any(
        c not in "0123456789abcdef" for c in vals["source_sha256"]
    ):
        _fail()
    return _ProceduralSnapshot(
        vals["evidence_id"],
        vals["document"],
        chunk_index,
        vals["related_procedure"],
        vals["text"],
        vals["applicable_asset_id"],
        vals["applicable_asset_type"],
        vals["source_path"],
        start_line,
        end_line,
        vals["source_sha256"],
        vals["index_contract_version"],
    )


def _evidence_snapshot(value: object) -> _EvidenceSnapshot:
    if type(value) is not EvidenceReference:
        _fail()
    assert type(value) is EvidenceReference
    kind, source, stable_id, retrieval, status = (
        value.kind,
        value.source,
        value.stable_id,
        value.retrieval,
        value.validation_status,
    )
    if (
        type(kind) is not EvidenceKind
        or type(status) is not EvidenceValidationStatus
        or type(retrieval) is not RetrievalMetadata
    ):
        _fail()
    source = _validate_scalar_text(source, _MAX_IDENTIFIER_BYTES)
    stable_id = _validate_scalar_text(stable_id, _MAX_EVIDENCE_BYTES)
    retrieval_values = tuple(
        getattr(retrieval, name)
        for name in ("retrieval_run_id", "query_id", "retriever_name", "rank", "score")
    )
    for text in retrieval_values[:3]:
        _validate_scalar_text(text, _MAX_IDENTIFIER_BYTES)
    rank, score = retrieval_values[3:]
    _validate_signed_int(rank, lower=1)
    if score is not None and (type(score) is not float or not isfinite(score)):
        _fail()
    return _EvidenceSnapshot(
        kind,
        source,
        stable_id,
        retrieval_values[0],
        retrieval_values[1],
        retrieval_values[2],
        rank,
        score,
        status,
    )


def _event_snapshot(value: object, input_count: int, output_count: int) -> _EventSnapshot:
    if type(value) is not StageEvent:
        _fail()
    assert type(value) is StageEvent
    stage, run_id, status, duration, inputs, outputs, errors, retry, repair = (
        value.stage,
        value.run_id,
        value.status,
        value.duration_ms,
        value.input_ids,
        value.output_ids,
        value.errors,
        value.retry_count,
        value.repair_count,
    )
    if type(stage) is not StageName or type(status) is not TerminalStatus:
        _fail()
    run_id = _validate_scalar_text(run_id, _MAX_IDENTIFIER_BYTES)
    if duration is not None:
        _validate_signed_int(duration)
    inputs = _tuple_field(inputs, input_count)
    outputs = _tuple_field(outputs, output_count)
    errors = _tuple_field(errors, 0)
    for identifier in inputs + outputs:
        _validate_scalar_text(identifier, _MAX_EVIDENCE_BYTES)
    _validate_signed_int(retry)
    _validate_signed_int(repair)
    return _EventSnapshot(stage, run_id, status, duration, inputs, outputs, errors, retry, repair)


def _validate_coherence(
    sr_status: object,
    pr_status: object,
    asset: tuple[str, str, tuple[str, ...]],
    observation: _ObservationSnapshot,
    structure: _StructuredSnapshot,
    procedure: _ProceduralSnapshot,
    kg: _EvidenceSnapshot,
    document: _EvidenceSnapshot,
    sr_catalog: _CatalogSnapshot,
    pr_catalog: _CatalogSnapshot,
    se: _EventSnapshot,
    pe: _EventSnapshot,
    query_id: str,
) -> None:
    if (
        sr_status is not TerminalStatus.PASSED
        or pr_status is not TerminalStatus.PASSED
        or se.stage is not StageName.STRUCTURED_RETRIEVAL
        or pe.stage is not StageName.PROCEDURAL_RETRIEVAL
        or se.status is not TerminalStatus.PASSED
        or pe.status is not TerminalStatus.PASSED
    ):
        _fail()
    if (
        kg.kind is not EvidenceKind.KG_EDGE
        or document.kind is not EvidenceKind.DOCUMENT_CHUNK
        or kg.validation_status is not EvidenceValidationStatus.VALIDATED
        or document.validation_status is not EvidenceValidationStatus.VALIDATED
    ):
        _fail()
    if (
        kg.query_id != query_id
        or document.query_id != query_id
        or kg.retrieval_run_id != se.run_id
        or document.retrieval_run_id != pe.run_id
        or sr_catalog.evidence != (kg,)
        or pr_catalog.evidence != (document,)
    ):
        _fail()
    if (
        structure.subject != asset[0]
        or structure.predicate != "ex:hasRecommendedProcedure"
        or structure.evidence_id != kg.stable_id
        or structure.required_observation_id != observation.observation_id
        or procedure.evidence_id != document.stable_id
        or procedure.related_procedure != structure.procedure_id
        or procedure.applicable_asset_id != asset[0]
        or observation.observed_asset != asset[0]
    ):
        _fail()
    if (
        se.input_ids != (asset[0], query_id)
        or pe.input_ids != (asset[0], query_id)
        or se.output_ids
        != (observation.observation_id, structure.procedure_id, structure.evidence_id)
        or pe.output_ids != (procedure.evidence_id,)
    ):
        _fail()
    if (
        se.errors
        or pe.errors
        or se.retry_count
        or pe.retry_count
        or se.repair_count
        or pe.repair_count
    ):
        _fail()


def _serialize(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _serialize_bytes(value: object) -> bytes:
    return _serialize(value).encode("utf-8", errors="strict")
