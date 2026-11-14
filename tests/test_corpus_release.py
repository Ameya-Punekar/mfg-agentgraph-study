"""Contract tests for the Issue #115 versioned scenario corpus release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, XSD

from mfg_agentgraph.anomaly_triage_dataset import QueryCategory
from mfg_agentgraph.corpus_release import (
    CONTEXT_GRAPH,
    CORPUS,
    DEVELOPMENT_SPLIT,
    SOSA,
    AcquisitionKind,
    CorpusAsset,
    CorpusChunk,
    CorpusDocument,
    CorpusObservation,
    CorpusProcedure,
    CorpusQuery,
    CorpusSensor,
    ExtractionRecord,
    LicenceBasis,
    LicenceRecord,
    Lineage,
    MachineType,
    RecordingReference,
    ScenarioCorpus,
    SourceDerivation,
    build_corpus_release,
    corpus_to_trig,
    load_corpus_release,
)

_SHA = "a" * 64
_TEXT_SHA = "b" * 64


def _licence(**overrides: Any) -> LicenceRecord:
    fields: dict[str, Any] = {
        "identifier": "us-government-work",
        "basis": LicenceBasis.PUBLIC_DOMAIN_STATUTORY,
        "terms_url": "https://example.test/terms",
        "attribution": "U.S. Government work",
        "allows_redistribution": True,
        "share_alike": False,
    }
    fields.update(overrides)
    return LicenceRecord(**fields)


def _extraction(**overrides: Any) -> ExtractionRecord:
    fields: dict[str, Any] = {
        "tool": "pdftotext",
        "tool_version": "24.02.0",
        "rule": "full text, layout preserved",
    }
    fields.update(overrides)
    return ExtractionRecord(**fields)


def _document(**overrides: Any) -> CorpusDocument:
    fields: dict[str, Any] = {
        "document_id": "doc:pump-handbook",
        "title": "Pump handbook",
        "machine_types": (MachineType.PUMP,),
        "licence": _licence(),
        "acquisition": AcquisitionKind.BUNDLED_TEXT,
        "source_uri": "https://example.test/pump-handbook.pdf",
        "source_sha256": _SHA,
        "extraction": _extraction(),
        "text_sha256": _TEXT_SHA,
        "text_layer": True,
    }
    fields.update(overrides)
    return CorpusDocument(**fields)


def _recording(**overrides: Any) -> RecordingReference:
    fields: dict[str, Any] = {
        "dataset_record_id": "3384388",
        "dataset_doi": "10.5281/zenodo.3384388",
        "archive_key": "6_dB_pump.zip",
        "member_path": "pump/id_00/abnormal/00000000.wav",
        "member_crc32": "15d80cef",
        "member_sha256": _SHA,
        "seconds": 10.0,
        "sample_rate_hz": 16000,
        "channels": 8,
        "bits_per_sample": 16,
    }
    fields.update(overrides)
    return RecordingReference(**fields)


def _asset(asset_id: str = "asset:pump-01", **overrides: Any) -> CorpusAsset:
    fields: dict[str, Any] = {
        "asset_id": asset_id,
        "machine_type": MachineType.PUMP,
        "model_id": "id_00",
        "site_id": "site:plant-a",
        "display_name": "Feed pump 01",
    }
    fields.update(overrides)
    return CorpusAsset(**fields)


def _sensor(**overrides: Any) -> CorpusSensor:
    fields: dict[str, Any] = {
        "sensor_id": "sensor:pump-01-vibration",
        "asset_id": "asset:pump-01",
        "property_id": "vibration",
        "unit": "mm/s",
    }
    fields.update(overrides)
    return CorpusSensor(**fields)


def _observation(observation_id: str = "obs:pump-01-01", **overrides: Any) -> CorpusObservation:
    fields: dict[str, Any] = {
        "observation_id": observation_id,
        "asset_id": "asset:pump-01",
        "label": "abnormal",
        "recording": _recording(),
        "label_source": "mimii_dataset_label",
    }
    fields.update(overrides)
    return CorpusObservation(**fields)


def _procedure(procedure_id: str = "proc:pump-01-inspect") -> CorpusProcedure:
    return CorpusProcedure(
        procedure_id=procedure_id,
        machine_type=MachineType.PUMP,
        asset_ids=("asset:pump-01",),
        lineage=Lineage.AUTHORED_CURATED,
        text="Inspect the inlet for cavitation before adjusting the discharge valve.",
        evidence_chunk_ids=("chunk:pump-handbook-1",),
    )


def _chunk(chunk_id: str = "chunk:pump-handbook-1", **overrides: Any) -> CorpusChunk:
    text = "Inspect the inlet for cavitation. Check the discharge valve packing."
    fields: dict[str, Any] = {
        "chunk_id": chunk_id,
        "document_id": "doc:pump-handbook",
        "ordinal": 1,
        "text": text,
        "start_line": 10,
        "end_line": 12,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    fields.update(overrides)
    return CorpusChunk(**fields)


def _query(query_id: str = "atq-101", **overrides: Any) -> CorpusQuery:
    fields: dict[str, Any] = {
        "query_id": query_id,
        "category": QueryCategory.SINGLE_HOP,
        "split": DEVELOPMENT_SPLIT,
        "text": "Which pump reported an anomalous sound?",
        "expected_evidence_refs": ("obs:pump-01-01",),
        "expected_action": None,
        "rubric": "Names the pump and the observation time.",
    }
    fields.update(overrides)
    return CorpusQuery(**fields)


def _corpus(**overrides: Any) -> ScenarioCorpus:
    fields: dict[str, Any] = {
        "corpus_id": "mimii-synthetic-context-v1",
        "version": "v1",
        "documents": (_document(),),
        "assets": (_asset(),),
        "observations": (_observation(),),
        "sensors": (_sensor(),),
        "procedures": (_procedure(),),
        "chunks": (_chunk(),),
        "queries": (_query(),),
    }
    fields.update(overrides)
    return ScenarioCorpus(**fields)


def test_a_minimal_release_is_valid_and_digest_stable() -> None:
    first = _corpus()
    second = _corpus()

    assert first.document_sha256 == second.document_sha256
    assert len(first.document_sha256) == 64


def test_the_release_digest_changes_when_any_value_changes() -> None:
    baseline = _corpus().document_sha256
    changed = _corpus(assets=(_asset(model_id="id_02"),)).document_sha256

    assert changed != baseline


def test_the_development_digest_covers_only_the_development_split() -> None:
    baseline = _corpus()
    changed = _corpus(queries=(_query(text="Which pump is failing right now?"),))

    assert changed.development_sha256 != baseline.development_sha256
    assert changed.document_sha256 != baseline.document_sha256


def test_a_held_out_split_cannot_be_published_in_this_release() -> None:
    with pytest.raises(ValueError, match="development"):
        _corpus(queries=(_query(split="held_out"),))


def test_duplicate_identifiers_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _corpus(assets=(_asset(), _asset()))


def test_an_observation_must_reference_a_declared_asset() -> None:
    with pytest.raises(ValueError, match="asset"):
        _corpus(observations=(_observation(asset_id="asset:unknown"),))


def test_a_chunk_must_reference_a_declared_document() -> None:
    with pytest.raises(ValueError, match="document"):
        _corpus(chunks=(_chunk(document_id="doc:unknown"),))


def test_a_query_must_reference_declared_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        _corpus(queries=(_query(expected_evidence_refs=("obs:missing",)),))


def test_a_mimii_derived_observation_must_carry_the_recording_identity() -> None:
    with pytest.raises(ValueError, match="recording"):
        _corpus(observations=(_observation(recording=None),))


def test_an_authored_observation_must_not_claim_a_recording() -> None:
    with pytest.raises(ValueError, match="authored"):
        _corpus(
            observations=(
                _observation(
                    lineage=Lineage.AUTHORED_CURATED,
                    label_source="authored_context",
                    recording=_recording(),
                ),
            ),
        )


def test_the_acoustic_event_must_not_claim_a_detector_ran() -> None:
    with pytest.raises(ValueError, match="label"):
        _corpus(observations=(_observation(label_source="proprietary_detector"),))


def test_assets_are_authored_because_mimii_has_no_asset_hierarchy() -> None:
    with pytest.raises(ValueError, match="authored"):
        _corpus(assets=(_asset(lineage=Lineage.MIMII_DERIVED),))


def test_a_document_without_a_reuse_basis_is_rejected() -> None:
    with pytest.raises((TypeError, ValueError)):
        _corpus(documents=(_document(licence=None),))


def test_a_non_redistributable_document_may_not_be_bundled() -> None:
    with pytest.raises(ValueError, match="manifest"):
        _corpus(
            documents=(
                _document(
                    licence=_licence(allows_redistribution=False, share_alike=True),
                    acquisition=AcquisitionKind.BUNDLED_TEXT,
                ),
            ),
        )


def test_a_manifest_only_document_needs_no_bundled_text() -> None:
    manifest_only = dict(
        licence=_licence(allows_redistribution=False, share_alike=True),
        acquisition=AcquisitionKind.MANIFEST_ONLY,
        extraction=None,
        text_sha256=None,
    )
    corpus = _corpus(
        documents=(_document(**manifest_only),),
        chunks=(),
        procedures=(),
    )

    assert corpus.documents[0].acquisition is AcquisitionKind.MANIFEST_ONLY


def test_a_manifest_only_document_cannot_be_chunked() -> None:
    manifest_only = dict(
        licence=_licence(allows_redistribution=False, share_alike=True),
        acquisition=AcquisitionKind.MANIFEST_ONLY,
        extraction=None,
        text_sha256=None,
    )
    with pytest.raises(ValueError, match="manifest_only"):
        _corpus(documents=(_document(**manifest_only),), procedures=())


def test_a_share_alike_document_records_its_obligation() -> None:
    corpus = _corpus(
        documents=(_document(licence=_licence(share_alike=True)),),
    )

    assert corpus.share_alike_document_ids == ("doc:pump-handbook",)


def test_a_document_must_pin_its_raw_source() -> None:
    with pytest.raises((TypeError, ValueError)):
        _corpus(documents=(_document(source_sha256="", source_uri=""),))


def test_a_source_uri_must_be_absolute() -> None:
    with pytest.raises(ValueError, match="source_uri"):
        _corpus(documents=(_document(source_uri="pump-handbook.pdf"),))


def test_bundled_text_must_declare_how_it_was_extracted() -> None:
    with pytest.raises((TypeError, ValueError)):
        _corpus(documents=(_document(extraction=None),))


def test_the_release_digest_binds_the_raw_source_digest() -> None:
    baseline = _corpus().document_sha256
    changed = _corpus(documents=(_document(source_sha256="c" * 64),)).document_sha256

    assert changed != baseline


def test_a_chunk_whose_text_does_not_match_its_digest_is_rejected() -> None:
    """A syntactically valid digest must still describe the chunk text."""

    with pytest.raises(ValueError, match="text_sha256"):
        _corpus(chunks=(_chunk(text_sha256="b" * 64),))


def test_the_complete_provenance_profile_publishes_the_source_chain() -> None:
    corpus = _corpus(provenance_profile="complete")

    graph = Dataset()
    graph.parse(data=corpus_to_trig(corpus).decode("utf-8"), format="trig")
    context = graph.graph(URIRef(CONTEXT_GRAPH))
    document = URIRef("urn:mfg-agentgraph:corpus:doc:pump-handbook")

    assert (document, CORPUS.sourceUri, URIRef("https://example.test/pump-handbook.pdf")) in context
    assert (document, CORPUS.sourceSha256, Literal(_SHA)) in context
    assert (document, CORPUS.extractionTool, Literal("pdftotext")) in context
    assert list(context.triples((document, CORPUS.relevanceTier, None)))

    # A bare DOI is a literal: as a URIRef rdflib resolves it against the cwd.
    doi_terms = {term for _, _, term in context.triples((None, CORPUS.datasetDoi, None))}
    assert doi_terms == {Literal("10.5281/zenodo.3384388")}
    assert not any(str(term).startswith("file:") for term in doi_terms)


def test_the_legacy_provenance_profile_keeps_its_serialisation() -> None:
    """The frozen v1/v2 releases must not silently gain triples."""

    legacy = Dataset()
    legacy.parse(data=corpus_to_trig(_corpus()).decode("utf-8"), format="trig")
    context = legacy.graph(URIRef(CONTEXT_GRAPH))

    assert not list(context.triples((None, CORPUS.sourceUri, None)))
    assert "provenance_profile" not in _corpus().to_document()


def test_an_unknown_provenance_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="provenance_profile"):
        _corpus(provenance_profile="invented")


def _derivation(**overrides: Any) -> SourceDerivation:
    fields: dict[str, Any] = {
        "kind": "ocr_text_layer",
        "origin_uri": "https://example.test/origin-scan.pdf",
        "origin_sha256": "c" * 64,
        "manifest": "evaluation/scenario-corpus-v2-derived/derived-inputs-v2.json",
        "entry": "doc:pump-handbook",
        "derived_artifact_sha256": _SHA,
    }
    fields.update(overrides)
    return SourceDerivation(**fields)


def test_a_derived_source_publishes_the_origin_chain_beside_the_extracted_digest() -> None:
    """A digest no URL serves must be identified as a derived artifact, not as origin bytes."""

    corpus = _corpus(
        documents=(_document(derivation=_derivation()),),
        provenance_profile="complete",
    )

    graph = Dataset()
    graph.parse(data=corpus_to_trig(corpus).decode("utf-8"), format="trig")
    context = graph.graph(URIRef(CONTEXT_GRAPH))
    document = URIRef("urn:mfg-agentgraph:corpus:doc:pump-handbook")

    assert (document, CORPUS.derivationKind, Literal("ocr_text_layer")) in context
    assert (document, CORPUS.originUri, URIRef("https://example.test/origin-scan.pdf")) in context
    assert (document, CORPUS.originSha256, Literal("c" * 64)) in context
    assert (document, CORPUS.derivedArtifactSha256, Literal(_SHA)) in context
    assert (document, CORPUS.derivationEntry, Literal("doc:pump-handbook")) in context
    # The pair the release extracted from stays as recorded; the origin is separate.
    assert (document, CORPUS.sourceSha256, Literal(_SHA)) in context

    reloaded = ScenarioCorpus.from_document(corpus.to_document())
    assert reloaded.documents[0].derivation == _derivation()


def test_a_release_without_complete_provenance_may_not_declare_a_derivation() -> None:
    with pytest.raises(ValueError, match="complete provenance"):
        _corpus(documents=(_document(derivation=_derivation()),))


def test_a_derivation_must_name_the_document_it_describes() -> None:
    with pytest.raises(ValueError, match="must name the document"):
        _document(derivation=_derivation(entry="doc:another-handbook"))


def test_a_derivation_manifest_must_be_a_relative_json_path() -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        _derivation(manifest="/etc/derived-inputs.json")


def _reading(**overrides: Any) -> CorpusObservation:
    """An authored observation that states a reading, a time and an operating state."""

    fields: dict[str, Any] = {
        "observation_id": "obs:pump-01-vibration-001",
        "asset_id": "asset:pump-01",
        "label": "baseline_vibration",
        "label_source": "authored_context",
        "lineage": Lineage.AUTHORED_CURATED,
        "sensor_id": "sensor:pump-01-vibration",
        "value": 3.5,
        "observed_at": "2026-11-13T00:00:00Z",
        "operating_state": "baseline",
    }
    fields.update(overrides)
    return CorpusObservation(**fields)


def test_a_reading_without_a_sensor_has_no_unit_and_is_rejected() -> None:
    """The sensor defines the unit; a bare number would be dimensionless evidence."""

    with pytest.raises(ValueError, match="sensor"):
        _reading(sensor_id=None)


def test_a_reading_must_be_a_finite_number() -> None:
    for invalid in (float("nan"), float("inf"), True):
        with pytest.raises((TypeError, ValueError)):
            _reading(value=invalid)


def test_a_reading_timestamp_must_be_utc() -> None:
    """A local time without an offset cannot be ordered against another record."""

    for invalid in ("2026-11-13T00:00:00", "2026-11-13 00:00:00Z", "2026-13-01T00:00:00Z"):
        with pytest.raises(ValueError, match="observed_at"):
            _reading(observed_at=invalid)


def test_an_operating_state_must_come_from_the_declared_vocabulary() -> None:
    with pytest.raises(ValueError, match="operating_state"):
        _reading(operating_state="catastrophic")


def test_a_reading_must_declare_its_operating_state() -> None:
    with pytest.raises(ValueError, match="operating state"):
        _reading(operating_state=None)


def test_a_mimii_event_may_carry_neither_a_reading_nor_a_time() -> None:
    """MIMII supplies a recording and a dataset label, never a scalar or a wall-clock time."""

    with pytest.raises(ValueError, match="MIMII"):
        _reading(lineage=Lineage.MIMII_DERIVED, recording=_recording())
    with pytest.raises(ValueError, match="MIMII"):
        _observation(observed_at="2026-11-13T00:00:00Z")
    with pytest.raises(ValueError, match="MIMII"):
        _observation(operating_state="anomaly")


def test_a_reading_must_publish_complete_provenance() -> None:
    with pytest.raises(ValueError, match="complete provenance"):
        _corpus(observations=(_reading(),))


def test_an_authored_operating_state_alone_also_requires_complete_provenance() -> None:
    """The gate covers every new assertion, not only the ones carrying a number."""

    with pytest.raises(ValueError, match="complete provenance"):
        _corpus(
            observations=(
                _observation(
                    lineage=Lineage.AUTHORED_CURATED,
                    recording=None,
                    label_source="authored_context",
                    operating_state="anomaly",
                ),
            ),
        )


def test_identifier_only_observations_are_reported() -> None:
    corpus = _corpus()

    assert corpus.identifier_only_observation_ids == ()


def test_an_observation_with_no_reading_event_or_time_is_flagged() -> None:
    """A record that says nothing but its own identifier is the defect this release removes."""

    filler = CorpusObservation(
        observation_id="obs:pump-01-nominal-001",
        asset_id="asset:pump-01",
        label="nominal_vibration",
        label_source="authored_context",
        lineage=Lineage.AUTHORED_CURATED,
        sensor_id="sensor:pump-01-vibration",
    )
    corpus = _corpus(
        observations=(_observation("obs:pump-01-01"), filler),
        provenance_profile="complete",
    )

    assert corpus.identifier_only_observation_ids == ("obs:pump-01-nominal-001",)


def test_a_complete_release_publishes_the_reading_chain() -> None:
    corpus = _corpus(
        observations=(_reading(),),
        queries=(_query(expected_evidence_refs=("obs:pump-01-vibration-001",)),),
        provenance_profile="complete",
    )

    graph = Dataset()
    graph.parse(data=corpus_to_trig(corpus).decode("utf-8"), format="trig")
    context = graph.graph(URIRef(CONTEXT_GRAPH))
    subject = URIRef("urn:mfg-agentgraph:corpus:obs:pump-01-vibration-001")

    assert (subject, CORPUS.value, Literal(3.5, datatype=XSD.decimal)) in context
    assert (subject, CORPUS.operatingState, Literal("baseline")) in context
    assert list(context.triples((subject, CORPUS.observedAt, None)))
    sensor = URIRef("urn:mfg-agentgraph:corpus:sensor:pump-01-vibration")
    assert (subject, SOSA.madeBySensor, sensor) in context

    reloaded = ScenarioCorpus.from_document(corpus.to_document())
    assert reloaded.observations[0] == _reading()


def test_a_reading_must_come_from_a_sensor_on_the_same_asset() -> None:
    """A value attributed to the wrong asset is a false measurement, not a modelling gap."""

    with pytest.raises(ValueError, match="different asset"):
        _corpus(
            assets=(
                _asset(),
                _asset(asset_id="asset:pump-02", model_id="id_02", display_name="Booster pump 02"),
            ),
            sensors=(
                _sensor(),
                _sensor(sensor_id="sensor:pump-02-vibration", asset_id="asset:pump-02"),
            ),
            observations=(_reading(sensor_id="sensor:pump-02-vibration"),),
            queries=(_query(expected_evidence_refs=("obs:pump-01-vibration-001",)),),
            provenance_profile="complete",
        )


def test_a_sensor_must_be_hosted_by_a_declared_asset() -> None:
    with pytest.raises(ValueError, match="sensor"):
        _corpus(sensors=(_sensor(asset_id="asset:unknown"),))


def test_sensors_are_authored_because_mimii_supplies_recordings_only() -> None:
    with pytest.raises(ValueError, match="authored"):
        _corpus(sensors=(_sensor(lineage=Lineage.MIMII_DERIVED),))


def test_procedures_are_authored_because_mimii_supplies_recordings_only() -> None:
    with pytest.raises(ValueError, match="authored"):
        CorpusProcedure(
            procedure_id="proc:pump-01-inspect",
            machine_type=MachineType.PUMP,
            asset_ids=("asset:pump-01",),
            lineage=Lineage.MIMII_DERIVED,
            text="Inspect the inlet for cavitation before adjusting the discharge valve.",
            evidence_chunk_ids=("chunk:pump-handbook-1",),
        )


def test_an_observation_must_reference_a_declared_sensor() -> None:
    with pytest.raises(ValueError, match="sensor"):
        _corpus(observations=(_observation(sensor_id="sensor:missing"),))


def test_query_identifiers_are_unique() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _corpus(queries=(_query(), _query(text="A different question.")))


def test_a_trap_query_must_carry_no_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        _corpus(
            queries=(
                _query(
                    category=QueryCategory.TRAP_UNSUPPORTED,
                    expected_evidence_refs=("obs:pump-01-01",),
                ),
            ),
        )


def test_the_graph_serialisation_is_deterministic_and_typed() -> None:
    first = corpus_to_trig(_corpus())
    second = corpus_to_trig(_corpus())

    assert first == second
    dataset = Dataset()
    dataset.parse(data=first.decode("utf-8"), format="trig")
    context = dataset.graph(URIRef(CONTEXT_GRAPH))
    assert len(context) > 0
    assert (
        URIRef("urn:mfg-agentgraph:corpus:asset:pump-01"),
        RDF.type,
        CORPUS.Asset,
    ) in context
    observations = sorted(str(subject) for subject in context.subjects(RDF.type, SOSA.Observation))
    assert observations == ["urn:mfg-agentgraph:corpus:obs:pump-01-01"]


def test_a_release_round_trips_through_canonical_json(tmp_path: Path) -> None:
    corpus = _corpus()
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(corpus.to_document(), indent=2), encoding="utf-8")

    loaded = load_corpus_release(path)

    assert loaded.document_sha256 == corpus.document_sha256


def test_an_unknown_release_key_is_rejected(tmp_path: Path) -> None:
    document = _corpus().to_document()
    document["unexpected"] = "value"
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected"):
        load_corpus_release(path)


def test_building_twice_from_the_same_inputs_is_byte_identical(tmp_path: Path) -> None:
    inputs = _corpus()

    first = build_corpus_release(inputs.to_document())
    second = build_corpus_release(inputs.to_document())

    assert first == second
    assert first.decode("utf-8") == second.decode("utf-8")
