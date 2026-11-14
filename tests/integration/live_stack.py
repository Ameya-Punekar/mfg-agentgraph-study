"""Live proof for the Issue #114 deployment envelope.

This file is intentionally not named ``test_*.py`` so the default suite never
touches a container runtime. It is an explicit live proof only: every transport
call is real HTTP against the inherited ``MFG_*`` endpoints, every container
operation goes through the configured Docker CLI, and nothing falls back to a
default service address or a fixture.

Operator contract (nothing here has an incidental default)::

    cp deploy/env.example deploy/.env     # set MFG_FUSEKI_ADMIN_PASSWORD and ports
    export MFG_FUSEKI_URL=http://127.0.0.1:<port>
    export MFG_QDRANT_URL=http://127.0.0.1:<port>
    export MFG_OLLAMA_URL=http://127.0.0.1:<port>   # never assumed to be 11434
    export MFG_STACK_DOCKER=docker          # or docker.exe under WSL2
    export MFG_STACK_COMPOSE_PROJECT=mfg-agentgraph-live
    export MFG_AGENTGRAPH_LIVE_STACK=1
    uv run pytest tests/integration/live_stack.py -m integration

The first test performs the documented idempotent bootstrap from the committed
factory TriG and the packaged SHACL shapes, so a freshly started stack needs no
manual bootstrap step.

``MFG_STACK_DOCKER`` selects the Docker CLI; when it names a ``.exe`` binary the
compose file path is converted with ``wslpath`` so Windows Docker can read it.
``MFG_STACK_COMPOSE_PROJECT`` isolates the compose project. The service ports are
never assumed: they come only from the three ``MFG_*_URL`` variables above.
Force-recreate re-reads the compose interpolation variables, so export the same
``MFG_FUSEKI_PORT``/``MFG_QDRANT_PORT``/``MFG_OLLAMA_PORT`` values and
``MFG_FUSEKI_ADMIN_PASSWORD`` that started the stack.

The persistence proof creates one uniquely named RDF marker and one uniquely
identified Qdrant point (with a deterministic, caller-supplied probe vector; it
is never presented as an embedding), force-recreates only the Fuseki and Qdrant
containers while keeping their named volumes, and then re-reads the exact values.
Cleanup deletes only those two markers.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast
from urllib.parse import quote

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.term import Node

from mfg_agentgraph.shacl_validation import load_recommended_action_shapes
from mfg_agentgraph.stack_bootstrap import (
    BootstrapReport,
    BootstrapSources,
    StepOutcome,
    bootstrap_stack,
    named_graph_from_trig,
)
from mfg_agentgraph.stack_config import StackConfig, load_stack_config
from mfg_agentgraph.stack_preflight import TransportError, UrllibTransport, run_preflight

pytestmark = pytest.mark.integration

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
_COMPOSE: Final = _REPOSITORY_ROOT / "deploy" / "compose.yaml"
# The same factory source the ``mfg-agentgraph-stack bootstrap`` default uses.
_FACTORY_TRIG: Final = _REPOSITORY_ROOT / "tests" / "fixtures" / "fuseki" / "pump12.trig"

_LIVE_FLAG: Final = "MFG_AGENTGRAPH_LIVE_STACK"
_DOCKER_ENV: Final = "MFG_STACK_DOCKER"
_COMPOSE_PROJECT_ENV: Final = "MFG_STACK_COMPOSE_PROJECT"
# The live proof never guesses a service address from StackConfig defaults.
_ENDPOINT_ENV: Final = ("MFG_FUSEKI_URL", "MFG_QDRANT_URL", "MFG_OLLAMA_URL")

_PREFLIGHT_TIMEOUT_SECONDS: Final = 30.0
_BOOTSTRAP_TIMEOUT_SECONDS: Final = 600.0
_MARKER_TIMEOUT_SECONDS: Final = 30.0
_COMPOSE_QUERY_TIMEOUT_SECONDS: Final = 60.0
_COMPOSE_RECREATE_TIMEOUT_SECONDS: Final = 300.0
_WSLPATH_TIMEOUT_SECONDS: Final = 30.0
_READY_DEADLINE_SECONDS: Final = 240.0
_POLL_SECONDS: Final = 2.0

_CORE_SERVICES: Final = frozenset({"fuseki", "qdrant"})
_OLLAMA_SERVICES: Final = frozenset({"ollama", "ollama-gpu"})
_PREFLIGHT_IDENTITY_CHECKS: Final = (
    "fuseki_version",
    "qdrant_version",
    "ollama_version",
    "ollama_models",
)

_MARKER_VALUE_PREDICATE: Final = URIRef("urn:mfg-agentgraph:marker:value")
_MARKER_ORIGIN_PREDICATE: Final = URIRef("urn:mfg-agentgraph:marker:origin")
_MARKER_ORIGIN: Final = "issue-114-live-stack"

_TURTLE: Final = "text/turtle"
_SPARQL_QUERY: Final = "application/sparql-query"
_SPARQL_UPDATE: Final = "application/sparql-update"
_JSON: Final = "application/json"


def _require_live_stack() -> StackConfig:
    if os.environ.get(_LIVE_FLAG) != "1":
        pytest.fail(f"{_LIVE_FLAG}=1 must be set for the live stack test")
    missing = [name for name in _ENDPOINT_ENV if not os.environ.get(name, "").strip()]
    if missing:
        pytest.fail(
            "live stack selected but these endpoint variables are unset: "
            + ", ".join(missing)
            + "; this proof never falls back to a default endpoint"
        )
    return load_stack_config()


def _report_detail(report: BootstrapReport) -> str:
    return "; ".join(f"{step.name}: {step.outcome.value}: {step.detail}" for step in report.steps)


def _sources(config: StackConfig) -> BootstrapSources:
    factory_graph = named_graph_from_trig(_FACTORY_TRIG.read_bytes(), config.factory_graph)
    shapes_graph = load_recommended_action_shapes()
    assert len(factory_graph) > 0, "the committed factory TriG source is empty"
    assert len(shapes_graph) > 0, "the packaged SHACL shapes source is empty"
    return BootstrapSources(factory_graph=factory_graph, shapes_graph=shapes_graph)


# ---------------------------------------------------------------------------
# Docker CLI / compose helpers
# ---------------------------------------------------------------------------


def _docker_executable() -> str:
    return os.environ.get(_DOCKER_ENV, "").strip() or "docker"


def _require_docker() -> str:
    executable = _docker_executable()
    if shutil.which(executable) is None:
        pytest.fail(
            f"live stack selected but the Docker CLI {executable!r} is not on PATH; "
            f"set {_DOCKER_ENV} (for example docker.exe under WSL2)"
        )
    return executable


def _run_process(
    command: Sequence[str], *, description: str, timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        pytest.fail(f"{description}: executable {command[0]!r} was not found")
    except subprocess.TimeoutExpired:
        pytest.fail(f"{description} exceeded its {timeout_seconds:.0f}s bound")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        pytest.fail(f"{description} exited {completed.returncode}: {detail[-2000:]}")
    return completed


def _compose_file(docker: str) -> str:
    if os.name != "nt" and Path(docker).name.lower().endswith(".exe"):
        completed = _run_process(
            ["wslpath", "-w", str(_COMPOSE)],
            description="wslpath conversion of deploy/compose.yaml",
            timeout_seconds=_WSLPATH_TIMEOUT_SECONDS,
        )
        converted = completed.stdout.strip()
        if not converted:
            pytest.fail("wslpath returned an empty path for deploy/compose.yaml")
        return converted
    return str(_COMPOSE)


def _compose_prefix(docker: str) -> list[str]:
    prefix = [docker, "compose", "-f", _compose_file(docker)]
    project = os.environ.get(_COMPOSE_PROJECT_ENV, "").strip()
    if project:
        prefix.extend(["-p", project])
    return prefix


def _compose_service_records(stdout: str) -> dict[str, dict[str, object]]:
    text = stdout.strip()
    if not text:
        return {}
    entries: list[object]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        entries = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                pytest.fail(f"docker compose ps returned an unreadable JSON line: {stripped!r}")
    else:
        entries = parsed if isinstance(parsed, list) else [parsed]
    records: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            pytest.fail(f"docker compose ps returned a non-object record: {entry!r}")
        service = entry.get("Service")
        if not isinstance(service, str) or not service:
            pytest.fail(f"docker compose ps record has no service name: {entry!r}")
        records[service] = entry
    return records


def _compose_ps_records(docker: str) -> dict[str, dict[str, object]]:
    completed = _run_process(
        [*_compose_prefix(docker), "ps", "--format", "json"],
        description="docker compose ps",
        timeout_seconds=_COMPOSE_QUERY_TIMEOUT_SECONDS,
    )
    return _compose_service_records(completed.stdout)


def _record_health(record: Mapping[str, object]) -> object:
    # Compose 2.24+ exposes ``Health``; older 2.x versions only carry the
    # rendered ``Status`` (``Up 2 minutes (healthy)``).
    health = record.get("Health")
    if isinstance(health, str) and health:
        return health
    status = record.get("Status")
    if isinstance(status, str) and "(healthy)" in status:
        return "healthy"
    return health


def _compose_stack_is_healthy(records: Mapping[str, Mapping[str, object]]) -> bool:
    has_core = set(records) >= _CORE_SERVICES
    has_one_ollama = len(_OLLAMA_SERVICES & set(records)) == 1
    return (
        has_core
        and has_one_ollama
        and all(
            record.get("State") == "running" and _record_health(record) == "healthy"
            for record in records.values()
        )
    )


def _wait_for_compose_health(docker: str) -> dict[str, dict[str, object]]:
    deadline = time.monotonic() + _READY_DEADLINE_SECONDS
    while True:
        records = _compose_ps_records(docker)
        if not records:
            pytest.fail(
                "docker compose ps reports no containers for the selected project; "
                f"set {_COMPOSE_PROJECT_ENV} to the project that runs the stack"
            )
        if _compose_stack_is_healthy(records):
            return records
        if time.monotonic() >= deadline:
            return records
        time.sleep(_POLL_SECONDS)


def _container_ids(docker: str, services: Sequence[str]) -> tuple[str, ...]:
    completed = _run_process(
        [*_compose_prefix(docker), "ps", "-q", *services],
        description=f"docker compose ps -q {' '.join(services)}",
        timeout_seconds=_COMPOSE_QUERY_TIMEOUT_SECONDS,
    )
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def _force_recreate_containers(docker: str) -> None:
    # ``--force-recreate`` without ``--renew-anon-volumes`` replaces the
    # containers and keeps the named volumes that hold the graph and vectors.
    _run_process(
        [
            *_compose_prefix(docker),
            "up",
            "-d",
            "--force-recreate",
            "--no-deps",
            "fuseki",
            "qdrant",
        ],
        description="docker compose up --force-recreate fuseki qdrant",
        timeout_seconds=_COMPOSE_RECREATE_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# Runs first: it performs the documented idempotent bootstrap, so a freshly
# started stack has the graphs, the collection and the pinned models that the
# preflight test below verifies.
def test_bootstrap_is_idempotent_on_a_live_stack() -> None:
    config = _require_live_stack()
    transport = UrllibTransport(timeout_seconds=_BOOTSTRAP_TIMEOUT_SECONDS)
    sources = _sources(config)

    first = bootstrap_stack(config, transport, sources)
    assert first.ok, _report_detail(first)

    second = bootstrap_stack(config, transport, sources)
    assert second.ok, _report_detail(second)
    assert len(second.steps) == len(first.steps)
    not_already_present = [
        (step.name, step.outcome.value, step.detail)
        for step in second.steps
        if step.outcome is not StepOutcome.ALREADY_PRESENT
    ]
    assert not not_already_present, (
        "the second bootstrap run did not report every step as "
        f"{StepOutcome.ALREADY_PRESENT.value}: {not_already_present}"
    )


def test_compose_health_and_pinned_identities() -> None:
    config = _require_live_stack()
    docker = _require_docker()

    records = _wait_for_compose_health(docker)
    active = frozenset(records)
    missing = _CORE_SERVICES - active
    assert not missing, f"no running {sorted(missing)} service; active services: {sorted(active)}"
    ollama = _OLLAMA_SERVICES & active
    assert len(ollama) == 1, (
        f"expected exactly one active Ollama service, found {sorted(ollama)}; "
        f"active services: {sorted(active)}"
    )
    for name in sorted(active):
        record = records[name]
        health = _record_health(record)
        assert record.get("State") == "running", f"{name} state is {record.get('State')!r}"
        assert health == "healthy", f"{name} health is {health!r}"

    report = run_preflight(config, UrllibTransport(timeout_seconds=_PREFLIGHT_TIMEOUT_SECONDS))
    assert report.ok, "; ".join(f"{check.name}: {check.detail}" for check in report.failures)

    checks = {check.name: check for check in report.checks}
    for name in _PREFLIGHT_IDENTITY_CHECKS:
        check = checks.get(name)
        assert check is not None, f"preflight did not report the {name} check"
        assert check.ok, f"{name} failed: {check.detail}"
    version_pins = {
        "fuseki_version": config.fuseki_version,
        "qdrant_version": config.qdrant_version,
        "ollama_version": config.ollama_version,
    }
    for name, pin in version_pins.items():
        assert pin in checks[name].detail, (
            f"{name} detail {checks[name].detail!r} does not name the pinned version {pin!r}"
        )


def test_force_recreate_preserves_graph_and_point_markers() -> None:
    config = _require_live_stack()
    docker = _require_docker()

    bootstrap_transport = UrllibTransport(timeout_seconds=_BOOTSTRAP_TIMEOUT_SECONDS)
    report = bootstrap_stack(config, bootstrap_transport, _sources(config))
    assert report.ok, _report_detail(report)

    transport = UrllibTransport(timeout_seconds=_MARKER_TIMEOUT_SECONDS)
    token = uuid.uuid4().hex
    marker = URIRef(f"urn:mfg-agentgraph:marker:restart-proof:{token}")
    point_id = str(uuid.uuid4())
    vector = _probe_vector(config.embedding_dimension)
    payload: dict[str, object] = {
        "marker": token,
        "vector_origin": "caller_supplied_deterministic_probe",
        "vector_dimension": config.embedding_dimension,
    }
    expected_marker: set[tuple[Node, Node, Node]] = {
        (marker, _MARKER_VALUE_PREDICATE, Literal(token)),
        (marker, _MARKER_ORIGIN_PREDICATE, Literal(_MARKER_ORIGIN)),
    }

    succeeded = False
    try:
        _write_marker(config, transport, marker, token)
        _upsert_point(config, transport, point_id, vector, payload)

        before = _container_ids(docker, ("fuseki", "qdrant"))
        assert len(before) == 2 and all(before), f"expected two containers, found {before!r}"

        _force_recreate_containers(docker)

        after = _container_ids(docker, ("fuseki", "qdrant"))
        assert len(after) == 2 and all(after), f"expected two containers, found {after!r}"
        assert set(after).isdisjoint(before), (
            f"the containers were not replaced; ids before {before!r}, ids after {after!r}"
        )

        _wait_for_http(
            transport,
            config.fuseki.url("/$/ping"),
            description="Fuseki ping",
        )
        _wait_for_http(transport, config.qdrant.url("/healthz"), description="Qdrant healthz")

        _wait_for_marker(config, transport, marker, expected_marker)
        _wait_for_point(config, transport, point_id, payload, vector)
        succeeded = True
    finally:
        # Remove only the two markers; the stack's named volumes stay untouched.
        cleanup_errors: list[str] = []
        try:
            _delete_point(config, transport, point_id)
        except Exception as exc:  # noqa: BLE001 - reported after a passing body
            cleanup_errors.append(f"point marker cleanup failed: {exc}")
        try:
            _delete_marker(config, transport, marker)
        except Exception as exc:  # noqa: BLE001 - reported after a passing body
            cleanup_errors.append(f"RDF marker cleanup failed: {exc}")
        if succeeded and cleanup_errors:
            pytest.fail("; ".join(cleanup_errors))


# ---------------------------------------------------------------------------
# Fuseki marker helpers
# ---------------------------------------------------------------------------


def _write_marker(
    config: StackConfig, transport: UrllibTransport, marker: URIRef, token: str
) -> None:
    graph = Graph()
    graph.add((marker, _MARKER_VALUE_PREDICATE, Literal(token)))
    graph.add((marker, _MARKER_ORIGIN_PREDICATE, Literal(_MARKER_ORIGIN)))
    url = config.fuseki.url(
        f"/{config.fuseki_dataset}/data?graph={quote(config.provenance_graph, safe='')}"
    )
    response = transport.post(
        url,
        body=graph.serialize(format="turtle").encode(),
        content_type=_TURTLE,
    )
    assert response.status in {200, 201, 204}, f"marker write returned HTTP {response.status}"


def _read_marker(
    config: StackConfig, transport: UrllibTransport, marker: URIRef
) -> set[tuple[Node, Node, Node]]:
    query = (
        "CONSTRUCT { <"
        + str(marker)
        + "> ?p ?o } WHERE { GRAPH <"
        + config.provenance_graph
        + "> { <"
        + str(marker)
        + "> ?p ?o } }"
    )
    response = transport.post(
        config.fuseki_query_url(),
        body=query.encode(),
        content_type=_SPARQL_QUERY,
        headers={"Accept": _TURTLE},
    )
    assert response.status == 200, f"marker read returned HTTP {response.status}"
    graph = Graph()
    graph.parse(data=response.body, format="turtle")
    return {(subject, predicate, obj) for subject, predicate, obj in graph}


def _delete_marker(config: StackConfig, transport: UrllibTransport, marker: URIRef) -> None:
    update = (
        "DELETE WHERE { GRAPH <" + config.provenance_graph + "> { <" + str(marker) + "> ?p ?o } }"
    )
    response = transport.post(
        config.fuseki.url(f"/{config.fuseki_dataset}/update"),
        body=update.encode(),
        content_type=_SPARQL_UPDATE,
    )
    assert response.status in {200, 204}, f"marker delete returned HTTP {response.status}"


# ---------------------------------------------------------------------------
# Qdrant marker helpers
# ---------------------------------------------------------------------------


def _probe_vector(dimension: int) -> list[float]:
    # A deterministic, caller-supplied probe vector: it is not an embedding and
    # no model produced it.
    return [(index + 1) / 256.0 for index in range(dimension)]


def _unit(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


def _same_direction(observed: object, expected: Sequence[float]) -> bool:
    """Return whether a stored vector matches the probe up to Cosine scaling.

    A collection created with ``Cosine`` distance normalizes vectors on write, so
    Qdrant returns the unit vector rather than the exact values that were sent.
    Comparing direction proves the stored point is this probe, which is what the
    persistence test claims; it does not claim Qdrant stores raw bytes.
    """

    if not isinstance(observed, list) or len(observed) != len(expected):
        return False
    for got, want in zip(observed, _unit(expected), strict=True):
        if isinstance(got, bool) or not isinstance(got, (int, float)):
            return False
        if not math.isclose(float(got), want, rel_tol=1e-4, abs_tol=1e-9):
            return False
    return True


def _points_url(config: StackConfig, suffix: str = "") -> str:
    return config.qdrant.url(f"/collections/{config.qdrant_collection}/points{suffix}")


def _upsert_point(
    config: StackConfig,
    transport: UrllibTransport,
    point_id: str,
    vector: Sequence[float],
    payload: Mapping[str, object],
) -> None:
    body = json.dumps(
        {"points": [{"id": point_id, "vector": list(vector), "payload": dict(payload)}]}
    ).encode()
    response = transport.put(_points_url(config, "?wait=true"), body=body, content_type=_JSON)
    assert response.status in {200, 202}, f"point upsert returned HTTP {response.status}"


def _request_point(
    config: StackConfig, transport: UrllibTransport, point_id: str
) -> dict[str, object] | None:
    body = json.dumps({"ids": [point_id], "with_payload": True, "with_vector": True}).encode()
    response = transport.post(_points_url(config), body=body, content_type=_JSON)
    if response.status == 404:
        return None
    assert response.status == 200, f"point read returned HTTP {response.status}"
    document = cast(object, json.loads(response.body))
    assert isinstance(document, dict), "point read did not return a JSON object"
    result = document.get("result")
    assert isinstance(result, list), f"point read returned {result!r}"
    if not result:
        return None
    assert len(result) == 1, f"point read returned {result!r}"
    point = result[0]
    assert isinstance(point, dict), "point read did not return a point object"
    return cast(dict[str, object], point)


def _delete_point(config: StackConfig, transport: UrllibTransport, point_id: str) -> None:
    body = json.dumps({"points": [point_id]}).encode()
    response = transport.post(
        _points_url(config, "/delete?wait=true"), body=body, content_type=_JSON
    )
    assert response.status in {200, 202}, f"point delete returned HTTP {response.status}"


# ---------------------------------------------------------------------------
# Readiness helper
# ---------------------------------------------------------------------------


def _wait_for_marker(
    config: StackConfig,
    transport: UrllibTransport,
    marker: URIRef,
    expected: set[tuple[Node, Node, Node]],
) -> None:
    deadline = time.monotonic() + _READY_DEADLINE_SECONDS
    observed: set[tuple[Node, Node, Node]] = set()
    while time.monotonic() < deadline:
        try:
            observed = _read_marker(config, transport, marker)
        except TransportError:
            pass
        else:
            if observed == expected:
                return
        time.sleep(_POLL_SECONDS)
    pytest.fail(
        f"marker graph {marker} did not survive the container replacement; observed {observed!r}"
    )


def _wait_for_point(
    config: StackConfig,
    transport: UrllibTransport,
    point_id: str,
    expected_payload: Mapping[str, object],
    expected_vector: Sequence[float],
) -> None:
    deadline = time.monotonic() + _READY_DEADLINE_SECONDS
    observed: dict[str, object] | None = None
    while time.monotonic() < deadline:
        try:
            point = _request_point(config, transport, point_id)
        except TransportError:
            point = None
        if (
            point is not None
            and point.get("id") == point_id
            and point.get("payload") == expected_payload
            and _same_direction(point.get("vector"), expected_vector)
        ):
            return
        observed = point
        time.sleep(_POLL_SECONDS)
    pytest.fail(
        f"point {point_id} did not survive the container replacement; observed {observed!r}"
    )


def _wait_for_http(
    transport: UrllibTransport,
    url: str,
    *,
    description: str,
    expected_body: bytes | None = None,
) -> None:
    deadline = time.monotonic() + _READY_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        try:
            response = transport.get(url)
        except TransportError:
            pass
        else:
            if response.status == 200 and (expected_body is None or expected_body in response.body):
                return
        time.sleep(_POLL_SECONDS)
    pytest.fail(
        f"{description} at {url} did not become ready within {_READY_DEADLINE_SECONDS:.0f}s"
    )
