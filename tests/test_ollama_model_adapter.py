import http.client
import json
from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from math import inf
from pathlib import Path
from traceback import format_exception
from typing import Any, cast
from unittest.mock import patch

import pytest

import mfg_agentgraph.ollama_model_adapter as _adapter_module
from mfg_agentgraph.candidate_action import (
    CandidateAction,
    CandidateActionPlan,
    parse_candidate_actions,
)
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceValidationStatus,
)
from mfg_agentgraph.ollama_model_adapter import (
    _MAX_PROMPT_BYTES,
    _MAX_REQUEST_BYTES,
    _MAX_SIGNED_INT64,
    OLLAMA_PROMPT_ID,
    OLLAMA_SCHEMA_ID,
    OllamaCandidateAdapter,
    OllamaCandidateGenerationResult,
    OllamaFailureCategory,
    OllamaModelAdapterConfig,
    _ollama_schema,
    _validate_signed_int,
)
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import retrieve_structured_support

_VALID = {
    "base_url": "http://127.0.0.1:11434",
    "model_id": "llama3.2",
    "runtime_id": "runtime-1",
}


def make_config(**overrides: Any) -> OllamaModelAdapterConfig:
    values = {**_VALID, **overrides}
    return OllamaModelAdapterConfig(**values)


def test_constants_and_defaults_are_stable() -> None:
    config = make_config()

    assert OLLAMA_PROMPT_ID == "ollama-prompt:candidate-action-v1"
    assert OLLAMA_SCHEMA_ID == "candidate-action-schema:v1"
    assert config.timeout_seconds == 30.0
    assert config.seed == 0
    assert config.num_predict == 512


def test_config_is_frozen_slotted_and_adapter_stores_valid_config() -> None:
    config = make_config()
    adapter = OllamaCandidateAdapter(config)

    assert adapter.config is config
    with pytest.raises(FrozenInstanceError):
        config.model_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        adapter.config = config  # type: ignore[misc]
    assert not hasattr(config, "__dict__")
    assert not hasattr(adapter, "__dict__")


