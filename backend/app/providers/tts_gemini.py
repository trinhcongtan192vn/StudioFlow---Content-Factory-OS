"""Gemini TTS — provider TTS thứ 2 thực thi sinh audio THẬT (đợt 2, cùng lứa với
Gemini Image/Google Veo — người dùng báo test connection của bộ Gemini không xác
minh được gì vì trước đó vẫn là stub, xem app/providers/stubs.py cũ).

Gemini trả PCM THÔ (`inlineData.mimeType` dạng "audio/L16;rate=24000", KHÔNG có WAV
header) — trình duyệt không phát được PCM trần qua thẻ <audio>, phải tự bọc WAV
header (44 byte RIFF/WAVE chuẩn) trước khi trả bytes ra ngoài.
"""
import base64
import struct

import httpx

from app.providers.base import ProviderStatus, TTSProvider, raise_for_status_with_body

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_VOICE = "Kore"

# USD / 1M token (input text, output audio) — theo ai.google.dev/gemini-api/docs/pricing
# đã research ở M2 (specs/05_ai_providers.md §8c), áp dụng chung cho họ *-tts-preview.
PRICING: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-tts-preview": (1.00, 20.00),
    "gemini-2.5-pro-preview-tts": (1.00, 20.00),
    "gemini-2.5-flash-preview-tts": (0.50, 10.00),
}
DEFAULT_PRICING = (1.00, 20.00)


def _wrap_pcm_as_wav(pcm: bytes, *, sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """Bọc PCM thô thành file WAV chuẩn (44 byte header RIFF/WAVE) — không cần thư
    viện ngoài, đủ để mọi trình phát audio chuẩn (kể cả <audio> trình duyệt) đọc được."""
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", len(pcm),
    )
    return header + pcm


def _sample_rate_from_mime(mime_type: str, default: int = 24000) -> int:
    for part in mime_type.split(";"):
        part = part.strip()
        if part.startswith("rate="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                pass
    return default


class GeminiTTSProvider(TTSProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str = "", model_name: str = "gemini-3.1-flash-tts-preview", voice_id: str = ""):
        self.api_key = api_key
        self.model_name = model_name or "gemini-3.1-flash-tts-preview"
        self.voice_name = voice_id or DEFAULT_VOICE

    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        url = f"{API_BASE}/{self.model_name}:generateContent?key={self.api_key}"
        prompt = f"Đọc với sắc thái: {emotion}. Nội dung: {text}" if emotion else text
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice_name}}},
            },
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        parts = (((data.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
        inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
        if not inline or not inline.get("data"):
            raise RuntimeError("Gemini TTS không trả về audio — kiểm tra lại model/voice hoặc thử lại.")
        pcm = base64.b64decode(inline["data"])
        sample_rate = _sample_rate_from_mime(inline.get("mimeType", ""))
        return _wrap_pcm_as_wav(pcm, sample_rate=sample_rate)

    def test_connection(self) -> ProviderStatus:
        """Gọi GET /v1beta/models (miễn phí) thay vì sinh thử audio thật — tránh tốn
        phí mỗi lần bấm "Test"."""
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}")
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(char_count: int, model_name: str = "gemini-3.1-flash-tts-preview") -> float:
    """Ước tính thô theo ký tự (không có token count thật từ response test_connection-
    free-path) — quy đổi ~4 ký tự/token, chỉ phần output (audio) là đáng kể."""
    price_in, price_out = PRICING.get(model_name, DEFAULT_PRICING)
    approx_tokens = max(1, char_count // 4)
    return approx_tokens / 1_000_000 * price_out
