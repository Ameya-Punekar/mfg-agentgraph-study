# Anomaly Triage (the primary scenario)

**Summary**: The thesis demo and evaluation scenario: a pump station begins making an abnormal sound, and the operator asks "What should I check first, and why?". All four strategies answer the same query, enabling a controlled comparison.

**Sources**: `thesis-pitch-v2.md` §6, §10.

**Last updated**: 2026-04-26.

**Thesis relevance**: RQ1, RQ3.

---

## The scenario

- 14:03 — `PumpStation_12` produces an anomalous sound (from the [[mimii-dataset]]).
- An anomaly detector emits a `sosa:Observation` event, persisted into the [[fuseki-triplestore|Fuseki KG]].
- Operator asks: *"What should I check first, and why?"*

(source: thesis-pitch-v2.md §6, §10)

## What each strategy returns

All four strategies produce the same kind of action plan; they differ in what evidence accompanies it:

| Strategy | Action plan | Evidence package |
|---|---|---|
| S1 [[naive-rag]] | text only | flat retrieved chunks |
| S2 [[graphrag]] | text + community summaries | community-level summaries (no triple-level structure) |
| S3 [[og-rag]] | text + ontology-aligned chunks | ontology-tagged retrieval, no SHACL |
| S4 [[kg-agent-s4]] | text + ranked actions | `kg_edges` list, doc citations, SHACL report, PROV-O record |

(source: thesis-pitch-v2.md §10)

## Query mix (30 total)

- Single-hop — *"What is the last maintenance date of Pump_12?"*
- Multi-hop — *"Which assets share a cooling circuit with the faulty pump?"*
- Counterfactual — *"Would replacing the inlet filter fix this?"*

(source: thesis-pitch-v2.md §9.3)

## Why this scenario

It exercises every architectural decision: SSN/SOSA (sensor event), maintenance history (relational KG context), SOPs (vector retrieval), SHACL (plan validation against domain rules), PROV-O (audit). One scenario per the thesis scope boundary — coverage is depth-first not breadth-first. (source: thesis-pitch-v2.md §13)

## Related pages

- [[mimii-dataset]]
- [[strategy-comparison]]
- [[kg-agent-s4]]
- [[shacl-validation]]
