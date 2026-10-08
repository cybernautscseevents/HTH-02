"""ASGI entry point: `uvicorn backend.main:app --port 8000`."""

from backend.stewardship.api import create_app

app = create_app()
