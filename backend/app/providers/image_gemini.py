"""Gemini Image (Nano Banana) — provider Image thứ 2 thực thi sinh ảnh THẬT (đợt 2,
cùng lứa Gemini TTS/Google Veo). Đồng bộ — 1 request trả thẳng ảnh base64, không cần
polling, giống OpenAI Image (app/providers/image_openai.py).
"""
import base64

import httpx

from app.providers.base import ImageProvider, ProviderStatus, raise_for_status_with_body

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# USD / ảnh — theo ai.google.dev/gemini-api/docs/pricing đã research ở M2
# (specs/05_ai_providers.md §8c): Gemini 3.1 Flash Image ~$0.067/ảnh.
PRICE_PER_IMAGE: dict[str, float] = {
    "gemini-3-pro-image": 0.12,
    "gemini-3.1-flash-image": 0.067,
    "gemini-3.1-flash-lite-image": 0.04,
}
DEFAULT_PRICE_PER_IMAGE = 0.067


class GeminiImageProvider(ImageProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str = "", model_name: str = "gemini-3.1-flash-image"):
        self.api_key = api_key
        self.model_name = model_name or "gemini-3.1-flash-image"

    def generate(self, prompt: str) -> bytes:
        url = f"{API_BASE}/{self.model_name}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        parts = (((data.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
        inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
        if not inline or not inline.get("data"):
            raise RuntimeError("Gemini Image không trả về ảnh — kiểm tra lại model hoặc thử lại.")
        return base64.b64decode(inline["data"])

    def test_connection(self) -> ProviderStatus:
        """Gọi GET /v1beta/models (miễn phí) thay vì sinh thử 1 ảnh thật."""
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}")
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(image_count: int, model_name: str = "gemini-3.1-flash-image") -> float:
    return image_count * PRICE_PER_IMAGE.get(model_name, DEFAULT_PRICE_PER_IMAGE)
