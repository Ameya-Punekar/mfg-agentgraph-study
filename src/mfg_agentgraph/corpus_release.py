"""Versioned scenario-corpus release for Issue #115.

The release is the fixed input of the comparison. It names its licensed documents,
the authored asset and context records, the acoustic events traceable to declared
MIMII recordings, and the development-only query split. Every element carries an
explicit lineage, so a reader can always tell a dataset label from an authored fact
and an authored procedure from a quoted source sentence.

This module owns the contract and the deterministic serialisation only. Source
acquisition, chunk embedding, and held-out annotation belong to the issues that own
them; this release deliberately cannot carry a held-out split.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeVar, cast

from rdflib import Dataset, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from mfg_agentgraph.annotation_sources import canonical_json, sha256_of
from mfg_agentgraph.anomaly_triage_dataset import (
    TRAP_CATEGORIES,
    TRAP_TERMINAL_STATUS,
    QueryCategory,
    reject_duplicate_json_keys,
    require_text,
)

CORPUS_CONTRACT_VERSION: Final = "mfg-agentgraph-scenario-corpus-v1"
DEVELOPMENT_SPLIT: Final = "development"
IRI_PREFIX: Final = "urn:mfg-agentgraph:corpus:"
CONTEXT_GRAPH: Final = "urn:mfg-agentgraph:graph:corpus-context"
CORPUS: Final = Namespace("https://w3id.org/mfg-agentgraph/corpus#")
SOSA: Final = Namespace("http://www.w3.org/ns/sosa/")

_MAX_TEXT_BYTES: Final = 65_536
_SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}\Z")
_CRC32_PATTERN: Final = re.compile(r"[0-9a-f]{8}\Z")
_IDENTIFIER_PATTERN: Final = re.compile(r"[a-z]+:[A-Za-z0-9_.-]+\Z")
# Queries keep the frozen dataset's ``atq-NNN`` convention; prefixed identifiers are
# also accepted so a release can namespace its own questions.
_QUERY_ID_PATTERN: Final = re.compile(r"(atq-[0-9]{3}|[a-z]+:[A-Za-z0-9_.-]+)\Z")
_MIMII_LABEL_SOURCE: Final = "mimii_dataset_label"
_AUTHORED_LABEL_SOURCE: Final = "authored_context"
_MIMII_LABELS: Final = frozenset({"normal", "abnormal"})
# The operating-state vocabulary an authored reading may declare. It describes the
# scenario phase a reading belongs to, not a diagnosis: the corpus holds no threshold.
OPERATING_STATES: Final = frozenset({"anomaly", "baseline", "recovery", "transient"})
_UTC_TIMESTAMP_PATTERN: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z"
)
_RecordT = TypeVar("_RecordT")

_CORPUS_KEYS: Final = frozenset(
    {
        "contract_version",
        "corpus_id",
        "version",
        "documents",
        "assets",
        "observations",
        "procedures",
        "sensors",
        "chunks",
        "queries",
    }
)
# Releases before v3 omit this key and must keep their canonical bytes, so it is
# accepted but optional; a missing value means the legacy serialisation.
_CORPUS_OPTIONAL_KEYS: Final = frozenset({"provenance_profile"})
PROVENANCE_PROFILES: Final = frozenset({"legacy", "complete"})
_LICENCE_KEYS: Final = frozenset(
    {
        "identifier",
        "basis",
        "terms_url",
        "attribution",
        "allows_redistribution",
        "share_alike",
    }
)
_DOCUMENT_KEYS: Final = frozenset(
    {
        "document_id",
        "title",
        "machine_types",
        "licence",
        "acquisition",
        "source_uri",
        "source_sha256",
        "extraction",
        "text_sha256",
        "text_layer",
        "relevance_tier",
    }
)
# A release that publishes complete provenance can also record how a derived source
# artifact relates to the origin it was acquired from. Earlier releases omit the key
# and keep their canonical bytes, so it is accepted but optional.
_DOCUMENT_OPTIONAL_KEYS: Final = frozenset({"derivation"})
_DERIVATION_KEYS: Final = frozenset(
    {
        "derived_artifact_sha256",
        "entry",
        "kind",
        "manifest",
        "origin_sha256",
        "origin_uri",
    }
)
DERIVATION_KINDS: Final = frozenset({"assembled_capture", "ocr_text_layer"})
_EXTRACTION_KEYS: Final = frozenset({"tool", "tool_version", "rule"})
_RECORDING_KEYS: Final = frozenset(
    {
        "dataset_record_id",
        "dataset_doi",
        "archive_key",
        "member_path",
        "member_crc32",
        "member_sha256",
        "seconds",
        "sample_rate_hz",
        "channels",
        "bits_per_sample",
    }
)
_ASSET_KEYS: Final = frozenset(
    {"asset_id", "machine_type", "model_id", "site_id", "display_name", "lineage"}
)
_OBSERVATION_KEYS: Final = frozenset(
    {
        "observation_id",
        "asset_id",
        "label",
        "label_source",
        "lineage",
        "recording",
        "sensor_id",
    }
)
# A reading, its scenario timestamp and its operating state are optional so the frozen
# v1-v3 releases keep their canonical bytes; a release that omits them cannot claim them.
_OBSERVATION_OPTIONAL_KEYS: Final = frozenset({"value", "observed_at", "operating_state"})
_SENSOR_KEYS: Final = frozenset({"sensor_id", "asset_id", "property_id", "unit", "lineage"})
_PROCEDURE_KEYS: Final = frozenset(
    {"procedure_id", "machine_type", "asset_ids", "lineage", "text", "evidence_chunk_ids"}
)
_CHUNK_KEYS: Final = frozenset(
    {"chunk_id", "document_id", "ordinal", "text", "start_line", "end_line", "text_sha256"}
)
_QUERY_KEYS: Final = frozenset(
    {
        "query_id",
        "category",
        "split",
        "text",
        "expected_evidence_refs",
        "expected_action",
        "rubric",
    }
)


class MachineType(StrEnum):
    """The four machine classes the frozen protocol requires."""

    PUMP = "pump"
    FAN = "fan"
    VALVE = "valve"
    SLIDER = "slider"


class Lineage(StrEnum):
    """Where one element of the corpus came from."""

    MIMII_DERIVED = "mimii_derived"
    AUTHORED_CURATED = "authored_curated"


class LicenceBasis(StrEnum):
    """The documented reason a source document may be reused."""

    PUBLIC_DOMAIN_STATUTORY = "public_domain_statutory"
    OPEN_LICENCE = "open_licence"
    SITE_PERMISSION = "site_permission"


class AcquisitionKind(StrEnum):
    """Whether the release bundles the source text or only references the source."""

    BUNDLED_TEXT = "bundled_text"
    MANIFEST_ONLY = "manifest_only"


class RelevanceTier(StrEnum):
    """How directly a document covers its declared machine type."""

    DIRECT = "T1"
    NAMED_UNIT = "T2"
    COMPONENT = "T3"


def _strict_mapping(
    payload: object,
    keys: frozenset[str],
    name: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{name} must be a mapping")
    document = cast(Mapping[str, object], payload)
    missing = keys - set(document)
    if missing:
        raise ValueError(f"{name} is missing required key: {sorted(missing)[0]}")
    unknown = set(document) - keys - optional
    if unknown:
        raise ValueError(f"{name} contains unknown key: {sorted(unknown)[0]}")
    return document


def _require_sha256(value: object, name: str) -> str:
    digest = require_text(value, name)
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return digest


def _require_identifier(value: object, name: str) -> str:
    identifier = require_text(value, name)
    if _IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        raise ValueError(f"{name} must be a prefixed identifier such as asset:pump-01")
    return identifier


def _require_text_bytes(value: object, name: str) -> str:
    return require_text(value, name, maximum_bytes=_MAX_TEXT_BYTES)


def _require_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _require_flag(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _require_sequence(value: object, name: str, item_type: type[object]) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence")
    items = tuple(value)
    if not all(isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain only {item_type.__name__} values")
    return items


def _require_identifier_sequence(value: object, name: str, *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of identifiers")
    identifiers = tuple(_require_identifier(item, name) for item in value)
    if not allow_empty and not identifiers:
        raise ValueError(f"{name} must not be empty")
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            raise ValueError(f"{name} must not repeat {identifier!r}")
        seen.add(identifier)
    return identifiers


def _require_unique(items: Sequence[str], name: str) -> None:
    seen: set[str] = set()
    for identifier in items:
        if identifier in seen:
            raise ValueError(f"{name} must not contain duplicate identifier {identifier!r}")
        seen.add(identifier)


def _freeze_records(
    value: object,
    name: str,
    item_type: type[_RecordT],
    *,
    key: Callable[[_RecordT], str],
) -> tuple[_RecordT, ...]:
    """Return one validated, identifier-sorted tuple of records."""

    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of {item_type.__name__} records")
    items = tuple(value)
    if not all(isinstance(item, item_type) for item in items):
        raise TypeError(f"{name} must contain only {item_type.__name__} records")
    return tuple(sorted(cast(tuple[_RecordT, ...], items), key=key))


def _enum_value(value: object, enum_type: type[StrEnum], name: str) -> str:
    text = require_text(value, name)
    allowed = {member.value for member in enum_type}
    if text not in allowed:
        raise ValueError(f"{name} must be one of: " + ", ".join(sorted(allowed)))
    return text


def _iri(identifier: str) -> URIRef:
    return URIRef(IRI_PREFIX + identifier)


@dataclass(frozen=True, slots=True)
class LicenceRecord:
    """The documented reuse basis for one external document."""

    identifier: str
    basis: LicenceBasis
    terms_url: str
    attribution: str
    allows_redistribution: bool
    share_alike: bool

    def __post_init__(self) -> None:
        if not isinstance(self.basis, LicenceBasis):
            raise TypeError("basis must be a LicenceBasis")
        object.__setattr__(self, "identifier", require_text(self.identifier, "identifier"))
        terms_url = require_text(self.terms_url, "terms_url")
        if not terms_url.startswith(("https://", "http://")):
            raise ValueError("terms_url must be an absolute http(s) URL")
        object.__setattr__(self, "terms_url", terms_url)
        object.__setattr__(
            self, "attribution", _require_text_bytes(self.attribution, "attribution")
        )
        object.__setattr__(
            self,
            "allows_redistribution",
            _require_flag(self.allows_redistribution, "allows_redistribution"),
        )
        object.__setattr__(self, "share_alike", _require_flag(self.share_alike, "share_alike"))

    def to_document(self) -> dict[str, object]:
        return {
            "allows_redistribution": self.allows_redistribution,
            "attribution": self.attribution,
            "basis": self.basis.value,
            "identifier": self.identifier,
            "share_alike": self.share_alike,
            "terms_url": self.terms_url,
        }

    @classmethod
    def from_document(cls, payload: object) -> LicenceRecord:
        document = _strict_mapping(payload, _LICENCE_KEYS, "licence")
        return cls(
            identifier=cast(str, document["identifier"]),
            basis=LicenceBasis(_enum_value(document["basis"], LicenceBasis, "basis")),
            terms_url=cast(str, document["terms_url"]),
            attribution=cast(str, document["attribution"]),
            allows_redistribution=cast(bool, document["allows_redistribution"]),
            share_alike=cast(bool, document["share_alike"]),
        )


@dataclass(frozen=True, slots=True)
class RecordingReference:
    """One MIMII recording whose acoustic event the corpus derives from."""

    dataset_record_id: str
    dataset_doi: str
    archive_key: str
    member_path: str
    member_crc32: str
    member_sha256: str
    seconds: float
    sample_rate_hz: int
    channels: int
    bits_per_sample: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dataset_record_id", require_text(self.dataset_record_id, "dataset_record_id")
        )
        object.__setattr__(self, "dataset_doi", require_text(self.dataset_doi, "dataset_doi"))
        object.__setattr__(self, "archive_key", require_text(self.archive_key, "archive_key"))
        member_path = require_text(self.member_path, "member_path")
        if member_path.startswith("/") or ".." in member_path.split("/"):
            raise ValueError("member_path must be relative and must not traverse")
        object.__setattr__(self, "member_path", member_path)
        crc32 = require_text(self.member_crc32, "member_crc32")
        if _CRC32_PATTERN.fullmatch(crc32) is None:
            raise ValueError("member_crc32 must be 8 lowercase hexadecimal characters")
        object.__setattr__(self, "member_crc32", crc32)
        object.__setattr__(
            self, "member_sha256", _require_sha256(self.member_sha256, "member_sha256")
        )
        if isinstance(self.seconds, bool) or not isinstance(self.seconds, (int, float)):
            raise TypeError("seconds must be a number")
        if self.seconds <= 0:
            raise ValueError("seconds must be positive")
        object.__setattr__(self, "seconds", float(self.seconds))
        object.__setattr__(
            self, "sample_rate_hz", _require_positive_int(self.sample_rate_hz, "sample_rate_hz")
        )
        object.__setattr__(self, "channels", _require_positive_int(self.channels, "channels"))
        object.__setattr__(
            self, "bits_per_sample", _require_positive_int(self.bits_per_sample, "bits_per_sample")
        )

    def to_document(self) -> dict[str, object]:
        return {
            "archive_key": self.archive_key,
            "bits_per_sample": self.bits_per_sample,
            "channels": self.channels,
            "dataset_doi": self.dataset_doi,
            "dataset_record_id": self.dataset_record_id,
            "member_crc32": self.member_crc32,
            "member_path": self.member_path,
            "member_sha256": self.member_sha256,
            "sample_rate_hz": self.sample_rate_hz,
            "seconds": self.seconds,
        }

    @classmethod
    def from_document(cls, payload: object) -> RecordingReference:
        document = _strict_mapping(payload, _RECORDING_KEYS, "recording")
        return cls(
            dataset_record_id=cast(str, document["dataset_record_id"]),
            dataset_doi=cast(str, document["dataset_doi"]),
            archive_key=cast(str, document["archive_key"]),
            member_path=cast(str, document["member_path"]),
            member_crc32=cast(str, document["member_crc32"]),
            member_sha256=cast(str, document["member_sha256"]),
            seconds=cast(float, document["seconds"]),
            sample_rate_hz=cast(int, document["sample_rate_hz"]),
            channels=cast(int, document["channels"]),
            bits_per_sample=cast(int, document["bits_per_sample"]),
        )


@dataclass(frozen=True, slots=True)
class ExtractionRecord:
    """How a source artifact's text was produced."""

    tool: str
    tool_version: str
    rule: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool", require_text(self.tool, "tool"))
        object.__setattr__(self, "tool_version", require_text(self.tool_version, "tool_version"))
        object.__setattr__(self, "rule", _require_text_bytes(self.rule, "rule"))

    def to_document(self) -> dict[str, object]:
        return {"rule": self.rule, "tool": self.tool, "tool_version": self.tool_version}

    @classmethod
    def from_document(cls, payload: object) -> ExtractionRecord:
        document = _strict_mapping(payload, _EXTRACTION_KEYS, "extraction")
        return cls(
            tool=cast(str, document["tool"]),
            tool_version=cast(str, document["tool_version"]),
            rule=cast(str, document["rule"]),
        )


