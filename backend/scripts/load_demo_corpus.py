"""Load the eval corpus (eval/corpus/*.md, except INDEX.md) into a running HelpHub API.

Logs in, then POSTs each file to /documents/upload with the file stem as title.
Idempotent by title: a title already present in the tenant is skipped. Waits for
every document to be READY. Prints counts only, never URLs, credentials or text.

Settings come from the environment, falling back to ~/.helphub-local-creds
(KEY=VALUE lines): BASE_URL, TENANT_SLUG, EMAIL, PASSWORD.

Run from backend/:  uv run python scripts/load_demo_corpus.py
"""

import os
import sys
import time
from pathlib import Path

import httpx

CORPUS = Path(__file__).resolve().parents[1] / "eval" / "corpus"
CREDS_FILE = Path.home() / ".helphub-local-creds"
KEYS = ("BASE_URL", "TENANT_SLUG", "EMAIL", "PASSWORD")
REQUEST_TIMEOUT_SECONDS = 120.0
READY_WAIT_SECONDS = 120.0
PAGE = 100


def read_settings(creds_file: Path = CREDS_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if creds_file.exists():
        for line in creds_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in KEYS:
                values[key.strip()] = value.strip().strip("'\"")
    for key in KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    missing = [k for k in KEYS if not values.get(k)]
    if missing:
        raise SystemExit(f"Missing settings: {', '.join(missing)}")
    return values


def corpus_files(corpus: Path | None = None) -> list[Path]:
    corpus = corpus or CORPUS
    return sorted(p for p in corpus.glob("*.md") if p.name != "INDEX.md")


def existing_titles(client: httpx.Client) -> dict[str, str]:
    """Title -> document id for every document in the tenant."""
    titles: dict[str, str] = {}
    offset = 0
    while True:
        page = client.get("/documents", params={"limit": PAGE, "offset": offset})
        page.raise_for_status()
        rows = page.json()
        titles.update({d["title"]: d["id"] for d in rows})
        if len(rows) < PAGE:
            return titles
        offset += PAGE


def wait_ready(client: httpx.Client, doc_id: str) -> str:
    deadline = time.monotonic() + READY_WAIT_SECONDS
    while True:
        response = client.get(f"/documents/{doc_id}")
        response.raise_for_status()
        status = response.json()["status"]
        if status != "PENDING" or time.monotonic() > deadline:
            return status
        time.sleep(1)


def main() -> int:
    settings = read_settings()
    with httpx.Client(
        base_url=settings["BASE_URL"], timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        login = client.post(
            "/auth/login",
            json={
                "tenant_slug": settings["TENANT_SLUG"],
                "email": settings["EMAIL"],
                "password": settings["PASSWORD"],
            },
        )
        if login.status_code != 200:
            print(f"login failed: HTTP {login.status_code}")
            return 1
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        have = existing_titles(client)
        uploaded = skipped = failed = 0
        ids: list[str] = []
        for path in corpus_files():
            title = path.stem
            if title in have:
                skipped += 1
                ids.append(have[title])
                continue
            response = client.post(
                "/documents/upload",
                data={"title": title},
                files={"file": (path.name, path.read_bytes(), "text/markdown")},
            )
            if response.status_code in (200, 201):
                uploaded += 1
                ids.append(response.json()["id"])
            else:
                failed += 1
                print(f"upload failed for {title}: HTTP {response.status_code}")
        not_ready = sum(1 for i in ids if wait_ready(client, i) != "READY")
    print(
        f"files={len(corpus_files())} uploaded={uploaded} skipped={skipped} "
        f"failed={failed} not_ready={not_ready}"
    )
    return 1 if failed or not_ready else 0


if __name__ == "__main__":
    sys.exit(main())
