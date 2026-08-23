# 05 — AI Providers (Cloud + Local)

Provider AI ẩn sau **một interface chung**. Pipeline không biết đang gọi Claude hay Qwen local. Đây là điều kiện cho yêu cầu "thay thế provider mà không sửa lõi".

## 1. Phân loại

| Task | Provider hỗ trợ | Mặc định đề xuất |
|---|---|---|
| `llm` | Claude (Anthropic), Gemini (Google), OpenAI (GPT), **+ Local**: Qwen, DeepSeek, Kimi | — (bắt buộc chọn thủ công, xem §8b) |
| `tts` | Vbee, ElevenLabs, OpenAI TTS, Gemini TTS | Vbee |
| `image` | Flux, Flux Kontext (fluxapi.ai), Midjourney, OpenAI (GPT Image), Gemini (Nano Banana) | Flux |
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
- **`local_endpoint`**: gọi endpoint chạy tại máy có GPU, **không cần key**. Nhập URL + model (`llm`/`image`/`video`, endpoint HTTP thật — Ollama/vLLM/LM Studio cho `llm`, ComfyUI cho `image`/`video`); `tts` (Piper) là ngoại lệ chạy in-process, không có `endpoint_url` thật.

> **Đã build (2026-08-13):** mở rộng `local_endpoint` từ chỉ `llm` sang cả `tts`/`image`/
> `video` — trước đây câu này ghi "Chỉ áp dụng cho llm ở phạm vi MVP", không còn đúng.
> Adapter local thật đã có cho cả 4 nhóm: `LocalOpenAICompatProvider` (llm, Ollama —
> verify thật với `qwen3:14b` trên GPU), `PiperTTSProvider` (tts, in-process CPU),
> `ComfySDXLImageProvider` (image, ComfyUI+SDXL, GPU), `ComfyWanVideoProvider` (video,
> ComfyUI+Wan2.2 TI2V-5B chế độ text-to-video, GPU). Chi tiết đầy đủ (lý do chọn từng
> model, sự cố tương thích torch/CUDA với GPU Blackwell, kết quả verify qua pipeline
> thật) xem `IMPLEMENTATION_REPORT.md` mục 16.

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

## 8c. M2 — Provider TTS/Image/Video thực thi thật

6 provider đã thực thi sinh asset THẬT (khác Vbee/Flux/Midjourney/Runway vẫn chỉ khai
báo interface, xem `app/providers/stubs.py`):

| Task | Provider | File adapter | Ghi chú |
|---|---|---|---|
| `tts` | ElevenLabs | `app/providers/tts_elevenlabs.py` | Đồng bộ — 1 request trả thẳng audio bytes MP3. `voice_id` tái dùng cột `endpoint_url` (không thêm cột DB mới) — để trống dùng giọng demo công khai mặc định. |
| `tts` | Gemini TTS | `app/providers/tts_gemini.py` | Đồng bộ — trả PCM thô (`inlineData`, `mimeType` dạng `audio/L16;rate=...`), phải tự bọc WAV header (`_wrap_pcm_as_wav`) trước khi lưu — browser không phát được PCM trần. |
| `image` | OpenAI (GPT Image) | `app/providers/image_openai.py` | Đồng bộ — base64 response, size 1792x1024 (16:9) mặc định, `1024x1792` (9:16) cho project short-form — xem `aspect_ratio` dưới. |
| `image` | Gemini (Nano Banana) | `app/providers/image_gemini.py` | Đồng bộ — base64 qua `inlineData`, decode thẳng (không cần bọc gì thêm, khác TTS). |
| `video` | OpenAI Sora | `app/providers/video_sora.py` | **Bất đồng bộ** — gửi job (`start_generation`) rồi poll (`poll_generation`) tới khi `completed`, có thể mất vài phút. Rủi ro: request/response shape dựng theo suy luận pattern chung OpenAI, CHƯA verify với key thật lúc code. |
| `video` | Google Veo | `app/providers/video_veo.py` | **Bất đồng bộ** — pattern "long-running operation" riêng của Gemini API (`predictLongRunning` → poll `operations/{id}` → tải `video.uri`), khác hẳn cấu trúc REST job của Sora. **Rủi ro cao nhất trong toàn bộ app** — hoàn toàn suy luận từ tài liệu pattern chung, chưa verify với key thật. |

`VideoProvider` (interface, `app/providers/base.py`) mở rộng thêm `start_generation(prompt, *, seconds=8) -> job_id` và `poll_generation(job_id) -> (status, bytes|None)` — provider bất đồng bộ dùng 2 method này thay vì `generate()` đồng bộ cũ (`generate()` raise `NotImplementedError` ở Sora/Veo).

**`aspect_ratio` — mới (2026-08-21, mục 58 IMPLEMENTATION_REPORT.md)**: `ImageProvider.
generate()`/`VideoProvider.generate()`/`start_generation()` thêm optional kwarg
`aspect_ratio: Literal["16:9","9:16"] = "16:9"` (cùng pattern `seed`/`reference_image`
đã có) — `"9:16"` dùng cho project short-form (`Project.format`, xem §04). OpenAI Image
đổi `size` sang `1024x1792` (size dọc CHÍNH THỨC DALL-E 3), Sora sang `720x1280` (size
dọc chính thức), Veo sang `aspectRatio="9:16"` (API hỗ trợ sẵn) — cả 3 xác nhận qua
research, không đoán. SDXL/Wan (local) + Flux Image hoán đổi W/H (tự chọn được vì local/
theo docs BFL). Gemini Image + Flux Video KHÔNG có tham số kích thước trong API (xác
nhận qua research) — Gemini thêm gợi ý "bố cục dọc" vào prompt (best-effort), Flux Video
nhận tham số rồi bỏ qua — cả 2 dựa vào crop-to-fill ở `app/render/assembly.py::
_scale_cover_filter` để LUÔN ra đúng khung 9:16 dù ảnh/video gốc lệch tỷ lệ.

