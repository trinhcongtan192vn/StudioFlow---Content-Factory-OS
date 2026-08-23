"""Chuẩn hoá hiển thị thời gian theo múi giờ Việt Nam (UTC+7, không có DST) — app chỉ
phục vụ 1 người dùng tại VN (specs/06_uiux.md, `settings.general.timezone` mặc định
"Asia/Ho_Chi_Minh"). DB lưu UTC (đúng convention, `models/__init__.py` dùng
`datetime.utcnow`) — mọi nơi TRẢ dữ liệu thời gian ra API/UI phải quy đổi qua đây,
KHÔNG trả thẳng datetime UTC thô (trước đây `strftime()`/`isoformat()` gọi trực tiếp
trên giá trị UTC làm sai lệch 7 tiếng khi hiển thị — VD Audit Log/Chi phí hiện giờ UTC
mà không ghi rõ, người dùng đọc nhầm là giờ VN)."""
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def _as_utc(dt: datetime) -> datetime:
    """`datetime.utcnow()` trả naive datetime (không gắn tzinfo) — gán tzinfo=UTC
    trước khi quy đổi, KHÔNG dùng `.astimezone()` trực tiếp trên naive datetime (Python
    sẽ ngầm coi nó là giờ hệ thống local, sai vì giá trị thật đã là UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_vn(dt: datetime) -> datetime:
    """Datetime (UTC, naive hoặc aware) -> datetime aware theo giờ VN (UTC+7)."""
    return _as_utc(dt).astimezone(VN_TZ)


def vn_isoformat(dt: datetime) -> str:
    """ISO 8601 kèm offset +07:00 rõ ràng — an toàn để frontend `new Date(...)` parse
    lại (khác `dt.isoformat()` gọi thẳng trên naive UTC, thiếu offset nên JS hiểu nhầm
    là giờ local trình duyệt)."""
    return to_vn(dt).isoformat()


def vn_strftime(dt: datetime, fmt: str) -> str:
    """Chuỗi hiển thị đã quy đổi giờ VN, dùng cho các cột hiển thị trực tiếp (Audit
    Log, Chi phí) — không cần frontend parse lại."""
    return to_vn(dt).strftime(fmt)
