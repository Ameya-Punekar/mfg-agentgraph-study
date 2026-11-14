# Implementation reference

Detailed component contracts for the current research snapshot. Run all commands from the repository root.

For the project story, current progress and quick start, see the [README](../README.md).

## Shared S1–S4 evaluation contract

`mfg_agentgraph.evaluation_harness` defines the dependency-free, immutable
`mfg-agentgraph-evaluation-result-v1` record shared by future S1–S4 runs. Every
record captures a controlled configuration, dataset/query-set identifiers, run
manifest, raw output, typed errors, and the same ordered artifacts. The run
manifest requires a 64-character lowercase `dataset_sha256`, so a record names
the exact query-set bytes it ran against. Artifact availability is explicit: a
strategy reports either `present` or `not_applicable` with a reason.

`mfg_agentgraph.anomaly_triage_dataset` owns the versioned query set at
`evaluation/anomaly_triage/query-set-v1.json`, documented by
`evaluation/anomaly_triage/dataset-card-v1.md`. It validates stable query IDs,
the approved thirty-query composition (single-hop, multi-hop, action-plan,
counterfactual, provenance, and two trap classes), gold rubrics, expected
evidence references, and trap invariants, then computes the canonical SHA-256
recorded in every run manifest. Trap queries must cite no evidence and carry the
expected terminal status — `insufficient_evidence` for unsupported requests and
`validation_failed_closed` for unsafe ones.

Neither module executes a strategy or reports empirical RQ1–RQ4 findings; those
remain owned by Issues #35–#40.

```python
from pathlib import Path

from mfg_agentgraph.anomaly_triage_dataset import load_query_set

query_set = load_query_set(Path("evaluation/anomaly_triage/query-set-v1.json"))
print(query_set.document_sha256)
```

## Independent gold annotation

Every label in the query set was authored by the thesis author against the same SOP chunk and KG
fixture the strategies retrieve from, so those labels are not independent. The evaluation review
flagged that as gold-label bias. Independent labels must come from annotators who never saw the
author's labels, rubrics, query categories, the KG fixture, or any strategy output.

`evaluation/anomaly_triage/sources-v1.json` freezes what an annotator is given:
`mfg_agentgraph.annotation_sources` verifies each declared file's exact bytes, refuses a path that
escapes the declared root (including through a symlink), and publishes the only evidence identifiers
an annotator may cite. The manifest digest is carried through the packet, every submission, the
agreement report, and the gold artifact.

`mfg_agentgraph.gold_annotation` implements the collection boundary:

- `build_annotation_packet(query_set, manifest=...)` emits a blinded packet of `query_id` and
  `text` per query plus the frozen source texts and the dataset/manifest digests. Author categories,
  rubrics, expected evidence, expected actions, and trap terminal statuses are absent by
  construction; the KG identifier cannot appear because it is not in the manifest.
- `parse_annotation_submission(payload, packet=...)` accepts a strict `support` verdict
  (`supported`, `unsupported`, or `unsafe_request`) with canonical `ex:` citations, an optional
  action, and a one-line rubric. It rejects a wrong contract version, any digest mismatch, missing,
  duplicate or unknown `query_id`, and **any citation outside the frozen manifest**; `supported`
  requires evidence and the other verdicts forbid evidence and actions. Citations are canonicalized
  into a sorted tuple, so they behave as sets.
- `build_agreement_report(submissions, packet=...)` re-validates every submission against the packet
  (digests and full query coverage), requires at least two distinct annotators, rejects comparing one
  annotator with itself, and reports per pair: raw `support` agreement, Cohen's κ, evidence
  exact-match rate, mean Jaccard, and the sorted disagreement list. κ becomes
  `cohen_kappa_undefined_reason` when expected agreement is 1.0 and is never forced to 0.

`mfg_agentgraph.human_gold` emits the versioned `mfg-agentgraph-human-gold-v1` artifact only when
nothing is left unresolved: at least two distinct annotators, and an adjudication decision for every
disputed query. Each query records the human label and whether it is `unanimous` or `adjudicated`;
the author view appears only as `author_label_cross_check`. KG-derived author labels are therefore a
recorded cross-check, never the label.

```bash
uv run mfg-agentgraph-annotate packet \
  --query-set evaluation/anomaly_triage/query-set-v1.json \
  --sources evaluation/anomaly_triage/sources-v1.json --output annotations/packet.json
uv run mfg-agentgraph-annotate agreement \
  --query-set evaluation/anomaly_triage/query-set-v1.json \
  --sources evaluation/anomaly_triage/sources-v1.json \
  --submission annotations/annotator-a.json --submission annotations/annotator-b.json \
  --output annotations/agreement-report.json
uv run mfg-agentgraph-annotate gold \
  --query-set evaluation/anomaly_triage/query-set-v1.json \
  --sources evaluation/anomaly_triage/sources-v1.json \
  --submission annotations/annotator-a.json --submission annotations/annotator-b.json \
  --adjudication annotations/adjudication.json --output annotations/human-gold-v1.json
```

Every subcommand creates a new file, refuses to overwrite an existing one, and refuses an `--output`
path that is also an input, so a mistyped command cannot destroy a frozen submission, the manifest,
or the query set.

`evaluation/anomaly_triage/source-adequacy-audit-v1.md` records an **AI-authored** source-adequacy
review of all thirty queries against the frozen pack. It is explicitly not human annotation, not
benchmark gold, and not expert validation: it states which claims the pack can support, which it
cannot address, and which operational-safety questions it must not answer.

### Synthetic reference (adopted 2026-11-06)

The planned independent collection could not proceed, so the branch ships a narrower scope rather
than a simulated one. `mfg_agentgraph.synthetic_reference` emits
`mfg-agentgraph-synthetic-reference-v2` and `mfg_agentgraph.synthetic_evaluation` scores runs
against it.

The reference:

- `build_synthetic_reference(query_set, scenario, source_manifest)` records each query's reference
  label and resolves every cited identifier against the frozen scenario fixture and the source
  manifest. Only identifiers **declared** under an `id` field (or named in the manifest) anchor; a
  string that merely appears in the fixture — a predicate name, for example — is reported as
  reference-only and cannot anchor. An entry is `fixture_anchored`, `unanchored` (with the unresolved
  citations listed), or `not_applicable` when it cites nothing by contract. One bad citation cannot
  affect the others.
- The artifact is hash-addressed over the canonical document and binds `query_set_sha256`,
  `source_manifest_sha256`, and `scenario_sha256`, so changing the query set, the manifest, or the
  scenario's substance changes the digest.
- `authoring` records `independent_annotation: false`, `human_expert_review: false`, and
  `inter_annotator_agreement: null`; `original_requirement_status` records the unmet two-annotator
  requirement; `scope` states that the artifact is not benchmark gold.

The scorer:

- `score_reference_run(configuration=..., query_set=..., reference=..., observations=...)` reuses
  `compute_query_metrics` and `summarize_run` rather than reimplementing any metric. It refuses a run
  whose `dataset_sha256` does not match the reference, and a query set the reference does not
  describe.
- Label-derived metrics (`hits_at_any`, `evidence_support_coverage`, `evidence_citation_precision`,
  `answer_action_exact_match`, `answer_action_token_f1`) become `not_applicable` with a stated reason
  when an entry is `unanchored`, and their run-level summaries aggregate only anchored entries —
  `applicable_count` states that coverage, so a suppressed query can never reappear as a number in
  the aggregate. Run-measured metrics — SHACL pass, repair iterations, provenance completeness,
  latency, memory — are never suppressed, and `terminal_status_match` stays present because the
  expected status comes from the dataset contract, not a citation.
- A partial run is supported: a pilot reports what it measured and names the queries it did not.

```bash
uv run mfg-agentgraph-annotate synthetic \
  --query-set evaluation/anomaly_triage/query-set-v1.json \
  --sources evaluation/anomaly_triage/sources-v1.json \
  --scenario tests/fixtures/pump_12/scenario.json \
  --output evaluation/anomaly_triage/synthetic-reference-v2.json
```

```python
from mfg_agentgraph.synthetic_evaluation import score_reference_run

score = score_reference_run(
    configuration=configuration, query_set=query_set, reference=reference, observations=observations
)
print(score.to_json())  # canonical report: digests, scope, per-query values, summary
```

What this establishes: every reference citation resolves in a frozen, digest-pinned artefact, a run
cannot be scored against a reference describing different queries, and the artifact cannot be
mistaken for independent human annotation. What it does not establish: that any label is correct,
that the fixture settles the query, or that the labels are independent of the author.
`evaluation/anomaly_triage/synthetic-reference-v2.json` is the committed instance (26
`fixture_anchored`, 4 `not_applicable`, 0 `unanchored`), and a test fails if it drifts from its
inputs.

No independent human labels, submission, agreement report, or gold artifact exists yet. The tooling
cannot verify that two pseudonyms are two different people, so an agreement report is unverified
collection evidence until an external attestation accompanies it. Model-generated, agent-generated,
or author-generated labels are never substitutes, and `query-set-v1.json` is not edited to make
agreement look better.

Because the manifest deliberately excludes the KG, an SOP-only pack is adequate for **source
adequacy** rather than for adjudicating the benchmark key. A claim the pack cannot address is *not
assessable* from it: omission does not make a system answer false or an author label wrong, and
SOP-only judgments must not be promoted to gold for KG-dependent queries. Every gold artifact states
this in `label_scope`. Task-adequate annotation evidence and an external attestation of independent
annotators are still required.

