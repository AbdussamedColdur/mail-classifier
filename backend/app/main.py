"""MailKarar backend. Run with: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, config, db, engine, migrate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    migrate.run()
    config.seed_rules()
    engine.resume_interrupted_tasks()
    engine.start()
    yield


app = FastAPI(title="MailKarar", lifespan=lifespan)
app.include_router(api.router)

# After `npm run build` the backend serves the built front end itself on the same port.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
