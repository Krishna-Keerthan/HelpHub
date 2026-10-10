"""Text extraction for uploaded files. Everything happens in memory.

Every failure here happens before any database row exists.
"""

import asyncio
import io
import unicodedata

from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_PDF_PAGES = 200
MAX_TITLE_CHARS = 500
PDF_SIGNATURE = b"%PDF-"


class UnsupportedFileType(Exception):
    pass


class UnreadableDocument(Exception):
    """The file cannot be turned into text; messages are safe to return."""


def base_name(filename: str) -> str:
    """The last path segment, with either separator, minus control chars."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    return name.strip()[:MAX_TITLE_CHARS]


def extension(filename: str) -> str:
    name = base_name(filename).lower()
    dot = name.rfind(".")
    return name[dot:] if dot > 0 else ""


def check_extension(filename: str) -> str:
    ext = extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileType("only .txt, .md and .pdf files are supported")
    return ext


async def extract_text(filename: str, data: bytes) -> str:
    """Text of an uploaded file (no NUL stripping here; the service does it)."""
    if check_extension(filename) == ".pdf":
        return await asyncio.to_thread(_pdf_text, data)
    try:
        return data.decode("utf-8-sig")  # drops a leading BOM
    except UnicodeDecodeError:
        raise UnreadableDocument("file is not valid UTF-8 text") from None


def _pdf_text(data: bytes) -> str:
    if not data.startswith(PDF_SIGNATURE):
        raise UnreadableDocument("file is not a PDF")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnreadableDocument("encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise UnreadableDocument(f"PDF has more than {MAX_PDF_PAGES} pages")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except UnreadableDocument:
        raise
    except Exception:  # noqa: BLE001 - any pypdf failure means "unreadable"
        raise UnreadableDocument("PDF could not be read") from None
    if not text.strip():
        raise UnreadableDocument("PDF has no extractable text")
    return text
