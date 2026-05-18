"""
Trace middleware — adiciona X-Trace-ID a todas as requests.
"""
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        # Expose to downstream handlers (audit emitter reads this).
        request.state.trace_id = trace_id

        response: Response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
