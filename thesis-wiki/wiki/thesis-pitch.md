# Thesis Pitch v2 — MFG-AgentGraph

**Summary**: One-page summary of the master thesis pitch v2. Captures problem, related-work positioning, four research questions, the four-strategy comparison (S1–S4), tech stack, evaluation plan, hypotheses, timeline, and scope.

**Sources**: `thesis-pitch-v2.md`.

**Last updated**: 2026-04-26.

**Thesis relevance**: RQ1 / RQ2 / RQ3 / RQ4.

---

## Problem

Manufacturing AI assistants today are either cloud-based (unacceptable for data sovereignty and latency) or black-box (operators cannot audit recommendations). No open-source framework lets a factory run AI agents entirely on its own servers with traceable, standards-based evidence for each recommendation. (source: thesis-pitch-v2.md §1)

Three peer-reviewed surveys frame the gap: XAI in smart manufacturing is "under-developed, non-standardized, and fragmented" (npj Advanced Manufacturing 2024); few studies integrate LLMs and KGs *simultaneously* for manufacturing decision support (J. Manufacturing Systems 2025); agentic AI in industrial settings exhibits "opaque reasoning and unstructured decision paths" (ScienceDirect 2025). (source: thesis-pitch-v2.md §1)

## Positioning vs. prior work

Building on Pan et al.'s three-paradigm taxonomy ([[unifying-llms-kgs]] — *KG-enhanced LLMs*, *LLM-augmented KGs*, *Synergized*), this thesis sits primarily in paradigm 1 with elements of paradigm 3 via [[prov-o]] feedback. (source: thesis-pitch-v2.md §2.1, arXiv:2306.08302)

The four most relevant prior methods and their gaps for this thesis:

| Method | Venue | Core idea | Gap |
|---|---|---|---|
| [[graphrag]] | Microsoft / arXiv 2024 | LLM builds its own graph from text; community summaries at query time | No domain ontology, no SHACL, no provenance, not on manufacturing |
| [[reasoning-on-graphs]] (RoG) | ICLR 2024 | LLM plans relation paths on a KG, reasons over faithful chains | Requires fine-tuning; KGQA benchmark only, no agent loop |
| [[og-rag]] | EMNLP 2025 | Pre-existing ontology drives hypergraph retrieval; +55% recall | No SHACL, no agent loop, no provenance, not on manufacturing |
| KG-RAG for FMEA | J. Manufacturing Systems 2025 | KG augments RAG for FMEA QA | Cloud LLM only, no agent, no SSN/SOSA or PROV-O |

(source: thesis-pitch-v2.md §2.2, table 1)

## Research questions

See [[research-questions]] for the full RQ wording. Quick map:

- **RQ1** — Methods comparison across S1–S4 on faithfulness, groundedness, explainability.
- **RQ2** — Does pre-existing ontology + SHACL beat LLM-built graphs and unstructured retrieval?
- **RQ3** — Does PROV-O + SHACL evidence improve operator trust (user study)?
- **RQ4** — Is the full local stack viable on commodity hardware?

RQ1 is the empirical core; RQ2/RQ3 are technical and human-facing sub-dimensions; RQ4 is the feasibility check that all other results depend on. (source: thesis-pitch-v2.md §3)

## The four strategies (RQ1)

See [[strategy-comparison]] for the full matrix.

- [[naive-rag]] (S1) — vector-only retrieval, no KG. Status quo baseline.
- [[graphrag]] (S2) — Microsoft GraphRAG community summaries; LLM-built graph.
- [[og-rag]] (S3) — pre-existing ontology + hypergraph retrieval; SPARQL+vector hybrid.
- [[kg-agent-s4]] (S4 proposed) — LangGraph agent with SPARQL, SHACL self-correction, support subgraph, PROV-O record.

(source: thesis-pitch-v2.md §5)

## Architecture (six layers)

1. Data sources — MIMII signals, alarm/event logs, SOPs, manuals.
2. ETL + ingestion — anomaly detection, SSN/SOSA mapping, doc chunking, embedding.
3. Storage — [[fuseki-triplestore]] (RDF/SPARQL), Qdrant (vectors), [[shacl-validation]] shapes, [[prov-o]] records.
4. Local model runtime — Ollama / llama.cpp / vLLM + sentence-transformers.
5. Strategy harness — S1–S4 in a single harness for direct comparison.
6. Interface + evaluation — FastAPI, web UI, [[ragas-metrics]] + KG metrics, Docker Compose.

(source: thesis-pitch-v2.md §8)

## Evaluation plan

| RQ | Metric | Method |
|---|---|---|
| RQ1 | RAGAS [[faithfulness]] | LLM-as-judge |
| RQ1 | [[groundedness]] (% actions with ≥1 KG edge or doc citation) | Automated |
| RQ1 | Hits@Any, Hits@1, F1 | Automated |
| RQ2 | SHACL pass rate, % plans needing self-correction | Automated |
| RQ2 | Ontology coverage (% actions citing a named concept) | Automated |
| RQ3 | SUS score, Likert 1–5 | User study, 5–8 participants |
| RQ4 | p50/p95 latency, peak RAM/VRAM | Load testing, `psutil`/`nvidia-smi` |

Dataset: [[mimii-dataset]]. Scenario: [[anomaly-triage]] on a pump station, 30 manually authored queries (single-hop, multi-hop, counterfactual). (source: thesis-pitch-v2.md §9)

## Hypotheses

- **H1** — S4 > S1, S2, S3 on RAGAS faithfulness and groundedness.
- **H2** — S3 > S2 on multi-hop relational queries (expert ontology beats LLM-built graph).
- **H3** — SHACL self-correction fires on >30% of initially invalid plans.
- **H4** — Operators rate S4 ≥ 4 on Likert and ≥ 68 SUS.
- **H5** — S4 p95 latency ≤ 30 s on a CPU-only 16 GB laptop.

(source: thesis-pitch-v2.md §9)

## Timeline (March 2 – August 30, 2026, 26 weeks)

1. Wk 1–4 (Mar 2–29) — Foundation, literature, ontology v0, Fuseki running.
2. Wk 5–6 (Mar 30–Apr 12) — Storage layer, Qdrant + MIMII embeddings, Ollama.
3. Wk 7–10 (Apr 13–May 10) — Core S4 agent: LangGraph, SHACL loop, PROV-O.
4. Wk 11–13 (May 11–31) — S1, S2, S3 baselines + unified eval harness; first RQ1 results.
5. Wk 14–16 (Jun 1–21) — Hardening, second LLM backend, latency profiling (RQ4), UI v1, RQ2 results.
6. Wk 17–20 (Jun 22–Jul 19) — User study (RQ3).
7. Wk 21–26 (Jul 20–Aug 30) — Open-source packaging, thesis writing, defense.

(source: thesis-pitch-v2.md §11)

## Scope boundaries

- **In scope:** 4-way comparison on MIMII; one scenario (pump anomaly triage); Docker local deploy; minimal SSN/SOSA + domain ontology; RAGAS + KG metrics; open-source code; Llama 3 / Mistral / Phi-3 open weights.
- **Out of scope:** every machine type; closed-loop PLC control; full MES/ERP integration; ISO 15926 scope; large-scale annotation; commercial product; fine-tuning / training new models.

(source: thesis-pitch-v2.md §13)

## Related pages

- [[mfg-agentgraph]] — system architecture and deliverables
- [[research-questions]] — full RQ wording
- [[strategy-comparison]] — S1–S4 matrix
- [[mimii-dataset]] — evaluation dataset
- [[anomaly-triage]] — primary scenario
