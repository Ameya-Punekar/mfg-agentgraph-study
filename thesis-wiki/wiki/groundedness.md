# Groundedness

**Summary**: Thesis-defined construct: the percentage of action items in a response that include at least one explicit KG edge or document citation. Used alongside RAGAS [[faithfulness]] for RQ1.

**Sources**: `thesis-pitch-v2.md` §9.2.

**Last updated**: 2026-04-26.

**Thesis relevance**: RQ1.

---

## Definition

For each ranked action in a system response, count it as *grounded* if it includes a non-empty `kg_edges` list **or** a non-empty `doc_chunks` list. Groundedness = grounded actions / total actions. (source: thesis-pitch-v2.md §9.2 — "% actions with ≥1 KG edge or doc citation")

## Why it complements [[faithfulness]]

RAGAS faithfulness is text-level (does the answer follow from retrieved context, judged by LLM). Groundedness is structural — it asks whether the system *made the evidence visible at all*. S1–S3 can be high on faithfulness in principle, but only S4 can deliver structured `kg_edges`-level groundedness because the contract enforces it.

## How it interacts with the S4 hard contract

S4 enforces that every action *must* include a `kg_edges` list, and SHACL rejects plans without asset references. This is the design lever that pushes S4's groundedness toward 100% — the metric measures whether the contract held. (source: thesis-pitch-v2.md §10, §14)

## Relevance to RQ1 hypothesis H1

H1 predicts S4 > S1, S2, S3 on groundedness. Because S1 and S2 do not produce structured KG edges as part of their output protocol, groundedness will be low for them by construction; the *interesting* comparison is S3 vs. S4. (source: thesis-pitch-v2.md §9.4)

## Related pages

- [[faithfulness]]
- [[ragas-metrics]]
- [[kg-agent-s4]]
- [[strategy-comparison]]
