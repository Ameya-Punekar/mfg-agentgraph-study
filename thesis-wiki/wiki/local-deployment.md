# Local Deployment

**Summary**: All MFG-AgentGraph services run via Docker Compose on a factory's own hardware — no cloud, no external API calls. RQ4 evaluates whether this stack meets practical latency / memory targets on commodity hardware.

**Sources**: `thesis-pitch-v2.md` §1, §7, §9.2, §11, §14.

**Last updated**: 2026-05-04.

**Thesis relevance**: RQ4 (primary).

---

## Why local

Two motivations from §1 of the pitch:

1. **Data sovereignty** — sensor data, maintenance records, and SOPs are sensitive and often subject to factory data-handling policies.
2. **Reliability + latency** — internet outages and round-trip latency are unacceptable for shop-floor decision support.

(source: thesis-pitch-v2.md §1)

## What runs locally

| Component | Choices |
|---|---|
| LLM serving | Ollama (dev), llama.cpp (CPU-only), vLLM (GPU throughput) — swappable via env var |
| KG store | Apache Jena Fuseki ([[fuseki-triplestore]]) |
| Vector DB | Qdrant |
| Embeddings | HF sentence-transformers (`all-MiniLM-L6-v2` or `BAAI/bge-base-en-v1.5`) |
| API layer | FastAPI |
| Orchestration | Docker Compose (`docker-compose.cpu.yml` or `docker-compose.gpu.yml`) |

(source: thesis-pitch-v2.md §7)

## RQ4 metrics

- **Latency** — p50 / p95 response time (ms), measured via load testing.
- **Memory** — peak RAM and VRAM (GB), measured via `psutil` and `nvidia-smi`.

(source: thesis-pitch-v2.md §9.2)

## Hypothesis H5

S4 runs within a 30-second p95 latency on a consumer laptop (CPU-only, 16 GB RAM), confirming local viability. (source: thesis-pitch-v2.md §9.4)

## Empirical anchor: ToG with Llama2-70B competes with GPT-4 + CoT

[[think-on-graph]] (Sun et al. 2024, Table 2) shows the agentic-reasoning approach inherited by S4 lifts a small local LLM enough to compete with cloud LLMs:

- Llama2-70B-Chat + ToG: +18.5% on CWQ, +11.5% on WebQSP over CoT baseline.
- In some scenarios, **Llama2-70B + ToG > GPT-4 + CoT**.
- The gain *increases* with backbone size (Llama2-70B → ChatGPT → GPT-4: +18.5% → +20.1% → +23.5% on CWQ) — agentic reasoning amplifies the underlying LLM's capability rather than replacing it.

**Why this matters for RQ4**: the thesis can defensibly claim that a quantized local LLM in the 7B-70B range is *enough* for S4 to be useful, because the agentic loop and KG grounding do most of the heavy lifting. Cite directly when defending the local-deployment claim. (source: arXiv:2307.07697 Table 2, §3.2.2)

## Computational budget per S4 query (from ToG analysis)

Worst-case ToG LLM-call complexity is $2ND + D + 1$ per question (full ToG) or $ND + D + 1$ (ToG-R). With defaults $N=D=3$:

- Full ToG: max 22 LLM calls; observed average **8.7-14.3** on multi-hop datasets, **7.6-10.5** on slot-filling / fact-checking.
- ToG-R: max 13 LLM calls; observed average **~half** of ToG's call count.

For RQ4 with a 30s p95 budget and ~10 LLM calls per query, the per-call latency budget is ~**3s** — tight for a 70B model on CPU but reachable with quantized 7B-13B models on GPU or 4-bit GGUF on CPU. **Run ToG-R as the default in the local-deployment evaluation.** (source: arXiv:2307.07697 §B.2.1, Tables 7-8)

## Second empirical anchor: Llama-3.1-8b + AGENTiGraph ≥ GPT-4o zero-shot

[[agentigraph-2025|Zhao et al. CIKM 2025]] Table 2 reports that **Llama-3.1-8b** integrated with the AGENTiGraph multi-agent KG pipeline achieves classification accuracy **0.8356**, beating **GPT-4o zero-shot** (0.8334) on the TutorQA-3500 benchmark. On execution success, Llama-3.1-8b + agent (0.7230) is within ~5pp of GPT-4o zero-shot (0.7712). This generalises the [[think-on-graph|ToG]] finding (Llama-2-70B + ToG ≥ GPT-4 + CoT) to a **different LLM family, a different KG store, and a much smaller model size (8B not 70B)**.

For thesis defensibility under H5: the local-LLM viability claim now has **two independent empirical anchors** in published peer-reviewed work — ToG (ICLR 2024) and AGENTiGraph (CIKM 2025) — across different KG technologies. The 8B anchor is more aggressive and matches what a quantised local model would deliver on the consumer-laptop target. (source: arXiv:2508.02999 §4.2, Table 2)

## Pruning-tool optimization (efficiency lever from ToG)

[[think-on-graph]] Table 5 shows that replacing the LLM pruner with SentenceBERT cuts LLM calls from $2ND+D+1$ to $D+1$ (i.e., from ~22 to ~4 with $N=D=3$) but costs 7-15% accuracy. This is a candidate efficiency lever for S4 if local-LLM latency dominates the budget — at the cost of measurable accuracy loss to flag in the RQ4 chapter.

## Why single-agent: efficiency explosion (Chen et al. 2024)

[[multi-agent-systems-survey-2024b|Chen et al. 2024]] §6.2 names "efficiency explosion" as the headline practical-deployment challenge of LLM-MAS: each agent queries the LLM multiple times per action, and call counts compound across agents and rounds. Combined with the [[think-on-graph|ToG]] analysis above (~10 calls × 3 s ≈ 30 s p95 already), an n-agent debate or multi-stage pipeline puts MFG-AgentGraph over the 30 s budget on commodity hardware. **This is the cleanest published citation for the thesis's choice to stay single-agent.** (source: arXiv:2412.17481 §6.2)

The companion challenge — **accumulative effect** (errors compound across rounds) — also applies inside a single-agent self-refine loop, so cap SHACL-correction iteration count and report per-iteration faithfulness in the RQ1 evaluation. (source: arXiv:2412.17481 §6.2)

## Risk and mitigation

If local LLM is too slow for the 30 s p95 target: use quantised 4-bit GGUF models via llama.cpp; provide both CPU and GPU paths. Tested in Week 6. (source: thesis-pitch-v2.md §14)

## Open questions for ingest

- Latency budget breakdown across S4 stages (SPARQL vs. embedding vs. LLM vs. SHACL).
- Whether RAGAS LLM-as-judge can also run locally without quality collapse (relevant for fully-offline evaluation).
- Profile of `microsoft/graphrag` indexing cost — could it dominate local-deploy feasibility?

## Related pages

- [[mfg-agentgraph]]
- [[research-questions]]
- [[fuseki-triplestore]]
- [[langgraph-agent]]
- [[think-on-graph]]
- [[kg-agent-s4]]
- [[multi-agent-systems-survey-2024b]]
- [[agentigraph-2025]]