## RQ metric suite

`mfg_agentgraph.evaluation_metrics` turns comparable records into RQ-mapped
numbers with explicit absence. A strategy adapter supplies one
`MetricObservation` per query (predicted answer, cited evidence, terminal
status, optional SHACL/repair, provenance components, latency, peak memory);
`compute_query_metrics` returns that query's RQ1–RQ3 values and
`summarize_run` aggregates means, nearest-rank latency p50/p95, and peak memory
with applicable/undefined counts. Every undefined value carries a reason
instead of silently scoring zero.

| RQ | Metrics |
| --- | --- |
| RQ1 | `hits_at_any`, `evidence_support_coverage`, `evidence_citation_precision`, `answer_action_exact_match`, `answer_action_token_f1`, `terminal_status_match` |
| RQ2 | `initial_shacl_pass`, `final_shacl_pass`, `repair_iterations`, `repair_succeeded_after_failure` |
| RQ3 | `provenance_completeness` over `agent`, `activity`, `entity`, `used`, `wasGeneratedBy` |
| RQ4 | `latency_p50_ms`, `latency_p95_ms`, `peak_memory_mb` |

`answer_action_token_f1` is a deterministic lexical proxy, not semantic
similarity. `DEFERRED_METRICS` records what the suite deliberately does not
compute: RAGAS faithfulness and answer relevance (they need a non-deterministic
LLM judge) and operator-trust or usability instruments (they need participants).




## S4 strategy registration

`mfg_agentgraph.s4_evaluation_strategy` registers the production ten-stage S4
orchestrator in the shared harness. `build_s4_run_configuration(query_set)` fixes
the controlled configuration, `build_stable_ids(query_id)` derives per-query
run-scoped identities, and `run_s4_query(query, configuration, ...)` returns one
`EvaluationResult` plus the matching `MetricObservation`.

The record derives its artifacts from real orchestrator outputs: the answer
artifact carries the released action label or the terminal refusal, the
retrieved-context artifact carries the typed KG and document evidence IDs, the
validation artifact carries initial/final pass and repair iterations from the
SHACL and bounded-repair stage events, and the provenance artifact carries the
trace ID plus the PROV components found in the trace triples. Runs that fail
closed before validation or before the provenance write mark those artifacts
`not_applicable` with a reason instead of omitting them, and
`count_terminal_statuses` keeps every fail-closed outcome visible.

Two honest limitations: the deterministic fixture path does not interpret trap
wording, so S4 currently scores `terminal_status_match` 0 on trap queries, and
the candidate action identity stays fixed across runs because the deterministic
generation contract fixes it, while report, package, provenance, and prompt
identities are unique per query.

## S1 naive-RAG baseline

`mfg_agentgraph.s1_naive_rag` registers the baseline arm: lexical retrieval over
procedure paragraphs plus an extractive answer. `S1Chunk` carries the canonical
evidence ID so citations stay comparable with S4; `build_s1_index` and
`build_s1_index_from_document` build the corpus; `retrieve_naive` ranks chunks by
stopword-filtered query-token coverage with ties broken by evidence ID; and
`run_s1_query` emits the shared record and observation.

The record is honest about what S1 cannot do: the validation-report and
provenance-trace artifacts are `not_applicable` with reasons, and a query whose
tokens do not match the corpus fails closed as `insufficient_evidence` instead of
answering from nothing. Answers are extractive — the top retrieved sentence is
the answer — so token-F1 measures retrieval quality without a model in the loop.

Consequence for scoring: S1 can only ever cover document evidence, so on a query
whose gold evidence includes a KG edge, `evidence_support_coverage` tops out at
the document share (0.5 on `atq-013`) while citation precision can still be 1.0.

## S3 ontology-grounded RAG baseline

`mfg_agentgraph.s3_ontology_rag` registers the ontology-grounded arm. It keeps
the OG-RAG mechanism — ontology-mapped factual blocks, key and value relevance,
and greedy minimal-hyperedge coverage — and deliberately stops before S4's
constraints:

- `S3Fact` and `S3FactualBlock` model one attribute/value pair and the block
  (hyperedge) that contains it, each carrying its canonical evidence IDs;
- `retrieve_ontology_grounded` first drops blocks whose asset or procedure is
  outside the ontology scope, scores the remaining facts by query-token overlap
  on the key side and on the value side, then greedily selects the blocks that
  cover the most still-uncovered relevant facts, with ties broken by block name;
- `build_s3_run_configuration` and `run_s3_query` reuse the shared record,
  metric observation, typed retrieval results, and candidate-generation
  contract used by S4.

The capability boundary is explicit in the record: the validation-report and
provenance-trace artifacts are `not_applicable` with reasons, the raw output
states `constraint_validated: false` and `provenance_id: null`, and the metric
observation leaves the SHACL, repair, and provenance fields undefined, so S3
scores nothing it did not measure.

`check_s3_candidate_post_hoc(evaluation, ...)` is the separate, opt-in check. It
reuses the RDF assembly and SHACL validator on the recorded candidate after the
S3 answer is stored; a violation is returned as a `ShaclValidationResult` and
never rewrites the S3 record or turns a released answer into a gated one.

Two honest limitations: the deterministic fixture maps the ontology facts with
lexical query-token overlap rather than embeddings, so it demonstrates the
retrieval shape and comparability, not the paper's semantic gains; and the corpus
is a single Pump_12 scenario, so absolute scores are not topical-breadth
evidence.

A third limitation is measured rather than argued: the deterministic fixture does
not read trap wording, so a full-dataset smoke releases an answer for all four
trap queries. S3 therefore scores `terminal_status_match` 0 on traps, the same
honest failure the S4 fixture path shows. Faking abstention in the fixture layer
would corrupt the comparison; abstention is measured by the model-backed run and
the dedicated abstention suite. Because S3 cites whole factual blocks, its
citation precision against single-evidence gold queries is also mechanically
below 1.0.

## S2 GraphRAG-style baseline

`mfg_agentgraph.s2_graphrag` registers the document-built-graph arm. The graph
comes from the corpus alone — no expert ontology, no SHACL gate, no PROV-O — which
is exactly what separates S2 from S3:

- `build_s2_index(chunks, build_duration_ms=None)` reads the same `S1Chunk`
  corpus as S1 and S3, splits it into sentence claims, extracts content terms,
  weights co-occurring term pairs, detects communities by connected components,
  and writes one extractive summary per community with the source chunk IDs it
  came from;
- the build also records its own cost — `build_duration_ms`, canonical
  `index_bytes`, entity/claim/edge/community counts, and an `index_sha256` over
  the canonical index JSON — so a rebuild from the documented inputs is
  verifiable and the build cost never hides inside query latency;
- `build_s2_run_configuration(query_set, index)` binds a run to one index digest,
  and `run_s2_query(query, configuration, index=...)` map-reduces over the
  top-ranked community summaries, answering from the best-matching claim of each
  selected community and citing only the chunk evidence those claims came from;
- `summarize_index_build(index)` exposes the measured build cost for experiment
  reporting.

The record states the absent capabilities explicitly: `validation_report` and
`provenance_trace` are `not_applicable` with reasons, `constraint_validated:
false`, `provenance_id: null`, and the SHACL, repair, and provenance metrics are
undefined. A query that matches a community's summary vocabulary but no single
claim cannot be supported abstains as `insufficient_evidence` rather than
answering from a summary.

Three documented substitutions keep this deterministic: content-term extraction
replaces GraphRAG's LLM entity extraction, connected components replace
hierarchical Leiden (at one-scenario fixture scale Leiden yields one coarse
community anyway), and summaries are extractive rather than LLM-written. The arm
therefore demonstrates graph-and-summary structure plus build-cost accounting,
not the paper's reported global-sensemaking gains.

## Abstention suite

`mfg_agentgraph.abstention_suite` measures whether a strategy declines a trap
query and, more importantly, why. The suite *is* the trap subset of
`query-set-v1.json` — two `trap_unsupported` and two `trap_unsafe` queries —
derived through `abstention_suite_queries`, so there is no second manifest that
can drift from the dataset the loader validates.

`build_abstention_report(configuration=..., query_set=..., records=...)` takes the
strategy evaluation records themselves — the `S1QueryEvaluation`,
`S2QueryEvaluation`, `S3QueryEvaluation`, and `S4QueryEvaluation` objects, each of
which pairs an `EvaluationResult` with its `MetricObservation`. Bare observations
are not accepted: a report must derive its arm, query IDs, and terminal statuses
from records the harness produced, so a run cannot be relabelled. Each record must
name the supplied configuration and the query set's `dataset_sha256`, its result
and observation must agree on the query ID, and its recorded `terminal_status`
must match the observation.

The report (`mfg-agentgraph-abstention-suite-v1`) classifies every evaluated query
and states rates with numerator, denominator, and an explicit not-applicable
reason:

| Outcome | Meaning |
| --- | --- |
| `correct_abstention` | trap query ended in the status the dataset contract fixes |
| `wrong_abstention` | trap query ended in another non-`passed` status, such as `provenance_failed_closed` |
| `false_answer` | trap query ended `passed` |
| `answered` | answerable query ended `passed` |
| `over_abstained` | answerable query failed closed |

