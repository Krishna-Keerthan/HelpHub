"""Calibrate a provisional min_retrieval_score for semantic search.

Embeds a small demo support corpus as passages, then ~10 paraphrased relevant
questions and ~10 irrelevant ones as queries, and prints each query's top-hit
score (cosine similarity, the same ``1 - cosine distance`` that /search
returns). In memory only: no database, tenant or .env involved.

Run from backend/:  uv run python scripts/calibrate_threshold.py
"""

import asyncio

import numpy as np

from app.services.embeddings import FastEmbedProvider

CORPUS = [
    (
        "To reset your password, open Settings, choose Security, and click 'Reset password'. "
        "A reset link is emailed to you and stays valid for 30 minutes."
    ),
    (
        "You can invite teammates from the Members page. Enter their email address and pick "
        "a role: admin, agent, or viewer. Invitations expire after 7 days."
    ),
    (
        "Billing is charged monthly on the day you subscribed. To update your credit card, "
        "go to Billing, then Payment methods, and add a new card."
    ),
    (
        "To cancel your subscription, open Billing and select Cancel plan. You keep access "
        "until the end of the current billing period and no refund is issued for unused days."
    ),
    (
        "Two-factor authentication can be enabled under Security. Scan the QR code with an "
        "authenticator app and store the recovery codes somewhere safe."
    ),
    (
        "You can export all tickets as CSV from Reports, then Export. Large exports are "
        "emailed as a download link when ready."
    ),
    (
        "The API rate limit is 100 requests per minute per API key. Exceeding it returns "
        "HTTP 429 with a Retry-After header."
    ),
    (
        "Uploaded files may be PDF, DOCX or plain text and up to 20 MB each. Files are "
        "scanned and split into searchable chunks after upload."
    ),
]

RELEVANT = [
    "How do I change my password if I forgot it?",
    "How can I add a new person to my team?",
    "Where do I update the card used for payments?",
    "I want to stop my subscription, how?",
    "How do I turn on 2FA for my account?",
    "Can I download my tickets as a spreadsheet?",
    "What happens if I send too many API requests?",
    "What file types and sizes can I upload?",
    "How long is the password reset link good for?",
    "Will I get my money back if I cancel mid-month?",
]

IRRELEVANT = [
    "What is the capital of France?",
    "Give me a recipe for chocolate chip cookies.",
    "Who won the football world cup in 2018?",
    "How tall is Mount Everest?",
    "Explain how photosynthesis works.",
    "What's the best way to train for a marathon?",
    "Write a poem about the ocean.",
    "How do black holes form?",
    "What is the plot of Romeo and Juliet?",
    "How do I repair a flat bicycle tire?",
]


def top_scores(passages: np.ndarray, queries: np.ndarray) -> np.ndarray:
    return (queries @ passages.T).max(axis=1)


def unit(vectors: list[list[float]]) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float64)
    return arr / np.linalg.norm(arr, axis=1, keepdims=True)


async def main() -> None:
    provider = FastEmbedProvider()
    passages = unit(await provider.embed_passages(CORPUS))

    groups: dict[str, list[str]] = {"relevant": RELEVANT, "irrelevant": IRRELEVANT}
    results: dict[str, np.ndarray] = {}
    for name, queries in groups.items():
        vecs = unit([await provider.embed_query(q) for q in queries])
        scores = top_scores(passages, vecs)
        results[name] = scores
        print(f"\n== {name} ==")
        for q, s in zip(queries, scores, strict=True):
            print(f"{s:.4f}  {q}")

    rel_min = float(results["relevant"].min())
    irr_max = float(results["irrelevant"].max())
    print(f"\nrelevant   min={rel_min:.4f} mean={results['relevant'].mean():.4f}")
    print(f"irrelevant max={irr_max:.4f} mean={results['irrelevant'].mean():.4f}")
    if rel_min > irr_max:
        print(
            f"gap: ({irr_max:.4f}, {rel_min:.4f}); midpoint {(rel_min + irr_max) / 2:.4f}"
        )
    else:
        print("groups overlap: no clean threshold")


if __name__ == "__main__":
    asyncio.run(main())
