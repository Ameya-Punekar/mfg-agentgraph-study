# Beyond Chain-of-Thought: Survey of Chain-of-X (Xia et al. 2024)

**Summary**: Generalises CoT to **Chain-of-X (CoX)** — a sequence of structured nodes `<input, X₁, …, Xₙ, output>` where X is any task-tailored component (intermediates, augmentations, feedback, models). Provides a two-axis taxonomy (nodes × tasks) that places **ToG**, ReAct, GraphCoT, Self-Refine, and Chain-of-Verification in a single design space — useful for positioning [[kg-agent-s4|S4]] alongside published CoX methods.

**Sources**: `raw/Beyond_Chain_of_Thought_Survey_2024.pdf` (Xia, Wang, Liu, Li, Yu, Chen, McAuley, Li — SJTU + UCSD + Duke + Adobe Research, arXiv:2404.15676v3, 5 Feb 2025).

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ1 (positions S4 in the broader CoX design space; identifies competing hallucination-reduction CoX methods).

---

## What CoX is

CoT prompts the LLM with `<input, thoughts, output>`; CoX generalises this to `<input, X₁, …, Xₙ, output>` where each Xᵢ is a problem-related component that compositionally contributes to or iteratively refines the solution (source: arXiv:2404.15676 §2). Xia et al. survey ~80 CoX papers and propose two taxonomies:

- **Taxonomy of nodes** (§3) — what kind of thing each Xᵢ is.
- **Taxonomy of tasks** (§4) — what the chain is applied to.

## Node taxonomy (§3) — where S4 fits

| Node family | Sub-types | Examples | S4 mapping |
|---|---|---|---|
| **Chain-of-Intermediates** (§3.1) | Problem decomposition / Knowledge composition | CoT, Least-to-Most, CoCode, CoTable, CoLogic, CoKnowledge, CueCoT, CoSpot | S4's [[reasoning-on-graphs\|RoG]]-style relation-path plan ≈ problem decomposition |
| **Chain-of-Augmentation** (§3.2) | Instructions / Histories / **Retrievals** / Tools / Others | CoQuery, CoNote, **ReAct**, Verify-and-Edit, IRCoT, **GraphCoT**, **ToG**, RAT, ChatCoT, MultiToolCoT, CoAbstraction | **S4's KG-retrieval loop sits here.** Table 1 lists ToG + GraphCoT as the two KG-based members of this family. |
| **Chain-of-Feedback** (§3.3) | External feedback / **Self-feedback** | Chain-of-3DThought, CoHindsight (ext); Self-Refine, Chain-of-Verification (CoVe), CoNLI, CoDensity, CoSelfRevisions, CoFeedback (self) | **S4's SHACL validate→self-correct loop sits in Self-feedback.** Third independent placement (after [[multi-agent-systems-survey-2024b\|Chen et al. §3.1]] and [[understanding-planning-llm-agents-2024\|Huang et al. §6]]). |
| **Chain-of-Models** (§3.4) | Multiple LLMs cooperating | CoExperts, ChatEval, CoDiscussion, CoLoRA | Out of scope (thesis is single-agent). |

(source: arXiv:2404.15676 §3, Fig. 2)

## Table 1 — S4's neighbours in Chain-of-Retrievals

Xia et al. compare 11 Chain-of-Retrievals methods on (Self-Generated Query, Adaptive Retrieval, Retrieval Verification, Knowledge Source). Reproduced with thesis annotations:

| Method | Self-Q | Adaptive | Verify | Source |
|---|---|---|---|---|
| Self-Ask | ✓ | – | – | Textual Corpus |
| ReAct | ✓ | ✓ | – | Textual Corpus |
| Verify-and-Edit | ✓ | ✓ | – | Textual Corpus |
| CoKnowledge | ✓ | ✓ | ✓ | Textual & Tabular |
| IRCoT | ✓ | – | – | Textual Corpus |
| CoQuery | ✓ | ✓ | – | Textual Corpus |
| CoAction | ✓ | ✓ | ✓ | Textual & Market |
| RAT | ✓ | – | – | Textual Corpus |
| **ToG** | ✓ | ✓ | ✓ | **Knowledge Graph** |
| **GraphCoT** | ✓ | ✓ | – | **Knowledge Graph** |

(source: arXiv:2404.15676 Table 1)

