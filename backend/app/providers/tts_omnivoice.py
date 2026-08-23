"""OmniVoice (k2-fsa/OmniVoice) — TTS zero-shot voice cloning local qua GPU thật, chạy
như 1 service HTTP RIÊNG (`backend/local_servers/omnivoice_server.py`, venv tách biệt
khỏi backend chính) — KHÁC Piper (`tts_piper.py`, in-process, CPU). Đồng bộ (`httpx`,
khớp convention `image_comfy_sdxl.py`) — RTF 0.025-0.089 theo tài liệu OmniVoice (vài
trăm ms tới ~1-2s cho câu narration thường), không cần mô hình async start/poll như
video local (Wan2.2).

`gpu_lock`: OmniVoice chạy GPU thật (khác Piper CPU, không khoá) — cần khoá giống
Ollama/ComfyUI để tránh tranh chấp VRAM (xem app/providers/gpu_lock.py).
"""
import httpx

from app.providers.base import ProviderStatus, TTSProvider
from app.providers.gpu_lock import gpu_lock

_DEFAULT_BASE_URL = "http://127.0.0.1:8199"
_TIMEOUT_SEC = 120.0  # rộng rãi hơn nhiều so với RTF lý thuyết — phòng lúc model đang load lần đầu/máy chậm


class OmniVoiceProvider(TTSProvider):
    provider_name = "omnivoice"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model_name or "omnivoice"

    def synthesize(self, text: str, *, emotion: str = "", reference_audio: bytes | None = None) -> bytes:
        # emotion bỏ qua — OmniVoice không có tham số emotion rời rạc (điều khiển giọng
        # qua ref_audio (voice cloning) hoặc instruct (voice design), không phải qua đây).
        with gpu_lock:
            return self._synthesize_locked(text, reference_audio=reference_audio)

    def _synthesize_locked(self, text: str, *, reference_audio: bytes | None) -> bytes:
        data = {"text": text}
        files = {"ref_audio": ("ref.wav", reference_audio, "audio/wav")} if reference_audio else None
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            resp = client.post(f"{self.base_url}/synthesize", data=data, files=files)
            if resp.status_code >= 400:
                raise RuntimeError(f"OmniVoice server từ chối: HTTP {resp.status_code}: {resp.text[:500]}")
            return resp.content

    def unload(self) -> None:
        """Giải phóng VRAM OmniVoice đang giữ — gọi trước khi LLM local (Ollama) cần
        nạp model, best-effort giống `local_openai_compat.py::unload()` (chiều ngược
        lại). Đo thật: ComfyUI SDXL + OmniVoice cùng thường trú ~12.1GB/16GB, Ollama nạp
        thêm qwen3:14b (~9.6GB) làm TRÀN VRAM, Research thất bại hẳn (không chỉ chậm) —
        xem IMPLEMENTATION_REPORT.md mục 22. Nuốt lỗi — dọn VRAM thất bại không nên chặn
        luồng chính (LLM)."""
        try:
            with httpx.Client(timeout=10) as client:
                client.post(f"{self.base_url}/unload")
        except Exception:  # noqa: BLE001
            pass

    def test_connection(self) -> ProviderStatus:
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/health")
                resp.raise_for_status()
                data = resp.json()
                ok = bool(data.get("ok"))
                model_loaded = bool(data.get("model_loaded"))
            # Model chưa nạp KHÔNG phải lỗi — có thể do vừa bị `/unload` nhường VRAM cho
            # LLM local (mục 22), `/synthesize` sẽ tự nạp lại (chậm hơn ~vài giây ở lần
            # gọi đầu, model đã cache sẵn trên đĩa).
            message = "OmniVoice server đang chạy, model đã sẵn sàng (local, GPU)" if model_loaded else "OmniVoice server đang chạy (local, GPU) — model hiện chưa nạp vào VRAM, sẽ tự nạp lại ở lần sinh giọng đọc tiếp theo (mất thêm vài giây)."
            return ProviderStatus(ok=ok, message=message)
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(
                ok=False,
                message=f"Không kết nối được tới OmniVoice server ở {self.base_url}. Cần cài + chạy server trước (xem IMPLEMENTATION_REPORT.md). Lỗi: {e}",
            )


def estimate_cost(char_count: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7).
    return 0.0
