# 09 — Sprint Tasks (Epic-level)

Chia theo epic, sắp xếp theo thứ tự phụ thuộc. **Chỉ M1 (MVP) là phạm vi build hiện tại**; M2–M4 liệt kê để giữ ranh giới, chưa triển khai.

> **Trạng thái: M1 (MVP) đã build** theo design `StudioFlow Prototype.dc.html` —
> Electron + FastAPI + SQLite + React đã chạy end-to-end (đã verify: Electron spawn
> backend → health check → React app → gọi API thật). Chi tiết quyết định/lệch so với
> mô tả epic dưới đây: xem `IMPLEMENTATION_REPORT.md` ở gốc repo. Lệch epic đáng chú ý
> nhất: **EPIC 7** trong thực tế tách UI thành 3 màn tương tác (Outline&Hook / Script
> Studio / Visual Studio) thay vì 1 màn Script Studio duy nhất — xem `06_uiux.md` §2.
>
> **Đã build lại, 2026-08-17 (mục 44 IMPLEMENTATION_REPORT.md) — bỏ HẲN AI Research/
> Outline/Hook/Human Gate #1 (EPIC 7) và Production Pack/Human Gate #2 (EPIC 9)**, theo
> yêu cầu người dùng: "tập trung vào luồng chính: upload script, tạo visual và voice,
> sau đó render". Luồng M1 thật hiện tại chỉ còn: Brief → **Upload script (import CSV/
> Excel — con đường DUY NHẤT để có kịch bản)** → Visual Studio (shot list + sinh/upload
> ảnh-video + giọng đọc) → Output (export). Không còn gate nào theo `project.status`
> chặn giữa các bước. Các mục epic dưới đây giữ nguyên làm tài liệu Ý ĐỊNH GỐC (M1 ban
> đầu thật sự có Research/Outline/Hook/Gate #1/#2) — đánh dấu phần đã bỏ bằng blockquote
> ngay dưới mỗi epic liên quan, không xoá để giữ lịch sử quyết định.

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
- ~~AI Research → 2–3 outline (§07 mục 1).~~
- ~~Hook Variants 3 kiểu, không điểm (§07 mục 2).~~
- ~~**Human Gate #1** bắt buộc (§03 `/gate1`) — không bypass.~~
- ~~AI Generation kịch bản đa cột + streaming SSE (§03, §06); framework AIDA/PAS.~~
- Màn Script Studio (§06 màn ③): editor 2 cột (VẪN CÒN, khớp shot list sau import), sửa
  Audio (VO) từng block, cảnh báo inline.
**Done:** ~~đi từ brief → outline → gate1 → kịch bản chi tiết, streaming mượt.~~

> **Đã build lại (2026-08-17, mục 44)**: AI Research/Outline/Hook Variants/Human Gate #1
> bỏ HẲN. Kịch bản CHỈ đến từ **import CSV/Excel** (`/script/import/parse` +
> `/script/import/confirm`, xem `03_api.md`) — nhảy thẳng vào Script Studio đã có `body`,
> không qua trạng thái "chờ duyệt outline/hook" nào.

### EPIC 8 — Retention Guardrail
- Hook Strength (rubric §07 mục 6) + Anchor Gap + brand-fit (§08).
- `/guardrail/check`; ghi `retention_check`; hiển thị inline ~~+ Pack Review~~.
- Nạp retention thủ công: form + `retention_entry` + thanh so sánh (§08 mục 6, ~~màn
  ⑥~~ nay ở Cài đặt kênh).
**Done:** check chạy, cảnh báo phân cấp màu; nhập & đối chiếu retention.

> **Đã build lại (2026-08-17, mục 44)**: guardrail vẫn chạy (`retention_check` gắn ngay
> lúc `/script/import/confirm`, không đổi công thức đo — chỉ đổi thời điểm/nguồn kịch
> bản), nhưng KHÔNG còn hiển thị ở Pack Review (đã xoá màn đó) — chỉ còn cảnh báo inline
> ở Script Studio.

### EPIC 9 — Production Pack & Gate #2
- ~~Shot Prompt Builder (§07 mục 4) + Title/Thumbnail Concepts (§07 mục 5).~~
- ~~Assembly Pack đầy đủ (§04); màn Pack Review (§06 màn ④).~~
- ~~**Human Gate #2** approve/return; return → về gate1, tăng version.~~
**Done:** ~~Pack hoàn chỉnh, duyệt/trả về hoạt động, khoá Output tới khi approve.~~

> **Đã build lại (2026-08-17, mục 44)**: bỏ HẲN — không còn màn Pack Review, không còn
> Gate #2, không còn sinh Title/Description/Hashtags/Chapters bằng AI (`YoutubeMeta` chỉ
> còn `thumbnail_description` chỉnh tay — thumbnail thật đã có ở Visual Studio, mục 36).
> Shot Prompt Builder VẪN CÒN nhưng chuyển hẳn sang thuộc **Visual Studio** (EPIC M2, xem
> `/visual/generate`), không phải 1 bước riêng trước Gate #2 như ý định gốc. `Output/
> enter` giờ không cần điều kiện gì ngoài đã ở Visual Studio.

### EPIC 10 — Output: Export
- `/export` sinh Markdown/PDF/JSON từ Pack (§04 mục 4); màn Output Center (§06 màn ⑦).
- Thẻ "Render in-app" hiện nhãn Beta, disabled — **đã build thật ở M2** (xem dưới), không
  còn disabled.
**Done:** export ra file người-đọc + JSON, tải được.

### EPIC 11 — Polish UX
- Auto-save + version im lặng, phím tắt, optimistic UI, trạng thái rỗng có hướng dẫn, cảnh báo phân cấp màu (§06 mục 5).
- Modal xác nhận thao tác phá huỷ + Audit Log.
**Done:** đạt ngưỡng hiệu năng UX (<100ms optimistic, streaming <2s).

---

## MỐC SAU — CHƯA BUILD (giữ ranh giới)

### M2 — Production Layer (Beta)

> **Đã build 1 phần (2026-08-12, cập nhật):** thực thi thật 6 provider — **ElevenLabs**
> + **Gemini TTS** (TTS), **OpenAI Image** + **Gemini Image** (ảnh), **Sora** +
> **Google Veo** (video) — mỗi task có provider mặc định + **fallback THẬT** (tự động
> thử provider dự phòng khi provider mặc định gọi API lỗi, xem `specs/05` §8c). Sinh
> asset đã CHUYỂN sang **Visual Studio** (bước ②) theo phản hồi người dùng — không còn
> chờ tới Output Center; Render Studio giờ CHỈ còn ghép MP4. **Cập nhật 2026-08-17 (mục
> 44):** Gate #2 đã bỏ HẲN — ghép MP4 dùng được ngay từ Visual Studio, chỉ cần MỌI shot
> `visual_status=="ready"` và `approved=True` (kiểm trực tiếp trên `render.json`, không
> còn liên quan `project.status`/Gate nào). **Cập nhật thêm (mục 45):** video lệch độ dài
> so với slot kịch bản (hay gặp khi upload tay) không còn bị loop/cắt cứng — phát đủ độ
> dài thật, bù/trừ chênh lệch qua thời lượng hiển thị ảnh của shot liền kề. Module
> `backend/app/render/` vẫn tách biệt hoàn toàn script core
> (chỉ đọc `pack.json`, trạng thái riêng ở `render.json`). Chi phí ghi vào AuditLog/
> Budget như LLM (màn 💳 hiện đúng tổng, CHƯA tách theo loại tts/image/video — giới
> hạn đã biết). Chi tiết: `IMPLEMENTATION_REPORT.md`, `specs/05_ai_providers.md` §8c.
>
> **Chưa build:** provider còn lại (Vbee, Flux, Midjourney, Runway) vẫn chỉ khai báo
> interface; fallback thật cho `llm` (chỉ `tts`/`image`/`video` có); giới hạn số shot
> cho `/render` (đang cho phép bất kỳ số lượng); UI chọn thời lượng clip video thủ
> công (đang tự tính từ `end_sec - timestamp_sec` của beat, clamp 4-20s).
>
> **Cập nhật thêm (2026-08-20, mục 51-53 IMPLEMENTATION_REPORT.md):** video/audio
> thương hiệu cấp kênh + shot mở đầu riêng project (override, mục 51); render/transcript
> dùng độ dài giọng đọc THẬT thay vì timestamp kịch bản tham khảo (mục 52); nhạc nền cấp
> kênh + override riêng project, trộn qua `amix` làm bước hậu kỳ cuối (mục 53); Thư viện
> Creative Asset (`/library`, màn `Library.tsx`, sidebar icon 📚) — asset dùng lại được ở
> mọi nơi upload media trong app, không cần chọn lại từ máy mỗi lần.

- Thực thi adapter TTS/Image/Video; sinh asset thật.
- `/render`: ghép MP4 "đủ đăng", giới hạn số shot; human review asset trước ghép.
- Module render **tách biệt** script core, chỉ đọc `pack.json`.
- Chi phí render vào màn 💳 (đã có sẵn).

### M3 — Scale & Repurpose (GA)
- Repurposing Pack: short-form marks + Community Post/poll (mở khối `repurpose` trong schema).
- Kanban hàng đợi đa kênh.

> **Đã build TRƯỚC (2026-08-21, mục 58 IMPLEMENTATION_REPORT.md) — KHÁC hẳn Repurposing
> Pack ở trên:** Short-form sub-project (9:16, YouTube Shorts/TikTok) — project ĐỘC LẬP
> nội dung, tự đi qua đúng luồng Brief→Script Studio→Visual Studio→Output như long-form
> (KHÔNG tự động cắt/tóm tắt lại nội dung long-form bằng AI, KHÔNG dùng khối
> `repurpose`/`shortform_marks` trong `pack.json`), chỉ lồng hiển thị dưới 1 project
> long-form CÙNG kênh để nhóm (Sidebar/Dashboard) và khác tỷ lệ khung sinh ảnh/video
> (9:16 thay 16:9). Repurposing Pack thật (tự động rút trích từ long-form) VẪN CÒN nằm
> ở M3, chưa build.

### M4 — Intelligence Loop (Post-GA)
- Tích hợp YouTube Analytics API thay nạp tay (§08 mục 7).
- Tinh chỉnh gợi ý Hook/cấu trúc theo dữ liệu tích lũy.

---

## Ràng buộc xuyên suốt (mọi epic)
- Single-user, không RBAC.
- Provider thay thế được; không hardcode tên provider trong business logic.
- `04_data_schemas.md` là nguồn sự thật; đổi schema cập nhật file đó trước.
- Chống coupling: script core ⟂ render module.
