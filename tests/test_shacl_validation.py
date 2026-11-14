from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from mfg_agentgraph.rdf_action_mapper import MFG
from mfg_agentgraph.shacl_validation import validate_recommended_action


def _conforming_engine(**_kwargs: object) -> tuple[bool, Graph, str]:
    return True, Graph(), ""


def test_action_graph_digest_is_stable_across_triple_insertion_order() -> None:
    action = URIRef("http://example.org/Action")
    asset = URIRef("http://example.org/Pump_12")
    triples = (
        (action, RDF.type, MFG.RecommendedAction),
        (action, MFG.targetAsset, asset),
    )
    first = Graph()
    second = Graph()
    for triple in triples:
        first.add(triple)
    for triple in reversed(triples):
        second.add(triple)

    first_result = validate_recommended_action(
        first,
        action_uri=action,
        support_graph=Graph(),
        report_uri=URIRef("http://example.org/Report1"),
        run_id="run-digest",
        validation_engine=_conforming_engine,
    )
    second_result = validate_recommended_action(
        second,
        action_uri=action,
        support_graph=Graph(),
        report_uri=URIRef("http://example.org/Report2"),
        run_id="run-digest",
        validation_engine=_conforming_engine,
    )

    assert first_result.action_graph_digest is not None
    assert second_result.action_graph_digest == first_result.action_graph_digest
