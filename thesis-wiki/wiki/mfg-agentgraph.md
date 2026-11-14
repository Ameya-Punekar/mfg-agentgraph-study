# MFG-AgentGraph (the proposed system)

**Summary**: The full proposed system: an open-source Python framework that runs an LLM locally, stores factory knowledge in a standards-based KG, and uses a LangGraph agent that explains every recommendation via support subgraph + SHACL report + PROV-O record.

**Sources**: `thesis-pitch-v2.md` §4, §6, §7, §8, §12; RAGE-KG 2026 final submission §§3–4 and §6 at Git tag `submission/rage-kg-2026`.

**Last updated**: 2026-08-16.

**Thesis relevance**: RQ1, RQ2, RQ3, RQ4.

---

## What it is

> [!important] Architecture V1 baseline
> The exact final RAGE-KG 2026 submission is frozen as [[architecture-v1-rage-kg-2026|Architecture V1]]. Implementation V1 must satisfy that page's pipeline, evidence, validation, provenance, and fail-closed contracts; deviations must be explicit.

An open-source Python framework + CLI (`mfg-agentgraph`) that:

1. Runs a local LLM — no cloud, no external API.
2. Stores factory knowledge in a pre-existing, standards-based KG ([[ssn-sosa]] + domain model in [[fuseki-triplestore]]).
3. Uses a [[langgraph-agent]] that issues SPARQL, performs vector search, scores hypotheses, and self-corrects via [[shacl-validation]].
4. Explains every recommendation via support subgraph + SHACL report + [[prov-o]] trace.
5. Is empirically compared against three baselines (S1, S2, S3) drawn from peer-reviewed work.

(source: thesis-pitch-v2.md §4)

## Position in the broader literature (Pan et al. 2024)

In the [[unifying-llms-kgs|Pan 2024 roadmap]], MFG-AgentGraph is a **Stage-2 system** (Synergized LLMs + KGs) per the three-stage milestone roadmap (§7, Fig. 26). Specifically it sits in **§6.2 LLMs as Agents Reasoning** — the lighter-weight Synergized pattern that doesn't require fine-tuning, alongside ToG, RoG, StructGPT, KSL, KD-CoT.

The four-strategy comparison covers paradigm 1 (S1, S2, S3) → paradigm 3 (S4) within a single harness, which is itself unusual: most cited works in Pan 2024 evaluate a single paradigm. (source: Pan2024 §3.1, §6.2, §7, Fig. 26)

## Literature framing: KG as cognitive middle layer (Bian 2025 §6.4)

[[kg-construction-llm-survey-2024|Bian 2025]] §6.4 supplies the cleanest one-paragraph framing of MFG-AgentGraph in the published literature:

> "Beyond their use as retrieval backbones in RAG systems, Knowledge Graphs (KGs) are increasingly envisioned as a **cognitive middle layer** bridging raw input and LLM reasoning. In this paradigm, KGs provide a structured scaffold for **querying, planning, and decision-making**, enabling more interpretable and grounded generation." (source: arXiv:2510.20345 §6.4)

Use this as the lead reference when introducing the system in the thesis text — distinguishes MFG-AgentGraph from pure-RAG baselines (S1) by paradigm rather than just by mechanism.

## Closest published comparator: AGENTiGraph (Zhao et al., CIKM 2025)

[[agentigraph-2025|AGENTiGraph]] is the closest published architectural precedent: a multi-agent KG+LLM system targeting non-technical users in privacy-sensitive domains (legal, medical, education). Same positioning, similar 7-agent pipeline (Intent → Key Concept → Task Planning → KG Interaction → Reasoning → Response → Update), but **no SHACL, no PROV-O, no domain ontology** — the system claims auditability ("tracked and audited") without delivering a technical mechanism.

The thesis's four contributions over AGENTiGraph (ontology backbone via [[ssn-sosa]], [[shacl-validation|SHACL]] gating, [[prov-o|PROV-O]] trace, single-agent efficiency) are exactly the gaps AGENTiGraph leaves open. Cite this paper as the **closest published comparator** in the related-work chapter and frame thesis contributions as the missing technical pieces. (source: arXiv:2508.02999 §1, §2)

## Architecture (six layers)

| Layer | Components |
|---|---|
| 1. Data sources | MIMII signals, alarm/event logs, SOPs, manuals |
| 2. ETL + ingestion | Anomaly detection, SSN/SOSA mapping, doc chunking, embedding |
| 3. Storage | Fuseki KG, Qdrant vectors, SHACL shapes, PROV-O records |
| 4. Local model runtime | LLM server (Ollama / llama.cpp / vLLM), sentence-transformers |
| 5. Strategy harness | S1–S4 in a single comparable harness |
| 6. Interface + evaluation | FastAPI, web UI, RAGAS + KG metrics, Docker Compose |

