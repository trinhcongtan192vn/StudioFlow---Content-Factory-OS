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
    """`.strip()` — **mới (2026-08-22)**: bug thật phát hiện lúc điều tra Flux API key
    "đúng nhưng test connection vẫn lỗi" — 1 trong các đường lưu API key ở frontend
    thiếu `.trim()`, khoảng trắng/ký tự xuống dòng thừa dính vào key vẫn lưu được, tới
    lúc gọi API mới lộ ra bằng lỗi httpx `LocalProtocolError` khó hiểu (xem
    `app/providers/flux_common.py::check_auth`). Chặn NGAY TẠI NGUỒN — API key hợp lệ
    không bao giờ CẦN khoảng trắng ở đầu/cuối, strip ở đây áp dụng cho MỌI provider
    (điểm DUY NHẤT gọi hàm này, xem `app/routers/providers.py`), không cần sửa từng nơi
    gọi riêng lẻ."""
    if not plain:
        return ""
    plain = plain.strip()
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