@pytest.mark.parametrize(
    ("base_url", "endpoint"),
    [
        ("http://127.0.0.1:1", ("127.0.0.1", 1)),
        ("http://127.0.0.1:65535", ("127.0.0.1", 65535)),
        ("http://[::1]:1", ("::1", 1)),
        ("http://[::1]:65535", ("::1", 65535)),
    ],
)
def test_canonical_loopback_endpoints_are_accepted_without_resolution(
    base_url: str, endpoint: tuple[str, int]
) -> None:
    with patch("socket.getaddrinfo", side_effect=AssertionError("DNS called")):
        config = make_config(base_url=base_url)

    assert config.base_url == base_url
    assert config._transport_endpoint == endpoint


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434",
        "http://example.test:11434",
        "https://127.0.0.1:11434",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:+1",
        "http://127.0.0.1:01",
        "http://127.0.0.01:11434",
        "http://2130706433:11434",
        "http://0177.0.0.1:11434",
        "http://0x7f.0.0.1:11434",
        "http://127.0.0.1:11434/ollama",
        "http://127.0.0.1:11434?x=1",
        "http://127.0.0.1:11434#x",
        "HTTP://127.0.0.1:1",
        "Http://[::1]:1",
        "http://127.0.0.1:1?",
        "http://127.0.0.1:1#",
        "http://127.0.0.1:1/",
        "http://[::1]:1/",
        "http://user:pass@127.0.0.1:11434",
        "http://[::ffff:127.0.0.1]:11434",
        "http://[::1%25eth0]:11434",
        "http://::1:11434",
        "http://[::1:11434",
        " http://127.0.0.1:11434",
        "http://127.0.0.1:11434 ",
        "http://127.0.0.1:11434\x00",
    ],
)
def test_noncanonical_or_unsafe_endpoints_are_rejected(base_url: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        make_config(base_url=base_url)


@pytest.mark.parametrize("base_url", ["http://[::1", "http://[::1:11434"])
def test_malformed_url_has_no_public_exception_chain(base_url: str) -> None:
    with pytest.raises(ValueError) as raised:
        make_config(base_url=base_url)

    exception = raised.value
    assert str(exception) == "base_url is not a valid URL"
    assert exception.__cause__ is None
    assert exception.__context__ is None
    traceback_text = "".join(format_exception(exception))
    assert "Invalid IPv6 URL" not in traceback_text
    assert traceback_text.splitlines()[-1] == "ValueError: base_url is not a valid URL"


@pytest.mark.parametrize("field", ["model_id", "runtime_id"])
@pytest.mark.parametrize(
    "value", ["", " ", "\tname", "name\n", "name\x00", "name\x7f", "name\ud800"]
)
def test_identifiers_reject_blank_whitespace_controls_and_surrogates(
    field: str, value: str
) -> None:
    with pytest.raises((TypeError, ValueError)):
        make_config(**{field: value})


def test_identifiers_enforce_utf8_byte_limit_and_allow_multibyte_boundary() -> None:
    assert make_config(model_id="é" * 512).model_id == "é" * 512
    with pytest.raises(ValueError):
        make_config(model_id="é" * 513)
    assert make_config(runtime_id="a" * 1024).runtime_id == "a" * 1024
    with pytest.raises(ValueError):
        make_config(runtime_id="a" * 1025)


def test_surrogate_rejection_has_no_public_exception_chain() -> None:
    with pytest.raises(ValueError) as raised:
        make_config(model_id="name\ud800")

    exception = raised.value
    assert str(exception) == "model_id contains a surrogate"
    assert exception.__cause__ is None
    assert exception.__context__ is None


@pytest.mark.parametrize("timeout", [0.1, 120.0])
def test_timeout_accepts_exact_boundaries(timeout: float) -> None:
    assert make_config(timeout_seconds=timeout).timeout_seconds == timeout


@pytest.mark.parametrize("timeout", [0.099999, 120.000001, inf, -inf, float("nan")])
def test_timeout_rejects_out_of_range_and_nonfinite_values(timeout: float) -> None:
    with pytest.raises((TypeError, ValueError)):
        make_config(timeout_seconds=timeout)


@pytest.mark.parametrize("seed", [0, 2_147_483_647])
def test_seed_accepts_exact_boundaries(seed: int) -> None:
    assert make_config(seed=seed).seed == seed


@pytest.mark.parametrize("seed", [-1, 2_147_483_648, True])
def test_seed_rejects_out_of_range_and_bool(seed: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        make_config(seed=seed)


@pytest.mark.parametrize("num_predict", [1, 4096])
def test_num_predict_accepts_exact_boundaries(num_predict: int) -> None:
    assert make_config(num_predict=num_predict).num_predict == num_predict


@pytest.mark.parametrize("num_predict", [0, 4097, False])
def test_num_predict_rejects_out_of_range_and_bool(num_predict: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        make_config(num_predict=num_predict)


class HostileStr(str):
    def __str__(self) -> str:
        raise AssertionError("virtual str method called")

    def encode(self, *args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("virtual str method called")


class HostileInt(int):
    def __lt__(self, other: object) -> bool:
        raise AssertionError("virtual int method called")

    def __le__(self, other: object) -> bool:
        raise AssertionError("virtual int method called")


class HostileFloat(float):
    def __le__(self, other: object) -> bool:
        raise AssertionError("virtual float method called")


def test_exact_builtin_types_are_rejected_before_virtual_methods() -> None:
    hostile = HostileStr("llama")
    with pytest.raises(TypeError):
        make_config(model_id=hostile)
    with pytest.raises(TypeError):
        make_config(base_url=hostile)
    with pytest.raises(TypeError):
        make_config(seed=HostileInt(1))
    with pytest.raises(TypeError):
        make_config(num_predict=HostileInt(1))
    with pytest.raises(TypeError):
        make_config(timeout_seconds=HostileFloat(1.0))


def test_required_fields_and_types_are_validated() -> None:
    with pytest.raises(TypeError):
        OllamaModelAdapterConfig()  # type: ignore[call-arg]
    for field in ("base_url", "model_id", "runtime_id"):
        with pytest.raises(TypeError):
            make_config(**{field: 123})


def test_construction_does_not_make_network_calls() -> None:
    with patch("socket.getaddrinfo", side_effect=AssertionError("DNS called")):
        make_config()


def _prepared_fixture() -> tuple[Any, Any, str]:
    scenario = json.loads(
        (Path(__file__).parent / "fixtures" / "pump_12" / "scenario.json").read_text(
            encoding="utf-8"
        )
    )
    asset = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
    query_id = "query-pump-12-candidate-generation"
    return (
        retrieve_structured_support(
            resolved_asset=asset,
            scenario=scenario,
            retrieval_run_id="structured-run",
            query_id=query_id,
        ),
        retrieve_procedural_support(
            resolved_asset=asset,
            scenario=scenario,
            retrieval_run_id="procedural-run",
            query_id=query_id,
        ),
        query_id,
    )


def test_prepare_request_uses_chat_target_and_wire_request_line() -> None:
    structured, procedural, query_id = _prepared_fixture()
    prepared = OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, "generation-run-exact", query_id
    )
    assert prepared.endpoint == "http://127.0.0.1:11434/api/chat"
    assert prepared.request_line == b"POST /api/chat HTTP/1.1\r\n"


def test_prepared_state_has_only_serialized_body_and_retains_exact_evidence() -> None:
    structured, procedural, query_id = _prepared_fixture()
    prepared = OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, "generation-run-exact", query_id
    )
    assert not hasattr(prepared, "body")
    decoded = json.loads(bytes(prepared.serialized_body))
    assert set(decoded) == {
        "model",
        "messages",
        "format",
        "stream",
        "think",
        "keep_alive",
        "options",
    }
    assert prepared.generation_run_id == "generation-run-exact"
    assert prepared.query_id == query_id
    expected = (structured.evidence_references[0], procedural.evidence_references[0])
    assert prepared.evidence_references == expected
    assert prepared.evidence_references[0] is expected[0]
    assert prepared.evidence_catalog.references == expected
    assert all(
        token not in prepared.serialized_body.decode() for token in ("source", "sop.txt", "3e538")
    )
    assert all(token not in repr(prepared) for token in ("tests/fixtures", "sop.txt", "3e538"))


def test_canonical_messages_schema_options_and_headers() -> None:
    structured, procedural, query_id = _prepared_fixture()
    prepared = OllamaCandidateAdapter(make_config(seed=7, num_predict=99))._prepare_request(
        structured, procedural, "generation-run", query_id
    )
    body = json.loads(prepared.serialized_body)
    expected_system = (
        "Return only candidate-action JSON matching the supplied schema. Use only the supplied "
        "asset and evidence identifiers; do not invent identifiers."
    )
    assert body["messages"][0] == {
        "role": "system",
        "content": expected_system,
    }
    user = json.loads(body["messages"][1]["content"])
    assert user["evidence"] == [
        {"id": "ex:EvidenceEdge_001", "type": "kg_edge"},
        {"id": "ex:SOP_Chunk_7", "type": "document_chunk"},
    ]
    assert body["options"] == {"temperature": 0, "seed": 7, "num_predict": 99}
    assert body["stream"] is False and body["think"] is False and body["keep_alive"] == "5m"
    assert tuple(name for name, _ in prepared.headers) == (
        "Host",
        "Content-Type",
        "Accept",
        "Content-Length",
        "Connection",
    )
    assert prepared.headers[3][1] == str(len(prepared.serialized_body))


def test_preparation_failures_are_constant_and_unlinked() -> None:
    structured, procedural, query_id = _prepared_fixture()
    with pytest.raises(ValueError) as raised:
        OllamaCandidateAdapter(make_config())._prepare_request(
            structured, procedural, "generation-run", query_id + "\\x00"
        )
    exc = raised.value
    assert str(exc) == "invalid Ollama request prerequisites"
    assert exc.__cause__ is None and exc.__context__ is None
    assert "query-pump" not in "".join(format_exception(exc))


def _assert_preparation_rejected(
    adapter: OllamaCandidateAdapter, structured: Any, procedural: Any, query_id: str
) -> None:
    with pytest.raises(ValueError) as raised:
        adapter._prepare_request(structured, procedural, "generation-run", query_id)
    assert str(raised.value) == "invalid Ollama request prerequisites"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


class _RaisingEquality:
    def __eq__(self, other: object) -> bool:
        raise AssertionError("virtual equality called")

    def __ne__(self, other: object) -> bool:
        raise AssertionError("virtual inequality called")


def test_asset_and_catalog_drift_reject_without_virtual_equality() -> None:
    structured, procedural, query_id = _prepared_fixture()
    object.__setattr__(structured.asset, "primary_label", _RaisingEquality())
    _assert_preparation_rejected(
        OllamaCandidateAdapter(make_config()), structured, procedural, query_id
    )

    structured, procedural, query_id = _prepared_fixture()
    object.__setattr__(structured.evidence_catalog, "references", _RaisingEquality())
    _assert_preparation_rejected(
        OllamaCandidateAdapter(make_config()), structured, procedural, query_id
    )

    structured, procedural, query_id = _prepared_fixture()
    object.__setattr__(structured.asset, "aliases", _RaisingEquality())
    _assert_preparation_rejected(
        OllamaCandidateAdapter(make_config()), structured, procedural, query_id
    )


def test_signed_int64_constant_and_exact_boundaries() -> None:
    assert _MAX_SIGNED_INT64 == 9_223_372_036_854_775_807
    for lower in (0, 1):
        assert _validate_signed_int(_MAX_SIGNED_INT64, lower=lower) == _MAX_SIGNED_INT64
        with pytest.raises(ValueError):
            _validate_signed_int(_MAX_SIGNED_INT64 + 1, lower=lower)
    structured, procedural, query_id = _prepared_fixture()
    object.__setattr__(structured.event, "duration_ms", _MAX_SIGNED_INT64)
    OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, "generation-run", query_id
    )
    object.__setattr__(structured.event, "duration_ms", _MAX_SIGNED_INT64 + 1)
    _assert_preparation_rejected(
        OllamaCandidateAdapter(make_config()), structured, procedural, query_id
    )


def test_wire_schema_omits_string_maxima_but_local_limits_remain_fail_closed() -> None:
    def assert_no_string_max_length(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "string":
                assert "maxLength" not in node
            for child in node.values():
                assert_no_string_max_length(child)
        elif isinstance(node, list):
            for child in node:
                assert_no_string_max_length(child)

    assert_no_string_max_length(_ollama_schema())

    target_over_limit = json.loads(_candidate_content())
    target_over_limit["ranked_actions"][0]["target_asset"] = "x" * 1025
    evidence_over_limit = json.loads(_candidate_content())
    evidence_over_limit["ranked_actions"][0]["support_evidence"][0]["id"] = "x" * 8193
    for content in (
        _candidate_content(action="x" * 2049),
        json.dumps(target_over_limit),
        json.dumps(evidence_over_limit),
    ):
        with pytest.raises(ValueError):
            _adapter_module._validate_candidate_shape(content)


def test_schema_is_exact_approved_literal() -> None:
    assert _ollama_schema() == {
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
            }
        },
        "required": ["ranked_actions"],
        "additionalProperties": False,
    }


def test_canonical_user_json_and_full_headers_for_ipv4_and_ipv6() -> None:
    structured, procedural, query_id = _prepared_fixture()
    for base_url, host in (
        ("http://127.0.0.1:11434", "127.0.0.1:11434"),
        ("http://[::1]:11434", "[::1]:11434"),
    ):
        prepared = OllamaCandidateAdapter(make_config(base_url=base_url))._prepare_request(
            structured, procedural, "generation-run", query_id
        )
        body = json.loads(prepared.serialized_body)
        user = body["messages"][1]["content"]
        assert (
            user == '{"asset":{"id":"ex:Pump_12","type":"centrifugal_pump"},'
            '"evidence":[{"id":"ex:EvidenceEdge_001","type":"kg_edge"},'
            '{"id":"ex:SOP_Chunk_7","type":"document_chunk"}],'
            '"observation":{"id":"ex:Observation_Pump12_2026-05-18T14:03:00Z",'
            '"signal":"anomalous_sound"},'
            '"procedure":{"id":"ex:Procedure_InspectInletCavitation_Pump12"}}'
        )
        assert prepared.request_line == b"POST /api/chat HTTP/1.1\r\n"
        assert prepared.headers == (
            ("Host", host),
            ("Content-Type", "application/json"),
            ("Accept", "application/json"),
            ("Content-Length", str(len(prepared.serialized_body))),
            ("Connection", "close"),
        )
        assert (
            json.loads(prepared.serialized_body.decode("utf-8"))["messages"][1]["content"] == user
        )


