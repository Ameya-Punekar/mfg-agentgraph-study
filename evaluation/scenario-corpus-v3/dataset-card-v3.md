# Scenario corpus — v3 dataset card

**Contract**: `mfg-agentgraph-scenario-corpus-v1` (unchanged; releases add an optional `provenance_profile`)
**Corpus ID**: `mimii-synthetic-context-v3`
**Version**: `v3`
**Release digest** (`sha256`): `0c11ebe5aa1ea4d6ef55f9785714e58476391d01759d7e4efe6d017ad2f210fe`
**Development split digest**: `8d170b8fcec51e8442da7dd44ae0740e0e7b97710586d88f0db2214079fb1f82`
**Supersedes**: `evaluation/scenario-corpus-v2/` and `evaluation/scenario-corpus-v1/` (both frozen and byte-identical)
**Description**: **MIMII-event-grounded synthetic-context** evaluation corpus

## What v3 changes, and what it deliberately does not

v3 keeps v2's documents, chunks, assets, sensors and observations, adds ten verified document
families, and replaces the **authored** layer a measurement depends on:

| Element | v2 | v3 |
|---|---|---|
| Documents (artifacts / families) | 39 / 38 | **49 / 48** |
| Source-located chunks | 418 | **528** |
| Observations | 1,612 (4 `mimii_derived`) | 1,612 (unchanged) |
| Procedures | 4, first three chunks of a document | 4, **chunks that state the action and its reason** |
| Development queries | 10, each citing only its observation | 10, each citing observation + procedure + entailing chunk(s) |
| Provenance in the graph | source and extraction fields dropped | `provenance_profile: complete` publishes them, plus a derivation record for derived sources |
| Triples | 13,405 | **14,761** |

The two captured bundles now build from a committed text snapshot, so a cold cache reproduces
them; the derivation record is described under *Provenance now published in the graph*.

### The ten added families

| Document | Class | Tier | Basis | Chunks | Share-alike |
|---|---|---|---|---|---|
| `doc:skat-india-mark-ii-2008` | pump | T1 | `open_licence` | 12 | no |
| `doc:skat-india-mark-iii-2008` | pump | T1 | `open_licence` | 12 | no |
| `doc:practica-rope-pump-2011` | pump | T1 | `open_licence` | 7 | no |
| `doc:navedtra-14075-engineman-1c-1987` | pump, valve, fan | T2 | `public_domain_statutory` | 12 | no |
| `doc:navedtra-14259-utilitiesman-advanced-1995` | pump, valve, fan | T2 | `public_domain_statutory` | 12 | no |
| `doc:navedtra-14057-damage-controlman-2001` | pump, valve, fan | T2 | `public_domain_statutory` | 12 | no |
| `doc:voron-2.4r2-assembly-manual` | slider | T1 | `open_licence` (GPL-3.0) | 7 | **yes** |
| `doc:lulzbot-taz6-manual` | slider | T2 | `open_licence` (CC BY-SA) | 12 | **yes** |
| `doc:farmbot-genesis-v1.8-docs` | slider | T2 | `open_licence` (CC0) | 12 | no |
| `doc:printnc-v4-assembly-wiki` | slider | T1 | `open_licence` (CC0) | 12 | no |

Coverage after v3: valve 25, pump 19, fan 13, **slider 7** (up from 3 — the class that had no
industrial source). Registry and licence evidence: `evaluation/scenario-corpus-v3/sources-v3.json`.

Three licence readings are recorded rather than assumed: Voron's repository-level GPL-3.0 is
treated as share-alike (not permissive); LulzBot's manual states CC BY in one place and CC BY-SA
in another, so the conservative share-alike reading applies; HTML documentation bundles count as
documents, matching how the OSE/RepRap/LowRider sources were already counted. Share-alike
obligations now attach to **five** documents.

### Two families excluded on purpose

USBR FIST 2-12 and FIST 4-1A were verified but **excluded**: they are US federal works, yet the
documents themselves carry an "internal use only by Bureau of Reclamation operations and
maintenance staff" distribution statement. The v1 exclusion stands — a thesis artifact should not
rest on treating a stated distribution limitation as void. They are the two-document gap below.

