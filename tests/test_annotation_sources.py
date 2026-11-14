"""Primary-source bytes, identity, and corpus allowlist are immutable annotation inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mfg_agentgraph.annotation_sources import SourceArtifact, SourceManifest, load_source_manifest


def _manifest(tmp_path: Path) -> Path:
    (tmp_path / "sop.txt").write_bytes(b"Inspect the inlet.\r\n")
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": "mfg-agentgraph-annotation-sources-v1",
                "sources": [
                    {
                        "evidence_id": "ex:SOP_Chunk_7",
                        "path": "sop.txt",
                        "sha256": hashlib.sha256(b"Inspect the inlet.\r\n").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_manifest_binds_exact_source_bytes_and_vocabulary(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    manifest = load_source_manifest(path, root=tmp_path)
    assert manifest.allowed_evidence_refs == frozenset({"ex:SOP_Chunk_7"})
    assert manifest.sources[0].text == "Inspect the inlet.\r\n"
    original = manifest.document_sha256
    (tmp_path / "sop.txt").write_bytes(b"Inspect a different component.\n")
    with pytest.raises(ValueError, match="sha256"):
        load_source_manifest(path, root=tmp_path)
    assert manifest.document_sha256 == original


def test_manifest_rejects_duplicate_evidence_identity(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sources"] *= 2
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_source_manifest(path, root=tmp_path)


def test_manifest_rejects_unknown_fields_and_old_contract(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    original = json.loads(path.read_text(encoding="utf-8"))
    for changes in ({"contract_version": "old"}, {"labels": {"atq-001": "supported"}}):
        path.write_text(json.dumps({**original, **changes}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_source_manifest(path, root=tmp_path)


@pytest.mark.parametrize("relative", ["../escape.txt", "/etc/passwd", "dir/../../escape.txt"])
def test_manifest_cannot_read_outside_source_root(tmp_path: Path, relative: str) -> None:
    path = _manifest(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sources"][0]["path"] = relative
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="path"):
        load_source_manifest(path, root=tmp_path)


def test_manifest_symlink_cannot_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = _manifest(root)
    external = tmp_path / "outside.txt"
    external.write_bytes(b"Inspect the inlet.\r\n")
    (root / "sop.txt").unlink()
    (root / "sop.txt").symlink_to(external)
    with pytest.raises(ValueError, match="path"):
        load_source_manifest(path, root=root)


def _artifact(**overrides: object) -> SourceArtifact:
    fields: dict[str, object] = {
        "evidence_id": "ex:SOP_Chunk_7",
        "path": "sop.txt",
        "text": "Inspect the inlet.",
    }
    fields.update(overrides)
    if "sha256" not in overrides:
        candidate = fields["text"]
        fields["sha256"] = (
            hashlib.sha256(candidate.encode("utf-8")).hexdigest()
            if isinstance(candidate, str)
            else "a" * 64
        )
    return SourceArtifact(**fields)  # type: ignore[arg-type]


def test_guard_fail_closed_behavior_for_artifacts_and_manifests(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ex: identifier"):
        _artifact(evidence_id="SOP_Chunk_7")
    with pytest.raises(ValueError, match="64 lowercase"):
        _artifact(sha256="zz")
    with pytest.raises(TypeError, match="source text must be a string"):
        _artifact(text=3)
    with pytest.raises(ValueError, match="nonblank"):
        _artifact(text="   ")
    with pytest.raises(ValueError, match="exceeds"):
        _artifact(text="a" * 70_000)
    with pytest.raises(TypeError, match="sequence of SourceArtifact"):
        SourceManifest(sources="sop.txt")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must not be empty"):
        SourceManifest(sources=())
    with pytest.raises(TypeError, match="sequence of SourceArtifact"):
        SourceManifest(sources=("sop.txt",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate paths"):
        SourceManifest(sources=(_artifact(), _artifact(evidence_id="ex:Other")))

    manifest = SourceManifest(sources=(_artifact(),))
    assert manifest.annotator_documents() == [
        {"evidence_id": "ex:SOP_Chunk_7", "text": "Inspect the inlet."}
    ]
    assert manifest.document_sha256 == manifest.document_sha256

    with pytest.raises(TypeError, match="path must be a pathlib.Path"):
        load_source_manifest("sources.json", root=tmp_path)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="root must be a pathlib.Path"):
        load_source_manifest(tmp_path / "sources.json", root=".")  # type: ignore[arg-type]


def test_manifest_document_guards_fail_closed(tmp_path: Path) -> None:
    path = _manifest(tmp_path)

    path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(TypeError, match="must be a mapping"):
        load_source_manifest(path, root=tmp_path)

    path.write_text(
        json.dumps({"contract_version": "mfg-agentgraph-annotation-sources-v1"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing required key"):
        load_source_manifest(path, root=tmp_path)

    path.write_text(
        json.dumps({"contract_version": "mfg-agentgraph-annotation-sources-v1", "sources": 3}),
        encoding="utf-8",
    )
    with pytest.raises(TypeError, match="sequence of source mappings"):
        load_source_manifest(path, root=tmp_path)

    document = json.loads(_manifest(tmp_path).read_text(encoding="utf-8"))
    document["sources"][0]["path"] = "missing.txt"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="readable file"):
        load_source_manifest(path, root=tmp_path)

    document["sources"][0]["path"] = "sop.txt"
    document["sources"][0]["sha256"] = "z" * 64
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="64 lowercase"):
        load_source_manifest(path, root=tmp_path)

    document["sources"][0]["evidence_id"] = "SOP_Chunk_7"
    document["sources"][0]["sha256"] = hashlib.sha256(b"Inspect the inlet.\r\n").hexdigest()
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="ex: identifier"):
        load_source_manifest(path, root=tmp_path)


def test_source_artifact_digest_must_match_its_text() -> None:
    """A declared digest that does not cover the carried text is a false provenance claim."""
    with pytest.raises(ValueError, match="sha256 does not match"):
        SourceArtifact(
            evidence_id="ex:SOP_Chunk_7",
            path="sop.txt",
            sha256=hashlib.sha256(b"original").hexdigest(),
            text="substituted",
        )


def test_manifest_preserves_exact_bytes_for_whitespace_sensitive_sources(tmp_path: Path) -> None:
    raw = "\nInspect the inlet.\r\n"
    (tmp_path / "sop.txt").write_bytes(raw.encode("utf-8"))
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": "mfg-agentgraph-annotation-sources-v1",
                "sources": [
                    {
                        "evidence_id": "ex:SOP_Chunk_7",
                        "path": "sop.txt",
                        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_source_manifest(path, root=tmp_path)

    assert manifest.sources[0].text == raw
    assert manifest.annotator_documents()[0]["text"] == raw
