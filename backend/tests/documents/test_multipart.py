"""services/multipart.py: parsing and fixed-message errors, without HTTP."""

import pytest

from app.services.multipart import MalformedMultipart, parse_multipart

CT = "multipart/form-data; boundary=XX"


def _body(*parts: tuple[str, bytes]) -> bytes:
    out = b""
    for headers, data in parts:
        out += b"--XX\r\n" + headers.encode() + b"\r\n\r\n" + data + b"\r\n"
    return out + b"--XX--\r\n"


def test_parses_fields_and_files() -> None:
    body = _body(
        ('Content-Disposition: form-data; name="title"', "héllo".encode()),
        (
            'Content-Disposition: form-data; name="file"; filename="a.txt"',
            b"\x00\xffraw",
        ),
    )
    form = parse_multipart(CT, body)
    assert form.fields == {"title": "héllo"}
    assert form.files["file"].filename == "a.txt"
    assert form.files["file"].data == b"\x00\xffraw"


@pytest.mark.parametrize(
    "content_type",
    ["multipart/form-data", "application/json", "multipart/form-data; boundary="],
)
def test_missing_boundary_or_wrong_type_is_malformed(content_type: str) -> None:
    with pytest.raises(MalformedMultipart) as info:
        parse_multipart(content_type, b"")
    assert info.value.detail == "Malformed multipart body"


def test_non_utf8_field_is_rejected_without_echoing_it() -> None:
    body = _body(('Content-Disposition: form-data; name="title"', b"\xff\xfe secret"))
    with pytest.raises(MalformedMultipart) as info:
        parse_multipart(CT, body)
    assert info.value.detail == "Form fields must be UTF-8"
    assert "secret" not in info.value.detail
