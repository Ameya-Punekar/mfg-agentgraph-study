# AGENTiGraph (Zhao et al., CIKM 2025)

**Summary**: AGENTiGraph (Adaptive General-purpose Entities Navigated Through Interaction) is the **closest published architectural precedent for MFG-AgentGraph**: a multi-agent KG-LLM system with seven specialised agents (Intent → Key Concept → Task Planning → KG Interaction → Reasoning → Response → Update) targeting non-technical users in privacy-sensitive domains. Same positioning as MFG-AgentGraph (data sovereignty, multi-step KG reasoning, auditability), but **no SHACL, no PROV-O, no domain ontology** — extracts entities/relations via NER/RE on-the-fly. The gaps AGENTiGraph leaves open are exactly the contributions S4 makes.

**Sources**: `raw/AGENTiGraph_Multi_Agent_KG_2025.pdf` (Zhao, Blum, Gao, Chen, Yang, Marquez-Carpintero, Pina-Navarro, Fu, Morikawa, Iwasawa, Matsuo, Park, Li — University of Tokyo + Bielefeld + Alicante + Soongsil; CIKM 2025; arXiv:2508.02999v1, 5 Aug 2025).

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ1 (architectural comparator + baseline numbers), RQ4 (Llama-3.1-8b + agent loop ≥ GPT-4o zero-shot — second empirical anchor for local-LLM viability after [[think-on-graph]]).

---

## Why this paper matters most so far

Of all sources ingested, AGENTiGraph is **structurally the most similar published system to MFG-AgentGraph**:

| Dimension | AGENTiGraph | MFG-AgentGraph (S4) |
|---|---|---|
| Backbone | KG + LLM | KG + LLM |
| User | Non-technical (legal, medical, education) | Non-technical (factory operators) |
| Motivation | "Privacy, compliance, multi-step reasoning"; "construct proprietary knowledge bases ... incorporate emerging information such as regulations and research" | Data sovereignty + reliability + low-latency on-prem operator support |
| Architecture | Multi-agent pipeline (7 agents) | Single LangGraph agent with multiple tool nodes |
| KG store | Neo4j + Cypher | Apache Jena Fuseki + SPARQL |
| KG construction | NER + RE on-the-fly via LLM (schema-free, bottom-up) | Curated SSN/SOSA + manufacturing ontology (schema-based, top-down) |
| Validation | None | [[shacl-validation\|SHACL]] self-correction loop |
| Provenance | "Tracked and audited" (claimed, not delivered) | [[prov-o\|PROV-O]] with [[prov-agent-souza2025\|PROV-AGENT]] vocabulary |
| Visualisation | Graph visualisation + automated node induction | Support subgraph in evidence package |

(source: arXiv:2508.02999 §1, §2)

**The four S4 contributions over AGENTiGraph (ontology backbone, SHACL gating, PROV-O trace, single-agent efficiency)** are precisely what AGENTiGraph promises ("tracked and audited", "control reasoning") but does not technically deliver. Cite this paper in the related-work chapter as the **closest published comparator** and frame the thesis contributions as the missing technical pieces.

## The 7-agent pipeline (§2)

| # | Agent | What it does | MFG-AgentGraph counterpart |
|---|---|---|---|
| 1 | **User Intent Agent** | CoT + few-shot to interpret natural-language input intent (𝑖) | LangGraph router / first-step classifier |
| 2 | **Key Concept Extraction Agent** | NER + RE; map to KG via BERT-vector similarity | Schema-bound entity linker against SSN/SOSA + asset ontology |
| 3 | **Task Planning Agent** | CoT decomposes intent into ordered task sequence (𝑡₁…𝑡ₙ) | [[reasoning-on-graphs\|RoG]]-style relation-path plan |
| 4 | **KG Interaction Agent** | ReAct + few-shot generates formal query (Cypher) per task; dynamic refinement on intermediate results | [[think-on-graph\|ToG]] explore→prune→reason loop with SPARQL templates |
| 5 | **Reasoning Agent** | LLM contextual reasoning over retrieved subgraph | Local LLM hypothesis generation in S4 |
| 6 | **Response Generation Agent** | CoT + ReAct + few-shot synthesises coherent answer | Final S4 answer composition with evidence package |
| 7 | **Update Agent** | LLM-generated Cypher for new entities/relationships: 𝐺 ← 𝐺 ∪ 𝐸ₙₑw, 𝑅ₙₑw | **Not in S4 scope** — thesis treats KG as immutable except for sensor observation ingestion |

(source: arXiv:2508.02999 §2)

**Single-agent vs. multi-agent**: AGENTiGraph runs all seven agents per query — directly subject to the **efficiency-explosion** challenge of [[multi-agent-systems-survey-2024b|Chen et al. 2024]] §6.2 and [[multi-agent-llm-survey-2024|Guo et al. 2024]] §6.4. The thesis chooses to keep the same functional decomposition but execute it as **distinct LangGraph nodes within a single agent loop** — this is the architectural difference that protects the [[local-deployment]] / RQ4 latency budget.