@dataclass(frozen=True, slots=True)
class SourceDerivation:
    """How a document's source artifact relates to the origin it was acquired from.

    ``source_uri`` and ``source_sha256`` identify the artifact the release extracted
    from. For a native download those are the bytes the URL serves. When they are not
    — an OCR text layer, or a capture assembled from several pages — this record names
    the origin bytes, the derived artifact, and the manifest that declares both, so a
    reader can reproduce the text instead of trusting a digest no URL serves.
    """

    kind: str
    origin_uri: str
    origin_sha256: str
    manifest: str
    entry: str
    derived_artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in DERIVATION_KINDS:
            raise ValueError("kind must be one of: " + ", ".join(sorted(DERIVATION_KINDS)))
        origin_uri = require_text(self.origin_uri, "origin_uri")
        if not origin_uri.startswith(("https://", "http://")):
            raise ValueError("origin_uri must be an absolute http(s) URL")
        object.__setattr__(self, "origin_uri", origin_uri)
        object.__setattr__(
            self, "origin_sha256", _require_sha256(self.origin_sha256, "origin_sha256")
        )
        manifest = Path(require_text(self.manifest, "manifest"))
        if manifest.is_absolute() or ".." in manifest.parts or manifest.suffix != ".json":
            raise ValueError("manifest must be a repository-relative .json path")
        object.__setattr__(self, "manifest", manifest.as_posix())
        object.__setattr__(self, "entry", _require_identifier(self.entry, "entry"))
        if self.derived_artifact_sha256 is not None:
            object.__setattr__(
                self,
                "derived_artifact_sha256",
                _require_sha256(self.derived_artifact_sha256, "derived_artifact_sha256"),
            )

    def to_document(self) -> dict[str, object]:
        return {
            "derived_artifact_sha256": self.derived_artifact_sha256,
            "entry": self.entry,
            "kind": self.kind,
            "manifest": self.manifest,
            "origin_sha256": self.origin_sha256,
            "origin_uri": self.origin_uri,
        }

    @classmethod
    def from_document(cls, payload: object) -> SourceDerivation:
        document = _strict_mapping(payload, _DERIVATION_KEYS, "derivation")
        return cls(
            kind=cast(str, document["kind"]),
            origin_uri=cast(str, document["origin_uri"]),
            origin_sha256=cast(str, document["origin_sha256"]),
            manifest=cast(str, document["manifest"]),
            entry=cast(str, document["entry"]),
            derived_artifact_sha256=cast(str | None, document["derived_artifact_sha256"]),
        )


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    """One licensed source document in the procedural corpus."""

    document_id: str
    title: str
    machine_types: Sequence[MachineType]
    licence: LicenceRecord
    acquisition: AcquisitionKind
    source_uri: str
    source_sha256: str
    extraction: ExtractionRecord | None
    text_sha256: str | None
    text_layer: bool
    relevance_tier: RelevanceTier = RelevanceTier.NAMED_UNIT
    derivation: SourceDerivation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "document_id", _require_identifier(self.document_id, "document_id")
        )
        object.__setattr__(self, "title", _require_text_bytes(self.title, "title"))
        types = _require_sequence(self.machine_types, "machine_types", MachineType)
        if not types:
            raise ValueError("machine_types must name at least one MachineType")
        normalised = tuple(cast(MachineType, item) for item in types)
        _require_unique([item.value for item in normalised], "machine_types")
        object.__setattr__(self, "machine_types", normalised)
        if not isinstance(self.licence, LicenceRecord):
            raise TypeError("licence must be a LicenceRecord")
        if not isinstance(self.acquisition, AcquisitionKind):
            raise TypeError("acquisition must be an AcquisitionKind")
        if not isinstance(self.relevance_tier, RelevanceTier):
            raise TypeError("relevance_tier must be a RelevanceTier")
        object.__setattr__(self, "text_layer", _require_flag(self.text_layer, "text_layer"))
        source_uri = require_text(self.source_uri, "source_uri")
        if not source_uri.startswith(("https://", "http://")):
            raise ValueError("source_uri must be an absolute http(s) URL")
        object.__setattr__(self, "source_uri", source_uri)
        object.__setattr__(
            self, "source_sha256", _require_sha256(self.source_sha256, "source_sha256")
        )
        if self.acquisition is AcquisitionKind.BUNDLED_TEXT:
            if self.text_sha256 is None:
                raise ValueError("bundled_text documents must carry text_sha256")
            if not self.licence.allows_redistribution:
                raise ValueError(
                    "a document whose licence forbids redistribution must be declared "
                    "manifest_only instead of bundling its text"
                )
            if not isinstance(self.extraction, ExtractionRecord):
                raise TypeError("bundled_text documents must declare how the text was extracted")
            object.__setattr__(
                self, "text_sha256", _require_sha256(self.text_sha256, "text_sha256")
            )
        else:
            if self.text_sha256 is not None:
                raise ValueError("manifest_only documents must not carry text_sha256")
            if self.extraction is not None:
                raise ValueError("manifest_only documents must not claim an extraction")
            if self.licence.allows_redistribution:
                raise ValueError(
                    "manifest_only documents must not be redistributable; "
                    "a redistributable document is bundled instead"
                )
        if self.derivation is not None:
            if not isinstance(self.derivation, SourceDerivation):
                raise TypeError("derivation must be a SourceDerivation")
            if self.derivation.entry != self.document_id:
                raise ValueError("derivation.entry must name the document it is attached to")

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "acquisition": self.acquisition.value,
            "document_id": self.document_id,
            "extraction": None if self.extraction is None else self.extraction.to_document(),
            "licence": self.licence.to_document(),
            "machine_types": [item.value for item in self.machine_types],
            "relevance_tier": self.relevance_tier.value,
            "source_sha256": self.source_sha256,
            "source_uri": self.source_uri,
            "text_layer": self.text_layer,
            "text_sha256": self.text_sha256,
            "title": self.title,
        }
        if self.derivation is not None:
            document["derivation"] = self.derivation.to_document()
        return document

    @classmethod
    def from_document(cls, payload: object) -> CorpusDocument:
        document = _strict_mapping(
            payload, _DOCUMENT_KEYS, "document", optional=_DOCUMENT_OPTIONAL_KEYS
        )
        machine_types = _require_sequence(document["machine_types"], "machine_types", str)
        extraction = document["extraction"]
        derivation = document.get("derivation")
        return cls(
            document_id=cast(str, document["document_id"]),
            title=cast(str, document["title"]),
            machine_types=tuple(
                MachineType(_enum_value(item, MachineType, "machine_types"))
                for item in machine_types
            ),
            licence=LicenceRecord.from_document(document["licence"]),
            acquisition=AcquisitionKind(
                _enum_value(document["acquisition"], AcquisitionKind, "acquisition")
            ),
            source_uri=cast(str, document["source_uri"]),
            source_sha256=cast(str, document["source_sha256"]),
            extraction=None if extraction is None else ExtractionRecord.from_document(extraction),
            text_sha256=cast(str | None, document["text_sha256"]),
            text_layer=cast(bool, document["text_layer"]),
            relevance_tier=RelevanceTier(
                _enum_value(document["relevance_tier"], RelevanceTier, "relevance_tier")
            ),
            derivation=None if derivation is None else SourceDerivation.from_document(derivation),
        )