Layer 5 is the key research addition: all four [[strategy-comparison|integration strategies]] run inside the same harness so the evaluation in Layer 6 can directly compare them. (source: thesis-pitch-v2.md §8)

## Tech stack (all open source)

| Purpose | Tech | License |
|---|---|---|
| Agent framework | LangChain + LangGraph | MIT |
| Local LLM serving | Ollama / llama.cpp / vLLM | MIT / MIT / Apache-2.0 |
| KG store | Apache Jena Fuseki | Apache-2.0 |
| Ontology standards | SSN/SOSA, SHACL, PROV-O | W3C |
| Vector DB | Qdrant | Apache-2.0 |
| Embeddings | HF sentence-transformers (`all-MiniLM-L6-v2` or `BAAI/bge-base-en-v1.5`) | Apache-2.0 |
| SHACL | `pyshacl` | Apache-2.0 |
| GraphRAG baseline | `microsoft/graphrag` | MIT |
| API layer | FastAPI | MIT |
| Deployment | Docker Compose (`docker-compose.cpu.yml`, `docker-compose.gpu.yml`) | — |

(source: thesis-pitch-v2.md §7)

## Walk-through (Strategy 4 on a pump anomaly)

Operator at 14:03: *"What should I check first, and why?"*

1. **Load asset context** — SPARQL query retrieves `PumpStation_12` subgraph.
2. **Retrieve documents** — ontology-guided vector search finds SOP / manual chunks.
3. **Generate hypotheses** — local LLM proposes ranked candidate actions.
4. **Validate plan** — SHACL checks that every action references a real `sosa:FeatureOfInterest` and that maintenance steps follow ordering constraints. Self-corrects if invalid.
5. **Build evidence** — extracts the support subgraph and document citations.
6. **Record provenance** — writes a PROV-O activity record (sources, model, tools, timestamps).
7. **Respond** — JSON containing action plan + all supporting evidence.

(source: thesis-pitch-v2.md §6)

Example output structure:

```json
{
  "asset_id": "PumpStation_12",
  "strategy": "KG-Agent-S4",
  "ranked_actions": [{
    "rank": 1,
    "action": "Inspect pump inlet for cavitation",
    "evidence": {
      "kg_edges": ["PumpStation_12 -> sosa:hosts -> Pump_12", "..."],
      "doc_chunks": ["sop_cavitation#chunk3", "..."]
    }
  }],
  "shacl_validation": "PASSED",
  "self_corrections": 0,
  "provenance": { "model": "llama3.2:3b", "tools_used": ["sparql_query", "..."] }
}
```

(source: thesis-pitch-v2.md §10)

## Software deliverables

1. `mfg-agentgraph` Python package + CLI: `ingest`, `load-kg`, `index-docs`, `run-agent --strategy {s1|s2|s3|s4}`, `evaluate`.
2. Four-strategy evaluation harness producing reproducible reports.
3. Docker recipes (`cpu.yml` Ollama / `gpu.yml` vLLM).
4. Manufacturing ontology profile (OWL/TTL): SSN/SOSA + domain + SHACL + PROV-O template.
5. Open-source GitHub repo (MIT) with CONTRIBUTING, pinned deps, quickstart.

(source: thesis-pitch-v2.md §12)

## Key risks (and mitigations)

- **GraphRAG integration complexity** — timebox to 3 days; fallback to LightRAG (also MIT).
- **OG-RAG replication gap** — implement directly from arXiv:2412.15235 (Sharma, Kumar & Li, 2024); the ingested text names no code release.
- **Explainability theater** — hard contract: every S4 action *must* include `kg_edges`; SHACL rejects plans without asset references.
- **Ontology scope creep** — freeze minimal ontology by Week 4.
- **Hardware limits** — quantised 4-bit GGUF via llama.cpp; CPU and GPU paths.
- **User-study recruitment** — start Week 17, accept domain-adjacent professionals, 5 minimum.

(source: thesis-pitch-v2.md §14)

## Related pages

- [[architecture-v1-rage-kg-2026]]
- [[thesis-pitch]]
- [[strategy-comparison]]
- [[kg-agent-s4]]
- [[langgraph-agent]]
- [[fuseki-triplestore]]
- [[local-deployment]]
- [[kg-construction-llm-survey-2024]]
- [[agentigraph-2025]]
