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
| GET | `/projects/{id}/script/transcript-srt` | **Đã build lại (2026-08-20, mục 52)** — transcript kịch bản dạng `.srt` chuẩn, 1 cue/block script. Timeline giờ CỘNG DỒN độ dài GIỌNG ĐỌC THẬT (`narration_duration_sec`, đo qua ffprobe) của shot khớp `block_id`, KHÔNG còn dùng `timestamp_sec`/`end_sec` làm nguồn thật (chỉ fallback khi shot đó CHƯA sinh giọng đọc) — timestamp kịch bản chỉ mang tính tham khảo, người dùng có thể ước lượng sai. Cộng thêm offset = độ dài intro thật (nếu có, xem `app/render/intro.py::resolve_intro_source`) vào MỌI cue — khớp đúng thời điểm video ghép ra thật bắt đầu phát nội dung kịch bản. Nút "Tải transcript (.srt)" ở Script Studio. |
| PATCH | `/projects/{id}/visual/shots/{shot_id}` | Sửa tay 1 shot (`visual_fx`/`audio_sfx`/`visual_type`/`transition_to_next`/`camera_motion`), không gọi AI. `transition_to_next` — **mới (2026-08-17, mục 33)** — validate theo `app/render/transitions.py::TRANSITIONS` (400 nếu sai), dùng lúc `render/assemble` dựng transition thật giữa shot này và shot kế tiếp. `camera_motion` — **mới (2026-08-19, mục 48)** — validate theo `app/render/camera_motion.py::CAMERA_MOTIONS` (400 nếu sai), hiệu ứng Ken Burns (zoom/pan/tilt/roll/orbit) cho shot ẢNH, không có tác dụng nếu `visual_type=video`. |
| POST | `/projects/{id}/visual/shots/{shot_id}/regenerate-visual` | Sinh lại RIÊNG `visual_fx` bằng AI (đã build vòng 4 — tách khỏi audio, khớp 2 nút riêng trong design). |
| POST | `/projects/{id}/visual/shots/{shot_id}/regenerate-audio` | Sinh lại RIÊNG `audio_sfx` bằng AI. |
| POST | `/projects/{id}/visual/generate-all-visual` | Sinh lại `visual_fx` cho TOÀN BỘ shot (nút header "Tạo Visual cho toàn bộ block"). |
| POST | `/projects/{id}/visual/generate-all-tts` | Sinh lại `audio_sfx` cho TOÀN BỘ shot (nút header "Tạo giọng đọc (TTS) cho toàn bộ block"). |
| POST | `/projects/{id}/render/shots/{shot_id}/upload-visual` | **Mới (2026-08-17)** — module Render Studio (`render.py`, KHÁC 3 dòng `/visual/shots/...` phía trên vốn thuộc `pipeline.py` và chỉ sửa PROMPT text). Multipart `file` — upload ảnh/video có sẵn từ máy THAY CHO sinh bằng AI cho 1 shot, ghi thẳng vào `assets/{shot_id}.<ext>` (thay thế TẠI CHỖ, xoá file cũ nếu khác đuôi), cập nhật `ShotRenderStatus` (`visual_provider: "upload"`, `visual_status: "ready"`, `approved` reset về `false`). Loại file (ảnh PNG/JPEG/WEBP hay video MP4/WEBM/MOV) PHẢI khớp `shot.visual_type` hiện có — đổi kiểu qua `PATCH /visual/shots/{id}` trước nếu cần, endpoint này không tự đổi `visual_type` (giữ ranh giới render.py chỉ đọc pack.json, không ghi lại). Dùng được ngay cả khi chưa từng bấm "Bắt đầu sinh asset" (tự tạo entry `render.json`). Nút "↑ Upload ảnh/video" cạnh nút "Tạo ảnh/video" ở mỗi ShotCard, Visual Studio. |
| POST | `/projects/{id}/output/enter` | **Đã build lại (2026-08-17, mục 44)** — chuyển sang Output Center (step 3, đổi từ step 5 cũ), set LUÔN `status="ready_output"` (trước đây do `/gate2` approve set — nay `/gate2` không còn, endpoint này tự làm trọn vẹn). KHÔNG còn gate nào chặn trước khi gọi — nút "Đi tới Output →" ở Visual Studio dùng được ngay. |
| POST | `/projects/{id}/render/intro/upload-visual` | **Mới (2026-08-20, mục 51)** — shot mở đầu RIÊNG của project. Multipart `file` (ảnh HOẶC video, tự nhận diện) — set `RenderState.intro.kind`/`visual_asset_path`. Đổi sang video → tự xoá `audio_asset_path` cũ (video có audio riêng, không cần audio rời). |
| POST | `/projects/{id}/render/intro/upload-audio` | **Đã build lại (2026-08-20, mục 51)** — audio mở đầu, upload ĐỘC LẬP được (không còn bắt buộc phải có ảnh trước). Chỉ audio (không ảnh) → lúc ghép tự dùng ẢNH shot đầu tiên minh hoạ, giống audio thương hiệu cấp kênh. 400 nếu `kind=="video"` (video tự có audio riêng). |
| DELETE | `/projects/{id}/render/intro` | **Đổi hành vi (2026-08-22, mục 61)** — bỏ HẲN shot mở đầu cho project này, xoá file asset riêng (nếu có) trên đĩa, set `IntroAssetStatus.disabled=True` — KHÔNG còn quay về dùng brand nữa (trước mục 61: quay về fallback brand ngầm). |
| PATCH | `/projects/{id}/render/intro/inherit` | **Mới (2026-08-22, mục 61)** — không cần body. Set `disabled=False`, quay lại kế thừa video/audio thương hiệu cấp kênh (đối xứng với DELETE ở trên). Tự tạo `IntroAssetStatus` nếu chưa có. |
| PATCH | `/projects/{id}/render/intro/transition` | **Mới (2026-08-21, mục 55)** — body `{ transition_to_next }`, validate theo `TRANSITIONS` (400 nếu sai, cùng bảng dùng cho shot-to-shot). Tự tạo `IntroAssetStatus` nếu chưa có. `"cut"` (mặc định) ghép cắt cứng; giá trị khác dùng `_xfade_chain` blend ~0.6s giữa intro và shot đầu tiên. |
| GET | `/projects/{id}/render/intro/asset/{kind}` | **Mới (2026-08-20, mục 51)** — `kind` = `visual`\|`audio`, phục vụ preview (hỗ trợ Range). |
| POST | `/projects/{id}/render/bg-music/upload` | **Mới (2026-08-20, mục 53)** — nhạc nền RIÊNG của project, override nhạc nền mặc định cấp kênh. Multipart `file` (audio WAV/MP3). Giữ nguyên `volume` hiện có nếu đã chỉnh trước đó. |
| PATCH | `/projects/{id}/render/bg-music` | **Mới (2026-08-20, mục 53)** — chỉnh `volume` (0.0-1.0). Tự tạo `BgMusicOverride` nếu chưa có (chỉnh volume trước khi kịp upload file vẫn hợp lệ). |
| DELETE | `/projects/{id}/render/bg-music` | **Mới (2026-08-20, mục 53)** — bỏ nhạc nền riêng, xoá hẳn file trên đĩa, quay về dùng nhạc nền mặc định cấp kênh (nếu có). |
| GET | `/projects/{id}/render/bg-music/asset` | **Mới (2026-08-20, mục 53)** — tải/nghe lại nhạc nền riêng đã upload (hỗ trợ Range). |
| POST | `/projects/{id}/render/overlay/upload` | **Mới (2026-08-22, mục 68)** — hiệu ứng lớp phủ RIÊNG của project (VD mưa/tuyết rơi), override overlay mặc định cấp kênh. Multipart `file` (video mp4/webm/mov). Giữ nguyên `opacity` hiện có nếu đã chỉnh trước đó. |
| PATCH | `/projects/{id}/render/overlay` | **Mới (2026-08-22, mục 68)** — chỉnh `opacity` (0.0-1.0). Tự tạo `OverlayEffectOverride` nếu chưa có. |
| DELETE | `/projects/{id}/render/overlay` | **Mới (2026-08-22, mục 68)** — bỏ overlay riêng, xoá hẳn file trên đĩa, quay về dùng overlay mặc định cấp kênh (nếu có). |
| GET | `/projects/{id}/render/overlay/asset` | **Mới (2026-08-22, mục 68)** — tải/xem lại video overlay riêng đã upload (hỗ trợ Range). |

