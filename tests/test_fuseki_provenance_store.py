"""TDD contract tests for the bounded Fuseki provenance snapshot."""

from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from math import inf, nan
from traceback import format_exc
from typing import Any, cast

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF
from rdflib.store import Store

import mfg_agentgraph.fuseki_provenance_store as fuseki_store
from mfg_agentgraph.fuseki_provenance_store import (
    FusekiProvenanceStore,
    FusekiProvenanceStoreConfig,
)
from mfg_agentgraph.rdf_action_mapper import MFG

UPDATE = "http://127.0.0.1:3030/update"
QUERY = "http://127.0.0.1:3030/query"
BASE = "https://example.test/provenance"


def make_graph(*, count: int = 1) -> Graph:
    graph = Graph()
    root = URIRef("https://example.test/trace/1")
    graph.add(
        (root, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), MFG.ProvenanceTrace)
    )
    for index in range(count - 1):
        graph.add((root, URIRef(f"https://example.test/p/{index}"), Literal(index)))
    return graph


def make_store() -> FusekiProvenanceStore:
    return FusekiProvenanceStore(FusekiProvenanceStoreConfig(UPDATE, QUERY, BASE))


def test_config_is_frozen_and_replace_revalidates() -> None:
    config = FusekiProvenanceStoreConfig(UPDATE, QUERY, BASE)
    assert config.timeout_seconds == 5.0
    with pytest.raises(FrozenInstanceError):
        config.timeout_seconds = 2.0  # type: ignore[misc]
    assert replace(config, timeout_seconds=30.0).timeout_seconds == 30.0
    with pytest.raises(ValueError):
        replace(config, query_endpoint=UPDATE)


@pytest.mark.parametrize(
    "update, query",
    [
        ("http://localhost:3030/u", QUERY),
        ("https://127.0.0.1:3030/u", QUERY),
        ("http://127.0.0.2:3030/u", QUERY),
        ("http://127.0.0.1/u", "http://127.0.0.1:3030/q"),
        ("http://127.0.0.1:3030/u?", QUERY),
        ("http://127.0.0.1:3030/u", "http://127.0.0.1:3030/q#x"),
        ("http://user@127.0.0.1:3030/u", QUERY),
        ("http://[::1]:3030/u", QUERY),
    ],
)
def test_config_rejects_noncanonical_endpoints(update: str, query: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        FusekiProvenanceStoreConfig(update, query, BASE)


def test_ipv6_loopback_and_authority_are_canonical() -> None:
    config = FusekiProvenanceStoreConfig(
        "http://[::1]:3030/update", "http://[::1]:3030/query", BASE
    )
    assert config.update_endpoint == "http://[::1]:3030/update"


@pytest.mark.parametrize(
    ("update", "query", "base"),
    [
        ("http://127.0.0.1:3030/u\ud800", QUERY, BASE),
        (UPDATE, "http://127.0.0.1:3030/q\ud800", BASE),
        (UPDATE, QUERY, "https://example.test/provenance\ud800"),
    ],
)
def test_config_rejects_surrogates_without_retaining_input(
    update: str, query: str, base: str
) -> None:
    with pytest.raises(ValueError) as exc_info:
        FusekiProvenanceStoreConfig(update, query, base)

    error = exc_info.value
    assert type(error) is ValueError
    assert not hasattr(error, "object")
    assert "\\ud800" not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_config_rejects_huge_integer_timeout_without_conversion_leak() -> None:
    with pytest.raises(ValueError, match=r"timeout_seconds must be in \(0, 30\]") as exc_info:
        FusekiProvenanceStoreConfig(UPDATE, QUERY, BASE, 10**10_000)

    assert type(exc_info.value) is ValueError
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    "object_",
    [
        URIRef("https://example.test/object\ud800"),
        Literal("lexical\ud800"),
        Literal("lexical", datatype=URIRef("https://example.test/type\ud800")),
    ],
)
def test_graph_terms_reject_surrogates_without_retaining_input(object_: URIRef | Literal) -> None:
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/subject"),
            URIRef("https://example.test/predicate"),
            object_,
        )
    )

    with pytest.raises(ValueError) as exc_info:
        make_store()._snapshot_graph(graph)

    error = exc_info.value
    assert type(error) is ValueError
    assert not hasattr(error, "object")
    assert "\\ud800" not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_drifted_literal_language_rejects_surrogate_without_retaining_input() -> None:
    literal = Literal("lexical", lang="en")
    object.__setattr__(literal, "_language", "x-\ud800")
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/subject"),
            URIRef("https://example.test/predicate"),
            literal,
        )
    )

    with pytest.raises(ValueError) as exc_info:
        make_store()._snapshot_graph(graph)

    assert type(exc_info.value) is ValueError
    assert not hasattr(exc_info.value, "object")
    assert "\\ud800" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_graph_predicate_rejects_surrogate_without_retaining_input() -> None:
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/subject"),
            URIRef("https://example.test/predicate\ud800"),
            Literal("value"),
        )
    )

    with pytest.raises(ValueError) as exc_info:
        make_store()._snapshot_graph(graph)

    assert type(exc_info.value) is ValueError
    assert not hasattr(exc_info.value, "object")
    assert "\\ud800" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize("field", ["update_endpoint", "query_endpoint"])
