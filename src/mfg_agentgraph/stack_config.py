"""Validated configuration for the free local deployment envelope (Issue #114).

This module is the single place where service endpoints are constructed. Every
client in this package still receives an explicit URL; the posture is that the
application layer supplies loopback endpoints from :class:`StackConfig` rather
than accepting operator input. A non-loopback host is rejected unless the caller
opts in explicitly.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from urllib.parse import quote, urlsplit

LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})

_SUPPORTED_SCHEMES: Final = frozenset({"http", "https"})
_DIGEST_RE: Final = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NAME_RE: Final = re.compile(r"[A-Za-z0-9_-]+\Z")
_IRI_RE: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:\S+\Z")
_VERSION_RE: Final = re.compile(r"[0-9][0-9A-Za-z.+-]*\Z")

DEFAULT_FUSEKI_PORT: Final = 3030
DEFAULT_QDRANT_PORT: Final = 6333
DEFAULT_OLLAMA_PORT: Final = 11434
DEFAULT_FUSEKI_DATASET: Final = "ds"
# The pinned image's assembler publishes the query service under the name
# "sparql" (fuseki:serviceQuery "sparql"), not the Fuseki default "query".
DEFAULT_FUSEKI_QUERY_SERVICE: Final = "sparql"
DEFAULT_FUSEKI_ADMIN_USERNAME: Final = "admin"
DEFAULT_QDRANT_COLLECTION: Final = "procedural"
# The collection identity includes its metric, not only its width: a collection
# of the right size with a different distance silently changes score semantics.
DEFAULT_QDRANT_DISTANCE: Final = "Cosine"
DEFAULT_FACTORY_GRAPH: Final = "urn:mfg-agentgraph:graph:factory"
DEFAULT_SHAPES_GRAPH: Final = "urn:mfg-agentgraph:graph:shapes"
DEFAULT_PROVENANCE_GRAPH: Final = "urn:mfg-agentgraph:graph:provenance"
DEFAULT_GENERATION_MODEL: Final = "qwen2.5:7b-instruct-q4_K_M"
DEFAULT_GENERATION_MODEL_DIGEST: Final = (
    "sha256:845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"
)
DEFAULT_EMBEDDING_MODEL: Final = "nomic-embed-text"
DEFAULT_EMBEDDING_MODEL_DIGEST: Final = (
    "sha256:0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"
)
DEFAULT_EMBEDDING_DIMENSION: Final = 768
# A cold model pull transfers several gigabytes, so it never shares the short
# readiness timeout.
DEFAULT_PULL_TIMEOUT_SECONDS: Final = 3600.0
DEFAULT_FUSEKI_VERSION: Final = "6.2.0"
DEFAULT_QDRANT_VERSION: Final = "1.19.2"
DEFAULT_OLLAMA_VERSION: Final = "0.23.2"

_MAX_EMBEDDING_DIMENSION: Final = 4096


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must not be blank")
    return text


@dataclass(frozen=True, slots=True)
class ServiceEndpoint:
    """One validated service endpoint on the local envelope."""

    scheme: str
    host: str
    port: int

    def __post_init__(self) -> None:
        scheme = _require_text(self.scheme, "scheme").lower()
        if scheme not in _SUPPORTED_SCHEMES:
            raise ValueError("scheme must be http or https")
        host = _require_text(self.host, "host")
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if any(character in host for character in "/?#@ \t"):
            raise ValueError("host must not contain a path, credentials or whitespace")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        object.__setattr__(self, "scheme", scheme)
        object.__setattr__(self, "host", host)

    @property
    def authority(self) -> str:
        """Return the network authority, bracketing an IPv6 host."""

        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    @property
    def is_loopback(self) -> bool:
        """Return whether the endpoint is confined to the local machine."""

        return self.host in LOOPBACK_HOSTS

    def url(self, path: str = "") -> str:
        """Return an absolute URL for ``path`` on this endpoint."""

        if path and not path.startswith("/"):
            raise ValueError("path must start with '/'")
        return f"{self.scheme}://{self.authority}{path}"

    @classmethod
    def parse(cls, value: str) -> ServiceEndpoint:
        """Parse a base URL that carries no path, query, fragment or credentials."""

        text = _require_text(value, "endpoint")
        parts = urlsplit(text)
        if parts.scheme.lower() not in _SUPPORTED_SCHEMES:
            raise ValueError("endpoint must use http or https")
        if parts.username is not None or parts.password is not None:
            raise ValueError("endpoint must not contain credentials")
        if parts.path not in {"", "/"}:
            raise ValueError("endpoint must not contain a path")
        if parts.query or parts.fragment:
            raise ValueError("endpoint must not contain a query or fragment")
        if not parts.hostname:
            raise ValueError("endpoint must include a host")
        try:
            port = parts.port
        except ValueError as exc:
            raise ValueError("endpoint must contain a valid port") from exc
        if port is None:
            raise ValueError("endpoint must include an explicit port")
        return cls(parts.scheme, parts.hostname, port)


@dataclass(frozen=True, slots=True)
class ModelPin:
    """One pinned local Ollama model identity."""

    model_id: str
    digest: str

    def __post_init__(self) -> None:
        model_id = _require_text(self.model_id, "model_id")
        if any(character.isspace() for character in model_id):
            raise ValueError("model_id must not contain whitespace")
        digest = _require_text(self.digest, "digest")
        if _DIGEST_RE.fullmatch(digest) is None:
            raise ValueError("digest must be sha256: followed by 64 lowercase hex characters")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "digest", digest)

    @property
    def installed_name(self) -> str:
        """Return the name Ollama reports for this pin in ``/api/tags``."""

        return self.model_id if ":" in self.model_id else f"{self.model_id}:latest"


@dataclass(frozen=True, slots=True)
class StackConfig:
    """The one validated configuration object for the local stack."""

    fuseki: ServiceEndpoint
    qdrant: ServiceEndpoint
    ollama: ServiceEndpoint
    generation_model: ModelPin
    embedding_model: ModelPin
    fuseki_dataset: str = DEFAULT_FUSEKI_DATASET
    qdrant_collection: str = DEFAULT_QDRANT_COLLECTION
    factory_graph: str = DEFAULT_FACTORY_GRAPH
    shapes_graph: str = DEFAULT_SHAPES_GRAPH
    provenance_graph: str = DEFAULT_PROVENANCE_GRAPH
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    fuseki_query_service: str = DEFAULT_FUSEKI_QUERY_SERVICE
    admin_username: str = DEFAULT_FUSEKI_ADMIN_USERNAME
    # Never rendered by ``repr``: this value must not reach a log line.
    admin_password: str | None = field(default=None, repr=False)
    fuseki_version: str = DEFAULT_FUSEKI_VERSION
    qdrant_version: str = DEFAULT_QDRANT_VERSION
    ollama_version: str = DEFAULT_OLLAMA_VERSION
    allow_non_loopback: bool = False
    timeout_seconds: float = 5.0
    pull_timeout_seconds: float = DEFAULT_PULL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.allow_non_loopback, bool):
            raise TypeError("allow_non_loopback must be a boolean")
        for name, endpoint in (
            ("fuseki", self.fuseki),
            ("qdrant", self.qdrant),
            ("ollama", self.ollama),
        ):
            if not isinstance(endpoint, ServiceEndpoint):
                raise TypeError(f"{name} must be a ServiceEndpoint")
            if not endpoint.is_loopback and not self.allow_non_loopback:
                raise ValueError(
                    f"{name} host {endpoint.host!r} is not loopback; "
                    "the local envelope must stay on 127.0.0.1, ::1 or localhost"
                )
        for name in ("generation_model", "embedding_model"):
            if not isinstance(getattr(self, name), ModelPin):
                raise TypeError(f"{name} must be a ModelPin")
        dataset = _require_text(self.fuseki_dataset, "fuseki_dataset")
        if _NAME_RE.fullmatch(dataset) is None:
            raise ValueError("fuseki_dataset must be alphanumeric with _ or -")
        collection = _require_text(self.qdrant_collection, "qdrant_collection")
        if _NAME_RE.fullmatch(collection) is None:
            raise ValueError("qdrant_collection must be alphanumeric with _ or -")
        query_service = _require_text(self.fuseki_query_service, "fuseki_query_service")
        if _NAME_RE.fullmatch(query_service) is None:
            raise ValueError("fuseki_query_service must be alphanumeric with _ or -")
        object.__setattr__(self, "fuseki_query_service", query_service)
        object.__setattr__(
            self, "admin_username", _require_text(self.admin_username, "admin_username")
        )
        if self.admin_password is not None:
            if not isinstance(self.admin_password, str):
                raise TypeError("admin_password must be a string or None")
            if not self.admin_password.strip():
                raise ValueError("admin_password must not be blank when set")
        seen_graphs: dict[str, str] = {}
        for name in ("factory_graph", "shapes_graph", "provenance_graph"):
            iri = _require_text(getattr(self, name), name)
            if _IRI_RE.fullmatch(iri) is None:
                raise ValueError(f"{name} must be an absolute IRI")
            # Two roles on one named graph would make a bootstrap write compare two
            # different source graphs at the same URI, and a recreate could overwrite
            # the other role's data.
            if iri in seen_graphs:
                raise ValueError(f"{name} and {seen_graphs[iri]} must name different named graphs")
            seen_graphs[iri] = name
        if isinstance(self.embedding_dimension, bool) or not isinstance(
            self.embedding_dimension, int
        ):
            raise TypeError("embedding_dimension must be an integer")
        if not 1 <= self.embedding_dimension <= _MAX_EMBEDDING_DIMENSION:
            raise ValueError(
                f"embedding_dimension must be between 1 and {_MAX_EMBEDDING_DIMENSION}"
            )
        for name in ("fuseki_version", "qdrant_version", "ollama_version"):
            version = _require_text(getattr(self, name), name)
            if _VERSION_RE.fullmatch(version) is None:
                raise ValueError(f"{name} must be a version string")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, float):
            raise TypeError("timeout_seconds must be a float")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if isinstance(self.pull_timeout_seconds, bool) or not isinstance(
            self.pull_timeout_seconds, float
        ):
            raise TypeError("pull_timeout_seconds must be a float")
        if self.pull_timeout_seconds <= 0:
            raise ValueError("pull_timeout_seconds must be positive")

    def fuseki_query_url(self) -> str:
        """Return the dataset's published SPARQL query endpoint."""

        return self.fuseki.url(f"/{self.fuseki_dataset}/{self.fuseki_query_service}")

    def fuseki_data_url(self, graph_iri: str) -> str:
        """Return the Graph Store Protocol endpoint for one named graph."""

        return self.fuseki.url(f"/{self.fuseki_dataset}/data?graph={quote(graph_iri, safe='')}")

    def admin_auth_headers(self) -> dict[str, str]:
        """Return the basic-auth header for Fuseki's administrative endpoints."""

        if not self.admin_password:
            return {}
        credential = f"{self.admin_username}:{self.admin_password}".encode()
        return {"Authorization": f"Basic {base64.b64encode(credential).decode('ascii')}"}

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> StackConfig:
        """Build the configuration from ``MFG_*`` environment variables."""

        source = os.environ if environ is None else environ

        def endpoint(key: str, port_key: str, default_port: int) -> ServiceEndpoint:
            explicit = source.get(key)
            if explicit is not None:
                return ServiceEndpoint.parse(_require_text(explicit, key))
            # Compose publishes the loopback port from ``port_key``; deriving the
            # endpoint keeps one port input instead of two that can disagree.
            published = source.get(port_key)
            if published is None:
                return ServiceEndpoint("http", "127.0.0.1", default_port)
            return ServiceEndpoint("http", "127.0.0.1", int(_require_text(published, port_key)))

        def text(key: str, default: str) -> str:
            return _require_text(source.get(key, default), key)

        return cls(
            fuseki=endpoint("MFG_FUSEKI_URL", "MFG_FUSEKI_PORT", DEFAULT_FUSEKI_PORT),
            qdrant=endpoint("MFG_QDRANT_URL", "MFG_QDRANT_PORT", DEFAULT_QDRANT_PORT),
            ollama=endpoint("MFG_OLLAMA_URL", "MFG_OLLAMA_PORT", DEFAULT_OLLAMA_PORT),
            generation_model=ModelPin(
                text("MFG_GENERATION_MODEL", DEFAULT_GENERATION_MODEL),
                text("MFG_GENERATION_MODEL_DIGEST", DEFAULT_GENERATION_MODEL_DIGEST),
            ),
            embedding_model=ModelPin(
                text("MFG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
                text("MFG_EMBEDDING_MODEL_DIGEST", DEFAULT_EMBEDDING_MODEL_DIGEST),
            ),
            fuseki_dataset=text("MFG_FUSEKI_DATASET", DEFAULT_FUSEKI_DATASET),
            fuseki_query_service=text("MFG_FUSEKI_QUERY_SERVICE", DEFAULT_FUSEKI_QUERY_SERVICE),
            admin_username=text("MFG_FUSEKI_ADMIN_USERNAME", DEFAULT_FUSEKI_ADMIN_USERNAME),
            admin_password=(
                _require_text(source["MFG_FUSEKI_ADMIN_PASSWORD"], "MFG_FUSEKI_ADMIN_PASSWORD")
                if source.get("MFG_FUSEKI_ADMIN_PASSWORD")
                else None
            ),
            qdrant_collection=text("MFG_QDRANT_COLLECTION", DEFAULT_QDRANT_COLLECTION),
            embedding_dimension=int(
                text("MFG_EMBEDDING_DIMENSION", str(DEFAULT_EMBEDDING_DIMENSION))
            ),
            allow_non_loopback=text("MFG_ALLOW_NON_LOOPBACK", "false").lower() == "true",
            pull_timeout_seconds=float(
                text("MFG_OLLAMA_PULL_TIMEOUT_SECONDS", str(DEFAULT_PULL_TIMEOUT_SECONDS))
            ),
        )


# The documented operator file: `cp deploy/env.example deploy/.env`.
DEFAULT_ENV_FILE: Final = Path("deploy") / ".env"
_ENV_PREFIX: Final = "MFG_"


def _read_env_file(path: Path) -> dict[str, str]:
    """Read ``MFG_*`` assignments from one operator configuration file."""

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if not name.startswith(_ENV_PREFIX):
            continue
        text = value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1]
        values[name] = text
    return values


def load_stack_config(
    *,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> StackConfig:
    """Build the configuration from the environment, else from the operator file.

    A supplied ``environ`` is used verbatim, which keeps callers that own their
    inputs deterministic. Otherwise real environment variables override the
    values read from ``env_file`` (default ``deploy/.env`` in the current
    directory), so one file configures both Compose and these commands.
    """

    if environ is not None:
        return StackConfig.from_env(environ)
    path = DEFAULT_ENV_FILE if env_file is None else env_file
    file_values = _read_env_file(path) if path.exists() else {}
    return StackConfig.from_env({**file_values, **os.environ})
