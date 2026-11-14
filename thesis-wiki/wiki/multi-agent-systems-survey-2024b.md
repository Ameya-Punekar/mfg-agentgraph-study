# Multi-Agent Systems Survey (Chen et al. 2024)

**Summary**: Survey of 125 LLM-based Multi-Agent System (LLM-MAS) papers from ∗ACL/NeurIPS/AAAI/ICLR 2023-24, organising the field around three application aspects (solving complex tasks, simulating scenarios, evaluating generative agents). For MFG-AgentGraph the value is **positional**: it justifies the thesis's single-agent design choice and supplies a reusable agent-component decomposition that maps onto the LangGraph implementation.

**Sources**: `raw/Multi_Agent_Systems_Survey_2024b.pdf` (Chen, Liu, Han, Zhang, Liu — Harbin Institute of Technology, arXiv:2412.17481v2, 7 Jan 2025).

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ4 (efficiency-explosion argument for staying single-agent), RQ1 (related-work breadth — MAS is *not* one of S1-S4 but is the obvious next layer beyond S4).

---

## What this paper is

Chen et al. survey 125 papers on **LLM-based Multi-Agent Systems** (LLM-MAS), defined as "a collection of generative agents capable of interacting and collaborating within a shared environmental setting" (source: arXiv:2412.17481 §2). The authors propose a taxonomy distinct from Guo et al. 2024 (their immediate predecessor survey) by reorganising the field around the **purpose** of the LLM-MAS rather than its mechanism: (i) solving complex tasks, (ii) simulating specific scenarios, (iii) evaluating generative agents (source: arXiv:2412.17481 §1, Fig. 1).

The 125 papers were drawn from ∗ACL, NeurIPS, AAAI, ICLR 2023-24 plus selected unpublished arXiv work. The full list is on the authors' GitHub: `bianhua-12/Multi-generative_Agent_System_survey` (source: arXiv:2412.17481 §1, footnote 1).

## The agent-component decomposition (the part useful to the thesis)

§2.1 decomposes a generative agent into four parts and the environment into three:

| Component | Role | MFG-AgentGraph mapping |
|---|---|---|
| **LLM** | Core control / language interface | Local quantised LLM (7B-70B, see [[local-deployment]]) |
| **Profile** | Role definition in natural language; customised prompts per agent task | SOP-derived role prompt: "You are an anomaly-triage assistant for pump station 12" |
| **Reasoning** | Planning, deliberation | [[think-on-graph]]/[[reasoning-on-graphs]] planner over the KG |
| **Memory** | Long-term + short-term + sensory; stores past trajectories | Conversation history + [[prov-o]] trace + [[fuseki-triplestore]] historical observations |
| **Rules** *(env)* | Behavioural structure / norms | [[shacl-validation]] constraints (machine-checkable) + SOP rules |
| **Tools** *(env)* | Action execution that changes the world | SPARQL endpoint, SHACL validator, vector retrieval — registered as tool-calls in [[langgraph-agent]] |
| **Intervention** *(env)* | External (human/supervisor) control to read state or interrupt | Operator escalation step in [[anomaly-triage]] |

(source: arXiv:2412.17481 §2.1-§2.2)

**Why it matters**: even though MFG-AgentGraph runs **one** generative agent, the same seven-component decomposition is the cleanest way to describe the LangGraph design. Use it in the thesis architecture chapter to anchor the design vocabulary in survey-level terminology rather than ad-hoc names.

## Three reasoning-framework families for task-solving (§3.1)

For LLM-MAS that **solve complex tasks**, Chen et al. cluster the reasoning frameworks into three families:

1. **Multi-stage** — agents act as serial problem solvers at different pipeline stages (e.g. ChatDev, Qian et al. 2024b). Each agent owns a phase.
2. **Collective decision-making** — agents vote or debate to reach one answer (e.g. ChatEval, multi-agent debate).
3. **Self-refine** — an agent (or pair) reflects on and corrects its own output (Wang et al. 2024c, Chen et al. 2024e).

(source: arXiv:2412.17481 §3.1, Fig. 1)

**Mapping to S4**: the [[shacl-validation]] **validate → self-correct** loop is structurally a **single-agent self-refine** — one generative agent generating, a deterministic SHACL engine producing the critique signal, and the same agent regenerating with the failure report in context. This is the LLM-MAS family S4 most resembles, with the *critic* role replaced by deterministic constraint checking. Worth citing in the thesis defence as: "S4 inherits the self-refine pattern of Chen et al. 2024 §3.1 but substitutes a peer-LLM critic with a SHACL engine — gaining determinism and ontology-grounded provenance at the cost of critic flexibility."

## Why the thesis stays single-agent (the central positional claim)

§6.2 lists "Efficiency explosion" as the headline practical-deployment challenge of LLM-MAS:

> "Due to their autoregressive architecture, LLMs typically have slow inference speeds. However, generative agents need to query LLMs for each action multiple times, such as extracting information from memory, making plans before taking actions, and so on. When the LLM-MAS scales up, this problem will be magnified, especially for generative agents that have a large action space." (source: arXiv:2412.17481 §6.2)

The companion challenge is **Accumulative Effect**: "Since each round of LLM-MAS is based on the results of the previous round, and LLM-MAS have a great impact on the subsequent results" — i.e. errors compound across rounds (source: arXiv:2412.17481 §6.2).