**Positioning of S4**: a **Knowledge-Graph** Chain-of-Retrievals method with all three properties (Self-Generated Query via SPARQL, Adaptive Retrieval via the SHACL feedback loop, Retrieval Verification via SHACL itself). In Xia et al.'s vocabulary, the closest neighbour is ToG, which S4 already inherits from (see [[think-on-graph]]). S4's distinguishing additions over Table 1's ToG row are: (a) ontology-grounded shape verification rather than LLM-judged sufficiency, and (b) PROV-O-recorded retrieval traces.

## Task taxonomy (§4) — Hallucination & Alignment is where S4's faithfulness story lives

§4.2 Factuality & Safety lists CoX methods specifically for **hallucination reduction**: CoNLI (Lei et al.), CoVerification (Dhuliawala et al.), KDCoT (Wang et al.), CoNote (Yu et al.), CoQuestion (Huang et al.), CoAction (Pan et al.). Two patterns:

1. **Step-wise verification + iterative refinement** (Self-Refine, CoNLI, Chain-of-Verification). S4's SHACL loop is the deterministic counterpart.
2. **Knowledge augmentation at each reasoning step** (CoNote, CoKnowledge, CoAction). S4's KG retrieval at each plan step is the ontology-grounded counterpart.

S4 combines both patterns. Cite §4.2 in the related-work chapter when defending the hallucination-reduction design choice. (source: arXiv:2404.15676 §4.2)

## §4.5 LLMs as Agents — CoX for agent planning

§4.5 places LLM-agent CoX methods (CoAction, CoActionThought, CoSummarization, Co3DThought, CoContacts, CoAbstraction, CoDiscussion) and remarks that "CoX in agents enhances the multi-dimensional abilities of LLMs as autonomous and collaborative agents." S4 is a CoAction-style chain (each Xᵢ is a tool-call action) augmented with self-feedback (SHACL). (source: arXiv:2404.15676 §4.5)

## §5 Future directions — where the thesis sits

Xia et al. flag five open challenges:

1. **Causal Analysis on Intermediates** — "LLMs may skip rational steps when generating final results... Wang et al. observe a performance gain from CoT even with invalid rationales." S4's PROV-O trace + SHACL gate is one structural answer (the chain *cannot* skip the validation step).
2. **Reducing Inference Cost** — "Future research may explore reducing the length of CoX chains." Aligns with the [[local-deployment]] / RQ4 budget concern; ToG-R + SHACL is the thesis's response.
3. **Knowledge Distillation** — out of thesis scope.
4. **End-to-End Fine-tuning** — "future research can explore fine-tuning LLMs with CoX prompting and penalising errors from the final output." Thesis explicitly **opts out** via the no-fine-tuning RQ4 argument; cite Xia §5 to acknowledge the alternative direction.

(source: arXiv:2404.15676 §5)

## Pull-quotes

> "We define CoX as a generalisation of the CoT method for diverse tasks beyond LLM reasoning. We refer to the X in CoX as the 'node' of the chain structure." (source: arXiv:2404.15676 §2)

> "Self-Refine first generates an initial response using an LLM and then uses the same LLM to provide feedback and refine its own response iteratively. Without any additional training, Self-Refine generates considerably better responses than direct generation." (source: arXiv:2404.15676 §3.3)

## Open questions raised

- **Multi-modal MIMII as Chain-of-X**: §4.1 Multi-Modal Interaction (Text-Image, Text-Speech) covers methods like CoModality / CoInformation that operate on raw audio. The thesis currently flattens MIMII to text features — could explore audio→CoX as a future-work extension. (Already noted in [[understanding-planning-llm-agents-2024]] §9 multi-modal challenge.)
- **Chain-of-Models as future direction**: §3.4 — if the thesis ever extends S4 to a planner+validator two-agent setup (per [[multi-agent-systems-survey-2024b]] open question), it would join the Chain-of-Models / CoExperts family.

## Related pages

- [[kg-agent-s4]] — S4 = Chain-of-Augmentation (KG retrievals) + Chain-of-Feedback (SHACL self-feedback)
- [[shacl-validation]] — Self-feedback node in CoX taxonomy; counterpart to Self-Refine / CoVe
- [[think-on-graph]] — ToG and GraphCoT are S4's only two KG-based Chain-of-Retrievals neighbours in Table 1
- [[multi-agent-systems-survey-2024b]] — independent placement of self-refine family
- [[understanding-planning-llm-agents-2024]] — independent placement of reflection/refinement family
- [[rag-comprehensive-survey-2024]] — broader RAG context; this CoX survey is the prompt-pattern complement
