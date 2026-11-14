# Scenario corpus — v4 dataset card

**Contract**: `mfg-agentgraph-scenario-corpus-v1` (unchanged; releases add an optional
`provenance_profile` and optional per-record `derivation` and reading fields)
**Corpus ID**: `mimii-synthetic-context-v4`
**Version**: `v4`
**Release digest** (`sha256`): `218300e2b5b6515493f09e30b309d451d72b8b9b145a9949f6e5e4a6548e6d89`
**Development split digest**: `a8966fa9a30665fa19020351f2b883cf9e21f6e5b4bb0070c21809a613ad4af6`
**Supersedes**: `evaluation/scenario-corpus-v3/` (frozen and byte-identical)
**Description**: **MIMII-event-grounded synthetic-context** evaluation corpus

## What v4 changes, and what it deliberately does not

v3 reached 14,761 triples partly by repeating one observation 1,600 times: 1,608 of its 1,612
observations carried no reading, no time and no state. Those records account for 9,640 triples —
9,600 from the 1,600 nominal observations at six triples each, plus 40 from the eight sensorless
context observations at five each — and every one of them said nothing beyond "this identifier
exists". v4 keeps v3's evidence layer and authored layer unchanged and replaces only the observation
layer with a stated synthetic scenario timeline.

| Element | v3 | v4 |
|---|---|---|
| Documents (artifacts / families) | 49 / 48 | 49 / 48 (unchanged) |
| Source-located chunks | 528 | 528 (unchanged) |
| Assets / sensors | 8 / 64 | 8 / 64 (unchanged) |
| Observations | 1,612 | **1,604** (1,600 readings + 4 MIMII events) |
| Observations stating only an identifier | **1,608** | **0** |
| Readings with value + timestamp + state | 0 | **1,600** |
| Procedures / development queries | 4 / 10 | 4 / 10 (unchanged) |
| Triples | 14,761 | **19,521** |

Documents, chunks, assets, sensors, procedures and development queries are copied from the frozen
v3 release and checked against its digest, so a v4 build cannot rewrite the evidence layer. A
further consequence: the development digest differs from v3 because the release version is part of
the development-split document, not because a query changed.

## The scenario layer, in full

Every authored observation states four things: the asset it concerns, the **sensor** that made it
(which carries the unit), a numeric **value**, the scenario **instant**, and the **operating state**
the reading belongs to. Samples are hourly, `_SCENARIO_EPOCH = 2026-11-13T00:00:00Z` through
`2026-11-14T00:00:00Z`, twenty-five per sensor across eight properties on eight assets.

The generator is a pure function with no seed, so the canonical release JSON rebuilds
byte-identically. The TriG artifact is verified by graph isomorphism rather than byte equality,
because triple wire order is a serialiser detail, not a release property:

```text
value(property, state, index, asset) =
    round(baseline + swing * sin(2π · index / 24 + 0.35 · asset_index)
          + state_offset(state) + baseline * 0.02 * (asset_index mod 3), 3)
```

| Property | Unit | Baseline | Daily swing | Transient offset | Anomaly offset |
|---|---|---|---|---|---|
| `vibration` | mm/s | 2.4 | 0.3 | 1.1 | 3.2 |
| `acoustic_level` | dB | 68.0 | 2.0 | 6.0 | 14.0 |
| `discharge_pressure` | bar | 5.2 | 0.4 | 0.9 | 1.6 |
| `suction_pressure` | bar | 2.1 | 0.2 | 0.4 | 0.7 |
| `bearing_temperature` | degC | 52.0 | 3.0 | 8.0 | 15.0 |
| `motor_current` | A | 14.5 | 1.0 | 2.5 | 4.0 |
| `flow_rate` | m3/h | 36.0 | 3.0 | 6.0 | 9.0 |
| `speed` | rpm | 1480.0 | 12.0 | 25.0 | 40.0 |

`state_offset` is 0 for `baseline`, the transient offset for `transient`, the anomaly offset for
`anomaly`, and half the transient offset for `recovery`. Reading index 0–19 is `baseline`, 20 is
`transient`, 21–22 is the anomaly window, 23 is `transient` again, 24 is `recovery`.

**These numbers are fixtures.** They are chosen so a synthetic timeline is internally consistent.
They encode **no** manufacturer limit, **no** diagnostic threshold, **no** measured behaviour of any
real machine, and no inspection interval. The operating states are phases of a scenario, not
verdicts: `anomaly` means "the authored window in which the acoustic event is notionally placed", not
"this machine is faulty". Every record is `authored_curated` with `label_source: authored_context`,
so it can never be read as a MIMII measurement.

## Why MIMII events carry no value and no time

`doc`-level lineage already required a MIMII-derived observation to carry its recording identity and
the dataset label. v4 adds the converse rule in the record contract: a `mimii_derived` event may
declare **neither** `value` **nor** `observed_at`, because the dataset supplies an acoustic clip and
a label, not a scalar reading or a wall-clock time. Inventing either would fabricate evidence, and
`atq-201` was already narrowed in v3 for exactly this reason. The four recording-bearing events are
therefore the only observations without readings, and they are excluded from the identifier-only
count because their recording is a real, verifiable artifact.

## Where the triples come from

| Slice | Triples |
|---|---|
| The 1,600 readings, 9 each (type, sensor, asset, label, label source, lineage, value, timestamp, state) | 14,400 |
| The 4 MIMII events, 15 each (recording, dataset and provenance identity) | 60 |
| Documents, chunks, sensors, assets, procedures and queries | 5,061 |
| **Total** | **19,521** |

So the protocol's *order of 10^4–10^5 triples with multiple asset instances per machine type* clause
is now met by records that each state a reading — not by repetition. That is a **scale** statement
and nothing more: it does not establish topical breadth, industrial realism, decision quality or
Track A completeness. The 1,604 observations are synthetic telemetry over 8 assets; they are not
field data, and the corpus still holds no independent gold labels.

## Reproduction

```bash
uv run python scripts/build_scenario_corpus.py --version v4            # frozen v3 + scenario layer
uv run python scripts/build_scenario_corpus.py --version v4 --verify   # JSON bytes + TriG graph
uv run python scripts/build_scenario_corpus.py --version v3 --verify   # v3 must still reproduce 0c11ebe5…
uv run python scripts/build_scenario_corpus.py --version v2 --verify   # v2 must still reproduce 91f4894…
uv run mfg-agentgraph-corpus verify evaluation/scenario-corpus-v4/corpus-v4.json
uv run mfg-agentgraph-corpus load   evaluation/scenario-corpus-v4/corpus-v4.json
```

A v4 build refuses a v3 base whose canonical release digest differs from `_FROZEN_V3_DIGEST` —
the digest identifies release content, so reformatting the file does not change it and editing one
field does — refuses to write over a divergent v4 artifact, and refuses to publish a release whose
`identifier_only_observation_ids` is non-empty. `mfg-agentgraph-corpus verify` reports that count.

## Prohibited claims

- Any statement that this is MIMII maintenance decision support. MIMII supplies acoustic events only.
- That the readings are measurements, simulations of a real machine, calibration data, or evidence
  for any threshold, alarm setting, inspection interval or failure mode.
- Industrial decision quality, safety, operator trust or field effectiveness.
- Topical breadth beyond the four classes and the documents listed.
- "48 independent sources"; any held-out score before the blinded packet (issue #132) and
  independent annotation (issue #126) exist.
- That a triple count alone demonstrates domain richness.
- Any claim that the corpus is a complete re-publication of the source manuals.