**Thesis implication for RQ4**: the local-deployment latency budget for MFG-AgentGraph is already tight — [[think-on-graph]]'s ~10 LLM calls × 3 s ≈ 30 s p95 (see [[local-deployment]]). Multiplying that by an n-agent debate or multi-stage pipeline puts the system out of budget on commodity hardware. The single-agent design with deterministic-tool augmentation (SPARQL, SHACL) is the minimum-call architecture that still delivers grounded reasoning. Chen et al. §6.2 is the cleanest published citation for this design choice.

**Thesis implication for evaluation (RQ1)**: even within single-agent S4, the SHACL self-refine loop is subject to **Accumulative Effect** — a wrong plan in iteration 1 may bias the regeneration in iteration 2. Cap iteration count and report per-iteration faithfulness in the RQ1 chapter.

## What the survey does **not** cover (relevant to the thesis)

- **No knowledge-graph integration**. The 125 surveyed LLM-MAS use long-term memory (vector stores, summaries) and tools, but none of the surveyed reasoning frameworks treat a KG as the substrate of reasoning. This is a gap the thesis fills via [[kg-agent-s4|S4]].
- **No manufacturing applications**. §4 simulation domains are: Tiny Society, Economics, Social Media, Game (social) + Wireless (physical). Even Li et al. 2024a's "doctor agent" hospital simulacrum is the closest physical-world domain, and it is not industrial.
- **No provenance**. The five operator-trust queries from [[prov-agent-souza2025]] have no analogue in the surveyed LLM-MAS — provenance/audit-trail is treated as an open problem only obliquely (via "objective metrics for group behavior", §6.3).
- **No SHACL or ontology-grounded validation.** Self-refine is exclusively LLM-as-critic; deterministic constraint validation is absent.

## Communication taxonomy (§2.1, §3.1) — noted, not adopted

§2.1 splits inter-agent communication into **collaboration** (share information) vs. **consensus** (reach Nash equilibrium); §3.1 covers **speed optimization** (e.g. shorter messages, non-verbal) and **distributed discussion** (proceed under information asymmetry). All four are MAS-specific and irrelevant to a single-agent thesis. Recorded here for completeness.

## Open issues raised (§6) — relevant flags for thesis evaluation

| Issue | Relevance to MFG-AgentGraph |
|---|---|
| Generalized alignment | Local-LLM hallucination still a risk under SOP/ontology grounding — confirm via faithfulness metric |
| Hallucination | [[shacl-validation]] catches structural violations; semantic hallucination still requires faithfulness scoring |
| Lack of long-text capability | Conversation + PROV trace can grow large; check 8K-32K context fits the trace dump |
| Lack of objective metrics for group behaviour | N/A (single-agent), but Chen et al.'s framing supports treating the LLM-agent + SHACL critic as a "group" for metric design |
| Lack of common benchmarks | MIMII + author-built KGQA benchmark is the thesis's response in the manufacturing domain |

(source: arXiv:2412.17481 §6.1-§6.3)

## Notable resources flagged for possible reuse

| Paper | Why it might matter later |
|---|---|
| Liu et al. 2023b — **AGENTBENCH** | Multi-environment agent evaluation harness; could host an MFG-AgentGraph benchmark variant if the thesis wants a multi-task RQ1 extension |
| Hong et al. 2023 — **MetaGPT** | Role-based multi-agent code dev — closest pattern if the thesis ever extends S4 with a separate "SOP-author" agent and "diagnostician" agent |
| Wang et al. 2024c — self-refine on FOLIO-wiki | Self-refine baseline; structurally analogous to SHACL loop |
| Mou et al. 2024 — **SoMoSiMu-Bench** | Replacing edge agents with rule-based ones to control efficiency explosion — a potential pattern for RQ4 ablation if S4 is later embedded in a small MAS |

(source: arXiv:2412.17481 Tables 1-3)

## Pull-quotes worth saving

> "Compared to traditional agents, generative agents need to be able to perform more complex behaviors... Therefore, in addition to using LLMs as the core, generative agents also require the following characteristics: (i) Profiling... (ii) Memory... (iii) Planning... (iv) Action..." (source: arXiv:2412.17481 §2.1)

> "Generative agents have a certain probability of hallucination in their interaction with other agents. Various enhancement methods can alleviate this problem but cannot solve it." (source: arXiv:2412.17481 §6.1)

> "Due to their autoregressive architecture, LLMs typically have slow inference speeds. However, generative agents need to query LLMs for each action multiple times... When the LLM-MAS scales up, this problem will be magnified." (source: arXiv:2412.17481 §6.2)

## Open questions for the thesis

1. **Should the thesis consider a 2-agent ablation** (e.g. planner agent + validator agent) as a comparator to the single-agent S4? Chen et al. would call this collective decision-making + tool-use; the **efficiency-explosion** prediction is a clean RQ4 hypothesis to test.
2. **Profile authoring** — does the thesis hand-write the agent's role prompt or extract it from SOP text? §2.1 lists profiling as a defining trait but does not mandate a method.
3. **Long-context limit** — the Memory component grows monotonically (PROV trace + retrieved subgraph); §6.1 calls this out as a known LLM-MAS bottleneck. Plan compaction strategy before week-12 evaluation.

## Related pages

- [[langgraph-agent]] — agent-component mapping anchors LangGraph design
- [[local-deployment]] — efficiency-explosion citation feeds H5 / RQ4
- [[kg-agent-s4]] — S4 = single-agent self-refine over a KG, structurally inheriting Chen et al. §3.1's self-refine family
- [[shacl-validation]] — the deterministic critic in S4's self-refine loop
- [[prov-agent-souza2025]] — fills the provenance gap Chen et al. note as open
- [[think-on-graph]] — supplies the LLM-call complexity analysis that motivates staying single-agent
