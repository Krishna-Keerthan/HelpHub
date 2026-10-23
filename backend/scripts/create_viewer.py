"""Create one read-only viewer user in a tenant through the admin API.

Logs in as a tenant admin and POSTs /users with role "viewer". Idempotent: a
viewer with that email is left alone. Prints counts only, never URLs, emails or
passwords.

Admin settings (BASE_URL, TENANT_SLUG, EMAIL, PASSWORD) come from the
environment or ~/.helphub-local-creds, as for load_demo_corpus.py. The viewer's
VIEWER_EMAIL and VIEWER_PASSWORD come from the environment only.

Run from backend/:  VIEWER_EMAIL=... VIEWER_PASSWORD=... uv run python scripts/create_viewer.py
"""

import os
import sys

import httpx
from load_demo_corpus import read_settings

REQUEST_TIMEOUT_SECONDS = 30.0
PAGE = 100


def find_role(client: httpx.Client, email: str) -> str | None:
    offset = 0
    while True:
        page = client.get("/users", params={"limit": PAGE, "offset": offset})
        page.raise_for_status()
        rows = page.json()
        for row in rows:
            if row["email"] == email:
                return row["role"]
        if len(rows) < PAGE:
            return None
        offset += PAGE


def main() -> int:
    settings = read_settings()
    email = os.environ.get("VIEWER_EMAIL", "").strip().lower()
    password = os.environ.get("VIEWER_PASSWORD", "")
    if not email or not password:
        print("Missing settings: VIEWER_EMAIL, VIEWER_PASSWORD")
        return 1
    created = existing = conflicts = 0
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

        role = find_role(client, email)
        if role is None:
            response = client.post(
                "/users",
                json={"email": email, "password": password, "role": "viewer"},
            )
            if response.status_code != 201:
                print(f"create failed: HTTP {response.status_code}")
                return 1
            created += 1
        elif role == "viewer":
            existing += 1
        else:
            conflicts += 1
    print(f"created={created} existing={existing} conflicts={conflicts}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
