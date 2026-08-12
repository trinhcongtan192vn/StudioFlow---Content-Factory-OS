# 07 — Prompt Templates

Các prompt cho pipeline AI. Lưu trong bảng `prompt_template`/`prompt_template_version` (§02, đã build), phiên bản hoá, chỉnh được ở màn 🧩. Mọi prompt **inject BrandProfile** (§04) để giữ bản sắc kênh.

Quy ước placeholder: `{{brand_voice}}`, `{{forbidden}}`, `{{content_pillars}}`, `{{brief}}`, `{{hook_formats}}`, `{{retention_benchmark}}`, `{{visual_style_prompt}}`.

> **Đã build — thư viện template thực tế khớp design, task key khác tên mục dưới đây.**
> `StudioFlow Prototype.dc.html` định nghĩa sẵn nhiều template với placeholder riêng
> — bản build seed đúng các template này làm nguồn sự thật thay vì văn bản dưới đây
> (giữ dưới đây làm tài liệu về Ý ĐỊNH rubric/luồng, không phải nội dung final).
>
> **Nguyên tắc bắt buộc (đã sửa lỗi vòng review):** mỗi `task` key CHỈ ứng với ĐÚNG 1
> điểm gọi LLM trong `backend/app/pipeline/generation.py` (quan hệ 1:1). Trước đây
> `outline_hook` và `visual_image` bị dùng chung cho 2 lệnh gọi có bộ tham số khác
> nhau (VD sinh outline dùng `{{topic}}/{{brief}}/{{outline_count}}` nhưng sinh hook
> dùng `{{chosen_outline}}/{{hook_count}}` — cùng 1 template render 2 lần, mỗi lần chỉ
> 1 nửa placeholder được thay, nửa còn lại giữ nguyên `{{...}}` trong prompt gửi AI).
> Đã tách lại theo bảng dưới; task nào không có điểm gọi thật (VD `brief` cũ — Brief
> Editor không có bước AI-assist nào) đã bị GỠ khỏi seed thay vì để mồ côi trên màn
> Prompt Templates.
>
> | task key (DB) | Điểm gọi (generation.py) | Tham số `{{...}}` riêng (ngoài BrandProfile chung) |
> |---|---|---|
> | `outline` | `generate_research` — mục 1 | `topic`, `brief`, `outline_count` |
> | `hook` | `generate_hooks` — mục 2 | `chosen_outline`, `hook_count` |
> | `script` | `generate_full_script` — mục 3 | `outline`, `hook`, `framework`, `length` |
> | `script_revise` | `regenerate_full_script` — endpoint `/script/regenerate` | `current_script`, `user_feedback`, `length` |
> | `script_breakdown` | `breakdown_script` — bóc tách Full Script → body đa cột | CHỈ `script_text` (không inject BrandProfile) |
> | `visual_shots_init` | `generate_shots` — sinh HÀNG LOẠT shot ban đầu khi vào Visual Studio | `script` |
> | `visual_image` | `regenerate_shot_visual_fx` khi shot `visual_type=image` — nút "Tạo lại Visual" | `script_snippet`, `visual_description` |
> | `visual_video` | `regenerate_shot_visual_fx` khi shot `visual_type=video` — nút "Tạo lại Visual" | `script_snippet`, `visual_description` |
> | `visual_tts` | `regenerate_shot_audio_sfx` — nút "Tạo lại giọng đọc" | `script_snippet`, `emotion_description`, `voice_profile` |
> | `thumbnail` | `generate_titles_and_meta` — mục 5, gộp thêm description SEO + hashtags (`youtube_meta`) | `brief`, `script` |
>
> Tham số BrandProfile chung (mọi task trừ `script_breakdown`): `channel`,
> `brand_voice`, `forbidden`, `content_pillars`, `hook_formats`, `visual_style_prompt`,
> `retention_benchmark` — dựng trong `_brand_ctx()`. Danh sách tham số đầy đủ theo
> từng task cũng hiển thị trực tiếp trên màn 🧩 Prompt Templates (mở rộng 1 template
> hoặc mở dialog Sửa/Tạo mới) để không phải tra code khi soạn prompt.
>
> Chi tiết nội dung từng version: xem `backend/app/seed.py` (`PROMPT_SEED`).
>
> **Đã build vòng 4:** `visual_image`/`visual_video` dùng cho endpoint
> `regenerate-visual`/`generate-all-visual` (sinh `Shot.visual_fx`) — chọn template
> theo đúng `visual_type` hiện tại của shot; `visual_tts` dùng cho
> `regenerate-audio`/`generate-all-tts` (sinh `Shot.audio_sfx` — phạm vi rộng hơn tên
> gốc "TTS emotion", giờ là mô tả âm thanh/nhạc nền/emotion giọng đọc nói chung, khớp
> tên cột import "Âm thanh & Nhạc nền — Audio/SFX"). Khi `script.source == "import"`,
> các template này KHÔNG được gọi lúc tạo shot ban đầu (seed thẳng từ nội dung file) —
> chỉ dùng khi người dùng chủ động bấm "Tạo lại" sau đó.
>
> **`updated_by` của các version seed sẵn ghi "Hệ thống"** (không phải tên người thật)
> — app single-user không có quản lý user (§CLAUDE.md nguyên tắc 5); version do người
> dùng tự sửa trong app ghi "Bạn".

## 1. AI Research

**Vai trò:** tổng hợp raw_knowledge + tạo 2–3 dàn ý theo góc nhìn khác nhau. Có thể chạy model local.

