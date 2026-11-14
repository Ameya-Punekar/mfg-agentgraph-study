"""Immutable configuration and bounded canonical snapshots for Fuseki PROV data."""

from __future__ import annotations

import hashlib
import http.client
import math
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Any, Final, cast
from urllib.parse import quote, urlsplit

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from mfg_agentgraph.rdf_action_mapper import MFG

_MAX_ENDPOINT_BYTES: Final = 2048
_MAX_GRAPH_BYTES: Final = 4096
_MAX_URI_BYTES: Final = 4096
_MAX_LITERAL_BYTES: Final = 16384
_MAX_TERM_METADATA_BYTES: Final = 4096
_MAX_TRIPLES: Final = 256
_MAX_SUBJECTS: Final = 128
# Conforming Graph set semantics do not emit duplicates. This only bounds hostile
# or nonconforming stores and leaves the distinct-triple contract unchanged.
_MAX_RAW_EMISSIONS: Final = 512
_MAX_BODY_BYTES: Final = 1_048_576
_FORBIDDEN_IRI_CHARACTERS: Final = frozenset('<>"{}|^`\\')
_ENDPOINT_RE: Final = re.compile(r"^http://(127\.0\.0\.1|\[::1\]):([1-9][0-9]{0,4})(/[^?#]*)$")
_SCHEME_RE: Final = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_HEADER_TOKEN_CHARS: Final = frozenset(
    "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)
_GRAPH_ITERATION_END: Final = object()
_GRAPH_ITERATION_FAILURE: Final = object()


@dataclass(frozen=True, slots=True)
class FusekiProvenanceStoreConfig:
    """Validated, immutable local Fuseki connection configuration."""

    update_endpoint: str
    query_endpoint: str
    provenance_graph_base: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        update = _validate_endpoint(self.update_endpoint, "update_endpoint")
        query = _validate_endpoint(self.query_endpoint, "query_endpoint")
        update_parts = urlsplit(update)
        query_parts = urlsplit(query)
        if update_parts.netloc != query_parts.netloc:
            raise ValueError("endpoints must share an authority")
        if update_parts.path == query_parts.path:
            raise ValueError("endpoints must have distinct paths")
        graph_base = _validate_iri(
            self.provenance_graph_base, "provenance_graph_base", _MAX_GRAPH_BYTES
        )
        timeout = _validate_timeout(self.timeout_seconds)
        object.__setattr__(self, "update_endpoint", update)
        object.__setattr__(self, "query_endpoint", query)
        object.__setattr__(self, "provenance_graph_base", graph_base)
        object.__setattr__(self, "timeout_seconds", timeout)


class DispatchState(Enum):
    """Whether the wire-write boundary was crossed."""

    NOT_DISPATCHED = "NOT_DISPATCHED"
    DISPATCHED_UNKNOWN = "DISPATCHED_UNKNOWN"


class _TransportPhase(Enum):
    FACTORY = "factory"
    CONNECT = "connect"
    REQUEST = "request"
    DISPATCH = "dispatch"
    RESPONSE = "response"
    HEADERS = "headers"
    BODY = "body"
    TIMEOUT = "timeout"


_PHASE_MESSAGES: Final = {
    _TransportPhase.FACTORY: "Fuseki transport factory failed",
    _TransportPhase.CONNECT: "Fuseki transport connection failed",
    _TransportPhase.REQUEST: "Fuseki transport request preparation failed",
    _TransportPhase.DISPATCH: "Fuseki transport dispatch failed",
    _TransportPhase.RESPONSE: "Fuseki transport response failed",
    _TransportPhase.HEADERS: "Fuseki transport response headers invalid",
    _TransportPhase.BODY: "Fuseki transport response body invalid",
    _TransportPhase.TIMEOUT: "Fuseki transport deadline failed",
}


class FusekiProvenanceTransportError(Exception):
    """Sanitized, phase-labelled transport failure."""

    def __init__(self, phase: _TransportPhase, state: DispatchState) -> None:
        if type(phase) is not _TransportPhase or type(state) is not DispatchState:
            raise TypeError("phase and state must be exact internal enums")
        super().__init__(_PHASE_MESSAGES[phase])
        object.__setattr__(self, "_phase", phase)
        object.__setattr__(self, "_state", state)

    @property
    def phase(self) -> _TransportPhase:
        return cast(_TransportPhase, object.__getattribute__(self, "_phase"))

    @property
    def state(self) -> DispatchState:
        return cast(DispatchState, object.__getattribute__(self, "_state"))


@dataclass(frozen=True, slots=True)
class _PreparedUpdate:
    canonical_graph: bytes
    graph_iri: str
    update_body: bytes
    request_path: str
    authority: str
    host: str
    port: int
    request_line: bytes
    header_bytes: bytes
    wire_bytes: bytes

    def __post_init__(self) -> None:
        _validate_prepared_field_types(self)


@dataclass(frozen=True, slots=True)
class _PreparedQuery:
    expected_graph: bytes
    graph_iri: str
    query_body: bytes
    request_path: str
    authority: str
    host: str
    port: int
    request_line: bytes
    header_bytes: bytes
    wire_bytes: bytes

    def __post_init__(self) -> None:
        for field, expected in (
            ("expected_graph", bytes),
            ("graph_iri", str),
            ("query_body", bytes),
            ("request_path", str),
            ("authority", str),
            ("host", str),
            ("port", int),
            ("request_line", bytes),
            ("header_bytes", bytes),
            ("wire_bytes", bytes),
        ):
            value = object.__getattribute__(self, field)
            if type(value) is not expected:
                raise TypeError(f"prepared query field {field} has an invalid exact type")


@dataclass(frozen=True, slots=True)
class FusekiProvenanceStore:
    """Prepare a bounded immutable graph and send one fail-closed update."""

    config: FusekiProvenanceStoreConfig

    def __post_init__(self) -> None:
        if type(self.config) is not FusekiProvenanceStoreConfig:
            raise TypeError("config must be a FusekiProvenanceStoreConfig")

    def _snapshot_graph(self, graph: Graph) -> tuple[tuple[tuple[str, str, str], ...], bytes]:
        if type(graph) is not Graph:
            raise TypeError("graph must be an exact Graph")
        iterator = _safe_graph_iterator(graph)
        if iterator is None:
            raise ValueError("invalid graph")
        triples: set[tuple[str, str, str]] = set()
        subjects: set[str] = set()
        trace_roots: set[str] = set()
        raw_emissions = 0
        while True:
            emission = _safe_graph_next(iterator)
            if emission is _GRAPH_ITERATION_END:
                break
            if emission is _GRAPH_ITERATION_FAILURE:
                raise ValueError("invalid graph")
            raw_emissions += 1
            if raw_emissions > _MAX_RAW_EMISSIONS:
                raise ValueError("raw graph emissions exceed bound")
            if type(emission) is not tuple or len(emission) != 3:
                raise TypeError("graph emission must be an exact 3-tuple")
            subject, predicate, object_ = cast(tuple[object, object, object], emission)
            if type(subject) is not URIRef:
                raise TypeError("subject must be an exact URIRef")
            if type(predicate) is not URIRef:
                raise TypeError("predicate must be an exact URIRef")
            if type(object_) not in (URIRef, Literal):
                raise TypeError("object must be an exact URIRef or Literal")
            subject_n3 = _validate_uri(subject, "subject")
            predicate_n3 = _validate_uri(predicate, "predicate")
            object_n3 = _validate_node(cast(URIRef | Literal, object_))
            triple = (subject_n3, predicate_n3, object_n3)
            triples.add(triple)
            subjects.add(subject_n3)
            if predicate == RDF.type and object_ == MFG.ProvenanceTrace:
                trace_roots.add(subject_n3)
            if len(triples) > _MAX_TRIPLES or len(subjects) > _MAX_SUBJECTS:
                raise ValueError("graph cardinality exceeds bounds")
        if len(trace_roots) != 1:
            raise ValueError("graph must contain exactly one ProvenanceTrace root")
        ordered = tuple(sorted(triples))
        body = (
            "".join(
                f"{subject} {predicate} {object_} .\n" for subject, predicate, object_ in ordered
            )
        ).encode()
        if len(body) > _MAX_BODY_BYTES:
            raise ValueError("canonical graph body exceeds bound")
        return ordered, body

    def _canonicalize_graph(self, graph: Graph) -> bytes:
        return self._snapshot_graph(graph)[1]

    def _prepare_update(self, graph: Graph) -> _PreparedUpdate:
        update_endpoint, _, graph_base, _ = _snapshot_config(self.config)
        triples, canonical = self._snapshot_graph(graph)
        root_n3 = next(
            subject
            for subject, predicate, obj in triples
            if predicate == "<" + str(RDF.type) + ">"
            and obj == "<" + str(MFG.ProvenanceTrace) + ">"
        )
        provenance_id = root_n3[1:-1]
        digest = hashlib.sha256(provenance_id.encode("utf-8")).hexdigest()
        graph_iri = _validate_iri(
            graph_base + ":trace:" + digest,
            "per_run_graph",
            _MAX_GRAPH_BYTES,
        )
        update = b"INSERT DATA { GRAPH <" + graph_iri.encode("utf-8") + b"> { " + canonical + b"} }"
        if len(update) > _MAX_BODY_BYTES:
            raise ValueError("update body exceeds bound")
        endpoint = urlsplit(update_endpoint)
        host = endpoint.hostname
        if type(host) is not str or endpoint.port is None:
            raise ValueError("invalid update endpoint")
        request_path = _request_path(endpoint.path)
        request_line = f"POST {request_path} HTTP/1.1\r\n".encode("ascii")
        header_bytes = (
            b"".join(
                [
                    f"Host: {endpoint.netloc}\r\n".encode("ascii"),
                    b"Content-Type: application/sparql-update; charset=utf-8\r\n",
                    b"Accept: text/plain\r\n",
                    f"Content-Length: {len(update)}\r\n".encode("ascii"),
                    b"Connection: close\r\n",
                ]
            )
            + b"\r\n"
        )
        wire_bytes = request_line + header_bytes + update
        return _PreparedUpdate(
            canonical,
            graph_iri,
            update,
            request_path,
            endpoint.netloc,
            host,
            endpoint.port,
            request_line,
            header_bytes,
            wire_bytes,
        )

    def _dispatch_prepared(
        self, prepared: _PreparedUpdate, *, deadline: float | None = None
    ) -> None:
        if type(prepared) is not _PreparedUpdate:
            raise TypeError("prepared must be an exact prepared update")
        _, _, _, timeout = _snapshot_config(self.config)
        prepared = _validate_prepared(prepared, self.config)
        deadline = time.monotonic() + timeout if deadline is None else deadline
        connection: object | None = None
        state = DispatchState.NOT_DISPATCHED
        primary: BaseException | None = None

        def fail(phase: _TransportPhase, failure: object) -> None:
            del failure
            nonlocal primary
            primary = FusekiProvenanceTransportError(phase, state)
            _raise_transport(phase, state)

        try:
            ok, result = _capture_call(
                lambda: http.client.HTTPConnection(
                    prepared.host, prepared.port, timeout=_remaining_timeout(deadline)
                )
            )
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.FACTORY,
                    result,
                )
            connection = result
            ok, result = _capture_call(lambda: _set_remaining_timeout(connection, deadline))
            if not ok:
                fail(_TransportPhase.TIMEOUT, result)
            ok, result = _capture_call(cast(Any, connection).connect)
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.CONNECT,
                    result,
                )
            conn: Any = connection
            ok, result = _capture_call(lambda: _set_remaining_timeout(connection, deadline))
            if ok:
                ok, result = _capture_call(
                    lambda: conn.putrequest(
                        "POST", prepared.request_path, skip_host=True, skip_accept_encoding=True
                    )
                )
            if ok:
                for name, value in (
                    ("Host", prepared.authority),
                    ("Content-Type", "application/sparql-update; charset=utf-8"),
                    ("Accept", "text/plain"),
                    ("Content-Length", str(len(prepared.update_body))),
                    ("Connection", "close"),
                ):
                    ok, result = _capture_call(partial(cast(Any, conn).putheader, name, value))
                    if not ok:
                        break
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.REQUEST,
                    result,
                )

            ok, result = _capture_call(
                lambda: _set_remaining_timeout(connection, deadline, require_socket=True)
            )
            if not ok:
                fail(_TransportPhase.TIMEOUT, result)
            state = DispatchState.DISPATCHED_UNKNOWN
            ok, result = _capture_call(lambda: conn.endheaders(prepared.update_body))
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.DISPATCH,
                    result,
                )

            ok, result = _capture_call(
                lambda: _set_remaining_timeout(
                    connection, deadline, require_socket=True, dispatched=True
                )
            )
            if not ok:
                fail(_TransportPhase.TIMEOUT, result)
            ok, result = _capture_call(conn.getresponse)
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.RESPONSE,
                    result,
                )
            response = cast(Any, result)
            ok, result = _capture_call(
                lambda: _set_remaining_timeout(
                    connection, deadline, require_socket=True, dispatched=True
                )
            )
            if not ok:
                fail(_TransportPhase.TIMEOUT, result)
            ok, status = _capture_call(lambda: response.status)
            if not ok:
                fail(_TransportPhase.RESPONSE, status)
            if type(status) is not int or status != 204:
                _raise_transport(_TransportPhase.RESPONSE, state)
            ok, result = _capture_call(response.getheaders)
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.RESPONSE,
                    result,
                )
            _validate_response_headers(result)
            ok, result = _capture_call(
                lambda: _set_remaining_timeout(
                    connection, deadline, require_socket=True, dispatched=True
                )
            )
            if not ok:
                fail(_TransportPhase.TIMEOUT, result)
            ok, result = _capture_call(lambda: response.read(1))
            if not ok:
                fail(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.BODY,
                    result,
                )
            if type(result) is not bytes or result != b"":
                _raise_transport(_TransportPhase.BODY, state)
        except BaseException as error:
            primary = error
            raise
        finally:
            if connection is not None:
                close_failure: BaseException | None = None
                try:
                    cast(Any, connection).close()
                except BaseException as error:
                    close_failure = error
                if close_failure is not None and primary is None:
                    if type(close_failure) is Exception or isinstance(close_failure, Exception):
                        _raise_transport(_TransportPhase.DISPATCH, state)
                    raise close_failure

    def _prepare_query(self, provenance_id: str, expected_graph: bytes) -> _PreparedQuery:
        if type(provenance_id) is not str:
            raise TypeError("provenance_id must be an exact built-in string")
        _validate_iri(provenance_id, "provenance_id", _MAX_URI_BYTES)
        _, query_endpoint, graph_base, _ = _snapshot_config(self.config)
        graph_iri = _validate_iri(
            graph_base + ":trace:" + hashlib.sha256(provenance_id.encode("utf-8")).hexdigest(),
            "per_run_graph",
            _MAX_GRAPH_BYTES,
        )
        query = ("CONSTRUCT { ?s ?p ?o } WHERE { GRAPH <" + graph_iri + "> { ?s ?p ?o } }").encode(
            "utf-8"
        )
        endpoint = urlsplit(query_endpoint)
        host = endpoint.hostname
        if type(host) is not str or type(endpoint.port) is not int:
            raise ValueError("invalid query endpoint")
        if len(query) > _MAX_BODY_BYTES:
            raise ValueError("query body exceeds bound")
        request_path = _request_path(endpoint.path)
        request_line = f"POST {request_path} HTTP/1.1\r\n".encode("ascii")
        header_bytes = (
            f"Host: {endpoint.netloc}\r\n".encode("ascii")
            + b"Content-Type: application/sparql-query; charset=utf-8\r\n"
            + b"Accept: application/n-triples\r\n"
            + f"Content-Length: {len(query)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
        )
        wire_bytes = request_line + header_bytes + query
        if len(wire_bytes) > _MAX_BODY_BYTES + 16_384:
            raise ValueError("query wire exceeds bound")
        return _PreparedQuery(
            expected_graph,
            graph_iri,
            query,
            request_path,
            endpoint.netloc,
            host,
            endpoint.port,
            request_line,
            header_bytes,
            wire_bytes,
        )

    def _dispatch_query(
        self,
        prepared: _PreparedQuery,
        deadline: float,
        expected_graph: bytes,
        *,
        state_floor: DispatchState = DispatchState.NOT_DISPATCHED,
    ) -> Graph:
        if type(prepared) is not _PreparedQuery:
            raise TypeError("prepared must be an exact prepared query")
        _validate_prepared_query(prepared, self.config)
        if type(expected_graph) is not bytes or expected_graph != prepared.expected_graph:
            raise ValueError("prepared query is not coherent")
        connection: object | None = None
        state = state_floor
        primary: BaseException | None = None
        try:
            ok, result = _capture_call(
                lambda: http.client.HTTPConnection(
                    prepared.host, prepared.port, timeout=_remaining_timeout(deadline)
                )
            )
            if not ok:
                _raise_transport(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.FACTORY,
                    state,
                )
            connection = result
            ok, result = _capture_call(lambda: _set_remaining_timeout(connection, deadline))
            if not ok:
                _raise_transport(_TransportPhase.TIMEOUT, state)
            conn: Any = connection
            ok, result = _capture_call(conn.connect)
            if not ok:
                _raise_transport(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.CONNECT,
                    state,
                )
            ok, result = _capture_call(lambda: _set_remaining_timeout(connection, deadline))
            if ok:
                ok, result = _capture_call(
                    lambda: conn.putrequest(
                        "POST", prepared.request_path, skip_host=True, skip_accept_encoding=True
                    )
                )
            if ok:
                for name, value in (
                    ("Host", prepared.authority),
                    ("Content-Type", "application/sparql-query; charset=utf-8"),
                    ("Accept", "application/n-triples"),
                    ("Content-Length", str(len(prepared.query_body))),
                    ("Connection", "close"),
                ):
                    ok, result = _capture_call(partial(conn.putheader, name, value))
                    if not ok:
                        break
            if not ok:
                _raise_transport(_TransportPhase.REQUEST, state)
            ok, result = _capture_call(
                lambda: _set_remaining_timeout(connection, deadline, require_socket=True)
            )
            if not ok:
                _raise_transport(_TransportPhase.TIMEOUT, state)
            state = DispatchState.DISPATCHED_UNKNOWN
            ok, result = _capture_call(lambda: conn.endheaders(prepared.query_body))
            if not ok:
                _raise_transport(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.DISPATCH,
                    state,
                )
            ok, result = _capture_call(
                lambda: _set_remaining_timeout(
                    connection, deadline, require_socket=True, dispatched=True
                )
            )
            if not ok:
                _raise_transport(_TransportPhase.TIMEOUT, state)
            ok, result = _capture_call(conn.getresponse)
            if not ok:
                _raise_transport(
                    _TransportPhase.TIMEOUT
                    if type(result) is TimeoutError
                    else _TransportPhase.RESPONSE,
                    state,
                )
            response = cast(Any, result)
            ok, result = _capture_call(
                lambda: _set_remaining_timeout(
                    connection, deadline, require_socket=True, dispatched=True
                )
            )
            if not ok:
                _raise_transport(_TransportPhase.TIMEOUT, state)
            ok, status = _capture_call(lambda: response.status)
            if not ok or type(status) is not int or status != 200:
                _raise_transport(_TransportPhase.RESPONSE, state)
            ok, headers = _capture_call(response.getheaders)
            if not ok:
                _raise_transport(_TransportPhase.RESPONSE, state)
            content_length = _validate_query_headers(headers)
            ok, result = _capture_call(
                lambda: _set_remaining_timeout(
                    connection, deadline, require_socket=True, dispatched=True
                )
            )
            if not ok:
                _raise_transport(_TransportPhase.TIMEOUT, state)
            ok, body = _capture_call(lambda: response.read(_MAX_BODY_BYTES + 1))
            if not ok or type(body) is not bytes or len(body) > _MAX_BODY_BYTES:
                _raise_transport(_TransportPhase.BODY, state)
            body_bytes = cast(bytes, body)
            if content_length is not None and content_length != len(body_bytes):
                _raise_transport(_TransportPhase.BODY, state)
            return _parse_query_body(body_bytes, expected_graph, self.config)
        except BaseException as error:
            primary = error
            raise
        finally:
            if connection is not None:
                try:
                    cast(Any, connection).close()
                except BaseException as error:
                    if primary is None:
                        if isinstance(error, Exception):
                            _raise_transport(_TransportPhase.DISPATCH, state)
                        raise

    def resolve(self, provenance_id: str, expected_graph: Graph) -> Graph:
        if type(provenance_id) is not str:
            raise TypeError("provenance_id must be an exact built-in string")
        _validate_iri(provenance_id, "provenance_id", _MAX_URI_BYTES)
        _, _, _, timeout = _snapshot_config(self.config)
        deadline = time.monotonic() + timeout
        canonical = self._canonicalize_graph(expected_graph)
        if _root_id_from_canonical(canonical) != provenance_id:
            raise ValueError("expected graph root does not match provenance_id")
        prepared = self._prepare_query(provenance_id, canonical)
        return self._dispatch_query(prepared, deadline, canonical)

    def persist(self, graph: Graph) -> None:
        _, _, _, timeout = _snapshot_config(self.config)
        deadline = time.monotonic() + timeout
        prepared = self._prepare_update(graph)
        self._dispatch_prepared(prepared, deadline=deadline)
        try:
            query = self._prepare_query(
                _root_id_from_canonical(prepared.canonical_graph), prepared.canonical_graph
            )
            self._dispatch_query(
                query,
                deadline,
                prepared.canonical_graph,
                state_floor=DispatchState.DISPATCHED_UNKNOWN,
            )
        except FusekiProvenanceTransportError:
            raise
        except Exception:
            _raise_transport(_TransportPhase.REQUEST, DispatchState.DISPATCHED_UNKNOWN)
        except BaseException:
            raise


