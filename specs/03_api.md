# 03 — API Contract (FastAPI ↔ React)

REST trên `http://127.0.0.1:{PORT}`. Tất cả body JSON. Không auth (single-user, localhost). Lỗi trả `{ "error": { "code": "...", "message": "..." } }` với HTTP status phù hợp.

Quy ước: `POST` tạo/kích hoạt, `PATCH` cập nhật một phần, `GET` đọc, `DELETE` archive (đưa vào
Thùng rác — trừ path `.../permanent`, xoá cứng thật, xem mục Thùng rác bên dưới).

## System
| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | Health-check (Electron chờ khi khởi động). |
| GET | `/bootstrap` | Trả trạng thái cấu hình: đã có provider chưa, settings, danh sách channel. Frontend gọi đầu tiên. |

## Channel
| Method | Path | Mô tả |
|---|---|---|
| GET | `/channels` | Danh sách channel (KHÔNG gồm channel đã ở Thùng rác — `archived=True`). |
| POST | `/channels` | Tạo channel. |
| GET | `/channels/{id}` | Chi tiết + brandprofile hiện hành. |
| PATCH | `/channels/{id}` | Đổi tên/`archived` — `archived=true` = "Xoá" (chuyển vào Thùng rác), KHÔNG xoá file. |
| POST | `/channels/{id}/restore` | **Đã build (2026-08-16)**: khôi phục khỏi Thùng rác (`archived=false`). |
| DELETE | `/channels/{id}/permanent` | **Đã build (2026-08-16)**: xoá vĩnh viễn — CHỈ cho phép khi đã `archived=true`. Xoá DB row (cascade Project/BrandProfileVersion con) VÀ xoá `workspace/channels/{id}/` khỏi đĩa. KHÔNG khôi phục được. |

## BrandProfile
| Method | Path | Mô tả |
|---|---|---|
| GET | `/channels/{id}/brandprofile` | BrandProfile hiện hành (JSON §04). |
| PUT | `/channels/{id}/brandprofile` | Lưu bản mới → tạo version mới. |
| GET | `/channels/{id}/brandprofile/versions` | Lịch sử version. |
| POST | `/channels/{id}/brandprofile/clone-from/{src_channel_id}` | Clone từ kênh khác. |
| POST | `/channels/{id}/brandprofile/logo/upload` | **Mới (2026-08-22, mục 62)**: upload logo kênh (multipart PNG/JPEG/WEBP) — set `logo_path`, thay TẠI CHỖ (xoá file cũ khác đuôi nếu có), bump version. Thuần hiển thị, không dùng trong pipeline sinh asset/ghép video. |
| GET | `/channels/{id}/brandprofile/logo` | **Mới (2026-08-22, mục 62)**: tải/xem logo đã upload. |
| ~~POST/DELETE/GET~~ `/channels/{id}/brandprofile/style-references/*` | **ĐÃ GỠ BỎ (2026-09-09)**: 3 endpoint CRUD ảnh tham chiếu phong cách (IPAdapter, đã build 2026-08-23 mục 75) đã xoá hoàn toàn — tính năng chưa từng verify thật (custom node `ComfyUI_IPAdapter_plus` chưa từng được cài), người dùng yêu cầu bỏ hẳn khi rà soát tính năng LoRA Flux mới. Xem `04_data_schemas.md`/`05_ai_providers.md` §8k. |
| POST | `/channels/{id}/brandprofile/voice-sample/upload` | **Đã build (2026-08-16)**: upload mẫu giọng thương hiệu (multipart WAV/MP3) — set `voice_clone_ref_path`, bump version. Xem `05_ai_providers.md` §8e. |
| GET | `/channels/{id}/brandprofile/voice-sample` | **Đã build (2026-08-16)**: tải/nghe lại mẫu giọng đã upload. |
| POST | `/channels/{id}/brandprofile/intro/upload` | **Mới (2026-08-20)**: upload video/audio thương hiệu (multipart, tự nhận diện loại) — set `intro_video_path` HOẶC `intro_audio_path`, xoá field còn lại + file cũ (chỉ 1 trong 2). Bump version. Xem `04_data_schemas.md` §1, mục 51 IMPLEMENTATION_REPORT.md. |
| GET | `/channels/{id}/brandprofile/intro` | **Mới (2026-08-20)**: tải/xem lại video/audio thương hiệu đã upload (hỗ trợ Range — tua được). |
| POST | `/channels/{id}/brandprofile/bg-music/upload` | **Mới (2026-08-20, mục 53)**: upload nhạc nền mặc định của kênh (multipart, luôn audio WAV/MP3) — set `bg_music_path`, bump version. Chỉnh `bg_music_volume` qua `PUT .../brandprofile` sẵn có. Xem `04_data_schemas.md` §1. |
| GET | `/channels/{id}/brandprofile/bg-music` | **Mới (2026-08-20, mục 53)**: tải/nghe lại nhạc nền đã upload (hỗ trợ Range). |
| POST | `/channels/{id}/brandprofile/overlay/upload` | **Mới (2026-08-22, mục 68)**: upload hiệu ứng lớp phủ mặc định của kênh (VD mưa/tuyết rơi — multipart, luôn video mp4/webm/mov) — set `overlay_effect_path`, bump version. Chỉnh `overlay_effect_opacity` qua `PUT .../brandprofile` sẵn có. Blend LIÊN TỤC suốt toàn bộ video khi ghép MP4 (không chỉ đoạn đầu) — xem `04_data_schemas.md` §1. |
| GET | `/channels/{id}/brandprofile/overlay` | **Mới (2026-08-22, mục 68)**: tải/xem lại video hiệu ứng đã upload (hỗ trợ Range). |

## Project
| Method | Path | Mô tả |
|---|---|---|
| GET | `/channels/{id}/projects` | Danh sách project của kênh — **đã build lại (2026-08-21, mục 58)**: danh sách PHẲNG gồm CẢ long-form lẫn short-form con (mỗi item có `parent_project_id`/`format`), frontend tự group theo `parent_project_id`. |
| POST | `/channels/{id}/projects` | Tạo project (khởi tạo `draft`). **Đã build thêm (2026-08-21, mục 58)**: body nhận thêm `parent_project_id` (optional) — có giá trị → tạo short-form (9:16) lồng dưới project đó, `format` server tự suy (không nhận từ client). Validate: parent tồn tại (404), cùng kênh (400), parent phải là long-form (400 — không lồng quá 1 cấp). |
| GET | `/projects/{id}` | Chi tiết + status + con trỏ pack (gồm `parent_project_id`/`format`). |
| PATCH | `/projects/{id}` | Cập nhật title/status. |
| DELETE | `/projects/{id}` | Archive — "Xoá" (chuyển vào Thùng rác), KHÔNG xoá file. **Đã build thêm (2026-08-21, mục 58)**: archive 1 long-form cascade archive LUÔN mọi short-form con. |
| POST | `/projects/{id}/restore` | **Đã build (2026-08-16)**: khôi phục khỏi Thùng rác. **Đã build thêm (2026-08-21, mục 58)**: restore 1 long-form cascade restore luôn short-form con đang archived. |
| DELETE | `/projects/{id}/permanent` | **Đã build (2026-08-16)**: xoá vĩnh viễn — CHỈ cho phép khi đã archive. Xoá DB row (cascade PackVersion/RetentionEntry) VÀ xoá `workspace/channels/{cid}/projects/{id}/` khỏi đĩa. KHÔNG khôi phục được. **Đã build thêm (2026-08-21, mục 58)**: xoá 1 long-form cascade xoá vĩnh viễn short-form con TRƯỚC. |

## Thùng rác (Trash) — **đã build (2026-08-16)**
| Method | Path | Mô tả |
|---|---|---|
| GET | `/trash` | Gộp danh sách channel + project đang `archived=True`, dùng cho 1 màn Thùng rác duy nhất (`frontend/src/screens/Trash.tsx`). Mỗi project kèm `channel_name` để hiện ngữ cảnh (project có thể thuộc nhiều kênh khác nhau trong cùng danh sách). |

