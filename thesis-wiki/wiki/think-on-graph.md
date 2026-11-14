# Think-on-Graph (ToG, Sun et al., ICLR 2024)

**Summary**: Sun et al.'s ICLR 2024 paper proposing the **"LLM ⊗ KG" tight-coupling paradigm** in which the LLM acts as an *agent that iteratively explores the KG via beam search* — Search + Prune over relations then entities, with the LLM as both planner and pruner — until reasoning paths are sufficient to answer. The most direct peer-reviewed precedent for [[kg-agent-s4]]. Pan 2024 cites ToG as the canonical *LLMs as Agents Reasoning* method.

**Sources**: `Think_on_Graph_Sun2023.pdf` (arXiv:2307.07697v6, ICLR 2024 — Sun, Xu, Tang, Wang (IDEA Research / Xiamen / USC / HKUST / Microsoft Research Asia), Lin, Gong, Ni, Shum, Guo). Code at `github.com/IDEA-FinAI/ToG` (MIT).

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ1 (S4 method-paper basis — *more* direct than [[reasoning-on-graphs]]), RQ2 (KG-grounded reasoning paths as faithfulness substrate), RQ3 (knowledge traceability and correctability — Fig. 4 is structurally the same problem [[shacl-validation]] + [[prov-o]] solve), RQ4 (training-free, plug-and-play across LLMs, makes Llama2-70B competitive with GPT-4).

---

## Problem framing — three reasoning paradigms (Fig. 1)

The paper introduces a clean three-way distinction:

- **(a) LLM-only** (Chain-of-Thought etc.) — fluent but hallucinates and lacks domain knowledge.
- **(b) LLM ⊕ KG** (loose coupling — KBQA via LLM-generated SPARQL, Naive RAG, classic retrieve-then-augment) — the LLM translates the question once, then the KG is queried; if the KG misses a relation, retrieval fails. This is what [[naive-rag]] and most retrieval-augmented setups do.
- **(c) LLM ⊗ KG** (tight coupling — *what ToG proposes*) — the LLM iteratively *thinks* on the graph: at each step it explores neighboring relations/entities, evaluates them, prunes, and decides whether enough information has been gathered. The LLM and KG complement each other dynamically.

(source: arXiv:2307.07697 §1, Fig. 1)

This figure is the cleanest visual summary of where S4 sits — **S4 inherits ToG's "⊗" paradigm and adds the ontology backbone, SHACL, and PROV-O**.

## The ToG inference loop (§2.1)

Three phases:

1. **Initialization** (§2.1.1) — LLM extracts the top-$N$ topic entities $E^0$ from the question.
2. **Exploration** (§2.1.2) — at depth $D$, the LLM extends the top-$N$ reasoning paths via:
   - **Relation Exploration**: *Search* the relations linked to current tail entities (formal SPARQL templates in Appendix E.1) → *Prune* via LLM-scored relevance, keeping top-$N$.
   - **Entity Exploration**: *Search* tail entities for the chosen relations → *Prune* via LLM-scored relevance.
3. **Reasoning** (§2.1.3) — LLM evaluates whether current paths suffice; if yes, generate answer; else continue to depth $D_\max$. If $D_\max$ reached without sufficiency, fall back to LLM's inherent knowledge.

Full algorithmic procedure in Appendix A (Algorithms 1 and 2). The whole loop needs **at most $2ND + D + 1$ LLM calls** (or $ND + D + 1$ for ToG-R).

(source: arXiv:2307.07697 §2.1, §A)

## ToG-R variant (relation-based, §2.2)

Skips entity-LLM-pruning by random-sampling tail entities (under the assumption that entities in each candidate set $E^D_{\text{cand},n}$ probably belong to the same class with similar neighbours, so pruning has little impact on subsequent relation exploration). Trade-off:

- **Reduces LLM calls**: $ND + D + 1$ instead of $2ND + D + 1$ — roughly half the cost.
- **Reduces accuracy slightly**: ToG generally beats ToG-R on triple-rich datasets (e.g., CWQ 58.8 vs. 57.1 with ChatGPT) because intermediate-entity literal information helps reasoning. ToG-R wins when relation-chain literal information dominates.

For S4: **ToG-R is the candidate optimization to consider when local-LLM call latency dominates the RQ4 budget.** (source: arXiv:2307.07697 §2.2, §A, Table 1)