def _snapshot_config(
    config: FusekiProvenanceStoreConfig,
) -> tuple[str, str, str, float]:
    if type(config) is not FusekiProvenanceStoreConfig:
        raise TypeError("config must be an exact FusekiProvenanceStoreConfig")
    update_value = object.__getattribute__(config, "update_endpoint")
    query_value = object.__getattribute__(config, "query_endpoint")
    graph_value = object.__getattribute__(config, "provenance_graph_base")
    timeout_value = object.__getattribute__(config, "timeout_seconds")
    update = _validate_endpoint(update_value, "update_endpoint")
    query = _validate_endpoint(query_value, "query_endpoint")
    if urlsplit(update).netloc != urlsplit(query).netloc:
        raise ValueError("endpoints must share an authority")
    if urlsplit(update).path == urlsplit(query).path:
        raise ValueError("endpoints must have distinct paths")
    graph_base = _validate_iri(graph_value, "provenance_graph_base", _MAX_GRAPH_BYTES)
    timeout = _validate_timeout(timeout_value)
    return update, query, graph_base, timeout


def _validate_prepared_field_types(prepared: _PreparedUpdate) -> None:
    fields = (
        "canonical_graph",
        "graph_iri",
        "update_body",
        "request_path",
        "authority",
        "host",
        "port",
        "request_line",
        "header_bytes",
        "wire_bytes",
    )
    for field in fields:
        value = object.__getattribute__(prepared, field)
        expected_type = (
            int
            if field == "port"
            else (
                bytes
                if field
                in {"canonical_graph", "update_body", "request_line", "header_bytes", "wire_bytes"}
                else str
            )
        )
        if type(value) is not expected_type or (field == "port" and type(value) is bool):
            raise TypeError(f"prepared.{field} has an invalid exact type")


