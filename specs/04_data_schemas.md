# 04 — Data Schemas (Hợp đồng dữ liệu)

**Đây là nguồn sự thật.** JSON là định dạng máy-đọc; bản người-đọc (Markdown/PDF) sinh ra từ JSON, không ngược lại. Backend biểu diễn các schema này bằng **Pydantic models** (`backend/app/schemas/`). Đổi schema phải cập nhật file này trước.

Nguyên tắc: các khối chưa thuộc mốc hiện tại (ví dụ `repurpose`) vẫn có trong schema nhưng để `null` — tránh đổi schema khi mở mốc sau.

## 1. BrandProfile (cấp kênh)

Inject vào mọi agent AI để giữ bản sắc kênh.

```json
{
  "channel_id": "ch_finance_01",
  "brand_voice": {
    "tone": "chuyên gia, gần gũi, không giáo điều",
    "formality": "trung tính",
    "pacing": "nhanh, câu ngắn",
    "sample_lines": ["...", "..."]
  },
  "content_pillars": [
    { "name": "Kiến thức nền", "weight": 0.7 },
    { "name": "Theo trend", "weight": 0.1 },
    { "name": "Khuyến mãi", "weight": 0.1 },
    { "name": "Tức thời", "weight": 0.1 }
  ],
  "forbidden": ["cam kết lợi nhuận", "từ ngữ giật gân X, Y"],
  "visual_style_prompt": "minimal, tông xanh–trắng, biểu đồ sạch",
  "hook_formats_preferred": ["câu hỏi gây sốc", "con số phản trực giác"],
  "retention_benchmark": {
    "target_hook_strength": 0.7,
    "max_anchor_gap_sec": 45,
    "target_body_len_min": 8
  },
  "logo_path": "",
  "voice_clone_ref_path": "",
  "intro_video_path": "",
  "intro_audio_path": "",
  "bg_music_path": "",
  "bg_music_volume": 0.3,
  "style_lora_path": "",
  "style_lora_strength": 0.8,
  "overlay_effect_path": "",
  "overlay_effect_opacity": 0.5,
  "version": 3
}
```

### Ràng buộc
- `content_pillars[].weight` cộng lại ≈ 1.0.
- `retention_benchmark` dùng bởi guardrail (§08).
- `version` tăng mỗi lần lưu; khớp `brandprofile_version` trong DB (§02).
- `logo_path` — **đã build 2026-08-22**: đường dẫn 1 file ảnh logo kênh, rỗng nếu chưa
  upload. THUẦN hiển thị nhận diện thương hiệu ở màn Cài đặt/Sửa BrandProfile — KHÔNG
  dùng trong pipeline sinh asset/ghép video (khác `intro_video_path`/`voice_clone_ref_
  path`). Upload qua `POST /channels/{id}/brandprofile/logo/upload` (multipart, nhận
  PNG/JPEG/WEBP).
- `voice_clone_ref_path` — **đã build 2026-08-16**: đường dẫn 1 file audio mẫu (giọng
  đọc thương hiệu), rỗng nếu chưa upload. Dùng làm `reference_audio` cho voice cloning
  (OmniVoice, xem `specs/05_ai_providers.md` §8e) khi sinh narration cho MỌI project của
  kênh — provider không hỗ trợ voice cloning bỏ qua field này (không lỗi). Upload qua
  `POST /channels/{id}/brandprofile/voice-sample/upload` (multipart, không qua PUT
  JSON trực tiếp vì cần gửi file).
- `intro_video_path`/`intro_audio_path` — **đã build 2026-08-20**: video/audio thương
  hiệu, phát ở ĐẦU MỌI video của kênh khi ghép MP4 (mục 51 IMPLEMENTATION_REPORT.md).
  CHỈ 1 trong 2 khác rỗng tại 1 thời điểm — endpoint upload
  (`POST /channels/{id}/brandprofile/intro/upload`, multipart, tự nhận diện loại file)
  tự xoá field còn lại + file cũ trên đĩa. Chỉ có `intro_audio_path` → lúc ghép dùng
  ẢNH của shot ĐẦU TIÊN trong từng project làm hình minh hoạ (chỉ khả dụng nếu shot đó
  đã sinh xong visual — xem `app/render/assembly.py::_resolve_intro_source`). Có thể bị
  GHI ĐÈ bởi shot mở đầu riêng của TỪNG project — xem `3b. RenderState` bên dưới.
