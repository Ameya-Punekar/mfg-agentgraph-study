"""Command line for the free local deployment envelope (Issue #114).

``mfg-agentgraph-stack doctor`` runs the read-only preflight and exits non-zero
on any mismatch. ``bootstrap`` loads the graphs, creates the collection and pins
the models. ``status`` prints the resolved configuration without touching the
network.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from rdflib import Graph
from rdflib.exceptions import ParserError

from mfg_agentgraph.stack_bootstrap import (
    BootstrapReport,
    BootstrapSources,
    bootstrap_stack,
    named_graph_from_trig,
)
from mfg_agentgraph.stack_config import DEFAULT_ENV_FILE, StackConfig, load_stack_config
from mfg_agentgraph.stack_preflight import HttpTransport, UrllibTransport, run_preflight

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
_DEFAULT_FACTORY_GRAPH: Final = _REPOSITORY_ROOT / "tests" / "fixtures" / "fuseki" / "pump12.trig"
_DEFAULT_SHAPES: Final = Path(__file__).resolve().parent / "shapes" / "recommended_action.ttl"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mfg-agentgraph-stack",
        description="Manage the pinned, free local deployment envelope.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="configuration file read when the process environment is absent "
        f"(default: {DEFAULT_ENV_FILE})",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor", help="verify endpoints, versions, digests and data")
    bootstrap = subcommands.add_parser("bootstrap", help="load graphs, collection and models")
    bootstrap.add_argument(
        "--factory-graph",
        default=str(_DEFAULT_FACTORY_GRAPH),
        help="TriG document holding the factory named graph",
    )
    bootstrap.add_argument(
        "--shapes",
        default=str(_DEFAULT_SHAPES),
        help="Turtle document holding the SHACL shapes",
    )
    bootstrap.add_argument(
        "--recreate",
        action="store_true",
        help="replace a graph (or collection) whose content differs from the source",
    )
    subcommands.add_parser("status", help="print the resolved configuration")
    return parser


def _print_status(config: StackConfig) -> None:
    print(
        f"fuseki    {config.fuseki.url()} dataset={config.fuseki_dataset} "
        f"version={config.fuseki_version}"
    )
    print(
        f"qdrant    {config.qdrant.url()} collection={config.qdrant_collection} "
        f"version={config.qdrant_version} size={config.embedding_dimension}"
    )
    print(f"ollama    {config.ollama.url()} version={config.ollama_version}")
    print(
        f"graphs    factory={config.factory_graph} shapes={config.shapes_graph} "
        f"provenance={config.provenance_graph}"
    )
    for pin in (config.generation_model, config.embedding_model):
        print(f"model     {pin.model_id} digest={pin.digest}")


def _load_sources(config: StackConfig, factory_path: Path, shapes_path: Path) -> BootstrapSources:
    factory = named_graph_from_trig(factory_path.read_bytes(), config.factory_graph)
    shapes = Graph()
    shapes.parse(shapes_path, format="turtle")
    return BootstrapSources(factory_graph=factory, shapes_graph=shapes)


def _print_bootstrap(report: BootstrapReport) -> None:
    for step in report.steps:
        print(f"{step.outcome.value:<14} {step.name}: {step.detail}")


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: HttpTransport | None = None,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> int:
    """Run one stack command and return its process exit code."""

    args = _build_parser().parse_args(argv)
    resolved_env_file: Path | None = args.env_file if args.env_file is not None else env_file
    try:
        config = load_stack_config(environ=environ, env_file=resolved_env_file)
    except (OSError, TypeError, ValueError) as exc:
        print(f"configuration error: {exc}")
        return 1

    if args.command == "status":
        _print_status(config)
        return 0

    client = (
        transport
        if transport is not None
        else UrllibTransport(timeout_seconds=config.timeout_seconds)
    )
    if args.command == "doctor":
        report = run_preflight(config, client)
        for check in report.checks:
            print(f"{'ok  ' if check.ok else 'FAIL'} {check.name}: {check.detail}")
        return report.exit_code

    try:
        sources = _load_sources(config, Path(args.factory_graph), Path(args.shapes))
    except (OSError, ValueError, ParserError) as exc:
        print(f"source error: {exc}")
        return 1
    bootstrap_report = bootstrap_stack(config, client, sources, recreate=bool(args.recreate))
    _print_bootstrap(bootstrap_report)
    return bootstrap_report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
