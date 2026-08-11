# 01 — Kiến trúc

## 1. Tổng quan

StudioFlow là desktop app 3 lớp chạy hoàn toàn tại máy người dùng:

```
┌─────────────────────────────────────────────┐
│  Electron (main process)                     │
│   - Cửa sổ app, menu, lifecycle              │
│   - Spawn & quản lý FastAPI backend (child)  │
└───────────────┬─────────────────────────────┘
                │ HTTP (localhost)
┌───────────────▼─────────────────────────────┐
│  React + TypeScript (renderer)               │
│   - UI nghiệp vụ (§06_uiux)                  │
│   - Gọi REST API (§03_api)                   │
└───────────────┬─────────────────────────────┘
                │ REST (http://127.0.0.1:PORT)
┌───────────────▼─────────────────────────────┐
│  FastAPI (Python backend)                    │
│   - Business logic, pipeline AI              │
│   - Provider adapters (§05)                  │
│   - SQLite qua SQLAlchemy (§02)              │
└───────────────┬─────────────────────────────┘
                │
        ┌───────┴────────┬─────────────────┐
        ▼                ▼                 ▼
   SQLite file     Cloud AI APIs     Local AI (GPU)
   (index)         (Claude/Gemini)   (Ollama/vLLM)
```

## 2. Vì sao stack này

- **Python backend bắt buộc** để tích hợp model local trên GPU: Ollama, vLLM, torch, faster-whisper (mốc sau) sống trong hệ Python. Node không phải nơi cho AI local.
- **Electron** cho desktop chạy tại máy có GPU, dữ liệu nhạy cảm (tài liệu nội bộ, brief) không rời máy — khớp lý do dùng local model trong PRD §10.2b.
- **SQLite** đủ cho single-user; là **index/metadata store**, không phải nơi giữ file nặng.

## 3. File-as-source-of-truth

- **Artifact nội dung** (ProductionPack JSON, bản export Markdown/PDF, asset) lưu dạng **file trên đĩa** trong thư mục workspace.
- **SQLite** giữ index: danh sách Channel/Project, trạng thái, con trỏ tới file, lịch sử version, cấu hình.
- Lý do: JSON/file version-control dễ, người dùng có thể backup/copy thủ công, và Pack là thứ di chuyển được giữa các máy.

## 4. Cây thư mục dự án

```
studioflow/
├── CLAUDE.md
├── specs/                      # bộ tài liệu này
├── electron/                   # Electron main process
│   ├── main.ts
│   └── backend-launcher.ts     # spawn FastAPI
├── frontend/                   # React app
│   ├── src/
│   │   ├── screens/            # theo §06_uiux
│   │   ├── components/
│   │   ├── api/                # client gọi REST
│   │   └── store/              # state
│   └── package.json
├── backend/                    # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/            # theo §03_api
│   │   ├── models/             # SQLAlchemy (§02)
│   │   ├── schemas/            # Pydantic = JSON schema (§04)
│   │   ├── providers/          # adapter AI (§05)
│   │   ├── pipeline/           # agent research/script (§07)
│   │   └── guardrail/          # retention (§08)
│   └── requirements.txt
└── workspace/                  # dữ liệu người dùng (file-as-source)
    ├── studioflow.db           # SQLite index
    └── channels/<id>/projects/<id>/pack.json
```

## 5. Data workspace layout (trên đĩa)

```
workspace/
├── studioflow.db
└── channels/
    └── ch_finance_01/
        ├── brandprofile.json          # bản hiện hành
        ├── brandprofile.v{n}.json     # các version cũ
        └── projects/
            └── prj_2026_0142/
                ├── brief.json
                ├── pack.json          # ProductionPack (§04)
                ├── pack.v{n}.json
                ├── exports/           # Markdown/PDF sinh từ pack
                └── retention.json     # số liệu nạp tay (§08)
```

## 6. Nguyên tắc tách module (chống coupling)

- **Script core** (pipeline + guardrail) **độc lập** với **render module** (M2). Render chỉ đọc `pack.json`, không gọi ngược vào pipeline.
- **Provider layer** ẩn sau interface chung (§05) — pipeline không biết đang gọi Claude hay Qwen local.
- Đổi provider/model **không đụng** business logic.

## 7. Vòng đời & process

1. Electron khởi động → spawn FastAPI ở cổng localhost ngẫu nhiên → chờ health-check `/health`.
2. React nạp, đọc cấu hình từ backend.
3. Nếu **chưa cấu hình Provider AI nào** → chặn tuyến sản xuất, điều hướng tới màn Provider AI (§06).
4. Khi đóng app → Electron kill backend child process.

## 8. Yêu cầu phi chức năng (ràng buộc kỹ thuật)

- API key mã hoá at-rest (không lưu plaintext trong DB); local endpoint không cần key.
- Mọi thao tác admin quan trọng ghi Audit Log (§02 bảng `audit_log`).
- Hiệu năng UX: thao tác optimistic < 100ms; streaming AI hiện chữ < 2s (§06).
- Toàn bộ chạy offline được, trừ khi gọi cloud provider.
