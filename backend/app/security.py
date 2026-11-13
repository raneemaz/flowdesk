"""Password hashing (NFR-001: modern, maintained algorithm).

Argon2id via argon2-cffi - OWASP's current first recommendation for new
applications, ahead of scrypt/bcrypt/PBKDF2.
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(password_hash: str, raw_password: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw_password)
    except VerificationError:
        return False


# A real hash with no corresponding account, for login flows to verify
# against when the submitted email doesn't match a user - Argon2
# verification is deliberately slow, so skipping it for "user not found"
# would let a request's response time leak whether an email is
# registered, even though the response body itself is identical either
# way.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-used-only-for-timing-safety")
