from typing import Annotated, Any

from pydantic import BeforeValidator, EmailStr, StringConstraints


def _normalize_email(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


NormalizedEmail = Annotated[EmailStr, BeforeValidator(_normalize_email)]

# Length bounds apply when a password is set; login only caps the length.
NewPassword = Annotated[str, StringConstraints(min_length=12, max_length=128)]
LoginPassword = Annotated[str, StringConstraints(min_length=1, max_length=128)]

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,98}$")]
