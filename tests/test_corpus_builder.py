"""Behaviour tests for the versioned scenario-corpus builder (frozen v1, supplemental v2)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from rdflib import Dataset, URIRef

from mfg_agentgraph.corpus_release import (
    CONTEXT_GRAPH,
    AcquisitionKind,
    CorpusAsset,
    CorpusChunk,
    CorpusDocument,
    CorpusObservation,
    CorpusSensor,
    ExtractionRecord,
    LicenceBasis,
    LicenceRecord,
    Lineage,
    MachineType,
    RelevanceTier,
    ScenarioCorpus,
    build_corpus_release,
)

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_scenario_corpus.py"
_PAYLOAD = b"%PDF-1.4 supplemental valve manual fixture\n"
_OFFICIAL_URI = "https://example.test/official-valve-manual.pdf"
_REPLAY_URI = "https://web.archive.test/replay/valve-manual.pdf"
_SUPPLEMENT_ID = "doc:supplemental-valve-manual"
_SUPPLEMENT_TITLE = "Supplemental valve maintenance manual"
_SUPPLEMENT_TEXT = "Inspect the supplemental valve packing and check the gland for leakage."


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("build_scenario_corpus", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve postponed annotations through sys.modules, so the loaded
    # module must be registered before its body executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _base_corpus() -> ScenarioCorpus:
    text = "Inspect the pump inlet and check the discharge pressure."
    document = CorpusDocument(
        document_id="doc:base-handbook",
        title="Base handbook",
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
        source_uri="https://example.test/base-handbook.pdf",
        source_sha256="a" * 64,
        extraction=ExtractionRecord(tool="pdftotext", tool_version="26.01.0", rule="layout text"),
        text_sha256=_sha(text.encode("utf-8")),
        text_layer=True,
        relevance_tier=RelevanceTier.DIRECT,
    )
    chunk = CorpusChunk(
        chunk_id="chunk:base-handbook-c01",
        document_id="doc:base-handbook",
        ordinal=1,
        text=text,
        start_line=1,
        end_line=2,
        text_sha256=_sha(text.encode("utf-8")),
    )
    return ScenarioCorpus(
        corpus_id="mimii-synthetic-context-v1",
        version="v1",
        documents=(document,),
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
                observation_id="obs:pump-01-context",
                asset_id="asset:pump-01",
                label="abnormal",
                label_source="authored_context",
                lineage=Lineage.AUTHORED_CURATED,
            ),
        ),
        sensors=(),
        procedures=(),
        chunks=(chunk,),
        queries=(),
    )


def _entry(payload: bytes, **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "document_id": _SUPPLEMENT_ID,
        "title": _SUPPLEMENT_TITLE,
        "machine_types": ["valve"],
        "source_uri": _OFFICIAL_URI,
        "download_uri": _REPLAY_URI,
        "cache_name": "acquired/supplement.pdf",
        "source_sha256": _sha(payload),
        "basis": "public_domain_statutory",
        "terms_url": "https://example.test/terms",
        "attribution": "U.S. Government work",
        "allows_redistribution": True,
        "share_alike": False,
        "relevance_tier": "T2",
    }
    entry.update(overrides)
    return entry


@dataclass(frozen=True)
class _Layout:
    module: Any
    v1_dir: Path
    v2_dir: Path
    cache_dir: Path


def _layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    entries: list[dict[str, object]] | None = None,
    cache_payload: bytes = _PAYLOAD,
    write_cache: bool = True,
    pdftotext_version: str | None = "26.01.0",
) -> _Layout:
    module = _module()
    v1_dir = tmp_path / "release-v1"
    v2_dir = tmp_path / "release-v2"
    cache_dir = tmp_path / "cache" / "scenario-corpus"
    v1_dir.mkdir(parents=True)
    v2_dir.mkdir(parents=True)
    cache_dir.mkdir(parents=True)
    (v1_dir / "corpus-v1.json").write_bytes(build_corpus_release(_base_corpus().to_document()))
    if write_cache:
        cache_file = cache_dir / "acquired" / "supplement.pdf"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(cache_payload)
    manifest: dict[str, object] = {"documents": entries or [_entry(cache_payload)]}
    (v2_dir / "sources-v2.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(module, "RELEASE_DIR", v1_dir)
    monkeypatch.setattr(module, "RELEASE_DIR_V2", v2_dir)
    monkeypatch.setattr(module, "CACHE_DIR", cache_dir)
    # The production pins point at the real frozen releases; a fixture release is
    # frozen by its own digest, so the pin follows the fixture.
    monkeypatch.setattr(module, "_FROZEN_V1_DIGEST", _base_corpus().document_sha256)
    if pdftotext_version is not None:
        monkeypatch.setattr(module, "_require_pdftotext", lambda: pdftotext_version)
    return _Layout(module=module, v1_dir=v1_dir, v2_dir=v2_dir, cache_dir=cache_dir)


def _supplemental_document(
    spec: Any, path: Path, extraction_version: str
) -> tuple[CorpusDocument, list[CorpusChunk]]:
    document = CorpusDocument(
        document_id=spec.document_id,
        title=spec.title,
        machine_types=spec.machine_types,
        licence=LicenceRecord(
            identifier=spec.basis.value,
            basis=spec.basis,
            terms_url=spec.terms_url,
            attribution=spec.attribution,
            allows_redistribution=spec.allows_redistribution,
            share_alike=spec.share_alike,
        ),
        acquisition=AcquisitionKind.BUNDLED_TEXT,
        source_uri=spec.source_uri,
        source_sha256=_sha(path.read_bytes()),
        extraction=ExtractionRecord(
            tool="pdftotext", tool_version=extraction_version, rule="test extraction"
        ),
        text_sha256=_sha(_SUPPLEMENT_TEXT.encode("utf-8")),
        text_layer=True,
        relevance_tier=spec.relevance_tier,
    )
    chunk = CorpusChunk(
        chunk_id=f"{spec.document_id.replace('doc:', 'chunk:')}-c01",
        document_id=spec.document_id,
        ordinal=1,
        text=_SUPPLEMENT_TEXT,
        start_line=1,
        end_line=2,
        text_sha256=_sha(_SUPPLEMENT_TEXT.encode("utf-8")),
    )
    return document, [chunk]


def _install_fake_extraction(
    monkeypatch: pytest.MonkeyPatch, module: Any, *, chunks: bool = True
) -> None:
    def fake(
        spec: Any, path: Path, extraction_version: str
    ) -> tuple[CorpusDocument, list[CorpusChunk]]:
        document, produced = _supplemental_document(spec, path, extraction_version)
        return document, produced if chunks else []

    monkeypatch.setattr(module, "_document", fake)


def _reverse_trig_statements(payload: bytes) -> bytes:
    """Return the same TriG graph with its independent statement groups reversed."""

    text = payload.decode("utf-8")
    opening = text.index("{\n") + 2
    closing = text.rindex("\n}")
    body = text[opening:closing]
    if not body.endswith("\n"):
        body += "\n"
    groups: list[str] = []
    current: list[str] = []
    for line in body.splitlines(keepends=True):
        current.append(line)
        if line.rstrip().endswith(" ."):
            groups.append("".join(current))
            current = []
    if current:
        groups.append("".join(current))
    reversed_body = "".join(reversed(groups)).rstrip("\n")
    return (text[:opening] + reversed_body + text[closing:]).encode("utf-8")


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exception: object) -> Literal[False]:
        return False

    def read(self) -> bytes:
        return self._payload


def test_v2_build_appends_supplements_and_leaves_v1_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    _install_fake_extraction(monkeypatch, layout.module)
    v1_before = (layout.v1_dir / "corpus-v1.json").read_bytes()
    v1_files_before = sorted(path.name for path in layout.v1_dir.iterdir())

    assert layout.module.main(["--version", "v2"]) == 0

    assert (layout.v1_dir / "corpus-v1.json").read_bytes() == v1_before
    assert sorted(path.name for path in layout.v1_dir.iterdir()) == v1_files_before
    v1_payload = json.loads(v1_before)
    payload = json.loads((layout.v2_dir / "corpus-v2.json").read_text(encoding="utf-8"))
    assert payload["corpus_id"] == "mimii-synthetic-context-v2"
    assert payload["version"] == "v2"
    assert payload["contract_version"] == "mfg-agentgraph-scenario-corpus-v1"
    documents = {item["document_id"]: item for item in payload["documents"]}
    assert set(documents) == {"doc:base-handbook", _SUPPLEMENT_ID}
    assert documents["doc:base-handbook"] == v1_payload["documents"][0]
    supplement = documents[_SUPPLEMENT_ID]
    assert supplement["source_uri"] == _OFFICIAL_URI
    assert supplement["source_sha256"] == _sha(_PAYLOAD)
    assert supplement["machine_types"] == ["valve"]
    chunk_ids = {item["chunk_id"] for item in payload["chunks"]}
    assert chunk_ids == {"chunk:base-handbook-c01", "chunk:supplemental-valve-manual-c01"}
    base_chunks = [item for item in payload["chunks"] if item["document_id"] == "doc:base-handbook"]
    assert base_chunks == v1_payload["chunks"]
    for section in ("assets", "observations", "procedures", "sensors", "queries"):
        assert payload[section] == v1_payload[section]
    assert layout.module.main(["--version", "v2", "--verify"]) == 0


def test_v2_verify_tolerates_trig_wire_order_but_rejects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    _install_fake_extraction(monkeypatch, layout.module)
    assert layout.module.main(["--version", "v2"]) == 0
    trig_path = layout.v2_dir / "corpus-v2.trig"
    original = trig_path.read_bytes()
    reordered = _reverse_trig_statements(original)
    assert reordered != original
    Dataset().parse(data=reordered.decode("utf-8"), format="trig")

    trig_path.write_bytes(reordered)
    assert layout.module.main(["--version", "v2", "--verify"]) == 0

    trig_path.write_bytes(
        reordered.replace(
            _SUPPLEMENT_TITLE.encode("utf-8"), b"Tampered valve maintenance manual", 1
        )
    )
    assert layout.module.main(["--version", "v2", "--verify"]) == 1


def test_v2_build_rejects_a_corrupt_cached_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(
        tmp_path,
        monkeypatch,
        entries=[_entry(b"declared bytes that are not on disk")],
        cache_payload=b"corrupt cached bytes",
    )
    _install_fake_extraction(monkeypatch, layout.module)

    with pytest.raises(SystemExit) as exit_info:
        layout.module.main(["--version", "v2"])

    assert "sha256" in str(exit_info.value.code)
    assert (layout.v1_dir / "corpus-v1.json").read_bytes() == build_corpus_release(
        _base_corpus().to_document()
    )
    assert sorted(path.name for path in layout.v2_dir.iterdir()) == ["sources-v2.json"]


def test_v2_build_fails_closed_without_pdftotext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch, pdftotext_version=None)
    _install_fake_extraction(monkeypatch, layout.module)
    monkeypatch.setattr(layout.module, "shutil", types.SimpleNamespace(which=lambda name: None))
    v1_before = (layout.v1_dir / "corpus-v1.json").read_bytes()

    with pytest.raises(SystemExit) as exit_info:
        layout.module.main(["--version", "v2"])

    assert "pdftotext" in str(exit_info.value.code)
    assert (layout.v1_dir / "corpus-v1.json").read_bytes() == v1_before
    assert sorted(path.name for path in layout.v2_dir.iterdir()) == ["sources-v2.json"]


def test_v2_build_acquires_from_the_recorded_download_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch, write_cache=False)
    _install_fake_extraction(monkeypatch, layout.module)
    requested: list[str] = []

    def fake_urlopen(request: Any, timeout: float | None = None) -> _Response:
        requested.append(request.full_url)
        return _Response(_PAYLOAD)

    monkeypatch.setattr(layout.module.urllib.request, "urlopen", fake_urlopen)

    assert layout.module.main(["--version", "v2"]) == 0

    assert requested == [_REPLAY_URI]
    assert (layout.cache_dir / "acquired" / "supplement.pdf").read_bytes() == _PAYLOAD


def test_v2_manifest_rejects_unsafe_cache_name_and_incomplete_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(
        tmp_path,
        monkeypatch,
        entries=[_entry(_PAYLOAD, cache_name="../escape.pdf")],
    )
    with pytest.raises(SystemExit) as exit_info:
        layout.module.main(["--version", "v2"])
    assert "cache_name" in str(exit_info.value.code)

    incomplete = _entry(_PAYLOAD)
    del incomplete["download_uri"]
    second = _layout(tmp_path / "second", monkeypatch, entries=[incomplete])
    with pytest.raises(SystemExit) as exit_info:
        second.module.main(["--version", "v2"])
    assert "download_uri" in str(exit_info.value.code)


def test_v2_manifest_rejects_duplicate_and_colliding_document_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplicate = _layout(
        tmp_path / "duplicate",
        monkeypatch,
        entries=[_entry(_PAYLOAD), _entry(_PAYLOAD)],
    )
    with pytest.raises(SystemExit) as exit_info:
        duplicate.module.main(["--version", "v2"])
    assert "duplicate" in str(exit_info.value.code)

    colliding = _layout(
        tmp_path / "colliding",
        monkeypatch,
        entries=[_entry(_PAYLOAD, document_id="doc:base-handbook")],
    )
    with pytest.raises(SystemExit) as exit_info:
        colliding.module.main(["--version", "v2"])
    assert "collides" in str(exit_info.value.code)


def test_v2_build_rejects_a_supplement_without_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    _install_fake_extraction(monkeypatch, layout.module, chunks=False)

    with pytest.raises(SystemExit) as exit_info:
        layout.module.main(["--version", "v2"])

    assert "no procedural chunk" in str(exit_info.value.code)
    assert sorted(path.name for path in layout.v2_dir.iterdir()) == ["sources-v2.json"]


def test_v2_build_refuses_a_divergent_versioned_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    _install_fake_extraction(monkeypatch, layout.module)
    assert layout.module.main(["--version", "v2"]) == 0
    target = layout.v2_dir / "corpus-v2.json"
    target.write_text("frozen divergent release", encoding="utf-8")

    assert layout.module.main(["--version", "v2"]) == 1

    assert target.read_text(encoding="utf-8") == "frozen divergent release"


def test_default_version_still_builds_the_v1_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    monkeypatch.setattr(layout.module, "build", lambda: _base_corpus())

    assert layout.module.main([]) == 0

    payload = json.loads((layout.v1_dir / "corpus-v1.json").read_text(encoding="utf-8"))
    assert payload["corpus_id"] == "mimii-synthetic-context-v1"
    assert payload["version"] == "v1"
    assert (layout.v1_dir / "corpus-v1.trig").exists()
    assert not (layout.v2_dir / "corpus-v2.json").exists()


def test_trig_graph_is_parsed_from_the_corpus_context_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    _install_fake_extraction(monkeypatch, layout.module)
    assert layout.module.main(["--version", "v2"]) == 0

    dataset = Dataset()
    dataset.parse(
        data=(layout.v2_dir / "corpus-v2.trig").read_text(encoding="utf-8"), format="trig"
    )
    assert len(dataset.graph(URIRef(CONTEXT_GRAPH))) > 0


def test_the_v1_writer_refuses_to_replace_a_divergent_frozen_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    monkeypatch.setattr(layout.module, "build", lambda: _base_corpus())
    target = layout.v1_dir / "corpus-v1.json"
    target.write_text("frozen v1 release", encoding="utf-8")

    code = layout.module.main([])

    assert code == 1
    assert "refused" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8") == "frozen v1 release"


def test_a_v2_build_refuses_an_edited_v1_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _layout(tmp_path, monkeypatch)
    document = _base_corpus().to_document()
    document["documents"][0]["title"] = "Silently edited handbook"  # type: ignore[index]
    (layout.v1_dir / "corpus-v1.json").write_bytes(build_corpus_release(document))

    with pytest.raises(SystemExit) as exit_info:
        layout.module.build_v2()

    assert "byte-identical" in str(exit_info.value.code)


def _base_inputs() -> tuple[dict[str, str], set[str], dict[str, str]]:
    corpus = _base_corpus()
    return (
        {chunk.chunk_id: chunk.text for chunk in corpus.chunks},
        {a.asset_id for a in corpus.assets},
        {o.observation_id: o.asset_id for o in corpus.observations},
    )


def _authored_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "procedures": [
            {
                "procedure_id": "proc:pump-inspect",
                "machine_type": "pump",
                "asset_ids": ["asset:pump-01"],
                "text": "Inspect the pump inlet and check the discharge pressure.",
                "evidence_chunk_ids": ["chunk:base-handbook-c01"],
                "claims": [
                    {
                        "claim": "Inspect the pump inlet",
                        "chunk_id": "chunk:base-handbook-c01",
                        "quote": "Inspect the pump inlet",
                    }
                ],
            }
        ],
        "queries": [
            {
                "query_id": "atq-201",
                "category": "single_hop",
                "text": "What does the pump procedure require first?",
                "expected_evidence_refs": [
                    "proc:pump-inspect",
                    "chunk:base-handbook-c01",
                    "obs:pump-01-context",
                ],
                "expected_action": None,
                "rubric": "Names the inlet inspection from the cited chunk.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_the_v3_layer_requires_a_query_to_cite_its_procedure_and_a_chunk(
    tmp_path: Path,
) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    payload = _authored_payload()
    payload["queries"][0]["expected_evidence_refs"] = ["chunk:base-handbook-c01"]  # type: ignore[index]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        module.load_authored_v3(path, *_base_inputs())

    assert "must cite a procedure" in str(exit_info.value.code)


def test_the_v3_layer_rejects_a_chunk_its_procedure_does_not_claim(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    payload = _authored_payload()
    payload["queries"][0]["expected_evidence_refs"] = [  # type: ignore[index]
        "proc:pump-inspect",
        "chunk:unrelated-document-c01",
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        module.load_authored_v3(path, *_base_inputs())

    assert "does not claim" in str(exit_info.value.code)


def test_the_v3_layer_requires_a_non_trap_query_to_cite_an_observation(
    tmp_path: Path,
) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    payload = _authored_payload()
    payload["queries"][0]["expected_evidence_refs"] = [  # type: ignore[index]
        "proc:pump-inspect",
        "chunk:base-handbook-c01",
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        module.load_authored_v3(path, *_base_inputs())

    assert "must cite an observation" in str(exit_info.value.code)


def test_the_v3_layer_rejects_an_undeclared_observation(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    payload = _authored_payload()
    payload["queries"][0]["expected_evidence_refs"] = [  # type: ignore[index]
        "proc:pump-inspect",
        "chunk:base-handbook-c01",
        "obs:pump-99-ghost",
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        module.load_authored_v3(path, *_base_inputs())

    assert "undeclared observation" in str(exit_info.value.code)


def test_the_v3_layer_rejects_an_observation_of_an_uncovered_asset(
    tmp_path: Path,
) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    payload = _authored_payload()
    payload["queries"][0]["expected_evidence_refs"] = [  # type: ignore[index]
        "proc:pump-inspect",
        "chunk:base-handbook-c01",
        "obs:fan-01-mimii",
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    chunk_text, asset_ids, observation_assets = _base_inputs()
    observation_assets = dict(observation_assets, **{"obs:fan-01-mimii": "asset:fan-01"})

    with pytest.raises(SystemExit) as exit_info:
        module.load_authored_v3(path, chunk_text, asset_ids, observation_assets)

    assert "does not cover" in str(exit_info.value.code)


def test_the_v3_layer_rejects_a_claim_its_chunk_does_not_contain(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    payload = _authored_payload()
    payload["procedures"][0]["claims"][0]["quote"] = "Replace the impeller"  # type: ignore[index]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        module.load_authored_v3(path, *_base_inputs())

    assert "does not contain" in str(exit_info.value.code)


def test_the_v3_layer_accepts_a_complete_chain(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "authored-v3.json"
    path.write_text(json.dumps(_authored_payload()), encoding="utf-8")

    procedures, queries = module.load_authored_v3(path, *_base_inputs())

    assert [procedure.procedure_id for procedure in procedures] == ["proc:pump-inspect"]
    assert queries[0].expected_evidence_refs == (
        "proc:pump-inspect",
        "chunk:base-handbook-c01",
        "obs:pump-01-context",
    )


def _scenario_readings(module: Any) -> tuple[CorpusObservation, ...]:
    readings = module._scenario_observations(module._assets(), module._sensors())
    assert isinstance(readings, tuple)
    return tuple(cast(CorpusObservation, item) for item in readings)


def test_every_scenario_reading_states_a_value_a_time_and_a_state() -> None:
    module = _module()

    readings = _scenario_readings(module)

    assert readings
    for reading in readings:
        assert reading.value is not None, reading.observation_id
        assert reading.observed_at is not None, reading.observation_id
        assert reading.operating_state in module.OPERATING_STATES, reading.observation_id
        assert reading.sensor_id is not None, reading.observation_id
        assert reading.lineage is Lineage.AUTHORED_CURATED


def test_the_scenario_series_is_deterministic() -> None:
    module = _module()

    first = _scenario_readings(module)
    second = _scenario_readings(module)

    assert first == second


def test_the_scenario_series_covers_every_sensor_with_unique_instants() -> None:
    module = _module()

    readings = _scenario_readings(module)
    sensors = module._sensors()
    instants = [(item.sensor_id, item.observed_at) for item in readings]

    assert len(instants) == len(set(instants))
    for sensor in sensors:
        per_sensor = [item for item in readings if item.sensor_id == sensor.sensor_id]
        assert len(per_sensor) == module._SCENARIO_SAMPLES


def test_scenario_values_stay_positive_and_inside_the_declared_profile() -> None:
    """The profile is a scenario assumption, so a value outside it is a generator bug."""

    module = _module()
    profiles = {item[0]: item for item in module._PROPERTY_PROFILE}

    for reading in _scenario_readings(module):
        assert reading.sensor_id is not None
        assert reading.value is not None
        property_id = reading.sensor_id.split("-", 2)[2]
        baseline, swing, transient, anomaly = profiles[property_id][2:]
        ceiling = baseline + swing + max(transient, anomaly) + baseline * 0.05
        assert 0 < reading.value <= ceiling, reading.observation_id


def test_the_scenario_series_states_each_operating_state() -> None:
    module = _module()

    states = {reading.operating_state for reading in _scenario_readings(module)}

    assert states == set(module.OPERATING_STATES)


def test_a_release_with_an_identifier_only_observation_is_refused() -> None:
    module = _module()
    filler = CorpusObservation(
        observation_id="obs:pump-01-nominal-001",
        asset_id="asset:pump-01",
        label="nominal_vibration",
        label_source="authored_context",
        lineage=Lineage.AUTHORED_CURATED,
    )
    corpus = module.ScenarioCorpus(
        corpus_id="mimii-synthetic-context-v4",
        version="v4",
        documents=_base_corpus().documents,
        assets=_base_corpus().assets,
        observations=(filler,),
        sensors=(),
        procedures=(),
        chunks=_base_corpus().chunks,
        queries=(),
        provenance_profile="complete",
    )

    with pytest.raises(SystemExit, match="identifier-only"):
        module._require_informative_observations(corpus)


def _frozen_v3_corpus() -> ScenarioCorpus:
    base = _base_corpus()
    return ScenarioCorpus(
        corpus_id="mimii-synthetic-context-v3",
        version="v3",
        documents=base.documents,
        assets=base.assets,
        observations=base.observations,
        sensors=(
            CorpusSensor(
                sensor_id="sensor:pump-01-vibration",
                asset_id="asset:pump-01",
                property_id="vibration",
                unit="mm/s",
            ),
        ),
        procedures=base.procedures,
        chunks=base.chunks,
        queries=base.queries,
        provenance_profile="complete",
    )


def _v4_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = _module()
    v3_dir = tmp_path / "release-v3"
    v3_dir.mkdir(parents=True)
    frozen = _frozen_v3_corpus()
    (v3_dir / "corpus-v3.json").write_bytes(build_corpus_release(frozen.to_document()))
    monkeypatch.setattr(module, "RELEASE_DIR_V3", v3_dir)
    monkeypatch.setattr(module, "_FROZEN_V3_DIGEST", frozen.document_sha256)
    return module, v3_dir, frozen


def test_a_v4_build_replaces_only_the_observation_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _v3_dir, frozen = _v4_layout(tmp_path, monkeypatch)

    corpus = module.build_v4()

    assert corpus.version == "v4"
    assert corpus.documents == frozen.documents
    assert corpus.chunks == frozen.chunks
    assert corpus.queries == frozen.queries
    assert corpus.identifier_only_observation_ids == ()
    assert any(item.value is not None for item in corpus.observations)


def test_a_v4_build_refuses_an_edited_v3_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, v3_dir, _frozen = _v4_layout(tmp_path, monkeypatch)
    document = _frozen_v3_corpus().to_document()
    document["documents"][0]["title"] = "Silently edited handbook"  # type: ignore[index]
    (v3_dir / "corpus-v3.json").write_bytes(build_corpus_release(document))

    with pytest.raises(SystemExit) as exit_info:
        module.build_v4()

    assert "byte-identical" in str(exit_info.value.code)


def test_a_reformatted_but_unchanged_v3_base_is_still_the_frozen_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release identity is canonical content: indentation is not a different release."""

    module, v3_dir, frozen = _v4_layout(tmp_path, monkeypatch)
    document = _frozen_v3_corpus().to_document()
    (v3_dir / "corpus-v3.json").write_text(json.dumps(document, indent=2), encoding="utf-8")

    corpus = module.build_v4()

    assert corpus.documents == frozen.documents
    assert corpus.identifier_only_observation_ids == ()
