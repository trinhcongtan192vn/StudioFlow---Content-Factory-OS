# CLAUDE.md — StudioFlow

> File này là điểm vào cho Claude Code. Đọc file này trước, rồi đọc các spec liên quan trong `specs/` theo nhiệm vụ đang làm.

## Sản phẩm là gì

StudioFlow là **desktop app single-user** giúp một người vận hành nhiều kênh YouTube long-form tiếng Việt: biến brief + dữ liệu thô thành một **Production Pack** chuẩn hoá (kịch bản đa cột + shot list + prompt AI + title/thumbnail concept). AI làm phần tổng hợp & viết; con người kiểm soát chất lượng tại **2 human-gate bắt buộc**.

**Nguyên tắc lõi:**
1. **Production Pack (JSON) là artifact trung tâm** — mọi downstream chỉ đọc schema, không đọc file người-đọc.
2. **Ưu tiên số 1 là chất lượng kịch bản/retention** — mọi đánh đổi nghiêng về phía này.
3. **Không bao giờ có nút "generate all"** — 2 gate không được bypass.
4. **Provider AI thay thế được** — cloud (Claude/Gemini/OpenAI…) và local (Qwen/DeepSeek/Kimi qua GPU) đều là plugin sau một interface chung.
5. **Single-user, không RBAC** — không phân quyền nhiều người.

## Stack (đã chốt)

| Lớp | Công nghệ | Lý do |
|---|---|---|
| Desktop shell | Electron | Chạy local tại máy có GPU; dữ liệu không rời máy. |
| Frontend | React + TypeScript + Tailwind | UI nghiệp vụ, nhiều state. |
| Backend | Python + FastAPI | Hệ sinh thái AI local (Ollama/vLLM, torch). |
| DB | SQLite (qua SQLAlchemy) | Single-user, local, không cần server. |
| AI local runtime | Ollama / OpenAI-compatible endpoint | Chạy model open-source trên GPU. |

## Bản đồ tài liệu (`specs/`)

| File | Nội dung | Đọc khi |
|---|---|---|
| `01_architecture.md` | Kiến trúc tổng thể, luồng process, cây thư mục. | Bắt đầu bất kỳ việc gì. |
| `02_database.md` | Schema SQLite, bảng, quan hệ, migration. | Làm model/DB. |
| `03_api.md` | REST API contract giữa Electron/React và FastAPI. | Làm endpoint hoặc gọi API. |
| `04_data_schemas.md` | JSON schema của BrandProfile & ProductionPack (hợp đồng dữ liệu). | Bất kỳ chỗ nào đọc/ghi Pack. |
| `05_ai_providers.md` | Interface provider AI, adapter cloud + local, cấu hình. | Làm tích hợp AI. |
| `06_uiux.md` | Bố cục màn hình, component, nguyên tắc tương tác. | Làm frontend. |
| `07_prompt_templates.md` | Prompt cho từng agent + rubric chấm Hook. | Làm pipeline AI/prompt. |
| `08_retention_guardrail.md` | Công thức đo Hook Strength & Anchor Gap. | Làm guardrail/nạp retention. |
| `09_sprint_tasks.md` | Epic & thứ tự triển khai theo mốc. | Lập kế hoạch, chia việc. |

## Quy ước làm việc

- **Ngôn ngữ code:** comment/tài liệu tiếng Việt hoặc Anh đều được; tên biến/hàm tiếng Anh.
- **Hợp đồng dữ liệu:** `04_data_schemas.md` là nguồn sự thật. Đổi schema phải cập nhật file này trước.
- **Scope:** chỉ build phần thuộc **M1 (MVP)** trừ khi được yêu cầu khác. Xem cột scope trong `09_sprint_tasks.md`.
- **Không over-engineer:** đây là single-user local app, không cần auth phức tạp, không multi-tenant.

## Phạm vi MVP (M1) tóm tắt

Trong: Channel & BrandProfile · Brief intake 4 nhóm · Script Studio (Research → Gate #1 → Generation) · Hook Variants (3 kiểu, không điểm) · Retention Guardrail (cảnh báo) · Production Pack + Prompt Builder · Gate #2 · Export Pack · **toàn bộ khu Cài đặt admin** · nạp retention thủ công.

Ngoài (mốc sau): in-app render (M2) · repurposing (M3) · correlation tự động/YouTube API (M4).