def test_prompt_and_request_limits_use_exact_equality(monkeypatch: pytest.MonkeyPatch) -> None:
    structured, procedural, query_id = _prepared_fixture()
    adapter = OllamaCandidateAdapter(make_config())
    import mfg_agentgraph.ollama_model_adapter as module

    prepared = adapter._prepare_request(structured, procedural, "generation-run", query_id)
    body = json.loads(prepared.serialized_body)
    prompt_size = len(module._SYSTEM_TEXT.encode()) + len(body["messages"][1]["content"].encode())
    monkeypatch.setattr(module, "_MAX_PROMPT_BYTES", prompt_size)
    adapter._prepare_request(structured, procedural, "generation-run", query_id)
    monkeypatch.setattr(module, "_MAX_PROMPT_BYTES", prompt_size - 1)
    _assert_preparation_rejected(adapter, structured, procedural, query_id)
    monkeypatch.setattr(module, "_MAX_PROMPT_BYTES", _MAX_PROMPT_BYTES)
    wire_size = (
        len(prepared.request_line)
        + sum(
            len(n.encode("ascii")) + 2 + len(v.encode("latin-1")) + 2 for n, v in prepared.headers
        )
        + 2
        + len(prepared.serialized_body)
    )
    monkeypatch.setattr(module, "_MAX_REQUEST_BYTES", wire_size)
    adapter._prepare_request(structured, procedural, "generation-run", query_id)
    monkeypatch.setattr(module, "_MAX_REQUEST_BYTES", wire_size - 1)
    _assert_preparation_rejected(adapter, structured, procedural, query_id)
    assert _MAX_PROMPT_BYTES == 32768
    assert _MAX_REQUEST_BYTES == 65536


def test_raw_tuple_subclasses_are_rejected_before_virtual_methods() -> None:
    structured, procedural, query_id = _prepared_fixture()

    class HostileTuple(tuple[Any, ...]):
        def __len__(self) -> int:
            raise AssertionError("virtual len called")

        def __iter__(self) -> Iterator[Any]:
            raise AssertionError("virtual iter called")

    for owner, field in (
        (structured, "observations"),
        (structured, "evidence_references"),
        (procedural, "evidence_references"),
    ):
        if field == "event":
            continue
        original = getattr(owner, field)
        object.__setattr__(owner, field, HostileTuple(original))
        _assert_preparation_rejected(
            OllamaCandidateAdapter(make_config()), structured, procedural, query_id
        )
        object.__setattr__(owner, field, original)


def test_preparation_never_opens_a_transport() -> None:
    structured, procedural, query_id = _prepared_fixture()
    with (
        patch("socket.getaddrinfo", side_effect=AssertionError("DNS called")),
        patch("socket.create_connection", side_effect=AssertionError("socket opened")),
    ):
        OllamaCandidateAdapter(make_config())._prepare_request(
            structured, procedural, "generation-run", query_id
        )


def test_prepared_state_is_frozen_and_retains_exact_reference_objects() -> None:
    structured, procedural, query_id = _prepared_fixture()
    prepared = OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, "generation-run", query_id
    )
    assert type(prepared.serialized_body) is bytes
    assert type(prepared.request_line) is bytes
    assert type(prepared.headers) is tuple
    assert prepared.evidence_references[0] is structured.evidence_references[0]
    assert prepared.evidence_references[1] is procedural.evidence_references[0]
    assert prepared.evidence_catalog.references is prepared.evidence_references
    with pytest.raises(FrozenInstanceError):
        prepared.asset_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        structured.evidence_references[0].stable_id = "changed"  # type: ignore[misc]


# Milestone 4A: terminal candidate-generation result contract.
def _result_fixture() -> tuple[Any, Any, str, tuple[Any, Any], Any, str, Any]:
    structured, procedural, query_id = _prepared_fixture()
    refs = (structured.evidence_references[0], procedural.evidence_references[0])
    catalog = EvidenceCatalog(refs)
    refs = cast(tuple[Any, ...], catalog.references)
    raw = json.dumps(
        {
            "ranked_actions": [
                {
                    "rank": 1,
                    "action": "Inspect inlet for cavitation",
                    "target_asset": "ex:Pump_12",
                    "support_evidence": [
                        {"type": "kg_edge", "id": refs[0].stable_id},
                        {"type": "document_chunk", "id": refs[1].stable_id},
                    ],
                }
            ]
        },
        separators=(",", ":"),
    )
    plan = parse_candidate_actions(raw, known_assets=("ex:Pump_12",), evidence_catalog=catalog)
    return structured, procedural, query_id, refs, catalog, raw, plan


def _passed_result(metadata: tuple[tuple[str, int], ...] = ()) -> OllamaCandidateGenerationResult:
    _structured, _procedural, query_id, refs, catalog, raw, plan = _result_fixture()
    return OllamaCandidateGenerationResult(
        status=TerminalStatus.PASSED,
        plan=plan,
        raw_json=raw,
        evidence_catalog=catalog,
        evidence_references=refs,
        model_id="llama3.2",
        runtime_id="runtime-1",
        prompt_id=OLLAMA_PROMPT_ID,
        schema_id=OLLAMA_SCHEMA_ID,
        metadata=metadata,
        event=StageEvent(
            StageName.CANDIDATE_GENERATION,
            "generation-run",
            TerminalStatus.PASSED,
            input_ids=("ex:Pump_12", query_id, refs[0].stable_id, refs[1].stable_id),
            output_ids=("candidate-action-rank:1",),
        ),
    )


def _failed_result(category: OllamaFailureCategory) -> OllamaCandidateGenerationResult:
    return OllamaCandidateGenerationResult(
        TerminalStatus.VALIDATION_FAILED_CLOSED,
        None,
        None,
        None,
        (),
        "llama3.2",
        "runtime-1",
        OLLAMA_PROMPT_ID,
        OLLAMA_SCHEMA_ID,
        (),
        StageEvent(
            StageName.CANDIDATE_GENERATION,
            "generation-run",
            TerminalStatus.VALIDATION_FAILED_CLOSED,
            input_ids=("query-pump-12-candidate-generation",),
            errors=(StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, category.value),),
        ),
    )


def test_failure_categories_are_exactly_ordered() -> None:
    assert tuple(category.value for category in OllamaFailureCategory) == (
        "prerequisite",
        "request",
        "transport",
        "http_status",
        "response_headers",
        "response_size",
        "response_encoding",
        "response_json",
        "response_envelope",
        "candidate_schema",
        "candidate_validation",
        "internal",
    )


def test_canonical_passed_result_is_immutable_and_exactly_correlated() -> None:
    result = _passed_result()
    assert not hasattr(result, "__dict__")
    _structured, _procedural, query_id, refs, catalog, raw, plan = _result_fixture()
    assert result.plan is not None and result.evidence_catalog is not None
    assert result.plan.ranked_actions == plan.ranked_actions
    assert result.raw_json == raw
    assert result.evidence_catalog.references is result.evidence_references
    assert all(
        result.evidence_references[i] is result.evidence_catalog.references[i] for i in range(2)
    )
    assert result.event.input_ids == ("ex:Pump_12", query_id, refs[0].stable_id, refs[1].stable_id)
    assert result.event.output_ids == ("candidate-action-rank:1",)
    assert (
        result.event.duration_ms is None
        and result.event.retry_count == result.event.repair_count == 0
    )
    assert result.event.errors == ()
    with pytest.raises(FrozenInstanceError):
        result.status = TerminalStatus.INSUFFICIENT_EVIDENCE  # type: ignore[misc]
    assert replace(result, metadata=(("eval_count", 1),)).metadata == (("eval_count", 1),)


@pytest.mark.parametrize("category", tuple(OllamaFailureCategory))
def test_every_failure_category_is_closed_with_one_exact_error(
    category: OllamaFailureCategory,
) -> None:
    result = _failed_result(category)
    assert result.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.plan is None
    assert result.raw_json is None
    assert result.evidence_catalog is None
    assert result.evidence_references == ()
    assert result.metadata == ()
    assert result.event.input_ids == ("query-pump-12-candidate-generation",)
    assert result.event.output_ids == ()
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, category.value),
    )