@dataclass(frozen=True, slots=True)
class CorpusAsset:
    """One authored asset instance.

    MIMII supplies acoustic events, not an asset hierarchy, so an asset can never be
    MIMII-derived.
    """

    asset_id: str
    machine_type: MachineType
    model_id: str
    site_id: str
    display_name: str
    lineage: Lineage = Lineage.AUTHORED_CURATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _require_identifier(self.asset_id, "asset_id"))
        if not isinstance(self.machine_type, MachineType):
            raise TypeError("machine_type must be a MachineType")
        object.__setattr__(self, "model_id", require_text(self.model_id, "model_id"))
        object.__setattr__(self, "site_id", _require_identifier(self.site_id, "site_id"))
        object.__setattr__(
            self, "display_name", _require_text_bytes(self.display_name, "display_name")
        )
        if not isinstance(self.lineage, Lineage):
            raise TypeError("lineage must be a Lineage")
        if self.lineage is not Lineage.AUTHORED_CURATED:
            raise ValueError("assets are authored; MIMII supplies no asset hierarchy")

    def to_document(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "display_name": self.display_name,
            "lineage": self.lineage.value,
            "machine_type": self.machine_type.value,
            "model_id": self.model_id,
            "site_id": self.site_id,
        }

    @classmethod
    def from_document(cls, payload: object) -> CorpusAsset:
        document = _strict_mapping(payload, _ASSET_KEYS, "asset")
        return cls(
            asset_id=cast(str, document["asset_id"]),
            machine_type=MachineType(
                _enum_value(document["machine_type"], MachineType, "machine_type")
            ),
            model_id=cast(str, document["model_id"]),
            site_id=cast(str, document["site_id"]),
            display_name=cast(str, document["display_name"]),
            lineage=Lineage(_enum_value(document["lineage"], Lineage, "lineage")),
        )