@pytest.mark.parametrize("whitespace", [" ", "\t", "\n", "\r", "\u00a0", "\u2003"])
def test_config_rejects_internal_endpoint_whitespace(
    field: str, whitespace: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    endpoints = {"update_endpoint": UPDATE, "query_endpoint": QUERY}
    path = "/update" if field == "update_endpoint" else "/query"
    endpoint = endpoints[field].replace(path, f"/{whitespace}{path[1:]}", 1)
    values: tuple[str, str] = (
        (endpoint, QUERY) if field == "update_endpoint" else (UPDATE, endpoint)
    )

    real_urlsplit = cast(Any, fuseki_store).urlsplit

    def fail_if_urlsplit_is_called(value: str) -> object:
        if any(character.isspace() for character in value):
            raise AssertionError(f"urlsplit called for {value!r}")
        return real_urlsplit(value)

    monkeypatch.setattr(fuseki_store, "urlsplit", fail_if_urlsplit_is_called)
    with pytest.raises(ValueError, match=f"invalid {field}"):
        FusekiProvenanceStoreConfig(*values, BASE)


@pytest.mark.parametrize("field", ["update_endpoint", "query_endpoint"])
@pytest.mark.parametrize("control", ["\x00", "\x01", "\x1f", "\x7f", "\x85", "\x9f"])
def test_config_rejects_endpoint_controls_before_url_parsing(
    field: str, control: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = "/update" if field == "update_endpoint" else "/query"
    original = UPDATE if field == "update_endpoint" else QUERY
    endpoint = original.replace(path, f"/{control}{path[1:]}", 1)
    values = (endpoint, QUERY) if field == "update_endpoint" else (UPDATE, endpoint)

    real_urlsplit = cast(Any, fuseki_store).urlsplit

    def fail_if_urlsplit_is_called(value: str) -> object:
        if any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value):
            raise AssertionError("urlsplit called for endpoint containing a control scalar")
        return real_urlsplit(value)

    monkeypatch.setattr(fuseki_store, "urlsplit", fail_if_urlsplit_is_called)
    with pytest.raises(ValueError, match=f"invalid {field}"):
        FusekiProvenanceStoreConfig(*values, BASE)


@pytest.mark.parametrize(
    "value", ["", " update", "update ", "http://127.0.0.1:0/u", "http://127.0.0.1:65536/u"]
)
def test_config_rejects_invalid_values(value: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        FusekiProvenanceStoreConfig(value, QUERY, BASE)


@pytest.mark.parametrize("timeout", [True, False, 0, 30.0001, inf, nan, "5"])
def test_config_rejects_invalid_timeout(timeout: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        FusekiProvenanceStoreConfig(UPDATE, QUERY, BASE, cast(float, timeout))


def test_config_requires_exact_builtin_strings() -> None:
    class StringSubclass(str):
        pass

    with pytest.raises(TypeError):
        FusekiProvenanceStoreConfig(StringSubclass(UPDATE), QUERY, BASE)


def test_canonicalization_is_deterministic_and_escaped() -> None:
    graph = make_graph()
    root = URIRef("https://example.test/trace/1")
    graph.add((root, URIRef("https://example.test/label"), Literal(r'line\\"quote')))
    first = make_store()._canonicalize_graph(graph)
    second = make_store()._canonicalize_graph(graph)
    assert first == second
    assert b'\\"' in first


def test_snapshot_requires_exact_graph_and_node_types() -> None:
    class GraphSubclass(Graph):
        pass

    class URIRefSubclass(URIRef):
        pass

    class LiteralSubclass(Literal):
        pass

    store = make_store()
    for graph in [GraphSubclass(), "not a graph"]:
        with pytest.raises((TypeError, ValueError)):
            store._canonicalize_graph(graph)  # type: ignore[arg-type]
    graph = make_graph()
    graph.add(
        (URIRefSubclass("https://example.test/x"), URIRef("https://example.test/p"), Literal(1))
    )
    with pytest.raises(TypeError):
        store._canonicalize_graph(graph)
    graph = make_graph()
    graph.add(
        (URIRef("https://example.test/x"), URIRef("https://example.test/p"), LiteralSubclass("x"))
    )
    with pytest.raises(TypeError):
        store._canonicalize_graph(graph)


def test_snapshot_rejects_bnodes_and_trace_root_cardinality() -> None:
    store = make_store()
    graph = make_graph()
    graph.add((BNode(), URIRef("https://example.test/p"), Literal("x")))
    with pytest.raises(TypeError):
        store._canonicalize_graph(graph)
    empty = Graph()
    with pytest.raises(ValueError):
        store._canonicalize_graph(empty)
    multiple = make_graph()
    multiple.add(
        (
            URIRef("https://example.test/trace/2"),
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            MFG.ProvenanceTrace,
        )
    )
    with pytest.raises(ValueError):
        store._canonicalize_graph(multiple)


def test_snapshot_enforces_triple_subject_and_body_limits() -> None:
    store = make_store()
    graph = make_graph()
    root = URIRef("https://example.test/trace/1")
    for index in range(255):
        graph.add((root, URIRef(f"https://example.test/p/{index}"), Literal(index)))
    assert len(store._canonicalize_graph(graph)) > 0
    graph.add((root, URIRef("https://example.test/overflow"), Literal("x")))
    with pytest.raises(ValueError):
        store._canonicalize_graph(graph)

    too_many_subjects = make_graph()
    for index in range(128):
        too_many_subjects.add(
            (
                URIRef(f"https://example.test/s/{index}"),
                URIRef("https://example.test/p"),
                Literal(index),
            )
        )
    with pytest.raises(ValueError):
        store._canonicalize_graph(too_many_subjects)


def test_persist_validates_before_placeholder_io() -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        make_store().persist(make_graph())
    with pytest.raises(ValueError):
        make_store().persist(Graph())


@pytest.mark.parametrize(
    "base",
    ["", "relative", "https://example.test/" + "x" * 4096, "https://example.test/\n"],
)
def test_graph_base_is_bounded_and_safe(base: str) -> None:
    with pytest.raises(ValueError):
        FusekiProvenanceStoreConfig(UPDATE, QUERY, base)


def test_endpoint_and_authority_boundaries() -> None:
    long_path = "/" + "x" * 2010
    config = FusekiProvenanceStoreConfig(
        "http://127.0.0.1:1" + long_path,
        "http://127.0.0.1:1/query",
        BASE,
    )
    assert config.timeout_seconds == 5.0
    with pytest.raises(ValueError):
        FusekiProvenanceStoreConfig(
            "http://127.0.0.1:1/update",
            "http://127.0.0.1:2/query",
            BASE,
        )


@pytest.mark.parametrize(
    "node",
    [
        URIRef("relative"),
        URIRef("https://example.test/\n"),
        URIRef("https://example.test/" + "x" * 4096),
    ],
)
def test_uri_limits_and_safe_iri_surface(node: URIRef) -> None:
    graph = make_graph()
    graph.add((URIRef("https://example.test/s"), node, Literal("x")))
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def test_literal_and_metadata_limits() -> None:
    graph = make_graph()
    graph.add(
        (URIRef("https://example.test/s"), URIRef("https://example.test/p"), Literal("x" * 16385))
    )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            Literal("x", lang="x" * 4097),
        )
    )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def test_body_limit_is_checked_after_canonicalization() -> None:
    graph = make_graph()
    root = URIRef("https://example.test/trace/1")
    for index in range(255):
        graph.add(
            (
                root,
                URIRef(f"https://example.test/p/{index}"),
                Literal("x" * 5000),
            )
        )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def _text_with_exact_utf8_bytes(prefix: str, byte_count: int) -> str:
    prefix_bytes = prefix.encode()
    assert len(prefix_bytes) <= byte_count
    remaining = byte_count - len(prefix_bytes)
    whole, remainder = divmod(remaining, 2)
    return prefix + "é" * whole + ("x" if remainder else "")


@pytest.mark.parametrize(
    ("kind", "limit", "prefix"),
    [("endpoint", 2048, "http://127.0.0.1:1/"), ("graph", 4096, "https://example.test/")],
)
def test_configuration_byte_boundaries_and_multibyte_accounting(
    kind: str, limit: int, prefix: str
) -> None:
    at_limit = _text_with_exact_utf8_bytes(prefix, limit)
    over_limit = _text_with_exact_utf8_bytes(prefix, limit + 1)
    assert len(at_limit.encode()) == limit
    assert len(over_limit.encode()) == limit + 1
    if kind == "endpoint":
        query = "http://127.0.0.1:1/q"
        assert FusekiProvenanceStoreConfig(at_limit, query, BASE).update_endpoint == at_limit
        with pytest.raises(ValueError):
            FusekiProvenanceStoreConfig(over_limit, query, BASE)
    else:
        assert (
            FusekiProvenanceStoreConfig(UPDATE, QUERY, at_limit).provenance_graph_base == at_limit
        )
        with pytest.raises(ValueError):
            FusekiProvenanceStoreConfig(UPDATE, QUERY, over_limit)


@pytest.mark.parametrize("position", ["subject", "predicate", "object"])
def test_subject_predicate_and_object_require_exact_term_roles(position: str) -> None:
    class ControlledStore(Store):
        def triples(
            self, triple_pattern: object, context: object = None
        ) -> Iterator[tuple[tuple[Any, Any, Any], Iterator[Any]]]:
            del triple_pattern, context
            yield (
                (
                    Literal("not-a-subject")
                    if position == "subject"
                    else URIRef("https://example.test/s"),
                    Literal("not-a-predicate")
                    if position == "predicate"
                    else URIRef("https://example.test/p"),
                    BNode() if position == "object" else Literal("not-an-object"),
                ),
                iter(()),
            )

    with pytest.raises(TypeError, match="subject|predicate|object"):
        make_store()._canonicalize_graph(Graph(store=ControlledStore()))


@pytest.mark.parametrize("position", ["subject", "predicate", "object", "datatype"])
def test_hostile_rdf_subclasses_are_rejected_before_overrides(position: str) -> None:
    class HostileURIRef(URIRef):
        def __str__(self) -> str:
            raise AssertionError("hostile __str__ executed")

        def __format__(self, spec: str) -> str:
            raise AssertionError("hostile __format__ executed")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("hostile __eq__ executed")

        def n3(self, namespace_manager: object = None) -> str:
            raise AssertionError("hostile n3 executed")

    class HostileLiteral(Literal):
        def __str__(self) -> str:
            raise AssertionError("hostile literal __str__ executed")

        def __format__(self, spec: str) -> str:
            raise AssertionError("hostile literal __format__ executed")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("hostile literal __eq__ executed")

        def n3(self, namespace_manager: object = None) -> str:
            raise AssertionError("hostile literal n3 executed")

    hostile_uri = HostileURIRef("https://example.test/hostile")
    hostile_datatype_literal = str.__new__(Literal, "x")
    hostile_datatype_literal._language = None
    hostile_datatype_literal._datatype = hostile_uri
    hostile_datatype_literal._value = None
    hostile_datatype_literal._ill_typed = None
    values = {
        "subject": (hostile_uri, URIRef("https://example.test/p"), Literal("x")),
        "predicate": (URIRef("https://example.test/s"), hostile_uri, Literal("x")),
        "object": (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            HostileLiteral("x"),
        ),
        "datatype": (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            hostile_datatype_literal,
        ),
    }

    class ControlledStore(Store):
        def triples(
            self, triple_pattern: object, context: object = None
        ) -> Iterator[tuple[tuple[Any, Any, Any], Iterator[Any]]]:
            del triple_pattern, context
            yield values[position], iter(())

    with pytest.raises(TypeError):
        make_store()._canonicalize_graph(Graph(store=ControlledStore()))


def test_graph_emission_requires_exact_tuple_before_unpacking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iterated = False

    class HostileTuple(tuple[object, ...]):
        def __iter__(self) -> Iterator[object]:
            nonlocal iterated
            iterated = True
            raise AssertionError("hostile tuple iterator executed")

    emission = HostileTuple((URIRef("https://example.test/trace/1"), RDF.type, MFG.ProvenanceTrace))
    monkeypatch.setattr(Graph, "__iter__", lambda self: iter([emission]))

    with pytest.raises(TypeError, match="graph emission must be an exact 3-tuple"):
        make_store()._canonicalize_graph(Graph())
    assert iterated is False


@pytest.mark.parametrize("whitespace", [" ", "\t", "\n", "\r", "\u00a0", "\u2003"])
def test_graph_base_and_uri_reject_all_whitespace(whitespace: str) -> None:
    with pytest.raises(ValueError):
        FusekiProvenanceStoreConfig(UPDATE, QUERY, BASE + whitespace + "suffix")
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p" + whitespace + "suffix"),
            Literal("x"),
        )
    )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def _body_boundary_graph(first_literal_length: int) -> Graph:
    graph = Graph()
    root = URIRef("https://example.test/trace/1")
    graph.add(
        (root, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), MFG.ProvenanceTrace)
    )
    for index in range(64):
        length = first_literal_length if index == 0 else 16384
        graph.add((root, URIRef(f"https://example.test/p/{index}"), Literal("x" * length)))
    return graph


def test_canonical_body_exact_limit_is_accepted_and_one_byte_over_rejected() -> None:
    accepted = make_store()._canonicalize_graph(_body_boundary_graph(12162))
    assert len(accepted) == 1_048_576
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(_body_boundary_graph(12163))


@pytest.mark.parametrize("length", [4096])
def test_uri_byte_limit_accepts_exact_and_rejects_one_byte_over(length: int) -> None:
    exact = URIRef(_text_with_exact_utf8_bytes("https://example.test/", length))
    graph = make_graph()
    graph.add((URIRef("https://example.test/s"), exact, Literal("x")))
    assert make_store()._canonicalize_graph(graph)

    over = URIRef(_text_with_exact_utf8_bytes("https://example.test/", length + 1))
    graph = make_graph()
    graph.add((URIRef("https://example.test/s"), over, Literal("x")))
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def test_literal_lexical_byte_limit_accepts_exact_and_rejects_one_byte_over() -> None:
    graph = make_graph()
    graph.add(
        (URIRef("https://example.test/s"), URIRef("https://example.test/p"), Literal("é" * 8192))
    )
    assert make_store()._canonicalize_graph(graph)
    graph = make_graph()
    graph.add(
        (URIRef("https://example.test/s"), URIRef("https://example.test/p"), Literal("é" * 8193))
    )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def test_literal_metadata_byte_limits_accept_exact_and_reject_one_byte_over() -> None:
    exact_datatype = URIRef(_text_with_exact_utf8_bytes("https://example.test/", 4096))
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            Literal("x", datatype=exact_datatype),
        )
    )
    assert make_store()._canonicalize_graph(graph)

    over_datatype = URIRef(_text_with_exact_utf8_bytes("https://example.test/", 4097))
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            Literal("x", datatype=over_datatype),
        )
    )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)

    exact_language = "x" * 4096
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            Literal("x", lang=exact_language),
        )
    )
    assert make_store()._canonicalize_graph(graph)
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            Literal("x", lang="x" * 4097),
        )
    )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(graph)


