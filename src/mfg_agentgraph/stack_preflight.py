"""Read-only preflight for the free local deployment envelope (Issue #114).

Every check is independent and reports its own outcome, so a single unavailable
service cannot mask the state of the others. There is no fixture fallback: an
unreachable or mismatched service is always a failing check.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import Message
from typing import IO, Final, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from mfg_agentgraph.stack_config import DEFAULT_QDRANT_DISTANCE, StackConfig

# A single read bound, not a data cap: the corpus graph is read back with one
# CONSTRUCT whose body is parsed directly. At the protocol's 10^5-triple ceiling a
# turtle serialisation runs to several megabytes (13,405 triples measured at 1.07 MB),
# so a 1 MiB limit truncated a valid graph into a turtle syntax error.
_MAX_BODY_BYTES: Final = 67_108_864
_OK_STATUSES: Final = frozenset({200})
_JSON_ACCEPT: Final = {"Accept": "application/sparql-results+json"}


class TransportError(RuntimeError):
    """A service could not be reached or answered unusably."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """One bounded service response."""

    status: int
    body: bytes


class HttpTransport(Protocol):
    """The minimal transport surface the stack commands need."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        """Issue a GET request."""

    def post(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        """Issue a POST request."""

    def put(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        """Issue a PUT request."""


class _RejectingRedirectHandler(HTTPRedirectHandler):
    """Turn a redirect into its own status instead of following it."""

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> Request | None:
        del req, fp, code, msg, headers, newurl
        return None


def _read_bounded(response: IO[bytes], *, limit: int | None = None) -> bytes:
    """Read one response body, failing loudly instead of truncating it.

    A silently shortened body is indistinguishable from a complete one, so a
    truncated graph would be parsed and reported as different content. One byte
    past the limit is read to detect overflow.
    """

    bound = _MAX_BODY_BYTES if limit is None else limit
    body = response.read(bound + 1)
    if len(body) > bound:
        raise TransportError(f"response body exceeds the {bound}-byte read limit")
    return body


class UrllibTransport:
    """Standard-library transport that never uses a proxy or follows redirects."""

    __slots__ = ("_opener", "_timeout")

    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._opener = build_opener(ProxyHandler({}), _RejectingRedirectHandler())
        self._timeout = timeout_seconds

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        return self._request("GET", url, b"", None, headers, timeout_seconds)

    def post(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        return self._request("POST", url, body, content_type, headers, timeout_seconds)

    def put(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        return self._request("PUT", url, body, content_type, headers, timeout_seconds)

    def _request(
        self,
        method: str,
        url: str,
        body: bytes,
        content_type: str | None,
        headers: Mapping[str, str] | None,
        timeout_seconds: float | None,
    ) -> HttpResponse:
        timeout = self._timeout if timeout_seconds is None else _check_timeout(timeout_seconds)
        request = Request(url, data=body if method != "GET" else None, method=method)
        if content_type is not None:
            request.add_header("Content-Type", content_type)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return HttpResponse(status=response.status, body=_read_bounded(response))
        except HTTPError as exc:
            return HttpResponse(status=exc.code, body=_read_bounded(exc))
        except (URLError, OSError, TimeoutError) as exc:
            raise TransportError(str(exc)) from exc


def _check_timeout(value: float) -> float:
    """Return a validated per-call timeout."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout_seconds must be a number")
    if value <= 0:
        raise ValueError("timeout_seconds must be positive")
    return float(value)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One preflight outcome."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """The full preflight outcome for one configuration."""

    checks: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        """Return whether every check passed."""

        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        """Return the failing checks in evaluation order."""

        return tuple(check for check in self.checks if not check.ok)

    @property
    def exit_code(self) -> int:
        """Return a process exit code for this report."""

        return 0 if self.ok else 1


def _json_document(response: HttpResponse, name: str) -> dict[str, object]:
    if response.status not in _OK_STATUSES:
        raise TransportError(f"{name} returned HTTP {response.status}")
    try:
        document = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TransportError(f"{name} returned an unreadable response") from exc
    if not isinstance(document, dict):
        raise TransportError(f"{name} returned an unexpected document")
    return document


def _check(name: str, probe: object) -> CheckResult:
    assert callable(probe)
    try:
        detail = probe()
    except TransportError as exc:
        return CheckResult(name=name, ok=False, detail=f"transport failure: {exc}")
    return CheckResult(name=name, ok=True, detail=detail)


def _fuseki_ping(config: StackConfig, transport: HttpTransport) -> str:
    response = transport.get(config.fuseki.url("/$/ping"))
    if response.status not in _OK_STATUSES:
        raise TransportError(f"ping returned HTTP {response.status}")
    body = response.body.strip()
    if not body:
        raise TransportError("ping returned an empty body")
    return f"ping ok ({body.decode('utf-8', 'replace')[:64]})"


def _fuseki_version(config: StackConfig, transport: HttpTransport) -> str:
    response = transport.get(config.fuseki.url("/$/server"), headers=config.admin_auth_headers())
    if response.status in {401, 403}:
        raise TransportError(
            "the administrative endpoint requires authentication; "
            "set MFG_FUSEKI_ADMIN_PASSWORD so the version can be verified"
        )
    document = _json_document(response, "server")
    version = document.get("version")
    if version != config.fuseki_version:
        raise TransportError(f"expected Fuseki {config.fuseki_version}, service reports {version}")
    return f"Fuseki {version}"


def _fuseki_graphs(config: StackConfig, transport: HttpTransport) -> str:
    missing: list[str] = []
    for graph_iri in (config.factory_graph, config.shapes_graph):
        query = "ASK { GRAPH <" + graph_iri + "> { ?s ?p ?o } }"
        document = _json_document(
            transport.post(
                config.fuseki_query_url(),
                body=query.encode(),
                content_type="application/sparql-query",
                headers=_JSON_ACCEPT,
            ),
            "graph query",
        )
        if document.get("boolean") is not True:
            missing.append(graph_iri)
    if missing:
        raise TransportError(f"missing named graph(s): {', '.join(missing)}")
    return "factory and shapes graphs present"


def _qdrant_health(config: StackConfig, transport: HttpTransport) -> str:
    response = transport.get(config.qdrant.url("/healthz"))
    if response.status not in _OK_STATUSES:
        raise TransportError(f"healthz returned HTTP {response.status}")
    return "healthz ok"


def _qdrant_version(config: StackConfig, transport: HttpTransport) -> str:
    document = _json_document(transport.get(config.qdrant.url("/")), "root")
    version = document.get("version")
    if version != config.qdrant_version:
        raise TransportError(f"expected Qdrant {config.qdrant_version}, service reports {version}")
    return f"Qdrant {version}"


def _collection_vectors(document: Mapping[str, object]) -> Mapping[str, object] | None:
    result = document.get("result")
    if not isinstance(result, dict):
        return None
    config = result.get("config")
    if not isinstance(config, dict):
        return None
    params = config.get("params")
    if not isinstance(params, dict):
        return None
    vectors = params.get("vectors")
    return vectors if isinstance(vectors, dict) else None


def collection_vector_size(document: Mapping[str, object]) -> int | None:
    """Return the configured vector size from one Qdrant collection document."""

    vectors = _collection_vectors(document)
    if vectors is None:
        return None
    size = vectors.get("size")
    return size if isinstance(size, int) and not isinstance(size, bool) else None


def collection_distance(document: Mapping[str, object]) -> str | None:
    """Return the configured distance metric from one Qdrant collection document."""

    vectors = _collection_vectors(document)
    if vectors is None:
        return None
    distance = vectors.get("distance")
    return distance if isinstance(distance, str) else None


def _qdrant_collection(config: StackConfig, transport: HttpTransport) -> str:
    url = config.qdrant.url(f"/collections/{config.qdrant_collection}")
    response = transport.get(url)
    if response.status == 404:
        raise TransportError(f"collection {config.qdrant_collection!r} does not exist")
    document = _json_document(response, "collection")
    size = collection_vector_size(document)
    if size != config.embedding_dimension:
        raise TransportError(
            f"collection vector size is {size}, expected {config.embedding_dimension}"
        )
    distance = collection_distance(document)
    if distance != DEFAULT_QDRANT_DISTANCE:
        raise TransportError(
            f"collection distance is {distance!r}, expected {DEFAULT_QDRANT_DISTANCE!r}"
        )
    return f"collection {config.qdrant_collection} size {size} {distance}"


def _ollama_version(config: StackConfig, transport: HttpTransport) -> str:
    document = _json_document(transport.get(config.ollama.url("/api/version")), "version")
    version = document.get("version")
    if version != config.ollama_version:
        raise TransportError(f"expected Ollama {config.ollama_version}, service reports {version}")
    return f"Ollama {version}"


def installed_model_digests(transport: HttpTransport, config: StackConfig) -> dict[str, str]:
    """Return ``name -> digest`` for the models the local server reports."""

    document = _json_document(transport.get(config.ollama.url("/api/tags")), "tags")
    models = document.get("models")
    if not isinstance(models, list):
        raise TransportError("tags response has no model list")
    digests: dict[str, str] = {}
    for entry in models:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        digest = entry.get("digest")
        if isinstance(name, str) and isinstance(digest, str):
            digests[name] = digest
    return digests


def digest_matches(installed: str, pinned: str) -> bool:
    """Compare digests whether or not the server echoes the algorithm prefix.

    Ollama's ``/api/tags`` reports a bare hexadecimal digest, while the pinned
    identity is written as ``sha256:<hex>``.
    """

    return installed.removeprefix("sha256:") == pinned.removeprefix("sha256:")


def _ollama_models(config: StackConfig, transport: HttpTransport) -> str:
    digests = installed_model_digests(transport, config)
    problems: list[str] = []
    for pin in (config.generation_model, config.embedding_model):
        installed = digests.get(pin.installed_name)
        if installed is None:
            problems.append(f"missing model {pin.model_id}")
        elif not digest_matches(installed, pin.digest):
            problems.append(
                f"model digest mismatch for {pin.model_id}: "
                f"installed {installed}, pinned {pin.digest}"
            )
    if problems:
        raise TransportError("; ".join(problems))
    return "generation and embedding models pinned"


def run_preflight(config: StackConfig, transport: HttpTransport) -> PreflightReport:
    """Run every read-only health check against the configured envelope."""

    if not isinstance(config, StackConfig):
        raise TypeError("config must be a StackConfig")
    checks = (
        _check("fuseki_ping", lambda: _fuseki_ping(config, transport)),
        _check("fuseki_version", lambda: _fuseki_version(config, transport)),
        _check("fuseki_graphs", lambda: _fuseki_graphs(config, transport)),
        _check("qdrant_health", lambda: _qdrant_health(config, transport)),
        _check("qdrant_version", lambda: _qdrant_version(config, transport)),
        _check("qdrant_collection", lambda: _qdrant_collection(config, transport)),
        _check("ollama_version", lambda: _ollama_version(config, transport)),
        _check("ollama_models", lambda: _ollama_models(config, transport)),
    )
    return PreflightReport(checks=checks)
