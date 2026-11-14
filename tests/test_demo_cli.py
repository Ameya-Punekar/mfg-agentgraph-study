import os
import subprocess
import sysconfig
import tomllib
from pathlib import Path

import pytest

from mfg_agentgraph.demo_cli import main
from mfg_agentgraph.stage_instrumentation import StageName

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_EXPECTED_OUTPUT = """MFG-AgentGraph deterministic S4 demo
terminal_status: passed
recommendation: Inspect the pump inlet of Pump_12 for cavitation
evidence_package_id: ex:EvidencePackage_Pump12_001
provenance_id: ex:ProvenanceTrace_Pump12_001
stages:
01. entity_asset_resolution: passed
02. structured_retrieval: passed
03. procedural_retrieval: passed
04. candidate_generation: passed
05. rdf_reification: passed
06. shacl_validation: passed
07. bounded_repair: passed
08. explicit_fallback: passed
09. evidence_package_assembly: passed
10. prov_o_trace_writing: passed
"""


def test_main_prints_exact_deterministic_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert capsys.readouterr().out == _EXPECTED_OUTPUT


def test_repeated_runs_are_byte_identical(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    first = capsys.readouterr().out
    assert main() == 0
    second = capsys.readouterr().out

    assert first.encode() == second.encode()


def test_stage_summary_uses_exact_canonical_order(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main() == 0
    stage_lines = capsys.readouterr().out.splitlines()[6:]

    assert len(stage_lines) == 10
    assert tuple(line.split(". ", 1)[1].split(": ", 1)[0] for line in stage_lines) == tuple(
        stage.value for stage in StageName
    )
    assert all(line.endswith(": passed") for line in stage_lines)


def test_project_registers_demo_command() -> None:
    with (_REPOSITORY_ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    assert project["project"]["scripts"]["mfg-agentgraph-demo"] == ("mfg_agentgraph.demo_cli:main")


def test_registered_command_prints_exact_output() -> None:
    executable_name = "mfg-agentgraph-demo.exe" if os.name == "nt" else "mfg-agentgraph-demo"
    executable = Path(sysconfig.get_path("scripts")) / executable_name

    completed = subprocess.run(
        [str(executable)],
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout == _EXPECTED_OUTPUT
    assert completed.stderr == ""
