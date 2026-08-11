"""Mã hoá API key at-rest (§01 mục 8, §05 mục 8).

Single-user local app: khoá đối xứng sinh 1 lần, lưu trong workspace (không rời máy).
Không phải mô hình bảo mật đa người dùng/production SaaS — phù hợp phạm vi CLAUDE.md.
"""
from cryptography.fernet import Fernet

from app.config import SECRET_KEY_PATH


def _get_key() -> bytes:
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    SECRET_KEY_PATH.write_bytes(key)
    return key


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    f = Fernet(_get_key())
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    f = Fernet(_get_key())
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def mask_secret(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) <= 8:
        return "•" * len(plain)
    return f"{plain[:4]}{'•' * 8}{plain[-4:]}"
