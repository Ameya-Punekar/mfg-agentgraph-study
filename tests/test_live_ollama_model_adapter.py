import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "tests" / "integration" / "live_ollama_model_adapter.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("live_ollama_model_adapter", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_result(module: Any) -> Any:
    return SimpleNamespace(
        status=module.TerminalStatus.PASSED,
        model_id="llama3.2",
        runtime_id="ollama-live-script",
        prompt_id=module.OLLAMA_PROMPT_ID,
        schema_id=module.OLLAMA_SCHEMA_ID,
        event=SimpleNamespace(stage=module.StageName.CANDIDATE_GENERATION),
    )


def test_live_script_import_has_no_environment_network_output_or_mutation_side_effects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("socket.getaddrinfo", side_effect=AssertionError("network")),
        patch("socket.create_connection", side_effect=AssertionError("network")),
    ):
        module = _module()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert hasattr(module, "main")


def test_live_script_missing_environment_fails_before_config_or_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(module, "OllamaModelAdapterConfig", side_effect=AssertionError("config")),
        patch.object(module, "OllamaCandidateAdapter", side_effect=AssertionError("adapter")),
        patch("socket.create_connection", side_effect=AssertionError("network")),
    ):
        assert module.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "LIVE_OLLAMA_MODEL_ADAPTER_FAILED\n"


def test_live_script_success_calls_generate_once_and_prints_only_constant_marker(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _module()
    monkeypatch.setenv("MFG_AGENTGRAPH_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("MFG_AGENTGRAPH_OLLAMA_MODEL", "llama3.2")
    result = _fake_result(module)
    adapter = module.OllamaCandidateAdapter(
        module.OllamaModelAdapterConfig("http://127.0.0.1:11434", "llama3.2", "ollama-live-script")
    )
    with patch.object(module.OllamaCandidateAdapter, "generate", return_value=result) as generate:
        monkeypatch.setattr(module, "_build_adapter", lambda *_args: adapter)
        assert module.main() == 0

    generate.assert_called_once()
    captured = capsys.readouterr()
    assert captured.out == "LIVE_OLLAMA_MODEL_ADAPTER_OK\n"
    assert captured.err == ""


def test_live_script_rejects_nonpassing_or_identity_drift_without_leaking_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _module()
    monkeypatch.setenv("MFG_AGENTGRAPH_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("MFG_AGENTGRAPH_OLLAMA_MODEL", "llama3.2")
    result = _fake_result(module)
    object.__setattr__(result, "status", module.TerminalStatus.VALIDATION_FAILED_CLOSED)
    adapter = module.OllamaCandidateAdapter(
        module.OllamaModelAdapterConfig("http://127.0.0.1:11434", "llama3.2", "ollama-live-script")
    )
    with patch.object(module.OllamaCandidateAdapter, "generate", return_value=result):
        monkeypatch.setattr(module, "_build_adapter", lambda *_args: adapter)
        assert module.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "LIVE_OLLAMA_MODEL_ADAPTER_FAILED\n"
    assert "Pump_12" not in captured.err


def test_live_script_filename_is_not_pytest_collection_pattern() -> None:
    path = Path(__file__).parents[1] / "tests" / "integration" / "live_ollama_model_adapter.py"
    assert path.name == "live_ollama_model_adapter.py"
    assert not path.name.startswith("test_")
