"""Provider giả lập — dùng làm mặc định lúc chưa cấu hình Cloud/Local thật.

Quyết định triển khai (xem IMPLEMENTATION_REPORT.md): specs §06 mục 4 yêu cầu chặn
tuyến sản xuất khi chưa có provider LLM nào. Để app chạy được ngay sau khi cài đặt
(không cần API key, không cần GPU) mà vẫn tôn trọng nguyên tắc đó, seed data đăng ký
sẵn MỘT provider `local_endpoint` tên "Local Mock (Dev)" trỏ vào adapter này — về mặt
kiến trúc nó vẫn đi qua đúng interface LLMProvider như Claude/Local GPU thật, người
dùng có GPU chỉ cần thêm provider Local Endpoint trỏ tới Ollama/vLLM và đặt làm mặc
định, không phải sửa code.
"""
import hashlib
import textwrap

from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderStatus


class MockLLMProvider(LLMProvider):
    provider_name = "mock"

    def __init__(self, model_name: str = "mock-deterministic"):
        self.model_name = model_name

    def complete(self, system, messages: list[LLMMessage], *, temperature=0.7, max_tokens=4000) -> LLMResult:
        prompt = "\n".join(m.content for m in messages)
        seed = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
        text = self._fake_response(prompt, seed)
        return LLMResult(text=text, input_tokens=len(prompt) // 4, output_tokens=len(text) // 4, estimated_cost_usd=0.0, model=self.model_name)

    def test_connection(self) -> ProviderStatus:
        return ProviderStatus(ok=True, message="Mock provider — luôn sẵn sàng (không gọi mạng)")

    @staticmethod
    def _fake_response(prompt: str, seed: str) -> str:
        # Sinh nội dung placeholder hợp lệ đủ để pipeline downstream hoạt động khi
        # demo/dev không có key thật. Không dùng cho môi trường thật.
        # Trả nhiều đoạn (paragraph) để các bước downstream cần bóc tách theo đoạn
        # (breakdown script) vẫn ra nhiều beat thay vì 1 khối duy nhất — giữ trải
        # nghiệm demo mặc định (provider Mock) có ý nghĩa dù chưa cấu hình key thật.
        snippet = textwrap.shorten(prompt.replace("\n", " "), width=90, placeholder="…")
        return (
            f'[MOCK-{seed}] Nội dung minh hoạ mở đầu, sinh tự động từ yêu cầu: "{snippet}".\n\n'
            f"[MOCK-{seed}] Đoạn tiếp theo diễn giải chi tiết hơn — đây là placeholder, chưa phải nội dung "
            f"sản xuất thật, cần thay bằng provider AI thật để có chất lượng đạt chuẩn retention.\n\n"
            f"[MOCK-{seed}] Một đoạn ví dụ/case study minh hoạ giả lập, giữ đúng cấu trúc nhiều đoạn để "
            f"pipeline bóc tách theo timeline hoạt động bình thường.\n\n"
            f"[MOCK-{seed}] Đoạn kết, chốt lại ý chính. Vào Cài đặt → Provider AI để kết nối Claude/GPT/Gemini "
            f"hoặc model local (Ollama/vLLM) và thay thế toàn bộ nội dung placeholder này."
        )
