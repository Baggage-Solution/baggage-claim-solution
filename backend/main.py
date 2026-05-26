from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.core.logging import configure_logging
from backend.core.middleware import RequestContextMiddleware
from backend.api.routes import health, webhook, decision

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
    allow_origins=["*"],        # POC only — restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(webhook.router)
app.include_router(decision.router)
