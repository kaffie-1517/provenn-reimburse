BACKEND := cd backend &&

.PHONY: infra infra-down install migrate seed api worker test lint web demo

infra:        ## postgres, minio, prometheus, grafana
	docker compose up -d

infra-down:
	docker compose down -v

install:
	$(BACKEND) uv sync
	cd web && npm install

migrate:
	$(BACKEND) uv run alembic upgrade head

seed:         ## demo accounts + sample activity
	$(BACKEND) uv run python -m app.seed --with-activity

api:
	$(BACKEND) uv run uvicorn app.main:app --reload --port 8000

worker:
	$(BACKEND) uv run python -m app.worker

test:         ## needs a postgres; set TEST_DATABASE_URL to override
	$(BACKEND) uv run pytest -q

lint:
	$(BACKEND) uv run ruff check app tests && uv run ruff format --check app tests
	cd web && npm run lint

web:
	cd web && npm run dev

demo:         ## make demo KEY=pk_...
	$(BACKEND) uv run python scripts/partner_demo.py $(KEY)