## Pre-defined SPARQL queries (Appendix E.1) — directly reusable in S4

ToG uses two parameterizable SPARQL templates per primitive (incoming + outgoing variants) to delegate Search to the triplestore:

```sparql
# Relation Search (outgoing)
PREFIX ns: <http://rdf.freebase.com/ns/>
SELECT ?relation
WHERE { ns:mid ?relation ?x . }

# Relation Search (incoming)
PREFIX ns: <http://rdf.freebase.com/ns/>
SELECT ?relation
WHERE { ?x ?relation ns:mid . }

# Entity Search (outgoing)
PREFIX ns: <http://rdf.freebase.com/ns/>
SELECT ?tailEntity
WHERE { ns:mid ns:relation ?tailEntity . }

# Entity Search (incoming)
PREFIX ns: <http://rdf.freebase.com/ns/>
SELECT ?tailEntity
WHERE { ?tailEntity ns:mid ns:relation . }

# MID → Label
SELECT DISTINCT ?tailEntity WHERE {
  { ?entity ns:type.object.name ?tailEntity . FILTER(?entity = ns:mid) }
  UNION
  { ?entity owl:sameAs ?tailEntity . FILTER(?entity = ns:mid) }
}
```

For S4 against [[fuseki-triplestore]]: replace the Freebase prefix with the SSN/SOSA + manufacturing domain prefixes; the structural shape of the queries carries over verbatim. (source: arXiv:2307.07697 §E.1)

For Wikidata, ToG abstains from SPARQL and uses 9 pre-defined REST APIs (`label2qid`, `pid2label`, `get_all_relations_of_an_entity`, `get_tail_entities_given_head_and_relation`, etc., §E.2). These are equivalent in shape to the SPARQL versions.

## The five LLM prompts (Appendix E.3) — directly reusable

S4's [[langgraph-agent]] should adapt these almost verbatim, swapping the few-shot exemplars to manufacturing-domain examples:

**E.3.1 Relation Prune**:
```
Please retrieve k relations (separated by semicolons) that contribute
to the question and rate their contribution on a scale from 0 to 1
(the sum of the scores of k relations is 1).

In-Context Few-shot
Q: {Query}
Topic Entity: {Topic Entity}
Relations: {list of relations}
A:
```

**E.3.2 Entity Prune**:
```
Please score the entities' contribution to the question on a scale
from 0 to 1 (the sum of the scores of all entities is 1).

In-Context Few-shot
Q: {Query}
Relation: {Current Relation}
Entites: {list of entities}
Score:
```

**E.3.3 Reasoning (sufficiency check)**:
```
Given a question and the associated retrieved knowledge graph triples
(entity, relation, entity), you are asked to answer whether it's
sufficient for you to answer the question with these triples and your
knowledge (Yes or No).

In-Context Few-shot
Q: {Query}
Knowledge triples: {Explored Paths}
A:
```

**E.3.4 Generate**:
```
Given a question and the associated retrieved knowledge graph triples
(entity, relation, entity), you are asked to answer the question with
these triples and your own knowledge.
```

(source: arXiv:2307.07697 §E.3)

**Triple > Sequence > Sentence prompt format** (Table 4): triples are most efficient and best-performing in ToG. Sentences degrade ToG-R significantly because relation-only chains don't form natural sentences. **S4 should adopt the triple format** — `(entity, relation, entity)` rather than verbalized natural-language paths.

## Headline results

Across 9 KGQA / open-domain QA / slot-filling / fact-checking datasets, ToG with GPT-4 **beats fine-tuning-based SOTA on 6 of 9 datasets** despite being training-free. Excerpts from Table 1:

| Dataset | Prior FT SOTA | ToG (ChatGPT) | ToG (GPT-4) |
|---|---|---|---|
| CWQ | 70.4 | 57.1 | **69.5 (ToG-R)** |
| WebQSP | 82.1 | 76.2 | **82.6** |
| GrailQA | 75.4 | 68.7 | **81.4** |
| QALD10-en | 45.4 | 50.2 | **54.7 (ToG-R)** |
| Simple Q | 85.8 | 53.6 | 66.7 |
| WebQuestions | 56.3 | 54.5 | **57.9** |
| T-REx | 87.7 | 76.8 | 77.1 |
| Zero-Shot RE | 74.6 | 88.0 | 86.9 |
| Creak | 88.2 | 91.2 | **95.6** |