## Thư viện (Creative Asset) — **mới (2026-08-20, mục 53)**
> Entry point "Thư viện" ở sidebar, ngang hàng Dashboard/Thùng rác/Cài đặt — quản lý
> nhạc nền/video/ảnh/giọng đọc dùng lại được ở nhiều nơi. ĐỘC LẬP không gắn channel/
> project nào — xem `04_data_schemas.md` §3c.

| Method | Path | Mô tả |
|---|---|---|
| GET | `/library/assets?kind=` | Danh sách asset, lọc theo `kind` (`music`\|`video`\|`image`\|`voice`) nếu truyền, không truyền = tất cả. |
| POST | `/library/assets/upload?kind=` | Multipart `file` — `kind` bắt buộc qua query string, loại file phải khớp `kind` (400 nếu không khớp). |
| PATCH | `/library/assets/{asset_id}` | **Mới (2026-08-21, mục 54)** — body `{ name }`, đổi tên hiển thị (400 nếu rỗng). KHÔNG đụng file vật lý trên đĩa. Dùng cả ở màn Thư viện lẫn ngay sau khi bấm "Thêm vào thư viện" (`AddToLibraryButton.tsx`, các màn khác). |
| DELETE | `/library/assets/{asset_id}` | Xoá hẳn khỏi DB + file trên đĩa, không thể hoàn tác. |
| GET | `/library/assets/{asset_id}/file` | Tải/xem/nghe asset (hỗ trợ Range). |

**Không có** endpoint "chọn từ thư viện" riêng ở các nơi upload khác (voice sample,
intro, shot visual, bg music, thumbnail...) — frontend (`LibraryPicker.tsx`) tự `fetch()`
bytes qua `GET .../file` rồi gọi thẳng API upload sẵn có ở nơi gọi, tương tự
`AddToLibraryButton.tsx` `fetch()` blob từ URL đang hiển thị rồi POST sang
`/library/assets/upload` — xem `IMPLEMENTATION_REPORT.md` mục 53, quyết định kiến trúc.

## Brief
| Method | Path | Mô tả |
|---|---|---|
| GET | `/projects/{id}/brief` | Đọc brief (4 nhóm input). |
| PUT | `/projects/{id}/brief` | Lưu brief. Trả về danh sách trường còn thiếu (không chặn). |
| POST | `/projects/{id}/brief/sources` | **Đã build, mới**: thêm nguồn tham khảo — multipart `file` hoặc form field `youtube_url`. MVP trích xuất text đơn giản (đếm ký tự với file text-based); transcript YouTube thật để mốc sau. |
| DELETE | `/projects/{id}/brief/sources/{source_id}` | Gỡ 1 nguồn tham khảo. |

## Pipeline AI (lõi)

> **Đã build (2026-08-17, mục 44 IMPLEMENTATION_REPORT.md) — bỏ HẲN cả bảng "ý định
> gốc" dưới đây lẫn phần lớn bảng "Endpoint đã build" kế tiếp**: `/research`, `/hooks`,
> `/gate1`, `/generate`, `/gate2` — cùng các endpoint tương ứng thật đã build
> (`/research`, `/gate1`, `/script/regenerate`, `PATCH /script/text`,
> `/script/approve`, `/pack/build` (bản cũ, sinh title/meta), `/pack/titles-meta`,
> `/gate2`) — **KHÔNG còn tồn tại**. Theo yêu cầu người dùng: bỏ hẳn luồng AI Research/
> Outline/Hook/Full-Script + Pack Review/Gate #2, "tập trung vào luồng chính: upload
> script, tạo visual và voice, sau đó render". Script import (mục "Script Import" bên
> dưới) là con đường DUY NHẤT còn lại để có script — không giữ bảng gốc lại tham chiếu
> nữa vì không còn ý nghĩa (khác các đợt "đã build khác bản gốc" trước, lần này bản gốc
> bị bỏ HẲN chứ không chỉ đổi cách làm). Bảng "Endpoint đã build" bên dưới đã xoá các
> dòng tương ứng, giữ lại đúng những gì còn tồn tại thật.

