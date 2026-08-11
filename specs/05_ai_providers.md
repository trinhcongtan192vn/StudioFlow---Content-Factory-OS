# 05 — AI Providers (Cloud + Local)

Provider AI ẩn sau **một interface chung**. Pipeline không biết đang gọi Claude hay Qwen local. Đây là điều kiện cho yêu cầu "thay thế provider mà không sửa lõi".

## 1. Phân loại

| Task | Provider hỗ trợ | Mặc định đề xuất |
|---|---|---|
| `llm` | Claude (Anthropic), Gemini (Google), OpenAI (GPT), **+ Local**: Qwen, DeepSeek, Kimi | Claude |
| `tts` | Vbee, ElevenLabs, Gemini TTS | Vbee |
| `image` | Flux, Midjourney | Flux |
| `video` (M2) | Runway, Sora, Gemini (Veo) | Runway |

## 2. Hai loại kết nối

- **`cloud_api`**: gọi API bên thứ ba, cần API key (mã hoá at-rest).
- **`local_endpoint`**: gọi endpoint OpenAI-compatible chạy tại máy (Ollama/vLLM/LM Studio), nhập URL + model, **không cần key**. Chỉ áp dụng cho `llm` ở phạm vi MVP.

## 3. Interface adapter (backend)

Mỗi task có một base class; mỗi provider là một adapter implement nó. Ví dụ LLM:

```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, messages: list, *, stream: bool = False,
                 temperature: float = 0.7, max_tokens: int = 4000) -> LLMResult: ...

    @abstractmethod
    def test_connection(self) -> ProviderStatus: ...

# Adapters
class ClaudeProvider(LLMProvider): ...      # cloud_api
class GeminiProvider(LLMProvider): ...      # cloud_api
class OpenAIProvider(LLMProvider): ...      # cloud_api
class LocalOpenAICompatProvider(LLMProvider): ...  # local_endpoint (Ollama/vLLM)
```

`LocalOpenAICompatProvider` dùng chuẩn OpenAI-compatible (`/v1/chat/completions`) nên Ollama, vLLM, LM Studio đều gọi chung một adapter — chỉ khác `base_url` và `model`.

Tương tự có `TTSProvider`, `ImageProvider`, (M2) `VideoProvider`.

## 4. Factory & chọn provider

```python
def get_llm(task_role: str) -> LLMProvider:
    """task_role: 'research' | 'script' | 'hook' | ...
    Đọc provider_config (§02), lấy provider is_default cho task 'llm',
    trừ khi có override theo project. Trả adapter đã cấu hình."""
```

## 5. Khuyến nghị dùng local vs cloud (giữ ưu tiên retention)

| Bước pipeline | Khuyến nghị | Lý do |
|---|---|---|
| AI Research, nháp dàn ý | **Local OK** (Qwen/DeepSeek…) | Khối lượng lớn, chi phí 0, dữ liệu không rời máy. |
| AI Generation kịch bản chi tiết (sau Gate #1) | **Cloud mạnh nhất** | Ảnh hưởng trực tiếp retention — ưu tiên số 1. |
| Chấm Hook Strength (guardrail) | Local hoặc cloud | Rubric cố định, chấp nhận model khá. |

Người dùng override được ở từng Project. Đây là **khuyến nghị mặc định**, không cứng.

## 6. Fallback

Mỗi task có thể đặt một provider `is_fallback`. Khi provider chính trả lỗi/timeout, tự chuyển fallback một lần, ghi Audit Log.

## 7. Chi phí

- Adapter cloud ước tính chi phí mỗi call (theo token/asset) → cộng vào `budget.spent` (§02).
- Local endpoint chi phí = 0.
- Trước bước sinh asset đắt (video), nếu vượt `soft_limit` → cảnh báo (không chặn).

## 8. Bảo mật

- API key mã hoá at-rest, giải mã trong bộ nhớ khi gọi, **không** trả về client dạng thô (§01, §03).
- Local endpoint URL lưu plaintext (không nhạy cảm).

## 8b. Đã build — provider Mock (dev/demo, không có trong đặc tả gốc)

`app/providers/mock.py` — `MockLLMProvider` implement đúng interface `LLMProvider`
(§3), trả nội dung placeholder xác định (deterministic) mà không gọi mạng. Seed data
đăng ký nó làm provider LLM mặc định (`connection_type: local_endpoint`, tên
"Local Mock (Dev)") để app chạy được ngay sau khi cài đặt mà không cần API key hay
GPU — đúng yêu cầu "chưa cần triển khai model local vì máy chưa có GPU, nhưng code
phải sẵn sàng chạy trên PC có GPU". Khi có GPU: thêm 1 provider Local Endpoint trỏ
Ollama/vLLM (dùng chung `LocalOpenAICompatProvider`) và đặt làm mặc định — không cần
sửa code pipeline.

## 9. Ràng buộc MVP

- TTS/Image config có mặt trong màn Provider AI nhưng **chỉ dùng thật ở M2** (khi có render). MVP chỉ cần LLM hoạt động đầy đủ + prompt cho image/tts được sinh ra trong Pack (không thực thi).
- Video (Runway/Sora/Veo): chỉ khai báo interface, chưa implement (M2).
