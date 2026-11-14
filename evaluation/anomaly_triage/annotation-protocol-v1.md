# Annotation protocol v1 — independent human gold labels

**Contract**: `mfg-agentgraph-annotation-sources-v1` (frozen sources),
`mfg-agentgraph-annotation-packet-v2` (packet), `mfg-agentgraph-gold-annotation-v2` (submission,
agreement report), `mfg-agentgraph-annotation-adjudication-v1` (adjudication), and
`mfg-agentgraph-human-gold-v1` (gold artifact)
**Applies to**: `evaluation/anomaly_triage/query-set-v1.json` (`anomaly-triage-v1`, 30 queries)
**Status**: protocol and tooling complete and enforced; **no independent human labels have been
collected**, so the issue's acceptance criteria are not met. A revised, explicitly non-independent
scope was adopted on 2026-11-06 — see *Revised scope* below.

## Why this protocol exists

Every label in `query-set-v1.json` was authored by the thesis author against the same SOP chunk
and KG fixture that S1–S4 retrieve from. The evaluation review (2026-09-29, R1/R2) flagged that
as gold-label bias: a scored result built on those labels can be attacked as self-referential.

This protocol fixes the *collection* procedure, not the labels. Independent labels must come
from people who did not author the queries, did not see the author's labels, rubrics, query
categories, or any strategy output, and worked only from the primary sources.

The author read the SOP *and* the KG; an annotator reads only the frozen manifest. That asymmetry
is the point: the labels are collected without the KG, so any label that matches the KG was not
derived from it. Independence is still a claim about the **annotators and their information access**,
attested outside the tooling; the tooling enforces what an annotator was given and may cite, but it
cannot verify that two pseudonyms are two different people.

## Primary sources an annotator may use

`evaluation/anomaly_triage/sources-v1.json` is the frozen manifest. It declares each permitted
source file, the evidence identifier that source is cited by, and the source file's SHA-256.
Loading it verifies the bytes, refuses a path outside the declared root (including through a
symlink), and refuses a duplicate identifier. The packet carries the manifest digest and the exact
source text, so an annotator needs nothing else and cannot wander into the labelled artifacts.

### Corpus vocabulary

| Identifier | Source | Frozen digest |
| --- | --- | --- |
| `ex:SOP_Chunk_7` | `tests/fixtures/sop/pump12-sop.txt` | recorded in `sources-v1.json` |

Citation membership is **enforced**, not merely requested: a submission citing any identifier
outside this table is rejected (`evidence_refs ... is not in the frozen source manifest`), and the
manifest digest is carried through the packet, every submission, the agreement report, and the gold
artifact, so an edited source invalidates the whole chain.

### What is deliberately not a source

The knowledge graph (`tests/fixtures/fuseki/pump12.trig`) and the author-authored labels are **not**
annotation sources. Issue #79 requires KG-derived labels to be at most a cross-check, so annotators
never see them, and the manifest cannot cite them.

The consequence must be stated precisely rather than worked around. An SOP-only pack is adequate for
**source adequacy**, not for adjudicating the benchmark key:

- when the pack omits an observation, a procedure link, an evidence edge, a timestamp, or a run
  record, the corresponding claim is **not assessable from this packet**;
- omission does **not** establish that a system answer is false, or that an author label is wrong;
- SOP-only judgments must **not** be promoted to benchmark gold for KG-dependent queries;
- `unsupported` means the frozen pack is silent about the request. It is never a claim about the
  world, and a grader that treats it as a wrong answer would penalise facts the pack withheld.

Independent human gold therefore needs more than this pack: task-adequate evidence plus an external
attestation that the annotators were independent. Issue #79's two-human requirement stays open until
both exist.

## Blinding rules

The annotator must not see, and the packet must not contain:

- the query `category` (especially the trap classes);
- `expected_evidence_refs`, `expected_action`, `expected_terminal_status`, or `gold_rubric`;
- any S1–S4 answer, retrieval list, metric value, or run record;
- agreement output from another annotator before their own submission is frozen.

`build_annotation_packet` emits only `query_id` and `text` per query, plus the dataset identity
and digests. A test asserts that no author-authored label value appears in the packet bytes.

## Per-query judgment

For each query the annotator records exactly one `support` verdict:

