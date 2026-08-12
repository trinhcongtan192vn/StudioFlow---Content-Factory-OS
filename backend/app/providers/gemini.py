import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus


# USD / 1M token (input, output) — theo ai.google.dev/gemini-api/docs/pricing, đối
# chiếu lại 2026-08-12. Model không có trong bảng rơi vào DEFAULT_PRICING.
PRICING: dict[str, tuple[float, float]] = {
    "gemini-3.6-flash": (1.50, 7.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}
DEFAULT_PRICING = (1.25, 5.0)


class GeminiProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def _url(self):
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def complete(self, system, messages: list[LLMMessage], *, temperature=0.7, max_tokens=4000) -> LLMResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]} for m in messages],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(self._url(), json=body)
            resp.raise_for_status()
            data = resp.json()
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        usage = data.get("usageMetadata", {})
        in_tok, out_tok = usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
        price_in, price_out = PRICING.get(self.model_name, DEFAULT_PRICING)
        cost = in_tok / 1_000_000 * price_in + out_tok / 1_000_000 * price_out
        return LLMResult(text=text, input_tokens=in_tok, output_tokens=out_tok, estimated_cost_usd=cost, model=self.model_name)

    def test_connection(self) -> ProviderStatus:
        try:
            self.complete("Trả lời đúng 1 từ.", [LLMMessage(role="user", content="ping")], max_tokens=8)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))
