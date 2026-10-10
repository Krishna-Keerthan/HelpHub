"""POST /documents/upload: multipart file uploads (.txt, .md, .pdf)."""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.ingestion_helpers import owner_chunks, owner_document
from tests.pdf_helpers import blank_pdf, encrypted_pdf, text_pdf

MD = "# Refund policy\n\nRefunds are issued within 14 days of purchase.\n"
TXT = "Shipping takes three to five business days.\nExpress is next day.\n"


async def _upload(
    client: AsyncClient,
    tenant: SeededTenant,
    filename: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    title: str | None = None,
):
    return await client.post(
        "/documents/upload",
        files={"file": (filename, data, content_type)},
        data={"title": title} if title is not None else None,
        headers=auth_headers(tenant),
    )


async def _document_count(owner_conn: AsyncConnection, tenant_id) -> int:
    result = await owner_conn.execute(
        text("SELECT count(*) FROM documents WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    count = result.scalar_one()
    await owner_conn.rollback()
    return count


# --- happy paths -------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "stored"),
    [
        ("refunds.md", MD.encode(), MD),
        ("shipping.txt", TXT.encode(), TXT),
        ("bom.txt", b"\xef\xbb\xbf" + TXT.encode(), TXT),  # BOM dropped
    ],
    ids=["md", "txt", "txt-bom"],
)
async def test_text_upload_creates_ready_document(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    filename: str,
    data: bytes,
    stored: str,
) -> None:
    tenant = await make_tenant(role="agent")  # agents may upload
    response = await _upload(client, tenant, filename, data, "text/plain")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "READY"
    assert body["title"] == filename  # default title: the file's base name
    assert body["created_by"] == str(tenant["user_id"])
    assert "raw_text" not in body
    row = await owner_document(owner_conn, body["id"])
    assert row is not None
    assert row["raw_text"] == stored
    assert row["created_by"] == tenant["user_id"]
    for chunk in await owner_chunks(owner_conn, body["id"]):
        assert stored[chunk["char_start"] : chunk["char_end"]] == chunk["text"]


async def test_pdf_upload_extracts_text(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    pdf = text_pdf("Office hours are nine to five.", "Closed on public holidays.")

    response = await _upload(
        client, tenant, "hours.pdf", pdf, "application/pdf", title="Office hours"
    )

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Office hours"
    row = await owner_document(owner_conn, response.json()["id"])
    assert row is not None
    assert "Office hours are nine to five." in row["raw_text"]
    assert "Closed on public holidays." in row["raw_text"]


async def test_traversal_filename_becomes_plain_title(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await _upload(
        client, tenant, "../../etc/passwd.txt", b"just text", "text/plain"
    )

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "passwd.txt"
    row = await owner_document(owner_conn, response.json()["id"])
    assert row is not None and row["raw_text"] == "just text"


async def test_backslash_traversal_filename_becomes_plain_title(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await _upload(
        client, tenant, "..\\..\\windows\\notes.md", b"# notes", "text/markdown"
    )
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "notes.md"


# --- 415 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename", ["evil.exe", "data.csv", "noextension", "x.pdf.sh"]
)
async def test_unsupported_extension_is_415(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    filename: str,
) -> None:
    tenant = await make_tenant()
    response = await _upload(client, tenant, filename, b"anything")
    assert response.status_code == 415
    assert await _document_count(owner_conn, tenant["id"]) == 0


# --- 422 (always before any row exists) ---------------------------------------


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("latin1.txt", "café".encode("latin-1")),
        ("empty.txt", b""),
        ("blank.md", b"  \n\t \n"),
        ("fake.pdf", b"not a pdf at all"),
        ("broken.pdf", b"%PDF-1.4\nthis is not a real pdf"),
        # pypdf alone would accept this; only the %PDF- signature check rejects it.
        ("disguised.pdf", None),
        ("encrypted.pdf", None),
        ("no-text.pdf", None),
        ("too-many-pages.pdf", None),
    ],
    ids=[
        "invalid-utf8",
        "empty",
        "whitespace",
        "pdf-signature",
        "pdf-unreadable",
        "pdf-junk-before-signature",
        "pdf-encrypted",
        "pdf-no-text",
        "pdf-over-200-pages",
    ],
)
async def test_unprocessable_upload_is_422_without_row(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    filename: str,
    data: bytes | None,
) -> None:
    generated = {
        "disguised.pdf": lambda: b"GIF89a junk header\n" + text_pdf("Hidden text"),
        "encrypted.pdf": encrypted_pdf,
        "no-text.pdf": lambda: blank_pdf(1),
        "too-many-pages.pdf": lambda: blank_pdf(201),
    }
    payload = data if data is not None else generated[filename]()
    tenant = await make_tenant()

    response = await _upload(client, tenant, filename, payload)

    assert response.status_code == 422, response.text
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_missing_file_field_is_422(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await client.post(
        "/documents/upload",
        files={"attachment": ("a.txt", b"text", "text/plain")},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 422


async def test_upload_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/documents/upload", files={"file": ("a.txt", b"text", "text/plain")}
    )
    assert response.status_code == 401


# --- 413 ---------------------------------------------------------------------


async def test_file_over_limit_is_413(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    tenant = await make_tenant()
    response = await _upload(client, tenant, "big.txt", b"x" * 1025, "text/plain")
    assert response.status_code == 413
    assert await _document_count(owner_conn, tenant["id"]) == 0


def test_max_upload_bytes_default() -> None:
    assert type(settings).model_fields["max_upload_bytes"].default == 5 * 1024 * 1024


class _CountingBody:
    """Request body that records how much of it the server consumed."""

    def __init__(self, total: int, chunk: int = 4096) -> None:
        self.total, self.chunk, self.consumed = total, chunk, 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while self.consumed < self.total:
            self.consumed += self.chunk
            yield b"x" * self.chunk


MULTIPART = "multipart/form-data; boundary=testboundary"


async def test_declared_content_length_over_limit_rejected_before_reading(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, make_tenant: MakeTenant
) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    tenant = await make_tenant()
    body = _CountingBody(total=1024 * 1024)

    response = await client.post(
        "/documents/upload",
        content=body,
        headers={
            **auth_headers(tenant),
            "Content-Type": MULTIPART,
            "Content-Length": str(body.total),
        },
    )

    assert response.status_code == 413
    assert body.consumed <= body.chunk  # at most what the transport pre-fetched


async def test_streamed_body_over_limit_stops_reading_early(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, make_tenant: MakeTenant
) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    tenant = await make_tenant()
    body = _CountingBody(total=1024 * 1024)  # no Content-Length: chunked

    response = await client.post(
        "/documents/upload",
        content=body,
        headers={**auth_headers(tenant), "Content-Type": MULTIPART},
    )

    assert response.status_code == 413
    # Bounded read: stops a little past the cap, never reads the whole body.
    assert body.consumed < body.total // 4
