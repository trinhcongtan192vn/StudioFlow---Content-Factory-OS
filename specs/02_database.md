# 02 — Database (SQLite)

SQLite là **index/metadata store** (§01). Nội dung nặng (Pack JSON, exports, asset) nằm trên đĩa; DB giữ con trỏ và trạng thái. Dùng SQLAlchemy + Alembic cho migration.

## 1. Sơ đồ quan hệ

```
channel (1) ──< project (1) ──< pack_version
   │                  │
   │                  └──< retention_entry
   └──< brandprofile_version

provider_config      app_setting      prompt_template      audit_log
(độc lập)            (key-value)      (độc lập)            (độc lập)
```

## 2. Bảng

### channel
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | TEXT PK | ví dụ `ch_finance_01` |
| name | TEXT | |
| created_at | DATETIME | |
| brandprofile_path | TEXT | trỏ tới `brandprofile.json` hiện hành |
| brandprofile_version | INTEGER | version đang active |
| archived | BOOLEAN | default 0 |

### brandprofile_version
Lưu lịch sử version của BrandProfile (nội dung đầy đủ ở file JSON, §04).
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| channel_id | TEXT FK→channel | |
| version | INTEGER | |
| file_path | TEXT | `brandprofile.v{n}.json` |
| created_at | DATETIME | |
| note | TEXT | mô tả thay đổi |

### project
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | TEXT PK | `prj_2026_0142` |
| channel_id | TEXT FK→channel | |
| title | TEXT | tên nội bộ |
| status | TEXT | enum §3 |
| brief_path | TEXT | `brief.json` |
| pack_path | TEXT | `pack.json` hiện hành |
| pack_version | INTEGER | |
| parent_project_id | TEXT FK→project, null | **mới (2026-08-21, mục 58)**: short-form (9:16) là sub-project ĐỘC LẬP nội dung, lồng dưới 1 project long-form CÙNG kênh chỉ để nhóm hiển thị — null = long-form, có giá trị = short-form. Không lồng quá 1 cấp (parent LUÔN là long-form). |
| format | TEXT | **mới (2026-08-21, mục 58)**: `"long"` (mặc định) \| `"short"` — quyết định tỷ lệ khung sinh ảnh/video/ghép MP4 (`app/render/assembly.py::RESOLUTION_MAP_VERTICAL`). |
| created_at / updated_at | DATETIME | |

### pack_version
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| project_id | TEXT FK→project | |
| version | INTEGER | |
| file_path | TEXT | `pack.v{n}.json` |
| status_at_save | TEXT | trạng thái khi lưu |
| created_at | DATETIME | |

### retention_entry
Số liệu nạp tay (§08).
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| project_id | TEXT FK→project | |
| published_at | DATE | |
| ret_0 / ret_25 / ret_50 / ret_100 | REAL | % giữ chân tại mốc |
| avg_view_duration | REAL | giây |
| thumbnail_ctr | REAL | % |
| created_at | DATETIME | |

### provider_config
Cấu hình provider AI (§05).
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| task | TEXT | enum: `llm`/`tts`/`image`/`video` |
| provider_name | TEXT | `claude`/`gemini`/`openai`/`flux`/`ollama`… |
| connection_type | TEXT | `cloud_api` / `local_endpoint` |
| api_key_encrypted | TEXT | null nếu local |
| endpoint_url | TEXT | dùng cho local |
| model_name | TEXT | |
| is_default | BOOLEAN | provider mặc định cho task |
| is_fallback | BOOLEAN | |
| enabled | BOOLEAN | |
| status | TEXT | `ok`/`error`/`untested` |

### app_setting
Key-value cho Cấu hình chung, Tham số AI mặc định, Thương hiệu ứng dụng.
| Cột | Kiểu | Ghi chú |
|---|---|---|
| key | TEXT PK | ví dụ `default_temperature`, `org_name` |
| value | TEXT | JSON-encoded nếu phức tạp |

