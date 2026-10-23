"""In-memory multipart/form-data parsing; no web framework imports.

Starlette's form parser spools files over 1 MB to disk; uploads here never
touch the disk. Errors carry fixed messages only (never body content).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header


class MalformedMultipart(Exception):
    """The body is not valid multipart/form-data."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class FilePart:
    filename: str
    data: bytes


@dataclass(frozen=True)
class FormData:
    fields: dict[str, str]
    files: dict[str, FilePart]


@dataclass
class _Collector:
    """Receives the parser's callbacks and accumulates complete parts."""

    parts: list[tuple[dict[bytes, bytes], bytes]] = field(default_factory=list)
    headers: dict[bytes, bytes] = field(default_factory=dict)
    name: bytearray = field(default_factory=bytearray)
    value: bytearray = field(default_factory=bytearray)
    data: bytearray = field(default_factory=bytearray)

    def on_part_begin(self) -> None:
        self.headers.clear()
        self.data.clear()

    def on_header_field(self, chunk: bytes, start: int, end: int) -> None:
        self.name.extend(chunk[start:end])

    def on_header_value(self, chunk: bytes, start: int, end: int) -> None:
        self.value.extend(chunk[start:end])

    def on_header_end(self) -> None:
        self.headers[bytes(self.name).lower()] = bytes(self.value)
        self.name.clear()
        self.value.clear()

    def on_part_data(self, chunk: bytes, start: int, end: int) -> None:
        self.data.extend(chunk[start:end])

    def on_part_end(self) -> None:
        self.parts.append((dict(self.headers), bytes(self.data)))

    def callbacks(self) -> dict[str, Callable[..., None]]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
        }


def _boundary(content_type: str) -> bytes:
    ctype, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if ctype != b"multipart/form-data" or not boundary:
        raise MalformedMultipart("Malformed multipart body")
    return boundary


def _split_parts(parts: list[tuple[dict[bytes, bytes], bytes]]) -> FormData:
    fields: dict[str, str] = {}
    files: dict[str, FilePart] = {}
    for headers, data in parts:
        _, options = parse_options_header(headers.get(b"content-disposition", b""))
        name = options.get(b"name", b"").decode("utf-8", "replace")
        filename = options.get(b"filename")
        if filename is not None:
            files[name] = FilePart(filename.decode("utf-8", "replace"), data)
            continue
        try:
            fields[name] = data.decode("utf-8")
        except UnicodeDecodeError:
            raise MalformedMultipart("Form fields must be UTF-8") from None
    return FormData(fields, files)


def parse_multipart(content_type: str, body: bytes) -> FormData:
    collector = _Collector()
    parser = MultipartParser(_boundary(content_type), callbacks=collector.callbacks())
    try:
        parser.write(body)
        parser.finalize()
    except MultipartParseError:
        raise MalformedMultipart("Malformed multipart body") from None
    return _split_parts(collector.parts)
