# MIMII Dataset

**Summary**: Public dataset of industrial machine sounds (pumps, fans, sliders, valves) with both normal and anomalous conditions, recorded in real factory environments. The evaluation dataset for the thesis.

**Sources**: `thesis-pitch-v2.md` §9.3, §10. Dataset documentation [NEEDS VERIFICATION] until dataset README is added to `raw/`.

**Last updated**: 2026-04-26.

**Thesis relevance**: RQ1 (evaluation), RQ4.

---

## What it is

MIMII — Malfunctioning Industrial Machine Investigation and Inspection. A public dataset of real factory recordings covering pumps, fans, sliders, and valves in normal vs. anomalous operating conditions. (source: thesis-pitch-v2.md §9.3)

## Use in the thesis

- ETL scripts run an anomaly detector on MIMII signals and produce structured `sosa:Observation` events mapped onto [[ssn-sosa]]. (source: thesis-pitch-v2.md §6 step 1)
- These events populate the [[fuseki-triplestore|Fuseki KG]] alongside synthetic asset hierarchy and maintenance history.
- The primary evaluation scenario is [[anomaly-triage]] on a pump station ("PumpStation_12 produces an anomalous sound at 14:03"). (source: thesis-pitch-v2.md §10)
- 30 anomaly-triage queries (single-hop, multi-hop, counterfactual) are authored against this synthetic-KG-plus-MIMII setup. (source: thesis-pitch-v2.md §9.3)

## Open questions for ingest

- License of MIMII (relevant for open-source release).
- Whether the dataset README documents ground-truth labels suitable for direct anomaly mapping.
- How the synthetic asset hierarchy and maintenance history will be generated (already, the pitch says by the thesis author).

## Related pages

- [[anomaly-triage]]
- [[ssn-sosa]]
- [[strategy-comparison]]
