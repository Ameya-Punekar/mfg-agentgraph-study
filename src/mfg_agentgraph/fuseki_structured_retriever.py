"""Fuseki-backed structured retrieval preserving the deterministic result contract."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)
from mfg_agentgraph.stage_instrumentation import (
    StageError,
    StageErrorCode,
    StageEvent,
    StageName,
    TerminalStatus,
)
from mfg_agentgraph.structured_retrieval import (
    StructuredObservation,
    StructuredRetrievalResult,
    StructuredSupportRecord,
)

FUSEKI_STRUCTURED_RETRIEVER_NAME = "fuseki_sparql"

_EXPECTED_ASSET_ID = "ex:Pump_12"
_EXPECTED_LOCATION_ID = "ex:PumpStation_12"
_EXPECTED_OBSERVATION_ID = "ex:Observation_Pump12_2026-05-18T14:03:00Z"
_EXPECTED_OBSERVED_AT = "2026-05-18T14:03:00Z"
_EXPECTED_SIGNAL = "anomalous_sound"
_EXPECTED_ANOMALY = "anomalous_sound"
_EXPECTED_DESCRIPTION = "Anomalous sound detected at Pump_12 at 14:03 UTC."
_EXPECTED_PROCEDURE_ID = "ex:Procedure_InspectInletCavitation_Pump12"
_EXPECTED_EVIDENCE_ID = "ex:EvidenceEdge_001"
_EXPECTED_PREDICATE = "ex:hasRecommendedProcedure"
_XSD_DATETIME = "http://www.w3.org/2001/XMLSchema#dateTime"
_SOSA = "http://www.w3.org/ns/sosa/"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_MAX_RESPONSE_BYTES = 1_000_000
_RESULT_VARS = (
    "asset",
    "location",
    "observation",
    "observedAt",
    "signal",
    "anomaly",
    "description",
    "procedure",
    "evidence",
    "predicate",
)
_FORBIDDEN_IRI_CHARACTERS = frozenset('<>"{}|^`\\')


@dataclass(frozen=True, slots=True)
class FusekiStructuredRetrieverConfig:
    """Trusted, immutable connection and named-graph configuration."""

    query_endpoint: str
    factory_graph: str
    shapes_graph: str
    provenance_graph: str
    resource_namespace: str
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        endpoint = _validate_endpoint(self.query_endpoint)
        factory = _validate_absolute_iri(self.factory_graph, "factory_graph")
        shapes = _validate_absolute_iri(self.shapes_graph, "shapes_graph")
        provenance = _validate_absolute_iri(self.provenance_graph, "provenance_graph")
        namespace = _validate_absolute_iri(self.resource_namespace, "resource_namespace")
        if len({factory, shapes, provenance}) != 3:
            raise ValueError("named graph IRIs must be distinct")
        timeout = _validate_timeout(self.timeout_seconds)
        object.__setattr__(self, "query_endpoint", endpoint)
        object.__setattr__(self, "factory_graph", factory)
        object.__setattr__(self, "shapes_graph", shapes)
        object.__setattr__(self, "provenance_graph", provenance)
        object.__setattr__(self, "resource_namespace", namespace)
        object.__setattr__(self, "timeout_seconds", timeout)


@dataclass(frozen=True, slots=True)
class FusekiStructuredRetriever:
    """Retrieve Pump_12 structured support from an explicit Fuseki query endpoint."""

    config: FusekiStructuredRetrieverConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, FusekiStructuredRetrieverConfig):
            raise TypeError("config must be a FusekiStructuredRetrieverConfig")

    def retrieve(
        self,
        *,
        resolved_asset: KnownAsset,
        retrieval_run_id: str,
        query_id: str,
    ) -> StructuredRetrievalResult:
        """Query the configured factory graph and fail closed on any service defect."""

        _validate_asset(resolved_asset)
        run_id = _require_strict_nonblank(retrieval_run_id, "retrieval_run_id")
        normalized_query_id = _require_strict_nonblank(query_id, "query_id")
        input_ids = (resolved_asset.asset_id, normalized_query_id)
        if resolved_asset.asset_id != _EXPECTED_ASSET_ID:
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                0,
                "resolved_asset.asset_id",
                "resolved asset is not supported by the Pump_12 service contract",
            )

        query = _build_query(self.config)
        started = perf_counter_ns()
        try:
            payload = _post_sparql_query(self.config, query)
            observation, support = _parse_result(payload, self.config.resource_namespace)
        except _RetrievalFailure as exc:
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                _duration_ms(started),
                exc.field,
                exc.detail,
            )
        except Exception:
            return _failure(
                resolved_asset,
                run_id,
                input_ids,
                _duration_ms(started),
                "fuseki_service",
                "unexpected Fuseki retrieval failure",
            )

        reference = EvidenceReference(
            kind=EvidenceKind.KG_EDGE,
            source=self.config.factory_graph,
            stable_id=support.evidence_id,
            retrieval=RetrievalMetadata(
                retrieval_run_id=run_id,
                query_id=normalized_query_id,
                retriever_name=FUSEKI_STRUCTURED_RETRIEVER_NAME,
                rank=1,
                score=1.0,
            ),
            validation_status=EvidenceValidationStatus.VALIDATED,
        )
        event = StageEvent(
            stage=StageName.STRUCTURED_RETRIEVAL,
            run_id=run_id,
            status=TerminalStatus.PASSED,
            duration_ms=_duration_ms(started),
            input_ids=input_ids,
            output_ids=(observation.observation_id, support.procedure_id, support.evidence_id),
        )
        return StructuredRetrievalResult(
            status=TerminalStatus.PASSED,
            asset=resolved_asset,
            observations=(observation,),
            support_records=(support,),
            evidence_references=(reference,),
            evidence_catalog=EvidenceCatalog((reference,)),
            event=event,
        )


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class _RetrievalFailure(Exception):
    def __init__(self, field: str, detail: str) -> None:
        super().__init__(detail)
        self.field = field
        self.detail = detail


def _build_query(config: FusekiStructuredRetrieverConfig) -> str:
    namespace = config.resource_namespace
    asset = f"{namespace}Pump_12"
    located_at = f"{namespace}locatedAt"
    recommended = f"{namespace}hasRecommendedProcedure"
    applicable_asset = f"{namespace}applicableAsset"
    requires_observation = f"{namespace}requiresObservation"
    signal = f"{namespace}signal"
    anomaly = f"{namespace}anomaly"
    description = f"{namespace}description"
    evidence_edge = f"{namespace}EvidenceEdge"
    return f"""SELECT {" ".join(f"?{name}" for name in _RESULT_VARS)}