def test_subject_limit_accepts_128_and_rejects_129_subjects() -> None:
    accepted = make_graph()
    for index in range(127):
        accepted.add(
            (
                URIRef(f"https://example.test/s/{index}"),
                URIRef("https://example.test/p"),
                Literal(index),
            )
        )
    assert make_store()._canonicalize_graph(accepted)

    rejected = make_graph()
    for index in range(128):
        rejected.add(
            (
                URIRef(f"https://example.test/s/{index}"),
                URIRef("https://example.test/p"),
                Literal(index),
            )
        )
    with pytest.raises(ValueError):
        make_store()._canonicalize_graph(rejected)


def _graph_with_repeated_store_emissions(emissions: int) -> Graph:
    triple = (
        URIRef("https://example.test/trace/1"),
        RDF.type,
        MFG.ProvenanceTrace,
    )

    class RepeatingStore(Store):
        def triples(
            self, triple_pattern: object, context: object = None
        ) -> Iterator[tuple[tuple[Any, Any, Any], Iterator[Any]]]:
            del triple_pattern, context
            for _ in range(emissions):
                yield triple, iter(())

    return Graph(store=RepeatingStore())


def test_duplicate_store_emissions_are_deduplicated_before_cardinality_bound() -> None:
    graph = _graph_with_repeated_store_emissions(257)

    assert make_store()._canonicalize_graph(graph)


def test_hostile_store_emission_ceiling_accepts_exact_and_rejects_one_over() -> None:
    assert make_store()._canonicalize_graph(_graph_with_repeated_store_emissions(512))
    with pytest.raises(ValueError, match="raw graph emissions"):
        make_store()._canonicalize_graph(_graph_with_repeated_store_emissions(513))


class _SecretStoreFailure(Exception):
    secret = "placeholder-store-sentinel-must-not-escape"

    def __str__(self) -> str:
        return self.secret

    def __repr__(self) -> str:
        return f"_SecretStoreFailure({self.secret!r})"


class _SecretBaseException(BaseException):
    pass


class _FailingEmissions:
    def __init__(self, *, fail_on_first: bool) -> None:
        self._fail_on_first = fail_on_first
        self._calls = 0

    def __iter__(self) -> "_FailingEmissions":
        return self

    def __next__(self) -> tuple[tuple[URIRef, URIRef, URIRef], Iterator[Any]]:
        self._calls += 1
        if self._fail_on_first or self._calls > 1:
            raise _SecretStoreFailure
        return (
            (
                URIRef("https://example.test/trace/1"),
                RDF.type,
                MFG.ProvenanceTrace,
            ),
            iter(()),
        )


class _BaseFailingEmissions(_FailingEmissions):
    def __next__(self) -> tuple[tuple[URIRef, URIRef, URIRef], Iterator[Any]]:
        self._calls += 1
        if self._fail_on_first or self._calls > 1:
            raise _SecretBaseException
        return (
            (
                URIRef("https://example.test/trace/1"),
                RDF.type,
                MFG.ProvenanceTrace,
            ),
            iter(()),
        )


@pytest.mark.parametrize("fail_on_first", [True, False])
def test_hostile_store_failures_are_fixed_and_causeless(fail_on_first: bool) -> None:
    class HostileStore(Store):
        def triples(
            self, triple_pattern: object, context: object = None
        ) -> Iterator[tuple[tuple[Any, Any, Any], Iterator[Any]]]:
            del triple_pattern, context
            return _FailingEmissions(fail_on_first=fail_on_first)

    with pytest.raises(ValueError) as exc_info:
        make_store()._canonicalize_graph(Graph(store=HostileStore()))

    error = exc_info.value
    assert str(error) == "invalid graph"
    assert "placeholder-store-sentinel-must-not-escape" not in repr(error)
    assert "placeholder-store-sentinel-must-not-escape" not in format_exc()
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("fail_on_first", [True, False])
def test_base_exception_from_store_is_not_sanitized(fail_on_first: bool) -> None:
    class HostileStore(Store):
        def triples(
            self, triple_pattern: object, context: object = None
        ) -> Iterator[tuple[tuple[Any, Any, Any], Iterator[Any]]]:
            del triple_pattern, context
            return _BaseFailingEmissions(fail_on_first=fail_on_first)

    with pytest.raises(_SecretBaseException):
        make_store()._canonicalize_graph(Graph(store=HostileStore()))


