"""Contract tests for the Issue #114 stack preflight."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from mfg_agentgraph.stack_config import ModelPin, ServiceEndpoint, StackConfig
from mfg_agentgraph.stack_preflight import (
    HttpResponse,
    PreflightReport,
    TransportError,
    UrllibTransport,
    run_preflight,
)

_DIGEST = "sha256:" + "a" * 64
_FUSEKI = "http://127.0.0.1:3030"
_QDRANT = "http://127.0.0.1:6333"
_OLLAMA = "http://127.0.0.1:11434"


def _config() -> StackConfig:
    return StackConfig(
        fuseki=ServiceEndpoint.parse(_FUSEKI),
        qdrant=ServiceEndpoint.parse(_QDRANT),
        ollama=ServiceEndpoint.parse(_OLLAMA),
        generation_model=ModelPin("qwen2.5:7b-instruct-q4_K_M", _DIGEST),
        embedding_model=ModelPin("nomic-embed-text", _DIGEST),
    )


@dataclass
class _FakeTransport:
    """Route table transport: a route value is a response or an exception."""

    routes: dict[tuple[str, str], Any]

    def _dispatch(self, method: str, url: str) -> HttpResponse:
        outcome = self.routes.get((method, url))
        if outcome is None:
            raise TransportError(f"no route for {method} {url}")
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, HttpResponse)
        return outcome

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        return self._dispatch("GET", url)

    def post(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        return self._dispatch("POST", url)

    def put(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        return self._dispatch("PUT", url)


def _json(payload: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status=200, body=json.dumps(payload).encode())


def _healthy_routes() -> dict[tuple[str, str], Any]:
    return {
        ("GET", f"{_FUSEKI}/$/ping"): HttpResponse(200, b"pong"),
        ("GET", f"{_FUSEKI}/$/server"): _json({"version": "6.2.0"}),
        ("POST", f"{_FUSEKI}/ds/sparql"): _json({"head": {}, "boolean": True}),
        ("GET", f"{_QDRANT}/healthz"): HttpResponse(200, b"healthz check passed"),
        ("GET", f"{_QDRANT}/"): _json({"title": "qdrant", "version": "1.19.2"}),
        ("GET", f"{_QDRANT}/collections/procedural"): _json(
            {"result": {"config": {"params": {"vectors": {"size": 768, "distance": "Cosine"}}}}}
        ),
        ("GET", f"{_OLLAMA}/api/version"): _json({"version": "0.23.2"}),
        ("GET", f"{_OLLAMA}/api/tags"): _json(
            {
                "models": [
                    {"name": "qwen2.5:7b-instruct-q4_K_M", "digest": _DIGEST},
                    {"name": "nomic-embed-text:latest", "digest": _DIGEST},
                ]
            }
        ),
    }


def _report(routes: dict[tuple[str, str], Any]) -> PreflightReport:
    return run_preflight(_config(), _FakeTransport(routes))


def test_a_healthy_stack_passes_every_check() -> None:
    report = _report(_healthy_routes())

    assert report.ok is True
    assert report.exit_code == 0
    assert report.failures == ()
    assert {check.name for check in report.checks} == {
        "fuseki_ping",
        "fuseki_version",
        "fuseki_graphs",
        "qdrant_health",
        "qdrant_version",
        "qdrant_collection",
        "ollama_version",
        "ollama_models",
    }


def test_fuseki_version_mismatch_fails_loudly() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_FUSEKI}/$/server")] = _json({"version": "5.1.0"})

    report = _report(routes)

    assert report.ok is False
    assert report.exit_code == 1
    failure = next(c for c in report.failures if c.name == "fuseki_version")
    assert "5.1.0" in failure.detail
    assert "6.2.0" in failure.detail


def test_missing_named_graph_fails_the_graph_check() -> None:
    routes = _healthy_routes()
    routes[("POST", f"{_FUSEKI}/ds/sparql")] = _json({"boolean": False})

    report = _report(routes)

    assert report.ok is False
    assert [c.name for c in report.failures] == ["fuseki_graphs"]


def test_collection_dimension_mismatch_fails() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_QDRANT}/collections/procedural")] = _json(
        {"result": {"config": {"params": {"vectors": {"size": 384, "distance": "Cosine"}}}}}
    )

    report = _report(routes)

    failure = next(c for c in report.failures if c.name == "qdrant_collection")
    assert "384" in failure.detail


def test_collection_with_a_different_distance_metric_fails() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_QDRANT}/collections/procedural")] = _json(
        {"result": {"config": {"params": {"vectors": {"size": 768, "distance": "Dot"}}}}}
    )

    report = _report(routes)

    failure = next(c for c in report.failures if c.name == "qdrant_collection")
    assert "Dot" in failure.detail
    assert "Cosine" in failure.detail


def test_collection_without_a_reported_distance_fails() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_QDRANT}/collections/procedural")] = _json(
        {"result": {"config": {"params": {"vectors": {"size": 768}}}}}
    )

    report = _report(routes)

    assert [c.name for c in report.failures] == ["qdrant_collection"]


def test_model_digest_mismatch_is_not_ignored() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_OLLAMA}/api/tags")] = _json(
        {"models": [{"name": "qwen2.5:7b-instruct-q4_K_M", "digest": "sha256:" + "b" * 64}]}
    )

    report = _report(routes)

    assert report.ok is False
    failure = next(c for c in report.failures if c.name == "ollama_models")
    assert "nomic-embed-text" in failure.detail or "digest" in failure.detail


def test_a_transport_error_fails_one_check_without_aborting_the_rest() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_QDRANT}/healthz")] = TransportError("connection refused")

    report = _report(routes)

    assert report.ok is False
    failed = {c.name for c in report.failures}
    assert failed == {"qdrant_health"}
    assert len(report.checks) == 8


def test_an_unexpected_status_fails_the_check() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_OLLAMA}/api/version")] = HttpResponse(500, b"boom")

    report = _report(routes)

    failure = next(c for c in report.failures if c.name == "ollama_version")
    assert "500" in failure.detail


def test_never_falls_back_to_fixtures_when_the_service_is_absent() -> None:
    with pytest.raises(TransportError):
        _FakeTransport({}).get(f"{_FUSEKI}/$/ping")

    report = _report({})

    assert report.ok is False
    assert len(report.failures) == 8


def test_unprefixed_server_digests_still_match_the_pin() -> None:
    routes = _healthy_routes()
    bare = _DIGEST.removeprefix("sha256:")
    routes[("GET", f"{_OLLAMA}/api/tags")] = _json(
        {
            "models": [
                {"name": "qwen2.5:7b-instruct-q4_K_M", "digest": bare},
                {"name": "nomic-embed-text:latest", "digest": bare},
            ]
        }
    )

    assert _report(routes).ok is True


@contextmanager
def _serve(routes: dict[str, tuple[int, bytes]]) -> Iterator[int]:
    """Serve fixed responses so the real stdlib transport is exercised."""

    class Handler(BaseHTTPRequestHandler):
        def _respond(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            payload = self.rfile.read(length) if length else b""
            if self.command in {"POST", "PUT"} and payload:
                body = payload
                status = 200
            else:
                status, body = routes.get(self.path, (404, b"missing"))
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _respond
        do_POST = _respond
        do_PUT = _respond

        def log_message(self, *args: object) -> None:
            """Silence the default request log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_urllib_transport_reads_real_responses_and_keeps_error_statuses() -> None:
    with _serve({"/$/ping": (200, b"pong")}) as port:
        transport = UrllibTransport(timeout_seconds=5.0)
        base = f"http://127.0.0.1:{port}"

        assert transport.get(f"{base}/$/ping") == HttpResponse(status=200, body=b"pong")
        assert transport.get(f"{base}/absent").status == 404
        assert transport.post(f"{base}/echo", body=b"payload") == HttpResponse(
            status=200, body=b"payload"
        )
        assert transport.put(f"{base}/echo", body=b"replacement").status == 200