@pytest.mark.parametrize("duplicate_indices", [(0, 0, 1), (1, 1, 0)])
def test_duplicate_support_references_within_one_action_are_rejected(
    duplicate_indices: tuple[int, int, int],
) -> None:
    result = _passed_result()
    assert result.plan is not None
    refs = result.evidence_references
    action = result.plan.ranked_actions[0]
    duplicate_action = CandidateAction(
        rank=action.rank,
        action=action.action,
        target_asset=action.target_asset,
        support_evidence=tuple(refs[index] for index in duplicate_indices),
    )
    duplicate_plan = CandidateActionPlan((duplicate_action,))

    with pytest.raises(ValueError, match="invalid Ollama generation result"):
        replace(result, plan=duplicate_plan)


def test_multiple_ranked_actions_reuse_references_and_exact_union() -> None:
    _s, _p, query_id, refs, catalog, _raw, _plan = _result_fixture()
    raw = json.dumps(
        {
            "ranked_actions": [
                {
                    "rank": 1,
                    "action": "Inspect",
                    "target_asset": "ex:Pump_12",
                    "support_evidence": [{"type": "kg_edge", "id": refs[0].stable_id}],
                },
                {
                    "rank": 2,
                    "action": "Verify",
                    "target_asset": "ex:Pump_12",
                    "support_evidence": [
                        {"type": "kg_edge", "id": refs[0].stable_id},
                        {"type": "document_chunk", "id": refs[1].stable_id},
                    ],
                },
            ]
        },
        separators=(",", ":"),
    )
    plan = parse_candidate_actions(raw, known_assets=("ex:Pump_12",), evidence_catalog=catalog)
    result = OllamaCandidateGenerationResult(
        TerminalStatus.PASSED,
        plan,
        raw,
        catalog,
        refs,
        "llama3.2",
        "runtime-1",
        OLLAMA_PROMPT_ID,
        OLLAMA_SCHEMA_ID,
        (),
        StageEvent(
            StageName.CANDIDATE_GENERATION,
            "generation-run",
            TerminalStatus.PASSED,
            input_ids=("ex:Pump_12", query_id, refs[0].stable_id, refs[1].stable_id),
            output_ids=("candidate-action-rank:1", "candidate-action-rank:2"),
        ),
    )
    assert result.plan is not None
    assert result.plan.ranked_actions[1].support_evidence[0] is refs[0]


@pytest.mark.parametrize(
    "metadata",
    [
        (),
        (("total_duration", 1),),
        (
            ("total_duration", 1),
            ("load_duration", 1),
            ("prompt_eval_count", 1),
            ("prompt_eval_duration", 1),
            ("eval_count", 1),
            ("eval_duration", 1),
        ),
    ],
)
def test_allowed_metadata_subsets_are_in_allow_list_order(
    metadata: tuple[tuple[str, int], ...],
) -> None:
    assert _passed_result(metadata).metadata == metadata


@pytest.mark.parametrize(
    "metadata",
    [
        (("eval_count", 1), ("total_duration", 1)),
        (("eval_count", 1), ("eval_count", 2)),
        (("unknown", 1),),
        (("eval_count", None),),
        (("eval_count", True),),
        (("eval_count", -1),),
        (("eval_count", _MAX_SIGNED_INT64 + 1),),
        [("eval_count", 1)],
        (("eval_count", 10**60),),
    ],
)
def test_metadata_drift_is_rejected(metadata: Any) -> None:
    with pytest.raises(ValueError, match="invalid Ollama generation result"):
        _passed_result(metadata)


def test_result_raw_json_has_exact_262144_byte_limit() -> None:
    result = _passed_result()
    exact = replace(result, raw_json="a" * 262144)
    assert exact.raw_json is not None
    assert len(exact.raw_json.encode()) == 262144
    for raw in ("a" * 262145, "é" * 131073, "a\x00", "a\ud800"):
        with pytest.raises(ValueError, match="invalid Ollama generation result"):
            replace(result, raw_json=raw)


@pytest.mark.parametrize(
    ("action_text", "expected_bytes"), [("a" * 2048, 2048), ("é" * 2048, 4096)]
)
def test_result_action_accepts_exact_character_and_utf8_boundaries(
    action_text: str, expected_bytes: int
) -> None:
    result = _passed_result()
    assert len(action_text) == 2048
    assert len(action_text.encode("utf-8")) == expected_bytes
    assert result.plan is not None
    action = result.plan.ranked_actions[0]
    bounded_plan = CandidateActionPlan(
        (CandidateAction(action.rank, action_text, action.target_asset, action.support_evidence),)
    )

    bounded = replace(result, plan=bounded_plan)

    assert bounded.plan is bounded_plan


@pytest.mark.parametrize(
    ("action_text", "expected_chars", "expected_bytes"),
    [("a" * 2049, 2049, 2049), ("é" * 2047 + "€", 2048, 4097)],
)
def test_result_action_rejects_character_or_utf8_limit_plus_one(
    action_text: str, expected_chars: int, expected_bytes: int
) -> None:
    result = _passed_result()
    assert len(action_text) == expected_chars
    assert len(action_text.encode("utf-8")) == expected_bytes
    assert result.plan is not None
    action = result.plan.ranked_actions[0]
    oversized_plan = CandidateActionPlan(
        (CandidateAction(action.rank, action_text, action.target_asset, action.support_evidence),)
    )

    with pytest.raises(ValueError) as raised:
        replace(result, plan=oversized_plan)

    assert str(raised.value) == "invalid Ollama generation result"
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_result_errors_are_constant_and_unlinked() -> None:
    with pytest.raises(ValueError) as raised:
        replace(_passed_result(), plan=None)
    error = raised.value
    assert str(error) == "invalid Ollama generation result"
    assert error.__cause__ is None and error.__context__ is None
    assert "rejected" not in repr(error)
    assert "query-pump" not in "".join(format_exception(error))


class _HostileSequence(tuple[Any, ...]):
    def __len__(self) -> int:
        raise AssertionError("virtual len called")

    def __iter__(self) -> Iterator[Any]:
        raise AssertionError("virtual iter called")

    def __eq__(self, other: object) -> bool:
        raise AssertionError("virtual equality called")


class _HostileList(list[Any]):
    def __len__(self) -> int:
        raise AssertionError("virtual len called")

    def __iter__(self) -> Iterator[Any]:
        raise AssertionError("virtual iter called")

    def __eq__(self, other: object) -> bool:
        raise AssertionError("virtual equality called")


def _set_path(owner: Any, field: str, value: Any) -> None:
    object.__setattr__(owner, field, value)


@pytest.mark.parametrize(
    ("owner_name", "field"),
    [
        ("structured", "observations"),
        ("structured", "support_records"),
        ("structured", "evidence_references"),
        ("structured_catalog", "references"),
        ("procedural", "support_records"),
        ("procedural", "evidence_references"),
        ("procedural_catalog", "references"),
        ("structured_event", "input_ids"),
        ("structured_event", "output_ids"),
        ("structured_event", "errors"),
        ("procedural_event", "input_ids"),
        ("procedural_event", "output_ids"),
        ("procedural_event", "errors"),
        ("structured_asset", "aliases"),
        ("procedural_asset", "aliases"),
    ],
)
@pytest.mark.parametrize(
    "hostile_type", [_HostileSequence, _HostileList], ids=["tuple-subclass", "list-subclass"]
)
def test_all_raw_collections_fail_closed_before_virtual_methods(
    owner_name: str, field: str, hostile_type: type[Any]
) -> None:
    structured, procedural, query_id = _prepared_fixture()
    owners = {
        "structured": structured,
        "structured_catalog": structured.evidence_catalog,
        "structured_event": structured.event,
        "structured_asset": structured.asset,
        "procedural": procedural,
        "procedural_catalog": procedural.evidence_catalog,
        "procedural_event": procedural.event,
        "procedural_asset": procedural.asset,
    }
    owner = owners[owner_name]
    object.__setattr__(owner, field, hostile_type(getattr(owner, field)))
    _assert_preparation_rejected(
        OllamaCandidateAdapter(make_config()), structured, procedural, query_id
    )


