# 05 — AI Providers (Cloud + Local)

Provider AI ẩn sau **một interface chung**. Pipeline không biết đang gọi Claude hay Qwen local. Đây là điều kiện cho yêu cầu "thay thế provider mà không sửa lõi".

## 1. Phân loại

| Task | Provider hỗ trợ | Mặc định đề xuất |
|---|---|---|
| `llm` | Claude (Anthropic), Gemini (Google), OpenAI (GPT), **+ Local**: Qwen, DeepSeek, Kimi | — (bắt buộc chọn thủ công, xem §8b) |
| `tts` | Vbee, ElevenLabs, OpenAI TTS, Gemini TTS | Vbee |
| `image` | Flux, Midjourney, OpenAI (GPT Image), Gemini (Nano Banana) | Flux |
| `video` (M2) | Runway, Sora (OpenAI), Google Veo | Runway |

> **Đã build vòng 7 (2026-08-12):** bổ sung provider TTS/Image/Video của OpenAI và
> Gemini (`provider_name: "openai"`/`"gemini"` — CÙNG provider_name với `llm` nhưng
> khác `task`, khác model list riêng — tra theo cặp `(task, provider_name)` trong
> `CLOUD_MODELS_BY_TASK`, xem `backend/app/routers/providers.py`). **Anthropic
> (Claude) không có sản phẩm TTS/Image/Video công khai** — chỉ nhận ảnh làm input qua
> vision, không sinh ảnh/audio/video — nên không có adapter Anthropic ở 3 task này,
> chỉ có ở `llm`. Model cụ thể + giá: xem `backend/app/routers/providers.py`
> (`CLOUD_MODELS`/`CLOUD_MODELS_BY_TASK`) — đối chiếu tài liệu chính thức
> `developers.openai.com/api/docs/pricing` và `ai.google.dev/gemini-api/docs/pricing`
> 2026-08-12. Cũng như adapter LLM (§8b), các adapter này CHƯA thực thi sinh asset
> thật ở M1 (`app/providers/stubs.py` — `NotImplementedMixin`), chỉ lưu key + test
> kết nối (`test_connection()` trả `ok=True` khi có key, không gọi API thật) để chuẩn
> bị sẵn cho M2.

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

## 8b. Provider Mock — chỉ dùng thủ công (dev/test), KHÔNG seed mặc định

`app/providers/mock.py` — `MockLLMProvider` implement đúng interface `LLMProvider`
(§3), trả nội dung placeholder xác định (deterministic) mà không gọi mạng. **Đổi theo
yêu cầu người dùng:** cài đặt mới KHÔNG còn tự động seed provider Mock làm mặc định
nữa — người dùng phải chủ động vào Cài đặt → Provider AI kết nối 1 provider thật
(Claude/GPT/Gemini hoặc local endpoint Ollama/vLLM) trước khi chạy được các bước cần
AI. Lý do: seed Mock ngầm khiến pipeline "chạy được" nhưng sinh nội dung giả lập vô
nghĩa mà người dùng không hề hay biết — sai với nguyên tắc "chất lượng kịch bản là ưu
tiên số 1" (§CLAUDE.md).

Khi chưa có provider LLM khả dụng (`enabled=True, is_default=True`, hoặc bất kỳ
provider `enabled` nào cho task `llm`), `app/providers/factory.py::get_llm()` raise
`NoProviderConfiguredError` thay vì âm thầm fallback về Mock; tương tự khi provider đã
cấu hình nhưng khởi tạo lỗi (VD sai API key). Lỗi này được 1 exception handler toàn
cục trong `app/main.py` bắt và trả về **HTTP 400** với `{"detail": "<thông điệp tiếng
Việt, có hướng dẫn vào Cài đặt>"}` — cùng format với mọi `HTTPException` khác trong
app (không dùng format `{error:{code,message}}` ở §03).

Frontend bắt lỗi này ở mọi hành động cần AI (Bắt đầu Research, Duyệt Gate #1, Tạo lại/
Duyệt Script, Tạo Visual, Xem Production Pack, …) qua `ApiError` (`api/client.ts`) và
hiển thị banner `<AiErrorBanner>` (`components/AiErrorBanner.tsx`) với nút "Cấu hình
ngay →" điều hướng thẳng tới màn Cài đặt. Ngoài ra có 1 banner nổi góc dưới-phải toàn
cục (`App.tsx`, dựa trên `GET /bootstrap → has_llm_provider`) hiển thị bất cứ khi nào
chưa có provider LLM nào — kể cả trước khi người dùng bấm hành động nào.

Guardrail check (§08) là NGOẠI LỆ có điều kiện: chỉ cần Provider AI khi
`hook_spoken` khác rỗng (chấm Hook Strength) — script nhập từ file CSV/Excel (không có
hook) chạy guardrail được mà KHÔNG cần provider (`run_guardrail_check(..., db=db)` chỉ
gọi `get_llm()` khi thật sự cần, xem `app/guardrail/check.py`).

`MockLLMProvider` vẫn hữu ích để: (a) pytest suite tạo 1 provider Mock riêng trong
`conftest.py` (không đụng tới seed thật) chạy pipeline test offline, (b) người dùng
tự thêm thủ công qua UI nếu muốn 1 provider "luôn sẵn sàng" cho việc dev/demo không
tốn phí. Khi có GPU: thêm 1 provider Local Endpoint trỏ Ollama/vLLM (dùng chung
`LocalOpenAICompatProvider`) và đặt làm mặc định — không cần sửa code pipeline.

