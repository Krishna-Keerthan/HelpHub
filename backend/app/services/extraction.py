"""Text extraction for uploaded files. Everything happens in memory; PDFs are
parsed in a separate, killable, resource-limited worker (pdf_worker.py).

Every failure here happens before any database row exists.
"""

import asyncio
import json
import os
import sys
import unicodedata
from pathlib import Path

from app.core.config import settings

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_PDF_PAGES = 200
MAX_TITLE_CHARS = 500


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


class ExtractedTextTooLarge(Exception):
    pass


async def extract_text(filename: str, data: bytes) -> str:
    """Text of an uploaded file (no NUL stripping here; the service does it)."""
    if check_extension(filename) == ".pdf":
        return await _pdf_text(data)
    try:
        return data.decode("utf-8-sig")  # drops a leading BOM
    except UnicodeDecodeError:
        raise UnreadableDocument("file is not valid UTF-8 text") from None


# --- PDF: separate, killable, resource-limited worker process ----------------

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_WORKER_ERRORS = {
    "not_pdf": "file is not a PDF",
    "encrypted": "encrypted PDFs are not supported",
    "too_many_pages": f"PDF has more than {MAX_PDF_PAGES} pages",
    "unreadable": "PDF could not be read",
    "no_text": "PDF has no extractable text",
}
_semaphore: asyncio.Semaphore | None = None


def _worker_slots() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.pdf_max_concurrency)
    return _semaphore


def _worker_env() -> dict[str, str]:
    """Only what the interpreter needs: no secrets, no DATABASE_URL."""
    return {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"}


async def _pdf_text(data: bytes) -> str:
    timeout = settings.pdf_timeout_seconds
    async with _worker_slots():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.services.pdf_worker",
            str(MAX_PDF_PAGES),
            str(settings.max_document_chars),
            str(settings.pdf_cpu_seconds),
            str(settings.pdf_memory_bytes),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=_BACKEND_ROOT,
            env=_worker_env(),
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(data), timeout)
        except TimeoutError:
            await _kill(process)
            raise UnreadableDocument("PDF took too long to process") from None
        except BaseException:  # cancelled request: never leave the worker running
            await _kill(process)
            raise
    if process.returncode != 0:  # e.g. killed by its memory or CPU limit
        raise UnreadableDocument("PDF could not be processed within limits")
    try:
        result = json.loads(stdout)
    except ValueError:
        raise UnreadableDocument("PDF could not be read") from None
    if "text" in result:
        return result["text"]
    if result.get("error") == "too_large":
        raise ExtractedTextTooLarge("document is too large")
    raise UnreadableDocument(
        _WORKER_ERRORS.get(result.get("error"), "PDF could not be read")
    )


async def _kill(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.kill()
        await process.wait()
