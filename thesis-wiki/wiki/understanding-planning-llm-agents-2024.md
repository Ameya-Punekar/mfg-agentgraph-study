# Understanding the Planning of LLM Agents (Huang et al. 2024)

**Summary**: First systematic survey of LLM-Agent **planning** ability, organising the field into five directions (Task Decomposition / Multi-Plan Selection / External Planner-Aided / Reflection & Refinement / Memory-Augmented). Most thesis-relevant contribution: the **External Planner-Aided** category supplies the published precedent for combining LLM reasoning with deterministic symbolic validators — i.e. the LLM+SHACL pattern of [[kg-agent-s4|S4]].

**Sources**: `raw/Understanding_Planning_LLM_Agents_Survey_2024.pdf` (Huang, Liu, Chen, Wang, Wang, Lian, Wang, Tang, Chen — USTC + Huawei Noah's Ark Lab, arXiv:2402.02716v1, 5 Feb 2024).

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ1 (S4 mechanism positioning), RQ4 (LLM-call expense data).

---

## Five-direction taxonomy and mapping to S4

Huang et al. partition LLM-agent planning into five categories (Fig. 1, Table 1) — each interconnected, not mutually exclusive (source: arXiv:2402.02716 §2):

| Direction | Mechanism | S4 mapping |
|---|---|---|
| **Task Decomposition** | "Divide and conquer" — decompose goal into sub-goals, plan each. Decomposition-first (HuggingGPT, Plan-and-Solve, ProgPrompt) vs. interleaved (CoT, ReAct, PoT, PAL). | S4's relation-path plan from [[reasoning-on-graphs|RoG]] is decomposition-first; [[think-on-graph|ToG]]'s exploration loop is interleaved. |
| **Multi-Plan Selection** | Generate K candidate plans, search/vote (Self-Consistency, ToT, GoT, LLM-MCTS, RAP, LLM-A*). | **Not used in current S4**. Candidate extension: keep top-K relation-path plans and pick by ontology-coverage. |
| **External Planner-Aided** | LLM formalises task; symbolic planner produces plan (LLM+P, LLM+PDDL, LLM+ASP) or neural planner re-ranks (CALM, SwiftSage). | **Closest precedent for S4's LLM + SHACL pattern.** Replaces "PDDL plan synthesis" with "SHACL plan validation" — same statistical-AI-meets-symbolic-AI pattern. |
| **Reflection & Refinement** | Iterative generate-feedback-refine (Self-Refine, Reflexion, CRITIC, LEMA). | S4's SHACL **validate → self-correct** loop (already cross-mapped in [[multi-agent-systems-survey-2024b]] §3.1). |
| **Memory-Augmented** | RAG-based memory (Generative Agents, MemoryBank, MemGPT, REMEMBER) or embodied/fine-tuned memory (CALM, AgentTuning). | S4's [[fuseki-triplestore]] subgraph + [[prov-o]] trace = RAG-based KG memory. Fine-tuning-based memory is **not** thesis scope (RQ4 local-deploy budget). |

(source: arXiv:2402.02716 §3-§7, Table 1)

## The S4 framing: External Planner-Aided as the precedent for LLM + SHACL

§5 covers methods where the LLM "primarily plays a supportive role... parsing textual feedback and providing additional reasoning information to assist in planning." Symbolic planners cited: LLM+P (Liu et al. 2023a, PDDL/Fast-Downward), LLM-DP (Dagan et al. 2023, BFS solver), LLM+PDDL (Guan et al. 2023, LPG with manual verification), LLM+ASP (Yang et al. 2023b, CLINGO ASP solver).

§5.3 closes with the framing the thesis adopts:

> "The advantages brought by symbolic systems include theoretical completeness, stability, and interpretability. The combination of statistical AI with LLM is poised to become a major trend in the future development of artificial intelligence." (source: arXiv:2402.02716 §5.3)

**S4 is one instance of this trend**, swapping the roles:
- LLM+P / LLM+PDDL: LLM **formalises** the problem; symbolic planner **synthesises** the plan.
- **S4**: LLM **synthesises** the SPARQL plan and answer; symbolic engine ([[shacl-validation|SHACL]]) **validates** the plan and triggers regeneration.

This is the inverse direction of LLM+P — *plan-then-validate* rather than *formalise-then-plan* — but inhabits the same hybrid statistical/symbolic family Huang et al. identify as the major future direction. Cite §5.3 in the related-work chapter.

## §9 challenges that map to thesis hypotheses

| Challenge | Quote | Thesis hook |
|---|---|---|
| **Hallucinations** | "Plans may include actions that interact with items not existed in the environment." | RQ1 faithfulness metric; SHACL catches structural cases; semantic cases need RAGAS. |
| **Feasibility of generated plans** | "**Connecting LLM with symbolic planning models without altering LLM itself is a promising future direction.**" | **Direct citation supporting S4's no-fine-tuning, ontology-grounded design.** |
| **Efficiency of generated plans** | "Planning is greedily based on generated plans... without considering the efficiency of the generated plans." | RQ4 latency; not yet operationalised in thesis — possible RQ4 extension. |
| **Multi-Modal Environment Feedback** | "Real-world environment feedback is often multi-modal... challenging to describe in natural language." | MIMII is **already multi-modal** (audio); current thesis converts to text features. Worth flagging in limitations. |
| **Fine-grained Evaluation** | "Existing benchmarks mostly rely on the final completion status of tasks, lacking fine-grained step-wise evaluations." | **Validates the thesis's RAGAS + per-stage metric design** for RQ1. |

(source: arXiv:2402.02716 §9)

## Empirical: LLM-call expense scales with reflection (Table 2)

Table 2 (text-davinci-003 on AlfWorld / ScienceWorld / HotPotQA / FEVER) reports per-benchmark dollar cost:

| Method | AlfWorld $ | ScienceWorld $ | HotPotQA $ | FEVER $ |
|---|---|---|---|---|
| Fewshot-CoT | 98.60 | 272.22 | 5.73 | 2.25 |
| CoT-SC | 105.37 | 274.33 | 7.86 | 3.21 |
| ReAct | 152.18 | 356.03 | 66.00 | 22.20 |
| Reflexion | 220.17 | 724.48 | 112.49 | 37.26 |

(source: arXiv:2402.02716 Table 2)

**Pattern**: Reflexion ≈ 1.5-2× ReAct cost for ≈ +10-25% success-rate. The thesis's SHACL self-refine pattern should show a similar cost profile — local-deployment compute substitutes for the dollar cost, and the cost/quality trade-off feeds RQ4. Table 2 values are an external reference point for the thesis's own per-method LLM-call accounting.

## Memory taxonomy (§7) — confirms S4's RAG-based memory choice

Huang et al. split agent memory into:

- **RAG-based memory**: external store, retrieve at planning time. Forms include text (Generative Agents, MemGPT), vectors (MemoryBank, TiM), tabular (REMEMBER), and **knowledge graph** (cites [[unifying-llms-kgs|Pan et al. 2024]] explicitly as the KG-as-memory representative). (source: arXiv:2402.02716 §7.1)
- **Embodied memory**: fine-tune the LLM on agent trajectories (CALM, TDT, AgentTuning).

The thesis chooses RAG-based memory via [[fuseki-triplestore]] + [[prov-o]] trace — fine-tuning is excluded by [[local-deployment]] hardware budget. Huang et al.'s §7.3 trade-off ("RAG-based: real-time, low-cost external memory updates... but rely on accuracy of retrieval algorithm" vs. "Fine-tuning: larger memorisation capacity... high update cost, struggles with retaining fine-grained details") is the cleanest published justification for the thesis's choice.

## Pull-quotes worth saving

> "The combination of statistical AI with LLM is poised to become a major trend in the future development of artificial intelligence." (source: arXiv:2402.02716 §5.3)

> "Connecting LLM with symbolic planning models without altering LLM itself is a promising future direction." (source: arXiv:2402.02716 §9, "Feasibility")

> "Existing benchmarks mostly rely on the final completion status of tasks, lacking fine-grained step-wise evaluations." (source: arXiv:2402.02716 §9, "Fine-grained Evaluation")

## Open questions raised

1. **Multi-Plan Selection extension to S4**: should S4 generate top-K relation-path plans and pick the highest ontology-coverage one (analogue of ToT's tree-search)? Currently S4 follows a single ToG-style beam — a measurable RQ1 ablation.
2. **Embodied memory as RQ4 ablation**: parameter-efficient fine-tuning (LoRA/QLoRA) of the local LLM on past anomaly-triage trajectories could lift small-model performance, at the cost of reproducibility. Out of scope for the master thesis but worth noting.
3. **Multi-modal MIMII**: current thesis converts MIMII audio to textual features; Huang et al.'s §9 multi-modal challenge applies. Document as limitation.

## Related pages

- [[kg-agent-s4]] — five-direction taxonomy maps to S4 component-by-component
- [[shacl-validation]] — External Planner-Aided is the precedent paradigm
- [[multi-agent-systems-survey-2024b]] — Reflection & Refinement = self-refine in Chen et al.'s taxonomy
- [[unifying-llms-kgs]] — Huang et al. cite Pan et al. 2024 as the KG-as-memory representative
- [[think-on-graph]], [[reasoning-on-graphs]] — task-decomposition manner of S4 (interleaved + decomposition-first respectively)
- [[local-deployment]] — Table 2 expense data anchors the RQ4 cost comparison