## Empirical anchor for RQ4 — Llama-3.1-8b + agent ≥ GPT-4o zero-shot

Table 2 (TutorQA 3,500-query benchmark, NLP-education domain):

| Setting | Acc | F1 | Exec. Success |
|---|---|---|---|
| **Zero-shot LLM** | | | |
| LLaMa 3.1-8b | 0.6234 | 0.6112 | 0.5387 |
| LLaMa 3.1-70b | 0.6789 | 0.6935 | 0.5912 |
| Gemini-1.5 pro | 0.8256 | 0.8078 | 0.7434 |
| GPT-4 | 0.7845 | 0.7463 | 0.7123 |
| GPT-4o | 0.8334 | 0.8156 | 0.7712 |
| **Few-shot Pure LLM** | | | |
| GPT-4 (few-shot) | 0.8532 | 0.8291 | 0.7805 |
| **AGENTiGraph (multi-agent)** | | | |
| LLaMa 3.1-8b | 0.8356 | 0.8178 | 0.7230 |
| LLaMa 3.1-70b | 0.8789 | 0.8367 | 0.7967 |
| Gemini-1.5 pro | 0.9389 | 0.9323 | 0.8901 |
| GPT-4 | 0.9234 | 0.8912 | 0.8778 |
| GPT-4o | 0.9512 | 0.9467 | 0.9045 |

(source: arXiv:2508.02999 Table 2)

**Headline finding for RQ4**: Llama-3.1-8b + AGENTiGraph (acc 0.8356) **beats GPT-4o zero-shot** (0.8334) on classification accuracy. On execution success, Llama-3.1-8b + agent (0.7230) is within 5pp of GPT-4o zero-shot (0.7712).

**Why this matters**: it confirms the [[think-on-graph|ToG]] result on a **different LLM family and a different KG** — the agentic-loop-amplifies-small-LLMs effect generalises beyond the original ToG/Llama-2-70B setting. The thesis can now cite **two independent empirical anchors** for H5 ("local LLM is enough"):

1. ToG with Llama2-70B competing with GPT-4 + CoT on multi-hop QA ([[think-on-graph]] Table 2).
2. AGENTiGraph with Llama-3.1-**8b** beating GPT-4o zero-shot on KG-grounded classification (Zhao et al. Table 2).

The 8b-model anchor is more aggressive — supports the thesis claim that even a 7-8B quantised local model could be sufficient under an agent loop.

## Functionality positioning (Table 1) — same baselines as S1 / S2

AGENTiGraph's own comparison table directly mirrors the thesis's S1-S2-S4 framing:

| Functionality | LLM Chatbots (≈ S1) | GraphRAG (≈ S2) | AGENTiGraph (≈ S4-like) |
|---|---|---|---|
| Basic QA | ✓ | ✓ | ✓ |
| Multi-round QA | ✓ | ✓ | ✓ |
| **Multi-hop Reasoning** | ✗ | ✓ | ✓ |
| **Private Data** | ✗ | ✓ | ✓ |
| Visualisation | ✗ | ✗ | ✓ |
| User Interaction (graph manipulation) | ✗ | ✗ | ✓ |
| Graph Edits | ✗ | ✗ | ✓ |
| Realtime Updates | ✗ | ✗ | ✓ |
| Automated Workflow | ✗ | ✗ | ✓ |

(source: arXiv:2508.02999 Table 1)

**Thesis use**: this is essentially the [[strategy-comparison]] matrix already implicit in MFG-AgentGraph, with three columns (S1/S2/S4) — re-use the same row structure plus columns for SHACL pass-rate, PROV-O coverage, and ontology grounding. Cite Zhao et al. Table 1 as prior art for the functionality-comparison framing.

## What AGENTiGraph promises but does not deliver

§1 claims: "AGENTiGraph empowers users to actively curate, manipulate, and visualise their graphs via natural language dialogue. By orchestrating specialised agents for intent classification, graph updates, and continuous knowledge integration, **it ensures a chain of knowledge can be both tracked and audited**, addressing pressing challenges in privacy, compliance, and multi-step reasoning." (source: arXiv:2508.02999 §1)

But the §2 pipeline contains **no provenance recording, no validation step, no audit trail**. The system delivers on visualisation and natural-language interaction; the auditability claim is rhetorical. **Exactly the gap the thesis fills with PROV-O and SHACL.**

Frame in the thesis introduction:

