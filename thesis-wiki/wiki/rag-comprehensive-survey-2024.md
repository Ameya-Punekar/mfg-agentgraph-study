# RAG Comprehensive Survey (Gupta, Ranjan, Singh 2024)

**Summary**: A 2024 survey of Retrieval-Augmented Generation tracing its evolution from foundational concepts (BM25 / DPR / REALM / Lewis 2020) through current variants. Provides the working definition of "canonical RAG" used as the [[naive-rag|S1]] baseline in this thesis, and surfaces several recent variants that bear on the [[graphrag|S2]] and [[kg-agent-s4|S4]] design.

**Sources**: `RAG_Comprehensive_Survey_2024.pdf`. Authors: Gupta, Ranjan (Carnegie Mellon, USA); Singh (BIT Sindri, India). arXiv:2410.12837.

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (S1 baseline), RQ4 (challenges).

---

## Core architecture (working definition for S1)

RAG is a hybrid architecture introduced by Lewis et al. 2020 (NeurIPS) that integrates two components (source: RAG_Comprehensive_Survey_2024.pdf §1.2, §2.1):

1. **Retriever** — fetches relevant documents from an external corpus.
2. **Generator** — synthesises the retrieved content into a coherent answer.

Flow: `User Input → Retriever ↔ External Knowledge → Ranked Information → Generator → Output`. (source: RAG_Comprehensive_Survey_2024.pdf §1.2 fig. 2)

This is the canonical-RAG definition used in [[naive-rag|S1]].

## Retriever mechanisms

| Method | What it does | Citation |
|---|---|---|
| **BM25** | TF-IDF–based sparse keyword matching; strong baseline; struggles on semantically complex queries | Robertson 2009 |
| **DPR** (Dense Passage Retrieval) | Bi-encoder; query and document encoded into dense vectors; nearest-neighbour search; semantic match beyond keywords | Karpukhin et al. 2020 |
| **REALM** | Retrieval is *jointly trained* with the generator during pre-training | Guu et al. 2020 |
| **Cross-encoder re-ranking** | Re-ranks initial retrieval by jointly encoding query+doc; higher cost | (general technique) |

(source: RAG_Comprehensive_Survey_2024.pdf §2.2)

## Generator mechanisms

- **T5** (Raffel et al. 2020) — text-to-text framing; outperforms GPT-3/BART on Natural Questions and TriviaQA.
- **BART** (Lewis et al. 2020) — denoising autoencoder; strong for noisy-input generation.
- General trend: any modern LLM can serve as the generator. (source: RAG_Comprehensive_Survey_2024.pdf §2.3)

## Modalities (text-only is most mature)

The survey covers text, audio (Wav2Vec 2.0, Baevski 2020), video (I3D, TimeSformer), and multimodal (Flamingo, Alayrac 2022). For the thesis, only text-based RAG matters in baselines; sensor signals are converted upstream (anomaly detector → `sosa:Observation`) and never enter the LLM context as raw audio. (source: RAG_Comprehensive_Survey_2024.pdf §3)

## Recent variants surveyed (and what they mean for the thesis)

The survey's "Recent Trends in RAG" figure lists 17 variants (LA-RAG, HyPA-RAG, SFR-RAG, MemoRAG, Self-Route, NLLB-E5, RULE, METRAG, RAFT, MK Summary, CommunityKG-RAG, RAPTOR, FILCO, Self-RAG, RAGTruth, NoMIRACL, TRAQ, FABULA). The variants that matter most for this thesis:

| Variant | Why relevant |
|---|---|
| **CommunityKG-RAG** (Chang et al. 2024) | Zero-shot integration of *KG community structures* into RAG using multi-hop connections; close cousin to Microsoft [[graphrag|GraphRAG]]. Outperforms traditional methods without domain-specific training. (source: §4) |
| **RAPTOR** (Sarthi et al. 2024) | Hierarchical *summary tree* via recursive embedding/clustering/summarisation; alternative to GraphRAG community summaries; +20% on QuALITY with GPT-4. (source: §4) |
| **Self-RAG** (Asai et al. 2023) | Adaptive retrieval + *reflection tokens* to self-evaluate and refine output. Direct precedent for the S4 SHACL self-correction pattern. (source: §4) |
| **RAFT** (Zhang et al. 2024) | Retrieval-Augmented Fine-Tuning: trains models to *ignore distractor* documents and cite directly from relevant sources. Out of scope for this thesis (no fine-tuning), but the "ignore distractor" framing matters for SHACL contract design. (source: §4) |
| **METRAG** (Gan et al. 2024) | Multi-layered, *thoughts-enhanced* RAG with utility-oriented thoughts and a task-adaptive summariser. Pattern overlap with the S4 plan-retrieve-validate loop. (source: §4) |

## Challenges flagged by the survey (and where they map to RQs)

- **Scalability and efficiency** → [[research-questions|RQ4]]: high computational cost makes real-time / resource-constrained deployment hard. (source: §5)
- **Retrieval quality and relevance** → RQ1: irrelevant/outdated retrievals degrade output; especially hard for long-form generation. (source: §5)
- **Bias and fairness** → out of scope per [[thesis-pitch]] §13. (source: §5)
- **Coherence** → RQ1 RAGAS [[faithfulness]] metric directly addresses this. (source: §5)
- **Interpretability and transparency** → [[research-questions|RQ3]]: "RAG models are often treated as black boxes, with limited transparency in how retrieval influences generation." This is precisely the gap S4 with [[prov-o]] is meant to close. (source: §5)

## Future directions (per the survey)

- Multimodal integration, scaling, personalization, privacy, cross-lingual support.
- Most do not directly intersect with the thesis scope. The privacy/secure-data-handling thread aligns weakly with the data-sovereignty motivation behind [[local-deployment|RQ4]]. (source: §6)

## Notes / cautions

- **Taxonomy gap:** this survey does *not* present the popular "Naive RAG / Advanced RAG / Modular RAG" three-stage taxonomy. That formulation comes from Gao et al. 2023 (a different survey, not in `raw/` yet). The Gupta et al. survey is flatter and more variant-focused.
- **Manufacturing relevance is indirect:** the survey doesn't cover industrial / KG-grounded manufacturing. Use it for the S1 baseline definition and for landscape framing of RAG variants only.

## Wiki updates triggered by this source

- Refined [[naive-rag]] with the canonical retriever/generator decomposition and explicit Lewis 2020 attribution.
- Added a "related variants" note to [[graphrag]] for CommunityKG-RAG and RAPTOR.
- Added a "self-correction precedent" note to [[kg-agent-s4]] linking Self-RAG.
- Logged remaining open questions for the [[bm25-dpr|retriever]] choice in the S1 baseline implementation.

## Related pages

- [[naive-rag]]
- [[graphrag]]
- [[kg-agent-s4]]
- [[ragas-metrics]]
- [[research-questions]]
