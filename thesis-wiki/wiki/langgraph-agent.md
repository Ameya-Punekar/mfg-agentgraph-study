# LangGraph Agent

**Summary**: LangGraph is the agent framework underpinning [[kg-agent-s4|S4]]. Provides stateful, checkpointed multi-step workflows that orchestrate the plan→retrieve→validate→explain loop.

**Sources**: `thesis-pitch-v2.md` §6, §7; `raw/langgraph-docs.md`. LangGraph docs [NEEDS VERIFICATION] — not yet ingested in detail.

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ1 (S4 implementation), RQ4.

---

## What it is

LangChain + LangGraph (MIT) — industry-standard for multi-step agentic workflows with stateful checkpointing. (source: thesis-pitch-v2.md §7)

## Why it fits S4

The S4 pipeline (plan → SPARQL → vector → LLM → SHACL validate → self-correct on failure → support subgraph → PROV-O) is a stateful graph of steps with conditional branches (validation pass/fail). LangGraph's graph-of-nodes model maps directly to this. (source: thesis-pitch-v2.md §6)

## Component decomposition (Chen et al. 2024 §2.1)

[[multi-agent-systems-survey-2024b|Chen et al. 2024]] decomposes a generative agent into **LLM + Profile + Reasoning + Memory** plus an environment of **Rules + Tools + Intervention**. Even though MFG-AgentGraph runs a single agent, this seven-part decomposition is the cleanest survey-level vocabulary for the LangGraph design:

| Component | Implementation |
|---|---|
| LLM | Local quantised model (see [[local-deployment]]) |
| Profile | SOP-derived role prompt for the anomaly-triage assistant |
| Reasoning | [[think-on-graph]] / [[reasoning-on-graphs]] planner over the KG |
| Memory | Conversation history + [[prov-o]] trace + historical observations from [[fuseki-triplestore]] |
| Rules | [[shacl-validation]] constraints + SOP-derived rules |
| Tools | SPARQL endpoint, SHACL validator, vector retrieval — registered as LangGraph tool nodes |
| Intervention | Operator escalation/override step in [[anomaly-triage]] |

(source: arXiv:2412.17481 §2.1-§2.2)

## Self-refine framing (Chen et al. 2024 §3.1)

The S4 **plan → SPARQL → vector → LLM → SHACL → self-correct** loop is structurally a **single-agent self-refine** in Chen et al.'s reasoning-framework taxonomy — the LLM-as-critic role is replaced by a deterministic SHACL engine. This trades critic flexibility for determinism + ontology-grounded provenance. (source: arXiv:2412.17481 §3.1)

## Open questions for ingest

- Best pattern for surfacing SHACL validation failures back to the LLM as tool output.
- Checkpoint strategy that survives container restarts (relevant for RQ4 reliability).
- Instrumentation hooks for capturing the support subgraph and PROV-O trace from inside the graph.

## Related pages

- [[kg-agent-s4]]
- [[mfg-agentgraph]]
- [[shacl-validation]]
- [[prov-o]]
- [[multi-agent-systems-survey-2024b]]
