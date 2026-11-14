# Unifying LLMs and KGs: A Roadmap (Pan et al. 2024)

**Summary**: Pan et al.'s *IEEE TKDE* roadmap paper that defines the **three-paradigm taxonomy** the thesis pitch builds on — KG-enhanced LLMs, LLM-augmented KGs, and Synergized LLMs + KGs. Provides the canonical placement of every strategy S1-S4 in the broader literature and supplies the yin-yang argument for *why* combining the two is needed in the first place.

**Sources**: `Unifying_LLMs_KGs_Roadmap_Pan2024.pdf` (arXiv:2306.08302v3, IEEE Trans. Knowledge & Data Engineering 2024 — Pan, Luo, Wang, Chen, Wang, Wu — Griffith / Monash / NTU / Beijing IT / Hefei UT).

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (paradigm placement of S1-S4), RQ2 (KG-enhanced LLM Inference + KGs Prompting are the relevant subcategories), RQ3 (KGs for hallucination detection & editing knowledge — §7.1, §7.2), RQ4 (LLMs as Agents Reasoning is the lightest-weight Synergized pattern, fits local deployment).

---

## The yin-yang motivation (Fig. 1)

The paper opens with a pros/cons summary that maps directly to the thesis's problem statement:

| | Pros | Cons |
|---|---|---|
| **LLMs** | General Knowledge, Language Processing, Generalizability | Implicit Knowledge, Hallucination, Indecisiveness, Black-box, Lacking Domain-specific/New Knowledge |
| **KGs** | Structural Knowledge, Accuracy, Decisiveness, Interpretability, Domain-specific Knowledge, Evolving Knowledge | Incompleteness, Lacking Language Understanding, Unseen Facts |

(source: Pan2024 §1, Fig. 1). MFG-AgentGraph's pitch (§1, §3) repeats this almost verbatim — LLMs for language, KGs for structural correctness in manufacturing — so this figure is the natural diagram to reference in the thesis introduction.

## The three paradigms (§3.1, Fig. 6)

1. **KG-enhanced LLMs**. KGs augment LLMs. Sub-categories (§4):
   - **Pre-training** — KGs in training objective, in inputs, or via instruction-tuning (e.g., OntoPrompt §4.1.3 — see below).
   - **Inference** — *Retrieval-Augmented Knowledge Fusion* (RAG itself!) and *KGs Prompting* (CoK chain-of-knowledge, Mindmap, ChatRule).
   - **Interpretability** — KGs for LLM probing (LAMA, LPAQA) and analysis (KagNet, QA-GNN).
2. **LLM-augmented KGs**. LLMs help build/maintain KGs. Sub-categories (§5): KG embedding, KG completion, KG construction (entity discovery, coreference, relation extraction), KG-to-text generation, KGQA.
3. **Synergized LLMs + KGs**. Bidirectional. Four-layer architecture (Data, Synergized Model, Technique, Application). Two reasoning patterns (§6.2):
   - **LLM-KG Fusion Reasoning** — joint encoders (KEPLER, JointGT, DRAGON, GreaseLM, JointLK, HKLM); heavy, end-to-end trained.
   - **LLMs as Agents Reasoning** — LLM iteratively interacts with KG via tools/search (**KD-CoT, KSL, StructGPT, ToG, RoG**); no fine-tuning required.

## How the thesis's S1-S4 map onto Pan's taxonomy

This is the most actionable use of the paper. Each row is a placement that should appear in the thesis related-work section.

| Thesis strategy | Pan paradigm | Pan sub-category | Cited cousin in Pan |
|---|---|---|---|
| [[naive-rag]] (S1) | KG-enhanced LLMs | Inference / Retrieval-Augmented Knowledge Fusion | RAG (Lewis 2020), REALM, RAG-2 |
| [[graphrag]] (S2) | KG-enhanced LLMs **+** LLM-augmented KGs | Inference / KGs Prompting **+** KG construction | (the LLM both builds the graph and uses it — straddles two paradigms) |
| [[og-rag]] (S3) | KG-enhanced LLMs | Pre-training / KGs Instruction-tuning **and** Inference / KGs Prompting | **OntoPrompt** (§4.1.3, ref [110]) — "ontology-enhanced prompt-tuning to place knowledge of entities into the context of LLMs" |
| [[kg-agent-s4]] (S4) | **Synergized LLMs + KGs** | **LLMs as Agents Reasoning** (§6.2) | **ToG, RoG, StructGPT, KSL, KD-CoT** (the exact bucket) |

