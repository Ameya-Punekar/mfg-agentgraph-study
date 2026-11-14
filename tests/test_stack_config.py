"""Contract tests for the Issue #114 local stack configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from mfg_agentgraph.stack_config import (
    LOOPBACK_HOSTS,
    ModelPin,
    ServiceEndpoint,
    StackConfig,
    load_stack_config,
)

_VALID_DIGEST = "sha256:" + "a" * 64


def _config(**overrides: Any) -> StackConfig:
    fields: dict[str, Any] = {
        "fuseki": ServiceEndpoint("http", "127.0.0.1", 3030),
        "qdrant": ServiceEndpoint("http", "127.0.0.1", 6333),
        "ollama": ServiceEndpoint("http", "127.0.0.1", 11434),
        "generation_model": ModelPin("qwen2.5:7b-instruct-q4_K_M", _VALID_DIGEST),
        "embedding_model": ModelPin("nomic-embed-text", _VALID_DIGEST),
    }
    fields.update(overrides)
    return StackConfig(**fields)


def test_defaults_are_loopback_and_match_the_frozen_envelope() -> None:
    config = StackConfig.from_env({})

    assert config.fuseki.url() == "http://127.0.0.1:3030"
    assert config.qdrant.url() == "http://127.0.0.1:6333"
    assert config.ollama.url() == "http://127.0.0.1:11434"
    assert config.factory_graph == "urn:mfg-agentgraph:graph:factory"
    assert config.shapes_graph == "urn:mfg-agentgraph:graph:shapes"
    assert config.provenance_graph == "urn:mfg-agentgraph:graph:provenance"
    assert config.embedding_dimension == 768
    assert config.qdrant_collection == "procedural"
    assert config.generation_model.model_id == "qwen2.5:7b-instruct-q4_K_M"
    assert config.embedding_model.model_id == "nomic-embed-text"
    assert config.allow_non_loopback is False


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5", "192.168.1.20", "example.com"])
def test_non_loopback_host_is_rejected_by_default(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        _config(fuseki=ServiceEndpoint("http", host, 3030))


def test_allow_non_loopback_permits_a_remote_host() -> None:
    config = _config(
        fuseki=ServiceEndpoint("http", "10.0.0.5", 3030),
        allow_non_loopback=True,
    )

    assert config.fuseki.host == "10.0.0.5"


@pytest.mark.parametrize("host", sorted(LOOPBACK_HOSTS))
def test_every_declared_loopback_host_is_accepted(host: str) -> None:
    assert _config(fuseki=ServiceEndpoint("http", host, 3030)).fuseki.host == host


def test_environment_overrides_the_endpoint_port() -> None:
    config = StackConfig.from_env({"MFG_FUSEKI_URL": "http://127.0.0.1:3999"})

    assert config.fuseki.url() == "http://127.0.0.1:3999"


def test_unrelated_environment_keys_are_ignored() -> None:
    assert StackConfig.from_env({"PATH": "/usr/bin", "HOME": "/root"}).fuseki.port == 3030


def test_blank_environment_value_is_rejected() -> None:
    with pytest.raises(ValueError):
        StackConfig.from_env({"MFG_QDRANT_URL": "   "})


@pytest.mark.parametrize(
    "digest",
    ["", "sha256:", "md5:" + "a" * 32, "sha256:" + "A" * 64, "sha256:" + "a" * 63],
)
def test_invalid_model_digest_is_rejected(digest: str) -> None:
    with pytest.raises(ValueError):
        ModelPin("nomic-embed-text", digest)


@pytest.mark.parametrize("dimension", [0, -1, 5000])
def test_embedding_dimension_is_bounded(dimension: int) -> None:
    with pytest.raises(ValueError):
        _config(embedding_dimension=dimension)


@pytest.mark.parametrize("port", [0, -1, 70000, True])
def test_port_must_be_a_valid_integer(port: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        ServiceEndpoint("http", "127.0.0.1", port)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1:3030/path",
        "http://user:secret@127.0.0.1:3030",
        "http://127.0.0.1:3030?x=1",
        "http://127.0.0.1:3030#frag",
        "ftp://127.0.0.1:3030",
        "not-a-url",
    ],
)
def test_service_endpoint_parse_rejects_unsupported_urls(value: str) -> None:
    with pytest.raises(ValueError):
        ServiceEndpoint.parse(value)


def test_service_endpoint_parse_accepts_a_loopback_base_url() -> None:
    endpoint = ServiceEndpoint.parse("http://127.0.0.1:3030")

    assert endpoint == ServiceEndpoint("http", "127.0.0.1", 3030)


def test_service_endpoint_url_brackets_an_ipv6_host() -> None:
    endpoint = ServiceEndpoint("http", "::1", 3030)

    assert endpoint.url("/$/ping") == "http://[::1]:3030/$/ping"


@pytest.mark.parametrize("iri", ["factory", "graph/factory", "urn:mfg agent"])
def test_graph_iri_must_be_absolute(iri: str) -> None:
    with pytest.raises(ValueError):
        _config(factory_graph=iri)


def test_collection_name_rejects_path_characters() -> None:
    with pytest.raises(ValueError):
        _config(qdrant_collection="../etc")


def test_query_service_defaults_to_the_pinned_image_service_name() -> None:
    config = StackConfig.from_env({})

    assert config.fuseki_query_service == "sparql"
    assert config.fuseki_query_url() == "http://127.0.0.1:3030/ds/sparql"


def test_query_service_is_validated() -> None:
    with pytest.raises(ValueError):
        _config(fuseki_query_service="sparql/../etc")


def test_admin_credentials_are_optional_and_never_required() -> None:
    config = StackConfig.from_env({})

    assert config.admin_password is None
    assert config.admin_auth_headers() == {}


def test_admin_credentials_produce_a_basic_auth_header() -> None:
    config = _config(admin_password="s3cret")

    headers = config.admin_auth_headers()

    assert headers["Authorization"].startswith("Basic ")
    assert "s3cret" not in headers["Authorization"]


def test_admin_password_comes_from_the_environment() -> None:
    config = StackConfig.from_env({"MFG_FUSEKI_ADMIN_PASSWORD": "from-env"})

    assert config.admin_password == "from-env"


def test_a_published_port_derives_the_endpoint_when_no_url_is_given() -> None:
    config = StackConfig.from_env(
        {"MFG_FUSEKI_PORT": "23030", "MFG_QDRANT_PORT": "23333", "MFG_OLLAMA_PORT": "31434"}
    )

    assert config.fuseki.url() == "http://127.0.0.1:23030"
    assert config.qdrant.url() == "http://127.0.0.1:23333"
    assert config.ollama.url() == "http://127.0.0.1:31434"


def test_an_explicit_endpoint_url_wins_over_the_published_port() -> None:
    config = StackConfig.from_env(
        {"MFG_FUSEKI_URL": "http://127.0.0.1:3999", "MFG_FUSEKI_PORT": "23030"}
    )

    assert config.fuseki.url() == "http://127.0.0.1:3999"


@pytest.mark.parametrize("port", ["", "http", "0", "70000"])
def test_a_published_port_must_be_a_valid_port(port: str) -> None:
    with pytest.raises(ValueError):
        StackConfig.from_env({"MFG_QDRANT_PORT": port})


def test_the_operator_file_populates_the_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in tuple(os.environ):
        if name.startswith("MFG_"):
            monkeypatch.delenv(name)
    path = tmp_path / "env"
    path.write_text("MFG_QDRANT_PORT=23333\nMFG_FUSEKI_ADMIN_PASSWORD=s3cret\n", encoding="utf-8")

    config = load_stack_config(env_file=path)

    assert config.qdrant.url() == "http://127.0.0.1:23333"
    assert config.admin_password == "s3cret"


def test_a_supplied_mapping_ignores_the_operator_file(tmp_path: Path) -> None:
    path = tmp_path / "env"
    path.write_text("MFG_QDRANT_PORT=23333\n", encoding="utf-8")

    assert load_stack_config(environ={}, env_file=path).qdrant.port == 6333


def test_a_missing_operator_file_falls_back_to_the_pinned_defaults(tmp_path: Path) -> None:
    config = load_stack_config(environ={}, env_file=tmp_path / "absent")

    assert config.qdrant.port == 6333


def test_the_admin_password_never_appears_in_the_configuration_repr() -> None:
    config = _config(admin_password="s3cret")

    assert "s3cret" not in repr(config)


def test_the_cold_pull_timeout_defaults_to_a_multi_gigabyte_budget() -> None:
    config = StackConfig.from_env({})

    assert config.pull_timeout_seconds == 3600.0


def test_the_pull_timeout_comes_from_the_environment() -> None:
    config = StackConfig.from_env({"MFG_OLLAMA_PULL_TIMEOUT_SECONDS": "1800"})

    assert config.pull_timeout_seconds == 1800.0


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_the_pull_timeout_must_be_positive(value: float) -> None:
    with pytest.raises(ValueError):
        _config(pull_timeout_seconds=value)


def test_a_non_numeric_pull_timeout_is_rejected() -> None:
    with pytest.raises(ValueError):
        StackConfig.from_env({"MFG_OLLAMA_PULL_TIMEOUT_SECONDS": "soon"})


def test_two_graph_roles_may_not_share_one_named_graph() -> None:
    """Aliased roles would let one bootstrap step overwrite another's data."""

    with pytest.raises(ValueError, match="different named graphs"):
        _config(shapes_graph="urn:mfg-agentgraph:graph:factory")


def test_the_three_graph_roles_are_distinct_by_default() -> None:
    config = StackConfig.from_env({})

    assert len({config.factory_graph, config.shapes_graph, config.provenance_graph}) == 3
