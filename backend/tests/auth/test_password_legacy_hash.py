"""A hash made with the previous Argon2 parameters keeps verifying after the change."""

from app.core.security import verify_password

# Made with pwdlib's PasswordHash.recommended() (m=65536 KiB, t=3, p=4) for
# the password below, before the parameters were lowered.
LEGACY_ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$AHrMPsjajFHq59i8bQIN8A$co0UbFiKgV40vL66Py8MZ97IUFrZlXa0Cr6Ww1upTHk"
LEGACY_PLAINTEXT = (
    "Old-Params-Pass-123!"  # gate-allow: secret fake value used only by this test
)


def test_legacy_parameters_are_the_old_ones() -> None:
    assert LEGACY_ARGON2.split("$")[1:4] == ["argon2id", "v=19", "m=65536,t=3,p=4"]


def test_hash_with_old_parameters_still_verifies() -> None:
    assert verify_password(LEGACY_PLAINTEXT, LEGACY_ARGON2) is True
    assert verify_password("wrong-password", LEGACY_ARGON2) is False