- `style_lora_path`/`style_lora_strength` — **đã build 2026-08-22 (mục 64)**: Style LoRA
  khoá "chữ ký hình ảnh" cho ảnh sinh bằng provider `local_sdxl` (ComfyUI). `style_lora_
  path` là TÊN FILE thật trong `ComfyUI/models/loras/` (KHÔNG PHẢI đường dẫn tuyệt đối
  như các field asset khác — LoRA sống trong thư mục ComfyUI, không phải channel_dir).
  Rỗng = không dùng LoRA. `style_lora_strength` (mặc định 0.8) là trọng số áp dụng. CHỈ
  áp dụng cho `local_sdxl` — provider khác bỏ qua. Xem `specs/05_ai_providers.md` §8h.
- `bg_music_path`/`bg_music_volume` — **đã build 2026-08-20 (mục 53)**: nhạc nền MẶC
  ĐỊNH của kênh, phát ĐÈ LIÊN TỤC dưới TOÀN BỘ video (kể cả intro) khi ghép MP4 cho mọi
  project của kênh, rỗng nếu chưa upload. `bg_music_volume` (0.0=câm, 1.0=to bằng giọng
  đọc chính, mặc định 0.3) áp dụng khi KHÔNG có override riêng ở project. Upload qua
  `POST /channels/{id}/brandprofile/bg-music/upload` (multipart, luôn audio). Có thể bị
  GHI ĐÈ bởi nhạc nền riêng của TỪNG project (`RenderState.bg_music`, ưu tiên cao hơn) —
  xem `app/render/bg_music.py::resolve_bg_music_source` và `3b. RenderState` bên dưới.
- `overlay_effect_path`/`overlay_effect_opacity` — **đã build 2026-08-22 (mục 68)**:
  hiệu ứng lớp phủ (overlay — VD mưa/tuyết rơi, do người dùng TỰ upload, app không ship
  sẵn preset nào) MẶC ĐỊNH của kênh, blend ĐÈ LIÊN TỤC lên TOÀN BỘ video (kể cả intro)
  khi ghép MP4, cùng nguyên lý áp dụng với `bg_music_path` (KHÔNG phải per-shot như
  intro). LUÔN là video (mp4/webm/mov), rỗng nếu chưa upload. `overlay_effect_opacity`
  (0.0=tắt hẳn, 1.0=full cường độ, mặc định 0.5) áp dụng khi KHÔNG có override riêng ở
  project — dùng làm tham số `colorchannelmixer` giảm độ sáng overlay trước khi blend
  `screen` (blend mode này không có tham số alpha trực tiếp). Upload qua `POST
  /channels/{id}/brandprofile/overlay/upload` (multipart, luôn video). Có thể bị GHI ĐÈ
  bởi overlay riêng của TỪNG project (`RenderState.overlay`, ưu tiên cao hơn) — xem
  `app/render/overlay.py::resolve_overlay_source` và `3b. RenderState` bên dưới.

## 2. Brief (cấp video, đầu vào)

4 nhóm input chuẩn hoá.

```json
{
  "project_id": "prj_2026_0142",
  "channel_id": "ch_finance_01",
  "strategy": {
    "content_matrix_slot": "Kiến thức nền",
    "growth_objective": "kéo traffic mới",
    "conversion_point": "zalo_group"
  },
  "audience": {
    "seo_keywords": ["...", "..."],
    "retention_notes": "khán giả hay thoát ở phút 2 khi lý thuyết dài",
    "pain_points": ["...", "..."]
  },
  "raw_knowledge": {
    "documents": ["path/to/doc1.md"],
    "expert_notes": "...",
    "key_message": "..."
  },
  "brand_voice_override": null
}
```

`conversion_point` enum gợi ý: `affiliate` / `course` / `zalo_group` / `email_list` / `none`.