### Endpoint đã build (khớp `backend/app/routers/pipeline.py`)
| Method | Path | Mô tả |
|---|---|---|
| PATCH | `/projects/{id}/script/body/{index}/audio` | **Mới (2026-08-17, mục 32)** — sửa tay Audio (VO) của 1 block riêng. `index` = vị trí trong `script.body`. Tự đồng bộ lại `full_text`. Nút bút chì cạnh cột Audio ở Script Studio. |
| POST | `/projects/{id}/visual/generate` | Sinh Shot List (mỗi shot = 1 beat: visual_fx + audio_sfx) từ `script.body` (LUÔN từ import — mục 44, không còn nhánh AI). Chuyển step→2 (đổi từ step→3 cũ, mục 44 renumber). **ĐỒNG BỘ theo `block_id`** (mục 30/31, 2026-08-17) — shot đã có (VD do `ensure-shots-for-narration` tạo trước) GIỮ NGUYÊN `shot_id`, block MỚI vẫn được bổ sung shot tương ứng. |
| POST | `/projects/{id}/visual/ensure-shots-for-narration` | **Mới (2026-08-17, mục 30)** — tạo shot list nếu chưa có, KHÔNG đổi `step`/`status`. Dùng khi bấm "Sinh giọng đọc cho toàn bộ block" ở Script Studio (step 1, đổi từ step 2 cũ — mục 44) — `render/start` cần `shot_id` để lưu trạng thái narration, dù người dùng chưa qua Visual Studio. |
| GET | `/projects/{id}/script/transcript-srt` | Transcript kịch bản dạng `.srt` chuẩn. Timeline CỘNG DỒN độ dài GIỌNG ĐỌC THẬT (`narration_duration_sec`, đo qua ffprobe) của shot khớp `block_id`, KHÔNG còn dùng `timestamp_sec`/`end_sec` làm nguồn thật (chỉ fallback khi shot đó CHƯA sinh giọng đọc — **đã build lại 2026-08-20, mục 52**) — timestamp kịch bản chỉ mang tính tham khảo, người dùng có thể ước lượng sai. Cộng thêm offset = độ dài intro thật (nếu có, xem `app/render/intro.py::resolve_intro_source`) vào MỌI cue — khớp đúng thời điểm video ghép ra thật bắt đầu phát nội dung kịch bản. **Cắt nhỏ cue dài — mới (2026-09-12, mục 141)**, theo yêu cầu người dùng ("mỗi block có thể đọc quá dài nên việc hiển thị subtitle theo transcript bị tràn chữ"): 1 block KHÔNG còn LUÔN là 1 cue duy nhất — `app/render/captions.py::split_block_into_cues` cắt text dài hơn `DEFAULT_MAX_CUE_CHARS` (84 ký tự, ~2 dòng phụ đề chuẩn) thành nhiều cue ngắn hơn, CHỈ cắt ở ranh giới từ, timestamp mỗi cue chia lại theo tỷ lệ SỐ KÝ TỰ trên khoảng `(start, duration)` gốc của CHÍNH block đó — khớp ĐÚNG VO thật của từng ngôn ngữ (không giả định tốc độ đọc/nói), tái dùng được cho tính năng chèn caption cứng lúc ghép video sau này. Nút "Tải transcript (.srt)" ở Script Studio. |
| GET | `/projects/{id}/script/transcript-txt`, `/projects/{id}/script/transcript-txt/{lang}` | **Mới (2026-09-12, mục 136)**, theo yêu cầu người dùng — kịch bản dạng `.txt` THUẦN, KHÔNG timestamp/SRT numbering (khác `.srt` ở trên) — đọc/duyệt/dịch nội dung liền mạch. Xây ĐỘNG từ `pack.script.body[].audio`/`audio_by_lang[lang]` (CỐ Ý không dùng `Script.full_text` — chỉ là snapshot ngôn ngữ chính lúc import, không theo kịp chỉnh sửa/bản dịch sau đó, xem `pack_export.py::build_script_txt`). `{lang}` phải thuộc `NARRATION_LANGUAGES` (400 nếu sai), 400 nếu chưa có script/chưa có nội dung ngôn ngữ đó. Nút "Tải kịch bản (.txt)" ở Script Studio, cạnh nút `.srt`, theo `viewLang` đang chọn. Pack Export cũng xuất `script_<lang>.txt` cho mọi ngôn ngữ có nội dung, cùng quy ước hậu tố như `transcript_<lang>.srt`/`narration_full_<lang>.mp3`. |
| PATCH | `/projects/{id}/visual/shots/{shot_id}` | Sửa tay 1 shot (`visual_fx`/`audio_sfx`/`visual_type`/`transition_to_next`/`camera_motion`), không gọi AI. `transition_to_next` — **mới (2026-08-17, mục 33)** — validate theo `app/render/transitions.py::TRANSITIONS` (400 nếu sai), dùng lúc `render/assemble` dựng transition thật giữa shot này và shot kế tiếp. `camera_motion` — **mới (2026-08-19, mục 48)** — validate theo `app/render/camera_motion.py::CAMERA_MOTIONS` (400 nếu sai), hiệu ứng Ken Burns (zoom/pan/tilt/roll/orbit) cho shot ẢNH, không có tác dụng nếu `visual_type=video`. |
| PATCH | `/projects/{id}/visual/shots/bulk` | **Mới (2026-09-10, mục 130)** — sửa hàng loạt `transition_to_next`/`camera_motion` cho NHIỀU shot cùng lúc (Visual Studio, chọn shot qua checkbox + "Chọn tất cả"). Body `{shot_ids: string[], transition_to_next?, camera_motion?}` — truyền được 1 hoặc cả 2 field (field bỏ qua giữ nguyên giá trị cũ từng shot), validate cùng bảng `TRANSITIONS`/`CAMERA_MOTIONS` như PATCH đơn (400 nếu sai), 404 nếu không shot nào trong `shot_ids` khớp project. Đọc/ghi `pack.json` ĐÚNG 1 LẦN (không lặp N request PATCH đơn). **Route path literal `/bulk` ĐĂNG KÝ TRƯỚC route `{shot_id}` phía trên** (FastAPI khớp theo thứ tự đăng ký, không tự ưu tiên path cụ thể hơn path param — để sau sẽ bị `{shot_id}` nuốt mất, xem docstring backend). |
| POST | `/projects/{id}/visual/shots/{shot_id}/regenerate-visual` | Sinh lại RIÊNG `visual_fx` bằng AI (đã build vòng 4 — tách khỏi audio, khớp 2 nút riêng trong design). |
| POST | `/projects/{id}/visual/shots/{shot_id}/regenerate-audio` | Sinh lại RIÊNG `audio_sfx` bằng AI. |
| POST | `/projects/{id}/visual/generate-all-visual` | Sinh lại `visual_fx` cho TOÀN BỘ shot (nút header "Tạo Visual cho toàn bộ block"). |
| POST | `/projects/{id}/visual/generate-all-tts` | Sinh lại `audio_sfx` cho TOÀN BỘ shot (nút header "Tạo giọng đọc (TTS) cho toàn bộ block"). |
| POST | `/projects/{id}/render/shots/{shot_id}/upload-visual` | **Mới (2026-08-17)** — module Render Studio (`render.py`, KHÁC 3 dòng `/visual/shots/...` phía trên vốn thuộc `pipeline.py` và chỉ sửa PROMPT text). Multipart `file` — upload ảnh/video có sẵn từ máy THAY CHO sinh bằng AI cho 1 shot, ghi thẳng vào `assets/{shot_id}.<ext>` (thay thế TẠI CHỖ, xoá file cũ nếu khác đuôi), cập nhật `ShotRenderStatus` (`visual_provider: "upload"`, `visual_status: "ready"`, `approved` reset về `false`). Loại file (ảnh PNG/JPEG/WEBP hay video MP4/WEBM/MOV) PHẢI khớp `shot.visual_type` hiện có — đổi kiểu qua `PATCH /visual/shots/{id}` trước nếu cần, endpoint này không tự đổi `visual_type` (giữ ranh giới render.py chỉ đọc pack.json, không ghi lại). Dùng được ngay cả khi chưa từng bấm "Bắt đầu sinh asset" (tự tạo entry `render.json`). Nút "↑ Upload ảnh/video" cạnh nút "Tạo ảnh/video" ở mỗi ShotCard, Visual Studio. |
| DELETE | `/projects/{id}/render/shots/{shot_id}/visual` | **Mới (2026-09-02, mục 107)** — xoá ảnh/video đã sinh/upload/gán (từ Kho tư liệu) cho 1 shot, theo yêu cầu người dùng ("cho phép remove video/image ở từng shot sau khi đã add"). Xoá file trên đĩa (`unlink_retrying`), reset `ShotRenderStatus` về `visual_status="pending"` (`visual_asset_path`/`visual_provider`/`linked_clip_id`/`visual_watermark_note` = `null`, `approved=false`) — KHÔNG tự sinh/upload lại cái khác, chỉ trả shot về trạng thái chưa có visual. 404 nếu chưa từng có `render.json` entry cho shot này (khác `upload-visual` — endpoint đó tự tạo entry, endpoint này không có gì để xoá nên báo lỗi thẳng). Nút "Xoá ảnh/video" (màu cảnh báo) ở mỗi ShotCard, Visual Studio — chỉ hiện khi shot đang có asset. |
| POST | `/projects/{id}/render/shots/{shot_id}/remove-watermark` | **Mới (2026-08-28, mục 99)** — xoá watermark khỏi ảnh/video ĐÃ SINH/upload cho 1 shot, tái dùng `app/watermark/` (Florence-2 + LaMa) xây cho Kho Tài Nguyên. Yêu cầu `visual_status=="ready"` (400 nếu chưa) — chạy nền, đè `visual_asset_path` bằng bản `_nowm`. KHÔNG phát hiện watermark KHÔNG phải lỗi — ghi `ShotRenderStatus.visual_watermark_note` (không phải `visual_error`), asset gốc giữ nguyên. Nút "Xoá watermark" ở mỗi ShotCard, Visual Studio. |
| POST | `/projects/{id}/render/remove-watermark-all` | **Mới (2026-08-28, mục 99)** — xoá watermark cho MỌI shot đang `visual_status=="ready"`, bỏ qua thầm lặng shot chưa sinh xong (cùng nguyên tắc `approve-all`). Ghi tóm tắt (`scanned`/`cleaned`/`no_watermark`/`failed`) vào `RenderState.watermark_scan_summary`, hiện thành banner sau khi quét xong. Mục "⋯ Tuỳ chọn khác" ở header Visual Studio. |
| POST | `/projects/{id}/output/enter` | **Đã build lại (2026-08-17, mục 44)** — chuyển sang Output Center (step 3, đổi từ step 5 cũ), set LUÔN `status="ready_output"` (trước đây do `/gate2` approve set — nay `/gate2` không còn, endpoint này tự làm trọn vẹn). KHÔNG còn gate nào chặn trước khi gọi — nút "Đi tới Output →" ở Visual Studio dùng được ngay. |
| POST | `/projects/{id}/render/intro/upload-visual` | **Mới (2026-08-20, mục 51)** — shot mở đầu RIÊNG của project. Multipart `file` (ảnh HOẶC video, tự nhận diện) — set `RenderState.intro.kind`/`visual_asset_path`. Đổi sang video → tự xoá `audio_asset_path` cũ (video có audio riêng, không cần audio rời). |
| POST | `/projects/{id}/render/intro/upload-audio` | **Đã build lại (2026-08-20, mục 51)** — audio mở đầu, upload ĐỘC LẬP được (không còn bắt buộc phải có ảnh trước). Chỉ audio (không ảnh) → lúc ghép tự dùng ẢNH shot đầu tiên minh hoạ, giống audio thương hiệu cấp kênh. 400 nếu `kind=="video"` (video tự có audio riêng). |
| DELETE | `/projects/{id}/render/intro` | **Đổi hành vi (2026-08-22, mục 61)** — bỏ HẲN shot mở đầu cho project này, xoá file asset riêng (nếu có) trên đĩa, set `IntroAssetStatus.disabled=True` — KHÔNG còn quay về dùng brand nữa (trước mục 61: quay về fallback brand ngầm). |
| PATCH | `/projects/{id}/render/intro/inherit` | **Mới (2026-08-22, mục 61)** — không cần body. Set `disabled=False`, quay lại kế thừa video/audio thương hiệu cấp kênh (đối xứng với DELETE ở trên). Tự tạo `IntroAssetStatus` nếu chưa có. |
| PATCH | `/projects/{id}/render/intro/transition` | **Mới (2026-08-21, mục 55)** — body `{ transition_to_next }`, validate theo `TRANSITIONS` (400 nếu sai, cùng bảng dùng cho shot-to-shot). Tự tạo `IntroAssetStatus` nếu chưa có. `"cut"` (mặc định) ghép cắt cứng; giá trị khác dùng `_xfade_chain` blend ~0.6s giữa intro và shot đầu tiên. |
| GET | `/projects/{id}/render/intro/asset/{kind}` | **Mới (2026-08-20, mục 51)** — `kind` = `visual`\|`audio`, phục vụ preview (hỗ trợ Range). |
| POST | `/projects/{id}/render/character-reference/upload` | **Mới (2026-09-09, mục 127)** — ảnh nhân vật tham khảo RIÊNG của project, TỰ ĐỘNG sinh `description` đồng bộ qua VisionProvider (không chặn upload nếu provider lỗi/chưa cấu hình — ghi `caption_error`). Multipart `file` (ảnh PNG/JPEG/WEBP). Thay THẲNG nếu đã có ảnh trước đó (1 slot/project). |
| POST | `/projects/{id}/render/character-reference/recaption` | **Mới (2026-09-09, mục 127)** — sinh lại `description` từ ảnh ĐÃ CÓ (không upload lại) — dùng khi lần trước lỗi hoặc muốn thử lại sau khi đổi provider vision. 404 nếu chưa có ảnh. |
| PATCH | `/projects/{id}/render/character-reference/description` | **Mới (2026-09-09, mục 127)** — sửa tay `description` (body `{ description }`) — VisionProvider không phải lúc nào cũng mô tả đúng ý, người dùng tự viết lại được. 404 nếu chưa có ảnh. |
| DELETE | `/projects/{id}/render/character-reference` | **Mới (2026-09-09, mục 127)** — bỏ hẳn ảnh tham khảo, xoá file trên đĩa, `RenderState.character_reference` về `null`. |
| GET | `/projects/{id}/render/character-reference/asset` | **Mới (2026-09-09, mục 127)** — phục vụ preview ảnh tham khảo (hỗ trợ Range). 404 nếu chưa có. |
| POST | `/projects/{id}/render/bg-music/upload` | **Mới (2026-08-20, mục 53)** — nhạc nền RIÊNG của project, override nhạc nền mặc định cấp kênh. Multipart `file` (audio WAV/MP3). Giữ nguyên `volume` hiện có nếu đã chỉnh trước đó. |
| PATCH | `/projects/{id}/render/bg-music` | **Mới (2026-08-20, mục 53)** — chỉnh `volume` (0.0-1.0). Tự tạo `BgMusicOverride` nếu chưa có (chỉnh volume trước khi kịp upload file vẫn hợp lệ). |
| DELETE | `/projects/{id}/render/bg-music` | **Mới (2026-08-20, mục 53)** — bỏ nhạc nền riêng, xoá hẳn file trên đĩa, quay về dùng nhạc nền mặc định cấp kênh (nếu có). |
| GET | `/projects/{id}/render/bg-music/asset` | **Mới (2026-08-20, mục 53)** — tải/nghe lại nhạc nền riêng đã upload (hỗ trợ Range). |
| POST | `/projects/{id}/render/overlay/upload` | **Mới (2026-08-22, mục 68)** — hiệu ứng lớp phủ RIÊNG của project (VD mưa/tuyết rơi), override overlay mặc định cấp kênh. Multipart `file` (video mp4/webm/mov). Giữ nguyên `opacity` hiện có nếu đã chỉnh trước đó. Tự đặt `disabled=False`. |
| PATCH | `/projects/{id}/render/overlay` | **Mới (2026-08-22, mục 68)** — chỉnh `opacity` (0.0-1.0). Tự tạo `OverlayEffectOverride` nếu chưa có. |
| DELETE | `/projects/{id}/render/overlay` | **Đổi hành vi (2026-09-02, mục 105)** — bỏ HẲN overlay cho project này (set `disabled=True`, KHÔNG còn fallback ngầm về overlay mặc định cấp kênh như trước), xoá hẳn file riêng trên đĩa nếu có. |
| PATCH | `/projects/{id}/render/overlay/inherit` | **Mới (2026-09-02, mục 105)** — dùng lại overlay thương hiệu cấp kênh, đặt `disabled=False`. Không cần body, cùng pattern `render/intro/inherit`. |
| GET | `/projects/{id}/render/overlay/asset` | **Mới (2026-08-22, mục 68)** — tải/xem lại video overlay riêng đã upload (hỗ trợ Range). |
| POST | `/projects/{id}/render/background-video/upload` | **Mới (2026-09-02, mục 106)**, **đổi hành vi (mục 110)** — video nền CHUNG cho toàn bộ block, loop theo tổng thời lượng timeline (không phân biệt ranh giới shot). Multipart `file` (video mp4/webm/mov). KHÔNG có cấp kênh mặc định để kế thừa (thuần override project). Mục 110 — mỗi lần gọi THÊM 1 video vào `asset_paths` (list, KHÔNG còn thay thế tại chỗ như bản 1-video cũ) — cho phép nhiều video nối thành 1 "playlist" lúc ghép. |
| DELETE | `/projects/{id}/render/background-video/{index}` | **Mới (2026-09-02, mục 110)** — bỏ ĐÚNG 1 video nền theo vị trí `index` (0-based, khớp thứ tự hiện trên UI) trong `asset_paths`, xoá file trên đĩa. Khác endpoint không-index bên dưới (bỏ HẲN cả danh sách). |
| DELETE | `/projects/{id}/render/background-video` | **Mới (2026-09-02, mục 106)** — bỏ HẲN toàn bộ video nền (mọi video + cấu hình random/transition), xoá hẳn mọi file trên đĩa, quay lại yêu cầu MỌI shot phải có visual riêng lúc ghép (hành vi gốc). |
| PATCH | `/projects/{id}/render/background-video` | **Mới (2026-09-02, mục 110)** — body `{ random_order?, transition? }` (chỉ gửi field muốn đổi). `random_order` (bool) — bật "random loop": xáo trộn thứ tự video 1 LẦN mỗi lượt ghép (không xáo lại mỗi vòng lặp). `transition` (cùng danh sách `TRANSITIONS` dùng cho shot-to-shot, 400 nếu sai) — hiệu ứng chuyển cảnh GIỮA các video liên tiếp trong playlist, `"cut"` mặc định. Chỉ có ý nghĩa khi có ≥2 video. |
| GET | `/projects/{id}/render/background-video/asset/{index}` | **Mới (2026-09-02, mục 106)**, **đổi path (mục 110)** — tải/xem lại 1 video nền theo `index` (hỗ trợ Range). |
| POST | `/projects/{id}/render/layers/upload` | **Mới (2026-09-02, mục 112)**, **`blend_mode` thêm mục 113** — layer video ĐỊNH VỊ theo lưới 3x3 (VD voice wave, logo) — theo yêu cầu người dùng. Multipart `file` (video mp4/webm/mov) + form field `position` (1 trong 9 giá trị lưới 3x3, mặc định `"bottom-center"`), `width_pct` (0.05–1.0, mặc định 0.3), `opacity` (0.0–1.0, mặc định 1.0), `blend_mode` (`"alpha"` mặc định — nguồn CÓ SẴN kênh alpha, WebM VP9/MOV ProRes4444 trong suốt; hoặc `"screen"` — nguồn NỀN ĐEN ĐẶC, không alpha, screen-blend cục bộ đúng vùng layer, theo yêu cầu người dùng "tôi chỉ có video layer nền đen thôi"). Mỗi lần gọi THÊM 1 layer MỚI vào `RenderState.layers` (list, không thay thế — nhiều layer cùng lúc, mỗi layer có thể dùng `blend_mode` khác nhau). |
| PATCH | `/projects/{id}/render/layers/{layer_id}` | **Mới (2026-09-02, mục 112)** — body `{ position?, width_pct?, opacity?, blend_mode? }` (chỉ gửi field muốn đổi), validate cùng ràng buộc endpoint upload. |
| DELETE | `/projects/{id}/render/layers/{layer_id}` | **Mới (2026-09-02, mục 112)** — bỏ ĐÚNG 1 layer, xoá file trên đĩa. |
| GET | `/projects/{id}/render/layers/{layer_id}/asset` | **Mới (2026-09-02, mục 112)** — tải/xem lại 1 layer đã upload (hỗ trợ Range). |
| POST | `/projects/{id}/render/image-layers/upload` | **Mới (2026-09-02, mục 115)** — layer ẢNH ĐỊNH VỊ, song song layer video ở trên — theo yêu cầu người dùng. Multipart `file` (ảnh png/jpg/webp) + form field `position` (1 trong 9 giá trị lưới 3x3 HOẶC `"full"` — phủ toàn khung hình, bỏ qua `width_pct`), `width_pct`/`opacity`/`blend_mode` (giống hệt layer video). Mỗi lần gọi THÊM 1 layer MỚI vào `RenderState.image_layers` (list RIÊNG, không chung với layer video). |
| PATCH | `/projects/{id}/render/image-layers/{layer_id}` | **Mới (2026-09-02, mục 115)** — body `{ position?, width_pct?, opacity?, blend_mode? }`, validate cùng ràng buộc endpoint upload. |
| DELETE | `/projects/{id}/render/image-layers/{layer_id}` | **Mới (2026-09-02, mục 115)** — bỏ ĐÚNG 1 layer ảnh, xoá file trên đĩa. |
| GET | `/projects/{id}/render/image-layers/{layer_id}/asset` | **Mới (2026-09-02, mục 115)** — tải/xem lại 1 layer ảnh đã upload (hỗ trợ Range). |
| PATCH | `/projects/{id}/render/caption-layer` | **Mới (2026-09-12, mục 142)** — Layer CAPTION (phụ đề cứng burn-in), theo yêu cầu người dùng "thêm caption vào video ở bước visual studio... chọn 9 vị trí, kích thước, độ mờ tương tự phần Layer video định vị", sau đó xác nhận thêm "chọn cả loại ngôn ngữ nữa". KHÁC `layers`/`image-layers` (list, upload file) — 1 CẤU HÌNH DUY NHẤT/project, KHÔNG upload gì (nội dung lấy thẳng từ `pack.script.body`). Body `{ enabled?, position?, size_pct?, opacity?, lang? }` (partial update, tự tạo `RenderState.caption_layer` nếu chưa có). `position` — 9 giá trị lưới 3x3 (không có `"full"`). `size_pct` (0.01–0.3, mặc định 0.045) — cỡ chữ = % CHIỀU CAO khung hình xuất (khác `width_pct` — % chiều RỘNG — của layer video/ảnh). `opacity` (0.0–1.0). `lang` — `null`/bỏ qua = dùng ĐÚNG ngôn ngữ đang ghép video (`export_lang` của lượt `assemble`/xuất short-video); khác đi = ngôn ngữ caption ĐỘC LẬP với ngôn ngữ giọng đọc (chỉ cần CÓ chữ dịch, không cần đã sinh audio ngôn ngữ đó). Burn TRỰC TIẾP vào TỪNG SEGMENT lúc ghép (`assembly.py::_build_segment`, filter `subtitles` qua file `.ass` tự sinh — xem `app/render/captions.py::write_shot_caption_ass`) — áp dụng CHO CẢ video chính (`assemble`) LẪN short-video export (mục 137-140), dùng CHUNG cấu hình. Không có endpoint DELETE riêng — tắt qua `enabled=false`. |

