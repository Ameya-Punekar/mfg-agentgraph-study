# Scenario corpus — v2 dataset card

**Contract**: `mfg-agentgraph-scenario-corpus-v1` (unchanged; only the release version moves)
**Corpus ID**: `mimii-synthetic-context-v2`
**Version**: `v2`
**Release digest** (`sha256`): `91f48943414bb886e167924aca8caa2f9108e0d52f103f56eab90bbadd7ced76`
**Development split digest**: `9c16742882baefc772de56dcbec3ffdb158bf640a03fe81b056f567a29c907a7`
**Supersedes**: `evaluation/scenario-corpus-v1/` (frozen, still valid, byte-identical)
**Description**: **MIMII-event-grounded synthetic-context** evaluation corpus

## What changed from v1

v2 is additive. The builder loads the frozen v1 release and appends 11 documents that the v1
card recorded as unreachable. Nothing in the v1 layer is re-derived, so the v1 evidence layer
cannot drift underneath a v2 measurement.

| Element | v1 | v2 |
|---|---|---|
| Documents | 28 | **39** |
| Source-located chunks | 292 | **418** (126 added) |
| Assets | 8 | 8 |
| Sensors | 64 | 64 |
| Observations | 1,612 (4 `mimii_derived`) | 1,612 (4 `mimii_derived`) |
| Procedures | 4 | 4 |
| Development queries | 10 | 10 |
| Triples | 12,413 | **13,405** |

`corpus-v2.json` is 760,582 canonical bytes; `corpus-v2.trig` is 1,043,477 bytes.

### The 11 added documents

| Document ID | Class | Tier | Basis | Chunks |
|---|---|---|---|---|
| `doc:nrc-nureg-cr-4819-v1` | valve | T1 | `site_permission` | 12 |
| `doc:nrc-nureg-cr-4302-v1` / `-v2` | valve | T1 | `site_permission` | 12 / 12 |
| `doc:nrc-nureg-cr-4692` | valve | T1 | `site_permission` | 12 |
| `doc:nrc-nureg-cr-5515` | valve | T1 | `site_permission` | 12 |
| `doc:nrc-nureg-cr-5583` | valve | T1 | `site_permission` | 12 |
| `doc:nrc-nureg-cr-6478` | valve | T1 | `site_permission` | 12 |
| `doc:nrc-nureg-cr-6819-v2` | valve | T2 | `site_permission` | 12 |
| `doc:nrc-nureg-1296` | valve | T2 | `site_permission` | 6 |
| `doc:cdc-niosh-2019-124` | fan | T2 | `public_domain_statutory` | 12 |
| `doc:usace-em-1110-2-3105-2020` | pump | T1 | `public_domain_statutory` | 12 |

The authoritative registry, with URL, replay URL, cache path, digest and licence evidence per
document, is `evaluation/scenario-corpus-v2/sources-v2.json`. `evaluation/scenario-corpus-v1/acquisition-v1.json`
records how the bytes were obtained.

## Lineage — unchanged rules

The v1 rules still hold and are enforced by the contract, not by review: a `mimii_derived`
observation must carry its recording identity and declare `label_source: mimii_dataset_label`;
assets and sensors can never be MIMII-derived; licence governs bundling and chunking; only the
`development` split is representable. v2 adds documents and chunks only — the observation layer
is copied verbatim, so the acoustic-evidence-to-authored-context separation is untouched.

## Licences in v2

| Basis | Documents | Meaning |
|---|---|---|
| `public_domain_statutory` | 25 | 17 U.S.C. §105; third-party figures may still be embedded |
| `site_permission` | 9 | NRC site disclaimer: U.S. Government work not subject to copyright, "freely available for non-exclusive rights in publication or reproduction for any purpose", credit requested; embedded third-party material excluded |
| `open_licence` | 5 | OGL v3.0, GFDL, CC BY-SA |

**Share-alike obligations attach to three documents** and therefore to any derived text:
`doc:ose-universal-cnc-axis`, `doc:reprap-prusa-mendel`, `doc:v1e-lowrider`.

The nine NRC reports are recorded under the **site permission**, not blanket federal authorship,
because contractor-prepared NUREG/CR reports can contain approved third-party material. Only text
is used: embedded figures, photographs and quoted industry standards stay third-party and are
excluded. CDC's acquired copy states it "is in the public domain and may be freely copied or
reprinted"; the USACE 2020 manual states it "is approved for public release with unlimited
distribution".