> **Đã build — lệch so với trên:** design chỉ có 4 lựa chọn trong segmented control:
> `none` / `affiliate` / `course` / `private_traffic` (gộp `zalo_group` thành khái niệm
> tổng quát hơn "kênh riêng tư", bỏ `email_list`). Backend dùng đúng 4 giá trị này.
> Đồng thời `raw_knowledge.documents` đổi từ `list[string path]` sang
> `list[BriefSource]` — mỗi nguồn có `{id, kind: "youtube"|"file", label, status:
> "extracting"|"done"|"error", char_count}` — khớp UI upload file/link YouTube có
> trạng thái trích xuất trong Brief Editor (không có trong đặc tả gốc). Xem
> IMPLEMENTATION_REPORT.md mục Brief.

## 3. ProductionPack (artifact trung tâm)

```json
{
  "project_id": "prj_2026_0142",
  "channel_id": "ch_finance_01",
  "brandprofile_version": 3,
  "status": "approved",
  "script": {
    "hook": { "spoken": "...", "visual": "...", "duration_sec": 4 },
    "body": [
      {
        "timestamp_sec": 5,
        "audio": "lời narration...",
        "visual": "mô tả hình/B-roll...",
        "direction": "chỉ dẫn diễn xuất/dựng...",
        "anchor": true
      }
    ],
    "cta": { "spoken": "...", "conversion_point": "zalo_group" }
  },
  "shots": [
    {
      "shot_id": "s01",
      "asset_type": "broll_image",
      "provider": "flux",
      "prompt": "prompt chuẩn hoá theo visual_style_prompt của kênh",
      "linked_timestamp_sec": 5
    }
  ],
  "titles": [
    { "text": "...", "seo_score_hint": "...", "angle": "curiosity" }
  ],  # ĐÚNG 3 phương án, tối ưu Conversion/CTR, mỗi text tối đa ~90 ký tự (hướng dẫn trong prompt, KHÔNG cắt cứng — 2026-08-17, xem ghi chú dưới) — không phải 5-10 như bản gốc
  "thumbnail_concepts": [
    { "metaphor": "...", "text_overlay": "...", "layout": "..." }
  ],
  "repurpose": { "shortform_marks": [], "community_post": null },
  "retention_check": {
    "hook_strength": 0.72,
    "max_anchor_gap_sec": 38,
    "warnings": []
  },
  "version": 5
}
```

### Enum & ràng buộc
- `status`: khớp enum Project (§02) — giá trị trong Pack phản ánh trạng thái tại thời điểm lưu.
- `shots[].asset_type`: `broll_image` / `motion_graphic` / `stock_footage` / `broll_video`.
- `shots[].provider`: tên provider từ cấu hình (§05) — cloud hoặc local đều được.
- `repurpose`: để `null` ở MVP (mốc M3).
- `retention_check.warnings[]`: mảng object `{ type, severity, at_timestamp_sec, message }`; `severity` = `amber` | `red` (§08).

### Đã build — mở rộng theo design (StudioFlow Prototype.dc.html)

> **Đã build lại, 2026-08-17 (mục 44 IMPLEMENTATION_REPORT.md) — TOÀN BỘ lịch sử
> `research`/`hooks`/`titles`/`youtube_meta.description|hashtags|chapters` bên dưới
> (kể cả các đợt sửa 2026-08-16/17 về SEO→Conversion/CTR, giới hạn ký tự, chapters
> 1/block...) mô tả tính năng **ĐÃ BỊ XOÁ HẲN**, không chỉ đổi hành vi như các đợt
> trước. Theo yêu cầu người dùng: bỏ hẳn luồng AI Research/Outline/Hook + Pack Review/
> Gate #2, "tập trung vào luồng chính: upload script, tạo visual và voice, sau đó
> render". Giữ lại lịch sử dưới đây để thấy được các quyết định đã đưa ra trước khi
> bị xoá; **schema THẬT hiện hành** nằm ở JSON block ngay dưới đây (đã cập nhật khớp
> `backend/app/schemas/__init__.py`).

