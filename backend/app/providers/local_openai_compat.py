"""Adapter cho model local chạy qua endpoint OpenAI-compatible (§05 mục 3, §10.2b PRD).

Dùng chung cho Ollama / vLLM / LM Studio — chỉ khác nhau ở base_url + model. **Đã verify
thật** với Ollama + `qwen3:14b` trên GPU thật (RTX 5060 Ti, xem IMPLEMENTATION_REPORT.md
mục 16.2) — không còn là "kiến trúc sẵn sàng chưa test" nữa:

    base_url = http://localhost:11434/v1   (Ollama)
    model    = qwen3:14b (đã verify) / deepseek-r1:14b / kimi-... (chưa thử)

Chi phí = 0 (§05 mục 7) vì chạy tại máy, không tính estimated_cost_usd.

**Quản lý VRAM dùng chung với Image/Video local** (IMPLEMENTATION_REPORT.md mục 16.6b —
đo thật: Ollama giữ model nạp sẵn ~5 phút sau lần gọi cuối theo mặc định, đủ để tranh
chấp VRAM với ComfyUI chạy ngay sau đó, gây thrashing chậm gấp ~2.4 lần):
- `gpu_lock` (module-level, `app/providers/gpu_lock.py`) bọc quanh mỗi lệnh gọi —
  chặn LLM và Image/Video chạy ĐỒNG THỜI trên cùng GPU.
- Gửi kèm `keep_alive: "30s"` trong body — **ghi chú: xác nhận qua test thật là Ollama
  KHÔNG áp dụng field này khi gọi qua `/v1/chat/completions` (OpenAI-compat shim bỏ qua
  field lạ, `ollama ps` vẫn hiện ~5 phút còn lại)** — giữ lại vì vô hại và có thể được
  backend OpenAI-compat khác tôn trọng, nhưng KHÔNG dựa vào nó để giải phóng VRAM.
- `unload()` mới — gọi API gốc của Ollama (`/api/generate` + `keep_alive: 0`, KHÔNG
  phải endpoint OpenAI-compat) để buộc giải phóng VRAM ngay lập tức. Best-effort, nuốt
  lỗi (vLLM/LM Studio không có API tương đương). `app/render/engine.py` gọi hàm này
  trước khi sinh Image/Video local để đảm bảo VRAM trống trước khi ComfyUI cần.
"""
import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus
from app.providers.gpu_lock import gpu_lock


class LocalOpenAICompatProvider(LLMProvider):
    provider_name = "local"

    def __init__(self, base_url: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def complete(self, system, messages: list[LLMMessage], *, temperature=0.7, max_tokens=4000) -> LLMResult:
        body = {
            "model": self.model_name,
            "messages": [{"role": "system", "content": system}] + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "keep_alive": "30s",
        }
        with gpu_lock, httpx.Client(timeout=300) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResult(
            text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            estimated_cost_usd=0.0,
            model=self.model_name,
        )

    def test_connection(self) -> ProviderStatus:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{self.base_url}/models")
                resp.raise_for_status()
            return ProviderStatus(ok=True, message="Endpoint khả dụng")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=f"Không kết nối được tới local endpoint: {e}")

    def unload(self) -> None:
        """Yêu cầu Ollama giải phóng VRAM ngay — dùng API gốc `/api/generate` (không
        phải shim OpenAI-compat, vốn bỏ qua `keep_alive`), `keep_alive: 0` bắt unload
        tức thì. Best-effort — nuốt lỗi (endpoint không phải Ollama, VD vLLM/LM Studio,
        sẽ không có route này, không nên chặn luồng chính vì việc dọn VRAM thất bại."""
        native_base = self.base_url[: -len("/v1")] if self.base_url.endswith("/v1") else self.base_url
        try:
            with httpx.Client(timeout=10) as client:
                client.post(f"{native_base}/api/generate", json={"model": self.model_name, "keep_alive": 0})
        except Exception:  # noqa: BLE001
            pass
