# 02 — Database (SQLite)

SQLite là **index/metadata store** (§01). Nội dung nặng (Pack JSON, exports, asset) nằm trên đĩa; DB giữ con trỏ và trạng thái. Dùng SQLAlchemy + Alembic cho migration.

## 1. Sơ đồ quan hệ

```
channel (1) ──< project (1) ──< pack_version
   │                  │
   │                  ├──< retention_entry
   │                  └──< youtube_video_metrics_snapshot
   ├──< brandprofile_version
   └──< youtube_channel_metrics_snapshot

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
| youtube_channel_id | TEXT, null | **mới 2026-09-12** — id kênh YouTube THẬT gắn với kênh này, lấy từ `channels.list(mine=true)` sau khi OAuth (KHÔNG cho user tự nhập tay), xem §M4 dưới |
| youtube_channel_title | TEXT, null | tên kênh YouTube (cache hiển thị, không cần gọi lại API) |
| youtube_connected_at | TEXT, null | ISO datetime lúc kết nối/kết nối lại |

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
| youtube_video_id | TEXT, null | **mới 2026-09-12** — video YouTube tương ứng project này, user TỰ CHỌN từ dropdown ở Output Center (KHÔNG tự đoán theo tên trùng khớp), xem §M4 dưới |
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
| rpm | REAL, null | **mới 2026-09-12** — doanh thu/1.000 view (€), LUÔN nhập tay — quyền `yt-analytics-monetary.readonly` khó xin cho app cá nhân nên không tự động hoá (§M4 dưới) |
| created_at | DATETIME | |

### youtube_channel_metrics_snapshot / youtube_video_metrics_snapshot — **mới 2026-09-12, §M4 (đã triển khai Phase 1)**
Chỉ số kéo TỰ ĐỘNG từ YouTube Data/Analytics API qua OAuth (không phải nạp tay như
`retention_entry`). Mỗi lần bấm "Đồng bộ" (thủ công, đúng CLAUDE.md nguyên tắc 3 — không
polling nền) ghi 1 SNAPSHOT MỚI (không update tại chỗ) — giữ lịch sử theo thời gian, đọc
dòng mới nhất cho hiển thị hiện tại, cùng pattern `retention_entry`. Xem
`app/youtube_analytics.py` + `app/routers/youtube_analytics.py`.

**youtube_channel_metrics_snapshot** (1 dòng/lần đồng bộ, cấp KÊNH):
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| channel_id | TEXT FK→channel | |
| synced_at | TEXT | ISO datetime lúc đồng bộ |
| subscriber_count / total_views / video_count | INTEGER, null | từ `channels.list` |
| avg_view_percentage | REAL, null | APV — trung bình CÓ TRỌNG SỐ theo view giữa các video đã liên kết (không phải trung bình cộng đơn giản) |
| avg_impression_ctr | REAL, null | CTR thumbnail — **luôn null**, YouTube Analytics API công khai KHÔNG có metric này (đã verify thật qua tài liệu chính thức Google, xem mục 153 IMPLEMENTATION_REPORT.md); nhập tay qua `RetentionEntry.thumbnail_ctr` ở Output Center |
| avg_retention_at_30s | REAL, null | retention giây 30, trọng số theo view |
| comments_per_1000_views | REAL, null | tổng bình luận / tổng view * 1000 |
| de_at_ch_views_pct | REAL, null | % view từ Đức/Áo/Thuỵ Sĩ trên tổng view |

**youtube_video_metrics_snapshot** (1 dòng/video/lần đồng bộ, cấp PROJECT):
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | INTEGER PK | |
| project_id | TEXT FK→project | |
| synced_at | TEXT | |
| views / comment_count | INTEGER, null | |
| impressions | INTEGER, null | **luôn null** — metric không tồn tại trên YouTube Analytics API công khai, xem `impression_ctr` bên dưới |
| avg_view_percentage | REAL, null | APV video này |
| avg_view_duration_sec | REAL, null | |
| retention_at_30s | REAL, null | nội suy tuyến tính từ `retention_curve` tại giây 30 |
| impression_ctr | REAL, null | % — **luôn null**, đã verify (mục 153) YouTube Analytics API công khai không có metric `impressions`/`impressionClickThroughRate` cho bất kỳ dimension nào (chỉ có với Content Owner + `yt-analytics-monetary.readonly`, ngoài phạm vi app); CTR thumbnail phải nhập tay |
| video_duration_sec | REAL, null | từ `contentDetails.duration` (ISO 8601) |
| views_by_country | TEXT, null | JSON `{country_code: views}` |
| retention_curve | TEXT, null | JSON `[{ratio, watch_ratio}]` — dimension `elapsedVideoTimeRatio` của report `audienceRetention`, dùng khớp với `pack.script.body[]` theo TỶ LỆ CỘNG DỒN THEO THỨ TỰ BLOCK (không phải giây tuyệt đối của kịch bản gốc, vì timeline video thật ăn theo giọng đọc thật) — xem `correlate_retention_with_blocks`, endpoint `GET /projects/{id}/youtube/retention-chapters` |

### app_setting — dùng thêm key OAuth YouTube (§M4, per-channel từ mục 154)
`youtube_oauth_client` (JSON `{client_id, client_secret}`, mã hoá qua `app/crypto.py`) —
1 dòng DÙNG CHUNG toàn app (chỉ là định danh app đăng ký với Google). Token truy cập
(access/refresh) dùng key `youtube_oauth:{channel_id}` — **1 dòng RIÊNG cho MỖI kênh
StudioFlow** (sửa mục 154, thiết kế cũ Phase 1 dùng 1 key cố định `youtube_oauth` chung
toàn app — SAI khi 1 Google Account quản nhiều kênh YouTube, 2 kênh StudioFlow bị gán
NHẦM cùng 1 kênh YouTube thật). Vẫn TÁI DÙNG bảng key-value chung (không tạo bảng riêng)
— chỉ đổi cách đặt key, không cần migration schema. Xem `app/youtube_analytics.py::
load_oauth_client`/`save_credentials`/`load_credentials`, `youtube_migration.py::
migrate_youtube_token_to_per_channel` (di trú token cũ sang key riêng cho kênh đã kết nối
trước bản sửa).

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
| status | TEXT | `detecting`/`tagging`/`indexed`/`error` — có thể bị KẸT sai nếu backend crash/khởi động lại giữa 1 task nền (`auto_detect_scenes`/`caption_all_pending_clips` chỉ ghi status ở dòng cuối cùng); `GET /asset-vault/raw` và `GET /asset-vault/clips` tự SUY LẠI (self-heal) từ dữ liệu clip con có sẵn mỗi lần đọc, xem `ingest.py::reconcile_raw_video_status` + IMPLEMENTATION_REPORT.md mục 132 |
| error_message | TEXT, null | |
| progress_current | INTEGER, null | **mới 2026-08-27**: tiến trình thật (byte đã tải qua yt-dlp `progress_hooks`, hoặc frame/clip đã xử lý qua PySceneDetect `callback=`) — null khi không có việc gì đang chạy |
| progress_total | INTEGER, null | tổng tương ứng (`total_bytes`/tổng frame/tổng số clip cần cắt) |
| progress_label | TEXT, null | nhãn hiển thị (VD "Đang cắt cảnh 3/12") |
| created_at | DATETIME | |
| source_project_id | TEXT, null | **mới 2026-09-11** — đánh dấu hàng "ảo" đại diện 1 `Project` (Visual Studio), KHÔNG phải video thật user upload/dán URL — không có file thật, `original_filename`=tên project. `GET /asset-vault/raw` lọc `source_project_id IS NULL` (loại khỏi Raw Library). Xem `asset_vault/from_visual_studio.py`. |

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
| media_kind | TEXT | **mới 2026-09-11** — `"video"` (mặc định, MỌI clip cắt cảnh cũ+mới) hoặc `"image"` (asset ảnh lưu từ Visual Studio). Dùng để lọc đúng loại khi gợi ý/gán vào shot (`assign_vault_clip`/`matching.py`). |
| source_shot_id | TEXT, null | **mới 2026-09-11** — `shot_id` GỐC, chỉ có giá trị khi clip được LƯU từ Visual Studio (`raw_video_id` trỏ tới hàng `raw_video` "ảo" của project đó) — dùng nhận diện "đã lưu chưa" để cập nhật đè thay vì tạo dòng mới. Xem `asset_vault/from_visual_studio.py::save_shots_to_vault`. |

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