def _drift_cases() -> list[tuple[str, Any]]:
    return [
        ("structured status", lambda s, p: _set_path(s, "status", "passed")),
        ("asset type", lambda s, p: _set_path(s, "asset", object())),
        ("observation scalar type", lambda s, p: _set_path(s.observations[0], "description", 1)),
        (
            "observation control",
            lambda s, p: _set_path(s.observations[0], "description", "bad\x00"),
        ),
        (
            "observation surrogate",
            lambda s, p: _set_path(s.observations[0], "description", "bad\ud800"),
        ),
        ("coherence mismatch", lambda s, p: _set_path(s.support_records[0], "subject", "other")),
        ("structured event stage", lambda s, p: _set_path(s.event, "stage", object())),
        (
            "structured event status",
            lambda s, p: _set_path(s.event, "status", TerminalStatus.INSUFFICIENT_EVIDENCE),
        ),
        ("structured event run", lambda s, p: _set_path(s.event, "run_id", "other-run")),
        (
            "structured event input",
            lambda s, p: _set_path(s.event, "input_ids", ("other", "other")),
        ),
        (
            "structured event output",
            lambda s, p: _set_path(s.event, "output_ids", ("other", "other", "other")),
        ),
        ("structured event counter", lambda s, p: _set_path(s.event, "retry_count", 1)),
        ("procedural event stage", lambda s, p: _set_path(p.event, "stage", object())),
        (
            "procedural event status",
            lambda s, p: _set_path(p.event, "status", TerminalStatus.INSUFFICIENT_EVIDENCE),
        ),
        ("procedural event run", lambda s, p: _set_path(p.event, "run_id", "other-run")),
        (
            "procedural event input",
            lambda s, p: _set_path(p.event, "input_ids", ("other", "other")),
        ),
        ("procedural event output", lambda s, p: _set_path(p.event, "output_ids", ("other",))),
        ("procedural event counter", lambda s, p: _set_path(p.event, "repair_count", 1)),
        (
            "evidence kind",
            lambda s, p: _set_path(s.evidence_references[0], "kind", EvidenceKind.KG_RESOURCE),
        ),
        (
            "evidence status",
            lambda s, p: _set_path(
                p.evidence_references[0], "validation_status", EvidenceValidationStatus.INVALID
            ),
        ),
        ("evidence source", lambda s, p: _set_path(s.evidence_references[0], "source", object())),
        (
            "evidence stable id",
            lambda s, p: _set_path(s.evidence_references[0], "stable_id", "other-id"),
        ),
        (
            "retrieval query",
            lambda s, p: _set_path(s.evidence_references[0].retrieval, "query_id", "other-query"),
        ),
        (
            "retrieval run",
            lambda s, p: _set_path(
                s.evidence_references[0].retrieval, "retrieval_run_id", "other-run"
            ),
        ),
        (
            "retrieval retriever",
            lambda s, p: _set_path(s.evidence_references[0].retrieval, "retriever_name", object()),
        ),
        (
            "retrieval rank",
            lambda s, p: _set_path(s.evidence_references[0].retrieval, "rank", object()),
        ),
        (
            "retrieval score type",
            lambda s, p: _set_path(s.evidence_references[0].retrieval, "score", "not-a-score"),
        ),
        (
            "retrieval object type",
            lambda s, p: _set_path(s.evidence_references[0], "retrieval", object()),
        ),
    ]


@pytest.mark.parametrize(
    ("name", "mutation"),
    _drift_cases(),
    ids=[case[0] for case in _drift_cases()],
)
def test_object_setattr_drift_matrix_is_constant_unlinked_error(name: str, mutation: Any) -> None:
    structured, procedural, query_id = _prepared_fixture()
    mutation(structured, procedural)
    _assert_preparation_rejected(
        OllamaCandidateAdapter(make_config()), structured, procedural, query_id
    )


def test_serialized_body_embeds_the_approved_schema() -> None:
    structured, procedural, query_id = _prepared_fixture()
    prepared = OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, "generation-run", query_id
    )
    body = json.loads(prepared.serialized_body)
    assert body["format"] == _ollama_schema()


def test_accepted_unprompted_markers_are_not_serialized_or_leaked_in_repr() -> None:
    structured, procedural, query_id = _prepared_fixture()
    generation_marker = "accepted-generation-marker"
    query_marker = "accepted-query-marker"
    asset_marker = "accepted-asset-marker"
    observation_marker = "accepted-observation-marker"
    procedural_marker = "accepted-procedural-marker"
    source_marker = "accepted-source-marker"
    retrieval_marker = "accepted-retrieval-marker"
    run_marker = "accepted-run-marker"
    duration_marker = 987654

    _set_path(structured.asset, "primary_label", asset_marker)
    _set_path(structured.asset, "aliases", ("Pump_12", asset_marker))
    _set_path(procedural.asset, "primary_label", asset_marker)
    _set_path(procedural.asset, "aliases", ("Pump_12", asset_marker))
    _set_path(structured.observations[0], "observed_at", observation_marker)
    _set_path(structured.observations[0], "anomaly", observation_marker)
    _set_path(structured.observations[0], "description", observation_marker)
    _set_path(procedural.support_records[0], "document", procedural_marker)
    _set_path(procedural.support_records[0], "text", procedural_marker)
    _set_path(procedural.support_records[0], "source_path", "accepted/source-marker.txt")
    _set_path(procedural.support_records[0], "source_sha256", "a" * 64)
    _set_path(procedural.support_records[0], "index_contract_version", procedural_marker)
    _set_path(procedural.support_records[0], "chunk_index", 8)
    _set_path(procedural.support_records[0], "start_line", 2)
    _set_path(procedural.support_records[0], "end_line", 3)
    for result in (structured, procedural):
        _set_path(result.evidence_references[0], "source", source_marker)
        _set_path(result.evidence_references[0].retrieval, "retriever_name", retrieval_marker)
        _set_path(result.evidence_references[0].retrieval, "score", 0.25)
        _set_path(result.evidence_references[0].retrieval, "retrieval_run_id", run_marker)
        _set_path(result.evidence_references[0].retrieval, "query_id", query_marker)
    _set_path(structured.event, "run_id", run_marker)
    _set_path(procedural.event, "run_id", run_marker)
    _set_path(structured.event, "input_ids", (structured.asset.asset_id, query_marker))
    _set_path(procedural.event, "input_ids", (procedural.asset.asset_id, query_marker))
    _set_path(structured.event, "duration_ms", duration_marker)
    _set_path(procedural.event, "duration_ms", duration_marker)

    prepared = OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, generation_marker, query_marker
    )
    body_text = prepared.serialized_body.decode()
    headers_text = repr(prepared.headers)
    repr_text = repr(prepared)
    assert generation_marker not in body_text and generation_marker not in headers_text
    assert query_marker not in body_text and query_marker not in headers_text
    for marker in (
        asset_marker,
        observation_marker,
        procedural_marker,
        source_marker,
        "accepted/source-marker.txt",
        retrieval_marker,
        run_marker,
        str(duration_marker),
    ):
        assert marker not in body_text
        assert marker not in headers_text
    for marker in (
        asset_marker,
        observation_marker,
        procedural_marker,
        source_marker,
        "accepted/source-marker.txt",
        retrieval_marker,
    ):
        assert marker not in repr_text
    assert prepared.generation_run_id == generation_marker
    assert prepared.query_id == query_marker


def test_preparation_only_builds_bytes_and_does_not_open_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured, procedural, query_id = _prepared_fixture()
    with (
        patch("socket.getaddrinfo", side_effect=AssertionError("DNS called")),
        patch("socket.create_connection", side_effect=AssertionError("socket opened")),
        patch("http.client.HTTPConnection", side_effect=AssertionError("HTTP opened")),
        patch("http.client.HTTPSConnection", side_effect=AssertionError("HTTPS opened")),
    ):
        prepared = OllamaCandidateAdapter(make_config())._prepare_request(
            structured, procedural, "generation-run", query_id
        )
    assert type(prepared.serialized_body) is bytes


# Milestone 4B: deterministic fake HTTP and response-envelope contract.


