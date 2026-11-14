"""Local CLI for the annotation and reference-label workflows.

Three subcommands keep each boundary explicit: ``packet`` writes the blinded packet an
annotator may see, ``agreement`` validates independent submissions against that exact
packet before reporting pre-adjudication agreement, and ``gold`` emits the versioned gold
artifact from frozen submissions. ``synthetic`` writes the separate, explicitly
non-independent synthetic-reference artifact, which is not gold.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mfg_agentgraph.annotation_sources import load_source_manifest
from mfg_agentgraph.anomaly_triage_dataset import load_query_set
from mfg_agentgraph.gold_annotation import (
    AgreementReport,
    AnnotationSubmission,
    build_agreement_report,
    build_annotation_packet,
    load_annotation_submission,
)
from mfg_agentgraph.human_gold import build_human_gold, load_adjudication_record
from mfg_agentgraph.synthetic_reference import (
    build_synthetic_reference,
    load_scenario_fixture,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mfg-agentgraph-annotate",
        description="Export the blinded annotation packet and report agreement.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    packet = subcommands.add_parser(
        "packet", help="write the blinded annotation packet for one query set"
    )
    packet.add_argument("--query-set", type=Path, required=True)
    packet.add_argument("--sources", type=Path, required=True, help="frozen source manifest")
    packet.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="root the manifest paths are relative to (default: current directory)",
    )
    packet.add_argument("--output", type=Path, required=True)

    agreement = subcommands.add_parser(
        "agreement", help="validate independent submissions and report agreement"
    )
    agreement.add_argument("--query-set", type=Path, required=True)
    agreement.add_argument("--sources", type=Path, required=True, help="frozen source manifest")
    agreement.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="root the manifest paths are relative to (default: current directory)",
    )
    agreement.add_argument(
        "--submission", type=Path, action="append", required=True, help="repeat per annotator"
    )
    agreement.add_argument("--output", type=Path, required=True)

    gold = subcommands.add_parser(
        "gold", help="emit the versioned human-gold artifact from frozen submissions"
    )
    gold.add_argument("--query-set", type=Path, required=True)
    gold.add_argument("--sources", type=Path, required=True, help="frozen source manifest")
    gold.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="root the manifest paths are relative to (default: current directory)",
    )
    gold.add_argument("--submission", type=Path, action="append", required=True)
    gold.add_argument("--adjudication", type=Path, required=True)
    gold.add_argument("--output", type=Path, required=True)

    synthetic = subcommands.add_parser(
        "synthetic",
        help="write the synthetic-reference artifact (not human gold)",
    )
    synthetic.add_argument("--query-set", type=Path, required=True)
    synthetic.add_argument("--sources", type=Path, required=True, help="frozen source manifest")
    synthetic.add_argument("--scenario", type=Path, required=True, help="frozen scenario fixture")
    synthetic.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="root the manifest paths are relative to (default: current directory)",
    )
    synthetic.add_argument("--output", type=Path, required=True)
    return parser


def _write_new_artifact(path: Path, text: str) -> None:
    """Create one new artifact, refusing to truncate an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation keeps the check and the write in one atomic step.
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as error:
        raise ValueError(f"refusing to overwrite existing annotation artifact {path}") from error


def _require_distinct_output(output: Path, inputs: Sequence[Path]) -> None:
    """Refuse an output path that is also one of the artifacts this run reads."""
    resolved = output.resolve()
    for candidate in inputs:
        if candidate.resolve() == resolved:
            raise ValueError(f"output path must not overwrite an input artifact {candidate}")


def _print_report(report: AgreementReport) -> None:
    print(f"annotators: {', '.join(report.annotator_ids)}")
    print(f"queries: {report.query_count}")
    print(f"unanimous support: {report.unanimous_support_query_count}")
    print(f"unanimous evidence: {report.unanimous_evidence_query_count}")
    for pair in report.pairs:
        first, second = pair.annotator_ids
        kappa = "undefined" if pair.cohen_kappa is None else f"{pair.cohen_kappa:.3f}"
        print(
            f"{first} vs {second}: support={pair.support_agreement_rate:.3f} kappa={kappa} "
            f"evidence_exact={pair.evidence_exact_match_rate:.3f} "
            f"evidence_jaccard={pair.evidence_mean_jaccard:.3f} "
            f"disagreements={len(pair.disagreement_query_ids)}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the packet export or agreement report against an explicit query set."""
    args = _build_parser().parse_args(argv)
    manifest = load_source_manifest(args.sources, root=args.root)

    if args.command == "synthetic":
        inputs = [args.query_set, args.sources, args.scenario]
        _require_distinct_output(args.output, inputs)
        reference = build_synthetic_reference(
            query_set=load_query_set(args.query_set),
            scenario=load_scenario_fixture(args.scenario),
            source_manifest=manifest,
        )
        _write_new_artifact(args.output, reference.to_json() + "\n")
        counts = ", ".join(
            f"{strength}={count}" for strength, count in reference.strength_counts.items()
        )
        print(
            f"wrote synthetic reference for {len(reference.entries)} queries to {args.output} "
            f"({counts}); this artifact is not human gold"
        )
        return 0

    packet = build_annotation_packet(load_query_set(args.query_set), manifest=manifest)
    if args.command == "packet":
        _require_distinct_output(args.output, [args.query_set, args.sources])
        _write_new_artifact(args.output, packet.to_json() + "\n")
        print(f"wrote blinded packet for {len(packet.queries)} queries to {args.output}")
        return 0

    inputs = [args.query_set, args.sources, *args.submission]
    if args.command == "gold":
        inputs.append(args.adjudication)
    _require_distinct_output(args.output, inputs)
    submissions: list[AnnotationSubmission] = [
        load_annotation_submission(path, packet=packet) for path in args.submission
    ]
    if args.command == "gold":
        gold = build_human_gold(
            query_set=load_query_set(args.query_set),
            packet=packet,
            submissions=submissions,
            adjudication=load_adjudication_record(args.adjudication),
        )
        _write_new_artifact(args.output, gold.to_json() + "\n")
        print(
            f"wrote human gold for {len(gold.queries)} queries from "
            f"{len(gold.annotator_ids)} annotators to {args.output}"
        )
        return 0

    report = build_agreement_report(submissions, packet=packet)
    _write_new_artifact(args.output, report.to_json() + "\n")
    _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
