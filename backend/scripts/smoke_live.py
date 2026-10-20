"""Live smoke test of a running HelpHub API: login, upload, search, chat, delete, logout.

    BASE_URL=https://... SMOKE_TENANT_SLUG=acme SMOKE_EMAIL=... SMOKE_PASSWORD=... \\
        uv run python scripts/smoke_live.py

The tenant must already exist (scripts/seed_tenant.py). Credentials come from the
environment only. Output is step names and timings; no token, password, document
text or answer text is ever printed. Exit code 0 only if every step passed.
"""

import json
import os
import sys
import time
import uuid
from collections.abc import Callable

import httpx

READY_TIMEOUT_SECONDS = 180.0
CHAT_TIMEOUT_SECONDS = 120.0
REQUEST_TIMEOUT_SECONDS = 120.0


class SmokeFailure(Exception):
    """A step failed. The message is fixed text plus a status code, never a body."""


def _expect(response: httpx.Response, *codes: int) -> httpx.Response:
    if response.status_code not in codes:
        raise SmokeFailure(f"HTTP {response.status_code}, expected {sorted(codes)}")
    return response


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"missing environment variable {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def run(base_url: str, slug: str, email: str, password: str) -> int:
    marker = f"smoke{uuid.uuid4().hex[:12]}"
    state: dict[str, str] = {}
    timings: list[tuple[str, float, str]] = []
    client = httpx.Client(base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS)

    def auth() -> dict[str, str]:
        return {"authorization": f"Bearer {state['access']}"}

    def login() -> None:
        r = _expect(
            client.post(
                "/auth/login",
                json={"tenant_slug": slug, "email": email, "password": password},
            ),
            200,
        )
        body = r.json()
        state["access"], state["refresh"] = body["access_token"], body["refresh_token"]

    def upload() -> None:
        text = (
            f"Smoke test document {marker}. The quokka protocol {marker} says that "
            "the zebra-blue handshake must be repeated twice before the gateway opens."
        )
        r = _expect(
            client.post(
                "/documents",
                headers=auth(),
                json={"title": f"smoke {marker}", "content": text},
            ),
            200,
            201,
        )
        state["doc"] = r.json()["id"]

    def wait_ready() -> None:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while True:
            r = _expect(client.get(f"/documents/{state['doc']}", headers=auth()), 200)
            status = r.json()["status"]
            if status == "READY":
                return
            if status == "FAILED":
                raise SmokeFailure("document status FAILED")
            if time.monotonic() > deadline:
                raise SmokeFailure("document not READY in time")
            time.sleep(1.0)

    def search() -> None:
        r = _expect(
            client.post(
                "/search",
                headers=auth(),
                json={"query": f"quokka protocol {marker}", "k": 5},
            ),
            200,
        )
        if state["doc"] not in {hit["document_id"] for hit in r.json()}:
            raise SmokeFailure("uploaded document not among the search hits")

    def chat() -> None:
        events: list[str] = []
        done_status = ""
        with client.stream(
            "POST",
            "/chat/stream",
            headers=auth(),
            json={"message": f"What does the quokka protocol {marker} say?"},
            timeout=CHAT_TIMEOUT_SECONDS,
        ) as r:
            _expect(r, 200)
            current = ""
            for line in r.iter_lines():
                if line.startswith("event:"):
                    current = line.split(":", 1)[1].strip()
                    events.append(current)
                elif line.startswith("data:") and current == "done":
                    done_status = str(json.loads(line.split(":", 1)[1])["status"])
        if not events or events[-1] != "done":
            last = events[-1] if events else "none"
            raise SmokeFailure(f"stream did not end with done (last event: {last})")
        state["chat_note"] = f"events={len(events)} status={done_status}"

    def delete() -> None:
        _expect(client.delete(f"/documents/{state['doc']}", headers=auth()), 204)

    def logout() -> None:
        _expect(
            client.post(
                "/auth/logout", headers=auth(), json={"refresh_token": state["refresh"]}
            ),
            204,
        )

    steps: list[tuple[str, Callable[[], None]]] = [
        ("login", login),
        ("upload", upload),
        ("wait_ready", wait_ready),
        ("search", search),
        ("chat_stream", chat),
        ("delete", delete),
        ("logout", logout),
    ]
    failed = False
    for name, step in steps:
        started = time.monotonic()
        try:
            step()
            outcome = "ok"
        except (SmokeFailure, httpx.HTTPError, KeyError, ValueError) as exc:
            # Class name and the fixed SmokeFailure text only: an httpx or JSON
            # error message could carry a URL or body fragment.
            detail = str(exc) if isinstance(exc, SmokeFailure) else type(exc).__name__
            outcome = f"FAIL ({detail})"
            failed = True
        elapsed = time.monotonic() - started
        note = state.pop("chat_note", "") if name == "chat_stream" else ""
        timings.append((name, elapsed, outcome))
        print(f"{name:12} {elapsed:7.2f} s  {outcome} {note}".rstrip(), flush=True)
        if failed:
            break
    if (
        failed
        and "doc" in state
        and state.get("access")
        and not any(n == "delete" for n, _, _ in timings)
    ):
        try:  # best-effort cleanup of the smoke document
            client.delete(f"/documents/{state['doc']}", headers=auth())
        except httpx.HTTPError:
            pass
    client.close()
    print("SMOKE FAILED" if failed else "SMOKE OK")
    return 1 if failed else 0


def main() -> int:
    return run(
        _env("BASE_URL").rstrip("/"),
        _env("SMOKE_TENANT_SLUG"),
        _env("SMOKE_EMAIL"),
        _env("SMOKE_PASSWORD"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
