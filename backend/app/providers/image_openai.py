"""OpenAI Image (GPT Image) — provider Image đầu tiên thực thi sinh ảnh THẬT (M2
Production Layer). Đồng bộ: 1 request trả thẳng ảnh base64, không cần polling —
khác Video (Sora), xem app/providers/video_sora.py.
"""
import base64

import httpx

from app.providers.base import ImageProvider, ProviderStatus, raise_for_status_with_body

API_URL = "https://api.openai.com/v1/images/generations"

# USD / ảnh — ước tính cố định theo size 1792x1024 (16:9, khớp visual_style_prompt
# "aspect 16:9" đã ép trong prompt), xem specs/05_ai_providers.md. Không phải hoá đơn
# chính xác (giá OpenAI Image tính theo token input/output ảnh phức tạp hơn 1 số cố
# định), đủ cho cảnh báo ngân sách mềm.
PRICE_PER_IMAGE = 0.06


class OpenAIImageProvider(ImageProvider):
    provider_name = "openai"

    def __init__(self, api_key: str = "", model_name: str = "gpt-image-2"):
        self.api_key = api_key
        self.model_name = model_name or "gpt-image-2"

    def generate(self, prompt: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        body = {"model": self.model_name, "prompt": prompt, "size": "1792x1024"}
        with httpx.Client(timeout=180) as client:
            resp = client.post(API_URL, headers=headers, json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64)

    def test_connection(self) -> ProviderStatus:
        """Gọi GET /v1/models (miễn phí) thay vì sinh thử 1 ảnh thật — tránh tốn phí
        mỗi lần bấm "Test" trong Cài đặt → Provider AI."""
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {self.api_key}"})
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(image_count: int) -> float:
    return image_count * PRICE_PER_IMAGE