| `support` | Meaning |
| --- | --- |
| `supported` | The primary sources justify an answer; cite at least one identifier from the corpus vocabulary. |
| `unsupported` | The primary sources are silent or cannot settle the request; cite no evidence and propose no action. |
| `unsafe_request` | The request asks for action the sources forbid or do not authorize; cite no evidence and propose no action. |

Verdicts overlap in practice, so apply this precedence — the first row that applies wins, which is
what lets two annotators facing the same sources reach the same verdict:

1. `unsafe_request` when the request asks for forbidden or unauthorized action, even if it is also
   unanswerable;
2. `supported` when the sources justify an answer and the evidence can be cited;
3. `unsupported` when the sources are silent or cannot settle the request.

Always record a one-line `rubric` stating what a correct answer must contain, plus an optional
`action` string only for `supported` verdicts. Evidence references must be canonical `ex:`
identifiers from the corpus vocabulary, never free text.

Annotators judge the sources, not the system. "I do not know" is not a verdict: if the sources
cannot settle a query, the honest verdict is `unsupported`, and that disagreement is itself a
finding worth reporting.

## Collection procedure

1. Export the packet:
   `mfg-agentgraph-annotate packet --query-set evaluation/anomaly_triage/query-set-v1.json
   --sources evaluation/anomaly_triage/sources-v1.json --output <packet.json>` (run from the
   repository root, which is the manifest root; otherwise pass `--root`).
2. Give each of at least two annotators the packet, which already contains the frozen source text.
   Never give them the query-set JSON, the dataset card, any wiki page describing labels, the KG
   fixture, or each other's drafts.
3. Each annotator fills one submission with a distinct pseudonymous `annotator_id`, keeping names
   and contact details out of the artifact.
4. Submissions are frozen before comparison: each records the `query_set_sha256`,
   `manifest_sha256`, and `packet_sha256` it was collected against, and validation rejects any
   mismatch, missing query, duplicate judgment, unknown `query_id`, or out-of-vocabulary citation.
5. Only then compute agreement, and only then adjudicate.

## Agreement, reported before adjudication

`build_agreement_report(submissions, packet=...)` first re-checks every submission against that
packet — both digests and exact query coverage — so a report can never describe a partial or
rebound set, and then reports, for every pair of annotators:

- raw `support` agreement (`support_agreement_count`, `support_agreement_rate`);
- Cohen's κ over the three `support` classes, or an explicit
  `cohen_kappa_undefined_reason` when expected agreement is 1.0 (for example, both annotators
  used a single class). κ is never approximated or reported as 0 in that case;
- `evidence_exact_match_rate` and `evidence_mean_jaccard` over cited sets, with two empty sets
  scoring 1.0. Citations are canonicalized on validation, so the same identifiers in a different
  submission order agree;
- the `disagreement_query_ids` list, sorted, for adjudication.

Comparing one annotator with itself is rejected: a revised duplicate is not inter-annotator
agreement. Free-text rubrics are not scored for agreement; they are adjudication input only.

## Adjudication and promotion

- Disagreements are resolved by discussion or a third adjudicator and recorded in a separate
  adjudication document (`mfg-agentgraph-annotation-adjudication-v1`) naming the adjudicator, the
  query, the resolution, and a rationale. Original submissions are never edited: preservation is
  what makes the reported agreement reproducible.
- `mfg-agentgraph-annotate gold` emits the versioned `mfg-agentgraph-human-gold-v1` artifact only
  when both requirements hold: at least two distinct annotators, and every disputed query resolved
  by adjudication. A remaining dispute fails closed with
  `human gold cannot be emitted with unadjudicated queries: ...`.
- Each gold query records the human `support`, its evidence citations, and whether the label is
  `unanimous` or `adjudicated`. The author view appears only in
  `author_label_cross_check` (`agreement_count`, `disagreement_query_ids`), never as the label.
- `query-set-v1.json` is never edited in place after a benchmark cites it. A query a human majority
  rejects stays labelled as the humans decided; changing the author dataset requires its own
  version decision.

## Agreement report command

```bash
mfg-agentgraph-annotate agreement \
  --query-set evaluation/anomaly_triage/query-set-v1.json \
  --submission annotations/annotator-a.json \
  --submission annotations/annotator-b.json \
  --output annotations/agreement-report.json
```

```bash
mfg-agentgraph-annotate gold \
  --query-set evaluation/anomaly_triage/query-set-v1.json \
  --sources evaluation/anomaly_triage/sources-v1.json \
  --submission annotations/annotator-a.json \
  --submission annotations/annotator-b.json \
  --adjudication annotations/adjudication.json \
  --output annotations/human-gold-v1.json
```

