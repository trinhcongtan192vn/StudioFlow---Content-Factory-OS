import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus


class GeminiProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-pro"):
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
        cost = in_tok / 1_000_000 * 1.25 + out_tok / 1_000_000 * 5.0
        return LLMResult(text=text, input_tokens=in_tok, output_tokens=out_tok, estimated_cost_usd=cost, model=self.model_name)

    def test_connection(self) -> ProviderStatus:
        try:
            self.complete("Trả lời đúng 1 từ.", [LLMMessage(role="user", content="ping")], max_tokens=8)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))
