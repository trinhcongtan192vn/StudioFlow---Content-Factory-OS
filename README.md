# StudioFlow — Bộ Spec cho Claude Code

Bộ tài liệu này bóc tách từ PRD StudioFlow (Content Factory OS single-user cho media house đa kênh YouTube) thành các spec riêng để đưa vào Claude Code build.

## Cách dùng với Claude Code

1. Đặt cả thư mục này ở gốc repo (hoặc trong `docs/`).
2. Claude Code đọc **`CLAUDE.md`** trước — đó là điểm vào, tóm tắt sản phẩm + stack + bản đồ tài liệu.
3. Mỗi phiên làm việc, chỉ Claude Code tới spec liên quan (ví dụ "build EPIC 7 theo `specs/07` và `specs/03`").
4. Build theo thứ tự epic trong `specs/09_sprint_tasks.md` — **chỉ M1 (MVP)**.

## Cấu trúc

```
studioflow-specs/
├── CLAUDE.md                       # ĐỌC TRƯỚC — điểm vào
├── README.md                       # file này
└── specs/
    ├── 01_architecture.md          # kiến trúc, stack, cây thư mục
    ├── 02_database.md              # SQLite schema
    ├── 03_api.md                   # REST API contract
    ├── 04_data_schemas.md          # JSON: BrandProfile & ProductionPack (nguồn sự thật)
    ├── 05_ai_providers.md          # adapter cloud + local (GPU)
    ├── 06_uiux.md                  # màn hình, component, tương tác
    ├── 07_prompt_templates.md      # prompt các agent + rubric Hook
    ├── 08_retention_guardrail.md   # công thức đo + nạp retention
    └── 09_sprint_tasks.md          # epic theo mốc
```

## Quyết định kỹ thuật đã chốt

- **Stack:** Electron + React/TS + Python FastAPI + SQLite. Python backend để chạy model AI local trên GPU.
- **AI local:** Qwen/DeepSeek/Kimi qua endpoint OpenAI-compatible (Ollama/vLLM/LM Studio).
- **Single-user, không RBAC.**
- **Phạm vi build:** M1 (MVP) — bao gồm toàn bộ khu Cài đặt admin + nạp retention thủ công.

## Nguyên tắc bất biến

1. Production Pack (JSON) là artifact trung tâm; export là view sinh từ nó.
2. Ưu tiên chất lượng kịch bản/retention.
3. 2 human-gate bắt buộc, không "generate all".
4. Provider AI thay thế được sau interface chung.
5. Script core tách khỏi render module (chống coupling).

## Trạng thái build

M1 (MVP) đã được build theo design Nocturne (`StudioFlow Prototype.dc.html`) và đã verify chạy end-to-end (Electron → FastAPI → SQLite → React). Chi tiết quyết định triển khai, lệch so với specs và lý do: xem **`IMPLEMENTATION_REPORT.md`** ở gốc repo.

### Chạy dự án (dev)

Yêu cầu: Node.js 18+, Python 3.11+. Muốn dùng **Render Studio** (M2 — ghép MP4 từ asset đã sinh) cần cài thêm **ffmpeg** và có sẵn trên `PATH` (`ffmpeg -version` chạy được từ terminal) — không bắt buộc cho phần còn lại của app.

```bash
# 1. Backend (tạo venv lần đầu, seed dữ liệu demo tự động)
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # .venv/bin/pip trên macOS/Linux
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8756

# 2. Frontend (terminal khác)
cd frontend
npm install
npm run dev   # http://localhost:5173

# 3. Electron (terminal khác, sau khi backend + frontend đã chạy)
npm install   # ở gốc repo — cài luôn frontend + electron qua npm workspaces
cd electron
npm run build
cd ..
node_modules/.bin/electron electron/dist/main.js
```

Electron tự spawn thêm 1 tiến trình backend riêng (cổng ngẫu nhiên) khi mở app — không cần bước 1 nếu chỉ chạy qua Electron, bước 1 chỉ cần khi muốn gọi thẳng API để dev/debug backend độc lập.

App **không** tự seed provider AI mặc định — vào **Cài đặt → Provider AI → "+ Thêm provider"** để kết nối Claude/GPT/Gemini (Cloud API) hoặc model local GPU (Local Endpoint, Ollama/vLLM) trước khi dùng bất kỳ tính năng cần AI nào; thiếu provider sẽ hiện cảnh báo rõ ràng thay vì âm thầm dùng nội dung giả lập (xem `specs/05_ai_providers.md` §8b).

**M2 — Render Studio** (Output Center → "Render in-app"): sinh ảnh/video/giọng đọc **thật**, tốn phí API thật (ElevenLabs cho TTS, OpenAI Image cho ảnh, Sora cho video) — cấu hình đủ 3 provider này (task `tts`/`image`/`video`) trước khi bấm "Bắt đầu sinh asset". Danh sách provider TTS/Image/Video khác (Vbee, Flux, Midjourney, Runway, Veo, Gemini TTS/Image) mới chỉ khai báo interface, chưa thực thi thật.
