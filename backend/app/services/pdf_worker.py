"""PDF text extraction worker, run as ``python -m app.services.pdf_worker``.

A separate process because pypdf's CPU and memory use is unbounded for a
crafted file, and a thread cannot be killed. The parent passes the PDF on
stdin and the limits as arguments, kills the process at a wall-clock
deadline, and gives it a minimal environment (no secrets). This module must
not import app settings or anything that reads them.

Output: one JSON object on stdout, {"text": ...} or {"error": <code>}.
"""

import io
import json
import resource
import sys

ERROR_CODES = (
    "not_pdf",
    "encrypted",
    "too_many_pages",
    "unreadable",
    "no_text",
    "too_large",
)
PDF_SIGNATURE = b"%PDF-"


def apply_limits(cpu_seconds: int, memory_bytes: int) -> None:
    """Kernel-enforced backstops for the parent's wall-clock timeout."""
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))


def extract(data: bytes, max_pages: int, max_chars: int) -> dict[str, str]:
    if not data.startswith(PDF_SIGNATURE):
        return {"error": "not_pdf"}
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return {"error": "encrypted"}
        if len(reader.pages) > max_pages:
            return {"error": "too_many_pages"}
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            parts.append(page_text)
            total += len(page_text) + 2
            if total > max_chars:  # stop early; the service would reject it
                return {"error": "too_large"}
    except MemoryError:
        raise
    except Exception:  # noqa: BLE001 - any pypdf failure means "unreadable"
        return {"error": "unreadable"}
    text = "\n\n".join(parts)
    if not text.strip():
        return {"error": "no_text"}
    return {"text": text}


def main(argv: list[str]) -> int:
    max_pages, max_chars, cpu_seconds, memory_bytes = (int(arg) for arg in argv)
    apply_limits(cpu_seconds, memory_bytes)
    data = sys.stdin.buffer.read()
    json.dump(extract(data, max_pages, max_chars), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
