# RAGAS Metrics

**Summary**: RAGAS is the de facto evaluation framework for RAG systems. It defines metrics across retrieval quality (context precision, context recall, noise sensitivity), generation quality (faithfulness, response relevancy), and extended metrics (Nvidia answer accuracy, context relevance, response groundedness). The thesis adopts RAGAS plus KG-specific metrics (Hits@Any, F1) and the [[llms-meet-kgs-qa-survey-2025|Ma et al.]] ReaQ dimension for RQ1.

**Sources**: `thesis-pitch-v2.md` §2.4, §9.2; `raw/ragas-metrics-docs.md` (verified — official RAGAS docs at docs.ragas.io).

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ1.

---

## What it is

RAGAS — Retrieval-Augmented Generation Assessment. A framework that evaluates RAG outputs along several axes using an LLM as judge. Supports evaluation of prompts, simple RAG systems, AI workflows, and AI agents. (source: ragas-metrics-docs.md; thesis-pitch-v2.md §2.4)

## Complete metric catalogue (verified from docs)

### RAG Metrics

| Metric | Category | What it measures |
|---|---|---|
| **Context Precision** | Retrieval | Are the retrieved contexts relevant? (precision of retrieval) |
| **Context Recall** | Retrieval | Was all needed information retrieved? (recall of retrieval) |
| **Context Entities Recall** | Retrieval | Were the right entities retrieved from context? |
| **Noise Sensitivity** | Retrieval | How sensitive is the system to irrelevant/noisy retrieved context? |
| **Response Relevancy** | Generation | Does the answer address the question? |
| **[[faithfulness]]** | Generation | Does the answer follow from the retrieved context? (no hallucinations) |

(source: ragas-metrics-docs.md — Available Metrics → Retrieval Augmented Generation section)

### Nvidia Metrics (Alternative Implementations)

| Metric | What it measures |
|---|---|
| **Answer Accuracy** | Factual correctness of the answer |
| **Context Relevance** | Relevance of retrieved context |
| **Response Groundedness** | Is the response grounded in provided context? (≈ [[groundedness]]) |

(source: ragas-metrics-docs.md — Nvidia Metrics section)

### Agent Evaluation Metrics

RAGAS also supports **agent evaluation** — directly applicable to the S4 [[langgraph-agent]] pipeline. The framework can evaluate AI workflows (multi-step pipelines) and AI agents (tool-using agents), not just simple RAG chains. This means the thesis can run RAGAS evaluation end-to-end on the full S4 agent loop, not just the final retrieval+generation step. (source: ragas-metrics-docs.md — Tutorials section: "Evaluate an AI Agent", "Evaluate an AI Workflow")

## Faithfulness computation

RAGAS computes faithfulness by decomposing the answer into atomic claims and asking an LLM whether each claim is supported by the retrieved context. Tradeoff: scalable, but introduces judge-model bias — usually mitigated by using a strong model (GPT-4 / Claude) as judge while the system under test uses a smaller local model. (source: ragas-metrics-docs.md — Faithfulness section)

## KG-specific extensions used in the thesis

- **Hits@Any, Hits@1, F1** for entity retrieval (cited as WhatBreaks 2025 in the pitch).
- **Multi-Hop Semantic Matching** (cited as KGRAGEval 2024).

(source: thesis-pitch-v2.md §2.4)

## AnsQ / RetQ / ReaQ augmentation

[[llms-meet-kgs-qa-survey-2025|Ma et al. 2025]] propose a three-dimensional evaluation framework that maps to and extends RAGAS:

| Dimension | RAGAS analogue | Thesis metric |
|---|---|---|
| **AnsQ** (Answer Quality) | faithfulness + response relevancy | Faithfulness, Hits@Any |
| **RetQ** (Retrieval Quality) | context precision + context recall | KG edge precision/recall |
| **ReaQ** (Reasoning Quality) | Not in RAGAS | **Novel**: per-step SHACL-pass rate, PROV-O path correctness |

ReaQ is the thesis-novel metric column: measure reasoning chain correctness via SHACL-validated intermediate step conformance. Cite Ma et al. §4.1 as the published basis. (source: arXiv:2505.20099 §4.1)

## Use in MFG-AgentGraph

The evaluation harness runs all four [[strategy-comparison|strategies]] over the same 30-query set against MIMII-grounded ground truth, logging RAGAS faithfulness, [[groundedness]], Hits@Any, and F1. (source: thesis-pitch-v2.md §9.2)

The pitch explicitly adopts RAGAS to "enable comparison against published baselines". (source: thesis-pitch-v2.md §2.4)

## Caveat raised by GraphRAG authors

Edge et al. 2024 (the [[graphrag-microsoft-2024|Microsoft GraphRAG paper]]) explicitly state that "context relevance, faithfulness, and answer relevance" — i.e., three of RAGAS's four core metrics — are **"not relevant to global sensemaking"** and design their own criteria (comprehensiveness, diversity, empowerment + control "directness"). (source: arXiv:2404.16130 §2.4)

**Implication for the thesis evaluation**: S2 ([[graphrag]]) is *optimized for criteria the thesis does not measure*. Two ways to handle this:

1. **Acknowledge in writeup**: report RAGAS results but note that S2's strength on global-sensemaking criteria isn't captured by faithfulness — frame the thesis as targeting *operational anomaly-triage QA*, where local-fact retrieval is the right task (not global sensemaking). This is well-aligned with [[anomaly-triage]] and the 30-query set's single-hop / multi-hop / counterfactual structure.
2. **Add a global-sensemaking sub-evaluation**: include a small set of "what are the recurring failure modes" style questions evaluated on Edge et al.'s criteria. Optional but strengthens the comparison.

## Open questions (resolved)

- ~~Exact RAGAS faithfulness formulation~~ → Atomic claim decomposition + LLM judge (resolved from docs)
- ~~Which judge model~~ → Configurable; default varies by version. Use GPT-4 as judge for thesis evaluation consistency.
- ~~Additional metrics~~ → Context Entities Recall, Noise Sensitivity, Nvidia Answer Accuracy confirmed (resolved from docs)

## Remaining open questions

- **Local LLM as RAGAS judge** (RQ4): can a quantized local model serve as judge without quality collapse? Critical for fully local evaluation pipeline.
- **Agent-mode RAGAS evaluation**: use the agent evaluation pathway for end-to-end S4 assessment — prototype during Phase 3.

## Related pages

- [[faithfulness]]
- [[groundedness]]
- [[strategy-comparison]]
- [[graphrag-microsoft-2024]]
- [[research-questions]]
- [[llms-meet-kgs-qa-survey-2025]]
- [[langgraph-agent]]
- [[references-master]]
