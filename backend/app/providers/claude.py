import httpx

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus

API_URL = "https://api.anthropic.com/v1/messages"

# USD / 1M token (input, output) — theo bảng giá chính thức docs.claude.com/en/docs/
# about-claude/models/overview, đối chiếu lại 2026-08-12. Model không có trong bảng
# (snapshot cũ, alias tự nhập...) rơi vào DEFAULT_PRICING — ước tính giữa Sonnet/Opus,
# đủ cho cảnh báo ngân sách mềm (§05 mục 7), không phải hoá đơn chính xác.
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}
DEFAULT_PRICING = (3.0, 15.0)


class ClaudeProvider(LLMProvider):
    provider_name = "claude"

    def __init__(self, api_key: str, model_name: str = "claude-sonnet-5"):
        self.api_key = api_key
        self.model_name = model_name

    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def complete(self, system, messages: list[LLMMessage], *, temperature=0.7, max_tokens=4000) -> LLMResult:
        body = {
            "model": self.model_name,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(API_URL, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []))
        usage = data.get("usage", {})
        in_tok, out_tok = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        price_in, price_out = PRICING.get(self.model_name, DEFAULT_PRICING)
        cost = in_tok / 1_000_000 * price_in + out_tok / 1_000_000 * price_out
        return LLMResult(text=text, input_tokens=in_tok, output_tokens=out_tok, estimated_cost_usd=cost, model=self.model_name)

    def test_connection(self) -> ProviderStatus:
        try:
            self.complete("Trả lời đúng 1 từ.", [LLMMessage(role="user", content="ping")], max_tokens=8)
            return ProviderStatus(ok=True, message="Kết nối thành công")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))
