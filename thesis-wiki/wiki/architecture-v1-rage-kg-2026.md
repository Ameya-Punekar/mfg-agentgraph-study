# Architecture V1 — RAGE-KG 2026 final-submission baseline

**Summary**: Frozen implementation baseline for MFG-AgentGraph Architecture V1. It records the architecture exactly as committed in the final RAGE-KG 2026 submission and defines the contract that Implementation V1 must realize before later architectural revisions are considered.

**Sources**: RAGE-KG 2026 final submission, `concept-paper/publication/rage-kg-2026/manuscript.md` §§3–4 and §6, Git tag `submission/rage-kg-2026`, commit `59b2796f8adceebbee61a896e689f265a5d36c2a` (2026-07-27).

**Last updated**: 2026-08-16.

**Thesis relevance**: RQ1, RQ2, RQ3, RQ4.

---

## Status and version meaning

This page designates the final RAGE-KG 2026 submission as **Architecture V1** of MFG-AgentGraph.

- **Architecture V1 is frozen** at submission commit `59b2796f8adceebbee61a896e689f265a5d36c2a`.
- **Implementation V1** is the first executable system that realizes this architecture.
- Changes discovered during implementation must be recorded as implementation decisions or deviations; they must not silently rewrite the V1 baseline.
- A future Architecture V2 must explicitly list its differences from this page and explain why the implementation evidence required the change.
- The paper is an architecture/concept contribution. It does not itself establish the future empirical results of Implementation V1.

## Immutable submission provenance

| Item | Canonical reference |
|---|---|
| Submission tag | `submission/rage-kg-2026` |
| Archival branch | `archive/rage-kg-2026-submission` |
| Frozen commit | `59b2796f8adceebbee61a896e689f265a5d36c2a` |
| Markdown manuscript | `concept-paper/publication/rage-kg-2026/manuscript.md` |
| LaTeX source | `concept-paper/publication/rage-kg-2026/latex/ceurart-main.tex` |
| Compiled PDF | `concept-paper/publication/rage-kg-2026/latex/ceurart-main.pdf` |
| Overleaf package | `concept-paper/publication/rage-kg-2026/rage-kg-2026-overleaf-current.zip` |

Repository links:

- [Frozen submission commit](https://github.com/Ameya-Punekar/mfg-agentgraph/commit/59b2796f8adceebbee61a896e689f265a5d36c2a)
- [Submission tag](https://github.com/Ameya-Punekar/mfg-agentgraph/tree/submission/rage-kg-2026)
- [Archival submission branch](https://github.com/Ameya-Punekar/mfg-agentgraph/tree/archive/rage-kg-2026-submission)

Git object identities recorded during archival verification:

- `manuscript.md`: `48c62a1f88b8591896a5f6e2ac76c7b56e01740a`
- `ceurart-main.tex`: `198d6cd72937f74228bc032692e001ae5068e7ac`
- `ceurart-main.pdf`: `05f32c07dfc8cbfb87b4b632ddedc3f7196240ce`
- `rage-kg-2026-overleaf-current.zip`: `906882fef56520502191c596b09dbf83bbaec288`

## V1 design requirements

Architecture V1 is governed by six requirements from the submitted paper:

1. **R1 — Local deployment**: run on factory-controlled hardware without requiring external inference services.
2. **R2 — Structured domain grounding**: represent assets, sensors, observations, anomaly events, procedures, and their relationships using [[ssn-sosa]] plus the MFG-AgentGraph domain profile.
3. **R3 — Hybrid evidence retrieval**: combine SPARQL retrieval over the RDF graph with vector retrieval over SOP/manual chunks.
4. **R4 — Constraint-valid action plans**: reify generated actions as RDF and gate them through [[shacl-validation]].
5. **R5 — Auditable evidence packages**: return stable evidence identifiers and write a [[prov-o]] trace for the generation process.
6. **R6 — Comparable strategy harness**: expose S1–S4 as configurations of one shared evaluation harness.

These are implementation acceptance constraints, not optional aspirations. (source: final manuscript §3.1)

## System boundary and stores

Architecture V1 uses two complementary evidence stores:

| Store | V1 technology | Required contents |
|---|---|---|
| Structured store | Apache Jena Fuseki | SSN/SOSA-aligned RDF for assets, sensors, observations, anomaly events, procedures, validation resources, and provenance records |
| Unstructured store | Qdrant | Embedded, addressable SOP and manual passages with metadata that permits ontology/asset filtering |

Fuseki must separate factory data, SHACL shapes, and provenance traces into named graphs. Qdrant chunks must have stable identifiers because recommendations cite them as evidence. (source: final manuscript §3.1)

## V1 execution pipeline

The canonical S4 request path is:

1. **Entity and asset resolution** maps operator terms, timestamps, and sensor references to KG identifiers.
2. **Structured retrieval** runs SPARQL over Fuseki for the relevant asset/observation subgraph.
3. **Procedural retrieval** performs ontology-filtered vector search over SOP/manual chunks in Qdrant.
4. **Candidate generation** asks the local LLM for ranked actions in a structured JSON contract.
5. **RDF reification** converts the JSON fields into typed RDF resources, including `mfg:RecommendedAction`.
6. **SHACL validation** validates the action and its support graph.
7. **Bounded repair** returns violated shape IDs/messages to the agent, which retrieves missing evidence or regenerates the candidate.
8. **Explicit fallback** returns operator disambiguation, insufficient evidence, unsupported/lower-ranked output, or failure when the retry budget is exhausted; an invalid recommendation must not be shown as valid.
9. **Evidence-package assembly** binds the recommendation to KG support, document chunks, the SHACL report, and a provenance identifier.
10. **PROV-O trace writing** records retrieval, model, validation, and repair activities before the response is released.

This order is normative for Implementation V1. In particular, provenance writing and validation are pre-release gates rather than asynchronous post-processing. (source: final manuscript §§3.2–3.5)

## Candidate-action contract

The LLM does not emit free-text triples. It emits structured JSON whose identifiers are resolved into RDF resources. The minimum V1 action record is conceptually:

```json
{
  "ranked_actions": [{
    "rank": 1,
    "action": "Inspect the pump inlet of Pump_12 for cavitation",
    "target_asset": "ex:Pump_12",
    "support_evidence": [
      {"type": "kg_edge", "id": "ex:EvidenceEdge_001"},
      {"type": "doc_chunk", "id": "ex:SOP_Chunk_7"}
    ]
  }]
}
```

Implementation V1 must resolve `target_asset` and every evidence identifier against known resources before SHACL evaluation. The initial gate requires exactly one known target asset IRI and at least one modeled support-evidence resource. Operational shape modules additionally check that observations concern the target asset, fall within the anomaly window, and that cited procedures apply to the asset type. Passing SHACL means only that encoded constraints passed; it does not prove that the action is optimal or safe. (source: final manuscript §§3.3–3.4)

## Bounded repair and fail-closed behavior

| Violation | Required repair | Required fallback |
|---|---|---|
| Missing target asset | Re-run entity resolution and regenerate with a resolved IRI | Ask the operator to disambiguate |
| Missing observation support | Retrieve the asset/time-window observation subgraph | Return insufficient evidence |
| Missing procedural citation | Run ontology-filtered vector retrieval for fault/action terms | Mark unsupported and lower rank |
| Invalid evidence package | Rebuild the package and write validation/provenance records | Fail closed |

The repair loop terminates when validation passes, the retry budget is exhausted, or entity resolution requires operator input. Implementation V1 must expose initial failure rate, repair count, self-correction success, and final pass/fallback state as measurable events. (source: final manuscript §§3.2, 3.4, 3.7)

## Provenance and response contract

The V1 trace models:

- the S4 agent as `prov:SoftwareAgent`;
- retrieval, LLM invocation, validation, and repair as `prov:Activity` resources;
- prompts, models, retrieved KG/document resources, candidates, SHACL reports, and recommendations as `prov:Entity` resources.

Every released recommendation must include a `provenance_id` linking the human-readable response to the machine-readable trace. Provenance-write failure is blocking: the response must return no recommendation rather than an untraced recommendation. Retention and access rules are required because traces may contain sensitive prompts or operational evidence. (source: final manuscript §3.5)

## Implementation V1 component map

| Component | Primary responsibility | Observable output |
|---|---|---|
| Query/API adapter | Accept operator query and correlation/run ID | Normalized request |
| Entity resolver | Bind query terms to KG identifiers | Resolution candidates, confidence, selected IRIs |
| SPARQL retriever | Retrieve structured asset/anomaly evidence | Stable RDF statements/resources |
| Vector retriever | Retrieve applicable SOP/manual passages | Stable document-chunk IDs and scores |
| S4 orchestrator | Execute the bounded state machine | State transitions and retry count |
| Local model adapter | Produce schema-conforming candidate actions | Structured candidate JSON |
| RDF action mapper | Resolve IDs and reify candidates | Candidate action graph |
| SHACL validator | Check structural/evidence constraints | Conformance flag, report, violated shape IDs |
| Repair controller | Convert validation feedback into bounded retry/fallback actions | Repair decision and terminal state |
| Evidence builder | Assemble all support references | Evidence package |
| Provenance writer | Persist the run trace | `provenance_id` and PROV-O graph |
| Strategy harness | Run S1–S4 under controlled configuration | Comparable run records and metrics |

Module names may differ in code, but these responsibilities and interfaces must remain traceable.

## First vertical slice

The first end-to-end Implementation V1 slice should reproduce the paper's pump-station scenario:

- resolve `Pump_12` from an operator query;
- retrieve a relevant observation subgraph and `SOP_Chunk_7`-like procedural evidence;
- generate an intentionally incomplete candidate in a test fixture;
- observe SHACL violations for missing target/evidence;
- repair to a valid RDF action;
- emit an evidence package and persisted PROV-O trace;
- prove fail-closed behavior for validation failure and provenance-write failure.

This slice should be implemented with deterministic fixtures before connecting the complete dataset or benchmarking model quality.

## S1–S4 evaluation boundary

The shared harness exposes:

- **S1 Naive RAG**: vector retrieval plus LLM generation;
- **S2 GraphRAG**: LLM-built graph plus community summaries;
- **S3 OG-RAG**: expert ontology plus hybrid retrieval;
- **S4 KG-Agent**: KG grounding, SHACL gate, bounded repair, and PROV-O trace.

Implementation V1 must avoid changing unrelated hardware/model/retrieval variables between strategies during controlled comparison. The submitted architecture leaves exact latency targets and empirical results to the implementation study. (source: final manuscript §§3.6–3.7 and §4)

## RQ mapping

- **RQ1**: the shared S1–S4 harness and quality/validity comparison.
- **RQ2**: SSN/SOSA grounding, action/evidence modeling, and SHACL constraint modules.
- **RQ3**: evidence packages, machine-readable validation reports, PROV-O traces, and trust/audit assessment.
- **RQ4**: locally deployable model/runtime stack and quality/latency/resource trade-offs.

## V1 acceptance checklist

Implementation V1 is architecture-conformant only when:

- [ ] all ten pipeline stages are present and instrumented;
- [ ] entity resolution can request operator disambiguation;
- [ ] SPARQL and vector evidence have stable identifiers;
- [ ] model output is schema-validated and reified as RDF;
- [ ] SHACL gates every S4 recommendation;
- [ ] repair is bounded and exposes explicit terminal states;
- [ ] invalid or unsupported recommendations fail closed;
- [ ] each released recommendation includes its evidence package and `provenance_id`;
- [ ] provenance-write failure blocks recommendation release;
- [ ] the pump-station vertical slice passes deterministic tests;
- [ ] S1–S4 run through one comparable harness;
- [ ] deviations from this baseline are recorded rather than silently introduced.

## Related pages

- [[mfg-agentgraph]]
- [[kg-agent-s4]]
- [[strategy-comparison]]
- [[ssn-sosa]]
- [[shacl-validation]]
- [[prov-o]]
- [[fuseki-triplestore]]
- [[local-deployment]]
- [[research-questions]]