class FakeHTTPResponse:
    def __init__(
        self,
        status: object = 200,
        headers: object = None,
        body: object = b"",
        *,
        exceptions: dict[str, BaseException] | None = None,
    ) -> None:
        self.status = status
        self.headers = [("Content-Type", "application/json")] if headers is None else headers
        self.body = body
        self.exceptions = exceptions or {}
        self.calls: list[tuple[str, object]] = []

    def getheaders(self) -> object:
        self.calls.append(("getheaders", None))
        if "getheaders" in self.exceptions:
            raise self.exceptions["getheaders"]
        return self.headers

    def read(self, amount: object = None) -> object:
        self.calls.append(("read", amount))
        if "read" in self.exceptions:
            raise self.exceptions["read"]
        return self.body


class FakeHTTPConnection:
    instances: list["FakeHTTPConnection"] = []
    constructor_args: list[tuple[object, ...]] = []
    constructor_kwargs: list[dict[str, object]] = []
    response: FakeHTTPResponse | None = None
    exceptions: dict[str, BaseException] = {}

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).constructor_args.append(args)
        type(self).constructor_kwargs.append(kwargs)
        self.calls: list[tuple[str, object]] = []
        self.exceptions = type(self).exceptions
        type(self).instances.append(self)
        if "constructor" in self.exceptions:
            raise self.exceptions["constructor"]

    def _maybe_raise(self, name: str) -> None:
        if name in self.exceptions:
            raise self.exceptions[name]

    def putrequest(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("putrequest", (args, kwargs)))
        self._maybe_raise("putrequest")

    def putheader(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("putheader", (args, kwargs)))
        self._maybe_raise("putheader")

    def endheaders(self, body: object = None) -> None:
        self.calls.append(("endheaders", body))
        self._maybe_raise("endheaders")

    def getresponse(self) -> FakeHTTPResponse:
        self.calls.append(("getresponse", None))
        self._maybe_raise("getresponse")
        response = type(self).response
        assert response is not None
        return response

    def close(self) -> None:
        self.calls.append(("close", None))
        self._maybe_raise("close")


def _reset_fake_http() -> None:
    FakeHTTPConnection.instances = []
    FakeHTTPConnection.constructor_args = []
    FakeHTTPConnection.constructor_kwargs = []
    FakeHTTPConnection.response = None
    FakeHTTPConnection.exceptions = {}


def _canonical_envelope(model: str = "llama3.2", content: str = '{"ranked_actions": []}') -> bytes:
    return json.dumps(
        {
            "model": model,
            "created_at": "2026-05-18T14:03:00Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
            "total_duration": 1,
            "eval_count": 2,
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _prepared_for_exchange() -> Any:
    structured, procedural, query_id = _prepared_fixture()
    return OllamaCandidateAdapter(make_config())._prepare_request(
        structured, procedural, "generation-run", query_id
    )


def _exchange_with(response: FakeHTTPResponse, *, base_url: str = _VALID["base_url"]) -> Any:
    _reset_fake_http()
    FakeHTTPConnection.response = response
    structured, procedural, query_id = _prepared_fixture()
    adapter = OllamaCandidateAdapter(make_config(base_url=base_url))
    prepared = adapter._prepare_request(structured, procedural, "generation-run", query_id)
    with patch.object(http.client, "HTTPConnection", FakeHTTPConnection):
        return adapter._exchange(prepared)


def _failure_category(response: FakeHTTPResponse, *, config: Any = None) -> OllamaFailureCategory:
    _reset_fake_http()
    FakeHTTPConnection.response = response
    prepared = _prepared_for_exchange()
    adapter = OllamaCandidateAdapter(make_config() if config is None else config)
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        pytest.raises(_adapter_module._AdapterFailure) as raised,
    ):
        adapter._exchange(prepared)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    return raised.value.category


def test_exchange_happy_path_is_exactly_one_wire_attempt() -> None:
    response = FakeHTTPResponse(body=_canonical_envelope())
    envelope = _exchange_with(response)
    connection = FakeHTTPConnection.instances[0]
    prepared = _prepared_for_exchange()
    assert FakeHTTPConnection.constructor_args == [("127.0.0.1", 11434)]
    assert FakeHTTPConnection.constructor_kwargs == [{"timeout": 30.0}]
    assert connection.calls[:2] == [
        ("putrequest", (("POST", "/api/chat"), {"skip_host": True, "skip_accept_encoding": True})),
        ("putheader", (("Host", "127.0.0.1:11434"), {})),
    ]
    assert [cast(tuple[Any, Any], call[1])[0] for call in connection.calls[1:6]] == [
        ("Host", "127.0.0.1:11434"),
        ("Content-Type", "application/json"),
        ("Accept", "application/json"),
        ("Content-Length", str(len(prepared.serialized_body))),
        ("Connection", "close"),
    ]
    assert connection.calls[6] == ("endheaders", prepared.serialized_body)
    assert connection.calls[7:10] == [("getresponse", None), ("close", None)]
    assert response.calls == [("getheaders", None), ("read", 1_000_001)]
    assert envelope.content == '{"ranked_actions": []}'
    assert envelope.metadata == (("total_duration", 1), ("eval_count", 2))


def test_exchange_ipv6_uses_prepared_host_and_endpoint() -> None:
    response = FakeHTTPResponse(body=_canonical_envelope())
    _exchange_with(response, base_url="http://[::1]:11434")
    assert FakeHTTPConnection.constructor_args == [("::1", 11434)]
    assert cast(tuple[Any, Any], FakeHTTPConnection.instances[0].calls[1][1])[0] == (
        "Host",
        "[::1]:11434",
    )


@pytest.mark.parametrize(
    "phase", ["constructor", "putrequest", "putheader", "endheaders", "getresponse", "read"]
)
def test_transport_failures_are_one_attempt_and_sanitized(phase: str) -> None:
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope())
    FakeHTTPConnection.exceptions = {phase: TimeoutError("marker-body")}
    if phase == "read":
        assert FakeHTTPConnection.response is not None
        FakeHTTPConnection.response.exceptions = {"read": TimeoutError("marker-body")}
    prepared = _prepared_for_exchange()
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        pytest.raises(_adapter_module._AdapterFailure) as raised,
    ):
        OllamaCandidateAdapter(make_config())._exchange(prepared)
    assert raised.value.category is OllamaFailureCategory.TRANSPORT
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert len(FakeHTTPConnection.constructor_args) == 1
    if phase != "constructor":
        assert [call[0] for call in FakeHTTPConnection.instances[0].calls].count("close") == 1
    assert "marker-body" not in repr(raised.value)


@pytest.mark.parametrize(
    "phase",
    ["constructor", "putrequest", "putheader", "endheaders", "getresponse", "read", "close"],
)
def test_ordinary_exceptions_are_internal_except_close_transport_types(phase: str) -> None:
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope())
    FakeHTTPConnection.exceptions = {phase: RuntimeError("internal-marker")}
    if phase == "read":
        assert FakeHTTPConnection.response is not None
        FakeHTTPConnection.response.exceptions = {"read": RuntimeError("internal-marker")}
    prepared = _prepared_for_exchange()
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        pytest.raises(_adapter_module._AdapterFailure) as raised,
    ):
        OllamaCandidateAdapter(make_config())._exchange(prepared)
    assert raised.value.category is OllamaFailureCategory.INTERNAL
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert "internal-marker" not in repr(raised.value)


@pytest.mark.parametrize("status", [199, 201, True, 200.0, "200", object()])
def test_non_200_or_non_exact_status_does_not_read_response(status: object) -> None:
    response = FakeHTTPResponse(status=status, body=_canonical_envelope())
    assert _failure_category(response) is OllamaFailureCategory.HTTP_STATUS
    assert response.calls == []


def test_exchange_header_helper_has_truthful_declared_length_return() -> None:
    assert _adapter_module._response_headers(FakeHTTPResponse()) is None


def test_response_body_size_and_nonbytes_are_stable_and_single_read() -> None:
    too_large = FakeHTTPResponse(body=b"x" * 1_000_001)
    assert _failure_category(too_large) is OllamaFailureCategory.RESPONSE_SIZE
    assert too_large.calls.count(("read", 1_000_001)) == 1
    nonbytes = FakeHTTPResponse(body="not-bytes")
    assert _failure_category(nonbytes) is OllamaFailureCategory.TRANSPORT
    assert nonbytes.calls.count(("read", 1_000_001)) == 1