@dataclass(frozen=True, slots=True)
class CorpusSensor:
    """One sensor hosted by an asset; the SSN/SOSA grounding layer."""

    sensor_id: str
    asset_id: str
    property_id: str
    unit: str
    lineage: Lineage = Lineage.AUTHORED_CURATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "sensor_id", _require_identifier(self.sensor_id, "sensor_id"))
        object.__setattr__(self, "asset_id", _require_identifier(self.asset_id, "asset_id"))
        object.__setattr__(self, "property_id", require_text(self.property_id, "property_id"))
        object.__setattr__(self, "unit", require_text(self.unit, "unit"))
        if not isinstance(self.lineage, Lineage):
            raise TypeError("lineage must be a Lineage")
        if self.lineage is not Lineage.AUTHORED_CURATED:
            raise ValueError("sensors are authored; MIMII supplies recordings, not sensors")

    def to_document(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "lineage": self.lineage.value,
            "property_id": self.property_id,
            "sensor_id": self.sensor_id,
            "unit": self.unit,
        }

    @classmethod
    def from_document(cls, payload: object) -> CorpusSensor:
        document = _strict_mapping(payload, _SENSOR_KEYS, "sensor")
        return cls(
            sensor_id=cast(str, document["sensor_id"]),
            asset_id=cast(str, document["asset_id"]),
            property_id=cast(str, document["property_id"]),
            unit=cast(str, document["unit"]),
            lineage=Lineage(_enum_value(document["lineage"], Lineage, "lineage")),
        )


