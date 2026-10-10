"""Paragraph/sentence-aware text chunking with exact source offsets.

Chunk text is always ``source[start:end]``: nothing is normalized, stripped or
rewritten. Leading and trailing whitespace is dropped by moving ``start`` and
``end``, never by editing the text.
"""

import re
from bisect import bisect_left
from typing import TypedDict

DEFAULT_MAX_CHARS = 1000
DEFAULT_OVERLAP = 150

# A blank line: two newlines with only horizontal whitespace (or the \r of a
# \r\n pair) between them.
_PARAGRAPH_BREAK = re.compile(r"\n[ \t\r]*\n")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")

Span = tuple[int, int]


class Chunk(TypedDict):
    index: int
    start: int
    end: int
    text: str


def _trim(text: str, start: int, end: int) -> Span | None:
    """Shrink [start, end) to its non-whitespace bounds; None if all whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _split(text: str, pattern: re.Pattern[str], span: Span) -> list[Span]:
    """Split ``span`` on ``pattern`` matches into trimmed, non-empty spans."""
    start, end = span
    pieces: list[Span] = []
    cursor = start
    for match in pattern.finditer(text, start, end):
        pieces.append((cursor, match.start()))
        cursor = match.end()
    pieces.append((cursor, end))
    return [t for piece in pieces if (t := _trim(text, *piece)) is not None]


def _hard_wrap(text: str, span: Span, max_chars: int) -> list[Span]:
    """Cut a trimmed span into pieces of at most ``max_chars``.

    Each cut is at the last whitespace within the window; if the window has
    none, the cut is exactly at ``max_chars``.
    """
    pos, end = span
    pieces: list[Span] = []
    while end - pos > max_chars:
        limit = pos + max_chars
        cut = limit
        while cut > pos and not text[cut].isspace():
            cut -= 1
        if cut == pos:  # no whitespace in the window: break the word
            pieces.append((pos, limit))
            pos = limit
        else:
            piece_end = cut
            while text[piece_end - 1].isspace():  # text[pos] is non-space: stops
                piece_end -= 1
            pieces.append((pos, piece_end))
            pos = cut
            while text[pos].isspace():
                pos += 1
    pieces.append((pos, end))
    return pieces


def _segments(text: str, max_chars: int) -> list[Span]:
    """Trimmed spans, each at most ``max_chars``, in source order."""
    segments: list[Span] = []
    for para in _split(text, _PARAGRAPH_BREAK, (0, len(text))):
        if para[1] - para[0] <= max_chars:
            segments.append(para)
            continue
        for sentence in _split(text, _SENTENCE_BREAK, para):
            if sentence[1] - sentence[0] <= max_chars:
                segments.append(sentence)
            else:
                segments.extend(_hard_wrap(text, sentence, max_chars))
    return segments


def chunk_text(
    text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[Chunk]:
    """Split ``text`` into chunks of at most ``max_chars`` characters.

    Segments (paragraphs, then sentences, then hard-wrapped pieces) are packed
    greedily. The next chunk starts at the first segment boundary at or after
    ``previous_end - overlap``, so consecutive chunks share at most ``overlap``
    characters and every chunk starts strictly after the previous one.
    """
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must satisfy 0 <= overlap < max_chars")

    segments = _segments(text, max_chars)
    if not segments:
        return []
    starts = [start for start, _ in segments]
    last = len(segments) - 1

    chunks: list[Chunk] = []
    i = 0
    while True:
        first = segments[i][0]
        j = i
        while j < last and segments[j + 1][1] - first <= max_chars:
            j += 1
        end = segments[j][1]
        chunks.append(
            {"index": len(chunks), "start": first, "end": end, "text": text[first:end]}
        )
        if j == last:
            return chunks
        # bisect result is at most j + 1; max() guarantees forward progress.
        i = max(bisect_left(starts, end - overlap), i + 1)
        # Skip starts whose chunk could not reach past this chunk's last
        # segment: it would be a pure duplicate of text already emitted.
        while i <= j and segments[j + 1][1] - segments[i][0] > max_chars:
            i += 1
