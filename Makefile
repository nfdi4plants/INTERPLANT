.PHONY: help up down restart logs psql serve test test-stack test-all lint format clean

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

lint:
	uv run ruff check .

format:
	uv run ruff format .

clean:
	docker compose down -v