@dataclass(frozen=True, slots=True)
class CorpusObservation:
    """One acoustic event or one authored plant reading, with its declared lineage.

    An authored record may state a numeric ``value`` in the unit of the sensor that made
    it, the scenario ``observed_at`` instant, and the ``operating_state`` it belongs to.
    A record that states none of those carries no information beyond its own identifier,
    which is what a release must not accumulate.
    """

    observation_id: str
    asset_id: str
    label: str
    label_source: str
    lineage: Lineage = Lineage.MIMII_DERIVED
    recording: RecordingReference | None = None
    sensor_id: str | None = None
    value: float | None = None
    observed_at: str | None = None
    operating_state: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_id", _require_identifier(self.observation_id, "observation_id")
        )
        object.__setattr__(self, "asset_id", _require_identifier(self.asset_id, "asset_id"))
        if self.sensor_id is not None:
            object.__setattr__(self, "sensor_id", _require_identifier(self.sensor_id, "sensor_id"))
        label = require_text(self.label, "label")
        label_source = require_text(self.label_source, "label_source")
        if not isinstance(self.lineage, Lineage):
            raise TypeError("lineage must be a Lineage")
        self._require_reading()
        self._require_scenario_time()
        if self.operating_state is not None and self.operating_state not in OPERATING_STATES:
            raise ValueError(
                "operating_state must be one of: " + ", ".join(sorted(OPERATING_STATES))
            )
        if self.lineage is Lineage.MIMII_DERIVED:
            if self.value is not None:
                raise ValueError(
                    "a MIMII-derived event carries a recording and a dataset label, not a "
                    "scalar reading: its value would be invented"
                )
            if self.observed_at is not None:
                raise ValueError(
                    "a MIMII-derived event must not declare observed_at: the dataset records no "
                    "wall-clock time, so any timestamp would be fabricated"
                )
            if self.operating_state is not None:
                raise ValueError(
                    "a MIMII-derived event must not declare operating_state: an operating state "
                    "is authored scenario context, not dataset content"
                )
            if self.recording is None:
                raise ValueError("a mimii_derived observation must carry its recording identity")
            if not isinstance(self.recording, RecordingReference):
                raise TypeError("recording must be a RecordingReference")
            if label not in _MIMII_LABELS:
                raise ValueError("label must be normal or abnormal for a MIMII-derived event")
            if label_source != _MIMII_LABEL_SOURCE:
                raise ValueError(
                    f"label_source must be {_MIMII_LABEL_SOURCE!r}: the label comes from the "
                    "dataset, not from a detector this study ran"
                )
        else:
            if self.recording is not None:
                raise ValueError("an authored observation must not claim a MIMII recording")
            if label_source != _AUTHORED_LABEL_SOURCE:
                raise ValueError(
                    f"label_source must be {_AUTHORED_LABEL_SOURCE!r} for authored context"
                )
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "label_source", label_source)

    def _require_reading(self) -> None:
        """Validate a scalar reading and the state it belongs to.

        The sensor carries the unit, so a number without one is not evidence: it would be
        dimensionless and impossible to interpret. A reading also has to say which phase
        of the scenario it belongs to, because a value with no context is an orphan.
        """

        if self.value is None:
            return
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("value must be a number")
        value = float(self.value)
        if not math.isfinite(value):
            raise ValueError("value must be a finite number")
        object.__setattr__(self, "value", value)
        if self.sensor_id is None:
            raise ValueError(
                "an observation that states a value must declare the sensor that made it: "
                "the sensor defines the unit"
            )
        if self.operating_state is None:
            raise ValueError("an observation that states a value must declare its operating state")

    def _require_scenario_time(self) -> None:
        """Validate the scenario instant as an unambiguous UTC timestamp."""

        if self.observed_at is None:
            return
        if not isinstance(self.observed_at, str):
            raise TypeError("observed_at must be a string")
        if _UTC_TIMESTAMP_PATTERN.fullmatch(self.observed_at) is None:
            raise ValueError("observed_at must be a UTC timestamp such as 2026-11-13T00:00:00Z")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"observed_at is not a calendar instant: {error}") from error

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "asset_id": self.asset_id,
            "label": self.label,
            "label_source": self.label_source,
            "lineage": self.lineage.value,
            "observation_id": self.observation_id,
            "recording": None if self.recording is None else self.recording.to_document(),
            "sensor_id": self.sensor_id,
        }
        # Only a record that states them serialises them, so the frozen releases keep
        # their canonical bytes.
        if self.value is not None:
            document["value"] = self.value
        if self.observed_at is not None:
            document["observed_at"] = self.observed_at
        if self.operating_state is not None:
            document["operating_state"] = self.operating_state
        return document

    @classmethod
    def from_document(cls, payload: object) -> CorpusObservation:
        document = _strict_mapping(
            payload, _OBSERVATION_KEYS, "observation", optional=_OBSERVATION_OPTIONAL_KEYS
        )
        recording = document["recording"]
        return cls(
            observation_id=cast(str, document["observation_id"]),
            asset_id=cast(str, document["asset_id"]),
            label=cast(str, document["label"]),
            label_source=cast(str, document["label_source"]),
            lineage=Lineage(_enum_value(document["lineage"], Lineage, "lineage")),
            recording=None if recording is None else RecordingReference.from_document(recording),
            sensor_id=cast(str | None, document["sensor_id"]),
            value=cast(float | None, document.get("value")),
            observed_at=cast(str | None, document.get("observed_at")),
            operating_state=cast(str | None, document.get("operating_state")),
        )


@dataclass(frozen=True, slots=True)
class CorpusProcedure:
    """One authored maintenance procedure, optionally quoting corpus chunks."""

    procedure_id: str
    machine_type: MachineType
    asset_ids: Sequence[str]
    lineage: Lineage
    text: str
    evidence_chunk_ids: Sequence[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "procedure_id", _require_identifier(self.procedure_id, "procedure_id")
        )
        if not isinstance(self.machine_type, MachineType):
            raise TypeError("machine_type must be a MachineType")
        object.__setattr__(
            self,
            "asset_ids",
            _require_identifier_sequence(self.asset_ids, "asset_ids", allow_empty=False),
        )
        if not isinstance(self.lineage, Lineage):
            raise TypeError("lineage must be a Lineage")
        if self.lineage is not Lineage.AUTHORED_CURATED:
            raise ValueError("procedures are authored; MIMII supplies recordings, not procedures")
        object.__setattr__(self, "text", _require_text_bytes(self.text, "text"))
        object.__setattr__(
            self,
            "evidence_chunk_ids",
            _require_identifier_sequence(
                self.evidence_chunk_ids, "evidence_chunk_ids", allow_empty=False
            ),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "asset_ids": list(self.asset_ids),
            "evidence_chunk_ids": list(self.evidence_chunk_ids),
            "lineage": self.lineage.value,
            "machine_type": self.machine_type.value,
            "procedure_id": self.procedure_id,
            "text": self.text,
        }

    @classmethod
    def from_document(cls, payload: object) -> CorpusProcedure:
        document = _strict_mapping(payload, _PROCEDURE_KEYS, "procedure")
        return cls(
            procedure_id=cast(str, document["procedure_id"]),
            machine_type=MachineType(
                _enum_value(document["machine_type"], MachineType, "machine_type")
            ),
            asset_ids=cast(Sequence[str], document["asset_ids"]),
            lineage=Lineage(_enum_value(document["lineage"], Lineage, "lineage")),
            text=cast(str, document["text"]),
            evidence_chunk_ids=cast(Sequence[str], document["evidence_chunk_ids"]),
        )


@dataclass(frozen=True, slots=True)
class CorpusChunk:
    """One source-located chunk of a bundled document."""

    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    start_line: int
    end_line: int
    text_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_id", _require_identifier(self.chunk_id, "chunk_id"))
        object.__setattr__(
            self, "document_id", _require_identifier(self.document_id, "document_id")
        )
        object.__setattr__(self, "ordinal", _require_positive_int(self.ordinal, "ordinal"))
        object.__setattr__(self, "text", _require_text_bytes(self.text, "text"))
        start_line = _require_positive_int(self.start_line, "start_line")
        end_line = _require_positive_int(self.end_line, "end_line")
        if start_line > end_line:
            raise ValueError("start_line must not exceed end_line")
        object.__setattr__(self, "start_line", start_line)
        object.__setattr__(self, "end_line", end_line)
        digest = _require_sha256(self.text_sha256, "text_sha256")
        # A syntactically valid digest that does not match the text would let an
        # edited chunk load while still advertising the original identity.
        if digest != hashlib.sha256(self.text.encode("utf-8")).hexdigest():
            raise ValueError("text_sha256 must be the SHA-256 of text")
        object.__setattr__(self, "text_sha256", digest)

    def to_document(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "end_line": self.end_line,
            "ordinal": self.ordinal,
            "start_line": self.start_line,
            "text": self.text,
            "text_sha256": self.text_sha256,
        }

    @classmethod
    def from_document(cls, payload: object) -> CorpusChunk:
        document = _strict_mapping(payload, _CHUNK_KEYS, "chunk")
        return cls(
            chunk_id=cast(str, document["chunk_id"]),
            document_id=cast(str, document["document_id"]),
            ordinal=cast(int, document["ordinal"]),
            text=cast(str, document["text"]),
            start_line=cast(int, document["start_line"]),
            end_line=cast(int, document["end_line"]),
            text_sha256=cast(str, document["text_sha256"]),
        )