The thesis-pitch-v2 §1 framing — *"paradigm 1 with elements of paradigm 3"* — means: S1, S2, S3 are paradigm-1 contributions evaluated as baselines, while S4 introduces a paradigm-3 (Synergized / Agents) component. Pan et al. validate this reading.

## Why "LLMs as Agents Reasoning" is the right S4 anchor

§6.2 explicitly contrasts the two Synergized patterns:

- **Fusion Reasoning** "may introduce extra parameters and computational costs while lacking interpretability" — disqualifying for RQ4 (local deployment) and RQ3 (operator trust).
- **Agents Reasoning** "provides a flexible framework for reasoning on KGs without additional training cost, which can be generalized to different LLMs and KGs. Meanwhile, the reasoning process is interpretable, which can be used to explain the results."

This sentence is essentially a thesis-justifying epigraph for [[kg-agent-s4]] — quote it directly when defending S4's design choices.

## OntoPrompt: the closest cited precedent for OG-RAG

§4.1.3 *KGs Instruction-tuning*: **OntoPrompt** (Ye et al. 2022, ref [110]) — *"ontology-enhanced prompt-tuning that can place knowledge of entities into the context of LLMs, which are further finetuned on several downstream tasks."* (source: Pan2024 §4.1.3)

This is the closest peer-reviewed work to [[og-rag]] cited in the roadmap. Worth chasing into `raw/` if the OG-RAG paper itself stays missing — OntoPrompt could either substitute as the S3 reference or stand alongside it.

## Future directions that justify thesis design choices

§7 lists six future directions; four directly underwrite MFG-AgentGraph design decisions:

- **§7.1 KGs for Hallucination Detection** — "combine LLMs and KGs to achieve a generalized fact-checking model that can detect hallucinations across domains." This is exactly what [[shacl-validation]] does at the structural level for S4. Cite this when defending the SHACL self-correction loop.
- **§7.2 KGs for Editing Knowledge in LLMs** — argues for KG-driven knowledge updates rather than re-training. Underwrites the local-LLM + Fuseki design where the *KG* is the editable knowledge layer, not the model.
- **§7.5 LLMs for Understanding KG Structure** — *"Conventional LLMs trained on plain text data are not designed to understand structured data like knowledge graphs ... it is necessary to develop LLMs that can directly understand the KG structure and reason over it."* This admits current LLMs are poor at raw graph reasoning, which **validates building an agent (tool-calling SPARQL) rather than expecting graph linearization to suffice**. Strongest defense of the LangGraph + SPARQL-tool design in [[langgraph-agent]].
- **§7.6 Synergized LLMs and KGs for Bidirectional Reasoning** — frames the Synergized paradigm as a "dual-driving wheel" for "knowledge-driven search" + "data/text-driven inference". Frames the S4 plan→retrieve→reason→validate loop in the paper's own language.

## The three-stage milestone roadmap (Fig. 26)

The paper proposes a chronological roadmap:

- **Stage 1**: KG-enhanced LLMs + LLM-augmented KGs (parallel single-direction tracks).
- **Stage 2**: Synergized LLMs + KGs.
- **Stage 3**: Graph Structure Understanding + Multi-modality + Knowledge Updating.

MFG-AgentGraph is a **Stage-2 system** (Synergized via Agents Reasoning) with explicit Stage-3 elements (Knowledge Updating via [[prov-o]]-tracked KG edits; the SHACL self-correction is also a primitive form of Stage-3 knowledge updating). This is the strongest single-sentence positioning of the thesis in the broader literature.

## Methods cited in Pan that are already in `raw/`

For cross-referencing future ingest of these papers:

