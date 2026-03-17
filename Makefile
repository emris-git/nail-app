POETRY_RUN=poetry run

.PHONY: install
install:
	poetry install

.PHONY: dev
dev:
	$(POETRY_RUN) uvicorn app.asgi:app --reload --host 0.0.0.0 --port $${PORT:-8000}

.PHONY: bot-polling
bot-polling:
	$(POETRY_RUN) python -m app.main --polling

.PHONY: lint
lint:
	$(POETRY_RUN) ruff check .
	$(POETRY_RUN) black --check .

.PHONY: fmt
fmt:
	$(POETRY_RUN) black .
	$(POETRY_RUN) ruff check . --fix

.PHONY: typecheck
typecheck:
	$(POETRY_RUN) mypy app tests

.PHONY: test
test:
	$(POETRY_RUN) pytest

.PHONY: migrate
migrate:
	$(POETRY_RUN) alembic upgrade head

.PHONY: migrate-new
migrate-new:
	$(POETRY_RUN) alembic revision --autogenerate -m "$(m)"

