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
  "cultural_lock_positive": "áo tứ thân, khăn mỏ quạ, mái đình làng Bắc Bộ, ngói âm dương",
  "cultural_lock_negative": "japanese kimono, torii gate, korean hanbok, japanese architecture, korean architecture, anime style, manga, japanese art style",
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
  "overlay_effect_path": "",
  "overlay_effect_opacity": 0.5,
  "primary_language": "vi",
  "voice_clone_ref_paths": {},
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
- `cultural_lock_positive`/`cultural_lock_negative` — **đã build 2026-08-23 (mục 75)**:
  chống thiên lệch văn hoá Nhật/Hàn của checkpoint/LoRA "Á Đông" (đa số train từ dữ liệu
  Nhật/Trung/Hàn). `cultural_lock_positive` — từ khoá Việt Nam cụ thể theo triều đại/
  thời kỳ (trang phục, kiến trúc, hoạ tiết), rỗng mặc định (đặc thù từng kênh), áp dụng
  MỌI provider (cloud lẫn local) — nối vào `_build_visual_prompt` NGAY SAU content.
  `cultural_lock_negative` — loại trừ văn hoá ngoại lai. **Đợt dọn dẹp (2026-09-24)**:
  hiện KHÔNG nối vào bất kỳ provider nào — trước đây chỉ có tác dụng qua negative-prompt
  thật của `local_sdxl`/`local_wan` (đã xoá cùng 3 provider local khác, xem
  `specs/05_ai_providers.md`) — để dành nối vào `local_qwen` (có negative_prompt thật)
  sau nếu cần, KHÔNG xoá field/UI vì ngoài phạm vi yêu cầu hiện tại.
- **`motion_tone`/`style_loras`/`flux_style_loras` — ĐÃ XOÁ HOÀN TOÀN (2026-09-24)**: 3
  field này (ràng buộc chuyển động cho `local_wan`, Style LoRA cho `local_sdxl`/
  `local_flux`) hết tác dụng khi người dùng quyết định xoá hẳn 5 provider local cũ
  (SDXL/Flux/Wan/LocalAI ảnh/LocalAI video — chất lượng kém hơn hẳn `local_qwen` theo
  đánh giá thật sau khi so sánh trực tiếp) — xem `specs/05_ai_providers.md` mục dọn dẹp,
  `IMPLEMENTATION_REPORT.md` mục 156.
- **Ảnh tham chiếu phong cách (IPAdapter) — ĐÃ GỠ BỎ HOÀN TOÀN (2026-09-09)**: field
  `style_reference_paths`/`style_reference_weight` (đã build 2026-08-23, mục 75) và toàn
  bộ cơ chế IPAdapter/img2img liên quan đã bị xoá khỏi codebase. Tính năng chưa từng
  verify thật (custom node cộng đồng `ComfyUI_IPAdapter_plus` chưa từng được cài trên máy
  người dùng — mọi lần gọi âm thầm fallback về "không có IPAdapter"). Người dùng yêu cầu
  bỏ hẳn khi rà soát tính năng LoRA Flux mới: "nếu không work thì bỏ luôn tính năng ảnh
  tham chiếu". Xem `specs/05_ai_providers.md` §8k (cập nhật ghi lại quyết định gỡ bỏ).
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
- `primary_language`/`voice_clone_ref_paths` — **mới (2026-09-04)**: giọng đọc đa ngôn
  ngữ cho thị trường nước ngoài. `primary_language` (1 trong 6:
  `vi`/`en`/`de`/`pt_br`/`es`/`fr`, mặc định `"vi"`) quyết định ngôn ngữ nào dùng để
  render video + tính timestamp (field `Shot.audio`/`ShotRenderStatus.narration_*` GỐC
  — không có field mới nào, video/SRT/pack export mặc định KHÔNG đổi hành vi trừ khi đổi
  `primary_language`). `voice_clone_ref_paths` (dict `{lang: path}`) — mẫu giọng clone
  RIÊNG từng ngôn ngữ, thay `voice_clone_ref_path` đơn (field đó GIỮ NGUYÊN, đọc như mẫu
  của `primary_language` khi dict chưa có entry tương ứng — tương thích ngược dữ liệu
  cũ). Upload qua `POST /channels/{id}/brandprofile/voice-sample/upload/{lang}`. Xem
  `app/render/schemas.py::NARRATION_LANGUAGES` (nguồn sự thật danh sách 6 ngôn ngữ).
- `visual_grade`/`grain_enabled`/`aspect_fill_mode`/`bg_music_ducking_enabled` — **đã
  build 2026-08-26 (CHANGE_Semantic_BRoll_Asset_Vault.md §9b)**: mở rộng hậu kỳ theo
  BrandProfile, KHÔNG viết render engine mới (mở rộng `app/render/assembly.py` đã có).
  `visual_grade` (rỗng mặc định = giữ hành vi cũ) chọn 1 trong preset màu cố định
  (`cinematic_warm`/`moody_dark`/`documentary_faded`, danh sách hằng số
  `assembly.py::_GRADE_PRESETS` — KHÔNG cho nhập chuỗi filter tuỳ ý). `grain_enabled`
  (mặc định tắt) bật film grain nhẹ (`noise=alls=8:allf=t+u`). `aspect_fill_mode`
  (`"crop"` mặc định — hành vi cover-crop cũ; `"blur"` — nền là chính nội dung phóng to +
  làm mờ, không mất chi tiết rìa, hữu ích cho clip B-roll từ Asset Vault lệch tỷ lệ).
  `bg_music_ducking_enabled` (mặc định tắt) — tự giảm nhạc nền khi có giọng đọc
  (`sidechaincompress`) thay vì trộn 1 mức volume cố định xuyên suốt. Chuẩn hoá loudness
  EBU R128 (`loudnorm=I=-14:TP=-1.0:LRA=11`) áp dụng LUÔN cho mọi video (không cần field
  BrandProfile — chuẩn hoá kỹ thuật thuần tuý, không phải lựa chọn thẩm mỹ).