@pytest.mark.parametrize("term", [URIRef("https://example.test/hostile"), Literal("hostile")])
def test_rdf_serialization_failures_are_fixed_and_causeless(
    term: URIRef | Literal, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_n3(self: object, namespace_manager: object = None) -> str:
        del self, namespace_manager
        raise _SecretStoreFailure

    monkeypatch.setattr(type(term), "n3", fail_n3)

    with pytest.raises(ValueError) as exc_info:
        if type(term) is URIRef:
            fuseki_store._validate_uri(term, "term")
        else:
            fuseki_store._validate_node(term)

    error = exc_info.value
    assert str(error) in {"invalid term", "invalid literal"}
    assert "placeholder-store-sentinel-must-not-escape" not in repr(error)
    assert "placeholder-store-sentinel-must-not-escape" not in format_exc()
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("term", [URIRef("https://example.test/hostile"), Literal("hostile")])
def test_base_exception_from_rdf_serialization_propagates(
    term: URIRef | Literal, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_n3(self: object, namespace_manager: object = None) -> str:
        del self, namespace_manager
        raise _SecretBaseException

    monkeypatch.setattr(type(term), "n3", fail_n3)

    with pytest.raises(_SecretBaseException):
        if type(term) is URIRef:
            fuseki_store._validate_uri(term, "term")
        else:
            fuseki_store._validate_node(term)


def test_prepares_exact_hashed_graph_update_without_persist_dispatch() -> None:
    store = make_store()
    prepared = store._prepare_update(make_graph())
    import hashlib

    provenance_id = "https://example.test/trace/1"
    digest = hashlib.sha256(provenance_id.encode("utf-8")).hexdigest()
    expected_graph = f"{BASE}:trace:{digest}"
    assert prepared.graph_iri == expected_graph
    assert prepared.canonical_graph == (
        b"<https://example.test/trace/1> "
        b"<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
        b"<https://w3id.org/mfg-agentgraph/v1#ProvenanceTrace> .\n"
    )
    assert prepared.update_body == (
        b"INSERT DATA { GRAPH <"
        + expected_graph.encode()
        + b"> { "
        + prepared.canonical_graph
        + b"} }"
    )
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        store.persist(make_graph())


def test_prepared_update_is_immutable_and_rejects_injected_graph_base() -> None:
    prepared = make_store()._prepare_update(make_graph())
    with pytest.raises(FrozenInstanceError):
        prepared.update_body = b"x"  # type: ignore[misc]
    for base in ["https://example.test/> GRAPH ?g", "https://example.test/\\n"]:
        with pytest.raises(ValueError):
            FusekiProvenanceStoreConfig(UPDATE, QUERY, base)


def test_dispatch_uses_single_exact_request_and_accepts_empty_204(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 204

        def getheaders(self) -> list[tuple[str, str]]:
            return [("Content-Length", "0")]

        def read(self, size: int = -1) -> bytes:
            assert size == 1
            return b""

    class FakeConnection:
        instances: list["FakeConnection"] = []

        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.host, self.port, self.timeout = host, port, timeout
            self.sock = _Socket()
            self.calls: list[object] = []
            self.response = FakeResponse()
            self.__class__.instances.append(self)

        def connect(self) -> None:
            self.calls.append("connect")

        def putrequest(self, *args: object, **kwargs: object) -> None:
            self.calls.append(("putrequest", args, kwargs))

        def putheader(self, *args: object) -> None:
            self.calls.append(("putheader", args))

        def endheaders(self, body: bytes) -> None:
            self.calls.append("endheaders")
            self.body = body

        def getresponse(self) -> FakeResponse:
            self.calls.append("getresponse")
            return self.response

        def close(self) -> None:
            self.calls.append("close")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", FakeConnection)
    make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    connection = FakeConnection.instances[-1]
    assert connection.body.startswith(
        b"INSERT DATA { GRAPH <https://example.test/provenance:trace:"
    )
    assert connection.calls.count("endheaders") == 1
    assert connection.calls[-1] == "close"


def test_dispatch_factory_failure_is_not_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom(Exception):
        pass

    monkeypatch.setattr(
        cast(Any, fuseki_store).http.client,
        "HTTPConnection",
        lambda *a, **k: (_ for _ in ()).throw(Boom()),
    )
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    assert exc.value.state is fuseki_store.DispatchState.NOT_DISPATCHED


class _HostileText(str):
    def __add__(self, other: object) -> str:
        raise AssertionError("hostile __add__ executed")

    def __hash__(self) -> int:
        raise AssertionError("hostile __hash__ executed")

    def __format__(self, spec: str) -> str:
        raise AssertionError("hostile __format__ executed")


class _HostileFloat(float):
    def __float__(self) -> float:
        raise AssertionError("hostile __float__ executed")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("update_endpoint", _HostileText(UPDATE)),
        ("query_endpoint", _HostileText(QUERY)),
        ("provenance_graph_base", _HostileText(BASE)),
        ("timeout_seconds", _HostileFloat(5.0)),
    ],
)
def test_prepare_revalidates_drifted_config_before_hostile_operations(
    field: str, value: object
) -> None:
    store = make_store()
    object.__setattr__(store.config, field, value)
    with pytest.raises(TypeError):
        store._prepare_update(make_graph())


def test_prepare_revalidates_all_config_cross_field_coherence_before_hashing() -> None:
    store = make_store()
    object.__setattr__(store.config, "query_endpoint", UPDATE)
    with pytest.raises(ValueError):
        store._prepare_update(make_graph())


def test_resulting_graph_iri_uses_the_same_exact_byte_limit() -> None:
    exact_base = _text_with_exact_utf8_bytes("https://example.test/", 4096 - len(b":trace:") - 64)
    store = FusekiProvenanceStoreConfig(UPDATE, QUERY, exact_base)
    prepared = FusekiProvenanceStore(store)._prepare_update(make_graph())
    assert len(prepared.graph_iri.encode()) == 4096

    drifted = FusekiProvenanceStoreConfig(UPDATE, QUERY, exact_base + "x")
    with pytest.raises(ValueError, match="per_run_graph"):
        FusekiProvenanceStore(drifted)._prepare_update(make_graph())


def _update_body_boundary_graph(target: int) -> Graph:
    graph = make_graph()
    root = URIRef("https://example.test/trace/1")
    index = 0
    while True:
        graph.add(
            (
                root,
                URIRef(f"https://example.test/p/{index}"),
                Literal("x" * 16_384),
            )
        )
        index += 1
        try:
            prepared = make_store()._prepare_update(graph)
        except ValueError:
            graph.remove(
                (root, URIRef(f"https://example.test/p/{index - 1}"), Literal("x" * 16_384))
            )
            break
        if len(prepared.update_body) >= target:
            break
    return graph


def test_update_body_exact_limit_and_one_byte_over_rejected_before_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store()
    exact_graph = None
    exact_length = None
    for literal_length in range(12162, 11900, -1):
        candidate = _body_boundary_graph(literal_length)
        try:
            prepared = store._prepare_update(candidate)
        except ValueError:
            continue
        if len(prepared.update_body) == 1_048_576:
            exact_graph = candidate
            exact_length = literal_length
            break
    assert exact_graph is not None
    assert exact_length is not None
    assert len(store._prepare_update(exact_graph).update_body) == 1_048_576

    over_graph = _body_boundary_graph(exact_length + 1)

    class NoConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("connection created after rejection")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", NoConnection)
    with pytest.raises(ValueError, match="update body exceeds bound"):
        store._prepare_update(over_graph)


def test_prepared_drift_is_rejected_before_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    prepared = make_store()._prepare_update(make_graph())
    object.__setattr__(prepared, "host", _HostileText("127.0.0.1"))
    object.__setattr__(prepared, "port", True)

    class NoConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("hostile prepared value reached connection")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", NoConnection)
    with pytest.raises(TypeError):
        make_store()._dispatch_prepared(prepared)


def test_direct_prepared_construction_rejects_non_builtin_fields() -> None:
    prepared = make_store()._prepare_update(make_graph())
    with pytest.raises(TypeError):
        replace(prepared, host=_HostileText(prepared.host))
    with pytest.raises(TypeError):
        replace(prepared, port=True)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("canonical_graph", b"not canonical"),
        ("graph_iri", "https://attacker.invalid/graph"),
        ("update_body", b"INSERT DATA {}"),
        ("request_path", "/attacker"),
        ("authority", "attacker.invalid:1"),
        ("host", "attacker.invalid"),
        ("port", 1),
        ("request_line", b"POST /attacker HTTP/1.1\r\n"),
        ("header_bytes", b"Host: attacker.invalid\r\n\r\n"),
        ("wire_bytes", b"attacker wire"),
    ],
)
def test_every_prepared_field_is_cross_checked_before_connection(
    field: str, replacement: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = make_store()._prepare_update(make_graph())
    object.__setattr__(prepared, field, replacement)

    class NoConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("incoherent prepared value reached connection")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", NoConnection)
    with pytest.raises((TypeError, ValueError)):
        make_store()._dispatch_prepared(prepared)


def test_coherently_drifted_prepared_canonical_graph_is_revalidated_before_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store()
    prepared = store._prepare_update(make_graph())
    canonical = prepared.canonical_graph + b"DROP ALL\n"
    update_body = (
        b"INSERT DATA { GRAPH <" + prepared.graph_iri.encode("utf-8") + b"> { " + canonical + b"} }"
    )
    header_bytes = (
        f"Host: {prepared.authority}\r\n".encode("ascii")
        + b"Content-Type: application/sparql-update; charset=utf-8\r\n"
        + b"Accept: text/plain\r\n"
        + f"Content-Length: {len(update_body)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
    )
    object.__setattr__(prepared, "canonical_graph", canonical)
    object.__setattr__(prepared, "update_body", update_body)
    object.__setattr__(prepared, "header_bytes", header_bytes)
    object.__setattr__(prepared, "wire_bytes", prepared.request_line + header_bytes + update_body)

    class NoConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("invalid canonical graph reached connection")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", NoConnection)
    with pytest.raises(ValueError, match="invalid prepared canonical graph"):
        store._dispatch_prepared(prepared)


def test_dispatch_revalidates_drifted_timeout_before_connection() -> None:
    store = make_store()
    object.__setattr__(store.config, "timeout_seconds", _HostileFloat(5.0))
    with pytest.raises(TypeError):
        store._dispatch_prepared(store._prepare_update(make_graph()))


@pytest.mark.parametrize("endpoint", [UPDATE, "http://[::1]:3030/update"])
def test_prepare_exact_wire_bytes_for_ipv4_and_ipv6(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("http_proxy", "http://attacker.invalid:9")
    query = endpoint.replace("/update", "/query")
    store = FusekiProvenanceStore(FusekiProvenanceStoreConfig(endpoint, query, BASE))
    graph = make_graph()
    graph.add(
        (
            URIRef("https://example.test/s"),
            URIRef("https://example.test/p"),
            Literal('literal } INSERT DATA { GRAPH ?g "quoted"'),
        )
    )
    prepared = store._prepare_update(graph)
    authority = "127.0.0.1:3030" if "127.0.0.1" in endpoint else "[::1]:3030"
    assert prepared.request_line == b"POST /update HTTP/1.1\r\n"
    assert prepared.header_bytes == (
        f"Host: {authority}\r\n".encode()
        + b"Content-Type: application/sparql-update; charset=utf-8\r\n"
        + b"Accept: text/plain\r\n"
        + f"Content-Length: {len(prepared.update_body)}\r\n".encode()
        + b"Connection: close\r\n\r\n"
    )
    assert (
        prepared.wire_bytes == prepared.request_line + prepared.header_bytes + prepared.update_body
    )
    assert len(prepared.wire_bytes) == (
        len(prepared.request_line) + len(prepared.header_bytes) + len(prepared.update_body)
    )
    assert b"WITH" not in prepared.update_body
    assert b"DELETE" not in prepared.update_body
    assert b"CLEAR" not in prepared.update_body
    assert b"DROP" not in prepared.update_body
    assert b"INSERT DATA" in prepared.update_body
    assert b'"literal } INSERT DATA { GRAPH ?g \\"quoted\\""' in prepared.update_body


class _Socket:
    def __init__(self, *, setter: object = None) -> None:
        self.values: list[float] = []
        self.setter = setter if setter is not None else self.values.append

    def settimeout(self, value: float) -> None:
        if not callable(self.setter):
            raise AttributeError("missing setter")
        cast(Any, self.setter)(value)


class _TransportFailure(Exception):
    def __init__(self, marker: str) -> None:
        self.marker = marker

    def __str__(self) -> str:
        return self.marker

    def __repr__(self) -> str:
        return f"_TransportFailure({self.marker!r})"


class _TransportBase(BaseException):
    pass


class _Response:
    def __init__(
        self,
        headers: object = [("Content-Length", "0")],
        body: object = b"",
        status: object = 204,
    ) -> None:
        self.headers = headers
        self.body = body
        self._status = status
        self.read_calls: list[int] = []

    @property
    def status(self) -> object:
        return self._status

    def getheaders(self) -> object:
        return self.headers

    def read(self, size: int = -1) -> object:
        self.read_calls.append(size)
        return self.body


class _Connection:
    instances: list["_Connection"] = []
    failure: str | None = None
    response: _Response = _Response()
    with_socket = True
    close_socket_after_response = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.sock = _Socket() if self.with_socket else None
        self.timeout = timeout
        self.calls: list[str] = []
        self.request_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.header_calls: list[tuple[object, ...]] = []
        self.bodies: list[bytes] = []
        self.__class__.instances.append(self)

    def _maybe_fail(self, phase: str) -> None:
        if self.failure == phase:
            raise _TransportFailure(f"secret-{phase}")

    def connect(self) -> None:
        self.calls.append("connect")
        self._maybe_fail("connect")

    def putrequest(self, *args: object, **kwargs: object) -> None:
        self.calls.append("putrequest")
        self.request_calls.append((args, kwargs))
        self._maybe_fail("request")

    def putheader(self, *args: object) -> None:
        self.calls.append("putheader")
        self.header_calls.append(args)
        self._maybe_fail("request")

    def endheaders(self, body: bytes) -> None:
        self.calls.append("endheaders")
        self.bodies.append(body)
        self._maybe_fail("endheaders")

    def getresponse(self) -> _Response:
        self.calls.append("getresponse")
        self._maybe_fail("getresponse")
        if self.close_socket_after_response:
            self.sock = None
        return self.response

    def close(self) -> None:
        self.calls.append("close")
        self._maybe_fail("close")


def _patch_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    _Connection.instances.clear()
    _Connection.failure = None
    _Connection.response = _Response()
    _Connection.with_socket = True
    _Connection.close_socket_after_response = False
    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", _Connection)


@pytest.mark.parametrize("headers", [(), {}, ([("Content-Length", "0")],)])
def test_response_headers_require_exact_list(headers: object) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers(headers)


@pytest.mark.parametrize(
    "header",
    [
        ("Transfer-Encoding", "chunked"),
        ("Content-Encoding", "gzip"),
        ("content-length", "1"),
        ("Content-Length", "0"),
    ],
)
def test_response_header_forbidden_and_duplicate_rules(header: tuple[str, str]) -> None:
    headers = [header, ("Content-Length", "0")]
    if header == ("Content-Length", "0"):
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
            fuseki_store._validate_response_headers(headers)
    elif header[0].lower() == "content-length":
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
            fuseki_store._validate_response_headers([header])
    else:
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
            fuseki_store._validate_response_headers([header])


@pytest.mark.parametrize(
    "name,value", [("X\r", "ok"), ("X", "bad\nvalue"), ("X:evil", "ok"), ("X", "\x01")]
)
def test_response_headers_reject_wire_injection(name: str, value: str) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers([(name, value)])


def test_response_header_wire_byte_boundary() -> None:
    prefix = "X: "
    value = "a" * (16_384 - 2 - 1 - 2 - 2)
    fuseki_store._validate_response_headers([(prefix[:-2], value)])
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers([(prefix[:-2], value + "a")])


@pytest.mark.parametrize("status", [True, 200, 204.0, "204"])
def test_response_status_requires_exact_204(
    status: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_transport(monkeypatch)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        if type(status) is int and status == 204:
            raise AssertionError("unreachable")
        if type(status) is not int or status != 204:
            fuseki_store._raise_transport(
                fuseki_store._TransportPhase.RESPONSE, fuseki_store.DispatchState.DISPATCHED_UNKNOWN
            )


@pytest.mark.parametrize("body", [b"x", bytearray(), "", bytearray(b"x"), memoryview(b"")])
def test_response_body_requires_exact_empty_bytes_and_single_read(body: object) -> None:
    response = _Response(body=body)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        if type(response.read(1)) is not bytes or response.body != b"":
            fuseki_store._raise_transport(
                fuseki_store._TransportPhase.BODY, fuseki_store.DispatchState.DISPATCHED_UNKNOWN
            )
    assert response.read_calls == [1]


def test_transport_failure_is_sanitized_causeless_and_close_does_not_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    _Connection.failure = "getresponse"
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    error = exc_info.value
    assert str(error) == "Fuseki transport response failed"
    assert "secret-getresponse" not in repr(error)
    assert "secret-getresponse" not in "".join(format_exc())
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _Connection.instances[-1].calls[-1] == "close"


def test_missing_socket_after_connect_is_not_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)
    _Connection.with_socket = False
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    assert exc_info.value.state is fuseki_store.DispatchState.NOT_DISPATCHED
    assert "endheaders" not in _Connection.instances[-1].calls


def test_dispatch_close_failure_is_sanitized_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)
    _Connection.failure = "close"
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    assert exc_info.value.phase is fuseki_store._TransportPhase.DISPATCH
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_base_exception_is_not_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)

    def raise_base(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise _TransportBase("base-secret")

    monkeypatch.setattr(_Connection, "connect", raise_base)
    with pytest.raises(_TransportBase):
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))


