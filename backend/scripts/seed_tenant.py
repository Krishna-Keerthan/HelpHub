"""Create a tenant and its first admin through the service layer.

Usage (from backend/, with DATABASE_URL, MIGRATION_DATABASE_URL and JWT_SECRET set):
    uv run python scripts/seed_tenant.py --name "Acme" --slug acme --email admin@acme.test
The password comes from SEED_ADMIN_PASSWORD, or is prompted for (never an argument).
Works while ALLOW_PUBLIC_REGISTRATION is false. Prints ids only, never a token.
"""

import argparse
import asyncio
import getpass
import os
import sys

from pydantic import ValidationError

from app.db.session import engine
from app.schemas.auth import RegisterRequest
from app.services import auth as auth_service


async def seed(data: RegisterRequest) -> int:
    try:
        user, _ = await auth_service.create_tenant_with_admin(data)
    except auth_service.TenantSlugTaken:
        print(f"error: slug '{data.tenant_slug}' is already taken", file=sys.stderr)
        return 1
    except auth_service.ReservedSlug:
        print(f"error: slug '{data.tenant_slug}' is reserved", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"created tenant {data.tenant_slug} (id {user.tenant_id}), admin {user.id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    password = os.environ.get("SEED_ADMIN_PASSWORD") or getpass.getpass(
        "Admin password: "
    )
    try:
        data = RegisterRequest(
            tenant_name=args.name,
            tenant_slug=args.slug,
            email=args.email,
            password=password,
        )
    except ValidationError as exc:
        # Field names only: the error text would echo the rejected password.
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        print(f"error: invalid {', '.join(fields)}", file=sys.stderr)
        return 2
    return asyncio.run(seed(data))


if __name__ == "__main__":
    raise SystemExit(main())
