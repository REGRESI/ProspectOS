.PHONY: db dev api migrate seed-demo test lint typecheck build smoke
UV_CACHE_DIR ?= /tmp/prospectos-uv
export UV_CACHE_DIR
db:
	docker compose up -d db
dev:
	pnpm dev
api:
	cd services/api && uv run --env-file ../../.env uvicorn app.main:app --host 0.0.0.0 --port 8000
migrate:
	cd services/api && uv run --env-file ../../.env python -m app.migrate
seed-demo:
	cd services/api && uv run --env-file ../../.env python -m app.seed
test:
	cd services/api && uv run pytest
	pnpm test
lint:
	cd services/api && uv run ruff check .
	pnpm lint
typecheck:
	pnpm typecheck
build:
	pnpm build
smoke:
	curl --fail --silent http://127.0.0.1:8000/health/ready