## Why the query and procedure layer was replaced

v2 shipped rubrics that its own evidence could not satisfy. `atq-206` asked which document chunk
and recording supported a recommendation while declaring only `obs:fan-01-mimii`; `atq-201` asked
for an observation time the contract cannot express; and each procedure cited the first three
chunks of its document — for the pump a table of contents, for the valve Navy promotional text,
for the slider frame-assembly steps. A run could therefore earn full expected-evidence credit
from a supporting observation alone.

v3 fixes this by construction, and the builder enforces it rather than the card asserting it:

- every non-trap query must cite a `proc:` reference **and** at least one `chunk:`;
- a cited chunk must be one the procedure already claims as evidence;
- every authored claim must quote its chunk **verbatim**, so a procedure cannot describe work
  its evidence omits;
- trap queries stay reference-free and are excluded from these rules.

## What was dropped instead of invented

Authoring the layer surfaced claims the corpus cannot support. Each was narrowed or removed
rather than written up as if sourced:

| Claim that was dropped | Why |
|---|---|
| Fan "inlet and outlet conditions" | No chunk describes fan inlet/outlet inspection |
| Fan "restore the system effect before changing speed" | The only "system effect" line is a pump LCC checklist |
| Pump "cavitation" / "recirculation" | Zero occurrences corpus-wide |
| Pump "trapped air presents as abnormal noise" | The only "trapped air" is concrete compaction in a handpump manual |
| Pump "isolate before impeller work" | No chunk states it |
| Valve "gland" inspection / "depressurise before renewing packing" | "gland" appears only in turbine passages; no depressurisation instruction exists |
| Valve "verify actuator stroke" | The corpus records "reset stroke" as repair, not an independent check |
| Slider "clean the guide surface" / "verify carriage play" | No linear-guide or rail instruction exists; slider evidence is Prusa bushings on smooth rods |
| `atq-201` observation time | `CorpusObservation` has no timestamp; the recording carries duration and identity only |

`proc:slider-lubrication` keeps its identifier for reference stability even though the entailed
content is bushing free-sliding and bearing alignment rather than relubrication.

## Provenance now published in the graph

`provenance_profile: complete` adds, per document, `sourceUri`, `sourceSha256`,
`relevanceTier`, `textLayer`, `allowsRedistribution`, `textSha256` and the extraction identity
(`extractionTool`, `extractionToolVersion`, `extractionRule`); per MIMII event it adds
`datasetDoi`, `recordingCrc32`, `recordingSeconds`, `sampleRateHz`, `channels` and
`bitsPerSample`. Previously a SPARQL consumer could join a chunk to its document and stop there.

### Derived sources carry their own record

For a native download, `sourceUri` is the URL and `sourceSha256` is the digest of the bytes it
serves. Three documents are not native downloads, and for them that pair alone would be a false
claim: `doc:nrc-nureg-cr-6478` extracts from an OCR text layer, and the FarmBot and PrintNC
documents extract from captures assembled out of several pages. Each of the three therefore also
carries `derivationKind`, `originUri`, `originSha256`, `derivationManifest`,
`derivationEntry` and — where one exists — `derivedArtifactSha256`:

| Document | Kind | `originUri` | `originSha256` | Derived artifact |
|---|---|---|---|---|
| `doc:nrc-nureg-cr-6478` | `ocr_text_layer` | OSTI 515583 purl | `cb14029b…` | OCR PDF `98bb723e…` |
| `doc:farmbot-genesis-v1.8-docs` | `assembled_capture` | `genesis.farm.bot/v1.8/` | capture `9279738b…` | — |
| `doc:printnc-v4-assembly-wiki` | `assembled_capture` | `wiki.printnc.info/en/v4/assembly` | capture `38e377bc…` | — |

`derivationManifest` names the committed manifest that declares the artifact chain in full: the
origin URL and digest, the derived OCR artifact, and the pinned extracted text with its own
digest. For the two captures it also lists every component page URL with its segment digest, in
assembly order. `derivationKind` is what keeps the pair honest — for an `assembled_capture` it
says the digest belongs to the capture the release assembled, not to the landing page's response
body.