```
Bạn là trợ lý nghiên cứu nội dung cho kênh YouTube.
GIỌNG KÊNH: {{brand_voice}}
TRỤ CỘT NỘI DUNG: {{content_pillars}}
CẤM KỴ (tuyệt đối tránh): {{forbidden}}

BRIEF: {{brief}}

Nhiệm vụ:
1. Tổng hợp tài liệu thô thành các ý chính, ghi rõ điểm đắt giá.
2. Đề xuất ĐÚNG 3 dàn ý (outline) theo 3 GÓC NHÌN khác nhau cho cùng chủ đề.
   Mỗi dàn ý: tiêu đề góc nhìn + 4–6 beat chính.
Trả về JSON: { "synthesis": "...", "outlines": [{ "id","angle","beats":[...] }] }
Chỉ trả JSON, không thêm chữ nào khác.
```

## 2. Hook Variants

**Vai trò:** sinh 3 Hook theo 3 kiểu tâm lý. **KHÔNG kèm điểm số** — con người chọn.

```
Viết 3 biến thể HOOK (3–5 giây đầu) cho video, mỗi biến thể theo MỘT kiểu tâm lý khác nhau.
GIỌNG KÊNH: {{brand_voice}}
KIỂU HOOK ƯA DÙNG CỦA KÊNH: {{hook_formats}}
CẤM KỴ: {{forbidden}}
DÀN Ý ĐÃ CHỌN: {{chosen_outline}}

Mỗi Hook gồm: spoken (lời nói), visual (mô tả hình), psychological_type (tên kiểu tâm lý).
KHÔNG chấm điểm, KHÔNG xếp hạng.
Trả JSON: { "hooks": [{ "spoken","visual","psychological_type" }] }
Chỉ trả JSON.
```

## 3. AI Generation kịch bản chi tiết

**Vai trò:** viết Master Production Script đa cột sau Gate #1. **Khuyến nghị model cloud mạnh nhất** (ảnh hưởng retention).

```
Viết kịch bản sản xuất chi tiết cho video, dạng đa cột theo timeline.
GIỌNG KÊNH: {{brand_voice}}
CẤM KỴ: {{forbidden}}
CHUẨN RETENTION: {{retention_benchmark}}   # cài anchor mỗi ≤ max_anchor_gap_sec
DÀN Ý + HOOK ĐÃ DUYỆT: {{gate1_result}}
STYLE HÌNH ẢNH: {{visual_style_prompt}}

Yêu cầu:
- Hook giữ nguyên tinh thần bản đã duyệt.
- Body chia theo timestamp; cứ ≤ {{max_anchor_gap_sec}}s phải có 1 emotional anchor
  hoặc thông tin đắt giá (đánh dấu anchor=true).
- Mỗi dòng body: audio (narration) | visual (mô tả hình/B-roll) | direction (chỉ dẫn).
- CTA tự nhiên, điều hướng tới conversion_point trong brief.
- Ép theo framework: {{framework}}  # AIDA/PAS
Trả JSON đúng schema ProductionPack.script (§04). Chỉ trả JSON.
```

## 4. Shot Prompt Builder

**Vai trò:** từ cột visual của script, sinh prompt AI chuẩn hoá cho từng shot.

```
Với mỗi cảnh cần hình/video minh hoạ trong kịch bản, tạo 1 prompt AI để sinh asset.
STYLE HÌNH ẢNH KÊNH (bắt buộc tuân theo): {{visual_style_prompt}}
KỊCH BẢN: {{script}}

Mỗi shot: shot_id, asset_type (broll_image/motion_graphic/stock_footage/broll_video),
prompt (theo style kênh), linked_timestamp_sec.
Trả JSON: { "shots": [...] } đúng schema §04. Chỉ trả JSON.
```

## 5. Title & Thumbnail Concepts

```
Tạo 5–10 tiêu đề tối ưu ĐỒNG THỜI SEO YouTube + tò mò (CTR), và 3 concept thumbnail.
GIỌNG KÊNH: {{brand_voice}}   BRIEF: {{brief}}   KỊCH BẢN: {{script}}
Tiêu đề: text, angle (curiosity/benefit/number...), seo_score_hint.
Thumbnail: metaphor, text_overlay, layout.
Trả JSON: { "titles":[...], "thumbnail_concepts":[...] } (§04). Chỉ trả JSON.
```

## 6. Rubric chấm Hook Strength (Guardrail — §08)

**Vai trò:** chấm điểm 0–1 cho guardrail cảnh báo. Đây là điểm **nội bộ**, KHÔNG hiển thị cho người dùng ở bước chọn Hook Variants.

```
Chấm điểm HOOK sau theo thang 0.0–1.0. Cộng điểm theo 4 tiêu chí ngang nhau:
1. Độ cụ thể (không chung chung).
2. Yếu tố tò mò / phản trực giác.
3. Liên quan trực tiếp tới pain point trong brief: {{pain_points}}
4. Độ dài đạt yêu cầu (≤ 5 giây khi đọc).
HOOK: {{hook_spoken}}
Trả JSON: { "hook_strength": 0.0-1.0, "reasons": ["..."] }. Chỉ trả JSON.
```

## 7. Nguyên tắc chung

- Mọi prompt **bắt LLM trả JSON thuần** (không markdown fence) → backend parse thẳng vào Pydantic (§04).
- BrandProfile luôn được inject; `forbidden` là ràng buộc cứng trong mọi prompt.
- Prompt template chỉnh được ở runtime (màn 🧩) mà không sửa code.
- Mỗi `task` key ứng với ĐÚNG 1 điểm gọi LLM (1:1) — không tái dùng 1 task key cho 2
  lệnh gọi có bộ tham số khác nhau. Thêm bước AI mới → thêm task key mới, không gắn
  vào task key sẵn có.
- Không seed/hiển thị template cho task key KHÔNG có điểm gọi thật trong code — màn
  Prompt Templates chỉ liệt kê những gì thật sự ảnh hưởng tới output khi sửa.
