import pytest
from app.services.chunker import chunk_text  # Assumes your chunker utility function


@pytest.mark.parametrize(
    "text, max_chars, overlap",
    [
        ("Hello world! This is a test string for chunking.", 15, 5),
        ("Short", 10, 2),
        ("", 20, 5),
        (
            "NoSpacesHereAtAllJustOneLongContinuousLineWithoutAnyBreaksOrSpacesToTestHardWrapping",
            20,
            4,
        ),
        (
            "こんにちは世界 🌍🚀 Unicode and emoji test string with multi-byte characters.",
            25,
            5,
        ),
        ("Line 1\r\nLine 2\r\nLine 3 with \r\n carriage returns.", 30, 10),
    ],
)
def test_chunker_properties(text, max_chars, overlap):
    chunks = chunk_text(text, max_chars=max_chars, overlap=overlap)

    # Edge case: empty text
    if not text:
        assert chunks == []
        return

    # Determinism check: same input always gives same output
    assert chunks == chunk_text(text, max_chars=max_chars, overlap=overlap)

    # Chunk indexes are sequential and each chunk advances through the source
    for i, chunk in enumerate(chunks):
        assert chunk["index"] == i
        if i:
            assert chunk["start"] > chunks[i - 1]["start"]

    for chunk in chunks:
        # Every chunk is non-empty and at most max_chars
        assert len(chunk["text"]) > 0
        assert len(chunk["text"]) <= max_chars

        # source[start:end] == chunk text for every chunk
        start, end = chunk["start"], chunk["end"]
        assert text[start:end] == chunk["text"]

    # Chunks cover every non-whitespace character of the source: merge the
    # [start, end) ranges and check no non-whitespace position falls in a gap.
    covered = [False] * len(text)
    for chunk in chunks:
        for pos in range(chunk["start"], chunk["end"]):
            covered[pos] = True
    uncovered = [
        pos for pos, ch in enumerate(text) if not ch.isspace() and not covered[pos]
    ]
    assert uncovered == []

    # Neighboring chunks overlap by at most overlap
    for i in range(len(chunks) - 1):
        current_end = chunks[i]["end"]
        next_start = chunks[i + 1]["start"]
        overlap_length = max(0, current_end - next_start)
        assert overlap_length <= overlap