(source: arXiv:2307.07697 Table 1)

## Plug-and-play across LLMs (Table 2) — most thesis-relevant

ToG inherits the same plug-and-play property as RoG's planner but applies it to the *whole* loop, not just planning. Δ over CoT baseline:

| Backbone LLM | CWQ Δ | WebQSP Δ |
|---|---|---|
| Llama2-70B-Chat | +18.5% | +11.5% |
| ChatGPT | +20.1% | +14.0% |
| GPT-4 | +23.5% | +15.3% |

(source: arXiv:2307.07697 Table 2, §3.2.2)

**Two findings critical to the thesis**:

1. **The gain *increases* with backbone size** — bigger LLMs extract more value from ToG (more potential of KG can be mined with a more powerful LLM).
2. **Llama2-70B + ToG > GPT-4 + CoT in some scenarios** — implies a much cheaper deployment route. This is the empirical anchor for thesis-pitch §3 ("local-deployable, can compete with cloud LLMs"). Cite directly when defending [[local-deployment]].

## Plug-and-play across KGs (Table 3)

ToG works against both Freebase (88M entities) and Wikidata. Wikidata gives smaller gains than Freebase on CWQ/WebQSP because the test questions were constructed against Freebase (mismatched coverage), not because ToG is weaker on Wikidata structurally. **For the manufacturing setting**, this means S4's effectiveness will depend critically on KG coverage of the specific domain — flag for [[ssn-sosa]] + manufacturing ontology design. (source: arXiv:2307.07697 §3.2.3, Table 3)

## Search depth and width (Fig. 3) — tuning recommendations

- Performance grows with both depth and width up to ~3, then plateaus.
- Default $N=3, D_\max=3$ (max 22 LLM calls per question with full ToG; ~10 with ToG-R).
- Reasoning depth distribution (Fig. 12) shows most CWQ questions need 3-4 hops; most WebQSP need 2-3. Manufacturing KG queries (asset → component → fault → SOP) are likely to fit within $D=3$.

(source: arXiv:2307.07697 §3.2.3, Fig. 3, Fig. 12)

## Pruning tool ablation (Table 5) — efficiency lever

| Pruning model | CWQ | WebQSP | LLM calls |
|---|---|---|---|
| LLM (ChatGPT) | 58.8 | 76.2 | 2ND+D+1 (full) |
| BM25 | 51.4 (-7.4) | 58.7 (-17.5) | D+1 |
| SentenceBERT | 51.7 (-7.1) | 66.3 (-9.9) | D+1 |

(source: arXiv:2307.07697 Table 5, §3.2.3)

**For S4**: replacing LLM pruning with SentenceBERT cuts LLM calls from ~22 to 4 (D=3) but costs 7-15% accuracy. Whether this trade-off is favorable depends on local-LLM latency. The ablation also shows ToG-R + SentenceBERT and width 5 recovers some accuracy (66.3% → 68.5% on WebQSP) — practical recipe for the thesis.

## Knowledge traceability and correctability (§3.3, Fig. 4) — *the* RQ3 anchor

ToG's most thesis-relevant qualitative property: when the LLM emits an incorrect answer, the explicit reasoning paths can be traced back to the offending KG triple, the user can correct the KG, and the corrected KG immediately changes future ToG outputs. This is **bidirectional knowledge flow** — KG informs LLM at inference, LLM (via human) informs KG via correction. (source: arXiv:2307.07697 §3.3, Fig. 4)

**S4 inherits and *automates* this loop**:

| ToG mechanism | S4 mechanism |
|---|---|
| Human spots error → traces path → manually corrects triple | [[shacl-validation]] *automatically* rejects plans that violate domain shapes; agent self-corrects |
| Path traceability via LLM-printed reasoning chains | Triple-level traceability via [[prov-o]] activity records |
| KG-correction is manual | KG-correction is auditable (every PROV-O record names the activity, tools, sources) |

This is the cleanest framing of S4's contribution over ToG: **same loop, automated and audited.**

## Evidence-of-answers analysis (§B.2, Fig. 7) — strong faithfulness signal

For correctly-answered questions, where does the answer come from?

| Dataset | KG paths only | Both KG + LLM | LLM inherent only |
|---|---|---|---|
| CWQ | 60% | 13% | 27% |
| WebQSP | 72% | 3% | 25% |
| GrailQA | **93%** | 4% | 3% |

