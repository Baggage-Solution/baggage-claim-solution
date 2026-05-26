from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.masking import mask_sensitive_text, mask_sensitive_value


_request_id_ctx_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys())
_MESSAGE_PREFIX_RE = re.compile(r"^\[(?P<component>[^\]]+)\]\s*(?P<message>.*)$")
_VERBOSE_TEXT_FIELDS = {
    "message",
    "question",
    "query",
    "incoming_query",
    "last_user_message",
}
_BOUNDARY_MESSAGE_SUFFIXES = (
    "_started",
    "_completed",
    "_failed",
    "_hit",
    "_miss",
    "_skipped",
    "_stored",
    "_finalized",
)


def generate_request_id() -> str:
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    return _request_id_ctx_var.get(None)


def bind_request_id(request_id: str | None) -> Token:
    return _request_id_ctx_var.set(request_id)


def reset_request_id(token: Token) -> None:
    _request_id_ctx_var.reset(token)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        component = None
        m = _MESSAGE_PREFIX_RE.match(msg)
        if m:
            component = m.group("component")
            msg = m.group("message")

        extra: Dict[str, Any] = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_RECORD_FIELDS and not k.startswith("_")
        }

        for field in _VERBOSE_TEXT_FIELDS:
            if field in extra and isinstance(extra[field], str):
                extra[field] = mask_sensitive_text(extra[field])

        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": msg,
            "request_id": current_request_id(),
        }
        if component:
            payload["component"] = component
        if extra:
            payload["extra"] = {k: mask_sensitive_value(k, v) for k, v in extra.items()}
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class _PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        req_id = current_request_id()
        prefix = f"[{req_id[:8]}] " if req_id else ""
        return f"{record.levelname:<8} {prefix}{record.name} — {record.getMessage()}"


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter() if fmt == "json" else _PlainFormatter())
    root.addHandler(handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, logger_name: str = "baggage_claim.http"):
        super().__init__(app)
        self._logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        req_id = current_request_id() or "unknown"

        self._logger.info(
            "http_request_started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "request_id": req_id,
            },
        )

        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        self._logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "request_id": req_id,
            },
        )
        return response