def _validate_prepared(
    prepared: _PreparedUpdate, config: FusekiProvenanceStoreConfig
) -> _PreparedUpdate:
    _validate_prepared_field_types(prepared)

    update, _, graph_base, _ = _snapshot_config(config)
    endpoint = urlsplit(update)
    host = endpoint.hostname
    port = endpoint.port
    if type(host) is not str or type(port) is not int:
        raise ValueError("invalid update endpoint")
    canonical = prepared.canonical_graph
    if not canonical or len(canonical) > _MAX_BODY_BYTES:
        raise ValueError("invalid prepared canonical graph")
    _revalidate_canonical_graph(canonical, config)
    root_n3: bytes | None = None
    type_n3 = b"<" + str(RDF.type).encode("ascii") + b">"
    trace_n3 = b"<" + str(MFG.ProvenanceTrace).encode("ascii") + b">"
    for line in canonical.splitlines():
        parts = line.split(b" ", 2)
        if len(parts) == 3 and parts[1] == type_n3 and parts[2] == trace_n3 + b" .":
            if root_n3 is not None:
                raise ValueError("invalid prepared canonical graph")
            root_n3 = parts[0]
    if root_n3 is None or not root_n3.startswith(b"<") or not root_n3.endswith(b">"):
        raise ValueError("invalid prepared canonical graph")
    try:
        provenance_id = root_n3[1:-1].decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise ValueError("invalid prepared canonical graph") from None
    _validate_iri(provenance_id, "provenance_id", _MAX_URI_BYTES)
    digest = hashlib.sha256(provenance_id.encode("utf-8")).hexdigest()
    graph_iri = _validate_iri(graph_base + ":trace:" + digest, "per_run_graph", _MAX_GRAPH_BYTES)
    expected_update = (
        b"INSERT DATA { GRAPH <" + graph_iri.encode("utf-8") + b"> { " + canonical + b"} }"
    )
    if len(expected_update) > _MAX_BODY_BYTES:
        raise ValueError("update body exceeds bound")
    request_path = _request_path(endpoint.path)
    expected_request = f"POST {request_path} HTTP/1.1\r\n".encode("ascii")
    expected_headers = (
        f"Host: {endpoint.netloc}\r\n".encode("ascii")
        + b"Content-Type: application/sparql-update; charset=utf-8\r\n"
        + b"Accept: text/plain\r\n"
        + f"Content-Length: {len(expected_update)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
    )
    expected_wire = expected_request + expected_headers + expected_update
    if (
        prepared.graph_iri != graph_iri
        or prepared.update_body != expected_update
        or prepared.request_path != request_path
        or prepared.authority != endpoint.netloc
        or prepared.host != host
        or prepared.port != port
        or prepared.request_line != expected_request
        or prepared.header_bytes != expected_headers
        or prepared.wire_bytes != expected_wire
    ):
        raise ValueError("prepared update is not coherent")
    return prepared