### prompt_template
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| task | TEXT | `research`/`script`/`hook`/`shot_prompt`/`title`… |
| version | INTEGER | |
| content | TEXT | nội dung prompt (§07) |
| is_default | BOOLEAN | |
| created_at | DATETIME | |

### audit_log
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| action | TEXT | `provider_changed`/`budget_updated`/`config_changed`… |
| detail | TEXT | JSON |
| created_at | DATETIME | |

### budget (đơn giản, MVP)
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| channel_id | TEXT FK→channel, null | **đã build**: hạn mức đặt theo KÊNH (màn Chi phí & Ngân sách trong design nhóm theo kênh, không theo project) |
| project_id | TEXT FK→project | null = ngân sách chung |
| soft_limit | REAL | ngưỡng cảnh báo |
| threshold_pct | INTEGER | **đã build, mới**: % ngưỡng cảnh báo (mặc định 60-80%) — cần cho thanh so sánh trong design |
| spent | REAL | cộng dồn chi phí ước tính |

### raw_video — **mới 2026-08-26, chuyển TOÀN CỤC + gắn nhiều kênh 2026-08-27 (CHANGE_Semantic_BRoll_Asset_Vault.md)**
Kho Tài Nguyên là 1 màn RIÊNG ở sidebar (KHÔNG còn theo từng kênh) — hiện TẤT CẢ video/
clip từ MỌI kênh, lọc theo kênh qua query param. 1 `RawVideo` gắn được NHIỀU kênh dạng tag
(bắt buộc ≥1 lúc import) qua bảng m2m `raw_video_channel` — bảng m2m ĐẦU TIÊN của dự án.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | TEXT PK | `raw_<ts>` |
| file_path | TEXT | trong `asset_vault_raw_dir()` (`workspace/asset_vault/raw/`, TOÀN CỤC — sibling của `LIBRARY_DIR`, không còn theo `channel_dir`) |
| source_url | TEXT, null | null nếu upload trực tiếp, khác null nếu tải qua yt-dlp (CHỈ khi user tự dán link + xác nhận) |
| original_filename | TEXT, null | **mới 2026-08-27** — tên file GỐC user upload, giữ NGUYÊN (không sanitize) chỉ để hiển thị (`_raw_video_name`/`rawVideoLabel` ưu tiên field này) — tên trên đĩa (`file_path`) vẫn có tiền tố `{raw_id}_` + bản đã sanitize (bỏ ký tự nguy hiểm, giữ dấu tiếng Việt) |
| import_note | TEXT | ghi chú nguồn/license, tuỳ chọn |
| status | TEXT | `detecting`/`tagging`/`indexed`/`error` |
| error_message | TEXT, null | |
| progress_current | INTEGER, null | **mới 2026-08-27**: tiến trình thật (byte đã tải qua yt-dlp `progress_hooks`, hoặc frame/clip đã xử lý qua PySceneDetect `callback=`) — null khi không có việc gì đang chạy |
| progress_total | INTEGER, null | tổng tương ứng (`total_bytes`/tổng frame/tổng số clip cần cắt) |
| progress_label | TEXT, null | nhãn hiển thị (VD "Đang cắt cảnh 3/12") |
| created_at | DATETIME | |

### raw_video_channel — **mới 2026-08-27, bảng m2m ĐẦU TIÊN của dự án**
| Cột | Kiểu | Ghi chú |
|---|---|---|
| raw_video_id | TEXT FK→raw_video, PK | |
| channel_id | TEXT FK→channel, PK | |

Quản lý dưới dạng TAG — 1 video gốc gắn nhiều kênh, sửa lại bất kỳ lúc nào qua
`PATCH /asset-vault/raw/{raw_id}/channels` (ghi đè toàn bộ danh sách).

