"""Minimal RDF mapper for candidate actions.

MFG is the internal Architecture V1 namespace for MFG-AgentGraph RDF terms. It is
stable for this package's contracts but is not a published ontology.
"""

from collections.abc import Mapping
from enum import StrEnum

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from mfg_agentgraph.candidate_action import CandidateAction

MFG = Namespace("https://w3id.org/mfg-agentgraph/v1#")


class RdfActionMappingErrorCode(StrEnum):
    """Stable machine-readable RDF action mapping failure codes."""

    UNKNOWN_RESOURCE_ID = "unknown_resource_id"
    INVALID_MAPPING_INPUT = "invalid_mapping_input"


class RdfActionMappingError(ValueError):
    """Deterministic RDF mapping error without rejected IDs or objects."""

    __slots__ = ("code", "field")

    def __init__(self, code: RdfActionMappingErrorCode, field: str) -> None:
        if not isinstance(code, RdfActionMappingErrorCode):
            raise TypeError("code must be a RdfActionMappingErrorCode")
        self.code = code
        self.field = field
        super().__init__(f"{code.value}: {field}")


def map_candidate_action_to_rdf(
    action: CandidateAction,
    *,
    action_iri: URIRef,
    resource_iris: Mapping[str, URIRef],
) -> Graph:
    """Map a validated candidate action to a new RDFLib graph."""

    _validate_inputs(action, action_iri, resource_iris)
    target_iri = _resolve_resource(resource_iris, action.target_asset, field="target_asset")
    evidence_iris = tuple(
        _resolve_resource(resource_iris, reference.stable_id, field="support_evidence")
        for reference in action.support_evidence
    )

    graph = Graph()
    graph.add((action_iri, RDF.type, MFG.RecommendedAction))
    graph.add((action_iri, RDFS.label, Literal(action.action)))
    graph.add((action_iri, MFG.targetAsset, target_iri))
    graph.add((action_iri, MFG.rank, Literal(action.rank, datatype=XSD.integer)))
    for evidence_iri in evidence_iris:
        graph.add((action_iri, MFG.hasSupportEvidence, evidence_iri))
    return graph


def _validate_inputs(
    action: CandidateAction,
    action_iri: URIRef,
    resource_iris: Mapping[str, URIRef],
) -> None:
    if type(action) is not CandidateAction:
        raise RdfActionMappingError(RdfActionMappingErrorCode.INVALID_MAPPING_INPUT, "action")
    if not isinstance(action_iri, URIRef):
        raise RdfActionMappingError(RdfActionMappingErrorCode.INVALID_MAPPING_INPUT, "action_iri")
    if isinstance(resource_iris, str | bytes) or not isinstance(resource_iris, Mapping):
        raise RdfActionMappingError(
            RdfActionMappingErrorCode.INVALID_MAPPING_INPUT, "resource_iris"
        )
    for key, value in resource_iris.items():
        if not isinstance(key, str) or not isinstance(value, URIRef):
            raise RdfActionMappingError(
                RdfActionMappingErrorCode.INVALID_MAPPING_INPUT, "resource_iris"
            )


def _resolve_resource(
    resource_iris: Mapping[str, URIRef],
    stable_id: str,
    *,
    field: str,
) -> URIRef:
    resolved = resource_iris.get(stable_id)
    if resolved is None:
        raise RdfActionMappingError(RdfActionMappingErrorCode.UNKNOWN_RESOURCE_ID, field)
    return resolved