> **Đã build vòng 4 — đổi tên field**: `Shot.prompt` → `Shot.visual_fx`, `Shot.tts_emotion`
> → `Shot.audio_sfx` (khớp tên 2 trong 6 cột import — xem mục Script Import). Endpoint
> `POST /visual/shots/{id}/regenerate` (gộp cả 2 field) đã bị **xoá**, thay bằng 2
> endpoint `regenerate-visual`/`regenerate-audio` ở trên — không giữ lại cho tương
> thích ngược vì chỉ có frontend nội bộ gọi.

### Script Import — nhập kịch bản CSV/Excel (đã build vòng 4, không có trong bản gốc)
| Method | Path | Mô tả |
|---|---|---|
| GET | `/projects/{id}/script/import/template` | **Mới (2026-08-16)** — trả file `.xlsx` mẫu đúng 6 cột (`build_template_workbook()`, cùng file `script_import.py` — sửa cột thì sửa cả header mẫu lẫn `COLUMN_KEYWORDS` để không lệch nhau), kèm 2 dòng ví dụ minh hoạ định dạng "Thời lượng" (`H:MM–H:MM`). Nội dung tĩnh, không phụ thuộc project — path lồng theo project chỉ để nhất quán với 2 endpoint dưới. Nút "Tải file mẫu" ở Gate1Outline.tsx, cạnh nút Nhập kịch bản. |
| POST | `/projects/{id}/script/import/parse` | Multipart `file` (.csv/.xlsx/.xls, 5 cột cố định: Mã, Thời lượng, Loại Visual, Visual/FX, Audio/SFX + 1 cột VO đơn HOẶC nhiều cột `VO (XX)` — **mới 2026-09-04**, giọng đọc đa ngôn ngữ, mỗi cột 1 mã ngôn ngữ trong `NARRATION_LANGUAGES`). Parse **phía server** (`app/pipeline/script_import.py`, dùng `csv` chuẩn + `openpyxl`), trả `{ beats, stats: {block_count, word_count, duration_label}, full_text }` — mỗi `beat` có thêm `audio_by_lang` khi file dùng dạng nhiều cột `VO (XX)`. KHÔNG ghi vào Pack — chỉ xem trước. Lỗi (thiếu cột/file trống) → 400 kèm thông điệp tiếng Việt hiển thị thẳng cho người dùng. |
| POST | `/projects/{id}/script/import/confirm` | Body `{ beats, full_text }` (từ response của `/parse`) → ghi vào `pack.script` (`source: "import"`), chạy guardrail, **bỏ qua AI Generation**, nhảy thẳng step→2 (Script Studio, đã duyệt), status→`generating`. Không yêu cầu đã qua Gate 1 trước đó — **gọi được ngay từ step 0** (Brief, project mới tạo, chưa chạy Research), không có gating nào theo step/status/`pack.research` (xác nhận 2026-08-16, mục 26 IMPLEMENTATION_REPORT.md). UI: nút "Nhập kịch bản từ file" có ở CẢ `BriefEditor.tsx` (step 0) lẫn `Gate1Outline.tsx` (step 1), dùng chung component `ScriptImportControls.tsx`. |

