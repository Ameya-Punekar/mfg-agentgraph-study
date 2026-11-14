"""Contract tests for the explicitly invoked live Fuseki provenance proof."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from rdflib import Graph

SCRIPT_PATH = Path(__file__).parents[1] / "tests" / "integration" / "live_fuseki_provenance.py"


def _graph_copy(graph: Graph) -> Graph:
    copy = Graph()
    for triple in graph:
        copy.add(triple)
    return copy


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("live_fuseki_provenance", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_script_import_has_no_side_effects(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.dict(os.environ, {}, clear=True):
        module = _module()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert hasattr(module, "test_live_fuseki_provenance")


def test_live_script_missing_environment_fails_without_constructing_store(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(module, "FusekiProvenanceStoreConfig", side_effect=AssertionError("config")),
        pytest.raises(pytest.fail.Exception),
    ):
        module.test_live_fuseki_provenance()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_live_script_success_persists_once_and_cleans_exact_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    for name, value in {
        module.UPDATE_ENV: "http://127.0.0.1:3030/update",
        module.QUERY_ENV: "http://127.0.0.1:3030/query",
        module.GRAPH_BASE_ENV: "https://example.org/live-provenance",
        module.TRACE_ENV: "https://example.org/live-trace/1",
    }.items():
        monkeypatch.setenv(name, value)
    calls: list[str] = []
    monkeypatch.setattr(
        module.FusekiProvenanceStore,
        "persist",
        lambda self, graph: calls.append("persist"),
    )
    monkeypatch.setattr(
        module.FusekiProvenanceStore,
        "resolve",
        lambda self, provenance_id, expected_graph: _graph_copy(expected_graph),
    )
    monkeypatch.setattr(module, "_ask_graph_empty", lambda config, graph_iri: True)
    monkeypatch.setattr(
        module,
        "_delete_exact_graph",
        lambda config, graph_iri, canonical: calls.append("delete"),
    )
    monkeypatch.setattr(
        module, "_assert_graph_empty", lambda config, graph_iri: calls.append("empty")
    )

    module.test_live_fuseki_provenance()

    assert calls == ["persist", "delete", "empty"]


def test_live_script_does_not_cleanup_after_unknown_persist_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    for name, value in {
        module.UPDATE_ENV: "http://127.0.0.1:3030/update",
        module.QUERY_ENV: "http://127.0.0.1:3030/query",
        module.GRAPH_BASE_ENV: "https://example.org/live-provenance",
        module.TRACE_ENV: "https://example.org/live-trace/2",
    }.items():
        monkeypatch.setenv(name, value)
    calls: list[str] = []

    def fail(self: object, graph: object) -> None:
        del self
        del graph
        calls.append("persist")
        raise RuntimeError("unknown")

    monkeypatch.setattr(module.FusekiProvenanceStore, "persist", fail)
    monkeypatch.setattr(module, "_ask_graph_empty", lambda config, graph_iri: True)
    monkeypatch.setattr(module, "_delete_exact_graph", lambda *args: calls.append("delete"))

    with pytest.raises(RuntimeError, match="unknown"):
        module.test_live_fuseki_provenance()
    assert calls == ["persist"]


def test_live_script_filename_is_not_collected_by_default_pattern() -> None:
    assert SCRIPT_PATH.name == "live_fuseki_provenance.py"
    assert not SCRIPT_PATH.name.startswith("test_")
