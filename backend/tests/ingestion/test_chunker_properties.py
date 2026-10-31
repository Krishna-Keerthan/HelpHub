from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.chunker import chunk_text

# Mixes unicode, emoji, whitespace of every kind, sentence punctuation and long
# unbroken runs, which exercise every splitting strategy.
messy_text = st.one_of(
    st.text(max_size=400),
    st.text(alphabet=" \t\r\n.!?ab😀é世", max_size=400),
    st.text(alphabet="xyz", min_size=1, max_size=300),
    st.builds(
        lambda words, seps: "".join(w + s for w, s in zip(words, seps, strict=False)),
        st.lists(st.text(alphabet="abc.é", min_size=1, max_size=15), max_size=40),
        st.lists(st.sampled_from([" ", "  ", "\n", "\r\n", "\n\n", "\r\n\r\n"])),
    ),
)


@st.composite
def chunk_params(draw):
    max_chars = draw(st.integers(min_value=1, max_value=60))
    overlap = draw(st.integers(min_value=0, max_value=max_chars - 1))
    return max_chars, overlap


@settings(max_examples=500, deadline=None)
@given(text=messy_text, params=chunk_params())
def test_chunk_properties(text, params):
    max_chars, overlap = params
    chunks = chunk_text(text, max_chars=max_chars, overlap=overlap)

    # Determinism
    assert chunks == chunk_text(text, max_chars=max_chars, overlap=overlap)

    if not text.strip():
        assert chunks == []
        return
    assert chunks, "non-blank text must produce chunks"

    for i, chunk in enumerate(chunks):
        assert chunk["index"] == i
        # Exact slice: nothing normalized or rewritten
        assert text[chunk["start"] : chunk["end"]] == chunk["text"]
        # Size and content
        assert 0 < len(chunk["text"]) <= max_chars
        assert chunk["text"].strip() != ""
        # Whitespace is trimmed by moving the offsets
        assert not chunk["text"][0].isspace()
        assert not chunk["text"][-1].isspace()
        if i:
            previous = chunks[i - 1]
            # Strictly increasing starts, and overlap never exceeds `overlap`
            assert chunk["start"] > previous["start"]
            assert chunk["end"] > previous["end"]
            assert max(0, previous["end"] - chunk["start"]) <= overlap

    # Merged coverage: no non-whitespace character falls in a gap
    covered = [False] * len(text)
    for chunk in chunks:
        for pos in range(chunk["start"], chunk["end"]):
            covered[pos] = True
    assert [p for p, ch in enumerate(text) if not ch.isspace() and not covered[p]] == []


def test_crlf_offsets_are_preserved():
    text = "First paragraph.\r\n\r\nSecond paragraph that is a bit longer.\r\n"
    chunks = chunk_text(text, max_chars=20, overlap=0)
    assert [c["text"] for c in chunks] == [
        "First paragraph.",
        "Second paragraph",
        "that is a bit",
        "longer.",
    ]
    for c in chunks:
        assert text[c["start"] : c["end"]] == c["text"]