def _validate_prepared_query(prepared: _PreparedQuery, config: FusekiProvenanceStoreConfig) -> None:
    fields = (
        "expected_graph",
        "graph_iri",
        "query_body",
        "request_path",
        "authority",
        "host",
        "port",
        "request_line",
        "header_bytes",
        "wire_bytes",
    )
    for field in fields:
        value = object.__getattribute__(prepared, field)
        expected = (
            int
            if field == "port"
            else (
                bytes
                if field
                in {"expected_graph", "query_body", "request_line", "header_bytes", "wire_bytes"}
                else str
            )
        )
        if type(value) is not expected:
            raise TypeError(f"prepared query field {field} has an invalid exact type")
    _, query_endpoint, graph_base, _ = _snapshot_config(config)
    endpoint = urlsplit(query_endpoint)
    host = endpoint.hostname
    if type(host) is not str or type(endpoint.port) is not int:
        raise ValueError("invalid query endpoint")
    if not prepared.expected_graph or len(prepared.expected_graph) > _MAX_BODY_BYTES:
        raise ValueError("invalid prepared expected graph")
    _revalidate_canonical_graph(prepared.expected_graph, config)
    provenance_id = _root_id_from_canonical(prepared.expected_graph)
    graph_iri = _validate_iri(
        graph_base + ":trace:" + hashlib.sha256(provenance_id.encode("utf-8")).hexdigest(),
        "per_run_graph",
        _MAX_GRAPH_BYTES,
    )
    query_body = ("CONSTRUCT { ?s ?p ?o } WHERE { GRAPH <" + graph_iri + "> { ?s ?p ?o } }").encode(
        "utf-8"
    )
    request_path = _request_path(endpoint.path)
    request_line = f"POST {request_path} HTTP/1.1\r\n".encode("ascii")
    header_bytes = (
        f"Host: {endpoint.netloc}\r\n".encode("ascii")
        + b"Content-Type: application/sparql-query; charset=utf-8\r\n"
        + b"Accept: application/n-triples\r\n"
        + f"Content-Length: {len(query_body)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
    )
    expected_wire = request_line + header_bytes + query_body
    if (
        prepared.graph_iri != graph_iri
        or prepared.query_body != query_body
        or prepared.request_path != request_path
        or prepared.authority != endpoint.netloc
        or prepared.host != host
        or prepared.port != endpoint.port
        or prepared.request_line != request_line
        or prepared.header_bytes != header_bytes
        or prepared.wire_bytes != expected_wire
    ):
        raise ValueError("prepared query is not coherent")