`trap_abstention_recall`, `trap_false_answer_rate`, and
`trap_wrong_abstention_rate` cover the trap suite;
`unsupported_abstention_recall` and `unsafe_refusal_recall` split it by trap
class; `answerable_over_abstention_rate` covers over-refusal. A wrong-reason
abstention is never credited as recall — a provenance-write failure is not the
system choosing to decline — and a false answer is never counted as an
abstention. A rate's denominator counts the *evaluated* queries of its class, so
a zero denominator is `not_applicable` with a reason, never `0.0`.

Three claims are deliberately bounded:

- **Status, not intent.** `correct_abstention` is a match on the contract's
  terminal status. An operational failure can produce the same status, so the
  report establishes that a run declined with the required status, not that the
  strategy recognised the request as unanswerable or unsafe.
- **Capability, not capability-free scoring.** `unsafe_refusal_recall` is scored
  only for arms that can pass or fail a validation gate (`VALIDATION_GATE_STRATEGIES`,
  which Architecture V1 R4 makes S4 only). S1, S2, and S3 report it as
  `not_applicable` with a capability reason, because a `0.0` there would describe
  a missing mechanism rather than a measured refusal failure.
- **Fixture behaviour, not model behaviour.** Every registered adapter is
  deterministic and none interprets trap wording. Model-backed abstention is
  therefore still unmeasured and needs an explicitly configured, pinned
  model-backed strategy run; it is not something the registered pilot supplies.

The report is digest-bound and reproducible from its own rows. It carries the
dataset ID, query-set ID, every query-set ID with its category, the evaluated
IDs, and the unevaluated IDs, whose complement relation is checked, so a partial
run cannot quietly drop queries. Because the categories are recorded, the suite
must equal the dataset's trap subset exactly — a partial report cannot relabel
an unevaluated answerable query as a trap, or omit an unevaluated trap. It refuses a mismatched configuration identity or dataset
digest, duplicate or unknown records, and any hand-assembled report whose outcome
counts, evaluated IDs, suite IDs, or six rates disagree with its per-query rows.
Each row also re-validates itself: a trap row's expected status must equal the
dataset contract's, and its outcome must be the one its category and observed
status imply. `strategy` is an `EvaluationStrategy` member, so a report cannot
name an arm that does not exist.

Measured baselines on the deterministic fixture path, both recorded rather than
repaired:

| Arm | Traps declined | False answers | Over-abstentions | Refusal recall |
| --- | --- | --- | --- | --- |
| S4 | 0 / 4 | 4 | 0 / 26 | `0.0` (0/2) |
| S1 | 0 / 4 | 4 | 2 / 26 | `not_applicable` (no gate) |

Both arms release the same cavitation answer for every trap, which is the
documented consequence of deterministic adapters not reading trap wording.
Keyword-sniffing abstention inside the fixture layer would fake the behaviour
under test, so the numbers stand as the honest fixture baseline. Extending the
suite past four traps needs a new query-set version, because any query, label,
or count change requires one.

## Deterministic local S4 demo

After `uv sync --locked`, run the service-free Pump_12 vertical slice from the repository
root:

```bash
uv run mfg-agentgraph-demo
```

The command prints the terminal status, released recommendation, evidence-package ID,
provenance ID, and the ordered status of all ten S4 stages. It always uses the canonical
`tests/fixtures/pump_12/scenario.json` fixture together with fixed demo identities and a
fixed UTC timestamp, so repeated runs produce the same output.

This is a local deterministic demonstration, not a production command. It performs no
network, live-model, Fuseki, Qdrant, or other service call. Its provenance callback accepts
the trace in memory but does not provide durable persistence. A passing demo is not a claim
that the recommendation is safe or optimal.

## Local deployment envelope

The implementation study runs on one pinned, free, loopback-only stack: Fuseki 6.2.0
(TDB2), Qdrant 1.19.2 and Ollama 0.23.2. `deploy/compose.yaml` pins each image by
manifest digest and binds every port to `127.0.0.1`.

```bash
cp deploy/env.example deploy/.env          # set MFG_FUSEKI_ADMIN_PASSWORD
docker compose -f deploy/compose.yaml --profile cpu up -d
uv run mfg-agentgraph-stack bootstrap       # graphs, collection, pinned models
uv run mfg-agentgraph-stack doctor          # non-zero on any mismatch
uv run mfg-agentgraph-stack status          # resolved configuration, no network
```

`bootstrap` runs before `doctor` because the readiness gate checks the graphs, the
collection and the pinned models that `bootstrap` creates; on a cold stack the first
run also downloads the pinned models (several gigabytes). The CLI reads `deploy/.env`
from the current directory when no environment is supplied, so the same file
configures both Compose and the CLI; a real environment variable always wins.

`doctor` is the readiness gate: it verifies endpoint reachability, exact service
versions, the pinned model digests and the presence of the factory and shapes graphs,
and it has no fixture fallback. The pinned Fuseki image authenticates `/$/server`, so
`doctor` needs `MFG_FUSEKI_ADMIN_PASSWORD` and reports an explicit authentication
failure when it is missing; the dataset query endpoint is `/ds/sparql` because that is
the service name the image's assembler declares. `bootstrap` is idempotent and refuses
to replace a graph or collection whose content differs unless `--recreate` is passed; it
never deletes a collection. Non-loopback endpoints are rejected unless
`allow_non_loopback` is set explicitly.

Full commands, profiles, the licence table and the WSL2 notes are in
`docs/deployment.md`. Hardware latency and memory are measured by a later issue; this
substrate only guarantees that the envelope can be measured.

## Scenario corpus (Issue #115)

`evaluation/scenario-corpus-v1/` is the frozen versioned corpus release: 28 licensed documents
reduced to 292 procedural chunks, 8 assets, 64 SSN/SOSA sensors, 1,612 observations (4
MIMII-derived acoustic events plus authored context), 4 procedures and 10 development-split
queries, as 12,413 triples. Its card records composition, lineage, licences, the share-alike
documents, and the honest shortfall against the protocol's ~50-document target.

`evaluation/scenario-corpus-v2/` is the additive successor: it loads the frozen v1 release and
appends the 11 documents that v1 recorded as unreachable (nine NRC valve reports, the CDC/NIOSH
dust-control handbook, and the USACE EM 1110-2-3105 2020 edition), giving **39 document
artifacts / 38 document families, 418 chunks and 13,405 triples** with the v1 observation layer
copied verbatim. `sources-v2.json` pins the official URL, the validated replay used for
acquisition, the cache path, the content digest and the licence evidence per document. The
protocol's ~50-document target is still unmet and must not be claimed.

`evaluation/scenario-corpus-v3/` keeps v2's evidence layer, adds ten
verified document families (SKAT India Mark II/III, PRACTICA rope pump, three NAVEDTRA courses,
Voron 2.4R2, LulzBot TAZ 6, FarmBot Genesis, PrintNC) reaching **49 artifacts / 48 families and
528 chunks**, and replaces the authored layer so every procedure cites chunks that state the
action and its reason and every non-trap query cites observation + procedure + entailing chunk.
`provenance_profile: complete` publishes source, extraction and recording identity into the graph;
`authored-v3.json` carries the per-claim quotes the builder verifies. A document whose extracted
artifact is not the bytes its origin serves — the OCR'd NUREG/CR-6478 and the two assembled HTML
captures — also carries a `derivation` record naming the origin URL and digest, the derived
artifact digest, and the committed manifest that declares both, so a consumer never has to treat
a derived hash as origin bytes.

`evaluation/scenario-corpus-v4/` is the current release: it keeps v3's documents, chunks, assets,
sensors, procedures and development queries byte-for-byte and replaces only the observation layer,
which in v3 repeated one identifier-only record 1,600 times (**1,608** of 1,612 observations stated
nothing but their own identity). v4 states, for each of **1,600** authored readings, a value in the
sensor's unit, the scenario instant and the operating state it belongs to, so
**`identifier_only_observation_ids` is empty** and the graph grows from 14,761 to **19,521** triples
by adding information rather than repetition. The four MIMII events remain the only
recording-bearing observations and may carry neither a value nor a timestamp, because the dataset
supplies an acoustic clip and a label, not a reading or a wall-clock time. The generated values are
**synthetic scenario fixtures** produced by a declared, seedless formula: they encode no
manufacturer limit, diagnostic threshold or measured behaviour, and the card lists the profile.
Reaching the protocol's 10^4-triple order is a scale statement only; the ~50-document target stays
**approximately met at 48**, the two excluded USBR manuals being a recorded licence decision.

```bash
uv run python scripts/build_scenario_corpus.py                        # v1 (default), needs pdftotext
uv run python scripts/build_scenario_corpus.py --verify               # fail if a v1 rebuild differs
uv run python scripts/build_scenario_corpus.py --version v2           # append the v2 documents
uv run python scripts/build_scenario_corpus.py --version v3           # v2 + ten families + authored layer
uv run python scripts/build_scenario_corpus.py --version v3 --verify  # JSON bytes + TriG graph
uv run python scripts/build_scenario_corpus.py --version v4           # v3 + the scenario observation layer
uv run python scripts/build_scenario_corpus.py --version v4 --verify  # JSON bytes + TriG graph
uv run mfg-agentgraph-corpus verify evaluation/scenario-corpus-v4/corpus-v4.json
uv run mfg-agentgraph-corpus load   evaluation/scenario-corpus-v4/corpus-v4.json
```

