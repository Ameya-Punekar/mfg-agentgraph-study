"""Command line for the versioned scenario-corpus release (Issue #115).

``verify`` validates a release and prints its identities. ``build`` writes the
canonical bytes of a validated release, and ``trig`` writes its graph
serialisation; both refuse to replace a frozen file with different content.
``load`` publishes the release into the corpus-context named graph using the same
idempotent, non-destructive bootstrap as the deployment CLI, so it can never
overwrite the factory or provenance graphs.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final

from rdflib import Dataset, Graph, URIRef

from mfg_agentgraph.corpus_release import (
    CONTEXT_GRAPH,
    ScenarioCorpus,
    build_corpus_release,
    corpus_to_trig,
    load_corpus_release,
)
from mfg_agentgraph.stack_bootstrap import (
    BootstrapReport,
    BootstrapSources,
    bootstrap_stack,
    named_graph_from_trig,
)
from mfg_agentgraph.stack_config import load_stack_config
from mfg_agentgraph.stack_preflight import HttpTransport, UrllibTransport

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
_FAILURE_TYPES: Final = (OSError, TypeError, ValueError)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mfg-agentgraph-corpus",
        description="Manage the versioned scenario-corpus release.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    verify = subcommands.add_parser("verify", help="validate a release and print its identities")
    verify.add_argument("release", type=Path, help="release JSON document")
    for name, help_text in (
        ("build", "write the canonical bytes of a validated release"),
        ("trig", "write the release graph serialisation"),
    ):
        writer = subcommands.add_parser(name, help=help_text)
        writer.add_argument("release", type=Path, help="release JSON document")
        writer.add_argument("--output", type=Path, required=True, help="file to write")
    load = subcommands.add_parser(
        "load", help="publish the release into the corpus-context named graph"
    )
    load.add_argument("release", type=Path, help="release JSON document")
    load.add_argument(
        "--recreate",
        action="store_true",
        help="replace a corpus graph whose content differs from the release",
    )
    return parser


def _print_release(corpus: ScenarioCorpus) -> None:
    print(f"corpus {corpus.corpus_id} {corpus.version}")
    print(f"documents {len(corpus.documents)}")
    print(f"assets {len(corpus.assets)}")
    print(f"observations {len(corpus.observations)}")
    print(f"identifier_only {len(corpus.identifier_only_observation_ids)}")
    print(f"procedures {len(corpus.procedures)}")
    print(f"chunks {len(corpus.chunks)}")
    print(f"queries {len(corpus.queries)} development")
    share_alike = corpus.share_alike_document_ids
    print("share_alike " + (", ".join(share_alike) if share_alike else "none"))
    print(f"sha256 {corpus.document_sha256}")
    print(f"development_sha256 {corpus.development_sha256}")


def _write_frozen(path: Path, payload: bytes) -> int:
    """Write ``payload`` unless the file already holds a different frozen release."""

    if path.exists():
        existing = path.read_bytes()
        if existing == payload:
            print(f"unchanged {path}")
            return 0
        print(
            f"refused {path} already holds a different frozen release; "
            "write a new version file instead of editing it"
        )
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    print(f"wrote {path} ({len(payload)} bytes)")
    return 0


def _graph_of(payload: bytes) -> Graph:
    dataset = Dataset()
    dataset.parse(data=payload.decode("utf-8"), format="trig")
    return dataset.graph(URIRef(CONTEXT_GRAPH))


def _write_frozen_graph(path: Path, payload: bytes) -> int:
    """Write ``payload`` unless the file already holds an equivalent graph.

    Serialisers do not order triples predictably, so the frozen identity of a
    graph release is its content, not its byte order.
    """

    if path.exists():
        existing = path.read_bytes()
        try:
            same = existing == payload or _graph_of(existing).isomorphic(_graph_of(payload))
        except Exception:  # noqa: BLE001 - an unparseable file is never "the same"
            same = False
        if same:
            print(f"unchanged {path}")
            return 0
        print(
            f"refused {path} already holds a different frozen release; "
            "write a new version file instead of editing it"
        )
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    print(f"wrote {path} ({len(payload)} bytes)")
    return 0


def _sources(corpus: ScenarioCorpus) -> BootstrapSources:
    """Return the single corpus graph this command is allowed to publish.

    ``load`` must not touch the shapes graph: reporting it would bootstraps a
    second named graph, and with ``--recreate`` could replace the stack's shapes.
    """

    return BootstrapSources(
        factory_graph=named_graph_from_trig(corpus_to_trig(corpus), CONTEXT_GRAPH),
        shapes_graph=Graph(),
    )


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
    """Run one corpus command and return its process exit code."""

    args = _build_parser().parse_args(argv)
    try:
        corpus = load_corpus_release(args.release)
    except _FAILURE_TYPES as exc:
        print(f"corpus error: {exc}")
        return 1

    if args.command == "verify":
        _print_release(corpus)
        return 0
    if args.command == "build":
        return _write_frozen(args.output, build_corpus_release(corpus.to_document()))
    if args.command == "trig":
        return _write_frozen_graph(args.output, corpus_to_trig(corpus))

    try:
        config = replace(
            load_stack_config(environ=environ, env_file=env_file), factory_graph=CONTEXT_GRAPH
        )
    except _FAILURE_TYPES as exc:
        print(f"configuration error: {exc}")
        return 1
    client = (
        transport
        if transport is not None
        else UrllibTransport(timeout_seconds=config.timeout_seconds)
    )
    try:
        report = bootstrap_stack(
            config,
            client,
            _sources(corpus),
            recreate=bool(args.recreate),
            include_shapes=False,
        )
    except _FAILURE_TYPES as exc:
        print(f"corpus error: {exc}")
        return 1
    _print_bootstrap(report)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
