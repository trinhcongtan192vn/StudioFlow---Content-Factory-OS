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
  "version": 3
}
```

### Ràng buộc
- `content_pillars[].weight` cộng lại ≈ 1.0.
- `retention_benchmark` dùng bởi guardrail (§08).
- `version` tăng mỗi lần lưu; khớp `brandprofile_version` trong DB (§02).

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
  ],
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

Design tách quy trình generation thành nhiều bước tương tác nhỏ hơn (Outline+Hook →
Script Studio → **Visual Studio** riêng biệt → Pack Review) thay vì 1 bước "AI
Generation" duy nhất. Để Pack vẫn là artifact trung tâm xuyên suốt toàn bộ vòng đời
đó (kể cả trước khi hoàn tất), schema thực tế bổ sung so với bản trên:

```json
{
  "...": "...(như trên)...",
  "research": {
    "synthesis": "...",
    "outlines": [{ "id", "title", "points": ["..."], "selected": true }]
  },
  "hooks": [
    { "id", "psychological_type", "spoken", "visual", "selected": true }
  ],
  "script": {
    "hook": { "spoken", "visual", "duration_sec" },
    "full_text": "kịch bản liền mạch trước khi bóc tách theo đoạn",
    "source": "ai | import",
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
    { "shot_id", "asset_type", "visual_type": "image|video", "provider", "visual_fx", "audio_sfx", "block_id": "null trừ khi import", "linked_timestamp_sec" }
  ],
  "youtube_meta": {
    "description": "mô tả SEO đầy đủ",
    "hashtags": ["..."],
    "chapters": [{ "ts_sec", "label" }],
    "thumbnail_description": "..."
  }
}
```

- `research` + `hooks`: kết quả AI Research/Hook Variants sống trong CHÍNH pack.json
  ngay từ trước Gate #1, thay vì một artifact tạm rời rạc — giữ nguyên tắc "Pack JSON
  là artifact trung tâm" xuyên suốt cả work-in-progress.
- `youtube_meta` (mới, top-level): description SEO + chapters + hashtags — cần cho
  quy trình đăng YouTube thật, rộng hơn `titles`/`thumbnail_concepts` gốc. `titles`
  và `thumbnail_concepts` vẫn giữ nguyên vị trí/ý nghĩa như spec gốc.
- **Đã build vòng 4 (2026-08-12)** — nhập kịch bản CSV/Excel (xem `03_api.md` mục
  Script Import):
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

## 4. Bản người-đọc (export)

Sinh từ ProductionPack:
- **Markdown/PDF:** kịch bản đa cột dạng bảng (timestamp | audio | visual | direction), theo sau là shot list + prompts, title/thumbnail concepts.
- **JSON:** chính `pack.json`.

Export **không** chứa thông tin mà JSON không có — nó là view, không phải nguồn.
