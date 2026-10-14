import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.user import UserCreate, UserRead

# gate-allow: secret fake value used only by this test
PASSWORD = "a-long-enough-password"


def test_email_is_stripped_and_lowercased_in_every_request_schema() -> None:
    register = RegisterRequest(
        tenant_name="Acme",
        tenant_slug="acme",
        email="  Admin@Example.COM ",
        password=PASSWORD,
    )
    login = LoginRequest(
        tenant_slug="acme", email="  Admin@Example.COM ", password=PASSWORD
    )
    create = UserCreate(email="  Admin@Example.COM ", password=PASSWORD)

    assert register.email == login.email == create.email == "admin@example.com"


@pytest.mark.parametrize("length", [11, 129])
def test_password_length_bounds_rejected(length: int) -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password="x" * length)


@pytest.mark.parametrize("length", [12, 128])
def test_password_length_bounds_accepted(length: int) -> None:
    UserCreate(email="a@example.com", password="x" * length)


def test_login_does_not_enforce_minimum_password_length() -> None:
    LoginRequest(tenant_slug="acme", email="a@example.com", password="short")


def test_unknown_role_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password=PASSWORD, role="owner")  # type: ignore[arg-type]


@pytest.mark.parametrize("slug", ["", "A", "Acme", "has space", "-lead", "x" * 101])
def test_bad_slug_rejected(slug: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            tenant_name="Acme",
            tenant_slug=slug,
            email="a@example.com",
            password=PASSWORD,
        )


def test_user_read_never_exposes_password_hash() -> None:
    assert "password_hash" not in UserRead.model_fields
    assert "password" not in UserRead.model_fields
