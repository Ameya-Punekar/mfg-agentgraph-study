# KG-Agent S4 (Proposed)

**Summary**: The proposed full system. A LangGraph agent issues SPARQL against Fuseki, performs ontology-guided vector retrieval from Qdrant, generates hypotheses with a local LLM, validates against SHACL with a self-correction loop, extracts a support subgraph, and records a PROV-O trace. The S4 strategy that this thesis introduces.

**Sources**: `thesis-pitch-v2.md` §5.4, §6. Method-paper basis: [[reasoning-on-graphs]], [[think-on-graph]], [[think-on-graph-2]], [[og-rag]] — most [NEEDS VERIFICATION] until the per-source PDFs are read.

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ1 (proposed method), RQ2 (SHACL), RQ3 (PROV-O), RQ4 (local deployment).

---

## What it is (pipeline)

1. **Plan** — agent decides what to retrieve based on the query.
2. **KG retrieval** — SPARQL query against [[fuseki-triplestore]] for the relevant subgraph.
3. **Vector retrieval** — ontology-guided search in Qdrant for SOP/manual passages.
4. **Hypothesis generation** — local LLM ranks candidate actions given the joined context.
5. **SHACL validation** — `pyshacl` checks the plan against domain shapes; if invalid, the agent self-corrects (loops back to step 2 with the validation report as input).
6. **Support subgraph** — extract the exact KG edges and document chunks used as evidence.
7. **PROV-O record** — write an activity entry with data sources, model version, tools used, timestamps.

(source: thesis-pitch-v2.md §6)

## Peer-reviewed basis

| Component | Source | Citation |
|---|---|---|
| Plan-as-relation-path | [[reasoning-on-graphs]] | Luo et al., ICLR 2024, arXiv:2310.01061 — verified |
| Iterative explore→prune→reason loop ("LLM ⊗ KG") | [[think-on-graph]] | Sun et al., ICLR 2024, arXiv:2307.07697 — **verified, the most direct S4 precedent** |
| Hybrid KG + corpus retrieval | [[think-on-graph-2]] | Sun et al., ICLR 2025, arXiv:2407.10805 |
| Ontology backbone | [[og-rag]] | Sharma, Kumar & Li, arXiv:2412.15235 (2024 preprint) — see [[og-rag-2024]] |
| SHACL repair loop | Manufacturing KG digital-twin practice | DigitalTwinKG 2025 |
| PROV-O audit trail | [[prov-agent-souza2025]] **(verified)**; Dibowski 2024 (FOIS); Lavrinovics et al. 2025 (J. Web Semantics) | Souza et al., e-Science 2025, arXiv:2508.02866 |
| SSN/SOSA modelling | [[ssn-sosa]] | Janowicz et al. 2018 (arXiv:1805.09979, *J. Web Semantics*) — **verified, see [[sosa-ssn-2018]]** |

(source: thesis-pitch-v2.md §5.4) — all individual method claims [NEEDS VERIFICATION] until source PDFs are read.

## Key additions over S1–S3

- **vs. S1 ([[naive-rag]]):** adds KG, agent loop, validation, provenance.
- **vs. S2 ([[graphrag]]):** swaps LLM-built graph for expert ontology; adds validation and provenance.
- **vs. S3 ([[og-rag]]):** adds the agent loop, SHACL self-correction, support subgraph extraction, and PROV-O.

(source: thesis-pitch-v2.md §5.4)

## Placement in Pan et al. 2024 taxonomy — *the* paradigm-3 anchor

S4 is the only one of the four strategies that sits in **paradigm 3: Synergized LLMs + KGs** in the [[unifying-llms-kgs|Pan 2024 roadmap]] (S1, S2, S3 are all paradigm-1). Within paradigm 3 §6.2, S4 belongs specifically to **LLMs as Agents Reasoning** — the same bucket as ToG, RoG, StructGPT, KSL, and KD-CoT — *not* to LLM-KG Fusion Reasoning (KEPLER, JointGT, DRAGON, GreaseLM, JointLK, HKLM), which would require fine-tuning.

