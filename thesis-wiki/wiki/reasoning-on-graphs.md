# Reasoning on Graphs (RoG, Luo et al., ICLR 2024)

**Summary**: Luo et al.'s ICLR 2024 paper proposing the **planning-retrieval-reasoning** framework: an instruction-fine-tuned LLM generates KG-grounded relation paths as faithful plans, a constrained-BFS retriever fetches concrete reasoning paths from the KG, and the same LLM reasons over those paths to produce answers with step-by-step explanations. The peer-reviewed basis for [[kg-agent-s4]]'s plan→retrieve→reason flow.

**Sources**: `Reasoning_on_Graphs_RoG_2024.pdf` (arXiv:2310.01061v2, ICLR 2024 — Luo, Li, Haffari (Monash), Pan (Griffith)).

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (S4 method-paper basis), RQ2 (relation paths as plans = a faithful-plan precedent for the SHACL-validated plan in S4), RQ4 (footprint analysis: RoG's 38-hour 2× A100 training is exactly what S4 must avoid).

---

## Problem framing

LLMs hallucinate during reasoning and lack up-to-date knowledge. KGs offer structured facts but most KG-aware LLM methods *"only treat KGs as factual knowledge bases and overlook the importance of their structural information for reasoning"* (Abstract). RoG argues that **relation paths** in KGs are themselves the reasoning structure and should be used as *plans* — not just as retrieval targets. (source: arXiv:2310.01061 §1, §4.1)

## The framework (Fig. 2)

Three modules, all driven by the same LLM:

1. **Planning module** — given a question $q$, the LLM generates the top-$K$ relation paths $z = \{r_1, r_2, \ldots, r_l\}$ (a sequence of relations like `marry_to → father_of`) that are "grounded by the KG", meaning every path corresponds to at least one valid traversal in $\mathcal{G}$. Generated as a structured sentence: `<PATH> r_1 <SEP> r_2 <SEP> ... <SEP> r_l </PATH>`. (source: arXiv:2310.01061 §4.3)
2. **Retrieval module** — given the relation path plan $z$ and the question entities $\mathcal{T}_q$, a constrained BFS over $\mathcal{G}$ returns all concrete reasoning paths $\mathcal{W}_z = \{w_z(e_q, e_*)\}$ that follow $z$ from a question entity. (source: arXiv:2310.01061 §4.4, Algorithm 1 in §A.3)
3. **Reasoning module** — the same LLM, given the question and the retrieved reasoning paths, produces the final answer plus an interpretable explanation. (source: arXiv:2310.01061 §4.4)

## Optimization (Eq. 7)

The two modules share weights and are jointly fine-tuned on two instruction-tuning tasks:

- **Planning optimization** (Eq. 4): KL divergence between LLM-generated relation paths and the *shortest paths in the KG between question and answer entities*. Effectively distills the KG structure into the LLM's output distribution. (source: arXiv:2310.01061 §4.2, Eq. 4)
- **Retrieval-reasoning optimization** (Eq. 6): FiD-style reasoning over K sampled plans, maximizing $\log P_\theta(a \mid q, \mathcal{Z}^*_K, \mathcal{G})$.

The combined loss (Eq. 7) is what the 38-hour fine-tuning optimizes.

## Implementation footprint

| Item | Value |
|---|---|
| Backbone LLM | LLaMA2-Chat-7B |
| Training datasets | WebQSP (2826 train) + CWQ (27,639 train) over Freebase (88M entities, 20K relations, 126M triples) |
| Instruction-tuning instance count | 216,006 planning + 30,465 retrieval-reasoning + 2,000 interpretability |
| Hardware | 2× A100-80GB GPU |
| Training time | **38 hours** (3 epochs, batch size 4, lr 2e-5, cosine warmup 0.03) |
| Inference plans | top-$K$=3 via beam search |
| Transfer footprint | 2 hours additional fine-tuning to MetaQA-3hop (Wiki-Movies) |

(source: arXiv:2310.01061 §A.6, §A.7.1, Table 13)

## Headline results

On the two KGQA benchmarks, RoG beats the prior SOTA (DECAF, semantic-parsing) by significant margins:

| Dataset | Method | Hits@1 | F1 |
|---|---|---|---|
| WebQSP (≤2-hop) | DECAF (DPR+FiD-3B) | 82.1 | 78.8 |
| WebQSP | **RoG** | **85.7** | 70.8 |
| CWQ (≤4-hop) | UniKGQA | 51.2 | 49.1 |
| CWQ | **RoG** | **62.6** | **56.2** |

(source: arXiv:2310.01061 Table 1)

The CWQ improvement (+22.3% Hits@1, +14.4% F1) is the strongest single result and demonstrates RoG's superiority specifically on multi-hop reasoning.

## Plug-and-play planning (§5.3, Table 3) — the most thesis-relevant finding

The frozen RoG planning module can be paired with an *unmodified* downstream LLM that only does the reasoning step. Hits@1 improvements over zero-shot baselines:

| LLM | WebQSP Δ | CWQ Δ |
|---|---|---|
| ChatGPT | 66.7 → 81.5 (**+14.8 = +8.5%**) | 39.9 → 52.7 (+12.8) |
| Alpaca-7B | 51.8 → 64.7 (+12.9) | 27.4 → 35.0 (+7.6) |
| LLaMA2-Chat-7B | 64.4 → 74.2 (+9.8) | 34.6 → 56.2 (+21.6) |
| Flan-T5-xl | 31.0 → 67.9 (**+36.9 = +119.3%**) | 14.7 → 37.8 (+23.1) |

(source: arXiv:2310.01061 Table 3, §5.3)

**Why this matters for S4**: it shows the *planning module's value can be inherited without inheriting the reasoning module's fine-tuning*. S4 must replicate the planning behavior without RoG's 38-hour training step.

## Ablation findings

- **w/o planning** drops F1 from 70.81 to 49.56 on WebQSP (degenerates to vanilla LLM).
- **w/o reasoning** drops Hits@1 to 50.16 on WebQSP — even with KG paths retrieved, raw majority voting under-performs LLM-mediated reasoning.
- **Random plans** (skip the planning module's KG grounding, retrieve random paths) drops F1 to 35.24 on WebQSP — confirms that KG-grounded plans are doing real work, not just providing noise reduction.

(source: arXiv:2310.01061 Table 2)

## How S4 adapts RoG without fine-tuning

The core insight to inherit: *plans should be expressed as KG-grounded relation paths, not as free-text plans*. S4's adaptation strategy (per [[kg-agent-s4]] and [[thesis-pitch]] §5.5):

| RoG component | RoG implementation | S4 adaptation |
|---|---|---|
| Plan generation | Fine-tune LLM on shortest-path supervision | **Prompt** local LLM with the **ontology vocabulary** ([[ssn-sosa]] + domain shapes) as context — relation choices are constrained by the schema, not learned |
| Path retrieval | Constrained BFS in Python (Algorithm 1) | **Parameterized SPARQL query** against [[fuseki-triplestore]] — the BFS is delegated to the SPARQL engine |
| Reasoning | Fine-tuned LLM with FiD-style aggregation | Same local LLM with retrieved paths in the prompt context (no FiD) |
| Explanation | Few-shot prompt for interpretable output | Path + [[shacl-validation]] report + [[prov-o]] record |
| Faithfulness check | Path existence in KG (implicit) | Path existence **plus SHACL shape validation** — explicit constraint check |

This adaptation is what lets S4 inherit RoG's plan-as-relation-path idea while staying compatible with **RQ4** (local deployment, no fine-tuning of a large model) and improving **RQ2** (faithfulness) via SHACL.

## Algorithm 1 — Constrained BFS retrieval (§A.3, directly translatable to SPARQL)

```
Input: question q, relation path z = {r_1, ..., r_l}, KG G
Output: reasoning paths W_z

W_z ← {}
Q ← Queue()
for each e_q in T_q:                         # initialize with question entities
    Q.append((e_q, []))
while Q not empty:
    (s, w_z) ← Q.pop()
    if len(w_z) == len(z):
        W_z.append(w_z)                      # path complete
    else:
        r ← z[len(w_z) + 1]                  # next relation
        for each (s, r', t) in G:
            if r' == r:
                w'_z.append((s, r', t))
                Q.append((t, w'_z))           # extend path
return W_z
```

(source: arXiv:2310.01061 §A.3, Algorithm 1)

For S4, this is replaced by a templated SPARQL query against Fuseki — same algorithmic shape, executed by the triplestore for efficiency.

## Prompts (§A.10) — directly reusable in S4

**Planning prompt** (verbatim adaptable):

```
Please generate a valid relation path that can be helpful
for answering the following question: <Question>
```

**Reasoning prompt** (verbatim adaptable):

```
Based on the reasoning paths, please answer the given question.
Please keep the answer as simple as possible and return all the
possible answers as a list.

Reasoning Paths:
<Reasoning Paths>     # formatted as e_0 → r_1 → e_1 → ... → r_l → e_l

Question:
<Question>
```

**Explanation prompt** (used for the interpretability sub-task with few-shot examples):

```
Based on the reasoning paths, please answer the given question
and explain why.

Here are some examples:
<Examples>

Reasoning Paths: <Reasoning Paths>
Question: <Question>
```

S4 should adopt these prompts almost verbatim, adding the SHACL report as additional context to the reasoning prompt and constraining the planning prompt with the SSN/SOSA relation vocabulary.

## Placement in Pan 2024 taxonomy

Pan et al. 2024 cites RoG twice ([[unifying-llms-kgs]]):

- **§4.1.3 KGs Instruction-tuning** — because RoG fine-tunes on KG-derived shortest-path supervision.
- **§6.2 LLMs as Agents Reasoning** — because at inference, RoG iteratively plans-then-retrieves, treating the LLM as a graph-interacting agent.

This dual placement is faithful to the paper: RoG's *training* is paradigm-1 (KG-enhanced LLM via instruction-tuning), while its *inference* pattern is paradigm-3 (Synergized / Agents). **S4 keeps only the paradigm-3 inference pattern and replaces the paradigm-1 training with prompt engineering + ontology constraints.** This is the most precise way to position S4 vs. RoG in the related-work chapter. (source: Pan2024 §4.1.3, §6.2; arXiv:2310.01061 §1)

## Limitations and gaps relative to S4

| RoG limitation | How S4 addresses it |
|---|---|
| 38-hour fine-tuning on 2× A100 | Prompt-only — no fine-tuning of any model |
| Fine-tuned to *Freebase* relation vocabulary | Schema-driven via SSN/SOSA + domain ontology — relation set is explicit and small |
| Faithfulness = path exists in KG | Faithfulness = path exists **and** satisfies SHACL shapes |
| No provenance | Full PROV-O activity record |
| Self-consistency only via top-K beam search | SHACL self-correction loop with re-planning on failure |
| Generic encyclopedia QA (WebQSP, CWQ) | Anomaly-triage (PumpStation_12 case) — much smaller, more typed KG |

## Open questions for ingest

- Does prompt-only generation of valid relation paths from a small ontology actually work as well as RoG's fine-tuned planner on a manufacturing KG? Evidence from the plug-and-play table (Flan-T5-xl gained 119% from RoG planning) suggests a *specialized* planner does most of the work — risk for S4 that needs prompt engineering experiments to validate.
- Should S4 inherit RoG's $K=3$ default for top-$K$ plans, or tune for the manufacturing setting?
- KG-Agent (Jiang et al. 2024, arXiv:2402.11163) is cited by RoG (§A.2.1) as the named "agent" framework over KGs — not in `raw/` but worth pulling in if a more direct S4 precedent is needed.

## Related pages

- [[kg-agent-s4]]
- [[think-on-graph]]
- [[think-on-graph-2]]
- [[unifying-llms-kgs]]
- [[shacl-validation]]
- [[fuseki-triplestore]]
- [[langgraph-agent]]
- [[strategy-comparison]]