(source: arXiv:2307.07697 Fig. 7, §B.2)

**Most ToG correct answers genuinely come from the KG, not LLM hallucination decorated with paths.** This is the empirical evidence that the *agentic-reasoning* paradigm works as claimed. For the thesis, this validates the H1 framing that S4's KG-grounding does real work, not theatrical work.

## Path-overlap analysis (§B.2, Fig. 10) — manufacturing-relevant

For correctly-answered samples, how often do ToG's explored paths match the ground-truth SPARQL paths?

- On CWQ, ~25% of correct samples have **0 overlap** with the ground-truth path but still arrive at the correct answer.
- ~40% of CWQ correct samples have only partial (25-50%) overlap.
- Only ~14% have 100% overlap.

(source: arXiv:2307.07697 Fig. 10)

**Implication**: ToG explores *alternative reasoning paths*. This is robustness against KG incompleteness — useful in manufacturing KGs that won't have the full ground-truth structure. **S4 inherits this robustness automatically because it inherits ToG's exploration loop.**

## Comparison with naive beam search (§B.1, Table 6)

| Method | CWQ | WebQSP |
|---|---|---|
| Naive beam search (top-1 per depth) | 30.1 | 46.1 |
| **ToG (top-N reasoning paths)** | **58.8** | **76.2** |

Naive beam search accumulates calibration errors along the path; ToG's top-$N$ retention partially mitigates this. **For S4, this argues against a greedy single-path approach — keep the top-$N$ relation paths through the loop.**

## Placement in Pan 2024 taxonomy

[[unifying-llms-kgs|Pan 2024]] §6.2 cites ToG (ref [240]) as the canonical *LLMs as Agents Reasoning* method. Unlike [[reasoning-on-graphs|RoG]] (which spans §4.1.3 instruction-tuning + §6.2 agents reasoning), **ToG is purely a §6.2 method** — there is no fine-tuning component. This makes ToG a *cleaner* paradigm-3 anchor for S4 than RoG.

The thesis-defensibility argument: S4 = ToG + ontology + SHACL + PROV-O. Each addition is a concrete, peer-reviewed extension of the ToG loop. The literature-review structure should introduce ToG first as the agentic-reasoning paradigm, then position [[og-rag]] as adding the ontology backbone, [[shacl-validation]] as adding the constraint layer, and [[prov-o]] as adding the audit trail.

(source: Pan2024 §6.2, ref [240]; arXiv:2307.07697 §1)

## Limitations and gaps relative to S4

| ToG limitation | How S4 addresses it |
|---|---|
| Generic Freebase / Wikidata KG | Domain ontology ([[ssn-sosa]] + manufacturing shapes) — typed, smaller, more precise |
| No constraint validation | [[shacl-validation]] self-correction loop |
| Knowledge correction is manual (human spots error → corrects KG) | Automated via SHACL + agent self-correction; manual escalation only on shape failure |
| No provenance | Full [[prov-o]] activity record per agent run |
| Reasoning sufficiency = LLM judges Yes/No | Sufficiency = LLM-Yes **and** SHACL-pass; double gating |
| Generic KGQA evaluation (WebQSP, CWQ, etc.) | Manufacturing anomaly-triage 30-query set |
| Computational cost: 2ND+D+1 LLM calls (≈22 with N=D=3) | RQ4 budget: must verify ≤30s p95 with local LLM; consider ToG-R variant if too slow |

## Open questions for ingest

- Is the manufacturing KG large enough to make ToG's exploration meaningful, or so small that a single SPARQL CONSTRUCT query returns the full subgraph? Empirical question for Phase 4.
- Should S4 inherit ToG's $N=D=3$ defaults or tune for typical manufacturing query depth (asset→component→fault→SOP ≈ 3-4 hops)?
- Should the local-LLM deployment use ToG-R (cheaper) or full ToG (more accurate)? Run both as ablations within S4.
- How does ToG-style exploration interact with [[og-rag|S3]]'s ontology-hypergraph retrieval? Are they orthogonal (exploration over a constrained vocabulary) or competing approaches?

## Related pages

- [[kg-agent-s4]]
- [[reasoning-on-graphs]]
- [[think-on-graph-2]]
- [[unifying-llms-kgs]]
- [[shacl-validation]]
- [[prov-o]]
- [[fuseki-triplestore]]
- [[langgraph-agent]]
- [[strategy-comparison]]
- [[local-deployment]]
