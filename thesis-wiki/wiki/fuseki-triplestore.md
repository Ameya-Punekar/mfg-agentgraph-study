# Apache Jena Fuseki

**Summary**: Apache-2.0 SPARQL 1.1 triplestore with native RDF/OWL, SHACL, and PROV-O support. The KG store for MFG-AgentGraph. Supports standalone, embedded, and Docker deployment modes with TDB2 persistent storage.

**Sources**: `thesis-pitch-v2.md` §6, §7; `raw/apache-jena-fuseki-docs.md` (verified).

**Last updated**: 2026-05-11.

**Thesis relevance**: RQ2 (ontology storage), RQ4 (local deployment).

---

## What it is

Apache Jena Fuseki — a SPARQL 1.1 server distributed under Apache-2.0. Provides the SPARQL 1.1 protocols for query and update as well as the SPARQL Graph Store protocol. Integrated with TDB2 for robust, transactional, persistent storage. Also incorporates Jena text query for full-text search. (source: apache-jena-fuseki-docs.md, w3.org/TR/sparql11-protocol)

Available as:
- **Standalone server** — `fuseki-server` command-line
- **Docker container** — `jena/fuseki` image (ideal for thesis [[local-deployment]])
- **Embedded SPARQL server** — programmatic Java API
- **WAR file** — for servlet containers

Maven artifact: `org.apache.jena:jena-fuseki-main` (source: apache-jena-fuseki-docs.md)

## What it stores in MFG-AgentGraph

- Asset graph (`PumpStation_12`, `Pump_12`, etc.) typed against [[ssn-sosa]].
- Maintenance and alarm history.
- Sensor observations (`sosa:Observation` from MIMII anomaly detector).
- [[shacl-validation|SHACL]] shapes (constraints).
- [[prov-o|PROV-O]] activity records (one per agent run).

(source: thesis-pitch-v2.md §6 steps 1–2, step 6, §8 layer 3)

## Why it fits the thesis

- **W3C-standard SPARQL 1.1** — defensible for a "standards-based" thesis.
- **Native SHACL support** — Jena includes a SHACL engine (`jena-shacl` module with Javadoc) for S4's self-correction loop without an external service. (source: apache-jena-fuseki-docs.md — SHACL listed in References and Javadoc sections)
- **Apache-2.0** — compatible with the open-source release goal.
- **Docker deployment** — single-container setup for reproducible local deployment (RQ4).
- **TDB2 transactions** — ACID-compliant writes protect against concurrent agent access corruption.
- **Text search integration** — Jena text query can complement SPARQL for hybrid retrieval if needed.
- **GeoSPARQL module** — available as Fuseki module if spatial queries over plant-floor layout are needed (out of current scope). (source: apache-jena-fuseki-docs.md)

## Deployment recommendations for thesis

| Option | Use case | Recommendation |
|---|---|---|
| **TDB2** | Persistent storage for production evaluation runs | ✅ **Recommended** — robust, transactional, persistent |
| TDB1 | Legacy | ❌ Avoid — TDB2 supersedes |
| In-memory | Unit tests, CI | ✅ For test harness only |
| **Docker** | Reproducible thesis evaluation environment | ✅ **Recommended** for RQ4 local deployment |

**PROV-O storage pattern**: Use **separate named graphs** — one named graph per agent run (e.g., `<urn:prov:run:2026-05-11T15:00:00>`) containing all PROV-O triples for that execution. This allows per-run SPARQL queries (e.g., "show me the provenance of the last triage decision") without filtering overhead. The SSN/SOSA observation graph stays in the default graph.

**SHACL validation pattern**: Jena SHACL runs **on demand** via the `jena-shacl` API, not on ingest. The [[langgraph-agent]] SHACL-validation tool node calls the Jena SHACL validator programmatically after each LLM-generated plan, receives a `ValidationReport`, and routes to either the answer node (conformant) or the self-correction node (non-conformant). (source: apache-jena-fuseki-docs.md SHACL section; thesis-pitch-v2.md §6 step 4)

## Fuseki configuration for thesis

Key configuration endpoints per dataset (source: apache-jena-fuseki-docs.md — Fuseki Configuration link):

| Endpoint | Protocol | Thesis use |
|---|---|---|
| `/dataset/query` | SPARQL 1.1 Query | S4 SPARQL tool reads |
| `/dataset/update` | SPARQL 1.1 Update | Sensor observation ingestion |
| `/dataset/data` | SPARQL Graph Store | Named graph management for PROV-O |

Security: Apache Shiro integration available for authentication if the thesis demo needs access control. Data access control documented separately. (source: apache-jena-fuseki-docs.md)

## Client access from Python

Use `SPARQLWrapper` or `rdflib` with the Fuseki SPARQL endpoint. The `RDFConnection` API is available for Java clients. For the thesis's Python-based [[langgraph-agent]], `SPARQLWrapper` is the standard pattern:

```python
from SPARQLWrapper import SPARQLWrapper, JSON
sparql = SPARQLWrapper("http://localhost:3030/mfg/query")
sparql.setQuery("SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10")
sparql.setReturnFormat(JSON)
results = sparql.query().convert()
```

## Open questions (resolved)

- ~~TDB1 vs. TDB2~~ → **TDB2** (resolved: TDB2 is current, transactional, recommended)
- ~~PROV-O storage pattern~~ → **Separate named graphs per run** (resolved)
- ~~SHACL endpoint pattern~~ → **On-demand via jena-shacl API** (resolved)

## Remaining open questions

- **Fuseki memory footprint** for the thesis-scale KG (~10k triples for MIMII + asset ontology + PROV traces) — likely fits in <256MB heap. Measure during Phase 2.
- **Concurrent access** if the evaluation harness runs multiple queries in parallel — TDB2 transactions handle this, but benchmark throughput.

## Related pages

- [[ssn-sosa]]
- [[shacl-validation]]
- [[prov-o]]
- [[kg-agent-s4]]
- [[mfg-agentgraph]]
- [[local-deployment]]
- [[langgraph-agent]]
- [[references-master]]
