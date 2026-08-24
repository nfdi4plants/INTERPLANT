# INTERPLANT

## Project timeline
![Timeline](proposal/Gantt_Chart_INTERPLANT.png)

## [Project Board](https://gitlab.fz-juelich.de/ibg-3/data-management/projects/interplant/-/boards)

## Meeting space
- [Matrix room](https://matrix.to/#/!QwWKp0StvFM0u_wvZR83dabW7SbiWMCJN5HhljqYdyQ?via=helmholtz.cloud)

## Where do we stand? (regularily updated)

What's done (P0 → P1)

- P0 - Specs: all four specs + JSON schemas + vocabularies shipped (record-schema, collection-schema, portal-mapping/DocumentSchema, harvester).
- Dev stack: Postgres 17 + PostGIS 3.6 + pygeoapi, CI shell - merged.
- P1 - Harvester walking skeleton: full pipeline exists and writes to Postgres: enumerate → isa_reader → classify → build_record → validate → idempotent upsert (ON CONFLICT into a JSONB records table). CLI orchestrates it.
- P1 - Enrichment: organism / license / file_counts extractors + omics & experiment-context classifiers (omics coverage 11%→27%).
- Omics accuracy: unified vocab → 8 schema-enum values, a technology-signal tier, and a hand-labelled gold-set regression gate. Accuracy 28.3% baseline → 42.4% on the deduplicated 92-row gold set; 105 tests green, lint clean.
- P1 - Batch harvest: `harvester harvest` enumerates all public ARCs, clones each (stateless temp clone), runs the shared pipeline, upserts into Postgres, and writes a JSON+Markdown audit artifact. `make harvest-all` runs it locally; a non-blocking nightly CI job validates the live upstream; a fixture gate protects the pipeline on every push.
- P2 - Catalog API (omics): pygeoapi serves the records over OGC API - Records as `arc-records` (all records) plus 7 omics thematic collections (`dataplant-proteomics`, `-transcriptomics`, `-genomics`, `-metabolomics`, `-phenotyping`, `-imaging`, `-microbiome`). Collections are generated from `catalog/collections/*.yaml` descriptors via `make catalog-gen` (single source of truth) over flattening SQL views. Null geometry for now. `make catalog-up` brings up a populated serving stack.
- P2 - Portal feed (OAI-PMH): a Flask service (`oai/`) serves the records as an OAI-PMH 2.0 data provider (`make oai-up`, http://localhost:8001/oai), mapping each record to AWI's DocumentSchema. Full 6-verb compliance, `oai_dc` + `documentschema` formats, resumption tokens. The DocumentSchema-in-XML encoding is provisional pending AWI confirmation.


What's not done

- P2 - Catalog API (remainder): experiment_context collections (blocked on the demoted classifier) and real geometry. OAI-PMH endpoint done; public HTTPS hosting + AWI registration are deployment/ops follow-ups.
- P4/P5: 11 L1 collection descriptors + narrative; overview pages / portal plugin.
- registering as an Earth Data Portal content provider with AWI (o2a-support@awi.de) for sandbox access.


## Local development

Bring up Postgres+PostGIS and pygeoapi locally, then run the test suite.

### Prerequisites

- Docker (with the current user in the `docker` group, or use `sudo`).
- [uv](https://docs.astral.sh/uv/) for Python dependency management.
- Python >= 3.12 (uv will provision one if absent).

### First-time setup

```bash
git clone git@gitlab.fz-juelich.de:ibg-3/data-management/projects/interplant.git
cd interplant
uv sync --dev
make up
make test-all
```

### Useful URLs (once `make up` is running)

| Endpoint | URL |
|---|---|
| Postgres DSN | `postgresql://interplant:interplant@localhost:5432/interplant` |
| pygeoapi /collections | http://localhost:5000/collections |
| pygeoapi /openapi | http://localhost:5000/openapi |
| pygeoapi /conformance | http://localhost:5000/conformance |

### Common workflows

- Run only the spec tests (no Docker needed): `make test`
- Run the stack smoke tests against the running compose stack: `make test-stack`
- Tail logs: `make logs`
- Open a psql shell: `make psql`
- Reset the Postgres volume if data is wedged: `make clean && make up`

### How the test gate works

`tests/stack/` is gated by the env var `INTERPLANT_STACK_TESTS=1`. A plain `pytest` invocation will skip the whole package so it does not blow up when the stack is down. The `make test-stack` and `make test-all` targets set the gate automatically.

### Harvester (walking skeleton)

The `harvester/` package ingests one ARC into Postgres end-to-end. Skeleton scope: one ARC at a time, omics-only classifier, no audit log, no nightly schedule. Quality filter, dedup, audit logging, experiment-context classifier, and scheduling are deferred to Plan 4.

End-to-end smoke ingest:

```bash
make up                  # bring Postgres + pygeoapi up (Plan 2 stack)
make harvest-prototype   # parse + classify + upsert ARCs/ArcPrototype-main into local Postgres
make psql                # inspect: SELECT id, payload->>'type' FROM records;
```

Unit tests (no stack required):

```bash
make test-harvester
```

DB-backed tests (requires `make up`):

```bash
make test-harvester-db
```

The harvester accepts any ARC root directory:

```bash
uv run python -m harvester ingest /path/to/some/ARC --dsn postgresql://...
```

`arctrl` (DataPLANT's ISA-XLSX library) handles parsing. The pipeline is: `IsaReader.read()` -> minimal omics classifier (folder-name + regex vocab) -> `build_record()` -> JSON-schema validation against `docs/specs/schemas/record.schema.json` -> idempotent `INSERT ... ON CONFLICT` upsert into the `records` table.

## Production

The public endpoint runs on `interplant-live` and is served natively, not under
Docker. See [`deploy/README.md`](deploy/README.md) for install, upgrade and
verification steps.

`compose.yaml` remains the local development and CI stack. It is not the
production mechanism, and its published Postgres port and default password are
acceptable only on a laptop.

Stale records are pruned automatically: `harvester refresh` stages a full harvest
and swaps it into `public.records` in one transaction, so records for ARCs that
vanished upstream disappear on the next publish. Do not run a manual
`DELETE FROM records` against production - a truncated corpus is what AWI would
publish, and their harvester expires entries on a 5-day TTL.
