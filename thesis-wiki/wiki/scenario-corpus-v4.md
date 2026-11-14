# Scenario corpus v4

**Summary**: The current corpus release: v3's evidence layer and authored layer unchanged, with the
observation layer rebuilt so each of 1,600 authored records states a value in its sensor's unit, the
scenario instant and its operating state. It removes the 1,608 identifier-only observations that made
v3's triple count mostly repetition, raises the graph to 19,521 triples by adding information, and
keeps the four MIMII events as the only recording-bearing observations — carrying neither a value nor
a timestamp, because the dataset supplies neither.

**Sources**: `evaluation/scenario-corpus-v4/corpus-v4.json`, `corpus-v4.trig`, `dataset-card-v4.md`;
[[scenario-corpus-v3]]; [[scenario-corpus-v2]]; [[scenario-corpus-v1]]; `scripts/build_scenario_corpus.py`;
`src/mfg_agentgraph/corpus_release.py`; [[implementation-study-protocol-v1]]; GitHub issue #137.

**Last updated**: 2026-11-13.

**Thesis relevance**: RQ1 / RQ2 (RQ3 provenance and RQ4 local reproduction as prerequisites).

---

## Composition

| Element | Value |
|---|---|
| Documents | 49 artifacts / **48 families** (unchanged from v3) |
| Source-located chunks | 528 (unchanged) |
| Assets / sensors | 8 / 64 (unchanged) |
| Observations | **1,604** — 1,600 readings + 4 MIMII events |
| Observations stating only an identifier | **0** (v3: 1,608) |
| Procedures / development queries | 4 / 10 (unchanged) |
| Triples | **19,521** |
| Release digest | `218300e2…` |
| Development digest | `a8966fa9…` |

## What was broken

v3 reached 14,761 triples partly by repetition. 1,608 of its 1,612 observations carried an
identifier, an asset and a label and nothing else: no reading, no time, no state. Those records
account for **9,640** triples — 9,600 from the 1,600 nominal observations at six each, 40 from the
eight sensorless context observations at five each — and every one said only that an identifier
existed, so the frozen protocol's *order of 10^4–10^5 triples with multiple asset instances per
machine type* clause stayed unmet in any meaningful sense. The card recorded the shortfall; v4
removes the cause.

## The record contract

`CorpusObservation` gained three optional fields — `value`, `observed_at`, `operating_state` — with
validation that fails closed:

- a value must be a finite number **and** declare the sensor that made it, because the sensor
  carries the unit; a dimensionless number is not evidence;
- a value must declare its operating state, drawn from the closed vocabulary
  `baseline | transient | anomaly | recovery` — phases of a scenario, not diagnoses;
- a timestamp must be an unambiguous UTC instant, so records are orderable;
- a **MIMII-derived event may carry neither a value nor a timestamp**: the dataset supplies an
  acoustic clip and a label, and any scalar or wall-clock time would be fabricated;
- a reading must be made by a sensor hosted on the same asset, so a value cannot be attributed to
  the wrong machine;
- a release that states readings must publish `provenance_profile: complete`.

`ScenarioCorpus.identifier_only_observation_ids` reports the records that state nothing, and
`mfg-agentgraph-corpus verify` prints the count. The v4 build refuses to publish a release with a
non-empty list. The check is deliberately **not** in the contract: v1–v3 are frozen with 1,608 such
records and must keep loading.

## The scenario layer

Hourly samples from `2026-11-13T00:00:00Z` to `2026-11-14T00:00:00Z`, 25 per sensor across eight
properties on eight assets. The generator is a pure, seedless function of the declared profile,
reading index and asset position, so the canonical JSON rebuilds byte-identically; the TriG artifact
is verified by graph isomorphism, because triple wire order is a serialiser detail. Index 0–19 is
`baseline`, 20
`transient`, 21–22 the anomaly window, 23 `transient` again, 24 `recovery`.

**The numbers are fixtures.** They carry no manufacturer limit, no diagnostic threshold, no
inspection interval and no measured behaviour. `anomaly` means "the authored window in which the
acoustic event is notionally placed", never "this machine is faulty". The card lists the full
profile so the generator can be re-derived rather than trusted.

## Scale, stated precisely

| Slice | Triples |
|---|---|
| 1,600 readings × 9 predicates | 14,400 |
| 4 MIMII events × 15 predicates | 60 |
| Documents, chunks, sensors, assets, procedures, queries | 5,061 |
| **Total** | **19,521** |

The protocol's triple-order clause is met by records that each state a reading. That is a **scale**
statement and nothing more: it establishes no topical breadth, no industrial realism, no decision
quality, and no Track A completeness. The observations are synthetic telemetry over 8 assets, not
field data, and no independent gold labels exist yet.

## Reproducing it

```bash
uv run python scripts/build_scenario_corpus.py --version v4            # frozen v3 + scenario layer
uv run python scripts/build_scenario_corpus.py --version v4 --verify   # JSON bytes + TriG graph
uv run python scripts/build_scenario_corpus.py --version v3 --verify   # v3 must still reproduce 0c11ebe5…
uv run mfg-agentgraph-corpus verify evaluation/scenario-corpus-v4/corpus-v4.json
uv run mfg-agentgraph-corpus load   evaluation/scenario-corpus-v4/corpus-v4.json
```

A v4 build refuses a v3 base that is not byte-identical to `_FROZEN_V3_DIGEST` and refuses to write
over a divergent v4 artifact. The development digest differs from v3 because the release version is
part of the development-split document, not because a query changed.

## Prohibited claims

That the readings are measurements, simulations of a real machine, calibration data, or evidence for
any threshold, alarm setting, inspection interval or failure mode; industrial decision quality,
safety, operator trust or field effectiveness; topical breadth beyond the listed documents; "48
independent sources"; any held-out score before #132 and #126 exist; that a triple count alone
demonstrates domain richness; a complete re-publication of any manual.

## Related pages

- [[scenario-corpus-v3]]
- [[scenario-corpus-v2]]
- [[scenario-corpus-v1]]
- [[implementation-study-protocol-v1]]
- [[implementation-decisions]]
- [[mimii-dataset]]
- [[anomaly-triage]]
