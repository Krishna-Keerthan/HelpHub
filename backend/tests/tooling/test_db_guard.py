"""The local-database guard: pure logic on constructed URLs, no connection."""

import pytest

from tests.helpers.db_guard import host_is_local, non_local_variables, refusal_message

SECRET = "s3cr3t-pw"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "db", "postgres"])
def test_local_hosts_are_accepted(host: str) -> None:
    assert host_is_local(f"postgresql+asyncpg://u:{SECRET}@{host}:5432/app")


@pytest.mark.parametrize(
    "host",
    ["db.abc.supabase.co", "aws-0.pooler.supabase.com", "example.com", "10.0.0.5"],
)
def test_other_hosts_are_refused(host: str) -> None:
    assert not host_is_local(f"postgresql+asyncpg://u:{SECRET}@{host}:5432/app")


@pytest.mark.parametrize("url", [None, "", "not a url", "postgresql+asyncpg:///app"])
def test_unset_or_hostless_is_refused(url: str | None) -> None:
    assert not host_is_local(url)


def test_refusal_names_variables_but_never_the_url() -> None:
    names = non_local_variables(
        {
            "DATABASE_URL": f"postgresql+asyncpg://u:{SECRET}@localhost/app",
            "MIGRATION_DATABASE_URL": f"postgresql+asyncpg://u:{SECRET}@x.supabase.co/app",
        }
    )
    assert names == ["MIGRATION_DATABASE_URL"]
    message = refusal_message(names)
    assert message is not None
    assert "MIGRATION_DATABASE_URL" in message
    assert SECRET not in message
    assert "supabase" not in message


def test_all_local_gives_no_refusal() -> None:
    assert refusal_message([]) is None