@pytest.mark.parametrize("connection", [object(), type("C", (), {"sock": object()})()])
def test_timeout_expiry_and_missing_socket_setter_are_fixed(
    monkeypatch: pytest.MonkeyPatch, connection: object
) -> None:
    monkeypatch.setattr(cast(Any, fuseki_store).time, "monotonic", lambda: 10.0)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._set_remaining_timeout(connection, 9.0, require_socket=True)


class _BadSocket:
    settimeout = None


class _RaisingSocket:
    def settimeout(self, value: float) -> None:
        del value
        raise _TransportFailure("secret-settimeout")


class _BadTimeoutConnection:
    sock = None

    @property
    def timeout(self) -> float:
        return 0.0

    @timeout.setter
    def timeout(self, value: float) -> None:
        del value
        raise _TransportFailure("secret-timeout")


@pytest.mark.parametrize(
    "connection",
    [
        type("C", (), {"sock": _BadSocket()})(),
        type("C", (), {"sock": _RaisingSocket()})(),
        _BadTimeoutConnection(),
    ],
)
def test_timeout_setter_failures_are_sanitized(connection: object) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        fuseki_store._set_remaining_timeout(connection, 10_000.0)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "secret-" not in repr(exc_info.value)


@pytest.mark.parametrize("headers", [[("only-one",)], [(1, "0")], [("X", "€")], [[("X", "0")]]])
def test_response_header_shapes_and_latin1_fail_closed(headers: object) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers(headers)


def test_prepared_empty_canonical_is_rejected_before_connection() -> None:
    prepared = make_store()._prepare_update(make_graph())
    object.__setattr__(prepared, "canonical_graph", b"")
    with pytest.raises(ValueError, match="canonical graph"):
        make_store()._dispatch_prepared(prepared)


def test_dispatch_sanitizes_status_property_failure_on_real_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)

    class SecretStatusResponse(_Response):
        @property
        def status(self) -> int:
            raise _TransportFailure("secret-status")

    _Connection.response = SecretStatusResponse()
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    assert exc_info.value.phase is fuseki_store._TransportPhase.RESPONSE
    assert exc_info.value.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert "secret-status" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize("name", ["X(", "X)", "X@", "X/", "X?", "X="])
def test_response_header_names_require_rfc_token(name: str) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers([(name, "ok")])


def test_transport_error_exposes_immutable_exact_phase_and_state() -> None:
    error = fuseki_store.FusekiProvenanceTransportError(
        fuseki_store._TransportPhase.RESPONSE,
        fuseki_store.DispatchState.DISPATCHED_UNKNOWN,
    )
    with pytest.raises(AttributeError):
        object.__setattr__(error, "phase", fuseki_store._TransportPhase.FACTORY)
    with pytest.raises(AttributeError):
        object.__setattr__(error, "state", fuseki_store.DispatchState.NOT_DISPATCHED)
    assert error.args == ("Fuseki transport response failed",)
    assert error.phase is fuseki_store._TransportPhase.RESPONSE
    assert error.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN


def test_dispatch_uses_remaining_deadline_for_factory_and_later_setters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    clock = iter([100.0, 100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0])
    monkeypatch.setattr(cast(Any, fuseki_store).time, "monotonic", lambda: next(clock))
    make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    connection = _Connection.instances[-1]
    assert connection.timeout <= 5.0
    assert connection.sock is not None
    assert connection.sock.values
    assert all(value > 0 for value in connection.sock.values)
    assert connection.sock.values == sorted(connection.sock.values, reverse=True)


@pytest.mark.parametrize("failure", ["connect", "request", "endheaders", "getresponse", "close"])
def test_real_dispatch_path_sanitizes_each_ordinary_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _patch_transport(monkeypatch)
    _Connection.failure = failure
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    assert "secret-" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert _Connection.instances[-1].calls.count("close") == 1


@pytest.mark.parametrize(
    "point",
    [
        "factory",
        "connect",
        "request",
        "endheaders",
        "getresponse",
        "status",
        "getheaders",
        "read",
        "close",
        "socket",
    ],
)
def test_real_dispatch_path_propagates_base_exception_at_every_boundary(
    monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    _patch_transport(monkeypatch)

    def raise_base(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise _TransportBase("base-secret")

    if point == "factory":
        monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", raise_base)
    elif point == "socket":
        monkeypatch.setattr(_Socket, "settimeout", raise_base)
    elif point == "status":

        class BaseStatusResponse(_Response):
            @property
            def status(self) -> object:
                return raise_base()

        _Connection.response = BaseStatusResponse()
    elif point in {"getheaders", "read"}:
        response = _Response()
        monkeypatch.setattr(response, point, raise_base)
        _Connection.response = response
    else:
        method = "putrequest" if point == "request" else point
        monkeypatch.setattr(_Connection, method, raise_base)

    with pytest.raises(_TransportBase):
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))


def test_base_exception_during_close_does_not_replace_ordinary_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    _Connection.failure = "getresponse"

    def raise_base(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise _TransportBase("close-base-secret")

    monkeypatch.setattr(_Connection, "close", raise_base)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))
    assert exc_info.value.phase is fuseki_store._TransportPhase.RESPONSE


def _render_captured_request(connection: _Connection) -> bytes:
    assert connection.request_calls == [
        (("POST", "/update"), {"skip_host": True, "skip_accept_encoding": True})
    ]
    headers = b"".join(
        f"{name}: {value}\r\n".encode("ascii") for (name, value) in connection.header_calls
    )
    assert len(connection.bodies) == 1
    return b"POST /update HTTP/1.1\r\n" + headers + b"\r\n" + connection.bodies[0]


