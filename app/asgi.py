from __future__ import annotations

from fastapi import FastAPI

from app.api.main import create_app

app: FastAPI = create_app()