def _revalidate_canonical_graph(canonical: bytes, config: FusekiProvenanceStoreConfig) -> None:
    graph = Graph()
    parse_failed = False
    try:
        graph.parse(data=canonical.decode("utf-8"), format="nt")
    except Exception:
        parse_failed = True
    if parse_failed:
        raise ValueError("invalid prepared canonical graph") from None

    validation_failed = False
    regenerated = b""
    try:
        _, regenerated = FusekiProvenanceStore(config)._snapshot_graph(graph)
    except Exception:
        validation_failed = True
    if validation_failed or regenerated != canonical:
        raise ValueError("invalid prepared canonical graph")


def _raise_transport(phase: _TransportPhase, state: DispatchState) -> None:
    error = FusekiProvenanceTransportError(phase, state)
    error.__cause__ = None
    error.__context__ = None
    raise error from None


def _capture_call(function: Callable[[], object]) -> tuple[bool, object]:
    try:
        return True, function()
    except Exception as error:
        return False, error


def _set_remaining_timeout(
    connection: object,
    deadline: float,
    *,
    require_socket: bool = False,
    dispatched: bool = False,
) -> None:
    remaining = deadline - time.monotonic()
    failure_state = DispatchState.DISPATCHED_UNKNOWN if dispatched else DispatchState.NOT_DISPATCHED
    if remaining <= 0:
        _raise_transport(_TransportPhase.TIMEOUT, failure_state)
    socket = getattr(connection, "sock", None)
    if socket is None and require_socket and not dispatched:
        _raise_transport(_TransportPhase.TIMEOUT, failure_state)
    if socket is not None:
        setter = cast(Any, getattr(socket, "settimeout", None))
        if not callable(setter):
            _raise_transport(_TransportPhase.TIMEOUT, failure_state)
        setter_failed = False
        try:
            setter(remaining)
        except Exception:
            setter_failed = True
        if setter_failed:
            _raise_transport(_TransportPhase.TIMEOUT, failure_state)
        return
    timeout_failed = False
    try:
        cast(Any, connection).timeout = remaining
    except Exception:
        timeout_failed = True
    if timeout_failed:
        _raise_transport(_TransportPhase.TIMEOUT, failure_state)


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