@dataclass(frozen=True, slots=True)
class CorpusQuery:
    """One development-split query with its expected evidence and rubric."""

    query_id: str
    category: QueryCategory
    split: str
    text: str
    expected_evidence_refs: Sequence[str]
    expected_action: str | None
    rubric: str

    def __post_init__(self) -> None:
        query_id = require_text(self.query_id, "query_id")
        if _QUERY_ID_PATTERN.fullmatch(query_id) is None:
            raise ValueError("query_id must be atq-NNN or a prefixed identifier")
        object.__setattr__(self, "query_id", query_id)
        if not isinstance(self.category, QueryCategory):
            raise TypeError("category must be a QueryCategory")
        split = require_text(self.split, "split")
        if split != DEVELOPMENT_SPLIT:
            raise ValueError(
                f"split must be {DEVELOPMENT_SPLIT!r}; held-out questions are released by the "
                "blinded-packet issue, never here"
            )
        object.__setattr__(self, "split", split)
        object.__setattr__(self, "text", _require_text_bytes(self.text, "text"))
        refs = _require_identifier_sequence(
            self.expected_evidence_refs, "expected_evidence_refs", allow_empty=True
        )
        action = self.expected_action
        if action is not None:
            action = _require_text_bytes(action, "expected_action")
        object.__setattr__(self, "rubric", _require_text_bytes(self.rubric, "rubric"))
        if self.category in TRAP_CATEGORIES:
            if refs:
                raise ValueError("expected_evidence_refs must be empty for trap queries")
            if action is not None:
                raise ValueError("expected_action must be absent for trap queries")
        else:
            if not refs:
                raise ValueError("expected_evidence_refs must not be empty for non-trap queries")
        object.__setattr__(self, "expected_evidence_refs", refs)
        object.__setattr__(self, "expected_action", action)

    @property
    def expected_terminal_status(self) -> str | None:
        """Return the dataset contract's status for a trap query."""

        if self.category in TRAP_CATEGORIES:
            return TRAP_TERMINAL_STATUS[self.category].value
        return None

    def to_document(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "expected_action": self.expected_action,
            "expected_evidence_refs": list(self.expected_evidence_refs),
            "query_id": self.query_id,
            "rubric": self.rubric,
            "split": self.split,
            "text": self.text,
        }

    @classmethod
    def from_document(cls, payload: object) -> CorpusQuery:
        document = _strict_mapping(payload, _QUERY_KEYS, "query")
        return cls(
            query_id=cast(str, document["query_id"]),
            category=QueryCategory(_enum_value(document["category"], QueryCategory, "category")),
            split=cast(str, document["split"]),
            text=cast(str, document["text"]),
            expected_evidence_refs=cast(Sequence[str], document["expected_evidence_refs"]),
            expected_action=cast(str | None, document["expected_action"]),
            rubric=cast(str, document["rubric"]),
        )


