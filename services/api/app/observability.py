"""Bound request bodies and log operational metadata without query strings or PII."""

from fastapi import HTTPException
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        limit = (
            6 * 1024 * 1024
            if path.endswith("/assets/upload")
            else (3 * 1024 * 1024 + 65536 if path.endswith("/imports/preview") else 256 * 1024)
        )
        headers = dict(scope.get("headers", []))
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            content_length = limit + 1
        if content_length > limit:
            return await JSONResponse(
                {"code": "body_too_large", "message": "Upload exceeds request limit."},
                status_code=413,
            )(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Upload exceeds request limit.")
            return message

        await self.app(scope, bounded_receive, send)