## 8c. M2 — Provider TTS/Image/Video thực thi thật (2026-08-12)

3 provider đã thực thi sinh asset THẬT (khác mọi provider tts/image/video khác vẫn chỉ
khai báo interface, xem `app/providers/stubs.py`):

| Task | Provider | File adapter | Ghi chú |
|---|---|---|---|
| `tts` | ElevenLabs | `app/providers/tts_elevenlabs.py` | Đồng bộ — 1 request trả thẳng audio bytes. `voice_id` tái dùng cột `endpoint_url` (không thêm cột DB mới) — để trống dùng giọng demo công khai mặc định. |
| `image` | OpenAI (GPT Image) | `app/providers/image_openai.py` | Đồng bộ — base64 response, size cố định 1792x1024 (16:9). |
| `video` | OpenAI Sora | `app/providers/video_sora.py` | **Bất đồng bộ** — gửi job (`start_generation`) rồi poll (`poll_generation`) tới khi `completed`, có thể mất vài phút. Đây là điểm rủi ro cao nhất: request/response shape dựng theo suy luận pattern chung OpenAI, CHƯA verify với key thật lúc code — nếu sai, sửa theo message lỗi thật (đã có `raise_for_status_with_body`, xem §8b). |

`VideoProvider` (interface, `app/providers/base.py`) mở rộng thêm `start_generation(prompt, *, seconds=8) -> job_id` và `poll_generation(job_id) -> (status, bytes|None)` — provider bất đồng bộ dùng 2 method này thay vì `generate()` đồng bộ cũ (`generate()` raise `NotImplementedError` ở Sora).

`app/providers/factory.py` có thêm `get_tts(db)`/`get_image(db)`/`get_video(db)` — cùng pattern `get_llm()`: raise `NoProviderConfiguredError` khi chưa cấu hình/khởi tạo được provider cho task đó, không âm thầm bỏ qua.

**Orchestration** (`backend/app/render/`, module MỚI, tách biệt hoàn toàn script core — "Chống coupling: script core ⟂ render module", §09): `engine.py::run_asset_generation()` chạy trong `FastAPI BackgroundTasks` (không block request, vì Sora poll có thể mất tới ~8 phút — giới hạn `VIDEO_MAX_WAIT_SEC`), sinh **2 thứ** cho mỗi shot — visual (ảnh/video từ `visual_fx`) và **narration** (TTS hoá `beat.audio` — lời thoại thật, dùng `beat.direction`/`audio_sfx` chỉ làm gợi ý emotion, KHÔNG TTS hoá `audio_sfx` vì đó là mô tả nhạc nền chứ không phải lời đọc — xem §07 mục 7). Trạng thái từng shot (`pending|generating|ready|error` + đường dẫn asset + cờ `approved` cho human review) lưu ở `render.json` riêng trong `project_dir()`, KHÔNG ghi vào `pack.json`.

**Ghép MP4** (`app/render/assembly.py`): ffmpeg qua `subprocess` — mỗi shot render 1 segment (ảnh: `-loop 1` + trim theo duration beat; video: trim theo duration), mux narration làm audio track, rồi `ffmpeg -f concat` nối toàn bộ segment theo thứ tự timestamp. Bắt buộc **MỌI shot phải `visual_status=="ready"` VÀ `approved=True`** trước khi ghép (human review, đúng yêu cầu §09 M2). Yêu cầu `ffmpeg` có sẵn trên `PATH` — không bundle binary (xem README.md).

**Chi phí**: mỗi lần sinh asset thành công ghi qua `record_asset_usage()` (`app/routers/pipeline.py`, cạnh `record_usage()` gốc cho LLM) vào cùng `AuditLog`/`Budget` — giá ước tính (không phải hoá đơn chính xác): ElevenLabs ~$0.30/1K ký tự, OpenAI Image ~$0.06/ảnh (1792x1024), Sora ~$0.10/giây (`sora-2`) hoặc ~$0.30/giây (`sora-2-pro`).

**API mới**: `POST/GET /projects/{id}/render/{start,status}`, `POST .../render/shots/{shot_id}/{approve,regenerate-visual,regenerate-narration}`, `POST .../render/assemble`, `GET .../render/{download, shots/{shot_id}/asset/{visual|narration}}` — xem `app/routers/render.py`.

**Frontend**: `RenderStudio.tsx` (nhúng trong Output Center, thẻ "Render in-app" — KHÔNG phải step Stepper mới, khớp §06 mục 2 màn ⑦) — bấm "Bắt đầu sinh asset" → poll trạng thái mỗi 3s → xem trước ảnh/video/audio thật từng shot → "Duyệt" từng shot → "Ghép MP4" khi mọi shot đã duyệt → preview + tải file cuối.

## 9. Ràng buộc MVP

- TTS/Image config có mặt trong màn Provider AI — **3 provider (ElevenLabs/OpenAI Image/Sora) đã thực thi thật từ M2** (§8c), còn lại (Vbee, Flux, Midjourney, Runway, Veo, Gemini TTS/Image) vẫn chỉ khai báo interface + prompt sinh trong Pack, không thực thi.
- Video (Runway/Veo): chỉ khai báo interface, chưa implement — Sora đã implement (§8c).