## Provenance trap worth recording

Every acquired PDF came from **Internet Archive Wayback playback** of the official URL, because
`www.nrc.gov`, `www.cdc.gov`, `media.defense.gov` and `publications.usace.army.mil` reject this
egress at the CDN edge (Akamai 403 even for their homepages; an identical failure in a managed
Chromium). Wayback's raw-stream `id_` modifier is throttled to 429 for these files, normal
playback is not. Two captures truncated at exactly 5,242,880 bytes were rejected by an
`%%EOF` + `pdfinfo` + size gate and re-fetched from complete snapshots.

`doc:nrc-nureg-cr-6478` arrived **image-only** from both the NRC URL and its OSTI mirror
(OSTI 515583, 55 pp, 0 native words). A text layer was produced by real OCR — tesseract 5.5.0 at
300 dpi, text placed over the untouched 55-page scan with PyMuPDF in a throwaway environment, no
project runtime dependency added. The result (`acquired/nrc-nureg-cr-6478-ocr.pdf`,
sha256 `98bb723ed4c28ae8fe5d167b7c5b1db4b20c9db5bfeaf79c70ef3a8de32429e0`, 55 pp, 17,716 words)
yields 12 procedural chunks. Its text is machine-OCR: character-level errors are possible, so a
quoted clause from this document must be checked against the page image. Both original scans are
preserved unchanged.

## Scale, and the remaining shortfall

Track A asks for approximately 50 documents. v2 has **39 document artifacts**, which is **38
underlying document families**: `doc:usace-em-1110-2-3105-2020` supersedes the 1994 edition that
v1 already bundles as `doc:usace-em-1110-2-3105`. The count must be stated one way or the other,
never as "39 independent sources".

**The ~50 target is still unmet, and this card does not claim otherwise.** Remaining gaps:

- Two Navy manuals are incomplete: NAVEDTRA 14265A part 1 (Ch 1–8 plus Ch 9 to printed page 9-28)
  and NAVEDTRA 14264A Chapter 9 only. They are **not** in v2, because a partial manual is not the
  document.
- `media.defense.gov` splits those courses into dozens of objects with gaps in the numbering, so
  completion needs a US-network or DoD-accredited fetch.
- **Linear slides still have no industrial seam**: no industrial linear-guide manufacturer grants
  reuse, so the slide documents remain open-hardware documentation.
- The chunk rule still selects at most 12 procedural passages per document, so v2 remains a
  representative excerpt, not a re-publication.

## Leakage and split rules

Unchanged from v1: development-only split; queries authored before any strategy ran; no held-out
claim may cite this split; the 1,608 context observations are generated by a declared rule and
cannot support a claim about real asset behaviour.

## Reproduction

```bash
uv run python scripts/build_scenario_corpus.py --version v2            # build from the frozen v1 release
uv run python scripts/build_scenario_corpus.py --version v2 --verify   # JSON bytes + TriG graph isomorphism
uv run python scripts/build_scenario_corpus.py --version v1 --verify   # v1 must still reproduce 16a9568…
uv run mfg-agentgraph-corpus verify evaluation/scenario-corpus-v2/corpus-v2.json
uv run mfg-agentgraph-corpus load   evaluation/scenario-corpus-v2/corpus-v2.json
```

`--version v1` is the default and behaves exactly as before. The v2 build verifies the pinned
SHA-256 of every supplemental artifact on every run, refuses a cached byte mismatch, refuses a
supplemental document that yields no procedural chunk, and refuses to overwrite a divergent
versioned release rather than silently replacing it. Downloaded artifacts stay under
`.cache/scenario-corpus/` and are never committed.

The verified rebuild used the local source cache. Keep
`.cache/scenario-corpus/acquired/nrc-nureg-cr-6478-ocr.pdf`: its recorded download URL
serves the original scan, not the locally derived OCR PDF. A cache-free build therefore
requires recreating that OCR layer; downloading the scan alone will fail the pinned digest.
No cache-free rebuild or live Fuseki reload of v2 was exercised in this inclusion pass.

## Prohibited claims

- Any statement that this is MIMII maintenance decision support. MIMII supplies acoustic events only.
- Industrial decision quality, safety, operator trust, or field effectiveness.
- Topical breadth beyond the four classes and the documents listed.
- Protocol-scale (Track A) completeness; "39 independent sources"; or any held-out score before
  the blinded packet and independent annotation exist.
- Any claim that the corpus is a complete re-publication of the source manuals.