WHERE {{
  GRAPH <{config.factory_graph}> {{
    VALUES ?asset {{ <{asset}> }}
    ?asset <{located_at}> ?location ;
           <{recommended}> ?procedure .
    ?observation a <{_SOSA}Observation> ;
                 <{_SOSA}hasFeatureOfInterest> ?asset ;
                 <{_SOSA}resultTime> ?observedAt ;
                 <{signal}> ?signal ;
                 <{anomaly}> ?anomaly ;
                 <{description}> ?description .
    ?procedure a <{namespace}Procedure> ;
               <{applicable_asset}> ?asset ;
               <{requires_observation}> ?observation .
    ?evidence a <{evidence_edge}> ;
              <{_RDF}subject> ?asset ;
              <{_RDF}predicate> ?predicate ;
              <{_RDF}object> ?procedure ;
              <{requires_observation}> ?observation .
    FILTER (?predicate = <{recommended}>)
  }}
}}
"""


def _post_sparql_query(config: FusekiStructuredRetrieverConfig, query: str) -> bytes:
    request = Request(
        config.query_endpoint,
        data=query.encode("utf-8"),
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/sparql-query; charset=utf-8",
        },
        method="POST",
    )
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler())
    try:
        with opener.open(request, timeout=config.timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.partition(";")[0].strip().lower()
            if media_type != "application/sparql-results+json":
                raise _RetrievalFailure(
                    "sparql_results", "Fuseki response media type is not SPARQL Results JSON"
                )
            body: bytes = response.read(_MAX_RESPONSE_BYTES + 1)
    except _RetrievalFailure:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise _RetrievalFailure("fuseki_service", "Fuseki query request failed") from exc
    if len(body) > _MAX_RESPONSE_BYTES:
        raise _RetrievalFailure("sparql_results", "Fuseki response exceeds the size limit")
    return body


def _parse_result(
    payload: bytes, resource_namespace: str
) -> tuple[StructuredObservation, StructuredSupportRecord]:
    try:
        document = json.loads(payload, object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _RetrievalFailure("sparql_results", "Fuseki returned malformed JSON") from exc
    if not isinstance(document, dict) or set(document) != {"head", "results"}:
        raise _RetrievalFailure("sparql_results", "SPARQL result envelope is invalid")
    head = document["head"]
    results = document["results"]
    if not isinstance(head, dict) or head.get("vars") != list(_RESULT_VARS):
        raise _RetrievalFailure("sparql_results", "SPARQL result variables are invalid")
    if not isinstance(results, dict) or set(results) != {"bindings"}:
        raise _RetrievalFailure("sparql_results", "SPARQL result bindings are invalid")
    bindings = results["bindings"]
    if not isinstance(bindings, list) or len(bindings) != 1:
        raise _RetrievalFailure(
            "sparql_results", "SPARQL query must return exactly one support row"
        )
    row = bindings[0]
    if not isinstance(row, dict) or set(row) != set(_RESULT_VARS):
        raise _RetrievalFailure("sparql_results", "SPARQL support row is invalid")

    asset = _compact_uri(row["asset"], resource_namespace)
    location = _compact_uri(row["location"], resource_namespace)
    observation_id = _compact_uri(row["observation"], resource_namespace)
    observed_at = _literal(row["observedAt"], datatype=_XSD_DATETIME)
    signal = _literal(row["signal"])
    anomaly = _literal(row["anomaly"])
    description = _literal(row["description"])
    procedure = _compact_uri(row["procedure"], resource_namespace)
    evidence = _compact_uri(row["evidence"], resource_namespace)
    predicate = _compact_uri(row["predicate"], resource_namespace)

    _expect(asset, _EXPECTED_ASSET_ID, "asset.id")
    _expect(location, _EXPECTED_LOCATION_ID, "asset.location")
    _expect(observation_id, _EXPECTED_OBSERVATION_ID, "observation.id")
    _expect(observed_at, _EXPECTED_OBSERVED_AT, "observation.observed_at")
    _expect(signal, _EXPECTED_SIGNAL, "observation.signal")
    _expect(anomaly, _EXPECTED_ANOMALY, "observation.anomaly")
    _expect(description, _EXPECTED_DESCRIPTION, "observation.description")
    _expect(procedure, _EXPECTED_PROCEDURE_ID, "procedure.id")
    _expect(evidence, _EXPECTED_EVIDENCE_ID, "kg_evidence.id")
    _expect(predicate, _EXPECTED_PREDICATE, "kg_evidence.predicate")

    return (
        StructuredObservation(
            observation_id=observation_id,
            observed_asset=asset,
            observed_at=observed_at,
            signal=signal,
            anomaly=anomaly,
            description=description,
        ),
        StructuredSupportRecord(
            evidence_id=evidence,
            subject=asset,
            predicate=predicate,
            procedure_id=procedure,
            required_observation_id=observation_id,
        ),
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _RetrievalFailure("sparql_results", "SPARQL result contains a duplicate key")
        result[key] = value
    return result


def _compact_uri(term: object, resource_namespace: str) -> str:
    if not isinstance(term, dict) or set(term) != {"type", "value"}:
        raise _RetrievalFailure("sparql_results", "SPARQL URI binding is invalid")
    if term.get("type") != "uri" or not isinstance(term.get("value"), str):
        raise _RetrievalFailure("sparql_results", "SPARQL URI binding is invalid")
    value = term["value"]
    if not value.startswith(resource_namespace):
        raise _RetrievalFailure("sparql_results", "SPARQL URI uses an unknown namespace")
    local_name = value[len(resource_namespace) :]
    if not local_name or any(character.isspace() for character in local_name):
        raise _RetrievalFailure("sparql_results", "SPARQL URI local name is invalid")
    return f"ex:{local_name}"


def _literal(term: object, *, datatype: str | None = None) -> str:
    if not isinstance(term, dict):
        raise _RetrievalFailure("sparql_results", "SPARQL literal binding is invalid")
    expected_keys = {"type", "value"} if datatype is None else {"type", "value", "datatype"}
    if set(term) != expected_keys or term.get("type") != "literal":
        raise _RetrievalFailure("sparql_results", "SPARQL literal binding is invalid")
    if datatype is not None and term.get("datatype") != datatype:
        raise _RetrievalFailure("sparql_results", "SPARQL literal datatype is invalid")
    value = term.get("value")
    if not isinstance(value, str) or not value:
        raise _RetrievalFailure("sparql_results", "SPARQL literal value is invalid")
    return value


def _expect(actual: str, expected: str, field: str) -> None:
    if actual != expected:
        raise _RetrievalFailure(field, f"{field} does not match the Pump_12 contract")


def _failure(
    asset: KnownAsset,
    run_id: str,
    input_ids: tuple[str, str],
    duration_ms: int,
    field: str,
    detail: str,
) -> StructuredRetrievalResult:
    error = StageError(StageErrorCode.INSUFFICIENT_EVIDENCE, field=field, detail=detail)
    event = StageEvent(
        stage=StageName.STRUCTURED_RETRIEVAL,
        run_id=run_id,
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        duration_ms=duration_ms,
        input_ids=input_ids,
        errors=(error,),
    )
    return StructuredRetrievalResult(
        status=TerminalStatus.INSUFFICIENT_EVIDENCE,
        asset=asset,
        event=event,
    )


def _validate_endpoint(value: object) -> str:
    endpoint = _require_strict_nonblank(value, "query_endpoint")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("query_endpoint must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("query_endpoint must not contain credentials")
    if parsed.fragment:
        raise ValueError("query_endpoint must not contain a fragment")
    if parsed.query:
        raise ValueError("query_endpoint must not contain a query string")
    if parsed.hostname is None:
        raise ValueError("query_endpoint must include a host")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("query_endpoint must contain a valid port") from exc
    return endpoint


def _validate_absolute_iri(value: object, field_name: str) -> str:
    iri = _require_strict_nonblank(value, field_name)
    if (
        not urlsplit(iri).scheme
        or not iri.partition(":")[2]
        or any(character.isspace() or character in _FORBIDDEN_IRI_CHARACTERS for character in iri)
    ):
        raise ValueError(f"{field_name} must be an absolute IRI")
    return iri


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timeout_seconds must be a number")
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    return timeout


def _validate_asset(value: object) -> None:
    if not isinstance(value, KnownAsset):
        raise TypeError("resolved_asset must be a KnownAsset")


def _require_strict_nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    if value != normalized:
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value


def _duration_ms(started: int) -> int:
    return max(0, (perf_counter_ns() - started) // 1_000_000)