> **Đã build vòng 4 — đổi tên field**: `Shot.prompt` → `Shot.visual_fx`, `Shot.tts_emotion`
> → `Shot.audio_sfx` (khớp tên 2 trong 6 cột import — xem mục Script Import). Endpoint
> `POST /visual/shots/{id}/regenerate` (gộp cả 2 field) đã bị **xoá**, thay bằng 2
> endpoint `regenerate-visual`/`regenerate-audio` ở trên — không giữ lại cho tương
> thích ngược vì chỉ có frontend nội bộ gọi.

### Script Import — nhập kịch bản CSV/Excel (đã build vòng 4, không có trong bản gốc)
| Method | Path | Mô tả |
|---|---|---|
| GET | `/projects/{id}/script/import/template` | **Mới (2026-08-16)** — trả file `.xlsx` mẫu đúng 6 cột (`build_template_workbook()`, cùng file `script_import.py` — sửa cột thì sửa cả header mẫu lẫn `COLUMN_KEYWORDS` để không lệch nhau), kèm 2 dòng ví dụ minh hoạ định dạng "Thời lượng" (`H:MM–H:MM`). Nội dung tĩnh, không phụ thuộc project — path lồng theo project chỉ để nhất quán với 2 endpoint dưới. Nút "Tải file mẫu" ở Gate1Outline.tsx, cạnh nút Nhập kịch bản. |
| POST | `/projects/{id}/script/import/parse` | Multipart `file` (.csv/.xlsx/.xls, 6 cột: Mã block, Thời lượng, Loại Visual, Visual/FX, Audio/SFX, VO Content). Parse **phía server** (`app/pipeline/script_import.py`, dùng `csv` chuẩn + `openpyxl`), trả `{ beats, stats: {block_count, word_count, duration_label}, full_text }`. KHÔNG ghi vào Pack — chỉ xem trước. Lỗi (thiếu cột/file trống) → 400 kèm thông điệp tiếng Việt hiển thị thẳng cho người dùng. |
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
| GET | `/projects/{id}/retention` | Số liệu đã nhập + chênh lệch so benchmark. |
| PUT | `/projects/{id}/retention` | Lưu số liệu nạp tay (§08). |

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
>   bỏ duyệt (`approved=false`) các shot visual bị sinh lại.
> - `GET /projects/{id}/render/status`, `GET /projects/{id}/render/gpu-status` — trạng
>   thái từng shot + hàng đợi GPU local.
> - `POST /projects/{id}/render/cancel` — dừng batch đang chạy.
> - `POST /projects/{id}/render/shots/{shot_id}/regenerate-visual` /
>   `regenerate-narration` — sinh lại 1 shot riêng lẻ, LUÔN sinh lại (không có khái niệm
>   "resume" ở mức 1 shot — bấm là sinh lại thật).
> - `POST /projects/{id}/render/shots/{shot_id}/approve`,
>   `POST /projects/{id}/render/approve-all` — duyệt shot đã sinh visual xong.
> - `POST /projects/{id}/render/assemble` — ghép MP4 từ các shot đã ready + đã duyệt.
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
| GET | `/providers/local-sdxl/models` | **Mới (2026-08-22, mục 65)** — query `kind` (`checkpoints`\|`loras`) + `base_url` (tuỳ chọn, mặc định ComfyUI `127.0.0.1:8188`). Liệt kê file `.safetensors` THẬT đang có trong ComfyUI (đổ vào dropdown chọn checkpoint provider `local_sdxl`/Style LoRA BrandProfile, thay vì gõ tay). 502 nếu ComfyUI không phản hồi. |

## Cấu hình khác (Admin)
| Method | Path | Mô tả |
|---|---|---|
| GET/PUT | `/settings` | app_setting theo key: `general`, `ai_params`, `app_branding` (🎨 — bổ sung, xem `06_uiux.md`). |
| GET/POST/PATCH/DELETE | `/prompt-templates` | Quản lý prompt template (§07). PATCH nhận `active_version` (đặt mặc định) hoặc `new_version_body`+`new_version_note` (thêm version mới). |
| GET | `/audit-log?type=system\|expense` | Nhật ký, lọc theo loại (khớp seg-control 3 tab trong design). |
| GET | `/budget` | **Đã build**: trả theo TỪNG KÊNH (không phải theo project) — `{channel_id, channel_name, soft_limit, threshold_pct, spent, over_threshold}`. |
| PATCH | `/budget/{channel_id}` | Sửa `soft_limit`/`threshold_pct` cho 1 kênh. |
