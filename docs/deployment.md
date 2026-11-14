# Local deployment envelope

The implementation study runs on one fixed, free, local stack: Apache Jena Fuseki
(TDB2) for the knowledge graph, Qdrant for procedural vectors, and Ollama for the
local models. The envelope is frozen by
`thesis-wiki/wiki/implementation-study-protocol-v1.md`; this page records how to
start it and what it does not promise.

## Pinned identities

| Component | Image | Licence |
|---|---|---|
| Fuseki 6.2.0 (TDB2, via `deploy/fuseki/`) | `secoresearch/fuseki:6.2.0@sha256:74833bbf…` | Apache-2.0 |
| Qdrant 1.19.2 | `qdrant/qdrant:v1.19.2@sha256:b7b0444c…` | Apache-2.0 |
| Ollama 0.23.2 | `ollama/ollama:0.23.2@sha256:d00473cb…` | MIT |
| Generation model | `qwen2.5:7b-instruct-q4_K_M` | Apache-2.0 |
| Embedding model | `nomic-embed-text` v1.5 | Apache-2.0 |
| MIMII audio (bootstrap download, `#115`) | Zenodo 3384388 | CC BY-SA 4.0 |

`deploy/compose.yaml` carries the full digests. The trailing `…` above is
documentation shorthand only; never copy a shortened digest into the compose file.

`stain/jena-fuseki` stops at 5.1.0, so the protocol's Fuseki 6.2.0 is served by
`secoresearch/fuseki`, which publishes a `6.2.0` tag. This substitution is
recorded in `wiki/implementation-decisions.md`.

## Start the stack

```bash
cp deploy/env.example deploy/.env      # then edit MFG_FUSEKI_ADMIN_PASSWORD
docker compose -f deploy/compose.yaml --profile cpu up -d
uv run mfg-agentgraph-stack bootstrap    # load graphs, create collection, pin models
uv run mfg-agentgraph-stack doctor       # exits non-zero on any mismatch
```

`bootstrap` precedes `doctor` because the gate checks exactly what `bootstrap`
creates. On a cold stack `bootstrap` also downloads `qwen2.5:7b-instruct-q4_K_M`
(4.68 GB) and `nomic-embed-text` (274 MB), so the first run takes as long as the
transfer does: the pull is bounded by `MFG_OLLAMA_PULL_TIMEOUT_SECONDS` (default
3600 s), never by the 5 s readiness timeout.

`mfg-agentgraph-stack` reads `deploy/.env` from the current directory when no
environment is supplied (override with `--env-file PATH`); a real environment
variable always takes precedence. That makes one file configure both Compose and
the CLI, including the published ports and the Fuseki admin password.

`status` prints the resolved configuration without touching the network:

```bash
uv run mfg-agentgraph-stack status
```

### Profiles

- `--profile cpu` starts Ollama on CPU. This is the default student profile and
  the one WSL2 users should start with.
- `--profile gpu` starts the GPU variant and requires the NVIDIA Container
  Toolkit. Without a compatible host the profile fails; it never silently falls
  back to CPU.
- No profile starts only Fuseki and Qdrant, and `doctor` then fails on Ollama —
  by design.

### WSL2

Docker must be reachable from the distribution, not only from Windows. In Docker
Desktop, enable *Settings → Resources → WSL integration* for this distribution.
If `docker version` reports `could not be found in this WSL 2 distro`, the stack
cannot start and `doctor` correctly reports every service as unreachable.

## What bootstrap does

`bootstrap` is idempotent and never destroys data silently:

| Target | Missing | Identical | Different |
|---|---|---|---|
| factory graph | loaded | reported `already_present` | `refused` unless `--recreate` |
| shapes graph | loaded | reported `already_present` | `refused` unless `--recreate` |
| Qdrant collection | created at the configured size and distance (`768`, `Cosine`) | `already_present` | `refused` (a collection is never deleted) |
| model | pulled, then re-verified by digest | `already_present` | `failed` (a digest mismatch is not a pull problem) |

Sources default to the committed factory TriG fixture and the packaged SHACL
shapes. Issue `#115` replaces the factory source with the versioned scenario
corpus; until then the default path is the repository fixture.

Fuseki publishes `/ds/data` and `/ds/update` as **read-only** unless
`ENABLE_DATA_WRITE` and `ENABLE_UPDATE` are true, so `deploy/compose.yaml` sets
both. Bootstrap and provenance persistence depend on them; with either off, every
write fails and `bootstrap` reports a failed step rather than a partial success.

## Endpoint and authentication facts (verified against the pinned images)

These were confirmed by running the pinned images, not assumed:

| Behaviour | Reality |
|---|---|
| SPARQL query endpoint | `http://127.0.0.1:3030/ds/sparql` — the image's assembler names the service `sparql`; `/ds/query` returns 405 |
| `GET /$/ping` | 200 with an ISO-8601 timestamp body; it does **not** return `pong` |
| `GET /$/server` | **401 without credentials**; 200 with HTTP basic auth once `ADMIN_PASSWORD` is set |
| Graph Store Protocol | `POST|PUT /ds/data?graph=<iri>` works once `ENABLE_DATA_WRITE=true` |

Because `/$/server` is authenticated, `MFG_FUSEKI_ADMIN_PASSWORD` is a real
configuration input, not just a container variable: `doctor` uses it to verify the
Fuseki version and reports an explicit authentication failure when it is missing
rather than silently skipping the check. The password is never printed by
`status` and never included in an error message.

The query service name is configurable (`MFG_FUSEKI_QUERY_SERVICE`, default
`sparql`) because it is a property of the pinned image, not of the SPARQL
protocol.

## TDB2 dataset