### Streaming — **chưa build**
`Accept: text/event-stream` cho generation chưa triển khai ở bản này; các lệnh gọi AI hiện chạy đồng bộ (request/response thường), phản hồi đủ nhanh với provider Mock/local nhỏ nhưng có thể chậm với model cloud lớn cho kịch bản dài. Đây là giới hạn đã biết — xem IMPLEMENTATION_REPORT.md mục "Không làm / để sau".

## Production Pack
| Method | Path | Mô tả |
|---|---|---|
| GET | `/projects/{id}/pack` | ProductionPack hiện hành (JSON §04). |
| PATCH | `/projects/{id}/pack` | Sửa thủ công một phần Pack (editor). Tạo version. |
| GET | `/projects/{id}/pack/versions` | Lịch sử. |
| POST | `/projects/{id}/pack/build` | (Re)build shot list + title/thumbnail concepts từ script. |

## Retention Guardrail
| Method | Path | Mô tả |
|---|---|---|
| POST | `/projects/{id}/guardrail/check` | Chạy check → trả `{ hook_strength, max_anchor_gap_sec, warnings[] }` (§08). |

## Retention nạp tay
| Method | Path | Mô tả |
|---|---|---|
| GET | `/projects/{id}/retention` | Số liệu đã nhập + chênh lệch so benchmark. Trả thêm `entry.rpm` (**mới 2026-09-12**). |
| PUT | `/projects/{id}/retention` | Lưu số liệu nạp tay (§08). Body nhận thêm `rpm` (luôn nhập tay). |

