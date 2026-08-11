import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self, api_key: str, model_name: str = "gpt-4.1"):
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
        cost = in_tok / 1_000_000 * 2.5 + out_tok / 1_000_000 * 10.0
        return LLMResult(text=text, input_tokens=in_tok, output_tokens=out_tok, estimated_cost_usd=cost, model=self.model_name)

    def test_connection(self) -> ProviderStatus:
        try:
            self.complete("Trả lời đúng 1 từ.", [LLMMessage(role="user", content="ping")], max_tokens=8)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))