@pytest.mark.parametrize(
    "raw", [b"\\xff", b"\\xef\\xbb\\xbf{}", b"{", b"[] trailing", b'{"x":1,"x":2}', b'{"x":NaN}']
)
def test_malformed_or_unsafe_json_is_response_json(raw: bytes) -> None:
    assert _failure_category(FakeHTTPResponse(body=raw)) in {
        OllamaFailureCategory.RESPONSE_ENCODING,
        OllamaFailureCategory.RESPONSE_JSON,
    }


def test_envelope_requires_exact_types_keys_and_model() -> None:
    base = json.loads(_canonical_envelope().decode())
    cases = []
    for key in ("model", "created_at", "message", "done", "done_reason"):
        altered = dict(base)
        altered[key] = 1
        cases.append(altered)
    altered = dict(base)
    altered["extra"] = 1
    cases.append(altered)
    altered = dict(base)
    altered["model"] = "other"
    cases.append(altered)
    for value in cases:
        raw = json.dumps(value, separators=(",", ":")).encode()
        assert (
            _failure_category(FakeHTTPResponse(body=raw)) is OllamaFailureCategory.RESPONSE_ENVELOPE
        )


def test_content_scanner_accepts_string_content_without_decoding_candidate() -> None:
    content = '{"text":"😀"}'
    envelope = _exchange_with(FakeHTTPResponse(body=_canonical_envelope(content=content)))
    assert type(envelope.content) is str and envelope.content == content


def test_generate_accepts_pretty_printed_candidate_json() -> None:
    structured, procedural, query_id = _prepared_fixture()
    pretty_content = json.dumps(json.loads(_candidate_content()), indent=2)
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope(content=pretty_content))
    with patch.object(http.client, "HTTPConnection", FakeHTTPConnection):
        result = OllamaCandidateAdapter(make_config()).generate(
            structured, procedural, "generation-run", query_id
        )

    assert result.status is TerminalStatus.PASSED
    assert result.plan is not None
    assert result.raw_json == pretty_content


@pytest.mark.parametrize("control", ["\x00", "\x01", "\x0b", "\x1f"])
def test_candidate_controls_outside_strings_are_response_json(control: str) -> None:
    content = '{"ranked_actions": []}' + control
    assert (
        _failure_category(FakeHTTPResponse(body=_canonical_envelope(content=content)))
        is OllamaFailureCategory.RESPONSE_JSON
    )


def test_candidate_direct_surrogate_is_response_json_without_encoding_error() -> None:
    with pytest.raises(ValueError):
        _adapter_module._scan_json('{"text":"bad\ud800"}', max_depth=5, max_tokens=32)

    content = '{"text":"bad\\ud800"}'
    assert (
        _failure_category(FakeHTTPResponse(body=_canonical_envelope(content=content)))
        is OllamaFailureCategory.RESPONSE_JSON
    )


@pytest.mark.parametrize("content", ["{", '{"x": 1'])
def test_candidate_content_scanner_rejects_invalid_content_without_candidate_decode(
    content: str,
) -> None:
    assert (
        _failure_category(FakeHTTPResponse(body=_canonical_envelope(content=content)))
        is OllamaFailureCategory.RESPONSE_JSON
    )


def test_response_headers_require_literal_approved_content_type_values() -> None:
    for content_type in (
        "Application/JSON",
        "application/json; CHARSET=UTF-8",
        "application/json; charset=UTF-8",
    ):
        assert (
            _failure_category(
                FakeHTTPResponse(
                    headers=[("Content-Type", content_type)],
                    body=_canonical_envelope(),
                )
            )
            is OllamaFailureCategory.RESPONSE_HEADERS
        )


def test_adapter_failure_is_redacted_and_stable() -> None:
    failure = _adapter_module._AdapterFailure(OllamaFailureCategory.INTERNAL)
    assert str(failure) == "internal"
    assert repr(failure) == "_AdapterFailure(<redacted>)"
    assert failure.category is OllamaFailureCategory.INTERNAL


def test_exchange_rejects_unprepared_state_and_failure_category_is_exact() -> None:
    with pytest.raises(_adapter_module._AdapterFailure) as raised:
        OllamaCandidateAdapter(make_config())._exchange(cast(Any, object()))
    assert raised.value.category is OllamaFailureCategory.REQUEST
    with pytest.raises(TypeError):
        _adapter_module._AdapterFailure(cast(Any, "internal"))


def test_direct_helper_failures_have_no_exception_context() -> None:
    with pytest.raises(_adapter_module._AdapterFailure) as headers:
        _adapter_module._response_headers(FakeHTTPResponse(headers=object()))
    assert headers.value.category is OllamaFailureCategory.RESPONSE_HEADERS
    assert headers.value.__cause__ is None and headers.value.__context__ is None
    with pytest.raises(_adapter_module._AdapterFailure) as decoded:
        _adapter_module._decode_json("not json")
    assert decoded.value.category is OllamaFailureCategory.RESPONSE_JSON
    assert decoded.value.__cause__ is None and decoded.value.__context__ is None


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_base_exception_propagates_but_close_is_attempted(signal: type[BaseException]) -> None:
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope())
    FakeHTTPConnection.exceptions = {"putrequest": signal("marker")}
    prepared = _prepared_for_exchange()
    with patch.object(http.client, "HTTPConnection", FakeHTTPConnection), pytest.raises(signal):
        OllamaCandidateAdapter(make_config())._exchange(prepared)
    assert [call[0] for call in FakeHTTPConnection.instances[0].calls].count("close") == 1


def test_getheaders_and_close_exceptions_are_classified_without_overwriting_prior_failure() -> None:
    response = FakeHTTPResponse(
        body=_canonical_envelope(), exceptions={"getheaders": TimeoutError("marker")}
    )
    assert _failure_category(response) is OllamaFailureCategory.RESPONSE_HEADERS
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope())
    FakeHTTPConnection.exceptions = {"close": TimeoutError("close-marker")}
    prepared = _prepared_for_exchange()
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        pytest.raises(_adapter_module._AdapterFailure) as raised,
    ):
        OllamaCandidateAdapter(make_config())._exchange(prepared)
    assert raised.value.category is OllamaFailureCategory.TRANSPORT
    assert raised.value.__cause__ is None and raised.value.__context__ is None


def test_close_failure_does_not_overwrite_an_existing_failure() -> None:
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(status=500, body=_canonical_envelope())
    FakeHTTPConnection.exceptions = {"close": TimeoutError("close-marker")}
    prepared = _prepared_for_exchange()
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        pytest.raises(_adapter_module._AdapterFailure) as raised,
    ):
        OllamaCandidateAdapter(make_config())._exchange(prepared)
    assert raised.value.category is OllamaFailureCategory.HTTP_STATUS

    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(headers=object(), body=_canonical_envelope())
    FakeHTTPConnection.exceptions = {"close": RuntimeError("close-marker")}
    prepared = _prepared_for_exchange()
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        pytest.raises(_adapter_module._AdapterFailure) as raised,
    ):
        OllamaCandidateAdapter(make_config())._exchange(prepared)
    assert raised.value.category is OllamaFailureCategory.RESPONSE_HEADERS


# Milestone 4C: public generation boundary.
def _candidate_content(action: str = "Inspect inlet for cavitation") -> str:
    _structured, _procedural, query_id, refs, _catalog, _raw, _plan = _result_fixture()
    return json.dumps(
        {
            "ranked_actions": [
                {
                    "rank": 1,
                    "action": action,
                    "target_asset": "ex:Pump_12",
                    "support_evidence": [
                        {"type": "kg_edge", "id": refs[0].stable_id},
                        {"type": "document_chunk", "id": refs[1].stable_id},
                    ],
                }
            ]
        },
        separators=(",", ":"),
    )


def test_generate_calls_exchange_once_and_parser_is_authoritative() -> None:
    structured, procedural, query_id = _prepared_fixture()
    content = _candidate_content()
    response = FakeHTTPResponse(body=_canonical_envelope(content=content))
    _reset_fake_http()
    FakeHTTPConnection.response = response
    adapter = OllamaCandidateAdapter(make_config())
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        patch.object(
            _adapter_module, "parse_candidate_actions", wraps=parse_candidate_actions
        ) as parser,
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)

    assert result.status is TerminalStatus.PASSED
    assert result.plan is not None
    assert result.raw_json == content
    assert result.evidence_catalog is not None
    assert result.evidence_catalog.references is result.evidence_references
    assert result.event.input_ids == (
        "ex:Pump_12",
        query_id,
        structured.evidence_references[0].stable_id,
        procedural.evidence_references[0].stable_id,
    )
    assert parser.call_args.kwargs == {
        "known_assets": ("ex:Pump_12",),
        "evidence_catalog": result.evidence_catalog,
    }
    assert parser.call_args.args == (content,)
    assert len(FakeHTTPConnection.instances) == 1


