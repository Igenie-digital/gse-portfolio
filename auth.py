"""
Auth helpers — password hashing (PBKDF2-SHA256) and session tokens.
No third-party dependencies: uses only stdlib hashlib, os, uuid.
"""
import hashlib
import os
import uuid
from datetime import datetime, timedelta


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        key  = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return key.hex() == key_hex
    except Exception:
        return False


def new_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex   # 64-char random hex


def token_expiry() -> str:
    return (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
