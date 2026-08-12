import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus

API_URL = "https://api.openai.com/v1/chat/completions"

# USD / 1M token (input, output) — theo developers.openai.com/api/docs/pricing, đối
# chiếu lại 2026-08-12. Model không có trong bảng rơi vào DEFAULT_PRICING.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (5.0, 30.0),
    "gpt-5.6-terra": (2.0, 12.0),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.1": (1.25, 10.0),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}
DEFAULT_PRICING = (2.5, 10.0)


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, api_key: str, model_name: str = "gpt-5.6-terra"):
        self.api_key = api_key
        self.model_name = model_name

    def complete(self, system, messages: list[LLMMessage], *, temperature=0.7, max_tokens=4000) -> LLMResult:
        body = {
            "model": self.model_name,
            "messages": [{"role": "system", "content": system}] + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        with httpx.Client(timeout=120) as client:
            resp = client.post(API_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok, out_tok = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        price_in, price_out = PRICING.get(self.model_name, DEFAULT_PRICING)
        cost = in_tok / 1_000_000 * price_in + out_tok / 1_000_000 * price_out
        return LLMResult(text=text, input_tokens=in_tok, output_tokens=out_tok, estimated_cost_usd=cost, model=self.model_name)

    def test_connection(self) -> ProviderStatus:
        try:
            self.complete("Trả lời đúng 1 từ.", [LLMMessage(role="user", content="ping")], max_tokens=8)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))