### Provider mặc định + fallback THẬT (không chỉ lưu cờ DB)

`ProviderConfig.is_fallback` trước đây chỉ là cờ lưu DB, hiển thị lại trên UI nhưng
KHÔNG có logic nào đọc — đặt "Fallback" ở Cài đặt không có tác dụng gì. Đã sửa:
`app/providers/factory.py::get_tts_chain(db)`/`get_image_chain(db)`/`get_video_chain(db)`
trả về DANH SÁCH provider đã khởi tạo theo thứ tự ưu tiên (`_candidate_configs()`:
default trước, fallback sau nếu có cấu hình VÀ khác default). `app/render/engine.py`
(2 hàm `generate_visual_asset`/`generate_narration_asset`) và
`app/routers/pack.py::generate_thumbnail` thử LẦN LƯỢT từng provider trong chain —
dừng ở provider đầu tiên gọi API thành công; chỉ báo lỗi khi TẤT CẢ đều lỗi, gộp lý do
từng lần thử (VD `"openai: 401 Unauthorized...; gemini: <lỗi>"`). Phạm vi: chỉ áp dụng
cho `tts`/`image`/`video` — `get_llm()` (LLM) CHƯA có fallback (7+ điểm gọi rải khắp
`pipeline/generation.py`, để làm riêng sau nếu cần). `get_tts`/`get_image`/`get_video`
(số ít, không fallback) vẫn giữ lại, dùng cho `routers/providers.py::test_provider`.

### Đã chuyển sinh asset thật sang Visual Studio (KHÔNG còn ở Render Studio)