- **RoG** (ref [112], Luo et al. 2023, "Reasoning on graphs") → ingested as [[reasoning-on-graphs]]. Pan places it under **KGs Instruction-tuning** §4.1.3 *and* **LLMs as Agents Reasoning** §6.2 — verified after full ingest: this dual placement is precise. RoG's *training* (KL divergence vs. shortest paths in KG, 38h on 2× A100) is paradigm-1; its *inference* pattern (plan→retrieve→reason) is paradigm-3. The thesis's S4 keeps only the paradigm-3 inference and replaces the paradigm-1 training with prompt engineering + ontology constraints.
- **Think-on-Graph (ToG)** (ref [240], Sun et al. 2023) → ingested as [[think-on-graph]]. Pure Agents-Reasoning approach (no fine-tuning component, unlike RoG). The §6.2 placement is exact: ToG introduces the "LLM ⊗ KG" tight-coupling paradigm where the LLM is an iterative agent over the KG via Search + Prune beam search. **Most direct S4 precedent of any paper in `raw/`.**
- **StructGPT** (ref [237]) → not in `raw/` but cited as a sibling Agents-Reasoning method.

Note that Pan's discussion of RoG and ToG is brief (a few sentences each); the per-paper ingests are still the primary sources for those methods.

## Methods Pan covers that are NOT in our raw/ but worth flagging

- **KEPLER** (ref [40]) — joint embedding + LM pre-training; canonical Fusion Reasoning example. Not directly comparable to S4 but useful to mention in related work.
- **OntoPrompt** (ref [110]) — see above; closest cited precedent to OG-RAG.
- **CoK** chain-of-knowledge prompting (ref [117]) — alternative to KG retrieval; useful contrast for naive RAG.
- **Mindmap** (ref [65]) — KG-as-mindmap prompting; another KG-prompting alternative.
- **OreoLM** (ref [177]), **GreaseLM** (ref [178]), **JointLK** (ref [245]), **DRAGON** (ref [44]) — Synergized Fusion Reasoning models; cite as the "heavier alternative path" the thesis explicitly avoids.

## What Pan does NOT cover (gaps relative to the thesis)

- **No PROV-O / provenance discussion**. Pan's framing of "interpretability" is about KG-aided LLM probing/analysis, not audit trails of agent actions. The thesis's [[prov-o]] contribution is *not* anticipated by Pan and is genuinely additive.
- **No SHACL / constraint-validation discussion**. Pan mentions KG completion (filling missing facts) but not validation of LLM-proposed facts against domain shapes. [[shacl-validation]] is also additive.
- **No SSN/SOSA / sensor-domain coverage**. The paper's domain-specific KG examples are medical/finance/genealogy. [[ssn-sosa]] for manufacturing sensors is a domain-novelty contribution.
- **No local-deployment / RQ4 angle**. All cited methods assume cloud LLMs. [[local-deployment]] is novel.

These four gaps map cleanly onto the thesis's RQ2/RQ3/RQ4 contributions — useful framing for the contributions section.

## Open questions raised by ingest

- Should the thesis adopt Pan's "Stage-2 Synergized" language explicitly, or stick with its own S1-S4 vocabulary? Recommendation: introduce Pan's three paradigms in the literature review chapter as the *external* taxonomy, then keep S1-S4 as *internal* method labels.
- OntoPrompt (Pan ref [110]) is the closest cited precedent for OG-RAG. Worth pulling the actual paper (Ye et al., WWW 2022) into `raw/` if OG-RAG itself stays missing.
- CoK chain-of-knowledge (Pan ref [117]) is a non-RAG, non-graph baseline that the thesis currently does not include — flag whether it should be a fifth comparator or remain out of scope.

## Related pages

- [[thesis-pitch]]
- [[research-questions]]
- [[strategy-comparison]]
- [[naive-rag]]
- [[graphrag]]
- [[og-rag]]
- [[kg-agent-s4]]
- [[shacl-validation]]
- [[prov-o]]
- [[langgraph-agent]]
- [[reasoning-on-graphs]]
- [[think-on-graph]]