Every subcommand creates a new file and refuses to overwrite one that exists, and each refuses an
`--output` path that is also an input, so a mistyped command cannot destroy a frozen submission,
the manifest, or the query set.

## Revised scope (2026-11-06)

The planned collection could not proceed: the thesis has one available human (its author), who is
not a domain expert. The independence requirement is therefore **not waived, deferred, or
simulated** — it is recorded as unmet, and a narrower reference scope was adopted for the work that
can still be done honestly.

### What replaces it, and what it does not

`mfg_agentgraph.synthetic_reference` emits `mfg-agentgraph-synthetic-reference-v2`
(`evaluation/anomaly_triage/synthetic-reference-v2.json`). For each query it records the reference
label and resolves every cited identifier against two frozen artefacts: the scenario fixture
(`tests/fixtures/pump_12/scenario.json`) and this protocol's source manifest.

Three rules make the anchoring meaningful rather than decorative:

- **Only declared resources anchor.** An identifier counts when it is declared under an `id` field in
  the fixture or named in the source manifest. Strings that merely appear in the fixture — a
  predicate name such as `ex:hasRecommendedProcedure` — are reported as
  `fixture_reference_only_identifiers` and cannot anchor a citation.
- **An empty citation set is not applicable.** Trap queries cite nothing by contract, so they are
  `not_applicable` rather than vacuously `fixture_anchored`. The committed artifact is therefore
  26 `fixture_anchored`, 4 `not_applicable`, 0 `unanchored`.
- **The scenario's content is bound, not just its identifiers.** `scenario_sha256` covers the
  fixture's canonical bytes, so editing the fixture's substance changes the artifact digest even when
  every identifier is unchanged.

The artifact answers exactly one question: **can this citation be resolved in a frozen artefact?**
It does not answer "is this label correct?" or "does the fixture's record settle this query?", and it
does not claim to. Its `authoring` block records `independent_annotation: false`,
`human_expert_review: false`, `inter_annotator_agreement: null`, and its
`original_requirement_status` records the unmet requirement verbatim. Its `scope` states that it is
not benchmark gold.

Consequently it is **not** a substitute for this protocol. It cannot be cited as human annotation,
it produces no agreement statistic, and it does not remove author bias — it makes the labels
reproducible and their citation anchoring checkable.

### Scoring a run against the reference

`mfg_agentgraph.synthetic_evaluation.score_reference_run` is the consumer. It reuses the shared
deterministic metric engine (`compute_query_metrics`, `summarize_run`) rather than reimplementing any
metric, and adds only the reference gate and the scope statement:

- a run whose recorded `dataset_sha256` does not match the reference's query set is refused, and so is
  a query set the reference does not describe — numbers can never be attributed to the wrong reference;
- when an entry is `unanchored`, the label-derived metrics (`hits_at_any`,
  `evidence_support_coverage`, `evidence_citation_precision`, `answer_action_exact_match`,
  `answer_action_token_f1`) become not-applicable **with a stated reason** instead of scoring against
  a broken reference, and their run-level summaries aggregate only anchored entries, stating that
  coverage in `applicable_count` — a suppressed query must not reappear as a number in the aggregate;
- metrics measured from the run itself — SHACL pass, repair iterations, provenance completeness,
  latency, memory — are never suppressed, because the reference has no bearing on them, and
  `terminal_status_match` stays present because the expected terminal status comes from the dataset
  contract rather than from a citation;
- a partial run is supported, so the five-query pilot in #39 reports what it measured and names the
  queries it did not, instead of implying full coverage.

### What the thesis must report

- Reference labels were authored by the thesis author with AI assistance and are anchored to frozen
  fixtures; **no independent human annotation or inter-annotator agreement was obtained.**
- The corpus is one synthetic pump scenario, so results establish scenario-level software
  conformance, not independently validated industrial decision quality.
- Queries whose answer the frozen fixtures do not establish remain *not assessable* rather than
  wrong; `label_scope` in the human-gold schema states the same limit.

## Prohibited uses

- Generating labels with a model, an agent, or the author and presenting them as independent
  human annotation.
- Editing a submission after seeing another annotator's submission or the agreement report.
- Relabelling queries so that agreement, κ, or the existing trap composition looks better.
- Citing an agreement report as proof of human independence; that claim needs an external
  attestation recorded alongside the artifact.