Theo phản hồi người dùng: M2 ban đầu đặt việc sinh asset ở "Render Studio" (chỉ mở
được SAU Gate #2) — sai vị trí, người dùng cần sinh + duyệt asset ngay khi đang thao
tác từng shot ở **Visual Studio** (bước ④, TRƯỚC Gate #2). Sửa bằng cách BỎ điều kiện
`project.status` ở `POST /render/start` (trước đó yêu cầu `ready_output`/`exported`/
`published`) — chỉ cần đã có `shots` (giống `/visual/generate` đã yêu cầu
`script.body`). `approve`/`regenerate-visual`/`regenerate-narration` vốn không có
status gate, không đổi gì. **`POST /render/assemble` (ghép MP4) vẫn giữ status gate**
(chuyển từ `start_render` sang đây) — ghép MP4 vẫn chỉ làm được sau Gate #2, đúng vai
trò còn lại của Render Studio (Output Center). Kiến trúc `render.json`/`BackgroundTasks`
không đổi gì, chỉ đổi CHỖ GỌI (frontend) + điều kiện status (backend).

**Orchestration** (`backend/app/render/`, module tách biệt hoàn toàn script core —
"Chống coupling: script core ⟂ render module", §09): `engine.py::run_asset_generation()`
chạy trong `FastAPI BackgroundTasks` (không block request, vì Sora/Veo poll có thể mất
tới ~8 phút — giới hạn `VIDEO_MAX_WAIT_SEC`), sinh **2 thứ** cho mỗi shot — visual
(ảnh/video từ `visual_fx`) và **narration** (TTS hoá `beat.audio` — lời thoại thật,
dùng `beat.direction`/`audio_sfx` chỉ làm gợi ý emotion, KHÔNG TTS hoá `audio_sfx` vì
đó là mô tả nhạc nền chứ không phải lời đọc — xem §07 mục 7). Trạng thái từng shot
(`pending|generating|ready|error` + đường dẫn asset + cờ `approved` cho human review)
lưu ở `render.json` riêng trong `project_dir()`, KHÔNG ghi vào `pack.json`.

**Ghép MP4** (`app/render/assembly.py`): ffmpeg qua `subprocess` — mỗi shot render 1 segment (ảnh: `-loop 1` + trim theo duration beat; video: trim theo duration), mux narration làm audio track, rồi `ffmpeg -f concat` nối toàn bộ segment theo thứ tự timestamp. Bắt buộc **MỌI shot phải `visual_status=="ready"` VÀ `approved=True`** trước khi ghép (human review, đúng yêu cầu §09 M2). Yêu cầu `ffmpeg` có sẵn trên `PATH` — không bundle binary (xem README.md).

**Chi phí**: mỗi lần sinh asset thành công ghi qua `record_asset_usage()` (`app/routers/pipeline.py`, cạnh `record_usage()` gốc cho LLM) vào cùng `AuditLog`/`Budget` — giá ước tính (không phải hoá đơn chính xác): ElevenLabs ~$0.30/1K ký tự, Gemini TTS ~$1-20/1M token, OpenAI Image ~$0.06/ảnh, Gemini Image ~$0.04-0.12/ảnh tuỳ model, Sora ~$0.10-0.30/giây, Veo ~$0.15-0.40/giây.

**API**: `POST/GET /projects/{id}/render/{start,status}`, `POST .../render/shots/{shot_id}/{approve,regenerate-visual,regenerate-narration}`, `POST .../render/assemble`, `GET .../render/{download, shots/{shot_id}/asset/{visual|narration}}` — xem `app/routers/render.py`.

**Frontend**: sinh + duyệt asset THẬT nằm ở `VisualStudio.tsx` (mỗi shot: preview thật
`<img>`/`<video>`/`<audio>`, nút "Tạo ảnh/video"/"Tạo giọng đọc" gọi `/render/*`, nút
"Duyệt", cộng nút hàng loạt "Sinh asset cho toàn bộ block"; 2 nút cũ đổi tên "✎ Viết
lại mô tả bằng AI" — chỉ sửa PROMPT text qua LLM, không sinh asset thật). `RenderStudio.tsx`
(nhúng trong Output Center, thẻ "Render in-app") giờ CHỈ còn đọc `render/status` (tóm
tắt X/Y shot đã duyệt) + nút "Ghép MP4" + preview/tải file cuối — không sinh/duyệt gì
nữa (đã chuyển hết sang Visual Studio).

## 8d. Nhất quán Visual giữa các shot — Tier 1 + Tier 2 (đã build 2026-08-13/16)

> **Tier 2 (ảnh "anchor" tham chiếu) ĐÃ TẮT (2026-08-16, cùng ngày build ra) — xem
> IMPLEMENTATION_REPORT.md mục 21.** Test thật qua GPU với project thật của người dùng
> cho thấy khi ảnh anchor (Thumbnail) là ảnh nhiều chi tiết đồ hoạ (bản đồ minh hoạ,
> không phải ảnh chụp/nhân vật đơn giản), img2img ở MỌI mức denoise/CFG thử qua đều
> hoặc copy nguyên khung/chữ vào shot, hoặc đè mất nội dung riêng từng shot — không có
> điểm cân bằng ổn định. Người dùng chọn quay lại CHỈ Tier 1 (nhất quán qua text).
> `reference_image`/`seed` params + `_read_anchor_image()` + `RenderState.anchor_image_path`
> + gate `_require_thumbnail_approved` đều đã GỠ BỎ khỏi code — mục dưới đây (bao gồm cả
> "Thumbnail = anchor bắt buộc") giữ lại làm lịch sử build, KHÔNG còn phản ánh hành vi
> hiện tại. Hạ tầng img2img/start_image trong 2 adapter local (`image_comfy_sdxl.py`/
> `video_comfy_wan.py`) vẫn còn nguyên trong code (verify tốt với ảnh anchor sạch), chỉ
> không còn được gọi tự động — có thể bật lại nếu sau này cần. **Cập nhật thêm
> (2026-08-16, mục 27/28 IMPLEMENTATION_REPORT.md)**: việc tự sinh sớm `youtube_meta`/
> `titles` ở `/visual/generate` (mô tả ở mục "Thumbnail = anchor bắt buộc" bên dưới)
> cũng đã GỠ BỎ — giờ là nút riêng `POST /projects/{id}/pack/titles-meta` ở Pack Review
> (tab Title & Thumbnail), không còn tự động chạy khi vào Visual Studio.

Vấn đề người dùng phát hiện lúc test thật: visual giữa các shot lệch phong cách/tông
màu dù cùng 1 brand. Xử lý theo 2 tầng, cả 2 đều đã build:

**Tier 1 — không đổi kiến trúc provider:**
- `app/render/engine.py::_build_visual_prompt` — prompt THẬT gửi provider ảnh/video
  LUÔN nối `shot.visual_fx` + `brand.visual_style_prompt` — trước đây chỉ gửi
  `visual_fx` trơn. `shot.audio_sfx` (mood hint không khí/nhịp điệu, KHÔNG PHẢI chỉ dẫn
  âm thanh) CHỈ nối thêm khi sinh **video** — đổi 2026-08-16 (mục 21
  IMPLEMENTATION_REPORT.md): đưa vào prompt ẢNH TĨNH khiến model tự vẽ luôn chữ
  "[SFX]"/"[BGM]"/waveform giả lên ảnh (model ảnh không có khái niệm nhịp điệu/âm thanh
  để "hiểu" mood hint đó theo đúng ý định).
- `_deterministic_seed(project_id, shot_id)` — seed cố định theo hash, thay `time.time()`
  ngẫu nhiên — cùng 1 shot sinh lại cho kết quả gần giống lần trước.
- `app/render/assembly.py::_COLOR_GRADE_FILTER` — filter ffmpeg `eq=...` nhẹ, áp ĐỒNG
  NHẤT cho mọi segment lúc ghép, kéo gần tông màu giữa các provider/model khác nhau.

**Tier 2 — ảnh "anchor" tham chiếu:**
- `ImageProvider.generate()`/`VideoProvider.generate()`/`start_generation()`
  (`app/providers/base.py`) mở rộng thêm `seed: Optional[int]`,
  `reference_image: Optional[bytes]` — TUỲ CHỌN, provider cloud (OpenAI/Gemini/Sora/Veo)
  nhận rồi bỏ qua, không bắt buộc hỗ trợ.
- `image_comfy_sdxl.py` — có `reference_image` → **img2img** (upload ảnh qua
  `POST /upload/image` của ComfyUI → `LoadImage`+`ImageScale`+`VAEEncode` thay
  `EmptyLatentImage`, `KSampler denoise=0.6` thay `1.0`, giữ bố cục/tông màu ảnh gốc).
  KHÔNG dùng IPAdapter (custom node cộng đồng, rủi ro tên/version lệch).
- `video_comfy_wan.py` — có `reference_image` → nối vào input `start_image` của node
  `Wan22ImageToVideoLatent` (node gốc vốn hỗ trợ sẵn nhưng trước đó cố tình để trống để
  chạy T2V thuần — xem code comment).
- `app/render/schemas.py::RenderState.anchor_image_path` — ảnh tham chiếu dùng chung cho
  CẢ project. **Đã build 2026-08-16**: nguồn anchor DUY NHẤT là ảnh **Thumbnail đã
  duyệt** (xem mục dưới) — seed lần đầu gọi `_read_anchor_image()`, giữ cố định suốt
  project (đổi thumbnail sau đó không tự đổi lại anchor các shot đã sinh). Fallback cũ
  (shot ảnh đầu tiên sinh thành công tự thành anchor) vẫn giữ lại phòng khi không có
  thumbnail path hợp lệ.
- Verify thật qua GPU (RTX 5060 Ti): img2img giữ đúng bố cục/tông màu ảnh gốc, chỉ đổi
  đúng phần nội dung theo prompt mới; Wan2.2 chấp nhận + chạy đúng graph có `start_image`
  (`execution_cached` qua các node trước `KSampler` xác nhận wiring đúng).

### Thumbnail = ảnh "anchor" bắt buộc (đã build 2026-08-16)

Theo yêu cầu người dùng: Thumbnail (`pack.youtube_meta`) chuyển vai trò từ "ảnh minh hoạ
cho YouTube" (chỉ cần ở Pack Review) thành **ảnh tham chiếu bắt buộc cho MỌI shot**:

- Tạo/Upload/Duyệt Thumbnail chuyển từ Pack Review sang **ĐẦU Visual Studio**
  (`VisualStudio.tsx::ThumbnailCard`) — chốt TRƯỚC khi sinh asset shot, không phải sau.
  Lý do đặt ở Visual Studio chứ không phải Outline & Hook (đề xuất ban đầu của người
  dùng): `thumbnail_description` sinh từ TOÀN BỘ script (`generate_titles_and_meta`,
  cần `body` — chỉ có sau khi script duyệt), Outline & Hook chưa có script.
  `app/routers/pipeline.py::generate_visual_shots` (`/visual/generate`) giờ tự sinh sớm
  `youtube_meta` (best-effort — nuốt lỗi thiếu provider, không chặn luồng import
  không-cần-AI, xem `tests/test_no_provider.py`).
- **Upload ảnh từ máy** (`POST /pack/thumbnail/upload`, thêm giữa chừng theo yêu cầu
  người dùng) — cùng vai trò anchor như ảnh AI sinh, KHÔNG cần provider ảnh nào.
- `YoutubeMeta.thumbnail_approved: bool` (field mới, `app/schemas/__init__.py`) —
  `POST /pack/thumbnail/approve`. BẮT BUỘC `true` trước khi `render/start` và
  `render/shots/{id}/regenerate-visual` chạy được (`_require_thumbnail_approved`,
  `app/routers/render.py`, 400 rõ ràng nếu chưa duyệt) — KHÔNG áp cho
  `regenerate-narration` (giọng đọc không liên quan ảnh anchor).
- `app/routers/pipeline.py::build_pack` (Pack Review) SỬA để KHÔNG ghi đè `youtube_meta`
  nếu đã có sẵn — gọi lại sẽ xoá mất `thumbnail_status`/`thumbnail_approved` đã duyệt.
- **Bug đã sửa (2026-08-16)**: `<img src={api.thumbnailUrl(project.id)}>` là URL CỐ ĐỊNH
  — người dùng báo "upload/tạo AI lại ảnh nhưng ảnh không đổi" — backend thật ra chạy
  đúng (verify qua file mtime/size đổi thật), chỉ là React/trình duyệt không tự refetch
  vì `src` không đổi giá trị. Sửa bằng cache-bust query param (`?v=<nonce tăng dần>` ở
  `ThumbnailCard`, `?v=<thumbnail_asset_path>` ở Pack Review read-only).

## 8e. OmniVoice — TTS local zero-shot voice cloning (đã build 2026-08-16)

Người dùng phát hiện [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice) — TTS
zero-shot voice cloning mã nguồn mở, 600+ ngôn ngữ (tiếng Việt có **8482 giờ** dữ liệu
training theo `docs/languages.md` của repo — mức dữ liệu cao, không phải hỗ trợ hình
thức). Đề xuất ban đầu: thêm làm provider TTS local thứ 2 (song song Piper), và dùng
Voice Cloning làm "giọng thương hiệu" cố định theo từng kênh qua BrandProfile.

**Lệch kiến trúc có chủ đích so với đề xuất ban đầu**: người dùng đề xuất
`connection_type: local_engine` mới, gọi thẳng `model.generate()` **in-process** trong
tiến trình backend (giống cách LLM local gọi Ollama qua OpenAI-compat client, nhưng
KHÔNG qua HTTP — chạy trực tiếp trong worker). Không làm vậy — 3 lý do:
1. Backend hiện KHÔNG có `torch` (Piper dùng `onnxruntime` CPU, nhẹ) — đưa torch+CUDA
   vào thẳng venv backend lần đầu sẽ phình + dễ xung đột version, biến API server (luôn
   phải phản hồi nhanh) thành nơi giữ 1 model GPU nặng thường trực.
2. Không tận dụng được `gpu_lock` (`app/providers/gpu_lock.py`) — cơ chế ĐÃ CÓ để
   chống tranh chấp VRAM giữa Ollama/ComfyUI (đo thật: chạy đồng thời chậm 2.4 lần, mục
   16.6b) — khoá này chỉ hoạt động cho lệnh gọi HTTP tới 1 process GPU riêng.
3. **Không cần `connection_type` mới** — `factory.py::_build_asset_provider` đã phân
   biệt sẵn local in-process (`_LOCAL_ASSET_PROVIDER_NAMES`, chỉ Piper) và local HTTP
   (nhánh mặc định dùng `base_url`, ComfyUI) trong CÙNG `connection_type="local_endpoint"`.
   OmniVoice đi theo nhánh HTTP — dùng lại nguyên pattern ComfyUI.

→ **OmniVoice chạy như 1 service HTTP RIÊNG** (wrapper mới `backend/local_servers/
omnivoice_server.py`, venv TÁCH BIỆT khỏi `backend/.venv` — người dùng tự cài + chạy,
giống Ollama/ComfyUI, không phải subprocess backend tự spawn), giữ model thường trực
VRAM, expose `POST /synthesize` (multipart: `text` + `ref_audio`/`ref_text`/`instruct`
tuỳ chọn → trả WAV bytes trực tiếp, đồng bộ — RTF 0.025-0.089 theo tài liệu OmniVoice,
không cần mô hình async start/poll như video local). `app/providers/tts_omnivoice.py`
(`OmniVoiceProvider`) gọi qua `httpx`, khoá bằng `gpu_lock` (GPU thật, khác Piper CPU).

**Rủi ro phiên bản torch phát hiện lúc cài thật**: README OmniVoice khuyến nghị
`torch==2.8.0+cu128`. Máy này (RTX 5060 Ti, Blackwell/sm_120) đã xác nhận cu126 thiếu
kernel cho sm_120, cu130 crash với driver hiện tại — chỉ **cu129** chạy đúng (mục 16.2).
Cài `torch==2.8.0+cu129` thay vì gợi ý cu128 của README (cùng version torch với cu129 đã
verify qua ComfyUI, chỉ khác build CUDA) — venv cô lập nên không ảnh hưởng phần còn lại.

**`TTSProvider.synthesize()`** (`app/providers/base.py`) mở rộng thêm
`reference_audio: Optional[bytes] = None` — cùng cách đã thêm `seed`/`reference_image`
cho `ImageProvider`/`VideoProvider` (Tier 2, mục 8d) — TUỲ CHỌN, provider không hỗ trợ
(Vbee/ElevenLabs/OpenAI TTS/Gemini TTS/Piper) nhận rồi bỏ qua, không bắt buộc raise lỗi.

### Voice Cloning làm "giọng thương hiệu" theo kênh

`BrandProfile.voice_clone_ref_path` (field mới, `app/schemas/__init__.py`) — đường dẫn
1 file audio mẫu, upload qua `POST /channels/{id}/brandprofile/voice-sample/upload`
(multipart WAV/MP3, lưu `channel_dir(id)/voice_sample.{ext}`, bump BrandProfile version
như `put_brandprofile`). Tận dụng auto-transcribe của OmniVoice (Whisper ASR) — không
cần người dùng gõ tay `ref_text`. `app/render/engine.py::generate_narration_asset` đọc
`brand.voice_clone_ref_path` (`_read_voice_clone_ref`, cùng pattern `_read_anchor_image`
ở mục 8d) → truyền `reference_audio` cho MỌI shot narration của project thuộc kênh đó —
giữ giọng nhất quán xuyên suốt portfolio kênh mà không cần chọn lại mỗi lần.

**Tự động cắt mẫu về tối đa 10 giây lúc upload** (`_trim_voice_sample`, đã fix
2026-08-16, IMPLEMENTATION_REPORT.md mục 24) — bug thật: mẫu dài (đo thật 57.7s) khiến
OmniVoice lẫn nội dung tham chiếu vào narration sinh ra (đo thật: chỉ ~7.2 ký tự/giây so
với baseline Piper ~26-29). Model tự trim mẫu >20s nhưng chính tài liệu package khuyến
nghị 3-10s — app chủ động cắt sớm hơn hẳn ngưỡng đó thay vì tin cậy hoàn toàn vào model.

**Không làm — Voice Design map từ `brand_voice.tone`** (đề xuất #3 của người dùng): tài
liệu OmniVoice ghi rõ Voice Design "chỉ train chính trên dữ liệu tiếng Trung + tiếng
Anh", tiếng Việt "kết quả không ổn định". App này tiếng Việt là ngôn ngữ DUY NHẤT —
rủi ro chất lượng cao, giá trị thấp (Voice Cloning ở trên giải quyết đúng nhu cầu "giọng
nhất quán theo kênh" tốt hơn). Bỏ hẳn, không xây dựng.

**Tranh chấp VRAM với LLM local (đã fix, IMPLEMENTATION_REPORT.md mục 22)**: OmniVoice
giữ model thường trực trong VRAM (không tự unload như Ollama sau 5 phút) — đo thật lúc
verify: ComfyUI vừa dùng xong + OmniVoice cùng thường trú ~12.1GB/16GB (RTX 5060 Ti) làm
Ollama nạp `qwen3:14b` (~9.6GB) tràn VRAM, Research thất bại hẳn. `factory.py::get_llm()`
giờ tự gọi `_free_local_tts_vram(db)` (POST `omnivoice_server.py::/unload`) ngay trước khi
build provider LLM **local**, best-effort — chỉ chạy khi LLM sắp dùng là `local_endpoint`
(nếu LLM cấu hình qua cloud API, nhánh này không chạy, TTS/Image local giữ nguyên VRAM).
Rủi ro còn lại (chưa xử lý, ghi nhận có chủ đích): fix chỉ giải phóng OmniVoice, không
giải phóng checkpoint SDXL của ComfyUI — nếu ComfyUI vừa sinh xong VÀ cả 3 (SDXL+OmniVoice+
LLM local) cần VRAM cùng lúc vẫn có thể tràn, dù đo thật cho thấy ComfyUI tự giải phóng
VRAM giữa các lần sinh nên trường hợp này hiếm.

## 8f. Flux (Black Forest Labs) — Image + Video thật (đã build 2026-08-16)

Người dùng yêu cầu implement Flux Image thật + hướng dẫn lấy API key, đảm bảo dùng model
"phù hợp nhất đang có trên thị trường", và hỏi thẳng "Flux có tạo được video không?".

**Research trực tiếp lúc code (2026-08-16)** — catalog cũ ở stubs.py/frontend
(`flux-1.1-pro`, `flux-schnell`) đã LỖI THỜI, BFL đã chuyển sang thế hệ **FLUX.2**:
`flux-2-klein-4b`/`-9b` (rẻ nhất, open-weight) < `flux-2-pro` (cân bằng, "dẫn đầu
photorealism 2026") < `flux-2-flex` < `flux-2-max` (chất lượng cao nhất, ~2.3x giá
`pro`). **Chọn `flux-2-pro` làm mặc định** — cân bằng chất lượng/giá cho project dài
10-20 shot ảnh, không ép `max` (tăng chi phí không nhỏ); người dùng tự đổi qua
`model_name` nếu cần chất lượng cao nhất. Dùng bản PINNED (`flux-2-pro`, không phải
`flux-2-pro-preview` — alias này trỏ tới bản MỚI NHẤT, có thể đổi hành vi bất ngờ giữa
các lần gọi), đúng khuyến nghị tái lập kết quả của chính BFL.

**Flux có tạo được video không? — CÓ.** BFL ra mắt **FLUX 3** (23/7/2026) — model
multimodal đầu tiên của hãng vừa sinh ảnh vừa video (tới 20 giây/clip, có audio đồng
bộ), "generally available" qua API tính tới lúc research (không phải hàng chờ/early
access). Endpoint RIÊNG (`/v1/flux-3-video`), khác hẳn dòng FLUX.2 Image — 2 sản phẩm
độc lập. Đánh giá chất lượng công bố: FLUX 3 được chọn hơn Luma Ray 3.2 (93% lượt so
sánh) và Runway Gen-4.5 (77%) — đủ tốt để làm lựa chọn Video cloud thứ 3 cạnh Sora/Veo
đã có. Đã thêm `video_flux.py` (provider_name `flux`, tách biệt với Image dù cùng tên —
2 dict `_IMAGE_ADAPTERS`/`_VIDEO_ADAPTERS` riêng ở factory.py, không xung đột).

**Kiến trúc**: `image_flux.py` (đồng bộ, `generate()` block tới khi xong — cùng cách
OpenAI/Gemini Image) + `video_flux.py` (bất đồng bộ đúng nghĩa `VideoProvider`, cùng
convention Sora/Veo). Cả 2 dùng CHUNG `flux_common.py` (submit + poll qua
`GET /v1/get_result?id=`) vì đây là 2 adapter CÙNG 1 hãng CÙNG 1 cơ chế polling thật sự
giống hệt nhau — khác Sora/Veo (2 hãng riêng, không chung code được).

**`generate_audio=False` cố định cho Video**: FLUX 3 Video sinh audio đồng bộ (thoại,
SFX) ngay trong clip, nhưng `render/assembly.py::_build_segment` LUÔN ghép
`-map 0:v:0 -map 1:a:0` (chỉ lấy stream video từ asset, audio luôn lấy riêng từ
narration TTS) — audio Flux sinh ra bị bỏ hẳn lúc ghép, tắt hẳn để khỏi trả phí/thời
gian sinh audio vô ích (rẻ hơn đáng kể theo bảng giá BFL).

**Cách lấy API key** (hướng dẫn cho người dùng, ghi lại ở đây để không lặp lại chỗ
khác): đăng ký tại **bfl.ai** → vào mục API/Dashboard → tạo API key mới (dạng chuỗi,
không có định dạng `sk-...` như OpenAI) → nạp tiền trước khi dùng (pay-as-you-go, 1
credit = $0.01 USD, KHÔNG có gói miễn phí lâu dài) → dán key vào Cài đặt → Provider AI →
Thêm provider → chọn "Flux" (Image hoặc Video) → dán key, chọn model.

**Giá** (USD, research 2026-08-16, xem `PRICE_PER_MP`/`PRICE_PER_SECOND` trong 2 adapter
để cập nhật khi BFL đổi giá):
| Model | Giá |
|---|---|
| `flux-2-klein-4b` | $0.014/MP |
| `flux-2-klein-9b` | $0.015/MP |
| `flux-2-pro` (mặc định) | $0.03/MP |
| `flux-2-flex` | $0.05/MP |
| `flux-2-max` | $0.07/MP |
| `flux-3-video-hd` (mặc định, 720p) | $0.17/giây |
| `flux-3-video-fhd` (1080p) | $0.29/giây |

**Không có API key thật lúc code** — nhưng đã verify được KHÁ NHIỀU mà không cần key,
bằng cách gọi thật API BFL với key giả để dò đúng hành vi lỗi thật (không đoán):
- Endpoint `GET /v1/get_result` **KHÔNG kiểm tra auth khi id không tồn tại** — trả
  `404 "Task not found"` GIỐNG HỆT NHAU dù key đúng/sai/không gửi key. Phát hiện này làm
  đổi hẳn thiết kế `test_connection()` ban đầu (định dùng endpoint này để check kết nối
  miễn phí như OpenAI/Gemini — KHÔNG dùng được).
- Key sai định dạng UUID → `422 "Invalid API key format"`; đúng định dạng nhưng sai →
  `403 "Not authenticated"` — cả 2 xác nhận thật bằng key giả.
- → `test_connection()` giờ POST 1 job ảnh THẬT (`flux-2-klein-4b`, 256x256, ~$0.0009)
  để xác thực — **KHÔNG miễn phí tuyệt đối** như OpenAI/Gemini (BFL không có endpoint
  auth-check riêng), nhưng chi phí không đáng kể. Dùng chung 1 hàm cho cả Video (không
  submit job video thật $0.85+/lần chỉ để test — cùng 1 key/tài khoản BFL).

Phần CHƯA verify được (không có key thật): đường thành công thật sự (sinh ảnh/video khi
key ĐÚNG) — request/response dựng đúng theo OpenAPI spec chính thức
(`api.bfl.ai/openapi.json`) + tài liệu docs.bfl.ai, không đoán, nhưng nếu lệch so với
API thật khi người dùng test bằng key thật, sửa lại theo lỗi thật (cùng quy ước đã áp
dụng cho Veo/Sora — 2 adapter đó cũng ở trạng thái tương tự lúc build).

## 8g. Flux Kontext (fluxapi.ai) — provider ảnh THÊM MỚI song song §8f (đã build 2026-08-22)

> **Đã build (2026-08-22):** người dùng có sẵn API key nhưng "test connection" báo lỗi ở
> provider Flux (§8f) — điều tra ra key đó thuộc **fluxapi.ai**, dịch vụ bên thứ 3 ĐỘC LẬP
> với BFL chính thức (`bfl.ai`), không dùng chung được. Người dùng chốt: giữ nguyên §8f,
> thêm provider MỚI (`provider_name: "flux_kontext"`) song song cho ai dùng fluxapi.ai —
> xem `app/providers/image_flux_kontext.py`, IMPLEMENTATION_REPORT.md mục 60.

**Khác biệt kỹ thuật với BFL (§8f)** — 2 dịch vụ hoàn toàn tách biệt, KHÔNG dùng chung
key/code được: base URL riêng (`api.fluxapi.ai` thay vì `api.bfl.ai`), header auth khác
(`Authorization: Bearer` thay vì `x-key`), body dùng `aspectRatio` string trực tiếp
(khớp thẳng `AspectRatio` type của app, không cần đổi thành width/height như BFL).

**Phát hiện quan trọng nhất khi research (xác nhận THẬT bằng curl, không tin nguyên văn
tài liệu)**: fluxapi.ai LUÔN trả **HTTP 200** ở mọi trường hợp — kể cả auth sai hay body
thiếu field bắt buộc — trạng thái thật nằm ở field `"code"` trong JSON body (200=OK,
401=auth sai...), khác hẳn quy ước HTTP-status-code chuẩn mà BFL/OpenAI/Gemini/Sora/Veo
đều dùng. Mọi chỗ đọc response của adapter này PHẢI check `data["code"]`, không được chỉ
dựa `resp.status_code`. Tài liệu WebFetch-summarized lúc research còn ghi SAI 1 endpoint
(credit-check ghi `/api/v1/chat/credit`, thật ra `404` — endpoint đúng dò lại được là
`/api/v1/common/credit`) — bài học: luôn verify tài liệu bên thứ 3 bằng gọi API thật
trước khi tin, đặc biệt dịch vụ nhỏ/không chính thức.

**Chỉ hỗ trợ Image** (Kontext), KHÔNG có Video — fluxapi.ai không cung cấp sinh video.
`test_connection()` dùng `GET /api/v1/common/credit` (miễn phí — khác BFL không có
endpoint free nào). `reference_image` KHÔNG hỗ trợ (Kontext nhận ảnh tham chiếu qua
`inputImage` là URL công khai, app desktop này không có nơi host URL tạm — bỏ qua, an
toàn vì Tier 2 vốn tắt mặc định toàn app). Chưa có bảng giá công khai lúc tích hợp —
`estimate_cost()` trả `0.0`, không bịa số.

**Cách lấy API key**: đăng ký tại **fluxapi.ai** (KHÔNG phải bfl.ai) → lấy API key → Cài
đặt → Provider AI → Thêm provider → nhóm Image → chọn "Flux Kontext (fluxapi.ai)".

## 8h. Cải thiện chất lượng ảnh model local SDXL — đợt 1 (đã build 2026-08-22)

Người dùng báo ảnh sinh từ `local_sdxl` (ComfyUI) "khác hoàn toàn và xấu hơn nhiều" so
với Gemini API. Điều tra xác nhận sampler (`steps=30, cfg=7.0, dpmpp_2m+karras`)/resolution
(`1344x768`, đúng bucket SDXL) đều chuẩn — nguyên nhân THẬT gồm 2 phần, xem
IMPLEMENTATION_REPORT.md mục 63:

1. **`visual_fx` chứa chỉ dẫn chèn chữ tiếng Việt lên ảnh** (`[Title Card]:`,
   `[Text Overlay]:`, `[Graphic]:`...) mà pipeline KHÔNG có bước `drawtext`/overlay riêng
   nào — SDXL render chữ rất kém so với Gemini, đây là khác biệt lớn nhất. Fix:
   `app/render/engine.py::_strip_text_overlay_tags()` — xoá các tag này (giữ nguyên nội
   dung của tag `[Visual]:`, tag DUY NHẤT mang mô tả cảnh thật) khỏi prompt gửi riêng cho
   `local_sdxl` (KHÔNG đổi prompt gửi provider khác).
2. **Checkpoint SDXL base gốc chưa fine-tune** — nguyên nhân lớn thứ 2 (theo cộng đồng
   SDXL, xác nhận qua test thật: cùng prompt đã lọc sạch vẫn ra nội dung sai hẳn so với
   mô tả). Xử lý ở đợt 2 (§8i) — checkpoint painterly + Style LoRA thay base gốc.

**`_build_visual_prompt(shot, brand, *, is_video, for_local_sdxl=False)`** — tham số mới
`for_local_sdxl`: `True` (chỉ dùng cho `local_sdxl`) áp `_strip_text_overlay_tags`, nối
bằng ", " (văn phong tag thay câu văn). **Thứ tự (đã sửa mục 66, 2026-08-22)**: NỘI DUNG
CẢNH (`visual_fx`) LUÔN đứng ĐẦU (KHÔNG bị cắt), khối style cố định (§8i) + style kênh
đứng SAU — style kênh cắt về trần CỐ ĐỊNH `_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS=90` ký tự
(không phụ thuộc content dài/ngắn — trước đây "budget còn lại" khiến style phình to nhấn
chìm content ngắn, bug thật đã sửa). `generate_visual_asset()` tính prompt NGAY TRONG
vòng lặp fallback chain (trước tính 1 lần dùng chung) — 1 chain vừa có local vừa có cloud
cần đúng biến thể prompt cho từng provider thử.

**Checkpoint đổi được qua Cài đặt → Provider AI, không cần sửa code** — trước đây
`ComfySDXLImageProvider.model_name` tồn tại nhưng không dùng ở đâu (field "chết", mặc
định giả `"sdxl"`). Giờ: `factory.py::_build_asset_provider` truyền `model_name` cho
`local_sdxl`/`local_wan`; `image_comfy_sdxl.py` dùng `self.model_name or _CHECKPOINT_NAME`
làm `ckpt_name` thật trong workflow ComfyUI. Đổi checkpoint: tải file `.safetensors` vào
`ComfyUI/models/checkpoints/`, điền ĐÚNG tên file (kể cả đuôi) vào ô "Model" của provider
`local_sdxl` — để trống dùng mặc định (xem §8i cho giá trị mặc định hiện tại).

## 8i. Checkpoint & Style LoRA đúng art direction kênh — đợt 2 (đã build 2026-08-22)

Bổ sung §8h — người dùng chỉ ra bảng checkpoint đợt 1 (Juggernaut XL/RealVisXL) SAI HƯỚNG
cho kênh cần phong cách "tranh vẽ tay/sơn dầu, tránh 3D nhựa hoá" (2/3 lựa chọn đó là
photoreal). Chi tiết đầy đủ xem IMPLEMENTATION_REPORT.md mục 64.

**Checkpoint mặc định MỚI**: `paintersCheckpointOilPaint_v11.safetensors` ("Painter's
Checkpoint" v1.1, CivitAI model 240154 — SDXL 1.0 fine-tune hướng painterly, KHÔNG
photoreal) — thay `sd_xl_base_1.0.safetensors`. Xác nhận tải được (không cần đăng nhập)
qua endpoint download API của CivitAI (trang web yêu cầu sign-in nhưng API public).

**Style LoRA** (`BrandProfile.style_lora_path`/`style_lora_strength`, §04) — node
`LoraLoader` (CÓ SẴN trong ComfyUI core, KHÔNG phải custom node — khác IPAdapter Plus đã
cố tình bỏ ở §8d) chèn giữa `CheckpointLoaderSimple` và `KSampler`/`CLIPTextEncode` trong
CẢ 2 workflow (`_build_txt2img_workflow`/`_build_img2img_workflow`) khi `style_lora_path`
khác rỗng. `ComfySDXLImageProvider.generate()` nhận `lora_name`/`lora_strength` — KHÔNG
khai báo trên `ImageProvider` interface chung (chỉ `local_sdxl` cần) — `engine.py` đọc
từ BrandProfile, CHỈ truyền khi gọi đúng provider `local_sdxl`.

2 LoRA đã tải sẵn vào `ComfyUI/models/loras/` (mirror MIỄN PHÍ trên HuggingFace
`EldritchAdam/SDXL_Eldritch_LoRAs` — bản gốc trên CivitAI bị khoá tải, cần API key):
`ClassipeintXL2.1.safetensors` (oil painting) và `InkArtXL_1.2.safetensors` (ink wash —
đặt active mặc định cho kênh demo, khớp "mực tàu, giấy dó" trong `visual_style_prompt`).

**Negative prompt** (`image_comfy_sdxl.py::_NEGATIVE_PROMPT`) mở rộng — "no text, no
title card, no captions" CHUYỂN từ prompt dương (đợt 1) sang đây (negative conditioning
thật, hiệu quả hơn câu phủ định trong prompt dương); thêm `3d render, plastic, cgi,
glossy, photorealistic, smooth plastic surface` chặn hướng bị cấm trong art direction.

**Khối style cố định** (`_LOCAL_SDXL_STYLE_PREFIX`, `engine.py`): `"oil painting,
hand-painted, ink wash, muted warm tones, aged paper texture, cinematic concept art"` —
chèn SAU nội dung cảnh (đổi từ "đầu prompt" sang "sau nội dung" ở mục 66 — xem §8h, bug
thật content ngắn bị style nhấn chìm). HẰNG SỐ dùng chung mọi kênh hiện tại (đơn giản
trước) — CHƯA đưa vào BrandProfile theo từng kênh.

**KHÔNG làm đợt này**: train Style LoRA riêng cho kênh (cần hạ tầng train chưa có), IP-
Adapter (mâu thuẫn quyết định kiến trúc cũ ở §8d).

## 9. Ràng buộc MVP

- TTS/Image/Video config có mặt trong màn Provider AI — **9 provider (ElevenLabs, Gemini TTS, OpenAI Image, Gemini Image, Sora, Veo, Flux Image, Flux Video, Flux Kontext) đã thực thi thật** (§8c/§8f/§8g), còn lại (Vbee, Midjourney, Runway) vẫn chỉ khai báo interface + prompt sinh trong Pack, không thực thi.
- Provider mặc định + fallback thật cho `tts`/`image`/`video` (§8c) — `llm` chưa có fallback.
