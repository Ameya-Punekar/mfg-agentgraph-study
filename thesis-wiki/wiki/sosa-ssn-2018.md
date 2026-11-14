# SOSA: A Lightweight Ontology for Sensors, Observations, Samples, and Actuators (Janowicz et al. 2018)

**Summary**: Janowicz et al.'s journal article describing **SOSA**, the lightweight core ontology of the W3C/OGC Semantic Sensor Network (SSN) family. Defines 13 classes and 21 properties for representing sensors, observations, samples, actuators, procedures, and the activities that connect them — all directly aligned with W3C PROV-O. The peer-reviewed reference for [[ssn-sosa]] and the load-bearing standard for the thesis's manufacturing ontology backbone.

**Sources**: `SOSA_SSN_Ontology_Sensors_2018.pdf` (arXiv:1805.09979v2, *Web Semantics: Science, Services and Agents on the World Wide Web*, Dec 2018 — Janowicz, Haller, Cox, Le Phuoc, Lefrançois — UC Santa Barbara / ANU / CSIRO / TU Berlin / Mines Saint-Étienne). Normative spec: <https://www.w3.org/TR/vocab-ssn/> (W3C Recommendation, OGC Standard, 19 Oct 2017).

**Last updated**: 2026-04-27.

**Thesis relevance**: RQ2 (primary — the SSN/SOSA backbone is the *expert ontology* that distinguishes [[og-rag|S3]] and [[kg-agent-s4|S4]] from [[graphrag|S2]]'s LLM-built graph; H2 ontology hypothesis), RQ3 (PROV-O alignment composes with [[prov-agent-souza2025|PROV-AGENT]]), RQ4 (lightweight `ALI(D)` DL fragment fits local triplestore deployment).

---

## What SOSA is

A formal but **lightweight** general-purpose ontology for modeling the interaction between entities involved in **observation, actuation, and sampling**. Joint product of W3C and OGC's "Spatial Data on the Web" working group, published as a W3C Recommendation and OGC Standard in October 2017. Replaces the old SSN-XG's *Stimulus-Sensor-Observation* (SSO) core pattern. (source: arXiv:1805.09979 §1, §6)

Three core perspectives, all sharing a common structure:

1. **Observation perspective** — sensors produce observations of properties of features of interest.
2. **Sampling perspective** — samplers produce samples (which are themselves features of interest) representative of larger features.
3. **Actuation perspective** — actuators carry out actuations that change the state of actuatable properties of features of interest.

(source: arXiv:1805.09979 §2, Fig. 2)

## The 13 SOSA classes

| Class | Role |
|---|---|
| `Sensor` | A device, software, simulation, or person that responds to stimuli to produce observations |
| `Observation` | The act of carrying out an observation procedure to estimate a property's value |
| `ObservableProperty` | The property being observed (e.g., temperature, vibration frequency) |
| `Result` | The output of an observation/actuation/sampling — typed via `hasResult` (object) or `hasSimpleResult` (literal) |
| `FeatureOfInterest` | The entity whose property is being observed/sampled/actuated |
| `Procedure` | A workflow/protocol/algorithm specifying *how* to carry out an observation, sample, or actuation — the reproducibility anchor |
| `Sample` | An object representative of a larger feature; *both* a `Result` of `Sampling` *and* a `FeatureOfInterest` for further observation |
| `Sampler` | A device/software/agent that creates samples |
| `Sampling` | The act of creating a sample |
| `Actuator` | A device/software/agent that changes the state of the world |
| `Actuation` | The act of an actuator changing a property |
| `ActuatableProperty` | The property being changed (typically also an `ObservableProperty` so the loop closes) |
| `Platform` | An entity that hosts sensors/samplers/actuators (can host other platforms) |

(source: arXiv:1805.09979 §2.1-2.4, §6)

## The 21 SOSA properties

`hasResult`, `hasSimpleResult`, `isResultOf`, `hasFeatureOfInterest`, `isFeatureOfInterestOf`, `observedProperty`, `observes`, `isObservedBy`, `madeBySensor`, `madeObservation`, `madeSampling`, `madeActuation`, `madeBySampler`, `madeByActuator`, `hosts`, `isHostedBy`, `isSampleOf`, `hasSample`, `usedProcedure`, `phenomenonTime`, `resultTime`, `actsOnProperty`, `isActedOnBy`.

The Sensor/Platform graph schema diagrammed in Fig. 3 shows how they wire together. `phenomenonTime` is an object property using OWL-Time (interval or instant); `resultTime` is a datatype property (`xsd:dateTime`).

## Direct PROV-O alignment — the thesis's load-bearing edge

**This is the most important content in the paper for the thesis.** SOSA's core structure (Fig. 2) maps each class onto a PROV-O class:

| SOSA class | PROV-O alignment |
|---|---|
| `Sensor` | `prov:Agent` |
| `Sampler` | `prov:Agent` |
| `Actuator` | `prov:Agent` |
| `Observation` | `prov:Activity` |
| `Sampling` | `prov:Activity` |
| `Actuation` | `prov:Activity` |
| `Procedure` | `prov:Plan` |
| `Result` | `prov:Entity` |
| `FeatureOfInterest` | `prov:Entity` |

(source: arXiv:1805.09979 §2, Fig. 2)

**Compositional implication for S4**: every `sosa:Observation` is *automatically* a `prov:Activity`, which means [[prov-agent-souza2025|PROV-AGENT]]'s `AgentTool` (a subclass of `prov:Activity`) can declare `wasInformedBy` an `Observation` directly. The thesis's ontology stack composes as:

```
prov:Activity ←⊆ AgentTool (PROV-AGENT) ←⊆ AIModelInvocation (PROV-AGENT)
prov:Activity ←⊆ sosa:Observation ←⊆ MIMIIObservation (thesis subclass)
prov:Entity ←⊆ sosa:FeatureOfInterest ←⊆ PumpStation (thesis subclass)
prov:Entity ←⊆ DataObject (PROV-AGENT) ←⊆ DomainData (PROV-AGENT) ←⊆ sosa:Result
```

No conflicts, no awkward wrapping — the ontologies fit together cleanly because both are PROV-rooted.

## Aligned with OGC Observations and Measurements (O&M)

§3: `sosa:Observation ≡ om:Observation`, and `om:Process ≡ sosa:Sensor ⊔ ObservationProcedure`. This means the thesis's SSN/SOSA ontology is automatically interoperable with industrial OGC sensor-data standards already deployed in factories — *useful framing if a thesis reviewer asks "why not just use O&M?"* The answer: SOSA *is* O&M, in RDF with PROV alignment.

`sosa:Observation` is also a *superclass* of `oboe:Measurement` (Ecological Informatics) — relevant for cross-domain reuse. (source: arXiv:1805.09979 §3)

## Modular architecture (Fig. 1) — pick exactly what you need

SOSA is the core. Around it are **horizontal modules** (broaden scope) and **vertical alignment modules** (add depth):

- **Horizontal**: System Capabilities (battery, throughput — relevant for [[local-deployment|RQ4]] when modeling the deployment platform itself), Sample Relations.
- **Vertical alignments**: DUL, PROV-O, O&M, OBOE, SSNX (legacy SSN bridge).
- **Top**: full SSN module (richer axioms — `ALRIN(D)`).

**Thesis recommendation**: adopt SOSA core + PROV-O alignment module *only*. Skip DUL (unnecessary ontological commitment), skip OBOE (ecology-focused), use O&M alignment only if a reviewer demands OGC compliance. This keeps the DL fragment at `ALI(D)` — efficiently handled by Fuseki without DL reasoner overhead. (source: arXiv:1805.09979 §1, §3)

## Key design decisions

1. **Event-centric** (§2). Observations are *activities in the world*, not records-of-context as in the old SSO pattern. This is what makes the PROV alignment trivial. Aligns with Schema.org's `Action` class and standardized business process models.
2. **No disjointness declarations** (§2). Sensors can themselves be `FeatureOfInterest` (eye-exam example: an ophthalmologist's instruments observe the patient's eye, but the eye is itself observed by the surgeon). Useful for manufacturing where the same pump is the FoI of an acoustic sensor and also the FoI of a vibration sensor.
3. **Schema.org-style domain/range** (§2). Uses `domainIncludes`/`rangeIncludes` annotation properties (informal semantics) instead of RDFS `domain`/`range` (inferential). Lighter for triplestore use.
4. **No explicit geometry** — delegated to GeoSPARQL.
5. **No collection class** — uses terminological axioms (subclass with `∃madeBySensor.{Sensor1}`) instead, §5.1.
6. **Singletons for properties** — `ObservableProperty` instances (e.g., `<NitrateConcentration>`) are *singletons* used across many observations; recommend pulling from controlled vocabularies (SKOS-based code lists like SeaDataNet's SDN:P01).
7. **OWL-Time for `phenomenonTime`** — first-class temporal modeling.

(source: arXiv:1805.09979 §2.1-2.4, §5)

## What SOSA delegates to other vocabularies

SOSA explicitly *does not* model these — pull from the named vocabularies:

| Concern | Vocabulary |
|---|---|
| Geometry / spatial location | GeoSPARQL |
| Units of measure | QUDT, or custom datatypes (`cdt:pressure`, `cdt:ucum`) |
| Time intervals | OWL-Time |
| Catalogs / datasets | DCAT |
| Storage / streaming | SemSOS, Linked Stream Data tools |
| Actuator I/O interfaces | W3C Thing Description (WoT-TD), OWL-S, WSMX |
| Controlled vocabularies for `ObservableProperty` | SKOS code lists (e.g., SeaDataNet, NERC, SDN:P01) |

For the thesis, this means the manufacturing ontology stack will probably need: SOSA + PROV-O + QUDT (units) + GeoSPARQL (only if floor-plan geometry matters) + SKOS for property code lists.

## Concrete manufacturing-domain mapping for the thesis

Direct translation of [[anomaly-triage|the PumpStation_12 scenario]] into SOSA:

```turtle
ex:PumpStation_12 a sosa:FeatureOfInterest ;
    sosa:hasSample ex:Pump_12 .

ex:Pump_12 a sosa:FeatureOfInterest ;
    sosa:isSampleOf ex:PumpStation_12 .

ex:MIMII_AcousticSensor_42 a sosa:Sensor ;
    sosa:isHostedBy ex:RecordingRig_3 ;
    sosa:observes ex:AcousticSignature .

ex:MIMII_RecordingProtocol a sosa:Procedure ;
    rdfs:comment "16 kHz mono, 10 s per sample, anechoic chamber per Purohit et al. 2019."@en .

ex:AcousticSignature a sosa:ObservableProperty .

ex:Obs_2026-04-27_14-03 a sosa:Observation, prov:Activity ;
    sosa:madeBySensor ex:MIMII_AcousticSensor_42 ;
    sosa:hasFeatureOfInterest ex:Pump_12 ;
    sosa:observedProperty ex:AcousticSignature ;
    sosa:usedProcedure ex:MIMII_RecordingProtocol ;
    sosa:resultTime "2026-04-27T14:03:00Z"^^xsd:dateTime ;
    sosa:hasResult ex:Result_2026-04-27_14-03 .

ex:Result_2026-04-27_14-03 a sosa:Result, prov:Entity ;
    ex:anomalyScore 0.87 ;
    ex:fileURI <s3://mimii/pump_12/normal/2026-04-27_14-03.wav> .
```

The S4 agent then consumes this graph via SPARQL (per the [[think-on-graph|ToG]] Search templates) and emits a `prov:Activity` ([[prov-agent-souza2025|PROV-AGENT]] `AgentTool`) `wasInformedBy` the relevant `sosa:Observation`s. The chain from sensor → AI decision → action plan is fully PROV-traceable end-to-end. (source: arXiv:1805.09979 §2.2, §4.2 + thesis pitch §6)

## Reproducibility via `Procedure` (§2.1) — directly applicable to MIMII

The wind-speed example (§2.1): standard procedures define anemometer height (10m for meteorology, 2m for agrometeorology). Without the procedure, observations across sites are not comparable.

**For the thesis**: MIMII has a fixed recording protocol (16 kHz, mono, 10s segments, microphone position relative to machine). This protocol *must* be modeled as `sosa:Procedure` in the manufacturing KG, and *every* MIMII observation must `sosa:usedProcedure` it. Otherwise observations across machine variants (slider/valve/pump/fan) lose their cross-comparability — defeating the [[mimii-dataset|dataset's]] intended use. This is the kind of detail SHACL shapes should enforce ([[shacl-validation]]). (source: arXiv:1805.09979 §2.1)

## Why SOSA over building a custom manufacturing ontology

§6: as of 2018, **23 ontologies and 23 datasets** already used SOSA. Eight years later (2026), it is the de facto standard for sensor data on the Semantic Web — including in industrial-IoT contexts that the thesis's manufacturing scope sits in. Reviewer-defensible choice.

Building a custom manufacturing ontology from scratch would require defending the divergence from SSN/SOSA — an unfavorable trade vs. extending SSN/SOSA with manufacturing-specific subclasses (e.g., `mfg:RotatingMachineSensor v sosa:Sensor`).

## Open questions for ingest

- Which **SSN modules** (System Capabilities for [[local-deployment|RQ4]] hardware modeling? Sample Relations for sub-pump components?) does the thesis actually need beyond SOSA core? Recommend deciding by Phase 1 Week 4 (per the pitch's "freeze minimal ontology" mitigation).
- For QUDT: pin a specific QUDT version. The paper notes the custom datatype (`cdt:pressure`) is not yet recognized by current SPARQL engines — verify Fuseki's current support before adopting.
- The Web of Things (WoT) Thing Description is mentioned (§2.1, §2.4) for actuator I/O. The thesis does not currently invoke actuators, but if the demo includes a "send recommendation to maintenance system" hook, WoT-TD becomes relevant.
- Should `mfg:RotatingMachineSensor` and similar subclasses be defined under SOSA or under SSN? Default: define under SOSA core if the manufacturing-specific axioms are simple (just disjointness, range constraints) — keep `ALI(D)` fragment.

## Related pages

- [[ssn-sosa]]
- [[prov-o]]
- [[prov-agent-souza2025]]
- [[shacl-validation]]
- [[fuseki-triplestore]]
- [[mimii-dataset]]
- [[anomaly-triage]]
- [[kg-agent-s4]]
- [[research-questions]]
