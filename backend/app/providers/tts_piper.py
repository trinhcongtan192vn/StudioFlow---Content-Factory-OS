"""Piper TTS — model tiếng Việt mã nguồn mở, chạy in-process (không phải service HTTP
như Ollama/ComfyUI) — `PiperVoice` load thẳng file `.onnx` bằng onnxruntime, sinh audio
ngay trong tiến trình backend. Verify thật với GPU RTX 5060 Ti (dù bản thân Piper chạy
CPU theo lựa chọn dưới đây — xem lý do).

**Vì sao CPU, không phải GPU**: `PiperVoice.load(..., use_cuda=True)` có hỗ trợ CUDA qua
onnxruntime-gpu, nhưng model Piper (kiến trúc VITS nhỏ, ~30-60MB) đã đủ nhanh trên CPU
(< 1s cho câu vài chục từ) — dùng CPU cho TTS to giải phóng VRAM cho LLM/Image/Video
local (16GB không đủ chạy đồng thời nhiều model nặng), đúng khuyến nghị đã chốt khi
chọn Piper thay VietTTS (specs/05_ai_providers.md).

Không cần `base_url`/API key — model nằm local trên đĩa
(`app/config.py::PIPER_MODELS_DIR`, mặc định `backend/models/piper/`, tải riêng theo
hướng dẫn IMPLEMENTATION_REPORT.md, không commit vào git). `model_name` trên
`ProviderConfig` lưu tên file voice (không kèm đuôi `.onnx`), VD `vi_VN-vais1000-medium`
— cho phép thêm nhiều giọng khác nhau (tải thêm file) mà không cần sửa code.
"""
import io
import wave

from app.config import PIPER_MODELS_DIR
from app.providers.base import ProviderStatus, TTSProvider

DEFAULT_VOICE = "vi_VN-vais1000-medium"

_voice_cache: dict[str, "object"] = {}


def _voice_path(model_name: str) -> "tuple[object, object]":
    onnx_path = PIPER_MODELS_DIR / f"{model_name}.onnx"
    config_path = PIPER_MODELS_DIR / f"{model_name}.onnx.json"
    return onnx_path, config_path


def _load_voice(model_name: str):
    """Cache theo model_name trong process — load lại `PiperVoice` (đọc + khởi tạo
    onnxruntime session) mỗi lần synthesize tốn ~vài trăm ms không cần thiết, vì model
    không đổi giữa các lần gọi trong cùng 1 tiến trình backend."""
    if model_name in _voice_cache:
        return _voice_cache[model_name]
    from piper import PiperVoice  # import trễ — tránh lỗi ở nơi khác nếu chưa cài piper-tts

    onnx_path, config_path = _voice_path(model_name)
    if not onnx_path.exists():
        raise RuntimeError(
            f"Không tìm thấy model giọng Piper tại {onnx_path}. Tải file .onnx + .onnx.json "
            f"từ huggingface.co/rhasspy/piper-voices về {PIPER_MODELS_DIR} (xem IMPLEMENTATION_REPORT.md)."
        )
    voice = PiperVoice.load(onnx_path, config_path=config_path if config_path.exists() else None, use_cuda=False)
    _voice_cache[model_name] = voice
    return voice


class PiperTTSProvider(TTSProvider):
    provider_name = "piper"

    def __init__(self, model_name: str = ""):
        self.model_name = model_name or DEFAULT_VOICE

    def synthesize(self, text: str, *, emotion: str = "", reference_audio: bytes | None = None) -> bytes:
        # emotion bỏ qua — Piper (VITS thuần) không nhận điều khiển cảm xúc qua tham số
        # rời rạc như vậy (khác Gemini TTS dùng emotion làm gợi ý trong prompt).
        voice = _load_voice(self.model_name)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return buf.getvalue()

    def test_connection(self) -> ProviderStatus:
        onnx_path, _ = _voice_path(self.model_name)
        if not onnx_path.exists():
            return ProviderStatus(ok=False, message=f"Không tìm thấy model giọng tại {onnx_path} — xem IMPLEMENTATION_REPORT.md để tải.")
        try:
            _load_voice(self.model_name)
            return ProviderStatus(ok=True, message="Model giọng đã sẵn sàng (local, CPU)")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(char_count: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7). model_name nhận cho đồng nhất
    # chữ ký với các adapter TTS khác (xem tts_elevenlabs.py::estimate_cost).
    return 0.0
