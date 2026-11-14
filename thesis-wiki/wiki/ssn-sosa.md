# SSN / SOSA Ontology

**Summary**: W3C Recommendation for describing sensors, observations, samples, and actuators. SSN/SOSA is the standards-based backbone for sensor and event modelling in the MFG-AgentGraph KG.

**Sources**: `thesis-pitch-v2.md` §2.3, §6 step 2; `raw/SOSA_SSN_Ontology_Sensors_2018.pdf` (**verified — see [[sosa-ssn-2018]]**); `raw/w3c-ssn-sosa-spec.md`. W3C spec text itself still [NEEDS VERIFICATION] but the journal article covers the normative content.

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ2 (ontology integration).

---

## What it is

- **SOSA** (Sensor, Observation, Sample, and Actuator) — a lightweight core vocabulary, **13 classes + 21 properties**, DL fragment `ALI(D)`.
- **SSN** (Semantic Sensor Network) — full module that imports SOSA and adds richer axioms for systems, deployments, and procedures (DL fragment `ALRIN(D)`).

Together, they form the W3C Recommendation (Oct 2017) and OGC Standard for sensor and observation modelling, jointly published by W3C + OGC's *Spatial Data on the Web* working group. Replaces the old SSN-XG's *Stimulus-Sensor-Observation* (SSO) core. (source: arXiv:1805.09979 §1, §6; thesis-pitch-v2.md §2.3)

**Three core perspectives** (verified after ingest of [[sosa-ssn-2018]]): observation, sampling, actuation — all sharing a common structure (`Activity → hasFeatureOfInterest → FeatureOfInterest`; `Activity usedProcedure Procedure`; `Activity hasResult Result`).

## Aligned with PROV-O — the load-bearing edge for S4

SOSA's core classes are direct subclasses of PROV-O classes (verified in [[sosa-ssn-2018]] §2, Fig. 2):

- `Sensor`, `Sampler`, `Actuator` ⊆ `prov:Agent`
- `Observation`, `Sampling`, `Actuation` ⊆ `prov:Activity`
- `Procedure` ⊆ `prov:Plan`
- `Result`, `FeatureOfInterest` ⊆ `prov:Entity`

This means the thesis's SOSA-typed sensor data composes cleanly with [[prov-agent-souza2025|PROV-AGENT]]'s `AgentTool`/`AIModelInvocation` activities — both are PROV-rooted, no awkward wrapping.

## Why this thesis uses it

- De facto standard for IoT sensor modelling in manufacturing KG research (cited via IIoTKG 2022 in the pitch). (source: thesis-pitch-v2.md §2.3)
- Provides typed `sosa:Observation`, `sosa:FeatureOfInterest`, `sosa:hosts`, `sosa:observedProperty` — the core terms used by the MIMII anomaly mapping.
- Peer-reviewed and W3C-standardised — directly defensible for a thesis arguing for a "standards-based" stack.

## Example mapping in MFG-AgentGraph

```
PumpStation_12      sosa:hosts            Pump_12 .
Pump_12             ex:lastMaintenance    "2026-01-15"^^xsd:date .
AnomalyEvent_1403   a                     sosa:Observation ;
                    sosa:observedProperty ex:SoundAnomaly ;
                    sosa:hasFeatureOfInterest Pump_12 .
```

[[shacl-validation|SHACL]] enforces: every `sosa:Observation` must link to a `sosa:FeatureOfInterest`. (source: thesis-pitch-v2.md §6 step 2)

## Recommended thesis adoption (resolved after ingest)

Per [[sosa-ssn-2018]]: adopt **SOSA core + PROV-O alignment module only**. Skip:

- **DUL** alignment (unnecessary heavy ontological commitment).
- **OBOE** alignment (ecology-focused).
- **O&M** alignment (only adopt if a reviewer demands OGC compliance — Janowicz et al. note `sosa:Observation ≡ om:Observation`, so the alignment is automatic if needed).
- **Full SSN module** (richer axioms but `ALRIN(D)` complexity — only needed for the *System Capabilities* horizontal module if RQ4 hardware modeling requires it).

This keeps the thesis's KG at DL fragment `ALI(D)` — efficiently handled by [[fuseki-triplestore|Fuseki]] without external DL reasoner overhead.

For controlled vocabularies of `ObservableProperty` (e.g., `acoustic_signature`, `vibration_frequency`), use SKOS-based code lists per the SOSA paper §2.2 — do *not* enumerate properties as OWL classes. (source: arXiv:1805.09979 §2.2, §3, §5.2)

## Reproducibility via `Procedure` — must model MIMII protocol

[[sosa-ssn-2018]] §2.1 makes `Procedure` the load-bearing class for *reproducibility*. The wind-speed example (10m for meteorology vs. 2m for agrometeorology) shows that procedure standardization is what makes observations comparable.

**For the thesis**: MIMII has a fixed recording protocol (16 kHz mono, 10s segments, anechoic chamber, microphone position). This *must* be modeled as a `sosa:Procedure` instance, and every MIMII `sosa:Observation` must `sosa:usedProcedure` it. SHACL shapes ([[shacl-validation]]) should enforce this — otherwise observations across MIMII machine variants (slider/valve/pump/fan) lose their cross-comparability. (source: arXiv:1805.09979 §2.1)

## Open questions for ingest

- How does SOSA align with **SAREF** (referenced in the literature index) for industrial settings? Janowicz et al. don't cite SAREF — likely complementary, not competing. Worth checking if SAREF coverage of pump/fan/motor classes saves modeling time.
- What are the W3C-recommended **SHACL shapes for SSN/SOSA validation**? Not in this paper — likely on the W3C SDW group's later notes. Phase 1 deliverable.
- The paper notes a **custom datatype `cdt:pressure`** which is "not yet recognized by current SPARQL engines" (§2.2). Verify Fuseki's current QUDT/UCUM support before adopting; if unsupported, the thesis must use plain `xsd:decimal` + an explicit `qudt:unit` triple.

## Related pages

- [[sosa-ssn-2018]]
- [[shacl-validation]]
- [[mimii-dataset]]
- [[kg-agent-s4]]
- [[fuseki-triplestore]]
- [[prov-o]]
- [[prov-agent-souza2025]]
