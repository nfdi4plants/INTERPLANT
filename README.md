# INTERPLANT

## Project timeline
![Timeline](proposal/Gantt_Chart_INTERPLANT.png)

## [Project Board](https://gitlab.fz-juelich.de/ibg-3/data-management/projects/interplant/-/boards)

## Meeting space
- [Matrix room](https://matrix.to/#/!QwWKp0StvFM0u_wvZR83dabW7SbiWMCJN5HhljqYdyQ?via=helmholtz.cloud)


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