The choice between the two Synergized patterns is decisive for thesis-design defensibility. Pan §6.2 contrasts them in one passage: Fusion Reasoning *"may introduce extra parameters and computational costs while lacking interpretability"*, whereas Agents Reasoning *"provides a flexible framework for reasoning on KGs without additional training cost, which can be generalized to different LLMs and KGs. Meanwhile, the reasoning process is interpretable, which can be used to explain the results."* (source: Pan2024 §6.2). This passage should be quoted directly when defending S4 against reviewer objections about why fine-tuning was avoided.

## Why §7.5 of Pan 2024 specifically validates the agent design

§7.5 of the roadmap admits that *"Conventional LLMs trained on plain text data are not designed to understand structured data like knowledge graphs ... it is necessary to develop LLMs that can directly understand the KG structure and reason over it."* Until that future-direction is solved, the practical workaround is **tool-calling agents** — exactly what [[langgraph-agent]] + SPARQL tools provide in S4. (source: Pan2024 §7.5)

## PROV-AGENT framing — S4's PROV-O record is fully expressible in PROV-AGENT vocabulary

After ingest of [[prov-agent-souza2025]] (Souza et al., e-Science 2025), the PROV-O subgraph S4 emits per agent run can be expressed entirely in the PROV-AGENT taxonomy plus **one** new subclass:

| S4 component | PROV-AGENT class |
|---|---|
| The S4 agent | `AIAgent` |
| Each tool call (`sparql_query`, `vector_search`, `shacl_validate`) | `AgentTool` activity |
| Each local-LLM call (planning / pruning / reasoning) | `AIModelInvocation` activity |
| Prompt sent to LLM | `Prompt` entity |
| LLM response | `ResponseData` entity |
| Local LLM metadata | `AIModel` entity |
| Asset/sensor/observation triples | `DomainData` entities |
| Action plan (S4 output) | `DomainData` entity, `wasAttributedTo` the `AIAgent` |
| **SHACL validation report** | **NEW: `ValidationReport` (subclass of `DataObject`)** — not in PROV-AGENT |

The thesis's PROV-O contribution to the literature is: **PROV-AGENT + `ValidationReport` + SSN/SOSA-typed `DomainData`**. Use this framing in the contributions chapter — it positions S4 as a minimal, well-defined extension to a peer-reviewed (e-Science 2025) standard rather than a novel vocabulary. (source: arXiv:2508.02866 §III)

The five operator-trust queries enabled by PROV-AGENT (Q1-Q5 in [[prov-agent-souza2025]]) should be operationalized as concrete SPARQL queries against [[fuseki-triplestore]] and used as the test items in the [[research-questions|RQ3]] user study.

## Hard contract (anti-explainability-theater)

Every S4 action *must* include a non-empty `kg_edges` list. SHACL rejects plans that lack asset references. This is the structural guarantee that makes S4 auditable and is the operational defense against fluent-but-empty explanations. (source: thesis-pitch-v2.md §10, §14)

## Hybrid retrieval precedent: GraphRAG's own future-work proposal

[[graphrag-microsoft-2024|Edge et al. 2024]] explicitly identify a **hybrid local + global RAG** pattern as future work — combining embedding-based query→graph-annotation matching with just-in-time community-summary generation, allowing exploratory "drill down" through the community hierarchy. (source: arXiv:2404.16130 §6.2)

S4's plan→KG-retrieve→vector-retrieve flow is structurally the same idea executed with an **expert ontology** instead of an LLM-built graph and with **SHACL validation** instead of unconstrained LLM extraction. This means S4 isn't an arbitrary departure from S2; it is the direction the S2 paper's authors themselves identified as the natural next step. Useful framing for the related-work section. (source: arXiv:2404.16130 §6.2)

## Self-correction precedent: Self-RAG

