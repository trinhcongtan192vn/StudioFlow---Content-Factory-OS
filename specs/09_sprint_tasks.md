# 09 — Sprint Tasks (Epic-level)

Chia theo epic, sắp xếp theo thứ tự phụ thuộc. **Chỉ M1 (MVP) là phạm vi build hiện tại**; M2–M4 liệt kê để giữ ranh giới, chưa triển khai.

> **Trạng thái: M1 (MVP) đã build** theo design `StudioFlow Prototype.dc.html` —
> Electron + FastAPI + SQLite + React đã chạy end-to-end (đã verify: Electron spawn
> backend → health check → React app → gọi API thật). Chi tiết quyết định/lệch so với
> mô tả epic dưới đây: xem `IMPLEMENTATION_REPORT.md` ở gốc repo. Lệch epic đáng chú ý
> nhất: **EPIC 7** trong thực tế tách UI thành 3 màn tương tác (Outline&Hook / Script
> Studio / Visual Studio) thay vì 1 màn Script Studio duy nhất — xem `06_uiux.md` §2.

Thứ tự triển khai M1 (theo dependency): Foundation → DB → Provider AI → Data schemas → Pipeline → Guardrail → UI → Export.

## MỐC M0–M1 (MVP) — BUILD NGAY

### EPIC 1 — Foundation & App Shell
- Dựng khung Electron + React + FastAPI; Electron spawn backend, health-check (§01).
- Cấu trúc thư mục theo §01; workspace layout file-as-source.
- `/health`, `/bootstrap` (§03).
**Done:** app mở, backend chạy, frontend gọi được `/bootstrap`.

### EPIC 2 — Database & Models
- SQLite + SQLAlchemy + Alembic; toàn bộ bảng §02.
- Enum trạng thái Project; cơ chế version (ghi file `*.v{n}.json` + dòng version).
**Done:** CRUD channel/project chạy, version hoạt động.

### EPIC 3 — Provider AI (Admin, đầy đủ)
- Bảng `provider_config`; interface adapter §05.
- Adapter LLM: Claude, Gemini, OpenAI (cloud) + LocalOpenAICompat (Ollama/vLLM/LM Studio).
- Khai báo interface TTS/Image/Video (chưa thực thi asset ở MVP).
- API `/providers*` + test kết nối; mã hoá key at-rest; factory chọn default/override.
- Màn Provider AI (§06 mục 4): nhiều thẻ/nhóm, thêm cloud/local, dropdown default.
**Done:** thêm được provider cloud + local, test OK, chọn default; pipeline lấy đúng provider.

### EPIC 4 — Data Schemas & Config
- Pydantic models cho BrandProfile, Brief, ProductionPack (§04) = hợp đồng dữ liệu.
- `app_setting`, `prompt_template` seed mặc định (§07); màn Cấu hình chung, Tham số AI, Prompt Templates, Thương hiệu, Audit Log, Chi phí (§06 mục 3).
**Done:** đọc/ghi schema tròn vẹn; khu Cài đặt đầy đủ.

### EPIC 5 — Channel & BrandProfile
- CRUD channel; wizard BrandProfile nhiều bước + clone từ kênh khác; version hoá.
- Retention benchmark theo kênh.
- Màn Dashboard kênh (§06 màn ①).
**Done:** tạo kênh, cấu hình BrandProfile, xem lịch sử version.

### EPIC 6 — Brief Intake
- Schema Brief 4 nhóm (§04); màn Brief Editor (§06 màn ②) với chip "cần bổ sung".
- Kế thừa BrandProfile theo kênh; chọn conversion_point.
**Done:** tạo & lưu brief, cảnh báo trường thiếu (không chặn).

### EPIC 7 — Script Studio Pipeline (LÕI)
- AI Research → 2–3 outline (§07 mục 1).
- Hook Variants 3 kiểu, không điểm (§07 mục 2).
- **Human Gate #1** bắt buộc (§03 `/gate1`) — không bypass.
- AI Generation kịch bản đa cột + streaming SSE (§03, §06); framework AIDA/PAS.
- Màn Script Studio (§06 màn ③): editor 2 cột, chọn/sửa Hook, cảnh báo inline.
**Done:** đi từ brief → outline → gate1 → kịch bản chi tiết, streaming mượt.

### EPIC 8 — Retention Guardrail
- Hook Strength (rubric §07 mục 6) + Anchor Gap + brand-fit (§08).
- `/guardrail/check`; ghi `retention_check`; hiển thị inline + Pack Review.
- Nạp retention thủ công: form + `retention_entry` + thanh so sánh (§08 mục 6, màn ⑥).
**Done:** check chạy, cảnh báo phân cấp màu; nhập & đối chiếu retention.

### EPIC 9 — Production Pack & Gate #2
- Shot Prompt Builder (§07 mục 4) + Title/Thumbnail Concepts (§07 mục 5).
- Assembly Pack đầy đủ (§04); màn Pack Review (§06 màn ④).
- **Human Gate #2** approve/return; return → về gate1, tăng version.
**Done:** Pack hoàn chỉnh, duyệt/trả về hoạt động, khoá Output tới khi approve.

### EPIC 10 — Output: Export
- `/export` sinh Markdown/PDF/JSON từ Pack (§04 mục 4); màn Output Center (§06 màn ⑤).
- Thẻ "Render in-app" hiện nhãn Beta, disabled.
**Done:** export ra file người-đọc + JSON, tải được.

### EPIC 11 — Polish UX
- Auto-save + version im lặng, phím tắt, optimistic UI, trạng thái rỗng có hướng dẫn, cảnh báo phân cấp màu (§06 mục 5).
- Modal xác nhận thao tác phá huỷ + Audit Log.
**Done:** đạt ngưỡng hiệu năng UX (<100ms optimistic, streaming <2s).

---

## MỐC SAU — CHƯA BUILD (giữ ranh giới)

### M2 — Production Layer (Beta)
- Thực thi adapter TTS/Image/Video; sinh asset thật.
- `/render`: ghép MP4 "đủ đăng", giới hạn số shot; human review asset trước ghép.
- Module render **tách biệt** script core, chỉ đọc `pack.json`.
- Chi phí render vào màn 💳 (đã có sẵn).

### M3 — Scale & Repurpose (GA)
- Repurposing Pack: short-form marks + Community Post/poll (mở khối `repurpose` trong schema).
- Kanban hàng đợi đa kênh.

### M4 — Intelligence Loop (Post-GA)
- Tích hợp YouTube Analytics API thay nạp tay (§08 mục 7).
- Tinh chỉnh gợi ý Hook/cấu trúc theo dữ liệu tích lũy.

---

## Ràng buộc xuyên suốt (mọi epic)
- Single-user, không RBAC.
- Provider thay thế được; không hardcode tên provider trong business logic.
- `04_data_schemas.md` là nguồn sự thật; đổi schema cập nhật file đó trước.
- Chống coupling: script core ⟂ render module.
