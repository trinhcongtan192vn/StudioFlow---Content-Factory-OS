"""Vision captioning qua Ollama (local, đã cài sẵn cho task `llm` — xem
`local_openai_compat.py`) — bổ sung sau khi phát hiện máy người dùng KHÔNG cài LocalAI
(port 8080 không có gì lắng nghe, xem IMPLEMENTATION_REPORT.md mục 85 phần "sự cố Vision/
Embedding không kết nối"). Tái dùng ĐÚNG service đang chạy thay vì bắt cài thêm LocalAI —
Ollama hỗ trợ vision qua shim OpenAI-compat `/v1/chat/completions` với
`content: [{type: image_url, image_url: {url: data:...}}]`, đã verify thật với model
`moondream` (~1.7GB, tương đương VRAM với `moondream2` LocalAI, không tranh chấp thêm
VRAM so với phương án ban đầu).

Dùng chung `gpu_lock` với `local_openai_compat.py` vì CÙNG một tiến trình Ollama/GPU —
gọi vision đồng thời với LLM/Image/Video local sẽ gây thrashing y hệt lý do đã ghi ở
`local_openai_compat.py`.
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from app.providers.base import ProviderStatus, VisionProvider, VisionResult
from app.providers.gpu_lock import gpu_lock

_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
_MODEL_NAME = "moondream"

_CAPTION_PROMPT_SUFFIX = (
    '\n\nTrả lời DUY NHẤT bằng JSON hợp lệ, không thêm chữ nào khác, đúng định dạng: '
    '{"caption": "...", "tags": ["...", "..."], "mood_tone": "..."}'
)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Không tìm thấy JSON trong response VLM: {text[:200]}")
    return json.loads(match.group(0))


class OllamaVisionProvider(VisionProvider):
    provider_name = "ollama_vision"

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
        with gpu_lock, httpx.Client(timeout=120) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        try:
            parsed = _extract_json(text)
        except (ValueError, json.JSONDecodeError):
            return VisionResult(caption=text.strip()[:500], tags=[], mood_tone="")
        return VisionResult(
            caption=str(parsed.get("caption", "")).strip(),
            tags=[str(t).strip() for t in (parsed.get("tags") or []) if str(t).strip()],
            mood_tone=str(parsed.get("mood_tone", "")).strip(),
        )

    def test_connection(self) -> ProviderStatus:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self.base_url}/models")
                resp.raise_for_status()
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=f"Không kết nối được Ollama: {e}")
