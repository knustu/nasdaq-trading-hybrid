from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass

PBKDF2_ITERATIONS = 600_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{4,24}$")


@dataclass(frozen=True)
class PasswordRecord:
    salt_b64: str
    hash_b64: str
    iterations: int = PBKDF2_ITERATIONS


def validate_username(username: str) -> None:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("아이디는 영문, 숫자, 밑줄만 사용해 4~24자로 입력하세요.")


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("비밀번호에는 문자와 숫자가 각각 하나 이상 필요합니다.")


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> PasswordRecord:
    validate_password(password)
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return PasswordRecord(
        salt_b64=base64.b64encode(salt).decode("ascii"),
        hash_b64=base64.b64encode(digest).decode("ascii"),
        iterations=iterations,
    )


def verify_password(password: str, salt_b64: str, hash_b64: str, iterations: int) -> bool:
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
