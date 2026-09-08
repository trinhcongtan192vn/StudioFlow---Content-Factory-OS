"""Vision captioning qua Gemini — tuỳ chọn CLOUD thay cho VLM local (mặc định
`localai_vision`/Moondream, xem `vision_localai.py`). Dùng khi người dùng ưu tiên chất
lượng caption hơn chi phí 0đ/giữ ảnh trên máy — CHANGE_Semantic_BRoll_Asset_Vault.md §3b.

Tái dùng pattern HTTP client của `image_gemini.py` (cùng model family `generateContent`),
đổi `responseModalities` sang text + gửi kèm `inlineData` (ảnh) thay vì chỉ prompt."""
from __future__ import annotations

import base64
import json
import re

import httpx

from app.providers.base import ProviderStatus, VisionProvider, VisionResult, raise_for_status_with_body

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL_NAME = "gemini-3.1-flash"

_CAPTION_PROMPT_SUFFIX = (
    '\n\nTrả lời DUY NHẤT bằng JSON hợp lệ, không thêm chữ nào khác, đúng định dạng: '
    '{"caption": "...", "tags": ["...", "..."], "mood_tone": "..."}'
)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Không tìm thấy JSON trong response Gemini: {text[:200]}")
    return json.loads(match.group(0))


class GeminiVisionProvider(VisionProvider):
    provider_name = "gemini_vision"

    def __init__(self, api_key: str = "", model_name: str = ""):
        self.api_key = api_key
        self.model_name = model_name or _MODEL_NAME

    def caption(self, image_bytes: bytes, *, prompt: str) -> VisionResult:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        url = f"{API_BASE}/{self.model_name}:generateContent?key={self.api_key}"
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt + _CAPTION_PROMPT_SUFFIX},
                        {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                    ]
                }
            ],
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        parts = (((data.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise RuntimeError("Gemini Vision không trả về nội dung — kiểm tra lại model hoặc thử lại.")
        try:
            parsed = _extract_json(text)
        except (ValueError, json.JSONDecodeError):
            return VisionResult(caption=text[:500], tags=[], mood_tone="")
        return VisionResult(
            caption=str(parsed.get("caption", "")).strip(),
            tags=[str(t).strip() for t in (parsed.get("tags") or []) if str(t).strip()],
            mood_tone=str(parsed.get("mood_tone", "")).strip(),
        )

    def test_connection(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}")
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))