Self-RAG (Asai et al. 2023, surveyed in [[rag-comprehensive-survey-2024]]) introduced *reflection tokens* that let an LLM adaptively decide when to retrieve and self-evaluate output quality. The S4 SHACL self-correction loop is structurally similar but replaces opaque LLM-internal reflection tokens with an *external, auditable* validation step (SHACL report) — this matters for [[research-questions|RQ3]] since the validation evidence becomes part of the operator-visible explanation. (source: RAG_Comprehensive_Survey_2024.pdf §4)

## No fine-tuning

Unlike RoG (which requires fine-tuning), S4 uses prompting + tool use only — keeps the system reproducible on commodity hardware and broadens model swappability. (source: thesis-pitch-v2.md §5.5 row "Fine-tuning needed")

## ToG (Sun et al. 2023) is the most direct S4 precedent

After ingest of [[think-on-graph]], the cleanest framing is: **S4 = ToG + ontology backbone + SHACL self-correction + PROV-O record**. Each addition is a concrete extension of the ToG loop:

| ToG component | S4 inherits | S4 adds |
|---|---|---|
| Three-phase loop (Init → Explore → Reason) | Verbatim | — |
| Beam-search exploration (Search + Prune over relations + entities) | Verbatim, default $N=D=3$ | Schema-constrained relation set from [[ssn-sosa]] |
| Pre-defined SPARQL templates (Appendix E.1) | Verbatim shape; replace Freebase prefix with manufacturing prefix | Shapes/CONSTRUCT queries for support-subgraph extraction |
| LLM Reasoning sufficiency gate ("Yes/No") | Verbatim | **AND** [[shacl-validation]] pass — double gating |
| Human knowledge correction (Fig. 4) | Conceptual lineage | Automated via SHACL self-correction loop |
| Reasoning paths as evidence | Verbatim | Wrapped in [[prov-o]] activity record |
| Triple format `(e, r, e)` | Verbatim (avoid sentence verbalization per Table 4) | — |

The thesis-defensibility argument: ToG demonstrates that (a) tight-coupling agentic reasoning beats loose-coupling RAG on multi-hop questions (Table 1, +18-23% over CoT), (b) the gain *transfers* to small local LLMs (Llama2-70B + ToG ≥ GPT-4 + CoT in some scenarios — empirical anchor for [[local-deployment]] / RQ4), and (c) ~60-93% of correct answers genuinely come from KG paths (Fig. 7) — not LLM hallucination. S4 builds on these results without invalidating them. (source: arXiv:2307.07697 §3.2.2, §B.2)

### ToG vs. ToG-R for S4

ToG-R (relation-only, random entity prune) costs $ND+D+1$ LLM calls vs. ToG's $2ND+D+1$. With $N=D=3$ that's ~12 vs. ~22 calls per query. **For RQ4 (p95 ≤ 30s with a local LLM), ToG-R is the safer default**; full ToG is the accuracy-first ablation. Run both. (source: arXiv:2307.07697 §2.2, §B.2.1)

## Resolved: how RoG's relation-path planning maps onto the S4 SPARQL agent

After ingest of [[reasoning-on-graphs]], the RoG → S4 adaptation is:

| RoG component | S4 adaptation |
|---|---|
| Fine-tuned plan generator | **Prompt** local LLM with the [[ssn-sosa]] + domain ontology vocabulary in context — relation choices are constrained by the schema, not learned |
| Constrained BFS retrieval (Algorithm 1) | **Parameterized SPARQL query** — BFS is delegated to [[fuseki-triplestore]] |
| FiD-style multi-path reasoning | Same local LLM reading retrieved paths in the prompt (no FiD) |
| Path existence as faithfulness | Path existence **plus** [[shacl-validation]] shape validation |
| Top-K beam search self-consistency | SHACL self-correction loop with re-planning on shape failure |