@pytest.mark.parametrize("endpoint", [UPDATE, "http://[::1]:3030/update"])
def test_real_dispatch_emits_exact_prepared_wire_for_ipv4_and_ipv6(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_transport(monkeypatch)
    monkeypatch.setenv("http_proxy", "http://attacker.invalid:9")
    query = endpoint.replace("/update", "/query")
    store = FusekiProvenanceStore(FusekiProvenanceStoreConfig(endpoint, query, BASE))
    prepared = store._prepare_update(make_graph())

    assert cast(Any, store)._dispatch_prepared(prepared) is None

    assert len(_Connection.instances) == 1
    connection = _Connection.instances[0]
    assert (connection.host, connection.port) == (
        ("127.0.0.1", 3030) if "127.0.0.1" in endpoint else ("::1", 3030)
    )
    assert _render_captured_request(connection) == prepared.wire_bytes
    assert connection.calls.count("connect") == 1
    assert connection.calls.count("endheaders") == 1
    assert connection.calls.count("getresponse") == 1
    assert connection.calls.count("close") == 1
    assert _Connection.response.read_calls == [1]


@pytest.mark.parametrize("status", [True, 200, 204.0, "204"])
def test_real_dispatch_rejects_non_exact_204_status(
    status: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_transport(monkeypatch)
    _Connection.response = _Response(status=status)

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))

    error = exc_info.value
    assert error.phase is fuseki_store._TransportPhase.RESPONSE
    assert error.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert str(error) == "Fuseki transport response failed"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert UPDATE not in repr(error)
    assert _Connection.instances[-1].calls.count("endheaders") == 1
    assert _Connection.instances[-1].calls.count("close") == 1


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(f"X-{index}", "v") for index in range(31)] + [("Content-Length", "0")],
        [("X", "a" * 16_377)],
        [("Content-Length", "0")],
    ],
)
def test_real_dispatch_accepts_exact_response_header_boundaries(
    headers: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_transport(monkeypatch)
    _Connection.response = _Response(headers=headers)

    store = make_store()
    assert cast(Any, store)._dispatch_prepared(store._prepare_update(make_graph())) is None
    assert _Connection.response.read_calls == [1]
    assert _Connection.instances[-1].calls.count("close") == 1


@pytest.mark.parametrize(
    "headers",
    [
        [(f"X-{index}", "v") for index in range(32)] + [("Content-Length", "0")],
        [("X", "a" * 16_378)],
        [("Content-Length", "0"), ("content-length", "0")],
        [("Content-Length", "0"), ("content-length", "1")],
        [("tRaNsFeR-EnCoDiNg", "chunked")],
        [("cOnTeNt-EnCoDiNg", "gzip")],
        [("Content-Length", "1")],
        [("X(", "v")],
        [("X", "€")],
        [("X", "bad\nvalue")],
        [(1, "v")],
        [("X", 1)],
        [("only-one",)],
        [[("X", "v")]],
        (),
    ],
)
def test_real_dispatch_rejects_invalid_response_headers(
    headers: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_transport(monkeypatch)
    _Connection.response = _Response(headers=headers)

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))

    error = exc_info.value
    assert error.phase is fuseki_store._TransportPhase.HEADERS
    assert error.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert str(error) == "Fuseki transport response headers invalid"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert UPDATE not in repr(error)
    assert "attacker.invalid" not in format_exc()
    assert len(_Connection.instances) == 1
    assert _Connection.instances[-1].calls.count("endheaders") == 1
    assert _Connection.instances[-1].calls.count("close") == 1


def test_real_dispatch_accepts_one_exact_empty_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)

    store = make_store()
    assert cast(Any, store)._dispatch_prepared(store._prepare_update(make_graph())) is None
    assert _Connection.response.read_calls == [1]


@pytest.mark.parametrize("body", [b"x", bytearray(), "", bytearray(b"x"), memoryview(b"")])
def test_real_dispatch_rejects_non_exact_empty_bytes_body(
    body: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_transport(monkeypatch)
    _Connection.response = _Response(body=body)

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store()._dispatch_prepared(make_store()._prepare_update(make_graph()))

    error = exc_info.value
    assert error.phase is fuseki_store._TransportPhase.BODY
    assert error.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert str(error) == "Fuseki transport response body invalid"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _Connection.response.read_calls == [1]
    assert _Connection.instances[-1].calls.count("close") == 1


def _query_response_for(graph: Graph) -> _Response:
    canonical = make_store()._canonicalize_graph(graph)
    return _Response(
        headers=[
            ("Content-Type", "application/n-triples"),
            ("Content-Length", str(len(canonical))),
        ],
        body=canonical,
        status=200,
    )


def _two_connection_factory(responses: list[_Response]) -> object:
    index = 0

    def factory(host: str, port: int, timeout: float) -> _Connection:
        nonlocal index
        connection = _Connection(host, port, timeout)
        connection.response = responses[index]
        index += 1
        return connection

    return factory


def test_persist_dispatches_update_then_exact_query_and_confirms_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    graph = make_graph()
    monkeypatch.setattr(
        cast(Any, fuseki_store).http.client,
        "HTTPConnection",
        _two_connection_factory([_Response(), _query_response_for(graph)]),
    )
    assert cast(Any, make_store().persist(graph)) is None
    assert len(_Connection.instances) == 2
    assert _Connection.instances[0].calls.count("endheaders") == 1
    assert _Connection.instances[1].calls.count("endheaders") == 1
    assert _Connection.instances[1].request_calls == [
        (("POST", "/query"), {"skip_host": True, "skip_accept_encoding": True})
    ]
    assert _Connection.instances[1].header_calls[1:3] == [
        ("Content-Type", "application/sparql-query; charset=utf-8"),
        ("Accept", "application/n-triples"),
    ]


def test_persist_accepts_socket_closed_after_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch)
    _Connection.close_socket_after_response = True
    graph = make_graph()
    monkeypatch.setattr(
        cast(Any, fuseki_store).http.client,
        "HTTPConnection",
        _two_connection_factory([_Response(), _query_response_for(graph)]),
    )

    assert cast(Any, make_store().persist(graph)) is None
    assert _Connection.instances[0].sock is None


def test_resolve_requires_exact_id_and_expected_root_before_query_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store()
    graph = make_graph()

    class StringSubclass(str):
        pass

    monkeypatch.setattr(
        cast(Any, fuseki_store).http.client,
        "HTTPConnection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("I/O")),
    )
    with pytest.raises(TypeError):
        store.resolve(StringSubclass("https://example.test/trace/1"), graph)
    with pytest.raises(ValueError):
        store.resolve("https://example.test/other", graph)


def test_query_lexical_rejection_happens_before_rdflib_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Graph,
        "parse",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("parser")),
    )
    for body in [
        b"# comment\n",
        b"\n",
        b'<https://example.test/s> <https://example.test/p> "x" .',
        b'\xef\xbb\xbf<https://example.test/s> <https://example.test/p> "x" .\n',
    ]:
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
            fuseki_store._parse_query_body(
                body, make_store()._canonicalize_graph(make_graph()), make_store().config
            )


def test_query_body_parser_accepts_canonical_roundtrip() -> None:
    graph = make_graph()
    canonical = make_store()._canonicalize_graph(graph)
    parsed = fuseki_store._parse_query_body(canonical, canonical, make_store().config)
    assert make_store()._canonicalize_graph(parsed) == canonical


def test_query_dispatch_rejects_response_defects_after_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = make_graph()
    cases = [
        _Response(status=204),
        _Response(headers=[("Content-Length", "0")], status=200),
        _Response(
            headers=[("Content-Type", "application/n-triples"), ("Content-Length", "1")],
            body=b"",
            status=200,
        ),
        _Response(
            headers=[("Content-Type", "application/n-triples")],
            body=b"# comment\n",
            status=200,
        ),
    ]
    for response in cases:
        _patch_transport(monkeypatch)
        monkeypatch.setattr(
            cast(Any, fuseki_store).http.client,
            "HTTPConnection",
            _two_connection_factory([_Response(), response]),
        )
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
            make_store().persist(graph)
        assert len(_Connection.instances) == 2
        assert all(connection.calls.count("close") == 1 for connection in _Connection.instances)


def test_query_dispatch_parser_ordinary_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    graph = make_graph()
    response = _query_response_for(graph)
    monkeypatch.setattr(
        cast(Any, fuseki_store).http.client,
        "HTTPConnection",
        _two_connection_factory([_Response(), response]),
    )
    monkeypatch.setattr(
        fuseki_store,
        "_parse_query_body",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret")),
    )
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store().persist(graph)
    assert "secret" not in format_exc()
    assert exc_info.value.__cause__ is None


def test_prepared_query_contains_exact_wire_fields() -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())
    prepared = store._prepare_query("https://example.test/trace/1", canonical)
    assert prepared.request_line == b"POST /query HTTP/1.1\r\n"
    assert prepared.header_bytes.endswith(b"Connection: close\r\n\r\n")
    assert (
        prepared.wire_bytes == prepared.request_line + prepared.header_bytes + prepared.query_body
    )


def test_direct_resolve_dispatches_one_query_and_returns_fresh_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch)
    graph = make_graph()
    response = _query_response_for(graph)

    def factory(host: str, port: int, timeout: float) -> _Connection:
        connection = _Connection(host, port, timeout)
        connection.response = response
        return connection

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", factory)
    result = make_store().resolve("https://example.test/trace/1", graph)
    assert result is not graph
    assert make_store()._canonicalize_graph(result) == make_store()._canonicalize_graph(graph)
    assert len(_Connection.instances) == 1


@pytest.mark.parametrize("language", [True, False])
def test_query_scanner_accepts_multibyte_language_and_datatype(language: bool) -> None:
    graph = make_graph()
    subject = URIRef("https://example.test/s")
    predicate = URIRef("https://example.test/p")
    object_ = (
        Literal("é", lang="en-US")
        if language
        else Literal("x", datatype=URIRef("https://example.test/type"))
    )
    graph.add((subject, predicate, object_))
    body = make_store()._canonicalize_graph(graph)
    assert fuseki_store._parse_query_body(body, body, make_store().config)


def test_query_scanner_rejects_invalid_unicode_escape_before_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Graph, "parse", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("parser"))
    )
    body = b'<https://example.test/s> <https://example.test/p> "\\uD800" .\n'
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._parse_query_body(
            body, make_store()._canonicalize_graph(make_graph()), make_store().config
        )


