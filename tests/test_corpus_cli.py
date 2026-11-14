"""Contract tests for the Issue #115 corpus command line."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import pytest
from rdflib import Dataset, URIRef

from mfg_agentgraph.anomaly_triage_dataset import QueryCategory
from mfg_agentgraph.corpus_cli import main
from mfg_agentgraph.corpus_release import (
    CONTEXT_GRAPH,
    DEVELOPMENT_SPLIT,
    AcquisitionKind,
    CorpusAsset,
    CorpusChunk,
    CorpusDocument,
    CorpusObservation,
    CorpusProcedure,
    CorpusQuery,
    ExtractionRecord,
    LicenceBasis,
    LicenceRecord,
    Lineage,
    MachineType,
    RecordingReference,
    RelevanceTier,
    ScenarioCorpus,
)
from mfg_agentgraph.stack_config import (
    DEFAULT_EMBEDDING_MODEL_DIGEST,
    DEFAULT_GENERATION_MODEL_DIGEST,
)
from mfg_agentgraph.stack_preflight import HttpResponse

_SHA = "a" * 64
_TEXT_SHA = "b" * 64
_FACTORY_GRAPH = "urn:mfg-agentgraph:graph:factory"


def _corpus() -> ScenarioCorpus:
    return ScenarioCorpus(
        corpus_id="mimii-synthetic-context-v1",
        version="v1",
        documents=(
            CorpusDocument(
                document_id="doc:pump-handbook",
                title="Pump handbook",
                machine_types=(MachineType.PUMP,),
                licence=LicenceRecord(
                    identifier="us-government-work",
                    basis=LicenceBasis.PUBLIC_DOMAIN_STATUTORY,
                    terms_url="https://example.test/terms",
                    attribution="U.S. Government work",
                    allows_redistribution=True,
                    share_alike=False,
                ),
                acquisition=AcquisitionKind.BUNDLED_TEXT,
                source_uri="https://example.test/pump-handbook.pdf",
                source_sha256=_SHA,
                extraction=ExtractionRecord(
                    tool="pdftotext",
                    tool_version="24.02.0",
                    rule="full text, layout preserved",
                ),
                text_sha256=_TEXT_SHA,
                text_layer=True,
                relevance_tier=RelevanceTier.DIRECT,
            ),
        ),
        assets=(
            CorpusAsset(
                asset_id="asset:pump-01",
                machine_type=MachineType.PUMP,
                model_id="id_00",
                site_id="site:plant-a",
                display_name="Feed pump 01",
            ),
        ),
        observations=(
            CorpusObservation(
                observation_id="obs:pump-01-01",
                asset_id="asset:pump-01",
                label="abnormal",
                label_source="mimii_dataset_label",
                lineage=Lineage.MIMII_DERIVED,
                recording=RecordingReference(
                    dataset_record_id="3384388",
                    dataset_doi="10.5281/zenodo.3384388",
                    archive_key="6_dB_pump.zip",
                    member_path="pump/id_00/abnormal/00000000.wav",
                    member_crc32="15d80cef",
                    member_sha256=_SHA,
                    seconds=10.0,
                    sample_rate_hz=16000,
                    channels=8,
                    bits_per_sample=16,
                ),
            ),
        ),
        sensors=(),
        procedures=(
            CorpusProcedure(
                procedure_id="proc:pump-01-inspect",
                machine_type=MachineType.PUMP,
                asset_ids=("asset:pump-01",),
                lineage=Lineage.AUTHORED_CURATED,
                text="Inspect the inlet for cavitation.",
                evidence_chunk_ids=("chunk:pump-handbook-1",),
            ),
        ),
        chunks=(
            CorpusChunk(
                chunk_id="chunk:pump-handbook-1",
                document_id="doc:pump-handbook",
                ordinal=1,
                text="Inspect the inlet for cavitation. Check the discharge valve packing.",
                start_line=10,
                end_line=12,
                text_sha256=hashlib.sha256(
                    b"Inspect the inlet for cavitation. Check the discharge valve packing."
                ).hexdigest(),
            ),
        ),
        queries=(
            CorpusQuery(
                query_id="atq-101",
                category=QueryCategory.SINGLE_HOP,
                split=DEVELOPMENT_SPLIT,
                text="Which pump reported an anomalous sound?",
                expected_evidence_refs=("obs:pump-01-01",),
                expected_action=None,
                rubric="Names the pump and the observation time.",
            ),
        ),
    )


def _release_file(tmp_path: Path, corpus: ScenarioCorpus | None = None) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps((corpus or _corpus()).to_document(), indent=2), encoding="utf-8")
    return path


@dataclass
class _Transport:
    """Records every call and serves the documented stack responses."""

    calls: list[tuple[str, str]] = field(default_factory=list)
    bodies: list[bytes] = field(default_factory=list)
    existing_graph: bytes = b""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(("GET", url))
        if "/collections/" in url:
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "result": {
                            "config": {"params": {"vectors": {"size": 768, "distance": "Cosine"}}}
                        }
                    }
                ).encode(),
            )
        if url.endswith("/api/tags"):
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "models": [
                            {
                                "name": "qwen2.5:7b-instruct-q4_K_M",
                                "digest": DEFAULT_GENERATION_MODEL_DIGEST,
                            },
                            {
                                "name": "nomic-embed-text:latest",
                                "digest": DEFAULT_EMBEDDING_MODEL_DIGEST,
                            },
                        ]
                    }
                ).encode(),
            )
        return HttpResponse(200, b"turtle")

    def post(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(("POST", url))
        self.bodies.append(body)
        if url.endswith("/sparql"):
            return HttpResponse(200, self.existing_graph)
        return HttpResponse(204, b"")

    def put(
        self,
        url: str,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> HttpResponse:
        self.calls.append(("PUT", url))
        self.bodies.append(body)
        return HttpResponse(204, b"")


def test_verify_reports_digests_and_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _release_file(tmp_path)

    code = main(["verify", str(path)], transport=_Transport(), environ={})

    out = capsys.readouterr().out
    assert code == 0
    assert _corpus().document_sha256 in out
    assert _corpus().development_sha256 in out
    assert "documents 1" in out


def test_verify_fails_on_an_invalid_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = _corpus().to_document()
    document["queries"][0]["split"] = "held_out"  # type: ignore[index]
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    code = main(["verify", str(path)], transport=_Transport(), environ={})

    out = capsys.readouterr().out
    assert code == 1
    assert "development" in out


def test_build_writes_canonical_bytes_and_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _release_file(tmp_path)
    output = tmp_path / "built.json"

    first = main(
        ["build", str(source), "--output", str(output)], transport=_Transport(), environ={}
    )
    first_bytes = output.read_bytes()
    second = main(
        ["build", str(source), "--output", str(output)], transport=_Transport(), environ={}
    )
    out = capsys.readouterr().out

    assert first == 0
    assert second == 0
    assert output.read_bytes() == first_bytes
    assert "unchanged" in out


def test_build_refuses_to_replace_a_different_frozen_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _release_file(tmp_path)
    output = tmp_path / "built.json"
    output.write_text("frozen", encoding="utf-8")

    code = main(["build", str(source), "--output", str(output)], transport=_Transport(), environ={})

    out = capsys.readouterr().out
    assert code == 1
    assert "refused" in out.lower()
    assert output.read_text(encoding="utf-8") == "frozen"


def test_trig_writes_a_deterministic_graph(tmp_path: Path) -> None:
    source = _release_file(tmp_path)
    first = tmp_path / "first.trig"
    second = tmp_path / "second.trig"

    assert (
        main(["trig", str(source), "--output", str(first)], transport=_Transport(), environ={}) == 0
    )
    assert (
        main(["trig", str(source), "--output", str(second)], transport=_Transport(), environ={})
        == 0
    )

    assert first.read_bytes() == second.read_bytes()
    dataset = Dataset()
    dataset.parse(data=first.read_text(encoding="utf-8"), format="trig")
    assert len(dataset.graph(URIRef(CONTEXT_GRAPH))) > 0


def test_load_targets_only_the_corpus_context_graph(tmp_path: Path) -> None:
    source = _release_file(tmp_path)
    transport = _Transport()

    code = main(["load", str(source)], transport=transport, environ={})

    assert code == 0
    graph_urls = [url for _, url in transport.calls if "/ds/data?graph=" in url]
    assert graph_urls
    assert any(quote(CONTEXT_GRAPH, safe="") in url for url in graph_urls)
    assert not any(quote(_FACTORY_GRAPH, safe="") in url for url in graph_urls)
    assert not any(
        quote("urn:mfg-agentgraph:graph:provenance", safe="") in url for url in graph_urls
    )
    # A corpus load must never create or replace the stack's shapes graph.
    assert not any(quote("urn:mfg-agentgraph:graph:shapes", safe="") in url for url in graph_urls)
    assert not any("recommended_action.ttl" in str(step) for step in transport.calls)


def test_trig_write_accepts_an_equivalent_graph_in_a_different_order(tmp_path: Path) -> None:
    """A reordered serialisation describes the same release."""

    source = _release_file(tmp_path)
    target = tmp_path / "release.trig"
    assert main(["trig", str(source), "--output", str(target)], environ={}) == 0

    dataset = Dataset()
    dataset.parse(data=target.read_text(encoding="utf-8"), format="trig")
    reordered = Dataset()
    for prefix, namespace in dataset.namespaces():
        reordered.bind(prefix, namespace)
    graph = reordered.graph(URIRef(CONTEXT_GRAPH))
    for triple in reversed(sorted(dataset.graph(URIRef(CONTEXT_GRAPH)))):
        graph.add(triple)
    target.write_bytes(reordered.serialize(format="trig").encode())

    assert main(["trig", str(source), "--output", str(target)], environ={}) == 0


def test_load_reports_a_refusal_when_the_corpus_graph_diverges(tmp_path: Path) -> None:
    source = _release_file(tmp_path)
    transport = _Transport(
        existing_graph=b"<urn:s> <urn:p> <urn:o> .",
    )

    code = main(["load", str(source)], transport=transport, environ={})

    assert code == 1


def test_an_unknown_command_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["explode"], transport=_Transport(), environ={})

    assert excinfo.value.code == 2


def test_a_missing_release_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["verify", str(tmp_path / "absent.json")], transport=_Transport(), environ={})

    out = capsys.readouterr().out
    assert code == 1
    assert "corpus error" in out


def test_the_release_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text('{"contract_version": "a", "contract_version": "b"}', encoding="utf-8")

    code = main(["verify", str(path)], transport=_Transport(), environ={})

    assert code == 1