The thesis-defensibility argument for skipping RoG's fine-tuning rests on two empirical anchors from Luo et al. 2024 (Table 3): the planner's value transfers to *unmodified* downstream LLMs (Flan-T5-xl gained +119% Hits@1 with the frozen planner) — meaning the heavy lifting is in the planning *prompt structure*, not the LLM weights themselves. S4 replaces "trained planner weights" with "schema-constrained planning prompt + SHACL gating" and inherits the rest. (source: arXiv:2310.01061 §5.3, Table 3)

## Three-role hybrid framing (Ma et al. EDBT 2025)

[[llms-meet-kgs-qa-survey-2025|Ma et al. 2025]] organise LLM+KG-for-QA into three roles. **S4 is a hybrid that inhabits all three simultaneously**:

| Ma et al. role | S4 instance | Closest cited precedent |
|---|---|---|
| §3.1 Background Knowledge (RAG paradigm) | SPARQL subgraph in prompt context | GRAG, LEGO-GraphRAG, KG²RAG |
| §3.2 Reasoning Guidelines (online + agent-based) | [[think-on-graph\|ToG]]/[[reasoning-on-graphs\|RoG]] explore→prune→reason loop, schema-constrained | ToG, ToG-2, KG-Agent, **PoG** (closest self-correction precedent) |
| §3.3 Refiners and Validators (KG-driven filtering/validation) | [[shacl-validation\|SHACL]] gate + self-correction | **KGR** (Guan AAAI 2024 — closest validator precedent) |

In Ma et al. Table 6 (Hybrid Methods), no published method combines **agent-based reasoning + symbolic constraint validation** — the cell S4 occupies. (source: arXiv:2505.20099 §3.1-§3.4)

## Placement in Huang et al. 2024's five-direction LLM-agent planning taxonomy

[[understanding-planning-llm-agents-2024|Huang et al. 2024]] organise LLM-agent planning into five directions; S4 inhabits four of them simultaneously:

| Direction | S4 instance |
|---|---|
| Task Decomposition | Relation-path plan from [[reasoning-on-graphs|RoG]] (decomposition-first) + [[think-on-graph|ToG]] explore loop (interleaved) |
| External Planner-Aided | **LLM + [[shacl-validation|SHACL]]** — published precedents are LLM+P (PDDL), LLM+ASP (CLINGO); S4 inverts the direction (plan-then-validate) |
| Reflection & Refinement | SHACL **validate → self-correct** loop |
| Memory-Augmented | RAG-based KG memory via [[fuseki-triplestore]] + [[prov-o]] trace (no embodied/fine-tuned memory by RQ4 budget) |

**Multi-Plan Selection** is the one direction S4 currently does **not** use — generating top-K relation-path plans and ranking by ontology coverage is a clean RQ1 ablation candidate. (source: arXiv:2402.02716 §2-§7)

Huang §9 names "**connecting LLM with symbolic planning models without altering LLM itself**" as a promising future direction — a direct citation for S4's no-fine-tuning + symbolic-validator design. (source: arXiv:2402.02716 §9)

## Open questions for ingest

- Does prompt-only relation-path planning from a small manufacturing ontology actually match RoG's fine-tuned planner quality? The plug-and-play table suggests the planner does most of the work — flag for prompt-engineering experiments in Phase 4.
- What hybrid pattern does ToG 2.0 propose for joining KG and unstructured corpus retrieval?
- KG-Agent (Jiang et al. 2024, arXiv:2402.11163) is cited by RoG as the named "agent over KG" framework — not in `raw/` but worth chasing as a more direct S4 precedent.

## Related pages

- [[strategy-comparison]]
- [[langgraph-agent]]
- [[fuseki-triplestore]]
- [[shacl-validation]]
- [[prov-o]]
- [[reasoning-on-graphs]]
- [[think-on-graph]]
- [[think-on-graph-2]]
- [[graphrag-microsoft-2024]]
- [[unifying-llms-kgs]]
- [[prov-agent-souza2025]]
- [[understanding-planning-llm-agents-2024]]
- [[beyond-chain-of-thought-2024]]
- [[llms-meet-kgs-qa-survey-2025]]