### processed_clip — **mới 2026-08-26, bỏ `channel_id` riêng 2026-08-27, có tag kênh riêng 2026-08-28**
| Cột | Kiểu | Ghi chú |
|---|---|---|
| clip_id | TEXT PK | `clip_<ts>` |
| raw_video_id | TEXT FK→raw_video | KHÔNG cascade xoá khi raw_video bị xoá — clip đã cắt dùng được độc lập. Chỉ dùng để hiện "video nguồn"/trạng thái, KHÔNG còn dùng để tra kênh (xem `channels` dưới) |
| storage_url | TEXT | trong `asset_vault_clips_dir()` (`workspace/asset_vault/clips/`, TOÀN CỤC) |
| duration_sec | REAL | đo qua ffprobe lúc cắt |
| resolution | TEXT | `"WxH"` |
| caption | TEXT | AI sinh (Vision provider) hoặc tay |
| tags | TEXT | JSON array (string) |
| mood_tone | TEXT | |
| vector_id | TEXT, null | id trong Chroma collection TOÀN CỤC — null nếu chưa embed |
| usage_count | INTEGER | tăng khi gán vào 1 shot (`ShotRenderStatus.linked_clip_id`) |
| last_used_at | DATETIME, null | |
| active | BOOLEAN | tắt = ẩn khỏi gợi ý matching, không xoá |
| rights_status | TEXT | `unverified` (mặc định)/`licensed_verified`/`public_domain` — cảnh báo Guardrail khi `unverified` |
| rights_note | TEXT | ghi chú license/nguồn do user nhập |
| created_at | DATETIME | |
| caption_error | TEXT, null | **mới 2026-08-27** — lỗi gắn nhãn AI lần gần nhất (nếu có), riêng TỪNG clip — dùng cho bulk gắn nhãn theo lựa chọn tự do (`POST /asset-vault/clips/caption-batch`, có thể trải nhiều `raw_video` khác nhau, không có 1 hàng RawVideo chung để gắn cờ lỗi như luồng "Gắn nhãn" theo từng video). Xoá (null) khi gắn nhãn lại thành công hoặc khi user tự sửa caption tay. |

### processed_clip_channel — **mới 2026-08-28, bảng m2m thứ 2 của dự án**
| Cột | Kiểu | Ghi chú |
|---|---|---|
| clip_id | TEXT FK→processed_clip, PK | |
| channel_id | TEXT FK→channel, PK | |

Bug thật đã sửa (xem IMPLEMENTATION_REPORT.md mục 98): kênh của 1 clip TỪNG CHỈ suy ra qua
JOIN `raw_video_id` → `raw_video` → `raw_video_channel` — xoá `raw_video` cha (hành vi
BÌNH THƯỜNG, không cascade xoá clip con) làm clip mất SẠCH thông tin kênh + biến mất khỏi
mọi kết quả matching B-roll của MỌI kênh (`asset_vault/matching.py::_clips_for_channel`
vốn INNER JOIN qua `raw_video`). Nay clip có tag kênh RIÊNG, SAO CHÉP từ `raw_video.
channels` NGAY lúc cắt cảnh (`ingest.py::_make_clip_row`), độc lập với raw_video cha từ
đó — sửa tay được riêng từng clip (`PATCH /asset-vault/clips/{id}/channels`) hoặc hàng
loạt (`POST /asset-vault/clips/batch-tag-channels`, union không ghi đè). Sửa kênh Ở MỨC
RAW VIDEO (`PATCH /asset-vault/raw/{id}/channels`, `POST .../batch-tag-channels`) vẫn
CASCADE ghi đè/cộng thêm xuống mọi clip con hiện có, giữ UX "1 control edit cả nhóm".
DB cũ (trước bản vá) được backfill 1 lần lúc khởi động (`asset_vault/migration.py::
_backfill_processed_clip_channel`) — chỉ khôi phục được clip mà raw_video cha CÒN TỒN
TẠI tại thời điểm chạy migration; clip đã mồ côi TỪ TRƯỚC coi như mất tag vĩnh viễn, cần
gắn lại tay.