@dataclass(frozen=True, slots=True)
class ScenarioCorpus:
    """One immutable, hash-addressed scenario-corpus release."""

    corpus_id: str
    version: str
    documents: Sequence[CorpusDocument]
    assets: Sequence[CorpusAsset]
    observations: Sequence[CorpusObservation]
    sensors: Sequence[CorpusSensor]
    procedures: Sequence[CorpusProcedure]
    chunks: Sequence[CorpusChunk]
    queries: Sequence[CorpusQuery]
    provenance_profile: str = "legacy"

    def __post_init__(self) -> None:
        object.__setattr__(self, "corpus_id", require_text(self.corpus_id, "corpus_id"))
        object.__setattr__(self, "version", require_text(self.version, "version"))
        profile = require_text(self.provenance_profile, "provenance_profile")
        if profile not in PROVENANCE_PROFILES:
            raise ValueError(
                "provenance_profile must be one of: " + ", ".join(sorted(PROVENANCE_PROFILES))
            )
        object.__setattr__(self, "provenance_profile", profile)
        documents = _freeze_records(
            self.documents, "documents", CorpusDocument, key=lambda item: item.document_id
        )
        assets = _freeze_records(self.assets, "assets", CorpusAsset, key=lambda item: item.asset_id)
        observations = _freeze_records(
            self.observations,
            "observations",
            CorpusObservation,
            key=lambda item: item.observation_id,
        )
        sensors = _freeze_records(
            self.sensors, "sensors", CorpusSensor, key=lambda item: item.sensor_id
        )
        procedures = _freeze_records(
            self.procedures,
            "procedures",
            CorpusProcedure,
            key=lambda item: item.procedure_id,
        )
        chunks = _freeze_records(self.chunks, "chunks", CorpusChunk, key=lambda item: item.chunk_id)
        queries = _freeze_records(
            self.queries, "queries", CorpusQuery, key=lambda item: item.query_id
        )

        for name, values in (
            ("documents", [item.document_id for item in documents]),
            ("assets", [item.asset_id for item in assets]),
            ("observations", [item.observation_id for item in observations]),
            ("sensors", [item.sensor_id for item in sensors]),
            ("procedures", [item.procedure_id for item in procedures]),
            ("chunks", [item.chunk_id for item in chunks]),
            ("queries", [item.query_id for item in queries]),
        ):
            _require_unique(values, name)

        object.__setattr__(self, "documents", documents)
        if profile != "complete":
            derived = [item.document_id for item in documents if item.derivation is not None]
            if derived:
                raise ValueError(
                    f"document {derived[0]!r} declares a derivation but the release does not "
                    "publish complete provenance"
                )
        object.__setattr__(self, "assets", assets)
        reading_ids = [
            item.observation_id
            for item in observations
            if item.value is not None
            or item.observed_at is not None
            or item.operating_state is not None
        ]
        if reading_ids and profile != "complete":
            raise ValueError(
                f"observation {reading_ids[0]!r} states a reading, a scenario time or an "
                "operating state but the release does not publish complete provenance"
            )
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "sensors", sensors)
        object.__setattr__(self, "procedures", procedures)
        object.__setattr__(self, "chunks", chunks)
        object.__setattr__(self, "queries", queries)

        self._require_references()

    def _require_references(self) -> None:
        document_ids = {item.document_id for item in self.documents}
        asset_ids = {item.asset_id for item in self.assets}
        observation_ids = {item.observation_id for item in self.observations}
        chunk_ids = {item.chunk_id for item in self.chunks}
        for chunk in self.chunks:
            if chunk.document_id not in document_ids:
                raise ValueError(f"chunk {chunk.chunk_id!r} references an undeclared document")
            document = next(
                item for item in self.documents if item.document_id == chunk.document_id
            )
            if document.acquisition is not AcquisitionKind.BUNDLED_TEXT:
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} quotes a manifest_only document; "
                    "only bundled text may be chunked"
                )
        sensor_ids = {item.sensor_id for item in self.sensors}
        for sensor in self.sensors:
            if sensor.asset_id not in asset_ids:
                raise ValueError(f"sensor {sensor.sensor_id!r} is hosted by an undeclared asset")
        sensor_assets = {item.sensor_id: item.asset_id for item in self.sensors}
        for observation in self.observations:
            if observation.sensor_id is not None and observation.sensor_id not in sensor_ids:
                raise ValueError(
                    f"observation {observation.observation_id!r} references an undeclared sensor"
                )
            if observation.asset_id not in asset_ids:
                raise ValueError(
                    f"observation {observation.observation_id!r} references an undeclared asset"
                )
            if (
                observation.sensor_id is not None
                and sensor_assets[observation.sensor_id] != observation.asset_id
            ):
                raise ValueError(
                    f"observation {observation.observation_id!r} is made by a sensor hosted by "
                    "a different asset"
                )
        for procedure in self.procedures:
            for asset_id in procedure.asset_ids:
                if asset_id not in asset_ids:
                    raise ValueError(
                        f"procedure {procedure.procedure_id!r} references an undeclared asset"
                    )
            for chunk_id in procedure.evidence_chunk_ids:
                if chunk_id not in chunk_ids:
                    raise ValueError(
                        f"procedure {procedure.procedure_id!r} references undeclared evidence"
                    )
        evidence = observation_ids | chunk_ids | {item.procedure_id for item in self.procedures}
        evidence |= asset_ids | document_ids
        for query in self.queries:
            for reference in query.expected_evidence_refs:
                if reference not in evidence:
                    raise ValueError(
                        f"query {query.query_id!r} cites evidence that is not in the release: "
                        f"{reference!r}"
                    )

    @property
    def identifier_only_observation_ids(self) -> tuple[str, ...]:
        """Return the observations that state nothing beyond their own identifier.

        A record with no reading, no event identity and no time cannot support any claim;
        it only inflates the graph. A release reports them so a build can refuse to publish.
        """

        return tuple(
            item.observation_id
            for item in self.observations
            if item.value is None and item.recording is None and item.observed_at is None
        )

    @property
    def share_alike_document_ids(self) -> tuple[str, ...]:
        """Return the documents whose licence imposes a share-alike obligation."""

        return tuple(
            document.document_id for document in self.documents if document.licence.share_alike
        )

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "assets": [item.to_document() for item in self.assets],
            "chunks": [item.to_document() for item in self.chunks],
            "contract_version": CORPUS_CONTRACT_VERSION,
            "corpus_id": self.corpus_id,
            "documents": [item.to_document() for item in self.documents],
            "observations": [item.to_document() for item in self.observations],
            "procedures": [item.to_document() for item in self.procedures],
            "sensors": [item.to_document() for item in self.sensors],
            "queries": [item.to_document() for item in self.queries],
            "version": self.version,
        }
        # Only a release that opts in records the field, so the canonical bytes of
        # the frozen legacy releases stay identical.
        if self.provenance_profile != "legacy":
            document["provenance_profile"] = self.provenance_profile
        return document

    @property
    def document_sha256(self) -> str:
        """Return the SHA-256 of the whole release."""

        return sha256_of(self.to_document())

    @property
    def development_sha256(self) -> str:
        """Return the SHA-256 of the development split a run may bind."""

        return sha256_of(
            {
                "contract_version": CORPUS_CONTRACT_VERSION,
                "corpus_id": self.corpus_id,
                "queries": [query.to_document() for query in self.queries],
                "split": DEVELOPMENT_SPLIT,
                "version": self.version,
            }
        )

    @classmethod
    def from_document(cls, payload: object) -> ScenarioCorpus:
        document = _strict_mapping(payload, _CORPUS_KEYS, "corpus", optional=_CORPUS_OPTIONAL_KEYS)
        if document["contract_version"] != CORPUS_CONTRACT_VERSION:
            raise ValueError(f"contract_version must be {CORPUS_CONTRACT_VERSION!r}")
        return cls(
            corpus_id=cast(str, document["corpus_id"]),
            version=cast(str, document["version"]),
            provenance_profile=cast(str, document.get("provenance_profile", "legacy")),
            documents=tuple(
                CorpusDocument.from_document(item)
                for item in _require_sequence(document["documents"], "documents", Mapping)
            ),
            assets=tuple(
                CorpusAsset.from_document(item)
                for item in _require_sequence(document["assets"], "assets", Mapping)
            ),
            observations=tuple(
                CorpusObservation.from_document(item)
                for item in _require_sequence(document["observations"], "observations", Mapping)
            ),
            procedures=tuple(
                CorpusProcedure.from_document(item)
                for item in _require_sequence(document["procedures"], "procedures", Mapping)
            ),
            sensors=tuple(
                CorpusSensor.from_document(item)
                for item in _require_sequence(document["sensors"], "sensors", Mapping)
            ),
            chunks=tuple(
                CorpusChunk.from_document(item)
                for item in _require_sequence(document["chunks"], "chunks", Mapping)
            ),
            queries=tuple(
                CorpusQuery.from_document(item)
                for item in _require_sequence(document["queries"], "queries", Mapping)
            ),
        )


def _http_uri(value: str, label: str) -> URIRef:
    """Return ``value`` as a URIRef, refusing anything that is not an absolute URL.

    An annotation glued onto a URL (for example a licence note) serialises as an
    invalid IRI, and rdflib raises that deep inside the serializer.
    """

    if not value.startswith(("http://", "https://")) or any(
        character in value for character in " \t\n"
    ):
        raise ValueError(f"{label} must be an absolute http(s) URL: {value!r}")
    return URIRef(value)


