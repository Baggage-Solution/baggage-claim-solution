from __future__ import annotations

# ── Windows asyncio fix — MUST be the very first thing in this file ──────────
# uvicorn --reload spawns a child worker process. The policy must be set at
# module import time inside that worker, before uvicorn creates its event loop.
# Setting it in a run.py or __main__ guard is too late when --reload is used.
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ─────────────────────────────────────────────────────────────────────────────

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import decision, health, qr, webhook
from backend.config import get_settings
from backend.core.logging import configure_logging
from backend.core.middleware import RequestContextMiddleware

settings = get_settings()
configure_logging(level=settings.log_level, fmt=settings.log_format)

app = FastAPI(
    title="Baggage Damage Claim — WhatsApp AI",
    description="ABC Airline POC — 3-Week Sprint",
    version="0.1.0",
)

# ── Middleware (order matters — RequestContext first) ─────────────────────────
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # POC only — restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(webhook.router)
app.include_router(decision.router)
app.include_router(qr.router)  # T-018 — QR code generation

# ── Static file serving — uploaded claim photos ───────────────────────────────
# Serves damage + bag tag photos at /uploads/{claim_id}/{filename}
# Used by the agent dashboard (T-017) to display claim photos for review.
# Phase 2 swap: replace with Cloudflare R2 or S3 signed URLs.
os.makedirs("data/uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")
