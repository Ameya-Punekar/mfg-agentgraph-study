# Faithfulness

**Summary**: One of the four core RAGAS metrics: the fraction of claims in the generated answer that are entailed by the retrieved context. The primary RQ1 metric for "does the system make things up?".

**Sources**: `thesis-pitch-v2.md` §2.4, §9.2; `raw/ragas-metrics-docs.md`. Definition [NEEDS VERIFICATION] until RAGAS docs are ingested.

**Last updated**: 2026-04-26.

**Thesis relevance**: RQ1.

---

## Definition (working)

Decompose the answer into atomic factual claims; for each claim, check whether the retrieved context entails it (LLM-as-judge); faithfulness = supported claims / total claims. [NEEDS VERIFICATION from `raw/ragas-metrics-docs.md`.]

## Use in the thesis

RAGAS faithfulness is the primary metric for RQ1's [[strategy-comparison|S1–S4 comparison]] and for hypothesis H1 (S4 > S1, S2, S3 on faithfulness). (source: thesis-pitch-v2.md §9.2, §9.4)

## Distinct from [[groundedness]]

- **Faithfulness** — answer claims supported by the *retrieved context* (text-level entailment, judged by an LLM).
- **Groundedness** — fraction of action items with at least one explicit KG edge or document citation (structural, not entailment-based).

The thesis tracks both because S1–S3 cannot produce structured `kg_edges`, so groundedness is a near-degenerate floor for them and only S4 can be high on it. RAGAS faithfulness is the apples-to-apples textual metric.

## Related pages

- [[ragas-metrics]]
- [[groundedness]]
- [[strategy-comparison]]
