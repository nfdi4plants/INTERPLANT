# INTERPLANT

INTERPLANT makes public DataPLANT ARCs findable on the AWI Earth Data Portal
([earth-data.de](https://earth-data.de)).

An ARC (Annotated Research Context) is a plant-science project kept as a git
repository, with its metadata in ISA-XLSX files, on
[git.nfdi4plants.org](https://git.nfdi4plants.org). Those repositories are
public, but a researcher looking for, say, proteomics data from a given
organism cannot search across them. INTERPLANT reads them, turns each ARC into
one structured catalog record, and publishes the records in a form the portal
can harvest.

The project is a DataPLANT 2026 Community Call project, run at FZJ IBG-3. The
application and budget are in [`proposal/`](proposal/).

## Live service

OGC API - Records is the ingestion path: AWI's harvester reads it nightly and
the DataPLANT records in the portal's index come from it. The OAI-PMH endpoint
stays up as a proven fallback. Never register both with AWI at the same time.

## How it works

```mermaid
flowchart LR
    subgraph DP["DataPLANT (source - read only)"]
        ARCs[("Public ARCs<br/>git.nfdi4plants.org<br/>ISA-XLSX metadata")]
    end
    subgraph VM["INTERPLANT - interplant-live VM"]
        H["Harvester - nightly 02:00<br/>enumerate, filter, dedup<br/>parse ISA (arctrl)<br/>classify + enrich<br/>build + validate record"]
        S[("staging.records")]
        G{"Publish gate<br/>+ atomic swap"}
        P[("Postgres + PostGIS<br/>public.records (JSONB)<br/>+ catalog SQL views")]
        Y["catalog/collections/*.yaml<br/>(thematic collections)"]
        OGC["pygeoapi<br/>OGC API - Records<br/>plabipd.de/ogc"]
        OAI["Flask OAI-PMH<br/>plabipd.de/oai<br/>(fallback)"]
    end
    subgraph AWI["AWI Earth Data Portal"]
        AH["o2a harvester<br/>OGCAPIRecordsHarvester"]
        EDP["earth-data.de<br/>search index"]
    end
    U["Researchers<br/>browser, QGIS, scripts"]
    ARCs -->|"GitLab API +<br/>shallow clone"| H
    H --> S --> G -->|"only if corpus<br/>passes the floor"| P
    Y -->|"make catalog-gen"| OGC
    P --> OGC
    P --> OAI
    OGC -->|"nightly full harvest"| AH
    OAI -.->|"parked, never<br/>registered together"| AH
    AH --> EDP --> U
    OGC --> U
```

1. **Harvest.** A nightly systemd timer (02:00) runs `harvester refresh`. It
   lists public ARCs through the GitLab API and only harvests when that list
   changed or the last publish is older than 7 days. It filters and
   deduplicates the ARCs,
   shallow-clones each one. It
   classifies the omics type, enriches organism, license and
   location, builds one record per ARC and validates it against
   [`record.schema.json`](docs/specs/schemas/record.schema.json).
2. **Stage and gate.** Records go into `staging.records`. A publish gate
   compares the corpus against a floor and refuses one that looks truncated.
   If it passes, an atomic swap moves the corpus into `public.records`.
3. **Serve.** pygeoapi publishes the records over OGC API - Records through
   SQL views. `arc-records` holds every record; the omics collections and the
   ARC locations collection are generated from `catalog/collections/*.yaml`
   by `make catalog-gen`. A Flask service
   serves the same records as OAI-PMH, mapped to AWI's DocumentSchema.
4. **Portal.** AWI's harvester fleet takes a full dump of the OGC API every
   night, using the `OGCAPIRecordsHarvester` and a DataPLANT harvest script we
   wrote (those files are kept outside this repository). AWI expires records it
   no longer sees after 5 days, which is why step 2 refuses a truncated corpus.

## Project

![Timeline](proposal/Gantt_Chart_INTERPLANT.png)

Status: the harvester, the OGC API - Records service (with branded HTML pages
and a location collection) and the OAI-PMH fallback are in production, and
the portal ingests through OGC API - Records.

## Developing

### Prerequisites

- Docker (current user in the `docker` group, or use `sudo`)
- [uv](https://docs.astral.sh/uv/)
- Python >= 3.12 (uv provisions one if absent)

### Quickstart

```bash
git clone git@gitlab.fz-juelich.de:ibg-3/data-management/projects/interplant.git
cd interplant
uv sync --dev
make up           # Postgres + PostGIS and pygeoapi (docker compose)
make test-all     # spec, harvester and stack tests
```

To get a populated local OGC API from the test fixtures:

```bash
make catalog-up   # up, generate catalog, harvest tests/fixtures/arcs, apply views
```

| Local endpoint | URL |
|---|---|
| pygeoapi collections | http://localhost:5000/collections |
| pygeoapi OpenAPI | http://localhost:5000/openapi |
| pygeoapi conformance | http://localhost:5000/conformance |
| OAI-PMH (after `make oai-up`) | http://localhost:8001/oai |
| Postgres | `postgresql://interplant:interplant@localhost:5432/interplant` |

The compose stack is for local development and CI only. Its published Postgres
port and default password are acceptable only on a laptop.

### Running the harvester

`python -m harvester` has three subcommands:

| Subcommand | Use |
|---|---|
| `ingest <arc_path>` | Ingest one ARC directory into Postgres. |
| `harvest` | Batch-harvest many ARCs (`--source live` or `--local-dir`), optionally `--dry-run`. Writes a JSON and Markdown audit report to `--out-dir`. |
| `refresh` | Production entry point: harvest into staging, then publish through the gate. Needs `INTERPLANT_PG_DSN`. |

```bash
uv run python -m harvester ingest ARCs/ArcPrototype-main --dsn postgresql://...
uv run python -m harvester --help
```

### Make targets

Run `make help` for the full list. The common ones:

| Target | What it does |
|---|---|
| `make up` / `down` / `restart` | Start, stop or restart the compose stack |
| `make logs` / `psql` | Tail logs, open a psql shell |
| `make clean` | Tear down the stack and delete the Postgres volume |
| `make test` | Spec tests only (no Docker) |
| `make test-harvester` | Harvester unit tests |
| `make test-harvester-db` | Harvester DB-backed tests (stack must be up) |
| `make test-stack` | Stack smoke tests (stack must be up) |
| `make test-all` | Everything |
| `make harvest-prototype` | Ingest `ARCs/ArcPrototype-main` locally |
| `make harvest-all` | Harvest all live public ARCs into the local Postgres |
| `make harvest-dryrun` | Harvest live ARCs, validate only, no DB writes |
| `make catalog-gen` | Regenerate catalog SQL and the pygeoapi config from `catalog/collections/*.yaml` |
| `make catalog-views` | Apply the catalog views to the local Postgres |
| `make brand-assets` | Regenerate `ogc/static/img` from `ogc/brand/src` |
| `make oai-up` | Build and start the OAI-PMH endpoint |
| `make lint` / `format` | `ruff check` / `ruff format` |

### Testing

`tests/` has `specs`, `harvester`, `oai`, `portal`, `stack` and `templates`.
The tests in `tests/stack/` and the `db`-marked harvester tests need a running
Postgres and are gated by `INTERPLANT_STACK_TESTS=1`. A plain `pytest` skips
them. `make test-stack`, `make test-harvester-db` and `make test-all` set the
gate for you.

CI (`.gitlab-ci.yml`) runs `ruff check .` first, then `pytest` against a
PostGIS service. A green pytest alone does not mean CI passes, so run
`make lint` too before pushing.

### Repository map

| Path | Contents |
|---|---|
| `harvester/` | The harvest pipeline: enumeration, filters, dedup, ISA parsing, `classifiers/`, `extractors/`, `geodata/`, record building, DB upsert, `publish.py` (gate and swap), `cli.py` |
| `catalog/collections/` | YAML descriptors for the thematic collections |
| `sql/` | Catalog views, generated collection SQL, read-only role setup |
| `scripts/` | `generate_catalog.py`, `apply_catalog_views.py`, `generate_brand_assets.py` and probe/utility scripts |
| `pygeoapi-config.base.yml`, `pygeoapi-config.yml` | pygeoapi configuration (the latter is generated by `make catalog-gen`) |
| `ogc/` | Branded HTML templates, static files and brand sources for the OGC API |
| `oai/` | Flask OAI-PMH endpoint |
| `deploy/` | systemd units, `install.sh`, env example, deployment runbook |
| `docs/` | Specs, diagrams, harvester handbook, Postman collection |
| `proposal/` | Project application, budget, Gantt chart |
| `tests/` | Test suites and fixtures |
| `compose.yaml` | Local dev and CI stack |

## Production

Production runs natively under systemd on `interplant-live` (units in
[`deploy/`](deploy/)). pygeoapi is the one containerised service. Install,
upgrade, verification and what to do when the gate refuses a corpus are in
[`deploy/README.md`](deploy/README.md).

Do not run a manual `DELETE FROM records` against production. Stale records
are pruned automatically: `harvester refresh` stages a full harvest and swaps
it into `public.records` in one transaction, so records for ARCs that vanished
upstream disappear on the next publish. A hand-deleted or truncated corpus is
exactly what AWI would pick up, and their harvester expires entries it no
longer sees after 5 days.

## Further documentation

- [`docs/specs/README.md`](docs/specs/README.md): record schema, collection schema, portal mapping, harvester spec, JSON schemas and vocabularies
- [`docs/diagrams/`](docs/diagrams/): architecture, data model, harvester pipeline and OAI flow diagrams
- [`docs/harvester-handbook.md`](docs/harvester-handbook.md): portal and taxonomy notes
- [`deploy/README.md`](deploy/README.md): production operations
- [`ogc/brand/README.md`](ogc/brand/README.md): branding of the OGC HTML pages

## License

Apache License 2.0, see [`LICENSE`](LICENSE).