v1 and v2 omit the field and keep their exact serialisation, which is why their committed
digests still verify.

## Scale — what is met, and what is not

Track A asks for ~50 documents and a meaningful 10^4–10^5-triple graph. v3 has **49 document
artifacts / 48 families** and **14,761 triples**. Both figures need their measurement beside
them.

**Documents.** 48 families against an *approximately* 50 target. The two-document gap is the two
excluded USBR manuals, and it is a licence decision rather than a search failure. Every one of
the 48 is a distinct, licensed work; editions, chapters and mirrors are not counted.

**Triples.** The count is still largely multiplicity: 64 sensors × 25 `nominal_*` observations
produce **9,600 triples**, and those 1,600 records differ only by identifier — no value, no time,
no state, no result. A further 390 triples are the v3 provenance fields, 16 of them the three derivation records. Strip the duplicate
nominal records and roughly 5,100 triples remain, below the protocol's 10^4 floor. The owner
decision for this release was to keep the observation layer unchanged and record the shortfall
rather than author a new observation contract now. **No Track A scale claim may cite this
corpus**; a successor release that adds authored `value` / `observed-at` / state fields is needed
first.

Other limits, unchanged:

- Two Navy manuals remain incomplete and excluded (NAVEDTRA 14265A part 1, 14264A Ch 9 only).
- Slides are still open-hardware documentation: no industrial linear-guide manufacturer grants
  reuse, so industrial slide-rail practice remains unrepresented despite the 3→7 growth.
- Chunks remain a ≤12-passage excerpt per document, not a re-publication.
- `doc:nrc-nureg-cr-6478`'s text is machine OCR, so a quoted clause must be checked against the
  page image.
- Two documentation bundles were captured as HTML pages; their text derives from the committed
  text snapshot, so a re-capture could change their chunks — and therefore the release digest —
  even though the capture is reproduced exactly from `evaluation/scenario-corpus-v3-derived/`.
  The graph records the origin, the capture digest and the per-component page list.

## Reproduction

```bash
uv run python scripts/build_scenario_corpus.py --version v3            # frozen v2 + authored layer
uv run python scripts/build_scenario_corpus.py --version v3 --verify   # JSON bytes + TriG graph
uv run python scripts/build_scenario_corpus.py --version v2 --verify   # v2 must still reproduce 91f4894…
uv run python scripts/build_scenario_corpus.py --version v1 --verify   # v1 must still reproduce 16a9568…
uv run mfg-agentgraph-corpus verify evaluation/scenario-corpus-v3/corpus-v3.json
uv run mfg-agentgraph-corpus load   evaluation/scenario-corpus-v3/corpus-v3.json
```

A later version refuses a base whose canonical release digest differs from the frozen release it
claims (`_FROZEN_V1_DIGEST`, `_FROZEN_V2_DIGEST`; the digest identifies release content, so
reformatting the file does not change it), and the v1 writer refuses to replace a divergent
frozen artifact instead of overwriting it. `--cache-dir` points the source cache at a fresh
directory to prove a cold rebuild. Three cold runs are recorded: v2 reproduces `91f4894…` from
an empty cache, and v3 reproduces `0c11ebe5…` from an empty cache — downloading the eight PDFs
and reading the two captured bundles from the committed
`evaluation/scenario-corpus-v3-derived/` text snapshots — as does v3 with only its HTML capture
inputs absent. `evaluation/scenario-corpus-v2-derived/` likewise holds the pinned text for the
one OCR-only report.

## Prohibited claims

- Any statement that this is MIMII maintenance decision support. MIMII supplies acoustic events only.
- Industrial decision quality, safety, operator trust, or field effectiveness.
- Topical breadth beyond the four classes and the documents listed.
- Protocol-scale (Track A) completeness; a "10^4-triple meaningful graph"; "49 independent
  sources" or "48 independent sources"; or any held-out score before the blinded packet and
  independent annotation exist.
- Any claim that the corpus is a complete re-publication of the source manuals.