The image ships a **TDB1** assembler. The protocol fixes TDB2, so
`deploy/fuseki/configuration/assembler.ttl` and `deploy/fuseki/config.ttl` replace
the image's files with `tdb2:DatasetTDB2` at `/fuseki-base/databases/tdb2`, keeping
the Lucene text index. Verified live: `databases/tdb2/Data-0001` appears after
startup. Both files are derived from the pinned image and must be re-diffed if the
image pin changes.

The tracked configuration is mounted **read-only** at `/fuseki-config`, and the
compose `entrypoint` copies it into the container's own `/fuseki-base` before
handing over to the image entrypoint. The copy is required, not cosmetic: the image
entrypoint applies `ENABLE_DATA_WRITE`, `ENABLE_UPDATE` and `ENABLE_SHACL` by
rewriting those files with `sed -i`. Mounting them directly made a stack start
mutate tracked repository files, and binding the files individually instead fails
with `Resource busy`. Seeding a container-local copy keeps the repository immutable
while the image's rewrite logic still runs.

The server-wide ARQ query timeout is therefore a repository fact:
`arq:queryTimeout` is `30000` in `deploy/fuseki/config.ttl`. The image's
`QUERY_TIMEOUT` environment knob is deliberately unused, so the timeout is not a
property of whoever started the container. A different envelope belongs to the
measured protocol, not to this file.

## Ollama binding

The published port is bound to `127.0.0.1` on the host, and the container listens on
`0.0.0.0:11434` inside it. Both halves are required: Docker forwards published
traffic to the container interface, so an in-container bind of `127.0.0.1` is
unreachable from the host even though the container healthcheck passes. Host
exposure is still loopback-only.

## Network use

- Bootstrap-only: image pull, model pull, and (from `#115`) the MIMII download.
- Runtime: no outbound connection. The transport ignores environment proxies and
  does not follow redirects, so a redirect from a configured loopback endpoint is
  surfaced as its own status rather than followed.

## Verifying the envelope end to end

`tests/integration/live_stack.py` is the live acceptance proof and is excluded from
the default suite. It refuses every default: the three service URLs must be exported
explicitly, and the admin password is read through the same loader the CLI uses.
It exercises compose health and pinned identities, a second `bootstrap` that must
report `already_present` for every step, and forced container replacement of Fuseki
and Qdrant that must preserve an RDF provenance marker and a stored vector point
(Qdrant normalizes vectors on write for a `Cosine` collection, so the point is
compared by direction, not raw bytes).

```bash
export MFG_AGENTGRAPH_LIVE_STACK=1 MFG_STACK_COMPOSE_PROJECT=mfg-issue114-live
export MFG_FUSEKI_URL=http://127.0.0.1:23030 MFG_QDRANT_URL=http://127.0.0.1:23333
export MFG_OLLAMA_URL=http://127.0.0.1:31434
uv run pytest tests/integration/live_stack.py -m integration --no-cov
```

The test creates one uniquely named marker and one uniquely identified point and
deletes only those two; it never drops a collection or a volume.

## Loopback posture

`StackConfig` is the only place endpoints are constructed, and it rejects any
host outside `127.0.0.1`, `::1` and `localhost` unless `allow_non_loopback` is set
explicitly. The existing service clients (`fuseki_structured_retriever`,
`qdrant_procedural_retriever`, `ollama_model_adapter`, `fuseki_provenance_store`)
still accept a caller-supplied URL; the application layer must supply them from
`StackConfig` rather than from operator input. The API in `#124` is where that
becomes a hard boundary.

**Loopback excludes remote hosts, not other processes on this machine.** Publishing
on `127.0.0.1` keeps the services off the network, but every local process can still
reach them, and the pinned services are not authenticated for data-plane access:
Fuseki's data/update endpoints run with `ENABLE_DATA_WRITE` and `ENABLE_UPDATE` so
bootstrap and provenance writes work, Qdrant has no API key configured, and Ollama
provides no authentication mechanism at all. A local process can therefore write
those named graphs, delete collections, or trigger model downloads; `--recreate` is
a guard against operator mistakes, not an authorization boundary.

The envelope is therefore a **single-operator** stack: run it on a machine you
control, on a single-user host, and treat anything already able to run code as
already trusted. Multi-user hosts need OS-level isolation (a dedicated user or a
separate VM/container network), and restricting data-plane access belongs to a
protocol amendment or to the `#124` service boundary, not to a silent change here.
Detecting this is out of scope for `doctor`, which verifies the deployment, not the
host's trust model.

## Loading the scenario corpus

`uv run mfg-agentgraph-corpus load evaluation/scenario-corpus-v1/corpus-v1.json` publishes the
release through the same idempotent bootstrap used above, with one substitution: the target
graph is `urn:mfg-agentgraph:graph:corpus-context` instead of the factory graph. The factory and
provenance graphs are therefore never touched by a corpus load, and a divergent corpus graph is
refused unless `--recreate` is passed.

Isolation is **by named graph, not by Fuseki dataset**: the pinned assembler declares exactly one
dataset (`ds`), so a second dataset would need a second Fuseki service, which the frozen envelope
does not include. Recorded as an implementation decision.

## Deliberately out of scope

- Latency, memory and throughput numbers: measured by `#131`.
- Real embeddings and the corpus: `#117` and `#115`.
- Any hosted or paid fallback.

## Failure is reported, not hidden

`doctor` prints one line per check and exits non-zero if any check fails. There is
no fixture fallback anywhere on this path: an unreachable service is a failure,
not a degraded mode.

Ollama's `/api/tags` reports a **bare hexadecimal** digest while the pinned identity
is written `sha256:<hex>`; `doctor` and `bootstrap` compare the hexadecimal body on
both sides, so a matching model is never reported as a mismatch.