`build` writes canonical bytes and refuses to replace a frozen release with different content, and
each version writes only under its own `evaluation/scenario-corpus-vN/` directory. `verify` also
prints how many observations state nothing but an identifier, which must be zero.
`load` publishes only into the `urn:mfg-agentgraph:graph:corpus-context` named graph through the
same idempotent bootstrap as the deployment CLI, so the factory and provenance graphs are never
touched. Source artifacts are cached under `.cache/` and are not committed.

## Repository layout

```text
.
├── AGENTS.md                         # Workspace instructions for AI agents
├── README.md                         # Project overview and workflow entry point
├── CONTRIBUTING.md                   # Branch, commit, PR, review, and merge rules
├── SECURITY.md                       # Secret-handling and security reporting policy
├── CODEOWNERS                        # Default review ownership
├── pyproject.toml                    # Python package and quality-tool configuration
├── uv.lock                           # Reproducible Python dependency lock
├── deploy/                           # Pinned free local stack (compose, env example)
├── src/mfg_agentgraph/               # Implementation V1 product package
├── tests/                            # Deterministic product tests
├── docs/engineering-standards.md     # Minimal-code, testing, and PR quality policy
├── docs/deployment.md                 # Local envelope commands, profiles, licences
├── docs/repository-governance.md     # Detailed professional repo rules
├── scripts/wiki_health.py            # Thesis-wiki structural lint
├── scripts/repo_quality_check.py     # Repo governance/quality lint
├── thesis-wiki/raw/                  # Immutable source material; do not edit
├── thesis-wiki/wiki/                 # Maintained Obsidian/LLM research brain
└── concept-paper/                    # Concept/position paper artifacts
```

## Thesis wiki workflow

The wiki is the source of truth for research memory.

1. Read `AGENTS.md`.
2. Read `thesis-wiki/AGENTS.md` if present.
3. Read `thesis-wiki/wiki/index.md`.
4. Never modify `thesis-wiki/raw/`.
5. Use Obsidian wikilinks such as `[[kg-agent-s4]]`.
6. Cite claims with source filenames and arXiv/DOI when available.
7. Mark uncertain claims with `[NEEDS VERIFICATION]`.
8. After wiki edits, update navigation if needed and append `thesis-wiki/wiki/log.md`.
9. Run `python3 scripts/wiki_health.py` before committing.

## Development workflow

This repository uses trunk-based development with protected `main`.

1. Create a branch from `main` using the naming convention in `CONTRIBUTING.md`.
2. Make small, focused commits using Conventional Commits.
3. Run local validation:

   ```bash
   uv sync --locked
   uv run ruff check src tests
   uv run ruff format --check src tests
   uv run mypy
   uv run pytest
   uv run coverage report --include=src/mfg_agentgraph/fixture_model_adapter.py
   uv run zizmor .github/workflows
   python3 scripts/wiki_health.py
   python3 scripts/repo_quality_check.py
   ```

4. Open a pull request using the PR template.
5. Merge with squash merge after checks pass.
6. Delete the branch after merge.

For solo-agent emergency/admin changes, direct commits to `main` are allowed only when explicitly requested by the repository owner; the same validation and commit hygiene still apply.

## Branch naming

Use lower-case kebab-case names:

```text
feat/<short-description>
fix/<short-description>
docs/<short-description>
research/<paper-or-topic>
experiment/<rq-or-benchmark>
ci/<short-description>
chore/<short-description>
```

Examples:

```text
research/tog-2-verification
experiment/rq1-s1-s4-harness
docs/concept-paper-venue-plan
ci/repo-quality-checks
```

## Validation

```bash
uv sync --locked
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest
uv run coverage report --include=src/mfg_agentgraph/fixture_model_adapter.py
uv run zizmor .github/workflows
python3 scripts/wiki_health.py
python3 scripts/repo_quality_check.py
```

`pytest` enforces at least 90% branch coverage for `src/mfg_agentgraph`.
A separate check enforces 90% for `src/mfg_agentgraph/fixture_model_adapter.py` with:

```bash
uv run coverage report --include=src/mfg_agentgraph/fixture_model_adapter.py
```

GitHub Actions runs the same locked checks on implementation branches, `main`, and pull requests. See `docs/engineering-standards.md` for the reuse-first rule, dependency policy, and Architecture V1 decision discipline.

## Operator request contract

The initial S4 entry-point contract is `mfg_agentgraph.operator_request.normalize_operator_request`. It accepts a JSON-like mapping with required `query_text`, timezone-aware ISO-8601 `timestamp`, and `run_id` fields, plus optional ordered `asset_hints` and `sensor_hints`.

```python
from mfg_agentgraph.operator_request import normalize_operator_request

request = normalize_operator_request(
    {
        "query_text": " Why did Pump 12 vibrate? ",
        "timestamp": "2026-08-23T20:15:00+02:00",
        "run_id": " operator-run ",
        "asset_hints": [" Pump_12 "],
    }
)
```

Valid input returns an immutable `NormalizedOperatorRequest` with trimmed strings, UTC-normalized timestamp, and immutable hint tuples. Malformed input returns a typed `RequestValidationFailure` instead of raising raw `KeyError`, `TypeError`, or `ValueError`. This is only the request normalization boundary; later S4 stages such as entity resolution, KG checks, orchestration, validation/repair, evidence packaging, provenance writing, and terminal-state instrumentation are not implemented here.

## Entity and asset resolution contract

The deterministic S4 entity-resolution boundary is `mfg_agentgraph.entity_resolution`. It resolves a caller-provided asset hint or already-extracted term against an explicit in-memory `AssetCatalog` of `KnownAsset` records.

```python
from mfg_agentgraph.entity_resolution import AssetCatalog, KnownAsset
from mfg_agentgraph.stage_instrumentation import TerminalStatus

catalog = AssetCatalog(
    (
        KnownAsset(
            asset_id="ex:Pump_12",
            primary_label="Pump 12",
            aliases=("Pump_12",),
        ),
    )
)

result = catalog.resolve(" pump_12 ", min_confidence=0.9)
assert result.status is TerminalStatus.PASSED
assert result.selected_asset is not None
assert result.selected_asset.asset_id == "ex:Pump_12"
```

Canonical asset IDs match exactly and case-sensitively, with no surrounding-whitespace normalization. Primary labels and registered aliases use only `strip()` plus `casefold()` normalization. Confidence scores are fixed deterministic priorities, not learned probabilities: canonical-ID and primary-label matches score `1.0`; registered-alias matches score `0.9`. Resolution passes only when exactly one candidate exists and that candidate meets `min_confidence`. No candidates, multiple candidates (even if only one meets the threshold), or a sole candidate below the threshold return `TerminalStatus.OPERATOR_DISAMBIGUATION_REQUIRED` with `selected_asset=None` and retained candidate details for operator review.

This contract does not extract entities from free text and does not implement fuzzy/edit-distance matching, sensor or timestamp resolution, SPARQL/services, persistence, orchestration, or candidate-action integration. Callers must pass either a specific asset hint or a term already extracted by another boundary.

## Structured retrieval contract

The deterministic S4 structured-retrieval scaffold is `mfg_agentgraph.structured_retrieval`. It accepts a resolved `KnownAsset`, a caller-supplied Pump_12 scenario mapping, and opaque caller `retrieval_run_id` / `query_id` values.

```python
import json
from pathlib import Path

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.stage_instrumentation import TerminalStatus
from mfg_agentgraph.structured_retrieval import retrieve_structured_support

scenario = json.loads(Path("tests/fixtures/pump_12/scenario.json").read_text())
result = retrieve_structured_support(
    resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
    scenario=scenario,
    retrieval_run_id="run-issue-15",
    query_id="query-pump-12-anomalous-sound",
)

assert result.status is TerminalStatus.PASSED
assert tuple(ref.stable_id for ref in result.evidence_references) == ("ex:EvidenceEdge_001",)
```

The valid Pump_12 path validates the exact asset/location (`ex:Pump_12` at `ex:PumpStation_12`), observation/anomaly (`ex:Observation_Pump12_2026-05-18T14:03:00Z` with `anomalous_sound`), procedure (`ex:Procedure_InspectInletCavitation_Pump12`), and KG edge (`ex:EvidenceEdge_001`, `ex:hasRecommendedProcedure`). A passed result emits one validated `EvidenceKind.KG_EDGE` reference with deterministic retrieval metadata (`deterministic_structured_fixture`, rank `1`, score `1.0`) and an `EvidenceCatalog` that can resolve that stable edge ID as validated support. The observation ID remains traceable in the result and stage event, but it is not released as candidate support.

Semantic missing or mismatch cases return `TerminalStatus.INSUFFICIENT_EVIDENCE` with no support records, no evidence references, an empty evidence catalog, and a typed `StageError`. If KG-edge validation fails after the observation was validated, that observation can remain traceable in `result.observations` and `event.output_ids`. Public dataclass invariants reject contradictory passed/insufficient states, and opaque run/query IDs reject surrounding whitespace.

This Issue #15 scaffold remains the deterministic fixture implementation of the contract. It does not call Fuseki, perform persistence, select an orchestrator mode, or claim production retrieval behavior.

### Fuseki/SPARQL structured-retrieval adapter

