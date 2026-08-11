# 03 — API Contract (FastAPI ↔ React)

REST trên `http://127.0.0.1:{PORT}`. Tất cả body JSON. Không auth (single-user, localhost). Lỗi trả `{ "error": { "code": "...", "message": "..." } }` với HTTP status phù hợp.

Quy ước: `POST` tạo/kích hoạt, `PATCH` cập nhật một phần, `GET` đọc, `DELETE` archive.

## System
| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | Health-check (Electron chờ khi khởi động). |
| GET | `/bootstrap` | Trả trạng thái cấu hình: đã có provider chưa, settings, danh sách channel. Frontend gọi đầu tiên. |

## Channel
| Method | Path | Mô tả |
|---|---|---|
| GET | `/channels` | Danh sách channel + số project, số chờ duyệt. |
| POST | `/channels` | Tạo channel. |
| GET | `/channels/{id}` | Chi tiết + brandprofile hiện hành. |
| PATCH | `/channels/{id}` | Đổi tên/archive. |

## BrandProfile
| Method | Path | Mô tả |
|---|---|---|
| GET | `/channels/{id}/brandprofile` | BrandProfile hiện hành (JSON §04). |
| PUT | `/channels/{id}/brandprofile` | Lưu bản mới → tạo version mới. |
| GET | `/channels/{id}/brandprofile/versions` | Lịch sử version. |
| POST | `/channels/{id}/brandprofile/clone-from/{src_channel_id}` | Clone từ kênh khác. |

## Project
| Method | Path | Mô tả |
|---|---|---|
| GET | `/channels/{id}/projects` | Danh sách project của kênh. |
| POST | `/channels/{id}/projects` | Tạo project (khởi tạo `draft`). |
| GET | `/projects/{id}` | Chi tiết + status + con trỏ pack. |
| PATCH | `/projects/{id}` | Cập nhật title/status. |
| DELETE | `/projects/{id}` | Archive. |

## Brief
| Method | Path | Mô tả |
|---|---|---|
| GET | `/projects/{id}/brief` | Đọc brief (4 nhóm input). |
| PUT | `/projects/{id}/brief` | Lưu brief. Trả về danh sách trường còn thiếu (không chặn). |
| POST | `/projects/{id}/brief/sources` | **Đã build, mới**: thêm nguồn tham khảo — multipart `file` hoặc form field `youtube_url`. MVP trích xuất text đơn giản (đếm ký tự với file text-based); transcript YouTube thật để mốc sau. |
| DELETE | `/projects/{id}/brief/sources/{source_id}` | Gỡ 1 nguồn tham khảo. |

## Pipeline AI (lõi)

> **Đã build — endpoint thực tế khác bản dưới đây**, vì design tách quy trình generation
> thành nhiều màn tương tác nhỏ hơn (Outline+Hook gộp chung, Script Studio tách biệt
> "viết Full Script" khỏi "bóc tách theo đoạn", Visual Studio riêng cho shot).
> Bảng gốc giữ lại để tham chiếu ý định ban đầu; bảng "Endpoint đã build" bên dưới là
> nguồn sự thật hiện hành.

| Method | Path | Mô tả (ý định gốc) |
|---|---|---|
| POST | `/projects/{id}/research` | Chạy AI Research → trả 2–3 dàn ý + tổng hợp tài liệu. Chuyển status `researching`→`await_gate1`. |
| POST | `/projects/{id}/hooks` | Sinh 3 Hook Variants (kiểu tâm lý, **không kèm điểm**). |
| POST | `/projects/{id}/gate1` | **Human Gate #1**: nhận `{ chosen_outline_id, chosen_hook, edited_hook }`. Bắt buộc trước generation. |
| POST | `/projects/{id}/generate` | Sinh kịch bản chi tiết + shot prompts. Yêu cầu đã qua gate1. Hỗ trợ streaming (xem dưới). Chuyển `generating`→`await_gate2`. |
| POST | `/projects/{id}/gate2` | **Human Gate #2**: `{ action: "approve"｜"return", note }`. `approve`→`ready_output`; `return`→`await_gate1` (tăng version). |

