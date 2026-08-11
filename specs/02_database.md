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
- Xoá Project = archive (soft delete) ở MVP, không xoá cứng file.