Design tách quy trình generation thành nhiều bước tương tác nhỏ hơn (Outline+Hook →
Script Studio → **Visual Studio** riêng biệt → ~~Pack Review~~) thay vì 1 bước "AI
Generation" duy nhất — bước Outline+Hook/Pack Review đã bỏ hẳn (mục 44), chỉ còn
Script Studio (nhận script từ import) → Visual Studio → Output. Schema THẬT hiện hành:

```json
{
  "...": "...(như trên)...",
  "script": {
    "hook": "null — không còn sinh Hook bằng AI, giữ field để đọc được project cũ",
    "full_text": "kịch bản liền mạch — vẫn ghi (đồng bộ từ body) nhưng không còn UI sửa tay riêng",
    "source": "import — LUÔN LÀ 'import' cho project mới; 'ai' chỉ còn để đọc project CŨ đã lưu trước 2026-08-17",
    "body": [
      {
        "timestamp_sec": 0, "end_sec": 5, "audio": "...", "visual": "...",
        "direction": "...", "direction_label": "Direction | Audio/SFX",
        "block_id": "B01 (chỉ có khi import)", "visual_type": "Image|Video (chỉ có khi import)",
        "anchor": false, "warning": "Warning | null — cảnh báo guardrail gần nhất, hiển thị inline"
      }
    ],
    "cta": { "spoken", "conversion_point" }
  },
  "shots": [
    { "shot_id", "asset_type", "visual_type": "image|video", "provider", "visual_fx", "audio_sfx", "block_id": "null trừ khi import", "linked_timestamp_sec", "transition_to_next": "cut (mặc định) — xem app/render/transitions.py, mục 33 IMPLEMENTATION_REPORT.md (2026-08-17)", "camera_motion": "none (mặc định) — Ken Burns cho ẢNH tĩnh (zoom/pan/tilt/roll/orbit), xem app/render/camera_motion.py, mục 48 IMPLEMENTATION_REPORT.md (2026-08-19), KHÔNG có tác dụng khi visual_type=video" }
  ],
  "youtube_meta": {
    "thumbnail_description": "chỉnh tay ở Visual Studio (ThumbnailCard) — KHÔNG còn sinh bằng AI",
    "thumbnail_status": "pending|generating|ready|error",
    "thumbnail_asset_path": "null trừ khi đã sinh ảnh thật",
    "thumbnail_provider": "null trừ khi đã sinh ảnh thật",
    "thumbnail_error": "null trừ khi lỗi",
    "thumbnail_approved": "bool — bắt buộc trước khi Visual Studio cho sinh asset shot (ảnh anchor phong cách)"
  }
}
```

> **XOÁ HẲN (2026-08-17, mục 44):** `research` (synthesis + outlines), `hooks`
> (psychological_type/spoken/visual/selected), `titles` (3 phương án Conversion/CTR),
> `youtube_meta.description`/`hashtags`/`chapters`. Không còn trong
> `app/schemas/__init__.py::ProductionPack`/`YoutubeMeta` — project CŨ đọc lại các
> field này sẽ đơn giản là bị bỏ qua (Pydantic không lỗi, chỉ không map vào field nào).

<details><summary>Lịch sử trước khi xoá (2026-08-12 → 2026-08-17, giữ để tham chiếu quyết định)</summary>

- `research` + `hooks`: kết quả AI Research/Hook Variants từng sống trong CHÍNH
  pack.json ngay từ trước Gate #1, thay vì một artifact tạm rời rạc — giữ nguyên tắc
  "Pack JSON là artifact trung tâm" xuyên suốt cả work-in-progress.
- `youtube_meta` (mới lúc đó, top-level): description SEO + chapters + hashtags — cần
  cho quy trình đăng YouTube thật, rộng hơn `titles`/`thumbnail_concepts` gốc.

**Đã build (2026-08-12):** 4 field `thumbnail_*` mới trong `youtube_meta` — theo dõi
trạng thái sinh ảnh thumbnail THẬT ở Pack Review (nút "Tạo ảnh Thumbnail bằng AI",
tái dùng OpenAI Image adapter — M2, `specs/05_ai_providers.md` §8c). Khác Visual
Studio/Render Studio (asset theo shot, sống ở `render.json` riêng), thumbnail là dữ
liệu Pack-level nên nằm thẳng trong `pack.json`/`youtube_meta` — **field `thumbnail_*`
này KHÔNG bị xoá ở mục 44**, vẫn còn nguyên (chỉ đổi nơi duyệt/sinh sang Visual Studio).

