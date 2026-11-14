"""Contract tests for the Issue #114 stack command line."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from mfg_agentgraph.stack_cli import main
from mfg_agentgraph.stack_config import (
    DEFAULT_EMBEDDING_MODEL_DIGEST,
    DEFAULT_GENERATION_MODEL_DIGEST,
)
from mfg_agentgraph.stack_preflight import HttpResponse, TransportError

_FUSEKI = "http://127.0.0.1:3030"
_QDRANT = "http://127.0.0.1:6333"
_OLLAMA = "http://127.0.0.1:11434"


class _Transport:
    def __init__(self, healthy: bool) -> None:
        self.healthy = healthy
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(url)
        if not self.healthy:
            raise TransportError("connection refused")
        if url == f"{_FUSEKI}/$/ping":
            return HttpResponse(200, b"pong")
        if url == f"{_FUSEKI}/$/server":
            return HttpResponse(200, json.dumps({"version": "6.2.0"}).encode())
        if url == f"{_QDRANT}/healthz":
            return HttpResponse(200, b"healthz check passed")
        if url == f"{_QDRANT}/":
            return HttpResponse(200, json.dumps({"version": "1.19.2"}).encode())
        if url == f"{_QDRANT}/collections/procedural":
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "result": {
                            "config": {"params": {"vectors": {"size": 768, "distance": "Cosine"}}}
                        }
                    }
                ).encode(),
            )
        if url == f"{_OLLAMA}/api/version":
            return HttpResponse(200, json.dumps({"version": "0.23.2"}).encode())
        if url == f"{_OLLAMA}/api/tags":
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "models": [
                            {
                                "name": "qwen2.5:7b-instruct-q4_K_M",
                                "digest": DEFAULT_GENERATION_MODEL_DIGEST,
                            },
                            {
                                "name": "nomic-embed-text:latest",
                                "digest": DEFAULT_EMBEDDING_MODEL_DIGEST,
                            },
                        ]
                    }
                ).encode(),
            )
        raise AssertionError(f"unexpected GET {url}")

    def post(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(url)
        if not self.healthy:
            raise TransportError("connection refused")
        if url == f"{_FUSEKI}/ds/sparql":
            return HttpResponse(200, json.dumps({"boolean": True}).encode())
        if url.startswith(f"{_FUSEKI}/ds/data"):
            return HttpResponse(204, b"")
        raise AssertionError(f"unexpected POST {url}")

    def put(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(url)
        raise AssertionError(f"unexpected PUT {url}")


def test_doctor_reports_success_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["doctor"], transport=_Transport(healthy=True), environ={})

    assert code == 0
    out = capsys.readouterr().out
    assert "fuseki_version" in out
    assert "fail" not in out.lower()


def test_doctor_exits_non_zero_when_a_service_is_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["doctor"], transport=_Transport(healthy=False), environ={})

    assert code == 1
    out = capsys.readouterr().out
    assert "connection refused" in out


def test_status_prints_the_resolved_envelope_without_network_calls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = _Transport(healthy=True)

    code = main(["status"], transport=transport, environ={})

    assert code == 0
    out = capsys.readouterr().out
    assert _FUSEKI in out
    assert _QDRANT in out
    assert _OLLAMA in out
    assert transport.calls == []


def test_bootstrap_exits_non_zero_when_the_services_are_absent() -> None:
    code = main(["bootstrap"], transport=_Transport(healthy=False), environ={})

    assert code == 1


def test_doctor_rejects_a_non_loopback_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        ["doctor"],
        transport=_Transport(healthy=True),
        environ={"MFG_QDRANT_URL": "http://10.0.0.5:6333"},
    )

    assert code == 1
    assert "loopback" in capsys.readouterr().out


def test_an_unknown_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["explode"], transport=_Transport(healthy=True), environ={})

    assert excinfo.value.code == 2


def _env_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "env"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_cli_reads_the_deploy_env_file_when_no_environment_is_supplied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env_file(
        tmp_path,
        "# live stack\nMFG_FUSEKI_URL=http://127.0.0.1:23030\n"
        "MFG_QDRANT_URL='http://127.0.0.1:23333'\n"
        "MFG_FUSEKI_ADMIN_PASSWORD=s3cret\n"
        "UNRELATED_KEY=ignored\n",
    )

    code = main(["status"], transport=_Transport(healthy=True), environ=None, env_file=path)

    out = capsys.readouterr().out
    assert code == 0
    assert "http://127.0.0.1:23030" in out
    assert "http://127.0.0.1:23333" in out
    assert "s3cret" not in out


def test_the_process_environment_overrides_the_env_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _env_file(tmp_path, "MFG_FUSEKI_URL=http://127.0.0.1:23030\n")

    code = main(
        ["status"],
        transport=_Transport(healthy=True),
        environ={"MFG_FUSEKI_URL": "http://127.0.0.1:3999"},
        env_file=path,
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "http://127.0.0.1:3999" in out
    assert "23030" not in out


def test_a_missing_env_file_keeps_the_pinned_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in tuple(os.environ):
        if name.startswith("MFG_"):
            monkeypatch.delenv(name)

    code = main(
        ["status"],
        transport=_Transport(healthy=True),
        environ=None,
        env_file=tmp_path / "absent",
    )

    out = capsys.readouterr().out
    assert code == 0
    assert _FUSEKI in out


def test_an_unreadable_env_file_is_a_configuration_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["status"],
        transport=_Transport(healthy=True),
        environ=None,
        env_file=tmp_path,
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "configuration error" in out
