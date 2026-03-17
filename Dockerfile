FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --upgrade pip && pip install poetry

COPY pyproject.toml README.md ./
RUN poetry install --only main --no-root

COPY . .

ENV PORT=8000

CMD ["poetry", "run", "uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]