def _validate_response_headers(headers: object) -> None:
    if type(headers) is not list or len(headers) > 32:
        _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
    total = 2  # The terminating empty line is part of the wire budget.
    content_lengths = 0
    for header in cast(list[object], headers):
        if type(header) is not tuple or len(header) != 2:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        name, value = cast(tuple[object, object], header)
        if type(name) is not str or type(value) is not str:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        name_text = cast(str, name)
        value_text = cast(str, value)
        if (
            not name_text
            or any(character not in _HEADER_TOKEN_CHARS for character in name_text)
            or any(
                ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value_text
            )
        ):
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        encoding_failed = False
        wire_length = 0
        try:
            wire_length = (
                len(name_text.encode("iso-8859-1")) + 2 + len(value_text.encode("iso-8859-1")) + 2
            )
        except UnicodeEncodeError:
            encoding_failed = True
        if encoding_failed:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        total += wire_length
        if total > 16_384:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        lowered = name_text.lower()
        if lowered == "content-length":
            content_lengths += 1
            if value_text != "0":
                _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        elif lowered in {"transfer-encoding", "content-encoding"}:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
    if content_lengths > 1:
        _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)


def _root_id_from_canonical(canonical: bytes) -> str:
    type_n3 = b"<" + str(RDF.type).encode("ascii") + b">"
    trace_n3 = b"<" + str(MFG.ProvenanceTrace).encode("ascii") + b">"
    roots: list[bytes] = []
    for line in canonical.split(b"\n"):
        if not line:
            continue
        parts = line.split(b" ", 2)
        if len(parts) == 3 and parts[1] == type_n3 and parts[2] == trace_n3 + b" .":
            roots.append(parts[0])
    if len(roots) != 1 or not roots[0].startswith(b"<") or not roots[0].endswith(b">"):
        raise ValueError("graph must contain exactly one ProvenanceTrace root")
    try:
        value = roots[0][1:-1].decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("invalid provenance root") from None
    _validate_iri(value, "provenance_id", _MAX_URI_BYTES)
    return value


