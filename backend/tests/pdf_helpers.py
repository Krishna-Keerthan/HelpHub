"""Small in-memory PDFs for upload tests."""

import io

from pypdf import PdfReader, PdfWriter


def text_pdf(*page_texts: str) -> bytes:
    """A valid PDF with one Helvetica text line per page."""
    pages = page_texts or ("Hello PDF",)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Pages, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in pages:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        objects.append(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
        content_id = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents %d 0 R /Resources << /Font << /F1 3 0 R >> >> >>" % content_id
        )
        kids.append(b"%d 0 R" % len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(kids),
        len(kids),
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def blank_pdf(pages: int) -> bytes:
    """Pages with no text at all."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def encrypted_pdf(text: str = "Secret text") -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf(text))))
    writer.encrypt("user-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