def test_generate_maps_parser_valid_missing_prepared_reference_to_internal() -> None:
    structured, procedural, query_id = _prepared_fixture()
    refs = (structured.evidence_references[0], procedural.evidence_references[0])
    content = json.dumps(
        {
            "ranked_actions": [
                {
                    "rank": 1,
                    "action": "Inspect inlet for cavitation",
                    "target_asset": "ex:Pump_12",
                    "support_evidence": [
                        {"type": "document_chunk", "id": refs[1].stable_id},
                    ],
                }
            ]
        },
        separators=(",", ":"),
    )
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope(content=content))
    with patch.object(http.client, "HTTPConnection", FakeHTTPConnection):
        result = OllamaCandidateAdapter(make_config()).generate(
            structured, procedural, "generation-run", query_id
        )

    assert result.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "internal"),
    )
    assert result.plan is None and result.raw_json is None and result.evidence_catalog is None
    assert len(FakeHTTPConnection.instances) == 1


def test_generate_does_not_catch_base_exception_from_passed_result_construction() -> None:
    structured, procedural, query_id = _prepared_fixture()
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(
        body=_canonical_envelope(content=_candidate_content())
    )
    marker = KeyboardInterrupt("marker")
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        patch.object(_adapter_module, "OllamaCandidateGenerationResult", side_effect=marker),
        pytest.raises(KeyboardInterrupt) as raised,
    ):
        OllamaCandidateAdapter(make_config()).generate(
            structured, procedural, "generation-run", query_id
        )

    assert raised.value is marker
    assert len(FakeHTTPConnection.instances) == 1


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"ranked_actions": []}),
        json.dumps(
            {
                "ranked_actions": [
                    {
                        "rank": True,
                        "action": "x",
                        "target_asset": "ex:Pump_12",
                        "support_evidence": [],
                    }
                ]
            }
        ),
        json.dumps(
            {
                "ranked_actions": [
                    {
                        "rank": 1,
                        "action": "x" * 2049,
                        "target_asset": "ex:Pump_12",
                        "support_evidence": [],
                    }
                ]
            }
        ),
        json.dumps(
            {
                "ranked_actions": [
                    {
                        "rank": 1,
                        "action": "x",
                        "target_asset": "x" * 1025,
                        "support_evidence": [],
                    }
                ]
            }
        ),
        json.dumps(
            {
                "ranked_actions": [
                    {
                        "rank": 1,
                        "action": "x",
                        "target_asset": "ex:Pump_12",
                        "support_evidence": [{"type": "kg_edge", "id": "x" * 8193}],
                    }
                ]
            }
        ),
    ],
)
def test_generate_maps_fixed_local_candidate_shape_failures_to_candidate_schema(
    content: str,
) -> None:
    structured, procedural, query_id = _prepared_fixture()
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope(content=content))
    adapter = OllamaCandidateAdapter(make_config())
    with (
        patch.object(http.client, "HTTPConnection", FakeHTTPConnection),
        patch.object(
            _adapter_module,
            "parse_candidate_actions",
            side_effect=AssertionError("parser bypassed"),
        ),
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)

    assert result.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "candidate_schema"),
    )
    assert result.plan is None and result.raw_json is None and result.evidence_catalog is None


def test_generate_maps_parser_rejection_to_candidate_validation() -> None:
    structured, procedural, query_id = _prepared_fixture()
    content = _candidate_content().replace("ex:Pump_12", "ex:Unknown")
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope(content=content))
    with patch.object(http.client, "HTTPConnection", FakeHTTPConnection):
        result = OllamaCandidateAdapter(make_config()).generate(
            structured, procedural, "generation-run", query_id
        )
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "candidate_validation"),
    )


def test_generate_maps_oversized_message_content_to_response_size() -> None:
    structured, procedural, query_id = _prepared_fixture()
    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope(content="x" * 262145))
    with patch.object(http.client, "HTTPConnection", FakeHTTPConnection):
        result = OllamaCandidateAdapter(make_config()).generate(
            structured, procedural, "generation-run", query_id
        )

    assert result.status is TerminalStatus.VALIDATION_FAILED_CLOSED
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "response_size"),
    )


def test_generate_maps_preparation_and_exchange_failures_without_retry() -> None:
    structured, procedural, query_id = _prepared_fixture()
    adapter = OllamaCandidateAdapter(make_config())
    with patch.object(
        OllamaCandidateAdapter,
        "_prepare_request",
        side_effect=_adapter_module._PreparationError("x"),
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "prerequisite"),
    )

    _reset_fake_http()
    FakeHTTPConnection.response = FakeHTTPResponse(body=_canonical_envelope())
    with patch.object(
        OllamaCandidateAdapter,
        "_exchange",
        side_effect=_adapter_module._AdapterFailure(OllamaFailureCategory.TRANSPORT),
    ) as exchange:
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "transport"),
    )
    exchange.assert_called_once()


@pytest.mark.parametrize("field", ["generation_run_id", "query_id"])
def test_generate_rejects_invalid_public_ids_before_preparation(field: str) -> None:
    structured, procedural, query_id = _prepared_fixture()
    values: dict[str, Any] = {"generation_run_id": "generation-run", "query_id": query_id}
    values[field] = True
    with (
        patch.object(
            OllamaCandidateAdapter, "_prepare_request", side_effect=AssertionError("prepared")
        ),
        pytest.raises(ValueError, match="invalid Ollama generation input"),
    ):
        OllamaCandidateAdapter(make_config()).generate(
            structured, procedural, values["generation_run_id"], values["query_id"]
        )


def test_generate_maps_unexpected_preparation_and_exchange_errors_to_internal() -> None:
    structured, procedural, query_id = _prepared_fixture()
    adapter = OllamaCandidateAdapter(make_config())
    with patch.object(
        OllamaCandidateAdapter, "_prepare_request", side_effect=RuntimeError("secret")
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "internal"),
    )

    prepared = adapter._prepare_request(structured, procedural, "generation-run", query_id)
    with patch.object(OllamaCandidateAdapter, "_exchange", side_effect=RuntimeError("secret")):
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "internal"),
    )
    assert prepared.endpoint.endswith("/api/chat")


def test_generate_maps_unexpected_shape_and_parser_errors_to_sanitized_categories() -> None:
    structured, procedural, query_id = _prepared_fixture()
    adapter = OllamaCandidateAdapter(make_config())
    envelope = _adapter_module._OllamaEnvelope(_candidate_content(), ())
    with (
        patch.object(OllamaCandidateAdapter, "_exchange", return_value=envelope),
        patch.object(
            _adapter_module, "_validate_candidate_shape", side_effect=RuntimeError("secret")
        ),
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "candidate_schema"),
    )

    with (
        patch.object(OllamaCandidateAdapter, "_exchange", return_value=envelope),
        patch.object(
            _adapter_module, "parse_candidate_actions", side_effect=RuntimeError("secret")
        ),
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "internal"),
    )


def test_generate_preserves_sanitized_shape_failure_category() -> None:
    structured, procedural, query_id = _prepared_fixture()
    adapter = OllamaCandidateAdapter(make_config())
    envelope = _adapter_module._OllamaEnvelope(_candidate_content(), ())
    with (
        patch.object(OllamaCandidateAdapter, "_exchange", return_value=envelope),
        patch.object(
            _adapter_module,
            "_validate_candidate_shape",
            side_effect=_adapter_module._AdapterFailure(OllamaFailureCategory.RESPONSE_JSON),
        ),
    ):
        result = adapter.generate(structured, procedural, "generation-run", query_id)
    assert result.event.errors == (
        StageError(StageErrorCode.CANDIDATE_GENERATION_FAILED, "response_json"),
    )


def test_failed_result_rejects_released_payload_fields() -> None:
    failed = _failed_result(OllamaFailureCategory.INTERNAL)
    passed = _passed_result()
    assert passed.plan is not None
    with pytest.raises(ValueError, match="invalid Ollama generation result"):
        replace(failed, plan=passed.plan)