## Chỉ số YouTube (§M4, Phase 1 — **đã triển khai 2026-09-12**, OAuth per-channel từ mục 154)
Kéo chỉ số THẬT từ YouTube Data/Analytics API qua OAuth loopback (Desktop app flow) —
xem `app/youtube_analytics.py` + `app/routers/youtube_analytics.py`, `specs/02_database.md`
(bảng `youtube_channel_metrics_snapshot`/`youtube_video_metrics_snapshot`). RPM (doanh
thu), CTR thumbnail và Returning Viewers KHÔNG tự động hoá — quyền
`yt-analytics-monetary.readonly` khó xin cho app cá nhân/CTR thumbnail không có trong API
công khai (xem mục 153); cả 3 vẫn nạp tay qua `PUT /projects/{id}/retention`.

**OAuth Client dùng CHUNG toàn app** (chỉ là định danh app đăng ký với Google), nhưng
**token truy cập (access/refresh) RIÊNG theo TỪNG kênh StudioFlow** (mục 154, sửa lỗ
hổng: 1 Google Account có thể quản nhiều kênh YouTube — brand channel/kênh được share —
dùng chung 1 token khiến 2 kênh StudioFlow bị gán NHẦM cùng 1 kênh YouTube thật).

| Method | Path | Mô tả |
|---|---|---|
| POST | `/settings/youtube/oauth-client` | Body `{client_id, client_secret}` — lưu OAuth Client do user tự đăng ký ở Google Cloud Console (mã hoá qua `app/crypto.py`, app-level, dùng chung mọi kênh). |
| GET | `/settings/youtube/status` | `{has_oauth_client}` — "đã kết nối" giờ RIÊNG theo từng kênh, xem endpoint `oauth-status` bên dưới. |
| GET | `/channels/{id}/youtube/authorize-url?redirect_uri=...` | Trả `{url}` — URL consent Google RIÊNG cho kênh này (`channel_id` nhúng vào `state`, Google echo lại ở callback), mở bằng trình duyệt HỆ THỐNG (`shell.openExternal`, KHÔNG mở trong cửa sổ app). Scope: `youtube.readonly` + `yt-analytics.readonly` (không xin quyền monetary). |
| GET | `/channels/{id}/youtube/oauth-status` | `{connected}` — trạng thái token RIÊNG của kênh này, frontend poll sau khi mở `authorize-url`. |
| GET | `/oauth/callback` | Loopback callback DÙNG CHUNG cho mọi kênh (Google redirect về đây sau khi user đồng ý) — nhận `code` + `state` (= `channel_id`), tự suy `redirect_uri` từ chính request (KHÔNG nhận qua query param, Google không đảm bảo echo param tuỳ ý) → đổi lấy access/refresh token, lưu RIÊNG cho kênh theo `state` vào `app_setting` (key `youtube_oauth:{channel_id}`) → gọi `channels.list(mine=true)` gán luôn `Channel.youtube_channel_id/title/connected_at`. Trả HTML tĩnh cho tab trình duyệt (không phải React app). Thiếu/sai `state` → 400. |
| POST | `/channels/{id}/youtube/disconnect` | Xoá 3 field trên VÀ xoá token OAuth riêng của kênh này (không còn dùng chung nên không giữ lại). |
| GET | `/projects/{id}/youtube-videos-available` | Danh sách video YouTube của kênh CHƯA gắn project khác + video đang gắn hiện tại — cho dropdown ở Output Center. Lấy qua `playlistItems.list` trên "uploads" playlist (rẻ quota hơn `search.list`). |
| PATCH | `/projects/{id}/youtube-link` | Body `{video_id}` (hoặc `null` để gỡ) — user TỰ CHỌN, KHÔNG tự đoán theo tên trùng khớp. |
| POST | `/channels/{id}/youtube/sync` | Nút "Đồng bộ" thủ công (không polling nền) — 1 lượt batch Analytics API cho MỌI video đã liên kết + 1 lượt riêng/video cho `audienceRetention` (API không hỗ trợ batch report này) → ghi 1 `youtube_channel_metrics_snapshot` + N `youtube_video_metrics_snapshot` MỚI (không update tại chỗ). Trả về giống `GET .../metrics`. |
| GET | `/channels/{id}/youtube/metrics` | Snapshot kênh mới nhất + list video (mỗi project đã liên kết) kèm snapshot mới nhất — nguồn dữ liệu cho tab "Chỉ số YouTube" ở Dashboard. |
| GET | `/projects/{id}/youtube/retention-chapters` | Khớp `retention_curve` đã đồng bộ với `pack.script.body[]` theo tỷ lệ cộng dồn thời lượng từng block (ưu tiên `narration_duration_sec` thật nếu project render qua StudioFlow, fallback ước tính kịch bản) → `{video_duration_sec, chapters: [{block_id, start_ratio, end_ratio, avg_retention}]}`, đánh dấu chương tụt mạnh nhất. Chỉ hiển thị thông tin — KHÔNG tự feed ngược vào guardrail. |

## Output — Export (M1)
| Method | Path | Mô tả |
|---|---|---|
| POST | `/projects/{id}/export` | `{ format: "markdown"｜"pdf"｜"json" }` → sinh file trong `exports/`, trả path. Yêu cầu `ready_output`. |

## Output — Render (M2, chưa build ở MVP)
| Method | Path | Mô tả |
|---|---|---|
| POST | `/projects/{id}/render` | (M2) Sinh asset + ghép MP4. Định nghĩa interface, chưa implement. |