**Đã build (2026-08-17):** `titles` TRƯỚC ĐÂY yêu cầu LLM sinh 5-10 tiêu đề đa dạng góc
tiếp cận (curiosity/benefit/seo...). Đổi theo yêu cầu người dùng — chỉ còn ĐÚNG 3 tiêu
đề, ưu tiên khả năng SEO YouTube tốt nhất, sắp thứ tự SEO tốt nhất trước.

**Đã build (2026-08-17, tiếp theo):** đổi mục tiêu tối ưu của `titles` từ SEO sang
**Conversion/CTR** + giới hạn cứng tối đa 50 ký tự/tiêu đề.

**Đã build (2026-08-17, tiếp theo nữa):** tăng giới hạn lên **90 ký tự**, bỏ hẳn cắt
cứng ở backend — chỉ còn hướng dẫn trong prompt.

**Đã build (2026-08-17):** `youtube_meta.chapters` TRƯỚC ĐÂY sinh 1 mốc/block script —
sửa lại LLM tự chọn TỐI ĐA 5-8 mốc theo ngữ nghĩa.

</details>

- **Đã build vòng 4 (2026-08-12)** — nhập kịch bản CSV/Excel (xem `03_api.md` mục
  Script Import), **giờ là con đường DUY NHẤT để có script (2026-08-17, mục 44)**:
  - `script.source: "ai" | "import"` — đánh dấu nguồn gốc để `/visual/generate` biết
    seed shot trực tiếp từ nội dung import (không gọi AI diễn giải lại) hay gọi AI
    tổng hợp prompt chuẩn hoá (nhánh `"ai"`, hành vi gốc không đổi).
  - `script.body[].block_id`, `.visual_type`, `.direction_label`: 3 field mới, chỉ có
    giá trị khi block tới từ file import (6 cột: Mã block, Thời lượng, Loại Visual,
    Visual/FX, Audio/SFX, VO Content) — `direction_label` đổi tên hiển thị cột
    "Direction" thành "Audio/SFX" cho đúng ngữ cảnh dữ liệu.
  - `shots[].prompt` **đổi tên thành `visual_fx`**, `shots[].tts_emotion` **đổi tên
    thành `audio_sfx`** — khớp đúng tên 2 trong 6 cột import, vì 1 shot giờ có thể tới
    từ AI HOẶC từ import trực tiếp. Thêm `shots[].block_id` (liên kết ngược về block
    gốc khi có).

Chi tiết & lý do từng quyết định: xem `IMPLEMENTATION_REPORT.md` ở gốc repo, mục 9.

## 3b. RenderState (M2, TÁCH KHỎI ProductionPack)

> **Đã build 1 phần M2 (2026-08-12).** Trạng thái sinh asset thật + ghép MP4 sống
> trong file **RIÊNG** `render.json` (`backend/app/render/schemas.py`), cố tình KHÔNG
> phải 1 field của `ProductionPack`/`pack.json` — giữ nguyên tắc "script core ⟂
> render module" (§09 Ràng buộc xuyên suốt). Render module chỉ ĐỌC `pack.json`
> (`shots[]`, `script.body[]`), không bao giờ ghi lại vào đó.