@pytest.mark.parametrize(
    "body",
    [
        b"bad\n",
        b"<https://example.test/s> <https://example.test/p> <bad space> .\n",
        b'<https://example.test/s> <https://example.test/p> "x\\q" .\n',
        b'<https://example.test/s> <https://example.test/p> "x"@bad--tag .\n',
        b'<https://example.test/s> <https://example.test/p> "x"^^<relative> .\n',
        b'<https://example.test/s> <https://example.test/p> "x" .',
        b'<https://example.test/s> <https://example.test/p> "x" .\r\n',
    ],
)
def test_query_scanner_rejects_malformed_terms_before_parse(
    body: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        Graph, "parse", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("parser"))
    )
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._parse_query_body(
            body, make_store()._canonicalize_graph(make_graph()), make_store().config
        )


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Type", "application/n-triples")],
        [("Content-Type", "application/n-triples; charset=utf-8"), ("X-Test", "é")],
        [("Content-Type", "application/n-triples"), ("Content-Length", "1")],
        [("Content-Type", "application/n-triples"), ("Content-Length", "01")],
        [("Content-Type", "application/n-triples"), ("Content-Length", "-1")],
        [
            ("Content-Type", "application/n-triples"),
            ("Content-Length", "1"),
            ("content-length", "1"),
        ],
    ],
)
def test_query_header_contract_is_exact(headers: list[tuple[str, str]]) -> None:
    valid = headers == [("Content-Type", "application/n-triples")]
    valid |= headers[0][1] == "application/n-triples; charset=utf-8" and len(headers) == 2
    valid |= headers == [
        ("Content-Type", "application/n-triples"),
        ("Content-Length", "1"),
    ]
    if valid:
        result = fuseki_store._validate_query_headers(headers)
        assert result is None or result == 1
    else:
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
            fuseki_store._validate_query_headers(headers)


@pytest.mark.parametrize("failure", ["connect", "request", "endheaders", "getresponse", "close"])
def test_persist_query_transport_failures_remain_dispatched_unknown(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _patch_transport(monkeypatch)
    graph = make_graph()
    response = _query_response_for(graph)
    index = 0

    def factory(host: str, port: int, timeout: float) -> _Connection:
        nonlocal index
        connection = _Connection(host, port, timeout)
        connection.response = _Response() if index == 0 else response
        if index == 1:
            connection.failure = failure
        index += 1
        return connection

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", factory)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store().persist(graph)
    assert exc_info.value.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert _Connection.instances[-1].calls.count("close") == 1


@pytest.mark.parametrize(
    "field",
    [
        "graph_iri",
        "query_body",
        "request_path",
        "authority",
        "host",
        "port",
        "request_line",
        "header_bytes",
        "wire_bytes",
    ],
)
def test_drifted_query_fields_are_rejected_before_connection(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())
    prepared = store._prepare_query("https://example.test/trace/1", canonical)
    replacement: object = True if field == "port" else (1 if field == "query_body" else "drift")
    if field in {"query_body", "request_line", "header_bytes", "wire_bytes"}:
        replacement = b"drift"
    object.__setattr__(prepared, field, replacement)

    class NoConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("connection reached")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", NoConnection)
    with pytest.raises((TypeError, ValueError)):
        store._dispatch_query(prepared, 10_000.0, canonical)


def test_query_dispatch_rejects_expected_graph_drift_before_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())
    prepared = store._prepare_query("https://example.test/trace/1", canonical)

    class NoConnection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("connection reached")

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", NoConnection)
    with pytest.raises(ValueError):
        store._dispatch_query(prepared, 10_000.0, canonical + b"x")


def test_query_rejects_wrong_prepared_type_before_connection() -> None:
    with pytest.raises(TypeError):
        make_store()._dispatch_query(cast(Any, object()), 10_000.0, b"x")


@pytest.mark.parametrize("failure", ["factory", "timeout"])
def test_persist_query_factory_failures_are_dispatched_unknown(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _patch_transport(monkeypatch)
    graph = make_graph()
    response = _query_response_for(graph)
    calls = 0

    def factory(host: str, port: int, timeout: float) -> _Connection:
        nonlocal calls
        calls += 1
        if calls == 2:
            if failure == "timeout":
                raise TimeoutError("secret")
            raise _TransportFailure("secret")
        connection = _Connection(host, port, timeout)
        connection.response = response
        return connection

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", factory)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store().persist(graph)
    assert exc_info.value.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN


def test_query_validation_rejects_malformed_expected_canonical_without_io() -> None:
    config = FusekiProvenanceStoreConfig(UPDATE, QUERY, BASE)
    canonical = make_store()._canonicalize_graph(make_graph())
    prepared = make_store()._prepare_query("https://example.test/trace/1", canonical)
    object.__setattr__(prepared, "expected_graph", b"not nt")
    with pytest.raises(ValueError):
        fuseki_store._validate_prepared_query(prepared, config)


@pytest.mark.parametrize("headers", [None, {}, [("bad name", "x")], [("X", "\x01")], [("X", "€")]])
def test_query_headers_reject_shapes_controls_and_non_latin1(headers: object) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_query_headers(headers)


def test_remaining_validation_boundaries_and_exact_internal_types() -> None:
    with pytest.raises(TypeError):
        fuseki_store.FusekiProvenanceTransportError(
            cast(Any, "phase"), fuseki_store.DispatchState.NOT_DISPATCHED
        )
    with pytest.raises(TypeError):
        fuseki_store.FusekiProvenanceTransportError(
            fuseki_store._TransportPhase.BODY, cast(Any, "state")
        )
    with pytest.raises((TypeError, ValueError)):
        fuseki_store._validate_endpoint(1, "endpoint")
    with pytest.raises(ValueError):
        fuseki_store._validate_endpoint("http://127.0.0.1:1/u?x", "endpoint")
    with pytest.raises(TypeError):
        fuseki_store._validate_iri(1, "iri", 10)
    with pytest.raises(ValueError):
        fuseki_store._validate_iri("relative", "iri", 100)
    with pytest.raises(TypeError):
        fuseki_store._validate_timeout(True)
    with pytest.raises(ValueError):
        fuseki_store._validate_timeout(0)


def test_prepared_query_constructor_checks_every_exact_field() -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())
    prepared = store._prepare_query("https://example.test/trace/1", canonical)
    fields = {
        "expected_graph": "bad",
        "graph_iri": b"bad",
        "query_body": "bad",
        "request_path": b"bad",
        "authority": b"bad",
        "host": b"bad",
        "port": True,
        "request_line": "bad",
        "header_bytes": "bad",
        "wire_bytes": "bad",
    }
    for field, value in fields.items():
        with pytest.raises(TypeError):
            cast(Any, replace)(prepared, **{field: value})


def test_uncovered_small_failure_helpers_are_exercised() -> None:
    with pytest.raises(TypeError):
        fuseki_store._snapshot_config(cast(Any, object()))
    with pytest.raises(TimeoutError):
        fuseki_store._remaining_timeout(0.0)
    ok, result = fuseki_store._capture_call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert not ok and isinstance(result, RuntimeError)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers([("X", "v")] * 33)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._validate_response_headers([("Content-Length", "1")])
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._scan_nt_line(b"<https://example.test/s> <https://example.test/p> .\n")


def _direct_query_connection(
    monkeypatch: pytest.MonkeyPatch,
    response: _Response,
) -> None:
    _patch_transport(monkeypatch)

    def factory(host: str, port: int, timeout: float) -> _Connection:
        connection = _Connection(host, port, timeout)
        connection.response = response
        return connection

    monkeypatch.setattr(cast(Any, fuseki_store).http.client, "HTTPConnection", factory)


