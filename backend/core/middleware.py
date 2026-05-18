from __future__ import annotations

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.logging import bind_request_id, generate_request_id, reset_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Assigns a request_id to every incoming request (from header or generated),
    binds it to a ContextVar for structured logging, and echoes it in response headers.
    Direct copy from Proj A enterprise-chatbot-framework.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or generate_request_id()
        start = time.perf_counter()
        token = bind_request_id(request_id)
        request.state.request_id = request_id

        try:
            response: Response = await call_next(request)
        finally:
            reset_request_id(token)

        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = str(int((time.perf_counter() - start) * 1000))
        return response
