"""HTTP body helpers: bounded reads and the HTTP mapping of multipart errors.

Uploads are never read past the size cap; parsing lives in services/multipart.py.
"""

from fastapi import HTTPException, Request, status

from app.services import multipart
from app.services.multipart import FormData

# Room for multipart boundaries, part headers and small form fields.
MULTIPART_OVERHEAD = 64 * 1024


def _too_large() -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE, detail="Request body is too large"
    )


def media_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";", 1)[0].strip().lower()


async def read_bounded(request: Request, limit: int) -> bytes:
    """The request body, or 413 as soon as it exceeds ``limit`` bytes.

    A declared Content-Length over the limit is rejected before reading.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise _too_large()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise _too_large()
    return bytes(body)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def parse_multipart(content_type: str, body: bytes) -> FormData:
    """The service parser, with its errors mapped to 422."""
    try:
        return multipart.parse_multipart(content_type, body)
    except multipart.MalformedMultipart as exc:
        raise _unprocessable(exc.detail) from None