Vector DB: Chroma `PersistentClient` file-based tại `asset_vault_chroma_dir()`
(`workspace/asset_vault/vault.chroma/`) — **1 collection TOÀN CỤC** (trước đây 1
collection/kênh, đổi 2026-08-27 khớp kho toàn cục) — lọc kênh chuyển hẳn sang tầng SQL
(JOIN qua `raw_video_channel`) SAU khi overfetch Chroma (`top_k*10`, tăng hệ số vì không
còn tách vật lý theo kênh), KHÔNG chạy service riêng (khớp triết lý SQLite/file của hệ
thống). Xem `app/asset_vault/vector_store.py`.

Migration 1 lần lúc backend khởi động (`app/asset_vault/migration.py`, gọi từ
`main.py` ngay sau `create_all()`, idempotent): chuyển `raw_video.channel_id` cũ (cột FK
đơn) sang bảng `raw_video_channel`, thêm cột `progress_*`, di chuyển file thật từ
`channels/<id>/asset_vault/...` sang thư mục toàn cục mới. Dùng pattern SQLite "12-step"
(rename bảng cũ → `create_all()` tạo bảng mới đúng schema → copy dữ liệu qua → xoá bảng
cũ) vì `ALTER TABLE DROP COLUMN` từ chối cột đang nằm trong `FOREIGN KEY` constraint.

### prompt_template — **đã build: tách 2 bảng thay vì 1**
Bản gốc mô tả 1 bảng `prompt_template` có cột `version`; bản build tách `prompt_template` (id, name, task, active_version) + `prompt_template_version` (template_id FK, version, content, note, updated_by, created_at) để giữ đúng lịch sử nhiều bản ghi/1 template mà UI Prompt Templates (🧩) trong design yêu cầu (mỗi template có nhiều version xem lại được, không phải version rời).

### app_setting — dùng thêm key `app_branding`
Ngoài `default_temperature`, `org_name`… dùng thêm key `app_branding` (JSON `{name, accent_swatch}`) cho màn Thương hiệu ứng dụng (🎨) — không cần bảng riêng.

## 3. Enum trạng thái Project

`draft` → `researching` → `await_gate1` → `generating` → `await_gate2` → `ready_output` → `exported` → `published`

Trả về từ gate: `await_gate2` → `await_gate1` (giữ lịch sử, tăng pack_version).

> **Đã build — lệch nhỏ:** design đưa nút "Trả về" đi thẳng về màn Script Studio (step 2), không phải về Outline & Hook (step 1). Vì enum không có trạng thái riêng cho "đang ở Script Studio sau khi trả về", bản build dùng lại `generating` cho quãng này. Xem IMPLEMENTATION_REPORT.md mục Gate #2.

## 4. Nguyên tắc

- **Không** lưu nội dung Pack/BrandProfile đầy đủ trong DB — chỉ path + version. File JSON là nguồn sự thật.
- Version = ghi file mới `*.v{n}.json` + thêm dòng vào bảng version, cập nhật con trỏ hiện hành.
- Xoá Project/Channel = archive (soft delete, `archived=True`) — item chuyển vào **Thùng
  rác** (`GET /trash`, `frontend/src/screens/Trash.tsx`, đã build 2026-08-16), không xoá
  file, khôi phục được (`POST .../restore`). Chỉ khi người dùng chủ động bấm "Xoá vĩnh
  viễn" TỪ Thùng rác (`DELETE .../permanent`) mới thật sự xoá DB row (cascade — xem
  `Channel.projects`/`Project.pack_versions`/`retention_entries` ở app/models) VÀ xoá cây
  thư mục trên đĩa (`app/config.py::delete_channel_dir`/`delete_project_dir`) — không thể
  hoàn tác.
