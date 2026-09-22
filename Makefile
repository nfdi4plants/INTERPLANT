.PHONY: help up down restart logs psql serve test test-stack test-harvester test-harvester-db test-all harvest-prototype harvest-all harvest-dryrun catalog-views catalog-gen brand-assets catalog-up oai-up lint format clean

DSN ?= postgresql://interplant:interplant@localhost:5432/interplant

# Per-ARC arctrl parse budget for diagnostic dry runs. Empty means no limit,
# which is what harvest-all uses: a slow ARC is still valid data.
DRYRUN_PARSE_TIMEOUT ?= 300

help:
	@echo "INTERPLANT - local development targets"
	@echo ""
	@echo "  make up         Bring the stack up (Postgres + pygeoapi)"
	@echo "  make down       Stop the stack (keeps the volume)"
	@echo "  make restart    Restart the stack"
	@echo "  make logs       Tail logs from both services"
	@echo "  make psql       Open a psql shell against the local Postgres"
	@echo "  make serve      Alias for 'up'"
	@echo "  make test       Run the spec tests (no stack needed)"
	@echo "  make test-stack Run the stack smoke tests (requires the stack up)"
	@echo "  make test-all   Run all tests (spec + stack)"
	@echo "  make test-harvester      Run harvester unit tests"
	@echo "  make test-harvester-db   Run harvester db-backed tests (requires the stack up)"
	@echo "  make harvest-prototype   Ingest ARCs/ArcPrototype-main into the local Postgres"
	@echo "  make harvest-all         Batch-harvest all live public ARCs into the local Postgres"
	@echo "  make harvest-dryrun      Batch-harvest live ARCs in dry-run mode (validate only)"
	@echo "                           Bounded by DRYRUN_PARSE_TIMEOUT=$(DRYRUN_PARSE_TIMEOUT)s per ARC"
	@echo "  make catalog-views       Apply the catalog serving views to the local Postgres"
	@echo "  make catalog-gen         Regenerate catalog views + pygeoapi config from descriptors"
	@echo "  make brand-assets        Regenerate ogc/static/img from ogc/brand/src"
	@echo "  make catalog-up          Up + harvest fixtures + apply views (serving stack)"
	@echo "  make oai-up               Build + start the OAI-PMH endpoint (http://localhost:8001/oai)"
	@echo "  make lint       Run ruff check"
	@echo "  make format     Run ruff format"
	@echo "  make clean      Tear down the stack AND delete the Postgres volume"

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down
	docker compose up -d

logs:
	docker compose logs -f

psql:
	docker compose exec db psql -U interplant -d interplant

serve: up

test:
	uv run pytest tests/specs -v

test-stack:
	INTERPLANT_STACK_TESTS=1 uv run pytest tests/stack -v

test-all:
	INTERPLANT_STACK_TESTS=1 uv run pytest -v

test-harvester:
	uv run pytest tests/harvester -v

test-harvester-db:
	INTERPLANT_STACK_TESTS=1 uv run pytest tests/harvester -v -m db

harvest-prototype:
	INTERPLANT_STACK_TESTS=1 uv run python -m harvester ingest ARCs/ArcPrototype-main

harvest-all:
	uv run python -m harvester harvest --source live --dsn $(DSN)

harvest-dryrun:
	uv run python -m harvester harvest --source live --dry-run --parse-timeout $(DRYRUN_PARSE_TIMEOUT)

catalog-views:
	uv run python scripts/apply_catalog_views.py $(DSN)

catalog-gen:
	uv run python scripts/generate_catalog.py

brand-assets:
	uv run python scripts/generate_brand_assets.py

catalog-up: up catalog-gen
	uv run python -m harvester harvest --local-dir tests/fixtures/arcs --dsn $(DSN)
	uv run python scripts/apply_catalog_views.py $(DSN)

oai-up: up
	docker compose up -d --build oai

lint:
	uv run ruff check .

format:
	uv run ruff format .

clean:
	docker compose down -v