```
RenderState
  project_id: string
  shots: ShotRenderStatus[]
    shot_id: string
    visual_status: "pending" | "generating" | "ready" | "error"
    visual_asset_path: string | null      # đường dẫn file trong assets/<shot_id>.<ext> — AI sinh luôn png/mp4; upload tay có thể là jpg/webp/webm/mov (2026-08-17)
    visual_provider: string | null        # tên provider AI, hoặc "upload" nếu người dùng tự tải ảnh/video lên (2026-08-17)
    visual_error: string | null
    approved: bool                        # human review — bắt buộc trước khi ghép
    narration_status: "pending" | "generating" | "ready" | "error"
    narration_asset_path: string | null   # assets/<shot_id>.{mp3|wav} — TTS hoá script.body[].audio (lời thoại thật)
    narration_provider: string | null
    narration_error: string | null
    narration_duration_sec: float | null  # đo THẬT qua ffprobe khi sinh xong — **đã build lại 2026-08-20, mục 52**: NGUỒN THẬT cho độ dài segment lúc ghép MP4 (`assembly.py::_shot_base_duration`) VÀ timeline transcript .srt (`pipeline.py::_build_srt`), thay cho `timestamp_sec`/`end_sec` (script.body) — timestamp kịch bản giờ CHỈ tham khảo, không dùng để render/xuất transcript nữa (fallback khi CHƯA sinh giọng đọc)
  intro: IntroAssetStatus | null          # shot mở đầu RIÊNG của project — mới (2026-08-20), xem ghi chú dưới
    kind: "image" | "video"               # tự suy theo file upload, không phải người dùng chọn tay
    visual_asset_path: string | null      # assets/intro.<ext>
    audio_asset_path: string | null       # assets/intro_audio.<ext> — CHỈ áp dụng/bắt buộc khi kind=="image"
    transition_to_next: string             # hiệu ứng chuyển cảnh intro→shot đầu tiên — mới (2026-08-21, mục 55), mặc định "cut", cùng bảng TRANSITIONS dùng cho shot-to-shot
  bg_music: BgMusicOverride | null        # nhạc nền RIÊNG của project — mới (2026-08-20, mục 53), xem ghi chú dưới
    asset_path: string | null             # assets/bg_music.<ext>
    volume: float                          # 0.0 (câm) .. 1.0 (to bằng giọng đọc chính) — mặc định 0.3
  overlay: OverlayEffectOverride | null   # hiệu ứng lớp phủ RIÊNG của project — mới (2026-08-22, mục 68), xem ghi chú dưới
    asset_path: string | null             # assets/overlay.<ext> — LUÔN video
    opacity: float                         # 0.0 (tắt hẳn) .. 1.0 (full cường độ) — mặc định 0.5
  assembly_status: "not_started" | "assembling" | "done" | "error"
  assembly_error: string | null
  final_video_path: string | null         # renders/final.mp4 sau khi ghép xong
```

Chi tiết: `specs/05_ai_providers.md` §8c, `IMPLEMENTATION_REPORT.md`.

> **Đã build (2026-08-17):** upload ảnh/video tay thay cho AI (`render/shots/{id}/
> upload-visual`) — cùng field `visual_asset_path`/`visual_provider` ở trên, KHÔNG
> field mới. Endpoint vẫn tuân thủ "render module chỉ ĐỌC pack.json" — loại file phải
> khớp `shot.visual_type` có sẵn (không tự đổi), chỉ ghi vào `render.json`.

> **Đã build (2026-08-20, mục 51 IMPLEMENTATION_REPORT.md):** `intro` — shot mở đầu
> riêng của project, KHÔNG gắn với `pack.shots` (không phải AI sinh, không timestamp
> trong kịch bản) — đúng nguyên tắc "render module tách biệt script core". Khi "đủ"
> (video, HOẶC ảnh + audio đi kèm bắt buộc), OVERRIDE HẲN `BrandProfile.intro_video_path`/
> `intro_audio_path` khi ghép — xem `app/render/assembly.py::_resolve_intro_source` cho
> thứ tự ưu tiên đầy đủ. Endpoint: `POST /projects/{id}/render/intro/upload-visual`,
> `POST .../upload-audio` (400 nếu `kind=="video"` — video tự có audio riêng),
> `DELETE .../intro`, `GET .../intro/asset/{visual|audio}`.

> **Đã build (2026-08-21, mục 55 IMPLEMENTATION_REPORT.md):** `intro.transition_to_next`
> — hiệu ứng chuyển cảnh GIỮA intro và shot đầu tiên của kịch bản, cùng bảng
> `app/render/transitions.py::TRANSITIONS` dùng cho `transition_to_next` giữa 2 shot
> thường. `"cut"` (mặc định) ghép cắt cứng như trước; giá trị khác dùng LẠI
> `_xfade_chain` (cùng cơ chế shot-to-shot, mục 43/47) coi intro+thân video như 2 "run".
> `PATCH /projects/{id}/render/intro/transition`.