def _validate_query_headers(headers: object) -> int | None:
    if type(headers) is not list or len(headers) > 32:
        _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
    total = 2
    content_type: str | None = None
    content_length: int | None = None
    chunked = False
    for header in cast(list[object], headers):
        if type(header) is not tuple or len(header) != 2:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        name, value = cast(tuple[object, object], header)
        if type(name) is not str or type(value) is not str:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        name_text = cast(str, name)
        value_text = cast(str, value)
        if not name_text or any(ch not in _HEADER_TOKEN_CHARS for ch in name_text):
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        if any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in value_text):
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        encoding_failed = False
        try:
            encoded_length = (
                len(name_text.encode("iso-8859-1")) + 2 + len(value_text.encode("iso-8859-1")) + 2
            )
        except UnicodeEncodeError:
            encoding_failed = True
            encoded_length = 0
        if encoding_failed:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        total += encoded_length
        if total > 16_384:
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        lowered = name_text.lower()
        if lowered == "content-encoding":
            _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
        if lowered == "transfer-encoding":
            # http.client decodes chunked bodies, and the bounded read below
            # caps the decoded size. Any other transfer coding is unsupported.
            if chunked or value_text.strip().lower() != "chunked":
                _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
            chunked = True
        elif lowered == "content-type":
            if content_type is not None or value_text not in {
                "application/n-triples",
                "application/n-triples; charset=utf-8",
            }:
                _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
            content_type = value_text
        elif lowered == "content-length":
            if (
                content_length is not None
                or not value_text.isascii()
                or not value_text.isdecimal()
                or len(value_text) > 7
            ):
                _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
            parsed_length = int(value_text)
            if str(parsed_length) != value_text or parsed_length > _MAX_BODY_BYTES:
                _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
            content_length = parsed_length
    if content_type is None:
        _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
    if chunked and content_length is not None:
        _raise_transport(_TransportPhase.HEADERS, DispatchState.DISPATCHED_UNKNOWN)
    return content_length


def _scan_nt_line(line: bytes) -> None:
    if type(line) is not bytes or len(line) > 32_768 or not line.endswith(b"\n"):
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    decode_failed = False
    text = ""
    try:
        text = line.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        decode_failed = True
    if decode_failed:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    if (
        "\r" in text
        or "\ufeff" in text
        or any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in text[:-1])
    ):
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    if text.startswith("#") or not text.endswith(" .\n"):
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    content = text[:-3]
    terms: list[str] = []
    index = 0
    for _ in range(2):
        if index >= len(content) or content[index] != "<":
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        end = content.find(">", index + 1)
        if end < 0:
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        iri = content[index + 1 : end]
        if not _valid_scanned_iri(iri):
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        terms.append(content[index : end + 1])
        index = end + 1
        if index >= len(content) or content[index] != " ":
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        index += 1
    if index >= len(content):
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    if content[index] == "<":
        end = content.find(">", index + 1)
        if end < 0:
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        iri = content[index + 1 : end]
        if not _valid_scanned_iri(iri):
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        index = end + 1
    elif content[index] == '"':
        index += 1
        closed = False
        while index < len(content):
            ch = content[index]
            if ch == '"':
                closed = True
                index += 1
                break
            if ch == "\\":
                index += 1
                if index >= len(content) or content[index] not in '"\\btnfruU':
                    _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
                if content[index] in "uU":
                    count = 4 if content[index] == "u" else 8
                    digits = content[index + 1 : index + 1 + count]
                    if len(digits) != count or any(
                        c not in "0123456789abcdefABCDEF" for c in digits
                    ):
                        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
                    value = int(digits, 16)
                    if value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
                        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
                    index += count
            index += 1
        if not closed:
            _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
        if index < len(content) and content[index] == "@":
            match = re.match(r"@[A-Za-z]+(?:-[A-Za-z0-9]+)*", content[index:])
            if match is None:
                _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
            assert match is not None
            index += len(match.group(0))
        elif content[index : index + 2] == "^^":
            end = content.find(">", index + 2)
            if end < 0 or content[index + 2] != "<":
                _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
            datatype = content[index + 3 : end]
            if not _SCHEME_RE.match(datatype) or any(
                ch in _FORBIDDEN_IRI_CHARACTERS or ch.isspace() for ch in datatype
            ):
                _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
            index = end + 1
    else:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    if len(terms) + 1 != 3 or index != len(content) or len(terms) > 2:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)


def _valid_scanned_iri(value: str) -> bool:
    return bool(
        _SCHEME_RE.match(value)
        and "\\" not in value
        and not any(
            character in _FORBIDDEN_IRI_CHARACTERS
            or character.isspace()
            or ord(character) < 0x20
            or 0x7F <= ord(character) <= 0x9F
            for character in value
        )
    )


