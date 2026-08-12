"""ElevenLabs TTS — provider TTS đầu tiên thực thi sinh audio THẬT (M2 Production
Layer). Trước đó chỉ có stub raise NotImplementedError (app/providers/stubs.py).

Ghi chú lựa chọn kỹ thuật: ElevenLabs yêu cầu `voice_id` trong path — ProviderConfig
hiện không có cột riêng cho voice_id (chỉ có model_name dùng cho `model_id` API, VD
"eleven_v3"). Tái dùng `endpoint_url` (String, không ràng buộc chỉ local_endpoint ở
tầng DB) để lưu voice_id cho provider ElevenLabs cụ thể — không thêm cột DB mới cho 1
provider. Để trống → dùng DEFAULT_VOICE_ID (giọng public demo "Rachel").
"""
import httpx

from app.providers.base import ProviderStatus, TTSProvider, raise_for_status_with_body

API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" — voice công khai dùng làm mặc định khi chưa chọn

# USD / 1K ký tự — ước tính theo tier Creator, xem specs/05_ai_providers.md. Không phải
# hoá đơn chính xác, đủ cho cảnh báo ngân sách mềm (giống PRICING các adapter LLM).
PRICE_PER_1K_CHARS = 0.30


class ElevenLabsTTSProvider(TTSProvider):
    provider_name = "elevenlabs"

    def __init__(self, api_key: str = "", model_name: str = "eleven_v3", voice_id: str = ""):
        self.api_key = api_key
        self.model_name = model_name or "eleven_v3"
        self.voice_id = voice_id or DEFAULT_VOICE_ID

    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        url = f"{API_BASE}/text-to-speech/{self.voice_id}"
        headers = {"xi-api-key": self.api_key, "content-type": "application/json"}
        body = {"text": text, "model_id": self.model_name}
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, json=body)
            raise_for_status_with_body(resp)
            return resp.content

    def test_connection(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{API_BASE}/user", headers={"xi-api-key": self.api_key})
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(char_count: int, model_name: str = "") -> float:
    # model_name nhận cho ĐỒNG NHẤT chữ ký với estimate_cost() các adapter khác
    # (tts_gemini.py) — xem ghi chú tương tự ở image_openai.py::estimate_cost.
    return char_count / 1000 * PRICE_PER_1K_CHARS
