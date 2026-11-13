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
