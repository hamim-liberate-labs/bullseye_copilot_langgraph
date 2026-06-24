"""
FastAPI application entrypoint — the LangGraph Bullseye Copilot gateway.

Wires the v1 router (login, chat, chat/stream, artifacts), open CORS for the
experiment, and optional serving of the built frontend. Run with:
    uvicorn bullseye_copilot.main:app --port 8000
or via ../run.py for reload.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from bullseye_copilot.api.v1.router import api_router
from bullseye_copilot.core.config import FRONTEND_DIST
from bullseye_copilot.core.logging_config import setup_logging

setup_logging()

app = FastAPI(title="Bullseye Copilot Gateway (LangGraph)")

# Experiment-wide open CORS; tighten to the frontend origin before any deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# ── Frontend (production build) ───────────────────────────────────────────────

if FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/bullseye-logo.svg", include_in_schema=False)
    async def logo() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "bullseye-logo.svg")
