# PROV-AGENT (Souza et al., IEEE e-Science 2025)

**Summary**: Souza et al.'s IEEE e-Science 2025 paper proposing **PROV-AGENT**, a W3C PROV extension for tracking AI agent interactions in agentic workflows. Defines concrete PROV subclasses for AI agents, tools, model invocations, prompts, and responses, and integrates them with traditional workflow tasks via Model Context Protocol (MCP). Self-described as **the first provenance framework designed to track AI agent actions and decisions in agentic workflows** — direct precedent for S4's PROV-O audit trail and resolves the `[NEEDS VERIFICATION]` flag in [[prov-o]].

**Sources**: `PROV_AGENT_Provenance_AI_Agents_2025.pdf` (arXiv:2508.02866v3, Proc. 21st IEEE Int. Conf. on e-Science 2025 — Souza, Gueroudji, DeWitt, Rosendo, Ghosal, Ross, Balaprakash, Ferreira da Silva — Oak Ridge National Lab + Argonne National Lab). Code: `github.com/ORNL/flowcept` (open-source).

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ3 (primary — direct PROV-O basis for S4's audit trail), RQ2 (the AIAgent / AgentTool / AIModelInvocation classes integrate with [[shacl-validation]] shapes), RQ4 (the manufacturing use case demonstrates cross-facility deployment).

---

## Problem framing

Foundation-model agents are non-deterministic and can hallucinate. In agentic workflows where one agent's output becomes another's input, errors **propagate**. Existing provenance approaches (W3C PROV, ProvONE, PROV-DfA, PROV-ML, FAIR4ML) capture data flow and task execution history but **do not represent reasoning processes, model invocations, or contextual information that drive agent decisions** (§I, §II.B).

The paper argues that *agentic provenance* — provenance data tracking AI-agent tasks and their influence on downstream non-agentic tasks and data — provides the "glue power" needed to unify these elements into a single queryable graph for traceability, root-cause analysis, and continuous agent improvement (§II.A).

## The PROV-AGENT model (§III, Fig. 3)

Extends W3C PROV's three core classes ([[prov-o|PROV-O]] in our wiki) — `Agent`, `Activity`, `Entity` — with concrete subclasses:

| PROV core class | PROV-AGENT subclass | What it represents |
|---|---|---|
| `Agent` | **AIAgent** | The AI agent itself (LLM-backed software agent) |
| `Activity` | **Campaign**, **Workflow**, **Task** | Standard workflow structures |
| `Activity` | **AgentTool** | One execution of an MCP-style tool by an agent |
| `Activity` | **AIModelInvocation** | A single foundation-model invocation (prompt → response) |
| `Entity` | **DataObject** | Generic data class with three concrete subclasses below |
| `Entity` (`DataObject`) | **DomainData** | Domain-specific data (parameters, KPIs, files, pointers) |
| `Entity` (`DataObject`) | **SchedulingData** | Where the activity ran (compute node, CPU/GPU ID) |
| `Entity` (`DataObject`) | **TelemetryData** | Runtime metrics (CPU/GPU usage, disk usage, latency) |
| `Entity` | **Prompt** | The prompt sent to a model |
| `Entity` | **AIModel** | Model metadata (name, type, provider, temperature, params) |
| `Entity` | **ResponseData** | The model's response |

(source: arXiv:2508.02866 §III, Fig. 3)

## Standard PROV relationships wire the graph

PROV-AGENT does **not** introduce new relationship vocabulary — it uses standard PROV constructs throughout. Key edges:

- `AgentTool wasInformedBy AIModelInvocation` — the tool's logic depends on what the model said.
- `AIModelInvocation used Prompt` and `AIModelInvocation used AIModel`.
- `AIModelInvocation generated ResponseData` (PROV `wasGeneratedBy`).
- `ResponseData wasAttributedTo AIAgent`.
- `AgentTool wasAssociatedWith AIAgent`.
- `Task generated SchedulingData / TelemetryData / DomainData`.
- `AgentTool generated AgentDecision` (a `DomainData` instance) `wasAttributedTo AIAgent`.

This means a PROV-AGENT trace is a fully W3C-conformant PROV graph — any standard PROV reasoner / SPARQL query / serialization works without extension. (source: arXiv:2508.02866 §III)

## MCP integration is core

PROV-AGENT is built on the **Model Context Protocol (MCP)** [§II.A] — a standard that defines:

- Tools (callable functions exposed to the agent)
- Prompts (templated requests)
- Resources (data the agent can fetch)
- Context management
- Agent-client architecture

LangChain, AutoGen, LangGraph, CrewAI, and Academy all support MCP. PROV-AGENT maps MCP concepts directly onto PROV: an MCP tool execution becomes an `AgentTool` activity; an MCP resource fetch becomes a `Prompt` augmentation (RAG); the MCP server's lifecycle becomes a `Workflow`. (source: arXiv:2508.02866 §II.A, §III, §IV.A)

**Implication for [[langgraph-agent]]**: since LangGraph supports MCP, a LangGraph-built S4 agent can adopt PROV-AGENT's instrumentation pattern directly without re-architecting.

## Implementation: Flowcept (§IV.A)

Open-source distributed provenance system at `github.com/ORNL/flowcept`. Federated, broker-based; data observability hooks for Dask, MLflow, Redis, Kafka, SQLite, file systems, object stores; consolidation service writes to a persistent provenance database.

**Two Python decorators are the entire instrumentation surface for agentic workflows**:

```python
from langchain_openai import ChatOpenAI
from flowcept import FlowceptLLM, flowcept_agent_tool

@mcp.tool()
@flowcept_agent_tool
def evaluate_scores(layer, result, scores):
    ...
    prompt = get_prompt(layer, result, scores)
    llm = FlowceptLLM(ChatOpenAI(model="gpt-4o"))
    response = llm.invoke(prompt)
    ...
    return ...
```

(source: arXiv:2508.02866 Fig. 4)

- `@flowcept_agent_tool` creates an `AgentTool` activity, captures inputs/outputs, links to the executing `AIAgent`.
- `FlowceptLLM` wraps any LLM client (CrewAI/LangChain/OpenAI compatible). On `invoke()`, it captures the prompt, response, model metadata (provider, name, temperature), and optional telemetry (response time). Each call becomes an `AIModelInvocation`.
- The provenance system automatically establishes `wasInformedBy` from `AgentTool` to `AIModelInvocation`.

**For S4**: this is a near-zero-friction instrumentation pattern. Two decorators per agent tool plus one wrapper around the local LLM client gives a full PROV-AGENT trace. Could either adopt Flowcept directly or replicate the decorator pattern in [[langgraph-agent]] with a lighter Python implementation that writes to [[fuseki-triplestore]].

## The five enabled queries (§IV.B) — RQ3 spine

Each query is a concrete RDF/SPARQL traversal over the PROV-AGENT graph. **These five queries should appear verbatim (or close to verbatim) in the thesis RQ3 evaluation chapter** — they are the canonical operator-trust queries the user study should test.

| ID | Query | RQ3 hypothesis served |
|---|---|---|
| **Q1** | Given an agent decision, what was the complete lineage until the first input data? | "Operators can trace any recommendation back to its full evidence chain" — supports H4 (Likert ≥ 4, SUS ≥ 68) |
| **Q2** | For layer/iteration N, what was the agent decision, the available score options, and the reasoning? | "Operators understand *why* the agent picked option A over B" |
| **Q3** | What was the LLM prompt and response when a surprising agent decision was identified? | **The hallucination-debugging query** — most direct test of PROV-O's value-add |
| **Q4** | How did an agent decision influence subsequent workflow activities? | Error-propagation analysis across iterations |
| **Q5** | Where did erroneous data originate, and how did it propagate? | Root-cause analysis spanning sensor → model → agent decision → downstream task |

(source: arXiv:2508.02866 §IV.B)

## The use case is structurally identical to the thesis scenario

§IV.B's evaluation use case is **autonomous additive manufacturing** at ORNL: a metal 3D printer (edge) streams sensor data layer-by-layer to an HPC physics-based model (Manufacturing Demonstration Facility → OLCF), an AI agent (gpt-4o via cloud) makes per-layer control decisions, and decision_i informs decision_i+1.

Map this onto the thesis's [[anomaly-triage|PumpStation_12 anomaly-triage scenario]]:

| ORNL additive manufacturing | Thesis anomaly triage |
|---|---|
| 3D printer at MDF | Pump station |
| Layer-by-layer sensor data (edge) | Acoustic / vibration sensor data ([[mimii-dataset|MIMII]]) |
| Physics-based model (HPC) | Anomaly detector + KG + SOPs |
| Per-layer control decision (cloud gpt-4o) | Per-anomaly action plan (local LLM) |
| Decision_i influences decision_i+1 | Single-shot per anomaly (no feedback loop in thesis design) |

**Same architecture, different domain.** The thesis can directly cite PROV-AGENT's evaluation as a sibling deployment, with the differences being: (a) thesis is single-shot (no iterative feedback), (b) thesis uses local LLM not cloud, and (c) thesis adds [[shacl-validation]] which PROV-AGENT does not. (source: arXiv:2508.02866 §IV.B)

## Self-described novelty

Conclusion §V: *"To the best of our knowledge, this is the first provenance framework designed to track agent actions and decisions in agentic workflows."*

§II.B contrasts PROV-AGENT with prior PROV extensions:

- **PROV-DfA** (Souza & Mattoso 2018) — human actions in human-steered workflows, not AI agents.
- **ProvONE** — workflow-specific metadata for traditional workflow management systems.
- **PROV-ML** (Souza et al. 2022) — ML model training/evaluation, not inference-time agentic decisions.
- **FAIR4ML** (Castro et al. 2025) — model-centric FAIR principles.
- **Davis et al. 2017**, **Friedman et al. 2020** — multi-agent PROV extensions that *predate agentic workflows and lack core agentic AI concepts*.

For the thesis: PROV-AGENT (Aug 2025) and the thesis project (Mar–Aug 2026) are **contemporaneous**. The thesis can cite PROV-AGENT as a parallel-developed precedent but should clearly delineate the additive contributions (see next section).

## Gaps relative to S4 — additive thesis contributions

| PROV-AGENT | S4 adds |
|---|---|
| `DomainData` is generic | Specialized via [[ssn-sosa]] + manufacturing ontology shapes — typed, validated |
| **No SHACL / no constraint validation** — agent decisions are traced but not gated | [[shacl-validation]] self-correction loop **rejects** decisions that violate domain shapes |
| Cloud-LLM focused (gpt-4o) | Local-LLM focused ([[local-deployment]] / RQ4) |
| Observability-first | Correctness-first **and** observability — both layers |
| Cross-facility (edge / cloud / HPC) emphasized | Single-facility local deployment (simpler scope) |
| Use case is single iterative agent (3D-print control) | Use case is single-shot per anomaly query (4-strategy harness) |
| No comparison against baselines without provenance | Compares S1 (no PROV-O) → S4 (full PROV-O) on operator-trust user study |

The novelty story for the thesis: PROV-AGENT establishes the *vocabulary* and *capture mechanism*; S4 extends it with **constraint-validated** agent decisions ([[shacl-validation]]) and an **expert ontology** ([[ssn-sosa]]) for the manufacturing domain. PROV-AGENT does not do these.

## Mapping S4 components to PROV-AGENT classes

Useful for the implementation chapter — the S4 PROV record can be entirely expressed in PROV-AGENT vocabulary:

| S4 component (per [[kg-agent-s4]]) | PROV-AGENT class |
|---|---|
| The S4 agent itself | `AIAgent` (one instance per agent) |
| Each tool call (`sparql_query`, `vector_search`, `shacl_validate`) | `AgentTool` activity |
| Each local-LLM call (planning, pruning, reasoning, generation) | `AIModelInvocation` activity |
| The local LLM | `AIModel` entity |
| Prompt sent to LLM | `Prompt` entity |
| LLM output | `ResponseData` entity |
| Asset, sensor, observation triples retrieved from Fuseki | `DomainData` entities |
| Action plan output | `DomainData` entity (`AgentDecision` analogue), `wasAttributedTo` the agent |
| SHACL validation report | **NEW S4 SUBCLASS — not in PROV-AGENT**: `ValidationReport` (subclass of `DataObject`), `wasGeneratedBy` a `shacl_validate` `AgentTool` activity |

The last row is where S4 *extends* PROV-AGENT minimally — adding one new entity subclass (`ValidationReport`) and one new tool type (`shacl_validate`). This is the cleanest framing of the S4 contribution to the provenance literature: **PROV-AGENT + `ValidationReport`**.

## Open questions for ingest

- Is Flowcept practical to adopt directly, or does its broker-based + Redis/Kafka infrastructure exceed the local-deployment footprint? Lighter alternative: replicate the decorator pattern with a SQLAlchemy-or-Fuseki backend.
- The five queries (Q1-Q5) need to be operationalized as concrete SPARQL queries against Fuseki for the thesis evaluation. Templates can be lifted from PROV-AGENT's example traversals — flag for Phase 4 implementation.
- PROV-AGENT does not specify how to *visualize* the provenance graph for operators. The thesis user study (RQ3 / H4) must design a UI — PROV-AGENT's Streamlit chat interface (Fig. 5B) is one option; a force-directed graph view is another.
- How does PROV-AGENT's MCP-centric model interact with [[langgraph-agent]]'s state-graph abstraction? Both can coexist — LangGraph state transitions are `Activity` instances, MCP tool calls are also `Activity` instances; the choice is mostly aesthetic.

## Action items for the wiki

- Resolve `[NEEDS VERIFICATION]` flags in [[prov-o]] for `PROV_AGENT_Provenance_AI_Agents_2025.pdf` — done in this ingest.
- Update `kg-agent-s4.md` PROV-O row in the peer-reviewed-basis table with the verified citation.
- The thesis-pitch §5.4 row currently cites *Dibowski 2024 (FOIS)* and *Lavrinovics et al. 2025 (J. Web Semantics)* as the PROV-O audit-trail basis. **PROV-AGENT (Souza et al. 2025) should be added as a third reference** — it is more directly applicable since it is *agentic* provenance, whereas the other two are general AI-agent provenance and KG audit framework respectively. None of those three papers is in `raw/`; PROV-AGENT is the only verified reference.

## Related pages

- [[prov-o]]
- [[kg-agent-s4]]
- [[shacl-validation]]
- [[langgraph-agent]]
- [[research-questions]]
- [[anomaly-triage]]
- [[mfg-agentgraph]]
- [[fuseki-triplestore]]