### Endpoint đã build (khớp `backend/app/routers/pipeline.py`)
| Method | Path | Mô tả |
|---|---|---|
| POST | `/projects/{id}/research` | Sinh **cả outline lẫn hook** trong 1 lệnh (khớp UX: bấm "Bắt đầu Research" xong thấy cả hai ở Gate 1). Ghi vào `pack.research` + `pack.hooks`. Chuyển step 0→1, status→`await_gate1`. |
| POST | `/projects/{id}/gate1` | `{ chosen_outline_id, chosen_hook_id, edited_hook_text? }` — đánh dấu selected + gọi luôn AI Generation Full Script. Chuyển step→2, status→`generating`. |
| POST | `/projects/{id}/script/regenerate` | `{ feedback }` — viết lại Full Script theo góp ý (không đổi step). |
| PATCH | `/projects/{id}/script/text` | Auto-save khi sửa tay Full Script (im lặng, §06 mục 5). |
| POST | `/projects/{id}/script/approve` | Bóc tách Full Script theo đoạn (timestamp/audio/visual/direction) + chạy guardrail, gắn cảnh báo inline vào từng dòng. |
| POST | `/projects/{id}/visual/generate` | Sinh Shot List (mỗi shot = 1 beat: visual_fx + audio_sfx). Nếu `script.source == "import"` seed trực tiếp từ nội dung block, KHÔNG gọi AI (§ mục Script Import bên dưới). Chuyển step→3. |
| PATCH | `/projects/{id}/visual/shots/{shot_id}` | Sửa tay 1 shot (`visual_fx`/`audio_sfx`/`visual_type`), không gọi AI. |
| POST | `/projects/{id}/visual/shots/{shot_id}/regenerate-visual` | Sinh lại RIÊNG `visual_fx` bằng AI (đã build vòng 4 — tách khỏi audio, khớp 2 nút riêng trong design). |
| POST | `/projects/{id}/visual/shots/{shot_id}/regenerate-audio` | Sinh lại RIÊNG `audio_sfx` bằng AI. |
| POST | `/projects/{id}/visual/generate-all-visual` | Sinh lại `visual_fx` cho TOÀN BỘ shot (nút header "Tạo Visual cho toàn bộ block"). |
| POST | `/projects/{id}/visual/generate-all-tts` | Sinh lại `audio_sfx` cho TOÀN BỘ shot (nút header "Tạo giọng đọc (TTS) cho toàn bộ block"). |
| POST | `/projects/{id}/pack/build` | Sinh Title/Description/Hashtags/Thumbnail + chạy guardrail tổng hợp. Chuyển step→4, status→`await_gate2`. |
| POST | `/projects/{id}/gate2` | `{ action: "approve"｜"return", note }`. `approve`→ step 5, status `ready_output`. `return`→ **step 2 (Script Studio)**, không phải step 1 — xem `02_database.md` §2 ghi chú enum. Tăng `pack_version`. |
| POST | `/projects/{id}/output/enter` | Chuyển sang Output Center (step 5) sau khi Gate #2 approved. |

> **Đã build vòng 4 — đổi tên field**: `Shot.prompt` → `Shot.visual_fx`, `Shot.tts_emotion`
> → `Shot.audio_sfx` (khớp tên 2 trong 6 cột import — xem mục Script Import). Endpoint
> `POST /visual/shots/{id}/regenerate` (gộp cả 2 field) đã bị **xoá**, thay bằng 2
> endpoint `regenerate-visual`/`regenerate-audio` ở trên — không giữ lại cho tương
> thích ngược vì chỉ có frontend nội bộ gọi.

### Script Import — nhập kịch bản CSV/Excel (đã build vòng 4, không có trong bản gốc)
| Method | Path | Mô tả |
|---|---|---|
| POST | `/projects/{id}/script/import/parse` | Multipart `file` (.csv/.xlsx/.xls, 6 cột: Mã block, Thời lượng, Loại Visual, Visual/FX, Audio/SFX, VO Content). Parse **phía server** (`app/pipeline/script_import.py`, dùng `csv` chuẩn + `openpyxl`), trả `{ beats, stats: {block_count, word_count, duration_label}, full_text }`. KHÔNG ghi vào Pack — chỉ xem trước. Lỗi (thiếu cột/file trống) → 400 kèm thông điệp tiếng Việt hiển thị thẳng cho người dùng. |
| POST | `/projects/{id}/script/import/confirm` | Body `{ beats, full_text }` (từ response của `/parse`) → ghi vào `pack.script` (`source: "import"`), chạy guardrail, **bỏ qua AI Generation**, nhảy thẳng step→2 (Script Studio, đã duyệt), status→`generating`. Không yêu cầu đã qua Gate 1 trước đó. |

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

## Provider AI (Admin)
| Method | Path | Mô tả |
|---|---|---|
| GET | `/providers` | Danh sách provider theo task. |
| POST | `/providers` | Thêm provider (cloud hoặc local endpoint). |
| PATCH | `/providers/{id}` | Cập nhật (model, default, fallback, enabled). |
| DELETE | `/providers/{id}` | Xoá (thao tác phá huỷ — cần xác nhận ở UI). |
| POST | `/providers/{id}/test` | Test kết nối → cập nhật `status`. |

## Cấu hình khác (Admin)
| Method | Path | Mô tả |
|---|---|---|
| GET/PUT | `/settings` | app_setting theo key: `general`, `ai_params`, `app_branding` (🎨 — bổ sung, xem `06_uiux.md`). |
| GET/POST/PATCH/DELETE | `/prompt-templates` | Quản lý prompt template (§07). PATCH nhận `active_version` (đặt mặc định) hoặc `new_version_body`+`new_version_note` (thêm version mới). |
| GET | `/audit-log?type=system\|expense` | Nhật ký, lọc theo loại (khớp seg-control 3 tab trong design). |
| GET | `/budget` | **Đã build**: trả theo TỪNG KÊNH (không phải theo project) — `{channel_id, channel_name, soft_limit, threshold_pct, spent, over_threshold}`. |
| PATCH | `/budget/{channel_id}` | Sửa `soft_limit`/`threshold_pct` cho 1 kênh. |