> **Đã build (nhiều đợt, xem `backend/app/routers/render.py` để biết đầy đủ)** — bảng
> trên đã CŨ (M2 "Render Studio" đã build từ lâu, không còn `POST /projects/{id}/render`
> đơn lẻ). Các endpoint chính THẬT SỰ đang dùng (Visual Studio + Output Center):
> - `POST /projects/{id}/render/start?kind=both|visual|narration&force=false` — sinh
>   asset cho TOÀN BỘ block. Mặc định (`force=false`) bỏ qua shot đã `ready` (resume sau
>   lỗi 1 vài shot, không gọi lại API tốn phí). **`force=true` — mới (2026-08-22, mục
>   67)**: sinh lại HÀNG LOẠT kể cả shot đã có sẵn (dùng khi đổi BrandProfile sang giọng/
>   style ảnh mới) — reset shot `ready` (đúng `kind`) về `generating` trước khi chạy, và
>   bỏ duyệt (`approved=false`) các shot visual bị sinh lại. **Endpoint KHÔNG đổi** —
>   nhưng UI gọi `kind=narration` (cả `force=false` lẫn `force=true`) đã chuyển HẲN từ
>   Visual Studio sang Script Studio (2026-09-02, mục 109, theo yêu cầu người dùng) —
>   Visual Studio giờ chỉ còn gọi `kind=visual` ở batch header (per-shot "Tạo giọng đọc"
>   vẫn còn, không đổi).
> - `GET /projects/{id}/render/status`, `GET /projects/{id}/render/gpu-status` — trạng
>   thái từng shot + hàng đợi GPU local.
> - `POST /projects/{id}/render/cancel` — dừng batch đang chạy. Cờ "đang chạy"/"đã yêu
>   cầu huỷ" (`engine.py::_in_progress`/`_cancel_requested`) là PER-PROJECT, KHÔNG tách
>   theo `kind` (visual hay narration) — chỉ 1 batch chạy được cùng lúc cho 1 project
>   (`_require_not_in_progress` chặn mở batch mới khi đã có 1 cái đang chạy), nên endpoint
>   này LUÔN dừng ĐÚNG batch đang chạy bất kể gọi từ đâu. Nút "⏹ Dừng" có ở CẢ Visual
>   Studio (dừng batch visual) lẫn Script Studio (**mới 2026-09-02, mục 110** — dừng
>   batch giọng đọc, theo yêu cầu người dùng: batch giọng đọc quản lý chính ở Script
>   Studio từ mục 109 nhưng trước đó chỉ Visual Studio có nút dừng, buộc người dùng rời
>   màn để dừng cái họ vừa bấm ở Script Studio).
> - `POST /projects/{id}/render/shots/{shot_id}/regenerate-visual` /
>   `regenerate-narration` — sinh lại 1 shot riêng lẻ, LUÔN sinh lại (không có khái niệm
>   "resume" ở mức 1 shot — bấm là sinh lại thật).
> - `PATCH /projects/{id}/render/narration-speed` — **mới (2026-09-02, mục 109)** — body
>   `{ speed: float }` (0.5–2.0, 400 nếu ngoài khoảng), lưu `RenderState.narration_speed`.
>   Nút chỉnh tốc độ ở Script Studio. Áp dụng bằng time-stretch file audio (ffmpeg
>   `atempo`) NGAY SAU khi provider TTS sinh xong — xem `engine.py::generate_narration_
>   asset`/`_apply_narration_speed` — KHÔNG PHẢI tham số riêng của từng provider (hoạt
>   động đồng nhất bất kể ElevenLabs/Gemini/Piper/OmniVoice). Chỉ áp dụng cho lần sinh
>   MỚI — đổi giá trị KHÔNG tự sinh lại narration đã có sẵn.
> - `DELETE /projects/{id}/render/shots/{shot_id}/visual` — **mới (2026-09-02, mục 107)**
>   — xoá ảnh/video hiện có của 1 shot, trả về `visual_status="pending"` (xem bảng chi
>   tiết ở trên).
> - `POST /projects/{id}/render/shots/{shot_id}/approve`,
>   `POST /projects/{id}/render/approve-all` — vẫn tồn tại (đánh dấu `approved` cho từng
>   shot), nhưng **KHÔNG còn chặn ghép video** (bỏ 2026-09-02, mục 107, theo yêu cầu
>   người dùng: "bỏ luồng duyệt block, ko cần phải có thì mới render được video") — chỉ
>   còn là cờ tuỳ chọn, không có UI nào ở Visual Studio gọi tới 2 endpoint này nữa.
> - `POST /projects/{id}/render/assemble` — ghép MP4 từ các shot đã `visual_status ==
>   "ready"` (hoặc không có visual riêng NHƯNG project có video nền chung — xem
>   `background-video/upload`), không còn yêu cầu `approved`. **Đổi (2026-09-02, mục
>   111)** — 409 "đang ghép rồi" giờ CHỈ dựa vào `engine.is_assembly_in_progress` (cờ
>   TRONG BỘ NHỚ), KHÔNG còn tin mù quáng `state.assembly_status` đã lưu — field này có
>   thể bị KẸT "assembling" mãi mãi nếu thread ghép "chết lặng" giữa chừng (bug thật đã
>   gặp — xem `assembly.py::assemble_video` docstring); giờ tự phục hồi được (khởi động
>   lại app, hoặc cờ tự dọn qua `finally` khi hàm chạy xong dù lỗi gì). Body thêm field
>   `lang` — **mới (2026-09-11, mục 134)**, theo yêu cầu người dùng: chọn NGÔN NGỮ giọng
>   đọc dùng để xuất video (`null`/bỏ qua → ngôn ngữ chính của kênh). 400 NGAY nếu
>   `lang` không thuộc `NARRATION_LANGUAGES`, HOẶC nếu giọng đọc ngôn ngữ đã chọn CHƯA
>   sinh xong cho MỌI shot (chặn cứng, không cho ghép — khác thiết kế lần đầu chỉ cảnh
>   báo). Thời lượng TỪNG SHOT khi ghép ăn theo giọng đọc của ngôn ngữ đã chọn (không còn
>   LUÔN cố định ngôn ngữ chính như trước), xem `assembly.py::_narration_for_lang`.
> - `POST /projects/{id}/render/assemble/reset` — **mới (2026-09-02, mục 111)** — đặt lại
>   `assembly_status` bị kẹt "assembling" về "error" NGAY TRONG UI (nút "Đặt lại tiến
>   trình bị treo", `RenderStudio.tsx`, hiện suốt lúc đang ghép). 409 nếu tiến trình vẫn
>   đang chạy THẬT (`is_assembly_in_progress`), 400 nếu không có gì để đặt lại. Không xoá
>   file trung gian đã dựng dở — lần ghép lại tự ghi đè.
> - **Giọng đọc đa ngôn ngữ — mới (2026-09-04)**, theo yêu cầu người dùng (kênh phục vụ
>   thị trường nước ngoài). `lang` (path param) phải thuộc `NARRATION_LANGUAGES`
>   (`vi`/`en`/`de`/`pt_br`/`es`/`fr`, `app/render/schemas.py`) — 400 nếu sai. Ngôn ngữ
>   CHÍNH của kênh (`BrandProfile.primary_language`) đi qua các endpoint gốc ở trên
>   (KHÔNG dùng nhóm này); nhóm này CHỈ cho ngôn ngữ KHÁC ngôn ngữ chính:
>   - `POST /projects/{id}/render/narration-translations/{lang}/start?force=false` —
>     sinh giọng đọc `lang` cho MỌI shot đã có văn bản dịch (`ScriptBodyItem.
>     audio_by_lang[lang]`, xem §04). Shot chưa dịch tới BỊ BỎ QUA (coi là ready, không
>     lỗi) — rollout từng ngôn ngữ dần không bị chặn. Cùng pattern `force`/`_require_not_
>     in_progress` với `render/start`.
>   - `POST /projects/{id}/render/shots/{shot_id}/regenerate-narration-translation/{lang}`
>     — sinh lại 1 shot riêng lẻ cho `lang`.
>   - `GET /projects/{id}/render/shots/{shot_id}/asset/narration/{lang}` — phục vụ file
>     audio đã sinh (Range request, cùng `range_file_response`).
>   - `GET /projects/{id}/render/narration-download/{lang}` — ghép giọng đọc TOÀN BỘ
>     script cho `lang` thành 1 `.mp3`, tải về (`engine.build_narration_download(id,
>     lang=lang)`).
>   - `GET /projects/{id}/script/transcript-srt/{lang}` — transcript `.srt` cho `lang`,
>     timeline theo giọng đọc THẬT của chính ngôn ngữ đó (không dùng lại timeline ngôn
>     ngữ chính).
>   - `GET /projects/{id}/script/transcript-txt/{lang}` — **mới (2026-09-12, mục 136)** —
>     cùng nội dung nhưng dạng `.txt` THUẦN, không timestamp — xem bảng chi tiết ở trên.
>   - `PATCH /projects/{id}/script/body/{index}/translation/{lang}` — body `{ text }`,
>     sửa tay `audio_by_lang[lang]` của 1 block (đồng bộ cả vào `audio` gốc nếu `lang ==
>     primary_language`).
>   - `GET /projects/{id}/script/import/template?multilang=true` — mẫu Excel 11 cột (1
>     VO/ngôn ngữ) thay vì 6 cột đơn ngôn ngữ mặc định.
>   - `POST /channels/{id}/brandprofile/voice-sample/upload/{lang}`,
>     `GET /channels/{id}/brandprofile/voice-sample/{lang}` — mẫu giọng clone RIÊNG cho
>     `lang` (ghi `BrandProfile.voice_clone_ref_paths[lang]`, dùng làm `reference_audio`
>     cho OmniVoice — provider khác nhận rồi bỏ qua, xem `05_ai_providers.md` §8e).
>   - Pack Export (`POST /projects/{id}/export/pack-bundle`) tự thêm
>     `transcript_<lang>.srt`/`narration_full_<lang>.mp3` vào `included`/`skipped` cho
>     MỖI ngôn ngữ có ít nhất 1 block đã dịch — ngôn ngữ chưa dùng tới không xuất hiện.
>     **Đổi (2026-09-11, mục 134)** — `transcript_<lang>.srt`/`narration_full_<lang>.mp3`
>     giờ LUÔN có hậu tố ngôn ngữ, kể cả ngôn ngữ CHÍNH của kênh (trước đây ngôn ngữ chính
>     xuất tên KHÔNG hậu tố `transcript.srt`/`narration_full.mp3`) — nhất quán với
>     `video_final_<lang>.*` (video đã ghép, hậu tố = `RenderState.final_video_lang`,
>     ngôn ngữ giọng đọc dùng lúc ghép gần nhất, xem `assemble` ở trên) — theo yêu cầu
>     người dùng, tránh nhầm lẫn/ghi đè khi xuất Pack nhiều lần cho các ngôn ngữ khác nhau
>     vào cùng 1 thư mục đích. `transcript_<lang>.srt` ở đây dùng
>     `pack_export.py::build_srt_text` (KHÁC hàm `_build_srt` ở `routers/pipeline.py`
>     dùng cho endpoint `/script/transcript-srt` ở trên — 2 hàm SONG SONG, không dùng
>     chung) — cả 2 đều đã áp dụng cắt nhỏ cue dài qua `captions.py` (mục 141).
> - **Lưu asset Visual Studio vào Kho Tài Nguyên để tái sử dụng — mới (2026-09-11, mục
>   135)**, theo yêu cầu người dùng. `POST /projects/{id}/visual/shots/save-to-vault`
>   (body `{shot_ids}`) — lưu/cập nhật đè `ProcessedClip` cho MỖI shot (bỏ qua shot chưa
>   sẵn sàng, không chặn cả batch), trả `{saved, updated, skipped}`. Kho Tài Nguyên giờ
>   chứa CẢ ảnh lẫn video (`ProcessedClip.media_kind`) — `assign-vault-clip` đổi check từ
>   "chỉ nhận video" sang so `shot.visual_type` với `clip.media_kind` của đúng clip;
>   `vault-candidates` lọc thêm theo `media_kind` khớp shot đang xin gợi ý.
> - **Tự động điền block còn thiếu từ Kho Tài Nguyên — mới (2026-09-11, mục 135)**.
>   `GET /projects/{id}/render/vault-auto-fill-suggestions` — quét shot CHƯA có visual
>   sẵn sàng, gợi ý 1 clip/shot (ngưỡng similarity RIÊNG cao hơn gợi ý thủ công — 0.8 so
>   với 0.65 — + lọc `media_kind` + khung hình ngang/dọc khớp `project.format`), CHỈ trả
>   gợi ý, không tự gán. `POST /projects/{id}/render/vault-auto-fill-apply` (body
>   `{items: [{shot_id, clip_id}]}`) — áp dụng ĐÚNG cặp người dùng đã duyệt ở màn review
>   (client gửi lại, không để backend tự truy vấn lại), lỗi 1 item không chặn batch.
> - **Xuất short-video 9:16 từ 1 khoảng block — mới (2026-09-12, mục 137)**, theo yêu cầu
>   người dùng: repurpose 1 đoạn của project long-form thành YouTube Shorts/TikTok mà
>   KHÔNG cần tạo 1 project short-form riêng (`Project.format=="short"` là 1 project TRỐNG
>   hoàn toàn, không copy block nào từ cha — khác hẳn tính năng này). Artifact sống NGAY
>   trong `RenderState.short_exports` (tối đa 3/project), xem §04.
>   - `POST /projects/{id}/render/short-export` — body `{start_block_id, end_block_id,
>     regenerate_images, lang}`. 400 nếu đã đủ 3 export, mã block đầu/cuối không tồn tại/
>     thứ tự ngược, `lang` không thuộc `NARRATION_LANGUAGES`, HOẶC giọng đọc ngôn ngữ đã
>     chọn CHƯA sinh xong cho MỌI shot **TRONG KHOẢNG ĐÃ CHỌN** (chặn cứng, cùng
>     nguyên tắc `assemble` chính — mục 134 — nhưng CHỈ soi shot trong khoảng, không phải
>     toàn project). Tạo entry `status="pending"` rồi chạy nền (`BackgroundTasks`) — poll
>     tiến độ qua `GET /render/status` sẵn có (không có endpoint GET riêng). Short-video
>     CHỈ gồm THUẦN shot trong khoảng (không kèm intro/nhạc nền/overlay như video chính).
>     `lang` — **mới (2026-09-12, mục 140)**, theo yêu cầu người dùng "cho phép chọn ngôn
>     ngữ khi xuất short-video, tương tự như khi render long-video": `null`/bỏ qua → ngôn
>     ngữ chính của kênh, LƯU LUÔN giá trị đã resolve vào `ShortVideoExport.lang`.
>     `regenerate_images=true` — sinh lại ẢNH (không bao giờ video) đúng tỷ lệ 9:16 cho
>     từng shot ẢNH trong khoảng, lưu RIÊNG không đụng asset 16:9 gốc; `false` (mặc định)
>     — giữ ảnh/video gốc, ép crop-fill vào khung dọc (**đổi 2026-09-12, mục 138** — bản
>     đầu dùng letterbox/viền đen, người dùng test thật báo ảnh bị "co hẹp", yêu cầu
>     không co ảnh, chỉ crop phần giữa).
>   - `DELETE /projects/{id}/render/short-export/{export_id}` — xoá file + entry, giải
>     phóng lại 1 slot trong cap 3.
>   - `GET /projects/{id}/render/short-export/{export_id}/download` — tải video (Range
>     request), 400 nếu chưa `status=="done"`. Tên file (Content-Disposition) có hậu tố
>     ngôn ngữ (`short_<start>-<end>_<lang>.<ext>` — mục 140).
>   - Pack Export tự thêm `short_<start_block_id>-<end_block_id>_<lang>.<ext>` cho MỖI
>     export đã `status=="done"` — export lỗi/đang chạy dở không xuất hiện trong bundle.
>     Hậu tố ngôn ngữ **mới (mục 140)** — CẦN THIẾT (không chỉ nhất quán): 2 export CÙNG
>     khoảng block khác ngôn ngữ (hợp lệ, chiếm 2/3 slot khác nhau) trước đây đè tên file
>     lên nhau.
> - Còn nhiều endpoint khác (upload ảnh/audio thay AI, shot mở đầu, nhạc nền override...)
>   — xem trực tiếp router, bảng này KHÔNG liệt kê đầy đủ.

## Provider AI (Admin)
| Method | Path | Mô tả |
|---|---|---|
| GET | `/providers` | Danh sách provider theo task. |
| POST | `/providers` | Thêm provider (cloud hoặc local endpoint). |
| PATCH | `/providers/{id}` | Cập nhật (model, default, fallback, enabled). |
| DELETE | `/providers/{id}` | Xoá (thao tác phá huỷ — cần xác nhận ở UI). |
| POST | `/providers/{id}/test` | Test kết nối → cập nhật `status`. |
| GET | `/providers/comfyui/models` | **Mới (2026-08-22, mục 65)**, thêm `kind=unet_gguf` **(2026-09-09)**, đổi tên từ `/providers/local-sdxl/models` **(2026-09-24, đợt dọn dẹp xoá `local_sdxl`)** — query `kind` (`checkpoints`\|`loras`\|`unet_gguf`) + `base_url` (tuỳ chọn, mặc định ComfyUI `127.0.0.1:8188`). Liệt kê file THẬT đang có trong ComfyUI (đổ vào dropdown chọn UNet GGUF cho provider `local_qwen`, provider ComfyUI duy nhất còn lại). 502 nếu ComfyUI không phản hồi. |

## Cấu hình khác (Admin)
| Method | Path | Mô tả |
|---|---|---|
| GET/PUT | `/settings` | app_setting theo key: `general`, `ai_params`, `app_branding` (🎨 — bổ sung, xem `06_uiux.md`). |
| GET/POST/PATCH/DELETE | `/prompt-templates` | Quản lý prompt template (§07). PATCH nhận `active_version` (đặt mặc định) hoặc `new_version_body`+`new_version_note` (thêm version mới). |
| GET | `/audit-log?type=system\|expense` | Nhật ký, lọc theo loại (khớp seg-control 3 tab trong design). |
| GET | `/budget` | **Đã build**: trả theo TỪNG KÊNH (không phải theo project) — `{channel_id, channel_name, soft_limit, threshold_pct, spent, over_threshold}`. |
| PATCH | `/budget/{channel_id}` | Sửa `soft_limit`/`threshold_pct` cho 1 kênh. |
