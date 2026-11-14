# Research Questions

**Summary**: The four research questions structuring the thesis. RQ1 is the empirical core; RQ2 and RQ3 are technical and human sub-dimensions; RQ4 is the feasibility prerequisite.

**Sources**: `thesis-pitch-v2.md` §3.

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4 (this page anchors all of them).

---

## RQ1 — Methods comparison (primary)

> How do four KG–LLM integration strategies — Naive RAG, GraphRAG-style community summaries, OG-RAG ontology-grounded retrieval, and KG-Agent path reasoning with constraint validation — compare on groundedness, faithfulness, and explainability for manufacturing anomaly-triage decision support?

Motivation: multiple peer-reviewed methods exist, but no study compares them empirically on a manufacturing dataset using standardised metrics. (source: thesis-pitch-v2.md §3)

Operationalised by [[strategy-comparison]] across S1–S4 and the metrics in [[ragas-metrics]] ([[faithfulness]], [[groundedness]], Hits@Any, F1).

## RQ2 — Ontology integration

> Does grounding an LLM agent in a pre-existing, standards-based domain ontology (SSN/SOSA + SHACL) produce higher answer verifiability and fewer invalid action plans than an LLM-constructed graph (GraphRAG-style) or unstructured vector retrieval?

Motivation: [[og-rag]] and DeBellis et al. (Applied Ontology, 2024) argue formal ontology beats dynamically built graphs for domain-critical applications, but this has not been tested in manufacturing with a constraint-validation loop. (source: thesis-pitch-v2.md §3)

Metrics: SHACL pass rate, % plans needing self-correction, ontology concept coverage. See [[shacl-validation]], [[ssn-sosa]].

## RQ3 — Provenance and operator trust

> Does structured provenance ([[prov-o]] trace + SHACL validation report) improve perceived explainability and operator trust compared to an equivalent agent that produces the same action plan without a structured evidence package?

Motivation: the "explainability theater" risk — fluent text that *looks* like an explanation but carries no verifiable evidence. (source: thesis-pitch-v2.md §3, citing XAIManufacturing 2024)

Metrics: SUS score, Likert 1–5, qualitative interviews. Methodology: user study with 5–8 participants.

**Scope status (2026-11-07)**: not executed. The original trust/usability study remains **unmet**. The
study that the delivery roadmap can run with a single student is narrower: real domain reviewers use
the interface to answer the five provenance queries on paired outputs, measuring **auditability and
traceability task performance only** (issue `#127`). That evidence must never be reported as operator
trust, usability, safety, or field effectiveness, and no operational or clinical conclusion follows from
it. Any move back to the original trust study needs a new protocol version. See
[[delivery-roadmap]].

**Test items for the user study** — adopted verbatim from the five operator-trust queries enabled by [[prov-agent-souza2025|PROV-AGENT]] (Souza et al., e-Science 2025, §IV.B):

1. *Q1*: Given an agent decision, what was the complete lineage until the first input data?
2. *Q2*: For the most recent recommendation, what was the decision, the alternatives considered, and the reasoning?
3. *Q3*: What was the LLM prompt and response when a *surprising* recommendation was identified? — the hallucination-debugging query.
4. *Q4*: How did this recommendation influence subsequent actions? (counterfactual)
5. *Q5*: Where did this erroneous recommendation originate, and how did it propagate?

Each query is an SPARQL traversal over the [[prov-o|PROV-O]] subgraph in [[fuseki-triplestore]]. The user study should test whether operators can answer these questions using S4's evidence package vs. a stripped-down baseline that returns the same plan without structured provenance. (source: arXiv:2508.02866 §IV.B)

## RQ4 — Local deployment viability

> Can a locally-deployed, ontology-grounded LLM agent (running on commodity CPU/GPU hardware without any cloud dependency) meet the latency and resource constraints required for practical manufacturing decision support?

Motivation: data-sovereignty makes cloud LLMs unacceptable in many factories, but no published work provides measured latency/memory benchmarks for a full KG-agent stack running locally on representative hardware. (source: thesis-pitch-v2.md §3)

Metrics: p50/p95 latency, peak RAM/VRAM. See [[local-deployment]].

## Relationship between RQs

```
        RQ1 (methods comparison)
        /                      \
   RQ2 (ontology)         RQ3 (provenance/trust)
        \                      /
              RQ4 (local viability)
```

RQ1 is the empirical spine; RQ2 and RQ3 sub-dimension it (technical and human-facing); RQ4 is a feasibility constraint all other results depend on. (source: thesis-pitch-v2.md §3.1)

## Related pages

- [[thesis-pitch]]
- [[strategy-comparison]]
- [[ragas-metrics]]
- [[shacl-validation]]
- [[prov-o]]
- [[local-deployment]]
