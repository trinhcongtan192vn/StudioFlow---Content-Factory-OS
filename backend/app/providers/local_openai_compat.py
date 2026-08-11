"""Adapter cho model local chạy qua endpoint OpenAI-compatible (§05 mục 3, §10.2b PRD).

Dùng chung cho Ollama / vLLM / LM Studio — chỉ khác nhau ở base_url + model.
Máy dev hiện tại KHÔNG có GPU nên adapter này không được kiểm thử với model thật
trong phiên bản này, nhưng code đã sẵn sàng chạy: bất kỳ endpoint nào tuân thủ
chuẩn `POST {base_url}/chat/completions` (OpenAI schema) đều dùng được, ví dụ:

    base_url = http://localhost:11434/v1   (Ollama)
    model    = qwen2.5:32b / deepseek-r1:32b / kimi-...

Chi phí = 0 (§05 mục 7) vì chạy tại máy, không tính estimated_cost_usd.
"""
import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus


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
        }
        with httpx.Client(timeout=300) as client:
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
