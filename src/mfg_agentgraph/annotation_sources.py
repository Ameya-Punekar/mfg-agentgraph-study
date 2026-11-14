"""Frozen primary-source manifest for independent gold annotation.

An annotator may only read the artifacts this manifest declares, and may only cite the
evidence identifiers it allows. Both facts are covered by digests, so a later edit to a
source file invalidates every packet and submission collected against it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from mfg_agentgraph.anomaly_triage_dataset import (
    reject_duplicate_json_keys,
    require_text,
)

SOURCES_CONTRACT_VERSION = "mfg-agentgraph-annotation-sources-v1"

_MAX_TEXT_BYTES = 65_536
_EVIDENCE_REF_PATTERN = re.compile(r"^ex:[A-Za-z0-9_]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_MANIFEST_KEYS = frozenset({"contract_version", "sources"})
_SOURCE_KEYS = frozenset({"evidence_id", "path", "sha256"})


def canonical_json(document: Mapping[str, object]) -> str:
    """Return the canonical JSON text used for every annotation digest."""
    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_of(document: Mapping[str, object]) -> str:
    """Return the SHA-256 of one canonical annotation document."""
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def _require_sha256(value: object, field_name: str) -> str:
    digest = require_text(value, field_name)
    if not _SHA256_PATTERN.fullmatch(digest):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return digest


def _require_mapping_keys(
    payload: object, field_name: str, required: frozenset[str]
) -> Mapping[str, object]:
    # JSON object keys are always strings, so only shape and membership need checking here.
    if not isinstance(payload, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    document = cast(Mapping[str, object], payload)
    keys = set(document)
    missing = required - keys
    if missing:
        raise ValueError(f"{field_name} is missing required key: {sorted(missing)[0]}")
    unknown = set(document) - required
    if unknown:
        raise ValueError(f"{field_name} contains unknown key: {sorted(unknown)[0]}")
    return document


def require_source_text(value: object, field_name: str = "source text") -> str:
    """Return the exact source text, rejecting only blank or oversized content.

    Whitespace is preserved: the digest binds the literal bytes, so a normalizing
    validator would publish text the manifest does not actually cover.
    """
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be nonblank")
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError(f"{field_name} exceeds {_MAX_TEXT_BYTES} UTF-8 bytes")
    return value


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """One frozen primary source: its allowed evidence identifier and exact text."""

    evidence_id: str
    path: str
    sha256: str
    text: str

    def __post_init__(self) -> None:
        evidence_id = require_text(self.evidence_id, "evidence_id")
        if not _EVIDENCE_REF_PATTERN.fullmatch(evidence_id):
            raise ValueError(f"evidence_id must be a canonical ex: identifier, got {evidence_id!r}")
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "path", require_text(self.path, "path"))
        declared = _require_sha256(self.sha256, "sha256")
        exact = require_source_text(self.text)
        observed = hashlib.sha256(exact.encode("utf-8")).hexdigest()
        if observed != declared:
            raise ValueError(
                f"source text sha256 does not match: declared {declared}, observed {observed}"
            )
        object.__setattr__(self, "sha256", declared)
        object.__setattr__(self, "text", exact)

    def to_document(self) -> dict[str, object]:
        """Return the declared identity only; the text is bound by ``sha256``."""
        return {"evidence_id": self.evidence_id, "path": self.path, "sha256": self.sha256}

    def to_annotator_document(self) -> dict[str, object]:
        """Return the read-only view an annotator receives."""
        return {"evidence_id": self.evidence_id, "text": self.text}


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """One immutable, hash-addressed set of primary annotation sources."""

    sources: Sequence[SourceArtifact]

    def __post_init__(self) -> None:
        if isinstance(self.sources, (str, bytes, bytearray)) or not isinstance(
            self.sources, Sequence
        ):
            raise TypeError("sources must be a sequence of SourceArtifact instances")
        sources = tuple(self.sources)
        if not sources:
            raise ValueError("sources must not be empty")
        if not all(isinstance(source, SourceArtifact) for source in sources):
            raise TypeError("sources must be a sequence of SourceArtifact instances")
        evidence_ids = [source.evidence_id for source in sources]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("sources must not contain duplicate evidence_id values")
        paths = [source.path for source in sources]
        if len(set(paths)) != len(paths):
            raise ValueError("sources must not contain duplicate paths")
        object.__setattr__(self, "sources", sources)

    @property
    def allowed_evidence_refs(self) -> frozenset[str]:
        """Return every evidence identifier an annotator may cite."""
        return frozenset(source.evidence_id for source in self.sources)

    def to_document(self) -> dict[str, object]:
        return {
            "contract_version": SOURCES_CONTRACT_VERSION,
            "sources": [source.to_document() for source in self.sources],
        }

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the canonical declaration."""
        return sha256_of(self.to_document())

    def annotator_documents(self) -> list[dict[str, object]]:
        """Return the source texts the annotator is allowed to read."""
        return [source.to_annotator_document() for source in self.sources]


def _resolve_source_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ValueError(f"source path {relative!r} escapes the source root {root_resolved}")
    if not candidate.is_file():
        raise ValueError(f"source path {relative!r} is not a readable file")
    return candidate


def load_source_manifest(path: Path, *, root: Path) -> SourceManifest:
    """Load and verify one manifest, binding every declared file's exact bytes.

    Verification refuses a changed source, a path outside ``root`` (including through a
    symlink), a duplicate evidence identifier, or any field the contract does not define.
    """
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    payload = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys
    )
    document = _require_mapping_keys(payload, "source manifest", _MANIFEST_KEYS)
    contract_version = require_text(document["contract_version"], "contract_version")
    if contract_version != SOURCES_CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {SOURCES_CONTRACT_VERSION!r}")
    raw_sources = document["sources"]
    if isinstance(raw_sources, (str, bytes, bytearray)) or not isinstance(raw_sources, Sequence):
        raise TypeError("sources must be a sequence of source mappings")

    artifacts: list[SourceArtifact] = []
    for entry in raw_sources:
        source = _require_mapping_keys(entry, "source", _SOURCE_KEYS)
        relative = require_text(source["path"], "path")
        resolved = _resolve_source_path(root, relative)
        data = resolved.read_bytes()
        declared = _require_sha256(source["sha256"], "sha256")
        observed = hashlib.sha256(data).hexdigest()
        if observed != declared:
            raise ValueError(
                f"source {relative!r} sha256 does not match the manifest: "
                f"declared {declared}, observed {observed}"
            )
        artifacts.append(
            SourceArtifact(
                evidence_id=require_text(source["evidence_id"], "evidence_id"),
                path=relative,
                sha256=declared,
                text=data.decode("utf-8"),
            )
        )
    return SourceManifest(sources=artifacts)