> **Đã build (2026-08-20, mục 53 IMPLEMENTATION_REPORT.md):** `bg_music` — nhạc nền
> riêng của project, OVERRIDE HẲN `BrandProfile.bg_music_path`/`bg_music_volume` khi có
> `asset_path` — xem `app/render/bg_music.py::resolve_bg_music_source`. Trộn vào audio
> là bước HẬU KỲ CUỐI CÙNG trong `assemble_video()` (SAU intro), không đụng tới video
> stream (`-c:v copy`) — xem `app/render/assembly.py::_mix_bg_music`. Endpoint:
> `POST /projects/{id}/render/bg-music/upload`, `PATCH .../bg-music` (chỉnh `volume`,
> tự tạo record nếu chưa có), `DELETE .../bg-music`, `GET .../bg-music/asset`.

> **Đã build (2026-08-22, mục 68 IMPLEMENTATION_REPORT.md):** `overlay` — hiệu ứng lớp
> phủ (overlay, VD mưa/tuyết rơi) riêng của project, OVERRIDE HẲN `BrandProfile.overlay_
> effect_path`/`overlay_effect_opacity` khi có `asset_path` — xem `app/render/overlay.py
> ::resolve_overlay_source`. Áp dụng CÙNG CƠ CHẾ với `bg_music` (hậu kỳ trên video đã
> ghép xong, LIÊN TỤC suốt toàn bộ video kể cả intro — KHÁC `intro`, chỉ áp dụng đoạn mở
> đầu), nhưng blend VIDEO (`blend=all_mode=screen`, tái encode `-c:v`) chứ không trộn
> AUDIO — xem `app/render/assembly.py::_mix_overlay_effect`. Endpoint:
> `POST /projects/{id}/render/overlay/upload`, `PATCH .../overlay` (chỉnh `opacity`, tự
> tạo record nếu chưa có), `DELETE .../overlay`, `GET .../overlay/asset`.

## 3c. CreativeAsset (Thư viện Creative Asset, ĐỘC LẬP — mới 2026-08-20, mục 53)

> Không gắn channel/project nào — dùng chung toàn app, lưu ở `workspace/library/<kind>/`
> (khác `channels/` — xem `specs/01_architecture.md` §5). Bảng SQLite riêng
> (`app/models/__init__.py::CreativeAsset`), không phải file JSON theo channel/project.

```
CreativeAsset
  id: string                              # "asset_<epoch_ms>"
  kind: "music" | "video" | "image" | "voice"
  name: string                            # tên gốc file lúc upload (không đuôi)
  created_at: datetime
```

Endpoint: `GET /library/assets?kind=`, `POST /library/assets/upload?kind=` (multipart),
`PATCH /library/assets/{id}` (**mới 2026-08-21, mục 54** — body `{name}`, đổi tên hiển
thị, KHÔNG đụng file vật lý — sửa được ngay sau khi bấm "Thêm vào thư viện" ở bất kỳ màn
nào, hoặc bất kỳ lúc nào ở màn Thư viện), `DELETE /library/assets/{id}`, `GET
/library/assets/{id}/file` (Range-request, xem `app/rangefile.py`, mục 49). **Không có**
endpoint "chọn từ thư viện" riêng ở từng nơi upload khác trong app — frontend tự
`fetch()` bytes qua `GET .../file` rồi gọi thẳng API upload sẵn có ở nơi gọi (xem
`IMPLEMENTATION_REPORT.md` mục 53, quyết định kiến trúc).

## 4. Bản người-đọc (export)

Sinh từ ProductionPack:
- **Markdown/PDF:** kịch bản đa cột dạng bảng (timestamp | audio | visual | direction), theo sau là shot list + prompts, title/thumbnail concepts.
- **JSON:** chính `pack.json`.

Export **không** chứa thông tin mà JSON không có — nó là view, không phải nguồn.