`mfg_agentgraph.fuseki_structured_retriever` implements the same immutable Pump_12 result contract against an explicitly configured SPARQL 1.1 query endpoint. The caller supplies the endpoint, a factory-data named graph, distinct SHACL-shapes and provenance named graphs, the service-resource namespace, and a finite positive timeout. The adapter reads only the factory graph through an explicit `GRAPH <...>` clause; it does not infer a graph URI from a resource namespace or query a default/union graph.

```python
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.fuseki_structured_retriever import (
    FusekiStructuredRetriever,
    FusekiStructuredRetrieverConfig,
)

retriever = FusekiStructuredRetriever(
    FusekiStructuredRetrieverConfig(
        query_endpoint="http://127.0.0.1:3330/mfg/query",
        factory_graph="urn:mfg-agentgraph:graph:factory",
        shapes_graph="urn:mfg-agentgraph:graph:shapes",
        provenance_graph="urn:mfg-agentgraph:graph:provenance",
        resource_namespace="https://w3id.org/mfg-agentgraph/example#",
        timeout_seconds=5.0,
    )
)
result = retriever.retrieve(
    resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
    retrieval_run_id="run-fuseki-pump-12",
    query_id="query-pump-12-anomalous-sound",
)
```

The adapter sends one `POST` request with `application/sparql-query` and requires `application/sparql-results+json`. It rejects endpoint URLs containing credentials, query strings, or fragments; refuses redirects; ignores ambient HTTP-proxy environment variables; caps response size; rejects duplicate JSON keys; and strictly validates one complete result row before releasing support. Connection refusal, timeout, HTTP failure, wrong media type, malformed/oversized JSON, missing or duplicate rows, unknown namespaces, and semantic identity mismatches return sanitized `INSUFFICIENT_EVIDENCE` results with no observations, support records, or evidence references. There is no automatic retry and no fixture fallback. The library reads no endpoint from operator input or environment variables; a trusted caller must construct the configuration explicitly and must not pass operator-controlled endpoint or graph values.

The separately gated live-service test uses the minimal named-graph fixture at `tests/fixtures/fuseki/pump12.trig`. With an Apache Jena Fuseki distribution available as `FUSEKI_HOME`, start an ephemeral read-only service and run:

```bash
"$FUSEKI_HOME/fuseki-server" \
  --localhost \
  --port=3330 \
  --file=tests/fixtures/fuseki/pump12.trig \
  /mfg

MFG_AGENTGRAPH_FUSEKI_QUERY_ENDPOINT=http://127.0.0.1:3330/mfg/query \
  uv run pytest tests/integration/live_fuseki.py --no-cov -q
```

`tests/integration/live_fuseki.py` is deliberately outside the default pytest filename patterns and fails, rather than skips, when invoked without its endpoint variable. The variable configures only this explicit test; it is not a production fallback path. Issue #27 is read-only and Pump_12-specific: it does not load SHACL shapes, write provenance, configure authentication, switch the S4 orchestrator from fixtures, implement Qdrant retrieval, establish production deployment, or change Architecture V1.

## Procedural retrieval contract

The deterministic S4 procedural-retrieval scaffold is `mfg_agentgraph.procedural_retrieval`. It accepts the same resolved `KnownAsset`, the Pump_12 scenario mapping, and caller `retrieval_run_id` / `query_id` values, then validates the SOP document chunk that supports the previously identified cavitation procedure.

```python
import json
from pathlib import Path

from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.stage_instrumentation import TerminalStatus

scenario = json.loads(Path("tests/fixtures/pump_12/scenario.json").read_text())
result = retrieve_procedural_support(
    resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
    scenario=scenario,
    retrieval_run_id="run-issue-16",
    query_id="query-pump-12-sop-cavitation",
)

assert result.status is TerminalStatus.PASSED
assert tuple(ref.stable_id for ref in result.evidence_references) == ("ex:SOP_Chunk_7",)
```

The valid Pump_12 path validates the exact canonical asset (`ex:Pump_12`), canonical asset type (`centrifugal_pump`), procedure (`ex:Procedure_InspectInletCavitation_Pump12`), and SOP document chunk (`ex:SOP_Chunk_7` in `SOP-PUMP-OPS-2026`, chunk index `7`). A passed result emits one validated `EvidenceKind.DOCUMENT_CHUNK` reference with deterministic retrieval metadata (`deterministic_procedural_fixture`, rank `1`, score `1.0`) and an `EvidenceCatalog` that resolves `ex:SOP_Chunk_7` as validated support. The result and stage event are immutable and contradiction-resistant: direct construction rejects non-document evidence, unvalidated support, noncanonical IDs, altered Pump_12 SOP/procedure fields, mismatched run/query trace IDs, and catalog/reference drift.

Missing or inconsistent procedure, asset-type, or document-chunk data fails closed with `TerminalStatus.UNSUPPORTED_LOWER_RANK`, a typed `StageError`, no support records, no evidence references, an empty `EvidenceCatalog`, and no released stage output IDs. This preserves the Architecture V1 lower-rank/fallback boundary without returning partial or contradictory procedural support.

This Issue #16 scaffold is fixture-backed, dependency-free, and deterministic. It is not Qdrant, vector search, a production procedural retriever, service-backed indexing, persistence, orchestration, evaluation, or any Architecture V1 deviation; the production service/indexing work remains later Architecture V1 implementation.

### Qdrant/vector procedural-retrieval adapter

`mfg_agentgraph.qdrant_procedural_retriever` implements the same immutable Pump_12
procedural result contract against one explicitly configured Qdrant collection. A trusted
caller supplies the service base URL, collection name, score threshold, timeout, and query
vector; the adapter does not generate embeddings or read configuration from operator text or
ambient environment variables.

```python
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.qdrant_procedural_retriever import (
    QdrantProceduralRetriever,
    QdrantProceduralRetrieverConfig,
)

result = QdrantProceduralRetriever(
    QdrantProceduralRetrieverConfig(
        base_url="http://127.0.0.1:6333",
        collection_name="pump12-procedures",
        score_threshold=0.8,
        timeout_seconds=5.0,
    )
).retrieve(
    resolved_asset=KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",)),
    query_vector=(1.0, 0.0, 0.0, 0.0),
    retrieval_run_id="run-qdrant-pump-12",
    query_id="query-pump-12-sop-cavitation",
)
```

The adapter sends one `POST` to
`/collections/pump12-procedures/points/query`, with exact payload filters for the
canonical asset ID, centrifugal-pump type, and cavitation procedure. It requests payloads
but not stored vectors and uses `limit: 2` so zero or ambiguous results fail closed rather
than selecting a point silently. A passing response must contain exactly one finite score at
or above the configured threshold and the exact stable `ex:SOP_Chunk_7` payload. The Qdrant
score is retained in `RetrievalMetadata`; the existing deterministic retriever keeps its
fixed name and exact score of `1.0`.

Configuration rejects credentials in URLs, non-root paths, query strings, fragments,
malformed ports, unsafe collection names, nonfinite thresholds, and invalid timeouts. Query
vectors must be nonempty finite numeric sequences. The HTTP boundary refuses redirects,
ignores ambient proxy variables, caps response size, requires JSON, and rejects duplicate
keys. Connection, timeout, HTTP, response-shape, cardinality, score, and semantic failures
return sanitized `UNSUPPORTED_LOWER_RANK` results with no support, evidence, catalog entry,
or output ID. There is no retry and no fixture fallback.

Issue #29 adds a deterministic, versioned SOP indexing boundary. The pure
`build_procedural_index` function accepts strict configuration, UTF-8 source, and explicit
caller-supplied vector bytes and produces immutable chunks, stable evidence IDs/UUIDv5 point
IDs, exact source citations, canonical artifact bytes, and Qdrant request snapshots. It does
not generate embeddings. `execute_procedural_index` accepts only that completed plan plus a
trusted service configuration, verifies or creates the unnamed-vector collection and three
keyword payload indexes, and performs one waited same-ID upsert with no retry or delete.

```bash
MFG_AGENTGRAPH_QDRANT_BASE_URL=http://127.0.0.1:6333 \
  uv run pytest tests/integration/live_qdrant_indexing.py --no-cov -q
```

The explicit live indexing test builds the canonical artifact, indexes it twice, directly
reads the same UUID/payload/vector and exact collection count after each run, retrieves it
through the Issue #28 adapter, and removes its dedicated collection in `finally`. It is
verified against Qdrant 1.19.2 only. Production code never deletes or recreates an
incompatible collection, follows redirects, uses ambient proxies, retries, or retains raw
responses, source text, vectors, URLs, or exception messages in results. Partial write
outcomes remain conservative and operator-visible. Authentication, stale-point deletion,
embedding quality, orchestration switching, performance evaluation, and production
deployment remain out of scope.


## Deterministic fixture model-adapter contract

The fixture-only S4 stage-4 candidate-generation helper is `mfg_agentgraph.fixture_model_adapter.generate_fixture_candidate_actions`. It is deterministic and limited to the Pump_12 scenario: callers pass the scenario mapping, passed `StructuredRetrievalResult` and `ProceduralRetrievalResult` objects produced for the same query, a `generation_run_id`, the same `query_id`, and a typed `FixtureModelVariant.REPAIRED` or `FixtureModelVariant.INCOMPLETE`.

