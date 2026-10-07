.PHONY: install dev-infra migrate dev api worker scheduler mock web lint typecheck test gen-client check-client compose-up load-test

install:            ## Install Python and JS dependencies
	uv sync --all-packages --all-groups
	pnpm install

migrate:            ## Apply migrations, create checkpoint tables, seed demo data
	cd apps/api && uv run python -m app.db.migrate

api:                ## FastAPI on :8000
	cd apps/api && uv run uvicorn app.main:app --reload --port 8000

worker:             ## arq worker
	cd apps/api && uv run python -m app.workers.worker

scheduler:          ## scheduler (enqueues only)
	cd apps/api && uv run python -m app.workers.scheduler

mock:               ## Demo jobs MCP server over Streamable HTTP on :8811
	uv run python -m mock_mcp.jobs_server --http --port 8811

web:                ## Next.js on :3000
	pnpm --filter @agent-platform/web dev

lint:
	pnpm turbo run lint

typecheck:
	pnpm turbo run typecheck

test:
	pnpm turbo run test

gen-client:         ## Regenerate the TS client from FastAPI's OpenAPI schema
	bash scripts/gen-client.sh

check-client:       ## Fail if the committed client is stale (CI)
	bash scripts/gen-client.sh --check

compose-up:         ## Whole stack in Docker
	docker compose -f infra/docker-compose.yml up --build

load-test:          ## Start N concurrent demo executions and report timings
	cd apps/api && uv run python ../../scripts/load_test.py --executions 50
