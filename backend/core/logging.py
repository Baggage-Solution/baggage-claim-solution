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
    """Generate a new UUID4 string as a unique request identifier.

    Returns:
        str: A UUID4 string (e.g. "550e8400-e29b-41d4-a716-446655440000").
    """
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    """Return the request_id bound to the current async context, or None.

    Returns:
        str | None: The active request_id, or None outside a request context.
    """
    return _request_id_ctx_var.get(None)


def bind_request_id(request_id: str | None) -> Token:
    """Bind a request_id to the current async context.

    Args:
        request_id: The ID to bind. Pass None to clear.

    Returns:
        Token: ContextVar token — pass to reset_request_id to unset.
    """
    return _request_id_ctx_var.set(request_id)


def reset_request_id(token: Token) -> None:
    """Reset the request_id ContextVar to its previous value.

    Args:
        token: Token returned by bind_request_id.
    """
    _request_id_ctx_var.reset(token)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """Serialise a LogRecord as a JSON string with PII masking applied."""
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
        """Serialise a LogRecord as a human-readable plain-text string."""
        req_id = current_request_id()
        prefix = f"[{req_id[:8]}] " if req_id else ""
        return f"{record.levelname:<8} {prefix}{record.name} — {record.getMessage()}"


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure the root logger with the specified level and formatter.

    Sets up a single StreamHandler to stdout. Clears any existing handlers
    to avoid duplicate log lines when called multiple times (e.g. in tests).

    Args:
        level: Log level string — "DEBUG", "INFO", "WARNING", "ERROR".
        fmt: Formatter type — "json" (default) or "plain" (human-readable).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter() if fmt == "json" else _PlainFormatter())
    root.addHandler(handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that logs each HTTP request/response with structured fields.

    Not added to the main app by default (RequestContextMiddleware is used instead),
    but available for environments that need explicit request logging.
    """

    def __init__(self, app, *, logger_name: str = "baggage_claim.http"):
        super().__init__(app)
        self._logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log HTTP request start and completion with method, path, and status.

        Args:
            request: Incoming Starlette request.
            call_next: ASGI middleware chain callable.

        Returns:
            Response: Downstream response passed through unchanged.
        """
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
