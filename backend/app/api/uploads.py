"""HTTP body helpers: bounded reads and in-memory multipart parsing.

Starlette's form parser spools files over 1 MB to disk; uploads here never
touch the disk and are never read past the size cap.
"""

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

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


@dataclass(frozen=True)
class FilePart:
    filename: str
    data: bytes


@dataclass(frozen=True)
class FormData:
    fields: dict[str, str]
    files: dict[str, FilePart]


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def parse_multipart(content_type: str, body: bytes) -> FormData:
    ctype, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if ctype != b"multipart/form-data" or not boundary:
        raise _unprocessable("Malformed multipart body")

    parts: list[tuple[dict[bytes, bytes], bytes]] = []
    headers: dict[bytes, bytes] = {}
    field, value, data = bytearray(), bytearray(), bytearray()

    def on_part_begin() -> None:
        headers.clear()
        data.clear()

    def on_header_field(chunk: bytes, start: int, end: int) -> None:
        field.extend(chunk[start:end])

    def on_header_value(chunk: bytes, start: int, end: int) -> None:
        value.extend(chunk[start:end])

    def on_header_end() -> None:
        headers[bytes(field).lower()] = bytes(value)
        field.clear()
        value.clear()

    def on_part_data(chunk: bytes, start: int, end: int) -> None:
        data.extend(chunk[start:end])

    def on_part_end() -> None:
        parts.append((dict(headers), bytes(data)))

    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
        },
    )
    try:
        parser.write(body)
        parser.finalize()
    except MultipartParseError:
        raise _unprocessable("Malformed multipart body") from None

    fields: dict[str, str] = {}
    files: dict[str, FilePart] = {}
    for part_headers, part_data in parts:
        _, options = parse_options_header(part_headers.get(b"content-disposition", b""))
        name = options.get(b"name", b"").decode("utf-8", "replace")
        filename = options.get(b"filename")
        if filename is not None:
            files[name] = FilePart(filename.decode("utf-8", "replace"), part_data)
        else:
            try:
                fields[name] = part_data.decode("utf-8")
            except UnicodeDecodeError:
                raise _unprocessable("Form fields must be UTF-8") from None
    return FormData(fields, files)
