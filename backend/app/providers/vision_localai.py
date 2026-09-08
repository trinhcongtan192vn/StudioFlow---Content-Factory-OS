"""Vision captioning qua LocalAI — CHANGE_Semantic_BRoll_Asset_Vault.md §3/§3b.

Xác nhận THẬT qua tài liệu chính thức (localai.io/docs/features/gpt-vision/, không suy
đoán — đúng kỷ luật đã áp dụng cho `image_localai.py`/`video_localai.py`): vision dùng
CHUNG endpoint `/v1/chat/completions` với LLM thường (KHÔNG có endpoint riêng), gửi ảnh
qua `messages[].content` dạng mảng OpenAI-vision chuẩn
`[{"type":"text",...},{"type":"image_url","image_url":{"url": "data:..."}}]`. Model
`moondream2` được liệt kê CHÍNH THỨC trong tài liệu — chọn làm mặc định (mục tiêu VRAM
nhỏ ~2-4GB, xem đối chiếu GPU trong plan: máy người dùng đã CHẬT VRAM vì OmniVoice giữ
sẵn ~9.9GB, Qwen2.5-VL 7B spec đề xuất ~12GB sẽ không đủ chỗ)."""
from __future__ import annotations

import base64
import json
import re

import httpx

from app.providers.base import ProviderStatus, VisionProvider, VisionResult

_DEFAULT_BASE_URL = "http://127.0.0.1:8080"
_MODEL_NAME = "moondream2"

_CAPTION_PROMPT_SUFFIX = (
    '\n\nTrả lời DUY NHẤT bằng JSON hợp lệ, không thêm chữ nào khác, đúng định dạng: '
    '{"caption": "...", "tags": ["...", "..."], "mood_tone": "..."}'
)


def _extract_json(text: str) -> dict:
    """LLM/VLM đôi khi bọc JSON trong ```json ... ``` hoặc thêm chữ thừa trước/sau —
    cùng cách phòng vệ đã dùng cho `score_hook_strength` (app/guardrail/check.py)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Không tìm thấy JSON trong response VLM: {text[:200]}")
    return json.loads(match.group(0))


class LocalAIVisionProvider(VisionProvider):
    provider_name = "localai_vision"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model_name or _MODEL_NAME

    def caption(self, image_bytes: bytes, *, prompt: str) -> VisionResult:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        body = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt + _CAPTION_PROMPT_SUFFIX},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{self.base_url}/v1/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        try:
            parsed = _extract_json(text)
        except (ValueError, json.JSONDecodeError):
            # VLM không trả đúng JSON yêu cầu — vẫn dùng được, chỉ mất tags/mood_tone có
            # cấu trúc. KHÔNG raise — captioning chạy nền hàng loạt, 1 clip lỗi format
            # không nên chặn cả batch (đúng nguyên tắc "lỗi 1 phần không chặn cả batch"
            # đã áp dụng cho generate_all_visual).
            return VisionResult(caption=text.strip()[:500], tags=[], mood_tone="")
        return VisionResult(
            caption=str(parsed.get("caption", "")).strip(),
            tags=[str(t).strip() for t in (parsed.get("tags") or []) if str(t).strip()],
            mood_tone=str(parsed.get("mood_tone", "")).strip(),
        )

    def test_connection(self) -> ProviderStatus:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self.base_url}/v1/models")
                resp.raise_for_status()
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=f"Không kết nối được LocalAI: {e}")
