# Scenario corpus v3

**Summary**: Superseded by [[scenario-corpus-v4]] (2026-11-13), which keeps this release's evidence and authored layers byte-identical. The release as frozen: v2's evidence layer plus ten verified document families (48 families in total, approximately the protocol's 50) and a corrected authored layer where every procedure cites chunks that state the action and its reason and every non-trap query cites observation + procedure + entailing chunk, with source, extraction and recording provenance published into the graph.

**Sources**: `evaluation/scenario-corpus-v3/corpus-v3.json`, `corpus-v3.trig`, `sources-v3.json`, `authored-v3.json`, `dataset-card-v3.md`; [[scenario-corpus-v2]]; [[scenario-corpus-v1]]; `scripts/build_scenario_corpus.py`; [[implementation-study-protocol-v1]]; GitHub issue #115.

**Last updated**: 2026-11-13.

**Thesis relevance**: RQ1 / RQ2 (RQ3 provenance and RQ4 local reproduction as prerequisites).

---

## Composition

| Element | Value |
|---|---|
| Documents | 49 artifacts / **48 families** |
| Source-located chunks | 528 |
| Assets / sensors | 8 / 64 |
| Observations | 1,612 (exactly 4 `mimii_derived`) |
| Procedures | 4, each with verbatim-quoted chunk support |
| Development queries | 10, each with a complete evidence chain |
| Triples | 14,761 |
| Release digest | `0c11ebe5…` |
| Development digest | `8d170b8f…` |

Coverage: valve 25, pump 19, fan 13, **slider 7** (was 3). Licence bases: 28
`public_domain_statutory`, 12 `open_licence`, 9 `site_permission`; **five** documents now carry
share-alike obligations (adding Voron GPL-3.0 and LulzBot CC BY-SA).

## Why the authored layer was rebuilt

v2's rubrics could not be satisfied by v2's own evidence. `atq-206` asked which document chunk and
recording supported a recommendation while declaring only `obs:fan-01-mimii`; `atq-201` asked for an
observation time the contract cannot express. Each procedure cited the first three chunks of its
document — for the pump a table of contents, for the valve Navy promotional text, for the slider
frame-assembly steps.

v3 enforces three rules in the builder instead of asserting them in prose: every non-trap query
cites a procedure *and* a chunk; a cited chunk is one the procedure claims; and every authored
claim quotes its chunk verbatim. Eleven claims the corpus could not support were dropped or
narrowed rather than written up as sourced — fan inlet/outlet inspection, pump cavitation and
recirculation, valve gland inspection and depressurisation, slider guide-surface cleaning and
carriage-play verification among them.

## Provenance in the graph

`provenance_profile: complete` publishes per-document `sourceUri`, `sourceSha256`,
`relevanceTier`, `textLayer`, `allowsRedistribution`, `textSha256` and the extraction identity, and
per MIMII event `datasetDoi`, `recordingCrc32`, `recordingSeconds`, `sampleRateHz`, `channels` and
`bitsPerSample`. Previously a SPARQL consumer could join a chunk to its document and stop there.
The field is optional, so v1 and v2 keep their exact serialisation and digests.

Three documents are not native downloads, and for them the `sourceUri`/`sourceSha256` pair alone
would misrepresent the bytes: `doc:nrc-nureg-cr-6478` extracts from an OCR text layer, and the
FarmBot and PrintNC documents from captures assembled out of several pages. Each carries
`derivationKind`, `originUri`, `originSha256`, `derivationManifest`, `derivationEntry` and, where
one exists, `derivedArtifactSha256`, so a reader can follow NRC citation → OSTI scan (`cb14029b…`)
→ OCR artifact (`98bb723e…`) → committed text, or landing page → per-component capture digest →
pinned text snapshot. `derivationKind` distinguishes "this digest is the origin's response body"
from "this digest is the capture the release assembled". The manifests
(`evaluation/scenario-corpus-v{2,3}-derived/`) declare the chain and the component URLs in order.

## Scale: approximately met on documents, not met on the graph

**Documents**: 48 families against an *approximately* 50 target. The two-document gap is the two
USBR FIST manuals, excluded because their own distribution statement limits them to internal
Bureau of Reclamation use — a licence decision, not a search failure.

**Triples**: 9,600 of the 14,761 come from 64 sensors × 25 `nominal_*` observations that differ
only by identifier, with no value, time or state. Strip them and roughly 5,100 triples remain,
below the protocol's 10^4 floor. The owner decision was to keep the observation layer unchanged
and record the shortfall; a successor release needs authored `value` / `observed-at` / state
fields before a Track A scale claim exists.

## Reproducing it

```bash
uv run python scripts/build_scenario_corpus.py --version v3           # frozen v2 + ten families + authored layer
uv run python scripts/build_scenario_corpus.py --version v3 --verify  # JSON bytes + TriG graph isomorphism
uv run mfg-agentgraph-corpus load evaluation/scenario-corpus-v3/corpus-v3.json
```

A later version refuses a base that is not byte-identical to the frozen release it claims, the v1
writer refuses to replace a divergent frozen artifact, and the load path publishes only the
corpus-context graph. `--cache-dir` proves a cold rebuild: v3 reproduces `0c11ebe5…` from an
empty cache — the eight PDFs are downloaded and verified, the two captures are read from the
committed `evaluation/scenario-corpus-v3-derived/` text snapshots with their component lists and
digests checked against the manifest.

## Prohibited claims

Track A completeness; a "10^4-triple meaningful graph"; "48/49 independent sources"; industrial
decision quality, safety, operator trust or field effectiveness; topical breadth beyond the listed
documents; a complete re-publication of any manual; any held-out score before the blinded packet
and independent annotation exist.

## Related pages

- [[scenario-corpus-v2]]
- [[scenario-corpus-v1]]
- [[implementation-study-protocol-v1]]
- [[implementation-decisions]]
- [[mimii-dataset]]
- [[anomaly-triage]]
