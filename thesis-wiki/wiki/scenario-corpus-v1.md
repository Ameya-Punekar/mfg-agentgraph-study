# Scenario corpus v1

**Summary**: The versioned four-class anomaly-triage corpus (`mfg-agentgraph-scenario-corpus-v1`) that later S1–S4 measurements cite, with its composition, lineage rules, licences and the recorded shortfall against the protocol's document target.

**Sources**: `evaluation/scenario-corpus-v1/corpus-v1.json`, `corpus-v1.trig`, `acquisition-v1.json`, `dataset-card-v1.md`; `src/mfg_agentgraph/corpus_release.py`, `corpus_cli.py`, `scripts/build_scenario_corpus.py`; [[implementation-study-protocol-v1]]; [[mimii-dataset]]; GitHub issue #115.

**Last updated**: 2026-11-09.

**Thesis relevance**: RQ1 / RQ2 (RQ3 provenance and RQ4 local reproduction as prerequisites).

---

## What it is

One immutable release that fixes the input of the comparison: licensed procedural documents,
authored plant context, acoustic events traceable to declared MIMII recordings, and a
development-only query split. It is described as **MIMII-event-grounded synthetic-context**
evaluation, never as MIMII maintenance decision support.

| Element | Count | Lineage |
|---|---|---|
| Licensed documents | 28 | authored/curated (third-party text, excerpted) |
| Source-located chunks | 292 | derived, excerpt rule declared |
| Assets | 8 (two per machine class) | authored/curated |
| SSN/SOSA sensors | 64 | authored/curated |
| Observations | 1,612 | 4 **MIMII-derived**, 1,608 authored context |
| Procedures | 4 | authored, bound to chunks |
| Development queries | 10 | authored |
| Triples | 12,413 | one named graph |

## Why lineage is structural, not a comment

The protocol's central data rule is that acoustic grounding must be separable from authored
decision context. The contract therefore refuses:

- a `mimii_derived` observation without its recording identity, or with a `label_source` other
  than the dataset's — nothing in the corpus may claim that a detector ran;
- an asset or sensor marked `mimii_derived`, because MIMII supplies recordings, not an asset
  hierarchy;
- bundling or chunking a document whose licence forbids redistribution;
- any `split` other than `development`.

## The recorded shortfall

Track A asks for approximately 50 documents. This release has **28**, and says so in the card
and the decision record. The 13 further verified identities behind four hosts that refuse
programmatic download (`www.nrc.gov`, `media.defense.gov`, `www.cdc.gov`,
`publications.usace.army.mil`) were re-attempted after the freeze; the evidence is
`evaluation/scenario-corpus-v1/acquisition-v1.json`:

| Outcome | Identities | Where |
|---|---|---|
| Complete, validated | 11 (9 NRC valve reports, CDC/NIOSH 2019-124 dust control, USACE EM 1110-2-3105 **2020**) | Wayback playback of the official URLs |
| Partial | 2 (NAVEDTRA 14265A part 1 to Ch 9; NAVEDTRA 14264A Ch 9 only) | same transport; both Navy manuals are split uploads |
| Duplicate, not a new source | 1 (USACE EM 1110-2-3105 1994 + Changes 1–2, cleaner OCR than the cached mirror) | archive.org |

The block is at the CDN edge, not per file: even the hosts' homepages return Akamai 403 to this
egress (`89.245.181.195`, Düsseldorf), and a managed Chromium load fails identically, so it is
not a user-agent artefact. Wayback's raw-stream modifier (`id_`) is throttled to 429 for these
PDFs; normal playback serves the original bytes. Two captures truncated at exactly 5,242,880 B
were rejected and re-fetched. Seven of the nine NRC files were cross-checked against OSTI
catalogue report numbers.

These acquisitions **do not change v1**: the release still has 28 documents, and a Track A
completeness claim remains false. Eleven of them — the nine NRC reports (CR-6478 with the OCR
text layer), CDC/NIOSH 2019-124 and USACE EM 1110-2-3105 2020 — now form
[[scenario-corpus-v2]] (39 artifacts, 418 chunks, 13,405 triples), which is the release later
measurements should cite. Two hazards travel with them: NAVEDTRA 14265A carries a
copyright-for-record-purposes statement alongside its Distribution Statement A (so it stays out
until cleared), and NUREG/CR-6478 needed real OCR because both available scans are image-only.

Linear slides are the weakest class: no industrial linear-guide manufacturer grants reuse, so
the only slide documents are open-hardware documentation. Industrial slide-rail practice is
unrepresented, and that is a corpus limitation rather than a search gap.

## Reproducing it

```bash
uv run python scripts/build_scenario_corpus.py            # needs pdftotext; caches sources under .cache/
uv run python scripts/build_scenario_corpus.py --verify   # fail if a rebuild differs
uv run mfg-agentgraph-corpus load evaluation/scenario-corpus-v1/corpus-v1.json
```

`build` refuses to replace a frozen release with different content. `load` publishes only into
`urn:mfg-agentgraph:graph:corpus-context`, so the deployment's factory and provenance graphs are
never touched.

The 17 acquired-but-not-ingested files live in `.cache/scenario-corpus/acquired/` (gitignored).
`evaluation/scenario-corpus-v1/acquisition-v1.json` is committed instead of the PDFs: it records,
per identity, the official URL, the transport actually used, the Wayback snapshot, sha256, byte
count, page count, text-layer outcome and the licence caveat, so any file can be re-fetched and
checked without storing ~104 MB of third-party documents in git.

## Prohibited claims

Industrial decision quality, safety, operator trust, field effectiveness, topical breadth beyond
the listed documents, Track A completeness, and any held-out score before the blinded packet
and independent annotation exist.

## Related pages

- [[scenario-corpus-v2]] — the additive successor measurements cite
- [[implementation-study-protocol-v1]]
- [[mimii-dataset]]
- [[anomaly-triage]]
- [[local-deployment]]
- [[implementation-decisions]]
- [[delivery-roadmap]]