> "AGENTiGraph (Zhao et al. CIKM 2025) is the closest published system to MFG-AgentGraph's design — a multi-agent KG+LLM framework for non-technical users in privacy-sensitive domains. AGENTiGraph claims to ensure 'a chain of knowledge can be both tracked and audited' but provides no technical mechanism for validation or provenance. MFG-AgentGraph delivers on this promise via SHACL constraint validation and PROV-O traces grounded in PROV-AGENT (Souza et al. e-Science 2025)."

## UI / Interface — relevant for thesis deliverable design

§3.1 describes a **dual-mode interface** with three components:

1. **Chatbot Mode** — LLM-based intent + response over KG traversal.
2. **Exploration Mode** — interactive KG visualisation with entity recognition; supports hierarchy navigation.
3. **Knowledge Graph Management Layer** — bridges multi-agent system to Neo4j via Bolt protocol.

User study (§4.3): 7-point Likert ratings on Interface Intuitiveness 5.8, Response Comprehensibility 6.0, Relation Judgment Accuracy 6.3, Path Searching Clarity 5.9, Overall Satisfaction 6.0. **Useful precedent for the RQ3 user-study Likert design**: AGENTiGraph used five aspects on a 7-point scale; thesis can use a similar instrument augmented with PROV-AGENT's Q1-Q5 operator-trust queries (already noted in [[prov-agent-souza2025]]).

(source: arXiv:2508.02999 §3.1, §4.3, Table 3)

## TutorQA — relevant benchmark precedent

§4.1: Zhao et al. extend TutorQA from base size to 3,500 cases (500 queries × 6 predefined tasks + 500 free-form), using LLMs to mimic student questions with human verification. Tasks: Relation Judgment, Prerequisite Prediction, Path Searching, Concept Clustering, Subgraph Completion, Idea Hamster. Dataset published on HuggingFace `li-lab/tutorqa`.

**Thesis use**: this is a prototypical method for building a domain-specific KGQA benchmark from an authoritative source — the manufacturing thesis can use the same recipe (LLM-generated questions over MIMII metadata + SOPs + asset ontology, then expert verification) for the RQ1 benchmark.

## Pull-quotes worth saving

> "AGENTiGraph empowers users to actively curate, manipulate, and visualise their graphs via natural language dialogue. By orchestrating specialised agents for intent classification, graph updates, and continuous knowledge integration, it ensures a chain of knowledge can be both tracked and audited." (source: arXiv:2508.02999 §1) — *the rhetorical claim S4 actually delivers on*

> "Our results show that AGENTiGraph still provides substantial gains over these new baselines. For instance, GPT-4o integrated with AGENTiGraph achieves a 95.12% accuracy in task classification, which highlights that AGENTiGraph's hierarchical, multi-step reasoning pipeline and structured approach—beyond just zero-shot or few-shot prompting—drives meaningful improvements." (source: arXiv:2508.02999 §4.2)

> "These improvements are consistent across all model sizes, even for the simpler LLaMa 3.1-8b, suggesting that the agent-based pipeline amplifies the capabilities of underlying models." (source: arXiv:2508.02999 §4.2) — *direct support for thesis H5 / RQ4*

## Open questions raised

1. **Should S4 add a Concept-Linking-via-BERT-similarity step** between SPARQL retrieval and LLM reasoning? AGENTiGraph's Key Concept Extraction Agent (BERT-vector linking) is one mechanism for grounding free-text user query into the SSN/SOSA vocabulary. Worth prototyping in Phase 2.
2. **Can the thesis adopt AGENTiGraph's TutorQA-style benchmark construction recipe** (LLM-generate questions → human verification) for the manufacturing KGQA benchmark? Cheap and well-precedented.
3. **Visualisation deliverable**: AGENTiGraph's Exploration Mode (KG visualisation + automated node induction) is more developed than the thesis's current "support subgraph in evidence package" plan. If timeline allows, port the dual-mode pattern.
4. **Update Agent (Cypher-from-LLM graph edits)** is explicitly **out of S4 scope** — sensor observations are appended via a deterministic ingestion pipeline, not LLM-authored triples. Worth flagging as a deliberate scope decision in the thesis architecture chapter.

## Related pages

- [[mfg-agentgraph]] — direct architectural comparator; framing for thesis introduction
- [[kg-agent-s4]] — gaps that AGENTiGraph leaves open (SHACL, PROV-O, ontology grounding) are S4's contributions
- [[strategy-comparison]] — AGENTiGraph Table 1 mirrors the S1/S2/S4 functionality matrix
- [[local-deployment]] — Llama-3.1-8b + agent ≥ GPT-4o zero-shot is second empirical anchor for H5
- [[think-on-graph]] — first empirical anchor; AGENTiGraph generalises the finding to a different LLM family
- [[multi-agent-systems-survey-2024b]] — efficiency-explosion argument applies to AGENTiGraph's 7-agent pipeline
- [[research-questions]] — AGENTiGraph user-study Likert design informs RQ3 instrument