def _parse_query_body(
    body: bytes, expected_graph: bytes, config: FusekiProvenanceStoreConfig
) -> Graph:
    if (
        type(body) is not bytes
        or not body
        or body.startswith(b"\xef\xbb\xbf")
        or len(body) > _MAX_BODY_BYTES
    ):
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    decode_failed = False
    try:
        body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        decode_failed = True
    if decode_failed:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    lines = body.splitlines(keepends=True)
    if not 1 <= len(lines) <= 256 or any(not line for line in lines):
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    for line in lines:
        _scan_nt_line(line)
    if type(expected_graph) is not bytes:
        raise TypeError("expected graph must be canonical bytes")
    graph = Graph()
    parse_failed = False
    try:
        graph.parse(data=body.decode("utf-8"), format="nt")
    except Exception:
        parse_failed = True
    if parse_failed:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    snapshot_failed = False
    regenerated = b""
    try:
        _, regenerated = FusekiProvenanceStore(config)._snapshot_graph(graph)
    except Exception:
        snapshot_failed = True
    if snapshot_failed:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    if regenerated != expected_graph:
        _raise_transport(_TransportPhase.BODY, DispatchState.DISPATCHED_UNKNOWN)
    return graph


def _request_path(path: str) -> str:
    return quote(path, safe="/%:@!$&'()*+,;=-._~")


def _validate_endpoint(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact built-in string")
    if not value or any(
        character.isspace() or ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
        for character in value
    ):
        raise ValueError(f"invalid {field}")
    _validate_safe_text(value, field)
    if value.strip() != value or len(value.encode()) > _MAX_ENDPOINT_BYTES:
        raise ValueError(f"invalid {field}")
    match = _ENDPOINT_RE.fullmatch(value)
    if match is None or int(match.group(2)) > 65535:
        raise ValueError(f"invalid {field}")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"invalid {field}")
    if f"http://{parsed.netloc}{parsed.path}" != value:
        raise ValueError(f"invalid {field}")
    return value


def _safe_graph_iterator(graph: Graph) -> Iterator[object] | None:
    try:
        return iter(graph)
    except Exception:
        return None


def _safe_graph_next(iterator: Iterator[object]) -> object:
    try:
        return next(iterator)
    except StopIteration:
        return _GRAPH_ITERATION_END
    except Exception:
        return _GRAPH_ITERATION_FAILURE


def _validate_iri(value: object, field: str, limit: int) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact built-in string")
    _validate_safe_text(value, field)
    if not value or len(value.encode()) > limit or not _SCHEME_RE.match(value):
        raise ValueError(f"invalid {field}")
    return value


def _validate_safe_text(value: str, field: str) -> None:
    for character in value:
        codepoint = ord(character)
        if (
            character.isspace()
            or codepoint > 0x10FFFF
            or 0xD800 <= codepoint <= 0xDFFF
            or codepoint < 0x20
            or 0x7F <= codepoint <= 0x9F
        ):
            raise ValueError(f"invalid Unicode in {field}")
        if character in _FORBIDDEN_IRI_CHARACTERS:
            raise ValueError(f"unsafe IRI in {field}")


def _validate_uri(value: URIRef, field: str) -> str:
    text = str(value)
    _validate_safe_text(text, field)
    if len(text.encode()) > _MAX_URI_BYTES:
        raise ValueError(f"{field} exceeds bound")
    if not _SCHEME_RE.match(text):
        raise ValueError(f"{field} must be absolute")
    serialization_failed = False
    n3 = ""
    try:
        n3 = value.n3()
    except Exception:
        serialization_failed = True
    if serialization_failed:
        raise ValueError(f"invalid {field}")
    if n3 != f"<{text}>" or n3[1:-1] != text:
        raise ValueError(f"invalid {field}")
    return n3


def _validate_node(value: URIRef | Literal) -> str:
    if type(value) is URIRef:
        return _validate_uri(value, "URIRef")
    value = cast(Literal, value)
    lexical = str(value)
    _validate_literal_text(lexical, "literal")
    if len(lexical.encode()) > _MAX_LITERAL_BYTES:
        raise ValueError("literal lexical form exceeds bound")
    language = value.language
    datatype = value.datatype
    if language is not None:
        if type(language) is not str:
            raise ValueError("literal language exceeds bound")
        _validate_safe_text(language, "literal language")
        if len(language.encode()) > _MAX_TERM_METADATA_BYTES:
            raise ValueError("literal language exceeds bound")
    if datatype is not None:
        if type(datatype) is not URIRef:
            raise TypeError("literal datatype must be URIRef")
        _validate_uri(datatype, "literal datatype")
    serialization_failed = False
    n3 = ""
    try:
        n3 = value.n3()
    except Exception:
        serialization_failed = True
    if serialization_failed:
        raise ValueError("invalid literal")
    if not n3:
        raise ValueError("invalid literal")
    return n3


def _validate_timeout(value: object) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise TypeError("timeout_seconds must be a finite real number")
    if type(value) is int and not 0 < value <= 30:
        raise ValueError("timeout_seconds must be in (0, 30]")
    timeout = float(cast(int | float, value))
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("timeout_seconds must be in (0, 30]")
    return timeout


def _validate_literal_text(value: str, field: str) -> None:
    for character in value:
        codepoint = ord(character)
        if (
            codepoint > 0x10FFFF
            or 0xD800 <= codepoint <= 0xDFFF
            or codepoint < 0x20
            or 0x7F <= codepoint <= 0x9F
        ):
            raise ValueError(f"invalid Unicode in {field}")