@pytest.mark.parametrize("endpoint", [UPDATE, "http://[::1]:3030/update"])
def test_real_query_dispatch_emits_exact_prepared_wire_for_ipv4_and_ipv6(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    query_endpoint = endpoint.replace("/update", "/query")
    store = FusekiProvenanceStore(FusekiProvenanceStoreConfig(endpoint, query_endpoint, BASE))
    graph = make_graph()
    canonical = store._canonicalize_graph(graph)
    prepared = store._prepare_query("https://example.test/trace/1", canonical)
    _direct_query_connection(monkeypatch, _query_response_for(graph))
    monkeypatch.setenv("http_proxy", "http://attacker.invalid:9")

    result = store._dispatch_query(
        prepared, cast(Any, fuseki_store).time.monotonic() + 5.0, canonical
    )

    assert store._canonicalize_graph(result) == canonical
    assert len(_Connection.instances) == 1
    connection = _Connection.instances[0]
    assert connection.request_calls == [
        (("POST", "/query"), {"skip_host": True, "skip_accept_encoding": True})
    ]
    captured_headers = b"".join(
        f"{name}: {value}\r\n".encode("ascii") for name, value in connection.header_calls
    )
    captured = b"POST /query HTTP/1.1\r\n" + captured_headers + b"\r\n" + connection.bodies[0]
    assert captured == prepared.wire_bytes
    assert prepared.query_body.count(prepared.graph_iri.encode("ascii")) == 1
    assert b"GRAPH ?g" not in prepared.query_body
    assert connection.calls.count("endheaders") == 1
    assert connection.calls.count("close") == 1


def test_query_wire_uses_utf8_for_valid_non_ascii_graph_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_base = "https://example.test/прованс"
    store = FusekiProvenanceStore(FusekiProvenanceStoreConfig(UPDATE, QUERY, graph_base))
    graph = make_graph()
    canonical = store._canonicalize_graph(graph)
    _direct_query_connection(monkeypatch, _query_response_for(graph))

    prepared = store._prepare_query("https://example.test/trace/1", canonical)
    result = store._dispatch_query(
        prepared, cast(Any, fuseki_store).time.monotonic() + 5.0, canonical
    )

    assert graph_base.encode("utf-8") in prepared.query_body
    assert store._canonicalize_graph(result) == canonical


@pytest.mark.parametrize("operation", ["update", "query"])
def test_multibyte_endpoint_path_uses_utf8_percent_encoded_request_target(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_endpoint = "http://127.0.0.1:3030/é" if operation == "update" else UPDATE
    query_endpoint = "http://127.0.0.1:3030/é" if operation == "query" else QUERY
    store = FusekiProvenanceStore(
        FusekiProvenanceStoreConfig(update_endpoint, query_endpoint, BASE)
    )
    graph = make_graph()
    canonical = store._canonicalize_graph(graph)
    _patch_transport(monkeypatch)
    prepared: Any

    if operation == "update":
        prepared = store._prepare_update(graph)
        monkeypatch.setattr(
            cast(Any, fuseki_store).http.client,
            "HTTPConnection",
            _two_connection_factory([_Response()]),
        )
        store._dispatch_prepared(prepared)
    else:
        prepared = store._prepare_query("https://example.test/trace/1", canonical)
        _direct_query_connection(monkeypatch, _query_response_for(graph))
        store._dispatch_query(prepared, cast(Any, fuseki_store).time.monotonic() + 5.0, canonical)

    assert prepared.request_path == "/%C3%A9"
    assert prepared.request_line == b"POST /%C3%A9 HTTP/1.1\r\n"
    assert _Connection.instances[-1].request_calls == [
        (("POST", "/%C3%A9"), {"skip_host": True, "skip_accept_encoding": True})
    ]


@pytest.mark.parametrize(
    ("headers", "accepted"),
    [
        ([("Content-Type", "application/n-triples")] + [(f"X-{i}", "v") for i in range(31)], True),
        ([("Content-Type", "application/n-triples")] + [(f"X-{i}", "v") for i in range(32)], False),
        ([("Content-Type", "application/n-triples"), ("X", "a" * 16_340)], True),
        ([("Content-Type", "application/n-triples"), ("X", "a" * 16_341)], False),
        ([("Content-Type", "Application/N-Triples")], False),
        ([("content-type", "application/n-triples; charset=utf-8")], True),
        ([("Content-Type", "application/n-triples"), ("Transfer-Encoding", "chunked")], True),
        ([("Content-Type", "application/n-triples"), ("Transfer-Encoding", "CHUNKED")], True),
        (
            [
                ("Content-Type", "application/n-triples"),
                ("Transfer-Encoding", "chunked"),
                ("Transfer-Encoding", "chunked"),
            ],
            False,
        ),
        (
            [
                ("Content-Type", "application/n-triples"),
                ("Transfer-Encoding", "gzip"),
            ],
            False,
        ),
        (
            [
                ("Content-Type", "application/n-triples"),
                ("Transfer-Encoding", "chunked"),
                ("Content-Length", "1"),
            ],
            False,
        ),
        ([("Content-Type", "application/n-triples"), ("Content-Encoding", "gzip")], False),
        (
            [
                ("Content-Type", "application/n-triples"),
                ("Content-Length", "0"),
                ("content-length", "0"),
            ],
            False,
        ),
    ],
)
def test_real_query_dispatch_enforces_header_contract(
    headers: list[tuple[str, str]], accepted: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = make_graph()
    canonical = make_store()._canonicalize_graph(graph)
    response = _Response(headers=headers, body=canonical, status=200)
    _direct_query_connection(monkeypatch, response)

    if accepted:
        assert make_store().resolve("https://example.test/trace/1", graph)
    else:
        with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
            make_store().resolve("https://example.test/trace/1", graph)
        assert exc_info.value.phase is fuseki_store._TransportPhase.HEADERS
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__context__ is None
    assert len(_Connection.instances) == 1
    assert _Connection.instances[0].calls.count("close") == 1


def test_query_content_length_over_limit_rejected_before_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = make_graph()
    response = _Response(
        headers=[
            ("Content-Type", "application/n-triples"),
            ("Content-Length", "1048577"),
        ],
        body=b"secret-body",
        status=200,
    )
    _direct_query_connection(monkeypatch, response)

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        make_store().resolve("https://example.test/trace/1", graph)
    assert response.read_calls == []


@pytest.mark.parametrize(
    "line",
    [
        b"<relative> <https://example.test/p> <https://example.test/o> .\n",
        b"<https://example.test/s> <relative> <https://example.test/o> .\n",
        b"<https://example.test/s> <https://example.test/p> <relative> .\n",
        b"<https://example.test/s> <https://example.test/p> <https://example.test/o> extra .\n",
        b"<https://example.test/s>  <https://example.test/p> <https://example.test/o> .\n",
    ],
)
def test_query_scanner_rejects_noncanonical_iri_and_separator_surfaces(line: bytes) -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._scan_nt_line(line)


def test_query_decode_parse_and_snapshot_failures_are_causeless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as decode_info:
        fuseki_store._parse_query_body(b"\xff\n", canonical, store.config)
    assert decode_info.value.__cause__ is None
    assert decode_info.value.__context__ is None

    def fail_parse(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("secret-parser")

    monkeypatch.setattr(Graph, "parse", fail_parse)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as parse_info:
        fuseki_store._parse_query_body(canonical, canonical, store.config)
    assert "secret-parser" not in format_exc()
    assert parse_info.value.__cause__ is None
    assert parse_info.value.__context__ is None


def test_query_snapshot_failure_is_causeless(monkeypatch: pytest.MonkeyPatch) -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())

    def fail_snapshot(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("secret-snapshot")

    monkeypatch.setattr(FusekiProvenanceStore, "_snapshot_graph", fail_snapshot)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        fuseki_store._parse_query_body(canonical, canonical, store.config)
    assert "secret-snapshot" not in format_exc()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize("defect", ["status", "headers", "read", "body-type", "body-over"])
def test_real_query_response_defects_are_sanitized_and_bounded(
    defect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = make_graph()
    response = _query_response_for(graph)

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError(f"secret-{defect}")

    if defect == "status":

        class BadStatus(_Response):
            @property
            def status(self) -> object:
                return fail()

        response = BadStatus(
            headers=response.headers,
            body=response.body,
        )
    elif defect == "headers":
        monkeypatch.setattr(response, "getheaders", fail)
    elif defect == "read":
        monkeypatch.setattr(response, "read", fail)
    elif defect == "body-type":
        response.body = bytearray(cast(bytes, response.body))
    else:
        response.body = b"x" * 1_048_577
    _direct_query_connection(monkeypatch, response)

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store().resolve("https://example.test/trace/1", graph)
    assert f"secret-{defect}" not in format_exc()
    assert exc_info.value.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert _Connection.instances[-1].calls.count("close") == 1
    if defect in {"body-type", "body-over"}:
        assert response.read_calls == [1_048_577]


def test_query_header_encoding_failure_is_causeless() -> None:
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        fuseki_store._validate_query_headers(
            [("Content-Type", "application/n-triples"), ("X", "€")]
        )
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_query_parser_base_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())

    def fail_parse(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise _TransportBase("base-parser")

    monkeypatch.setattr(Graph, "parse", fail_parse)
    with pytest.raises(_TransportBase):
        fuseki_store._parse_query_body(canonical, canonical, store.config)


def test_query_parser_accepts_reordered_equivalent_triples() -> None:
    store = make_store()
    graph = make_graph(count=2)
    canonical = store._canonicalize_graph(graph)
    reordered = b"".join(reversed(canonical.splitlines(keepends=True)))

    parsed = fuseki_store._parse_query_body(reordered, canonical, store.config)

    assert store._canonicalize_graph(parsed) == canonical


def test_query_parser_enforces_line_count_expected_type_and_exact_manifest() -> None:
    store = make_store()
    canonical = store._canonicalize_graph(make_graph())
    line = b"<https://example.test/s> <https://example.test/p> <https://example.test/o> .\n"

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError):
        fuseki_store._parse_query_body(line * 257, canonical, store.config)
    with pytest.raises(TypeError, match="canonical bytes"):
        fuseki_store._parse_query_body(canonical, cast(Any, make_graph()), store.config)
    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        fuseki_store._parse_query_body(canonical, canonical + b"x", store.config)
    assert exc_info.value.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN


@pytest.mark.parametrize("variant", ["missing", "extra", "foreign", "conflicting"])
def test_persist_rejects_nonidentical_complete_readback_on_real_path(
    variant: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = make_graph(count=2)
    returned = Graph()
    for triple in graph:
        returned.add(triple)
    root = URIRef("https://example.test/trace/1")
    predicate = URIRef("https://example.test/p/0")
    if variant == "missing":
        returned.remove((root, predicate, None))
    elif variant == "extra":
        returned.add((root, URIRef("https://example.test/extra"), Literal("extra")))
    elif variant == "foreign":
        returned.add(
            (
                URIRef("https://example.test/foreign"),
                URIRef("https://example.test/p"),
                Literal("foreign"),
            )
        )
    else:
        returned.remove((root, predicate, None))
        returned.add((root, predicate, Literal("conflict")))
    _patch_transport(monkeypatch)
    monkeypatch.setattr(
        cast(Any, fuseki_store).http.client,
        "HTTPConnection",
        _two_connection_factory([_Response(), _query_response_for(returned)]),
    )

    with pytest.raises(fuseki_store.FusekiProvenanceTransportError) as exc_info:
        make_store().persist(graph)

    assert exc_info.value.state is fuseki_store.DispatchState.DISPATCHED_UNKNOWN
    assert len(_Connection.instances) == 2
    assert all(connection.calls.count("endheaders") == 1 for connection in _Connection.instances)
    assert all(connection.calls.count("close") == 1 for connection in _Connection.instances)
