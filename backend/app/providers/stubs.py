"""TTS/Image/Video: khai báo interface theo §05 mục 3, KHÔNG thực thi sinh asset thật.
Test kết nối vẫn hoạt động (chỉ kiểm tra đã lưu key, không gọi API thật) — chuẩn bị
provider trước khi có adapter thật.

Đã thực thi thật — KHÔNG còn ở file này: ElevenLabs (TTS, tts_elevenlabs.py), OpenAI
Image (image_openai.py), Sora (video_sora.py) — M2; Gemini TTS (tts_gemini.py), Gemini
Image (image_gemini.py), Google Veo (video_veo.py) — đợt 2. Các provider còn lại dưới
đây (Vbee, Flux, Midjourney, Runway, OpenAI TTS) vẫn chỉ là khai báo interface — chưa
research/implement, để làm ở đợt sau.
"""
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
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — CHƯA xác minh kết nối thật (provider này chưa gọi API, chỉ kiểm tra đã nhập key)")


class FluxImageProvider(ImageProvider, NotImplementedMixin):
    provider_name = "flux"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Flux image generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — CHƯA xác minh kết nối thật (provider này chưa gọi API, chỉ kiểm tra đã nhập key)")


class MidjourneyImageProvider(ImageProvider, NotImplementedMixin):
    provider_name = "midjourney"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Midjourney image generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — CHƯA xác minh kết nối thật (provider này chưa gọi API, chỉ kiểm tra đã nhập key)")


class RunwayVideoProvider(VideoProvider, NotImplementedMixin):
    provider_name = "runway"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def generate(self, prompt: str) -> bytes:
        self._not_implemented("Runway video generate")

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — CHƯA xác minh kết nối thật (provider này chưa gọi API, chỉ kiểm tra đã nhập key)")


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
        return ProviderStatus(ok=bool(self.api_key), message="Đã lưu key — CHƯA xác minh kết nối thật (provider này chưa gọi API, chỉ kiểm tra đã nhập key)")