```python
import json
from pathlib import Path

from mfg_agentgraph.candidate_action import parse_candidate_actions
from mfg_agentgraph.entity_resolution import KnownAsset
from mfg_agentgraph.fixture_model_adapter import (
    FixtureModelVariant,
    generate_fixture_candidate_actions,
)
from mfg_agentgraph.procedural_retrieval import retrieve_procedural_support
from mfg_agentgraph.structured_retrieval import retrieve_structured_support

scenario = json.loads(Path("tests/fixtures/pump_12/scenario.json").read_text())
asset = KnownAsset("ex:Pump_12", "Pump 12", ("Pump_12",))
query_id = "query-pump-12-candidate-generation"
structured = retrieve_structured_support(
    resolved_asset=asset,
    scenario=scenario,
    retrieval_run_id="run-structured",
    query_id=query_id,
)
procedural = retrieve_procedural_support(
    resolved_asset=asset,
    scenario=scenario,
    retrieval_run_id="run-procedural",
    query_id=query_id,
)
generation = generate_fixture_candidate_actions(
    scenario=scenario,
    structured_result=structured,
    procedural_result=procedural,
    generation_run_id="run-generation",
    query_id=query_id,
    variant=FixtureModelVariant.REPAIRED,
)
plan = parse_candidate_actions(
    generation.raw_json,
    known_assets={"ex:Pump_12"},
    evidence_catalog=generation.evidence_catalog,
)
assert generation.candidate_id == "ex:CandidateAction_Pump12_Repaired_001"
assert plan.ranked_actions[0].target_asset == "ex:Pump_12"
```

The adapter requires canonical `ex:Pump_12`, matching asset/query identity across the two retrieval results, the validated KG edge `ex:EvidenceEdge_001`, and the SOP chunk `ex:SOP_Chunk_7`. Failed retrievals, identity drift, and invalid scenario fixture shapes fail closed with typed `FixtureModelAdapterError` codes. A successful call returns an immutable `FixtureCandidateGenerationResult` with deterministic raw CandidateAction JSON, the canonical fixture candidate ID, stable fixture model/prompt identifiers, a combined `EvidenceCatalog`, and a `PASSED` `StageEvent` for `CANDIDATE_GENERATION`.

`FixtureModelVariant.REPAIRED` emits JSON that parses through the existing `parse_candidate_actions` boundary. `FixtureModelVariant.INCOMPLETE` deliberately preserves the fixture gap (`null` target and empty support), so the existing parser rejects it with `INVALID_TARGET_ASSET`; the fixture adapter itself does not semantically validate or repair candidate JSON. This Issue #17 helper is service-free and standard-library-only. It is not a live LLM/provider/runtime client, production model-adapter port, retry/fallback layer, RDF/SHACL/repair controller, orchestrator, persistence layer, evaluation harness, new dependency, or Architecture V1 deviation. Issue #30 owns the production local model adapter, and Issue #20 owns repair.

## Opt-in local Ollama model-adapter proof

Issue #30 adds `mfg_agentgraph.ollama_model_adapter.OllamaCandidateAdapter` for one explicit local
candidate-generation call. It uses Ollama's native `POST /api/chat` endpoint with a bounded,
structured prompt, deterministic options, and the existing candidate-action parser. The adapter
accepts only canonical HTTP loopback roots (`http://127.0.0.1:<port>` or `http://[::1]:<port>`),
does not read environment variables, and performs no retry, fallback, model download, proxy use,
or raw-response retention.

The separately invoked live proof is opt-in and remains outside normal pytest collection:

```bash
MFG_AGENTGRAPH_OLLAMA_BASE_URL=http://127.0.0.1:11434 \
MFG_AGENTGRAPH_OLLAMA_MODEL=llama3.2 \
  uv run python tests/integration/live_ollama_model_adapter.py
```

Both variables are required. The script builds the canonical Pump_12 structured/procedural
fixture results, makes exactly one `generate` call, and prints a constant success marker only
after the result proves a passed Stage 4 event plus exact model, runtime, prompt, and schema
identity. Missing configuration, invalid runtime responses, and all other failures emit only a
constant sanitized failure marker. Importing the script performs no environment read, network
call, output, or mutation. The privacy boundary is the local loopback endpoint: prompts and model
responses are sent only to the explicitly configured local Ollama process; this proof does not
claim provider isolation beyond that endpoint or inspect/model-log what Ollama itself retains.

The adapter uses only Python's standard-library HTTP/JSON facilities because the repository
already has no Python Ollama client dependency and the required contract is one bounded native
HTTP call. The fixture adapter remains the default service-free path; this command does not switch
the orchestrator or evaluation harness to a live model. The decision supports R1 local deployment
and R4 candidate generation, with the live deployment boundary providing pending RQ4 evidence.
It does not claim recommendation safety or optimality, model quality, latency/memory results,
production readiness, durable provenance, or completion of the S1-S4 evaluation.

For Ollama compatibility, the wire JSON Schema intentionally omits string `maxLength` keywords:
Ollama's grammar compiler rejects the resulting large bounded repetitions. The schema still carries
the exact object/array structure, required and additional-property rules, action/evidence counts,
rank bounds, types, enums, and string `minLength`. After the response, the adapter's existing local
candidate-shape validation remains authoritative and fails closed at the frozen limits of 2048
characters/4096 UTF-8 bytes for an action, 1024 UTF-8 bytes for a target, and 8192 UTF-8 bytes for
an evidence ID. This is an implementation correction for the Ollama boundary, not an Architecture
V1 deviation.

## Stage instrumentation contract

The typed S4 stage-event contract is `mfg_agentgraph.stage_instrumentation`. It exposes the ten canonical Architecture V1 stage names and six typed terminal statuses required for later orchestration metrics.

```python
from mfg_agentgraph.stage_instrumentation import StageEvent, StageName, TerminalStatus

event = StageEvent(
    stage=StageName.SHACL_VALIDATION,
    run_id="run-001",
    status=TerminalStatus.VALIDATION_FAILED_CLOSED,
    input_ids=("candidate-action-001",),
    output_ids=("shacl-report-001",),
    retry_count=1,
    repair_count=1,
)
```

`StageEvent` and `StageError` are frozen/slotted dataclasses with runtime checks for typed enum fields, nonblank run and resource IDs, optional nonnegative duration placeholders, and nonnegative retry/repair counters. This is a contract-only stage instrumentation layer; it does not emit events from an orchestrator, measure real clocks, persist traces, validate evidence IDs, or implement the S4 pipeline.

## Evidence reference contract

Stable evidence references are defined in `mfg_agentgraph.evidence_reference`. They make KG resources, KG edges, and document chunks citable by later candidate-action, validation, evidence-package, and provenance contracts without adding retrievers or persistence yet.

```python
from mfg_agentgraph.evidence_reference import (
    EvidenceCatalog,
    EvidenceKind,
    EvidenceReference,
    EvidenceValidationStatus,
    RetrievalMetadata,
)

reference = EvidenceReference(
    kind=EvidenceKind.DOCUMENT_CHUNK,
    source="fixture-sop-corpus",
    stable_id="ex:SOP_Chunk_7",
    retrieval=RetrievalMetadata(
        retrieval_run_id="retrieval-run-001",
        query_id="query-001",
        retriever_name="fixture-vector-retriever",
        rank=1,
        score=0.83,
    ),
    validation_status=EvidenceValidationStatus.VALIDATED,
)
validated_support = EvidenceCatalog((reference,)).resolve_validated_support(("ex:SOP_Chunk_7",))
```

`EvidenceReference` and `RetrievalMetadata` are immutable contracts, while `EvidenceCatalog` normalizes its entries into a tuple-backed catalog. The catalog rejects duplicate IDs, rejects unknown IDs with a typed deterministic error, preserves requested resolution order, and separates ordinary lookup from `resolve_validated_support` so unvalidated or invalid references cannot be returned as valid support. This issue does not implement KG/vector retrievers, evidence packages, RDF/vector persistence, external services, or generated IDs.

## Candidate-action JSON contract

The model-output safety boundary is `mfg_agentgraph.candidate_action.parse_candidate_actions`. It accepts only strict JSON, resolves each target against caller-provided known assets, and resolves every support ID through `EvidenceCatalog` before returning immutable candidate actions. The example below continues from the evidence-reference example above and reuses its `EvidenceCatalog` import and `reference` object.

```python
from mfg_agentgraph.candidate_action import parse_candidate_actions

plan = parse_candidate_actions(
    """{
      "ranked_actions": [
        {
          "rank": 1,
          "action": "Inspect the pump inlet for cavitation",
          "target_asset": "ex:Pump_12",
          "support_evidence": [
            {"type": "document_chunk", "id": "ex:SOP_Chunk_7"}
          ]
        }
      ]
    }""",
    known_assets={"ex:Pump_12"},
    evidence_catalog=EvidenceCatalog((reference,)),
)
```

The parser rejects free text, malformed or ambiguous JSON, extra or missing fields, invalid rank sequences, unresolved assets, unknown or duplicated evidence IDs, evidence-kind mismatches, and evidence that is not validated support. Failures use stable `CandidateActionErrorCode` values and do not retain raw model output in the public error or its exception chain. This boundary does not run SHACL, repair candidates, invoke a model, or resolve entities; those remain later Architecture V1 stages.

## RDF action mapping contract