def test_urllib_transport_returns_a_corpus_sized_graph_whole() -> None:
    """A CONSTRUCT body for the corpus graph must not be silently truncated.

    The graph reader parses the transport body directly, so a capped read turns a
    valid corpus graph into a turtle syntax error instead of a load result.
    """

    payload = b"x" * 4_000_000
    with _serve({"/big": (200, payload)}) as port:
        response = UrllibTransport(timeout_seconds=5.0).get(f"http://127.0.0.1:{port}/big")

    assert response.status == 200
    assert response.body == payload


def test_urllib_transport_raises_instead_of_truncating_an_oversized_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body over the read limit is an error, never a silent partial read."""

    from mfg_agentgraph import stack_preflight

    monkeypatch.setattr(stack_preflight, "_MAX_BODY_BYTES", 8)
    with (
        _serve({"/big": (200, b"y" * 64)}) as port,
        pytest.raises(TransportError, match="read limit"),
    ):
        UrllibTransport(timeout_seconds=5.0).get(f"http://127.0.0.1:{port}/big")


def test_urllib_transport_raises_on_an_unreachable_service() -> None:
    with _serve({}) as port:
        closed = port
    with pytest.raises(TransportError):
        UrllibTransport(timeout_seconds=2.0).get(f"http://127.0.0.1:{closed}/")


def test_non_json_success_bodies_are_transport_failures() -> None:
    with _serve({"$/server": (200, b"not json")}) as port:
        routes = {
            ("GET", f"http://127.0.0.1:{port}/$/server"): HttpResponse(200, b"not json"),
        }

        config = StackConfig(
            fuseki=ServiceEndpoint.parse(f"http://127.0.0.1:{port}"),
            qdrant=ServiceEndpoint.parse(_QDRANT),
            ollama=ServiceEndpoint.parse(_OLLAMA),
            generation_model=ModelPin("qwen2.5:7b-instruct-q4_K_M", _DIGEST),
            embedding_model=ModelPin("nomic-embed-text", _DIGEST),
        )
        report = run_preflight(config, _FakeTransport(routes))

        failure = next(c for c in report.failures if c.name == "fuseki_version")
        assert "unreadable" in failure.detail


def test_ping_accepts_the_timestamp_body_fuseki_6_returns() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_FUSEKI}/$/ping")] = HttpResponse(200, b"2026-11-08T18:37:50.818+00:00\r\n")

    assert _report(routes).ok is True


def test_ping_rejects_an_empty_body() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_FUSEKI}/$/ping")] = HttpResponse(200, b"")

    report = _report(routes)

    failure = next(c for c in report.failures if c.name == "fuseki_ping")
    assert "empty" in failure.detail


def test_graph_queries_use_the_published_sparql_service() -> None:
    routes = _healthy_routes()
    published = routes.pop(("POST", f"{_FUSEKI}/ds/sparql"))
    routes[("POST", f"{_FUSEKI}/ds/query")] = published

    report = _report(routes)

    assert [c.name for c in report.failures] == ["fuseki_graphs"]


def test_version_check_sends_admin_credentials_when_configured() -> None:
    seen: list[dict[str, str]] = []

    class Recorder(_FakeTransport):
        def get(
            self,
            url: str,
            *,
            headers: Mapping[str, str] | None = None,
            timeout_seconds: float | None = None,
        ) -> HttpResponse:
            seen.append(dict(headers or {}))
            return super().get(url, headers=headers, timeout_seconds=timeout_seconds)

    config = StackConfig(
        fuseki=ServiceEndpoint.parse(_FUSEKI),
        qdrant=ServiceEndpoint.parse(_QDRANT),
        ollama=ServiceEndpoint.parse(_OLLAMA),
        generation_model=ModelPin("qwen2.5:7b-instruct-q4_K_M", _DIGEST),
        embedding_model=ModelPin("nomic-embed-text", _DIGEST),
        admin_password="s3cret",
    )

    report = run_preflight(config, Recorder(_healthy_routes()))

    assert report.ok is True
    assert any("Authorization" in headers for headers in seen)


def test_unauthenticated_server_endpoint_is_reported_as_an_auth_problem() -> None:
    routes = _healthy_routes()
    routes[("GET", f"{_FUSEKI}/$/server")] = HttpResponse(401, b"")

    report = _report(routes)

    failure = next(c for c in report.failures if c.name == "fuseki_version")
    assert "auth" in failure.detail.lower()


def test_urllib_transport_never_follows_a_redirect_to_another_location() -> None:
    class Redirecting(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/moved":
                self.send_response(302)
                self.send_header("Location", "/target")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b"followed"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            """Silence the default request log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Redirecting)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{int(server.server_address[1])}"
        response = UrllibTransport(timeout_seconds=5.0).get(f"{base}/moved")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == 302
    assert response.body != b"followed"


def test_urllib_transport_honours_a_per_call_timeout() -> None:
    with _serve({"/$/ping": (200, b"pong")}) as port:
        transport = UrllibTransport(timeout_seconds=5.0)

        response = transport.get(f"http://127.0.0.1:{port}/$/ping", timeout_seconds=120.0)

    assert response == HttpResponse(status=200, body=b"pong")


@pytest.mark.parametrize("timeout", [0.0, -1.0])
def test_urllib_transport_rejects_a_non_positive_timeout_override(timeout: float) -> None:
    with pytest.raises(ValueError):
        UrllibTransport(timeout_seconds=5.0).get("http://127.0.0.1:1/", timeout_seconds=timeout)
