from __future__ import annotations

# ── P-009 — Simulator feature flag applied here ───────────────────────────────
# /uploads static mount and future simulator-specific routes are gated on
# settings.enable_simulator. /dashboard, /webhook, /decision, /qr, /health
# are ALWAYS mounted — they are production routes airline ops depends on.
#
# Author: Anoushka (unified branch — P-009)

# ── Windows asyncio fix — MUST be the very first thing in this file ──────────
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ─────────────────────────────────────────────────────────────────────────────

import logging
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

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Baggage Damage Claim — WhatsApp AI",
    description="ABC Airline — AWS Production Phase",
    version="0.2.0",
)

# ── Middleware (order matters — RequestContext first) ─────────────────────────
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # POC only — restrict in production via ALB / API GW
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core routes — ALWAYS mounted (production + dev) ───────────────────────────
app.include_router(health.router)
app.include_router(webhook.router)
app.include_router(decision.router)
app.include_router(qr.router)

# ── Simulator-gated routes — ONLY when ENABLE_SIMULATOR=true ─────────────────
# The simulator code is NOT deleted. It lives here, conditionally activated.
# Local dev: set ENABLE_SIMULATOR=true in .env
# Production ECS task definition: omit the variable (defaults to False)
# /dashboard is a production route for airline ops staff — never gated here.
if settings.enable_simulator:
    logger.info(
        "simulator_enabled — mounting /uploads static files",
        extra={"enable_simulator": True},
    )
    os.makedirs("data/uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")
else:
    logger.info(
        "simulator_disabled — /uploads not mounted (ENABLE_SIMULATOR=false)",
        extra={"enable_simulator": False},
    )