> **Đã REVERT (2026-08-27)**: tính năng "2.5D Depth-Parallax" (`CHANGE_2.5D_Parallax_
> Synthesizer.md`, build 2026-08-26 — thêm `BrandProfile.parallax_intensity_default`,
> `Shot.parallax_intensity`, 4 preset `parallax_*` trong `camera_motion`, module
> `app/render/depth_parallax.py`, endpoint sinh video Parallax riêng shot) đã bị GỠ BỎ
> HOÀN TOÀN theo yêu cầu người dùng — không còn field/endpoint/module nào liên quan tồn
> tại trong code. Xem IMPLEMENTATION_REPORT.md mục 87 (lịch sử build) và mục nói về revert
> (lý do gỡ, phạm vi đã xoá) để biết chi tiết.

## 1b. Kho Tài Nguyên / Asset Vault (SQL, ĐỘC LẬP khỏi BrandProfile JSON — mới 2026-08-26, chuyển TOÀN CỤC 2026-08-27)

Kho tư liệu video TOÀN CỤC (CHANGE_Semantic_BRoll_Asset_Vault.md) — màn RIÊNG ở sidebar
("Kho Tài nguyên", dưới Dashboard), hiện TẤT CẢ video/clip từ MỌI kênh, lọc theo kênh qua
query param. 1 `RawVideo` gắn được NHIỀU kênh dạng tag (bảng m2m `raw_video_channel`,
bắt buộc ≥1 lúc import) — trước đây (2026-08-26) mỗi kênh có kho RIÊNG (`channel_id` FK
đơn trên `raw_video`/`processed_clip`, Chroma collection/kênh); đổi hẳn sang TOÀN CỤC theo
yêu cầu người dùng, xem `specs/02_database.md` mục `raw_video`/`raw_video_channel`/
`processed_clip`. 3 bảng SQL (`raw_video`/`raw_video_channel`/`processed_clip`) + 1 Chroma
collection TOÀN CỤC (`workspace/asset_vault/vault.chroma/`, lọc kênh ở tầng SQL sau khi
overfetch), KHÁC `CreativeAsset` (§3c, dùng lại NGUYÊN VẸN, đứng ngoài mọi kênh — Asset
Vault là NGUYÊN LIỆU THÔ bị cắt thành nhiều clip con). Tiến trình thật khi tải video (yt-dlp
`progress_hooks`) và khi cắt cảnh (PySceneDetect `callback=` cho bước phát hiện, đếm vòng
lặp cho bước cắt) — xem `raw_video.progress_current`/`progress_total`/`progress_label`.
`shots[].linked_clip_id` **KHÔNG tồn tại** trên `Shot` (ProductionPack) —
field tương đương sống trên `ShotRenderStatus.linked_clip_id` (`3b. RenderState` bên
dưới), để việc gán clip từ Kho đi ĐÚNG con đường `upload-visual` đã có (module `render.py`
chỉ ĐỌC `pack.json`, không bao giờ ghi lại). `shots[].asset_type` (đã có sẵn giá trị
`stock_footage`, xem §3 bên dưới) hiện KHÔNG được set tự động khi gán clip từ Kho — đây
là quyết định đơn giản hoá có chủ ý (tránh module `render.py` phải ghi `pack.json`), có
thể bổ sung sau nếu cần phân loại `asset_type` chính xác hơn ở tầng script.

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
        "anchor": false, "warning": "Warning | null — cảnh báo guardrail gần nhất, hiển thị inline",
        "audio_by_lang": "{lang: text} — mới 2026-09-04, giọng đọc đa ngôn ngữ. Rỗng {} với script cũ/file import 1 cột VO. `audio` (field gốc, trên) LUÔN = audio_by_lang[primary_language] — xem app/pipeline/script_import.py"
      }
    ],
    "cta": { "spoken", "conversion_point" }
  },
  "shots": [
    { "shot_id", "asset_type", "visual_type": "image|video", "provider", "visual_fx", "audio_sfx", "block_id": "null trừ khi import", "linked_timestamp_sec", "transition_to_next": "cut (mặc định) — xem app/render/transitions.py, mục 33 IMPLEMENTATION_REPORT.md (2026-08-17)", "camera_motion": "none (mặc định) — Ken Burns cho ẢNH tĩnh (zoom/pan/tilt/roll/orbit), xem app/render/camera_motion.py, KHÔNG có tác dụng khi visual_type=video" }
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
  narration_speed: float                  # mới (2026-09-02, mục 109) — mặc định 1.0, chỉnh ở Script Studio, xem ghi chú dưới
  shots: ShotRenderStatus[]
    shot_id: string
    visual_status: "pending" | "generating" | "ready" | "error"
    visual_asset_path: string | null      # đường dẫn file trong assets/<shot_id>.<ext> — AI sinh luôn png/mp4; upload tay có thể là jpg/webp/webm/mov (2026-08-17)
    visual_provider: string | null        # tên provider AI, hoặc "upload" nếu người dùng tự tải ảnh/video lên (2026-08-17)
    visual_error: string | null
    approved: bool                        # cờ human review tuỳ chọn — KHÔNG còn bắt buộc trước khi ghép (bỏ gate 2026-09-02, mục 107, theo yêu cầu người dùng); vẫn ghi lại qua POST .../approve nhưng Visual Studio không còn UI nào gọi tới
    linked_clip_id: string | null         # mới (2026-08-26) — trỏ tới ProcessedClip.clip_id khi visual_provider=="asset_vault" (Channel Asset Vault, §1b); dùng cho dedup (usage_count/last_used_at) + cảnh báo rights ở Guardrail
    saved_to_vault_clip_id: string | null # mới (2026-09-11) — chiều NGƯỢC lại linked_clip_id: set khi visual CỦA CHÍNH shot này đã được lưu vào Kho Tài Nguyên (nút "Lưu vào Kho tài nguyên") — trỏ tới ProcessedClip.clip_id vừa tạo/cập nhật, dùng cho badge UI + cập nhật đè khi lưu lại
    narration_status: "pending" | "generating" | "ready" | "error"
    narration_asset_path: string | null   # assets/<shot_id>.{mp3|wav} — TTS hoá script.body[].audio (lời thoại thật)
    narration_provider: string | null
    narration_error: string | null
    narration_duration_sec: float | null  # đo THẬT qua ffprobe khi sinh xong — **đã build lại 2026-08-20, mục 52**: NGUỒN THẬT cho độ dài segment lúc ghép MP4 (`assembly.py::_shot_base_duration`) VÀ timeline transcript .srt (`pipeline.py::_build_srt`/`pack_export.py::build_srt_text`), thay cho `timestamp_sec`/`end_sec` (script.body) — timestamp kịch bản giờ CHỈ tham khảo, không dùng để render/xuất transcript nữa (fallback khi CHƯA sinh giọng đọc). **Cắt nhỏ cue dài (2026-09-12, mục 141)** — khoảng `(start, duration)` tính từ field này giờ được `app/render/captions.py::split_block_into_cues` chia lại thành nhiều cue SRT ngắn hơn khi text 1 block dài hơn `DEFAULT_MAX_CUE_CHARS`, xem `03_api.md`
    narration_translations: { [lang]: TranslatedNarrationStatus }  # mới (2026-09-04) — giọng đọc CÁC NGÔN NGỮ KHÁC ngôn ngữ chính, xem ghi chú riêng bên dưới
      narration_status, narration_asset_path, narration_provider, narration_error, narration_duration_sec, narration_updated_at  # CÙNG Ý NGHĨA field narration_* gốc ở trên, chỉ khác: KHÔNG có narration_started_at (không có UI đồng hồ đếm riêng cho ngôn ngữ khác)
  intro: IntroAssetStatus | null          # shot mở đầu RIÊNG của project — mới (2026-08-20), xem ghi chú dưới
    kind: "image" | "video"               # tự suy theo file upload, không phải người dùng chọn tay
    visual_asset_path: string | null      # assets/intro.<ext>
    audio_asset_path: string | null       # assets/intro_audio.<ext> — CHỈ áp dụng/bắt buộc khi kind=="image"
    transition_to_next: string             # hiệu ứng chuyển cảnh intro→shot đầu tiên — mới (2026-08-21, mục 55), mặc định "cut", cùng bảng TRANSITIONS dùng cho shot-to-shot
  character_reference: CharacterReferenceStatus | null  # ảnh nhân vật tham khảo RIÊNG của project — mới (2026-09-09, mục 127), xem ghi chú dưới
    image_path: string | null             # assets/character_reference.<ext>
    description: string                    # TỰ SINH qua VisionProvider lúc upload/recaption (đồng bộ) — nối vào MỌI prompt sinh ảnh của project, sửa tay được qua PATCH
    caption_error: string | null           # lỗi sinh mô tả tự động (KHÔNG chặn upload — ảnh vẫn lưu, chỉ description rỗng)
  bg_music: BgMusicOverride | null        # nhạc nền RIÊNG của project — mới (2026-08-20, mục 53), xem ghi chú dưới
    asset_path: string | null             # assets/bg_music.<ext>
    volume: float                          # 0.0 (câm) .. 1.0 (to bằng giọng đọc chính) — mặc định 0.3
  overlay: OverlayEffectOverride | null   # hiệu ứng lớp phủ RIÊNG của project — mới (2026-08-22, mục 68), xem ghi chú dưới
    asset_path: string | null             # assets/overlay.<ext> — LUÔN video
    opacity: float                         # 0.0 (tắt hẳn) .. 1.0 (full cường độ) — mặc định 0.5
    disabled: bool                         # mới (2026-09-02, mục 105) — tắt HẲN overlay cho project này, kể cả khi kênh CÓ overlay mặc định (khác `asset_path=null`, vốn vẫn ngầm kế thừa kênh)
  background_video: BackgroundVideoOverride | null  # video nền CHUNG cho toàn bộ block — mới (2026-09-02, mục 106), nhiều video (mục 110), xem ghi chú dưới
    asset_paths: string[]                 # assets/background_video_<ts>_<n>.<ext> — LUÔN video, KHÔNG có field volume/opacity (chỉ lấy hình, không audio) và KHÔNG có cấp kênh mặc định để kế thừa. Thứ tự = thứ tự upload (đổi từ `asset_path` đơn cũ — mục 110)
    random_order: bool                    # mới (2026-09-02, mục 110) — mặc định false; true = xáo trộn thứ tự video 1 LẦN mỗi lượt ghép (không xáo lại mỗi vòng lặp khi loop)
    transition: string                    # mới (2026-09-02, mục 110) — mặc định "cut"; cùng danh sách TRANSITIONS dùng cho shot-to-shot, áp dụng GIỮA các video liên tiếp trong playlist
  layers: VideoLayer[]                    # layer video ĐỊNH VỊ theo lưới 3x3 (VD voice wave, logo) — mới (2026-09-02, mục 112), xem ghi chú dưới
    id: string
    asset_path: string                    # assets/layer_<ts>_<n>.<ext> — có/không kênh alpha tuỳ blend_mode (xem dưới)
    position: "top-left"|"top-center"|"top-right"|"middle-left"|"center"|"middle-right"|"bottom-left"|"bottom-center"|"bottom-right"  # mặc định "bottom-center"
    width_pct: float                      # % chiều rộng khung hình xuất, mặc định 0.3 — chiều cao tự co theo tỉ lệ gốc
    opacity: float                        # mặc định 1.0
    blend_mode: "alpha" | "screen"        # mới (2026-09-02, mục 113) — mặc định "alpha" (nguồn CÓ SẴN kênh alpha); "screen" = nguồn NỀN ĐEN ĐẶC, screen-blend cục bộ đúng vùng layer
  image_layers: ImageLayer[]              # layer ẢNH định vị (VD khung viền, watermark) — mới (2026-09-02, mục 115), xem ghi chú dưới. Song song VideoLayer, KHÁC 2 điểm: nguồn LUÔN ảnh tĩnh, position có thêm "full"
    id: string
    asset_path: string                    # assets/imglayer_<ts>_<n>.<ext> — png/jpg/webp
    position: "top-left"|"top-center"|"top-right"|"middle-left"|"center"|"middle-right"|"bottom-left"|"bottom-center"|"bottom-right"|"full"  # mặc định "bottom-center"; "full" = phủ TOÀN khung hình, bỏ qua width_pct
    width_pct: float                      # % chiều rộng khung hình xuất, mặc định 0.3 — bỏ qua khi position=="full"
    opacity: float                        # mặc định 1.0
    blend_mode: "alpha" | "screen"        # mặc định "alpha"; "screen" = ảnh nền đen đặc/không nền
  caption_layer: CaptionLayer | null      # layer CAPTION (phụ đề cứng burn-in) — mới (2026-09-12, mục 142), xem ghi chú dưới. 1 CẤU HÌNH DUY NHẤT/project (KHÁC layers/image_layers — list, upload file)
    enabled: bool                         # mặc định false
    position: "top-left"|"top-center"|"top-right"|"middle-left"|"center"|"middle-right"|"bottom-left"|"bottom-center"|"bottom-right"  # mặc định "bottom-center" — KHÔNG có "full" (không có ý nghĩa cho chữ)
    size_pct: float                       # cỡ chữ = % CHIỀU CAO khung hình xuất, mặc định 0.045 — khác width_pct (% chiều RỘNG) của layer video/ảnh
    opacity: float                        # mặc định 1.0
    lang: string | null                   # null = dùng ĐÚNG ngôn ngữ đang ghép video (export_lang); khác đi = ngôn ngữ caption ĐỘC LẬP với ngôn ngữ giọng đọc
  assembly_status: "not_started" | "assembling" | "done" | "error"
  assembly_error: string | null
  assembly_started_at: string | null      # mốc TOÀN BỘ assembly bắt đầu — dùng hiện "Đã chạy: X" ở RenderStudio.tsx
  assembly_progress: AssemblyProgress | null  # tiến trình ghép — mới (mục 43), xem ghi chú dưới
    stage: "background_video" | "segments" | "concat"  # "background_video" — mới (2026-09-02, mục 108)
    current: int
    total: int
    stage_started_at: string | null       # mốc STAGE HIỆN TẠI bắt đầu — mới (2026-09-02, mục 108), KHÁC assembly_started_at (toàn bộ assembly)
  final_video_path: string | null         # renders/final.mp4 sau khi ghép xong
  final_video_lang: string | null         # mới (2026-09-11, mục 134) — ngôn ngữ giọng đọc dùng lúc ghép gần nhất thành công (null cho render cũ trước tính năng chọn ngôn ngữ xuất video — fallback BrandProfile.primary_language)
  short_exports: ShortVideoExport[]       # mới (2026-09-12, mục 137) — xuất short-video 9:16 từ 1 khoảng block, xem ghi chú dưới. Tối đa 3 phần tử/project (chặn ở router, KHÔNG chặn ở schema)
    id: string                            # "short_<ts>_<hex6>"
    start_block_id: string
    end_block_id: string
    regenerate_images: bool               # true = sinh lại ẢNH (không bao giờ video) đúng 9:16 cho shot ảnh trong khoảng; false (mặc định) = giữ asset gốc + crop-fill (đổi từ letterbox, mục 138)
    lang: string | null                   # mới (2026-09-12, mục 140) — ngôn ngữ giọng đọc dùng xuất, LUÔN đã resolve với export mới (null chỉ gặp ở export cũ trước tính năng này — fallback BrandProfile.primary_language)
    status: "pending" | "generating_images" | "assembling" | "done" | "error"
    error: string | null
    progress_current: int | null
    progress_total: int | null
    progress_label: string | null
    video_path: string | null             # renders/short/<id>/short_final.<ext> sau khi xong
    created_at: string | null
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
> riêng của project, OVERRIDE `BrandProfile.bg_music_path`/`bg_music_volume` — xem
> `app/render/bg_music.py::resolve_bg_music_source`. Trộn vào audio là bước HẬU KỲ CUỐI
> CÙNG trong `assemble_video()` (SAU intro), không đụng tới video stream (`-c:v copy`) —
> xem `app/render/assembly.py::_mix_bg_music`. Endpoint:
> `POST /projects/{id}/render/bg-music/upload`, `PATCH .../bg-music` (chỉnh `volume`,
> tự tạo record nếu chưa có), `DELETE .../bg-music`, `GET .../bg-music/asset`.
>
> **Đã đổi hành vi (2026-08-23, mục 71 IMPLEMENTATION_REPORT.md):** `asset_path` và
> `volume` giờ override ĐỘC LẬP nhau thay vì all-or-nothing — `asset_path` ưu tiên
> project > brand (fallback riêng biệt); `volume` ưu tiên project (nếu object override
> TỒN TẠI, dù chưa có `asset_path`) > brand. Cho phép "dùng nhạc nền của kênh, chỉnh âm
> lượng riêng cho project này" chỉ bằng `PATCH .../bg-music`, không cần upload lại file.

> **Đã build (2026-08-22, mục 68 IMPLEMENTATION_REPORT.md):** `overlay` — hiệu ứng lớp
> phủ (overlay, VD mưa/tuyết rơi) riêng của project, OVERRIDE HẲN `BrandProfile.overlay_
> effect_path`/`overlay_effect_opacity` khi có `asset_path` — xem `app/render/overlay.py
> ::resolve_overlay_source`. Áp dụng CÙNG CƠ CHẾ với `bg_music` (hậu kỳ trên video đã
> ghép xong, LIÊN TỤC suốt toàn bộ video kể cả intro — KHÁC `intro`, chỉ áp dụng đoạn mở
> đầu), nhưng blend VIDEO (`blend=all_mode=screen`, tái encode `-c:v`) chứ không trộn
> AUDIO — xem `app/render/assembly.py::_mix_overlay_effect`. Endpoint:
> `POST /projects/{id}/render/overlay/upload`, `PATCH .../overlay` (chỉnh `opacity`, tự
> tạo record nếu chưa có), `DELETE .../overlay`, `GET .../overlay/asset`.
>
> **Đã đổi hành vi (2026-09-02, mục 105 IMPLEMENTATION_REPORT.md):** thêm `disabled` —
> `DELETE .../overlay` giờ set `disabled=True` (tắt HẲN, không còn fallback ngầm về
> overlay mặc định cấp kênh — trước đây KHÔNG có cách tắt hẳn khi đang kế thừa). `PATCH
> .../overlay/inherit` (mới) đặt lại `disabled=False`, cùng pattern `intro.disabled`/
> `render/intro/inherit`.

> **Đã build (2026-09-02, mục 106 IMPLEMENTATION_REPORT.md):** `background_video` — video
> nền CHUNG cho TOÀN BỘ block, khác hẳn `overlay`/`bg_music` (KHÔNG có cấp kênh mặc định
> để kế thừa, thuần override của project). Lúc ghép, dựng 1 bản "master" loop
> (`-stream_loop -1`) đúng nguồn upload cho tới khi phủ hết tổng thời lượng timeline shot
> list (SAU reflow), scale/color-grade CHỈ 1 LẦN — xem `app/render/assembly.py::_build_
> background_video_master`. Shot NÀO CHƯA cấu hình visual riêng (`ShotRenderStatus.
> visual_asset_path == null`) không còn bị chặn cứng lúc ghép (trước đây MỌI shot bắt
> buộc phải `visual_status=="ready"`) — tự lấy ĐÚNG đoạn nền tương ứng trên timeline
> (offset cộng dồn, KHÔNG loop riêng biệt từng shot — xem `_extract_background_video_
> chunk`) làm nội dung. Shot ĐÃ có visual riêng vẫn giữ NGUYÊN yêu cầu `ready` (`approved`
> không còn được kiểm — bỏ gate 2026-09-02, mục 107) và THAY THẾ TOÀN MÀN HÌNH cho đúng
> khoảng thời gian của nó (không phải chồng mờ/PiP) — nền chỉ hiện lại SAU khi hết shot
> đó. Endpoint: `POST /projects/{id}/render/background-video/upload`, `DELETE .../
> background-video`, `GET .../background-video/asset`.

> **Đã build (2026-09-02, mục 110 IMPLEMENTATION_REPORT.md):** nhiều video nền — theo
> yêu cầu người dùng ("cho phép upload nhiều video làm nền, cho phép set random loop
> on/off, cho phép set hiệu ứng chuyển cảnh giữa các video"). `asset_paths` (list, đổi
> từ `asset_path` đơn) — mỗi lần `POST .../upload` THÊM 1 video (KHÔNG còn thay thế tại
> chỗ). Trước khi loop (`_build_background_video_master`, không đổi), nếu có ≥2 video —
> `_build_background_video_playlist` (mới) nối chúng thành 1 "playlist" DUY NHẤT trước:
> scale/grade TỪNG clip rồi nối bằng filter `concat` (`transition=="cut"`) hoặc `xfade`
> THẬT (khác "cut", video-only — không audio, khác `_xfade_chain` của pipeline chính vốn
> phải blend cả audio). `random_order=true` — xáo trộn thứ tự `asset_paths` 1 LẦN mỗi
> lượt `assemble_video()` (KHÔNG mutate danh sách gốc, KHÔNG xáo lại mỗi vòng lặp khi
> `-stream_loop -1` lặp lại) — giữ đơn giản đúng yêu cầu "random loop on/off". Chỉ 1
> video (case phổ biến nhất) — bỏ qua HẲN bước playlist, dùng thẳng video đó, giữ NGUYÊN
> 100% hành vi mục 106 (không tốn thêm 1 lần re-encode vô ích). `assembly_progress`
> (mục 108) cộng thêm 1 đơn vị "playlist" khi có ≥2 video: `bg_total = 2 (playlist +
> master) + số shot trống`, so với `1 + số shot trống` khi chỉ 1 video. Endpoint mới:
> `DELETE .../background-video/{index}` (bỏ 1 video), `PATCH .../background-video`
> (`{random_order?, transition?}`) — `GET .../background-video/asset` đổi thành
> `GET .../background-video/asset/{index}`.

> **Đã build (2026-09-02, mục 108 IMPLEMENTATION_REPORT.md):** `assembly_progress.stage`
> thêm `"background_video"` — bước dựng video nền chung (`_build_background_video_master`
> + cắt chunk cho từng shot trống) chạy TRƯỚC Pass 2 (segment thật) khi project có cấu
> hình video nền, có thể mất vài phút với video dài (re-encode phủ hết tổng thời lượng
> timeline). TRƯỚC ĐÂY bước này chạy trong lúc `assembly_progress` đứng yên ở
> `stage="segments", current=0` (đặt sẵn từ đầu hàm cho có `total` ngay) — UI hiện nhầm
> "Đang ghép cảnh 0/N..." dù segment thật CHƯA bắt đầu, trông như bị treo. Đơn vị tiến
> trình tự nhiên: 1 (dựng master) + 1/chunk cắt cho mỗi shot trống. `stage_started_at`
> (mới, cùng đợt) — mốc STAGE HIỆN TẠI bắt đầu, reset lại NGAY trước khi Pass 2 chạy —
> ước lượng thời gian còn lại (`RenderStudio.tsx::remainingSec`) tính theo elapsed từ mốc
> này (không phải từ `assembly_started_at` toàn cục), tránh gộp nhầm thời gian dựng video
> nền vào trung bình thời gian/segment.

> **Đã build (2026-09-02, mục 109 IMPLEMENTATION_REPORT.md):** `narration_speed` — tốc
> độ phát giọng đọc cho TOÀN BỘ block của project, chỉnh qua `PATCH /projects/{id}/
> render/narration-speed` (nút ở Script Studio, KHÔNG PHẢI Visual Studio). Áp dụng bằng
> TIME-STRETCH file audio (ffmpeg `atempo`) NGAY SAU khi provider TTS sinh xong — xem
> `engine.py::generate_narration_asset`/`_apply_narration_speed` — KHÔNG PHẢI 1 tham số
> API riêng của từng provider TTS (ElevenLabs/Gemini/Piper/OmniVoice hỗ trợ speed khác
> nhau, có provider hoàn toàn không hỗ trợ) — hoạt động ĐỒNG NHẤT bất kể provider nào
> đang cấu hình, không cần sửa từng adapter. `narration_duration_sec` (ShotRenderStatus)
> đo SAU khi đã time-stretch — mọi logic downstream (segment duration lúc ghép, timeline
> transcript .srt) tự động dùng đúng thời lượng đã điều chỉnh mà không cần biết gì về
> khái niệm "speed". CHỈ áp dụng cho lần (re)generate MỚI — đổi giá trị KHÔNG tự sinh lại
> narration đã có sẵn (đúng nguyên tắc "không tự chạy ngầm, người dùng tự bấm sinh lại"),
> cần bấm "Sinh giọng đọc cho toàn bộ block" hoặc "Sinh lại TOÀN BỘ giọng đọc" (đều đã
> chuyển từ Visual Studio sang Script Studio cùng đợt này) để asset MỚI dùng tốc độ vừa
> chỉnh. Giá trị hợp lệ: 0.5–2.0 (400 nếu ngoài khoảng — phạm vi giữ trong ngưỡng ffmpeg
> `atempo` xử lý tốt bằng 1 lần filter, không cần chain nhiều lần).

> **Đã build (2026-09-04 IMPLEMENTATION_REPORT.md):** `narration_translations` — giọng
> đọc đa ngôn ngữ cho thị trường nước ngoài, theo yêu cầu người dùng ("Cho phép tạo nhiều
> voice giọng đọc hỗ trợ Anh/Việt/Đức/Brazil/Tây Ban Nha/Pháp"). Ngôn ngữ CHÍNH của kênh
> (`BrandProfile.primary_language`) tiếp tục dùng NGUYÊN field `narration_*`/`Shot.audio`
> gốc — render video/timestamp/SRT chính KHÔNG đổi hành vi. Văn bản dịch từng ngôn ngữ
> (`ScriptBodyItem.audio_by_lang`) đọc từ file import (cột `VO (VI)`/`VO (DE)`/... —
> `app/pipeline/script_import.py`) hoặc sửa tay (`PATCH .../script/body/{index}/
> translation/{lang}`). Engine TTS: chỉ OmniVoice hỗ trợ voice cloning per-language
> (`reference_audio` = `BrandProfile.voice_clone_ref_paths[lang]`, tái dùng
> `TTSProvider.synthesize()` sẵn có — KHÔNG thêm interface mới); ElevenLabs/Gemini TTS
> vẫn dùng được (tự nhận diện ngôn ngữ từ text) nhưng KHÔNG clone qua field này. Output
> Pack Export (`app/render/pack_export.py`) xuất thêm `transcript_<lang>.srt` +
> `narration_full_<lang>.mp3` cho MỖI ngôn ngữ có ít nhất 1 block đã dịch (ngôn ngữ chưa
> dùng tới bị bỏ qua hoàn toàn, không liệt kê "thiếu"). Endpoint mới: `POST .../render/
> narration-translations/{lang}/start`, `POST .../render/shots/{shot_id}/regenerate-
> narration-translation/{lang}`, `GET .../render/shots/{shot_id}/asset/narration/{lang}`,
> `GET .../render/narration-download/{lang}`, `GET .../script/transcript-srt/{lang}`.
> Script Studio: thanh 6 tag chọn ngôn ngữ đang xem/thao tác (mặc định = ngôn ngữ chính)
> thay UI panel Audio + mọi nút hàng loạt; panel Tiếng Việt tham chiếu hiện SONG SONG khi
> ngôn ngữ chính khác Việt VÀ đang xem ngôn ngữ khác Việt.

> **Đã build (2026-09-02, mục 112 IMPLEMENTATION_REPORT.md):** `layers` — layer video
> ĐỊNH VỊ theo lưới 3x3, theo yêu cầu người dùng ("thêm layer voice wave (dạng video
> loop) vào bên trên video nền... chia khung hình thành 9 phần và cho phép lựa chọn vị
> trí"). KHÁC `OverlayEffectOverride` (screen-blend, phủ HẾT khung hình liên tục, dành
> cho clip nền đen VD mưa/tuyết) — layer ở đây dùng nguồn CÓ SẴN KÊNH ALPHA (WebM VP9/
> MOV ProRes4444 trong suốt, xác nhận với người dùng asset thực tế của họ có alpha) và
> filter `overlay` chuẩn (không phải `blend`) để ĐỊNH VỊ tại 1 trong 9 ô lưới thay vì phủ
> hết khung hình. `list[VideoLayer]` (không phải 1 field đơn) — nhiều layer cùng lúc, VD
> voice wave góc dưới + logo góc trên. Vị trí → toạ độ dùng THẲNG biến runtime của ffmpeg
> (`main_w/main_h/overlay_w/overlay_h`) trong filter `overlay`, không tính pixel cụ thể ở
> Python — tự đúng tỉ lệ dù xuất độ phân giải nào (xem `assembly.py::_grid_position_
> expr`). Độ mờ (`opacity`) chỉnh qua `colorchannelmixer=aa={opacity}` trên kênh alpha
> CÓ SẴN của nguồn — khác cách overlay hiệu ứng lớp phủ phải giảm SÁNG (không có alpha
> để chỉnh trực tiếp). Áp dụng NGAY SAU overlay hiệu ứng lớp phủ (nếu có) trong hậu kỳ
> cuối cùng (`assembly.py::_composite_layers`) — layer LUÔN nổi TRÊN CÙNG, không bị mưa/
> tuyết che. Endpoint: `POST /projects/{id}/render/layers/upload` (multipart `file` +
> form `position`/`width_pct`/`opacity`, THÊM 1 layer mỗi lần gọi), `PATCH .../layers/
> {layer_id}`, `DELETE .../layers/{layer_id}`, `GET .../layers/{layer_id}/asset`.

> **Đã build (2026-09-02, mục 113 IMPLEMENTATION_REPORT.md):** `blend_mode` — theo yêu
> cầu người dùng ("tôi chỉ có video layer nền đen thôi, hãy process nền đen"): asset
> thật của người dùng KHÔNG có kênh alpha (khác giả định lúc thiết kế mục 112). Thêm
> `"screen"` (khác mặc định `"alpha"`, mục 112) — screen-blend CỤC BỘ đúng vùng layer,
> cùng kỹ thuật `_mix_overlay_effect` (nền đen "biến mất" khi blend screen) nhưng KHÔNG
> phủ hết khung hình — `assembly.py::_composite_layers` chế độ này: (1) `crop` đúng vùng
> nền tương ứng vị trí layer từ khung hình chính (dùng CHUNG `_grid_position_expr` với
> `overlay`, chỉ khác tên biến runtime của `crop`: `in_w/in_h/out_w/out_h`), (2)
> `format=gbrp` cả 2 nhánh rồi `blend=all_mode=screen` cho ra 1 "miếng vá" đã hoà trộn,
> (3) `overlay` miếng vá đó trở LẠI đúng vị trí đã cắt — vùng khác của khung hình giữ
> NGUYÊN không đụng tới. Cần biết TRƯỚC cả width lẫn height cụ thể của layer sau khi
> scale (`assembly.py::_layer_target_size`, dùng `media_probe.py::probe_video_
> dimensions` đo tỉ lệ khung hình GỐC qua ffprobe, kẹp không vượt khung hình chính) — khác
> chế độ `"alpha"` chỉ cần width (`scale=W:-2` để ffmpeg tự tính height). Độ mờ chỉnh qua
> `colorchannelmixer=rr/gg/bb={opacity}` (giảm SÁNG layer trước khi blend — cùng cách
> overlay hiệu ứng lớp phủ, vì `blend` screen không có tham số alpha trực tiếp).

> **Đã build (2026-09-02, mục 115 IMPLEMENTATION_REPORT.md):** `image_layers` — layer
> ẢNH ĐỊNH VỊ, theo yêu cầu người dùng ("bổ sung thêm block... setup Layer ảnh định vị
> với chức năng tương tự [layer video] nhưng cho ảnh nền đen hoặc không có nền. Ngoài hỗ
> trợ 9 vị trí layer thì còn hỗ trợ thêm full khung hình"). Song song `VideoLayer` (mục
> 112/113, DANH SÁCH RIÊNG — không dùng chung), CÙNG 2 chế độ `blend_mode`, chỉ khác 2
> điểm: (1) nguồn LUÔN ảnh tĩnh PNG/JPEG/WEBP — `assembly.py::_composite_image_layers`
> dùng `-loop 1` (không phải `-stream_loop -1` của video loop) để ghép; (2) `position`
> có thêm giá trị `"full"` — phủ TOÀN KHUNG HÌNH (scale-cover đúng độ phân giải xuất,
> `_scale_cover_filter` — CÙNG hàm `_mix_overlay_effect` dùng, KHÔNG phụ thuộc
> `BrandProfile.aspect_fill_mode`), bỏ qua HẲN `width_pct`. `"full"` + `blend_mode==
> "screen"` — KHÔNG cần bước `crop` (vùng blend = toàn khung hình = chính khung hình
> đang ghép, không phải 1 phần) nên blend THẲNG, bản chất chính là "hiệu ứng lớp phủ"
> (`OverlayEffectOverride`) áp dụng cho ẢNH TĨNH thay vì video loop. Áp dụng NGAY SAU
> layer video (nếu có) trong hậu kỳ cuối cùng — layer ẢNH LUÔN nổi TRÊN CÙNG mọi layer
> khác. Endpoint: `POST /projects/{id}/render/image-layers/upload`, `PATCH .../image-
> layers/{layer_id}`, `DELETE .../image-layers/{layer_id}`, `GET .../image-layers/
> {layer_id}/asset`.

> **Đã build (2026-09-12, mục 137 IMPLEMENTATION_REPORT.md):** `short_exports` — xuất
> short-video 9:16 từ 1 khoảng block (`start_block_id`..`end_block_id`), theo yêu cầu
> người dùng: repurpose 1 đoạn của project long-form thành YouTube Shorts/TikTok mà
> KHÔNG cần tạo 1 project short-form riêng (`Project.format=="short"`/`parent_project_id`
> là 1 project TRỐNG hoàn toàn, không copy block nào từ cha — khác hẳn tính năng này).
> Artifact sống NGAY trong `RenderState` của CHÍNH project long-form, tối đa 3 phần tử
> (chặn 400 ở router `POST /render/short-export`, KHÔNG chặn ở schema). Short-video CHỈ
> gồm THUẦN shot trong khoảng đã chọn (ảnh/video + giọng đọc, giữ transition đã cấu
> hình) — KHÔNG kèm intro/nhạc nền/overlay/video nền như video chính.
> `regenerate_images=true` — sinh lại ẢNH (KHÔNG BAO GIỜ video, kể cả khi bật cờ này —
> sinh lại video 9:16 tốn kém/chậm hơn hẳn ảnh, ngoài phạm vi tính năng) đúng tỷ lệ 9:16
> cho từng shot ẢNH trong khoảng, lưu vào `renders/short/<id>/assets/` RIÊNG, KHÔNG đụng
> `ShotRenderStatus.visual_asset_path` 16:9 gốc; `false` (mặc định) — giữ nguyên asset
> gốc, ép crop-fill vào khung dọc (`aspect_fill_mode="crop"`,
> `assembly.py::_scale_cover_filter` — phóng khung ngang lên vừa CHIỀU CAO khung dọc rồi
> cắt bớt 2 bên, KHÔNG co nhỏ nội dung). Shot dạng VIDEO trong khoảng LUÔN crop bản gốc
> CÙNG kiểu, KHÔNG BAO GIỜ được sinh lại. **Đổi (2026-09-12, mục 138)** — bản đầu (mục
> 137) dùng letterbox (viền đen trên/dưới, `_scale_letterbox_filter` — đã XOÁ HẲN, không
> còn nơi nào gọi tới) đúng yêu cầu ban đầu "hiện full khung ngang", nhưng người dùng test
> thật báo ảnh bị "co hẹp" giữa 2 viền đen — yêu cầu đổi hẳn sang crop, không co ảnh.
>
> **Đổi (2026-09-12, mục 140)** — thêm `lang`, theo yêu cầu người dùng "cho phép chọn
> ngôn ngữ khi xuất short-video, tương tự như khi render long-video": `null`/bỏ qua ở
> `POST /render/short-export` → ngôn ngữ CHÍNH của kênh, giá trị ĐÃ RESOLVE lưu vào
> `ShortVideoExport.lang`. 400 NGAY (ở `create_short_export`, trước khi tạo entry) nếu
> `lang` không thuộc `NARRATION_LANGUAGES`, HOẶC giọng đọc ngôn ngữ đã chọn CHƯA sinh
> xong cho MỌI shot **TRONG KHOẢNG ĐÃ CHỌN** (không phải toàn project — khác biệt CÓ CHỦ
> Ý so với `assemble` chính, mục 134). Thời lượng từng shot + giọng đọc mux vào segment
> đều ăn theo `lang` đã chọn (`_shot_base_duration`/`_narration_for_lang`, cùng cơ chế
> `assemble_video` chính). Tên file (Pack Export LẪN tải riêng lẻ) có hậu tố ngôn ngữ
> (`_<lang>`) — CẦN THIẾT: 2 export CÙNG khoảng block khác ngôn ngữ (hợp lệ, chiếm 2/3
> slot khác nhau) trước đây đè tên file lên nhau.
>
> Xoá qua `DELETE /render/short-export/{id}` (giải phóng lại slot); tải qua `GET /render/
> short-export/{id}/download`; Pack Export xuất
> `short_<start_block_id>-<end_block_id>_<lang>.<ext>` cho MỖI export `status=="done"`.

> **Đã build (2026-09-12, mục 142 IMPLEMENTATION_REPORT.md):** `caption_layer` — Layer
> CAPTION (phụ đề cứng burn-in), theo yêu cầu người dùng: "Bổ sung tính năng cho phép
> user thêm caption vào video ở bước visual studio... chọn 9 vị trí, kích thước, độ mờ
> tương tự phần Layer video định vị", sau đó xác nhận thêm "chọn cả loại ngôn ngữ nữa".
> KHÁC `layers`/`image_layers` (list, nhiều instance, nguồn là FILE upload) — đây là 1
> CẤU HÌNH DUY NHẤT/project (chỉ 1 track caption có ý nghĩa), nguồn nội dung là TEXT lấy
> thẳng từ `pack.script.body[].audio`/`audio_by_lang[lang]` (không upload gì).
>
> Burn TRỰC TIẾP vào TỪNG SEGMENT lúc ghép (KHÔNG PHẢI 1 lượt trên video đã ghép xong) —
> mỗi segment tự ffmpeg đảm bảo đúng độ dài qua `-t duration`, nên caption luôn khớp khít
> mà không cần tính lại mốc thời gian tuyệt đối qua transition/reflow/offset intro. Dùng
> `app/render/captions.py::write_shot_caption_ass` — cắt text dài thành nhiều cue qua
> `split_block_into_cues` (mục 141) rồi tự viết 1 file `.ass` HOÀN CHỈNH (tự khai
> `PlayResX`/`PlayResY` = ĐÚNG độ phân giải xuất, Style trực tiếp trong `[V4+ Styles]`) —
> **KHÔNG dùng `.srt` + `force_style`** (bản đầu dùng cách này, verify bằng ffmpeg thật
> phát hiện `force_style`/`original_size` KHÔNG quy đổi `Fontsize` sang pixel thật như kỳ
> vọng, chữ ra khổng lồ sai lệch hẳn — xem docstring `write_shot_caption_ass` cho chi
> tiết bug đã sửa). `position` tái dùng `LayerPosition` (9 ô lưới, map thẳng sang
> "Alignment" kiểu numpad của ASS/libass).
>
> `lang` — `null`/bỏ qua = dùng ĐÚNG ngôn ngữ đang ghép video (`export_lang` của lượt
> `assemble`/xuất short-video); khác đi = ngôn ngữ caption ĐỘC LẬP với ngôn ngữ giọng đọc
> (VD ghép giọng đọc tiếng Việt nhưng muốn caption tiếng Anh) — CHỈ cần CÓ chữ dịch
> (`audio_by_lang[lang]`), KHÔNG cần đã sinh audio ngôn ngữ đó (timing luôn theo ĐÚNG
> thời lượng thật của shot trên timeline, không phụ thuộc ngôn ngữ caption).
>
> Áp dụng CHO CẢ video chính (`assembly.py::_assemble_video_impl`) LẪN short-video
> export (`short_export.py::run_short_export`, mục 137-140) — 2 nơi dùng CHUNG
> `state.caption_layer`, nhất quán theo yêu cầu người dùng (xác nhận qua hỏi trực tiếp).
> KHÔNG áp dụng cho intro (không có nội dung script để burn). PATCH duy nhất
> `/render/caption-layer` (partial update, lazy-create) — không có POST/DELETE riêng
> (không có file upload, tắt qua `enabled=false`).

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