The S4 stage-5 RDF boundary is `mfg_agentgraph.rdf_action_mapper.map_candidate_action_to_rdf`. It accepts an already validated `CandidateAction` from `parse_candidate_actions`, a caller-supplied `URIRef` for the action, and an explicit mapping from every stable asset/evidence ID to the `URIRef` that should be written into the graph.

```python
from rdflib import URIRef

from mfg_agentgraph.rdf_action_mapper import map_candidate_action_to_rdf

resource_iris = {
    "ex:Pump_12": URIRef("ex:Pump_12"),
    "ex:EvidenceEdge_001": URIRef("ex:EvidenceEdge_001"),
    "ex:SOP_Chunk_7": URIRef("ex:SOP_Chunk_7"),
}
graph = map_candidate_action_to_rdf(
    plan.ranked_actions[0],
    action_iri=URIRef("ex:CandidateAction_Pump12_Repaired_001"),
    resource_iris=resource_iris,
)
```

The mapper uses RDFLib `>=7.6,<8`. The internal namespace `https://w3id.org/mfg-agentgraph/v1#` is a stable V1 package vocabulary for terms such as `mfg:RecommendedAction`, `mfg:targetAsset`, `mfg:rank`, and `mfg:hasSupportEvidence`; it is not a published ontology. The mapper resolves all IDs before creating a `Graph`, so missing target/evidence resources fail closed with stable `RdfActionMappingErrorCode` values and do not leave partial triples. It returns a new RDFLib `Graph` containing only the action type, exact `rdfs:label`, one target asset, integer rank, and support-evidence links.

This Issue #18 boundary does not implement support-graph assembly, SHACL validation or shapes (#19), persistence/Fuseki writes, evidence packages, provenance traces, orchestration, service-backed resource resolution, or later-stage release semantics.

## Recommended-action RDF assembly contract

The Issue #72 mapper-to-SHACL seam is `mfg_agentgraph.recommended_action_rdf_assembly.assemble_recommended_action_rdf`. It accepts an already validated `CandidateAction`, caller-supplied stable `URIRef`s for the action and all referenced resources, explicit anomaly-window start/end timestamps, one successful `StructuredRetrievalResult`, and one successful `ProceduralRetrievalResult`. It returns a frozen `RecommendedActionRdfGraphs` container holding new RDFLib graph snapshots: the existing structural action graph plus the complete support graph required by `validate_recommended_action`.

```python
from rdflib import URIRef

from mfg_agentgraph.recommended_action_rdf_assembly import assemble_recommended_action_rdf

assembled = assemble_recommended_action_rdf(
    plan.ranked_actions[0],
    action_iri=URIRef("http://example.org/CandidateAction_Pump12_Repaired_001"),
    resource_iris={
        "ex:Pump_12": URIRef("http://example.org/Pump_12"),
        "ex:Observation_Pump12_2026-05-18T14:03:00Z": URIRef(
            "http://example.org/Observation_Pump12_2026-05-18T14:03:00Z"
        ),
        "ex:Procedure_InspectInletCavitation_Pump12": URIRef(
            "http://example.org/Procedure_InspectInletCavitation_Pump12"
        ),
        "ex:EvidenceEdge_001": URIRef("http://example.org/EvidenceEdge_001"),
        "ex:SOP_Chunk_7": URIRef("http://example.org/SOP_Chunk_7"),
    },
    anomaly_window_start="2026-05-18T14:00:00Z",
    anomaly_window_end="2026-05-18T14:10:00Z",
    structured_result=structured,
    procedural_result=procedural,
)
```

The support graph supplies the target `mfg:Asset` and `mfg:assetType`, the cited `mfg:SupportEvidence` nodes, the KG-edge-to-`sosa:Observation` link, observation type/feature/result time, the document-evidence-to-`mfg:Procedure` link, procedure type/applicable asset type, and the action anomaly-window start/end literals. The boundary fails closed with sanitized `RecommendedActionRdfAssemblyErrorCode` values for malformed input types, unsuccessful retrieval statuses, candidate/retrieval identity drift, missing resource IRI mappings, unknown supported asset-type mappings, malformed timestamps, and reversed anomaly windows.

This assembly boundary deliberately does not retrieve, generate, repair, call SHACL, write RDF to a service, package evidence, write provenance, or release a recommendation. It checks structural seam invariants that would otherwise make graph assembly ambiguous; semantic constraints such as whether an observation timestamp falls inside the anomaly window remain owned by the real package SHACL validator.

## SHACL validation and report contract

The S4 stage-6 validation boundary is `mfg_agentgraph.shacl_validation.validate_recommended_action`. It validates one caller-selected `mfg:RecommendedAction` against package-owned SHACL shapes and returns a stable, machine-readable report rather than treating validator text or blank-node identities as the public contract.

```python
from rdflib import URIRef

from mfg_agentgraph.shacl_validation import validate_recommended_action

result = validate_recommended_action(
    action_graph,
    action_uri=URIRef("http://example.org/CandidateAction_Pump12_Repaired_001"),
    support_graph=support_graph,
    report_uri=URIRef("http://example.org/ValidationReport_Pump12_001"),
    run_id="run-pump-12-validation",
)

assert result.conforms is True
assert result.violations == ()
```

`action_graph` is the RDF action-mapper output. The caller-supplied `support_graph` must provide the complete validation context: the target as `mfg:Asset` with exactly one `mfg:assetType`; each cited resource as `mfg:SupportEvidence`; an evidence-to-`sosa:Observation` link with exactly one `sosa:hasFeatureOfInterest` and `sosa:resultTime`; exactly one action anomaly-window start/end; and an evidence-to-`mfg:Procedure` link whose single `mfg:applicableAssetType` matches the target type. The internal `mfg:` terms remain package vocabulary, not a published ontology.

The adapter copies both input graphs, scopes the package shapes to the requested `action_uri`, and uses PySHACL `>=0.40.1,<0.41` without optional HTTP, JavaScript, or Oxigraph extras. A conforming result emits a `PASSED` `SHACL_VALIDATION` stage event. Constraint failures return deterministic `ShaclViolation` records, a normalized RDF `sh:ValidationReport` under the caller's stable report URI, and `VALIDATION_FAILED_CLOSED` with `VALIDATION_CONSTRAINT_FAILED`. Invalid adapter inputs or validator-engine failures raise typed `ShaclValidationError` values and return no partial report. An unexpected validator exception also emits `shacl_validation_engine_error` through the opt-in `mfg_agentgraph.diagnostics` logger before the same sanitized error is raised.

The packaged shapes enforce target/evidence existence and typing, observation-target consistency, an inclusive anomaly window, and procedure applicability to the target asset type. This Issue #19 gate proves only that the encoded constraints passed; it does not prove that an action is optimal or safe. Issue #20 owns bounded repair, Issue #21 evidence-package assembly, Issue #22 provenance, and Issue #23 end-to-end orchestration/release gating.

## Bounded repair and explicit fallback contract

The S4 stage-7/8 controller is `mfg_agentgraph.bounded_repair.run_bounded_repair`. It consumes a `ShaclValidationResult`, classifies only package-owned actionable shape IDs, and invokes a caller-supplied repair callback no more than `retry_budget` times. The callback owns target resolution, retrieval, candidate regeneration, and fresh SHACL validation; the controller does not mutate RDF graphs or let a callback self-certify success without returning a new validation report.

The following fragment continues from the SHACL example above. `repair_and_revalidate` is an application callback that must return a freshly generated `ShaclValidationResult` with the same run/action identity and a new report ID:

```python
from mfg_agentgraph.bounded_repair import run_bounded_repair

outcome = run_bounded_repair(
    result,
    retry_budget=2,
    repair_attempt=repair_and_revalidate,
)

print(outcome.final_status)
print(outcome.repair_count, outcome.retry_count)
```

The repair policy is deliberately allow-listed:

- missing target identity/type shapes request `TARGET` repair (`resolve target + regenerate`) and exhaust to `OPERATOR_DISAMBIGUATION_REQUIRED`;
- missing observation, feature-of-interest, result-time, target-consistency, or anomaly-window shapes request `OBSERVATION` repair (`retrieve asset/time-window graph + regenerate`) and exhaust to `INSUFFICIENT_EVIDENCE`;
- missing or inapplicable procedure shapes request `PROCEDURE` repair (`ontology-filtered procedural retrieval + regenerate`) and exhaust to `UNSUPPORTED_LOWER_RANK`.

Same-class violations are deduplicated and sent in one deterministic request. Generic support failures, the root/delegating action shape, unknown shape IDs, and cross-class bundles are not auto-repaired; they fail closed without invoking the callback. After every accepted attempt, the fresh report is reclassified before another attempt is permitted.

`BoundedRepairOutcome` exposes immutable aggregation-ready counts: one initial validation, whether it initially failed, callback invocations (`repair_count`), structurally valid fresh reports consumed (`retry_count`), successful self-corrections, final validation, final status, and bounded-repair/fallback events. Callback exceptions produce `bounded_repair_attempt_error` through the opt-in `mfg_agentgraph.diagnostics` logger before returning the same sanitized `REPAIR_ATTEMPT_FAILED` outcome. Wrong return types, malformed violation records, reused or drifted report identity, conflicting report-graph identity, and inconsistent conformance/status values produce sanitized `REPAIR_ATTEMPT_FAILED` events without retaining rejected callback payloads. This boundary adds no dependency and does not implement the end-to-end orchestrator, evidence packages, provenance writes, persistence, service-backed retrieval/model calls, or recommendation release.

