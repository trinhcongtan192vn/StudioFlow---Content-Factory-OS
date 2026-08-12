"""TTS/Image/Video: khai báo interface theo §05 mục 3, KHÔNG thực thi sinh asset thật
ở M1 (§05 mục 9, §08.3 PRD) — Visual Studio chỉ sinh & lưu PROMPT, không gọi API asset.
Test kết nối vẫn hoạt động (cho phép chuẩn bị provider trước khi M2 bật thực thi).
"""
import httpx

from app.providers.base import ImageProvider, ProviderStatus, TTSProvider, VideoProvider


class NotImplementedMixin:
    def _not_implemented(self, what: str):
        raise NotImplementedError(f"{what} chưa được thực thi ở M1 — theo specs/08 PRD, sinh asset thật thuộc M2 (Production Layer).")


class VbeeTTSProvider(TTSProvider, NotImplementedMixin):
    provider_name = "vbee"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        self._not_implemented("Vbee TTS synthesize")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh giọng đọc thật sẽ mở ở M2")


class ElevenLabsTTSProvider(TTSProvider, NotImplementedMixin):
    provider_name = "elevenlabs"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        self._not_implemented("ElevenLabs TTS synthesize")

    def test_connection(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": self.api_key})
                ok = resp.status_code == 200
            return ProviderStatus(ok=ok, message="Kết nối thành công" if ok else f"HTTP {resp.status_code}")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


class FluxImageProvider(ImageProvider, NotImplementedMixin):
    provider_name = "flux"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Flux image generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh ảnh thật sẽ mở ở M2")


class MidjourneyImageProvider(ImageProvider, NotImplementedMixin):
    provider_name = "midjourney"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Midjourney image generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh ảnh thật sẽ mở ở M2")


class RunwayVideoProvider(VideoProvider, NotImplementedMixin):
    provider_name = "runway"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Runway video generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — render video thật sẽ mở ở M2")


class SoraVideoProvider(VideoProvider, NotImplementedMixin):
    provider_name = "sora"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Sora video generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — render video thật sẽ mở ở M2")


# ---------------------------------------------------------------------------
# TTS/Image/Video của OpenAI & Google Gemini (§05 — bổ sung theo yêu cầu người
# dùng: cùng 1 provider công nghệ (OpenAI/Gemini) có thể vừa là LLM (task=llm)
# vừa là TTS/Image ở đây (task=tts/image, cùng provider_name="openai"/"gemini",
# khác API key/model riêng theo từng task). Anthropic KHÔNG có sản phẩm TTS/Image/
# Video công khai (Claude chỉ nhận ảnh làm input qua vision, không sinh ảnh/audio/
# video) nên không có adapter tương ứng.
# ---------------------------------------------------------------------------
class OpenAITTSProvider(TTSProvider, NotImplementedMixin):
    provider_name = "openai"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        self._not_implemented("OpenAI TTS synthesize")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh giọng đọc thật sẽ mở ở M2")


class GeminiTTSProvider(TTSProvider, NotImplementedMixin):
    provider_name = "gemini"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def synthesize(self, text: str, *, emotion: str = "") -> bytes:
        self._not_implemented("Gemini TTS synthesize")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh giọng đọc thật sẽ mở ở M2")


class OpenAIImageProvider(ImageProvider, NotImplementedMixin):
    provider_name = "openai"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("OpenAI (GPT Image) generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh ảnh thật sẽ mở ở M2")


class GeminiImageProvider(ImageProvider, NotImplementedMixin):
    provider_name = "gemini"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Gemini (Nano Banana) image generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — sinh ảnh thật sẽ mở ở M2")


class VeoVideoProvider(VideoProvider, NotImplementedMixin):
    provider_name = "veo"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Google Veo video generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — render video thật sẽ mở ở M2")