def corpus_to_trig(corpus: ScenarioCorpus) -> bytes:
    """Serialise the release as TriG in one corpus-context named graph."""

    if not isinstance(corpus, ScenarioCorpus):
        raise TypeError("corpus must be a ScenarioCorpus")
    dataset = Dataset()
    graph = dataset.graph(URIRef(CONTEXT_GRAPH))
    for document in corpus.documents:
        subject = _iri(document.document_id)
        graph.add((subject, RDF.type, CORPUS.Document))
        graph.add((subject, CORPUS.title, Literal(document.title)))
        graph.add((subject, CORPUS.licenceIdentifier, Literal(document.licence.identifier)))
        graph.add((subject, CORPUS.licenceBasis, Literal(document.licence.basis.value)))
        graph.add(
            (
                subject,
                CORPUS.termsUrl,
                _http_uri(document.licence.terms_url, "licence terms_url"),
            )
        )
        graph.add((subject, CORPUS.attribution, Literal(document.licence.attribution)))
        graph.add(
            (
                subject,
                CORPUS.shareAlike,
                Literal(document.licence.share_alike, datatype=XSD.boolean),
            )
        )
        graph.add((subject, CORPUS.acquisition, Literal(document.acquisition.value)))
        graph.add((subject, CORPUS.lineage, Literal(Lineage.AUTHORED_CURATED.value)))
        if corpus.provenance_profile == "complete":
            # Without these a SPARQL consumer can reach a chunk's document but not
            # the artifact, extraction or rights record that document claims.
            graph.add((subject, CORPUS.sourceUri, _http_uri(document.source_uri, "source_uri")))
            graph.add((subject, CORPUS.sourceSha256, Literal(document.source_sha256)))
            graph.add((subject, CORPUS.relevanceTier, Literal(document.relevance_tier.value)))
            graph.add(
                (subject, CORPUS.textLayer, Literal(document.text_layer, datatype=XSD.boolean))
            )
            graph.add(
                (
                    subject,
                    CORPUS.allowsRedistribution,
                    Literal(document.licence.allows_redistribution, datatype=XSD.boolean),
                )
            )
            if document.text_sha256 is not None:
                graph.add((subject, CORPUS.textSha256, Literal(document.text_sha256)))
            if document.extraction is not None:
                graph.add((subject, CORPUS.extractionTool, Literal(document.extraction.tool)))
                graph.add(
                    (
                        subject,
                        CORPUS.extractionToolVersion,
                        Literal(document.extraction.tool_version),
                    )
                )
                graph.add((subject, CORPUS.extractionRule, Literal(document.extraction.rule)))
        if document.derivation is not None:
            derivation = document.derivation
            graph.add((subject, CORPUS.derivationKind, Literal(derivation.kind)))
            graph.add(
                (
                    subject,
                    CORPUS.originUri,
                    _http_uri(derivation.origin_uri, "derivation origin_uri"),
                )
            )
            graph.add((subject, CORPUS.originSha256, Literal(derivation.origin_sha256)))
            graph.add((subject, CORPUS.derivationManifest, Literal(derivation.manifest)))
            graph.add((subject, CORPUS.derivationEntry, Literal(derivation.entry)))
            if derivation.derived_artifact_sha256 is not None:
                graph.add(
                    (
                        subject,
                        CORPUS.derivedArtifactSha256,
                        Literal(derivation.derived_artifact_sha256),
                    )
                )
        for machine in document.machine_types:
            graph.add((subject, CORPUS.coversMachineType, Literal(machine.value)))
    for asset in corpus.assets:
        subject = _iri(asset.asset_id)
        graph.add((subject, RDF.type, CORPUS.Asset))
        graph.add((subject, CORPUS.machineType, Literal(asset.machine_type.value)))
        graph.add((subject, CORPUS.modelId, Literal(asset.model_id)))
        graph.add((subject, CORPUS.locatedAtSite, Literal(asset.site_id)))
        graph.add((subject, CORPUS.displayName, Literal(asset.display_name)))
        graph.add((subject, CORPUS.lineage, Literal(asset.lineage.value)))
    for sensor in corpus.sensors:
        subject = _iri(sensor.sensor_id)
        graph.add((subject, RDF.type, SOSA.Sensor))
        graph.add((subject, SOSA.isHostedBy, _iri(sensor.asset_id)))
        graph.add((subject, CORPUS.observesProperty, Literal(sensor.property_id)))
        graph.add((subject, CORPUS.unit, Literal(sensor.unit)))
        graph.add((subject, CORPUS.lineage, Literal(sensor.lineage.value)))
    for observation in corpus.observations:
        subject = _iri(observation.observation_id)
        graph.add((subject, RDF.type, SOSA.Observation))
        if observation.sensor_id is not None:
            graph.add((subject, SOSA.madeBySensor, _iri(observation.sensor_id)))
        graph.add((subject, SOSA.hasFeatureOfInterest, _iri(observation.asset_id)))
        graph.add((subject, CORPUS.label, Literal(observation.label)))
        graph.add((subject, CORPUS.labelSource, Literal(observation.label_source)))
        graph.add((subject, CORPUS.lineage, Literal(observation.lineage.value)))
        if observation.operating_state is not None:
            graph.add((subject, CORPUS.operatingState, Literal(observation.operating_state)))
        if observation.value is not None:
            graph.add((subject, CORPUS.value, Literal(observation.value, datatype=XSD.decimal)))
        if observation.observed_at is not None:
            graph.add(
                (
                    subject,
                    CORPUS.observedAt,
                    Literal(observation.observed_at, datatype=XSD.dateTime),
                )
            )
        recording = observation.recording
        if recording is not None:
            graph.add((subject, CORPUS.derivedFromRecording, Literal(recording.member_path)))
            graph.add((subject, CORPUS.recordingArchive, Literal(recording.archive_key)))
            graph.add((subject, CORPUS.recordingSha256, Literal(recording.member_sha256)))
            graph.add((subject, CORPUS.datasetRecord, Literal(recording.dataset_record_id)))
            if corpus.provenance_profile == "complete":
                # A bare DOI is an identifier, not an absolute IRI: turning it into a
                # URIRef makes rdflib resolve it against the working directory.
                graph.add((subject, CORPUS.datasetDoi, Literal(recording.dataset_doi)))
                graph.add((subject, CORPUS.recordingCrc32, Literal(recording.member_crc32)))
                graph.add(
                    (
                        subject,
                        CORPUS.recordingSeconds,
                        Literal(recording.seconds, datatype=XSD.decimal),
                    )
                )
                graph.add(
                    (
                        subject,
                        CORPUS.sampleRateHz,
                        Literal(recording.sample_rate_hz, datatype=XSD.integer),
                    )
                )
                graph.add(
                    (subject, CORPUS.channels, Literal(recording.channels, datatype=XSD.integer))
                )
                graph.add(
                    (
                        subject,
                        CORPUS.bitsPerSample,
                        Literal(recording.bits_per_sample, datatype=XSD.integer),
                    )
                )
    for procedure in corpus.procedures:
        subject = _iri(procedure.procedure_id)
        graph.add((subject, RDF.type, CORPUS.Procedure))
        graph.add((subject, CORPUS.machineType, Literal(procedure.machine_type.value)))
        graph.add((subject, CORPUS.text, Literal(procedure.text)))
        graph.add((subject, CORPUS.lineage, Literal(procedure.lineage.value)))
        for asset_id in procedure.asset_ids:
            graph.add((subject, CORPUS.applicableAsset, _iri(asset_id)))
        for chunk_id in procedure.evidence_chunk_ids:
            graph.add((subject, CORPUS.supportedByChunk, _iri(chunk_id)))
    for chunk in corpus.chunks:
        subject = _iri(chunk.chunk_id)
        graph.add((subject, RDF.type, CORPUS.DocumentChunk))
        graph.add((subject, CORPUS.partOfDocument, _iri(chunk.document_id)))
        graph.add((subject, CORPUS.ordinal, Literal(chunk.ordinal, datatype=XSD.integer)))
        graph.add((subject, CORPUS.startLine, Literal(chunk.start_line, datatype=XSD.integer)))
        graph.add((subject, CORPUS.endLine, Literal(chunk.end_line, datatype=XSD.integer)))
        graph.add((subject, CORPUS.text, Literal(chunk.text)))
        graph.add((subject, CORPUS.textSha256, Literal(chunk.text_sha256)))
    return dataset.serialize(format="trig").encode("utf-8")


def build_corpus_release(document: Mapping[str, object]) -> bytes:
    """Return the canonical bytes of a validated release document."""

    corpus = ScenarioCorpus.from_document(document)
    return canonical_json(corpus.to_document()).encode("utf-8")


def load_corpus_release(path: Path) -> ScenarioCorpus:
    """Load and validate one release with strict duplicate-key handling."""

    payload = cast(
        object,
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_keys),
    )
    return ScenarioCorpus.from_document(payload)