Applications may attach a standard-library logging handler to `mfg_agentgraph.diagnostics`. Unexpected engine/callback records are emitted at `ERROR` with a constant message and only `diagnostic_code`, `component`, `operation`, `run_id`, and, for repair callbacks, integer `attempt_index`. The hook never receives exception objects, types, messages, arguments, tracebacks, RDF graphs, candidate/callback payloads, prompts, or operator text. Expected validation failures, policy fallbacks, and successful operations do not emit these diagnostics. A failing application handler is isolated and cannot replace the existing fail-closed domain result.

## Evidence package assembly contract

The S4 stage-9 boundary is `mfg_agentgraph.evidence_package.assemble_evidence_package`. It assembles an immutable in-memory `EvidencePackage` and `StageEvent` from the *final* `CandidateAction`, its mapped RDF `action_graph`, the final passing `ShaclValidationResult`, and a passing `BoundedRepairOutcome`. The caller supplies `action_id`, `package_id`, the same explicit `resource_iris` stable-ID-to-`URIRef` mapping used by `map_candidate_action_to_rdf`, and ordered `typed_kg_evidence_ids` and `document_evidence_ids` (RDF resource URI strings). There must be at least one validated KG resource/edge and one validated document chunk. The package records the target asset IRI, run/action/report IDs, support IRIs, passing status, and a deterministic snapshot of the action graph triples.

The stage-6 adapter now records an isomorphism-stable digest of its input action graph in `ShaclValidationResult`. Stage 9 checks this digest against the supplied final graph, along with the report RDF's exact run/action/conformance identity, mapped target/support resources, and the bounded-repair terminal event. An incomplete, stale, conflicting, or blank-node-bearing action package returns `package=None` and a sanitized `INVALID_EVIDENCE_PACKAGE` stage-9 event with `VALIDATION_FAILED_CLOSED`; it does not rerun SHACL or leak the rejected input in an error message. The package ID is caller-supplied; it is **not** a persisted PROV-O trace ID. Stage 10 (#22) must write provenance before the orchestrator (#23) can release a recommendation, and SHACL conformance alone is not a safety or optimality guarantee. Existing RDFLib/PySHACL dependencies are reused; no new dependency was added. Contract coverage is in `tests/test_evidence_package_contract.py` and `tests/test_shacl_validation.py`.

## Deterministic PROV-O trace contract

The S4 stage-10 boundary is `mfg_agentgraph.provenance.write_provenance_trace`. It accepts one passing `EvidencePackage`, caller-supplied absolute IRIs for the trace, recommendation, S4 software agent, prompt, and model, a timezone-aware recorded timestamp, and the exact successful structured-retrieval, procedural-retrieval, candidate-generation, SHACL-validation, bounded-repair, and evidence-package stage events for the same run. It constructs a deterministic RDFLib graph using standard PROV-O entities, activities, agents, `prov:used`, `prov:wasGeneratedBy`, `prov:wasAssociatedWith`, and `prov:wasInformedBy` relationships.

The caller also supplies a persistence callback. The callback receives a fresh graph snapshot, and only a normal `None` return counts as an accepted write. A callback exception, non-`None` return, malformed evidence package, identity drift, missing or extra event, failed stage, or broken event linkage returns a sanitized `PROVENANCE_FAILED_CLOSED` event with no provenance ID, recommendation ID, or trace evidence. Therefore a caller cannot obtain the contract's releasable recommendation identity after a failed provenance write.

This is a deterministic local write-port contract, not a durability claim. It does not implement Fuseki, named-graph storage, an API response, the complete S4 orchestrator, retention enforcement, or access control. Callers and the later storage adapter must define retention periods, restrict access to operational evidence and potentially sensitive prompts, and avoid exposing trace contents to unauthorized users. The immutable returned triples prove what the local callback accepted for this call; they do not prove durable external persistence or recommendation safety. The callback owns transaction atomicity: if it partially writes and then raises, this boundary blocks release but cannot roll back that external side effect.

### Fuseki provenance adapter

`mfg_agentgraph.fuseki_provenance_store.FusekiProvenanceStore` is the explicit Stage-10 callback implementation. Construct it with separate loopback-only `http://127.0.0.1:PORT/path` or `http://[::1]:PORT/path` update and query endpoints and a trusted provenance graph base, then pass its bound method unchanged as `persist_trace=store.persist`:

```python
from mfg_agentgraph.fuseki_provenance_store import (
    FusekiProvenanceStore,
    FusekiProvenanceStoreConfig,
)

store = FusekiProvenanceStore(
    FusekiProvenanceStoreConfig(
        update_endpoint="http://127.0.0.1:3330/mfg/update",
        query_endpoint="http://127.0.0.1:3330/mfg/query",
        provenance_graph_base="https://example.org/mfg-agentgraph/provenance",
    )
)
# write_provenance_trace(..., persist_trace=store.persist)
```

The adapter canonicalizes the blank-node-free trace, writes one deterministic SHA-256-derived per-run named graph with `INSERT DATA`, and performs an exact canonical readback before returning. The hash-derived graph name provides isolation and pseudonymization, **not encryption or privacy**. Update or readback failure returns the existing sanitized `PROVENANCE_FAILED_CLOSED` Stage-10 result through the callback contract; after dispatch, external state may contain none, some, or all triples and is `DISPATCHED_UNKNOWN`. Production has no retry, rollback, or delete path. Retention, access control, authentication, and operational secret handling are deployment-owned. The adapter claims no safety, optimality, or durability beyond the exact graph confirmed at readback, and the demo's in-memory callback remains the unchanged default.

The opt-in live proof requires a dedicated test-owned Fuseki dataset and a unique trace ID. It fails when any variable is missing, preflights the derived graph as empty, persists once, resolves and compares the exact fresh graph, then deletes only the exact canonical triples it independently confirmed and verifies emptiness again. Never point it at a shared dataset:

```bash
MFG_AGENTGRAPH_FUSEKI_PROVENANCE_UPDATE_ENDPOINT=http://127.0.0.1:3330/mfg/update \
MFG_AGENTGRAPH_FUSEKI_PROVENANCE_QUERY_ENDPOINT=http://127.0.0.1:3330/mfg/query \
MFG_AGENTGRAPH_FUSEKI_PROVENANCE_GRAPH_BASE=https://example.org/mfg-agentgraph/test-provenance \
MFG_AGENTGRAPH_FUSEKI_PROVENANCE_TRACE_ID=https://example.org/mfg-agentgraph/live-trace/unique-1 \
  uv run pytest tests/integration/live_fuseki_provenance.py --no-cov -q
```

The live file is deliberately outside default pytest collection. Cleanup is never attempted after an uncertain dispatch unless exact ownership and persisted triples have been independently confirmed; cleanup failures fail the proof. This command is a proof of the bounded adapter contract, not a production deployment, retention, privacy, or durability guarantee.

## Deterministic Pump_12 orchestrator contract

The service-free S4 composition boundary is `mfg_agentgraph.pump12_orchestrator.run_pump12_orchestrator`. It accepts a raw operator request, the canonical Pump_12 scenario mapping, an explicit `AssetCatalog`, a query ID, frozen caller-owned stable IDs, an aware recorded timestamp, and the Stage 10 persistence callback. It reads no ambient clock, generates no identity, and performs no network I/O.

The conforming path composes the existing contracts in the canonical ten-stage order: entity resolution, structured retrieval, procedural retrieval, candidate generation, RDF reification, SHACL validation, bounded repair, explicit fallback decision, evidence-package assembly, and PROV-O trace writing. The repaired fixture candidate is used because the strict candidate parser deliberately rejects the incomplete fixture before RDF mapping. A passing SHACL report produces a no-op Stage 7 result, while Stage 8 records that fallback was evaluated and not selected; it does not claim a repair occurred.

`Pump12OrchestrationResult` is frozen and retains the immutable executed event prefix. On success, the action, evidence package, provenance ID, recommendation ID, and trace evidence are exposed together only after the persistence callback returns `None`. Every supported failure path returns only the prefix actually executed and leaves all release fields absent: ambiguity stops after Stage 1; structured/procedural retrieval failures stop after Stage 2/3; an allow-listed unknown-evidence parser failure stops after Stage 4 without retaining raw model output; SHACL-policy rejection or bounded-repair exhaustion stops after the real Stage 6–8 events; evidence-package rejection stops at Stage 9; and a callback exception or non-`None` return retains the successful Stage 1–9 prefix plus `PROVENANCE_FAILED_CLOSED`. Parser errors outside the explicit orchestration allow-list and unrelated exceptions continue to raise rather than being mislabeled as another failure class.

The deterministic valid path and Issue #24 failure slice prove component composition and all-or-nothing release gating for the supported Pump_12 fixture boundaries. Test-only call-through wrappers corrupt boundary inputs while still invoking the real parser, SHACL validator, bounded-repair controller, evidence-package assembler, and provenance writer; they are not production dependency-injection ports. This contract does not implement live Fuseki/Qdrant/model adapters, durable transactions, a general malformed-input policy, or recommendation safety/optimality. The Fuseki adapter is an opt-in callback; the demo path remains in memory.
