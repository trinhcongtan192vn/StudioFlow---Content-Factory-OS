# Implementation Report — StudioFlow M1 (MVP)

Ngày build: 2026-08-11. Nguồn thiết kế: Claude Design project "UI UX prototype cho PRD" (`StudioFlow Prototype.dc.html`, design system Nocturne). Nguồn nghiệp vụ: `CLAUDE.md` + `specs/*.md` + `specs/StudioFlow_PRD.md`.

Nguyên tắc thực thi theo đúng 4 yêu cầu đã nhận:
1. Build đúng design Nocturne — màu, spacing, component, layout port trực tiếp từ `styles.css` của design.
2. Khi design ≠ specs → ưu tiên design, cập nhật specs cho khớp thực tế (xem mục 2 và các file `specs/*.md` đã sửa).
3. Khi cần quyết định mà không có nguồn nào nói rõ → tự quyết định, ghi lại ở mục 3.
4. Model local (GPU) — code kiến trúc sẵn sàng, KHÔNG thực thi/test

 thật vì máy dev không có GPU (mục 5).

---

## 0. Trạng thái & cách chạy

Đã build và **verify chạy thật end-to-end** (không chỉ đọc code):
- Backend: `cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8756` — đã test toàn bộ luồng Brief → Research → Gate1 → Script → Visual → Pack Build → Gate2 → Export qua HTTP thật (script test bằng `httpx`, xem lịch sử phiên làm việc).
- Frontend: `cd frontend && npm install && npm run dev` (Vite, cổng 5173) — `tsc -b` và `npm run build` đều pass sạch.
- Electron: `npm install` ở gốc repo (workspaces hoist `electron`/`frontend`), rồi `node_modules/.bin/electron electron/dist/main.js` (sau khi `cd electron && npm run build`) — **đã chạy thật**: Electron tự chọn cổng trống, spawn backend Python, chờ `/health`, mở cửa sổ, load React app; React app gọi `/bootstrap` và `/channels` thành công (log xác nhận trong phiên build).
- Chạy cả 3 cùng lúc (dev): `npm run dev:backend` (root), `npm run dev:frontend` (root), rồi `npm run dev --workspace=electron`.

Dữ liệu demo được seed tự động lần đầu chạy (`backend/app/seed.py`): 3 kênh mẫu (Sử Việt Kể, Tiền Khôn, Tâm Lý Học Đời Thường) + 1 project draft/kênh + thư viện Prompt Templates + 1 provider LLM Mock mặc định (chạy được ngay, không cần API key).

---

## 1. Kiến trúc đã build

```
studio-flow/
├── backend/            FastAPI + SQLAlchemy + Pydantic (Python)
│   └── app/
│       ├── models/       SQLAlchemy — bảng theo specs/02, xem mục 2
│       ├── schemas/      Pydantic — BrandProfile/Brief/ProductionPack, xem mục 2
│       ├── providers/    LLMProvider ABC + Claude/OpenAI/Gemini/LocalOpenAICompat/Mock + TTS/Image/Video stub
│       ├── pipeline/     generation.py (orchestrator) + fallback_content.py (dự phòng khi JSON parse lỗi)
│       ├── guardrail/    check.py — Hook Strength, Anchor Gap, brand-fit
│       ├── routers/      1 file/nhóm endpoint, khớp specs/03 (đã cập nhật)
│       ├── seed.py, filestore.py, crypto.py, config.py, db.py, main.py
├── frontend/           React 18 + TypeScript + Vite, CSS thuần port từ Nocturne (không dùng Tailwind — xem mục 3.1)
│   └── src/
│       ├── styles/nocturne.css   token + component classes, 1:1 từ design + biến còn thiếu (mục 3.4)
│       ├── api/          client.ts (fetch wrapper) + types.ts
│       ├── store/         AppContext.tsx — nav state (view/channel/project/sidebar/panel)
│       ├── components/    Sidebar, Stepper, RightPanel, statusMeta
│       └── screens/
│           ├── Dashboard.tsx, ProjectView.tsx
│           ├── steps/     BriefEditor, Gate1Outline, ScriptStudio, VisualStudio, PackReview, OutputCenter
│           └── settings/  SettingsShell + General/Provider/Billing/AIParams/PromptTemplates/AuditLog/AppBranding
├── electron/           main.ts (spawn backend, mở cửa sổ) + backend-launcher.ts + preload.ts
├── workspace/           file-as-source-of-truth (channels/, projects/, pack.json, brief.json...)
└── specs/               đã cập nhật — xem mục 2
```

---

## 2. Lệch giữa design và specs — đã ưu tiên design (nguyên tắc #2)

Đầy đủ chi tiết đã ghi trực tiếp vào từng file `specs/*.md` liên quan (tìm block `> **Đã build`). Tóm tắt:

| # | Lệch | Quyết định | File specs đã cập nhật |
|---|---|---|---|
| 1 | Flow 6 bước (Brief → Outline&Hook → Script Studio → **Visual Studio** → Pack Review → Output) thay vì luồng "AI Generation" gộp 1 bước trong PRD/specs | Theo design. Research + Hook Variants gộp UX 1 bước dù backend vẫn 2 hàm riêng | `06_uiux.md` §1–2, `03_api.md`, `09_sprint_tasks.md` |
| 2 | `conversion_point` enum: design chỉ có `none/affiliate/course/private_traffic` (bỏ `email_list`, gộp `zalo_group`→`private_traffic`) | Theo design | `04_data_schemas.md` |
| 3 | `Brief.raw_knowledge.documents`: design có upload file/link YouTube với trạng thái trích xuất, spec gốc chỉ là `list[string]` | Theo design, mở schema thành `list[BriefSource]` | `04_data_schemas.md`, `03_api.md` |
| 4 | Pack Review có tab "Repurposing" hiển thị placeholder "Có ở M3" — không có trong đặc tả UI gốc | Theo design (giữ nguyên nguyên tắc `repurpose: null` ở M1) | không cần đổi schema, chỉ UI |
| 5 | `budget` gắn theo **kênh**, không phải theo project như bảng DB gốc; thêm `threshold_pct` | Theo design (màn Chi phí & Ngân sách nhóm theo kênh) | `02_database.md` |
| 6 | `prompt_template`: design cần lịch sử nhiều version/1 template, đặt version mặc định | Tách 2 bảng `prompt_template` + `prompt_template_version` | `02_database.md` |
| 7 | Nội dung/placeholder Prompt Templates: design có 9 template cụ thể với vocabulary riêng (`{{topic}}`, `{{current_script}}`...) khác `07_prompt_templates.md` gốc | Seed đúng theo design, giữ file gốc làm tài liệu ý định + bảng ánh xạ | `07_prompt_templates.md` |
| 8 | Gate #2 "Trả về" đưa thẳng về Script Studio (step 2), không phải Outline&Hook (step 1) như enum gợi ý | Theo design; enum Project dùng lại `generating` cho quãng này (không thêm state mới) | `02_database.md` §2, §3 |
| 9 | Visual Studio: 1 shot = 1 beat, gồm cả prompt hình/video LẪN mô tả cảm xúc TTS cùng lúc | Theo design; mở schema `Shot` thêm `tts_emotion`, `visual_type` | `04_data_schemas.md` |
| 10 | Pack Review tab "Title & Thumbnail" có thêm Description SEO, Chapters, Hashtags — rộng hơn `titles`/`thumbnail_concepts` gốc | Theo design; thêm khối `youtube_meta` mới vào ProductionPack | `04_data_schemas.md` |

---

## 3. Quyết định tự chủ động (không rõ trong design lẫn specs)

### 3.1 Không dùng Tailwind cho frontend
`CLAUDE.md` liệt kê "React + TypeScript + Tailwind" là stack đã chốt, nhưng design Nocturne là **plain CSS classes trên plain HTML** (`.btn`, `.card`, `.field`...), không phải utility-class Tailwind. Build lại đúng hệ thống đó bằng Tailwind sẽ tốn công dịch ngược token → utility mà không thêm giá trị, và dễ trôi khỏi 1:1 pixel-parity với design. Quyết định: **port thẳng `styles.css` của Nocturne** làm CSS thuần, dùng React chỉ để quản lý state/DOM, bỏ qua Tailwind. Đánh đổi được chấp nhận vì mục tiêu #1 là khớp design.

### 3.2 Provider Mock mặc định
Không có hướng dẫn nào về việc app nên xử lý ra sao khi chưa có provider AI thật (spec nói phải "chặn tuyến sản xuất"). Quyết định: **vẫn tôn trọng nguyên tắc chặn** (banner "Cần cấu hình Provider AI" hiện khi `has_llm_provider=false`), nhưng seed sẵn 1 provider LLM Mock (`app/providers/mock.py`) làm mặc định để app **demo được ngay** mà không cần key/GPU — implement đúng interface `LLMProvider` như mọi adapter khác, không phải hack tắt riêng.

### 3.3 Nội dung dự phòng khi provider trả JSON không hợp lệ
Prompt templates yêu cầu LLM trả JSON thuần (§07 nguyên tắc chung), nhưng không có model thật lúc build nên không thể verify parse JSON thật 100%. Quyết định: mọi bước pipeline (`app/pipeline/generation.py`) có **fallback content generator** (`fallback_content.py`) — nếu parse JSON lỗi hoặc provider lỗi/timeout, dùng nội dung dự phòng bám theo `topic`/`insight` của Brief thay vì crash giữa luồng. Đây cũng là lớp an toàn chung cho provider thật khi model trả sai định dạng.

### 3.4 Biến CSS còn thiếu trong design
`StudioFlow Prototype.dc.html` tham chiếu `var(--brief-amber-bg)` và `var(--brief-amber-text)` (chip "cần bổ sung" trong Brief Editor) nhưng `styles.css` của Nocturne **không khai báo hai biến này** — lỗi/thiếu sót trong chính bản design gốc. Quyết định: bổ sung 2 biến đó + `--color-warning`, `--color-danger`, `--color-danger-bg` (suy ra từ các màu hardcode `#d9a441`/`#d96157` đã dùng rải rác trong chính file design cho cảnh báo/xoá) vào `nocturne.css`, giữ đúng tinh thần màu của hệ thống.

### 3.5 Đặt Retention Nhập tay trong Output Center thay vì màn riêng
Xem mục 2 bảng dòng liên quan (⑧) — không có màn riêng trong design, và thêm 1 bước stepper thứ 7 sẽ phá cấu trúc 6 bước cố định của design. Đặt làm card trong Output Center vì đây là bước "sau khi đã export/đăng", đúng ngữ cảnh nghiệp vụ nhất.

### 3.6 Export "PDF" là văn bản thuần, chưa phải PDF render layout thật
Không có thư viện render PDF nào được chỉ định. Dựng pipeline PDF đẹp (WeasyPrint/wkhtmltopdf) là công sức đáng kể ngoài phạm vi "chất lượng kịch bản/retention" — ưu tiên số 1 theo `CLAUDE.md`. Quyết định: `format=pdf` hiện xuất file `.pdf` chứa văn bản thuần (giống `.md`) — **giới hạn đã biết**, xem mục 4.

### 3.7 Đơn giản hoá kéo-thả sắp xếp project trong sidebar
Design có `onDragStart/onDragOver/onDrop` để kéo-thả đổi thứ tự project trong 1 kênh. Đây là polish UX không ảnh hưởng nghiệp vụ lõi; quyết định **bỏ qua ở bản build này** để ưu tiên thời gian cho pipeline/gate/guardrail (đúng nguyên tắc "không over-engineer" + ưu tiên chất lượng kịch bản). Ghi vào mục 4 như hạng mục để sau.

### 3.8 Audit log "user" luôn là "Bạn"
Design có mock nhiều tên người dùng khác nhau (Hải Yến, Minh Anh...) cho từng dòng audit log — nhưng sản phẩm single-user, không RBAC (`CLAUDE.md`, PRD §2). Quyết định: mọi hành động ghi log với `user: "Bạn"`, chỉ trường `updated_by` của Prompt Template version giữ dạng text tự do (không phải danh sách người dùng thật) để không bịa ra một hệ thống nhiều người dùng không tồn tại.

---

## 4. Giới hạn đã biết / để sau (không phải bug, ghi nhận có chủ đích)

- **Streaming SSE cho AI Generation** (`03_api.md` gốc yêu cầu) — chưa build; các lệnh gọi AI hiện đồng bộ. Cần khi tích hợp model cloud lớn cho kịch bản dài (>10-15s response).
- **Ghi log chi phí tự động theo từng lệnh gọi AI** — `Budget.spent`/`AuditLog(type='expense')` có schema sẵn sàng nhưng chưa được pipeline tự động cập nhật sau mỗi lệnh gọi provider thật (cần propagate `LLMResult.estimated_cost_usd` từ `pipeline/generation.py` ra tới router để ghi log — việc nối dây, không phải thiết kế lại).
- **Kéo-thả sắp xếp project trong sidebar** — có trong design, chưa build (mục 3.7).
- **Trích xuất transcript YouTube thật / parse PDF-Word thật** cho nguồn tham khảo Brief — hiện chỉ lưu placeholder (đếm ký tự với file text, lưu link thô với YouTube). Cần tích hợp thư viện/API riêng (mốc sau).
- **Export "PDF"** là text thuần, chưa phải PDF layout thật (mục 3.6).
- **Render in-app (Output B)** — đúng theo spec, chưa build ở M1, thẻ hiện "Beta · M2" disabled.
- **Repurposing Pack** — đúng theo spec, để `null`, UI hiện placeholder "Có ở M3".

## 5. Model local / GPU-ready (yêu cầu #4)

Chưa chạy thật (máy dev không có GPU) nhưng kiến trúc đã sẵn sàng:
- `backend/app/providers/local_openai_compat.py` — `LocalOpenAICompatProvider` implement đầy đủ interface `LLMProvider`, gọi chuẩn OpenAI-compatible (`POST {base_url}/chat/completions`) — dùng được ngay cho Ollama/vLLM/LM Studio, chỉ cần đổi `base_url`/`model`.
- Màn Provider AI (Settings → Provider AI → "+ Thêm provider") có sẵn form chọn `Local Endpoint`, nhập URL + tên model — không cần sửa code khi người dùng có GPU, chỉ cần thêm provider và đặt làm mặc định cho task `llm`.
- Factory (`app/providers/factory.py`) chọn provider hoàn toàn qua `provider_config.is_default`/`connection_type` — pipeline không biết (và không cần biết) đang chạy cloud hay local.

## 7. Cập nhật sau phản hồi test thủ công (2026-08-11, vòng 2)

Người dùng test app thật và báo thiếu 5 hạng mục so với prototype. Đã xử lý:

1. **Sửa BrandProfile từ Dashboard** — trước đó chỉ tạo được kênh mới (Sidebar), không sửa được. Tách logic thành `components/ChannelDialog.tsx` dùng chung cho cả 2 luồng (create ở Sidebar, edit qua icon bút chì trên card kênh ở Dashboard) — đầy đủ field brand voice/pillars/taboos/retention benchmark như design, không chỉ name/niche.
2. **Thêm link YouTube ở Brief không có phản hồi** — nguyên nhân là lỗi thật: endpoint `/projects/{id}/brief/sources` nhận `youtube_url` như query param thay vì multipart form field (thiếu khai báo `Form(...)` trong FastAPI khi route đã có `UploadFile`), nên mọi request đều rơi vào nhánh lỗi 400 mà frontend không bắt exception → im lặng, không có gì xảy ra. Đã sửa cả 2 phía: backend dùng đúng `Form(None)`, frontend bắt lỗi và hiển thị thông báo. Đồng thời **implement trích xuất transcript YouTube thật** qua `youtube-transcript-api` (nâng lên bản 1.2.4, bản 0.6.2 lúc đầu bị YouTube chặn — xem code `app/youtube.py`) — đã test thật với video công khai, lấy được transcript, lưu file text cạnh `brief.json`, và nội dung này được đưa vào prompt AI Research (`{{brief}}` giờ có thêm nguồn transcript, không chỉ thông tin form nhập tay).
3. **Provider AI — model API lúc thêm** — dialog "+ Thêm provider" trước đó không cho chọn model ngay (chỉ nhận key, model mặc định gán ngầm ở backend). Đã thêm dropdown chọn model theo đúng danh mục provider (khớp `CLOUD_MODELS` backend) ngay trong bước thêm.
4. **Billing "Xem chi tiết"** — trước đó hoàn toàn chưa build (đã ghi ở mục 4 bản gốc là giới hạn biết trước). Đã đóng gói đầy đủ: `generation.py` giờ trả kèm usage (provider/model/token/cost) qua tham số `usage`, `routers/pipeline.py::record_usage` ghi vào `AuditLog(type=expense)` + cộng dồn `Budget.spent` sau MỌI lệnh gọi AI thật trong toàn bộ pipeline (research/hooks/script/breakdown/shots/titles/guardrail), endpoint mới `GET /budget/{channel_id}/detail` group theo project+provider kèm danh sách request, và màn Billing có nút "Xem chi tiết →" mở view giống prototype (bảng có thể mở rộng từng dòng). Đã test end-to-end.
5. **Prompt Templates — edit + gom nhóm** — trước đó chỉ tạo mới/xoá/thêm version, thiếu nút "Sửa" (đổi tên + đổi bước) và hiển thị dạng danh sách phẳng lọc theo stage key thay vì gom theo bước quy trình như prototype. Đã thêm dialog Sửa (dùng lại UI tạo mới, generalized create/edit) + gom nhóm theo 4 bước (Brief/Outline & Hook/Script Studio/Visual Studio) với filter tab theo bước; backend `PromptTemplatePatch` nhận thêm field `task` để đổi bước khi sửa.

## 8. Backend unit test suite (2026-08-11, vòng 3)

Trước vòng này, toàn bộ "test" chỉ là script `httpx` chạy tay + `tsc`/`vite build` — không có gì bảo vệ chống hồi quy. Đã bổ sung bộ test tự động bằng `pytest` + `fastapi.testclient.TestClient`, chạy trên workspace/DB tạm hoàn toàn cách ly khỏi `workspace/` thật (`backend/tests/conftest.py`), không cần mạng/API key thật (dùng provider Mock mặc định).

**Phạm vi (80 test, `backend/tests/`):**
- `test_health_bootstrap.py` — `/health`, `/bootstrap`.
- `test_channels.py` — CRUD kênh, BrandProfile get/put + version tăng đúng, lịch sử version, clone-from.
- `test_projects_brief.py` — CRUD project, guard chuyển step, brief get/put (trường thiếu không chặn), thêm nguồn file, thêm nguồn YouTube (mock `fetch_transcript_text` — thành công/lỗi trích xuất/URL không hợp lệ), gỡ nguồn.
- `test_pipeline_flow.py` — **luồng tích hợp đầy đủ** Brief→Research→Gate1→Script Studio (sửa tay + tạo lại theo góp ý + duyệt/bóc tách)→Visual Studio→Pack Review→Gate2 (trả về rồi duyệt lại)→Output/Export, cộng các guard 400 khi thiếu điều kiện.
- `test_guardrail.py` — unit test thuần cho `compute_anchor_gap`, `check_brand_fit`, `score_hook_strength` (parse JSON thành công / fallback heuristic khi provider lỗi / ghi usage), `run_guardrail_check` (đủ loại cảnh báo).
- `test_youtube_extract.py` — `extract_video_id` với nhiều định dạng URL YouTube hợp lệ/không hợp lệ (test thuần, không gọi mạng).
- `test_crypto.py` — roundtrip mã hoá/giải mã key + mask hiển thị.
- `test_providers.py` — CRUD provider, ràng buộc Local Endpoint chỉ cho LLM, đặt default (unset các provider khác), test_connection cho Mock (không cần mạng).
- `test_settings.py` — settings chung/ai_params/app_branding, Prompt Templates CRUD + versioning + đổi task, Audit Log + filter, Budget list/patch/detail (kèm 1 test chạy pipeline thật rồi kiểm tra ghi log chi phí đúng nhóm).

**2 lỗi thật được bộ test tìm ra ngay lần chạy đầu, đã sửa trong cùng vòng này:**
1. `pack.get("script", {}).get(...)` trong `routers/pipeline.py` (3 chỗ) và `routers/guardrail.py` (2 chỗ) crash `AttributeError` khi `pack["script"]` tồn tại nhưng có giá trị `None` (đúng trường hợp 1 project mới tạo) — `dict.get(key, default)` chỉ dùng default khi KEY VẮNG MẶT, không phải khi giá trị là `None`. Sửa thành `(pack.get("script") or {}).get(...)`. Ảnh hưởng: gọi `/visual/generate`, `/pack/build`, `/guardrail/check` trên project chưa có script sẽ lỗi 500 thay vì trả 400 rõ ràng.
2. Lỗi cách ly trong chính bộ test (không phải bug app): 1 test đổi provider LLM mặc định toàn cục rồi quên khôi phục, khiến test chạy sau âm thầm dùng fallback content thay vì provider Mock. Đã sửa + thêm fixture `autouse` khôi phục Mock làm default trước mỗi test, chống tái diễn.

**Chạy:** `cd backend && .venv/Scripts/python -m pytest tests/ -v` (Windows) — 80 passed, ~4s, không cần mạng.

**Chưa làm (để sau nếu cần):** test frontend (vitest/RTL — người dùng chọn ưu tiên backend trước), coverage report (`pytest-cov`), test cho các adapter cloud thật (Claude/GPT/Gemini/ElevenLabs...) vì cần key thật — hiện chỉ test được phần CRUD/metadata của provider, không test `complete()`/`test_connection()` thật của các adapter cloud.

## 9. Cập nhật vòng 4 (2026-08-12) — Nhập kịch bản CSV/Excel + header sticky

Design cập nhật thêm (đọc lại qua `claude_design` MCP, diff với bản trước — 524 dòng thay đổi trong `StudioFlow Prototype.dc.html`). 3 yêu cầu, đều đã build và verify end-to-end (pytest + smoke test HTTP thật):

### 9.1 Nút hành động chuyển lên header sticky

Cả 5 màn trong luồng project (Brief, Outline & Hook, Script Studio, Visual Studio, Pack Review) trước đó có nút hành động chính nằm CUỐI trang (phải cuộn xuống mới thấy). Design đổi sang **header dính (sticky) ở đầu canvas**, gồm tiêu đề + mô tả bên trái, nút hành động bên phải — luôn thấy được kể cả khi đã cuộn xuống đọc nội dung dài.

- Bổ sung component dùng chung `frontend/src/components/StepHeader.tsx` (không có trong design — design lặp lại y hệt đoạn CSS sticky ở cả 5 chỗ trong 1 file HTML, hợp lý cho 1 file .dc.html nhưng không hợp lý cho React component tách file; gom thành 1 component chung, cùng hành vi).
- **Sửa 1 chỗ mà chính design bỏ sót**: CSS sticky header trong file design KHÔNG đặt `background` — khi cuộn, card phía dưới sẽ lộ/đè qua chữ trong header. `StepHeader.tsx` thêm `background: var(--color-bg)` để header thật sự "dính" đúng nghĩa.
- Áp dụng cho: `BriefEditor`, `Gate1Outline`, `ScriptStudio`, `VisualStudio`, `PackReview`.

### 9.2 Nhập kịch bản từ CSV/Excel (6 trường)

Nút "Nhập kịch bản từ file (CSV/Excel)" đặt cạnh nút Duyệt Gate 1, cho phép **bỏ qua toàn bộ luồng AI** (chọn outline/hook + AI viết Full Script) khi đã có kịch bản viết sẵn — nhảy thẳng tới Script Studio ở trạng thái đã duyệt.

**6 cột bắt buộc** (khớp yêu cầu, tên cột nhận dạng theo từ khoá tiếng Việt, không phân biệt thứ tự cột): Mã block · Thời lượng · Loại Visual · Hình ảnh & Hiệu ứng (Visual/FX) · Âm thanh & Nhạc nền (Audio/SFX) · Kịch bản Giọng đọc (VO Content).

**Lệch so với design — quyết định đã ghi lại:**
- Design parse file bằng **SheetJS chạy phía client** (`xlsx.full.min.js` nạp qua CDN, ~800KB). Bản build **parse phía SERVER** (`backend/app/pipeline/script_import.py`, dùng `csv` chuẩn của Python cho CSV và `openpyxl` cho Excel). Lý do: (1) không phải tải thêm ~800KB JS vào bundle Electron mỗi lần mở app, (2) gom toàn bộ logic parse/validate vào 1 chỗ, test được bằng pytest (16 test mới, xem `tests/test_script_import.py`), (3) nhất quán với cách brief-sources đã xử lý file (cũng parse server-side).
- Flow 2 bước qua API: `POST /script/import/parse` (multipart file → trả preview: beats + stats, KHÔNG đụng Pack) rồi `POST /script/import/confirm` (JSON beats đã parse → ghi vào Pack, chạy guardrail, chuyển step). Giữ đúng UX 2 bước "xem trước → xác nhận" của design mà không cần re-upload file lần 2.
- Thêm `Script.source: "ai" | "import"` (không có trong design, tự quyết định) — đánh dấu nguồn gốc script để `/visual/generate` biết cách xử lý khác nhau (mục 9.3).
- Timestamp cột "Thời lượng" (vd. `"0:00–0:05"`) được parse ra `timestamp_sec`/`end_sec` số nguyên (giữ nhất quán với schema `ScriptBodyItem` đã có từ trước — số, không phải chuỗi hiển thị như design). Không đọc được → ước tính tuần tự (cộng dồn 8s/block) để không vỡ tính năng đo Anchor Gap.
- Cột "Âm thanh & Nhạc nền (Audio/SFX)" tái sử dụng field `direction` sẵn có trong `ScriptBodyItem`, kèm `direction_label` mới (mặc định `"Direction"`, đổi thành `"Audio/SFX"` khi tới từ import) — Script Studio hiển thị đúng tên cột theo nguồn gốc dữ liệu.
- **Anchor mặc định `false`** cho mọi block import (không suy luận/tự đánh dấu anchor giả) — script tự viết không có khái niệm "AI đánh dấu điểm neo cảm xúc"; đo Anchor Gap sẽ không cảnh báo với script import (giới hạn đã biết, ghi ở mục "để sau").

### 9.3 Script Studio & Visual Studio đổi giao diện theo luồng import mới

- **Script Studio**: mỗi block hiện thêm tag Mã block + Loại Visual nếu có; cột "Direction" đổi tên động theo `direction_label`; **bỏ panel "Hook đang dùng"** bên phải (không còn ý nghĩa khi script tới từ import, không qua chọn Hook) — layout 1 cột, `max-width: 900px`.
- **Visual Studio — đổi tên field + tách hành động**:
  - `Shot.prompt` → `Shot.visual_fx` ("Hình ảnh & Hiệu ứng — Visual/FX"), `Shot.tts_emotion` → `Shot.audio_sfx` ("Âm thanh & Nhạc nền — Audio/SFX") — khớp đúng tên 2 trong 6 cột import, vì giờ đây 1 shot có thể tới từ AI HOẶC từ import.
  - Nút "Tạo lại bằng AI" (1 nút, sinh cả 2 field cùng lúc) tách thành **2 nút riêng**: "Tạo lại Visual" (`POST /visual/shots/{id}/regenerate-visual`) và "Tạo lại giọng đọc" (`POST /visual/shots/{id}/regenerate-audio`) — dùng 2 hàm pipeline mới `regenerate_shot_visual_fx`/`regenerate_shot_audio_sfx`, mỗi hàm chỉ gọi AI sinh 1 field, không đụng field còn lại.
  - Thêm 2 nút hành động HÀNG LOẠT ở header: "Tạo Visual cho toàn bộ block" (`POST /visual/generate-all-visual`) và "Tạo giọng đọc (TTS) cho toàn bộ block" (`POST /visual/generate-all-tts`) — lặp qua tất cả shot, gọi AI riêng cho từng field.
  - **Quyết định tự chủ động quan trọng nhất vòng này**: khi `Script.source == "import"`, `POST /visual/generate` **KHÔNG gọi AI** — seed `visual_fx`/`audio_sfx` trực tiếp từ đúng nội dung cột Visual/FX và Audio/SFX người dùng đã viết trong file (`_seed_shot_from_beat` trong `pipeline.py`). Lý do: người dùng import kịch bản CHÍNH XÁC vì đã tự viết prompt/mô tả chi tiết — để AI "diễn giải lại" (paraphrase) sẽ phá nội dung đã chuẩn, ngược hoàn toàn ý định của tính năng import. Khi `source == "ai"`, hành vi cũ giữ nguyên (AI tổng hợp prompt chuẩn hoá qua `generate_shots`). Người dùng vẫn có thể bấm "Tạo lại Visual"/"Tạo lại giọng đọc" theo từng shot bất kỳ lúc nào nếu muốn AI viết lại, kể cả với shot gốc từ import.
  - Nút "Nghe full script" / "Nghe đoạn này" (play giả lập) trong design **không được build** — giữ nguyên quyết định đã ghi từ vòng 1: không có TTS thật chạy trong M1 (§05 mục 9), một nút "phát" không phát được gì thực sự là UI trang trí không phục vụ chức năng thật.
- **Pack Review**: tab "Full Script & Shot List" đổi hiển thị shot từ `s.prompt` sang `s.visual_fx` theo tên field mới.

### 9.4 Kiểm thử

16 test mới trong `tests/test_script_import.py` (parser thuần + endpoint parse/confirm + nhánh seed-không-gọi-AI khi import) cộng thêm cập nhật `tests/test_pipeline_flow.py` cho field đổi tên + 2 endpoint regenerate mới + 2 endpoint bulk mới. Tổng **96 test, tất cả pass**. Đã smoke-test thêm bằng HTTP thật (không qua pytest) toàn bộ luồng: parse CSV → confirm → visual/generate (xác nhận seed đúng, không gọi AI) → regenerate-visual → pack/build → gate2 approve.

## 10. Cập nhật vòng 5 (2026-08-12) — Bỏ Mock provider mặc định + sửa Prompt Templates

### 10.1 Bỏ Mock provider mặc định — báo lỗi rõ ràng thay vì âm thầm dùng nội dung giả lập

Theo yêu cầu người dùng: không cần Mock provider mặc định; nếu chưa cấu hình Provider AI thì phải hiện cảnh báo khi 1 bước cần AI, để người dùng chủ động vào Cài đặt xử lý — thay vì hành vi cũ (seed sẵn `MockLLMProvider` làm mặc định, mọi bước "chạy được" nhưng âm thầm sinh nội dung placeholder vô nghĩa).

- `app/providers/factory.py`: thêm `NoProviderConfiguredError`; `get_llm()` raise exception này khi không có provider LLM `enabled` nào (thay vì trả về `MockLLMProvider()`), và cả khi provider đã cấu hình nhưng khởi tạo lỗi (VD sai key). Xoá `get_llm_with_fallback()`/`get_fallback_llm()` (dead code sau khi bỏ fallback).
- `app/main.py`: thêm exception handler toàn cục cho `NoProviderConfiguredError` → HTTP 400, `{"detail": "<thông điệp tiếng Việt>"}` (cùng format `HTTPException` khác, không đổi format theo §03).
- `app/guardrail/check.py`: `run_guardrail_check()` đổi sang resolve LLM **lazy** (`db` thay vì `llm` bắt buộc) — chỉ thật sự cần Provider AI khi `hook_spoken` khác rỗng (chấm Hook Strength). Script nhập từ CSV/Excel (không có hook) chạy guardrail được mà không cần provider.
- `app/seed.py`: bỏ hẳn khối seed provider Mock mặc định.
- `backend/tests/conftest.py`: fixture `_ensure_mock_llm_is_default` tự tạo 1 provider Mock **riêng cho test suite** (không đụng seed thật) để pytest chạy pipeline offline.
- `tests/test_no_provider.py` (mới, 7 test): xác nhận `/bootstrap.has_llm_provider=False`, và từng endpoint cần AI (`/research`, `/gate1`, `/guardrail/check` khi có hook, `/pack/build`, `/visual/generate` khi script nguồn AI) trả 400 kèm thông điệp đúng khi không có provider — đồng thời xác nhận luồng import (không hook, không gọi AI ở `/visual/generate`) chạy được **không cần provider nào**.
- **Frontend**: banner nổi toàn cục góc dưới-phải (`App.tsx`, dựa vào `GET /bootstrap`) đã có sẵn từ trước, cảnh báo ngay cả khi chưa bấm hành động nào. Bổ sung mới: component `components/AiErrorBanner.tsx` + bắt lỗi (`try/catch` với `ApiError`) ở MỌI hành động gọi AI trong `BriefEditor` (Bắt đầu Research), `Gate1Outline` (Duyệt Gate #1), `ScriptStudio` (Tạo lại theo góp ý, Duyệt Script, Đi tới Visual Studio), `VisualStudio` (Tạo lại Visual/giọng đọc từng shot, 2 nút hàng loạt, Xem Production Pack) — trước đó các hành động này chạy trong `try {...} finally {...}` KHÔNG có `catch`, nên lỗi 400 mới sẽ thất bại lặng lẽ (cùng lớp lỗi đã gặp và sửa với luồng import YouTube ở vòng 2).
- Đã verify end-to-end bằng HTTP thật (tạo project tạm, tắt hết provider → `/research` trả đúng 400 kèm thông điệp; bật lại provider → chạy bình thường trả 200; dọn project tạm sau khi test) — không chỉ dựa vào pytest.
- Tổng **103 test, tất cả pass** (96 cũ + 7 mới).

### 10.2 Sửa Prompt Templates — khớp đúng luồng, tham số đúng, bỏ thông tin giả

Người dùng yêu cầu review màn Prompt Templates theo 4 tiêu chí: (1) mọi prompt phải thật sự được dùng và gắn với 1 bước trong luồng, (2) tham số truyền vào khớp đúng field thật, (3) hiển thị "từ điển" tham số ngay trên UI khi soạn/sửa, (4) bỏ thông tin không có thật (VD tên người soạn giả trong app single-user).

Rà lại `backend/app/pipeline/generation.py` (từng lệnh gọi `get_template_body(db, task_key)` và đúng bộ tham số `ctx` truyền vào), phát hiện 2 lớp lỗi:

- **Task key mồ côi** (seed sẵn nhưng không có điểm gọi thật nào trong code): `brief` ("Gợi ý Brief từ ý tưởng" — Brief Editor không có bước AI-assist nào gọi tới) và `visual_video` (`regenerate_shot_visual_fx` LUÔN dùng template `visual_image` bất kể `visual_type` của shot là ảnh hay video). → Gỡ `brief` khỏi seed (không có tính năng thật đứng sau); wire `visual_video` vào đúng nhánh khi shot có `visual_type == "video"` (tham số `visual_type` mới truyền qua `regenerate_shot_visual_fx`, lấy từ `target.get("visual_type")`/`s.get("visual_type")` ở 2 điểm gọi trong `routers/pipeline.py`).
- **1 task key dùng cho 2 lệnh gọi có bộ tham số khác nhau** (khiến 1 nửa `{{placeholder}}` không bao giờ được thay thế, giữ nguyên dạng `{{...}}` trong prompt gửi AI): `outline_hook` dùng chung cho cả `generate_research` (tham số `topic`/`brief`/`outline_count`) lẫn `generate_hooks` (tham số `chosen_outline`/`hook_count`); `visual_image` dùng chung cho cả `generate_shots` — sinh HÀNG LOẠT shot ban đầu (tham số `script`) — lẫn `regenerate_shot_visual_fx` — sinh lại 1 shot riêng lẻ (tham số `script_snippet`/`visual_description`). → Tách `outline_hook` thành 2 task key riêng `outline`/`hook`; tách phần batch của `visual_image` ra task key mới `visual_shots_init`. Nguyên tắc mới ghi vào specs/07 mục 7: **mỗi task key chỉ ứng đúng 1 điểm gọi LLM (1:1)**.
- `backend/app/seed.py` (`PROMPT_SEED`): viết lại theo cấu trúc 10 task key mới (`outline`, `hook`, `script`, `script_revise`, `script_breakdown`, `visual_shots_init`, `visual_image`, `visual_video`, `visual_tts`, `thumbnail`), mỗi bản seed chỉ dùng đúng placeholder mà `ctx` thật sự cung cấp cho điểm gọi tương ứng. Đổi mọi `updated_by` từ tên người giả (Hải Yến/Minh Anh/Đức Long) sang **"Hệ thống"** — app single-user không có quản lý user (§CLAUDE.md nguyên tắc 5); version do người dùng tự tạo qua UI vẫn ghi "Bạn" (không đổi, đã đúng từ trước).
- `frontend/src/screens/settings/PromptTemplatesSettings.tsx`: cập nhật `STAGE_LABEL`/`STAGE_TO_STEP` theo task key mới; thêm `TASK_PARAMS`/`COMMON_PARAMS` — từ điển tham số khớp CHÍNH XÁC với `ctx` dựng trong `generation.py` cho từng task — hiển thị qua component `ParamDictionary` ở cả (a) card mở rộng của 1 template có sẵn và (b) dialog Tạo mới/Sửa (theo task đang chọn), để biết ngay nên dùng `{{...}}` nào mà không phải đọc code backend.
- Dữ liệu prompt template cũ trong DB workspace thật (task key cũ, tên giả) đã được xoá và reseed lại theo cấu trúc mới (xác nhận với người dùng trước khi xoá vì đây là dữ liệu cục bộ đã tồn tại) — verify qua `GET /prompt-templates` sau khi khởi động lại backend: đủ 10 template, mọi `updated_by` đều là "Hệ thống".
- `backend/tests/test_settings.py`: cập nhật assertion tra cứu theo task key `outline` (trước đây `outline_hook`).
- Đã cập nhật `specs/07_prompt_templates.md` (bảng ánh xạ task key ↔ điểm gọi ↔ tham số, nguyên tắc 1:1 mới) làm nguồn sự thật khớp code.
- Tổng vẫn **103 test, tất cả pass** sau refactor (không thêm test riêng cho phần này — đã có test hiện có phủ CRUD + `test_no_provider.py` phủ việc chọn template theo task key gián tiếp qua pipeline).

## 11. Cập nhật vòng 6 (2026-08-12) — Sửa lỗi rename project + cập nhật danh sách/giá model AI thực tế

### 11.1 Đổi tên project

Không có UI nào cho phép đổi tên project dù backend `PATCH /projects/{id}` đã hỗ trợ field `title` từ trước — `ProjectView`/`Dashboard`/`Sidebar` chỉ hiển thị `project.title` dạng text tĩnh. Thêm click-to-edit ngay trên breadcrumb title ở `ProjectView.tsx` (bấm → input → Enter/blur lưu qua `patchProject`, Escape huỷ). Vì Sidebar cache danh sách project theo kênh và không có cơ chế tự làm mới khi có thay đổi ở nơi khác, thêm `AppContext.projectsVersion` + `bumpProjectsVersion(channelId)` — `ProjectView` gọi hàm này sau khi đổi tên thành công, `Sidebar` refetch khi version đổi.

### 11.2 Cập nhật danh sách & giá model AI theo thực tế 2026-08-12

Danh sách model trong `CLOUD_MODELS` (backend) / `CLOUD_CATALOG` (frontend) đã cũ (VD `claude-sonnet-4-5`, `gpt-4.1`, `gemini-2.5-pro` — đều là model thế hệ trước). Đã research lại qua tài liệu chính thức từng hãng (không dùng số liệu từ các trang tổng hợp giá bên thứ 3 — nhiều trang trong số đó có dấu hiệu nội dung SEO tự sinh, số liệu không đáng tin):

- **Anthropic** (`docs.claude.com/en/docs/about-claude/models/overview`): model hiện hành `claude-fable-5` ($10/$50 mỗi 1M token input/output), `claude-opus-5` ($5/$25), `claude-sonnet-5` ($2/$10), `claude-haiku-4-5` ($1/$5).
- **OpenAI** (`developers.openai.com/api/docs/pricing`, `/models`): dòng flagship hiện tại là GPT-5.6 với 3 tier `gpt-5.6-sol` ($5/$30, mạnh nhất), `gpt-5.6-terra` ($2/$12, cân bằng), `gpt-5.6-luna` ($0.20/$1.20, rẻ nhất).
- **Google Gemini** (`ai.google.dev/gemini-api/docs/pricing`, `/models`): `gemini-3.6-flash` ($1.50/$7.50, flagship GA mới nhất), `gemini-2.5-pro` ($1.25/$10.00, vẫn là lựa chọn reasoning chất lượng cao nhất có giá GA chính thức — `gemini-3.1-pro-preview` mạnh hơn nhưng còn preview nên không đưa vào danh sách mặc định), `gemini-2.5-flash-lite` ($0.10/$0.40, rẻ nhất).

Cập nhật: `backend/app/routers/providers.py` (`CLOUD_MODELS`), `frontend/src/screens/settings/ProviderSettings.tsx` (`CLOUD_CATALOG`) — 2 nơi phải khớp nhau. Đồng thời phát hiện thêm 1 vấn đề liên quan trong lúc rà soát: cả 3 adapter (`app/providers/claude.py`/`openai_provider.py`/`gemini.py`) trước đó tính `estimated_cost_usd` bằng 1 mức giá CỐ ĐỊNH DUY NHẤT bất kể model nào đang cấu hình (VD Claude luôn tính $3/$15 dù đang dùng Opus $5/$25 hay Haiku $1/$5) — sai số lớn cho tính năng Chi phí & Ngân sách. Thêm dict `PRICING: dict[model_name, (price_in, price_out)]` cho từng adapter (khớp bảng giá chính thức ở trên, gồm cả vài model thế hệ trước còn dùng được) + `DEFAULT_PRICING` làm fallback khi model không có trong bảng (model snapshot cũ/tự nhập), cost tính theo đúng model đang cấu hình. Default `model_name` của từng adapter khi tạo mới cũng đổi sang tier "cân bằng" hiện tại (`claude-sonnet-5`/`gpt-5.6-terra`/`gemini-3.6-flash`).

**Chưa cập nhật ở vòng này:** danh sách model của `elevenlabs`/`vbee`/`flux`/`midjourney`/`runway` — không research lại lần này (giữ nguyên); OpenAI/Gemini cho tts/image/video đã bổ sung ở vòng 7 (mục 12 dưới đây).

Verify: tạo 1 provider Claude qua API thật (không truyền `model_name`) → xác nhận `model_name` mặc định trả về là `claude-opus-5` (model đầu danh sách mới) và `available_models` đúng 4 model mới; dọn provider tạm sau khi test. Restart lại backend dev (8756) + Electron (backend con của Electron không tự nhận code mới vì chạy `uvicorn` không có `--reload`) để code mới thật sự có hiệu lực trên app đang chạy. Tổng vẫn **103 test, tất cả pass**, frontend typecheck sạch.

## 12. Cập nhật vòng 7 (2026-08-12) — Bổ sung provider TTS/Image/Video của OpenAI & Gemini

Yêu cầu: bổ sung provider AI từ các model của Gemini, OpenAI và Anthropic (nếu có) cho `tts`/`image`/`video` — trước đó 3 task này chỉ có Vbee/ElevenLabs (tts), Flux/Midjourney (image), Runway/Sora (video); dù `specs/05_ai_providers.md` mục 1 đã liệt kê ý định "Gemini TTS"/"Gemini (Veo)" từ trước, chưa từng build.

**Research** (tài liệu chính thức, đối chiếu 2026-08-12 — không dùng số liệu trang tổng hợp giá bên thứ 3):
- **Anthropic:** xác nhận KHÔNG có sản phẩm TTS/Image/Video công khai — Claude chỉ nhận ảnh làm input qua vision, không sinh ảnh/audio/video. Không có adapter Anthropic cho 3 task này.
- **OpenAI:** TTS — `gpt-4o-mini-tts`, `tts-1-hd`, `tts-1`; Image — `gpt-image-2` (mới nhất), `gpt-image-1-mini` (rẻ); Video (Sora) — `sora-2`, `sora-2-pro` (danh sách Sora cũ `sora-1` đã lỗi thời, cập nhật lại).
- **Google Gemini:** TTS — `gemini-3.1-flash-tts-preview`, `gemini-2.5-pro-preview-tts`, `gemini-2.5-flash-preview-tts`; Image (Nano Banana) — `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`; Video (Veo) — `veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`.

**Vấn đề kỹ thuật cần xử lý:** OpenAI và Gemini đã có mặt ở nhóm `llm` với model list riêng — cùng `provider_name` ("openai"/"gemini") nhưng khác `task` (tts/image) cần model list KHÁC NHAU. `CLOUD_MODELS` cũ chỉ tra theo `provider_name` (1 danh sách/provider, không phân biệt task) nên không đủ. Thêm `CLOUD_MODELS_BY_TASK: dict[(task, provider_name), list[str]]` trong `backend/app/routers/providers.py`, tra theo cặp `(task, provider_name)` trước, fallback về `CLOUD_MODELS` (tra theo `provider_name` — dùng cho `llm` và các provider chỉ có 1 task như Flux/Runway).

**Thay đổi:**
- `backend/app/providers/stubs.py`: thêm `OpenAITTSProvider`, `GeminiTTSProvider`, `OpenAIImageProvider`, `GeminiImageProvider`, `VeoVideoProvider` — cùng pattern `NotImplementedMixin` như các adapter TTS/Image/Video khác (chưa thực thi sinh asset thật ở M1, `test_connection()` chỉ kiểm tra đã lưu API key).
- `backend/app/routers/providers.py`: đăng ký adapter mới vào `_TTS_ADAPTERS`/`_IMAGE_ADAPTERS`/`_VIDEO_ADAPTERS`; thêm `CLOUD_MODELS_BY_TASK` + hàm `_cloud_models_for(task, provider_name)`; cập nhật `sora` sang `["sora-2", "sora-2-pro"]`.
- `frontend/src/screens/settings/ProviderSettings.tsx`: thêm 2 mục "OpenAI TTS"/"Gemini TTS" vào nhóm `tts`, "OpenAI Image (GPT Image)"/"Gemini Image (Nano Banana)" vào nhóm `image`, "Google Veo" vào nhóm `video` (giữ nguyên "Sora (OpenAI)" — chỉ đổi model list).
- `specs/05_ai_providers.md` mục 1: cập nhật bảng provider theo task khớp thực tế.

Verify: tạo 6 provider tạm (mỗi task tts/image/video × openai/gemini, cộng cả veo và sora) qua API thật → xác nhận `model_name` mặc định + `available_models` đúng theo `(task, provider_name)`, gọi `/providers/{id}/test` cho cả 6 → đều trả `ok:true`; dọn hết provider tạm sau khi test. Restart backend dev (8756) + Electron để code mới có hiệu lực. Tổng vẫn **103 test, tất cả pass**, frontend typecheck sạch.

## 13. M2 — Production Layer: TTS/Image/Video thật + ghép MP4 (2026-08-12)

Người dùng yêu cầu triển khai M2 (thực thi adapter TTS/Image/Video + ghép MP4 —
trước đó chỉ khai báo interface). Do khối lượng lớn (research provider, kiến trúc
async, ffmpeg — dependency hoàn toàn mới), đã lập plan riêng qua Claude Code plan mode
trước khi code (approve trước khi implement). Quyết định phạm vi: người dùng chọn làm
**trọn vẹn cả 3 loại (TTS+Image+Video) + ghép MP4 trong 1 đợt**, mỗi loại 1 provider
đầu tiên — **ElevenLabs** (TTS), **OpenAI Image** (ảnh), **quyết định tự chủ động:
OpenAI Sora** (video, thay vì Runway/Veo — lý do: chung hệ sinh thái API key với
Image, đỡ 1 tài khoản; pattern job-polling của OpenAI là dạng tự tin nhất về cấu trúc
chung trong 3 lựa chọn).

**Kiến trúc chính** (chi tiết: `specs/05_ai_providers.md` §8c, `specs/04_data_schemas.md`
§3b): module mới `backend/app/render/` (engine.py sinh asset, assembly.py ghép ffmpeg,
schemas.py) tách biệt hoàn toàn `ProductionPack`/`pack.json` — trạng thái sinh asset +
ghép video sống ở file riêng `render.json` trong `project_dir()`, script core chỉ bị
ĐỌC không bao giờ bị ghi. Router mới `backend/app/routers/render.py` (8 endpoint: start/
status/approve/regenerate-visual/regenerate-narration/assemble/download/asset). Chạy
qua `FastAPI BackgroundTasks` (không block request — Sora poll có thể mất tới 8 phút).

**3 quyết định kỹ thuật đáng chú ý:**
1. **`VideoProvider` interface mở rộng** — thêm `start_generation()`/`poll_generation()`
   bất đồng bộ bên cạnh `generate()` đồng bộ cũ, vì Sora/Runway/Veo đều là job-based
   (gửi job → chờ → poll → tải), khác hẳn TTS/Image (1 request trả thẳng bytes).
2. **Narration TTS hoá `script.body[].audio` (lời thoại thật), KHÔNG PHẢI `shot.audio_sfx`**
   (đó là mô tả nhạc nền/cảm xúc, không phải lời đọc — đã ghi rõ trong `specs/07` mục 7
   từ vòng trước) — `audio_sfx`/`direction` chỉ dùng làm gợi ý emotion cho TTS.
3. **Bug thực tế phát hiện & sửa khi implement**: endpoint regenerate-visual/regenerate-
   narration ban đầu định dùng closure bắt session `db` request-scoped (`Depends(get_db)`)
   bên trong `BackgroundTasks` — session này bị FastAPI đóng NGAY khi response trả về,
   TRƯỚC KHI background task chạy, sẽ lỗi "session is closed". Sửa bằng cách viết
   `regenerate_single_visual()`/`regenerate_single_narration()` trong `engine.py` tự mở/
   đóng `SessionLocal()` riêng — cùng pattern với `run_asset_generation()` (batch).

**Cost tracking**: `record_asset_usage()` mới (cạnh `record_usage()` gốc cho LLM, cùng
file `routers/pipeline.py`) — ghi cùng `AuditLog`/`Budget`, giá ước tính theo ký tự
(TTS)/số ảnh (Image)/số giây (Video), xem PRICING trong từng adapter.

**Frontend**: `RenderStudio.tsx` (mới) nhúng trong `OutputCenter.tsx` (thẻ "Render
in-app" hết `disabled`, mở panel thay vì cả 2 thẻ) — KHÔNG thêm step Stepper mới, khớp
đúng vị trí design gốc (§06 màn ⑦). Preview thật `<img>`/`<video>`/`<audio>` — khác hẳn
placeholder text ở Visual Studio (§06 màn ⑤, vẫn giữ nguyên, chỉ sinh prompt).

**Test**: `backend/tests/test_render.py` (10 test mới) — mock TOÀN BỘ HTTP ra ngoài qua
`respx` (thêm dependency mới), không gọi API thật/không tốn phí trong lúc test. Bug tự
phát hiện khi viết test: 1 test dự định kiểm tra "chưa cấu hình provider" vô tình gọi ra
INTERNET THẬT (401 từ OpenAI với key giả `sk-oai-test`) vì `client` là session-scoped
dùng chung với test khác đã tạo sẵn provider — sửa bằng cách chủ động xoá hết provider
tts/image/video ở đầu test (cùng pattern `_delete_all_llm_providers` đã dùng ở
`test_no_provider.py`) + thêm `@respx.mock` làm lưới an toàn kép (request lọt qua sẽ bị
respx chặn thay vì ra mạng thật). Tổng **113 test, tất cả pass** (103 cũ + 10 mới).

**Verify**: KHÔNG gọi API thật tốn phí trong lúc implement (đúng theo plan) — chỉ verify
cấu trúc + mock. Việc request/response của Sora khớp thực tế (rủi ro cao nhất, ghi rõ
trong code comment `video_sora.py`) cần người dùng tự bấm thử trong Render Studio với
key thật; nếu lệch, sửa theo message lỗi thật (đã có `raise_for_status_with_body`).
`ffmpeg` cần cài riêng trên máy chạy backend (không bundle) — đã thêm check rõ ràng
(`shutil.which`) + ghi vào README.md, test `assemble` khi thiếu ffmpeg dùng `monkeypatch`
thay vì cần cài thật trên máy dev/CI.

## 14. Pack Review — gộp Description/Timeline/Hashtags + Thumbnail AI + copy buttons; sửa lỗi Gemini test connection (2026-08-12)

### 14.1 Pack Review — Title & Thumbnail

- Bỏ tab "Repurposing" (chờ M3, tab rỗng gây rối) — `PackReview.tsx` chỉ còn 2 tab.
  `pack.repurpose` giữ nguyên trong schema, không xoá — chỉ ẩn UI.
- Description/Timeline/Hashtags gộp hiển thị chung 1 khối (không phải 3 field tách
  rời như trước) — Timeline định dạng `h:mm:ss - tên chapter` (hàm `formatTimestamp`,
  frontend). 1 nút Copy ở đầu khối copy TOÀN BỘ 3 phần ghép thành 1 đoạn text (mỗi
  phần cách nhau 1 dòng trống) — dán thẳng được vào ô Description khi upload YouTube
  Studio. Description (SEO) vẫn là field RIÊNG có thể sửa/lưu (auto-save debounce
  500ms qua `PATCH /pack`, giống pattern `BriefEditor.tsx`) — Timeline/Hashtags hiển
  thị read-only bên dưới (nguồn dữ liệu cấu trúc `chapters`/`hashtags` không đổi,
  chỉ GHÉP LÚC HIỂN THỊ/COPY, không lưu thành 1 blob text duy nhất — tránh lệch dữ
  liệu nếu sau này cần dùng `chapters` có cấu trúc ở chỗ khác, VD export).
- Nút Copy riêng ở mỗi Title (component `CopyButton` dùng chung, ✓ xanh 1.5s sau khi
  copy thành công).
- **Nút "Tạo ảnh Thumbnail bằng AI"** — sinh ảnh THẬT, tái dùng nguyên
  `app/providers/image_openai.py::OpenAIImageProvider` đã build ở M2 (không viết
  adapter mới). Backend: `POST /projects/{id}/pack/thumbnail/generate` (đồng bộ, 1
  ảnh — không cần `BackgroundTasks` như Render Studio nhiều shot); prompt ghép từ
  `thumbnail_description` + tiêu đề đầu tiên (gợi ý text overlay) +
  `brand.visual_style_prompt`. Lưu ảnh vào `assets/thumbnail.png` (tái dùng thư mục
  `assets/` đã tạo cho M2), trạng thái `thumbnail_status`/`thumbnail_asset_path`/
  `thumbnail_provider`/`thumbnail_error` ghi thẳng vào `youtube_meta` trong
  `pack.json` (KHÔNG dùng `render.json` riêng như shot — thumbnail là dữ liệu
  Pack-level, không phải asset theo shot). `GET /projects/{id}/pack/thumbnail` phục
  vụ file — frontend dùng làm cả `<img src>` và link tải (`download="thumbnail.png"`).
  Chi phí ghi qua `record_asset_usage()` có sẵn từ M2.

### 14.2 Sửa lỗi Gemini "Test kết nối" báo lỗi khó hiểu (mất chữ, chỉ hiện "parts")

**Nguyên nhân xác nhận**: `gemini.py::complete()` đọc thẳng
`data["candidates"][0]["content"]["parts"]` không qua kiểm tra — khi Gemini không trả
`parts` (thường gặp nhất: model có "thinking" bật mặc định ở dòng Gemini 2.5+/3.x tiêu
hết ngân sách `maxOutputTokens` rất nhỏ — `test_connection()` cũ dùng `max_tokens=8` —
cho suy luận nội bộ, không còn phần trả lời hiển thị dù HTTP vẫn 200 OK) → Python raise
`KeyError('parts')` trần, `str(e)` chỉ còn đúng chữ `'parts'` — đúng như người dùng mô
tả, không có ngữ cảnh gì để tự chẩn đoán.

**Sửa**: hàm `_extract_text()` mới parse phòng thủ — kiểm tra `candidates` rỗng (kèm
`promptFeedback.blockReason` nếu bị chặn an toàn), kiểm tra `parts` rỗng (kèm
`finishReason`, gợi ý "model dùng hết ngân sách token cho suy luận nội bộ — thử tăng
max_tokens hoặc đổi model"). Đồng thời tăng `max_tokens` của riêng lệnh test ping từ
8 → 64 để giảm khả năng gặp lại tình huống này ngay từ đầu.

**Điểm liên quan đã hỏi thêm**: các provider TTS/Image/Video còn ở dạng stub (Vbee,
Flux, Midjourney, Runway, OpenAI TTS, Gemini TTS/Image, Veo) trả `test_connection()`
chỉ dựa trên `bool(api_key)` — message cũ "Đã lưu key — sinh ảnh thật sẽ mở ở M2" dễ
hiểu lầm là ĐÃ xác minh kết nối thành công. Đổi thành "Đã lưu key — CHƯA xác minh kết
nối thật (provider này chưa gọi API, chỉ kiểm tra đã nhập key)" — trung thực hơn,
không hứa hẹn quá mức những gì thật sự đã kiểm tra. 3 provider đã thực thi thật ở M2
(ElevenLabs/OpenAI Image/Sora) không đổi — `test_connection()` của chúng gọi API thật
(hoặc endpoint free như `GET /v1/models`), message "Kết nối thành công" là đúng nghĩa.

**Test mới**: `backend/tests/test_pack_thumbnail.py` (4 test — mock qua `respx`, không
tốn phí). Tổng **117 test, tất cả pass** (113 cũ + 4 mới). Frontend typecheck sạch.

## 15. Chuyển sinh asset thật vào Visual Studio + Fallback provider thật + UX Provider AI + Gemini TTS/Image/Veo thật (2026-08-12)

Người dùng phản hồi 4 việc sau khi dùng thử M2. Đã lập plan qua Claude Code plan mode
trước khi code (approve trước khi implement) do đây là đổi kiến trúc thật, không chỉ
thêm tính năng nhỏ.

### 15.1 Sinh asset thật chuyển từ Render Studio sang Visual Studio

Tin tốt: kiến trúc `app/render/engine.py`/`render.json`/`BackgroundTasks` ở M2 đã đúng
sẵn — thứ DUY NHẤT sai là `POST /render/start` chặn bằng
`if p.status not in READY_STATUSES` (chỉ cho phép SAU Gate #2). Xoá điều kiện này
(chỉ cần có `shots`) là gọi được ngay từ Visual Studio (status lúc đó là
`"generating"`, step 3, TRƯỚC Gate #2) — không cần viết lại engine.py, không đổi tên
endpoint `/render/*`. Đã hỏi & xác nhận với người dùng: **Render Studio chỉ còn giữ
lại bước ghép MP4** — thêm status gate (`READY_STATUSES`) vào `POST /render/assemble`
(trước đó KHÔNG có gate nào) để ghép vẫn chỉ làm được sau Gate #2, đúng vai trò còn
lại (xuất thành phẩm ở Output Center, tách khỏi "duyệt nội dung" ở Visual Studio).

Frontend: `VisualStudio.tsx` port nguyên UI per-shot của `RenderStudio.tsx` cũ (preview
thật, badge trạng thái, nút Duyệt) vào — 2 nút cũ "Tạo lại Visual"/"Tạo lại giọng đọc"
(chỉ sửa PROMPT text qua LLM) đổi tên "✎ Viết lại mô tả bằng AI" để không nhầm với nút
sinh asset THẬT mới ("Tạo ảnh/video"/"Tạo giọng đọc"). `RenderStudio.tsx` cắt còn
~90 dòng (từ ~200) — chỉ đọc `render/status` tóm tắt + nút Ghép MP4 + preview/tải.

### 15.2 Fallback provider THẬT cho tts/image/video

`ProviderConfig.is_fallback` trước đó chỉ là cờ DB, KHÔNG có logic nào đọc — đặt
"Fallback" ở Cài đặt không có tác dụng gì (xác nhận bằng cách grep toàn backend,
`is_fallback` chỉ xuất hiện ở model + CRUD router, không ở `factory.py`/pipeline nào).

Thêm `factory.py::get_tts_chain()`/`get_image_chain()`/`get_video_chain()` — trả về
danh sách provider ĐÃ KHỞI TẠO theo thứ tự ưu tiên (`_candidate_configs()`: default
trước, fallback sau nếu có VÀ khác default). `app/render/engine.py` (2 hàm generate)
+ `app/routers/pack.py::generate_thumbnail` thử LẦN LƯỢT từng provider, dừng ở provider
đầu tiên thành công; lỗi TẤT CẢ mới báo, gộp lý do từng lần thử. Phạm vi: **chỉ
tts/image/video** — `get_llm()` có 7+ điểm gọi rải khắp `pipeline/generation.py`, để
riêng sau nếu cần (rủi ro đổi lớn hơn lợi ích ngay lúc này).

Vì fallback chain có thể rơi vào provider KHÁC HÃNG (VD default OpenAI Image lỗi →
fallback Gemini Image), phải chuẩn hoá chữ ký `estimate_cost()` giữa các adapter cùng
task (`(count, model_name="")`) để tính đúng giá theo provider THỰC SỰ THÀNH CÔNG,
không phải provider default. Cũng phát hiện & sửa 1 bug liên quan lúc làm: TTS
narration luôn lưu đuôi file cố định `.mp3` — ElevenLabs đúng, nhưng Gemini TTS trả
WAV (xem 15.3), lưu sai đuôi khiến `FileResponse` đoán nhầm `Content-Type` theo phần
mở rộng → browser phát audio có thể lỗi. Sửa bằng map `_TTS_EXT = {"elevenlabs":
"mp3", "gemini": "wav"}`.

### 15.3 Adapter thật mới: Gemini TTS, Gemini Image, Google Veo

- `app/providers/tts_gemini.py`: `generateContent` + `responseModalities:["AUDIO"]`.
  Gemini trả **PCM thô** (`inlineData`, `mimeType` dạng `audio/L16;rate=...`) — trình
  duyệt không phát được PCM trần qua `<audio>`, phải tự bọc WAV header 44-byte
  (`_wrap_pcm_as_wav()`, chuẩn RIFF/WAVE, không cần thư viện ngoài) trước khi lưu.
- `app/providers/image_gemini.py`: `generateContent` + `responseModalities:["IMAGE"]`,
  decode base64 thẳng — đơn giản hơn TTS, không cần bọc gì thêm.
- `app/providers/video_veo.py`: **rủi ro cao nhất trong toàn bộ app** — Veo dùng
  pattern "long-running operation" riêng của Gemini API (`predictLongRunning` → poll
  `operations/{id}` → tải `video.uri`), khác hẳn cấu trúc REST job-polling của Sora.
  Hoàn toàn suy luận theo tài liệu pattern chung, CHƯA verify với key thật lúc code —
  giống Sora ở M2, cần người dùng tự thử + sửa theo lỗi thật nếu request/response lệch
  (đã có `raise_for_status_with_body` để lộ rõ lỗi thật thay vì generic).
- Cả 3 dùng `test_connection()` gọi `GET /v1beta/models` (miễn phí) — không tốn phí
  sinh thử audio/ảnh/video thật mỗi lần bấm "Test" trong Cài đặt. Xoá 3 class stub
  tương ứng khỏi `app/providers/stubs.py` (promote thành real).

### 15.4 UX màn Provider AI

- **Test khi thêm, không phải sau khi thêm**: `AddProviderDialog` (frontend) — sau
  `createProvider()` gọi luôn `testProvider()`, hiện kết quả (✓/✗ + message) NGAY
  TRONG dialog thay vì tự đóng. Nếu fail: cho sửa lại API Key + "Lưu & Test lại" ngay
  tại chỗ (không bắt đóng dialog rồi tìm nút Sửa ở thẻ). Nút "Đóng"/"Xong" luôn có —
  test fail KHÔNG có nghĩa là không lưu provider, chỉ cảnh báo. Nút "Test" ở từng thẻ
  vẫn giữ nguyên (re-verify sau này, VD xoay key/hết quota).
- **Sửa bug: không sửa được API key**: khối "API Key" cũ dùng `<input readOnly>` LUÔN
  LUÔN, kể cả sau khi bấm icon "mắt" hiện chữ "(ẩn — nhập lại để đổi)" — chữ hứa hẹn
  sửa được nhưng input vẫn `readOnly`, không có cách nào thực sự đổi key sau khi tạo
  provider. Thay bằng nút "Sửa" bật `<input type="password">` THẬT SỰ nhập được + nút
  Lưu (`patchProvider(id, {api_key})`)/Hủy.
- **Sửa bug liên quan phát hiện lúc sửa**: khối hiển thị/sửa API Key trước đó bị ẩn
  hoàn toàn với `group === "video" || group === "image"` (`{group !== "video" &&
  group !== "image" && (...)}`) — nghĩa là card provider Image/Video KHÔNG BAO GIỜ
  hiện được API key, dù mọi provider Image/Video đều là `cloud_api` cần key (bug tồn
  tại từ trước M2, không ai phát hiện vì Image/Video chưa thực thi thật để cần sửa
  key). Xoá điều kiện thừa này — API key hiện/sửa được cho MỌI task cloud_api.

### 15.5 Kiểm thử & xác nhận thật

`backend/tests/test_render.py` bổ sung: `test_render_start_works_from_visual_studio_before_gate2`
(xác nhận đúng thay đổi chính — gọi được TRƯỚC Gate #2), `test_assemble_requires_gate2`
(xác nhận gate dời đúng chỗ), `test_image_fallback_used_when_default_fails` (default
OpenAI Image trả 401 → fallback Gemini Image được dùng, `visual_provider == "gemini"`
— xác nhận fallback THẬT hoạt động, không chỉ code compile), `test_gemini_tts_wraps_pcm_as_wav`,
`test_gemini_image_decodes_base64`, `test_veo_start_and_poll_downloads_video`,
`test_veo_poll_not_done_returns_no_bytes`, `test_gemini_and_veo_test_connection_via_api`.
Tổng **125 test, tất cả pass** (117 cũ + 8 mới). Frontend typecheck sạch.

Verify thật qua API (không tốn phí, mock hết HTTP qua `respx`): xác nhận `render/start`
trả 200 khi `project.status == "generating"` (trước đây 400) và `render/assemble` trả
400 đúng lúc chưa qua Gate #2 (trước đây không gate gì). Đã restart backend dev +
Electron để xác nhận sống trên app đang chạy.

## 16. Local AI Provider trên GPU thật — LLM + TTS + Image + Video (2026-08-13, vòng 8)

Máy build lần này có GPU thật — **NVIDIA RTX 5060 Ti, 16GB VRAM, kiến trúc Blackwell**
(compute capability 12.0, driver 576.88, CUDA runtime tối đa driver hỗ trợ: **12.9**).
Mục tiêu: biến phần "kiến trúc sẵn sàng, chưa test" (mục 5 ở trên, viết lúc máy build
không có GPU) thành chạy thật, verify thật cho **cả 4 nhóm task** (`llm`/`tts`/`image`/
`video`) — trước đó `local_endpoint` chỉ scaffold cho `llm`.

**Đính chính quan trọng ở phiên trước**: có báo nhầm "backend StudioFlow chạy ở cổng
8756" — thực ra đó là tiến trình còn sót của **project khác hoàn toàn** trên máy
(`E:\ai-content-studio`, repo GitHub riêng `trinhcongtan192vn/ai-content-studio`,
đang chạy thật từ 2026-08-04 với dữ liệu workspace thật của người dùng). Việc này đã
xác nhận lại với người dùng và **chỉ làm trên repo StudioFlow** — không đụng
`ai-content-studio`. Backend StudioFlow test thật trong mục này chạy ở cổng **8757**
(8756 vẫn bị project kia chiếm) để tránh lặp lại nhầm lẫn.

### 16.1 Rào cản mạng: `github.com` bị chặn ở tầng TLS/SNI trên máy này

Toàn bộ file cài đặt (Ollama, ComfyUI) đều host trên GitHub Releases, nhưng
`https://github.com` bị reset kết nối ngay sau khi gửi TLS ClientHello (curl `-v`:
`schannel: server close notification received` → `Empty reply from server`) — kể cả
`winget` cũng fail vì tải qua `github.com`. **`api.github.com` và các subdomain CDN
(`objects.githubusercontent.com`, `release-assets.githubusercontent.com`,
`raw.githubusercontent.com`, `codeload.github.com`) đều KHÔNG bị chặn** — chỉ đúng
hostname `github.com` (site chính). Đường vòng: lấy `asset id` qua
`GET api.github.com/repos/{owner}/{repo}/releases/latest`, rồi tải file qua
`GET api.github.com/repos/{owner}/{repo}/releases/assets/{id}` với header
`Accept: application/octet-stream` — endpoint này 302-redirect thẳng tới CDN asset
thật, không đi qua `github.com`. `winget install 7zip.7zip` sau đó lại tự chạy được
bình thường (không rõ vì sao khác Ollama — có thể chặn không ổn định theo route/thời
điểm) — không cần đường vòng cho 7-Zip.

### 16.2 LLM — Ollama + qwen3:14b

- Cài Ollama 0.32.9 (bản portable ZIP tải qua đường vòng ở 16.1, giải nén
  `C:\Tools\Ollama`, không dùng installer .exe để tránh phụ thuộc GUI) — `ollama serve`
  tự nhận GPU ngay, không cần cấu hình gì thêm: log xác nhận
  `library=CUDA compute=12.0 name=CUDA0 description="NVIDIA GeForce RTX 5060 Ti" driver=12.9`.
- Model: **`qwen3:14b`** (~9.3GB, Q4_K_M mặc định) — chọn vì (a) nằm trong danh sách
  spec đã đặt tên sẵn (Qwen/DeepSeek/Kimi, §05 mục 1/5), (b) dense model bám JSON
  format tốt hơn MoE cho nhu cầu output có cấu trúc nghiêm ngặt của pipeline, (c) vừa
  khít 16GB VRAM (`ollama ps` xác nhận **100% GPU, 9.6GB VRAM**), còn dư cho context.
- Verify tăng dần: (1) `curl` thẳng `/v1/chat/completions` — OK; (2) gọi trực tiếp
  `LocalOpenAICompatProvider.complete()`/`test_connection()` (code có sẵn từ trước,
  KHÔNG sửa gì) bằng script rời — OK, ~42 token/s; (3) thêm provider thật qua
  `POST /providers` (`connection_type=local_endpoint`, `endpoint_url=http://localhost:11434/v1`,
  `model_name=qwen3:14b`), đặt `is_default=true` (DB đang 0 provider, an toàn) — Test
  qua UI/API chain trả `ok=true`; (4) gọi thật `POST /projects/prj_demo_tlh/research`
  — sinh research + hook thật qua GPU trong ~38s, JSON hợp lệ, nội dung tiếng Việt mạch
  lạc đúng schema.
- **Giới hạn phát hiện được (không phải bug code)**: qwen3:14b trả `id` của outline/hook
  dạng số nguyên (`3`, `1`, `2`) thay vì string như cloud model (Claude/Gemini/GPT)
  thường tuân theo — `Gate1Body.chosen_outline_id: str` so khớp bằng `==` nên lệch kiểu
  dữ liệu làm "chosen_outline_id không hợp lệ". Đây là hành vi thật của model nhỏ hơn,
  đúng rủi ro đã lường trước (specs/05 mục 5: "Local OK cho AI Research", không phải
  bước generation cuối) — KHÔNG vá bằng cách sửa prompt lõi trong việc này (ngoài phạm
  vi), chỉ ghi nhận. Test thủ công đã tự stringify lại ID trong `pack.json` để đi tiếp
  pipeline; sản phẩm thật cần cân nhắc ép kiểu string ở tầng validate response LLM nếu
  dùng local cho bước này thường xuyên (để riêng, không thuộc việc này).
- Update `local_openai_compat.py`: bỏ câu "chưa test thật vì máy dev không có GPU" —
  đã verify thật. Đổi default gợi ý trong `ProviderSettings.tsx`
  (`qwen2.5:32b` → `qwen3:14b`) vì 32B không vừa 16GB VRAM phổ biến (~20GB ở Q4).

### 16.3 TTS — Piper (không dùng VietTTS)

Spec §05 chỉ nói tới Ollama/vLLM/LM Studio cho `llm`; TTS/Image/Video local hoàn toàn
mới ở việc này. Đã khảo sát `ai-content-studio` xem có hạ tầng local nào "tận dụng"
được không (theo gợi ý người dùng) — project đó có `adapters/tts/viettts.py` (VietTTS)
nhưng **tự ghi rõ "CHƯA kiểm chứng bằng lần gọi thật"**, và VietTTS trên Windows bắt
buộc Docker + NVIDIA Container Toolkit (chưa hỗ trợ native) — không có gì thật để tận
dụng trực tiếp, chỉ có code tham khảo. Đã hỏi người dùng, chọn **Piper TTS** thay vì
đi theo hướng VietTTS/Docker — lý do: cài Docker Desktop chỉ để chạy 1 tính năng là
thay đổi hệ thống quá nặng (bật virtualization/WSL2 + service nền lâu dài) so với lợi
ích; Piper cài thẳng qua `pip install piper-tts`, có giọng tiếng Việt sẵn
(`rhasspy/piper-voices` trên HuggingFace), chạy CPU (không tốn VRAM, nhường chỗ cho
LLM/Image/Video).

- Giọng: `vi_VN-vais1000-medium` (~63MB, `.onnx` + `.onnx.json`), tải về
  `backend/models/piper/` (thư mục mới, gitignore — xem `app/config.py::PIPER_MODELS_DIR`).
- Adapter mới `app/providers/tts_piper.py` — `PiperTTSProvider(TTSProvider)`, chạy
  in-process (không phải server HTTP như Ollama/ComfyUI), cache `PiperVoice` theo
  `model_name` trong process để không load lại onnxruntime session mỗi lần gọi.
- **Bug phát hiện + sửa lúc verify thật**: `routers/providers.py::test_provider` có
  logic khởi tạo adapter RIÊNG cho task khác `llm` (`adapter_cls(api_key=key)` — LUÔN
  LUÔN truyền `api_key`), bỏ qua hoàn toàn `factory.py::_build_asset_provider` (nơi đã
  code nhánh xử lý `local_endpoint` đúng) — bấm "Test" cho provider Piper lỗi
  `PiperTTSProvider.__init__() got an unexpected keyword argument 'api_key'`. Sửa bằng
  cách gọi chung `_build_asset_provider()` thay vì tự dựng adapter — bug này tồn tại
  từ trước (chưa ai phát hiện vì tới giờ TTS/Image/Video local chưa có adapter local
  nào để lộ ra).
- **Bug thứ 2 phát hiện + sửa**: `render/engine.py::_TTS_EXT` map provider→đuôi file
  (`elevenlabs→mp3, gemini→wav`) KHÔNG có Piper — fallback về `.mp3` mặc định trong khi
  Piper trả WAV thật, làm sai `Content-Type` khi phát trong app (cùng dạng bug với
  Gemini TTS đã sửa ở mục 15.2). Thêm `"piper": "wav"`.
- Verify tăng dần: (1) `synthesize()` trực tiếp — WAV thật, nghe được; (2) test qua
  UI/API chain (`POST /providers/{id}/test`) sau khi sửa 2 bug trên — `ok=true`; (3)
  **verify qua pipeline thật**: `POST /projects/prj_demo_tlh/render/start` sinh
  narration cho toàn bộ 10 shot — **10/10 `narration_status=ready`**, file `.wav` thật
  lưu đúng `assets/{shot_id}.wav` (không còn `.mp3` sai đuôi).

### 16.4 Image — ComfyUI + SDXL

**Interface `ImageProvider.generate(prompt)`** (app/providers/base.py) chỉ nhận prompt
text, KHÔNG có tham số ảnh tham chiếu — khác `ai-content-studio`'s
`ImageGenRequest.character_refs` (dùng IPAdapter Plus). Port sang repo này **bỏ hẳn**
phần IPAdapter — chỉ cần workflow txt2img SDXL thuần, rủi ro thấp hơn nhiều so với bản
gốc (chính bản gốc cũng tự ghi "CHƯA verify sống").

- ComfyUI 0.32.0, bản portable Windows+NVIDIA (tải qua đường vòng ở 16.1), giải nén
  `C:\Tools\ComfyUI_extract` (ngoài repo — hạ tầng local, giống Ollama). Checkpoint
  `sd_xl_base_1.0.safetensors` (6.94GB, HuggingFace `stabilityai/stable-diffusion-xl-base-1.0`)
  vào `ComfyUI/models/checkpoints/`.
- Adapter mới `app/providers/image_comfy_sdxl.py` — `ComfySDXLImageProvider(ImageProvider)`,
  ĐỒNG BỘ (`httpx.Client`, khớp convention `image_openai.py`/`image_gemini.py` của repo
  này — khác `ai-content-studio` dùng async): `POST /prompt` (queue) → poll
  `GET /history/{id}` → `GET /view` (tải PNG). Độ phân giải 1344×768 (~16:9, đúng 1
  bucket SDXL được train — khác 1792×1024 OpenAI Image dùng, ở SDXL sẽ giảm chất lượng
  rõ vì lệch xa vùng train).
- **Sự cố lớn nhất trong việc này — không tương thích torch/CUDA với GPU Blackwell**:
  xem chi tiết mục 16.6. Tóm tắt: bundled PyTorch mặc định (cu130) crash
  (`access violation`) vì driver chỉ hỗ trợ CUDA 12.9; đổi sang cu126 thì torch load
  được nhưng THIẾU hẳn kernel cho compute capability 12.0 (Blackwell) — cuối cùng
  `pip install torch==2.8.0 torchvision torchaudio --index-url .../whl/cu129` mới chạy
  đúng (matmul thật trên GPU OK).
- Verify tăng dần: (1) gọi `generate()` trực tiếp — ảnh PNG thật (1.5MB, 28.4s, cảnh
  đồng quê Việt Nam đúng mô tả prompt — xem ảnh trong lịch sử phiên làm việc); (2)
  thêm provider qua API + Test — `ok=true`; (3) **verify qua pipeline thật**:
  `POST .../render/shots/0/regenerate-visual` trên project demo — `visual_status=ready`,
  `visual_provider=local_sdxl`, file `.png` thật lưu vào `assets/0.png`.

### 16.5 Video — Wan2.2 TI2V-5B (ComfyUI), không phải LTX-Video

**Đã verify thật thành công qua GPU + qua đúng pipeline app** (`render/shots/{id}/regenerate-visual`
→ `visual_status=ready`, `visual_provider=local_wan`, file `.mp4` thật 362KB, H.264,
1280×704, 24fps, 7.875s — khớp chính xác thời lượng beat script tính ra) — xem 16.6b
cho hành trình xử lý sự cố tốc độ.

**Khác biệt kiến trúc quan trọng so với `ai-content-studio`**:
`VideoProvider.start_generation(prompt, *, seconds=8)` của repo này (app/render/engine.py:231)
CHỈ nhận prompt text, không có ảnh shot nào truyền vào — bắt buộc **text-to-video
thuần**. `ai-content-studio/apps/backend/app/adapters/video_gen/comfy_ltx.py` (LTX-Video)
nhận `req.image_path` — là image-to-video, không port trực tiếp được, và theo đúng ghi
chú của chính file đó, LTX ở chế độ img2vid mới là chế độ mạnh/tin cậy, dùng cho txt2vid
rủi ro cao hơn nữa.

Chọn **Wan2.2 TI2V-5B** thay thế: có workflow mẫu CHÍNH THỨC từ ComfyUI
(`Comfy-Org/workflow_templates` repo, `templates/video_wan2_2_5B_ti2v.json` — tải được
qua `raw.githubusercontent.com`, không bị chặn mạng), nhẹ hơn LTX (~8GB VRAM so với
~13GB). Workflow mẫu chính thức thực ra là TI2V (ảnh + text, node
`Wan22ImageToVideoLatent` nhận `start_image` qua `LoadImage`) — đọc thẳng source
ComfyUI (`comfy_extras/nodes_wan.py`) xác nhận `start_image` là
`io.Image.Input(..., optional=True)`: bỏ hẳn input này (không nối `LoadImage`), node tự
khởi tạo latent từ noise thuần → chạy đúng T2V mà KHÔNG cần tự dựng workflow riêng, chỉ
bớt 1 nhánh khỏi đúng workflow chính thức — độ tin cậy cao hơn hẳn so với suy đoán từ
đầu (khác cách LTX/IPAdapter phải làm ở `ai-content-studio`).

### 16.6 Sự cố xuyên suốt: torch/CUDA không tương thích GPU Blackwell (sm_120)

Ghi chi tiết vì đây là sự cố tốn nhiều thời gian nhất và có khả năng lặp lại với người
dùng khác có GPU RTX 50-series:

1. ComfyUI portable bản mặc định ("nvidia") bundle **torch 2.13.0+cu130**. Chạy thẳng
   → `Windows fatal exception: access violation` ngay khi `torch.cuda._lazy_init()`.
   Nguyên nhân: driver máy (576.88) chỉ hỗ trợ tới **CUDA 12.9**
   (`nvidia-smi` → `CUDA Version: 12.9`), thấp hơn CUDA 13.0 mà bundled torch cần —
   KHÔNG phải lỗi cấu hình, là bundled build quá mới so với driver.
2. Thử tải nguyên bản `ComfyUI_windows_portable_nvidia_cu126.7z` (2.1GB) song song với
   thử `pip install torch==2.13.0 --force-reinstall --index-url .../whl/cu126` ngay
   trên bản đã giải nén — pip nhanh hơn nhiều (không cần tải lại + giải nén 56000 file +
   di chuyển lại checkpoint 6.9GB) nên huỷ tải file zip, đi tiếp bằng pip. Kết quả: torch
   2.13.0+cu126 **load được, KHÔNG crash**, nhưng ComfyUI tự in cảnh báo rõ ràng lúc
   khởi động: *"NVIDIA GeForce RTX 5060 Ti with CUDA capability sm_120 is not compatible
   with the current PyTorch installation. The current PyTorch install supports ...
   sm_90"* — tức bản cu126 hoàn toàn không có kernel biên dịch cho Blackwell (sm_120),
   dù chạy không crash, mọi phép tính GPU thật sẽ lỗi.
3. Log cảnh báo tự gợi ý chính xác hướng sửa: *"For CUDA 12.9 use pip install
   torch==2.13.0 --index-url .../whl/cu129"* — nhưng bản `torch==2.13.0+cu129` KHÔNG
   tồn tại (kênh cu129 chỉ có tới 2.8.0/2.9.0). Thử `2.9.0` trước, bị lỗi xung đột phụ
   thuộc (`torchaudio` kênh cu129 chỉ có bản khớp `torch==2.8.0`) — cuối cùng
   **`torch==2.8.0+cu129` + `torchvision`/`torchaudio` cùng kênh** cài thành công,
   verify bằng phép nhân ma trận thật trên GPU (`torch.randn(4,4,device='cuda') @ ...`)
   chạy đúng, `torch.cuda.get_device_capability(0) == (12, 0)`.
4. **Quyết định có chủ đích**: KHÔNG update driver NVIDIA hệ thống dù đó là hướng "chính
   thống" hơn (bản mặc định cu130 của ComfyUI ngầm giả định driver mới) — update driver
   là thay đổi hệ thống rủi ro cao hơn nhiều (có thể cần khởi động lại, ảnh hưởng mọi
   phần mềm dùng GPU khác đang chạy, khó hoàn tác gọn), trong khi đổi phiên bản torch chỉ
   nằm gọn trong 1 virtualenv/embedded-python của riêng ComfyUI, hoàn toàn cô lập và dễ
   hoàn tác. Nếu người dùng khác gặp lại sự cố này: kiểm tra `nvidia-smi` → dòng
   "CUDA Version" → cài đúng kênh `pip install torch==2.8.0 torchvision torchaudio
   --index-url https://download.pytorch.org/whl/cu<XXX>` khớp (hoặc gần nhất, thấp
   hơn) con số đó, KHÔNG dùng bản mặc định bundled nếu GPU thuộc dòng RTX 50 (Blackwell).

### 16.6b Sự cố thứ 2: 16GB VRAM không đủ chạy đồng thời LLM + video local

Lần chạy `render/shots/0/regenerate-visual` (video) đầu tiên sau khi sửa timeout (mục
dưới) vẫn timeout, dù đã tăng `VIDEO_MAX_WAIT_SEC` lên 1500s — log ComfyUI cho thấy tốc
độ mỗi bước KSampler tăng đột biến (~51s/bước → 122s/bước) từ bước 7 trở đi, không phải
lỗi code. Nguyên nhân tìm ra qua `nvidia-smi --query-compute-apps`: **Ollama
(`llama-server.exe`) vẫn giữ nguyên `qwen3:14b` trong VRAM** (9.6GB) từ lần verify LLM ở
mục 16.2 — process idle nhưng chưa tự unload — cộng với Wan2.2 (~9.5GB) làm VRAM dùng
15.85/16.3GB (~97%), gây tranh chấp/thrashing giữa 2 model. `ollama stop qwen3:14b` treo
ở trạng thái "Stopping..." không giải phóng được (có thể vì GPU đang bận 100% cho
ComfyUI, driver không rảnh xử lý lệnh unload) — phải `Stop-Process -Force` thẳng tiến
trình `llama-server.exe`, giải phóng ngay ~8.5GB VRAM (15.85GB → 7.39GB). Sau đó chạy lại
sạch (VRAM 578MB lúc bắt đầu) — hoàn tất bình thường ở tốc độ ổn định, `visual_status=ready`.

**Bài học cho người dùng thật**: máy 16GB VRAM (RTX 5060 Ti và tương đương) **không đủ**
để LLM local (Ollama) và video/image local (ComfyUI) cùng resident VRAM một lúc — cần
unload model không dùng trước khi chạy tác vụ GPU nặng khác (`ollama stop <model>`, đợi
xác nhận qua `ollama ps` thật sự rảnh, không chỉ gọi lệnh). App hiện KHÔNG tự động điều
phối việc này (ngoài phạm vi việc này — tương đương `gpu_pool.py` của `ai-content-studio`,
xem phần "Không làm trong việc này" ở plan ban đầu).

### 16.6c Tăng `VIDEO_MAX_WAIT_SEC` (480s → 1500s)

Đo thật trên GPU này (RTX 5060 Ti): 1 clip Wan2.2 TI2V-5B ~8s tốn **7-18.5 phút** tuỳ
tải VRAM (20 bước KSampler, 1280×704, ~25-65s/bước lúc rảnh, gấp đôi lúc tranh VRAM với
Ollama) — vượt xa 480s (8 phút) cũ, vốn tune cho Sora/Veo (cloud). Tăng
`app/render/engine.py::VIDEO_MAX_WAIT_SEC` lên **1500s (25 phút)** — áp dụng chung cho
mọi provider video (kể cả Sora/Veo), không riêng local, nhưng an toàn vì cloud vốn nhanh
hơn nhiều nên không bao giờ chạm ngưỡng mới; chỉ local mới cần khoảng rộng này. Đợi
thêm không tốn phí (khác cloud tính tiền theo thời gian xử lý phía nhà cung cấp).

### 16.7 Tổng kết

Cả 4 nhóm task đều có provider local thật, verify qua đúng pipeline app (không chỉ
script test rời) trên project demo (`prj_demo_tlh`, kênh "Tâm Lý Học Đời Thường",
backend test chạy port 8757 — 8756 vẫn thuộc `ai-content-studio`):

| Task | Provider | Model | Hạ tầng | Kết quả verify |
|---|---|---|---|---|
| `llm` | `local` | qwen3:14b (Ollama) | `C:\Tools\Ollama` | Research pipeline thật, JSON hợp lệ, ~42 tok/s |
| `tts` | `piper` | vi_VN-vais1000-medium | `backend/models/piper/` | 10/10 shot narration ready, WAV thật |
| `image` | `local_sdxl` | SDXL base 1.0 | `C:\Tools\ComfyUI_extract` | Shot visual ready, ảnh thật 28.4s/ảnh |
| `video` | `local_wan` | Wan2.2 TI2V-5B | (cùng ComfyUI) | Shot visual ready, MP4 thật 7.875s, 7-18.5 phút/clip |

File adapter mới: `tts_piper.py`, `image_comfy_sdxl.py`, `video_comfy_wan.py`. File sửa:
`providers/factory.py` (nhánh `local_endpoint` cho asset provider), `routers/providers.py`
(bug dùng chung `_build_asset_provider`, bỏ giới hạn `local_endpoint` chỉ cho `llm`),
`render/engine.py` (`_TTS_EXT` thiếu piper, `VIDEO_MAX_WAIT_SEC`), `config.py`
(`PIPER_MODELS_DIR`), `ProviderSettings.tsx` (UI local cho cả 4 nhóm, `LOCAL_CATALOG`).
Hạ tầng cài ngoài repo (không commit): Ollama (`C:\Tools\Ollama`), ComfyUI
(`C:\Tools\ComfyUI_extract`), model weights (`backend/models/`, gitignored) — người
dùng khác cần tự cài lại theo hướng dẫn ở các mục 16.2-16.5 nếu muốn dùng local AI.

## 17. Cải thiện nhất quán Visual giữa các shot — Tier 1 (prompt/seed/color-grade) + Tier 2 (ảnh tham chiếu) (2026-08-13, vòng 9)

**Vấn đề người dùng phát hiện lúc test thật**: visual giữa các shot trong cùng 1 video
không đồng nhất về phong cách/tông màu, dù cùng 1 brand. Phân tích nguyên nhân (theo yêu
cầu "mô tả logic đang có + đề xuất cải tiến" trước khi code):

1. Prompt gửi cho provider ảnh/video (`app/render/engine.py::generate_visual_asset`)
   TRƯỚC ĐÂY chỉ là `shot.visual_fx` nguyên văn (LLM tự diễn giải lúc sinh script) —
   KHÔNG kèm `brand.visual_style_prompt` (style kênh) hay `shot.audio_sfx` (mô tả
   mood/nhạc nền), dù cả 2 đều là ngữ cảnh có sẵn.
2. Seed sinh ảnh/video hoàn toàn ngẫu nhiên theo `time.time()` mỗi lần gọi — không có
   cách nào giữ liên kết thị giác giữa các lần sinh, kể cả cùng 1 shot sinh lại.
3. Mỗi shot IMAGE/VIDEO sinh độc lập, không có cơ chế "ảnh tham chiếu" nào giữa các
   shot — khác hẳn cách 1 người dựng phim thật vẽ concept art rồi bám theo.
4. Ghép video (`assembly.py`) không có bước color-grade nào — lệch tông màu giữa các
   provider/model khác nhau (SDXL local vs OpenAI vs Gemini) không được kéo lại gần
   nhau ở bước cuối.

**Người dùng chọn triển khai CẢ 2 tầng đề xuất trong cùng phiên này:**

### Tier 1 — chi phí thấp, không đổi kiến trúc

- `_build_visual_prompt(shot, brand)` (mới, `engine.py`) — LUÔN nối `shot.visual_fx` +
  `shot.audio_sfx` (đóng vai "mood hint hình ảnh", có ghi rõ trong prompt là gợi ý
  không khí, KHÔNG PHẢI chỉ dẫn âm thanh — audio_sfx vốn không phải lời đọc, TTS hoá
  riêng từ `beat.audio`) + `brand.visual_style_prompt` (đọc qua
  `_load_brand_profile()`, file `brandprofile.json` cùng kênh) — thay cho việc chỉ gửi
  `visual_fx` trơn như trước. Bổ sung `audio_sfx` vào prompt theo đúng yêu cầu người
  dùng nêu giữa lúc triển khai Tier 1/2 ("thông tin Âm thanh & Nhạc nền cũng nên được
  đưa vào prompt tạo ảnh/video").
- `_deterministic_seed(project_id, shot_id)` (mới) — băm SHA-256 `"{project_id}:{shot_id}"`
  lấy 4 byte đầu làm seed, thay `int(time.time()*1000)` — mỗi shot trong 1 project có
  seed cố định, tái sinh cùng shot (VD đổi provider fallback) cho kết quả gần giống lần
  trước thay vì ngẫu nhiên hoàn toàn.
- `assembly.py::_COLOR_GRADE_FILTER` — filter ffmpeg `eq=contrast=1.04:saturation=1.06:
  brightness=0.01`, áp ĐỒNG NHẤT cho MỌI segment lúc ghép (`_build_segment`, nối tiếp
  sau `-vf scale=...`) — hệ số nhẹ, chủ đích không tạo hiệu ứng "phim màu" rõ rệt, chỉ
  kéo gần tông màu giữa các model/provider khác nhau.

### Tier 2 — ảnh "anchor" tham chiếu giữa các shot

Không dùng IPAdapter Plus (custom node cộng đồng, rủi ro tên/version lệch — đã cân nhắc
và loại khi khảo sát `ai-content-studio` ở mục 16.3) — chỉ dùng node **gốc** của
ComfyUI:

- `app/providers/base.py` — mở rộng chữ ký `ImageProvider.generate()` và
  `VideoProvider.generate()`/`start_generation()` thêm `seed: Optional[int] = None`,
  `reference_image: Optional[bytes] = None` — TUỲ CHỌN, provider không hỗ trợ (mọi
  adapter cloud: OpenAI/Gemini/Sora/Veo + stub) chỉ cần nhận rồi bỏ qua, không bắt buộc
  raise lỗi (tương thích ngược, đã cập nhật chữ ký ở `video_veo.py`, `image_openai.py`,
  `video_sora.py`, `image_gemini.py`, `stubs.py`).
- `image_comfy_sdxl.py::_build_img2img_workflow` — khi có `reference_image`: thêm
  `LoadImage` (ảnh phải upload trước qua `POST /upload/image`, xem `_upload_image()` —
  `LoadImage.image` chỉ nhận tên file có sẵn trong `input/` của chính ComfyUI, không
  nhận bytes trực tiếp qua JSON) → `ImageScale` (ép về đúng 1344x768, phòng lệch size)
  → `VAEEncode` (thay `EmptyLatentImage`) → `KSampler` với `denoise=0.6` (thay 1.0) —
  giữ lại bố cục/tông màu ảnh gốc, vẫn đủ "room" để nội dung mới theo prompt hiện ra.
  Không có `reference_image` → hành vi CŨ (txt2img thuần), không đổi.
- `video_comfy_wan.py::_build_txt2vid_workflow` — nối `LoadImage`+`ImageScale` vào input
  `start_image` (trước đó CỐ TÌNH để trống, xem mục 16.4 — node `Wan22ImageToVideoLatent`
  coi `start_image` là optional theo source `comfy_extras/nodes_wan.py`) khi có
  `reference_image` — video mở đầu bám đúng ảnh anchor thay vì khởi tạo latent từ noise
  thuần. `_upload_image()` dùng chung cơ chế `/upload/image` với adapter ảnh.
- `render/schemas.py::RenderState.anchor_image_path` (field mới) — lưu đường dẫn ảnh
  shot IMAGE **đầu tiên sinh thành công** của project; `engine.py::generate_visual_asset`
  tự set field này (không đổi lại nếu đã có) và đọc bytes qua `_read_anchor_image()`
  (trả `None` an toàn nếu file bị xoá/chưa có) để truyền làm `reference_image` cho MỌI
  shot ảnh/video sinh SAU trong project — cả 2 tầng nhất quán, không cần người dùng tự
  chọn ảnh tham chiếu.

**Verify thật qua GPU** (không chỉ code review):
- `image_comfy_sdxl.py`: gọi trực tiếp `generate()` 2 lần — txt2img (~12.2s) làm anchor,
  rồi img2img (~12.3s, cùng thời gian vì cùng 30 bước KSampler, denoise thấp hơn không
  đổi số bước) với `reference_image=<anchor bytes>` + prompt khác (thêm "con thuyền"). Kết
  quả: 2 ảnh giữ ĐÚNG bố cục/kiến trúc hải đăng, tông màu teal-cam, vị trí camera — chỉ
  thêm đúng phần tử mới theo prompt (thuyền ở biển) — xác nhận img2img hoạt động đúng ý
  đồ, không chỉ chạy không lỗi.
- `video_comfy_wan.py`: gọi `start_generation()` với `reference_image=<anchor bytes>` —
  ComfyUI CHẤP NHẬN job ngay (workflow validate qua được, thấy job trong
  `GET /queue` → `queue_running`, xác nhận node graph `LoadImage`→`ImageScale`→
  `start_image` nối đúng tên node/kiểu dữ liệu, không bị ComfyUI từ chối lúc submit).

**pytest**: 129/130 pass (backend, toàn bộ suite) — 1 lỗi còn lại là flake TIỀN TỒN TẠI
(UNIQUE constraint theo timestamp ID khi test chạy dồn dập, không liên quan thay đổi
này — pass khi chạy riêng lẻ, đã ghi nhận từ vòng 8).

File mới: không có (chỉ sửa file có sẵn). File sửa: `render/engine.py` (helper mới +
gọi seed/reference_image ở `generate_visual_asset`), `render/schemas.py`
(`anchor_image_path`), `render/assembly.py` (`_COLOR_GRADE_FILTER`), `providers/base.py`
(chữ ký ABC), `providers/image_comfy_sdxl.py` (img2img), `providers/video_comfy_wan.py`
(start_image), `providers/video_veo.py`/`video_sora.py`/`image_openai.py`/
`image_gemini.py`/`providers/stubs.py` (chữ ký tương thích, không đổi hành vi).

## 18. Thumbnail chuyển thành "anchor" bắt buộc — chốt sớm ở đầu Visual Studio (2026-08-13, vòng 9 tiếp theo)

**Yêu cầu người dùng**: chuyển "Tạo ảnh Thumbnail" từ Pack Review sang chốt SỚM hơn
(người dùng đề xuất "bước Outline & Hook"), bắt buộc DUYỆT Thumbnail trước khi cho sinh
asset ảnh/video ở Visual Studio, vì ảnh Thumbnail sẽ làm ảnh "anchor" (Tier 2, mục 17).

**Lệch có chủ đích so với đề xuất ban đầu của người dùng** (đã hỏi lại + được xác nhận
qua AskUserQuestion): KHÔNG đặt ở Outline & Hook (bước 1) mà đặt ở **đầu Visual Studio**
(bước 3) — vì `thumbnail_description` (mô tả để AI vẽ) được sinh từ TOÀN BỘ script đã
duyệt (`generation.py::generate_titles_and_meta`, cần `body` — chỉ có sau khi script
approve + breakdown), script CHƯA tồn tại ở Outline & Hook. Đặt ở đầu Visual Studio vẫn
giữ đúng tinh thần yêu cầu (chốt TRƯỚC khi sinh asset shot) mà không phải viết logic
sinh thumbnail-concept riêng biệt (chất lượng thấp hơn vì thiếu script thật).

**Thêm giữa chừng**: cho phép **upload ảnh Thumbnail có sẵn từ máy** (không chỉ sinh
bằng AI) — cùng vai trò anchor, không cần provider ảnh nào, hữu ích cho user chưa cấu
hình provider hoặc muốn dùng ảnh tự chụp/thiết kế sẵn.

### Thay đổi

- `app/schemas/__init__.py::YoutubeMeta` — thêm `thumbnail_approved: bool = False`, tự
  reset về `False` mỗi khi ảnh đổi (sinh lại AI hoặc upload ảnh khác — ảnh cũ đã duyệt
  không còn đúng nữa).
- `app/routers/pack.py` — thêm `POST /pack/thumbnail/upload` (multipart, PNG/JPEG/WEBP,
  lưu `assets/thumbnail.{ext}`, set `thumbnail_provider="upload"`) và
  `POST /pack/thumbnail/approve` (`{approved: bool}`, yêu cầu `thumbnail_status=="ready"`
  khi duyệt). `generate_thumbnail` (AI) cũng tự reset `thumbnail_approved=False`.
- `app/routers/pipeline.py::generate_visual_shots` (`/visual/generate`) — sinh SỚM
  `titles`/`youtube_meta` (tái dùng nguyên `generate_titles_and_meta`, không viết lại
  logic) NGAY khi vào Visual Studio, thay vì đợi `pack/build` (Pack Review). **Best-effort**
  — nuốt `NoProviderConfiguredError`, không chặn luồng NHẬP SCRIPT (import CSV/Excel)
  vốn phải chạy được với 0 provider AI (bất biến sản phẩm có test riêng,
  `tests/test_no_provider.py`) — thiếu provider thì `youtube_meta` đơn giản chưa có,
  người dùng vẫn dùng được đường upload tay (không cần AI) ở Visual Studio.
- `app/routers/pipeline.py::build_pack` (`/pack/build`) — SỬA để KHÔNG ghi đè
  `youtube_meta` nếu đã có sẵn (tránh xoá mất `thumbnail_status`/`thumbnail_asset_path`/
  `thumbnail_approved` — tất cả sống chung trong `youtube_meta`, gọi lại API cũ sẽ xoá
  luôn ảnh anchor đã duyệt mỗi lần quay lại Pack Review). Chỉ sinh (fallback, vẫn BẮT
  BUỘC provider) cho project chưa từng có `youtube_meta` (project cũ / edge case).
- `app/routers/render.py::_require_thumbnail_approved` (mới) — 400 rõ ràng nếu
  `pack.youtube_meta.thumbnail_approved` không true; áp cho `render/start` và
  `render/shots/{id}/regenerate-visual` (KHÔNG áp cho `regenerate-narration` — giọng đọc
  không liên quan ảnh anchor).
- `app/render/engine.py::_read_anchor_image` — SỬA để ưu tiên seed
  `state.anchor_image_path` từ `pack.youtube_meta.thumbnail_asset_path` (thumbnail đã
  duyệt) thay vì đợi "may rủi" shot ảnh đầu tiên nào sinh xong trước (logic cũ ở mục 17
  vẫn giữ lại làm fallback an toàn nếu vì lý do gì đó không có thumbnail path). Từ nay
  MỌI shot kể cả shot ĐẦU TIÊN đều có anchor ngay lập tức, không chỉ từ shot thứ 2 trở đi.
- Frontend: bỏ hẳn UI Tạo/Sửa Thumbnail khỏi `PackReview.tsx` (chỉ còn xem lại + tải ảnh,
  read-only, có ghi chú trỏ về Visual Studio). Thêm `ThumbnailCard` (component mới,
  `VisualStudio.tsx`) ở ĐẦU trang — 3 hành động (Tạo bằng AI / Upload ảnh từ máy / Duyệt),
  hiện rõ trạng thái đã/chưa duyệt. Nút "Sinh asset cho toàn bộ block" (header) + nút
  "Tạo ảnh/video" (từng `ShotCard`) đều `disabled` + tooltip giải thích khi
  `!pack.youtube_meta?.thumbnail_approved` — phản ánh đúng cổng chặn 400 phía backend,
  tránh người dùng bấm xong mới thấy lỗi.

### Verify thật (API trực tiếp qua backend đang chạy thật, project test tạo riêng rồi
archive lại sau khi xong — không đụng dữ liệu người dùng)

1. Tạo project mới → `research` → `gate1` → `script/approve` (đều qua LLM local
   qwen3:14b thật) → `visual/generate`: xác nhận `youtube_meta.thumbnail_description`
   TỰ ĐỘNG có sẵn (tiếng Việt, đúng ngữ cảnh script) mà KHÔNG cần gọi thêm request nào.
2. `render/start` trước khi duyệt Thumbnail → đúng 400 "Cần duyệt ảnh Thumbnail trước...".
3. `pack/thumbnail/upload` (ảnh lighthouse test từ mục 17) → `pack/thumbnail/approve` →
   `render/start` → 200, batch chạy nền thật.
4. Poll `render/status`: `anchor_image_path` tự seed ĐÚNG bằng đường dẫn ảnh vừa upload;
   shot đầu tiên (S01) sinh xong qua `local_sdxl` — tải ảnh xuống xem trực tiếp: giữ
   ĐÚNG bố cục/tông màu ảnh thumbnail gốc (hải đăng, vách đá, tông teal-cam), xác nhận
   img2img dùng đúng thumbnail vừa upload làm reference NGAY TỪ SHOT ĐẦU TIÊN (khác mục
   17 — lúc đó phải đợi tới khi 1 shot ảnh nào đó tự sinh xong mới có anchor).
5. Dừng batch (`render/cancel`) + archive project test, không để lại rác trong workspace
   dùng thật.

**pytest**: `test_render.py` (thêm `test_render_start_requires_thumbnail_approved` +
helper `_approve_fake_thumbnail`, bake vào `_drive_to_visual_studio`),
`test_no_provider.py` (sửa `test_pack_build_fails_without_provider_even_for_import` cho
đúng luồng mới — xoá provider TRƯỚC `/visual/generate` thay vì sau, để mô phỏng đúng
"chưa từng có provider" ở đúng điểm sinh meta mới) — 131/132 pass (1 lỗi còn lại là
flake tiền tồn tại, không liên quan, xem mục 17).

## 19. Sửa bug hiển thị Thumbnail + Thùng rác (Trash) + Lightbox xem full-size (2026-08-16)

### 19.1 Bug: upload/tạo AI lại ảnh Thumbnail nhưng ảnh không đổi trên UI

Người dùng báo 2 hiện tượng: (1) upload ảnh thumbnail xong ảnh không đổi, (2) bấm "Tạo
ảnh bằng AI" không có tác dụng. Verify thật qua backend đang chạy (project thật
`prj_1786626903294`, KHÔNG phải project test) — gọi `POST .../pack/thumbnail/generate`
trực tiếp: file `thumbnail.png` đổi thật (1729391 → 2044075 bytes, mtime cập nhật),
`thumbnail_status="ready"`, không lỗi. **Backend hoạt động đúng hoàn toàn** — bug 100%
ở frontend: `<img src={api.thumbnailUrl(project.id)}>` là URL CỐ ĐỊNH (không đổi theo
lần sinh/upload) — React chỉ refetch `<img>` khi giá trị `src` THẬT SỰ đổi, browser
cũng không tự biết ảnh phía sau URL đã đổi. Cả 2 "bug" người dùng báo thực ra là CÙNG 1
nguyên nhân.

Sửa: cache-bust bằng query string —
- `VisualStudio.tsx::ThumbnailCard` — state `cacheBust` (số tăng dần), bump sau MỖI lần
  `generate()`/`upload()` thành công, gắn `?v=${cacheBust}` vào URL.
- `PackReview.tsx` (đọc lại, không có action sinh/upload tại đây) — gắn
  `?v=${thumbnail_asset_path}` (đủ dùng vì mount lại là có `pack` mới từ server).

### 19.2 Thùng rác (Trash) — xoá kênh/project có thể khôi phục

Yêu cầu: "Cho phép xóa kênh và xóa project cho vào Thùng rác". Khảo sát trước khi code
phát hiện: `archived` (Channel/Project) đã tồn tại sẵn làm cơ chế soft-delete từ MVP
(`specs/02_database.md` §4 cũ: "archive, không xoá cứng file") nhưng **1 chiều, không
UI khôi phục** — `GET /channels`/`GET .../projects` lọc `archived==False`, xoá xong biến
mất VĨNH VIỄN khỏi tầm nhìn dù DB/file vẫn còn. Project còn KHÔNG có nút xoá nào trên UI
(chỉ có ở Channel/Dashboard). Không có `DELETE /channels/{id}` (chỉ `PATCH archived`),
không có xoá cứng thật (hard delete) ở đâu cả.

**Quyết định kiến trúc**: tái dùng NGUYÊN field `archived` làm trạng thái "trong Thùng
rác" (không thêm cột `deleted_at`/migration mới) — vì trong toàn bộ codebase, `archived`
CHỈ được dùng cho mục đích xoá, không có khái niệm "archive nhưng không phải xoá" nào
khác để xung đột.

- `app/config.py::delete_channel_dir`/`delete_project_dir` (mới) — `shutil.rmtree`,
  kiểm tra path thật sự nằm trong `CHANNELS_DIR` trước khi xoá (phòng vệ thêm dù
  channel_id/project_id luôn do server tự sinh).
- `app/routers/channels.py` — `POST /channels/{id}/restore`, `DELETE
  /channels/{id}/permanent` (CHỈ cho phép khi đã `archived=True`, xoá DB row — cascade
  ORM có sẵn sang Project/BrandProfileVersion — VÀ xoá thư mục trên đĩa).
- `app/routers/projects.py` — `POST /projects/{id}/restore`, `DELETE
  /projects/{id}/permanent` (tương tự, cascade PackVersion/RetentionEntry).
- `app/routers/trash.py` (router mới) — `GET /trash` gộp 2 danh sách (`archived=True`),
  project kèm `channel_name` (Thùng rác trộn project nhiều kênh khác nhau).
- Frontend: `screens/Trash.tsx` (màn mới) + nav "🗑 Thùng rác" ở Sidebar (ngang hàng
  Dashboard/⚙, `AppContext.tsx` thêm `view: "trash"` + `goTrash()`). Nút "Xoá dự án"
  MỚI THÊM ở header `ProjectView.tsx` (trước đó project hoàn toàn không có UI xoá).

**pytest** (`tests/test_trash.py`, mới, 6 test): archive→xuất hiện Thùng rác→restore→
biến mất khỏi Thùng rác (cả channel lẫn project); permanent-delete yêu cầu đã archive
trước (400 nếu chưa); permanent-delete xoá thật DB row (404 sau đó) VÀ thư mục trên đĩa.
Toàn bộ suite: 136/137 pass (1 flake tiền tồn tại không liên quan, xem mục 17).

**Phát hiện phụ lúc test thật** (không phải bug — báo lại cho người dùng, KHÔNG tự ý
sửa): kênh "Tâm Lý Học Đời Thường" hoá ra đã bị xoá (archived) lúc 14:46 cùng ngày —
audit log cho thấy hành động thật `"Xóa kênh"`, khả năng cao do người dùng tự bấm nhầm
nút xoá có sẵn (đã tồn tại từ trước, không phải tính năng mới) trong lúc app đang mở
test song song. 2 project của kênh (bao gồm project demo) còn nguyên trong Thùng rác —
người dùng được hỏi, chọn **để nguyên trong Thùng rác** (không khôi phục).

### 19.3 Lightbox — xem full-size ảnh/video

Yêu cầu: "Cho phép mở full ảnh/video visual và ảnh thumbnail ở Visual Studio và Pack
Review để xem kỹ hơn sau đó đóng lại được".

- `components/Lightbox.tsx` (mới) — overlay full-screen (tái dùng `.dialog-backdrop`,
  không dùng `.dialog` vì khung cố định 440px không hợp xem ảnh/video lớn), đóng bằng
  nút X / bấm ra ngoài / phím Esc. Export kèm `ExpandButton` — nút "phóng to" nhỏ đè góc
  khung preview, dùng riêng thay vì click thẳng lên `<video controls>` (tránh đụng
  control gốc play/pause/tua của trình duyệt).
- `VisualStudio.tsx` — `ShotPreview` (ảnh/video từng shot) + `ThumbnailCard` (ảnh
  Thumbnail) đều gắn `ExpandButton` + state lightbox riêng.
- `PackReview.tsx` — ảnh Thumbnail (tab Title & Thumbnail) gắn Lightbox tương tự. Thêm
  MỚI: mục "Shot List" (tab Full Script & Shot List) TRƯỚC ĐÂY chỉ hiện text (`visual_fx`
  + tag loại), KHÔNG hề thấy ảnh/video thật đã sinh — thêm `ShotThumb` (preview nhỏ
  56×40, bấm mở Lightbox) vào đầu mỗi dòng, đúng yêu cầu "xem kỹ hơn ở … Pack Review".

`npx tsc --noEmit` + `npm run build` (frontend) sạch sau cả 3 mục trên.

### 19.4 Bug: nút "Tải ảnh"/"Tải video" mở full ảnh/video, không tắt được

Người dùng báo nút "Tải ảnh" (Thumbnail, Pack Review) bấm vào MỞ HẲN ảnh full-size,
không có cách nào đóng lại. Nguyên nhân: nút đó vốn là `<a href={thumbnailUrl}
download="thumbnail.png">` — thuộc tính HTML `download` bị Chromium **âm thầm bỏ qua**
với URL **cross-origin** (giới hạn bảo mật chuẩn của trình duyệt) — frontend (Vite dev
server, cổng 5173) và backend (cổng do Electron cấp phát ngẫu nhiên mỗi lần chạy, xem
`electron/src/main.ts::findFreePort`) là 2 origin KHÁC NHAU (khác cổng = khác origin).
Mất `download` → trình duyệt rơi về hành vi mặc định: **điều hướng thẳng cả cửa sổ**
sang URL ảnh. Cửa sổ Electron kiểu kiosk (không thanh địa chỉ, không nút Back) → kẹt
luôn ở màn ảnh trần, không có cách thao tác quay lại app.

Rà soát phát hiện thêm 2 nút cùng lỗi CHƯA ai báo, cả 2 dùng `target="_blank"` thay vì
`download`: "Tải video" (Render Studio) và các link tải file export (Output Center,
"Xuất Pack" → JSON/Markdown). Electron 32 (bản đang dùng) mặc định **deny** mọi
`window.open()`/`target="_blank"` nếu main process không tự đăng ký
`setWindowOpenHandler` (không đăng ký ở `electron/src/main.ts`) → cả 2 nút này thực ra
**không làm gì cả** khi bấm.

Sửa tận gốc — bỏ hẳn cách dùng thẻ `<a href download>`/`target="_blank"` trỏ thẳng URL
backend, thay bằng `api/client.ts::downloadFile()` (helper mới): `fetch()` lấy file về
dạng `blob` (không bị giới hạn cross-origin như link navigation, chỉ cần CORS header —
backend đã có sẵn `allow_origins=["*"]`) → tạo `blob:` URL (LUÔN same-origin) → click
`<a download>` tạm trên blob URL đó → thu hồi URL. Áp dụng cho cả 3 nút:
`api.downloadThumbnail(id)` (Pack Review), `api.downloadRenderFile(id)` (Render Studio),
`api.downloadExportFile(id, filename)` (Output Center) — 2 nút sau mới sửa luôn dù chưa
ai báo, cùng gốc lỗi, để lại sẽ tiếp tục là nút chết. Tên file tải về ưu tiên đọc từ
header `Content-Disposition` server trả (VD `render/download` đổi đuôi theo codec
mp4/webm), fallback tên cố định/tên gốc nếu thiếu header.

## 20. Bug thật: anchor img2img "chảy" chữ/khung từ Thumbnail vào mọi shot (2026-08-16)

Người dùng báo: bấm "Tạo Visual" từng shot ở Visual Studio nhưng "ảnh tạo ra vẫn y hệt
như cũ, có vẻ không dùng ảnh thumbnail làm reference". Điều tra thật (không chỉ đọc
code) — tải lại `B02.png`/`B03.png` (2 shot người dùng vừa bấm tạo lại) và so với
`thumbnail.png`:

**Kết luận đầu tiên (đúng nhưng chưa đủ)**: anchor **CÓ** được dùng — cả B02 và B03 đều
copy gần nguyên khung gỗ chạm trổ + bố cục sông/cù lao của thumbnail, chữ bị vẽ lại
thành ký tự vô nghĩa (bằng chứng chắc chắn img2img đang chạy — txt2img thuần không thể
tự tạo trùng khung trang trí đó). Vấn đề thật: **`thumbnail.png` là 1 tấm bản đồ minh
hoạ dày đặc chữ/khung/mũi tên chú thích** (đúng kiểu thumbnail YouTube — "bold,
high-contrast", xem `pack.py::generate_thumbnail`) — dùng làm anchor cho b-roll khiến
MỌI shot đều dính khung/chữ rác giống hệt nhau, nhìn qua tưởng "không đổi gì".

**Sửa lần 1 (SAI hướng)**: hạ `_IMG2IMG_DENOISE` từ 0.6 → 0.45, tưởng sẽ giảm việc copy
chi tiết ảnh gốc. Test lại qua GPU thật với đúng prompt + anchor thật của B02 — kết quả
**TỆ HƠN**, ảnh gần như y nguyên thumbnail (kể cả ở 0.25, gần như bản sao 100%). Nguyên
nhân: hiểu sai chiều `denoise` — **giá trị CÀNG THẤP nghĩa là CÀNG BÁM ảnh gốc** (0.0 =
ảnh y nguyên, 1.0 = noise hoàn toàn = txt2img thuần), NGƯỢC với trực giác ban đầu.

**Sửa lần 2 (đúng, verify qua GPU thật nhiều mức)**: tăng `_IMG2IMG_DENOISE` — test
0.6 (gốc, bug) → 0.7 → 0.8, cùng 1 prompt/anchor/seed:
- 0.8: gần như bỏ qua hẳn anchor, kể cả màu sắc — không đạt mục đích "nhất quán".
- 0.7: giảm mạnh việc copy khung/chữ (không còn đọc được thước đo/mũi tên như 0.45),
  vẫn còn 1 dấu vết plaque nhỏ (`_IMG2IMG_EXTRA_NEGATIVE` chưa triệt tiêu 100% khi
  anchor quá nhiều chi tiết đồ hoạ — chấp nhận được, ưu tiên hơn 0.6/0.45 rõ rệt).
- **Control test** (ảnh anchor SẠCH — ảnh hải đăng chụp thật từ lúc verify Tier 2 gốc,
  mục 17): denoise 0.7 vẫn giữ ĐÚNG bố cục/tông màu/composition, xác nhận fix không làm
  hỏng trường hợp anchor tốt (ảnh chụp/minh hoạ đơn giản), chỉ giảm bớt lỗi khi anchor
  là ảnh nhiều chữ/UI.

**Chốt**: `_IMG2IMG_DENOISE = 0.7` (từ 0.6). Thêm `_IMG2IMG_EXTRA_NEGATIVE` (nối vào
negative prompt CHỈ ở nhánh img2img) — `"caption, subtitle, label, ornate frame,
border, sign, plaque, infographic, map legend, callout box, arrow annotation, ruler
markings"` — negative prompt chung `_NEGATIVE_PROMPT` (có sẵn "text") không đủ mạnh khi
latent khởi tạo (`VAEEncode`) đã mã hoá sẵn cấu trúc chữ/khung từ ảnh gốc.

File sửa: `app/providers/image_comfy_sdxl.py` (`_IMG2IMG_DENOISE`, `_IMG2IMG_EXTRA_NEGATIVE`,
comment giải thích lại đúng chiều `denoise` — comment cũ ở mục 17 cũng lẫn sai chiều dù
code khi đó tình cờ vẫn đúng vì 0.6 chưa phải cực đoan). Không đổi
`video_comfy_wan.py`/`start_image` (chưa có báo lỗi tương tự cho video, và Wan2.2 không
có tham số `denoise` cho `start_image` theo cùng cách — khác node).

pytest: 136/137 (1 flake tiền tồn tại khác, xem mục 17) — không có test tự động cho giá
trị `_IMG2IMG_DENOISE` cụ thể (phụ thuộc đánh giá thị giác qua GPU thật, không mock hợp
lý). Chưa regenerate lại được B02/B03 thật trong project của người dùng lúc viết mục
này — `thumbnail_approved` đang `False` (người dùng có vẻ vừa upload lại thumbnail
khác, cần tự bấm "Duyệt" lại ở Visual Studio trước khi sinh tiếp).

## 21. Tắt hẳn Tier 2 (anchor img2img) + audio_sfx chỉ vào prompt video (2026-08-16)

Sau mục 20 (hạ xuống rồi tăng lại `_IMG2IMG_DENOISE`), người dùng test tiếp bằng project
thật và báo: B02/B03 sinh ra **giống hệt thumbnail**, nội dung không liên quan gì tới
Visual/FX riêng của shot; B04/B05 test lại vẫn "giống ảnh cũ". Điều tra thêm (thử tăng
CFG 7→11 với đúng prompt+anchor thật) cho kết quả **TỆ HƠN** — chữ tiêu đề khổng lồ xuất
hiện (checkpoint SDXL liên hệ mạnh style "bản đồ cổ + isometric" với "thumbnail có chữ",
CFG cao càng đẩy sâu vào hướng đó). Xem ảnh so sánh đầy đủ trong lịch sử trò chuyện —
kết luận: **không có mức denoise/CFG nào vừa giữ phong cách Thumbnail vừa để nội dung
riêng từng shot hiện đúng**, khi Thumbnail là ảnh nhiều chi tiết đồ hoạ (bản đồ minh
hoạ). Hỏi lại người dùng — chọn **tắt hẳn Tier 2**, chỉ giữ Tier 1 (nhất quán qua text).

### Thay đổi

- `app/render/engine.py::generate_visual_asset` — `reference_image = None` cố định
  (không gọi đọc anchor nữa). Xoá hẳn `_read_anchor_image()` (0 caller sau khi tắt) và
  đoạn tự set `state.anchor_image_path` sau khi 1 shot ảnh sinh thành công (cũng hết tác
  dụng). Hạ tầng img2img/start_image trong `image_comfy_sdxl.py`/`video_comfy_wan.py`
  **GIỮ NGUYÊN** (đã verify hoạt động tốt với ảnh anchor sạch — ảnh hải đăng, mục 17) —
  chỉ tắt việc TỰ ĐỘNG gán Thumbnail làm anchor, không xoá năng lực adapter.
- `app/render/schemas.py::RenderState.anchor_image_path` — xoá field (không còn ai đọc/ghi).
- `app/routers/render.py::_require_thumbnail_approved` — xoá hẳn (cùng lý do: gate này
  chỉ có ý nghĩa khi Thumbnail còn là anchor bắt buộc). Bỏ gọi ở `start_render` và
  `regenerate_visual`. Thumbnail giờ KHÔNG còn chặn sinh asset ảnh/video — vẫn giữ
  nguyên chức năng tạo/upload/duyệt (dùng lúc xuất video lên YouTube, không đổi).
- Frontend (`VisualStudio.tsx`, `PackReview.tsx`) — bỏ mọi điều kiện `disabled`/tooltip
  gắn với `thumbnailApproved` ở nút "Sinh asset cho toàn bộ block" và "Tạo ảnh/video"
  từng shot; sửa lại copy ThumbnailCard/PackReview không còn nhắc "anchor"/"ảnh tham
  chiếu" (dễ gây hiểu lầm tính năng vẫn còn).
- `tests/test_render.py` — xoá `_approve_fake_thumbnail`, `test_render_start_requires_thumbnail_approved`
  (test cho hành vi đã bỏ); đơn giản hoá `_drive_to_visual_studio` (bỏ tham số
  `approve_thumbnail`).

### audio_sfx chỉ vào prompt VIDEO, không vào prompt ẢNH

Trong lúc test ở trên, phát hiện thêm: ảnh B02 (lúc còn Tier 2 bật) tự vẽ LUÔN 1
waveform giả + dòng chữ "[SFX]: Tiếng lật trang thư tịch cổ." / "[BGM]: Hạ tone..." lên
ảnh — vì `_build_visual_prompt` (mục 17/18) đưa `shot.audio_sfx` vào prompt cho CẢ ảnh
lẫn video, nhưng model ảnh tĩnh không có khái niệm "nhạc nền/nhịp điệu", nên vẽ luôn phần
mô tả đó thành chữ/UI trên ảnh thay vì chỉ dùng làm mood. Theo yêu cầu người dùng:
`_build_visual_prompt(shot, brand, *, is_video: bool)` — `audio_sfx` CHỈ nối vào prompt
khi `is_video=True`; ảnh tĩnh chỉ nhận `visual_fx` + `visual_style_prompt`.

### Verify thật (project thật của người dùng, KHÔNG phải project test)

Regenerate lại B02/B03/B05 qua đúng API `render/shots/{id}/regenerate-visual` sau khi
restart app với cả 2 fix — cả 3 đều: hết hẳn hiện tượng giống thumbnail/chữ rác, nội
dung bám đúng mô tả riêng shot (B02: đúng bản đồ Nam Bộ 1784 với label "VỌNG CÁC (XIÊM)"/
"20.000"/"HÀ TIÊN – RẠCH GIÁ" như prompt yêu cầu, chữ đọc được vì không còn nhiễu từ
img2img; B03: cảnh người trên thuyền — đúng ý cốt lõi dù chưa bám 100% mood "đêm/đuốc";
B05: bản vẽ concept art trang phục nhân vật — khớp phong cách concept sheet). Dừng
test thêm giữa chừng khi phát hiện project người dùng đã sang bước ghép (`assembly_status:
"done"`, `final_video_path` có sẵn) — người dùng đang thao tác song song thật, tránh can
thiệp thêm vào dữ liệu của họ.

pytest: 136/137 (1 flake tiền tồn tại, không liên quan) + `tsc --noEmit`/`npm run build`
sạch sau cả 2 fix.

## 22. OmniVoice — tích hợp TTS local voice cloning + fix tranh chấp VRAM với LLM local (2026-08-16)

### Tích hợp OmniVoice (Phase 1 + 2)

Người dùng đề xuất OmniVoice (k2-fsa/OmniVoice, zero-shot voice cloning, Apache-2.0) làm
provider TTS local mới, tận dụng Voice Cloning làm "giọng thương hiệu" cố định theo kênh.
Verify độc lập trước khi làm: repo đang phát triển tích cực (9155 sao, push gần nhất
2026-08-10), tiếng Việt có 8482 giờ dữ liệu training (không phải hỗ trợ hình thức), model
nhẹ (~3.3GB trên đĩa). Bỏ đề xuất #3 của người dùng (map `brand_voice.tone` → Voice
Design) vì tài liệu OmniVoice ghi rõ Voice Design chỉ ổn định cho tiếng Trung/Anh — sản
phẩm này tiếng Việt là ngôn ngữ duy nhất, rủi ro chất lượng cao hơn giá trị mang lại.

**Kiến trúc**: khác đề xuất ban đầu của người dùng (`connection_type: local_engine`,
gọi in-process) — chạy như **service HTTP riêng** (`backend/local_servers/omnivoice_server.py`,
venv cô lập `C:\Tools\OmniVoice\.venv`, KHÔNG chung `backend/.venv`), đúng pattern đã có
cho Ollama/ComfyUI. Lý do: (1) backend chính chưa có torch, đưa vào sẽ phình + rủi ro
xung đột version; (2) tận dụng được `gpu_lock` sẵn có (chỉ khoá được lệnh gọi HTTP tới
process riêng, không khoá được code chạy in-process); (3) không cần `connection_type`
mới — nhánh `local_endpoint` + `base_url` hiện có (giống ComfyUI) đã đủ.

`torch==2.8.0+cu129` (không theo gợi ý cu128 của README OmniVoice) — máy này (RTX 5060
Ti, Blackwell/sm_120) đã xác nhận cu126 thiếu kernel cho sm_120, cu130 crash với driver
hiện tại (mục 16.2); cu128 chưa được OmniVoice test trên Blackwell, rủi ro lặp lại lỗi
cu126, nên pin thẳng bản đã biết chạy đúng.

Adapter `tts_omnivoice.py` (HTTP client, mẫu `image_comfy_sdxl.py`) + mở rộng
`TTSProvider.synthesize()` thêm `reference_audio: bytes | None` (provider khác nhận rồi
bỏ qua, không bắt buộc raise). Phase 2: `BrandProfile.voice_clone_ref_path` +
endpoint upload/lấy mẫu giọng (`POST/GET /channels/{id}/brandprofile/voice-sample`),
`generate_narration_asset` tự đọc mẫu giọng kênh (nếu có) làm `reference_audio`.

Bug phát hiện lúc test thật (không phải code review):
- `model.generate()` trả về **list 1 phần tử** (numpy array), không phải array trực
  tiếp; sample rate đọc từ `model.sampling_rate`, không phải `sample_rate` (đoán sai lúc
  đầu, gây lỗi `soundfile.LibsndfileError: Format not recognised` — sửa bằng cách đọc
  trực tiếp giá trị trả về + grep docstring gốc của package, không đoán tiếp).
- Voice Cloning không kèm `ref_text` → tự kích hoạt Whisper ASR (`whisper-large-v3-turbo`,
  ~1.6GB) tải lần đầu — không phải bug, chỉ cần timeout client đủ rộng cho request đầu.

### Bug thật: tranh chấp VRAM giữa OmniVoice (TTS) và LLM local (Ollama)

Lúc verify Phase 2 trên project test, gọi `POST /projects/{id}/research` **thất bại hẳn**
(timeout, không phải chỉ chậm) — `pack.research` vẫn `null` sau đó. Root-cause qua
`nvidia-smi` + `curl :11434/api/ps`: ComfyUI (đã dùng cho Visual Studio trước đó) +
OmniVoice cùng thường trú VRAM ~12.1GB/16GB (RTX 5060 Ti), Ollama nạp thêm `qwen3:14b`
(~9.6GB) làm tràn hẳn, không có cơ chế nào giải phóng OmniVoice cho LLM local như đã có
theo chiều ngược lại (`render/engine.py::_free_llm_vram_if_local` giải phóng Ollama
trước khi sinh Image/Video local).

**Fix** — mirror đúng pattern đã có, chiều ngược lại:
- `omnivoice_server.py` — thêm `POST /unload` (giải phóng `_model` + `torch.cuda.empty_cache()`)
  và lazy-reload trong `/synthesize` (`if _model is None: _load_model()`) — model đã cache
  sẵn trên đĩa nên nạp lại nhanh, không cần giữ server ở trạng thái loaded/unloaded phức
  tạp.
- `tts_omnivoice.py::OmniVoiceProvider.unload()` — best-effort HTTP POST `/unload`, nuốt
  lỗi (dọn VRAM thất bại không nên chặn luồng LLM chính).
- `factory.py::_free_local_tts_vram(db)` — tìm config TTS local_endpoint/omnivoice đang
  bật, gọi `unload()`. Wire vào `get_llm()`: gọi `_free_local_tts_vram(db)` ngay trước khi
  build provider LLM, CHỈ khi provider LLM sắp dùng là `local_endpoint` (khớp đề xuất mới
  nhất của người dùng: ưu tiên TTS+Image chạy local, LLM có thể qua API cloud — nhánh này
  không chạy nếu LLM là cloud, TTS/Image local được giữ nguyên VRAM, không bị đụng tới).

**Trở ngại lúc verify — 2 process OmniVoice server cũ (stale) vẫn chạy song song**: 1 dùng
venv cô lập đúng, 1 dùng Python hệ thống (chắc còn sót lại từ lúc test trước đó trong
phiên) — CẢ HAI đều khởi động TRƯỚC khi thêm route `/unload` vào file, nên
`POST :8199/unload` trả về `404 Not Found` dù code đã đúng (uvicorn không có `--reload`
cho script này, không tự nạp lại code). Phát hiện bằng cách gọi `/unload` thủ công và
thấy 404 thay vì tin code đã đúng là xong. Xử lý: kill cả 2 process cũ, khởi động lại 1
process duy nhất từ venv cô lập đúng (`C:\Tools\OmniVoice\.venv`).

**Verify thật (real GPU, không mock)** trên project test `prj_1786874025067`:
- Đo floor VRAM khi không có model AI nào nạp: **3375 MiB** (Electron/Chrome/Windows nền
  — không đổi được, không phải phần app quản lý).
- Warm OmniVoice (`/synthesize`) rồi gọi thật `POST /projects/.../research` qua đúng API
  pipeline (`pipeline.py::run_research` → `get_llm()`) — poll `GET :8199/health` mỗi
  ~300ms: **flip `ok:true → ok:false` trong vòng ~380ms** sau khi request bắt đầu, xác
  nhận `_free_local_tts_vram` được gọi ĐÚNG lúc, không phải side-effect khác. Research
  hoàn tất `HTTP 200` với nội dung outline/hook thật (LLM sinh, không phải fallback) —
  `ollama api/ps` xác nhận `qwen3:14b` nạp thành công, VRAM đỉnh **13485 MiB / 16311 MiB**
  — trong ngân sách, không còn tràn.
- **Rủi ro còn lại, ghi nhận không xử lý ngay** (đúng nguyên tắc không xây trước khi có
  bằng chứng cần): fix này chỉ giải phóng OmniVoice, KHÔNG giải phóng checkpoint SDXL của
  ComfyUI trước khi LLM cần VRAM. Nếu ComfyUI vừa sinh ảnh/video xong (checkpoint còn
  "nóng" trong VRAM) VÀ OmniVoice cũng đang nạp VÀ LLM local cần nạp cùng lúc, vẫn có thể
  tràn (SDXL ~6-7GB tự nó đã gần bằng toàn bộ phần fix này giải phóng được). Đo thật lúc
  verify: `system_stats` của ComfyUI cho thấy nó tự giải phóng VRAM giữa các lần sinh
  (torch_vram gần 0 khi rảnh), nên rủi ro này hiếm gặp trong thực tế nhưng chưa loại trừ
  hẳn. Không xây thêm `_free_comfy_vram_if_local` ở đợt này — nếu người dùng báo lại lỗi
  tương tự cụ thể, xử lý tiếp lúc đó.

### 2 bug thật phát hiện lúc người dùng tự test tính năng (sau khi fix VRAM ở trên)

**Bug 1 — Test connection báo lỗi sai khi model OmniVoice đang ở trạng thái "chưa nạp" bình
thường**: người dùng bấm "Test" ở Cài đặt → Provider AI, nhận `"✗ OmniVoice server đang
chạy nhưng model chưa load xong — thử lại sau vài giây"` — đúng lúc model vừa bị
`/unload` (do fix VRAM ở trên vừa gọi, hoặc do LLM local vừa chạy trước đó). Nguyên nhân:
`GET /health` cũ trả `{"ok": _model is not None}` — coi "chưa nạp" (giờ là trạng thái BÌNH
THƯỜNG, không phải lỗi khởi động) như lỗi kết nối. Fix: `/health` tách 2 khái niệm —
`ok` = server process sống (luôn đủ để dùng, `/synthesize` tự nạp lại), `model_loaded` chỉ
mang tính thông tin. `tts_omnivoice.py::test_connection()` đọc `model_loaded` để hiển thị
đúng thông báo ("model hiện chưa nạp — sẽ tự nạp lại ở lần sinh giọng đọc tiếp theo") thay
vì báo lỗi. Verify thật: gọi `/unload` thủ công rồi test lại qua đúng API `POST
/providers/{id}/test` mà UI dùng — trước fix sẽ vẫn báo lỗi cũ (chưa test vì phát hiện
bug trước khi kịp), sau fix trả `ok:true` kèm thông báo đúng.

**Bug 2 — Upload mẫu giọng MP3 có thể bị từ chối nhầm**: người dùng hỏi định dạng hỗ trợ,
kiểm tra lại thấy `upload_voice_sample` (`channels.py`) chỉ nhận diện định dạng qua
`file.content_type` do trình duyệt/OS gửi lên — nhiều máy Windows KHÔNG đăng ký đúng MIME
cho `.mp3` (báo `application/octet-stream` hoặc rỗng thay vì `audio/mpeg`), khiến file
MP3 hợp lệ bị từ chối với `400 Chỉ nhận audio WAV/MP3` dù đúng định dạng. Fix: thêm
fallback theo đuôi file thật (`Path(file.filename).suffix`) khi content-type không nhận
diện được, mở rộng thêm vài biến thể MIME MP3/WAV ít gặp. Verify thật (không chỉ code
review) bằng `httpx` giả lập đúng lỗi gốc — upload `.mp3`/`.wav` với content-type
`application/octet-stream` (giả lập Windows không nhận diện) → cả 2 đều `200`, lưu đúng
đuôi; upload `.ogg` (định dạng thật sự không hỗ trợ) vẫn `400` đúng như thiết kế.

Cả 2 fix cần **restart process** mới có hiệu lực (`omnivoice_server.py` không có
`--reload`; backend do Electron spawn cũng không có `--reload`) — đã restart cả 2 và
verify lại qua API thật sau restart, không chỉ tin code đã sửa là xong (bài học lặp lại
từ chính mục 22 phần trên — lúc đó cũng có 2 process OmniVoice server cũ chưa restart làm
`/unload` trả 404 dù code đã đúng).

pytest: 136/136 pass sau cả 2 fix (`-p no:randomly` — loại bỏ flake trùng ID timestamp tiền
tồn tại khi chạy full suite quá nhanh).

pytest: 132/137 pass khi chạy full suite nhanh (4 fail do trùng ID timestamp — lỗi test
isolation tiền tồn tại, không liên quan thay đổi này, xác nhận bằng cách chạy riêng lẻ cả
4 test đều pass). `_free_local_tts_vram` không có test riêng (phụ thuộc hạ tầng GPU thật,
theo đúng quy ước đã áp dụng cho các adapter local khác — không viết test mock cho phần
này).

## 23. Flux (Black Forest Labs) — Image + Video thật (2026-08-16)

Người dùng yêu cầu: implement API Image cho Flux + hướng dẫn lấy API key, đảm bảo dùng
"model phù hợp nhất đang có trên thị trường", và đánh giá "Flux có tạo được video không?".

**Research trước khi code** (WebSearch/WebFetch trực tiếp — không dùng kiến thức cũ, vì
catalog Flux hiện có trong repo (`flux-1.1-pro`, `flux-schnell`, ở `stubs.py`/
`ProviderSettings.tsx`) đã lỗi thời): BFL đã chuyển hẳn sang thế hệ **FLUX.2** cho ảnh —
đọc trực tiếp OpenAPI spec `api.bfl.ai/openapi.json` để lấy đúng field request/response
(không đoán theo tên biến hay gặp). Phát hiện thêm ngoài yêu cầu ban đầu: **FLUX 3**
(23/7/2026) là model video CHÍNH THỨC của BFL, generally available qua API — trả lời
trực tiếp câu hỏi "Flux có tạo video không? CÓ", và implement luôn provider Video thay
vì chỉ trả lời bằng lời.

### Quyết định model mặc định

- **Image: `flux-2-pro`** (không phải `-preview`, không phải `-max`) — `-preview` là
  alias luôn trỏ bản mới nhất (hành vi có thể đổi bất ngờ giữa các lần gọi, đi ngược
  khuyến nghị tái lập kết quả của chính BFL); `-max` chất lượng cao hơn nhưng ~2.3x giá,
  không đáng ép mặc định cho project 10-20 shot ảnh. `-pro` là mức cân bằng, được mô tả
  là dẫn đầu photorealism 2026 trong tài liệu research được.
- **Video: `flux-3-video-hd`** (720p, $0.17/s) làm mặc định thay vì `-fhd` (1080p,
  $0.29/s) — cùng triết lý cân bằng chi phí/chất lượng, người dùng tự đổi qua
  `model_name` nếu cần 1080p.

### Kiến trúc

`flux_common.py` (mới) — helper DÙNG CHUNG cho `image_flux.py` + `video_flux.py`: cả 2
gọi API BFL qua CÙNG 1 cơ chế submit-rồi-poll (`POST /v1/{model}` → `{id, polling_url}`
→ `GET /v1/get_result?id=` lặp tới khi `status == "Ready"`) — khác Sora/Veo (2 hãng
riêng, không tách chung code được), đây là 2 sản phẩm CÙNG hãng CÙNG cơ chế nên tách
dùng chung hợp lý, tránh 2 bản poll-loop gần như giống hệt nhau.

- `image_flux.py::FluxImageProvider.generate()` — ĐỒNG BỘ (block tới khi xong, dùng
  `flux_common.poll_until_ready` tự lặp bên trong) để khớp `ImageProvider.generate()`,
  cùng cách OpenAI/Gemini Image đã làm (chạy trong background task, block không sao).
  Nhận `reference_image` (base64 qua `input_image`, cho Tier 2 nếu bật lại sau — hiện
  tắt toàn app, mục 21).
- `video_flux.py::FluxVideoProvider` — BẤT ĐỒNG BỘ đúng nghĩa `VideoProvider`
  (`start_generation`/`poll_generation`, đúng convention Sora/Veo) — `poll_generation()`
  CHỈ gọi 1 lần rồi trả ngay, vòng lặp chờ thật nằm ở
  `render/engine.py::_poll_video_until_done` (không dùng `poll_until_ready` — hàm đó tự
  lặp, chỉ hợp cho Image gọi đồng bộ 1 lần). `generate_audio=False` CỐ ĐỊNH trong request
  — FLUX 3 Video sinh audio đồng bộ (thoại/SFX) ngay trong clip, nhưng
  `render/assembly.py::_build_segment` LUÔN ghép `-map 0:v:0 -map 1:a:0` (chỉ lấy stream
  video từ asset, audio luôn lấy riêng từ narration TTS) — audio Flux sinh ra bị bỏ hẳn
  lúc ghép, tắt để khỏi trả phí/thời gian sinh audio vô ích.
- `factory.py` — `_IMAGE_ADAPTERS["flux"]` trỏ `FluxImageProvider` (thay stub cũ),
  `_VIDEO_ADAPTERS["flux"]` thêm mới `FluxVideoProvider` — 2 dict riêng theo task nên
  cùng `provider_name="flux"` ở cả 2 không xung đột.
- `stubs.py` — xoá `FluxImageProvider` (stub cũ, đã thay bằng bản thật).
- `render/engine.py` — `_IMAGE_COST_FN`/`_VIDEO_COST_FN` thêm `"flux"`.
- `routers/providers.py::CLOUD_MODELS["flux"]` cập nhật danh sách model Image mới,
  `CLOUD_MODELS_BY_TASK[("video","flux")]` thêm mới.
- `ProviderSettings.tsx::CLOUD_CATALOG` — cập nhật entry `image.flux` (model mới), thêm
  entry `video.flux` mới.

### Hướng dẫn lấy API key (cho người dùng)

Đăng ký tại **bfl.ai** → vào mục API/Dashboard → tạo API key mới (chuỗi, không có tiền
tố `sk-...` như OpenAI) → **nạp tiền trước khi dùng** (pay-as-you-go, 1 credit = $0.01
USD, KHÔNG có gói miễn phí lâu dài) → dán key vào Cài đặt → Provider AI → Thêm provider
→ chọn "Flux" (mục Image hoặc Video, 2 mục riêng) → dán key, chọn model (`flux-2-pro`
cho ảnh, `flux-3-video-hd` cho video, đều là lựa chọn đầu/mặc định trong danh sách).

### Verify được KHÁ NHIỀU dù không có API key thật — phát hiện 1 sai lầm thiết kế thật

Không có API key BFL (2026-08-16), nhưng thay vì chỉ dựng theo tài liệu rồi để đó, gọi
THẬT API bằng key GIẢ để dò chính xác hành vi lỗi — phát hiện **thiết kế ban đầu của
`test_connection()` SAI**: định dùng `GET /v1/get_result` (id giả) làm cách check kết
nối MIỄN PHÍ, giống OpenAI/Gemini (`GET /v1/models`). Test thật:

```
GET /v1/get_result?id=00000000-...  + key giả     -> 404 "Task not found"
GET /v1/get_result?id=00000000-...  + KHÔNG có key -> 404 "Task not found" (Y HỆT!)
POST /v1/flux-2-pro (key sai định dạng)            -> 422 "Invalid API key format"
POST /v1/flux-2-pro (key đúng định dạng, sai)      -> 403 "Not authenticated"
```

`get_result` không hề kiểm tra auth khi task không tồn tại — 2 dòng đầu giống hệt nhau
dù CÓ hay KHÔNG CÓ key chứng minh điều đó. Nếu không tự test mà chỉ tin theo suy luận
"REST API chuẩn thường trả 401/403 cho key sai", `test_connection()` sẽ LUÔN báo "kết
nối thành công" bất kể key đúng hay sai — bug im lặng, chỉ lộ ra khi người dùng thật sự
dùng key sai và không được cảnh báo.

**Sửa**: `flux_common.py::check_auth()` viết lại — POST 1 job ảnh THẬT tới model RẺ NHẤT
(`flux-2-klein-4b`, $0.014/MP) ở kích thước nhỏ nhất hợp lệ (256x256 = 0.0655MP) → chi
phí thật ~$0.0009/lần bấm Test. KHÔNG miễn phí tuyệt đối như OpenAI/Gemini (BFL không có
endpoint auth-check riêng) — nói rõ trong message trả về cho người dùng biết, không giấu.
Dùng CHUNG hàm này cho cả `video_flux.py::test_connection()` (cùng 1 key/tài khoản BFL)
— tránh phải submit job video thật (tối thiểu 5s × $0.17-0.29/s = $0.85-1.45/lần) chỉ để
xác thực kết nối.

Phần CÒN LẠI chưa verify được (không có key thật để hoàn tất): đường THÀNH CÔNG thật sự
(sinh ảnh/video khi key ĐÚNG) — request/response dựng đúng theo OpenAPI spec chính thức,
không đoán, nhưng nếu lệch so với API thật, sửa theo lỗi thật khi người dùng test bằng
key thật (cùng mức rủi ro đã ghi ở `video_veo.py`/`video_sora.py`).

pytest: 136/136 pass (`-p no:randomly`) sau khi thêm 3 file mới + wire factory/engine/
routers — không viết test riêng cho `image_flux.py`/`video_flux.py`/`flux_common.py`
(phụ thuộc API key thật, theo đúng quy ước đã áp dụng cho toàn bộ adapter cloud khác
trong repo — test chỉ verify wiring/factory, không mock gọi API thật).

## 24. Bug thật: mẫu giọng thương hiệu quá dài làm OmniVoice lẫn nội dung tham chiếu vào narration (2026-08-16)

Người dùng báo: "Đoạn Voice của B02 dùng voice clone bị lẫn nội dung của audio sample
với nội dung cần đọc". Điều tra thật (không chỉ đọc code):

1. Đo mẫu giọng thương hiệu người dùng đã upload (`voice_sample.mp3`,
   `ch_1786626899972`) bằng `ffprobe` — **dài 57.7 giây**.
2. Đọc source thật của package `omnivoice` (`omnivoice/models/omnivoice.py`, cài ở
   `C:\Tools\OmniVoice\.venv`) — xác nhận `create_voice_clone_prompt()` tự động trim
   mẫu >20s (`trim_long_audio`, cắt tại điểm lặng lớn nhất) khi thiếu `ref_text`, NHƯNG
   docstring chính package cảnh báo mẫu **>10s** đã "may cause slower generation, higher
   memory usage, and degraded voice cloning quality" — khuyến nghị 3-10s. App này chưa
   hề tự trim ở bước upload, chỉ dựa hoàn toàn vào auto-trim 20s (quá rộng) của model.
3. Đối chiếu số liệu thật để xác nhận đúng hiện tượng (không chỉ tin theo cảnh báo
   trong docstring): tính ký tự/giây từng shot từ `narration_duration_sec` thật (API
   `render/status`) so với độ dài text thật (`pack.json::script.body[].audio`):

   | Provider | Ký tự/giây |
   |---|---|
   | Piper (baseline, 9 shot) | ~26-29 |
   | Gemini (B01) | ~13.7 |
   | **OmniVoice (B02/B03, TRƯỚC fix)** | **~7.2** |

   OmniVoice chậm gần **4 lần** Piper — không phải do giọng đọc tự nhiên chậm (brand
   voice chỉ yêu cầu "nhịp điệu vừa phải"), mà khớp chính xác dấu hiệu model đang phát
   thêm nội dung ngoài text mục tiêu (lẫn nội dung tham chiếu), đúng như người dùng mô tả.

### Fix

`app/routers/channels.py::_trim_voice_sample()` (mới) — cắt mẫu giọng về tối đa **10
giây** (`ffmpeg -t 10 -af afade=out`, có fade-out 0.3s cuối tránh tiếng "pop" khi cắt
đột ngột) ngay lúc upload (`upload_voice_sample`), best-effort (không có ffmpeg/ffprobe
→ bỏ qua, không chặn upload). Chủ động cắt SỚM hơn hẳn ngưỡng auto-trim 20s của model —
bám sát khuyến nghị 3-10s thay vì để model tự xử lý mẫu quá dài.

### Verify thật (real GPU, dữ liệu thật của người dùng)

Cắt lại mẫu hiện có của người dùng bằng đúng lệnh trên (giữ bản gốc ở
`voice_sample.mp3.backup_original` — KHÔNG xoá, phòng người dùng muốn cắt lại đoạn
khác), gọi thật `POST render/shots/B02(và B03)/regenerate-narration` qua API:

| Shot | Trước (57.7s ref) | Sau (10s ref) | Ký tự/giây sau |
|---|---|---|---|
| B02 (526 ký tự) | 72.76s | **23.4s** | 22.5 |
| B03 (511 ký tự) | 71.72s | **22.4s** | 22.8 |

Cả 2 giảm hơn 2/3 thời lượng, ký tự/giây trở về mức hợp lý (gần bằng baseline Piper
~26-29, không còn là outlier ~7.2) — xác nhận fix giải quyết đúng triệu chứng người dùng
báo, không chỉ suy luận theo tài liệu package.

pytest: 136/136 pass (`-p no:randomly`; 1 lần chạy full suite nhanh có thêm vài fail do
đúng flake trùng ID timestamp tiền tồn tại — xác nhận lại bằng cách chạy riêng lẻ đều
pass, không liên quan thay đổi này).

### Cập nhật: báo cho người dùng biết lúc trim + bug thật thứ 2 bắt được lúc verify (2026-08-16, tiếp theo)

Người dùng yêu cầu: khi upload mẫu giọng bị tự động cắt 10s, phải BÁO rõ cho người dùng
biết (mục "Chưa làm" ở trên). Đã làm:

- `upload_voice_sample` trả thêm 2 field KHÔNG persist vào BrandProfile —
  `voice_sample_trimmed: bool`, `voice_sample_original_duration_sec: float | None` — chỉ
  để frontend hiện 1 lần ngay sau upload, không lưu lại DB/schema thật.
- `ChannelDialog.tsx` — thêm state `voiceNotice`, hiện dòng thông báo màu accent ngay
  dưới nút upload khi `voice_sample_trimmed === true`: "Đã tự động cắt mẫu còn 10 giây
  (mẫu gốc XX giây)...". Xoá mẫu (nút "Xoá") cũng xoá luôn thông báo cũ.
- `types.ts::VoiceSampleUploadResult` (mới, extends `BrandProfile`) — type riêng cho
  response endpoint này, không làm "bẩn" type `BrandProfile` dùng chung ở GET/PUT khác.

**Bug thật thứ 2 bắt được lúc verify tính năng này (không phải code review)** — gọi lại
API thật để kiểm tra tính năng vừa xong thì phát hiện `_trim_voice_sample` (viết ở mục
24 trên) **CHƯA BAO GIỜ trim thành công** kể từ lúc build, luôn âm thầm trả
`(False, None)`: `tmp_path = path.with_suffix(path.suffix + ".trim")` tạo tên file
**`voice_sample.mp3.trim`** — ffmpeg suy ra định dạng output từ đuôi file cuối cùng
(`.trim`, không phải định dạng hợp lệ), báo lỗi "Unable to choose an output format" và
thoát non-zero, bị nuốt bởi `except Exception: return False, None`. Vì hàm không raise
ra ngoài (chủ đích: lỗi trim không nên chặn upload) VÀ vì code review/pytest không gọi
ffmpeg thật, bug này không lộ ra cho tới khi verify thật bằng API call thứ 2 (mục 24 lúc
đầu chỉ verify bằng cách TỰ TAY chạy `ffmpeg` đúng cú pháp qua bash, KHÔNG phải gọi qua
chính hàm `_trim_voice_sample` — sai lầm phương pháp: verify "kết quả cuối" (B02/B03
duration giảm) chứ chưa verify "đường code thật" chạy qua, 2 việc khác nhau).

Phát hiện bằng cách: thêm `print()` debug tạm (bắt cả nhánh không tìm thấy ffmpeg lẫn
stderr thật của ffmpeg khi thất bại) vào đúng backend đang chạy, gọi lại API thật, đọc
log qua `[backend]` prefix trong log Electron — thấy rõ
`Unable to choose an output format for '...voice_sample.mp3.trim'`. Sửa:
`tmp_path = path.with_name(f"{path.stem}_trim{path.suffix}")` (→ `voice_sample_trim.mp3`,
đuôi thật ffmpeg nhận diện được). Xoá debug print sau khi xác nhận fix đúng.

**Verify lại thật sau fix**: gọi `POST voice-sample/upload` với mẫu 57.68s qua API —
response `{"voice_sample_trimmed": true, "voice_sample_original_duration_sec": 57.678367}`,
`ffprobe` xác nhận file lưu trên đĩa đúng `10.000000` giây.

pytest: 136/136 pass (`-p no:randomly`) sau fix. tsc --noEmit sạch.

## 25. Tải file Excel mẫu nhập kịch bản ở bước Outline & Hook (2026-08-16)

Người dùng yêu cầu: cho phép tải template Excel ở bước Outline & Hook để nhập kịch bản
đúng format (tính năng nhập CSV/Excel đã có từ vòng 4, nhưng chưa có cách lấy đúng file
mẫu — người dùng phải tự đoán tên 6 cột).

`backend/app/pipeline/script_import.py::build_template_workbook()` (mới) — sinh file
`.xlsx` bằng `openpyxl` (thư viện đã có sẵn, không thêm dependency) với ĐÚNG header 6 cột
lấy từ `COLUMN_KEYWORDS` (nguồn sự thật duy nhất — sửa cột thì sửa cả 2 chỗ trong cùng
file, tránh mẫu lệch parser), kèm 2 dòng ví dụ minh hoạ định dạng "Thời lượng"
(`H:MM–H:MM`) và nội dung từng cột. `GET /projects/{id}/script/import/template`
(`pipeline.py`) trả file qua `Response` + header `Content-Disposition` (không cần lưu
file tạm ra đĩa — build thẳng vào `BytesIO`).

Frontend: `api.downloadScriptImportTemplate()` dùng lại `downloadFile()` helper có sẵn
(bắt buộc — xem docstring hàm đó: `<a href>` thường bị Chromium bỏ qua `download` với
URL cross-origin, kẹt cả cửa sổ Electron). Nút "Tải file mẫu" đặt cạnh nút "Nhập kịch
bản từ file" ở `Gate1Outline.tsx` (đúng màn Outline & Hook — xác nhận qua
`StepHeader title="Outline & Hook"`).

**Verify thật (real API, không chỉ code review)**: gọi `GET .../script/import/template`
qua backend thật → `HTTP 200`, `Content-Disposition: attachment; filename="mau-nhap-
kich-ban.xlsx"`, đúng `content-type` xlsx. Vòng đầy đủ: tải file mẫu qua API → upload
lại chính file đó vào `POST .../script/import/parse` (trên project thật của người dùng,
CHỈ gọi `/parse` xem trước — KHÔNG gọi `/confirm` nên không đụng dữ liệu script thật của
họ) → parse đúng 2 block ví dụ, `stats.block_count: 2`. Xác nhận file mẫu tự sinh ra và
parser tự đọc lại khớp nhau tuyệt đối (cùng nguồn `COLUMN_KEYWORDS`).

pytest: 136/136 pass. tsc --noEmit sạch.

## 26. Bỏ qua Brief & Research, nhập kịch bản luôn (2026-08-16)

Người dùng yêu cầu: cho phép bỏ qua bước Brief/Research, nhảy thẳng tới upload file
kịch bản. Điều tra trước khi code (subagent Explore, không đoán): backend
(`POST /script/import/confirm`, `pipeline.py:289-332`) **đã sẵn sàng cho việc này từ
trước** — không có gating nào theo `step`/`status`/`pack.research`, tự nhảy thẳng
`step→2` bất kể project đang ở step nào. `pack.json` khởi tạo lúc tạo project đã có sẵn
`research: null`, `hooks: []` (Pydantic dump, không phải field thiếu), và grep toàn bộ
backend+frontend xác nhận không nơi nào khác đọc 2 field này ngoài chính màn Outline &
Hook — dự án đi thẳng Brief(step 0)→import→Script Studio(step 2) không làm hỏng gì ở
Visual Studio/Pack Review/Output/render engine. **Không cần sửa backend.**

Chỉ cần thêm UI ở `BriefEditor.tsx` (step 0): tách JSX nút "Nhập kịch bản từ file" +
"Tải file mẫu" + dialog xác nhận (vốn nằm nguyên trong `Gate1Outline.tsx`) thành
component dùng chung `frontend/src/components/ScriptImportControls.tsx` — tránh lặp
code giữa 2 màn cùng gọi chung 2 endpoint. `BriefEditor.tsx` giờ có thêm nút "Nhập kịch
bản từ file" cạnh "Bắt đầu Research", dùng lại y hệt component đó.

**Verify thật (real API, không chỉ code review)**: tạo channel+project throwaway mới
qua API → tải template → upload lại → `parse` → `confirm` — KHÔNG gọi bất kỳ endpoint
Brief/Research nào. Kết quả: `step: 0 → 2` trực tiếp, `max_step_reached: 2`,
`status: "generating"`, `pack.script.source: "import"`, `pack.research: None`,
`pack.hooks: []` — đúng như dự đoán từ investigation, không cần chỉnh backend.

pytest: 136/136 pass (không đổi backend nên chỉ chạy để xác nhận không phá gì). tsc
--noEmit sạch.

## 27. Nhãn nút "Đi tới Visual Studio" gây hiểu lầm khi đang gọi AI (2026-08-16)

Người dùng thấy nút "Đi tới Visual Studio" ở Script Studio chạy lâu dù kịch bản đã
nhập từ file (nội dung shot đã đầy đủ, tưởng không cần chờ). Đọc lại
`generate_visual_shots` (`pipeline.py:385-424`): nút này làm **2 việc** trong 1 request
— (1) tạo shot list, TỨC THÌ nếu `script.source == "import"` (đúng như người dùng nhận
xét, không gọi AI); (2) **luôn gọi AI sinh Title/Description/Thumbnail concept**
(`generate_titles_and_meta`) nếu `pack.youtube_meta` chưa có — bất kể script từ AI hay
import — đây mới là phần chậm thật (LLM call thật, vài giây tới cả phút tuỳ provider).
Không phải bug — thiết kế có chủ đích (sinh sớm thumbnail_description để hiện form Tạo
Thumbnail ngay đầu Visual Studio, xem comment gốc trong code) — nhưng nhãn nút cũ
"Đang sinh shot..." mô tả SAI phần đang thực sự làm cho người dùng chờ.

Fix: `ScriptStudio.tsx` — nhãn khi `busy` giờ phân biệt theo `pack.youtube_meta`: chưa
có → "Đang sinh Title/Mô tả/Thumbnail bằng AI..." (đúng phần đang chạy); đã có (lần
sau) → "Đang xử lý...". Thêm `title` tooltip giải thích trước khi bấm. Chỉ sửa UI —
KHÔNG đổi hành vi/thứ tự gọi API, đúng phạm vi yêu cầu (người dùng hỏi "đang xử lý gì",
không yêu cầu đổi tốc độ/luồng).

tsc --noEmit sạch (không đổi backend).

## 28. Tách sinh Title/Description/Thumbnail concept ra khỏi Visual Studio, chuyển thành nút riêng ở Pack Review (2026-08-16)

Tiếp theo mục 27 (nhãn nút gây hiểu lầm) — người dùng quyết định luôn: việc sinh Title/
Description/Thumbnail concept **không cần làm ở Visual Studio nữa**, chuyển hẳn thành 1
nút riêng ở Pack Review (tab "Title & Thumbnail"). Lý do gốc của việc sinh sớm (mục
"Sinh SỚM titles/youtube_meta" trong code cũ) đã hết hiệu lực: lúc đó cần
`thumbnail_description` có sẵn sớm vì Thumbnail đóng vai trò "anchor" img2img bắt buộc
cho từng shot — cơ chế anchor đã TẮT HẲN từ mục 21, nên không còn lý do ép sinh sớm/ẩn.

### Thay đổi

- `pipeline.py::generate_visual_shots` (`/visual/generate`) — XOÁ HẲN block tự gọi
  `gen.generate_titles_and_meta`. Giờ chỉ còn tạo shot list — với script nhập từ file
  (`source: "import"`) tức thì (0.1s đo thật), với script AI vẫn gọi LLM sinh shot
  (không đổi, đó là việc CẦN làm ở bước này) nhưng không còn "âm thầm" kèm thêm 1 lệnh
  gọi AI khác không liên quan.
- `pipeline.py::generate_titles_meta` (mới) — `POST /projects/{id}/pack/titles-meta`.
  KHÁC `build_pack` (chỉ sinh 1 LẦN nếu còn thiếu, an toàn cho auto-trigger cũ): endpoint
  này LUÔN sinh lại (đúng ý "nút sinh lại", không phải fallback), nhưng GIỮ NGUYÊN
  `thumbnail_status`/`thumbnail_asset_path`/`thumbnail_provider`/`thumbnail_error`/
  `thumbnail_approved` — merge có chủ đích từ `youtube_meta` cũ trước khi ghi đè, vì
  `generate_titles_and_meta()` trả về dict KHÔNG có 5 field này (chỉ description/
  hashtags/chapters/thumbnail_description) — ghi đè thẳng như code cũ từng làm (chỉ an
  toàn vì luôn chạy lúc `youtube_meta` còn trống) sẽ XOÁ MẤT ảnh Thumbnail thật đã tạo/
  duyệt riêng ở Visual Studio nếu dùng cho nút sinh-lại.
- `build_pack` — GIỮ NGUYÊN logic fallback cũ (chỉ sinh nếu còn thiếu) làm lưới an toàn
  cho project cũ/trường hợp người dùng chưa từng bấm nút mới, không đổi gì.
- Frontend: `PackReview.tsx` tab "Title & Thumbnail" — thêm nút "Sinh Title/Mô tả/
  Thumbnail concept bằng AI" (đổi thành "↻ Sinh lại..." khi đã có titles), gọi
  `api.generateTitlesMeta()` (mới, `client.ts`). `ScriptStudio.tsx`'s nhãn nút "Đi tới
  Visual Studio" (sửa ở mục 27) giờ luôn hiển thị đúng — không còn nhánh "sinh Title" vì
  bước đó không còn xảy ra ở đây nữa.

### Verify thật (real API, real timing — không chỉ code review)

Trên project throwaway `prj_1786898104210`:
- `POST /visual/generate` — **0.11s** (trước đây có thể mất 10s-vài phút tuỳ provider vì
  kèm lệnh gọi AI titles/meta). `youtube_meta`/`titles` sau lệnh này: `None`/`[]`.
- `POST /pack/titles-meta` — **32.93s** (LLM call thật, xác nhận đây đúng là phần chậm
  đã tách ra) — trả về 7 title + youtube_meta đầy đủ.
- Test riêng khả năng GIỮ NGUYÊN ảnh Thumbnail: patch `youtube_meta` với
  `thumbnail_status="ready"`, `thumbnail_asset_path`, `thumbnail_provider="gemini"`,
  `thumbnail_approved=true` (mô phỏng đã tạo/duyệt ở Visual Studio) → gọi lại
  `/pack/titles-meta` → cả 4 field GIỮ NGUYÊN y hệt, chỉ `description` đổi (nội dung AI
  mới) — xác nhận cơ chế merge đúng, không xoá mất Thumbnail khi sinh lại text.

pytest: 136/136 pass (`-p no:randomly`). tsc --noEmit sạch.

## 29. Tách nút "Sinh asset cho toàn bộ block" thành Visual riêng + Giọng đọc riêng (2026-08-16)

Người dùng yêu cầu: ở Visual Studio, cho phép sinh Visual và giọng đọc riêng cho TOÀN
BỘ block (khác 2 nút "Tạo lại" đã có sẵn CHO TỪNG SHOT riêng lẻ — đây là tách ở mức
BATCH, cùng tinh thần đã áp dụng cho bước sinh PROMPT trước đó — `visual/generate-all-
visual`/`-all-tts`, 2 endpoint riêng biệt).

### Thay đổi

- `render/engine.py::run_asset_generation(project_id, *, kind="both")` — thêm tham số
  `kind` ("both"|"visual"|"narration"). Trong vòng lặp qua từng shot: chỉ gọi
  `generate_visual_asset` nếu `kind in ("both","visual")`, chỉ gọi
  `generate_narration_asset` nếu `kind in ("both","narration")`. Mặc định `"both"` — giữ
  nguyên hành vi cũ cho mọi lời gọi hiện có.
- `render.py::start_render` — thêm query param `kind: str = "both"` (validate 3 giá trị
  hợp lệ, 400 nếu sai), truyền xuống `run_asset_generation`. KHÔNG đổi chữ ký endpoint
  theo cách phá vỡ tương thích — mặc định giữ nguyên nên toàn bộ test `render/start` cũ
  (gọi không kèm param) vẫn qua nguyên (136/136 pass, không sửa test nào).
- Frontend: `client.ts::startRender(id, kind = "both")`, `VisualStudio.tsx` — 1 nút cũ
  "Sinh asset (ảnh/video/giọng đọc) cho toàn bộ block" tách thành 2: "Sinh Visual (ảnh/
  video) cho toàn bộ block" và "Sinh giọng đọc cho toàn bộ block".

### Verify thật (real API, project throwaway `prj_1786898104210`, 2 shot)

- `POST render/start?kind=narration` → poll `render/status`: `visual_status` CẢ 2 shot
  giữ nguyên `"pending"` suốt quá trình, `narration_status` chuyển `generating→ready`
  đúng thứ tự — xác nhận không đụng gì tới visual.
- `POST render/start?kind=visual` (sau khi narration đã `ready`) → `narration_status`
  GIỮ NGUYÊN `"ready"` (không bị sinh lại), `visual_status` chuyển `generating` đúng —
  xác nhận chiều ngược lại cũng đúng. Huỷ batch (`render/cancel`) ngay sau khi xác nhận
  trạng thái đúng, không chờ ảnh/video sinh xong thật (tốn GPU/API vô ích cho 1 test).

pytest: 136/136 pass. tsc --noEmit sạch.

## 30. Sinh + tải giọng đọc ngay ở Script Studio, tải transcript .srt (2026-08-17)

Người dùng yêu cầu: (1) nút "Sinh giọng đọc cho toàn bộ block" ở Script Studio (trước
đây chỉ có ở Visual Studio) + hiện trạng thái sinh; (2) tải 1 file audio ghép TOÀN BỘ
giọng đọc script; (3) tải transcript kèm timeline dạng `.srt`.

### Vấn đề kiến trúc thật phải giải quyết trước khi thêm nút

`render/start` (sinh asset) lưu trạng thái theo `shot_id`, nhưng `pack.shots` chỉ được
tạo khi vào Visual Studio (`/visual/generate`, step 2→3) — ở Script Studio (step 2)
`pack.shots` RỖNG, không có gì để khoá trạng thái narration vào. Không thể đơn giản gọi
`/visual/generate` từ Script Studio vì nó ĐỔI LUÔN `step` (nhảy sang Visual Studio,
sai UX — người dùng chỉ muốn nghe thử giọng đọc, chưa muốn rời màn).

Sâu hơn: với script AI-viết (khác import), `shot_id` do chính LLM tự đặt tên trong JSON
trả về — KHÔNG có gì đảm bảo gọi 2 lần cho CÙNG 1 script sẽ ra CÙNG 1 bộ `shot_id` (khác
`_seed_shot_from_beat` dùng `block_id` ổn định cho script import). Nếu để Script Studio
tự tạo shot list riêng rồi Visual Studio tạo LẠI 1 lần nữa khi người dùng bấm "Đi tới
Visual Studio", 2 lần gọi có thể ra 2 bộ `shot_id` khác nhau — narration đã sinh ở lần 1
bị ĐỨT liên kết, biến mất khỏi Visual Studio dù đã tốn tiền/thời gian sinh.

**Fix**: `pipeline.py::_ensure_shots()` (hàm dùng chung mới) — tạo shot list CHỈ khi
`pack.shots` còn rỗng (idempotent), trả nguyên dữ liệu cũ nếu đã có. Cả `/visual/generate`
(bấm "Đi tới Visual Studio", vẫn đổi step như cũ) LẪN endpoint mới
`POST /visual/ensure-shots-for-narration` (bấm "Sinh giọng đọc" ở Script Studio, KHÔNG
đổi step) đều gọi qua hàm này — dù gọi theo thứ tự nào, `shot_id` luôn nhất quán, không
đứt liên kết. Verify thật: gọi `ensure-shots-for-narration` 2 lần liên tiếp trên cùng
project → `shot_id` list giống hệt nhau lần 1 và lần 2.

### Thay đổi

- `pipeline.py::_ensure_shots(pack, db, brand, body, usage)` (mới, refactor từ logic cũ
  trong `generate_visual_shots`) + `POST /visual/ensure-shots-for-narration` (mới).
- `render/engine.py::build_narration_download(project_id)` (mới) — ghép narration mọi
  shot (theo thứ tự `linked_timestamp_sec`) thành 1 file `.mp3` bằng
  `ffmpeg -filter_complex concat` (KHÔNG dùng concat demuxer + `-c copy` như
  `assembly.py` dùng cho video — mỗi shot có thể do PROVIDER TTS KHÁC NHAU sinh, trả
  định dạng khác nhau theo shot, `-c copy` chỉ an toàn khi mọi input CÙNG codec; filter
  concat giải mã về PCM trước khi nối nên không quan tâm codec gốc từng input). Raise
  lỗi rõ ràng nếu còn block chưa `narration_status=="ready"` (liệt kê tối đa 5 shot_id
  đầu tiên còn thiếu).
- `render.py::GET /render/narration-download` — serve file ghép qua `FileResponse`.
- `pipeline.py::_build_srt()`/`GET /script/transcript-srt` (mới) — sinh `.srt` chuẩn từ
  `script.body`, 1 cue/block, dùng `timestamp_sec`/`end_sec` sẵn có (khớp nhãn UI
  "00:00–00:35"), fallback +5s nếu thiếu `end_sec` (cùng hằng số `DEFAULT_BEAT_DURATION_SEC`
  đã dùng ở `assembly.py::_beat_duration`, không tự bịa số mới).
- **Sửa 1 lỗi thật phát hiện lúc code** (không phải lúc test) — `client.ts::downloadFile()`
  khi lỗi chỉ báo `res.statusText` chung chung ("Bad Request"), KHÔNG đọc field `detail`
  trong JSON body như `req()` — các nút tải file trước đây (Thumbnail/Export/Video) hiếm
  khi 400 với thông điệp người dùng cần đọc nên chưa lộ ra, nhưng nút tải audio ghép mới
  400 THƯỜNG XUYÊN (còn block chưa sinh xong — kịch bản dùng thật) với thông điệp cụ thể
  (liệt kê block thiếu) — sửa `downloadFile()` đọc `detail` giống `req()`, cải thiện
  luôn cho MỌI nút tải file cũ (không có rủi ro hồi quy, chỉ thêm thông tin lỗi).
- Frontend: `ScriptStudio.tsx` — toolbar mới (chỉ hiện khi đã bóc tách block, `!showEditor`):
  "Sinh giọng đọc cho toàn bộ block (X/Y)" (gọi `ensure-shots-for-narration` rồi
  `startRender(id,"narration")`), "▶ Nghe toàn bộ giọng đọc" (đã có sẵn, giờ hoạt động
  đúng vì `pack.shots` không còn rỗng), "⭳ Tải giọng đọc toàn bộ script (.mp3)" (disable
  tới khi ĐỦ mọi block ready), "⭳ Tải transcript (.srt)" (luôn sẵn khi có body). Trạng
  thái từng block ("Đang tạo giọng đọc…"/nút nghe) TÁI SỬ DỤNG nguyên logic
  `narrationStatusFor`/`shotForTimestamp` đã có sẵn trong file — không viết lại, chỉ cần
  `pack.shots` không còn rỗng là tự hoạt động đúng.

### Verify thật (real API, project throwaway tạo mới hoàn toàn từ step 0)

- Tạo project → import kịch bản (bỏ qua Brief/Research, mục 26) → step 2, `pack.shots`
  rỗng (xác nhận đúng điểm xuất phát cần fix).
- `POST script/transcript-srt` → nội dung `.srt` đúng chuẩn (số thứ tự, `HH:MM:SS,mmm`,
  timestamp khớp block thật).
- `POST visual/ensure-shots-for-narration` → tạo 2 shot, **step vẫn giữ nguyên 2**
  (không nhảy Visual Studio) — đúng yêu cầu cốt lõi.
- `POST render/start?kind=narration` → cả 2 block `narration_status: ready`,
  `visual_status` giữ nguyên `pending` suốt (không đụng).
- Gọi lại `ensure-shots-for-narration` LẦN 2 → `shot_id` list giống hệt lần 1 — xác
  nhận idempotent, không đứt liên kết.
- `GET render/narration-download` → file `.mp3` ghép, `ffprobe` đo **6.82s = ĐÚNG BẰNG**
  tổng `narration_duration_sec` 2 block cộng lại — xác nhận ghép không thiếu/thừa/lặp.
- Test 2 nhánh lỗi: chưa có shot → `"Chưa có shot nào — cần sinh giọng đọc trước."`; có
  shot nhưng chưa sinh narration → `"Còn 2 block chưa có giọng đọc sẵn sàng (B01, B02)
  — sinh xong hết mới ghép/tải được."` — cả 2 đúng HTTP 400 kèm thông điệp cụ thể.

pytest: 136/136 pass (`-p no:randomly`). tsc --noEmit sạch.

## 31. Bug thật: Script Studio và Visual Studio lệch trạng thái giọng đọc — `pack.shots` mất đồng bộ với `script.body` (2026-08-17)

Người dùng báo: Script Studio chỉ hiện 2 block có giọng đọc, trong khi Visual Studio đã
sinh đủ giọng cho toàn bộ block. Điều tra trên đúng project thật của người dùng (không
đoán) — `GET pack` cho thấy:

- `script.body`: **31 block** (B01-B31).
- `pack.shots`: chỉ **12 shot** (B01-B12) — do trước đó script được viết dài thêm (sửa/
  duyệt lại Full Script) SAU KHI shots đã tạo lần đầu; `_ensure_shots` (mục 30, viết
  "idempotent — có gì thì trả nguyên") không bao giờ mở rộng lại theo `body` mới, mắc
  đúng cạm bẫy đã tự ghi nhận nhưng chưa xử lý: *"đã có edge case tồn tại từ trước...
  không xây trước khi có bằng chứng cần"* — hoá ra bằng chứng xuất hiện ngay trên
  project thật của chính người dùng đang dùng.
- **Bug thứ 2, độc lập**: kể cả với 12 shot đang có, `linked_timestamp_sec` của shot
  KHÔNG khớp `timestamp_sec` của block tương ứng (VD block B02 `timestamp_sec=40` nhưng
  shot B02 `linked_timestamp_sec=35`) — `ScriptStudio.tsx::shotForTimestamp()` so khớp
  bằng `===` nên hầu hết block không tìm ra shot, dù shot đó THẬT SỰ tồn tại và có giọng
  đọc sẵn sàng. Visual Studio không bị ảnh hưởng vì nó lặp thẳng qua `pack.shots` (dùng
  `shot_id` trực tiếp), không cần khớp ngược từ block như Script Studio.

### Fix

- `pipeline.py::_ensure_shots()` — đổi từ "tạo nếu rỗng" sang **ĐỒNG BỘ theo `block_id`**
  (script import): block nào chưa có shot khớp `block_id` → tạo mới, APPEND; shot đã có
  GIỮ NGUYÊN (không đụng, bảo toàn asset/liên kết đã sinh). Script AI-viết (không có
  `block_id` ổn định — LLM không được yêu cầu trả field này) fallback so sánh SỐ LƯỢNG:
  `body` dài ra thì sinh lại toàn bộ, không đổi thì giữ nguyên — hạn chế đã biết, ghi rõ
  trong docstring (không có ID ổn định để làm tốt hơn khi thiếu `block_id`).
- `ScriptStudio.tsx::shotForTimestamp()` → đổi thành `shotForBlock(block, index)`: khớp
  theo `block.block_id` khi có (import), fallback theo VỊ TRÍ mảng khi không có
  (AI-viết) — bỏ hẳn so khớp theo `timestamp_sec` (nguồn gốc bug thứ 2). Cập nhật cả 3
  chỗ gọi (`playAllNarration`, `readyNarrationCount`, danh sách block).
- **Theo yêu cầu người dùng**: mỗi block ở Script Studio giờ hiện thêm tag `shot: {shot_id}`
  (đối chiếu trực tiếp với thẻ shot ở Visual Studio, vốn hiện `{shot_id} · {linked_timestamp_sec}s`)
  — hoặc tag cảnh báo "Chưa có shot" nếu block đó thật sự chưa đồng bộ, để tự kiểm tra
  bằng mắt thay vì chỉ tin vào con số đếm.

### Verify thật trên ĐÚNG project thật của người dùng (KHÔNG phải project test)

Chụp snapshot `pack.shots` + `render.json` TRƯỚC khi sửa, gọi
`POST visual/ensure-shots-for-narration` (an toàn, không đổi step/status — mục 30), rồi
so sánh:

- `pack.shots`: 12 → **31**, đúng 19 shot mới (B13-B31) được tạo, `step`/`status`
  KHÔNG đổi (vẫn step 4, không bị đẩy lùi/tiến sai).
- **12 shot cũ so khớp TỪNG BYTE giống hệt** trước/sau (không bị ghi đè) — xác nhận
  không mất dữ liệu visual/narration đã sinh cho B01-B12.
- `render.json` (trạng thái narration/visual thật) cho 12 shot cũ **giống hệt** trước/
  sau — không bị reset. 19 shot mới CHƯA có entry trong `render.json` (đúng — chưa gọi
  sinh asset cho chúng, chỉ đồng bộ shot list, tránh tốn phí/thời gian generation ngoài
  ý muốn của người dùng trong lúc verify).

pytest: 136/136 pass (`-p no:randomly`). tsc --noEmit sạch.

## 32. Sửa Audio + sinh giọng đọc RIÊNG từng block ở Script Studio (2026-08-17)

Người dùng yêu cầu 2 nút mới ở mỗi block Script Studio: (1) sửa tay nội dung Audio (VO),
(2) sinh giọng đọc riêng cho đúng block đó — khác nút batch "cho toàn bộ block" (mục 30)
vốn sinh hàng loạt, không tiện khi chỉ cần chỉnh 1 block.

### Thay đổi

- `pipeline.py::PATCH /script/body/{index}/audio` (mới) — sửa `script.body[index].audio`,
  dùng INDEX làm khoá (không phải `block_id`, vì script AI-viết không có field này ổn
  định — mục 31) — block không bị sắp xếp lại nên an toàn. Đồng bộ lại `full_text`
  (nối toàn bộ audio từng block) để không lệch với khối "Full Script" hiển thị ở
  PackReview.
- `ScriptStudio.tsx` — cột "Audio" mỗi block giờ có nút bút chì bật/tắt chế độ sửa
  (textarea, auto-save khi blur — cùng convention `ShotCard` ở Visual Studio). Nút
  "Tạo giọng đọc"/"↻ Sinh lại giọng đọc" riêng mỗi block — gọi
  `ensure-shots-for-narration` trước (idempotent, tạo shot cho ĐÚNG block này nếu còn
  thiếu, mục 30/31) rồi `render/shots/{shot_id}/regenerate-narration` (endpoint CÓ SẴN,
  vốn chỉ dùng ở Visual Studio — tái dùng nguyên, không viết logic sinh audio mới).

### Verify thật (real API, đúng luồng frontend gọi)

- `PATCH script/body/0/audio` → nội dung block 0 đổi đúng, `full_text` tự nối lại đúng
  thứ tự (block 0 mới + các block sau giữ nguyên).
- Gọi `ensure-shots-for-narration` → `regenerate-narration` cho shot của block 0 (đúng
  luồng nút mới) → kiểm tra **timestamp file** `.wav` (không chỉ tin `narration_status`,
  vì status vốn đã "ready" từ trước — cần bằng chứng file THẬT SỰ được ghi lại): B01.wav
  có `LastWriteTime` MỚI (vừa ghi lúc test), B02.wav **KHÔNG đổi** (giữ nguyên
  `LastWriteTime` cũ) — xác nhận đúng per-block, không đụng block khác.

pytest: 136/136 pass (`-p no:randomly`). tsc --noEmit sạch.

## 33. Chọn transition giữa các shot khi ghép video (2026-08-17)

Người dùng yêu cầu: ở Visual Studio, cho phép chọn transition giữa các shot, tự đề xuất
bộ transition phù hợp/hiệu quả để tránh chuyển cảnh nhàm chán (toàn cắt cứng).

### Curated 7 transition (+ "cut" mặc định)

Chọn theo tinh thần nội dung kể chuyện lịch sử/tài liệu dài (kênh mẫu "Người Kể Sử") —
bỏ hẳn các loại `xfade` hoa mỹ/game-y (zoomin, pixelize, squeezeh, circlecrop...) không
hợp giọng điệu nghiêm túc: `fade` (hoà tan), `fadeblack` (mờ qua đen — hợp đổi chủ đề),
`dissolve` (tan dần, hạt nhiễu), `wipeleft`/`wiperight` (gạt trái/phải),
`smoothleft`/`smoothright` (trượt mượt). Tên transition là tên CHUẨN của ffmpeg `xfade`
filter (không tự đặt). Thời lượng transition CỐ ĐỊNH 0.6s (không cho tuỳ chỉnh riêng —
người dùng chỉ yêu cầu chọn KIỂU, thêm tham số thời lượng là over-engineer ngoài phạm
vi yêu cầu).

### Kiến trúc — 2 tầng để KHÔNG re-encode toàn bộ khi không cần

`render/assembly.py` trước đây ghép MỌI shot bằng concat demuxer + `-c copy` (stream-
copy, không re-encode, rất nhanh). Transition thật (crossfade/wipe...) BẮT BUỘC re-
encode (ffmpeg `xfade`/`acrossfade` không stream-copy được) — nhưng ép re-encode TOÀN
BỘ video chỉ vì 1-2 chỗ có transition sẽ chậm đi rất nhiều cho video dài (10-30 shot),
đi ngược yêu cầu "render hiệu quả". Giải pháp 2 tầng:

1. **Gộp "run"** (`_run_boundaries`) — chuỗi shot liên tiếp nối bằng "cut" gộp thành 1
   "run", ghép NHANH như cũ (`_concat_fast`, stream-copy).
2. **Nối các run** bằng `_xfade_chain` — CHỈ chỗ nào người dùng THẬT SỰ chọn transition
   mới re-encode (đúng đoạn giao giữa 2 run, không đụng phần còn lại).

Nếu KHÔNG shot nào dùng transition (mặc định "cut" toàn bộ) → giữ NGUYÊN đường ghép
NHANH cũ 100%, không đổi hành vi/output — zero regression cho project không dùng tính
năng này (đã xác nhận qua pytest, không sửa test nào).

**Toán offset chain nhiều `xfade` liên tiếp** (điểm dễ sai nhất, đã tự phát hiện lúc
research): mỗi transition thứ i bắt đầu tại `cum - t` (cum = tổng thời lượng output
TÍCH LŨY), sau đó `cum` giảm đúng `t` (2 đoạn chồng lấn `t` giây trong lúc transition).
`acrossfade` (audio) không cần offset — tự crossfade đúng điểm nối 2 stream đưa vào
theo thứ tự.

**Bug tiềm ẩn tự phát hiện + sửa TRƯỚC khi test** (không phải lúc test mới thấy): shot
không có narration dùng `-an` (không có track audio) — `acrossfade` cần MỌI input có
audio, thiếu 1 sẽ lỗi cả filter graph khi nối. Thêm `ensure_audio_track` cho
`_build_segment` — sinh audio CÂM bằng `anullsrc` thay vì `-an` KHI VÀ CHỈ KHI assembly
có dùng transition (mặc định `False`, đường không-transition không đổi gì).

**Import vòng phát hiện lúc code** (không phải lúc chạy) — `pipeline.py` cần validate
giá trị `transition_to_next` lúc PATCH shot, định import thẳng `TRANSITIONS` từ
`assembly.py`, nhưng `assembly.py` → `app/render/engine.py` → `app/routers/pipeline.py`
(`record_asset_usage`) đã là 1 vòng có sẵn từ trước. Tách `TRANSITIONS` ra module riêng
`app/render/transitions.py` (không phụ thuộc gì) — cả `assembly.py` lẫn `pipeline.py`
cùng import từ đó, phá vòng.

### Thay đổi

- `app/schemas/__init__.py::Shot.transition_to_next: str = "cut"` (field mới).
- `app/render/transitions.py` (mới) — `TRANSITIONS` dict (nguồn sự thật duy nhất).
- `render/assembly.py` — `_build_segment` thêm `ensure_audio_track`; `_concat_fast`,
  `_xfade_chain`, `_run_boundaries` (mới); `assemble_video` rẽ nhánh theo
  `has_transitions`.
- `pipeline.py::PATCH /visual/shots/{shot_id}` — thêm `transition_to_next` vào
  `ShotPatchBody`, validate theo `TRANSITIONS` (400 nếu sai).
- Frontend: `VisualStudio.tsx::ShotCard` — dropdown "Chuyển cảnh sang shot kế tiếp"
  (ẩn ở shot CUỐI — không có "kế tiếp" để chuyển tới), `TRANSITION_OPTIONS` khớp
  backend. `patchShot` giờ gọi `refresh()` sau khi lưu (cần cho `<select>` — component
  CÓ ĐIỀU KHIỂN, khác `<textarea defaultValue>` không cần refresh).

### Verify thật — 2 vòng, cả unit lẫn tích hợp đầy đủ (real ffmpeg, không mock)

**Vòng 1 — unit, gọi thẳng `_build_segment`/`_concat_fast`/`_xfade_chain`**: dựng 4 clip
màu (đỏ/xanh lá/xanh dương/vàng) qua ffmpeg `testsrc`, sắp transition
cut→fade→cut → 2 run (run0=đỏ+lá, run1=lam+vàng) nối bằng "fade". Kết quả: thời lượng
final = 11.567s (kỳ vọng 11.4s, lệch nhỏ do làm tròn frame — chấp nhận được). **Lấy mẫu
màu pixel tại nhiều mốc thời gian quanh điểm chuyển** (không chỉ tin số liệu) —
`008200` (xanh lá thuần) → `00456f` (MÀU PHA TRỘN thật, không phải đỏ/xanh thuần) →
`0000ff` (xanh dương thuần) — xác nhận blend THẬT, không phải cắt cứng trá hình.

**Vòng 2 — tích hợp đầy đủ, gọi thẳng `assemble_video()` thật** (không mock) trên
project throwaway, patch transition qua ĐÚNG API `PATCH /visual/shots/{id}` (không chỉ
sửa file), giả lập 2 shot "đã sẵn sàng" bằng ảnh test (tránh tốn API/GPU sinh ảnh AI
thật) + audio narration THẬT đã có sẵn từ lần test trước: `assembly_status: done`,
KHÔNG lỗi. Thời lượng final **19.400s = ĐÚNG CHÍNH XÁC** `8 + 12 - 0.6` (2 block script
thật dài 8s/12s). Lấy mẫu màu quanh đúng mốc 7.4-8.2s: tím thuần (`7d007b`) → 2 mốc
BLEND (`a8324d`, `d56e21`) → cam thuần (`ffa500`) — crossfade mượt, đúng ý đồ. Dọn sạch
dữ liệu test khỏi project (reset render state, xoá ảnh/video test) sau khi verify xong.

pytest: 136/136 pass (`-p no:randomly`, không sửa test nào — xác nhận đường không-
transition không đổi hành vi). tsc --noEmit sạch.

## 34. Bước sinh ảnh/video lỗi hàng loạt — ComfyUI bị treo + shot AI trả sai kiểu dữ liệu (2026-08-17)

Người dùng báo bước tạo ảnh/video lỗi nhiều trên project thật "Cách mạng Tháng Tám
1945...". Điều tra trực tiếp trên đúng project — phát hiện **2 bug thật độc lập**, cả
2 đều đủ để chặn đứng sinh asset, không phải suy đoán.

### Bug 1 — ComfyUI bị TREO thật (HTTP 500 ngay cả endpoint status cơ bản)

`GET :8188/system_stats` (endpoint đọc trạng thái, không sinh gì) trả **500 Internal
Server Error** — server ComfyUI tự nó đã hỏng, không phải lỗi phía app. Đối chiếu
`GET :8188/queue` (endpoint này vẫn phản hồi được) cho thấy có 1 job Wan2.2 THẬT đang ở
trạng thái `queue_running` với nội dung prompt khớp đúng project của người dùng —
ComfyUI treo NGAY GIỮA lúc xử lý job này. `nvidia-smi` lúc đó: chỉ **~1.1GB VRAM trống
trên 16GB** — cực kỳ chật. ComfyUI đã chạy liên tục KHÔNG restart từ 13/8 (nhiều ngày) —
khả năng cao là tích tụ phân mảnh/rò rỉ VRAM qua nhiều lần sinh dồn dập.

**Fix**: restart process ComfyUI (không có cách nào phục hồi qua API khi chính
`/system_stats` đã 500 — không còn lựa chọn "graceful" nào khác). Verify thật:
VRAM trống nhảy từ **1.1GB → 15.8GB** ngay sau khi khởi động lại — xác nhận đúng
nguyên nhân, không phải trùng hợp.

### Bug 2 — Shot do AI sinh trả SAI KIỂU DỮ LIỆU, crash `render/start` (HTTP 500)

Sau khi ComfyUI đã khoẻ, gọi thật `POST render/start` cho project của người dùng vẫn
**500** — traceback thật từ log backend:
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for ShotRenderStatus
shot_id
  Input should be a valid string [type=string_type, input_value=1, input_type=int]
```
Đọc thẳng `pack.shots` xác nhận: `shot_id` là **số nguyên** (`1, 2, ..., 9`) thay vì
chuỗi (`"S01"`) — AI (`gen.generate_shots`, đường KHÔNG phải import) trả JSON hợp lệ
(qua được `_extract_json`) nhưng SAI KIỂU field `shot_id`. Cùng lúc `visual_type` cũng
sai — trả mô tả tự do ("documentary-style", "dramatic close-up"...) thay vì đúng
"image"/"video"; `render/engine.py::generate_visual_asset` so khớp `== "video"` TUYỆT
ĐỐI nên mọi giá trị không đúng "video" âm thầm rơi về ảnh — lỗi ÂM THẦM, không crash,
nhưng sai ý đồ nếu AI định làm video.

**Vì sao chỉ import mới an toàn trước đây**: `_seed_shot_from_beat` (đường import) đã
tự chuẩn hoá `visual_type` từ lâu (`.lower().startswith("video")`, mục cũ), nhưng
`_ensure_shots` nhánh AI (`gen.generate_shots`) dùng THẲNG output LLM, không qua bước ép
kiểu nào — lỗ hổng có từ khi tính năng shot AI ra đời, chỉ lộ ra khi LLM THẬT SỰ trả sai
định dạng (không phải lần nào cũng xảy ra, nên chưa bị phát hiện tới giờ).

**Fix**: `pipeline.py::_normalize_ai_shot()` (mới) — ép `shot_id` thành chuỗi (fallback
`f"S{index+1:02d}"` nếu rỗng), chuẩn hoá `visual_type`/`asset_type` — ÁP DỤNG NGAY SAU
`gen.generate_shots()` trong `_ensure_shots()`, cùng logic chuẩn hoá đã có cho import,
giờ nhất quán cho CẢ 2 nguồn. Không sửa `ShotRenderStatus` để "chấp nhận" số — sai chỗ
sửa, `shot_id` PHẢI là chuỗi (dùng làm tên file/khoá tra cứu khắp hệ thống).

**Sửa dữ liệu ĐÃ HỎNG của project thật** (không chỉ sửa code cho tương lai) — áp dụng
đúng logic chuẩn hoá trên trực tiếp vào `pack.json` hiện có: `shot_id` `1→"1"`...`9→"9"`
(chuỗi hợp lệ, giữ nguyên số gốc AI đã chọn — không đổi thành "S01" vì hàm chuẩn hoá ưu
tiên GIỮ giá trị gốc nếu không rỗng, chỉ fallback khi thật sự thiếu), `visual_type` tất
cả `→"image"` (không giá trị nào trong 9 shot thật sự có ý "video", xác nhận qua chính
nội dung mô tả).

### Verify thật — sinh asset thật thành công sau cả 2 fix

`POST render/start` → **HTTP 200** (trước đó 500). Poll `render/status` thật: shot 1
`visual_status: ready`, `provider: local_sdxl`, KHÔNG lỗi — batch tiếp tục chạy nền cho
8 shot còn lại. Không phải suy luận từ code — đây là generation THẬT chạy qua GPU thật
trên project thật của người dùng.

pytest: 136/136 pass (`-p no:randomly`).

## 35. Dọn UI Pack Review/Script Studio, nút "Duyệt toàn bộ block" ở Visual Studio, xác nhận transition không còn cắt cứng (2026-08-17)

### a. Bỏ khối "Full Script" trong tab đầu của Pack Review

Người dùng yêu cầu bỏ tab Full Script ở Pack Review — nội dung đó (`pack.script?.full_text`
hiển thị nguyên khối) trùng lặp với Script Studio, không còn cần thiết ở bước duyệt cuối.
Xoá khối `<div className="field">…Full Script…</div>` trong `PackReview.tsx` (tab
`content`), GIỮ NGUYÊN phần breakdown theo block (audio/visual/direction từng đoạn) và
Shot List bên dưới — đây vẫn là nội dung cần để duyệt. Đổi nhãn tab từ
`"Full Script & Shot List"` → `"Script & Shot List"` cho khớp nội dung còn lại.

### b. Nhãn nút "Đi tới Visual Studio" (Script Studio) còn nhắc tới việc sinh Title/Thumbnail đã KHÔNG còn xảy ra ở đó

Người dùng yêu cầu nút này không cần sinh Title/Thumbnail nữa, đi thẳng tới Visual
Studio. Kiểm tra lại backend (`pipeline.py::generate_visual_shots`) xác nhận việc sinh
`titles_and_meta` đã được gỡ khỏi endpoint này TỪ TRƯỚC (mục 28, 2026-08-16, chuyển
thành nút riêng ở Pack Review) — nút này chỉ còn gọi `_ensure_shots`. Bug thật còn sót
lại thuần ở FRONTEND: tooltip + nhãn trạng thái bận (`"Đang sinh Title/Mô tả/Thumbnail
bằng AI..."`) vẫn mô tả hành vi CŨ, gây hiểu lầm. Xoá tooltip + rút gọn nhãn bận về
`"Đang xử lý..."` cho khớp thực tế hiện tại.

### c. Nút "Duyệt toàn bộ block" ở Visual Studio (mới)

Trước đây chỉ có duyệt từng shot (`POST render/shots/{id}/approve`), người dùng phải bấm
lần lượt — bất tiện khi có nhiều shot đã sinh xong cùng lúc. Thêm:
- Backend: `POST /projects/{id}/render/approve-all` (`render.py::approve_all_shots`) —
  duyệt hàng loạt mọi shot có `visual_status == "ready"` chưa duyệt, bỏ qua thầm lặng
  shot đang sinh/lỗi (khớp đúng điều kiện gate `assemble` đang kiểm ở `not_approved`,
  không tạo ra trạng thái mà gate sau đó lại từ chối).
- Frontend: `client.ts::approveAllShots`, nút mới trong `VisualStudio.tsx` header, hiện
  số lượng shot đang chờ duyệt (`pendingApprovalCount`), disable khi không có shot nào
  cần duyệt.

Verify: `.venv/Scripts/python.exe -c "from app.routers.render import router"` import
sạch, `pytest` 136/136 pass, `tsc --noEmit` sạch (cả 2 lần, sau từng batch sửa). Restart
Electron app (kill tree PID gốc + `npm run dev:electron`) để backend nạp route mới —
xác nhận qua log thật: `Uvicorn running`, `GET /health` → 200, `GET /bootstrap` → 200,
`GET /channels` → 200 sau khi mở lại.

### d. Xác nhận: báo cáo "transition vẫn cắt cứng" ở project "test transition" — không phải bug code

Người dùng test transition ở project "test transition" (`prj_1786874025067`), báo output
vẫn cắt cứng. Điều tra trực tiếp: `PATCH /visual/shots/{id}` với `transition_to_next`
hoạt động đúng (200, persist đúng khi đọc lại ngay sau đó) khi assistant tự test độc lập.
Phát hiện người dùng đang CHỈNH SỬA đồng thời đúng project này (giá trị transition xuất
hiện trên shot 2/3 giữa 2 lần đọc mà assistant không hề đụng vào; 1 lần gọi
`render/assemble` của assistant bị 409 vì người dùng đã tự bấm ghép trước đó). Bản ghép
mà người dùng xem lúc báo lỗi nhiều khả năng đã bắt đúng lúc dữ liệu transition đang dở
dang (đang sửa giữa chừng), không phải cơ chế xfade sai. Người dùng xác nhận lại sau đó
("transition ok nhé") — không cần sửa thêm.

## 36. Nút "Xem Production Pack →" chạy chậm — bỏ Guardrail check lặp lại + bỏ fallback sinh Title/Thumbnail (2026-08-17)

Người dùng hỏi vì sao "Đang tổng hợp Pack" ở Visual Studio lâu. Trả lời trực tiếp: nút
này gọi `POST pack/build`, và bước chậm nhất trong đó là `run_guardrail_check` — chấm
lại Hook Strength bằng 1 lệnh gọi LLM thật. Người dùng yêu cầu bỏ hẳn bước này.

Kiểm tra lại trước khi xoá: `pack["retention_check"]` đã được tính SẴN ở 2 nơi từ TRƯỚC
khi tới `pack/build` — `script/approve` (kịch bản AI, `pipeline.py:434`) và
`script/import/confirm` (kịch bản import, `pipeline.py:398`), ngay lúc body script được
chốt lần đầu. Script body không đổi giữa lúc đó và lúc bấm "Xem Production Pack →", nên
`run_guardrail_check` gọi lại ở `build_pack` (`pipeline.py:718` cũ) là tính TRÙNG, tốn 1
lệnh LLM (vài giây tới cả phút nếu LLM local cần nạp lại VRAM) mà không đổi kết quả.

**Fix (phần 1)**: xoá lệnh gọi `run_guardrail_check` + set `pack["retention_check"]`
khỏi `build_pack`. `retention_check` đã có sẵn từ bước trước được giữ nguyên (không xoá,
không tính lại) — Pack Review vẫn hiện đúng cảnh báo retention như cũ, chỉ KHÔNG còn
chấm lại. Import `run_guardrail_check` ở `pipeline.py` vẫn cần (2 chỗ gọi còn lại:
`script/approve`, `script/import/confirm`), không xoá.

**Fix (phần 2, cùng yêu cầu, mở rộng thêm)**: người dùng yêu cầu bỏ luôn fallback sinh
Title/Description/Thumbnail concept trong `build_pack` (khối `if not
pack.get("youtube_meta")`) — sẽ tự bấm nút riêng `pack/titles-meta` ở Pack Review (mục
28) khi cần, không cần `build_pack` âm thầm gọi AI hộ. `build_pack` giờ CHỈ còn: kiểm
tra có script chưa, set status `await_gate2` + step 4 — không còn lệnh gọi AI nào, không
còn cần Provider AI để chạy được.

Phải sửa theo 3 test đang giả định hành vi cũ (không phải bug, chỉ là test khoá invariant
CŨ giờ đã đổi theo yêu cầu người dùng):
- `test_pipeline_flow.py::test_full_pipeline_happy_path` — thêm bước gọi
  `pack/titles-meta` TRƯỚC `pack/build` để vẫn kiểm được `titles`/`youtube_meta` sinh
  đúng (chỉ chuyển chỗ gọi, không bỏ kiểm).
- `test_no_provider.py::test_pack_build_fails_without_provider_even_for_import` → đổi
  tên thành `test_pack_titles_meta_requires_provider_even_for_import`, khẳng định lại
  invariant đúng chỗ: `pack/build` giờ chạy được (200) dù KHÔNG có provider, còn
  `pack/titles-meta` mới là nơi bắt buộc provider (400 khi thiếu).
- `test_pack_thumbnail.py::_drive_to_pack_built` (helper dùng chung 4 test sinh ảnh
  thumbnail) — thêm gọi `pack/titles-meta` trước `pack/build`, vì test sinh thumbnail
  cần sẵn `youtube_meta.thumbnail_description` (trước đây đến từ fallback, giờ phải tự
  gọi).

Verify: `pytest` 136/136 pass sau cả 2 phần fix (bao gồm 3 test sửa ở trên). Restart
Electron app để nạp code mới.

## 37. Bỏ hẳn tab "Script & Shot List" ở Pack Review (2026-08-17)

Tiếp nối mục 35a (đã bỏ khối "Full Script" text, giữ lại breakdown + Shot List trong
tab) — người dùng yêu cầu bỏ LUÔN cả tab, không chỉ phần Full Script. Pack Review giờ
chỉ còn 1 khối nội dung: **Title & Thumbnail** (trước đây là tab thứ 2).

`PackReview.tsx`: xoá `TABS`/`TabKey`/state `tab` và thanh chuyển tab (`<div
className="seg">`) — không còn lý do giữ UI chọn tab khi chỉ còn 1 lựa chọn. Xoá component
`ShotThumb` (chỉ dùng trong tab đã bỏ, không còn nơi gọi). Nội dung trước đây nằm trong
`{tab === "titles" && (...)}` giờ render thẳng, không điều kiện. `renderState`
(`getRenderStatus`) vẫn giữ nguyên — vẫn cần cho `computeRealStats` ở `StepHeader`
(không liên quan tab đã xoá).

Breakdown script theo block (timestamp/audio/visual/direction) và Shot List (ảnh/video
preview từng shot) — nội dung của tab đã xoá — không còn hiển thị ở Pack Review nữa.
Người dùng xem lại 2 phần này ở đúng nơi chúng được thao tác: breakdown ở Script Studio,
Shot List (kèm ảnh/video thật + approve) ở Visual Studio — Pack Review giờ đúng nghĩa là
bước duyệt Title/Description/Thumbnail trước khi Approve Gate #2.

Verify: `tsc --noEmit` sạch (đã xoá xong biến/hàm không dùng, không còn cảnh báo unused).
Chỉ sửa frontend — không cần restart Electron (Vite hot-reload).

## 38. Bug thật: Timeline/Chapters ở Pack Review sinh 1 mốc/block — hàng chục "chương" thay vì vài mốc nội dung chính (2026-08-17)

Người dùng yêu cầu chỉnh prompt Timeline/Chapters (tab Title & Thumbnail, Pack Review)
để chỉ sinh tối đa 5-8 mốc đại diện nội dung chính. Kiểm tra code trước khi sửa: phát
hiện `chapters` KHÔNG hề đi qua LLM — `generate_titles_and_meta()`
(`backend/app/pipeline/generation.py`) build thẳng bằng code, **1 chapter cho MỖI block
script** (`[{"ts_sec": b["timestamp_sec"], ...} for b in body]`). Kịch bản càng dài,
Chapters càng nhiều — 1 kịch bản 31 block (đúng bằng project "test transition" đã gặp ở
mục 34) ra **31 "chương"**, sai hẳn ý nghĩa YouTube Chapters (vài mốc phân đoạn nội
dung, không phải từng câu).

**Fix — chuyển thật sự sang LLM chọn (đúng ý "chỉnh prompt" của người dùng), có kiểm
soát để không hallucinate:**
- Prompt (`generate_titles_and_meta`, phần suffix cấu trúc JSON — hardcode ở CODE, áp
  dụng NGAY không phụ thuộc bản ghi Prompt Template trong DB, xem lý do dưới) — thêm
  field `"chapters":[{"ts_sec","label"}]` + chỉ dẫn rõ: tối đa 5-8 mốc, mỗi mốc = 1
  PHẦN NỘI DUNG CHÍNH, mốc đầu bắt buộc `ts_sec = 0`, `ts_sec` PHẢI lấy đúng 1 giá trị
  `timestamp_sec` có thật trong script (không tự bịa mốc).
- `_valid_chapters()` (mới) — lọc kết quả LLM: bỏ item sai kiểu/thiếu `label`, bỏ
  `ts_sec` KHÔNG khớp giá trị `timestamp_sec` thật nào trong `body` (chặn hallucination
  mốc không tồn tại), khử trùng, sắp theo thời gian, cắt còn tối đa 8. Rỗng sau lọc →
  `None`, rơi về fallback.
- `fallback_content.sample_chapters()` (mới, thay thế logic 1/block cũ) — rải đều tối
  đa 6 mốc theo timeline (chọn index cách đều `round(i*(n-1)/(target-1))`), dùng khi
  provider lỗi/không cấu hình HOẶC khi `_valid_chapters` trả `None`.

**Vì sao hardcode ở code thay vì chỉ sửa Prompt Template trong DB**: `PROMPT_SEED`
(`seed.py`) chỉ chèn vào DB 1 LẦN lúc bảng `prompt_template` rỗng — sửa file này KHÔNG
có tác dụng gì với cài đặt đã chạy từ trước (đã seed rồi), chỉ áp dụng cho cài đặt MỚI.
Vì cần fix có hiệu lực NGAY trên app đang chạy của người dùng, chỉ dẫn "tối đa 5-8 mốc"
đặt ở phần cấu trúc JSON hardcode trong `generation.py` (cùng chỗ với JSON_SUFFIX/cấu
trúc titles — vốn cũng không nằm trong template DB editable). Vẫn thêm `pt_thumb` "v2"
vào `PROMPT_SEED` để tài liệu hoá đúng ý định cho cài đặt mới/tham khảo trong màn Prompt
Templates, nhưng đó là phần bổ sung, không phải chỗ enforce chính.

Verify thật (script độc lập, dữ liệu mô phỏng đúng quy mô 31-block đã gặp thật ở mục
34): `sample_chapters()` trên 31 block → đúng 6 mốc rải đều (`ts_sec`: 0, 48, 96, 144,
192, 240). `_valid_chapters()`: mốc hợp lệ giữ nguyên, mốc `ts_sec` không khớp block nào
(hallucination giả lập) bị loại đúng 1/2, danh sách 20 mốc bị cắt còn 8, input rác/`None`
trả về `None` (rơi fallback) — cả 5 case đều đúng kỳ vọng. `pytest` 136/136 pass (không
có test cũ nào khoá số lượng chapters cụ thể, không cần sửa test). Restart Electron app
để nạp code mới.

## 39. Title sinh AI ở Pack Review: giới hạn còn 3 phương án, ưu tiên SEO thay vì đa dạng góc tiếp cận (2026-08-17)

Người dùng yêu cầu phần sinh Title chỉ gợi ý 3 tiêu đề có khả năng SEO tốt nhất trên
YouTube — trước đó prompt (`pt_thumb` v1) yêu cầu LLM sinh "5-10 tiêu đề tối ưu SEO+CTR",
đa dạng góc tiếp cận (`angle`: curiosity/benefit/seo...), không ưu tiên riêng SEO.

**Fix (cùng pattern mục 38 — hardcode ở code, không chỉ sửa template DB):**
- `generate_titles_and_meta()` — thêm chỉ dẫn hardcode trong phần cấu trúc JSON: trả
  ĐÚNG 3 tiêu đề, ưu tiên khả năng SEO (từ khoá đúng search intent người xem thực sự
  tìm, không phải giật tít/đa dạng góc tiếp cận), sắp SEO tốt nhất trước;
  `seo_score_hint` phải giải thích vì sao mạnh SEO (từ khoá, search intent) thay vì
  điểm CTR chung chung.
- `_MAX_TITLES = 3` — cắt cứng kết quả LLM còn tối đa 3 item (lọc thêm item sai kiểu/
  rỗng text trước khi cắt), phòng trường hợp LLM phớt lờ chỉ dẫn số lượng; nếu sau lọc
  rỗng hẳn → rơi về `fb.fallback_titles()` (không trả mảng rỗng cho UI).
- `fallback_content.fallback_titles()` (đường không có Provider AI) vốn ĐÃ trả đúng 3
  item từ trước — không cần sửa, tình cờ khớp sẵn yêu cầu mới.
- `seed.py::PROMPT_SEED["pt_thumb"]` thêm version "v3" tài liệu hoá đúng ý định (chỉ áp
  dụng cho cài đặt MỚI — xem lý do "hardcode ở code" đầy đủ ở mục 38, không lặp lại ở
  đây).

Verify thật (script độc lập, LLM giả lập cố tình trả 6 title bất chấp chỉ dẫn prompt chỉ
xin 3 — mô phỏng đúng rủi ro "LLM phớt lờ chỉ dẫn số lượng"): kết quả cuối cùng đúng 3
item, giữ đúng 3 item ĐẦU theo thứ tự LLM trả (khớp yêu cầu "sắp SEO tốt nhất trước").
`pytest` 136/136 pass (không có test cũ khoá số lượng titles cụ thể ngoài `>= 1`, không
cần sửa test). Restart Electron app để nạp code mới.

## 40. Title sinh AI: đổi mục tiêu SEO → Conversion/CTR + giới hạn cứng 50 ký tự (2026-08-17)

Tiếp nối mục 39 (vừa giới hạn còn 3 title, ưu tiên SEO) — người dùng đổi ý định: tối ưu
theo **Conversion** (khiến người xem đang lướt bấm vào xem — CTR) thay vì SEO từ khoá,
kèm giới hạn cứng **tối đa 50 ký tự/tiêu đề** (YouTube cắt tiêu đề dài ở nhiều vị trí
hiển thị — mobile, suggested videos — tiêu đề ngắn giữ trọn vẹn thông điệp).

**Fix (cùng pattern mục 38/39 — hardcode ở code, không chỉ sửa Prompt Template DB, xem
lý do đầy đủ ở mục 38):**
- Prompt: đổi hẳn hướng dẫn từ "SEO tốt nhất, đúng từ khoá search intent" sang
  "Conversion/CTR tốt nhất — tò mò/cảm xúc/lợi ích khiến bấm vào, không giật tít sai sự
  thật", thêm chỉ dẫn cứng "tối đa 50 ký tự (tính cả khoảng trắng), đếm kỹ trước khi
  trả". System message đổi từ "chuyên gia SEO YouTube" → "chuyên gia SEO & Conversion
  (CTR) cho YouTube" (giữ cả 2 vì cùng 1 lệnh gọi LLM còn sinh `youtube_description`
  hưởng lợi từ tư duy SEO, chỉ riêng `titles` đổi hẳn trọng số sang Conversion).
  `seo_score_hint` đổi ý nghĩa giải thích — giờ mô tả lý do mạnh về Conversion, không
  phải từ khoá SEO (tên field JSON giữ nguyên, tránh đổi schema không cần thiết).
- `fallback_content.cap_title()` (mới, `MAX_TITLE_CHARS = 50`) — cắt cứng còn tối đa 50
  ký tự, áp dụng ở CẢ 2 đường: `generate_titles_and_meta()` (sau khi lọc/cắt còn 3 item,
  map từng `text` qua `cap_title()`) VÀ `fallback_titles()` (đường không có Provider AI —
  trước đây có thể vượt 50 ký tự tuỳ độ dài `topic`, giờ luôn tuân thủ giới hạn).
  `angle` mặc định của title đầu tiên trong fallback đổi từ `"seo"` → `"conversion"` cho
  khớp mục tiêu mới (chỉ đổi nhãn, không đổi field key).

Verify thật (script độc lập, LLM giả lập cố tình trả **5 title** (vượt giới hạn 3), có 1
title dài vượt 50 ký tự, có 1 title rỗng): kết quả cuối cùng đúng 3 item, title dài bị
cắt CHÍNH XÁC còn 50 ký tự, title rỗng bị loại trước khi đếm đủ 3. `pytest` 136/136 pass.
Restart Electron app để nạp code mới.

## 41. Title: tăng giới hạn ký tự lên 90, bỏ cắt cứng ở backend — chỉ còn hướng dẫn trong prompt (2026-08-17)

Tiếp nối mục 40 (giới hạn cứng 50 ký tự ở cả prompt lẫn code) — người dùng đổi ý: tăng
lên **90 ký tự** và để LLM tự tuân thủ qua PROMPT, KHÔNG cắt cứng ở backend nữa.

**Fix:**
- `fallback_content.py` — xoá hẳn `MAX_TITLE_CHARS`/`cap_title()` (không còn nơi nào
  gọi tới). `fallback_titles()` trở lại text gốc không qua bước cắt.
- `generation.py::generate_titles_and_meta` — đổi hằng số `_TITLE_MAX_CHARS_HINT = 90`
  (thay `fb.MAX_TITLE_CHARS = 50` cũ), dùng trong CẢ prompt hướng dẫn LLM lẫn text
  fallback template mặc định (`get_template_body(...) or f"...tối đa
  {_TITLE_MAX_CHARS_HINT} ký tự..."`). Bỏ bước `fb.cap_title()` khỏi list comprehension
  lọc `titles` — giờ chỉ còn lọc item rỗng/sai kiểu + cắt SỐ LƯỢNG còn tối đa 3
  (`_MAX_TITLES`, KHÔNG đổi — người dùng chỉ yêu cầu bỏ cắt ký tự, không yêu cầu bỏ giới
  hạn số lượng).
- `seed.py::PROMPT_SEED["pt_thumb"]` thêm "v5" cập nhật con số 50→90 (chỉ áp dụng cài
  đặt mới, xem lý do "hardcode ở code" đầy đủ tại mục 38 — số 90 thực tế lấy hiệu lực từ
  hằng số trong `generation.py`, không phải từ bản ghi DB này).

Verify thật (script độc lập, LLM giả lập trả tiêu đề dài 88 ký tự — vượt mốc cũ 50 nhưng
dưới mốc mới 90): title trả về NGUYÊN VẸN không bị cắt (trước đây với `cap_title(50)` sẽ
bị cắt còn đúng 50). `pytest` 136/136 pass. Restart Electron app để nạp code mới.

## 42. Upload ảnh/video tay cho từng shot ở Visual Studio — thay thế AI, cùng shot_id (2026-08-17)

Người dùng yêu cầu: ở Visual Studio, cho phép upload ảnh/video từ máy cho MỖI shot, thay
thế cho sinh bằng AI — nếu shot đã có asset, upload phải THAY THẾ đúng shot_id đó (không
tạo ID mới) để đồng bộ với Pack Review/Output Center.

**Quyết định kiến trúc quan trọng — giữ đúng ranh giới "render.py không ghi lại
pack.json"** (docstring đầu `render.py`: "mọi endpoint ở đây chỉ ĐỌC pack.json..., không
bao giờ ghi lại"). Thiết kế ban đầu định cho upload TỰ ĐỘNG đổi `shot.visual_type` theo
loại file upload (VD shot đang "image" mà upload video thì tự chuyển "video") — vi phạm
ranh giới này vì phải ghi `pack.json` từ trong `render.py`. Chọn phương án khác: **loại
file upload PHẢI khớp `shot.visual_type` hiện có** — người dùng tự đổi tag Image/Video
(đã có sẵn, `PATCH /visual/shots/{id}` ở `pipeline.py`) TRƯỚC nếu muốn đổi loại, endpoint
upload không tự suy luận/ghi đè gì vào `pack.json`. Giữ nguyên kiến trúc cũ, không cần
sửa gì ở `pipeline.py`.

**Backend — `POST /projects/{id}/render/shots/{shot_id}/upload-visual`** (`render.py`,
model theo `pack.py::upload_thumbnail` + `channels.py::upload_voice_sample`'s content-
type/đuôi-file fallback):
- Nhận multipart `file`. Suy đuôi từ `Content-Type`, fallback theo đuôi tên file thật
  (trình duyệt/OS không phải lúc nào cũng gửi đúng MIME — cùng vấn đề đã gặp với voice
  sample, mục 13). Ảnh: PNG/JPEG/WEBP. Video: MP4/WEBM/MOV.
- Đọc `shot.visual_type` từ `pack.json` (read-only) — sai loại file so với type hiện có
  → 400 rõ ràng, gợi ý đổi tag Image/Video trước.
- Ghi file vào ĐÚNG slot `assets/{shot_id}.<ext>` — cùng path pattern
  `generate_visual_asset` dùng, đảm bảo "cùng ID". Nếu file cũ (từ AI sinh trước đó)
  khác đuôi (VD `.png` cũ, upload `.jpg` mới) → xoá file cũ, tránh rác trên đĩa; nếu
  cùng đuôi thì `write_bytes` tự ghi đè, không cần xoá.
- `engine._ensure_shot_entries()` — dùng được NGAY CẢ KHI chưa từng bấm "Bắt đầu sinh
  asset" (chưa có entry `render.json`), khác `regenerate-visual`/`approve` vốn 404 nếu
  chưa có entry — vì upload là đường THAY THẾ AI hoàn toàn, không nên bắt AI chạy trước.
- Cập nhật `ShotRenderStatus`: `visual_provider="upload"`, `visual_status="ready"`,
  `visual_error=None`, `approved=False` (asset mới → cần duyệt lại, cùng quy ước
  `regenerate_visual`). Đồng bộ (không qua BackgroundTasks, khác regenerate) — chỉ ghi
  file, không gọi AI. Vẫn giữ `_require_not_in_progress()` — tránh 2 request cùng ghi
  đè `render.json` nếu 1 batch AI đang chạy nền cho project.

**Frontend (`VisualStudio.tsx`)**:
- `api.uploadShotVisual(id, shotId, file)` (client.ts, mẫu `uploadThumbnail`).
- Mỗi `ShotCard` thêm nút **"↑ Upload ảnh/video"** (nhãn đổi theo `visual_type`) cạnh
  nút "Tạo ảnh/video" + `<input type="file">` ẩn, `accept` giới hạn đúng loại đang chọn.
  Lỗi upload (VD sai loại) hiện NGAY dưới nút của đúng thẻ shot đó — KHÔNG dùng banner
  lỗi chung đầu trang (không nêu rõ shot nào, dễ nhầm khi nhiều thẻ cùng lúc).
- **Bug thật phát hiện + fix cùng lúc**: `ShotPreview`'s `<img>/<video> src` dùng URL CỐ
  ĐỊNH theo shot_id — sau khi sinh lại/upload đè file, URL KHÔNG đổi nên browser không
  tự refetch, ảnh/video cũ vẫn hiện dù file trên đĩa đã đổi (CÙNG bug đã fix cho
  Thumbnail trước đó, mục 19 — hoá ra chưa bao giờ fix cho từng shot, chỉ chưa ai để ý
  vì trước đây chỉ có đường AI-sinh, ít khi "sinh lại" liên tục quan sát kỹ). Fix: thêm
  `shotCacheBust` (map shot_id → số đếm, bump sau MỖI lần sinh lại HOẶC upload thành
  công), gắn `?v=` vào URL — áp dụng cho CẢ 2 nút (regenerate lẫn upload), không chỉ
  upload.

Verify thật (`pytest`, 4 test mới trong `test_render.py`, KHÔNG mock endpoint — chỉ mock
HTTP ra ngoài của provider AI qua respx như mọi test khác trong file):
- `test_upload_shot_visual_replaces_asset_and_resets_approval` — upload `.jpg` đè lên
  shot đã có asset AI `.png`: `visual_provider` đổi "upload", `approved` reset False,
  file mới đúng bytes đã gửi, file `.png` cũ THẬT SỰ bị xoá khỏi đĩa (assert
  `Path(old_path).exists()` là False).
- `test_upload_shot_visual_works_before_render_start` — upload khi CHƯA từng gọi
  `render/start` — thành công, tự tạo entry.
- `test_upload_shot_visual_rejects_type_mismatch` — upload `.mp4` cho shot đang "image"
  → 400 đúng thông điệp.
- `test_upload_shot_visual_rejected_while_in_progress` — giả lập batch đang chạy
  (`engine._mark_in_progress`) → upload bị 409.

`pytest` 140/140 pass (136 cũ + 4 mới). `tsc --noEmit` sạch. Restart Electron app để nạp
backend mới.

## 43. 3 bug thật liên hoàn ở bước ghép MP4 khi dùng transition — video ngắn không loop, timebase lệch, ffmpeg hết bộ nhớ (2026-08-17)

Người dùng báo lỗi ở Output khi ghép video (project thật, 31 shot, có dùng transition,
video cuối 12+ phút) — "chạy hết các shot đến phần ghép cuối mới báo lỗi". Điều tra qua
3 vòng gọi API thật + đọc log thật (không suy đoán), phát hiện **3 bug độc lập, xếp lớp
lên nhau** — sửa bug 1 mới lộ ra bug 2, sửa bug 2 mới lộ ra bug 3.

### Bug 0 (tiền đề): `assembly_error` bị CẮT SAI ĐẦU chuỗi, che mất lý do lỗi thật

`assembly.py`'s `except subprocess.CalledProcessError` cũ ghi `(e.stderr or '')[:1000]`
— LẤY ĐẦU chuỗi. stderr ffmpeg LUÔN mở đầu bằng banner version+configuration (dài hơn
1000 ký tự), nên lý do lỗi thật (luôn ở CUỐI stderr) bị cắt mất, chỉ còn banner vô nghĩa
— lần đầu gọi `render/assemble` thật chỉ nhận được banner, không biết lỗi gì. Sửa: lấy
ĐUÔI chuỗi `(e.stderr or '').strip()[-2000:]` — nhờ vậy mới thấy được lỗi thật ở các bug
dưới đây.

### Bug 1: video ngắn hơn beat không được LOOP để lấp đủ thời lượng

`_build_segment` trước đây KHÔNG loop input video — `-i video.mp4 -t duration` chỉ cắt
tới hết độ dài THẬT của file, ngắn hơn `duration` nếu video gốc ngắn hơn (VD: AI sinh
video cố định "6s loopable" bất kể `duration` thật của beat dài hơn 6s; HOẶC video upload
tay ngắn hơn slot — B01 project thật: video upload 10s nhưng beat dài 40s). Segment build
ra CHỈ 10s trong khi `_xfade_chain`'s toán offset coi nó dài đúng 40s (dựa trên
`_beat_duration`, không phải đo thật từ file) → offset trỏ QUÁ độ dài thật của stream,
ffmpeg lỗi filter graph ở bước ghép cuối. **Fix**: `-stream_loop -1` cho MỌI input video
— vô hại nếu gốc dài hơn `duration` (chỉ đọc đủ, không cần loop tới), lặp lại tới đủ nếu
ngắn hơn, giữ đúng bất biến "mọi segment dài chính xác `duration`" như ảnh tĩnh (`-loop
1`). Nhân tiện sửa luôn `is_video` chỉ nhận diện `.mp4` cũ, bỏ sót `.webm`/`.mov` mà tính
năng upload (mục 42) cũng cho phép — `_VIDEO_ASSET_EXTS` mới gồm cả 3 đuôi.

### Bug 2: timebase lệch giữa segment ẢNH và segment VIDEO — lộ ra NGAY sau khi sửa bug 1

Sửa xong bug 1, gọi lại `render/assemble` thật → lỗi MỚI (nhờ bug 0 đã sửa, đọc được lý
do thật): `First input link main timebase (1/12288) do not match the corresponding
second input link xfade timebase (1/12800)`. Nguyên nhân đo thật: `_build_segment` không
ép framerate output — ảnh mặc định ra 25fps (`1/12800`-kiểu timebase), video giữ nguyên
framerate gốc của input (B01 upload: 24fps thật, đo bằng `ffprobe` →
`r_frame_rate=24/1`, `time_base=1/12288`). 2 segment khác nguồn (1 ảnh AI sinh, 1 video
upload) ra 2 timebase khác nhau — `xfade` KHÔNG chấp nhận chain 2 input lệch timebase.
**Fix**: thêm `fps={_OUTPUT_FPS}` (=30) vào `-vf` của MỌI segment, ép framerate/timebase
đồng nhất bất kể nguồn ảnh hay video. Đường KHÔNG-transition (concat demuxer, stream-
copy) không bị lỗi này nhưng cũng được chuẩn hoá framerate luôn — video xuất ra nhất
quán hơn, không đổi hành vi quan sát được của đường đó.

### Bug 3: ffmpeg hết bộ nhớ ("Cannot allocate memory") ở bước flush cuối — lộ ra sau khi sửa bug 2

Sửa xong bug 2, gọi lại `render/assemble` thật (project thật, 31 shot) → chạy ĐƯỢC RẤT
XA lần này (encode tới frame 24443/24469, gần như xong hẳn 12 phút 8 giây) nhưng lỗi
NGAY LÚC FLUSH CUỐI: `[fc#0] Task finished with error code: -12 (Cannot allocate
memory)`. Tái hiện được 2 lần liên tiếp, LUÔN đúng cùng 1 frame — xác nhận đây là lỗi
hết bộ nhớ THẬT do thiết kế filter graph, không phải flake ngẫu nhiên (loại trừ bằng đo
thật `nvidia-smi`/RAM hệ thống lúc đó vẫn còn ~19GB trống — không phải máy thiếu RAM nói
chung). Nguyên nhân: `_xfade_chain` bản đầu mở 1 lệnh ffmpeg DUY NHẤT với TẤT CẢ `n`
input cùng lúc (project thật có nhiều ranh giới transition trong 31 shot), chain toàn bộ
`xfade`/`acrossfade` trong 1 `filter_complex` — bộ nhớ đỉnh cần giữ tăng theo số input
mở đồng thời, tràn bộ nhớ ngay khi flush stream cuối của 1 video 12+ phút nhiều transition.

**Fix — ghép TUẦN TỰ từng cặp** (giống cách phần mềm dựng phim chuyên nghiệp xử lý nhiều
crossfade: gộp 2 rồi lấy kết quả gộp tiếp với cái kế tiếp), thay vì 1 lệnh khổng lồ — mỗi
lệnh ffmpeg CHỈ mở đúng 2 input, bộ nhớ đỉnh không còn phụ thuộc số lượng run. File trung
gian (`{out}_xstepNN.{ext}`) tự dọn ngay sau khi dùng xong (kể cả khi 1 bước sau đó lỗi,
nhờ `try/finally`). Đánh đổi: run ở giữa chain bị re-encode qua nhiều thế hệ hơn (hao chất
lượng nhẹ theo số transition, transition vốn chỉ ~0.6s/lần) — chấp nhận được vì ưu tiên là
ghép XONG được, không phải chất lượng transition tuyệt đối.

### Verify thật

- 2 test mới real-ffmpeg cho bug 1 (`test_build_segment_loops_short_video_to_fill_target_duration`,
  `test_build_segment_recognizes_webm_and_mov_as_video`): dựng video 2s thật, yêu cầu
  segment 5s, xác nhận output THẬT SỰ dài ~5s (loop hoạt động); dựng `.webm` thật, xác
  nhận nhận diện đúng nhánh video.
- 1 test mới cho bug 2 (`test_xfade_chain_handles_mixed_image_and_video_framerates`):
  dựng 1 run từ ảnh (25fps mặc định) + 1 run từ video 24fps thật, gọi `_xfade_chain`
  thật — trước fix lỗi đúng thông điệp timebase trên, sau fix ghép thành công.
- 1 test mới cho bug 3 (`test_xfade_chain_merges_incrementally_and_cleans_up_intermediates`):
  3 run thật (bắt buộc >2 để exercise nhánh tạo+dọn file trung gian, khác test 2-run ở
  trên) — ghép xong đúng, file trung gian bị xoá sạch (không để rác), duration hợp lý.
- **Verify trên chính project thật của người dùng** (`prj_1786897577764`, 31 shot, 12+
  phút, nhiều transition) qua API thật, không chỉ test đơn vị: gọi lại `render/assemble`
  nhiều lần sau mỗi fix — bug 1+2 xác nhận hết hẳn (encode chạy trọn tới gần cuối, lỗi
  chuyển hẳn sang bug 3 mới); bug 3 (OOM) tái hiện đúng 2 lần liên tiếp CÙNG frame trước
  fix, xác nhận không phải flake. Do đang chỉnh sửa dở dang backend khác (mục 44) nên
  KHÔNG kịp chạy lại full 12 phút lần cuối trên chính project này sau fix bug 3 — lần
  cuối cùng gọi lại thì phát hiện người dùng đang chỉnh sửa ĐỒNG THỜI project này (asset
  B01 vừa đổi từ video upload sang ảnh khác ngay giữa lúc verify, `render.json` chưa kịp
  đồng bộ) nên dừng, không tiếp tục ép chạy trên dữ liệu đang thay đổi — độ tin cậy của
  fix bug 3 dựa trên: (a) 3 test real-ffmpeg ở trên đều pass, (b) cơ chế 2-input-1-lúc về
  bản chất loại trừ đúng nguyên nhân đã xác định (không giữ nhiều input mở đồng thời).
  Khuyến nghị người dùng tự thử lại "Ghép MP4" 1 lần trên project thật để xác nhận cuối.

`pytest` 138/138 pass (full suite, thêm 5 test mới ở mục này). Backend touched — restart
Electron app.

## 44. Bỏ hẳn luồng AI Research/Outline/Hook/Full-Script + Pack Review/Gate #2 — chỉ còn "Upload script" (2026-08-17)

Theo yêu cầu người dùng: "Bỏ bước outline&hook và Pack review vì không còn cần thiết
nữa. Tập trung vào luồng chính: upload script, tạo visual và voice, sau đó render."
Xác nhận phạm vi qua 2 câu hỏi làm rõ trước khi bắt tay sửa (đổi lớn, ảnh hưởng cả CLAUDE.md's
nguyên tắc lõi #3 "2 human-gate bắt buộc"):
- AI Research/Outline/Hook: **bỏ HẲN**, không giữ làm tuỳ chọn — "Upload script" (import
  CSV/Excel, đã có sẵn từ trước) là con đường DUY NHẤT còn lại để có script.
- Pack Review: **bỏ hẳn cả 2 việc** nó đang làm — (1) sinh Title/Description bằng AI
  (bỏ luôn, không giữ ở đâu khác), (2) gate duyệt bắt buộc trước Output (bỏ hẳn, Output
  mở ngay). Thumbnail giữ nguyên — tính năng thật đã sống độc lập ở `ThumbnailCard`
  (Visual Studio) từ trước, không phụ thuộc Pack Review.

Luồng MỚI: **Brief (tuỳ chọn) → Upload script → Script Studio → Visual Studio → Output**
(4 bước, trước là 6). KHÔNG còn gate duyệt bắt buộc nào giữa các bước — `render/assemble`
và `/export` tự kiểm trực tiếp trên dữ liệu thật (shot đã sẵn sàng + đã duyệt) thay vì
dựa vào `project.status` làm gate riêng.

### Backend

- **`pipeline.py`** — xoá `/research`, `/gate1` (+ `Gate1Body`), `/pack/build`,
  `/pack/titles-meta`, `/gate2` (+ `Gate2Body`) hoàn toàn. Xoá thêm `/script/regenerate`,
  `/script/approve`, `PATCH /script/text` — phát hiện qua đọc kỹ `ScriptStudio.tsx`:
  cả 3 chỉ phục vụ trạng thái "`script.body` rỗng, chỉ có `full_text`" (`showEditor`),
  trạng thái này TRƯỚC ĐÂY chỉ tạo được qua `/gate1` (AI viết Full Script) — một khi
  `/gate1` biến mất, KHÔNG còn đường nào tạo ra trạng thái đó nữa (import luôn set
  `body` ngay lập tức), nên cả 3 endpoint + UI tương ứng trở thành TỬ LỘ hoàn toàn, xoá
  luôn thay vì để treo (đây là phát hiện qua truy vết code thật, sâu hơn báo cáo ban đầu
  của research agent — báo cáo đó đề xuất GIỮ 2 hàm này).
- `_ensure_shots()` bỏ nhánh AI (`gen.generate_shots`, dùng khi `source != "import"`) —
  script MỚI luôn là `"import"`, nhánh AI vĩnh viễn không còn được gọi tới. Xoá luôn
  `_normalize_ai_shot` (chỉ dùng trong nhánh đó).
- `enter_output` (`/output/enter`) giờ set CẢ `step=3` LẪN `status="ready_output"` +
  `max_step_reached` — trước đây chỉ set `step` (vì `status` do `gate2` approve set),
  giờ không còn `gate2` nên `enter_output` phải tự làm trọn vẹn.
- Đổi số step: Brief=0 (không đổi), Script Studio=1 (trước=2), Visual Studio=2
  (trước=3), Output=3 (trước=5) — mọi chỗ set `p.step = N` trong `import_script_confirm`/
  `generate_visual_shots`/`enter_output` đã cập nhật khớp.
- **`generation.py`** — xoá `generate_research`, `generate_hooks`, `generate_full_script`,
  `regenerate_full_script`, `breakdown_script`, `generate_shots`, `generate_titles_and_meta`
  (+ helper `_valid_chapters`/hằng số liên quan). Giữ `regenerate_shot_visual_fx`/
  `regenerate_shot_audio_sfx` (Visual Studio, không liên quan).
- **`fallback_content.py`** — xoá `fallback_outlines`, `fallback_hooks`/`HOOK_TYPES`,
  `fallback_full_script`, `fallback_breakdown`, `fallback_shots`, `fallback_titles`,
  `sample_chapters`, `fallback_youtube_meta`. Giữ `fallback_visual_fx`/`fallback_audio_sfx`.
- **`schemas/__init__.py`** — xoá class `Outline`/`HookVariant`/`ResearchBlock`/
  `TitleConcept`/`ThumbnailConcept`/`YoutubeChapter`; xoá field `ProductionPack.research`/
  `.hooks`/`.titles`/`.thumbnail_concepts`, `YoutubeMeta.description`/`.hashtags`/
  `.chapters`. GIỮ `YoutubeMeta.thumbnail_*` (ThumbnailCard vẫn dùng). `Script.source`
  đổi default `"ai"` → `"import"` (giữ cả 2 giá trị trong `Literal` để đọc được project
  CŨ đã lưu trên đĩa — không có Alembic, không migrate dữ liệu cũ, chỉ đổi ý nghĩa
  code-level).
- **`render.py`**/**`export.py`** — bỏ gate `p.status not in READY_STATUSES`/
  `("ready_output","exported","published")` — `render/assemble` đã tự kiểm
  `not_ready`/`not_approved` trên `state.shots` từ trước (đủ chặt, gate status là thừa);
  `export` đổi sang chỉ cần `pack.get("script")` tồn tại.
- **`export.py`** — markdown export bỏ mục `## Titles`/`## YouTube Description` (field
  gốc đã xoá). Giữ `## Hook`/`## CTA` dù thường rỗng (field vẫn còn trong schema, không
  phải dead — không scope-creep vào format export ngoài phần trực tiếp liên quan).
- **`channels.py`** — bỏ `review_count` (đếm project `await_gate1`/`await_gate2`, không
  còn ý nghĩa gì khi 2 status đó không tồn tại nữa) khỏi `_channel_out`.
- **`models/__init__.py`** — `ProjectStatus` enum bỏ `researching`/`await_gate1`/
  `await_gate2` (decorative, không ràng buộc DB thật — SQLAlchemy column là `String`
  thường, đổi Python-level thuần tuý, không phải migration).
- **`projects.py`** — xoá `STEP_TO_STATUS` (dict chết từ trước, không ai import).
- **`seed.py`** — xoá 7 entry `PROMPT_SEED` chết (`pt_outline`/`pt_hook`/`pt_script`/
  `pt_script_revise`/`pt_script_breakdown`/`pt_thumb`/`pt_visual_shots_init`) — chỉ ảnh
  hưởng cài đặt MỚI (seed chỉ chạy 1 lần lúc bảng rỗng); cài đặt hiện có của người dùng
  vẫn còn các template cũ trong DB (mồ côi, không còn code nào gọi tới `task` key tương
  ứng) — chấp nhận được, không viết script dọn dữ liệu cũ (rủi ro thấp, chỉ là UI Prompt
  Templates hiện thêm vài mục không còn tác dụng).

### Frontend

- Xoá hẳn `Gate1Outline.tsx`, `PackReview.tsx`.
- `ProjectView.tsx` — step routing còn 4 nhánh (Brief/ScriptStudio/VisualStudio/Output).
- `statusMeta.ts` — `STEP_LABELS` còn 4 mục; `STATUS_LABEL`/`STATUS_DOT_COLOR` bỏ 3 status
  đã xoá.
- `BriefEditor.tsx` — bỏ nút "Bắt đầu Research"/`startResearch`/`aiError`/spinner busy
  liên quan; `ScriptImportControls` giờ là hành động DUY NHẤT ở header (trước đây "hoặc"
  giữa 2 lựa chọn).
- `ScriptStudio.tsx` — bỏ hẳn nhánh `showEditor` (textarea Full Script + "Tạo lại theo
  góp ý" + "Duyệt Full Script & bóc tách theo đoạn", cùng `ReturnBanner`) — dead UI vì
  backend không còn đường nào tạo trạng thái "chưa bóc tách" nữa (xem lý do ở mục
  Backend trên). Header giờ LUÔN hiện "Đi tới Visual Studio →", breakdown theo block
  luôn hiện thẳng (không còn `!hasBody` gate).
- `VisualStudio.tsx` — `goPackReview()`/nút "Xem Production Pack →" đổi thành `goOutput()`
  gọi thẳng `api.enterOutput` — nút "Đi tới Output →". `DEFAULT_YOUTUBE_META` bỏ field
  `description`/`hashtags`/`chapters` đã xoá khỏi schema.
- `client.ts` — xoá `runResearch`, `approveGate1`, `regenerateScript`, `editScriptText`,
  `approveScript`, `buildPack`, `generateTitlesMeta`, `gate2`.
- `types.ts` — xoá `Outline`, `HookVariant`, `ResearchBlock`, `TitleConcept`,
  `YoutubeChapter`; trim `YoutubeMeta`/`ProductionPack` khớp schema mới.
- `Dashboard.tsx` — bỏ dòng "X chờ duyệt" (gắn với `review_count` đã xoá).

### Verify

`pytest` 138/138 pass (đã trừ 4 test tử lộ do endpoint xoá, viết lại `test_pipeline_flow.py`
đi hết luồng mới, `test_render.py`'s 2 helper (`_drive_to_visual_studio`/
`_drive_to_ready_output`) đổi sang import CSV, `test_pack_thumbnail.py`'s helper set
`thumbnail_description` tay thay vì qua `pack/titles-meta` đã xoá, `test_no_provider.py`
xoá 4 test chỉ còn ý nghĩa với đường AI (research/gate1/titles-meta/visual-generate-AI),
giữ 2 test còn hợp lệ). `tsc --noEmit` sạch. Phát hiện thêm 1 bug thật khi viết test mới:
`TestClient` chạy `BackgroundTasks` ĐỒNG BỘ trong cùng request — 1 test gọi
`render/assemble` với bytes ảnh GIẢ (không phải PNG thật) làm ffmpeg THẬT treo, treo
LUÔN cả request test (không phải hang ngẫu nhiên — tái hiện ổn định, xác nhận bằng
`tasklist`/`Get-CimInstance` thấy đúng tiến trình `pytest`/ffmpeg con còn sống); sửa bằng
cách giả lập chưa cài ffmpeg (`monkeypatch shutil.which`, cùng pattern test khác đã dùng)
— chỉ cần xác nhận request được CHẤP NHẬN, không cần ffmpeg thật chạy xong.

## 45. Duration reflow khi ghép MP4 — video lệch độ dài không còn bị loop/cắt cứng, bù qua shot liền kề (2026-08-17)

### Bối cảnh

Sau khi mục 43 fix xong (video ngắn hơn `duration` beat được `-stream_loop -1` lấp đầy,
video dài hơn bị `-t duration` cắt cụt), người dùng phản hồi KHÔNG muốn cách xử lý đó
nữa — nêu đúng nguyên nhân gốc thường gặp nhất: video upload tay từ máy tính hầu như
không bao giờ khớp CHÍNH XÁC với `duration` beat tính từ timestamp kịch bản (khác video
AI sinh, vốn được prompt yêu cầu ~6s cố định nên mục 43 chủ yếu che được). Loop lặp lại
nhìn giả (lặp y hệt đoạn video), cắt cụt mất nội dung — cả 2 đều không phải điều người
dùng muốn.

### Yêu cầu người dùng (logic mới)

- Video NGẮN hơn `duration` của shot: phát ĐỦ (không loop) hết độ dài thật của video,
  phần thời lượng còn thiếu lấy ẢNH của shot SAU lấp vào — tức kéo dài thời lượng hiển
  thị ảnh của shot sau thêm đúng phần thiếu đó. Nếu là shot CUỐI (không có shot sau) thì
  kéo dài shot TRƯỚC thay vào.
- Video DÀI hơn `duration`: tương tự, phát đủ (không cắt), co ngắn thời lượng hiển thị
  ảnh của shot sau (hoặc trước, nếu là shot cuối) để bù — tổng độ dài toàn video giữ
  nguyên, chỉ dịch ranh giới giữa 2 shot.

### Thiết kế & implementation

`app/render/assembly.py::_reflow_video_durations(statuses, durations)` — hàm thuần, sửa
`durations` (list độ dài từng shot, tính từ `_beat_duration`/timestamp kịch bản)
IN-PLACE, chạy TRƯỚC vòng build segment. Với mỗi shot có asset là VIDEO
(`_VIDEO_ASSET_EXTS`, ảnh tĩnh luôn khớp chính xác `-loop 1` nên bỏ qua): đo độ dài thật
qua `_probe_audio_duration_sec` (tái dùng hàm ffprobe sẵn có ở `engine.py`, hoạt động
chung cho mọi container media chứ không riêng audio). Lệch <0.05s coi là sai số làm
tròn, bỏ qua. Lệch đáng kể → `donor = i+1` nếu có, else `i-1`, else bỏ qua (chỉ 1 shot
duy nhất, không ai để bù — rơi về lưới an toàn loop/cắt cũ ở `_build_segment`, mục 43
vẫn còn nguyên làm fallback). `durations[donor] += (assigned - actual)`,
`durations[i] = actual` — 1 công thức dùng chung cho cả 2 chiều lệch (thiếu/thừa).
`durations[donor]` chặn sàn `_MIN_DONOR_DURATION_SEC = 0.5` (tránh 1 shot bị co gần 0s,
ffmpeg xử lý segment cực ngắn không ổn định) — trường hợp chênh lệch vượt quá ngân sách
shot liền kề, chấp nhận tổng độ dài video trôi nhẹ thay vì tạo segment gần-0s.

`assemble_video()` được tách lại thành 3 pass rõ ràng thay vì 1 vòng lặp gộp:
validate+tính `durations` quy định (pass 1) → `_reflow_video_durations` (pass 2) →
build segment theo `durations` đã reflow (pass 3, không đổi logic build). Nhờ vậy
`_build_segment` nhận `duration == actual` cho shot vừa reflow — logic loop/cắt cũ ở đó
tự nhiên thành no-op (đọc đúng 1 lượt hết video).

Áp dụng cho MỌI video (cả AI sinh lẫn upload tay), không riêng đường upload — chênh lệch
có thể xảy ra ở cả 2 nguồn, không có lý do giới hạn phạm vi hẹp hơn yêu cầu.

### Verify thật

5 test mới trong `test_render.py` (real ffmpeg, dựng video 2s/5s/10s thật bằng
`testsrc=duration=N`, đo lại bằng `ffprobe` thật — không giả lập số):
`test_reflow_borrows_from_next_shot_when_video_shorter_than_slot`,
`test_reflow_borrows_from_previous_shot_when_last_shot_video_shorter`,
`test_reflow_shortens_next_shot_when_video_longer_than_slot`,
`test_reflow_clamps_donor_at_minimum_duration_floor`,
`test_reflow_skips_when_only_one_shot_no_donor_available`. `pytest` 143/143 pass (full
suite, không có test nào trong 138 test cũ bị vỡ — hành vi cũ chỉ thay đổi khi có video
lệch duration thật, các test cũ dùng ảnh/video khớp sẵn không kích hoạt reflow).

Backend touched — restart Electron app để áp dụng.

## 46. Mã hoá GPU (NVENC) cho bước Ghép MP4 — theo yêu cầu người dùng ("CPU render có vẻ lâu") (2026-08-17)

### Bối cảnh

Người dùng hỏi tại sao lúc render CPU tăng chứ không phải RAM/VRAM — trả lời: `CODEC_MAP`
(`assembly.py`) chỉ khai báo encoder SOFTWARE (`libx264`/`libx265`/`libvpx-vp9`), mã hoá
hoàn toàn bằng CPU, không đụng GPU (GPU chỉ dùng ở bước SINH ASSET, tách biệt hoàn toàn
với bước ghép). Người dùng yêu cầu thêm lựa chọn "GPU encode" vì thấy CPU render lâu.

### Điều tra trước khi code (real, không chỉ đọc code)

- `ffmpeg -encoders | grep nvenc` → xác nhận bản ffmpeg trên máy CÓ đăng ký
  `h264_nvenc`/`hevc_nvenc`/`av1_nvenc` — nhưng **không có `vp9_nvenc`** (giới hạn thật
  của ffmpeg, không phải thiếu cấu hình) → GPU encode chỉ áp dụng được cho H.264/H.265.
- Thử encode THẬT 1 frame bằng `h264_nvenc` trên máy dev (RTX 5060 Ti, driver NVIDIA
  576.88) → **THẤT BẠI thật**: `Driver does not support the required nvenc API version.
  Required: 13.1 Found: 13.0` — tức chỉ thấy encoder trong `ffmpeg -encoders` KHÔNG đủ để
  biết dùng được, driver NVIDIA phải đủ mới cho đúng NVENC API version mà bản ffmpeg này
  cần. Phát hiện này định hình lại thiết kế: PHẢI có bước kiểm tra khả dụng THẬT (encode
  thử), không chỉ tra danh sách encoder.
- `ffmpeg -h encoder=h264_nvenc` → xác nhận `-cq` (0-51, "Set target quality level... for
  constant quality mode in VBR") — cùng thang số với `CRF_TABLE` hiện có, dùng lại được
  luôn, không cần bảng quy đổi riêng cho GPU.

### Thiết kế & implementation

**`app/render/assembly.py`**:
- `_GPU_ENCODER_MAP = {"h264": "h264_nvenc", "h265": "hevc_nvenc"}` (không có `vp9`).
- `resolve_video_codec(codec, use_gpu) -> str` — trả tên encoder ffmpeg thật; `raise
  ValueError` nếu `use_gpu=True` với `codec="vp9"` (không có `vp9_nvenc`).
- `_quality_flags(video_codec, crf) -> list[str]` — trả `["-crf", N]` cho encoder CPU,
  `["-rc", "vbr", "-cq", N]` cho encoder có đuôi `_nvenc`. `_build_segment`/`_xfade_chain`
  đổi từ hardcode `"-crf", str(crf)` sang gọi hàm này — 1 điểm sửa, áp dụng đồng nhất cả
  2 chỗ build ffmpeg command.
- `probe_gpu_encoder(ffmpeg) -> (bool, str)` — encode THẬT 1 frame 64×64 bằng `h264_nvenc`
  (`-f lavfi -i color=... -frames:v 1 ... -f null -`, cực nhanh, không ghi file), cache
  theo đường dẫn `ffmpeg` (tránh probe lại mỗi lần gọi). Nếu fail, trả về tail stderr
  (500 ký tự cuối — cùng nguyên tắc lấy ĐUÔI chuỗi đã áp dụng cho `assembly_error`, mục
  43) làm message giải thích.
- `assemble_video()` thêm tham số `use_gpu: bool = False`, gọi `resolve_video_codec` để
  ra `video_codec` thật thay vì tra thẳng `CODEC_MAP[codec][0]`.

**`app/routers/render.py`**:
- `AssembleBody` thêm `use_gpu: bool = False`.
- **Route mới `GET /render/gpu-encode-status`** (machine-level, không gắn `project_id`)
  — gọi `probe_gpu_encoder` thật, trả `{available, message}`. Frontend gọi lúc MỞ màn
  cấu hình export, không đợi tới lúc bấm "Ghép video" mới biết fail — cùng nguyên tắc
  "báo lỗi sớm" đã áp dụng cho chuỗi bug ghép MP4 ở mục 43.
- `start_assemble` gọi `resolve_video_codec(body.codec, body.use_gpu)` NGAY trong router
  (bắt `ValueError` → `HTTPException(400)`) trước khi giao `BackgroundTasks` — tổ hợp
  GPU+VP9 bị chặn tức thì, không đợi assembly chạy rồi mới báo lỗi.

**Frontend (`RenderStudio.tsx`)**: checkbox "Mã hoá bằng GPU (NVENC) — nhanh hơn, giảm
tải CPU" cạnh dropdown Định dạng — ẨN khi chọn VP9 (không có encoder GPU), DISABLE +
hiện lý do (rút gọn 140 ký tự đầu, full text ở `title` tooltip) khi
`GET /render/gpu-encode-status` trả `available: false`. Đổi Định dạng sang VP9 tự tắt
`use_gpu` (tránh gửi tổ hợp 400 bất ngờ). `types.ts`/`client.ts` thêm
`GpuEncodeStatus`/`getGpuEncodeStatus()`, `AssembleConfig` thêm `use_gpu`.

### Verify

10 test mới trong `test_render.py` — pure-logic (`resolve_video_codec`/`_quality_flags`,
không cần ffmpeg thật), real-ffmpeg (`probe_gpu_encoder` — KHÔNG assert cứng `ok` là
True/False vì phụ thuộc driver máy chạy test, chỉ xác nhận không crash + cache đúng), và
router (`GET /render/gpu-encode-status` thật + giả lập thiếu ffmpeg;
`POST /render/assemble` với `use_gpu=true, codec=vp9` → 400 ngay, không kịp đổi
`assembly_status`). `tsc --noEmit` sạch. `pytest` 152/153 (1 lỗi là flake tiền tồn tại
đã biết — `UNIQUE constraint failed: prompt_template.id` do 2 test seed ID cùng
millisecond, xác nhận lại bằng cách chạy riêng test đó PASS — không liên quan thay đổi
này, xem ghi chú tương tự ở mục Errors and fixes của phiên làm việc).

**Giới hạn đã biết, không phải bug**: trên chính máy dev (RTX 5060 Ti, driver NVIDIA
576.88), GPU encode hiện **KHÔNG dùng được** — driver chưa đủ mới cho NVENC API version
mà bản ffmpeg 8.1.2-essentials (gyan.dev) yêu cầu (cần ~610.00 theo thông báo của ffmpeg,
tức cần cập nhật driver NVIDIA lên bản mới hơn). Checkbox sẽ tự hiện đúng trạng thái này
(disabled + lý do) nhờ `probe_gpu_encoder` — không phải lỗi ẩn, người dùng thấy ngay lý
do khi mở màn cấu hình export. Cập nhật driver NVIDIA là hành động phía người dùng, ngoài
phạm vi code có thể tự làm.

Backend + frontend touched — restart Electron app để áp dụng.

## 47. Bug thật: lỗi "Cannot allocate memory" TÁI HIỆN sau fix mục 43 — xfade vẫn re-encode lại TOÀN BỘ phần tích luỹ mỗi bước merge (2026-08-17)

### Bối cảnh

Người dùng đổi HẾT video trong project sang ẢNH TĨNH (loại trừ khả năng do bug reflow
mục 45) rồi thử ghép lại — vẫn gặp lại **y hệt lỗi đã tưởng đã fix ở mục 43**: ffmpeg
chạy tới gần hết video (~13 phút 38s, frame 28369, libx264 in đủ thống kê cuối cùng —
tức đã ENCODE XONG gần hết) rồi crash `Task finished with error code: -12 (Cannot
allocate memory)` ngay lúc filter graph thread (`fc#0`) đóng luồng.

### Root cause đúng (khác chẩn đoán ban đầu ở mục 43)

Fix mục 43 ("ghép tuần tự từng cặp") giảm ĐÚNG số input mở ĐỒNG THỜI (luôn = 2, không
còn N input trong 1 filter_complex khổng lồ) — nhưng **không giảm được tổng THỜI LƯỢNG**
mà `xfade` phải decode+re-encode ở MỖI lệnh. `xfade` xử lý filter graph trên TOÀN BỘ 2
input đưa vào, không chỉ đúng đoạn overlap ~0.6s — nghĩa là `current_path` (vế tích luỹ,
DÀI DẦN qua mỗi vòng lặp merge) vẫn bị decode+re-encode LẠI TOÀN BỘ ở MỖI bước. Tới bước
CUỐI (merge lớn nhất trong chain), `current_path` đã dài gần bằng CẢ video — 1 lệnh
ffmpeg dù chỉ mở "2 input" vẫn phải xử lý ~13+ phút qua filter graph, lỗi hết bộ nhớ y
hệt bug gốc. Tức fix mục 43 giảm memory chỉ tình cờ đủ cho lần verify trước (dừng giữa
chừng do phát hiện người dùng đang chỉnh sửa đồng thời, xem mục 43 phần Verify — chưa
verify được LẦN CHẠY TRỌN VẸN cuối cùng), không phải fix triệt để.

### Fix thật sự

Tách phần KHÔNG ĐỔI khỏi phần CẦN blend TRƯỚC khi gọi `xfade`, thay vì đưa cả
`current_path` (dù dài bao nhiêu) làm input0 trực tiếp:
1. **`head`** = phần ĐẦU `current_path` (trước `t` giây cuối, `t` = thời lượng
   transition ~0.6s) — cắt bằng `ffmpeg -i current_path -t {head_keep} -c copy` —
   **stream-copy, KHÔNG decode/re-encode**, chi phí gần như 0 bất kể `current_path` dài
   bao nhiêu phút (đọc/copy packet nén, không giải mã).
2. **`blend`** = `xfade` giữa ĐÚNG `t` giây CUỐI của `current_path` (seek nhanh + chính
   xác bằng `-ss {head_keep} -i current_path` — ffmpeg hiện đại decode-rồi-bỏ tới đúng
   mốc, KHÔNG snap về keyframe gần nhất, chỉ tốn ~1 GOP decode chứ không phải cả file)
   VỚI TOÀN BỘ `run_paths[i]` (`offset=0`, vì input0 giờ chỉ còn đúng `t` giây).
3. Ghép `[head, blend]` lại bằng `_concat_fast` (stream-copy, không re-encode thêm).

Chi phí decode+encode thật của `xfade` mỗi bước giờ CHỈ còn ~`t` giây + độ dài 1 run kế
tiếp — KHÔNG còn phụ thuộc `current_path` đã tích luỹ bao lâu, chặn đứng bug ở gốc. Chưa
áp dụng cắt đối xứng cho `run_paths[i]` (vế còn lại — 1 run đơn lẻ hiếm khi tự nó dài
bằng cả video, không có bằng chứng cần tới mức đó, không over-engineer trước khi có case
thật đòi hỏi).

### Verify

`test_xfade_chain_handles_mixed_image_and_video_framerates` + `test_xfade_chain_merges_
incrementally_and_cleans_up_intermediates` (đã có từ mục 43) — cập nhật assertion dọn
rác kiểm thêm `_xhead*`/`_xblend*` (file trung gian mới), vẫn pass. Thêm test MỚI
`test_xfade_chain_bounds_cost_by_trimming_accumulator_not_reprocessing_whole_video` — 6
run (thay vì 2-3) để `current_path` thật sự tích luỹ qua NHIỀU thế hệ, verify GIÁN TIẾP
(không đo được RAM thật trong unit test, không mô phỏng rẻ tiền video 13 phút trong CI):
tổng duration nằm trong dải hợp lý (loại trừ lỗi cộng dồn do cắt head/blend sai offset ở
ranh giới), file trung gian dọn sạch. `pytest` 47/47 pass trong `test_render.py`, full
suite 152/153 (1 lỗi là flake ID-collision tiền tồn tại đã biết, xác nhận lại bằng chạy
riêng PASS — không liên quan thay đổi này).

**Khuyến nghị người dùng**: thử lại "Ghép video" trên project thật — nếu vẫn gặp lỗi
tương tự (dù đã fix root cause đúng theo phân tích trên), gửi lại log ffmpeg đầy đủ để
điều tra tiếp (VD nếu 1 "run" đơn lẻ — chuỗi shot nối "cut" không transition — tự nó đã
rất dài, cần áp dụng cắt đối xứng cho `run_paths[i]` như ghi chú "chưa over-engineer" ở
trên).

Backend touched — restart Electron app để áp dụng.

## 48. Hiệu ứng chuyển động camera (Ken Burns) cho ảnh tĩnh ở Visual Studio (2026-08-19)

### Yêu cầu người dùng

Ngoài transition giữa 2 shot đã có (mục 33), thêm hiệu ứng mô phỏng góc nhìn/đường đi
máy quay áp lên MỘT ảnh tĩnh: Zoom in/out, Pan/Tilt (trái/phải/lên/xuống), Roll/Orbit.

### Thiết kế

`app/render/camera_motion.py` (mới, tách riêng khỏi `assembly.py` cùng lý do với
`transitions.py` — tránh import vòng): `CAMERA_MOTIONS: dict[str,str]` (9 giá trị, gồm
`"none"`) + `build_camera_motion_filter(motion, duration, out_w, out_h, fps) -> str |
None`, sinh chuỗi filter ffmpeg (`zoompan` cho zoom/pan/tilt/orbit, `rotate`+`crop` cho
roll). `Shot.camera_motion: str = "none"` (schema mới), PATCH `/visual/shots/{id}`
validate giá trị (cùng pattern `transition_to_next`/`TRANSITIONS`). `_build_segment`
(`assembly.py`) áp filter này CHỈ khi shot là ẢNH (`not is_video`) — video giữ nguyên
chuyển động thật, không đè Ken Burns lên.

### Bug thật phát hiện lúc code (quan trọng — quyết định thiết kế `roll` khác hẳn nhóm zoom/pan)

Thử nghiệm bằng ảnh test thật (4 ô màu góc + ô đen giữa, dựng qua `ffmpeg drawbox`, xem
bằng **Read tool đọc ảnh trực tiếp** — không chỉ đoán qua log) trước khi viết code chính
thức:
- `zoom_in`/`zoom_out`/`pan_*`/`tilt_*` (dùng biến nội bộ `zoompan` — `on`, `zoom` tự
  tham chiếu): verify đúng ngay lần đầu, xem ảnh trước/sau xác nhận đúng hướng.
- `roll` (thử đặt `rotate=a='...*sin(2*PI*t/...)'` NGAY TRƯỚC `zoompan`, dùng `zoompan`
  để crop che góc lộ ra khi xoay): **ra clip KHÔNG XOAY** dù công thức đúng toán học —
  trích frame giữa clip (t=0.5s, lẽ ra góc xoay đạt đỉnh) vẫn phẳng như frame đầu.
  Nguyên nhân: `zoompan` không re-sample filter NGƯỢC DÒNG mỗi output frame — nó chỉ kéo
  1 input frame rồi tự sinh `d` output frame TỪ CHÍNH input đó (đúng thiết kế gốc: giữ 1
  frame video, tự animate zoom/pan trên nó). Với `-loop 1` + `d=n_frames` (= cả clip),
  `zoompan` chỉ kéo input 1 LẦN DUY NHẤT (gần t≈0) — giá trị `rotate`'s `t` bị "đóng
  băng" tại đó, toàn clip ra góc gần 0°.
- **Fix**: `roll` KHÔNG dùng `zoompan` — dùng `rotate` (filter per-frame bình thường,
  `t` cập nhật đúng mỗi frame nhận được) + `crop` TĨNH (margin cố định 1/1.15, đo thật
  đủ che góc lộ ra ở rotate ±3°) thay cho `zoompan`. Verify lại bằng ảnh test (viền đen
  gần cạnh, còn nằm trong margin crop): frame giữa clip xoay rõ, không lộ góc đen.

### Verify

7 test mới real-ffmpeg trong `test_render.py`: coverage tạo filter string cho cả 8 hiệu
ứng (bắt lỗi cú pháp biểu thức từng nhánh), `zoom_in` (lấy mẫu pixel — điểm gần góc thoát
khỏi vùng màu đỏ sau khi zoom, tâm ảnh nở to), `pan_left` (lấy mẫu pixel 2 góc đối diện,
đảo vị trí đúng hướng), `roll` (xác nhận KHÔNG lộ góc đen ở 4 góc khung + xác nhận pixel
THẬT SỰ đổi màu giữa frame đầu/giữa — test này SẼ FAIL nếu bug "đóng băng" ở trên tái
diễn, bắt regression trực tiếp), video-shot không bị áp camera_motion (output giống hệt
dù truyền `camera_motion="zoom_in"`), PATCH endpoint validate giá trị (400 nếu sai).
`pytest` 161/161 pass (full suite). `tsc --noEmit` sạch (frontend: `VisualStudio.tsx`
thêm dropdown "Chuyển động camera" trong `ShotCard`, chỉ hiện khi `visual_type ===
"image"`, khớp `CAMERA_MOTIONS` phía backend — cùng pattern `TRANSITION_OPTIONS`).

Backend + frontend touched — restart Electron app để áp dụng.

## 49. Bug thật: video player ở Render Studio không tua được — Starlette FileResponse thiếu HTTP Range (2026-08-20)

### Bối cảnh & nguyên nhân thật (xác nhận bằng đọc source, không đoán)

Người dùng báo player video ở Render Studio (thẻ `<video src={renderDownloadUrl}>`)
không tua (seek) được. Đọc thẳng `starlette/responses.py` trong `.venv` cài
(`starlette==0.38.6`) — **`FileResponse` KHÔNG xử lý header `Range` ở BẤT KỲ đâu**
(grep "range"/"206"/"Accept-Ranges" trong cả file: 0 kết quả) — luôn trả `200 OK` +
NGUYÊN file bất kể trình duyệt yêu cầu byte range nào. Trình duyệt `<video>`/`<audio>`
seek bằng cách gửi `Range: bytes=X-Y` — server bỏ qua hoàn toàn nên không tua được.

### Fix

`app/rangefile.py` (mới) — `range_file_response(request, path, *, media_type, filename)`:
không có header `Range` → trả `FileResponse` như cũ (thêm `Accept-Ranges: bytes` để
trình duyệt biết CÓ THỂ tua ở lần sau); có `Range` → parse `bytes=start-end` (hỗ trợ cả
dạng mở `bytes=1000-`), đọc đúng đoạn byte yêu cầu qua `open().seek()+read()` theo chunk
1MB (không load cả file vào RAM), trả `StreamingResponse` 206 + `Content-Range`/
`Accept-Ranges`/`Content-Length` đúng chuẩn RFC 7233; Range sai định dạng → 416.

Áp dụng cho MỌI endpoint phục vụ video/audio (cùng 1 bug gốc, sửa hết 1 lượt thay vì
chỉ chỗ người dùng tình cờ phát hiện): `render.py::get_shot_asset` (preview shot ở
Visual Studio), `render.py::download_render` (player + nút tải Render Studio),
`render.py::download_narration_full`, `channels.py::get_voice_sample` (nghe mẫu giọng
thương hiệu). Ảnh/document (`pack.py`, `export.py`) giữ nguyên `FileResponse` — không ai
"tua" 1 file JSON/ảnh tĩnh, ngoài phạm vi bug.

### Verify

5 test mới `test_rangefile.py` — dựng 1 app Starlette TỐI GIẢN (không đụng router thật),
verify qua HTTP thật (không mock nội bộ): không Range → 200 + `Accept-Ranges`; Range
đóng (`bytes=10-19`) → 206 + đúng byte; Range mở (`bytes=1000-`) → đúng tới hết file;
Range vượt quá kích thước file → tự kẹp về cuối file; Range sai định dạng → 416. `pytest`
166/166 pass (full suite).

## 50. Hiệu ứng camera "hơi bị giật" — chuyển động tuyến tính thiếu ease-in/ease-out (2026-08-20)

### Điều tra thật (loại trừ từng giả thuyết bằng đo đạc, không sửa mò)

Người dùng phản hồi hiệu ứng camera (mục 48) "ổn nhưng hơi bị giật". Điều tra qua nhiều
giả thuyết, MỖI giả thuyết đều verify bằng dựng ảnh test + đo pixel thật (không đoán):

1. **Nghi ngờ 1: `roll` bị duplicate frame do input `-loop 1` mặc định 25fps rồi convert
   sang 30fps.** Đo `ffprobe -show_entries frame=pts_time` trên clip roll thật — PTS
   cách đều tuyệt đối `0.033333s` (=1/30s) suốt clip, KHÔNG có duplicate/lệch nhịp. Loại
   trừ giả thuyết này.
2. **Nghi ngờ 2: `zoompan` làm tròn x/y về pixel nguyên trên ảnh trung gian quá nhỏ
   (upscale 2x chưa đủ).** Dựng ảnh gradient ngang (đen→trắng), lấy mẫu 1 pixel cố định
   qua TỪNG frame của clip pan — thấy dáng "bậc thang" (delta 0-3 mức xám/frame không
   đều). Test lại với upscale 6x VÀ với `-qp 0` (lossless, loại trừ nhiễu nén H.264) —
   dáng bậc thang gần như KHÔNG đổi. Kết luận: đây là nhiễu làm tròn nhỏ (~1-2 mức xám)
   VỐN CÓ của bất kỳ chuyển động rời rạc hoá nào, không phải nguyên nhân chính của cảm
   giác "giật" — không đáng để tăng upscale (không cải thiện, chỉ tốn thêm CPU/RAM).
3. **Nghi ngờ 3 (đúng, xác nhận bằng đo tốc độ theo từng vùng clip): chuyển động TUYẾN
   TÍNH — vận tốc KHÔNG ĐỔI suốt clip — khởi động/dừng ĐỘT NGỘT ở 2 đầu.** Đo "vận tốc"
   (delta mức xám giữa 2 mốc cách nhau 8 frame) ở 3 vùng của clip gradient pan (dữ liệu
   lossless thật): đầu clip (frame 0→8) = **2** mức xám/8-frame; giữa clip (frame
   26→34) = **8**; cuối clip (frame 51→59) = **3**. Camera thật không bao giờ bắt đầu/
   dừng chuyển động tức thời — vận tốc không đổi (đặc biệt việc DỪNG ĐỘT NGỘT đúng lúc
   shot kết thúc) tạo cảm giác máy móc, đúng khớp mô tả "giật" của người dùng.

### Fix

`app/render/camera_motion.py` — thêm `_eased_progress(n_frames)`: tỉ lệ tiến trình
0..1 làm mượt bằng **smoothstep** (`3f²-2f³`, `f = on/(n-1)`) thay vì tuyến tính thô.
`_zoom_expr` đổi từ CÔNG THỨC ĐỆ QUY (`zoom+step` tự tham chiếu frame trước, chỉ ra được
tuyến tính đều) sang HÀM ĐÓNG theo `on` (`z_start+(z_end-z_start)*eased_progress`) — áp
easing trực tiếp được. `_linear_expr` (dùng cho pan/tilt) đổi tương tự. Ảnh hưởng:
`zoom_in`/`zoom_out`/`pan_*`/`tilt_*`/`orbit` (đều gọi `_zoom_expr`/`_linear_expr`) đều
được easing; `roll` (dùng `sin()` chu kỳ qua `rotate`, không qua 2 hàm trên) giữ nguyên
— dao động hình sin vốn đã mượt tự nhiên ở đỉnh, không có vấn đề dừng-đột-ngột như
chuyển động tuyến tính.

### Verify

Đo lại CHÍNH XÁC cùng phép đo (delta 8-frame, 3 vùng) trên clip pan SAU fix: đầu=nhỏ,
giữa=lớn, cuối=nhỏ — đúng dáng ease-in/ease-out (khác hẳn dáng "mọi vận tốc bằng nhau"
trước fix). Test mới `test_camera_motion_pan_eases_in_and_out_instead_of_constant_
velocity` mã hoá lại đúng phép đo này — assert vận tốc giữa clip > đầu VÀ > cuối, sẽ
FAIL nếu ai đó lỡ đổi lại về tuyến tính (bắt regression trực tiếp). 8 test camera_motion
cũ (biên độ/hướng chuyển động ở frame ĐẦU và CUỐI clip) vẫn pass nguyên — smoothstep(0)=0
và smoothstep(1)=1 nên giá trị 2 ĐẦU clip không đổi, chỉ đường đi Ở GIỮA đổi. `pytest`
167/167 pass (full suite).

### Tiếp theo: người dùng báo VẪN còn giật riêng ở zoom in/out sau fix easing ("it still zoom in/out but the screen is stuttering")

Easing (trên) sửa đúng vấn đề "khởi động/dừng đột ngột" nhưng KHÔNG phải toàn bộ nguyên
nhân — điều tra thêm 1 vòng, tiếp tục loại trừ bằng đo đạc thay vì đoán:

- Kiểm tra lại DUPLICATE FRAME + PTS timing cho chính `zoom_in` (trước đó mới đo cho
  `roll`) — dựng ảnh caro (checkerboard, hợp để lộ alias/shimmer hơn gradient phẳng),
  hash MD5 toàn bộ 60 frame: **60/60 hash khác nhau** (không frame nào lặp), PTS cách
  đều tuyệt đối `1/30s`. Loại trừ nguyên nhân "player giật vì lặp/thiếu frame".
- Kiểm tra lại độ đơn điệu (monotonic) của vị trí crop qua TỪNG frame (không chỉ 3 mốc
  đầu/giữa/cuối như lần trước) trên clip zoom_in đã easing — dãy giá trị pixel giảm dần
  ĐỀU, không có điểm nào tăng ngược (không "rung"/dao động qua lại). Loại trừ nguyên
  nhân toán học sai.
- Kết luận: nguyên nhân còn lại là **thiếu motion blur**. Ken Burns số hoá — mỗi frame
  là 1 ảnh crop SẮC NÉT TUYỆT ĐỐI (zoompan không blur) — trong khi máy quay thật luôn có
  motion blur tự nhiên khi di chuyển. Đặc biệt rõ trên nội dung có chi tiết mịn (test
  bằng ảnh caro — đường kẻ mảnh "nhảy" rõ giữa các frame liên tiếp dù vị trí crop bên
  dưới hoàn toàn mượt về mặt số học) — đây là hiện tượng đã biết rộng rãi khi làm Ken
  Burns bằng phần mềm, không riêng ffmpeg (cùng lý do phim/video tốc độ khung hình thấp
  không blur nhìn "giật cục" hơn có blur dù cùng framerate).

**Fix**: thêm `tmix=frames=3:weights='1 1 1'` (trộn trung bình 3 frame liên tiếp, ~0.1s
cửa sổ ở 30fps) vào CUỐI MỌI filter chain camera motion (`build_camera_motion_filter`
refactor: mỗi nhánh giờ build `core`, hàm trả `f"{core},{_MOTION_BLUR}"` chung 1 chỗ —
không lặp lại ở từng nhánh) — mô phỏng motion blur nhẹ, xoá cảm giác "đứng hình"/khựng
giữa các frame mà không làm mờ hẳn nội dung. Verify bằng ảnh caro: frame giữa clip cho
thấy rõ viền mờ nhẹ (ghosting) ở vùng đang di chuyển nhanh — đúng hiệu ứng blur mong
muốn, khác hẳn viền sắc cạnh cứng trước fix.

`pytest` 167/167 pass (full suite, không test nào cần sửa — `tmix` không đổi số frame/
duration, chỉ làm mờ nhẹ nội dung; các test biên frame ĐẦU/CUỐI vẫn qua ngưỡng
`_approx_rgb` tol=12 vì frame đầu gần như không bị blur — `tmix` chỉ có 1 frame khả dụng
tại đó — và frame cuối chuyển động đã gần như dừng hẳn nhờ easing nên 3 frame gần nhau
gần giống hệt nhau, blur không đáng kể).

Backend touched — restart Electron app để áp dụng.

## 51. Video/audio thương hiệu (BrandProfile) + shot mở đầu riêng của project (2026-08-20)

### Yêu cầu người dùng

1. Màn Sửa BrandProfile: upload video HOẶC audio thương hiệu (tuỳ chọn, CHỈ 1 trong 2)
   — phát ở ĐẦU MỌI video của kênh khi ghép MP4. Chỉ có audio → minh hoạ bằng ẢNH của
   shot đầu tiên trong từng project.
2. Visual Studio: shot mở đầu RIÊNG của project (tuỳ chọn) — ảnh+audio đi kèm (bắt buộc
   audio nếu ảnh) hoặc video. Nếu "đủ", OVERRIDE HẲN video/audio thương hiệu cấp kênh.

### Thiết kế

- `BrandProfile` (`app/schemas/__init__.py`) thêm `intro_video_path`/`intro_audio_path`
  — mutual exclusivity do ENDPOINT tự đảm bảo (upload 1 loại tự xoá field còn lại +
  file cũ trên đĩa), không phải validation ở schema.
- `RenderState` (`app/render/schemas.py`) thêm `intro: Optional[IntroAssetStatus]` —
  KHÔNG gắn với `pack.shots` (không phải AI sinh, không timestamp trong kịch bản) —
  đúng nguyên tắc "render module tách biệt script core". `IntroAssetStatus.kind`
  ("image"/"video") tự suy theo file upload, không phải người dùng chọn tay.
- Endpoint mới: `POST/GET /channels/{id}/brandprofile/intro(/upload)` (channels.py,
  cùng pattern voice-sample); `POST /projects/{id}/render/intro/upload-visual`,
  `POST .../upload-audio`, `DELETE .../intro`, `GET .../intro/asset/{kind}` (render.py).
  Tất cả dùng `range_file_response` (mục 49) — có `<video>`/`<audio>` preview cần tua.
- `app/render/assembly.py::_resolve_intro_source(intro, brand, shots, by_id)` — thứ tự
  ưu tiên ĐÚNG yêu cầu: shot mở đầu project (nếu "đủ") > video thương hiệu kênh > audio
  thương hiệu kênh (kèm ảnh shot đầu tiên, chỉ dùng được nếu shot đó đã sinh xong).
  `_build_intro_segment` — `kind=="video"` GIỮ NGUYÊN audio gốc của chính file đó (khác
  `_build_segment` vốn `-an`/audio ngoài cho video B-roll); `kind=="image"` tái dùng
  `_build_segment` (ảnh tĩnh + 1 audio ngoài, thời lượng = độ dài audio đo qua ffprobe).
  `assemble_video()`: thân video (shot list) build ra `body.{ext}` riêng khi có intro,
  rồi ghép intro+thân thành `final.{ext}` ở bước cuối.

### 2 bug thật phát hiện lúc viết test end-to-end (real ffmpeg, không mock)

1. **Stream-copy concat làm méo timestamp**: dự định ban đầu dùng `_concat_fast`
   (stream-copy, như mọi nơi khác trong assembly.py) để ghép intro+thân — lỗi thật
   `Application provided invalid, non monotonically increasing dts to muxer`. Nguyên
   nhân: `_concat_fast` giả định MỌI file "tương thích" ở mức SPS/PPS/GOP (đúng với thân
   video — mọi segment LUÔN qua cùng 1 pattern lệnh `_build_segment` lặp lại), nhưng
   intro build từ 1 lệnh ffmpeg ĐỘC LẬP xử lý nội dung gốc RẤT khác (video thương hiệu
   người dùng tự upload, encoder/GOP bất kỳ) — dù ép cùng resolution/fps/codec/crf, vẫn
   không đủ để stream-copy an toàn. **Fix**: `_concat_intro_and_body` — dùng filter
   `concat` (decode 2 input rồi RE-ENCODE liền mạch) thay vì stream-copy, chấp nhận chi
   phí re-encode thêm 1 lần (chỉ 2 input, giống cách `_xfade_chain` re-encode ở ranh
   giới transition) để đổi lấy đúng đắn tuyệt đối.
2. **Thân video có thể KHÔNG có audio track nào** khi ghép với intro (luôn có audio):
   project không narration + không transition trước đây build thân với `-an` (hợp lệ
   khi đứng riêng) — nhưng filter `concat=n=2:v=1:a=1` đòi cả 2 input có audio, lỗi
   "Stream specifier ':a:0' ... matches no streams". Fix: `needs_audio_track =
   has_transitions or bool(intro_source)` — ép mọi segment thân có audio track (câm
   nếu cần) bất cứ khi nào sẽ ghép intro vào.

### Verify

24 test mới `test_intro.py`: upload/xoá/mutual-exclusivity ở cả 2 cấp (kênh + project),
`_resolve_intro_source` (5 test logic thuần, đủ 5 tình huống ưu tiên/fallback/thiếu),
`_build_intro_segment` (2 test real ffmpeg), và **2 test end-to-end THẬT** (dựng brand
intro video màu ĐỎ + 1 shot ẢNH màu XANH LÁ, gọi `assemble_video()` thật, xác nhận bằng
lấy mẫu pixel frame đầu ra ĐÚNG màu đỏ không phải xanh lá; test thứ 2 xác nhận shot mở
đầu project màu VÀNG override đúng brand intro đỏ) — 2 test này bắt được CẢ 2 bug thật ở
trên (không phát hiện được nếu chỉ test logic `_resolve_intro_source` suông). `pytest`
193/193 pass (full suite, 1 flake ID-collision tiền tồn tại đã biết không liên quan).
`tsc --noEmit` sạch — `ChannelDialog.tsx` thêm mục "Video/Audio thương hiệu" (mirror UI
mẫu giọng đọc, 2 nút upload loại trừ nhau); `VisualStudio.tsx` thêm `IntroShotCard`
(mirror `ThumbnailCard`) ngay dưới Thumbnail, trên danh sách shot.

Backend + frontend touched — restart Electron app để áp dụng.

### Bug thật + phản hồi UX sau khi người dùng tự test (2026-08-20, cùng ngày)

Người dùng test thật báo 4 vấn đề:

1. **"Upload audio ở brand profile, render lại video, nhưng ko thấy ghép vào đầu video"**
   và 4. **"có vẻ khi có cả audio brand profile và shot mở đầu, shot mở đầu chưa override"**
   — viết 3 test end-to-end THẬT mới để điều tra riêng 2 case này (đo pixel/âm lượng,
   không đoán): `test_assemble_prepends_brand_intro_audio_only_with_first_shot_image`,
   `test_assemble_project_intro_overrides_brand_audio_only_intro`,
   `test_assemble_project_intro_audio_only_uses_first_shot_image` — **cả 3 đều PASS
   ngay**, xác nhận logic backend (`_resolve_intro_source`) đã đúng từ đầu. Kết luận:
   nguyên nhân thật KHÔNG phải backend mà là **cache trình duyệt phía preview** — cả
   player video cuối cùng (`RenderStudio.tsx`) LẪN preview intro
   (`ChannelDialog.tsx::brandIntroUrl`) dùng URL CỐ ĐỊNH (không đổi giữa các lần ghép/
   upload) — trình duyệt không tự refetch, người dùng nhìn thấy bản CŨ dù backend đã
   ghi đè file mới đúng (CÙNG lớp bug đã biết ở `ThumbnailCard`, lần này quên áp dụng
   fix "cacheBust" cho 2 chỗ mới thêm). **Fix**: thêm `cacheBust` state (query string
   `?v=N`, bump sau mỗi lần upload/ghép xong) cho `RenderStudio.tsx`'s player + cả 2
   preview trong `ChannelDialog.tsx` (giọng đọc thương hiệu VÀ intro — mẫu giọng đọc
   hoá ra cũng thiếu fix này từ trước, sửa luôn 1 thể).
2. **"Xóa audio và Upload video, nhưng vẫn hiện lại audio đã upload ở phần trước"** —
   liên quan tới bug cache ở trên, NHƯNG còn 1 vấn đề UX thật: nút "Xoá" trước đây CHỈ
   xoá draft cục bộ (phải bấm "Lưu thay đổi" mới xoá thật ở server) — đổi thành PERSIST
   NGAY (gọi PUT luôn trong `removeBrandIntro()`), khớp kỳ vọng "Xoá" = xoá thật.
3. **UX request**: "chia thành 3 nút: upload video, upload ảnh, upload audio" (thay vì 1
   nút gộp ảnh/video) + "Khi có audio mà ko có ảnh thì sử dụng ảnh ở shot đầu tiên ngay
   sau đó luôn" (áp dụng cho CHÍNH shot mở đầu project, không chỉ audio thương hiệu cấp
   kênh). Backend: `upload_intro_audio` bỏ ràng buộc "phải có ảnh trước" (400 cũ), cho
   upload audio ĐỘC LẬP; `resolve_intro_source` (`app/render/intro.py`) thêm nhánh mới
   — project chỉ có audio (không ảnh/video) → mượn ảnh shot đầu tiên, VẪN ưu tiên hơn
   thương hiệu cấp kênh (đây vẫn là lựa chọn riêng của project). Frontend: `IntroShotCard`
   tách nút gộp thành "Upload video"/"Upload ảnh" riêng, nút "Upload audio" luôn hiện
   (không còn ẩn cho tới khi có ảnh), disable khi đang là video.

`pytest` full suite pass (thêm test cho audio-only project intro + test upload audio độc
lập). `tsc --noEmit` sạch.

## 52. Timestamp kịch bản chỉ tham khảo — render & transcript dùng độ dài giọng đọc THẬT (2026-08-20)

### Bug thật người dùng báo

"video khi render đang theo timestamp của block, vài trường hợp timestamp duration của
shot quá dài 40s trong khi giọng đọc chỉ có 34s, phải đợi 6s mới chạy tiếp giọng đọc tiếp
theo" — timestamp kịch bản (nhập tay lúc import CSV/Excel, VD "0:00–0:40") chỉ là ước
lượng của người dùng, không phải số đo thật; trước đây `assemble_video()` dùng ĐÚNG số
này làm độ dài segment (`_beat_duration`) bất kể giọng đọc TTS sinh ra dài bao nhiêu —
giọng đọc ngắn hơn để lại "khoảng chết" (ảnh đứng yên, không tiếng) tới hết đủ 40s mới
cắt sang shot kế tiếp.

Yêu cầu người dùng: (1) render dùng độ dài giọng đọc THẬT, không dùng timestamp; (2)
transcript export cũng đổi theo, dùng timeline giọng đọc thật; (3) phải cover cả case có
intro (video/audio thương hiệu HOẶC shot mở đầu riêng, mục 51) — transcript phải offset
đúng theo độ dài intro thật để khớp video ghép ra, không lệch.

### Thiết kế

**Vấn đề vòng import**: `routers/pipeline.py` (chứa endpoint transcript .srt) KHÔNG thể
import trực tiếp `app/render/engine.py` hay `app/render/assembly.py` — `engine.py` đã
import NGƯỢC LẠI từ `routers/pipeline.py` (`record_asset_usage`), tạo vòng nếu import
thêm chiều kia. Giải quyết bằng tách 2 module MỚI, KHÔNG phụ thuộc gì trong app (cùng
mẫu `transitions.py`/`camera_motion.py`):
- `app/render/media_probe.py::probe_duration_sec(path)` — logic ffprobe THẬT chuyển ra
  từ `engine.py::_probe_audio_duration_sec` (giữ lại alias tên cũ trong `engine.py`,
  mọi chỗ import cũ không cần đổi).
- `app/render/intro.py::resolve_intro_source`/`intro_duration_sec` — chuyển từ
  `assembly.py` (vốn định nghĩa `_resolve_intro_source` riêng, mục 51) sang module dùng
  CHUNG được — vừa giải quyết vòng import, vừa đảm bảo `assembly.py` (ghép MP4 thật) VÀ
  `pipeline.py` (transcript) tính offset intro Y HỆT NHAU (không lệch do 2 nơi tự suy
  luận riêng).

**Render** (`app/render/assembly.py`): `_shot_base_duration(status, beat)` — hàm mới,
thay thế lời gọi `_beat_duration()` trực tiếp trong vòng lặp build segment: ưu tiên
`status.narration_duration_sec` (đo thật qua ffprobe lúc sinh TTS, đã có sẵn field này
từ trước) khi `narration_status=="ready"`, fallback về `_beat_duration()` (timestamp
kịch bản) khi CHƯA sinh giọng đọc. `_reflow_video_durations` (mục 45, xử lý video lệch
slot) chạy SAU, không đổi — vẫn hoạt động đúng trên baseline mới (chỉ đổi NGUỒN số đầu
vào, không đổi thuật toán reflow).

**Transcript** (`app/routers/pipeline.py::_build_srt`): đổi hẳn cách tính cue — thay vì
dùng `timestamp_sec`/`end_sec` của TỪNG block độc lập, giờ CỘNG DỒN (cursor) độ dài giọng
đọc thật của shot khớp `block_id` (fallback về ước lượng timestamp CHỈ khi chưa sinh
giọng đọc cho shot đó — transcript vẫn xuất được sớm, trước khi hoàn tất Visual Studio).
`intro_offset` (đo qua `intro_duration_sec(resolve_intro_source(...))`, cùng dữ liệu
render.json + BrandProfile mà `assemble_video()` dùng) cộng vào MỌI cue — transcript
khớp đúng thời điểm video ghép ra THẬT bắt đầu phát nội dung kịch bản (sau khi intro
phát xong), không phải bắt đầu từ giây 0 nếu có intro.

### Verify

7 test mới `test_render.py` (`_shot_base_duration` × 2 pure-logic, 1 test end-to-end
THẬT — timestamp kịch bản ghi 8s nhưng giọng đọc thật ~2s, `assemble_video()` thật, xác
nhận video ra dài ~2s KHÔNG PHẢI ~8s) + 6 test mới `test_transcript.py` (`_build_srt` ×
5 pure-logic bao gồm "cue cộng dồn theo giọng đọc thật, không dùng lại timestamp gốc"
và "offset intro dịch mọi cue", + 1 test endpoint end-to-end THẬT với brand audio intro
+ giọng đọc thật, xác nhận cue transcript bắt đầu ĐÚNG sau intro). `pytest` full suite
pass (kể cả 2 module mới `media_probe.py`/`intro.py`, không phát sinh vòng import —
xác nhận bằng chạy full suite thật, không chỉ đọc code). `tsc --noEmit` không đổi (tính
năng này thuần backend).

Backend touched — restart Electron app để áp dụng.

## 53. Nhạc nền (background music) + Thư viện Creative Asset (2026-08-20)

### Yêu cầu người dùng

1. Upload nhạc nền MẶC ĐỊNH cho kênh (BrandProfile) — phát đè liên tục dưới TOÀN BỘ
   video (kể cả intro) khi ghép MP4 cho mọi project của kênh đó.
2. Cho phép TỪNG project override riêng nhạc nền ở Visual Studio (tương tự cách shot mở
   đầu — `IntroShotCard`, mục 51 — override video/audio thương hiệu cấp kênh).
3. Chỉnh tỷ lệ âm lượng nhạc nền so với giọng đọc chính (channel: `bg_music_volume`,
   project override: field `volume` riêng trong `BgMusicOverride`).
4. Trang quản lý Thư viện Creative Asset (nhạc nền/video/ảnh/giọng đọc) — entry point
   "Thư viện" ở sidebar dưới Dashboard — cho phép chọn asset đã lưu thay vì luôn phải
   upload lại từ máy ở MỌI màn có tính năng upload (voice sample, intro thương hiệu,
   shot mở đầu project, ảnh/video từng shot, thumbnail, nhạc nền), + nút "Thêm vào thư
   viện" ngay sau khi upload thành công ở các màn đó.

### Thiết kế — nhạc nền

Cùng cấu trúc ưu tiên như intro (mục 51): `RenderState.bg_music` (project,
`BgMusicOverride{asset_path, volume}`) ưu tiên hơn `BrandProfile.bg_music_path`/
`bg_music_volume` (kênh) — xem `app/render/bg_music.py::resolve_bg_music_source`, module
ĐỘC LẬP không phụ thuộc `engine.py` (cùng lý do `intro.py`/`transitions.py`/
`camera_motion.py` — `engine.py` import ngược `routers/pipeline.py` ở top-level, nên
`pipeline.py` không bao giờ được import `engine.py`/`assembly.py`).

Trộn nhạc nền là bước HẬU KỲ CUỐI CÙNG trong `assemble_video()` — SAU khi thân video +
intro (nếu có) đã ghép xong thành `final_path`, ghi đè lại chính `final_path` bằng
`_mix_bg_music()` (`app/render/assembly.py`). Verify THẬT bằng ffmpeg trước khi viết code
(không đoán): `-stream_loop -1` lặp vô hạn nhạc nền ngắn hơn video, `[1:a]volume=X[bg];
[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[a]` trộn 2 nguồn audio và
CHẶN ĐÚNG output ở độ dài input ĐẦU (video) — đo bằng ffprobe xác nhận không bị kéo dài
vô hạn theo nhạc nền lặp, kể cả KHÔNG cần thêm cờ `-t`/`-shortest`. `-c:v copy` giữ
nguyên video (chỉ audio cần decode+re-encode qua `amix`).

`needs_audio_track` (biến quyết định MỌI segment có track audio, kể cả câm) được mở rộng
thêm `or bool(bg_music_source)` — `_mix_bg_music` luôn giả định `final_path` có sẵn
`[0:a]` để trộn vào, cùng nguyên tắc đã áp dụng cho intro/transition ở mục 51/43.

Endpoint mới:
- Kênh: `POST/GET /channels/{id}/brandprofile/bg-music(/upload)` (`channels.py`) — luôn
  audio, tái dùng `_VOICE_EXT_BY_*`. Chỉnh volume qua `PUT .../brandprofile` sẵn có. Bỏ
  nhạc nền: PUT lại `bg_music_path=""` (cùng pattern intro/voice-sample, không cần route
  xoá riêng).
- Project: `POST/PATCH/DELETE/GET /projects/{id}/render/bg-music(/upload|/asset)`
  (`render.py`) — `PATCH` chỉnh `volume`, tự tạo `BgMusicOverride` nếu chưa có (chỉnh
  volume trước khi kịp upload file vẫn hợp lệ). `DELETE` xoá hẳn file, cùng nguyên tắc
  `delete_intro`.

### Thiết kế — Thư viện Creative Asset

Bảng SQLite mới `creative_asset` (`app/models/__init__.py::CreativeAsset` — id, kind,
name, file_path, created_at), ĐỘC LẬP không FK channel/project nào — file vật lý lưu ở
`workspace/library/<kind>/` (`app/config.py::LIBRARY_DIR`/`library_kind_dir`), NGOÀI
`channels/` (dùng chung toàn app). Router mới `app/routers/library.py`: `GET
/library/assets?kind=`, `POST /library/assets/upload?kind=`, `DELETE
/library/assets/{id}`, `GET /library/assets/{id}/file` (Range-request qua
`range_file_response`, mục 49).

**Quyết định kiến trúc quan trọng** (tránh phình route): KHÔNG thêm endpoint
"-from-library" song song ở MỌI nơi upload hiện có (voice sample, intro, shot visual,
bg music, thumbnail...). Thay vào đó, `LibraryPicker.tsx` (component dùng chung, mở modal
liệt kê asset theo `kind`) khi người dùng chọn 1 asset sẽ `fetch()` bytes qua
`GET .../file`, gói lại thành `File` bằng `new File([blob], name)`, rồi gọi THẲNG API
upload SẴN CÓ ở nơi gọi (y hệt luồng người dùng tự chọn file từ máy — "asset thư viện ==
1 File trình duyệt đưa cho app"). Tương tự, `AddToLibraryButton.tsx` (dùng chung) sau khi
1 nơi bất kỳ đã upload xong, `fetch()` blob từ CHÍNH URL đang hiển thị asset đó rồi POST
sang `/library/assets/upload`. Kết quả: **0 thay đổi** ở mọi endpoint upload đã có sẵn
trong app — đã wiring cả 2 component này vào: voice sample + intro thương hiệu (kênh,
`ChannelDialog.tsx`), nhạc nền kênh (`ChannelDialog.tsx`, mới), shot mở đầu project +
ảnh/video từng shot + thumbnail + nhạc nền project (`VisualStudio.tsx`, cả mới lẫn cũ).

Frontend mới: `screens/Library.tsx` (trang quản lý — 4 mục theo kind, mỗi mục lưới card
preview + nút xoá + nút upload trực tiếp), `components/LibraryPicker.tsx`,
`components/AddToLibraryButton.tsx`. Sidebar (`components/Sidebar.tsx`) thêm mục "Thư
viện" (icon sách) ngay dưới Dashboard — `AppContext.tsx` thêm `view: "library"` +
`goLibrary()`.

`VisualStudio.tsx` thêm `BgMusicCard` (component mới, cùng cấu trúc `IntroShotCard`) —
upload/xoá nhạc nền riêng của project + thanh trượt âm lượng (`onMouseUp`/`onTouchEnd`
mới PATCH, không PATCH liên tục theo từng pixel kéo).

### Verify

Backend: 33 test mới (`test_bg_music.py` 25 test — CRUD kênh/project + logic thuần
`resolve_bg_music_source` + 1 test `_mix_bg_music()` REAL ffmpeg xác nhận nhạc nền lặp
đúng và bị chặn đúng độ dài video (audio gốc video cố tình để CÂM — tiếng đo được ở giây
thứ 2 CHỈ có thể tới từ nhạc nền đã lặp, không lẫn nguồn khác) + 2 test end-to-end
`assemble_video()` THẬT (nhạc nền phủ hết đầu-cuối video, và project override đúng bài
kiểm bằng lọc `highpass=f=2000` phân biệt tần số brand/project, không chỉ "có tiếng" mà
xác nhận đúng NGUỒN nào đang phát); `test_library.py` 13 test — upload/list/filter/
delete/serve từng kind, từ chối kind không khớp file). `pytest` full suite: **238
passed** (không phát sinh vòng import mới — `bg_music.py` độc lập, xác nhận `from
app.main import app` load sạch trước khi chạy test). `tsc --noEmit`: **0 lỗi** trên toàn
bộ thay đổi frontend (types, client, Sidebar/AppContext, ChannelDialog, VisualStudio,
Library screen, 2 component mới).

Chưa verify bằng mắt/tai qua UI thật (Electron) trong phiên này — người dùng chủ động
yêu cầu dừng lại sau khi implement xong để tự test sau (xem log phiên làm việc).

## 54. Đổi tên asset thư viện — sau khi "Thêm vào thư viện" và ở màn Thư viện (2026-08-21)

### Yêu cầu người dùng

1. Cho phép edit tên asset SAU KHI bấm "Thêm vào thư viện" ở các màn cho phép thêm
   (voice sample, intro, shot visual, bg music...).
2. Cho phép edit tên asset tại màn quản lý "Thư viện".

### Thiết kế

Tên gợi ý ban đầu do `AddToLibraryButton` tự đặt theo ngữ cảnh nơi gọi (VD
"shot-mo-dau", "nhac-nen-kenh" — xem mục 53) không phải lúc nào cũng đúng ý người dùng —
cần sửa lại được mà không phải vòng qua màn Thư viện riêng. Thêm 1 endpoint DÙNG CHUNG
cho cả 2 yêu cầu thay vì 2 cơ chế riêng: `PATCH /library/assets/{asset_id}` (body
`{name}`) — chỉ đổi cột `name` hiển thị, KHÔNG đụng `file_path`/file vật lý trên đĩa
(tên hiển thị độc lập với tên file, không cần đồng bộ 2 chiều). 400 nếu tên rỗng (sau
`strip()`), 404 nếu asset không tồn tại.

Frontend:
- `AddToLibraryButton.tsx`: sau khi upload xong (`state === "done"`), thay vì chỉ hiện
  chữ tĩnh "Đã thêm vào thư viện ✓", giờ hiện TÊN THẬT + nút "Sửa tên" → bấm vào hiện
  input inline (Enter = Lưu, Esc = Huỷ) ngay tại chỗ, gọi `renameLibraryAsset` rồi cập
  nhật lại tên hiển thị từ response (không cần refetch danh sách — component này không
  giữ danh sách, chỉ giữ đúng 1 asset vừa tạo).
- `Library.tsx`: tách `AssetCard` thành component riêng (trước đây render trực tiếp
  trong `.map()`) — mỗi card tự giữ state `editing`/`nameDraft` riêng, nút "Sửa tên"
  cạnh nút "Xoá" sẵn có, Lưu xong gọi lại `load()` của `LibrarySection` cha để đồng bộ
  toàn danh sách (khác `AddToLibraryButton` — màn này CÓ giữ danh sách nên cần refetch).

### Verify

4 test mới `test_library.py` (đổi tên thành công + giữ nguyên file phục vụ được bình
thường, tự `strip()` khoảng trắng, 400 khi tên rỗng, 404 khi asset không tồn tại) —
**242 passed** toàn bộ `pytest` (2 lần chạy đầu dính đúng flake `_new_id` cộng dồn mili-
giây đã biết trước đó — mục "Known pre-existing flaky test" đầu tài liệu này — xác nhận
bằng chạy lại riêng lẻ, không phải regression). `tsc --noEmit`: 0 lỗi.

Backend + frontend đều đổi — restart Electron app để áp dụng.

## 55. Hiệu ứng chuyển cảnh cho Shot mở đầu (intro) + gộp nút "Chọn từ thư viện" (2026-08-21)

### Yêu cầu người dùng

1. Bổ sung cài đặt hiệu ứng chuyển cảnh cho Shot mở đầu (intro) ở Visual Studio.
2. Rà soát lại các nút "Chọn từ thư viện" để chỉ giữ 1 nút/mục — bấm vào mở danh sách
   audio/video/ảnh tương ứng để chọn, thay vì 1 nút RIÊNG cho từng loại file chấp nhận.

### Thiết kế — hiệu ứng chuyển cảnh intro

`IntroAssetStatus` (`app/render/schemas.py`) thêm `transition_to_next: str = "cut"` —
CÙNG bảng giá trị `app/render/transitions.py::TRANSITIONS` dùng cho `transition_to_next`
giữa 2 shot thường (mục 33). Endpoint mới `PATCH /projects/{id}/render/intro/transition`
(`render.py`), validate y hệt `pipeline.py::patch_shot`, tự tạo `IntroAssetStatus` nếu
chưa có (cùng pattern `patch_project_bg_music_volume`, mục 53 — chỉnh trước khi kịp
upload asset vẫn hợp lệ).

`assembly.py::assemble_video` — trước đây ghép intro+thân LUÔN cắt cứng
(`_concat_intro_and_body`, filter concat không xfade). Giờ rẽ nhánh theo
`state.intro.transition_to_next`: `"cut"` giữ nguyên đường cũ; giá trị khác dùng LẠI
`_xfade_chain` (cùng cơ chế xfade/acrossfade đã verify kỹ cho shot-to-shot, mục 43/47) —
coi intro + thân video như 2 "run" nối bằng 1 transition duy nhất
(`_xfade_chain(ffmpeg, [intro_path, body_path], [intro_dur, body_dur], [transition],
final_path, ...)`), đo thời lượng THẬT của cả 2 qua `app.render.intro::intro_duration_sec`
(intro) + `_probe_audio_duration_sec` (thân, alias `probe_duration_sec` — tên gọi "audio"
nhưng hàm dùng chung ffprobe `format=duration`, hoạt động đúng với video). Tái sử dụng
NGUYÊN VẸN `_xfade_chain` — không viết thêm code merge riêng, tận dụng cơ chế trim-head-
rồi-blend đã proven đúng đắn (đầu vào bất kỳ, độc lập nguồn gốc encode).

Frontend: `IntroShotCard` (`VisualStudio.tsx`) thêm dropdown "Chuyển cảnh sang shot đầu
tiên" (tái dùng `TRANSITION_OPTIONS` đã có sẵn cho shot-to-shot), gọi
`api.patchIntroTransition` ngay khi đổi.

### Verify — hiệu ứng chuyển cảnh

7 test mới `test_intro.py`: 3 test PATCH thuần (set giá trị, 400 khi sai, tự tạo
`IntroAssetStatus` khi chưa có) + 1 test end-to-end THẬT (`assemble_video()` 2 lần,
không mock) — ghép "cut" rồi ghép lại "fade" với CÙNG nội dung, đo `ffprobe` xác nhận
tổng thời lượng "fade" NGẮN HƠN RÕ RỆT so với "cut" (blend ~0.6s chồng lấp, đúng cơ chế
`_xfade_chain` đã biết — không chỉ chạy không lỗi mà XÁC NHẬN THẬT SỰ có blend).

### Thiết kế — gộp nút "Chọn từ thư viện"

`LibraryPicker.tsx` đổi prop `kind: CreativeAssetKind` (1 loại) → `kinds:
CreativeAssetKind[]` (nhiều loại cùng lúc) — fetch + gộp danh sách asset của MỌI kind
được truyền vào (kèm tag nhãn loại trong modal nếu >1 kind để phân biệt), `onPick` vẫn
chỉ nhận `File` (nơi gọi tự biết cách xử lý dựa trên `file.type`, không cần thêm tham số
kind). Áp dụng gộp ở 2 chỗ trước đây có NHIỀU nút cùng 1 mục:
- **Video/Audio thương hiệu** (`ChannelDialog.tsx`): 2 nút (`kind="video"` +
  `kind="music"`) → 1 nút `kinds={["video","music"]}`.
- **Shot mở đầu (intro)** (`VisualStudio.tsx::IntroShotCard`): 3 nút (video/ảnh/audio) →
  1 nút `kinds={["video","image","music"]}`, `onPick` route theo `file.type.startsWith(...)`
  (video/ → upload visual dạng video, image/ → upload visual dạng ảnh, còn lại → upload
  audio).

Các mục CHỈ chấp nhận đúng 1 loại (mẫu giọng, nhạc nền kênh/project, ảnh/video từng shot,
Thumbnail) giữ nguyên 1 nút — chỉ đổi cú pháp prop (`kind="x"` → `kinds={["x"]}"`), không
đổi hành vi.

### Verify — gộp nút thư viện

`tsc --noEmit`: 0 lỗi trên toàn bộ 6 call site đã đổi prop. Không có test backend riêng
(thuần UI, không đổi endpoint/logic backend nào) — xác nhận bằng đọc lại từng call site
chỉ còn ĐÚNG 1 `<LibraryPicker>` mỗi mục (`grep "LibraryPicker kind="` không còn khớp
đâu trong `frontend/src/`).

`pytest` full suite: **246 passed**. Backend + frontend đều đổi — restart Electron app.

## 56. Bug thật: "Sinh lại giọng đọc" xong vẫn nghe giọng CŨ, dù đã cài voice clone (2026-08-21)

### Bug người dùng báo

Project "Skip brief test": bấm "Tạo lại giọng đọc" ở Visual Studio, kỳ vọng dùng giọng
voice clone đã cài ở BrandProfile (mẫu giọng upload qua "Giọng đọc thương hiệu",
OmniVoice) — nhưng preview `<audio>` vẫn phát ra giọng CŨ y hệt trước khi bấm.

### Điều tra thật (không sửa mò)

1. Kiểm tra DB: TTS provider mặc định của app ĐÚNG LÀ `omnivoice` (`is_default=True`,
   `enabled=True`, server `http://127.0.0.1:8199` sống, `/health` trả `model_loaded:true`)
   — không phải bug chọn sai provider.
2. Kiểm tra `BrandProfile.voice_clone_ref_path` của kênh — có giá trị, file `voice_
   sample.mp3` tồn tại thật trên đĩa. `app/render/engine.py::_read_voice_clone_ref` đọc
   đúng, truyền `reference_audio` vào `provider.synthesize()` — code path đúng.
3. Gọi THẲNG `POST /projects/{id}/render/shots/{shot_id}/regenerate-narration` (API
   thật, không mock) cho shot B01 của ĐÚNG project người dùng báo — đo `mtime`/`sha256`
   của `assets/B01.wav` TRƯỚC và SAU: cả 2 đều đổi (file thật sự được ghi lại, không
   phải no-op), `narration_provider` vẫn là `"omnivoice"`.
4. Gọi thẳng OmniVoice server `/synthesize` 2 lần (CÙNG câu text) — 1 lần KHÔNG kèm
   `ref_audio`, 1 lần KÈM `ref_audio` = mẫu giọng thương hiệu thật của kênh — 2 file kết
   quả KHÁC HẲN nhau (size/hash khác) → xác nhận voice cloning THẬT SỰ có tác dụng ở tầng
   model, không phải bug "ref_audio bị bỏ qua".

**Kết luận: backend hoàn toàn đúng — sinh lại giọng đọc THẬT SỰ dùng voice clone, file
trên đĩa THẬT SỰ đổi.** Bug nằm ở FRONTEND: `ShotPreview` (`VisualStudio.tsx`) render
`<audio src={api.renderShotAssetUrl(projectId, shot.shot_id, "narration")}>` — URL CỐ
ĐỊNH theo `shot_id`, KHÔNG có cache-bust (`?v=`) như visual asset cùng component ĐÃ có
(`assetUrl` dòng ngay trên). Browser cache HTTP theo URL, không quan tâm file trên đĩa
đã đổi — phát lại đúng bản ĐÃ cache trước đó, y hệt cùng lớp bug cache-bust đã gặp nhiều
lần trước (Thumbnail/IntroShotCard/ChannelDialog...) nhưng LẦN NÀY bị bỏ sót ở audio
narration vì `regenNarrationAsset` cũng CHƯA từng gọi `bumpShotCacheBust()` (chỉ
`regenVisualAsset`/`uploadVisualAsset` gọi).

### Fix

- `regenNarrationAsset` (`VisualStudio.tsx`) — thêm `bumpShotCacheBust(shotId)` ngay sau
  khi trigger sinh lại (cùng thời điểm `regenVisualAsset` đã làm) — bump TRƯỚC khi sinh
  xong là đủ, vì `<audio>` chỉ mount SAU KHI `narration_status` chuyển "ready" (trước đó
  bị gỡ khỏi DOM do điều kiện `{status?.narration_status === "ready" && (...)}` false).
- `ShotPreview` — audio narration src đổi thành `...?v=${cacheBust}` (khớp pattern
  `assetUrl` visual đã có).
- `ScriptStudio.tsx::playShotAudio` — cùng lớp bug tiềm ẩn (gán `audioRef.current.src`
  TĨNH theo shot_id để phát preview kịch bản, không cache-bust) — sinh lại giọng ở Visual
  Studio rồi quay về Script Studio bấm play vẫn có thể dính cache cũ trong CÙNG phiên
  Electron. Fix bằng `Date.now()` (hàm này vốn chạy lại mỗi lần bấm play, không cần state
  đếm riêng như nơi khác).

### Verify

`tsc --noEmit`: 0 lỗi. Xác nhận thật bằng field investigation ở trên (mtime/hash file
đổi thật, output OmniVoice có/không ref_audio khác nhau thật) TRƯỚC khi kết luận nguyên
nhân — không đoán mò rồi sửa nhầm chỗ. Không có test tự động cho cache-bust UI (đặc thù
hành vi browser HTTP cache, không kiểm được qua pytest/tsc) — cùng cách các fix cache-
bust trước đó trong dự án chỉ verify bằng đọc code + giải thích cơ chế.

Frontend đổi — restart Electron app để áp dụng (backend không đổi, không có ảnh hưởng
gì tới dữ liệu đã sinh trước đó).

## 57. Bug thật: video render "không ghép được giọng đọc" — audio mất hẳn sau intro (2026-08-21)

### Bug người dùng báo

Project "Skip brief test": video render xong (assembly_status="done", không lỗi) nhưng
KHÔNG NGHE THẤY giọng đọc.

### Điều tra thật (không sửa mò)

1. `render.json` của project: `assembly_status="done"`, không lỗi, cả 2 shot
   `narration_status="ready"` với `narration_provider="omnivoice"`, có intro (video,
   `transition_to_next="fade"` — tính năng mới mục 55) + nhạc nền project (volume 1.0).
2. `ffprobe` file `final.mp4`: CÓ stream audio (aac), duration 16.49s hợp lý — không phải
   thiếu hẳn track audio.
3. Quét `mean_volume`/`n_samples` theo từng giây: 0-8s (trong intro) có tiếng thật;
   **từ ~9.6s trở đi (ngay sau điểm intro→thân video) `n_samples: 0` — audio HOÀN TOÀN
   TRỐNG tới hết video.** Đây là điểm mấu chốt: không phải "nhỏ tiếng", audio thật sự
   biến mất từ đúng ranh giới intro/thân video.
4. Tách riêng từng segment shot (`segments/segment_000.mp4`, `segment_001.mp4`) — CÓ
   tiếng thật, đúng narration. `ffprobe` stream audio: **`sample_rate=24000,
   channels=1`** — khác hẳn 44.1kHz stereo dùng ở MỌI nơi khác trong app (nhạc nền,
   video thương hiệu upload, audio câm `anullsrc`).
5. Tái hiện TRỰC TIẾP bước ghép intro+thân (`_xfade_chain`) bằng chính file thật của
   project: lệnh `acrossfade` cảnh báo `"... is shorter than crossfade duration ...,
   crossfade will be shorter by 4 samples"` và output blend ra **`24000 Hz, mono`**
   (lẽ ra phải 44.1kHz stereo) — xác nhận: khi 2 audio input lệch sample rate/kênh
   (intro 44.1kHz stereo vs thân video 24kHz mono) đi qua `acrossfade`/`concat`
   filter, ffmpeg tự "chọn" theo 1 bên (không báo lỗi cứng) → bước `_concat_fast`
   (stream-copy) NGAY SAU ĐÓ nối 2 file có audio định dạng khác nhau, kết quả AUDIO
   CỦA PHẦN SAU BỊ RỖNG (đã tái hiện + đo được y hệt lỗi thật, không suy đoán).

**Nguyên nhân gốc**: narration của provider **OmniVoice xuất ra 24kHz MONO** (đúng
sample rate của chính model, `omnivoice_server.py` ghi WAV theo `model.sampling_rate` —
KHÔNG chuẩn hoá). `app/render/assembly.py::_build_segment` trước đây KHÔNG ép sample
rate/kênh ở OUTPUT — chỉ khai `-c:a audio_codec` (tên codec), ffmpeg encode THEO NGUYÊN
input, nên segment mang narration OmniVoice trở thành 24kHz mono, khác hẳn 44.1kHz
stereo dùng xuyên suốt phần còn lại. Bug NGỦ YÊN từ lúc tích hợp OmniVoice (không phát
hiện sớm vì mọi test trước giờ dùng narration giả lập 44.1kHz stereo, khớp tình cờ với
chuẩn chung) — chỉ LỘ RA khi có ĐIỂM TRỘN/GHÉP giữa segment narration (24kHz mono) và 1
nguồn KHÁC đã chuẩn 44.1kHz stereo: cụ thể là tính năng **transition cho intro** (mục
55, MỚI thêm ngay hôm trước) — dùng `_xfade_chain` (acrossfade) thay vì `_concat_intro_
and_body` (concat filter) cũ. Trước mục 55, MỌI intro đều nối cắt cứng qua `concat`
filter — filter này CŨNG cần khớp định dạng nhưng có vẻ khoan dung hơn với sample
rate/kênh lệch nhẹ trong một số trường hợp; `acrossfade` thì không, làm bug hiện hình.

### Fix

Chuẩn hoá TRIỆT ĐỂ — ép sample rate/kênh 44.1kHz stereo ở **MỌI** điểm re-encode audio
trong `assembly.py` (không chỉ đúng chỗ narration), qua hằng số dùng chung
`_AUDIO_FORMAT_FLAGS = ["-ar", "44100", "-ac", "2"]`:
- `_build_segment` — output (mọi nhánh: narration/silence/không audio).
- `_build_intro_segment` (`kind=="video"`) — output.
- `_concat_intro_and_body` — THÊM filter `aformat=sample_rates=44100:channel_layouts=
  stereo` trên CẢ 2 audio input TRƯỚC `concat` (bản thân filter `concat` cũng đòi hỏi
  input khớp định dạng, không chỉ output cuối) + output.
- `_xfade_chain` (blend_cmd) — THÊM `aformat` trên cả 2 audio input TRƯỚC `acrossfade` +
  output. Đây là điểm ĐÚNG nơi bug thật xảy ra.
- `_mix_bg_music` — THÊM `aformat` trên CẢ audio chính lẫn nhạc nền TRƯỚC `amix` (nhạc
  nền là file NGƯỜI DÙNG TỰ UPLOAD, chưa từng qua `_build_segment`, có thể mang sample
  rate/kênh bất kỳ — cùng rủi ro, chủ động chuẩn hoá trước khi có bug thật thứ 2) +
  output.

Chuẩn hoá tại NGUỒN (`_build_segment`/`_build_intro_segment`) + tại MỌI điểm trộn
(`aformat` ngay trong filter graph, không chỉ output cuối) — không chỉ vá đúng 1 chỗ vừa
phát hiện, để an toàn trước MỌI provider TTS/nguồn audio tương lai có sample rate/kênh
khác lạ (không riêng OmniVoice).

### Verify

1 test unit mới `test_render.py` (`_build_segment` giả lập input 24kHz mono ĐÚNG định
dạng OmniVoice, xác nhận output LUÔN 44100Hz/2 kênh) + 1 test end-to-end THẬT mới
`test_intro.py` (tái hiện CHÍNH XÁC tổ hợp gây lỗi: intro video 44.1kHz stereo +
transition "fade" + narration 24kHz mono — `assemble_video()` thật, đo `mean_volume` tại
đúng điểm SAU intro, nơi bug thật xảy ra, xác nhận CÓ TIẾNG). Re-render TRỰC TIẾP đúng
project "Skip brief test" người dùng báo bằng code đã fix — `ffprobe`/`volumedetect` xác
nhận audio 44.1kHz stereo LIÊN TỤC suốt 16.5s (trước đây trống từ giây 9.6 trở đi).
`pytest` full suite: **248 passed**.

Backend đổi — restart Electron app để áp dụng cho các lần ghép MP4 tiếp theo (video CŨ
đã ghép lỗi từ trước fix vẫn cần ghép LẠI mới có audio đúng — file cũ không tự sửa).

## 58. Short-form sub-project (9:16, YouTube Shorts/TikTok) — nested dưới long-form (2026-08-21)

### Yêu cầu người dùng

1. Bổ sung luồng tạo project dạng short-form là sub-project của long-form project hiện
   tại. Hiển thị trên UI theo dạng danh sách phân tầng ở Sidebar và ở màn Dashboard kênh
   để biết short-form video nào thuộc project nào.
2. Các bước tạo video trong project short-form Y HỆT long-form nhưng khác tỷ lệ khung
   DỌC 9:16 để phù hợp đưa lên dạng short.

### Thiết kế (đã lập kế hoạch qua plan mode, review + duyệt trước khi code)

**Short-form KHÔNG PHẢI auto-repurpose** (đó là M3, `specs/09_sprint_tasks.md`, mốc SAU
— KHÔNG đụng tới ở đợt này) — là 1 project ĐỘC LẬP hoàn toàn về nội dung, tự đi qua lại
đúng luồng Brief→Script Studio→Visual Studio→Output như long-form, chỉ khác 2 điểm:
(1) sinh ảnh/video/ghép MP4 theo 9:16, (2) lồng hiển thị dưới project cha để nhóm.

**DB**: `Project` (`app/models/__init__.py`) thêm `parent_project_id` (self-referential
FK tới `project.id` — LẦN ĐẦU TIÊN dùng self-FK trong repo, không tiền lệ) + `format`
(`"long"`|`"short"`, mặc định `"long"`). Thêm cột nullable trực tiếp trên model class —
xác nhận lại: repo này KHÔNG dùng Alembic thật (dù `specs/02_database.md` ghi vậy),
chỉ `Base.metadata.create_all` — đúng quy ước additive-nullable-column đã dùng mọi lần
thêm cột trước đây, không cần migration script.

**API** (`app/routers/projects.py`): `POST /channels/{id}/projects` mở rộng field
optional `parent_project_id` — validate parent tồn tại (404), cùng kênh (400), parent
LÀ long-form (400 — chặn lồng short dưới short, không quá 1 cấp). `format` server tự
suy, KHÔNG nhận từ client. `GET /channels/{id}/projects` giữ NGUYÊN — vẫn trả danh sách
PHẲNG (có thêm 2 field mới), frontend tự group theo `parent_project_id` (đơn giản hơn
thêm endpoint cây riêng).

**Cascade** (quyết định qua AskUserQuestion lúc lập kế hoạch — chọn phương án cascade
đầy đủ): archive 1 long-form → archive LUÔN mọi short-form con (tránh mồ côi trong
Thùng rác); restore cha → restore luôn con đang archived; permanent-delete cha → xoá con
TRƯỚC (DB row + thư mục trên đĩa) rồi mới xoá cha. Archive/restore 1 short-form RIÊNG LẺ
KHÔNG kéo theo cha (chỉ 1 chiều long→short).

**Render pipeline (9:16)** — điều tra xác nhận TOÀN BỘ pipeline trước đây hardcode 16:9
(OpenAI Image `1792x1024`, SDXL `1344x768`, Flux `1408x800`, Sora `1280x720`, Veo
`aspectRatio:"16:9"`, Wan `1280x704`, `RESOLUTION_MAP` toàn ngang) — không có tham số
orientation nào:
- `app/providers/base.py` thêm `aspect_ratio: Literal["16:9","9:16"] = "16:9"` (`type
  AspectRatio`) cho `ImageProvider.generate()`/`VideoProvider.generate()`/
  `start_generation()` — ĐÚNG pattern optional kwarg đã có (`seed`/`reference_image`).
- Từng adapter đổi kích thước khi `aspect_ratio=="9:16"`, dùng ĐÚNG size CHUẨN đã biết
  của từng hãng (không đoán): OpenAI Image `1024x1792` (size dọc chính thức DALL-E 3),
  Sora `720x1280` (size dọc chính thức), Veo `aspectRatio="9:16"` (API hỗ trợ sẵn).
  SDXL/Wan (local, tự chọn được) hoán đổi W/H (768x1344, 704x1280). Flux Image hoán đổi
  W/H (800x1408, cùng megapixel nên giá không đổi). Gemini Image + Flux Video KHÔNG có
  tham số kích thước trong API (xác nhận qua research code) — best-effort: Gemini thêm
  gợi ý "bố cục dọc" vào prompt; Flux Video nhận tham số rồi bỏ qua (như provider chưa
  hỗ trợ) — CẢ 2 dựa vào crop-to-fill (dưới) để luôn ra đúng khung.
- `app/render/engine.py::generate_visual_asset` — đã có sẵn `Project` row, thêm
  `aspect_ratio = "9:16" if p.format=="short" else "16:9"`, truyền vào MỌI lời gọi
  provider (3 chỗ: video local_wan/video khác/image).
- `app/render/assembly.py`: `RESOLUTION_MAP_VERTICAL` mới (`720:1280`/`1080:1920`/
  `2160:3840`, cùng 3 mức chất lượng "720p"/"1080p"/"4k" như long-form, chỉ đổi CHIỀU) —
  `assemble_video()` chọn map theo `p.format`.
- **Crop-to-fill** (`_scale_cover_filter`, mới) — quyết định qua AskUserQuestion: đổi
  filter scale từ KÉO GIÃN (méo nếu input lệch tỷ lệ target) sang
  `scale=...:force_original_aspect_ratio=increase,crop=...` (phủ kín khung đúng tỷ lệ
  gốc rồi crop viền thừa CĂN GIỮA, không bao giờ méo) — áp dụng CHO CẢ long-form lẫn
  short-form (fix chung 1 lỗi tiềm ẩn có sẵn — ảnh lệch tỷ lệ nhẹ trước đây vẫn bị méo
  âm thầm). Quan trọng hơn hẳn với short-form vì Gemini/Flux Video không kiểm soát được
  khung, có thể trả về ảnh/video lệch hẳn 9:16 nếu chỉ dựa gợi ý prompt.
- Camera motion (`camera_motion.py`) — KHÔNG sửa code (đã tham số hoá theo `out_w`/
  `out_h` từ trước, biểu thức tương đối `iw`/`ih`/`zoom`) — chỉ cần verify bằng mắt.

**Frontend**: `ProjectSummary` thêm `parent_project_id`/`format`; `createProject` thêm
tham số `parentProjectId?`. `AppContext` thêm `expandedProjects`/`toggleProject`/
`expandProject` (mirror `expandedChannels`, cấp lồng thứ 2). `Sidebar.tsx` — mỗi
project long-form có Chevron phụ mở rộng danh sách short-form con (lọc client-side từ
CÙNG mảng phẳng `listProjects` trả về, không cần fetch riêng) + nút "+ Short mới"; tự
mở rộng cha khi project đang mở là short-form con (`useEffect` theo `activeProjectId`).
`Dashboard.tsx` — bảng project group long-form + short-form con indent ngay dưới, cột
"Loại" (badge "Long-form"/"Short 9:16"). `ProjectView.tsx` — breadcrumb thêm đoạn tên
project cha khi đang mở short-form + badge "Short 9:16". `VisualStudio.tsx` —
`ShotCard`/`IntroShotCard` đổi khung preview (cột `220px`→`140px`, box `124px`→`249px`)
khi `project.format=="short"` (qua `isVertical` prop mới) — `ThumbnailCard` GIỮ NGUYÊN
16:9 (thumbnail YouTube luôn ngang bất kể project). `RenderStudio.tsx` — nhãn độ phân
giải đổi theo format ("1080p (1080×1920 dọc)" cho short).

### Verify

Backend: 18 test mới `test_short_form_projects.py` — CRUD/validate tạo short-form
(parent thiếu/khác kênh/đã là short → đúng lỗi), cascade archive/restore/permanent-
delete THẬT (DB + thư mục trên đĩa), provider adapter nhận đúng tham số khung dọc
(respx-mock OpenAI Image/Sora/Veo/Gemini + pure-function SDXL/Wan workflow builder), VÀ
2 test end-to-end THẬT (ffmpeg thật, không mock) — short-form ra ĐÚNG `1080x1920`
(dùng ẢNH NGANG cố tình làm input để xác nhận crop-to-fill hoạt động thật, không phải
tình cờ đúng vì input đã đúng sẵn), long-form vẫn ra `1920x1080` như cũ (không regress).
`pytest` full suite: **266 passed**. `tsc --noEmit`: 0 lỗi trên toàn bộ 8 file frontend
đã đổi.

Chưa verify bằng mắt qua UI thật (Electron) trong phiên này — cần restart app + tự tạo
1 short-form thật qua Sidebar để xác nhận hiển thị lồng đúng và preview không bị bóp méo.

### Lưu ý vận hành: `Base.metadata.create_all` KHÔNG tự ALTER bảng đã tồn tại

Restart app lần đầu sau khi thêm 2 cột mới vào `Project` gặp lỗi thật:
`sqlite3.OperationalError: no such column: project.parent_project_id`. Nguyên nhân:
`Base.metadata.create_all()` (`app/main.py`) chỉ tạo bảng CHƯA TỒN TẠI — bảng `project`
đã có sẵn từ trước (dữ liệu thật của người dùng, `workspace/studioflow.db`) nên bị BỎ
QUA, không tự thêm cột mới. Đây là LẦN ĐẦU TIÊN đợt thêm cột rơi vào tình huống này
trong lịch sử dự án (mọi lần trước hoặc là bảng MỚI hoàn toàn, hoặc chỉ đổi ý nghĩa
code-level không cần cột DB mới) — quy ước "thêm cột nullable, không cần Alembic" chỉ
đúng cho DB MỚI TẠO (VD chạy `pytest`, mỗi test session tự tạo DB rỗng từ đầu).

Xử lý: backup `workspace/studioflow.db` (`cp` ra file `.bak-<timestamp>`), chạy
`ALTER TABLE project ADD COLUMN parent_project_id VARCHAR` +
`ALTER TABLE project ADD COLUMN format VARCHAR DEFAULT 'long'` trực tiếp bằng
`sqlite3`/`python -c "..."` (dừng app trước khi chạy, tránh ghi đè lúc đang có kết nối
mở), backfill `UPDATE project SET format='long' WHERE format IS NULL` cho toàn bộ 12
project sẵn có (SQLite áp `DEFAULT` cho cột mới ở CẢ hàng cũ khi `ALTER TABLE ADD
COLUMN` có `DEFAULT`, nhưng backfill lại 1 lần cho chắc). Xác nhận thật qua API sau khi
restart: `GET /channels/{id}/projects` trả đúng `parent_project_id: null, format:
"long"` cho project có sẵn, tạo mới 1 short-form con thật qua `POST` (kèm
`parent_project_id`) ra đúng `format: "short"`, xoá dọn lại project demo ngay sau đó
(không để lại rác trong workspace thật của người dùng).

**Ghi nhớ cho lần sau**: bất kỳ lúc nào thêm CỘT MỚI vào bảng đã có sẵn dữ liệu thật
(khác thêm bảng mới hoàn toàn), phải tự `ALTER TABLE` thủ công trên `workspace/
studioflow.db` sau khi đổi model — `create_all()` sẽ KHÔNG tự làm việc này.

## 59. Bug thật: render short-form lỗi hẳn — SAR (sample aspect ratio) lệch giữa intro và thân video (2026-08-22)

### Bug người dùng báo

Project short-form "Nghịch lý giữa công lao khai quốc và bản án tru di" — render lỗi
hẳn (`assembly_status="error"`), không ra video.

### Điều tra thật

`assembly_error` ghi lại nguyên văn lỗi ffmpeg:
```
[Parsed_concat_2] Input link in0:v0 parameters (size 1080x1920, SAR 0:1) do not match
the corresponding output link in0:v0 parameters (1080x1920, SAR 10240:10239)
[Parsed_concat_2] Failed to configure output pad on Parsed_concat_2
... Nothing was written into output file, because at least one of its streams received no packets.
```
Kênh của project này có **video thương hiệu cấp kênh** (`BrandProfile.intro_video_path`,
1920x1080/16:9) — project short-form không có intro riêng nên rơi vào nhánh fallback
brand-level (`_resolve_intro_source`). Shot ảnh sinh bằng SDXL local, bucket dọc
**768x1344** (tỷ lệ 4:7 ≈ 0.5714) — thêm mới ở mục 58 cho short-form, nhưng LỆCH tỷ lệ
9:16 thật (0.5625), không trùng khớp.

Tái hiện bằng ffmpeg thật (không suy đoán): scale 1 ảnh 768x1344 và 1 video 1920x1080
cùng về "cover" 1080x1920 qua `scale=1080:1920:force_original_aspect_ratio=increase,
crop=1080:1920` (filter thêm ở mục 58) — đo `sample_aspect_ratio` từng output: ảnh ra
`7680:7679`, video ra `10240:10239` — 2 giá trị GẦN 1:1 nhưng KHÁC NHAU. Nguyên nhân:
khi tỷ lệ input không khớp CHÍNH XÁC tỷ lệ target, `scale`+`force_original_aspect_ratio`
phải làm tròn 1 chiều về số nguyên — ffmpeg tự gán 1 SAR bù trừ phần lẻ do làm tròn thay
vì để nguyên SAR mặc định, và mức bù trừ khác nhau tuỳ mức lệch tỷ lệ của TỪNG input.
Filter `concat` (`_concat_intro_and_body`, ghép intro+thân video) đòi hỏi 2 input khớp
CẢ kích thước pixel LẪN SAR — 2 SAR gần-nhưng-khác nhau đủ làm `concat` từ chối hoàn
toàn, dù kích thước pixel giống hệt nhau (`1080x1920` cả 2).

**Bug này chỉ lộ ra ở tổ hợp short-form + có intro (dù intro tới từ đâu — brand-level
hay project-level đều như nhau)** — vì `_concat_intro_and_body` (filter `concat`, đòi
khớp SAR nghiêm ngặt) chỉ chạy khi CÓ intro; long-form KHÔNG bị ảnh hưởng theo cách này
vì hầu hết provider/asset đã native đúng 16:9 (aspect khớp target gần như luôn luôn,
không cần làm tròn → SAR mặc định sạch 1:1 tự nhiên).

### Fix

`_scale_cover_filter()` (mục 58) thêm `,setsar=1` vào CUỐI filter chain — ép CỐ ĐỊNH
sample aspect ratio về 1:1 (pixel vuông chuẩn), xoá bỏ SAR bù trừ tự động của `scale`.
Đồng thời thêm `setsar=1` vào nhánh Ken Burns/zoompan (`_build_segment`'s `motion_filter`
branch) — phòng ngừa lớp lỗi tương tự dù chưa tái hiện được cụ thể ở nhánh đó (roll dùng
`crop`+`scale` riêng, khác zoompan thường, có rủi ro tương tự).

### Verify

Tái hiện bug THẬT bằng ffmpeg trước khi fix (2 lệnh scale riêng biệt cho SAR khác nhau,
`concat` từ chối) — xác nhận `setsar=1` fix cả 2 về `1:1`, `concat` thành công. Re-render
TRỰC TIẾP đúng project người dùng báo bằng code đã fix — `assembly_status="done"`,
`final.mp4` thật (35.4s, 1080x1920, SAR 1:1). 1 test end-to-end THẬT mới
`test_short_form_projects.py` — tái hiện CHÍNH XÁC tổ hợp gây lỗi (video thương hiệu
16:9 cấp kênh + shot ảnh bucket SDXL 768x1344 lệch 9:16), xác nhận `assemble_video()`
thành công + output đúng khung + SAR sạch. `pytest` full suite: **267 passed**.

Backend đổi — restart Electron app để áp dụng cho các lần ghép MP4 tiếp theo (video
short-form CŨ đã lỗi từ trước fix chỉ cần bấm "Ghép MP4" lại, không cần làm gì thêm).

### Bug thêm (cùng ngày): preview video dọc tràn khỏi màn hình ở Render Studio

Sau khi fix xong lỗi ghép ở trên, người dùng báo tiếp: video DỌC render xong hiện ở
Render Studio bị "khung quá to so với trang, không xem được hết, phải scroll". Nguyên
nhân: `<video style={{width: "100%"}}>` trong thẻ "Video hoàn chỉnh" (`RenderStudio.tsx`)
nằm trong card rộng cố định `maxWidth: 640` — với video 16:9 (long-form), `width:100%`
cho chiều cao hợp lý (~360px). Với video 9:16 (short-form), CÙNG `width:100%` (=640px)
kéo chiều cao lên ~1138px (640 × 16/9) — tràn hẳn khỏi viewport.

Fix: khi `project.format === "short"`, đổi sang giới hạn theo **chiều cao**
(`maxHeight: "70vh"`, `width: "auto"`) thay vì chiều rộng — cùng cách `Lightbox.tsx` đã
xử lý đúng cho preview full-size ảnh/video từ trước (không đổi gì ở đó, đã sẵn đúng).
Video dọc giờ tự co bề rộng theo đúng tỷ lệ 9:16, luôn vừa khung nhìn theo chiều cao,
không cần cuộn. `tsc --noEmit`: 0 lỗi.

## 60. Bug thật: "Test connection" Flux luôn lỗi dù API key đúng — key thuộc dịch vụ bên thứ 3 khác hẳn BFL (2026-08-22)

### Bug người dùng báo

"Tôi đã điền api key chuẩn nhưng khi test connection vẫn lỗi" — provider Flux (Image),
task=image, `ProviderConfig` id=12.

### Điều tra thật

Kiểm tra key đang lưu trong DB: `has_whitespace=False` — LOẠI TRỪ giả thuyết đầu tiên
(khoảng trắng/ký tự thừa dính key lúc copy-paste). Đối chiếu `model_name` đang lưu
(`"flux-1.1-pro"`) với OpenAPI spec THẬT của BFL (`api.bfl.ai/openapi.json`) — phát hiện
1 bug PHỤ, KHÔNG LIÊN QUAN tới lỗi chính: model đúng phải là `flux-2-pro` (catalog
frontend/backend đã cập nhật đúng ở phiên trước, nhưng row DB CŨ của người dùng còn sót
giá trị model cũ trước khi catalog đổi). Sửa tạm qua `PATCH /providers/12` (không sửa
được `available_models` — Pydantic `ProviderPatch` không có field này — dropdown Settings
UI sẽ còn hiện option cũ tới khi người dùng xoá/thêm lại provider qua UI).

Vẫn KHÔNG giải thích được lỗi test connection chính. Hỏi lại người dùng: key lấy từ đâu
— xác nhận **key từ fluxapi.ai (dịch vụ bên thứ 3), KHÔNG PHẢI bfl.ai chính thức**. Đây
là 2 dịch vụ HOÀN TOÀN ĐỘC LẬP (auth khác — `x-key` vs `Authorization: Bearer`, base URL
khác — `api.bfl.ai` vs `api.fluxapi.ai`, request/response shape khác) — key fluxapi.ai
không bao giờ xác thực được với code hiện tại (chỉ gọi `api.bfl.ai`), giải thích đúng
triệu chứng "key chuẩn (đúng theo fluxapi.ai) nhưng test vẫn lỗi (vì code gọi nhầm hãng)".

Người dùng chốt (AskUserQuestion): (1) GIỮ NGUYÊN provider Flux/Flux Video hiện có (dùng
BFL thật) — không đụng; (2) THÊM provider MỚI song song cho fluxapi.ai (chỉ ảnh, fluxapi.ai
không có video), không thay thế.

### Bug PHỤ tìm thấy khi sửa lỗi chính (đáng giữ dù không phải root cause)

`app/crypto.py::encrypt_secret()` không tự `.strip()` input — 1 trong 3 đường lưu API key
ở `ProviderSettings.tsx` (`AddProviderDialog.save()`) thiếu `.trim()` (2 đường còn lại,
`saveKey()`/`saveAndRetry()`, đã có sẵn) — key dính khoảng trắng/xuống dòng thừa vẫn lưu
được, tới lúc gọi API mới lộ ra bằng lỗi httpx `LocalProtocolError` cực khó hiểu ("Illegal
header value"). Fix ở NGUỒN (`encrypt_secret()` tự strip — điểm DUY NHẤT gọi hàm này) +
fix đường lưu thiếu `.trim()` ở frontend + thêm bắt riêng `LocalProtocolError` trong
`flux_common.py::check_auth()` dịch sang thông điệp tiếng Việt rõ ràng (lưới an toàn cho
key lỡ lưu trước khi có fix). Cũng thêm phân biệt HTTP 402/429 (key ĐÚNG nhưng tài khoản
BFL hết credit/rate-limit) khỏi 401/403 (key sai) trong `check_auth()` — tránh người dùng
tưởng nhầm phải nhập lại key.

### Research API thật fluxapi.ai (verify từng bước bằng curl trực tiếp, KHÔNG tin nguyên
văn tài liệu WebFetch — tài liệu ghi sai 1 endpoint, xem bên dưới)

- Endpoint credit-check MIỄN PHÍ mà tài liệu (WebFetch-summarized) ghi là
  `/api/v1/chat/credit` — curl thật trả `404 Not Found`. Dò lại bằng cách thử nhiều biến
  thể đường dẫn — endpoint ĐÚNG là **`/api/v1/common/credit`**.
- **Phát hiện quan trọng nhất**: fluxapi.ai LUÔN trả **HTTP 200** ở MỌI trường hợp — kể
  cả key sai (`{"code":401,"msg":"Unauthorized..."}`, HTTP 200) và body thiếu field bắt
  buộc (cùng lỗi 401 HTTP 200, vì auth check chạy TRƯỚC validate body). Trạng thái THẬT
  nằm ở field `"code"` trong JSON body, không phải `resp.status_code` — khác hẳn quy ước
  BFL/OpenAI/Gemini đã dùng trong toàn bộ codebase trước đó. Xác nhận qua 3 endpoint khác
  nhau (credit-check, generate, poll) × 2 tình huống lỗi khác nhau (key sai, body sai) —
  không phải quirk cục bộ 1 endpoint.

### Fix

Thêm mới `app/providers/image_flux_kontext.py::FluxKontextImageProvider`
(`provider_name="flux_kontext"`, SONG SONG `image_flux.py`, không đụng file cũ):
- `generate()`: POST `/api/v1/flux/kontext/generate` (`Authorization: Bearer`,
  body `aspectRatio` string trực tiếp — khớp thẳng `AspectRatio` type có sẵn của app,
  không cần đổi như BFL width/height) → poll `GET /record-info?taskId=...` tới
  `successFlag==1` (tải `resultImageUrl`) hoặc `2`/`3` (lỗi).
- `test_connection()`: dùng `/api/v1/common/credit` (miễn phí, không tốn credit sinh
  ảnh — khác BFL không có endpoint free nào).
- CẢ 2 đọc `data["code"]` từ body, KHÔNG dựa `resp.status_code` (đúng phát hiện research).
- `reference_image` KHÔNG hỗ trợ (Kontext `inputImage` cần URL công khai, app desktop
  không có nơi host — bỏ qua tham số, an toàn vì Tier 2 vốn đã tắt mặc định toàn app).
- `estimate_cost()` trả `0.0` — fluxapi.ai chưa có bảng giá công khai lúc tích hợp,
  KHÔNG bịa số (cùng convention `video_flux.py`).

Đăng ký `factory.py::_IMAGE_ADAPTERS["flux_kontext"]` +
`render/engine.py::_IMAGE_COST_FN["flux_kontext"]` (thiếu dòng này sẽ âm thầm dùng nhầm
hàm cost của OpenAI — sai số tiền hiển thị) + `routers/providers.py::CLOUD_MODELS["flux_kontext"]`
(`["flux-kontext-pro", "flux-kontext-max"]`) + frontend
`ProviderSettings.tsx::CLOUD_CATALOG.image` thêm entry "Flux Kontext (fluxapi.ai)".

### Verify

6 test mới `tests/test_flux_kontext.py` (respx mock) — đặc biệt test riêng hành vi "HTTP
200 nhưng code=401 trong body vẫn phải raise lỗi" để bắt regression nếu sau này lỡ đổi
lại sang chỉ check `resp.status_code`. Full `pytest`: **273 passed** (267 + 6 mới).
`tsc --noEmit`: 0 lỗi.

Người dùng cần tự thêm provider "Flux Kontext (fluxapi.ai)" qua Settings với key
fluxapi.ai của mình rồi bấm Test — không thể verify live với key thật thay người dùng.

## 61. Shot mở đầu (intro) ở Visual Studio hiển thị rõ kế thừa từ BrandProfile — thay vì fallback ngầm (2026-08-22)

### Yêu cầu người dùng

"Chỉnh lại Shot mở đầu (intro) của mục Visual Studio để inherit từ brand profile. User có
thể remove và thay thế sau. Việc chỉnh sửa này ở mỗi video project này không làm ảnh
hưởng đến config của brand profile."

### Hiện trạng trước khi sửa

`app/render/intro.py::resolve_intro_source` (mục 51/59) đã LUÔN fallback về video/audio
thương hiệu cấp kênh khi project chưa có shot mở đầu riêng — nhưng đây là fallback NGẦM,
chỉ áp dụng lúc ghép MP4 thật. `IntroShotCard` (Visual Studio) không biết gì về brand,
project chưa cấu hình gì thì card hiện trống ("Chưa có") — người dùng không thấy được
asset nào SẼ ĐƯỢC DÙNG, và không có cách nào "bỏ" nó (vì chẳng có gì để bỏ ở UI, dù thực
tế video vẫn sẽ có intro khi ghép).

### Thiết kế: tri-state thay vì nhị phân "có/không có asset riêng"

Thêm `IntroAssetStatus.disabled: bool = False` (`app/render/schemas.py`) — 3 trạng thái:
1. **Kế thừa (mặc định)**: `disabled=False`, không có asset riêng — Visual Studio hiển
   thị THẬT video/audio thương hiệu cấp kênh làm preview (gắn nhãn "Kế thừa từ hồ sơ
   thương hiệu"), đọc qua `GET /channels/{id}/brandprofile` + `GET .../brandprofile/intro`
   (2 endpoint CÓ SẴN từ mục 51, chỉ đọc để hiển thị, không sửa).
2. **Đã tắt**: `disabled=True` — không dùng intro nào cả, kể cả brand có cấu hình.
   `resolve_intro_source` thêm bước ưu tiên (0): `if intro.disabled: return None` — ĐỨNG
   TRƯỚC cả kiểm tra project override lẫn brand fallback.
3. **Ghi đè riêng**: có `visual_asset_path`/`audio_asset_path` (hành vi CŨ, không đổi).

`DELETE /projects/{id}/render/intro` đổi hành vi: TRƯỚC set `intro=None` (im lặng quay
về kế thừa — không có tác dụng thấy được nếu project chưa từng override), GIỜ set
`disabled=True` (tắt hẳn, đúng nghĩa "Bỏ shot mở đầu" người dùng bấm). Thêm endpoint mới
`PATCH /projects/{id}/render/intro/inherit` (không cần body) — set `disabled=False`, lối
quay lại kế thừa brand mà không cần tải-rồi-upload lại thủ công. 2 endpoint upload
(`upload_intro_visual`/`upload_intro_audio`) tự set `disabled=False` khi lưu asset mới —
tránh trạng thái vô lý "vừa có asset riêng vừa đang tắt".

**Không ảnh hưởng BrandProfile** — đúng yêu cầu người dùng: cả 2 endpoint mới/đổi chỉ ghi
vào `render.json` CỦA TỪNG PROJECT (qua `engine.save_render_state`), never PUT lại
`brandprofile.json`. Đọc BrandProfile ở frontend (`api.getBrandProfile`) chỉ để hiển thị
preview, không có đường ghi nào ngược lại.

### Frontend

`IntroShotCard` (`VisualStudio.tsx`) nhận thêm prop `channelId`, tự fetch BrandProfile
lúc mount để biết `intro_video_path`/`intro_audio_path` có cấu hình không. Tính lại 3
nhãn trạng thái (tag) tương ứng 3 state ở trên. Khi đang kế thừa: preview box hiện THẬT
video/audio thương hiệu (qua `api.brandIntroUrl(channelId)`), nút "Bỏ shot mở đầu" khả
dụng (trước đây chỉ hiện khi đã có asset riêng). Khi đã tắt: hiện nút "Dùng lại mặc định
thương hiệu" (chỉ khi brand THẬT SỰ có cấu hình gì đó, tránh nút vô nghĩa). Upload
video/ảnh/audio luôn khả dụng ở mọi trạng thái (tự bật lại `disabled=False` phía backend).

### Verify

Backend: 6 test mới trong `test_intro.py` (đổi 1 test cũ theo hành vi DELETE mới + 5 test
mới cho disabled/inherit/resolve_intro_source priority). Full `pytest`: **279 passed**
(273 + 6). `tsc --noEmit`: 0 lỗi. Restart Electron app, smoke-test THẬT qua API trên
project có sẵn (`prj_1786626903294`, kênh có brand intro video thật): DELETE → xác nhận
`disabled=True`; PATCH inherit → xác nhận `disabled=False`; xác nhận endpoint asset
thương hiệu (`GET .../brandprofile/intro`) trả HTTP 200 — dùng được cho preview thật.

## 62. Logo kênh (BrandProfile) + bỏ mục BrandProfile ở sidebar phải luồng tạo video (2026-08-22)

### Yêu cầu người dùng

"- Bổ sung thêm mục cho phép upload logo của kênh vào brandprofile
- Bỏ phần Brandprofile ở sidebar bên phải luồng tạo video project vì ko cần thiết"

### Phần 1 — Logo kênh

Thêm `BrandProfile.logo_path: str = ""` (`app/schemas/__init__.py`) — THUẦN hiển thị nhận
diện thương hiệu, KHÔNG đọc ở bất kỳ module render/pipeline nào (khác `intro_video_path`/
`voice_clone_ref_path` — có dùng thật khi sinh asset/ghép video). Quyết định này để tránh
scope creep: người dùng chỉ yêu cầu "cho phép upload logo", không yêu cầu watermark hay
bất kỳ hành vi pipeline nào.

2 endpoint mới ở `app/routers/channels.py`, đúng pattern đã có cho voice-sample/intro/
bg-music (upload multipart → lưu đè tại `channel_dir/logo.{ext}`, xoá file cũ khác đuôi
nếu có, bump `brandprofile_version`, ghi `BrandProfileVersion` + `AuditLog`):
- `POST /channels/{id}/brandprofile/logo/upload` — nhận PNG/JPEG/WEBP.
- `GET /channels/{id}/brandprofile/logo` — dùng `FileResponse` (ảnh tĩnh, không cần hỗ
  trợ Range như video/audio — cùng cách `pack.py::get_thumbnail_asset` phục vụ thumbnail).

Frontend: `ChannelDialog.tsx` ("Sửa BrandProfile") thêm mục "Logo kênh" — cùng pattern
upload/xem/xoá đã có cho 3 mục kia (`api.uploadBrandLogo`/`api.brandLogoUrl` mới ở
`client.ts`), preview 56×56px, xoá qua PUT lại `logo_path=""` (không cần route xoá riêng,
cùng convention voice-sample/intro/bg-music).

### Phần 2 — Bỏ mục BrandProfile ở sidebar phải

`RightPanel.tsx` (sidebar phải, CHỈ dùng ở `ProjectView.tsx` — đúng "luồng tạo video
project" người dùng nhắc tới) trước đây fetch + hiển thị tóm tắt BrandProfile (tông
giọng, content pillars, cấm kỵ, retention benchmark) bên dưới tiêu đề "BrandProfile".
Người dùng thấy không cần thiết (đã có màn "Sửa BrandProfile" riêng đầy đủ hơn nhiều).

Bỏ ĐÚNG phần được yêu cầu — xoá fetch `api.getBrandProfile` + toàn bộ khối JSX hiển thị
profile + tiêu đề "BrandProfile". GIỮ LẠI phần "Phiên bản Pack" (không thuộc BrandProfile,
không được yêu cầu bỏ) + khung panel thu/phóng (nút mũi tên vẫn hoạt động). Prop
`channelId` không còn cần thiết cho component này — bỏ luôn khỏi signature + call site
(`ProjectView.tsx`), tránh prop chết không dùng.

### Verify

Backend: 6 test mới `test_channels.py` (upload set path, reject sai loại file, 404 khi
chưa có, serve đúng bytes, thay file cũ xoá rác, xoá qua PUT). Full `pytest`: **285
passed** (279 + 6). `tsc --noEmit`: 0 lỗi. Restart Electron app, smoke-test THẬT qua API
trên kênh có sẵn (`ch_1786626899972`): upload logo thật → xác nhận `logo_path` set đúng,
tải lại xác nhận bytes khớp hệt file gốc → dọn lại về `logo_path=""` (không để lại
rác trong dữ liệu thật của người dùng).

## 63. Cải thiện chất lượng ảnh model local (SDXL/ComfyUI) — đợt 1: prompt + checkpoint đổi được (2026-08-22)

### Yêu cầu người dùng

"model AI local để tạo image và video là model gì, tại sao ảnh tạo ra từ model local
khác hoàn toàn và xấu hơn nhiều so với ảnh của model api của gemini" — sau đó người dùng
gửi kèm 1 tài liệu đề xuất (`StudioFlow_ImageVideo_Improvement.md`, chẩn đoán: sampler/
resolution đều chuẩn, nguyên nhân chính là checkpoint SDXL base gốc chưa fine-tune,
nguyên nhân phụ là prompt dùng chung cho mọi provider) và yêu cầu lên plan triển khai.

### Phát hiện MỚI khi lập plan — không có trong tài liệu đính kèm

Đọc thật `pack.json` nhiều project của người dùng: `visual_fx` LUÔN có cấu trúc
`[Visual]: <mô tả cảnh>. [Tag]: <chữ cần vẽ lên ảnh>` — `[Tag]` là 1 trong
`Title Card`/`Text Overlay`/`Graphic`/`Quote Text`/`Insight Box`/`Animation`/
`Graphic Overlays`, luôn kèm NGUYÊN VĂN câu chữ/số tiếng Việt có dấu. `app/render/
assembly.py` xác nhận KHÔNG có bước `drawtext`/overlay chữ nào — các tag này đang trông
cậy HOÀN TOÀN vào chính model sinh ảnh để "vẽ" chữ thành pixel. SDXL (mọi checkpoint, kể
cả fine-tune tốt) render chữ RẤT kém so với Gemini — đây là lý do hợp lý nhất giải thích
đúng triệu chứng "khác hẳn, xấu hơn nhiều" (không chỉ "hơi kém hơn"). Phát hiện thêm:
`_NEGATIVE_PROMPT` (`image_comfy_sdxl.py`) đã có sẵn từ khoá "text" — positive prompt
(qua các tag trên) và negative prompt đang mâu thuẫn nhau ngay trong cùng 1 request.

### Quyết định cùng người dùng (AskUserQuestion trong lúc lập plan)

- Checkpoint fine-tune cụ thể (Juggernaut XL/RealVisXL/DreamShaper XL): **người dùng sẽ
  chốt sau** — không chặn phần code, vì thiết kế bên dưới làm checkpoint thành giá trị
  đổi được qua cấu hình, không cần sửa code khi chốt xong. Xác nhận qua ComfyUI THẬT đang
  chạy (`127.0.0.1:8188`): checkpoints folder tại `C:\Tools\ComfyUI_extract\
  ComfyUI_windows_portable\ComfyUI\models\checkpoints\`, hiện chỉ có `sd_xl_base_1.0.
  safetensors`; GPU RTX 5060 Ti 16GB (~11GB free); 299GB free disk — đủ chỗ. Cả 3
  checkpoint đề xuất xác nhận tải MIỄN PHÍ qua HuggingFace (không cần đăng nhập) —
  DreamShaper XL bản 1-file dễ tải nhất là **Turbo** (tối ưu 4-8 bước, cfg thấp — dùng
  chung sampler hiện tại 30 bước/cfg 7.0 sẽ RA ẢNH TỆ, cần đổi thêm nếu chọn nhánh này).
- Refiner pass (base+refiner 2 giai đoạn): **bỏ qua đợt này** — cộng đồng SDXL: refiner
  chính thức tune riêng cho base gốc, dùng chung checkpoint fine-tune thường KHÔNG cải
  thiện (đôi khi làm yếu phong cách riêng), lại tốn thêm ~6-7GB tải về + tăng VRAM/thời
  gian (máy đã có tranh chấp VRAM ComfyUI+OmniVoice+Ollama, xem mục 22). Đánh giá lại sau
  khi đổi checkpoint.
- Cách tải checkpoint khi chốt xong: người dùng chọn để Claude tự tải qua HuggingFace vào
  đúng thư mục ComfyUI (chạy nền, báo khi xong) — CHƯA THỰC HIỆN, chờ người dùng chốt
  checkpoint cụ thể.

### Việc đã làm (không phụ thuộc chọn checkpoint nào)

**1. Lọc tag chèn chữ khỏi prompt local SDXL** (`app/render/engine.py`):
`_strip_text_overlay_tags()` — regex 2 lượt: xoá HẲN mọi tag khác `[Visual]:` (tag+nội
dung, vì luôn là chữ/số cần vẽ), rồi bỏ riêng NHÃN `[Visual]:` (giữ nguyên nội dung cảnh
— tag này LUÔN mang mô tả cảnh thật, xác nhận qua grep toàn bộ shot nhiều project, kể cả
trường hợp lặp `[Visual]:` 2 lần trong 1 shot).

`_build_visual_prompt()` thêm tham số `for_local_sdxl: bool = False` — `True` (chỉ dùng
cho `local_sdxl`): áp filter trên, nối bằng ", " (văn phong tag thay vì câu văn đầy đủ),
thêm `"no text, no title card, no captions"` bổ trợ negative prompt có sẵn, cắt bớt PHẦN
STYLE (phụ) nếu tổng dài vượt `_LOCAL_SDXL_PROMPT_CHAR_BUDGET=320` ký tự (proxy cho giới
hạn ~77 token CLIP — tiếng Việt có dấu tokenize không đều, dùng ký tự làm ngưỡng an toàn,
không đếm token chính xác) — ưu tiên giữ nguyên vẹn mô tả cảnh, cắt style trước.
`False` (Gemini/OpenAI/Flux) — hành vi giữ NGUYÊN như cũ.

`generate_visual_asset()`: chuyển việc gọi `_build_visual_prompt()` vào TRONG vòng lặp
fallback chain (trước tính 1 lần dùng chung cho mọi provider thử) — chọn
`for_local_sdxl=(provider.provider_name == "local_sdxl")` cho từng lần thử, vì 1 chain có
thể vừa có local_sdxl (default) vừa có cloud (fallback), mỗi provider cần đúng biến thể.

**2. Checkpoint đổi được qua cấu hình, không hardcode** — trước đây `ComfySDXLImage
Provider.__init__` NHẬN `model_name` nhưng KHÔNG dùng ở đâu (field "chết", mặc định fake
`"sdxl"` không phải tên file thật); `factory.py` cũng KHÔNG truyền `model_name` cho
`local_sdxl`/`local_wan` (chỉ truyền `base_url`). Ô "Model" ở Cài đặt → Provider AI cho
provider local ĐÃ CÓ SẴN trên UI nhưng vô tác dụng.

- `factory.py::_build_asset_provider` — nhánh local (`local_sdxl`/`local_wan`) giờ
  truyền THÊM `model_name=cfg.model_name or ""`.
- `image_comfy_sdxl.py` — `_build_txt2img_workflow`/`_build_img2img_workflow` nhận
  `ckpt_name` làm tham số (thay vì đọc thẳng hằng số module); `_generate_locked` tính
  `ckpt_name = self.model_name or _CHECKPOINT_NAME` (rỗng → checkpoint mặc định
  `sd_xl_base_1.0.safetensors`, không đổi hành vi ai chưa cấu hình).
- `ProviderSettings.tsx` — `LOCAL_CATALOG.image[0].model_name` đổi từ `"sdxl"` (placeholder
  giả) sang `""`, sửa hint giải thích rõ cơ chế.

**Bug thật phát hiện lúc verify live**: DB thật của người dùng (`ProviderConfig` id=3,
task=image, provider_name=local_sdxl) đang lưu `model_name="sdxl"` — giá trị fake CŨ từ
trước khi field này có tác dụng. Với code MỚI, giá trị này sẽ bị gửi làm `ckpt_name`
THẬT tới ComfyUI (không phải tên file hợp lệ) → sinh ảnh sẽ lỗi ngay. Sửa qua PATCH
`model_name=""` trực tiếp trên API đang chạy — khôi phục đúng hành vi mặc định (dùng
checkpoint base gốc), không mất cấu hình nào khác.

### Verify

17 test mới (`test_render.py` — pure-function cho `_strip_text_overlay_tags`/
`_build_visual_prompt(for_local_sdxl=...)`, xác nhận `[Visual]:` được giữ nội dung, tag
khác bị xoá HẲN cả tag+nội dung, cloud KHÔNG đổi hành vi; `test_image_comfy_sdxl.py` mới
— respx mock ComfyUI, xác nhận `ckpt_name` đúng theo `model_name` cho CẢ txt2img lẫn
img2img, và fallback đúng checkpoint mặc định khi rỗng — file này CHƯA có test nào trước
đợt này). Full `pytest`: **296 passed** (285 + 11). `tsc --noEmit`: 0 lỗi.

Verify THẬT qua ComfyUI đang chạy (không chỉ mock): lấy đúng 1 `visual_fx` thật từ
`pack.json` người dùng (chứa `[Visual]`/`[Graphic]`) — so prompt trước/sau
(`for_local_sdxl=False/True`): độ dài giảm từ 977 → 356 ký tự, tag `[Graphic]`/nội dung
chữ biến mất hoàn toàn, mô tả cảnh giữ nguyên vẹn, prompt cloud (Gemini) không đổi. Submit
1 job sinh ảnh THẬT qua checkpoint base hiện có với prompt đã lọc — ra ảnh thật, KHÔNG
còn dấu hiệu chữ/glyph vô nghĩa (xác nhận filter hoạt động) — nhưng nội dung ảnh vẫn SAI
HẲN so với mô tả (cảnh sông đêm/thuyền chiến ra... bộ sưu tập tranh hoa lá/đồ vật hoàn
toàn không liên quan) — bằng chứng thực tế củng cố đúng kết luận: checkpoint base gốc là
nguyên nhân LỚN NHẤT, đúng thứ tự ưu tiên đã chốt trong plan.

Test wiring checkpoint đổi được: PATCH `model_name` provider thật sang 1 tên file KHÔNG
tồn tại → submit job thật → ComfyUI từ chối đúng với tên file đó trong lỗi (xác nhận value
chảy đúng suốt factory→provider→workflow) → PATCH lại `model_name=""` khôi phục.

Restart Electron app áp dụng cho lần sinh ảnh tiếp theo. **Việc CHƯA làm**: tải/đổi
checkpoint cụ thể (chờ người dùng chốt), refiner (bỏ qua đợt này), FLUX.2-klein, mọi phần
video/Wan, sửa prompt template LLM sinh `visual_fx` để không sinh tag chữ ngay từ đầu (fix
triệt để hơn, ảnh hưởng cả cloud — để ngỏ nếu đợt lọc tag chưa đủ).

## 64. Checkpoint & Style LoRA đúng art direction kênh "Người kể sử" — đợt 2 cải thiện ảnh local (2026-08-22)

### Yêu cầu người dùng

Tiếp nối mục 63 — người dùng gửi thêm `StudioFlow_Style_Checkpoint_Proposal.md`: bảng
checkpoint đợt 1 (Juggernaut XL/RealVisXL) SAI HƯỚNG cho kênh này (photoreal, ngược với
"tranh vẽ tay/sơn dầu, tránh 3D nhựa hoá" trong `BrandProfile.visual_style_prompt`). Yêu
cầu "cập nhật lại plan... chủ động triển khai... nếu có vấn đề gì thì chủ động đưa ra
phương án phù hợp nhất". Tài liệu đề xuất 3 lớp khoá phong cách (checkpoint painterly →
Style LoRA → IP-Adapter tuỳ chọn), CHỦ ĐỘNG không chốt cứng tên checkpoint/LoRA cụ thể
("tiêu chí lọc quan trọng hơn tên cụ thể") — uỷ quyền nghiên cứu + chọn cụ thể lúc build.

### Nghiên cứu thật (WebSearch + WebFetch + curl xác nhận tải được — không đoán)

**Checkpoint**: "Painter's Checkpoint" v1.1 (CivitAI model 240154,
`paintersCheckpointOilPaint_v11.safetensors`, 6.94GB, SDXL 1.0 fine-tune "alla prima,
gestural, atmospheric... far from clean sharp photorealism"). Trang CivitAI hiện nút
"Sign In" nhưng endpoint download API (`/api/download/models/{id}?fileId=...`) xác nhận
THẬT qua `curl -L` — trả HTTP 200 + header safetensors thật, không cần key. KHÔNG phải
bản Turbo — dùng ngay với sampler hiện có (30 steps/cfg 7.0), không cần đổi.

**2 Style LoRA**: LoRA gốc trên CivitAI đúng tiêu chí (ClassipeintXL — "LoRA painterly
nhất quán nhất cho SDXL" theo các nguồn search) hoá ra BỊ KHOÁ tải (HTTP 401, cần
API key/tài khoản CivitAI không có sẵn) — tìm được bản MIRROR MIỄN PHÍ trên HuggingFace
(`EldritchAdam/SDXL_Eldritch_LoRAs`, xác nhận HTTP 302→CDN thật qua curl):
- `ClassipeintXL2.1.safetensors` (133MB) — oil painting.
- `InkArtXL_1.2.safetensors` (107MB) — ink wash — tài liệu đề xuất gọi đây là lựa chọn
  "đặc biệt đáng thử" vì khớp CHÍNH XÁC "mực tàu, giấy dó" đã có sẵn trong
  `visual_style_prompt` của kênh này — **đặt làm LoRA active mặc định cho kênh demo**.

Cả 3 file tải THẬT vào đúng thư mục ComfyUI (`models/checkpoints/`, `models/loras/`) —
xác nhận qua `GET /models/checkpoints`/`GET /models/loras` của ComfyUI đang chạy, KHÔNG
cần restart ComfyUI để nhận diện file mới.

### Quyết định chủ động (theo đúng yêu cầu "chủ động đưa ra phương án phù hợp nhất")

- **Checkpoint đặt làm mặc định app-wide ngay** (`_CHECKPOINT_NAME` đổi từ
  `sd_xl_base_1.0` → `paintersCheckpointOilPaint_v11.safetensors`) — coi tài liệu đợt 2 là
  quyết định CUỐI CÙNG, thay thế hẳn "chờ người dùng chốt" ở đợt 1 (đã đủ tiêu chí + uỷ
  quyền rõ, không cần hỏi lại).
- **KHÔNG làm đợt này**: train Style LoRA riêng (cần hạ tầng train chưa có + 20-40 ảnh mẫu,
  tài liệu tự xếp "khi đã ổn định concept"); IP-Adapter (MÂU THUẪN trực tiếp quyết định
  kiến trúc đã có sẵn — `image_comfy_sdxl.py` docstring ghi rõ đã BỎ IPAdapter Plus vì
  "custom node cộng đồng dễ lệch tên/version" — không tự đảo ngược quyết định cũ mà
  không hỏi lại).
- **"no text/title card/caption" CHUYỂN từ prompt dương (đợt 1) sang negative prompt
  thật** (`image_comfy_sdxl.py::_NEGATIVE_PROMPT`) — phát hiện lúc code: câu phủ định
  nhét trong prompt dương kém hiệu quả hơn hẳn negative conditioning thật, và đây đúng
  chỗ nó nên ở ngay từ đầu. Thêm mới `3d render, plastic, cgi, glossy, photorealistic,
  smooth plastic surface` vào cùng negative prompt — chặn hướng "3D nhựa hoá giả tạo" bị
  cấm trong art direction.
- **Khối style cố định** (`oil painting, hand-painted, ink wash, muted warm tones, aged
  paper texture, cinematic concept art`) chèn ĐẦU prompt local — HẰNG SỐ dùng chung mọi
  kênh (đơn giản trước, CLAUDE.md "không over-engineer"), CHƯA đưa vào BrandProfile theo
  từng kênh — để ngỏ nếu có kênh khác cần style khác hẳn.

### Việc đã làm

- `BrandProfile.style_lora_path`/`style_lora_strength` (`app/schemas/__init__.py`) — tên
  file LoRA thật trong `ComfyUI/models/loras/` (KHÔNG phải đường dẫn tuyệt đối như
  `logo_path`/`intro_video_path` — LoRA sống trong thư mục ComfyUI, không phải
  channel_dir). Rỗng = không dùng LoRA, không đổi hành vi cho ai chưa cấu hình.
- Node `LoraLoader` (CÓ SẴN trong ComfyUI core, KHÔNG phải custom node — khác IPAdapter)
  chèn giữa `CheckpointLoaderSimple` và `KSampler`/`CLIPTextEncode` trong CẢ 2 workflow
  builder (`_build_txt2img_workflow`/`_build_img2img_workflow`, `image_comfy_sdxl.py`) —
  rỗng `lora_name` → bỏ qua hoàn toàn, nối thẳng như cũ.
- `ComfySDXLImageProvider.generate()` nhận thêm `lora_name`/`lora_strength` — **KHÔNG**
  khai báo trên `ImageProvider` interface chung (base.py) như `seed`/`reference_image`/
  `aspect_ratio` — khái niệm CHỈ có ý nghĩa với `local_sdxl`, ép mọi provider khác nhận 2
  tham số chết là thừa. `engine.py::generate_visual_asset` đọc
  `brand.get("style_lora_path"/"style_lora_strength")`, CHỈ truyền khi
  `provider.provider_name == "local_sdxl"`.
- `ChannelDialog.tsx` — thêm mục "Style LoRA cho ảnh local SDXL" (text tên file + số
  strength) — theo đúng convention app: mọi field BrandProfile đều có UI, không để field
  mới "vô hình" (người dùng cần thấy/chỉnh được lúc tự test app).

### Verify

6 test mới (2 respx test LoraLoader có/không trong workflow cho cả txt2img/img2img,
1 test nội dung `_NEGATIVE_PROMPT`, 1 test khối style prefix, 1 test tích hợp
end-to-end xác nhận `BrandProfile.style_lora_path` tới đúng request ComfyUI qua
`render/start` thật — bắt được 1 bug thật lúc viết: test integration đầu tiên bị TREO
>120s vì thiếu `@respx.mock` decorator, khiến request gọi RA MẠNG THẬT tới ElevenLabs —
sửa xong chạy 3s). Full `pytest`: **302 passed** (296 + 6). `tsc --noEmit`: 0 lỗi.

Verify THẬT qua ComfyUI (không chỉ mock): set BrandProfile kênh demo dùng InkArtXL, sinh
lại ĐÚNG 1 `visual_fx` đã dùng verify mục 63 (cảnh sông đêm/ánh đuốc/mai phục) bằng
checkpoint + LoRA mới — kết quả THAY ĐỔI RÕ RỆT so với ảnh mục 63 (bộ sưu tập hoa lá ngẫu
nhiên, sai hẳn nội dung): ra ĐÚNG 1 cảnh làng quê lịch sử mạch lạc, chất sơn dầu/nét vẽ
tay rõ, tông màu ấm trầm khớp brand, KHÔNG còn dấu hiệu 3D nhựa hoá, không chữ/glyph vô
nghĩa — bằng chứng thực tế xác nhận hướng painterly checkpoint + LoRA cải thiện đúng như
kỳ vọng (dù chưa khớp 100% bối cảnh "sông đêm" cụ thể — cải thiện thêm có thể tới từ
train LoRA riêng cho kênh sau này, xem phần "không làm đợt này").

Restart Electron app áp dụng. **Việc CHƯA làm**: train Style LoRA riêng cho kênh,
IP-Adapter, đưa khối style cố định vào BrandProfile theo từng kênh, mọi phần video/Wan.

## 65. Chọn checkpoint/Style LoRA bằng dropdown thay vì gõ tay (2026-08-22)

### Yêu cầu người dùng

"Nên cho chọn model trong phần cài đặt cho provider ComfyUI SDXL (local GPU) thay vì phải
gõ. Nên cho chọn 'Style LoRA cho ảnh local SDXL (tuỳ chọn)' ở màn Sửa brand profle thay vì
gõ." — cả 2 field mới thêm ở mục 63/64 (checkpoint qua `model_name` provider, Style LoRA
qua BrandProfile) đều đang là ô nhập tay tự do, dễ gõ sai tên file.

### Việc đã làm

**Backend** — `app/providers/image_comfy_sdxl.py::list_comfyui_models(kind, base_url)`:
gọi thẳng `GET {base_url}/models/{kind}` của ComfyUI (endpoint CÓ SẴN, đã xác nhận thật
lúc điều tra mục 63 — `kind` = `checkpoints`/`loras`) — dùng CHUNG cho cả 2 nhu cầu (chọn
checkpoint provider LẪN chọn Style LoRA BrandProfile), không cần 2 hàm riêng vì cùng 1
ComfyUI/cùng cơ chế liệt kê. Raise `RuntimeError` rõ ràng nếu ComfyUI không phản hồi được
— KHÔNG âm thầm trả rỗng (tránh nhầm "chưa có file" với "chưa kết nối được").

Endpoint mới `GET /providers/local-sdxl/models?kind=...&base_url=...`
(`app/routers/providers.py`) — 502 kèm thông điệp nếu ComfyUI chưa chạy, 400 nếu `kind`
sai. Đặt dưới `/providers/` dù dùng chung cho cả BrandProfile vì cùng 1 ComfyUI/local_sdxl
— không tạo router riêng chỉ cho 1 endpoint.

**Frontend** — `ComfyModelSelect` (component mới, `ProviderSettings.tsx`, export dùng
chung sang `ChannelDialog.tsx`): fetch danh sách lúc mount, hiện `<select>` với 1 option
rỗng (`emptyLabel` tuỳ context — "Mặc định app" cho checkpoint, "Không dùng" cho LoRA) +
các file thật. Giá trị ĐANG LƯU nhưng ComfyUI không (còn) thấy (VD đã xoá/đổi tên) vẫn
hiện trong dropdown — không tự ý xoá mất cấu hình đang có. ComfyUI chưa chạy/lỗi kết nối
→ fallback về ô nhập tay (KHÔNG chặn cấu hình) kèm thông báo lỗi rõ.

Wire vào 3 chỗ: `ProviderSettings.tsx` — ô "Model" của provider `local_sdxl` đã tồn tại
(sửa) VÀ lúc thêm mới (`AddProviderDialog`); `ChannelDialog.tsx` — ô "Style LoRA" (mục 64).
CHỈ áp dụng cho `local_sdxl`/`loras` — provider local khác (Ollama, Piper, OmniVoice,
local_wan) vẫn nhập tay như cũ (không nằm trong yêu cầu, và local_wan chưa có cơ chế
liệt kê checkpoint Wan tương tự đã xác nhận).

### Verify

4 test mới (`test_providers.py`, respx mock ComfyUI): liệt kê checkpoints thành công, liệt
kê loras với `base_url` tuỳ chỉnh, 400 khi `kind` sai, 502 khi ComfyUI không phản hồi.
Full `pytest`: **306 passed** (302 + 4). `tsc --noEmit`: 0 lỗi. Restart Electron, verify
THẬT qua log backend — UI tự gọi `GET /providers/local-sdxl/models?kind=checkpoints&
base_url=...` ngay khi mở màn Provider AI, trả đúng `["paintersCheckpointOilPaint_v11.
safetensors", "sd_xl_base_1.0.safetensors"]`; gọi trực tiếp `kind=loras` trả đúng
`["ClassipeintXL2.1.safetensors", "InkArtXL_1.2.safetensors"]` — khớp đúng file thật đã
tải ở mục 64.

## 66. Bug thật: ảnh local đúng STYLE nhưng SAI chủ thể — thứ tự prompt khiến content ngắn bị nhấn chìm (2026-08-22)

### Bug người dùng báo

"Đã implement xong nhưng style ảnh thì đúng, mà nội dung ảnh ko giống với mô tả text. Đã
test với video 'Bài học "trọng dụng lúc khủng hoảng, nghi kỵ lúc ổn định"' cho slot
S2-04." — shot S2-04 có `visual_fx = "Cô gái chăn trâu"` (project
`prj_1787364004200`).

### Điều tra thật (dựng lại đúng prompt đã gửi cho SDXL)

```
oil painting, hand-painted, ink wash, muted warm tones, aged paper texture, cinematic
concept art, Cô gái chăn trâu, Visual Style (Phong cách Thị giác) Tông màu chủ đạo (Color
Palette): Warm Muted Tones — Mực tàu, giấy dó, gỗ trầm, đồng cổ, đỏ nhạt phong hóa. Tạo
cảm giác cổ kính, trầm mặc nhưng sang trọng. Chất liệu h[...cắt ở 320 ký tự]
```

Nguyên nhân: thiết kế đợt 2 (mục 64) đặt khối style CỐ ĐỊNH (~90 ký tự) lên ĐẦU prompt
(theo đúng câu chữ đề xuất "chèn cố định ở đầu"), rồi tính "budget CÒN LẠI sau content"
để LẤP ĐẦY bằng `visual_style_prompt` của kênh (đoạn văn dài hàng trăm ký tự). Với shot
này, `visual_fx` chỉ 16 ký tự ("Cô gái chăn trâu") — style CỐ ĐỊNH + style KÊNH ăn hết
303/320 ký tự (95%), nội dung cảnh chỉ còn 5%, lại nằm Ở GIỮA (bị bao vây style cả 2
phía). SDXL/CLIP theo đúng phần nội dung nhiều nhất trong prompt (style) — ra ảnh
ĐÚNG tông/chất liệu nhưng KHÔNG có "cô gái"/"trâu" nào (xác nhận ảnh thật đã sinh trước
khi sửa: phong cảnh làng quê không nhân vật rõ ràng).

Đối chiếu lại tài liệu đề xuất ĐẦU TIÊN (`StudioFlow_ImageVideo_Improvement.md`, mục 63)
— hướng dẫn gốc thực ra đã nói ĐÚNG: "đưa yếu tố bố cục quan trọng nhất lên đầu câu, cắt/
nén mô tả style PHỤ" — nhưng lúc code đợt 2 lại làm NGƯỢC LẠI (đặt style lên đầu) vì làm
theo câu chữ cụ thể hơn của tài liệu đợt 2 (`StudioFlow_Style_Checkpoint_Proposal.md`,
mục 5: "chèn cố định các từ khoá phong cách ở đầu") — 2 tài liệu mâu thuẫn nhau về thứ
tự, và bản thân tài liệu đợt 2 không tính tới trường hợp `visual_fx` NGẮN.

### Fix

`_build_visual_prompt()` (`app/render/engine.py`) đổi lại thứ tự: **NỘI DUNG CẢNH
(`visual_fx`, đã lọc tag) LUÔN đứng ĐẦU** — không bị bất kỳ khối style nào che lấp. Style
cố định (`_LOCAL_SDXL_STYLE_PREFIX`) và style kênh (`visual_style_prompt`) đứng SAU.

Đồng thời đổi cơ chế cắt style kênh — từ "budget CÒN LẠI sau content" (phình to khi
content ngắn) sang **trần CỐ ĐỊNH** `_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS = 90` ký tự,
KHÔNG phụ thuộc content dài/ngắn — đảm bảo style kênh không bao giờ áp đảo, bất kể
`visual_fx` ngắn tới đâu. `visual_fx` KHÔNG bị cắt bởi bất kỳ giới hạn ký tự nào ở tầng
này nữa (tin tưởng LLM viết độ dài hợp lý — xác nhận qua nhiều shot thật, kể cả
`visual_fx` dài ~230 ký tự vẫn ổn).

Hằng số `_LOCAL_SDXL_PROMPT_CHAR_BUDGET` (đợt 2) không còn dùng — xoá (thay bằng cơ chế
trần cố định đơn giản, dễ dự đoán hơn).

### Verify

3 test mới/đổi (`test_render.py`): xác nhận nội dung cảnh đứng đầu (không phải style),
xác nhận `visual_fx` dài không bao giờ bị cắt, và **test tái hiện đúng bug thật** (shot
"Cô gái chăn trâu" + style kênh dài) — xác nhận style kênh bị giới hạn đúng trần cố định
VÀ nội dung cảnh chiếm tỷ trọng khá hơn hẳn trước (>=7%, so với ~5% lúc lỗi). Full
`pytest`: **307 passed** (306 + 1 net mới).

Verify THẬT qua ComfyUI + API thật (không chỉ mock): gọi
`POST /projects/prj_1787364004200/render/shots/S2-04/regenerate-visual` (project + shot
CHÍNH XÁC người dùng báo lỗi) sau khi restart Electron áp dụng fix — ảnh sinh lại có RÕ
2 cô gái + trâu (đúng "Cô gái chăn trâu"), vẫn giữ nguyên style painterly/tông ấm trầm
đúng brand — xác nhận fix giải quyết đúng triệu chứng người dùng báo, không đánh đổi
style đã đúng ở đợt 2.

## 67. Nút "Sinh ảnh/giọng đọc cho toàn bộ block" không hoạt động khi shot đã có sẵn — thêm force regenerate (2026-08-22)

### Yêu cầu người dùng

"Khi các shot ở visual studio đã có ảnh hoặc giọng đọc. Nút Sinh ảnh hoặc sinh giọng đọc
cho toàn bộ block có vẻ đang không hoạt động. Tôi muốn nó hoạt động để trong trường hợp
cần đổi cấu hình brand profile sang giọng mới hoặc visual mới thì sẽ cần"

### Điều tra

KHÔNG phải bug — hành vi có chủ đích từ trước: `generate_visual_asset()`/
`generate_narration_asset()` (`app/render/engine.py`) đều có guard
`if status.visual_status == "ready": return` (tương tự cho narration) — tránh gọi lại API
tốn phí khi batch chạy lần 2 để RESUME sau khi 1 vài shot lỗi. Nút "toàn bộ block" gọi
đúng 2 hàm này cho MỌI shot — khi mọi shot đã `ready`, cả 2 hàm return ngay không làm gì,
từ góc nhìn người dùng giống hệt "nút không hoạt động". Cơ chế bypass ĐÃ CÓ SẴN cho 1 shot
riêng lẻ (`regenerate_visual`/`regenerate_narration`, `app/routers/render.py`) — router tự
reset `status.visual_status = "generating"` TRƯỚC khi dispatch, vô hiệu hoá guard mà
KHÔNG cần sửa `engine.py` — nhưng chưa có phiên bản áp dụng cho CẢ BLOCK.

### Fix

`POST /projects/{id}/render/start` thêm query param `force: bool = False` (mặc định giữ
NGUYÊN hành vi resume cũ). `force=true` — router lặp qua mọi shot trong `state.shots`,
với shot nào đang `ready` (đúng theo `kind`) thì reset về `"generating"` TRƯỚC khi dispatch
background task — cùng cơ chế `regenerate_visual`/`regenerate_narration` đã có, generalize
ra cả block, KHÔNG cần đổi guard trong `engine.py`. Visual bị sinh lại cũng reset
`approved=False` (sinh lại thì cần duyệt lại, cùng nguyên tắc `regenerate_visual`).

Frontend (`VisualStudio.tsx`) — thêm 2 nút MỚI, tách riêng khỏi 2 nút "Sinh Visual/giọng
đọc cho toàn bộ block" hiện có (giữ nguyên, không đổi hành vi resume-only): **"Sinh lại
TOÀN BỘ Visual (kể cả đã có)"** / **"Sinh lại TOÀN BỘ giọng đọc (kể cả đã có)"**, màu cảnh
báo (`color: var(--color-danger)`), tooltip giải thích rõ tốn phí lại + bỏ duyệt. KHÔNG
thêm dialog xác nhận (`window.confirm`) — codebase này KHÔNG dùng pattern đó ở bất kỳ đâu
(rà toàn bộ frontend, không có precedent), giữ nhất quán bằng label/tooltip rõ ràng thay
vì thêm cơ chế mới.

### Verify

4 test mới (`test_render.py`, respx): xác nhận `force=False` (mặc định) không đụng shot
đã ready/đã duyệt, không gọi lại API; `force=true` gọi lại API THẬT (đếm qua
`respx.calls` — bug thật gặp lúc viết test: re-khai báo route bằng `respx.post(url)` lần
2 không kèm `.mock()` làm mất response, phải đếm qua call log thay vì route object) và
sinh lại thành công; reset đúng `approved=False`; tôn trọng đúng phạm vi `kind` (force
narration không đụng visual). Full `pytest`: **311 passed** (307 + 4). `tsc --noEmit`: 0
lỗi. Restart Electron, xác nhận param `force` có thật trong OpenAPI schema đang chạy
(`GET /openapi.json`) — không chạy force=true trên project thật của người dùng để tránh
tốn GPU/đè lại ảnh S2-04 vừa xác nhận đúng ở mục 66 một cách không cần thiết.

## 68. Hiệu ứng lớp phủ (overlay — mưa/tuyết rơi...) theo kênh + theo project (2026-08-22)

### Yêu cầu người dùng

"Bổ sung tính năng cho phép thêm hiệu ứng cho video như 1 layer khi render video, ví dụ
có thêm layer mưa rơi. hoặc tuyết rơi overlay trên nền của visual. Liệu có khả thi không?"
— sau khi xác nhận khả thi kỹ thuật (ffmpeg `blend=all_mode=screen`), người dùng chốt:
"Tôi muốn thêm theo kênh và theo project (tương tự như intro video)."

### Quyết định kiến trúc

Mô phỏng CHÍNH XÁC 2 pattern có sẵn nhưng tách theo 2 khía cạnh khác nhau: **cấu hình**
(2 cấp kênh/project, upload file, override — đúng như người dùng nói "tương tự intro
video") mô phỏng `intro.py`/`bg_music.py`; **cách áp dụng vào ffmpeg** lại mô phỏng
`bg_music.py` chứ KHÔNG phải `intro.py` — vì overlay phải phủ LIÊN TỤC suốt toàn bộ
video (mọi shot), giống nhạc nền, không phải chỉ đoạn mở đầu. Trộn 1 LẦN DUY NHẤT vào
`final_path` sau khi ghép xong toàn bộ (không per-shot) — mượt hơn ở mỗi lần cắt shot,
hiệu quả hơn nhiều lần (1 pass thay vì N pass), tự động phủ luôn cả đoạn intro.

Không ship sẵn file mưa/tuyết mẫu nào, không áp dụng per-shot, không thêm preset "loại
hiệu ứng" (rain/snow dropdown) — người dùng tự upload bất kỳ video hiệu ứng nào, đúng
tinh thần "tự do như intro video".

### Việc đã làm

- **Schema**: `BrandProfile.overlay_effect_path`/`overlay_effect_opacity` (mặc định
  `0.5`) — `app/schemas/__init__.py`. `RenderState.overlay: Optional[
  OverlayEffectOverride]` + class `OverlayEffectOverride(asset_path, opacity)` —
  `app/render/schemas.py`.
- **`app/render/overlay.py`** (file mới, cùng dạng `bg_music.py` — tránh vòng import
  engine.py↔pipeline.py): `resolve_overlay_source(project_overlay, brand)` — ưu tiên
  project override có `asset_path` > overlay mặc định kênh > `None`.
- **`app/render/assembly.py`**: hàm mới `_mix_overlay_effect()` — blend
  `[1:v]{scale/crop theo resolution},colorchannelmixer=rr/gg/bb={opacity}[ovl];
  [0:v][ovl]blend=all_mode=screen:shortest=1[v]`, overlay đọc qua `-stream_loop -1`
  (lặp vô hạn nếu clip ngắn hơn video), audio giữ nguyên `-c:a copy` + `-map 0:a?` (dấu
  `?` vì overlay có thể dùng độc lập, video chưa chắc đã có audio track). Gọi ngay sau
  khối `bg_music` hiện có trong `assemble_video()`.
- **Endpoint cấp kênh** (`app/routers/channels.py`): `POST/GET
  /channels/{id}/brandprofile/overlay(/upload)` — mô phỏng 1:1 `upload_brand_bg_music`/
  `get_brand_bg_music` (audio→video, tái dùng `_INTRO_VIDEO_EXT_BY_*` đã có).
- **Endpoint cấp project** (`app/routers/render.py`): `POST/PATCH/DELETE/GET
  /projects/{id}/render/overlay(/upload|/asset)` — mô phỏng 1:1 4 endpoint bg-music.
- **Frontend**: `types.ts`/`client.ts` thêm type + hàm gọi API; `ChannelDialog.tsx` —
  mục "Hiệu ứng lớp phủ mặc định của kênh" (upload video + preview + slider cường độ);
  `VisualStudio.tsx` — component `OverlayEffectCard` (mô phỏng `BgMusicCard` 1:1).

### Bug thật phát hiện lúc viết test — treo vô hạn (`ffmpeg` không bao giờ thoát)

Test ffmpeg thật đầu tiên (`_mix_overlay_effect` với overlay ngắn hơn video, cần
`-stream_loop -1` lặp lại) TREO >120s không thoát. Root cause: filter `blend` mặc định
`eof_action=repeat` (tài liệu ffmpeg, nhóm "framesync options") — khi input NGẮN HƠN
(`video_path`, không lặp) hết trước, `blend` không báo EOF mà LẶP LẠI frame cuối MÃI MÃI
để tiếp tục khớp với input kia (overlay lặp vô hạn) — nên cờ `-shortest` ở output KHÔNG
BAO GIỜ có tín hiệu để dừng tiến trình, dù bản thân `video_path` đã "hết" từ lâu. Đây là
bug THẬT sẽ khiến MỌI lần render có cấu hình overlay bị treo vô hạn trên máy người dùng
nếu không phát hiện qua test thật (không mock) — tái hiện bằng tay qua ffmpeg CLI trực
tiếp trước khi sửa để xác nhận chắc chắn nguyên nhân.

Fix: thêm `shortest=1` NGAY TRÊN filter `blend` (không phải cờ `-shortest` ở output) —
`blend=all_mode=screen:shortest=1` khiến chính filter kết thúc ngay khi input ngắn hơn
kết thúc, giải quyết tận gốc thay vì dựa vào cờ output không có tác dụng ở trường hợp này.

### Verify

21 test mới (`tests/test_overlay.py`, mô phỏng cấu trúc `test_bg_music.py`): CRUD 2 cấp
(channel + project, 13 test), pure-function `resolve_overlay_source` (4 test, ưu tiên/
fallback/bỏ qua override rỗng/None khi không có gì), **ffmpeg THẬT** (không mock, 4
test): `_mix_overlay_effect` trực tiếp (xác nhận `-shortest`+`shortest=1` chặn đúng độ
dài dù overlay lặp vô hạn — đo bằng cách scale cả frame về 1x1 rồi đọc 1 byte grayscale
thô làm "độ sáng trung bình", tránh cần so khớp ảnh phức tạp; nền đen + overlay trắng →
frame sau blend phải sáng hẳn), cường độ theo `opacity` (opacity thấp phải mờ hơn), và
`assemble_video()` đầu-cuối (overlay mặc định kênh phủ hết TOÀN BỘ video kể cả cuối,
project override thắng brand — phân biệt bằng kênh màu RGB khác nhau đỏ/lam). Full
`pytest`: **332 passed** (311 + 21). `tsc --noEmit`: 0 lỗi.

Backend chạy trong Electron (`electron/src/backend-launcher.ts`) spawn `uvicorn` KHÔNG
có `--reload` (khác `npm run dev:backend` ở root có `--reload` nhưng cổng 8756 lúc kiểm
tra lại đang bị 1 tiến trình KHÔNG LIÊN QUAN của người dùng chiếm — 1 app khác hẳn với
route `/api/v1/niches`, `/content-ideas`... không phải StudioFlow) — nên code mới CHƯA
có hiệu lực trong phiên Electron đang chạy cho tới khi người dùng tự restart app; không
tự ý kill tiến trình Electron/terminal đang chạy của người dùng. Người dùng cần restart
app để nghiệm thu tính năng này trên UI thật.

## 69. Bug thật: overlay đổi màu toàn bộ video sang tím + thêm/xoá overlay lỗi thoáng qua (2026-08-23)

### Yêu cầu người dùng

"Hiệu ứng lớp phủ (layter) test ở project 'Bài học "trọng dụng lúc khủng hoảng, nghi kỵ
lúc ổn định"' khi thêm/xóa bị lỗi. Thử lại lại được. Video render sau khi thêm layer
hiệu ứng bị đổi màu toàn bộ sang một lớp phủ màu tím - vẫn nhận ra hiệu ứng nhưng hình
ảnh bị đổi màu"

### Bug 1 — đổi màu tím: lỗi thật trong ffmpeg `blend` filter, không phải lỗi thiết kế

Điều tra bằng tay trực tiếp qua ffmpeg CLI (không đoán, đo thật): dựng nền ĐỎ THUẦN +
overlay XÁM 50% (đã qua `colorchannelmixer` như code thật), `blend=all_mode=screen` PHẢI
cho kết quả hồng nhạt (255,128,128 theo công thức screen chính xác — `screen(0,x)=x` là
đẳng thức toán học, không phải phỏng đoán) nhưng đo thật ra (255,59,255) — G và B lệch xa
nhau bất thường, đúng như triệu chứng "ngả tím" người dùng báo. Test dò từng bước:
- `blend` áp thẳng lên `yuv420p` (code cũ): SAI. Giả thuyết ban đầu — "screen" tính trên
  từng plane Y/U/V độc lập là sai về mặt toán học vì U/V trung tính là 128 (không phải 0
  như Y) — hợp lý nhưng CHƯA ĐỦ để giải thích hết.
- Ép `format=rgb24` trước `blend` (tưởng sẽ sửa vì RGB không có vùng trung tính lệch
  tâm): VẪN SAI, giá trị giống hệt như không ép. Loại trừ giả thuyết "chỉ do YUV".
  Test triệt để hơn: `blend(trắng,trắng)` và `blend(xám,xám)` qua `rgb24` cũng cho U/V
  lệch CỐ ĐỊNH +64 so với đúng — chứng minh bản thân pixel format `rgb24` (packed) có
  lỗi xử lý trong filter `blend` ở BUILD ffmpeg đang dùng (8.1.2-essentials, gyan.dev),
  không liên quan gì đến YUV/RGB nữa.
- Đổi `format=rgb24` → **`format=gbrp`** (planar RGB, cùng số liệu màu nhưng bố cục
  plane khác — mỗi kênh 1 plane riêng thay vì đan xen từng pixel): kết quả ĐÚNG NGAY —
  đo thật (255,127,127), sai số làm tròn 1 đơn vị, khớp hoàn toàn công thức. Xác nhận
  lại ở độ phân giải HD 1280x720 (khớp render thật) — vẫn đúng.

Fix (`app/render/assembly.py::_mix_overlay_effect`): thêm `format=gbrp` trên CẢ 2 nhánh
(overlay và video nền) TRƯỚC `blend=all_mode=screen:shortest=1`, giữ nguyên
`colorchannelmixer`/`_scale_cover_filter`/`shortest=1` đã có. Không cần hiểu sâu hơn TẠI
SAO build ffmpeg này lỗi riêng với `rgb24` trong `blend` — `gbrp` cho kết quả đúng và ổn
định qua nhiều lần đo lại nên chọn làm fix, không cố vá theo hướng khác phức tạp hơn
(colorspace/matrix flags — đã thử `setparams=range=pc`, `scale=out_range=full`, đều
KHÔNG chính xác bằng `gbrp`).

### Bug 2 — thêm/xoá overlay lỗi thoáng qua, thử lại được: Windows file lock

Rà log backend lúc lỗi: không có traceback/500 nào gắn với request overlay (chỉ có
`ConnectionResetError` là noise vô hại từ Range request bị huỷ giữa chừng, không liên
quan). Xác định nguyên nhân qua đọc code: MỌI endpoint upload/xoá asset ghi đè-tại-chỗ
(shot visual, intro visual/audio, bg-music, overlay — cả cấp kênh lẫn cấp project, 12
điểm gọi trong `render.py`+`channels.py`) đều gọi thẳng `Path.unlink()`/`path.write_bytes()`
KHÔNG có xử lý lỗi. Trên Windows, xoá/ghi đè 1 file NGAY SAU KHI trình duyệt vừa stream
xong preview `<video>`/`<audio>` (`range_file_response`) có thể vẫn còn giữ handle đọc
file trong chốc lát → `PermissionError` (WinError 32) — đúng khớp "lỗi 1 lần, thử lại
ngay sau đó lại được" (handle đã được trình duyệt nhả ra). Đây là lỗi TIỀM ẨN CÓ SẴN từ
trước ở MỌI tính năng upload media (không riêng overlay) — người dùng chỉ mới gặp rõ ở
overlay vì đây là tính năng đầu tiên có preview VIDEO (giữ connection/handle lâu hơn
audio) và người dùng đang test nhanh thêm/xoá liên tục.

Fix: `app/filestore.py` thêm `_retry_on_permission_error()` (thử lại tối đa 10 lần ×
150ms ≈ 1.5s khi gặp `PermissionError`) + `unlink_retrying()`; `write_bytes()` cũng tự
thử lại theo cùng cơ chế. Áp dụng THAY THẾ toàn bộ 12 điểm gọi `.unlink()` trực tiếp
trong `render.py`/`channels.py` (không chỉ overlay — sửa nhất quán cho shot visual,
intro, bg-music luôn, tránh lặp lại đúng bug này ở tính năng khác sau này).

### Verify

Test mới `test_mix_overlay_effect_preserves_hue_no_color_cast` (`test_overlay.py`) —
nền đỏ + overlay xám qua `blend`, assert G≈B (đúng hue) thay vì lệch xa (bug tím cũ) —
sẽ FAIL nếu quay lại `rgb24`/bỏ `format=gbrp`. Test mới `test_filestore.py` (3 test) —
mock `PermissionError` thoáng qua (2-3 lần đầu) rồi thành công, xác nhận
`unlink_retrying`/`write_bytes` tự thử lại đúng và vẫn raise nếu lỗi kéo dài mãi (không
retry vô hạn). Full `pytest`: **336 passed** (332 + 1 hue test + 3 filestore test).
Restart Electron, xác nhận cả 2 fix đã nạp vào backend đang chạy.

## 70. Nhạc nền & overlay riêng ở Visual Studio hiển thị rõ kế thừa từ BrandProfile (2026-08-23)

### Yêu cầu người dùng

"Phần nhạc nền và hiệu ứng lớp phủ riêng ở bước visual studio cũng cần inherit từ brand
profile nếu đã config sẵn (tương tự intro video)"

### Việc đã làm

`BgMusicCard`/`OverlayEffectCard` (`VisualStudio.tsx`) TRƯỚC ĐÂY hiện trống ("Chưa có
nhạc nền/overlay riêng") khi project chưa upload gì, dù lúc ghép MP4 THẬT SỰ đã tự
fallback dùng nhạc nền/overlay mặc định cấp kênh (`resolve_bg_music_source`/
`resolve_overlay_source`, fallback NGẦM, không hiện gì ở UI) — cùng loại vấn đề
`IntroShotCard` đã sửa ở mục 61. Áp dụng ĐÚNG pattern đó cho 2 card này: đọc
`BrandProfile.bg_music_path`/`overlay_effect_path` qua `api.getBrandProfile(channelId)`
(CHỈ để hiển thị, không PUT lại), khi project CHƯA có asset riêng và brand CÓ cấu hình
→ hiện preview thật (nghe được/xem được) của asset thương hiệu + tag "Kế thừa từ hồ sơ
thương hiệu". Cả 2 component cần thêm prop `channelId` (lấy từ `project.channel_id` ở
2 call site đầu Visual Studio).

KHÔNG thêm nút "tắt hẳn kế thừa" như `IntroAssetStatus.disabled` — bg-music/overlay
chưa có yêu cầu đó (chỉ có 2 trạng thái: override hoặc không, không có "chủ động tắt
hẳn cả 2"). Slider âm lượng/cường độ vẫn CHỈ hiện khi project có asset RIÊNG (giữ
nguyên hành vi cũ) — chỉnh khi đang kế thừa vô nghĩa vì `resolve_*_source` bỏ qua
override không có `asset_path` (xem test `test_resolve_bg_music_source_ignores_
override_without_path`/tương tự cho overlay).

### Verify

`tsc --noEmit`: 0 lỗi. Không cần test backend mới (không đổi logic backend, chỉ đọc
field BrandProfile có sẵn để hiển thị — đúng field đã có test resolve_*_source từ mục
53/68). Restart Electron để nạp thay đổi.

## 71. Chỉnh âm lượng nhạc nền riêng ở Visual Studio kể cả khi đang kế thừa brand (2026-08-23)

### Yêu cầu người dùng

"Block Phần nhạc nền cũng cần bổ sung thêm cấu hình 'Âm lượng nhạc nền so với giọng đọc
chính' ở visual studio tương tự như ở brand profile"

### Vấn đề

Sau mục 70 (hiển thị kế thừa), `BgMusicCard` vẫn CHỈ hiện thanh trượt âm lượng khi
project có asset RIÊNG (`hasAsset`) — lúc đang kế thừa nhạc brand thì KHÔNG chỉnh được
gì cả. Lý do lúc đó: `resolve_bg_music_source` coi `BgMusicOverride` là ALL-OR-NOTHING —
override CHƯA có `asset_path` (chỉ chỉnh volume, chưa upload) bị bỏ qua HOÀN TOÀN kể cả
phần volume, nên hiện thanh trượt lúc đó cũng vô nghĩa (chỉnh xong không có tác dụng gì
lúc ghép MP4).

### Việc đã làm

**Backend** (`app/render/bg_music.py::resolve_bg_music_source`) — tách riêng
`asset_path` và `volume` thay vì all-or-nothing: `asset_path` vẫn ưu tiên project >
brand (fallback riêng biệt), nhưng `volume` giờ ưu tiên project (nếu object override
TỒN TẠI, bất kể có `asset_path` hay chưa) > brand. Cho phép "dùng nhạc nền của kênh,
chỉnh âm lượng RIÊNG cho project này" mà không cần upload lại file — đúng ý người dùng
"tương tự brand profile" (brand profile chỉnh audio+volume độc lập, project giờ cũng
vậy).

**Frontend** (`BgMusicCard`) — thanh trượt âm lượng giờ hiện khi CÓ nguồn nhạc (asset
riêng HOẶC đang kế thừa brand), không chỉ khi có asset riêng. Giá trị khởi điểm khi
CHƯA có override riêng = volume HIỆN TẠI của brand (đọc thêm `bp.bg_music_volume` qua
`api.getBrandProfile`, trước đó chỉ đọc `bg_music_path`) — tránh "nhảy giá trị" về mặc
định cứng 0.3 khi brand đã chỉnh khác đi. Thêm ghi chú nhỏ dưới nhãn khi đang kế thừa
("chỉnh riêng cho project này, vẫn dùng nhạc của kênh") để rõ ý không phải đang sửa
BrandProfile.

### Verify

Cập nhật test `test_resolve_bg_music_source_ignores_override_without_asset_path` →
`test_resolve_bg_music_source_uses_project_volume_with_brand_asset_when_no_project_
asset` (đổi assertion đúng hành vi mới: override chỉ có volume vẫn áp dụng được, ghép
với asset_path của brand). Full `pytest`: **336 passed** (không đổi tổng số — sửa 1 test
cũ thay vì thêm mới, vì đây là đổi HÀNH VI của hàm resolve có sẵn). `tsc --noEmit`: 0
lỗi. Chưa áp dụng tương tự cho overlay/opacity (người dùng chỉ yêu cầu nhạc nền đợt
này) — `resolve_overlay_source` vẫn all-or-nothing, có thể cần đợt sau nếu người dùng
muốn tương tự.

## 72. Bug thật: shot B01 "lỗi" video local thực ra chỉ là bị Dừng — thêm 1 bug thật khác lúc điều tra (2026-08-23)

### Yêu cầu người dùng

"Kiểm tra lại lỗi tạo video cho shot B01 của project 'Nguyễn Trãi và án Lệ Chi Viên: Khi
tri thức va chạm quyền lực triều đình'" — kèm câu hỏi kiến trúc về pipeline video local
(xem phần trả lời riêng trong hội thoại, không phải mục sửa code).

### Điều tra B01

Đọc `render.json` của `prj_1787331251320`: `visual_error` là JSON THÔ từ ComfyUI —
`status_str: 'error'`, `messages` có entry `execution_interrupted` tại node `3`
(KSampler), sau khi đã chạy xong 7 node trước đó (~9.35 phút tính theo timestamp
`execution_start`→`execution_interrupted`). `execution_interrupted` là message ComfyUI
gửi khi có ai gọi `POST /interrupt` — rà code xác nhận `POST /projects/{id}/render/
cancel` (nút "Dừng") gọi ĐÚNG `engine.try_interrupt_local_gpu_job()` → ComfyUI
`/interrupt`, và đây là NƠI DUY NHẤT trong codebase gọi `/interrupt`. Kết luận: B01
KHÔNG lỗi thật — ai đó đã bấm "Dừng" trong lúc video đang render (video Wan2.2 local
mất nhiều phút/shot).

### Bug thật #1: interrupted bị hiện như lỗi kỹ thuật thay vì "đã dừng"

ComfyUI báo CẢ lỗi thực thi thật LẪN job bị Dừng qua CÙNG `status_str == "error"` trong
`/history` — code cũ (`image_comfy_sdxl.py`/`video_comfy_wan.py`) coi MỌI `status_str
== "error"` là lỗi provider thật, dump nguyên `entry['status']` (traceback/node id kỹ
thuật) vào `visual_error` — người dùng thấy shot "lỗi" trông như crash thật dù chỉ bấm
Dừng.

Fix: `app/providers/base.py` thêm `GenerationInterrupted` (exception dùng chung, đặt ở
`base.py` để tránh vòng import — provider không được import `engine.py`) +
`raise_if_interrupted(status, job_id)` (soi `status.messages` tìm message loại
`execution_interrupted`, phân biệt với `execution_error` — lỗi thật). Gọi hàm này TRƯỚC
khi raise `RuntimeError` chung ở cả `image_comfy_sdxl.py` VÀ `video_comfy_wan.py`
(cùng lỗ hổng, sửa nhất quán cả 2 — dù bug report chỉ nói video). `engine.py` bắt
`GenerationInterrupted` CÙNG NHÁNH với `GenerationCancelled` có sẵn (dừng ngay, không
thử fallback provider, thông báo rõ "đã dừng").

### Bug thật #2 (phát hiện phụ, lúc viết test cho bug #1): lỗi ảnh local KHÔNG BAO GIỜ báo được, treo tới hết timeout

Viết test cho `image_comfy_sdxl.py` (mô phỏng ComfyUI trả job lỗi) làm PYTEST TREO
THẬT — điều tra bằng debug print xác nhận: check `status_str == "error"` nằm LỒNG bên
trong `if entry.get("outputs")` — nhưng job lỗi/bị Dừng THẬT SỰ hầu như KHÔNG BAO GIỜ
có `outputs` (đó chính là ý nghĩa "lỗi", chưa kịp render xong) → nhánh raise KHÔNG BAO
GIỜ chạy tới, job lỗi bị coi nhầm là "đang chạy" cho tới khi hết hẳn timeout poll mới
báo lỗi CHUNG CHUNG "ComfyUI không trả kết quả" — che mất lý do lỗi thật hoàn toàn. Đây
là bug ĐỘC LẬP, có TRƯỚC cả đợt sửa này, chỉ tình cờ lộ ra vì trước giờ chưa có test nào
cho đường lỗi của file này. `video_comfy_wan.py` KHÔNG dính bug này (cấu trúc code vốn
đã kiểm `status_str` độc lập với `outputs`).

Fix: tách check `status_str == "error"` ra ĐỘC LẬP với `entry.get("outputs")`, kiểm
TRƯỚC khi cần outputs — khớp đúng cấu trúc `video_comfy_wan.py` đã có sẵn.

### Verify

5 test mới: `test_image_comfy_sdxl.py` (+2: raise đúng `GenerationInterrupted` khi có
`execution_interrupted`, raise `RuntimeError` thường khi lỗi thật — test THỨ 2 này lúc
đầu TREO THẬT, dẫn tới phát hiện bug #2), `test_video_comfy_wan.py` (file test MỚI, 3
test — chưa có test nào cho file này trước đợt này). Full `pytest`: **341 passed** (336
+ 5). Không cần restart Electron ngay (chưa test lại trên GPU thật) — khuyến nghị bấm
"Sinh lại video" cho shot B01, lỗi cũ chỉ là do đã bị Dừng giữa chừng, không phải lỗi
pipeline.

## 73. Cải thiện sinh video local (Wan2.2 TI2V-5B) — Image-to-Video + tinh chỉnh tham số (2026-08-23)

### Yêu cầu người dùng

Người dùng đính kèm `StudioFlow_Video_Improvement_Plan.md` (dựa trên điều tra mục 72)
đề xuất cải thiện pipeline video local — trọng tâm: chuyển từ text-to-video sang
image-to-video (dùng ảnh SDXL đã tune làm khung hình đầu), tách prompt chuyển động
riêng, rút ngắn clip + tinh chỉnh tham số. Lên plan (plan mode) rồi triển khai cả 3
phase liền theo yêu cầu người dùng "Triển khai luôn cả 3 phases".

### Quyết định phạm vi khác đề xuất gốc

KHÔNG thêm `shot.motion_type` (static_parallax/map_animation/ai_video) vào
ProductionPack — cơ chế "ảnh tĩnh + chuyển động camera" đề xuất mô tả (gọi là "parallax
2.5D") ĐÃ TỒN TẠI: `Shot.visual_type=image` + `Shot.camera_motion`
(`app/render/camera_motion.py` — Ken Burns 2D thật qua `zoompan`/`rotate`, KHÔNG phải
parallax lớp độ sâu thật như tên gọi trong đề xuất, nhưng cùng tinh thần: chuyển động
mượt trên ảnh tĩnh, không cần AI video). Đạt mục tiêu "giảm phụ thuộc Wan" bằng hướng
dẫn sử dụng (`specs/06_uiux.md`/`07_prompt_templates.md`), không đổi schema/pipeline.
`map_animation` (template bản đồ động) ngoài phạm vi hoàn toàn — hệ thống riêng, không
liên quan sinh video AI.

### Phase A — Tinh chỉnh tham số (`app/providers/video_comfy_wan.py`)

- Độ phân giải đổi `1280×704` → **`1344×768`** (khớp CHÍNH XÁC bucket SDXL đang dùng —
  `image_comfy_sdxl.py`, cả 2 số chia hết 16) — để ảnh anchor (Phase B) không cần
  `ImageScale` co/crop, giữ nguyên khung đã tune. Tăng ~14.5% pixel — CHƯA verify tốc
  độ/VRAM thật.
- Negative prompt thêm cụm chống lỗi ĐẶC THÙ video diffusion: `flickering, morphing,
  warping face, identity drift between frames, jittery motion` (khác lỗi ảnh tĩnh).
- `_MAX_GENERATE_SECONDS = 4` — số khung THỰC SỰ gửi cho Wan bị chặn ở 4s, `assembly.py`
  tự lặp (`-stream_loop -1`, `_build_segment`) hoặc hấp thụ chênh lệch
  (`_reflow_video_durations`) để lấp đầy thời lượng thật của shot — xác nhận AN TOÀN
  qua điều tra code trước khi làm (không vỡ đồng bộ audio).

### Phase B — Image-to-Video (`app/render/engine.py`)

Hàm mới `_try_generate_wan_anchor_image()`: khi provider đang thử là `local_wan`, sinh
1 ảnh anchor bằng ĐÚNG provider `local_sdxl` (nếu đã cấu hình) — cùng prompt đã tune
(`_build_visual_prompt(..., for_local_sdxl=True)`), cùng seed, cùng Style LoRA
(`brand.style_lora_path/strength`) — đảm bảo anchor CÙNG "chữ ký hình ảnh" với ảnh
khác trong project. Lưu `assets/{shot_id}_anchor.png` (KHÔNG phải `visual_asset_path`
của shot, chỉ artifact debug, chưa hiện UI). BEST-EFFORT toàn diện: không cấu hình
`local_sdxl`, hoặc sinh anchor lỗi bất kỳ → trả `None`, rơi về T2V thuần y hệt hành vi
cũ, KHÔNG chặn việc sinh video.

KHÁC Tier 2 cũ (mục ~18, đã tắt vì dùng CHUNG 1 thumbnail cho mọi shot gây lệch nội
dung): anchor lần này sinh RIÊNG cho ĐÚNG shot đang xử lý.

**Giữ nguyên `denoise: 1`** — không giảm để "tăng tốc": video model cần denoise đủ
mọi frame để tổng hợp chuyển động mạch lạc, hạ denoise giữ lại nhiễu trên TOÀN BỘ
latent (không chỉ frame đầu), rủi ro artifact mà không có lợi ích tốc độ rõ ràng (chi
phí vẫn là frame×step). I2V ở đây là đòn bẩy CHẤT LƯỢNG/NHẤT QUÁN phong cách, không
phải tốc độ.

### Phase C — Motion prompt riêng

`BrandProfile.motion_tone` (mới, mặc định "chuyển động chậm, tinh tế, không giật gân,
không rung camera" — khớp brand DNA kênh sử) + hàm `_build_video_motion_prompt()`
(content-first, lọc tag như `for_local_sdxl`, nối bằng ". " — Wan dùng UMT5 XXL kiểu
T5, hiểu câu văn tự nhiên tốt hơn CLIP nên KHÔNG dùng kiểu phẩy-ngăn-cách của SDXL).
CHỈ áp dụng cho `local_wan`, không đổi Sora/Veo/Flux. Field mới ở `ChannelDialog.tsx`
cạnh "Style hình ảnh kênh".

### Verify

14 test mới: `test_video_comfy_wan.py` (+3 — resolution khớp SDXL, negative prompt
chứa từ khoá mới, `_MAX_GENERATE_SECONDS` cắt đúng số khung), `test_render.py` (+9 —
`_build_video_motion_prompt` × 3, `_try_generate_wan_anchor_image` × 4 đơn vị (fallback
graceful khi thiếu provider/lỗi, lưu đúng file + truyền đúng LoRA), 1 test END-TO-END
thật qua `/render/start` xác nhận `local_wan` upload đúng ảnh anchor lên ComfyUI và
workflow video có `start_image`). Sửa 1 test cũ (`test_short_form_projects.py`) hardcode
số 1280×704 — đổi sang so sánh với hằng số thay vì số cứng, tránh trùng nguồn sự thật.
Full `pytest`: **352 passed** (341 + 14 mới − sửa lại 1 test cũ không tính thêm/bớt số
lượng thật). `tsc --noEmit`: 0 lỗi.

**Cần verify bằng mắt trên GPU thật** (không thể qua test): chất lượng/tốc độ ở độ
phân giải 1344×768 mới, video anchor có giữ đúng phong cách ảnh không, thời gian sinh
1 clip 4s có chấp nhận được không.

## 74. Rà soát UX luồng Brief → Script Studio → Visual Studio → Output (2026-08-23)

### Yêu cầu người dùng

"rà soát lại UI UX của luồng tạo video từ brief, đến script studio, visual studio, đến
output và để xuất cải thiện" — kèm 2 quan sát cụ thể: "nhiều nút bấm, bố trí chưa
consistent" và "right sidebar không để làm gì". Sau khi rà soát + trình bày báo cáo
(artifact), người dùng chốt "triển khai toàn bộ đề xuất".

### Điều tra

Đọc trực tiếp source 4 màn + shell dùng chung (`StepHeader.tsx`, `RightPanel.tsx`,
`ProjectView.tsx`, `Stepper.tsx`). Phát hiện chính: comment TRONG chính
`StepHeader.tsx` đã tự thú nhận nguyên nhân gốc — *"actions ngày càng dài (nhiều nút
được thêm theo các đợt cập nhật)"* — mỗi tính năng mới thêm 1 nút vào ĐÚNG chỗ cũ,
không ai rà lại tổng thể. Header Visual Studio có 7 nút cùng cỡ `btn-secondary`/
`btn-danger-color` trong 1 hàng; `RightPanel.tsx` sau khi bỏ tóm tắt BrandProfile
(mục 62) chỉ còn 1 dòng "Phiên bản Pack", chiếm 280px mọi màn.

### Đề xuất được duyệt + đã triển khai (5/5)

1. **RightPanel có nội dung thật** — thêm Kênh+niche, Định dạng (Long/Short), Số shot,
   Cảnh báo guardrail (script.body[].warning) — tất cả tính từ props đã có sẵn
   (`project`+`pack`, đã thêm `pack` làm prop mới), KHÔNG gọi thêm API nào. Chủ động
   không lặp lại thông tin StatsBar đã hiện ở header (từ/shot/thời lượng ước tính).
2. **Header Visual Studio tách 2 cấp** — component mới `OverflowMenu` (menu thả xuống,
   đóng bằng bấm ra ngoài — cùng cơ chế backdrop-click-to-close đã dùng ở
   `LibraryPicker.tsx`, chỉ đổi backdrop trong suốt + neo cạnh nút thay vì giữa màn
   hình) gom 2 nút "Sinh lại TOÀN BỘ..." (tốn phí + bỏ duyệt) vào "⋯ Tuỳ chọn khác" —
   tách khỏi 2 nút an toàn dùng hằng ngày. "Duyệt toàn bộ block" chuyển xuống sát danh
   sách shot (nó thao tác trên danh sách đó, không phải điều hướng cấp trang).
3. **1 `btn-primary`/hàng** — `ShotCard`: nút "Tạo giọng đọc" đổi `btn-primary` →
   `btn-secondary` (trước đó đứng ngang hàng với "Tạo ảnh/video", 2 primary cạnh nhau
   mất phân cấp). Các card khác (BgMusicCard/OverlayEffectCard/IntroShotCard) đã đúng
   quy tắc từ trước (không nút nào primary), không cần đổi.
4. **OutputCenter dùng lại `StepHeader`** — bỏ `<h3>/<p>` tự viết riêng (khác 3 màn
   kia). Bỏ nhãn "Beta · M2" đã lỗi thời trên "Render in-app" (đây giờ là đường DUY
   NHẤT thực sự ra được video hoàn chỉnh) + bỏ liệt kê cứng tên provider cụ thể
   (ElevenLabs/OpenAI/Sora — danh sách đã lỗi thời, giờ còn cả local SDXL/Wan2.2/
   OmniVoice/Piper/Flux/Gemini).
5. **Bỏ `window.confirm()` ở xoá project** (`ProjectView.tsx`) — đây là nơi DUY NHẤT
   dùng dialog xác nhận trình duyệt, trong khi mọi hành động phá huỷ khác chỉ dựa
   nhãn+tooltip. Hành động này CHỈ chuyển vào Thùng rác (khôi phục được), không xoá
   vĩnh viễn, nên hợp lý hơn khi theo ĐÚNG quy ước "label rõ đủ" của phần còn lại app —
   dành dialog xác nhận thật cho đúng chỗ cần (xoá VĨNH VIỄN ở Thùng rác, đã có sẵn,
   không hoàn tác được).

### Verify

`tsc --noEmit`: 0 lỗi sau mỗi file sửa. HMR (vite) áp thành công cả 4 file sửa
(`RightPanel.tsx`, `ProjectView.tsx`, `OutputCenter.tsx`, `VisualStudio.tsx`) không lỗi
runtime. Không đổi backend — không cần restart Electron.

## 75. Cultural lock chống thiên lệch văn hoá Nhật/Hàn cho ảnh local SDXL (2026-08-23)

### Yêu cầu người dùng

Ảnh sinh bằng local SDXL mang nét văn hoá Nhật/Hàn thay vì Việt Nam — nguyên nhân gốc:
checkpoint/LoRA phong cách "Á Đông/thuỷ mặc" trên Civitai tuyệt đại đa số train từ dữ
liệu Nhật (anime/Danbooru/ukiyo-e) và Trung/Hàn (webtoon/hanbok). Đề xuất 3 lớp giải
pháp: (1) prompt cultural-lock (từ khoá Việt + negative loại Nhật/Hàn), (2) ảnh tham
chiếu (IPAdapter) — chấp nhận đảo ngược quyết định "không dùng IPAdapter" đã ghi 2 lần
trong code, (3) stack nhiều LoRA (chất liệu + hướng văn hoá). Lên plan (plan mode, có
hỏi lại 1 câu về cơ chế ảnh tham chiếu — người dùng chọn IPAdapter dù biết rủi ro) rồi
triển khai cả 3 phần.

### Phần A — Cultural lock trong prompt

`BrandProfile` thêm `cultural_lock_positive` (rỗng mặc định — đặc thù theo từng kênh/
thời kỳ lịch sử, người dùng tự điền) và `cultural_lock_negative` (default sẵn: "japanese
kimono, torii gate, korean hanbok, japanese architecture, korean architecture, anime
style, manga, japanese art style" — phổ quát cho mọi kênh Việt). `_build_visual_prompt`/
`_build_video_motion_prompt` nối `cultural_lock_positive` SAU content, TRƯỚC style — áp
dụng MỌI provider (cloud lẫn local). `cultural_lock_negative` CHỈ áp dụng
`local_sdxl`/`local_wan` (negative-prompt thật qua ComfyUI) — cloud không có tham số
negative prompt (xác nhận qua code, không đoán). Field mới ở ChannelDialog.tsx.

### Phần B — Stack nhiều Style LoRA

Đổi `BrandProfile.style_lora_path`/`style_lora_strength` (đơn, mục 64) →
`style_loras: list[StyleLoraEntry]` (nhiều LoRA). `image_comfy_sdxl.py::_add_lora_nodes`
(đổi từ `_add_lora_node` số ít) CHAIN nhiều node `LoraLoader` liên tiếp — vẫn chỉ dùng
core node có sẵn. Frontend đổi 1 dòng LoRA thành danh sách thêm/bớt được, tái dùng
`ComfyModelSelect` mỗi dòng.

### Phần C — Ảnh tham chiếu qua IPAdapter (rủi ro cao, CHƯA verify thật)

**Đảo ngược quyết định** "không dùng IPAdapter" (`image_comfy_sdxl.py` docstring +
specs/05 §8d, do rủi ro custom node lệch tên/version) — người dùng xác nhận chấp nhận
đánh đổi vì IPAdapter là cơ chế ĐÚNG (tách phong cách khỏi bố cục, nhận nhiều ảnh cùng
lúc), khác img2img có sẵn (Tier 2, 1 ảnh, bố cục/màu ảnh gốc ảnh hưởng trực tiếp — GIỮ
NGUYÊN, không đụng).

`BrandProfile.style_reference_paths`/`style_reference_weight` mới — endpoint CRUD ĐẦU
TIÊN xử lý DANH SÁCH nhiều file trong BrandProfile (`POST/DELETE/GET .../style-
references/...`, khác logo/intro/bg-music/overlay đều 1 file). `image_comfy_sdxl.py::
_add_ipadapter_nodes` — `CLIPVisionLoader`+`IPAdapterModelLoader`+`LoadImage` (chain
`ImageBatch` nếu >1 ảnh)+`IPAdapterApply`, áp SAU LoRA nếu cả 2 cùng dùng (đọc thẳng
`workflow["3"]["inputs"]["model"]` hiện tại làm input). **Fallback tự động**: ComfyUI từ
chối job (400, thường "node type not found" nếu chưa cài đúng
`ComfyUI_IPAdapter_plus`/model) → thử lại NGAY 1 lần KHÔNG IPAdapter thay vì chặn hẳn
sinh ảnh.

**CHƯA THỂ verify thật** trên ComfyUI+IPAdapter (khác MỌI tính năng ComfyUI khác trong
codebase, đều verify qua GPU thật) — API IPAdapter đã đổi qua nhiều phiên bản cộng đồng.
Người dùng cần: cài `ComfyUI_IPAdapter_plus`, tải `CLIP-ViT-H-14-laion2B-s32B-b79K.
safetensors` (`ComfyUI/models/clip_vision/`) + `ip-adapter-plus_sdxl_vit-h.safetensors`
(`ComfyUI/models/ipadapter/`), test thật, báo lại NGUYÊN VĂN lỗi nếu ComfyUI từ chối
node/tham số để chỉnh đúng theo bản đã cài.

### Verify

Test mới: `_build_visual_prompt`/`_build_video_motion_prompt` cultural_lock_positive
đúng vị trí + áp dụng cả cloud/local; `_local_sdxl_kwargs` đọc đúng `style_loras`/
`cultural_lock_negative`/`style_reference_paths` (bỏ qua ảnh thiếu, không raise);
`_add_lora_nodes` chain đúng 2 LoRA liên tiếp (tương thích ngược 1 LoRA); `_add_ipadapter_
nodes` — 1 ảnh, nhiều ảnh (chain `ImageBatch`), áp SAU LoRA, fallback khi ComfyUI 400,
raise khi fallback cũng lỗi. Full `pytest`: **368 passed** (352 + 16 mới). `tsc --noEmit`:
0 lỗi.

## 76. Migrate LocalAI làm lớp AI local cho LLM+ảnh+video — additive, song song ComfyUI/Ollama (2026-08-25)

### Yêu cầu người dùng

Người dùng đưa `CHANGE_LocalAI_Migration.md` — đề xuất gộp 3 service local rời rạc
(ComfyUI cho ảnh+video, Ollama cho LLM, OmniVoice/Piper cho TTS) thành 1 service duy
nhất: **LocalAI** (github.com/mudler/LocalAI). Lên plan (plan mode) trước khi code:

- **Research code hiện tại** xác nhận: tài liệu change-spec nói 4 file spec (`01_
  architecture.md`, `05_ai_providers.md`, `02_database.md`, `09_sprint_tasks.md`) "đã cập
  nhật theo LocalAI" là SAI — cả 4 vẫn mô tả 100% kiến trúc ComfyUI/Ollama/OmniVoice hiện
  tại, vừa build/verify qua GPU thật tới mục 75 (23/8). Người dùng xác nhận: đây là tài
  liệu **đề xuất**, không phải hiện trạng.
- **Research tài liệu LocalAI thật** (WebFetch/WebSearch, không suy đoán): multi-LoRA CÓ
  hỗ trợ sẵn (`lora_adapters`/`lora_scales` dạng list trong YAML) + API quản lý model
  runtime (`POST /models/apply`, không cần restart); **IPAdapter KHÔNG được LocalAI hỗ
  trợ/expose** (cộng đồng khuyên dùng thẳng ComfyUI cho nhu cầu đó); video qua `/v1/videos`
  (PR #6777) hỗ trợ `InputReference` (image-to-video) nhưng là tính năng RẤT MỚI, chưa có
  case study rộng.
- 2 vòng `AskUserQuestion`: (1) hỏi rõ IPAdapter (mục 75, Phần C) đã từng chạy thật chưa —
  người dùng xác nhận **CHƯA TỪNG cài `ComfyUI_IPAdapter_plus`/test** → de-risk hẳn việc bỏ
  tính năng này; (2) hỏi phạm vi/khẩu vị rủi ro migrate — người dùng chọn **migrate TOÀN
  BỘ LLM + ảnh + video** sang LocalAI, xoá ComfyUI/Ollama SAU KHI verify thật qua GPU (TTS
  ngoài phạm vi, giữ nguyên Piper/OmniVoice).

### Đã build (đợt ADDITIVE — chưa xoá gì)

**Ảnh** — `backend/app/providers/image_localai.py` mới, `LocalAIImageProvider`
(`provider_name="localai_image"`), `POST /v1/images/generations` (OpenAI-compatible,
response `data: [{b64_json}]` — tái dùng pattern parse như `image_openai.py`). Giữ NGUYÊN
chữ ký `generate()` như `ComfySDXLImageProvider` (drop-in cho `engine.py`) — `loras` đồng
bộ vào 1 "model ảo" (`studioflow-sdxl`) qua `POST /models/apply`, CHỈ gọi khi chữ ký LoRA
(tên+trọng số) thực sự đổi so với lần gọi gần nhất (cache instance), tránh gọi thừa mỗi
shot; `reference_images`/`style_reference_weight` (IPAdapter) — BỎ QUA + log cảnh báo 1
lần, không có đường sang LocalAI; `extra_negative` map vào field `negative_prompt`.

**Video** — `backend/app/providers/video_localai.py` mới, `LocalAIVideoProvider`
(`provider_name="localai_video"`), `POST /v1/videos`. **Rủi ro cao nhất trong toàn bộ
migrate** — response đồng bộ (video có ngay) hay bất đồng bộ (job id, cần poll) CHƯA xác
nhận thật, thiết kế chịu được CẢ 2: nhánh đồng bộ cache bytes theo job_id giả (`sync:...`)
trả ngay ở `poll_generation`; nhánh bất đồng bộ GET `/v1/videos/{job_id}` (ĐOÁN theo quy
ước REST phổ biến, CHƯA verify) tới khi `status` hoàn tất. `input_reference` — ảnh anchor
gửi base64 data URI trong body JSON (khác ComfyUI cần `POST /upload/image` multipart).

**`factory.py`** — đăng ký `"localai_image"`/`"localai_video"` vào `_IMAGE_ADAPTERS`/
`_VIDEO_ADAPTERS` SONG SONG `"local_sdxl"`/`"local_wan"` (KHÔNG xoá).

**`engine.py`** — 5 chỗ hardcode `provider.provider_name == "local_sdxl"`/`"local_wan"`
đổi sang 2 tuple mới `_LOCAL_IMAGE_PROVIDER_NAMES = ("local_sdxl", "localai_image")`/
`_LOCAL_VIDEO_PROVIDER_NAMES = ("local_wan", "localai_video")` — cơ chế ảnh anchor per-
shot cho video (`_try_generate_wan_anchor_image`), chọn biến thể prompt (`for_local_sdxl`),
bọc `gpu_lock`, và cost estimation đều nhận diện ĐÚNG dù đang dùng ComfyUI hay LocalAI.
Xác nhận `try_interrupt_local_gpu_job`/`get_local_gpu_status` KHÔNG cần sửa — đã generic
theo `endpoint_url` của BẤT KỲ provider `local_endpoint` nào, có sẵn try/except best-
effort (LocalAI không có `/interrupt`/`/queue`/`/system_stats` kiểu ComfyUI sẽ tự thoái
hoá thành "unreachable", không lỗi).

**LLM** — KHÔNG cần code provider mới: `LocalOpenAICompatProvider` đã generic (không
hardcode Ollama), chỉ đổi hint ở `ProviderSettings.tsx::LOCAL_CATALOG.llm` (trỏ
`http://127.0.0.1:8080/v1` thay `:11434/v1` để dùng LocalAI thay Ollama).

**Frontend** — `GET /providers/localai/models` (`routers/providers.py`, liệt kê model
ĐÃ ĐĂNG KÝ qua `GET /v1/models`, khác `list_comfyui_models` liệt kê file thô trên đĩa) +
component `LocalAIModelSelect` mới (`ProviderSettings.tsx`, mirror `ComfyModelSelect`) +
2 entry mới trong `LOCAL_CATALOG.image`/`.video` (`localai_image`/`localai_video`, SONG
SONG entry ComfyUI cũ).

**Dọn dẹp 1 phần** (KHÔNG đợi cổng verify — tính năng chưa từng dùng thật, không phụ
thuộc kết quả verify LocalAI): bỏ hẳn mục "Ảnh tham chiếu phong cách — IPAdapter" khỏi
`ChannelDialog.tsx` (upload/xoá/thanh trượt trọng số) + 3 hàm client tương ứng
(`uploadStyleReference`/`deleteStyleReference`/`styleReferenceUrl`) +
`style_reference_paths`/`style_reference_weight` khỏi `api/types.ts`. **CỐ Ý giữ NGUYÊN**
field schema backend (`BrandProfile.style_reference_paths`/`style_reference_weight`) và 3
endpoint CRUD (`routers/channels.py`) — dọn nốt phần backend + `_add_ipadapter_nodes` ở
`image_comfy_sdxl.py` SAU khi xoá hẳn ComfyUI (cổng verify dưới).

### CHƯA làm ở đợt này (chờ cổng verify GPU thật)

`image_comfy_sdxl.py`/`video_comfy_wan.py` KHÔNG xoá, `local_sdxl`/`local_wan` vẫn đăng
ký đầy đủ và hoạt động bình thường (rollback tức thì bằng cách đổi default provider, dù
đã cấu hình LocalAI). 4 file specs CHƯA viết lại theo LocalAI. 2 điểm CHƯA verify được ghi
rõ ngay trong code (không suy đoán cứng mà không đánh dấu): (1) tên field negative-prompt
(`negative_prompt`, quy ước diffusers phổ biến, chưa xác nhận), (2) path/shape API quản
lý model runtime (`/models/apply`) và path poll job video bất đồng bộ
(`/v1/videos/{job_id}`) — đoán theo tài liệu đọc được, CHƯA verify request/response thật.

Cổng verify (từ plan, bắt buộc trước khi xoá ComfyUI/Ollama): người dùng tự cài/chạy
LocalAI, đăng ký model SDXL+LoRA+Wan2.2, đổi default provider llm/image/video sang
LocalAI, verify thật qua GPU: (a) 1 action LLM, (b) 1 shot ảnh có LoRA+cultural lock, (c)
1 shot video dùng ảnh anchor. Cả 3 PASS mới xoá code ComfyUI cũ + viết lại specs.

### Verify

Test mới: `test_image_localai.py` (12 test — đồng bộ LoRA/cache theo chữ ký/re-sync khi
đổi, negative_prompt, bỏ qua reference_images, size theo aspect_ratio, fallback khi
`/models/apply` lỗi, test_connection, `list_localai_models`), `test_video_localai.py` (10
test — nhánh đồng bộ VÀ bất đồng bộ, tải video qua `url`, raise khi job failed,
`input_reference` base64, `negative_prompt`, reject job, `generate()` raise
NotImplementedError, test_connection), `test_render.py` thêm
`test_try_generate_wan_anchor_image_finds_localai_image_provider_too` (unit) +
`test_video_localai_uses_localai_image_anchor_when_configured` (end-to-end qua
`/render/start` thật, xác nhận `localai_video` gọi được với `input_reference` từ ảnh
anchor `localai_image` sinh ra). Full `pytest`: **396 passed** (372 + 24 mới). `tsc
--noEmit`: 0 lỗi.

**Khác MỌI tính năng ComfyUI trong dự án (đều verify qua GPU thật trước khi coi là
xong)**: toàn bộ phần LocalAI ở mục này **CHƯA verify qua GPU thật** — test chỉ xác nhận
code build ĐÚNG request theo tài liệu LocalAI đã đọc, không xác nhận được hành vi LocalAI
thật. Chờ người dùng qua cổng verify ở trên.

## 77. LocalAI — sửa endpoint video đúng thật + thêm ảnh tham chiếu phong cách qua img2img (2026-08-25)

### Yêu cầu người dùng

Đưa bản `CHANGE_LocalAI_Migration.md` đã bổ sung §6 mục 2 — người dùng TỰ research thật
(không phải Claude) xác nhận qua tài liệu LocalAI chính thức: reference image giữ style
CÓ hỗ trợ (img2img `pipeline_type: StableDiffusionImg2ImgPipeline` field `image`, hoặc
Flux Kontext field `ref_images`), image-to-video CÓ hỗ trợ qua endpoint riêng `POST
/video` (KHÔNG `/v1`) nhận `start_image`/`num_frames`/`fps`/`cfg_scale`/`step`. Yêu cầu
đọc + đề xuất tính năng cải tiến + lên kế hoạch triển khai.

Lên plan mode (sửa tiếp file plan cũ của mục 76, không tạo mới): tự research thêm qua
WebFetch/WebSearch để xác nhận CHI TIẾT (docs `localai.io/docs/features/
video-generation/` và `/image-generation/`) — phát hiện quan trọng nhất: **Flux Kontext
KHÔNG PHẢI cloud `fluxapi.ai`** đã tích hợp sẵn (`image_flux_kontext.py`) mà là model MỞ
`flux.1-kontext-dev` (họ Flux ~12B) chạy LOCAL qua backend `stable-diffusion.cpp` —
tốn tải + VRAM riêng, không dùng chung checkpoint SDXL. Hỏi lại người dùng qua
`AskUserQuestion` — chọn **img2img** (rẻ hơn, dùng ngay checkpoint hiện có), Flux Kontext
ngoài phạm vi đợt này.

### Sửa `video_localai.py` — endpoint mục 76 SAI, viết lại toàn bộ

Đợt 76 code theo SUY ĐOÁN (`POST /v1/videos`, field `input_reference`, nhánh job-poll
`GET /v1/videos/{job_id}`) vì lúc đó chưa có tài liệu chính thức. Xác nhận thật qua
`localai.io/docs/features/video-generation/`: endpoint đúng là `POST {base_url}/video`
(không tiền tố `/v1`), field `start_image` (base64/data-URI/URL), `negative_prompt`,
`width`/`height`, `seconds`, `seed`, `response_format` (`"url"`/`"b64_json"`) —
**response ĐỒNG BỘ** (`{created, id, data: [{url}]}` hoặc `[{b64_json}]`), KHÔNG job-poll
như giả định đợt 76. Viết lại `LocalAIVideoProvider` — `start_generation()` gọi thẳng
`/video`, request `response_format: "b64_json"` (giữ fallback đọc `url`), nhận video
NGAY trong response, cache theo job_id giả (`sync:{id}`); `poll_generation()` chỉ đọc
cache trả về ngay — **xoá hẳn** nhánh GET job-status cũ.

### Thêm img2img vào `image_localai.py` — ảnh tham chiếu phong cách (thay IPAdapter cũ)

Đợt 76 nhận `reference_images`/`style_reference_weight` nhưng chỉ log cảnh báo rồi bỏ
qua ("không có đường sang LocalAI" — kết luận SAI, sửa lại đợt này). `generate()` giờ:
có `reference_images` → dùng ảnh ĐẦU TIÊN (img2img LocalAI chỉ nhận 1 ảnh/lần, khác
IPAdapter cũ nhận nhiều), đăng ký RIÊNG 1 model img2img
(`_virtual_model_name(img2img=True)` → `"studioflow-sdxl-img2img"`) qua CÙNG cơ chế
`/models/apply` đã có cho model txt2img (mở rộng `_apply_model()` thêm tham số
`pipeline_type`), cache đồng bộ LoRA đổi từ 1 biến đơn (`_synced_lora_signature`) sang
dict theo tên model (`_synced_lora_signatures`) — txt2img và img2img là 2 model KHÁC
NHAU trong LocalAI, đồng bộ độc lập. Body thêm field `image` (base64) + `strength` —
map từ `style_reference_weight` theo HƯỚNG NGƯỢC (`strength` cao = ít giữ ảnh gốc,
`style_reference_weight` cao = muốn giữ NHIỀU) bằng `strength = clamp(1 -
style_reference_weight, 0.3, 0.85)` — khoảng mượn kinh nghiệm tune thật cho Tier 2
ComfyUI (`image_comfy_sdxl.py::_IMG2IMG_DENOISE=0.7`).

**RỦI RO ĐÃ GHI RÕ, CHƯA LOẠI TRỪ**: img2img seed latent bằng 1 ảnh — CÙNG bản chất/rủi
ro Tier 2 ComfyUI đã TẮT (ảnh tham chiếu nhiều chi tiết đồ hoạ dễ bị copy nguyên khung/
chữ vào ảnh mới). Nếu người dùng gặp lại đúng bug này qua GPU thật, cân nhắc bỏ hẳn tính
năng thay vì cố tune tiếp — đã có tiền lệ. `pipeline_type` cho SDXL
(`StableDiffusionXLImg2ImgPipeline`) là SUY ĐOÁN theo quy ước đặt tên `diffusers` (tài
liệu LocalAI chỉ có ví dụ SD1.5), CHƯA verify tên class chính xác.

### Frontend — làm lại UI ảnh tham chiếu (đơn giản hơn IPAdapter cũ)

Đợt 76 xoá hẳn mục UI + 3 hàm client + 2 field `BrandProfile` type (tưởng dead feature).
Đợt này thêm lại `style_reference_paths`/`style_reference_weight` (`api/types.ts`),
`uploadStyleReference`/`deleteStyleReference`/`styleReferenceUrl` (`client.ts`, endpoint
backend không đổi — chưa từng xoá ở backend). UI ở `ChannelDialog.tsx` **đơn giản hơn**
gallery nhiều ảnh của IPAdapter cũ — **1 ô ảnh duy nhất** (khớp giới hạn thật 1 ảnh của
img2img) — upload ảnh mới tự xoá ảnh cũ trước (đảm bảo tối đa 1 phần tử, không đổi API
backend vẫn nhận list) + 1 thanh trượt "Mức giữ phong cách ảnh tham chiếu".

### Verify

Viết lại `test_video_localai.py` (11 test — bỏ hết test nhánh job-poll cũ, test mới cho
`/video` đồng bộ: đúng path không `/v1`, response đồng bộ không cần poll, đúng field
body, `start_image` base64, size theo aspect_ratio, fallback đọc `url`, reject job,
response không nhận diện được, `generate()` raise, test_connection). Thêm 4 test img2img
vào `test_image_localai.py` (dùng model img2img riêng + đúng `pipeline_type`, chỉ dùng
ảnh đầu tiên khi có nhiều, `strength` map đúng hướng ngược `style_reference_weight`,
cache đồng bộ độc lập giữa txt2img/img2img) — 12→16 test. Sửa
`test_video_localai_uses_localai_image_anchor_when_configured` (`test_render.py`) theo
endpoint/field mới. Full `pytest`: **401 passed** (396 + 5 mới ròng). `tsc --noEmit`: 0
lỗi.

Vẫn CHƯA verify qua GPU thật (cùng lý do mục 76) — endpoint/field đã CONFIRM qua tài
liệu chính thức (không còn thuần suy đoán), nhưng hành vi LocalAI thật + chất lượng
img2img/video vẫn chờ cổng verify của người dùng.

## 6. File specs đã cập nhật

`01_architecture.md`, `02_database.md`, `03_api.md`, `04_data_schemas.md`, `05_ai_providers.md`, `06_uiux.md`, `07_prompt_templates.md`, `09_sprint_tasks.md` — mỗi chỗ lệch đánh dấu bằng blockquote `> **Đã build...`, giữ nguyên nội dung gốc bên cạnh để thấy được ý định ban đầu vs. thực tế.

## 78. Bỏ LLM khỏi "Tạo lại Visual/Audio" — khôi phục nguyên si từ script gốc thay vì diễn giải lại qua AI (2026-08-25)

### Yêu cầu người dùng

"Khi Tạo lại visual/audio tại sao lại cần LLM? Lấy nguyên si mô tả đang điền trong phần
này chứ nhỉ? nếu ko có mô tả thì báo lỗi hoặc skip qua shot đó." + xác nhận Hook Strength
không cần nữa (không có UI, luồng đã bỏ) + yêu cầu chuyển hẳn sang provider LLM API ngoài,
chọn model tiết kiệm nhất.

### Điều tra trước khi sửa (không giả định)

Đọc `routers/pipeline.py` xác nhận đúng như người dùng nói: `shot.visual_fx`/
`shot.audio_sfx` được khởi tạo TRỰC TIẾP từ `beat.visual`/`beat.direction` (2 cột script
gốc) lúc tạo shot ở `/visual/generate` — KHÔNG qua LLM. "Tạo lại Visual/Audio"
(`regenerate-shot-visual`/`-audio`) trước đó gọi LLM chỉ để DIỄN GIẢI LẠI đúng 2 field này
thành 1 câu khác — không cộng thêm thông tin, tốn 1 lượt gọi Provider AI vô ích. Đồng thời
kiểm `hook_spoken`: `pack.script.hook.spoken` khởi tạo `""` lúc import script, KHÔNG có
đường ghi nào khác trong codebase — nhánh LLM Hook Strength ở `run_guardrail_check` (gate
`if hook_spoken:`) xác nhận đúng là dead code không thể chạm tới trong luồng M1 hiện tại
(hàm vẫn còn dùng cho cảnh báo anchor-gap/từ cấm không-LLM, không xoá cả hàm).

### Sửa

- `app/pipeline/generation.py` — viết lại toàn bộ, bỏ hết hàm LLM cũ, chỉ còn
  `restore_shot_visual_fx(beat)`/`restore_shot_audio_sfx(beat)`: trả nguyên si
  `beat.visual`/`beat.direction`, raise `ValueError` nếu rỗng.
- `app/pipeline/fallback_content.py` — xoá hẳn (không còn nơi nào import).
- `app/routers/pipeline.py` — 2 endpoint đơn shot (`regenerate-visual`/`regenerate-audio`)
  gọi hàm restore, bắt `ValueError` → `HTTPException(400, ...)`. 2 endpoint bulk
  (`generate-all-visual`/`generate-all-tts`) gọi restore trong vòng lặp, `except
  ValueError: continue` — bỏ qua đúng 1 shot thiếu mô tả, không chặn cả batch. Bỏ import
  `get_llm` (không còn dùng ở file này).
- `PROMPT_SEED` (`seed.py`, template `visual_image`/`visual_video`/`visual_tts`) và UI
  nhãn tương ứng ở `PromptTemplatesSettings.tsx` giờ hết tác dụng thật (module
  `generation.py` không còn đọc) — CHƯA xoá, để quyết định dọn tiếp sau (hạ tầng CRUD
  template dùng chung cho task khác, không phải code chết toàn bộ).

### Verify

`test_pipeline_flow.py`: siết assertion happy-path (`regenerate-visual`/`-audio` phải trả
đúng lại giá trị GỐC của script, không phải câu LLM diễn giải), thêm
`test_regenerate_visual_errors_when_script_beat_has_no_visual_description` (400 khi
script gốc rỗng) và `test_generate_all_visual_skips_shots_with_no_script_description_
instead_of_erroring` (bulk bỏ qua, không lỗi cả batch). `test_settings.py::
test_budget_detail_groups_after_pipeline_usage` phải viết lại nguồn usage LLM (test cũ
dùng `regenerate-visual` để sinh 1 lượt usage — nay endpoint đó không còn gọi LLM) —
chuyển sang set tay `hook.spoken` rồi gọi `guardrail/check` thật, monkeypatch
`MockLLMProvider.complete` trả JSON hợp lệ (Mock mặc định không bao giờ trả JSON, xác
nhận qua `test_guardrail.py::test_score_hook_strength_mock_provider_uses_fallback` — đúng
hành vi sẵn có, không phải bug). Full `pytest`: **403 passed**. `tsc --noEmit`: 0 lỗi
(không có thay đổi frontend ở đợt này).

### Chưa làm — chuyển sang LLM API ngoài

Yêu cầu thứ 3 của người dùng ("chuyển hẳn sang provider API LLM ngoài, lựa chọn model
tiết kiệm nhất") KHÔNG thể tự làm trọn vẹn — cần API key thật của người dùng, không có
sẵn. Sau đợt sửa này, LLM chỉ còn dùng ở ĐÚNG 1 chỗ thật trong toàn app: nhánh Hook
Strength của `guardrail/check` (hiện dead code vì `hook_spoken` luôn rỗng) + 1 số việc
nhẹ khác đã khảo sát trước đó trong phiên (research, không code) — nghĩa là cấu hình LLM
giờ gần như KHÔNG BẮT BUỘC nữa cho luồng M1 chính. Khuyến nghị đã đưa trước đó: nếu vẫn
muốn cấu hình, chọn tier rẻ/nhanh nhất đã tích hợp sẵn (Claude Haiku 4.5 hoặc Gemini 2.5
Flash-Lite) qua Cài đặt → Provider AI — người dùng tự nhập API key.

## 79. Bug thật (tiếp mục 76): CFR-normalize trước ghép intro phải áp dụng MỌI khi có intro, không chỉ nhánh có transition (2026-08-26)

### Yêu cầu người dùng

Project short-form thật "Đính chính lầm tưởng — vụ án không phải chuyện tình cảm cung
đình đơn giản mà là một cuộc thanh trừng chính trị" (`prj_1787673042428`) bị mất shot
cuối sau khi ghép video — đúng LỚP bug đã sửa ở mục 76, nhưng project này KHÔNG dùng
transition nào (mọi ranh giới "cut" mặc định), chỉ có intro riêng.

### Điều tra + tái hiện thật (không suy đoán)

Đọc `render.json`/`pack.json` thật của project: 4 shot ảnh + giọng đọc (S3-01..S3-04),
intro video riêng (`kind="video"`, `transition_to_next="cut"`), overlay hiệu ứng. `final.mp4`
đo qua ffprobe dài **40.3s**; tính tay theo lý thuyết (intro 10.005s + tổng narration
32.68s, không transition nên không có padding/overlap) phải ra **~42.685s** — hụt đúng
2.36s = ĐÚNG BẰNG độ dài giọng đọc shot S3-04. Trích 1 frame ở giây 41.5s của bản ĐÃ SỬA
xác nhận bằng mắt đây chính là ảnh S3-04 thật (không phải shot khác/đen), chứng minh
trước khi sửa nó bị drop hoàn toàn.

Tái hiện trực tiếp trên CHÍNH project này (backup rồi tạm set `transition_to_next=None`
cho mọi shot khớp đúng trạng thái lúc lỗi, gọi thẳng `assemble_video()`): ra đúng 40.3s
— xác nhận 100% đúng bug, không phải nghi ngờ.

Nguyên nhân gốc: bản fix mục 76 (2026-08-23) CHỈ chuẩn hoá `body_path` về CFR sạch
(`-vsync cfr` + `aresample=async=1:first_pts=0`) khi `has_transitions=True` (nhánh
`_xfade_chain`) — kết luận lúc đó "nhánh KHÔNG-transition dùng concat DEMUXER `-c copy`,
cùng nguồn `_build_segment` nên không gặp lệch" là **SAI**: concat demuxer giữ NGUYÊN
timestamp/timebase gốc từng segment (không viết lại liền mạch như concat filter), vẫn có
thể mang timebase không đều tuỳ input gốc. Khi `_concat_intro_and_body` (filter `concat`)
ghép `body_path` này với `intro_path` (CFR sạch), ffmpeg vẫn gặp DTS không tăng đơn điệu
và tự ý drop frame video cuối — HỆT bug mục 76, chỉ khác đường vào.

### Sửa

`app/render/assembly.py` — chuyển khối CFR-normalize (biến `cfr_body_path`) ra khỏi
nhánh lồng trong `else:` (has_transitions), đặt NGAY ĐẦU khối `if intro_source:` chung
(áp dụng cho CẢ 2 nhánh has_transitions True/False, miễn có intro). Test lại chính kịch
bản gây lỗi (all-"cut" + intro) với code đã sửa: ra **42.73s** (khớp lý thuyết, sai số
làm tròn bình thường) — hết drop. Regenerate lại `final.mp4` THẬT cho project của người
dùng (44.6s, đủ 4 shot, verify bằng ffprobe + trích frame S3-04 tại giây 41.5s).

### Verify

Thêm `test_export_pack_bundle_...` không liên quan — riêng cho bug này: thêm
`test_assemble_with_intro_and_no_transitions_does_not_drop_last_shot` (`test_render.py`)
— cùng cấu trúc test mục 76 nhưng KHÔNG patch transition nào (giữ mặc định "cut"), verify
`result_duration` không hụt hẳn so với lý thuyết. Full `pytest`: **407 passed** (404 + 2
test mới mục này + đã tính cả 1 test export-pack mục 80... — xem tổng cuối mục 80).

## 80. Tái cấu trúc Output Center — bỏ "Output A", "Output B" hiện thẳng không qua entry point, thêm "Xuất Pack" (2026-08-26)

### Yêu cầu người dùng

"Bỏ output A. Đưa nội dung tính năng outputB ra ngoài, ko cần bấm 'Mở render studio' làm
entry point nữa, Bổ sung nút Xuất pack — khi đó sẽ export các nội dung gói video ra
folder trên máy local (user chọn location) bao gồm: file transcript srt chuẩn, bộ assets
(ảnh,video) được đặt tên theo ID phù hợp, file voice mp3 đã ghép full, video rendered
(nếu có)."

### Sửa — Output Center (frontend)

`frontend/src/screens/steps/OutputCenter.tsx` — viết lại: bỏ hẳn card "Output A" (export
markdown/JSON spec-only qua `POST /projects/{id}/export`, ít dùng thực tế, `pack.json`
JSON đã có sẵn trên đĩa cho ai cần đọc trực tiếp) — endpoint backend + test liên quan
GIỮ NGUYÊN (không có caller frontend nào khác, không gây hại khi để đó, chỉ gỡ 3 hàm
client thừa `exportPack`/`downloadUrl`/`downloadExportFile` ở `api/client.ts`). Bỏ state
`renderOpen` + nút "Mở Render Studio" — `RenderStudio` giờ render THẲNG trong
`OutputCenter` (không còn prop `onClose`, bỏ luôn nút "← Quay lại" ở header của nó — xem
`RenderStudio.tsx`).

### Thêm — "Xuất Pack" (backend + Electron + frontend)

**Backend** (`app/render/pack_export.py`, mới): `build_srt_text()` — sinh transcript SRT
chuẩn từ `pack.script.body[].audio` (VO Content), timing dùng ĐÚNG `_shot_base_duration`
(tái dùng từ `assembly.py` — ưu tiên độ dài giọng đọc thật, khớp mốc thời gian với
`narration_full.mp3` xuất CÙNG bundle, để SRT tra đúng track audio đó). `export_pack_bundle()`
— orchestrator: (1) SRT, (2) copy asset ảnh/video từng shot `ready` vào `assets/{shot_id}{ext}`
(tên đã sẵn đúng chuẩn từ lúc sinh, không cần đổi tên), (3) tái dùng THẲNG
`engine.build_narration_download()` có sẵn (từng chỉ dùng cho nút tải riêng ở Script
Studio) rồi copy ra `narration_full.mp3`, (4) copy `final_video_path` (nếu
`assembly_status=="done"` và file tồn tại) ra `video_final.{ext}`. Từng phần lỗi riêng
(thiếu asset/narration chưa sinh xong hết/chưa ghép video) **KHÔNG chặn cả export** — ghi
vào `skipped` kèm lý do, đúng nguyên tắc "lỗi 1 phần không chặn cả batch" đã dùng ở
`generate_all_visual`. Endpoint mới `POST /projects/{id}/export/pack-bundle` (`render.py`,
body `{dest_dir}`) — ghi THẲNG ra filesystem tại `dest_dir` (backend chạy local ngay trên
máy người dùng, không cần stream qua HTTP).

**Electron** — cần dialog chọn thư mục NATIVE (React chạy trong Electron không có File
System Access API kiểu trình duyệt để chọn absolute path ghi trực tiếp bằng backend). Thêm
`ipcMain.handle("choose-folder", ...)` (`electron/src/main.ts`, `dialog.showOpenDialog`
với `openDirectory`+`createDirectory`) + cầu nối `window.studioflowNative.chooseFolder()`
(`electron/src/preload.ts`, cùng pattern optional-global đã có của `STUDIOFLOW_API_BASE`).

**Frontend** — `PackExportCard` mới trong `OutputCenter.tsx`: nút "Chọn thư mục..." gọi
`window.studioflowNative.chooseFolder()` khi có (Electron); fallback ô nhập đường dẫn tay
khi chạy dev server thuần trình duyệt (`window.studioflowNative` không tồn tại — không có
IPC). Nút "Xuất Pack" gọi `api.exportPackBundle()`, hiển thị danh sách `included`
(✓, xanh) + `skipped` (⊘, kèm lý do) sau khi xong.

### Verify

Backend: 3 test mới trong `test_render.py`
(`test_export_pack_bundle_writes_srt_assets_and_narration_but_skips_missing_video`,
`test_export_pack_bundle_includes_final_video_after_assemble`,
`test_export_pack_bundle_requires_dest_dir`) — verify thật bằng ffmpeg/ffprobe (SRT chứa
đúng text từng block, asset đặt tên đúng shot_id, narration mp3 ghép đúng độ dài, video
xuất hiện/vắng mặt đúng theo trạng thái ghép). Full `pytest`: **407 passed** (bao gồm cả 2
test mục 79). Xác nhận THÊM bằng HTTP call thật (không chỉ pytest fixture DB) tới backend
đang chạy trong Electron thật, nhắm đúng project `prj_1787673042428` (project vừa sửa bug
mục 79) — trả về đủ `["transcript.srt","assets/","narration_full.mp3","video_final.mp4"]`,
`skipped: []`; đọc lại SRT thấy đúng nội dung kịch bản thật, `ffprobe` xác nhận
`narration_full.mp3` = 32.68s (khớp tổng narration), `video_final.mp4` = 44.6s (khớp bản
đã sửa bug mục 79, đủ 4 shot) — xoá thư mục test sau khi verify xong.

Frontend: `tsc --noEmit` sạch cả `frontend/` lẫn `electron/`. KHÔNG chạy được click-through
tự động qua UI thật (môi trường này không có Playwright/trình duyệt cài sẵn, cài mới tốn
thời gian tải browser binary) — đã chụp màn hình xác nhận app khởi động lại không lỗi sau
khi đổi `main.ts`/`preload.ts`, nhưng CHƯA tự bấm thử nút "Chọn thư mục..."/"Xuất Pack"
qua chuột thật. Khuyến nghị người dùng tự bấm thử 1 lượt ở Output Center, đặc biệt dialog
chọn thư mục native (bản chất mở 1 dialog OS ngoài DOM, dù có Playwright cũng khó tự động
hoá đáng tin cậy hơn người dùng tự bấm).

## 81. Bug thật: giọng đọc bị cắt cụt khi shot video ngắn hơn chính giọng đọc của nó — đổi loop sang đóng băng khung hình cuối (2026-08-26)

### Yêu cầu người dùng

"Khi shot đang là video nhưng duration ngắn hơn độ dài của giọng đọc, giọng đọc shot đó
bị cắt để chuyển sang shot tiếp theo luôn. Hãy fix lại để ưu tiên việc play hết giọng đọc
của shot đó rồi mới chuyển cảnh. Có thể làm theo hướng khi video play hết thì dừng lại ở
frame cuối, giữ ở đó đến khi đọc xong mới chuyển cảnh."

### Điều tra (không suy đoán)

Đọc lại `_reflow_video_durations` (mục 45, 2026-08-17): vòng lặp này LUÔN co
`durations[i]` về ĐÚNG độ dài video thật (`actual`) mỗi khi lệch với `duration` đang gán
— kể cả khi `duration` đang gán DÀI HƠN `actual` CHÍNH VÌ đó là độ dài giọng đọc CỦA
SHOT ĐÓ (`_shot_base_duration`, Pass 1, ưu tiên giọng đọc thật làm `duration` gốc). Co
xuống `actual` (video thật, ngắn) làm `_build_segment` sau đó cắt narration audio theo
đúng `-t duration` méo này — mất phần cuối lời thoại. Đây là tương tác phụ không lường
trước giữa 2 tính năng: mục 43 (loop video ngắn để lấp `duration`, bảo vệ audio) và mục
45 (reflow — cố tình "tắt" loop bằng cách co `duration` xuống bằng `actual`, VÌ MỘT LÝ DO
KHÁC hẳn: video upload/AI lệch so với timestamp kịch bản, không phải vì giọng đọc).

### Sửa

`app/render/assembly.py`:
1. **`_narration_floor(status)`** (mới) — trả `narration_duration_sec` nếu shot có giọng
   đọc `ready`, else `0.0`.
2. **`_reflow_video_durations`** — `target = max(actual, _narration_floor(status))` thay
   vì luôn `= actual`; áp dụng CÙNG sàn khi shot LÁNG GIỀNG bị vay bớt (`donor_floor`) để
   láng giềng cũng không bị co xuống dưới giọng đọc của chính nó. Khi giọng đọc dài hơn
   video thật, `target == durations[i]` sẵn (vì đã set y hệt từ Pass 1) → `diff≈0` → bỏ
   qua hẳn, không co/vay gì.
3. **`_build_segment`** — bỏ hẳn `-stream_loop -1` (lặp lại TỪ ĐẦU — nhìn "giật", user
   đánh giá là "nhìn giả") cho input video, thay bằng filter `tpad=stop_mode=clone:
   stop_duration={duration}` (nhân bản khung hình CUỐI, đệm dư — phần dư luôn bị `-t
   duration` cắt bớt nên không cần biết trước độ dài thật để tính đúng số giây đệm). Vô
   hại khi video DÀI hơn `duration` (không bao giờ chạm tới phần đệm). Sửa CÓ ĐIỀU KIỆN
   theo `is_video` TRỰC TIẾP (không theo `motion_filter` — ảnh tĩnh `camera_motion=
   "none"` cũng cho `motion_filter is None`, dễ lẫn nhánh nếu chỉ if/else theo biến đó).

### Verify

Test thật bằng ffmpeg (không suy đoán): dựng video test 2s có nội dung ĐỔI DẦN theo thời
gian (`testsrc`), ép segment 5s, trích khung ở giây 1.9 (gần cuối clip gốc) và giây 4.5
(vùng đệm) — so bằng SSIM (không so byte thô, đã xác nhận byte thô lệch vài vị trí do
nhiễu nén H.264 dù nội dung giống hệt) — SSIM đo được đúng **1.0** (đóng băng đúng, không
lặp lại từ đầu). Thêm test unit cho `_reflow_video_durations` (shot video 2s + giọng đọc
6s → `durations[0]` giữ nguyên 6s, không co) và test END-TO-END qua `assemble_video()`
thật (project thật CSV import → visual/generate → gán video 2s + narration 6s → assemble
→ video ra ≥5.7s, không còn cắt cụt còn ~2s). Full `pytest`: **409 passed**.

## 82. Bug thật phát hiện khi bật GPU (NVENC): probe cũ dùng frame quá nhỏ, NVENC từ chối — mặc định bật sẵn checkbox GPU (2026-08-26)

### Bối cảnh

Người dùng hỏi cách bật GPU cho render (đang chạy CPU) — driver cũ (576.88) thiếu API
NVENC 13.1 (yêu cầu ≥610.00). Người dùng tự update driver lên **610.88**, báo lại "đã
update driver xong" + yêu cầu mặc định tick sẵn checkbox GPU.

### Bug thật phát hiện khi verify lại (không suy đoán)

Sau update driver, test NVENC thật với frame `64x64` (đúng size `probe_gpu_encoder` cũ
dùng) VẪN lỗi — nhưng lỗi KHÁC hẳn: `InitializeEncoder failed: invalid param (8): Frame
Dimension less than the minimum supported value.` — không còn liên quan driver, mà NVENC
từ chối kích thước frame quá nhỏ. Xác nhận bằng ffmpeg thật: `128x128` vẫn FAIL, `145x49`/
`256x144` PASS; encode THẬT ở độ phân giải thật (1280x720) chạy tốt bình thường. Nếu
không sửa, `probe_gpu_encoder` sẽ mãi báo "không dùng được" SAI dù GPU đã hoạt động tốt —
chặn đúng yêu cầu "mặc định bật" của người dùng ngay từ gốc.

### Sửa

- `app/render/assembly.py::probe_gpu_encoder` — đổi frame test từ `64x64` sang `256x144`
  (16:9 thu nhỏ, an toàn trên ngưỡng tối thiểu đã đo thật).
- `frontend/src/screens/steps/RenderStudio.tsx` — thêm `useEffect` theo dõi `gpuEncode`:
  khi `gpuEncode.available===true` (VÀ codec hiện tại không phải `vp9` — NVENC không hỗ
  trợ vp9), tự set `config.use_gpu=true` MỘT LẦN lúc probe xong — không đè lên lựa chọn
  người dùng tự tắt sau đó (effect không phụ thuộc lại chính `config` trong deps).

### Verify

`probe_gpu_encoder(shutil.which("ffmpeg"))` gọi trực tiếp trên máy thật (driver 610.88):
trả `(True, '')` — xác nhận đúng GPU khả dụng. Full `pytest`: **409 passed** (bao gồm 8
test GPU/reflow/freeze mục 81 hiện có, không cần test riêng cho kích thước frame vì
`test_probe_gpu_encoder_real_returns_consistent_cached_result` không hardcode size, tự
verify qua kết quả thật của máy chạy CI). `tsc --noEmit` sạch.

## 83. Xác nhận thật: đệm lặng tại ranh giới transition (mục 57) đã tự hoạt động đúng cho shot video bị đóng băng (mục 81) — không cần sửa code, chỉ thêm test khoá lại (2026-08-26)

### Yêu cầu người dùng

"việc xử lý delay khi chuyển cảnh để tránh bị cắt mất phần giọng đọc cũng cần áp dụng cho
trường hợp freeze shot là video" — lo ngại tính năng đệm lặng tại ranh giới transition
(`narration_lead_in_sec`/`narration_lead_out_sec`, mục 57) chưa tính tới shot video vừa
được đổi sang đóng băng khung hình cuối (mục 81, cùng ngày).

### Điều tra bằng ffmpeg thật (không kết luận từ đọc code suông)

Đọc lại luồng tính toán trong `assemble_video`: `_shot_base_duration` (ưu tiên giọng đọc)
→ `_reflow_video_durations` (mục 81, có sàn narration) → cộng `lead_in`/`lead_out` (mục
57) → `_build_segment` (tpad đóng băng phủ ĐỦ `duration` đã cộng đệm). Về logic, cơ chế
đệm lặng vốn KHÔNG phân biệt shot là ảnh hay video (chỉ dựa `has_narration` +
`transition_to_next`) — nên NÊN đã tự đúng, nhưng quyết định KHÔNG suy đoán, verify thật.

Dựng 2 test THẬT qua `assemble_video()` (không chỉ unit `_reflow_video_durations`):
1. Shot A = video 2s + giọng đọc 6s (sine 440Hz), transition "fade" sang shot B (ảnh).
2. Chiều ngược lại: shot A (ảnh) transition "fade" sang shot B = video 2s + giọng đọc 6s.

Dùng `ffmpeg -af silencedetect` (không đoán bằng mắt/tai) đo TOÀN BỘ audio video đã ghép:
cả 2 chiều chỉ phát hiện ĐÚNG 1 khoảng lặng — đúng vùng đệm transition (~0.65s, khớp
`_XFADE_DURATION_SEC=0.6` + sai số) — KHÔNG có khoảng lặng nào khác lọt vào giữa 6s giọng
đọc thật (sine tone phát liên tục không đứt quãng). Xác nhận: đệm lặng transition ĐÃ hoạt
động đúng cho shot video bị đóng băng, ở CẢ 2 hướng (lead-in lẫn lead-out) — không có bug,
không cần sửa `assembly.py`.

### Việc đã làm

Không sửa code (không có gì để sửa) — thêm CỐ ĐỊNH 2 test thật vào `test_render.py`
(`test_freeze_video_shot_lead_out_before_transition_does_not_truncate_narration`,
`test_freeze_video_shot_lead_in_after_transition_does_not_truncate_narration`) dùng
`silencedetect` để khoá lại hành vi đúng này — đây là đúng LOẠI tương tác 2 tính năng dễ
bị 1 refactor sau này vô tình phá vỡ mà không ai nhận ra ngay (2 tính năng viết ở 2 thời
điểm khác nhau, không có test chung nào phủ tổ hợp trước đây). Full `pytest`: **411
passed**.

## 84. Cải thiện tốc độ ghép video — build segment SONG SONG; 2 hướng khác đã thử nhưng phải bỏ (2026-08-26)

### Yêu cầu người dùng

"việc render bằng gpu vẫn có vẻ khá chậm, đặc biệt là bước ghép toàn bộ các cảnh, có cách
nào cải thiện ko"

### Đo đạc thật trước khi sửa (không đoán)

Viết script profiling tạm (monkeypatch `subprocess.run` để in thời gian từng lệnh ffmpeg)
chạy `assemble_video()` thật trên project 4 shot có đủ intro+overlay+transition
(`prj_1787673042428`). Xác nhận GPU (NVENC) đã hoạt động đúng và có lợi rõ: **22.85s
(GPU) so với 45.18s (CPU)** cho CÙNG project — không phải GPU "không chạy", nhưng vẫn có
dư địa cải thiện thêm.

### Hướng ĐÃ THỬ nhưng PHẢI HOÀN TÁC — gộp bước CFR-normalize vào `_concat_intro_and_body`

Phát hiện qua profiling: `body_cfr.{ext}` (mục 79, decode+re-encode NGUYÊN thân video để
tránh bug mất shot cuối) và `_concat_intro_and_body` (decode+re-encode LẠI, ghép intro)
chạy NGAY SAU NHAU trên CÙNG nội dung — tưởng có thể gộp làm 1 lệnh (chèn filter
`fps={_OUTPUT_FPS}` + `aresample=async=1:first_pts=0` thẳng vào filter graph `concat`,
tránh phải ghi/đọc lại file trung gian). **Verify thật lại đúng project gây bug gốc phát
hiện bản gộp làm bug "mất shot cuối" (mục 76/79) QUAY LẠI** — ra đúng ~40.3s (hụt shot
cuối) thay vì ~42.7s đúng. Đã HOÀN TÁC hoàn toàn, giữ nguyên bản 2-lệnh riêng của mục 79
— không đánh đổi ĐÚNG ĐẮN lấy tốc độ. (Nghi ngờ nguyên nhân: file trung gian ghi thật ra
đĩa rồi đọc lại có timestamp "chốt cứng" qua 1 lượt mux/demux hoàn chỉnh mà filter đơn
thuần trong CÙNG 1 graph không tái tạo được — chưa điều tra sâu hơn, không cần thiết vì
đã có đủ bằng chứng loại bỏ phương án.)

### Hướng ĐÃ THỬ nhưng KHÔNG đáng đánh đổi — NVENC preset nhanh hơn (`p1`/`p3`)

Test preset `p1` (nhanh nhất): SSIM so với mặc định (`p4`) = 0.989 (rất gần, có thể chấp
nhận được) NHƯNG file `final.mp4` (project test) ra **~53.6MB** so với **~14-19MB** mặc
định — gần **GẤP 3-4 LẦN** cho tốc độ tổng thể nhanh hơn ~20%. `p3` ("fast") không khá
hơn nhiều (~50MB, nhanh hơn ~17%). Phát hiện phụ (không phải bug, đặc tính vốn có của
NVENC): NGAY CẢ preset mặc định, GPU (NVENC) ra file LỚN HƠN ~2× so với CPU (libx264) ở
CÙNG số CQ/CRF=23 (verify thật: GPU ~40MB vs CPU ~18.76MB, cùng project/cấu hình) — đánh
đổi tốc độ-lấy-dung lượng vốn đã có sẵn khi bật GPU, KHÔNG đáng khuếch đại thêm bằng
preset nhanh hơn. Không áp dụng thay đổi preset.

### Hướng ĐÃ ÁP DỤNG — build segment (Pass 2, `assemble_video`) SONG SONG

Mỗi shot build ra `segment_{i}.{ext}` HOÀN TOÀN ĐỘC LẬP (không đọc/ghi chung gì với shot
khác) — trước đây chạy TUẦN TỰ dù không có lý do kỹ thuật bắt buộc. Đổi sang
`ThreadPoolExecutor` (`_SEGMENT_BUILD_WORKERS = min(4, os.cpu_count() or 4)` — 4 mặc
định, tự hạ trên máy ít core hơn). Verify AN TOÀN trước khi áp dụng: 4 lệnh `h264_nvenc`
chạy đồng thời trên máy dev (RTX 5060 Ti) không bị driver từ chối (không phải mọi GPU
GeForce đều giới hạn số phiên NVENC đồng thời — máy này không giới hạn), CPU (libx264, tự
đa luồng nội bộ) cũng không bị "oversubscribe" nghiêm trọng trên máy 20 core. Đo tốc độ
riêng: 4 lệnh GPU đồng thời nhanh hơn ~26% so với tuần tự (2.65s→1.96s); CPU đồng thời
nhanh hơn ~15% (5.14s→4.38s).

`seg_paths`/`assembly_progress` (2 trạng thái CHUNG cần đồng bộ giữa luồng) — dùng
`concurrent.futures.as_completed` + khoá (`threading.Lock`) quanh việc cập nhật tiến độ +
`save_render_state`; `seg_paths` build lại theo ĐÚNG thứ tự index (không theo thứ tự hoàn
thành) trước khi dùng ở các bước sau — giữ nguyên hành vi downstream. Lỗi ở 1 luồng vẫn
dừng cả assembly (giữ hành vi cũ) — `future.result()` re-raise ngay ở luồng chính.

### Verify

Re-run lại ĐÚNG kịch bản bug gốc (mục 79, transition "cut" toàn bộ + intro) SAU KHI đã
song song hoá — vẫn ra đúng ~42.7s (không hụt shot cuối), xác nhận song song hoá không
đụng gì tới logic timing/CFR. Full `pytest`: **411 passed** (103/103 test_render.py). Đo
lại tổng thời gian pipeline (project 4 shot, GPU): **22.85s → 16.51s (~28% nhanh hơn)** —
mức cải thiện sẽ RÕ RỆT HƠN cho project long-form thật nhiều shot hơn (4 worker xử lý
theo từng đợt 4 — càng nhiều shot, tỉ trọng thời gian tiết kiệm được ở Pass 2 càng lớn so
với các bước hậu kỳ cố định 1 lần như overlay/bg-music).

## 85. Channel Asset Vault + mở rộng Render Engine (CHANGE_Semantic_BRoll_Asset_Vault.md) — build đầy đủ Phase A+B+C (2026-08-26)

### Yêu cầu người dùng

Đưa `CHANGE_Semantic_BRoll_Asset_Vault.md` — đề xuất kho tư liệu video theo từng kênh
(user tự import footage, hệ thống cắt cảnh + gắn nhãn ngữ nghĩa + gợi ý khớp vào shot,
ưu tiên trước AI video) + mở rộng khả năng hậu kỳ (color grade, grain, loudness chuẩn,
ducking). Yêu cầu: "điều chỉnh lại plan nếu... chưa phù hợp với code base hiện tại...
tuyệt đối không build duplicate flow" + "triển khai toàn bộ luôn các phase rồi test 1
thể" — không tách giai đoạn, build hết Phase A/B/C trong 1 lượt.

### Đối chiếu spec ↔ thực tế TRƯỚC khi build (đầy đủ ở kế hoạch `partitioned-sauteeing-
pillow.md`, tóm tắt các điểm sai/lệch đã sửa)

1. **`shots[].motion_type` KHÔNG tồn tại** — spec khẳng định "đã có sẵn" từ 1 file
   (`StudioFlow_Video_Improvement_Plan.md`) không có trong repo. Thật ra đề xuất này ĐÃ
   bị bác bỏ trước đó (`specs/05_ai_providers.md` dòng ~618) — cơ chế tương đương đã có
   sẵn: `visual_type` + `camera_motion`. KHÔNG thêm field mới.
2. **`commercial_use_allowed` KHÔNG tồn tại** ở bất kỳ đâu — spec viện dẫn 2 lần như
   khuôn mẫu có sẵn, thực ra đã bị bác bỏ ở 1 lượt lên plan trước (mục 76).
3. **Phase C ("Render Engine mới") trùng lặp lớn với `assembly.py`** — Ken Burns,
   transition, bg music mix, overlay, GPU/CPU fallback, concat ĐỀU đã có (80+ mục sửa
   lỗi thật, 411 test). Quyết định (người dùng xác nhận): MỞ RỘNG `assembly.py`, KHÔNG
   viết engine mới — chỉ code phần thật sự thiếu (color grade theo kênh, grain, loudness
   chuẩn, ducking, blur-fill).
4. **VLM vision qua LocalAI dùng CHUNG `/v1/chat/completions`** với LLM thường (xác nhận
   qua tài liệu chính thức) — tách task "vision" riêng thay vì sửa `LLMProvider` hiện có.
5. **GPU máy dev đã xác nhận CHẬT VRAM** (OmniVoice giữ ~9.9GB) — chọn Moondream
   (~2-4GB) làm VLM mặc định thay Qwen2.5-VL 7B (~12GB) spec đề xuất.
6. **`CreativeAsset` (Thư viện, mục 53) KHÔNG trùng Asset Vault** — đã kiểm tra kỹ:
   `CreativeAsset` dùng lại NGUYÊN VẸN, đứng ngoài mọi kênh; Asset Vault là NGUYÊN LIỆU
   THÔ bị cắt thành nhiều clip con, per-channel, có metadata phong phú (caption/tags/
   rights/vector) — giữ 2 bảng tách biệt, KHÔNG gộp.

### Dependencies mới (cài + verify sạch trước khi code, không đoán API)

`chromadb==1.5.9`, `scenedetect[opencv]==0.7.1`, `yt-dlp==2026.8.19` — cài thử, xác nhận
`pydantic==2.9.2`/`fastapi==0.115.0` đã ghim KHÔNG bị nâng version, `import app.main`
sạch cùng lúc với 3 lib mới. Verify API thật bằng tay TRƯỚC khi viết code (không suy
đoán): `scenedetect.AdaptiveDetector` phát hiện đúng 2 scene trên video test 2 màu tách
biệt (mốc 3.0s chính xác); `chromadb.PersistentClient` add/query cosine — `distance`
trả về, KHÔNG phải similarity (`similarity = 1 - distance`, verify bằng số đo thật);
`yt_dlp.YoutubeDL` có `download()`. `-ss` TRƯỚC `-i` + `-t <duration>` SAU `-i` (không
phải `-to`) để cắt clip đúng mốc — verify bằng video 3 cảnh màu, trích frame xác nhận.

### Kiến trúc dữ liệu

`app/models/__init__.py`: `RawVideo` (id/channel_id/file_path/source_url/import_note/
status/error_message), `ProcessedClip` (clip_id/channel_id/raw_video_id/storage_url/
duration_sec/resolution/caption/tags/mood_tone/vector_id/usage_count/last_used_at/
active/rights_status/rights_note) — KHÔNG cascade xoá `ProcessedClip` khi `RawVideo` bị
xoá (clip đã cắt dùng độc lập). `app/config.py`: `asset_vault_raw_dir`/
`asset_vault_clips_dir`/`asset_vault_chroma_dir` (cùng cây `channel_dir(id)`).
`app/schemas/__init__.py::BrandProfile` thêm `visual_grade`/`grain_enabled`/
`aspect_fill_mode`/`bg_music_ducking_enabled`. `app/render/schemas.py::ShotRenderStatus`
thêm `linked_clip_id` (KHÔNG thêm gì vào `Shot`/pack.json — xem điểm #1 mục đối chiếu
và lý do kiến trúc ở specs/04 §1b).

### Provider infra mới: `vision`/`embedding`

`app/providers/base.py`: `VisionProvider`/`EmbeddingProvider` (ABC riêng, không sửa
`LLMProvider`). `app/providers/vision_localai.py` (`localai_vision`, model mặc định
`moondream2`, gọi `/v1/chat/completions`, parse JSON `{caption,tags,mood_tone}` từ
response text — fallback dùng nguyên văn text làm caption nếu không phải JSON, không
raise). `app/providers/vision_gemini.py` (`gemini_vision`, cloud, cùng pattern
`image_gemini.py`). `app/providers/embedding_localai.py` (`localai_embedding`, thử
`/v1/embeddings` trước, dự phòng `/embeddings` nếu 404). `factory.py` đăng ký
`_VISION_ADAPTERS`/`_EMBEDDING_ADAPTERS` + `get_vision`/`get_embedding`, dùng chung
`_build_asset_provider` đã có. `routers/providers.py` thêm 2 task vào registry test
connection + `CLOUD_MODELS_BY_TASK`. Frontend `ProviderSettings.tsx`: thêm `vision`/
`embedding` vào `GROUPS`/`CLOUD_CATALOG`/`LOCAL_CATALOG` — `CLOUD_CATALOG.embedding=[]`
(mảng rỗng, không thiếu key — tránh `CLOUD_CATALOG[group][0]` văng lỗi runtime khi mở
dialog "+ Thêm provider" ở tab chỉ có local); dialog tự mặc định tab "Local" khi nhóm
không có provider cloud nào.

### Pipeline Ingestion & Matching (`app/asset_vault/`, module mới)

`ingest.py`: `import_raw_video_upload`/`import_raw_video_url` (URL CHỈ tải khi user chủ
động dán + xác nhận qua request HTTP thật, không job nền nào tự gọi); `manual_cut_clip`
(cắt tay, đồng bộ) + `auto_detect_scenes` (PySceneDetect `AdaptiveDetector`, chạy nền —
CẢ 2 cách CÙNG tồn tại, không phải "thay thế nhau", lưới an toàn khi auto-detect chưa
tinh chỉnh tốt cho footage archival); `_extract_clip` tách audio (`-an`), chuẩn hoá
H.264; `caption_clip` (1 keyframe đại diện giữa clip — ĐƠN GIẢN HOÁ có chủ ý so với đề
xuất "2 keyframe 25%/75%" của spec, gộp 2 caption cần thêm bước merge phức tạp, lợi ích
chưa rõ hơn hẳn) → Vision provider → Embedding provider → upsert Chroma;
`caption_all_pending_clips` lỗi 1 clip không chặn cả batch (đúng nguyên tắc đã dùng ở
`generate_all_visual`). `matching.py`: `match_by_keyword` (Phase A, SQL LIKE thô, không
cần Chroma), `match_semantic` (Phase B, cosine similarity đúng namespace kênh, lọc
`active`+ngưỡng 0.65), `apply_dedup` (loại clip đã dùng trong CHÍNH project — nhận
`used_clip_ids` từ caller, KHÔNG đọc `render.json` trực tiếp để tránh phụ thuộc ngược
`app/render/`), `rank_by_usage`, `fallback_neutral_broll` (tag `"ambient"`).
`vector_store.py`: wrapper Chroma, 1 `PersistentClient`/kênh (cache theo `channel_id`).

### Router `app/routers/asset_vault.py` (mới, channel-scoped)

CRUD Raw/Processed Library đầy đủ theo §7.2: upload/import-url/delete/detect-scenes/
manual-cut/caption-all cho raw video; list (filter raw_video_id/rights_status/tag/
mood_tone)/patch/batch-patch/delete/file cho processed clip. Đăng ký trong `main.py`.

### `app/routers/render.py` — Video Slot (gán clip vào shot)

`GET .../vault-candidates` (đọc `pack.json` lấy `visual_fx` làm mô tả, thử semantic
trước rồi rơi về keyword, dedup theo `linked_clip_id` của shot KHÁC trong CÙNG project,
fallback B-roll trung tính khi hết candidate) — CHỈ gợi ý, human-gate giữ nguyên. `POST
.../assign-vault-clip` — hành vi Y HỆT `upload_shot_visual` đã có (copy file vào
`assets/{shot_id}{ext}`, `visual_provider="asset_vault"`, `approved=False`) chỉ khác
nguồn bytes; tăng `usage_count`/`last_used_at` của clip NGAY khi gán. Yêu cầu
`shot.visual_type=="video"` sẵn (cùng ràng buộc `upload_shot_visual`).

### Guardrail — cảnh báo rights

`routers/guardrail.py::_check_rights_warnings` — quét `render.json` (không phải
`pack.json`) tìm shot có `linked_clip_id` trỏ tới clip `rights_status=="unverified"`,
thêm warning `{"type":"rights","severity":"amber",...}` vào kết quả `guardrail/check` —
ĐÚNG cấu trúc warning dict đã có, KHÔNG chặn cứng (single-user, người dùng tự quyết).

### Mở rộng `app/render/assembly.py` (Phase C — KHÔNG viết engine mới)

5 thay đổi ĐỘC LẬP, mỗi cái verify riêng bằng ffmpeg thật trước khi ghép vào pipeline
(đúng kỷ luật đã dùng suốt phiên, đặc biệt sau bài học mục 84 — 1 thay đổi tưởng an toàn
đã tái phát bug thật):

1. **Color grade theo kênh** — `_resolve_color_grade_filter(brand)` tra
   `_GRADE_PRESETS` (`cinematic_warm`/`moody_dark`/`documentary_faded`), rỗng/không khớp
   → dùng ĐÚNG `_COLOR_GRADE_FILTER` cũ (không đổi hành vi kênh chưa cấu hình — verify
   bằng SSIM: `brand=None` và `brand={}` ra pixel giống hệt nhau, SSIM=1.0).
2. **Film grain** — `_grain_filter_suffix(brand)`, `noise=alls=8:allf=t+u` khi
   `grain_enabled`, rỗng khi tắt.
3. **Blur-fill tỷ lệ khung hình** — `_scale_blurfill_filter` (filter đa nhánh `split`+
   `overlay`, verify thật ghép chung 1 chuỗi `-vf` với color grade/fps chạy được không
   lỗi) — chọn qua `aspect_fill_mode`, mặc định vẫn `_scale_cover_filter` cũ.
4. **Auto-ducking nhạc nền** — nâng cấp `_mix_bg_music` bằng `sidechaincompress`
   (bg=main, giọng đọc=sidechain) + `amix normalize=0`. **Phát hiện quan trọng lúc
   verify tay**: `amix` có `normalize=true` MẶC ĐỊNH tự rescale, làm so sánh "có ducking
   vs không ducking" trên TOÀN BỘ mix bị nhiễu/đảo ngược — phải cô lập đúng dải tần nhạc
   nền (`bandpass=f=880`, tách khỏi giọng đọc 220Hz) trên CÙNG 1 output để đo đúng, cách
   so 2 output khác `normalize` là SAI PHƯƠNG PHÁP (đã tự phát hiện + sửa lại test).
5. **Chuẩn hoá loudness EBU R128** — `loudnorm=I=-14:TP=-1.0:LRA=11`, bước hậu kỳ CUỐI
   CÙNG, LUÔN áp dụng (không cần field BrandProfile). Verify: input cố tình rất nhỏ
   (volume=0.02) → output đo được > -20 LUFS (kéo gần về -14). Verify AN TOÀN với video
   KHÔNG có audio track (`-af` không lỗi, output giữ nguyên không audio, không crash).

Mỗi hàm nhận thêm `brand: dict | None = None`, mặc định giữ NGUYÊN hành vi cũ tuyệt
đối. Re-verify lại đúng kịch bản bug frame-drop (mục 79) SAU khi thêm cả 5 thay đổi —
vẫn ra đúng ~42.7s, không hụt shot cuối.

### Frontend

`ChannelDialog.tsx` — thêm tab-bar (`seg`/`seg-opt`, tái dùng CSS đã có) — "Thông tin
chung" (nội dung cũ, không đổi) / "Kho Tài nguyên" (CHỈ hiện ở `mode="edit"`, cùng ràng
buộc mọi upload asset khác trong dialog này). `AssetVaultTab.tsx` (mới) — Raw Library
(upload/URL, badge tiến trình `detecting→tagging→indexed→error`, poll nhẹ khi có video
đang xử lý) + Processed Clip Library (lưới thẻ clip, video preview, inline sửa caption/
rights, chọn nhiều + thao tác theo lô, bộ lọc). `VisualStudio.tsx` — nút "Video từ Kho"
(`VaultClipPicker.tsx`, mới, cùng khung mẫu `LibraryPicker.tsx`) cạnh nút Upload hiện có,
CHỈ hiện cho shot video — modal gợi ý candidate + match score (nếu semantic) + rights
badge, trạng thái rỗng dẫn thẳng tới "Cấu hình kênh → Kho Tài nguyên". `api/types.ts`/
`api/client.ts` — thêm `RawVideo`/`ProcessedClip`/`VaultCandidate(s)` + toàn bộ client
method tương ứng.

### Verify

Backend: `tests/test_asset_vault.py` (mới, 35 test — provider mock qua `respx`, scene
detection/cắt clip bằng ffmpeg THẬT không suy đoán, router qua HTTP thật, rights warning
end-to-end) + 6 test mới trong `test_render.py` cho 5 thay đổi assembly.py. Phát hiện +
sửa 1 lỗi cô lập test lúc viết: 2 fixture tạo kênh (`channel`/`project_with_brief`) bằng
ID mốc mili-giây CÓ THỂ TRÙNG nếu tạo quá nhanh trong cùng 1 test — tránh dùng cả 2
fixture kênh riêng biệt trong cùng 1 test, dùng channel_id cố định giả khi cần "kênh
khác" thay vì phụ thuộc timing. Full `pytest`: **452 passed** (411 cũ + 41 mới). `tsc
--noEmit` sạch cả `frontend/`.

KHÔNG thể verify qua UI thật bằng click chuột (không có Playwright/trình duyệt tự động
trong môi trường này) — đã xác nhận app khởi động lại không lỗi. CHƯA verify: hành vi
THẬT của LocalAI vision/embedding qua GPU thật (endpoint `/embeddings` cụ thể là
`/v1/embeddings` hay `/embeddings` tuỳ bản LocalAI người dùng cài — code đã tự dự phòng
cả 2, nhưng chưa xác nhận qua request thật), chất lượng caption Moondream thật, PySceneDetect
trên footage archival chất lượng thấp (câu hỏi mở #4 change-spec — chưa có dữ liệu thật
để đánh giá), ngưỡng similarity 0.65 (cần dữ liệu dùng thật để hiệu chỉnh).

## 86. Bug thật + gỡ rối dài hơi: tab "Kho Tài nguyên" (mục 85) không hiện/tự revert trên máy người dùng — nguyên nhân KHÔNG phải code, mà `ELECTRON_RUN_AS_NODE` bị kế thừa từ tiến trình Claude Code (2026-08-26)

**Triệu chứng người dùng báo** (nhiều vòng): (1) "chưa thấy giao diện Kho Tài nguyên",
(2) mở lên thấy 2 tab một lúc rồi "tự back lại màn cũ", (3) bấm tab "Thông tin chung" thì
dialog revert về giao diện cũ mất luôn 2 tab, (4) hard-refresh (Ctrl+Shift+R) trong cửa sổ
đang mở KHÔNG fix được.

**Đường đi sai lúc đầu**: nghi ngờ đầu tiên đúng một phần — 1 lỗi thật đã xảy ra (thêm
dòng `import AssetVaultTab from "./AssetVaultTab"` vào `ChannelDialog.tsx` TRƯỚC KHI tạo
file đó, khiến Vite dev server kẹt lỗi cho module này). Nhưng sau khi fix + verify bằng
Chrome DevTools Protocol (mở app thật, click qua CDP, screenshot) xác nhận code ĐÚNG, các
lần user report tiếp theo vẫn xảy ra — vì mỗi lần Claude Code tự restart tiến trình Vite
dev server trong khi cửa sổ Electron của người dùng vẫn đang mở/kết nối, Vite phát hiện
server restart và ép client full-reload — nếu người dùng đang thao tác đúng lúc đó, họ sẽ
thấy "vừa hiện đúng xong lại revert" dù code hoàn toàn đúng cả trước và sau. Đây là hệ quả
phụ của việc Claude Code tự ý kill/restart process nhiều lần liên tiếp để debug, KHÔNG
phải bug trong `ChannelDialog.tsx`/`AssetVaultTab.tsx`.

**Nguyên nhân gốc thật sự** (phát hiện khi build `start-app.bat`, xem dưới): biến môi
trường `ELECTRON_RUN_AS_NODE=1` — do chính tiến trình Claude Code (bản thân cũng là ứng
dụng Electron) đặt sẵn cho MỌI tiến trình con nó spawn (cả Bash tool lẫn PowerShell tool)
— bị KẾ THỪA khi Claude Code tự chạy `node_modules\.bin\electron.cmd` để mở app cho người
dùng test. Khi biến này bật, `electron.cmd` chạy như Node.js thường (KHÔNG mở cửa sổ
Electron thật) → `require("electron").app` trả về `undefined` → crash
`TypeError: Cannot read properties of undefined (reading 'isPackaged')` tại
`electron/dist/main.js:42`. Việc này giải thích tại sao `npm run dev --workspace=electron`
(script `dev:electron` gốc trong `electron/package.json`) LUÔN LỖI trên các phiên chạy từ
Claude Code — không phải lỗi cấu hình dự án, mà môi trường gọi bị ô nhiễm biến này. Suốt
phiên làm việc, Claude Code đã tránh được lỗi này bằng cách LUÔN gọi
`Remove-Item Env:\ELECTRON_RUN_AS_NODE` ngay trước mỗi lần `Start-Process electron.cmd`
trong PowerShell — nhưng đây là 1 bước dễ quên/dễ bỏ sót ở 1 số nhánh gọi (VD gọi qua
`.bat`/`cmd.exe` không có bước này), và mỗi lần bỏ sót sẽ khiến cửa sổ app KHÔNG mở được
(hoặc mở nhầm 1 cửa sổ Electron cũ còn sống sót từ lần trước, gây ảo giác "vẫn là giao
diện cũ" y hệt các báo cáo của người dùng).

**Fix triệt để**: tạo `start-app.bat` ở gốc repo (`e:\VideCode\StudioFlow\start-app.bat`)
— script khởi động 1 lệnh duy nhất, TỰ XOÁ `ELECTRON_RUN_AS_NODE` ngay trong thân script
(`set ELECTRON_RUN_AS_NODE=`) bất kể được gọi từ môi trường nào, rồi: (1) kill tiến trình
`electron`/`node` cũ còn sót, (2) khởi động Vite dev server nền, (3) tự chạy `tsc -p
electron/tsconfig.json` rồi mở app bằng đường dẫn `.bin\electron.cmd` TRỰC TIẾP (không
qua `npm run dev:electron` — script gốc đó vẫn lỗi trên môi trường này vì cùng lý do biến
môi trường, giữ nguyên không sửa vì không phải bug của riêng electron/package.json, mà là
môi trường gọi). **Verify đã làm thật**: xoá sạch mọi tiến trình electron/node, launch
`start-app.bat` như 1 tiến trình tách biệt hoàn toàn (`Start-Process`, không có bước can
thiệp thủ công nào khác) — xác nhận qua `Get-CimInstance Win32_Process` CHỈ ĐÚNG 1 tiến
trình electron.exe chính xuất hiện, và chụp ảnh TOÀN MÀN HÌNH thật (không phải CDP cô lập)
xác nhận app render đúng nội dung thật (Dashboard, danh sách kênh) — chứng minh launcher
hoạt động đúng kể cả khi gọi từ môi trường có biến `ELECTRON_RUN_AS_NODE` bị ô nhiễm.

**Bài học cho các phiên sau**: khi Claude Code cần tự mở ứng dụng Electron của người dùng
để test/demo, LUÔN xoá `ELECTRON_RUN_AS_NODE` trong CHÍNH lệnh khởi động (không dựa vào
nhớ xoá ở bước gọi bên ngoài) — và ưu tiên dùng `start-app.bat` có sẵn thay vì tự spawn
tiến trình bằng tay nhiều lần, để tránh đúng lớp lỗi "nhiều cửa sổ chồng chéo, cửa sổ cũ
còn sống sót" đã gây nhầm lẫn kéo dài trong phiên này.

**Vision/Embedding cho Channel Asset Vault đổi provider mặc định sang Ollama** (phát hiện
cùng lúc điều tra bug trên): máy người dùng THẬT SỰ không cài LocalAI (đã xác nhận qua
`netstat`/`curl` cổng 8080 không có gì lắng nghe) — chỉ có Ollama chạy sẵn (cổng 11434,
model `qwen3:14b` cho LLM). Thêm mới `app/providers/vision_ollama.py`
(`OllamaVisionProvider`, provider_name=`ollama_vision`) và
`app/providers/embedding_ollama.py` (`OllamaEmbeddingProvider`, provider_name=
`ollama_embedding`) — tái dùng ĐÚNG service Ollama đã chạy qua shim OpenAI-compat
(`{base_url}/chat/completions` và `{base_url}/embeddings`, base_url mặc định
`http://127.0.0.1:11434/v1`), model mặc định `moondream` (~1.7GB, vision) và
`nomic-embed-text` (~274MB, embedding) — cả 2 đã `ollama pull` thật và **verify thật qua
`curl` trực tiếp** (vision trả về caption hợp lệ dù ảnh test quá nhỏ để mô tả chính xác;
embedding trả về vector 768 chiều hợp lệ). Đặt làm mặc định (đứng đầu `_VISION_ADAPTERS`/
`_EMBEDDING_ADAPTERS` trong `factory.py` và đầu danh sách `LOCAL_CATALOG` trong
`ProviderSettings.tsx`), giữ nguyên `localai_vision`/`localai_embedding` cho người dùng
nào có cài LocalAI riêng (provider thay thế được, không xoá — CLAUDE.md nguyên tắc #4).

**Verify đã làm**: full `pytest` **452 passed** (không đổi số lượng — 2 adapter mới không
có test riêng theo mock, chỉ verify qua `curl` thật vì mục tiêu là xác nhận kết nối thật
với service đang chạy, không phải hành vi logic của adapter — logic parse JSON/response
giống hệt `vision_localai.py`/`embedding_localai.py` đã có test), `tsc --noEmit` sạch.

## 87. 2.5D Depth-Parallax Motion cho shot ảnh tĩnh (CHANGE_2.5D_Parallax_Synthesizer.md) — đổi hẳn kỹ thuật M1 sau khi verify Qwen-Image-Layered KHÔNG vừa VRAM máy này (2026-08-26)

**Yêu cầu người dùng**: triển khai spec đính kèm — biến ảnh minh hoạ tĩnh của shot thành
video "chiều sâu chuyển động" (2.5D parallax) thay cho Ken Burns phẳng hiện có, nhận cả
ảnh AI sinh lẫn ảnh người dùng tự upload. "Nếu có thông tin gì khác với code base hiện
tại, hãy chủ động đưa ra giải pháp xử lý phù hợp" — đúng tinh thần này, đối chiếu spec
với thực tế TRƯỚC khi code phát hiện 1 vấn đề chặn cứng cần đổi hướng kỹ thuật.

**Đối chiếu spec ↔ thực tế (đã verify bằng đọc code + tra cứu web thật, không suy đoán)**:

1. **`shots[].motion_type` KHÔNG tồn tại** — spec khẳng định field này "đã có sẵn" từ
   `StudioFlow_Video_Improvement_Plan.md` (file không có trong repo). Y HỆT lỗi đã bắt
   được ở mục 85 cho 1 spec khác — cơ chế tương đương đã có sẵn: `Shot.visual_type` +
   `Shot.camera_motion` (`app/render/camera_motion.py::CAMERA_MOTIONS`). Không thêm field
   mới, mở rộng ĐÚNG field `camera_motion` với 4 giá trị mới.
2. **P0 — CHẶN CỨNG thật sự: Qwen-Image-Layered không vừa VRAM máy này**. Model này CÓ
   THẬT (Alibaba, Apache 2.0, `github.com/QwenLM/Qwen-Image-Layered`, workflow ComfyUI
   chính thức tại `docs.comfy.org/tutorials/image/qwen/qwen-image-layered`) — đã verify
   qua tra cứu HuggingFace thật: `qwen_image_layered_fp8mixed.safetensors` (diffusion
   model, bản FP8 nhẹ nhất) = **20.5GB**, `qwen_2.5_vl_7b_fp8_scaled.safetensors` (text
   encoder bắt buộc đi kèm) = **9.38GB** — tổng ~30GB, gấp ~2.5 lần ước tính của spec gốc
   ("~10.5GB + 1.5GB VAE ≈ 12GB, vừa trong 16GB"). Máy dev có 16GB VRAM (RTX 5060 Ti,
   xem mục 15) — **bản thân diffusion model MỘT MÌNH (20.5GB) đã vượt TOÀN BỘ VRAM**, dù
   không chạy cùng gì khác. Không phải vấn đề tranh chấp tài nguyên như các trường hợp
   VRAM chật trước đây (mục 22, 5195) — model này đơn giản KHÔNG THỂ load trên phần cứng
   này.
   - Cũng phát hiện: workflow chính thức của Qwen-Image-Layered là **ComfyUI node graph**
     (`Empty Qwen Image Layered Latent` → `LatentCutToBatch` → `VAE Decode`), KHÔNG phải
     LocalAI như spec giả định ("đăng ký vào LocalAI YAML như model khác") — nếu VRAM đủ,
     đường đúng sẽ là `app/providers/image_comfy_sdxl.py`/`video_comfy_wan.py` (pattern
     gọi ComfyUI qua workflow JSON) chứ không phải `image_localai.py`. Không cần xử lý gì
     thêm vì đã đổi hướng M1 hoàn toàn.
3. **`§6 tự gợi ý preset theo emotional beat` không có dữ liệu nguồn** — field `anchor:
   true/false` trên dòng script (`specs/04_data_schemas.md:203`) là cờ nhị phân "điểm neo
   giữ chân người xem" cho Retention Guardrail (Anchor Gap), KHÔNG phải phân loại kiểu
   beat (giới thiệu nhân vật/hành quân/cao trào/chuyển tiêu điểm) mà spec §6 cần. Không
   có field nào phân loại beat theo nghĩa này ở bất kỳ đâu — bỏ tự-gợi-ý khỏi scope (xây
   bộ phân loại beat riêng là việc lớn ngoài phạm vi, vi phạm "không over-engineer"),
   preset mặc định Cinematic Push-in, người dùng tự đổi qua dropdown.

**Quyết định kỹ thuật thay thế (hỏi người dùng qua AskUserQuestion, chọn phương án khuyến
nghị)**: đổi M1 từ "bóc ảnh N lớp RGBA bằng AI" sang **depth-map + ffmpeg `displace`
filter** — kỹ thuật "3D Photo" thật (cùng nguyên lý LeiaPix/Facebook 3D Photos dùng),
KHÔNG cắt lớp, KHÔNG cần inpaint nền (né hẳn rủi ro #1 lớn nhất mà chính spec gốc nêu ra
— chất lượng inpaint nền trên ảnh phong cách tranh/sơn dầu), gần như không tốn VRAM. 2
phương án khác đã cân nhắc và bị loại: (a) rembg + ComfyUI SDXL inpaint có sẵn (2 lớp
thay N lớp) — vẫn giữ nguyên rủi ro inpaint nền, tốn thêm VRAM/thời gian GPU mỗi shot;
(b) vẫn build đúng Qwen-Image-Layered chấp nhận chậm/rủi ro OOM — không khuyến nghị trên
phần cứng hiện tại.

**Kiến trúc đã build**:
```
[Ảnh shot tĩnh] → [Depth estimation: onnxruntime + depth-anything-v2-small int8, ~27MB]
  → depth_map.png (cache theo sha256 ảnh gốc)
  → [Displacement synthesis: numpy thuần, KHÔNG AI, <1s]
  → xmap.mp4/ymap.mp4 (hoặc animated mask cho Focus Reveal)
  → [ffmpeg -filter_complex displace/maskedmerge] → scene_XXXX_parallax.mp4
  → [_build_segment() hiện có] — coi như 1 video input bình thường (color grade/grain/
    scale/tpad/setsar dùng lại NGUYÊN nhánh video đã có, không viết compositor riêng)
```

**Model depth — verify thật trước khi code**: tải `onnx-community/depth-anything-v2-small`
bản `model_int8.onnx` (27.26MB, xác nhận qua HTTP HEAD + tải thật), kiểm tra input/output
tensor thật qua `session.get_inputs()/get_outputs()` (input `pixel_values`
(batch,3,H,W) — H/W ĐỘNG, output `predicted_depth` tự động `14*floor(dim/14)`) thay vì
tin theo tài liệu web (khớp — nhưng vẫn verify theo đúng kỷ luật "không tin tài liệu
100%"). Test suy luận thật trên ảnh thật: 0.314s CPU, depth min/max/mean hợp lý (không
phẳng). Preprocessing (ImageNet mean/std, resize giữ tỷ lệ khung hình bội số 14 — KHÔNG
ép vuông 518×518 như `preprocessor_config.json` gợi ý, vì ảnh không vuông sẽ méo) verify
qua đúng 1 lần chạy thật trước khi viết vào `depth_parallax.py`.

**4 preset displacement — mỗi cái verify riêng bằng đo pixel thật (không suy đoán filter
tương đương, đúng kỷ luật mục 84)**:
- **Parallax Drift**: dịch ngang tỉ lệ theo depth. Verify: ảnh test có nửa trái depth=0.1
  (xa), nửa phải depth=0.9 (gần), đo cross-correlation pixel giữa frame đầu/cuối — nửa xa
  dịch ~1px, nửa gần dịch ~12px (đúng tỉ lệ kỳ vọng ~9:1, sai lệch nhỏ do làm tròn pixel).
- **Cinematic Push-in**/**Dolly Zoom**: dịch chuyển hướng tâm/ra tâm theo depth, render
  thật không lỗi — đã có test đo pixel riêng cho Drift làm đại diện xác nhận công thức
  displacement đúng, 2 preset còn lại dùng CHUNG cơ chế `_displacement_grid` (khác công
  thức toán, cùng pipeline đã verify).
- **Focus Reveal** (khác cơ chế — KHÔNG dùng `displace`): lúc đầu code SAI — dùng
  `maskedmerge=weight_expr=...`, chạy THẬT mới phát hiện `maskedmerge` **KHÔNG có tham số
  `weight_expr`** (`ffmpeg -h filter=maskedmerge` xác nhận filter này CHỈ có option
  `planes`, mask PHẢI là 1 stream video thật, không có biểu thức động) — con giống lỗi
  từng gặp với các filter ffmpeg khác trong session, xác nhận lại giá trị của việc LUÔN
  chạy thật thay vì suy đoán tham số filter. Fix: sinh mask animate bằng numpy (cùng
  pattern với xmap/ymap), `mask(x,y,t) = (1-depth(x,y))·(1-progress(t))·255`. Verify đo
  bằng biến thiên Laplacian (chỉ số độ nét chuẩn): vùng xa sharpness 102.6 (mờ) ở frame
  đầu → 8432.2 (sắc nét) ở frame cuối; vùng gần giữ ổn định 7303→9038 suốt clip — đúng ý
  đồ "chuyển tiêu cự".

**Tích hợp `assembly.py::_build_segment`**: khi `camera_motion` là 1 trong 4 preset
parallax VÀ ảnh (không phải video) — chạy `depth_parallax.render_parallax_clip` ra 1 file
mp4 trung gian TRƯỚC, gán `visual_path`/`is_video=True`, để phần còn lại hàm chạy ĐÚNG
nhánh video hiện có (không viết nhánh mới) — dọn file trung gian sau khi ghép xong (tránh
rò rỉ file, có test riêng xác nhận không còn `*_parallax_src.mp4` sót lại).

**Schema**: `BrandProfile.parallax_intensity_default: float = 0.8` (kênh sử "điềm tĩnh"),
`Shot.parallax_intensity: Optional[float] = None` (null = kế thừa), `camera_motion` mở
rộng 4 giá trị mới trong `CAMERA_MOTIONS` dict (`app/render/camera_motion.py`) — KHÔNG
thêm field `motion_type` mới (đúng quyết định đã áp dụng nhất quán từ mục 85).

**Backend mới**: `app/render/depth_parallax.py` (estimate_depth/get_or_compute_depth_map/
render_parallax_clip — cache depth map theo sha256 NỘI DUNG ảnh gốc, đổi preset/intensity/
duration sau đó chỉ chạy numpy+ffmpeg, không gọi lại AI — đúng ý đồ caching spec §8, áp
dụng cho depth map thay vì N layer PNG). `app/routers/pipeline.py`: `ShotPatchBody` thêm
`parallax_intensity`; endpoint mới `POST .../visual/shots/apply-parallax-all` ("Convert
All", CHỈ ghi metadata `camera_motion` hàng loạt — KHÔNG có job nền/tiến trình per-shot
như spec gốc giả định, vì trong kiến trúc app này `camera_motion` chỉ thực sự áp dụng LÚC
`render/assemble` chạy ffmpeg, giống 9 giá trị camera_motion cũ); endpoint mới `GET
.../render/shots/{shot_id}/depth-preview` (thay "Layer Breakdown Preview" gốc — trả PNG
depth map, cache luôn cho bước render thật dùng lại).

**Dependency mới**: `onnxruntime==1.28.0` (bản CPU — model quá nhỏ để cần GPU, tránh tranh
chấp VRAM với OmniVoice/Ollama/ComfyUI đang có). KHÔNG thêm Pillow/huggingface_hub — dùng
`cv2`/`numpy` (đã có sẵn qua `scenedetect[opencv]` từ mục 85) + `httpx` (đã có sẵn) để tải
model 1 lần. Model file (~27MB) KHÔNG commit git (`backend/app/render/models/`, thêm vào
`.gitignore`).

**Frontend**: `VisualStudio.tsx` — 4 option mới trong dropdown "Chuyển động camera" hiện
có (không dropdown riêng); Depth Intensity slider (0.5-2.0x, hiện khi chọn preset
parallax, mặc định đọc `BrandProfile.parallax_intensity_default` qua 1 lần fetch chung
cho CẢ block thay vì mỗi ShotCard tự fetch riêng); nút "Xem depth map" (tái dùng
`Lightbox` component có sẵn); "Chuyển tất cả shot ảnh sang 2.5D Parallax" gộp vào menu
"⋯ Tuỳ chọn khác" đã có (đúng pattern các hành động hàng loạt khác). `ChannelDialog.tsx`:
field `parallax_intensity_default` cạnh `motion_tone` đã có.

**Verify đã làm**: `depth_parallax.py` có 9 test riêng (`test_depth_parallax.py`) dùng
ffmpeg/ảnh/model ONNX THẬT (không mock) — đo pixel/Laplacian thật cho từng preset, test
tích hợp đầu-cuối qua `_build_segment` xác nhận color-grade vẫn áp dụng + file trung gian
được dọn sạch, cộng 4 test HTTP cho 2 endpoint mới (`apply-parallax-all`/`depth-preview`,
bao gồm case lỗi 400 khi preset không hợp lệ/shot chưa có ảnh). Sửa 1 test cũ
(`test_build_camera_motion_filter_covers_every_real_motion`) để loại trừ 4 preset parallax
(đúng hành vi mới — chúng KHÔNG xử lý bởi `build_camera_motion_filter`, không phải thiếu
sót). Full `pytest`: **465 passed** (452 cũ + 13 mới). `tsc --noEmit` sạch. Verify UI thật
qua Chrome DevTools Protocol trên app đang chạy thật (không phải TestClient cô lập): xác
nhận cả 4 option parallax hiện đúng trong dropdown thật, chọn 1 option làm Depth Intensity
slider + nút "Xem depth map" xuất hiện đúng với giá trị kế thừa BrandProfile hiển thị
chính xác ("0.80x · kế thừa từ hồ sơ thương hiệu").

**CHƯA verify**: chất lượng depth map thật trên ảnh phong cách tranh/sơn dầu/tư liệu lịch
sử thật của kênh (chỉ test bằng ảnh tổng hợp có cấu trúc rõ + 1 ảnh testsrc ffmpeg — chưa
có ảnh AI-gen/upload thật của kênh để đánh giá chất lượng ước lượng độ sâu chủ quan bằng
mắt); tham số biên độ displacement (`_PUSH_IN_MAX_PERCENT` v.v., hiện chọn nhỏ/thận trọng
theo brand DNA "điềm tĩnh") có thể cần tinh chỉnh sau khi xem video thật; hiệu năng
`onnxruntime` CPU trên ảnh độ phân giải cao thật (1920×1080+, test mới ở 640×480/320×240).

## 88. 4 phản hồi người dùng sau khi test thật: 2 entry point riêng cho ChannelDialog, bug OmniVoice do hibernate, nút sinh video Parallax NGAY cho từng shot, xác nhận "Video từ Kho" không lỗi ở short-form (2026-08-27)

**1. ChannelDialog vẫn mở giao diện cũ khi bấm "Sửa kênh"** — thay vì tiếp tục điều tra
sâu thêm cơ chế tab-switcher nội bộ (đã tốn nhiều công sức debug ở mục 86 mà vẫn có thể
tái phát do Vite HMR/restart), theo đúng yêu cầu người dùng: bỏ hẳn phụ thuộc vào việc
bấm chuyển tab BÊN TRONG dialog — **2 icon riêng biệt trên Dashboard** ("Sửa BrandProfile"
/ "Kho Tài nguyên"), mỗi icon mở 1 dialog MỚI đã đúng tab ngay từ đầu qua prop
`ChannelDialog.initialTab`. Verify thật qua CDP: click icon "Kho Tài nguyên" mở thẳng vào
"VIDEO GỐC (RAW LIBRARY)", click icon "Sửa BrandProfile" mở thẳng vào form "Tên kênh" —
không còn phụ thuộc trạng thái switcher nội bộ nào có thể lệch.

**2. OmniVoice lỗi "HTTP 500: Internal Server Error"** — tái hiện được thật bằng
`curl -X POST http://127.0.0.1:8199/synthesize`, server (PID cũ) trả 500 dù `/health`
báo `model_loaded: true`. Restart server (`omnivoice_server.py`) rồi thử lại → THÀNH
CÔNG, trả về WAV thật. **Kết luận: hibernate máy (mục 86 cuối phiên trước) đã làm hỏng
CUDA context của tiến trình OmniVoice đang giữ model trên GPU** — tiến trình sống sót qua
hibernate (không crash) nhưng context GPU không hợp lệ nữa, gây lỗi ở lần suy luận đầu
tiên sau khi máy thức dậy. Ollama (cũng giữ model trên GPU) sống sót qua đúng cùng lần
hibernate KHÔNG lỗi — không phải MỌI service GPU đều bị ảnh hưởng, có thể do khác cách
Ollama tự quản lý context/tự nạp lại model per-request. **Bài học cho các phiên sau: sau
khi hibernate/resume máy, nếu 1 service local giữ model trên GPU báo lỗi lạ dù health
check vẫn "ok", THỬ RESTART SERVICE ĐÓ TRƯỚC khi điều tra sâu hơn** — khả năng cao là
CUDA context bị hỏng bởi hibernate, không phải lỗi code.

**3. Thêm nút "Tạo video Parallax 2.5D" cho từng shot** — trước đó (mục 87) preset
`camera_motion=parallax_*` CHỈ là metadata áp dụng LÚC `render/assemble` ghép toàn bộ
video — người dùng không thấy kết quả cho tới tận bước Output, vi phạm nguyên tắc
human-gate "duyệt từng shot trước khi ghép MP4" mà mọi asset khác (ảnh/giọng đọc/video từ
Kho) đều tuân theo. Thêm hành động sinh video NGAY, khớp UX "Tạo ảnh"/"Tạo giọng đọc" đã
có.
- **Ràng buộc kiến trúc phải tôn trọng**: `render.py` chỉ ĐỌC pack.json, không bao giờ
  ghi lại (nguyên tắc đã có từ đầu dự án, `assign_vault_clip` cũng tuân theo — yêu cầu
  `shot.visual_type=="video"` SẴN thay vì tự đổi). Vì cần đổi `visual_type` từ "image"
  sang "video" (thứ SỐNG trong pack.json, thuộc quyền `pipeline.py`), endpoint mới KHÔNG
  tự làm việc này — **frontend gọi 2 API tuần tự**: (1) `PATCH .../visual/shots/{id}`
  (pipeline.py) đổi `visual_type` sang "video", (2) `POST .../render/shots/{id}/
  generate-parallax` (render.py, mới) — đọc ẢNH NGUỒN từ `render.json` (path ảnh cũ vẫn
  còn nguyên vì bước (1) không đụng render.json), chạy
  `depth_parallax.render_parallax_clip` (tái dùng NGUYÊN module mục 87, không viết logic
  mới), ghi đè asset của shot thành video thật. Lỗi ở bước (2) → frontend tự PATCH
  `visual_type` VỀ LẠI "image" (rollback), tránh kẹt shot ở trạng thái nửa vời (đánh dấu
  video trong pack.json nhưng file thật vẫn là ảnh cũ).
- Dùng lại `_shot_base_duration` (assembly.py, đã có — ưu tiên độ dài giọng đọc thật) cho
  duration, `RESOLUTION_MAP`/`RESOLUTION_MAP_VERTICAL` (đã có, chọn theo `project.format`)
  cho độ phân giải — không phát minh lại quy ước duration/resolution cho use-case
  single-shot này.
- Frontend: nút "Tạo video Parallax 2.5D" (btn-primary) đặt cạnh "Xem depth map", CHỈ hiện
  khi đã chọn 1 trong 4 preset parallax VÀ shot có ảnh sẵn sàng (`visual_status=="ready"`)
  — dùng NGUYÊN preset/intensity đang chọn trong dropdown/slider đã có (mục 87), không
  cần picker riêng trong nút.
- **Verify đã làm**: 3 test mới HTTP end-to-end (đầy đủ đúng luồng frontend thật: PATCH
  rồi POST) — xác nhận asset cuối là mp4 THẬT (`ffprobe` đọc được `codec_type=video`),
  `visual_provider="parallax"`, `approved=False`; 2 test lỗi (chưa đổi type / preset sai).
  Verify UI thật qua CDP trên app đang chạy thật: chọn "Parallax Drift" → bấm nút → đợi
  ~15s → shot chuyển hẳn sang video, hiện player phát được thật (ảnh bản đồ lịch sử động,
  đúng ~23s khớp giọng đọc, có điều khiển play/pause/scrubber) — không phải suy đoán từ
  test cô lập.

**4. "Video từ Kho" báo thiếu ở short-form — đã kiểm tra: KHÔNG PHẢI BUG.** Đọc code xác
nhận `VaultClipPicker` dùng CHUNG 1 `ShotCard` component cho CẢ long-form lẫn short-form
(`isVertical` chỉ đổi tỷ lệ khung preview, không rẽ nhánh component khác) — điều kiện hiện
nút DUY NHẤT là `shot.visual_type === "video"`, không có logic loại trừ theo `format`.
Verify thật qua CDP trên 1 project short-form thật: `hasCameraMotionSelect: true`,
`hasParallaxOption: true`, nhưng `hasVideoFromVault: false` — ĐÚNG NHƯ KỲ VỌNG vì mọi shot
trong project đó đang là kiểu ẢNH (chưa có shot nào đổi sang "video"). Sau khi thêm nút
"Tạo video Parallax 2.5D" (mục 3), 1 khi shot chuyển sang video (qua nút đó HOẶC tag
Image/Video thủ công), "Video từ Kho" tự xuất hiện — ĐÚNG cơ chế chung, không cần sửa gì
thêm riêng cho short-form. Không có thay đổi code nào cho mục này ngoài việc xác nhận.

**Verify tổng**: full `pytest` **468 passed** (465 cũ + 3 mới generate-parallax endpoint),
`tsc --noEmit` sạch. Restart toàn bộ app + verify LIVE qua Chrome DevTools Protocol cho cả
4 mục (không chỉ tin test cô lập) — đúng kỷ luật "verify thật" xuyên suốt dự án.

## 89. Dashboard — "Local Services & GPU Monitor" (bật/tắt Ollama/OmniVoice/ComfyUI + tổng quan GPU) (2026-08-27)

**Yêu cầu người dùng**: 1 khu vực ở cuối trang Dashboard hiện trạng thái bật/tắt các local
model/server + tình trạng dùng GPU + nút bật/tắt từng service — suốt phiên làm việc mọi
thao tác này đều phải làm thủ công qua terminal.

**Đã verify thật đường dẫn/lệnh khởi động từng service TRƯỚC khi code (không suy đoán)**:
`C:\Tools\Ollama\ollama.exe serve` (11434), `C:\Tools\OmniVoice\.venv\Scripts\python.exe
backend/local_servers/omnivoice_server.py --port 8199` (8199),
`C:\Tools\ComfyUI_extract\ComfyUI_windows_portable\python_embeded\python.exe -s
ComfyUI\main.py --windows-standalone-build` (8188, đọc trực tiếp từ `run_nvidia_gpu.bat`
có sẵn trong bản cài). `nvidia-smi` xác nhận chạy được thật trên máy, nhưng
`--query-compute-apps=pid,used_memory` trả `[N/A]` cho MỌI PID — **xác nhận giới hạn thật
của Windows WDDM driver mode: không báo VRAM per-process tin cậy được** (khác Linux/TCC)
— panel chỉ hiện tổng VRAM dùng/tổng + service nào đang giữ GPU context (đối chiếu PID),
không hứa hẹn breakdown MB/từng service.

**2 bug thật bắt được lúc verify tay từng hàm với service THẬT** (trước khi tin bất kỳ
unit test mock nào — đúng kỷ luật "verify thật" xuyên suốt dự án):
1. **Đường dẫn thực thi tương đối không được `subprocess.Popen` tự resolve theo `cwd=`
   trên Windows** — `start_service("comfyui")` (dùng `start_cmd=["python_embeded\\
   python.exe", ...]` tương đối, đúng như `run_nvidia_gpu.bat` viết) lỗi thật
   `[WinError 2] The system cannot find the file specified` dù hàm tự kiểm tra
   `exe_path.exists()` (đã tự resolve đúng) vẫn qua — vì kết quả resolve đó KHÔNG được
   dùng lại cho chính lệnh `Popen`, vẫn truyền `svc.start_cmd` gốc (tương đối). Fix: xây
   `resolved_cmd = [str(exe_path), *svc.start_cmd[1:]]`, dùng biến này cho `Popen`.
2. **Bản Ollama trên máy này là bản "portable", KHÔNG dùng thư mục model mặc định**
   (`~/.ollama/models`) — dữ liệu model thật (`moondream`/`nomic-embed-text`/`qwen3`) nằm
   ở `C:\Tools\Ollama\data`. Tiến trình `ollama.exe serve` gốc (khởi động từ trước, ngoài
   app) hẳn có biến môi trường `OLLAMA_MODELS` trỏ đúng chỗ này qua 1 wrapper/profile nào
   đó — `subprocess.Popen` mặc định KHÔNG kế thừa biến này (chỉ kế thừa env của tiến
   trình backend Python). Verify thật: sau khi `stop_service`+`start_service` mà THIẾU
   biến này, `curl .../api/tags` trả `{"models":[]}` dù blob model vẫn nguyên trên đĩa —
   chỉ khi thêm `env={**os.environ, "OLLAMA_MODELS": "C:\\Tools\\Ollama\\data"}` vào
   `Popen` mới thấy lại đủ 3 model. Thêm field `ServiceDef.extra_env` để xử lý ca này
   (chỉ Ollama cần, 2 service kia không).

**Backend**: `app/local_services.py` (module mới) — `SERVICES` registry (3 entry cố định,
HARDCODE đường dẫn theo đúng cách cài trên máy này, khớp cách toàn bộ app đã giả định 1
máy dev cụ thể — `base_url` mặc định `127.0.0.1:PORT` ở mọi provider local cũng vậy),
`check_status`/`get_all_statuses` (health check HTTP, không parse body — mỗi service trả
format khác hẳn nhau), `start_service` (kiểm tra file thực thi tồn tại + CHƯA chạy trước,
`subprocess.Popen` với `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` để sống sót độc lập
khỏi backend/Electron, log ra `workspace/service_logs/{name}.log`, KHÔNG đợi health check
thành công mới trả response — model nạp chậm, trả ngay rồi để frontend tự poll),
`stop_service` (dùng `psutil` tìm PID đang LISTEN đúng port — KHÔNG dựa vào PID tự lưu,
vì service có thể được khởi động NGOÀI app, đúng thực tế đã gặp suốt phiên — `terminate()`
cả tiến trình lẫn `children(recursive=True)` vì Ollama có thể có runner con, `kill()` dự
phòng nếu còn sống sau 5s), `get_gpu_stats` (2 lệnh `nvidia-smi`, best-effort
`available:False` nếu không có `nvidia-smi` trên PATH). Mở rộng `app/routers/system.py`
có sẵn (KHÔNG tạo router mới) — `GET /system/local-services`,
`POST /system/local-services/{name}/start`, `POST .../stop`.
`backend/requirements.txt`: ghim tường minh `psutil==7.2.2` (trước chỉ có mặt gián tiếp).

**Frontend**: `frontend/src/components/LocalServicesPanel.tsx` (mới), gắn ở CUỐI
`Dashboard.tsx` (sau bảng project) — poll `GET /system/local-services` mỗi 5s (dọn
interval lúc unmount), card GPU (thanh progress VRAM dùng/tổng, utilization%, nhiệt độ,
hoặc thông báo "không đọc được" nếu `available:false`), 1 hàng/service (chấm trạng thái +
nhãn "đang giữ GPU" nếu có + nút "Bật"/"Tắt"). Nút "Tắt" có `confirm()` cảnh báo có thể
làm gián đoạn tiến trình đang chạy (cùng pattern `handleDelete` xoá kênh đã dùng ở
Dashboard.tsx).

**Verify đã làm**: 15 test mock (`test_local_services.py`) — 2 test là REGRESSION TEST
trực tiếp cho 2 bug thật vừa bắt được ở trên (xác nhận `Popen` nhận đúng đường dẫn tuyệt
đối đã resolve, xác nhận `env` truyền đúng `extra_env`). **Trước đó đã verify TAY từng
hàm với CHÍNH 3 service thật đang chạy trên máy** (không chỉ tin mock): stop+start thật
Ollama (xác nhận cả 3 model hiện lại đúng sau khi thêm `OLLAMA_MODELS`), stop+start thật
OmniVoice (2 lượt, bắt được cả hiện tượng OmniVoice tự die ngẫu nhiên đã ghi nhận ở mục
88), start thật ComfyUI lần đầu tiên trong toàn bộ phiên làm việc (trước đó chưa từng kiểm
tra được vì luôn tắt) — xác nhận `/system_stats` trả về đúng sau ~15s khởi động.
Sau đó verify UI thật qua Chrome DevTools Protocol trên app đang chạy: panel hiện đúng cả
3 service + GPU thật (2.8/15.9GB, 0% util, 35°C), bấm "Tắt" OmniVoice → nút đổi thành
"Bật" + VRAM giảm, bấm "Bật" lại → "Đang xử lý..." → server sống lại thật (`curl
.../health` trả `model_loaded:true`) — vòng lặp đầy đủ, không suy đoán từ test cô lập.
Full `pytest` **483 passed** (468 cũ + 15 mới), `tsc --noEmit` sạch.

**Giới hạn đã biết, ghi rõ không giấu**: đường dẫn `SERVICES` hardcode theo máy dev này,
đổi máy cần sửa code; không có breakdown VRAM theo từng service (giới hạn thật Windows
WDDM); "Tắt" dừng HẲN process (không chỉ unload model khỏi VRAM) — đơn giản hơn, khớp
nghĩa đen yêu cầu, đánh đổi là "Bật" lại chậm hơn vài giây/chục giây do nạp lại model.

## 90. Bug thật: mất ~2s giọng đọc ở SHOT CUỐI CÙNG khi ghép video nhiều transition — `_xfade_chain` cộng dồn thời lượng LÝ THUYẾT thay vì đo thật (2026-08-27)

**Người dùng báo**: video ghép cho project "Nguyễn Trãi và án Lệ Chi Viên..." (29 shot,
16 run/15 ranh giới transition — dissolve/fade rải khắp video) bị mất khoảng 2 giây giọng
đọc ở shot cuối cùng (B29) sau khi ghép.

**Verify thật, không suy đoán**: dùng cross-correlation (numpy, tự viết — không có scipy
trong `.venv`) giữa audio nguồn `B29.wav` (12.66s) và audio trong `final.mp4` đã ghép
(bản người dùng đã xem, `renders/final.mp4` mtime 2026-08-26 01:12) — LẦN ĐẦU dùng
correlation "full" (không giới hạn lag hợp lệ) cho kết quả GIẢ (match yếu ở rìa cửa sổ,
dễ hiểu lầm "còn nguyên") — sửa lại giới hạn `lag ∈ [0, len(haystack)-len(needle)]` mới
lộ ra: vị trí ĐÚNG của 3s cuối narration (tính từ vị trí khớp mạnh của 3s đầu, score 0.34)
sẽ nằm NGOÀI đoạn 25s cuối file đã trích — tức file thật sự KẾT THÚC SỚM hơn ĐÚNG lúc
narration còn ~2.4s nữa mới xong. Xác nhận thêm: dựng lại (re-run) `assemble_video()` cho
CHÍNH project này (giữ nguyên code, `Path.unlink` monkeypatch thành no-op để giữ lại toàn
bộ file trung gian `_xfade_chain` sinh ra) — đo trực tiếp `body_xblend15.mp4` (bước merge
CUỐI, gộp shot B29 vào phần thân đã ghép) dài **15.336s** thay vì 13.26s lý thuyết
(`narration_floor 12.66s + lead_in 0.6s`) — lệch **+2.08s**, đúng cỡ với phần bị mất.

**Root cause**: `_xfade_chain` (mỗi lần merge 2 run bằng `xfade`/`acrossfade`) theo dõi độ
dài phần đã ghép (`current_duration`) bằng CÁCH CỘNG DỒN LÝ THUYẾT
(`current_duration += run_durations[i] - t`) từ `durations[]` — giá trị DỰ ĐỊNH tính từ
kịch bản/giọng đọc/reflow, KHÔNG PHẢI đo thật từ file `current_path` sau mỗi bước
`_concat_fast`/`_build_segment`/`xfade` trước đó. Mỗi bước encode/stream-copy có thể lệch
NHẸ so với lý thuyết (làm tròn frame ở `-t`, GOP/keyframe alignment của encoder, hành vi
nội bộ filter `acrossfade`/`xfade` khi 1 input ngắn hơn hẳn input kia) — sai số NHỎ nhưng
CỘNG DỒN qua nhiều lần merge (project này: 15 lần). Khi `current_duration` (lý thuyết)
VƯỢT quá thời lượng THẬT của `current_path`, `head_keep = current_duration - t` tính ra
LỚN HƠN nội dung thật sẵn có — `-ss head_keep` ở lệnh `blend_cmd` SEEK QUÁ điểm đó, ăn mất
1 phần cuối (kể cả đệm lặng bảo vệ giọng đọc `narration_lead_out_sec`, rồi tới cả narration
thật) của run TRƯỚC ranh giới. Rõ nhất ở LẦN MERGE CUỐI CÙNG (gộp shot cuối) vì không còn
run nào phía sau để "che" phần đã mất — mọi lần merge giữa video vẫn lệch y hệt nhưng ít
ai để ý vì nội dung mất nằm giữa 2 đoạn liền mạch, không lộ ra thành "hụt cuối video" rõ
rệt như shot cuối.

Test lại NHIỀU LẦN với ĐÚNG project + code cũ cho kết quả KHÔNG ổn định (1 lần dựng lại
KHÔNG tái hiện bug — trôi lệch đi hướng ngược lại, vô hại) — xác nhận đây là lỗi CỘNG DỒN
SAI SỐ (không phải lỗi logic cứng luôn-luôn-sai), giải thích vì sao chỉ project nhiều
transition + video dài mới lộ rõ, và vì sao không tái hiện được 100% mỗi lần thử.

**Fix**: đo lại `current_duration` THẬT bằng `_probe_audio_duration_sec` (ffprobe,
`format=duration`) ngay ĐẦU mỗi vòng lặp `_xfade_chain`, TRƯỚC khi tính `t`/`head_keep` —
tự sửa sai số tích luỹ ở MỌI bước thay vì chỉ tin phép cộng lý thuyết, loại bỏ khả năng
trôi lệch bất kể nguyên nhân gốc (làm tròn/encoder/filter) là gì. Fallback về giá trị lý
thuyết nếu ffprobe lỗi/thiếu binary (không chặn luồng ghép, cùng nguyên tắc
`probe_duration_sec` mọi nơi khác trong `assembly.py`). Chỉ sửa `app/render/assembly.py`
(`_xfade_chain`), không đổi API/schema nào.

**Verify sau fix**: dựng lại THẬT project của người dùng (`assemble_video()` trực tiếp,
không qua mock) — `body_xblend15.mp4`/tương đương giờ đúng lý thuyết, cross-correlation
(cùng script, giới hạn lag hợp lệ) xác nhận TOÀN BỘ 12.66s narration B29 có mặt, đúng vị
trí, kết thúc ĐÚNG lúc file kết thúc (sai lệch <40ms, trong ngưỡng làm tròn codec) — thay
final.mp4 cũ (thiếu ~2s) bằng bản đã ghép lại đúng cho project thật của người dùng. Full
`pytest tests/test_render.py` **109 passed**, không regression.

## 91. Kho Tài Nguyên — tách thành màn riêng ở sidebar, gắn nhiều kênh dạng tag, thanh tiến trình thật (CHANGE_Semantic_BRoll_Asset_Vault.md, 2026-08-27)

**Yêu cầu người dùng**: Asset Vault (trước đây là 1 TAB bên trong dialog "Sửa BrandProfile"
của từng kênh, kho RIÊNG mỗi kênh) đổi thành 1 MÀN RIÊNG có entry point ở sidebar (dưới
Dashboard), hiện TẤT CẢ video/clip đã cắt từ MỌI kênh, lọc theo kênh; vẫn cho nhập video
gốc như cũ nhưng phải gắn tên Kênh (dạng TAG, 1 video gắn được nhiều kênh) TRƯỚC khi cắt
cảnh; có thanh tiến trình thật khi tải video và khi cắt cảnh.

### Data model — bảng m2m đầu tiên của dự án

`raw_video_channel` (`raw_video_id`, `channel_id`, cả 2 PK) — THAY THẾ cột `channel_id`
đơn trước đây trên `raw_video`. `processed_clip` bỏ hẳn `channel_id` riêng — kênh của 1
clip = kênh của `raw_video` cha, lấy qua JOIN (`asset_vault/matching.py::_clips_for_channel`).
Migration 1 lần lúc backend khởi động (`app/asset_vault/migration.py`, gọi từ `main.py`
ngay sau `create_all()`) — **bug thật gặp lúc build**: `ALTER TABLE raw_video DROP COLUMN
channel_id` bị SQLite từ chối (`unknown column "channel_id" in foreign key definition`) vì
cột đó nằm trong 1 `FOREIGN KEY` constraint — SQLite (xác nhận bản 3.45.3, trên ngưỡng hỗ
trợ DROP COLUMN từ 3.35) có giới hạn RIÊNG cho cột thuộc FK. Fix bằng pattern "12-step"
chuẩn của SQLite: rename bảng cũ → `create_all()` tạo bảng mới đúng schema ORM → copy dữ
liệu qua bằng danh sách cột tường minh (loại `channel_id`) → `INSERT OR IGNORE` vào
`raw_video_channel` → xoá bảng cũ. Verify thật trên chính DB dev (không phải DB test) đã có
sẵn dữ liệu — xác nhận dữ liệu + file thật được giữ nguyên qua 3 lần chạy lại liên tiếp
(idempotent).

### Storage + Chroma — chuyển từ theo-từng-kênh sang TOÀN CỤC

`asset_vault_raw_dir()`/`asset_vault_clips_dir()`/`asset_vault_chroma_dir()` (trong
`config.py`) bỏ tham số `channel_id`, dời sang `workspace/asset_vault/` (sibling của
`LIBRARY_DIR`, tiền lệ đã có cho `CreativeAsset`). Chroma đổi từ 1 `PersistentClient`/kênh
sang 1 client TOÀN CỤC — scoping-theo-kênh chuyển hẳn từ "tách vật lý DB Chroma" sang
"filter SQL sau khi overfetch" (`query_similar_clips(embedding, top_k*10)` — tăng hệ số
overfetch từ `*3` lên `*10` vì Chroma không còn tự lọc theo kênh, cần dư nhiều hơn để lọc
lại qua JOIN `raw_video_channel`).

### Tiến trình thật (trước đây chỉ có 4 trạng thái thô, không có %)

- **Tải URL** (`ingest.py::download_raw_video_from_url`): dùng `yt_dlp` `progress_hooks`
  (tính năng có sẵn của yt-dlp, trước đây chưa từng dùng) — hook đọc `downloaded_bytes`/
  `total_bytes`, ghi vào `progress_current`/`progress_total`, throttle commit DB (chỉ ghi
  cách nhau ≥0.4s, không phải mỗi callback — tránh spam ghi). Đổi từ chạy ĐỒNG BỘ trong
  request sang chạy nền qua `BackgroundTasks` (`create_raw_video_placeholder_for_url` tạo
  hàng NGAY, `download_raw_video_from_url` tải THẬT trong task nền) — để frontend poll
  được tiến trình giữa chừng thay vì phải đợi cả request.
- **Cắt cảnh tự động** (`ingest.py::auto_detect_scenes`): 2 giai đoạn báo riêng — (1) PHÁT
  HIỆN cảnh dùng `SceneManager.detect_scenes(callback=...)` (đã verify thật API này gọi
  MỖI FRAME lúc quét với `(frame_ndarray, FrameTimecode)`, không suy đoán từ tài liệu),
  đọc `timecode.frame_num`/`video.duration.frame_num` làm current/total; (2) CẮT từng clip,
  cập nhật `progress_current=i, progress_total=n_scenes` SAU MỖI clip. Verify thật bằng
  video test 3 cảnh màu tách biệt (ffmpeg concat) — bắt snapshot progress thật qua
  monkeypatch `db.commit`, xác nhận đúng `current=74/total=218` (frame) ở giai đoạn phát
  hiện và đúng `0/3→1/3→2/3→3/3` ở giai đoạn cắt.

### Backend router — API TOÀN CỤC (`/asset-vault/...`, bỏ tiền tố `/channels/{channel_id}/`)

`GET /asset-vault/raw?channel_id=` (lọc tuỳ chọn), `POST /asset-vault/raw/upload`
(`channel_ids` JSON-string bắt buộc ≥1 phần tử qua `Form`), `POST .../import-url`
(`channel_ids: list[str]` bắt buộc trong body), `PATCH /asset-vault/raw/{id}/channels`
(mới — sửa lại tag kênh sau khi đã tạo, ghi đè toàn bộ danh sách), `GET /asset-vault/clips
?channel_id=` (lọc qua JOIN `raw_video_channel` khi có). `render.py::assign_vault_clip` và
`guardrail.py::_check_rights_warnings` (2 chỗ NGOÀI router `asset_vault.py` trực tiếp dùng
`ProcessedClip.channel_id`/`RawVideo.channel_id`) được sửa theo — tìm bằng
`grep -rn "ProcessedClip\.channel_id\|RawVideo\.channel_id" backend/app` NGAY sau khi đổi
model, sửa trước khi chạy test (không đợi test tự lộ ra).

### Frontend

`frontend/src/screens/AssetVault.tsx` (mới, top-level, mirror `Library.tsx`) thay cho
`AssetVaultTab.tsx` (xoá hẳn) — dropdown lọc kênh, multi-select checkbox kênh bắt buộc
≥1 trong form upload/import-url, chip hiển thị kênh đã gắn trên mỗi raw video (+ nút "Sửa
tag kênh" gọi PATCH), thanh `<progress>` thật đọc `progress_current`/`progress_total`/
`progress_label` (tái dùng đúng interval poll 2.5s có sẵn khi status đang xử lý).
`AppContext.tsx` thêm `View="asset_vault"` + `goAssetVault()`; `Sidebar.tsx` thêm entry
"Kho Tài nguyên" NGAY DƯỚI "Dashboard" (icon riêng — hộp+tam giác kiểu ổ băng, KHÔNG dùng
lại glyph lưới-4-ô của Dashboard để tránh 2 icon giống hệt nhau); `App.tsx` thêm route.
**Dọn dẹp đường vào cũ** (đã lỗi thời sau khi có màn riêng): `ChannelDialog.tsx` bỏ hẳn cơ
chế tab (`activeTab`/`initialTab`, thêm ở mục 88) — chỉ còn ĐÚNG "Sửa BrandProfile" như
trước; `Dashboard.tsx` bỏ icon "Kho Tài nguyên" thứ 2 ở channel card (cũng thêm ở mục 88),
chỉ giữ icon "Sửa BrandProfile" — theo đúng yêu cầu "Kho tài nguyên CẦN LÀ 1 màn riêng"
(thay thế, không phụ thêm cạnh dialog cũ).

### Bug thật bắt được lúc verify UI qua CDP (KHÔNG phải test mock)

Verify sống bằng cách chạy 2 Electron instance song song (`--remote-debugging-port=9222`,
KHÔNG đụng cửa sổ chính người dùng đang mở — Electron app này không khoá single-instance)
trỏ vào ĐÚNG workspace DB thật: upload 1 video test thật, gắn 2 kênh, cắt cảnh tự động ra
2 clip đúng kế thừa cả 2 tag kênh, đổi dropdown lọc kênh xác nhận đúng danh sách lọc, sửa
tag kênh (bỏ bớt 1 kênh) xác nhận video biến mất khỏi bộ lọc kênh vừa bỏ — toàn bộ luồng
chính hoạt động đúng.

Lúc dọn dữ liệu test (bấm "Xoá" trên video gốc — CỐ Ý không cascade xoá `ProcessedClip`
con, xem `specs/02_database.md`), phát hiện **`GET /asset-vault/clips` crash 500**
(`AttributeError: 'NoneType' object has no attribute 'channels'`) — `_clip_out` gọi
`_channels_out(c.raw_video)` nhưng `c.raw_video` là `None` cho clip mồ côi (raw_video cha
đã bị xoá, tình huống HOÀN TOÀN hợp lệ theo thiết kế, không phải edge case hiếm). Fix:
`_channels_out` trả `[]` khi `r is None` thay vì crash. Thêm regression test
`test_list_clips_survives_orphaned_clip_after_raw_video_deleted` (tạo raw video thật, xoá,
xác nhận list clip vẫn 200 với `channels: []`). Restart lại Electron debug instance
(backend launch qua `backend-launcher.ts` KHÔNG có `--reload`, cần restart để nạp code
mới), verify lại đúng luồng gây lỗi (xoá raw video → list clip) không còn crash.

**Verify**: 45 test `test_asset_vault.py` (viết lại HOÀN TOÀN cho API toàn cục — helper
seed mới tạo `RawVideo.channels=[...]` rồi `ProcessedClip` trỏ qua `raw_video_id`, không
còn kwarg `channel_id` trực tiếp), full `pytest` **493 passed** (không regression ngoài
file này), `tsc --noEmit` sạch. Dữ liệu test tạo ra lúc verify UI đã dọn sạch khỏi DB thật
(qua API, không xoá tay file/DB).

## 92. Revert HOÀN TOÀN tính năng "2.5D Depth-Parallax" (CHANGE_2.5D_Parallax_Synthesizer.md) theo yêu cầu người dùng (2026-08-27)

Người dùng yêu cầu bỏ hẳn tính năng 2.5D Depth-Parallax đã build ở mục 87 (đổi kỹ thuật từ
đề xuất gốc Qwen-Image-Layered sang depth-map ONNX nhẹ) + phần mở rộng ở mục 88/91 (nút
"Tạo video Parallax 2.5D" riêng từng shot, cường độ mặc định theo BrandProfile). Xoá TOÀN
BỘ code + model liên quan, KHÔNG chỉ tắt tính năng:

**Backend**: xoá hẳn `app/render/depth_parallax.py` (module ước lượng depth map ONNX +
displacement/xfade compositing) và `tests/test_depth_parallax.py` (16 test). Xoá model đã
tải về `app/render/models/depth_anything_v2_small_int8.onnx` (~27MB, `onnxruntime`/
`opencv-python` VẪN giữ trong `requirements.txt` — xác nhận vẫn cần cho Piper TTS
(`tts_piper.py`, ONNX runtime cho model VITS) và PySceneDetect Asset Vault, KHÔNG phải
dependency riêng của parallax, tránh xoá nhầm). `app/render/camera_motion.py` bỏ 4 preset
`parallax_*` khỏi `CAMERA_MOTIONS`, bỏ `PARALLAX_MOTIONS`, bỏ `eased_progress_numeric`
(chỉ dùng bởi depth_parallax). `app/render/assembly.py::_build_segment` bỏ nhánh rẽ
`PARALLAX_MOTIONS`/tham số `parallax_cache_dir`/`parallax_intensity`; `assemble_video` bỏ
tính `parallax_intensity` per-shot. `app/routers/render.py` xoá hẳn endpoint `POST
.../generate-parallax` (`GenerateParallaxBody`). `app/routers/pipeline.py` xoá field
`ShotPatchBody.parallax_intensity`, endpoint `POST .../apply-parallax-all`, endpoint `GET
.../depth-preview`. `app/schemas/__init__.py` xoá `BrandProfile.parallax_intensity_default`
và `Shot.parallax_intensity`.

**Frontend**: `VisualStudio.tsx` xoá 4 option `parallax_*` khỏi `CAMERA_MOTION_OPTIONS`,
xoá `PARALLAX_MOTIONS` set, state `parallaxIntensityDefault`/hiệu ứng fetch từ
BrandProfile, hàm `generateParallaxVideo`/`convertAllToParallax`, nút "Chuyển tất cả shot
ảnh sang 2.5D Parallax" (OverflowMenu), slider "Depth Intensity" + nút "Tạo video Parallax
2.5D"/"Xem depth map" trong `ShotCard`. `ChannelDialog.tsx` xoá field
`parallaxIntensityDefault` (Draft) + ô nhập "Cường độ mặc định 2.5D Depth-Parallax".
`api/types.ts`/`api/client.ts` xoá `parallax_intensity_default`/`parallax_intensity` khỏi
type `BrandProfile`/`Shot`, xoá `applyParallaxAll`/`generateParallax`/`depthPreviewUrl`.

**Docs**: `specs/04_data_schemas.md` thay đoạn mô tả `parallax_intensity_default`/
`Shot.parallax_intensity` bằng ghi chú "đã REVERT" (không xoá hẳn mục IMPLEMENTATION_
REPORT.md mục 87 — giữ làm lịch sử build/lý do đổi kỹ thuật, đúng quy ước append-only đã
dùng xuyên suốt tài liệu này). `.gitignore` bỏ dòng ignore riêng cho
`backend/app/render/models/` (thư mục không còn được tạo ra nữa).

**Verify**: `grep -rli parallax` toàn repo (trừ `.claude/worktrees/` — agent worktree
riêng, không thuộc phạm vi) xác nhận sạch (chỉ còn 1 dòng comment vô hại ở
`camera_motion.py` dùng chữ "parallax" mô tả hiệu ứng "orbit" chung chung, không liên quan
tính năng đã xoá). Full `pytest` **477 passed** (493 cũ − 16 test đã xoá cùng module,
KHÔNG có test nào khác fail). `tsc --noEmit` sạch.

## 93. Bug thật: `GET /asset-vault/clips` crash khi raw_video lỗi gắn nhãn không có nút thử lại (2026-08-27)

**Người dùng báo**: video gốc `raw_1787841423521` báo "Lỗi gắn nhãn clip
clip_1787841553477: [WinError 10061]" (Vision/Embedding provider — Ollama — chưa chạy lúc
đó) — sau khi bật lại Ollama, KHÔNG có nút nào để thử gắn nhãn lại, chỉ thấy dòng lỗi tĩnh.

**Fix UI**: `AssetVault.tsx::RawLibrarySection` — khi `status==="error"`, kiểm tra raw
video ĐÃ có clip nào chưa (nghĩa là cắt cảnh thành công, chỉ gắn nhãn lỗi) để hiện ĐÚNG nút
— "Gắn nhãn lại" (gọi lại `caption-all`) nếu đã có clip, "Cắt cảnh lại" (gọi lại
`detect-scenes`) nếu chưa có clip nào (nghĩa là chính bước cắt cảnh mới là bước lỗi).

**Fix backend đi kèm** (`ingest.py`): cả `caption_all_pending_clips` VÀ `auto_detect_scenes`
trước đây chỉ GHI `error_message` khi lỗi, KHÔNG XOÁ khi thử lại thành công — retry thành
công vẫn để lại thông báo lỗi CŨ (chỉ không hiện ra UI vì gate theo `status==="error"`,
nhưng vẫn là dữ liệu sai, tiềm ẩn hiện lại nếu logic hiển thị đổi sau này). Sửa: xoá
`error_message` khi retry thành công ở CẢ 2 hàm.

**Verify sống ngay trên project thật của người dùng** (không phải test giả lập) — dựng lại
đúng lỗi qua backend đang chạy thật của họ (tìm cổng thật qua `Get-CimInstance
Win32_Process`, không đoán), xác nhận Ollama đã reachable (`curl 11434/v1/models` → 200),
gọi lại `caption-all` trực tiếp — cả 34 clip của video đó gắn nhãn thành công thật (đọc lại
caption qua API, không suy đoán), `status` chuyển `indexed`, dọn `error_message` cũ còn sót.
Full `pytest` **477 passed**, không regression.

## 94. Bảng "Clip đã cắt" (Processed Clip Library) — đổi từ card-grid sang table đầy đủ cột + bộ lọc mở rộng + bulk gắn nhãn AI + panel xem trước (2026-08-27)

**Yêu cầu người dùng**: đổi phần "Clip đã cắt" ở Kho Tài nguyên từ dạng thẻ (card) sang
bảng (table) đầy đủ cột thông tin + tên video nguồn; thêm điều kiện lọc (kênh/chưa gắn
nhãn/trạng thái); cho phép select all/tick từng clip để BULK gắn nhãn; cho phép thêm tag
kênh (retag) ngay tại bảng; nút Play mở sidebar xem trước; vẫn gắn nhãn được từng clip.

### Backend — `ProcessedClip.caption_error` (cột mới) + bulk gắn nhãn theo lựa chọn tự do

Thêm `caption_error: TEXT, nullable` vào `ProcessedClip` (migrate qua `_add_missing_columns`
đã tổng quát hoá — trước chỉ xử lý `raw_video`, giờ nhận dict `{table: {cột: kiểu}}` cho cả
`processed_clip`) — cần vì bulk gắn nhãn theo LỰA CHỌN TỰ DO có thể trải NHIỀU `raw_video`
khác nhau, không có 1 hàng RawVideo chung để gắn cờ lỗi như luồng "Gắn nhãn"/"Gắn nhãn lại"
cũ (scope theo đúng 1 raw_video). `ingest.py` thêm `caption_clips(db, clips) -> (ok, err)`
— hàm dùng chung, lỗi/thành công ghi thẳng vào `caption_error` của TỪNG clip; refactor
`caption_all_pending_clips` gọi lại hàm này thay vì lặp tay. Router mới `POST
/asset-vault/clips/caption-batch` (`clip_ids: list[str]`, 400 nếu rỗng/chứa id không tồn
tại) — chạy nền qua `BackgroundTasks`, frontend poll `GET .../clips` như thường lệ (mỗi
clip tự commit ngay khi xong, không đợi cả batch). `GET /asset-vault/clips` thêm 2 filter
mới: `unlabeled=true` (caption rỗng) và `raw_status=` (JOIN lọc theo trạng thái raw_video
cha). `_clip_out` thêm `raw_video_name` (ưu tiên `import_note`, rồi tên file cuối của
`source_url`, cuối cùng `id`), `raw_video_status`, `caption_error`. `PATCH
/asset-vault/clips/{id}` xoá `caption_error` khi người dùng tự sửa caption tay (lỗi AI lần
trước không còn ý nghĩa).

### Frontend — bảng đầy đủ + filter bar riêng + panel xem trước

`AssetVault.tsx::ProcessedClipLibrarySection` viết lại hoàn toàn:
- **Bảng** (không còn grid card) — cột: checkbox, Play, Video nguồn, Kênh (chip + nút "Sửa
  tag kênh" tái dùng `RawChannelRetag` đã có, tra `RawVideo` qua `raw_video_id`), Caption
  (click-to-edit tại chỗ), Tags/Mood, Rights (dropdown), Thời lượng, Độ phân giải, Dùng,
  Trạng thái (badge trạng thái raw_video cha + chỉ báo "Đang gắn nhãn.../Lỗi gắn nhãn" khi
  có), Ngày tạo, Hành động (Tắt/Bật, Xoá). Bọc `overflow-x:auto` (nhiều cột, tránh vỡ layout
  ngang trên màn hẹp).
- **Filter bar riêng, ĐỘC LẬP khỏi dropdown kênh Ở ĐẦU TRANG** (dropdown đầu trang giờ chỉ
  còn scope cho "Video gốc (Raw Library)") — kênh, trạng thái rights (đã có), trạng thái
  video gốc (mới), video gốc (đã có, giờ hiện tên thay vì id kỹ thuật), checkbox "Chưa gắn
  nhãn" (mới). Lọc HOÀN TOÀN client-side (mọi field cần đã có sẵn trên `ProcessedClip` từ
  BE — `channels`/`raw_video_status`/`caption` — không cần round-trip riêng cho từng filter,
  đơn giản hơn, đúng tinh thần CLAUDE.md "không over-engineer" cho quy mô dữ liệu 1 người
  dùng). Đổi luôn cách `AssetVault` cha fetch `clips` — bỏ hẳn tham số `channel_id` khi gọi
  `listProcessedClips()` (fetch TOÀN BỘ, không còn lệ thuộc dropdown đầu trang).
- **Select all / tick từng clip** (đã có) — nút bulk MỚI "Gắn nhãn (AI)" gọi
  `api.captionClipsBatch`, tự thêm các clip vừa gửi vào `pendingCaptionIds` rồi POLL nhẹ
  (2s/lần, tái dùng `onChanged` của cha) tới khi MỌI id trong đó đã có `caption` hoặc
  `caption_error` mới — suy tiến trình TRỰC TIẾP từ dữ liệu clip đã có, KHÔNG cần thêm 1
  field trạng thái job riêng ở BE (đơn giản hơn, đủ dùng cho single-user).
- **Panel xem trước** (`ClipPreviewPanel`, mới) — trượt vào từ MÉP PHẢI màn hình khi bấm
  nút Play (icon tam giác) ở 1 hàng, hiện `<video controls autoPlay>` + caption đầy đủ +
  kênh + rights + metadata. Tự chứa (không dùng chung `RightPanel.tsx` — component đó gắn
  chặt vào layout `ProjectView`, không hợp với màn top-level). Dựng từ `.dialog-backdrop`/
  `.dialog` có sẵn nhưng ĐÈ `display:flex;justifyContent:flex-end` (class gốc dùng CSS Grid
  `place-items:center` — `justify-content` không có tác dụng thật trên grid 1-item, phải ép
  hẳn `display:flex` mới định vị được sát mép phải).

**Verify**: 7 test backend mới (`caption_clips` trải nhiều raw_video + lỗi riêng từng clip,
endpoint `caption-batch` 400 khi rỗng/id lạ + thành công thật qua `respx` mock, filter
`unlabeled`/`raw_status`, `raw_video_name`/`raw_video_status` xuất hiện đúng trong response)
— bắt được 1 lỗi test tự gây (dimension embedding lệch giữa các test dùng CHUNG 1 Chroma
collection session-scoped, Chroma từ chối thật "expecting dimension of 2, got 1"), sửa
khớp dimension các test khác. Full `pytest` **484 passed**, `tsc --noEmit` sạch.

**Verify UI SỐNG qua CDP trên đúng dữ liệu thật** (35 clip thật của `raw_1787841423521`,
không phải data giả lập) — mở bảng, xác nhận đủ cột + dữ liệu thật hiện đúng; bấm Play →
panel xem trước trượt vào từ phải, hiện đúng video/caption/kênh; tick "Chưa gắn nhãn" → lọc
đúng còn 4 clip rỗng caption; chọn tất cả 4 + bấm "Gắn nhãn (AI)" → xác nhận qua API TRỰC
TIẾP cả 4 đều được gắn caption thật (không suy đoán, đọc lại nội dung caption thật của model
Vision); đổi dropdown kênh RIÊNG của bảng clip (độc lập dropdown đầu trang) sang kênh không
có clip nào → đúng 0 kết quả, dropdown đầu trang KHÔNG bị ảnh hưởng (xác nhận tách biệt 2
bộ lọc đúng như thiết kế).

## 95. 3 phản hồi người dùng: xác nhận cắt cảnh/gắn nhãn KHÔNG tự động, nút "Mở thư mục" lưu trữ thật, fix bảng bị che khi thu hẹp cửa sổ + audit toàn app (2026-08-27)

**Câu hỏi 1 — trả lời, không phải bug**: cắt cảnh (`auto_detect_scenes`) và gắn nhãn
(`caption_all_pending_clips`/`caption_clips`) KHÔNG bao giờ tự chạy ngay sau khi upload/tải
video — xác nhận qua đọc code (`import_raw_video_upload`/`download_raw_video_from_url` chỉ
đặt `status`, không gọi 2 hàm trên) — đúng nguyên tắc #3 CLAUDE.md ("mỗi bước là hành động
rõ ràng người dùng tự bấm"). Người dùng LUÔN phải tự bấm "Cắt cảnh tự động" rồi "Gắn nhãn"
(hoặc bulk "Gắn nhãn (AI)" mới ở mục 94) cho từng video.

### Nút "Mở thư mục" lưu trữ thật (video gốc + clip đã cắt)

Backend: `GET /asset-vault/folders` trả `{raw_dir, clips_dir}` (đường dẫn tuyệt đối THẬT,
`asset_vault_raw_dir()`/`asset_vault_clips_dir()` tự đảm bảo thư mục tồn tại). Electron: IPC
mới `open-folder` (`main.ts`, dùng `shell.openPath` — trả chuỗi lỗi thay vì throw, convert
thành `Error` để renderer bắt bằng try/catch quen thuộc), expose qua `preload.ts::
studioflowNative.openFolder` (cùng bridge với `chooseFolder` có sẵn — chỉ tồn tại khi chạy
Electron thật, ẩn nút khi chạy dev server thuần trình duyệt, cùng pattern `hasNativePicker`
đã dùng ở OutputCenter.tsx). Frontend: `OpenFolderButton` (mới, `AssetVault.tsx`) — 2 nút
nhỏ cạnh tiêu đề "Video gốc"/"Clip đã cắt", lấy đường dẫn LƯỜI (lúc bấm, không fetch sẵn mỗi
lần mở màn — hành động hiếm dùng).

**Verify sống qua CDP** — click thật cả 2 nút, xác nhận qua `Shell.Application` COM
(PowerShell) rằng Explorer THẬT ĐÃ MỞ đúng 2 thư mục (`workspace/asset_vault/raw` và
`workspace/asset_vault/clips`), không chỉ suy đoán từ code — đóng lại 2 cửa sổ test sau khi
xác nhận. 1 test backend mới xác nhận cả 2 đường dẫn tồn tại thật trên đĩa.

### Bug thật: bảng "Clip đã cắt" bị che/cắt mất khi thu hẹp cửa sổ, không trượt ngang được

**Root cause** (xác nhận thật qua CDP, không suy đoán) — `AssetVault.tsx`'s root container
là 1 flex ITEM của Shell (`App.tsx`, `display:flex` hàng ngang chứa Sidebar + màn hiện tại)
nhưng KHÔNG có `min-width:0` — mặc định flex item không co xuống dưới kích thước nội dung
tối thiểu ("min-content"), nên bảng nhiều cột (bảng Clip đã cắt mới ở mục 94) ép RỘNG RA cả
container cha thay vì kích hoạt cuộn ngang CỤC BỘ đã có sẵn (`overflowX:"auto"` bọc
`<table>`) — đúng triệu chứng người dùng báo ("bị che mất, không trượt ngang được").

Verify bằng CDP `Emulation.setDeviceMetricsOverride` (thu hẹp viewport còn 900px) — TRƯỚC
fix: `document.documentElement.scrollWidth` (900) so với `clientWidth` (900) khớp nhau tại
mức container ngoài cùng NHƯNG cột cuối bảng bị cắt mất, không có cách nào cuộn tới; SAU
fix (thêm `minWidth:0` vào root `AssetVault.tsx`): đo trực tiếp — `table` wrapper có
`scrollWidth:1173` vs `clientWidth:590` (đúng như kỳ vọng, bảng RỘNG hơn khung nhìn) +
`overflowX:"auto"` hoạt động — cuộn `wrapper.scrollLeft=400` bằng script thật, chụp lại,
xác nhận các cột trước đó bị ẩn (TAGS/MOOD, RIGHTS, THỜI LƯỢNG...) hiện ra đúng, còn
`document.documentElement.scrollWidth` vẫn khớp `clientWidth` (900) — trang KHÔNG bị vỡ
layout, chỉ bảng cuộn cục bộ đúng ý đồ thiết kế.

**Audit toàn app** (theo yêu cầu người dùng) — grep mọi `<table` trong `frontend/src` (6
chỗ: `AssetVault.tsx` đã fix, `Dashboard.tsx`, `Trash.tsx` ×2, `settings/AuditLogSettings.
tsx`, `settings/BillingSettings.tsx`) — KHÔNG chỗ nào có wrapper `overflowX:auto` trước đó.
Bọc lại toàn bộ + thêm `minWidth:0` vào root của MỌI màn top-level còn thiếu (`Dashboard.
tsx`, `Library.tsx`, `Trash.tsx`, `settings/SettingsShell.tsx` — cả 2 tầng flex row của
riêng màn Cài đặt). `ProjectView.tsx` đã có sẵn `minWidth:0` đúng chỗ từ trước (không cần
sửa) — có thể là bài học đã áp dụng khi build màn đó, chỉ chưa lan ra các màn sau này.

**Verify**: `tsc --noEmit` sạch cả frontend lẫn electron (`main.ts`/`preload.ts` biên dịch
qua `tsc -p tsconfig.json`). Full `pytest` **485 passed**.

## 96. Bảng "Video gốc" (Raw Library) đầy đủ tính năng + module xoá watermark tái dùng được (Florence-2 + LaMa, tham khảo github.com/D-Ogi/WatermarkRemover-AI) (2026-08-27)

Yêu cầu người dùng: đổi "Video gốc (Raw Library)" từ list sang bảng như "Clip đã cắt" (mục
94) — bỏ filter kênh ở header chung của cả màn (mỗi bảng tự có filter riêng), giữ đủ action
hiện có, chọn nhiều để xử lý batch, upload nhiều file 1 lúc (giữ được tên file gốc để biết
đã upload file nào), tag nhiều kênh 1 lúc, play preview, và **xoá watermark trước khi cắt
cảnh** — module riêng, tái dùng được cho Visual Studio sau này (xoá watermark ảnh/video user
upload cho từng shot).

### Module `app/watermark/` (mới, độc lập, không phụ thuộc Asset Vault)

Kiến trúc tham khảo đúng repo người dùng chỉ định (Florence-2 phát hiện vùng + LaMa
inpaint lấp lại): `detector.py::detect_watermark_bboxes` (Florence-2 `<OPEN_VOCABULARY_
DETECTION>`, model cache theo tiến trình) + `remover.py` (LaMa qua `simple-lama-inpainting`,
`inpaint_regions_full_frame` cho ảnh đơn — dành cho Visual Studio sau này — và
`inpaint_region_cropped` cho video, chỉ chạy LaMa trên VÙNG NHỎ quanh bbox thay vì cả khung
hình để đủ nhanh cho video nhiều nghìn frame) + `pipeline.py` (2 hàm cấp cao:
`remove_watermark_from_image`, `remove_watermark_from_video` — video: tách frame bằng
ffmpeg, detect bbox 1 LẦN trên frame đại diện ở 20% thời lượng, inpaint từng frame theo bbox
đó, ghép lại giữ nguyên fps/audio).

**3 bug môi trường THẬT bắt được lúc cài đặt** (không phải bug logic, nhưng đều sẽ chặn
đứng `npm run dev:backend` nếu không phát hiện):
1. `pip install -r requirements.txt` crash `UnicodeDecodeError` (cp1252) — comment tiếng
   Việt không dấu BOM/khai báo encoding làm `pip._internal.utils.encoding.auto_decode()` rơi
   về `locale.getpreferredencoding()` (cp1252 trên máy Windows này), không đọc được UTF-8.
   Đây là bug ẨN CÓ SẴN từ trước (đã xác nhận qua `git show HEAD:...requirements.txt` — bản
   đã commit trước đó chưa có tiếng Việt), chỉ lộ ra khi thêm comment mới cho watermark. Fix:
   thêm `# coding: utf-8` làm DÒNG ĐẦU TIÊN của file.
2. `pip install transformers einops timm simple-lama-inpainting` (không kèm CUDA index) làm
   pip re-resolve và ÂM THẦM hạ `torch==2.8.0+cu129` xuống `torch==2.13.0+cpu` — không lỗi,
   không cảnh báo, chỉ `torch.cuda.is_available()` trả `False`. Bắt được nhờ CHỦ ĐỘNG kiểm
   tra lại sau khi cài (không chỉ tin exit code). Fix: cài lại đúng bản CUDA đã verify khớp
   ComfyUI đang dùng (`--index-url .../cu129 --force-reinstall --no-deps`), thêm
   `--extra-index-url https://download.pytorch.org/whl/cu129` vào đầu `requirements.txt` để
   `pip install -r` sau này luôn resolve đúng.
3. `transformers` mới nhất lúc cài (5.16.1) làm code remote của Florence-2 (viết cho API 4.x)
   crash `AttributeError: 'Florence2LanguageConfig' object has no attribute
   'forced_bos_token_id'` — ghim `transformers==4.49.0`.

**Bug thật quan trọng nhất — phát hiện qua test A/B trên CHÍNH 1 frame video thật**: prompt
nhiều khái niệm `"watermark, logo, text overlay"` làm Florence-2 trả bbox SAI (nguyên cả
khung hình), trong khi 1 từ đơn `"watermark"` cho bbox ĐÚNG (sai lệch <5px so với watermark
thật vẽ vào ảnh test). Kết luận và fix: giữ mặc định `text_input="watermark"` (1 từ đơn),
ghi lại đầy đủ trong docstring `detector.py` để không ai vô tình "cải thiện" thành câu dài
hơn mà không verify lại.

Verify tay end-to-end với model THẬT (không mock) trên cả ảnh tổng hợp lẫn video tổng hợp có
NỀN DI CHUYỂN dưới watermark TĨNH (crop+inpaint từng frame đúng theo bbox cố định, không bị
lẫn theo nền) — xác nhận bằng mắt qua các frame input/output. Test tự động (`test_watermark.
py`, 5 test) MOCK detect/inpaint (model thật ~90s nạp lần đầu, quá chậm cho suite chạy mỗi
commit) — chỉ test đúng luồng điều phối (cắt frame, gọi đúng thứ tự, dọn file tạm, xử lý lỗi).

### Backend — Raw Library: tên file gốc, batch tag/xoá, preview, tích hợp watermark

`RawVideo.original_filename` (cột mới, giữ NGUYÊN tên file user upload để hiển thị — tên
trên đĩa vẫn có tiền tố `{raw_id}_` + tên đã sanitize để tránh ký tự nguy hiểm, giữ dấu tiếng
Việt). `_raw_video_name`/`rawVideoLabel` ưu tiên field này trước `import_note`/`source_url`.
4 endpoint mới: `GET /asset-vault/raw/{id}/file` (preview, mirror endpoint clip có sẵn),
`POST /asset-vault/raw/batch-tag-channels` (UNION kênh, không ghi đè), `POST /asset-vault/
raw/batch-delete`, `POST /asset-vault/raw/{id}/remove-watermark` (chạy nền — poll qua field
progress có sẵn, KHÔNG đổi `status` khi xong để người dùng bấm "Cắt cảnh tự động" ngay sau
đó; đổi `file_path` sang bản `_nowm.mp4` đã xoá watermark, xoá file cũ).

### Frontend — `AssetVault.tsx`: bảng "Video gốc" mirror bảng "Clip đã cắt"

Bỏ filter kênh ở header toàn màn (mục cũ) — mỗi bảng con giờ có filter riêng. `RawLibrarySe
ction` viết lại hoàn toàn thành `<table>` (checkbox chọn/chọn tất cả, cột Tên file/Kênh/Trạng
thái/Ghi chú/Ngày tạo/Hành động, nút Play mở panel xem trước). Input upload thêm `multiple`,
xử lý TUẦN TỰ từng file (lỗi 1 file không chặn các file còn lại, giống pattern gắn nhãn hàng
loạt clip). Thanh bulk action khi có video được chọn: "+ Thêm kênh" (gọi batch-tag-channels),
"Cắt cảnh tự động (N)"/"Gắn nhãn (N)" (không có endpoint batch riêng — lặp gọi endpoint đơn
từng video, cô lập lỗi từng video), "Xoá watermark (N)", "Xoá" (batch-delete), "Bỏ chọn".
`PreviewPanelShell` (tách ra từ `ClipPreviewPanel` cũ) — khung panel trượt-từ-phải dùng
CHUNG cho cả preview clip lẫn preview video gốc mới (`RawVideoPreviewPanel`), chỉ phần
metadata hiển thị khác nhau truyền qua `children`.

**Verify sống qua CDP** (launch Electron thật với `--remote-debugging-port=9222`, phải
`env -u ELECTRON_RUN_AS_NODE` trước — biến này bị kế thừa từ tiến trình Claude Code, đã gặp
đúng bug này ở mục 86, khiến `electron.exe` chạy như Node thuần thay vì app thật): upload 2
file THẬT tên khác nhau ("Great Wall drone footage.mp4", "watermark_test_clip.mp4") cùng
lúc qua `DOM.setFileInputFiles` nhiều file — xác nhận cả 2 xuất hiện đúng tên trong bảng;
chọn cả 2 bằng checkbox — xác nhận thanh bulk hiện đúng "2 video đã chọn" + đủ nút; bấm
"+ Thêm kênh" gắn thêm 1 kênh — xác nhận UNION đúng (giữ kênh cũ, thêm kênh mới) trên cả 2
hàng; bấm Play trên 1 video gốc — panel xem trước mở đúng, phát được video, hiện đúng tên
file/kênh/trạng thái; bấm "Xoá" hàng loạt — xác nhận 2 video test biến mất khỏi bảng, chỉ
còn video gốc từ trước. `tsc --noEmit` sạch. Backend `pytest` **498 passed** (66/66 riêng
`test_asset_vault.py` + `test_watermark.py`).

**Chưa verify sống**: click nút "Xoá watermark" với model THẬT qua UI (model Florence-2/LaMa
mất ~90s nạp lần đầu — đã verify riêng pipeline này bằng script trực tiếp, xem phần module ở
trên, chỉ chưa lặp lại qua đúng nút bấm trên UI vì giới hạn thời gian phiên làm việc).

## 97. Bug thật (user tự test 2 video cùng lúc) + tăng tốc xoá watermark bằng batch inference GPU (2026-08-28)

Người dùng tự test tính năng xoá watermark (mục 96) với 2 video khác nhau chạy CÙNG LÚC —
báo 2 hiện tượng: (1) cả 2 video báo CÙNG số lượng frame (sai — 2 video khác nhau, số frame
phải khác), (2) dừng/xong tiến trình 1 video làm video kia LỖI theo.

### Bug thật: `tmp_dir` dùng chung 1 tên CỐ ĐỊNH cho MỌI video — 2 lượt song song ghi đè/xoá nhầm frame của nhau

**Root cause** (đọc code, không suy đoán): `ingest.py::remove_watermark_from_raw_video` xây
`tmp_dir = asset_vault_raw_dir() / "_watermark_tmp"` — KHÔNG có thành phần nào phân biệt
theo từng video, nên `remove_watermark_from_video`'s `frames_dir = tmp_dir / "wm_frames"`
(pipeline.py) là CÙNG 1 thư mục cho mọi lượt gọi. 2 video chạy song song (2 BackgroundTasks
khác nhau) cùng ghi frame vào đúng 1 thư mục (`frame_000001.jpg` video A và B ghi đè lẫn
nhau) → đếm frame ra cùng 1 con số sai; và `finally: shutil.rmtree(frames_dir)` của lượt
XONG TRƯỚC (dù thành công hay lỗi) xoá mất frame của lượt CHƯA XONG đang xử lý dở → lượt đó
crash `FileNotFoundError` khi mở frame kế tiếp — đúng khớp cả 2 hiện tượng người dùng báo.

**Fix**: cô lập `tmp_dir` theo `raw_video.id` (`.../​_watermark_tmp/{raw_video.id}/`) —
mỗi video có thư mục tạm RIÊNG, chạy song song bao nhiêu video cũng không đụng nhau. Thêm
dọn `shutil.rmtree(tmp_dir, ...)` ở cả nhánh thành công lẫn lỗi (trước chỉ dọn
`frames_dir` con bên trong `pipeline.py`, để lại thư mục cha rỗng theo từng id tích tụ dần).

**Verify thật** (`wm_bench.py`, script scratch, KHÔNG chỉ chạy pytest mock): dựng 2 video
tổng hợp số frame KHÁC NHAU rõ rệt (30 và 50 frame), chạy `remove_watermark_from_video`
thật (model thật, không mock) trên 2 thread SONG SONG với `tmp_dir` theo pattern mới, xác
nhận: video A báo đúng `(30, 30)`, video B báo đúng `(50, 50)`, không video nào lỗi. Trước
fix, chạy lại kịch bản tương tự sẽ tái hiện đúng cả 2 bug đã báo (không chạy lại bản lỗi để
đối chứng vì tốn thời gian — root cause đã đọc code xác nhận chắc chắn, không cần thực
nghiệm âm tính). Thêm test tự động
`test_remove_watermark_from_raw_video_uses_isolated_tmp_dir_per_video` (spy giá trị
`tmp_dir` thật truyền cho 2 raw video khác nhau, xác nhận khác nhau) để chặn regression.

### Tăng tốc: vá watermark THEO LÔ (batch) qua GPU thay vì tuần tự từng frame

Người dùng hỏi có cách nào chạy song song/dùng GPU nhanh hơn — GPU **đã** được dùng từ mục
96 (`device = "cuda" if torch.cuda.is_available() else "cpu"` ở cả Florence-2 lẫn LaMa),
nhưng vòng lặp vá từng frame gọi `SimpleLama` (thư viện `simple-lama-inpainting`) tuần tự
TỪNG ẢNH MỘT — crop nhỏ (~220×200px) nên 1 lượt forward đơn không tận dụng hết GPU, phần
lớn thời gian là overhead Python/khởi chạy kernel per-call, không phải tính toán thật.

**Giải pháp**: đọc source `simple-lama-inpainting` cài trên máy xác nhận model là 1
`torch.jit.load(...)` FCN thuần — bản thân model NHẬN batch dim bất kỳ bình thường, chỉ có
wrapper `SimpleLama.__call__` ép cứng batch=1. Thêm `remover.py::inpaint_regions_batch_
cropped` — bypass wrapper, tự dựng batch qua `prepare_img_and_mask` (hàm nội bộ của chính
thư viện đó) + `torch.cat`, chạy LaMa 1 lượt cho N frame (mọi frame video cùng độ phân
giải → cùng bbox/context_pad → cắt ra cùng kích thước crop, ghép batch trực tiếp được).
`pipeline.py`'s vòng lặp đổi từ 1 frame/lần sang lô 8 frame/lần (`_INPAINT_BATCH_SIZE`).
`inpaint_region_cropped` (đơn) giữ lại làm ca N=1 của hàm batch, không lặp code, không phá
API cũ.

**Đo thật** (`wm_bench.py`, GPU RTX 5060 Ti, video 640×480, 64 frame): tuần tự 3.14s
(49ms/frame) → batch=8 1.54s (24ms/frame) — nhanh gấp **~2 lần** (không phải suy đoán —
docstring ban đầu định ghi "4-6 lần" theo trực giác, SỬA lại đúng số đo thật sau khi
benchmark, đúng kỷ luật "verify thật, không suy đoán" của session này). Chưa thử batch
size khác 8 hoặc video/crop lớn hơn — có thể còn dư địa tăng thêm nếu cần, chưa đo.

**Verify**: sửa `test_watermark.py`'s test video (đổi mock từ `inpaint_region_cropped` cũ
sang `inpaint_regions_batch_cropped` mới, chữ ký nhận/trả list) — vẫn PASS không đổi hành
vi assert. Full `pytest` **499 passed** (498 trước + 1 test regression mới cho bug tmp_dir).

## 98. Bug thật (user tự phát hiện): xoá video gốc làm MẤT tag kênh của clip đã cắt + clip biến mất khỏi mọi kết quả matching + bulk gán tag kênh cho clip (2026-08-28)

Người dùng báo: xoá video gốc làm clip đã cắt từ video đó mất tag kênh. Đọc lại thiết kế
gốc (mục 91) xác nhận đây đúng là bug thiết kế, không phải hiển thị sai đơn thuần —
`ProcessedClip` TỪNG KHÔNG có tag kênh riêng, kênh CHỈ suy ra qua JOIN `raw_video_id` →
`raw_video` → `raw_video_channel`. `delete_raw_video` CỐ Ý không cascade xoá clip con
(clip đã cắt dùng độc lập, có thể đã gán vào shot project khác) — nhưng hệ quả là clip mất
SẠCH thông tin kênh, và (hệ quả NẶNG hơn, ẩn, không thấy ngay trên UI) `asset_vault/
matching.py::_clips_for_channel` INNER JOIN qua `RawVideo` nên clip mồ côi biến mất khỏi
MỌI kết quả matching B-roll Render Studio của MỌI kênh, dù file/caption/embedding vẫn còn
nguyên vẹn — 1 bug từng được "vá" một nửa ở mục 93 (chặn crash 500, trả `channels: []`)
nhưng chưa xử lý gốc rễ mất dữ liệu.

### Fix: `ProcessedClip` có tag kênh RIÊNG (`processed_clip_channel`, bảng m2m thứ 2 của dự án)

`models.py` — bảng `processed_clip_channel` mới + `ProcessedClip.channels`/`Channel.
processed_clips` relationship, SAO CHÉP từ `raw_video.channels` NGAY lúc cắt cảnh
(`ingest.py::_make_clip_row`, dùng chung cho cả `manual_cut_clip`/`auto_detect_scenes`) —
clip độc lập thật sự với raw_video cha từ đó, kể cả sau khi raw_video bị xoá.

`asset_vault/migration.py::_backfill_processed_clip_channel` (mới) — bảng mới hoàn toàn
nên `create_all()` tự tạo, hàm chỉ BACKFILL: clip nào chưa có dòng nào trong bảng mới VÀ
raw_video cha CÒN TỒN TẠI, sao chép kênh hiện tại của raw_video sang. Clip đã mồ côi TỪ
TRƯỚC (raw_video cha đã mất trước khi bản vá này chạy) — dữ liệu kênh gốc THẬT SỰ ĐÃ MẤT,
không có nguồn nào khác để khôi phục, cần người dùng tự gắn lại tay (endpoint mới bên dưới
chính là chỗ làm việc đó).

`asset_vault/matching.py::_clips_for_channel` — đổi từ INNER JOIN qua `RawVideo`/
`raw_video_channel` sang JOIN thẳng `processed_clip_channel` (tag riêng của clip) — không
còn phụ thuộc raw_video cha còn tồn tại hay không. Verify trực tiếp ở tầng này (không chỉ
qua router `/clips`) vì đây là nơi Render Studio THẬT SỰ gọi tới lúc gợi ý clip cho 1 shot.

`routers/asset_vault.py`:
- `_clip_out` đọc `c.channels` trực tiếp (không còn `_channels_out(c.raw_video)`).
- `GET /asset-vault/clips?channel_id=` lọc qua `processed_clip_channel` thay vì JOIN
  `RawVideo`.
- `PATCH /asset-vault/raw/{id}/channels` và `POST /asset-vault/raw/batch-tag-channels`
  (đã có từ mục 96) — thêm CASCADE: sửa/gắn thêm kênh ở mức raw video giờ ĐỒNG BỘ xuống
  MỌI clip con hiện có, giữ nguyên UX "1 control edit cả nhóm" người dùng đã quen.
- **Mới**: `PATCH /asset-vault/clips/{clip_id}/channels` (ghi đè tag RIÊNG của 1 clip,
  KHÔNG đụng raw_video cha — đường DUY NHẤT gắn lại tag cho clip đã mồ côi) và `POST
  /asset-vault/clips/batch-tag-channels` (bulk gán tag kênh cho NHIỀU clip đã chọn cùng
  lúc, union không ghi đè — đúng yêu cầu thứ 2 của người dùng trong cùng phản hồi này).

### Verify

7 test mới + 2 test cũ bổ sung assertion (`test_asset_vault.py`): cascade từ raw video
xuống clip (đơn + batch), 2 endpoint clip-level mới (đơn + batch, cả 2 nhánh input rỗng
400), clip cắt tự động/thủ công kế thừa đúng kênh raw_video cha, VÀ quan trọng nhất — viết
lại `test_list_clips_survives_orphaned_clip_after_raw_video_deleted` (từng assert
`channels: []` là ĐÚNG — giờ assert kênh ĐƯỢC GIỮ NGUYÊN sau khi xoá raw_video, cả qua
`GET /clips` lẫn qua filter `?channel_id=`) + test mới gọi thẳng `matching.py::
_clips_for_channel` sau khi xoá raw_video xác nhận clip vẫn được tìm thấy (hệ quả nặng
nhất của bug, trước đây không có test nào phủ tới tầng matching). Cập nhật `_seed_clip`
helper (dùng bởi rất nhiều test khác trong file) để gán đúng `clip.channels` — nếu không
sửa, hàng loạt test filter/matching theo kênh khác sẽ fail SAI (do giờ đọc tag riêng của
clip thay vì suy ra qua raw_video). Full `pytest` **506 passed** (499 trước + 7 mới).
`specs/02_database.md` cập nhật bảng `processed_clip`/`processed_clip_channel` mới.

**Frontend** (đã làm ngay sau, cùng lượt) — `AssetVault.tsx`: tách `RawChannelRetag` cũ
thành `ChannelRetag` DÙNG CHUNG (nhận `channels` + `onRetag` bất kỳ, không còn ép kiểu
`RawVideo`) — hàng "Clip đã cắt" giờ gọi `api.patchClipChannels` (sửa RIÊNG clip đó,
không cascade sang clip anh em/raw_video cha, hoạt động cả với clip mồ côi) thay vì
`api.patchRawVideoChannels` cũ. Thêm nút "+ Thêm kênh" bulk cho bảng "Clip đã cắt" (gọi
`POST /asset-vault/clips/batch-tag-channels` mới), cùng UI pattern nút bulk đã có ở bảng
"Video gốc" (mục 96). `tsc --noEmit` sạch.

## 99. Xoá watermark cho từng shot + toàn bộ block ở Visual Studio (tái dùng app/watermark/) (2026-08-28)

Theo yêu cầu người dùng: tự động phát hiện + xoá watermark trên ảnh/video từng shot ở
Visual Studio, cộng 1 nút xoá cho TOÀN BỘ slot, báo rõ ràng khi 1 ảnh không phát hiện
watermark. Đúng đúng ý đồ ban đầu của module `app/watermark/` (mục 96) — docstring lúc
build đã ghi "dự kiến từ Visual Studio sau này" — không cần đổi gì trong module đó,
CHỈ nối dây vào M2 Production Layer (render/engine.py, render/schemas.py, routers/render.py).

### Backend

`render/schemas.py` — `ShotRenderStatus.visual_watermark_note` (mới) — "không phát hiện
watermark" KHÔNG dùng `visual_error` (field đó gắn UI báo lỗi ĐỎ, dành cho lỗi thật như
model crash/ffmpeg thiếu) — tách field riêng để UI hiện thông báo trung tính, rõ ràng,
đúng yêu cầu người dùng "có thông báo rõ ràng" mà không đánh đồng với lỗi. `RenderState.
watermark_scan_summary` (mới, `WatermarkScanSummary{scanned,cleaned,no_watermark,failed,
finished_at}`) — tóm tắt 1 lượt xoá HÀNG LOẠT, vì rải `visual_watermark_note` riêng từng
shot dễ bị bỏ sót khi quét nhiều shot cùng lúc.

`render/engine.py` — `_remove_watermark_for_status` (dùng chung cho đơn lẻ/hàng loạt): xác
định ảnh/video qua `shot.get("visual_type")` (đọc pack.json, cùng cách `upload_shot_visual`
đã làm — module render CHỈ ĐỌC pack.json, không ghi lại, giữ đúng ranh giới script core ⟂
render đã có từ đầu dự án), gọi `remove_watermark_from_image`/`remove_watermark_from_video`
(y hệt chữ ký `app/watermark/pipeline.py` — KHÔNG sửa module đó), ghi kết quả TẠI CHỖ vào
`status` (path mới `_nowm`, hoặc `visual_watermark_note`, hoặc `visual_error`), trả về
`"cleaned"|"no_watermark"|"failed"`. `remove_shot_watermark`/`remove_all_shots_watermark`
(2 hàm mới, dùng cho BackgroundTasks) DÙNG CHUNG cờ `_mark_in_progress`/`is_generation_in_
progress` với sinh asset thường (`run_asset_generation`) — cố ý tái dùng ĐÚNG cơ chế chống
chạy chồng đã có (không tự chế lớp khoá riêng), vì đây CHÍNH LÀ lớp bug vừa sửa cho Kho Tài
Nguyên ở mục 97 (2 tiến trình cùng đụng file/state của cùng 1 project ghi đè lẫn nhau) —
tránh tái diễn ngay trong cùng phiên làm việc bằng cách bám đúng pattern đã có sẵn thay vì
nghĩ ra cách mới. `remove_all_shots_watermark` bỏ qua thầm lặng shot chưa `visual_status==
"ready"` (cùng nguyên tắc `approve_all_shots`), lỗi 1 shot không dừng cả batch (cùng
nguyên tắc `run_asset_generation`), check cờ huỷ trước mỗi shot (tái dùng `is_cancel_
requested` có sẵn — nút "⏹ Dừng" ở header đã hoạt động luôn cho cả thao tác này).

`routers/render.py` — 2 endpoint mới: `POST .../shots/{shot_id}/remove-watermark` (400 nếu
shot chưa `visual_status=="ready"`, set "generating" đồng bộ trước khi mở BackgroundTasks —
cùng pattern `regenerate-visual`) và `POST .../render/remove-watermark-all`. Cả 2 đều qua
`_require_not_in_progress` (409 nếu đang có tiến trình khác chạy) như mọi endpoint sinh
asset khác.

### Frontend (`VisualStudio.tsx`)

Nút "Xoá watermark" ở mỗi `ShotCard` (cạnh nút "Duyệt") — disable khi `visual_status!=
"ready"` hoặc có tiến trình khác đang chạy cho project. `status.visual_watermark_note`
hiện thành dòng chữ nhỏ, màu trung tính (KHÁC `uploadError`/lỗi đỏ) ngay dưới hàng nút.
Nút hàng loạt "Xoá watermark toàn bộ slot" gộp vào menu "⋯ Tuỳ chọn khác" (cùng nhóm các
hành động ít dùng/tốn thời gian như "Sinh lại TOÀN BỘ") — sau khi chạy xong, banner
`WatermarkSummaryBanner` mới (màu accent trung tính, chỉ chuyển đỏ nếu có shot lỗi thật)
tóm tắt "Đã quét N shot — X đã xoá watermark, Y không phát hiện watermark, Z lỗi", có nút
đóng (chỉ ẩn local, không gọi API xoá — lượt quét kế tiếp tự ghi đè summary mới). Tái dùng
ĐÚNG pattern polling/cache-bust đã có (`window.setTimeout(loadRenderStatus, 1200/3000)`
sau mỗi action nền, vì response POST phản ánh trạng thái TRƯỚC khi BackgroundTasks chạy —
bug thật bắt được lúc viết TEST cho tính năng này, xem bên dưới) — không thêm cơ chế mới.

**Bug thật bắt được lúc viết test (không phải sai ở code sản phẩm)**: test ban đầu assert
thẳng vào body của response POST `remove-watermark` để kiểm `visual_status`/`visual_
watermark_note` — LUÔN thấy `"generating"` dù mock chạy đồng bộ thành công, vì FastAPI
serialize `state.model_dump()` ở CÂU LỆNH `return` (bắt trạng thái TRƯỚC khi background
task chạy), không phải sau. Đối chiếu lại các test cũ (`test_regenerate_visual_resets_
approval`) xác nhận pattern ĐÚNG luôn phải là `POST` rồi `GET /render/status` RIÊNG để lấy
trạng thái mới nhất — sửa lại theo đúng pattern đó, không phải bug thật ở endpoint.

**Verify**: 7 test mới (`test_render.py`) — xoá thành công (đổi `visual_asset_path` sang
`_nowm`, xoá file cũ, dọn `visual_watermark_note`/`visual_error`), không phát hiện
watermark (giữ `visual_status=="ready"`, KHÔNG "error", asset gốc không đổi), lỗi thật
(set "error" + `visual_error`, không lẫn `visual_watermark_note`), 404 khi chưa có
`ShotRenderStatus`, 400 khi có state nhưng chưa `ready`, 409 khi có tiến trình khác đang
chạy, và hàng loạt với kết quả TRỘN (thành công/không tìm thấy/lỗi xen kẽ) xác nhận tổng
`watermark_scan_summary` khớp đúng từng loại + từng shot cập nhật đúng `visual_status`
tương ứng. Full `pytest` **513 passed** (506 trước + 7 mới). `tsc --noEmit` sạch.
`specs/03_api.md` cập nhật 2 endpoint mới.

**Chưa verify sống qua UI thật** — cùng lý do mục 96 (model Florence-2/LaMa thật ~90s nạp
lần đầu, giới hạn thời gian phiên làm việc) — logic điều phối đã verify đầy đủ qua test
tự động với model MOCK, chưa lặp lại bằng click thật trên Visual Studio với model thật.

## 100. Bug thật (user tự test với video Gemini/Veo thật): xoá watermark làm "mất hình ảnh" + làm rõ nguyên nhân lỗi "not found" ở Visual Studio (2026-08-28)

Người dùng báo 2 hiện tượng: (1) xoá watermark ở Kho Tài Nguyên cho video sinh bằng Gemini
(`L3B01.mp4`) làm video output MẤT HÌNH ẢNH; (2) bấm "Xoá watermark" ở Visual Studio báo
lỗi "not found", dẫn tới nhầm tưởng cần cấu hình Provider AI.

### Bug #1 — Florence-2 trả bbox GẦN NHƯ FULL-FRAME cho watermark dạng icon nhỏ (LaMa vá gần hết khung hình = phá huỷ nội dung)

**Root cause verify THẬT trên đúng file người dùng báo lỗi** (không suy đoán): tìm thấy
`workspace/asset_vault/raw/raw_1788341279704_L3B01.mp4` (video Gemini/Veo thật — cảnh bút
lông viết thư pháp chữ Hán, watermark thật là 1 icon NGÔI SAO LẤP LÁNH nhỏ ở góc dưới phải,
kiểu watermark chuẩn Gemini/Veo — khác hẳn watermark chữ/logo của video test tổng hợp trước
đây, mục 96). Trích đúng frame đại diện (20% thời lượng, giống pipeline thật dùng) rồi gọi
`detect_watermark_bboxes` thật: prompt mặc định `"watermark"` trả bbox `(1, 0, 1278, 719)`
— **99.6% diện tích khung hình**; `"logo"` cũng sai (78%). LaMa sau đó được giao vá gần hết
khung hình (mask phủ gần toàn bộ) → không còn đủ context thật để tham chiếu → sinh ảnh
NHOÈ/HALLUCINATE gần như xoá sạch nội dung gốc — đúng khớp "mất hình ảnh" người dùng báo.
Xác nhận thêm bằng CHÍNH file output THẬT còn sót lại trên máy dev (`..._L3B01_nowm.mp4`,
374KB — nhỏ bất thường so với gốc 3MB, dấu hiệu nội dung đã bị đồng nhất hoá/nén tốt hơn
hẳn) — trích frame từ file đó XÁC NHẬN BẰNG MẮT: cuộn giấy + chữ Hán biến mất hoàn toàn,
thay bằng 1 màu xám-xanh có vân sọc đều — đúng dấu hiệu LaMa hallucinate trên mask gần
full-frame, không phải suy đoán.

**Fix**: `detector.py::detect_watermark_bboxes_robust` (mới) — lọc bỏ MỌI bbox chiếm > 35%
diện tích khung hình (ngưỡng AN TOÀN, thấp hơn hẳn 2 lần đo sai 99.6%/78% nhưng đủ rộng cho
watermark to như dải chữ credit choán 1 góc lớn), rồi tự thử LẦN LƯỢT các prompt dự phòng
(`"logo"`, `"small icon in the corner"`) nếu prompt chính không cho bbox nào đủ nhỏ để tin
cậy. Verify lại THẬT trên ĐÚNG frame đã dùng để đo bug: prompt dự phòng `"small icon in the
corner"` (thử trực tiếp cả `"star icon"`/`"white star"`/`"four pointed star icon"` — đều
cho kết quả khớp) định vị ĐÚNG icon thật, bbox `(1130, 570, 1191, 629)` — chỉ 0.39% diện
tích, khít sát icon. Chạy `inpaint_region_cropped` thật trên bbox đúng này — kết quả ẢNH
GIỮ NGUYÊN TOÀN BỘ nội dung cuộn giấy/chữ Hán, chỉ mất đúng icon ngôi sao ở góc — xác nhận
bằng mắt qua ảnh output thật, không phải mock. `pipeline.py` (`remove_watermark_from_image`/
`remove_watermark_from_video`) đổi sang gọi `detect_watermark_bboxes_robust` thay vì
`detect_watermark_bboxes` trực tiếp — áp dụng cho CẢ Kho Tài Nguyên lẫn Visual Studio (mục
99, dùng chung `pipeline.py`) mà không cần sửa gì ở 2 nơi gọi đó.

**Verify**: 4 test mới (`test_watermark.py`) — mock `detect_watermark_bboxes` (cấp thấp,
gọi model) bằng bảng tra THEO PROMPT, dùng ĐÚNG giá trị bbox đã đo thật ở trên (không phải
số bịa) để verify logic lọc/fallback: bbox full-frame bị loại, tự chuyển sang prompt dự
phòng đúng, trả rỗng nếu MỌI prompt đều không đáng tin, và KHÔNG lãng phí gọi thêm prompt dự
phòng khi prompt chính đã đủ tin cậy (tránh chậm thêm không cần thiết cho trường hợp bình
thường). Full `pytest` **517 passed**.

**File dữ liệu thật của người dùng bị hỏng do bug NÀY** — `raw_1788341279704_L3B01_nowm.mp4`
hiện là bản THẬT ĐÃ HỎNG còn sót lại trên máy (dùng để chẩn đoán ở trên), file gốc có
watermark đã bị `remove_watermark_from_raw_video` XOÁ THẬT sau khi rename (không giữ bản
gốc) — người dùng cần tải/sinh lại `L3B01.mp4` từ Gemini rồi thử lại xoá watermark bằng
code đã vá; KHÔNG có cách khôi phục nội dung gốc từ file hỏng hiện có.

### Bug #2 — Không phải bug code: tiến trình backend do Electron spawn KHÔNG tự nạp lại code mới

Verify trực tiếp (không suy đoán): `electron/src/backend-launcher.ts::startBackend` chạy
`uvicorn app.main:app` KHÔNG có `--reload` — MỌI thay đổi code backend chỉ có hiệu lực sau
khi **tắt hẳn rồi mở lại app** (không phải chỉ điều hướng lại màn hình). Xác nhận đúng tiến
trình backend THẬT của app đang chạy trên máy người dùng lúc báo lỗi (`curl .../openapi.
json` tới đúng port tiến trình Electron con đang giữ) — tổng số route ÍT HƠN hẳn code hiện
tại, và **hoàn toàn không có** `POST /projects/{id}/render/shots/{shot_id}/remove-watermark`
(mục 99, viết SAU lần app này khởi động) — khớp chính xác lỗi "not found" (404 mặc định của
FastAPI khi không route nào khớp, không phải lỗi từ code endpoint). Tiến trình đó VẪN đang
chạy tính tới lúc điều tra, nghĩa là nếu người dùng thử lại NGAY (chưa khởi động lại app) sẽ
còn gặp lỗi này, VÀ vẫn dính bug #1 (chưa có bản vá `detect_watermark_bboxes_robust`).

**Không sửa code cho bug này** — đây là hành vi vốn có của kiến trúc dev hiện tại (uvicorn
không `--reload` khi Electron tự spawn), không phải lỗi logic. Đã cân nhắc thêm `--reload`
cho nhánh dev nhưng KHÔNG làm — uvicorn `--reload` trên Windows spawn thêm 1 tiến trình con
qua watcher, `backendProcess.kill()` hiện tại (Electron `main.ts`) chỉ kill tiến trình con
TRỰC TIẾP, rủi ro để lại tiến trình backend mồ côi mỗi lần tắt app (đổi 1 bug hiếm gặp lấy 1
rủi ro rò rỉ tiến trình thường trực) — báo lại người dùng: **tắt hẳn app (không chỉ đóng cửa
sổ/chuyển màn) rồi mở lại** mỗi khi có bản vá backend mới, thay vì đổi kiến trúc.

## 101. Thanh tiến trình THẬT khi xoá watermark ở Visual Studio (dùng chung component với Kho Tài Nguyên) (2026-09-02)

Người dùng xác nhận bug mục 100 đã hết (S3-01 xoá watermark thành công), đề xuất UX: hiện
thanh tiến trình khi xử lý xoá watermark ở Visual Studio, giống hệt thanh đã có ở Kho Tài
Nguyên (`RawVideo.progress_current/total/label`) — trước đó Visual Studio chỉ hiện chữ tĩnh
"Đang xử lý..." trên nút, không có % hay số frame.

### Backend

`render/schemas.py::ShotRenderStatus` — 3 field mới `visual_watermark_progress_current/
total/label` (Optional int/int/str) — CHỈ có giá trị cho shot VIDEO (ảnh vá 1 lượt Florence-
2+LaMa duy nhất, quá nhanh để cần %); null khi không có lượt xoá watermark nào đang chạy.
Không cần migration (Pydantic model sống trong `render.json`, không phải bảng SQL).

`render/engine.py::_remove_watermark_for_status` — thêm tham số `on_progress`, truyền
THẲNG vào `remove_watermark_from_video(..., on_progress=on_progress)` (hàm này đã tự gọi
callback mỗi ~8 frame từ mục 97, không cần sửa gì ở `watermark/pipeline.py`). Dọn 3 field
progress về `None` trong `finally` — chạy ở MỌI nhánh thoát (thành công/lỗi/không tìm
thấy), nút quay lại đúng trạng thái tĩnh thay vì kẹt hiện % cũ. `remove_shot_watermark`/
`remove_all_shots_watermark` mỗi hàm tự đóng 1 closure `_on_progress` ghi field vào đúng
`status` của shot đang xử lý RỒI `save_render_state` NGAY (cùng đơn vị "mỗi lần gọi
callback = 1 lần ghi file" như `ingest.py`'s `RawVideo` — file `render.json` nhỏ, ghi mỗi
~8 frame không đáng lo hiệu năng).

### Frontend

Tách `ProgressBar` (trước đây định nghĩa RIÊNG trong `AssetVault.tsx`) thành component dùng
chung `components/ProgressBar.tsx` — giữ NGUYÊN style/logic, Kho Tài Nguyên đổi sang import
từ đây (không đổi hành vi). `VisualStudio.tsx::ShotCard` hiện `<ProgressBar>` ngay dưới hàng
nút action khi `visual_watermark_progress_total` có giá trị — đúng vị trí/kiểu dáng người
dùng yêu cầu ("tương tự thanh tiến trình ở Kho Tài Nguyên"), tự động ẩn/hiện theo poll 3s có
sẵn (`hasInFlight`), không cần thêm cơ chế polling riêng.

**Verify**: test mới `test_remove_shot_watermark_reports_progress_then_clears_it` — spy
`save_render_state` (TestClient chạy BackgroundTasks đồng bộ, không polling HTTP giữa
chừng được) xác nhận progress ĐƯỢC GHI THẬT vào file mỗi lần callback gọi (khớp giá trị
10/20 rồi 20/20), VÀ trạng thái cuối cùng đã dọn sạch về `None` cả 3 field. Full `pytest`
**518 passed** (517 trước + 1 mới). `tsc --noEmit` sạch.

## 102. Bulk xoá clip đã cắt ở Kho Tài Nguyên (2026-09-02)

Bảng "Clip đã cắt" đã có multi-select (dùng cho bulk gắn nhãn/tag kênh từ mục 94/98) nhưng
chưa có hành động XOÁ hàng loạt — chỉ xoá được từng clip 1. Thêm `POST /asset-vault/clips/
batch-delete` (mirror `batch_delete_raw_videos` — lặp qua từng clip gọi `ingest.
delete_processed_clip` thay vì 1 câu SQL DELETE hàng loạt, vì cần dọn file trên đĩa + vector
Chroma cho từng clip, không chỉ xoá hàng DB). Frontend: nút "Xoá" (màu đỏ) trong thanh bulk
action, cùng vị trí/kiểu dáng các nút bulk khác, có `confirm()` trước khi xoá thật. 2 test
mới (`test_batch_delete_clips_removes_files_and_rows`, `..._rejects_empty_list`). Full
`pytest` **520 passed**. `tsc --noEmit` sạch.

## 103. "Method Not Allowed" ở bulk-xoá clip (backend chưa restart) + bug thật phát hiện lúc kiểm tra: `assign_vault_clip` lọc kênh SAI query sau khi clip có tag riêng (mục 98) (2026-09-02)

Người dùng báo bấm bulk-xoá clip (mục 102) ra lỗi "Method Not Allowed", và hỏi liệu xoá
clip có làm shot ĐÃ GÁN clip đó ở Visual Studio hết dùng được không.

**"Method Not Allowed" — xác nhận lại KHÔNG phải bug code**: check trực tiếp tiến trình
backend app đang chạy (`curl .../openapi.json`) — vẫn là tiến trình CŨ (122 route, không
có `/asset-vault/clips/batch-delete`), cùng nguyên nhân "chưa tắt hẳn app rồi mở lại" đã
gặp ở mục 100. Giải thích thêm TẠI SAO lỗi cụ thể là 405 (không phải 404 như mục 100) —
Starlette khớp `POST /asset-vault/clips/batch-delete` với path pattern
`/asset-vault/clips/{clip_id}` (khớp "PARTIAL" — coi "batch-delete" là 1 giá trị `clip_id`
hợp lệ) của 2 route PATCH/DELETE đã có sẵn — path khớp nhưng method không khớp route nào =
405, khác hẳn path không khớp gì cả = 404.

**Trả lời câu hỏi về matching**: xoá 1 clip KHÔNG làm hỏng shot ĐÃ GÁN clip đó trước đó —
verify qua đọc code `assign_vault_clip` (`render.py`): lúc gán, file được COPY hẳn vào
`assets/{shot_id}.<ext>` RIÊNG của project (`shutil.copy2`), không tham chiếu sống tới file
trong Kho — xoá clip sau đó không đụng tới bản copy này. `linked_clip_id` (ID tham chiếu
còn lại trong `render.json`) trở thành tham chiếu "chết" vô hại — `guardrail.py` đã tự xử
lý `clip is None` (bỏ qua cảnh báo rights, không crash). Hệ quả ĐÚNG duy nhất: clip đã xoá
không còn được GỢI Ý/GÁN cho shot MỚI nữa — đúng ý nghĩa của việc xoá.

**Bug thật phát hiện lúc kiểm tra kỹ câu hỏi này** — `assign_vault_clip` (`render.py`)
lọc kênh của clip khi gán qua JOIN `raw_video_channel` (kênh của `raw_video` CHA) — sót lại
TỪ TRƯỚC khi `ProcessedClip` có tag kênh RIÊNG (mục 98, lúc đó chỉ sửa `matching.py::
_clips_for_channel` cho danh sách GỢI Ý, quên mất hàm GÁN THẬT này cũng cần đổi tương tự).
Hệ quả: (1) clip mồ côi (raw_video cha đã bị xoá) VẪN hiện đúng trong danh sách gợi ý
(matching.py đã fix) nhưng KHÔNG BAO GIỜ gán được — JOIN `RawVideo` không còn hàng nào để
khớp, 404 "Không tìm thấy clip"; (2) clip đã tự sửa tag kênh riêng (khác kênh của
raw_video cha) bị lọc SAI theo kênh CŨ. Fix: đổi sang JOIN `processed_clip_channel` (tag
riêng của clip), khớp đúng `matching.py`. Test mới `test_assign_vault_clip_works_for_clip_
whose_raw_video_was_deleted` (xoá raw_video cha rồi gán clip mồ côi vào shot — trước fix sẽ
404, sau fix 200) tái hiện đúng bug #1 ở trên. Full `pytest` **521 passed**.

## 104. Bug thật: xoá trắng `motion_tone`/`cultural_lock_negative` ở Sửa BrandProfile rồi lưu — mở lại vẫn còn giá trị cũ + kênh mới tạo không trống hẳn (2026-09-02)

Người dùng tự test: xoá trắng 2 field "Tông chuyển động video AI local (motion_tone)" và
"Loại trừ văn hoá ngoại lai (cultural_lock_negative)" rồi lưu — mở lại dialog vẫn thấy giá
trị cũ, như chưa lưu được. Đồng thời yêu cầu: kênh MỚI TẠO nên có các trường trống hẳn.

**Root cause verify thật (đọc code, không suy đoán) — bug nằm HOÀN TOÀN Ở FRONTEND, backend
lưu/đọc đúng**: `PUT /channels/{id}/brandprofile` (`routers/channels.py`) là full-replace,
`body.model_dump()` KHÔNG có `exclude_unset`/`exclude_none`/truthy-check nào — chuỗi rỗng
gửi lên được ghi đúng nguyên văn vào `brandprofile.json`. Bug thật ở `ChannelDialog.tsx::
draftFromProfile` — 2 field NÀY (khác MỌI field khác trong cùng hàm, vốn đều `|| ""`) dùng
`bp.motion_tone || "chuyển động chậm, tinh tế..."` / `bp.cultural_lock_negative || "japanese
kimono..."` — chuỗi rỗng THẬT SỰ đã lưu (falsy trong JS) bị coi giống hệt "chưa có giá trị",
form tự điền lại đúng cụm gợi ý cũ (trùng khớp default cũ của SCHEMA, mục 58 file schemas),
trông y hệt "chưa lưu được" dù backend đã lưu đúng chuỗi rỗng. `emptyDraft()` (form kênh
MỚI TẠO) cũng ghim cứng 2 cụm gợi ý này làm giá trị THẬT thay vì để trống — cộng thêm
`BrandProfile` Pydantic schema (`schemas/__init__.py`) TỪNG có default không rỗng cho cả 2
field — kênh mới tạo (`BrandProfile(channel_id=cid, niche=...)`, không truyền 2 field này)
tự nhận default không rỗng đó.

### Fix

`schemas/__init__.py` — đổi default `motion_tone`/`cultural_lock_negative` về `""`. `Channel
Dialog.tsx`: `emptyDraft()` đổi 2 field về `""`; `draftFromProfile()` đổi `|| "<gợi ý cũ>"`
thành `|| ""` (khớp mọi field khác trong hàm) — sửa ĐÚNG gốc rễ bug xoá-không-lưu-được. Gợi ý
cũ KHÔNG mất hẳn — chuyển thành `placeholder` (chữ mờ trong ô nhập, không phải giá trị thật)
ở JSX, cùng pattern `motionTone`'s input đã có sẵn placeholder từ trước (chỉ `culturalLock
Negative`'s textarea là thiếu, đã thêm). `render/engine.py` đọc 2 field này qua `brand.get(
...) or ""` rồi CHỈ nối vào prompt nếu non-empty (`if motion_tone: ...`) — đã tự xử lý rỗng
gracefully từ trước, không cần sửa gì (kênh không tuỳ biến field này sẽ không có ràng buộc
chuyển động/loại trừ văn hoá trong prompt — đánh đổi CÓ CHỦ Ý, đúng yêu cầu "trống hẳn"
người dùng, không âm thầm áp default ẩn nữa).

**Verify**: 2 test mới (`test_channels.py`) — kênh mới tạo có `motion_tone`/`cultural_lock_
negative` rỗng đúng qua API thật; PUT ghi giá trị rồi PUT lại chuỗi rỗng, GET lại xác nhận
rỗng (verify riêng phần BACKEND đã đúng từ trước, phân biệt rõ với bug thật ở frontend).
Full `pytest` **523 passed**. `tsc --noEmit` sạch.

## 105. Visual Studio: tắt hẳn overlay khi đang kế thừa kênh + chuyển Thumbnail sang Output Center (2026-09-02)

Theo yêu cầu người dùng (1 trong 4 cải tiến Visual Studio đề xuất cùng lúc — 2 mục dưới đây
đã làm, 2 mục còn lại xem phần hỏi thêm ở cuối phiên làm việc).

### Cho phép tắt hẳn overlay khi đang kế thừa từ kênh

Trước đây `DELETE /projects/{id}/render/overlay` chỉ xoá ASSET RIÊNG của project rồi quay
về dùng overlay mặc định cấp kênh (fallback ngầm) — không có cách nào tắt hẳn overlay khi
project ĐANG kế thừa (không có override riêng để mà xoá). Đổi hành vi giống hệt
`delete_intro`/`enable_intro_inherit` đã có sẵn cho shot mở đầu: `OverlayEffectOverride`
thêm field `disabled: bool` (mới) — `DELETE .../overlay` giờ LUÔN set `disabled=True` (xoá
file riêng nếu có), `PATCH .../overlay/inherit` (endpoint mới) đặt lại `False`. `overlay.py::
resolve_overlay_source` kiểm `disabled` TRƯỚC TIÊN — bỏ qua cả brand default nếu `True`.
Upload overlay mới tự đặt lại `disabled=False` (chắc chắn muốn DÙNG). Frontend
`OverlayEffectCard`: nút "Bỏ hiệu ứng lớp phủ" giờ hiện CẢ khi đang kế thừa (trước chỉ hiện
khi đã có asset riêng), thêm nút "Dùng lại mặc định thương hiệu" khi đã tắt, thêm tag "Đã
tắt — không dùng overlay". 8 test mới (`test_overlay.py`, mirror các test tương ứng của
intro). Full `pytest` **527 passed** (1 fail/1 error không liên quan — flaky do state SQLite
chia sẻ giữa module test, PASS khi chạy riêng, không phải do thay đổi này).

### Chuyển block Thumbnail từ Visual Studio sang đầu Output Center

`ThumbnailCard` (không phụ thuộc state riêng của Visual Studio, chỉ cần `project`/`pack`/
`refresh` — cả 3 đều có sẵn qua `StepProps`) — di chuyển nguyên component + hằng số
`DEFAULT_YOUTUBE_META` từ `VisualStudio.tsx` sang đầu `OutputCenter.tsx` (trước cả
`PackExportCard`/`RenderStudio`/`RetentionCard`) — đúng ngữ cảnh "dùng lúc xuất video lên
YouTube" hơn là Visual Studio (nơi tập trung sinh ảnh/video/giọng đọc từng shot). Không đổi
logic/API nào, chỉ đổi VỊ TRÍ render. `tsc --noEmit` sạch.

**2 mục còn lại của yêu cầu 4 cải tiến**: "hiệu ứng chuyển cảnh cho shot mở đầu" hoá ra ĐÃ
CÓ SẴN đầy đủ từ trước (cả FE dropdown lẫn BE áp dụng qua `_xfade_chain`, y hệt shot-to-shot
— xem `IntroShotCard`/`assembly.py:1167`), không cần sửa gì — đã báo lại người dùng xác
nhận. "Video nền chung cho toàn bộ block, per-shot visual đè lên trên khi tới slot đó" là
tính năng KIẾN TRÚC MỚI, có nhiều điểm mơ hồ về hành vi (shot không cấu hình visual có được
BỎ QUA validation hiện tại không, video nền có SLICE liên tục theo timeline hay loop riêng
từng slot...) — đã hỏi lại người dùng làm rõ trước khi thiết kế, chưa triển khai trong mục
này.

## 106. Video nền chung cho toàn bộ block ở Visual Studio (mục cuối trong 4 cải tiến người dùng yêu cầu) (2026-09-02)

Sau khi hỏi lại 2 điểm mấu chốt còn mơ hồ (xem mục 105) — người dùng chọn: (1) shot CHƯA
cấu hình visual riêng được phép BỎ TRỐNG (không còn bắt buộc mọi shot phải có ảnh/video),
đoạn thời gian đó tự hiện đúng đoạn video nền tương ứng trên timeline CHUNG (không loop
riêng từng shot); (2) shot ĐÃ có visual riêng THAY THẾ TOÀN MÀN HÌNH (không phải chồng
mờ/PiP) trong đúng khoảng thời gian của nó.

### Data model + endpoint (mirror bg_music/overlay, đơn giản hơn — không có cấp kênh)

`render/schemas.py::BackgroundVideoOverride` (mới, field DUY NHẤT `asset_path`) —
`RenderState.background_video`. KHÁC bg_music/overlay: KHÔNG có field volume/opacity (chỉ
lấy HÌNH, audio luôn bỏ qua — giọng đọc/nhạc nền vẫn là nguồn audio duy nhất, đúng nguyên
tắc mọi visual video khác trong app), và KHÔNG có cấp kênh mặc định để "inherit" (đúng
phạm vi yêu cầu, tránh over-engineer thêm 1 lớp kế thừa không ai hỏi tới). 3 endpoint mới
(`routers/render.py`): `POST .../background-video/upload`, `DELETE .../background-video`,
`GET .../background-video/asset` — mirror `upload_project_overlay`/`delete_project_bg_
music` gần như nguyên vẹn.

### Assembly (`app/render/assembly.py::assemble_video`) — phần việc chính

**Pass 1 (validate)** — đổi từ chặn cứng MỌI shot phải `visual_status=="ready"` sang: shot
CÓ visual riêng vẫn giữ NGUYÊN yêu cầu `ready`+`approved` (human-gate không đổi cho nội
dung ĐÃ cấu hình); shot KHÔNG có visual chỉ raise lỗi khi `background_video_source` KHÔNG
được cấu hình (giữ nguyên hành vi gốc cho project chưa dùng tính năng này). Phát hiện hữu
ích lúc đọc code: `_shot_base_duration`/`_reflow_video_durations` ĐÃ SẴN hoạt động đúng
cho shot trống (chỉ đọc `narration_duration_sec`, không đụng `visual_asset_path`) — không
cần sửa gì ở 2 hàm đó, tiết kiệm đáng kể công sức so với dự tính ban đầu.

**2 hàm ffmpeg mới** — `_build_background_video_master` (dựng 1 bản loop `-stream_loop -1`
đúng nguồn upload, cắt đủ `sum(durations)` SAU khi đã cộng đệm lead-in/out transition,
scale/color-grade CHỈ 1 LẦN ở đây — tránh lặp lại xử lý cho mỗi chunk) rồi `_extract_
background_video_chunk` (cắt ĐÚNG `[offset_cộng_dồn, offset+duration)` cho từng shot
trống — `-ss` TRƯỚC `-i` + RE-ENCODE, không stream-copy, để seek CHÍNH XÁC theo khung
hình, tránh hở/đè giữa các chunk nối tiếp). Offset cộng dồn tính theo ĐÚNG thứ tự shot
trên timeline — khớp yêu cầu "không phân biệt cảnh/slot" (video nền như đang chạy LIÊN
TỤC phía sau suốt cả video, shot có visual riêng chỉ "che" tạm 1 đoạn rồi trả lại đúng
chỗ nền đang ở).

**Pass 2 (build segment)** — TÁI DÙNG NGUYÊN `_build_segment` cho shot trống (truyền
đường dẫn CHUNK đã cắt sẵn làm `visual_path` thay vì `status.visual_asset_path`) — không
cần viết pipeline song song riêng, tự động thừa hưởng mọi xử lý sẵn có (scale/crop, color
grade, ghép narration, đệm transition) mà không cần code thêm.

### Frontend

`BackgroundVideoCard` (mới, `VisualStudio.tsx`) — mirror `OverlayEffectCard`/`BgMusicCard`
nhưng đơn giản hơn (không có volume/opacity slider, không trạng thái "kế thừa"), đặt ngay
sau "Hiệu ứng lớp phủ riêng". Copy chú thích rõ KHÁC overlay: "thay THẾ HẲN cho slot chưa
cấu hình" thay vì "đè mờ liên tục".

### Verify

**Test end-to-end THẬT với ffmpeg thật** (`test_background_video.py`, mới) — dựng project
2 shot: shot A có video ĐỎ thuần + narration riêng, shot B HOÀN TOÀN TRỐNG (không visual)
chỉ có narration để biết thời lượng; video nền XANH DƯƠNG thuần, cố tình NGẮN hơn hẳn
tổng timeline (1s so với tổng ~4s) để verify luôn cả việc LOOP hoạt động đúng. Gọi
`assemble_video()` thật — xác nhận: (1) KHÔNG bị chặn dù shot B chưa có visual, (2) tổng
thời lượng khớp tổng 2 narration, (3) trích frame giữa khoảng shot A ra ĐÚNG màu đỏ (giữ
visual riêng), (4) trích frame giữa khoảng shot B ra ĐÚNG màu xanh dương (lấp đúng đoạn
nền tương ứng, không lệch). Cộng 5 test CRUD endpoint đơn giản. Full `pytest` **534
passed**. `tsc --noEmit` sạch. `specs/03_api.md`/`specs/04_data_schemas.md` cập nhật đầy
đủ endpoint + field mới (bao gồm cả `overlay.disabled`/`render/overlay/inherit` của mục
105 mà lượt trước chưa kịp đồng bộ vào specs).

## 107. Visual Studio: cho phép xoá ảnh/video từng shot + bỏ gate "duyệt" trước khi ghép video (2026-09-02)

Theo yêu cầu người dùng: "Cho phép remove video/image ở từng shot/block sau khi đã add" +
"Bỏ luồng duyệt block, ko cần phải có thì mới render được video".

### Xoá ảnh/video của 1 shot

Trước đây CHỈ có 2 cách đổi visual của shot: sinh lại (AI) hoặc upload/gán clip Kho —
CẢ HAI đều THAY THẾ, không có cách nào XOÁ về trạng thái trống mà không phải thay ngay
bằng cái khác. Endpoint mới `DELETE /projects/{id}/render/shots/{shot_id}/visual`
(`routers/render.py`) — mirror pattern `delete_intro`/`delete_project_overlay`: xoá file
trên đĩa (`unlink_retrying`), reset `ShotRenderStatus` về `visual_status="pending"`
(`visual_asset_path`/`visual_provider`/`linked_clip_id`/`visual_watermark_note` = `null`,
`approved=false`). 404 nếu chưa từng có render.json entry cho shot (khác `upload-visual`
tự tạo entry — ở đây không có gì để xoá nên báo lỗi thẳng thay vì tạo entry rỗng vô
nghĩa). `_require_not_in_progress` chặn chồng lên batch/regenerate khác đang chạy, cùng
nguyên tắc mọi endpoint mutate render.json khác.

Frontend: nút "Xoá ảnh/video" (màu cảnh báo, `color: var(--color-danger)`) ở mỗi
`ShotCard` — CHỈ hiện khi `status?.visual_asset_path` có giá trị (không có gì để xoá thì
không hiện nút). `api.removeShotVisual` (client.ts, dùng `del<RenderState>`).

### Bỏ gate "duyệt" trước khi ghép video

Yêu cầu rõ ràng, không mơ hồ — bỏ HẲN, không giữ dạng "tuỳ chọn nhưng vẫn nhắc nhở". Xoá
gate ở **3 lớp** (bỏ sót 1 lớp là tính năng coi như chưa xong — phát hiện lúc rà lại code,
xem "Phát hiện thêm lúc rà soát" bên dưới):

1. **`assembly.py::assemble_video` Pass 1`** — xoá khối `if not status.approved: raise
   RuntimeError(...)`, chỉ còn giữ `visual_status != "ready"` là điều kiện chặn.
2. **`routers/render.py::start_assemble`** — xoá biến `not_approved`/check tương ứng (400
   "chưa được duyệt"). Đồng thời sửa LUÔN check `not_ready` cho khớp `assembly.py` (bug có
   sẵn từ mục 106, chưa ai phát hiện ra: router chưa hề trừ trường hợp shot KHÔNG có visual
   riêng NHƯNG project có `background_video` — trước đây LUÔN 400 "chưa sinh xong visual"
   dù `assemble_video()` thực ra CHO PHÉP trường hợp này, tức tính năng video nền chung mục
   106 chưa từng dùng được qua HTTP thật, chỉ chạy qua test gọi thẳng `assemble_video()`).
3. **`RenderStudio.tsx` (Output Center) — nút "Ghép video"** — đây là chỗ CHẶN THẬT SỰ mà
   người dùng nhìn thấy: `disabled={!allApproved || assembling}` (tính từ
   `approvedCount === shots.length`). Nếu chỉ sửa 2 lớp backend ở trên mà bỏ sót lớp này,
   backend đã cho phép ghép không cần duyệt nhưng nút bấm trên UI vẫn khoá — coi như CHƯA
   sửa gì từ góc nhìn người dùng. Đổi sang `canAssemble` tính từ `notReadyCount` (chỉ còn
   xét `visual_status`, có tính luôn ngoại lệ shot trống khi có `background_video`, khớp
   logic router ở lớp 2). Xoá dòng hiển thị "X/Y đã duyệt" + hint "bấm Duyệt" khỏi card
   "Tình trạng shot".

**Xoá UI "Duyệt" khỏi Visual Studio** — giữ nút "Duyệt" vô hiệu (không còn chặn gì) sẽ gây
hiểu lầm là vẫn cần bấm. Xoá HẲN khỏi `VisualStudio.tsx`: nút header "Duyệt toàn bộ block
(N)", nút per-shot "Duyệt"/"Đã duyệt" ở `ShotCard`, tag "Đã duyệt", state
`pendingApprovalCount`/`approvingAll`, hàm `approveAsset`/`approveAllAssets`. **Backend giữ
nguyên** `POST .../approve`, `POST .../approve-all`, field `ShotRenderStatus.approved` —
xoá hẳn field/endpoint tốn công dọn nhiều chỗ (export pack, mọi test dựng
`ShotRenderStatus(approved=True)` sẵn có) mà không mang lại lợi ích thật (field không gây
hại gì khi không ai đọc để gate nữa) — giữ lại làm cờ tuỳ chọn, không có UI nào gọi tới.
`client.ts` cũng giữ nguyên `approveShotAsset`/`approveAllShots` (không dùng, không hại).

### Test

Sửa `test_assemble_requires_all_shots_ready_and_approved` (kỳ vọng cũ: 400 khi chưa duyệt)
thành 2 test: `test_assemble_requires_all_shots_ready` (400 khi CHƯA sinh asset — vẫn còn
gate hợp lệ) + `test_assemble_does_not_require_approval` (200 dù không shot nào được
duyệt — xác nhận đúng hành vi mới). Thêm 6 test mới cho `DELETE .../visual`: xoá thành
công (reset đúng field + xoá file đĩa), xoá clip Kho tư liệu đã gán (`linked_clip_id` về
`null`, clip KHÔNG bị xoá khỏi Kho), 404 khi chưa có render.json entry, 404 shot không tồn
tại, 409 khi có tiến trình khác đang chạy, và 1 test xác nhận xoá visual của shot (không
có background_video) làm shot đó CHẶN LẠI được `render/assemble` (400) — không phải lỗi
500 bất ngờ ở tầng ffmpeg. Full `pytest` **541 passed**. `tsc --noEmit` sạch.
`specs/03_api.md`/`specs/04_data_schemas.md` cập nhật endpoint mới + ghi rõ `approved`
không còn được kiểm.

## 108. Progress bar lúc ghép video hiện SAI khi có dùng video nền chung (2026-09-02)

Theo yêu cầu người dùng: "Phần progress bar khi render video cần điều chỉnh để hiển thị
phù hợp trong trường hợp có sử dụng video nền chung."

### Bug thật

`assemble_video` (`assembly.py`) đặt `assembly_progress = AssemblyProgress(stage=
"segments", current=0, total=len(shots))` NGAY ĐẦU hàm (có `total` sớm để UI hiện số
ngay) — nhưng khi project CÓ cấu hình video nền chung (mục 106), bước dựng video nền
(`_build_background_video_master` — re-encode LOOP phủ hết TOÀN BỘ tổng thời lượng
timeline, có thể mất VÀI PHÚT với video dài, LÀ BƯỚC CHẬM NHẤT trong cả assembly nếu có
dùng tính năng này) chạy NGAY SAU đó, TRƯỚC Pass 2 (segment thật) — nhưng KHÔNG hề cập
nhật lại `assembly_progress` trong suốt bước này. Kết quả: `RenderStudio.tsx` hiện
"Đang ghép cảnh 0/N..." SUỐT thời gian dựng video nền — trông y hệt bị treo ở segment
đầu tiên, dù thực ra chưa có segment nào bắt đầu. Phát hiện lúc đọc lại code theo yêu cầu
người dùng (không phải bug người dùng tự report trước, dù đúng là nguyên nhân cảm giác
"progress bar hiển thị không đúng" họ mô tả).

### Fix — stage riêng + mốc thời gian riêng cho từng stage

`AssemblyProgress` (`schemas.py`) thêm:
- `stage` thêm giá trị `"background_video"` (cùng `"segments"`/`"concat"` cũ).
- `stage_started_at: str | null` — mốc STAGE HIỆN TẠI bắt đầu, KHÁC `RenderState.
  assembly_started_at` (mốc TOÀN BỘ assembly, vẫn giữ nguyên vai trò hiện "Đã chạy: X").

`assembly.py::assemble_video` — trước khi gọi `_build_background_video_master`, set
`stage="background_video", current=0, total=1+len(blank_indices)` (đơn vị tự nhiên: 1
cho bước dựng master + 1 cho mỗi chunk cắt riêng từng shot trống), lưu `render.json`
NGAY (không đợi ffmpeg chạy xong mới ghi). Sau khi master xong → `current=1`. Sau MỖI
chunk cắt xong (`_extract_background_video_chunk`, trong vòng lặp theo shot trống) →
`current += 1`, lưu lại. Ngay TRƯỚC KHI Pass 2 (ThreadPoolExecutor build segment thật)
bắt đầu — reset LẠI `AssemblyProgress(stage="segments", current=0, total=len(shots))`
với `stage_started_at` MỚI (biến `segments_stage_started_at`, capture 1 lần, dùng lại
cho MỌI lần cập nhật `current` trong vòng lặp Pass 2 — không phải mốc mới mỗi lần 1
segment xong). Nếu không reset mốc này, ước lượng "còn lại" ở FE (`remainingSec =
elapsed/current * (total-current)`) sẽ TÍNH GỘP luôn thời gian đã tốn ở bước dựng video
nền vào "elapsed", thổi phồng sai lệch ETA ngay từ segment đầu tiên hoàn thành (VD dựng
nền tốn 3 phút, 1 segment đầu xong sau 5s nữa → công thức cũ tưởng "trung bình 3 phút
5s/segment", ước lượng còn lại sai theo cấp số nhân).

`RenderStudio.tsx`: `stageElapsedSec` (mới) tính từ `progress.stage_started_at` thay vì
`elapsedSec` (từ `assembly_started_at`) khi tính `remainingSec` — chỉ áp dụng
`stage==="segments"` (giữ nguyên guard cũ, `background_video`/`concat` vẫn hiện "Đang ước
lượng..." như trước, đúng vì KHÔNG có cách tính ETA đáng tin cho 2 stage này). Label
riêng cho `stage==="background_video"`: "Đang dựng video nền chung (X/Y)... — video dài
có thể mất vài phút" — thay vì mượn nhầm label "Đang ghép cảnh" của stage segments.
`current`/`total` mới của stage này (không phải hằng số 0) cũng làm thanh progress nhích
dần thay vì đứng yên tuyệt đối.

### Test

Test mới `test_assemble_reports_background_video_stage_progress_before_segments`
(`test_background_video.py`, ffmpeg thật) — spy quanh CẢ 3 hàm ffmpeg liên quan
(`_build_background_video_master`, `_extract_background_video_chunk`, `_build_segment`),
đọc LẠI `render.json` NGAY TRƯỚC mỗi lần gọi (không suy đoán từ log) — xác nhận: (1) lúc
gọi dựng master, `assembly_progress` ĐÃ LÀ `stage="background_video", current=0,
total=2`; (2) lúc cắt chunk, `current=1`; (3) lúc Pass 2 gọi `_build_segment` lần đầu,
`stage` đã chuyển hẳn `"segments"` VÀ `stage_started_at` là mốc MỚI, khác hẳn mốc của
stage `background_video` (xác nhận ETA không bị gộp elapsed sai). Full `pytest` **542
passed**. `tsc --noEmit` sạch. `specs/04_data_schemas.md` bổ sung mô tả đầy đủ
`assembly_progress`/`AssemblyProgress` (trước đây field này chưa từng được liệt kê chi
tiết trong schema doc, dù đã tồn tại từ mục 43 — tiện thể bổ sung luôn khi đang sửa khu
vực này).

## 109. Chuyển batch giọng đọc từ Visual Studio sang Script Studio + thêm chỉnh tốc độ giọng đọc (2026-09-02)

Theo yêu cầu người dùng:
- "Bỏ Chức năng Sinh giọng đọc cho toàn bộ block ở màn visual."
- "Nút sinh giọng đọc cho toàn bộ block (kể cả đã có) chuyển sang bước Script Studio."
- "Bổ sung nút điều chỉnh tốc độ giọng đọc cho toàn bộ block ở bước Script Studio."

### Chuyển batch giọng đọc — không đổi API, chỉ đổi UI

Script Studio (`ScriptStudio.tsx`) đã CÓ SẴN nút "Sinh giọng đọc cho toàn bộ block" (bản
`force=false`, gọi `POST render/start?kind=narration`, tồn tại từ mục 30) — chỉ THIẾU bản
`force=true` ("kể cả đã có", tốn phí sinh lại toàn bộ). Việc cần làm: (1) xoá 2 nút
narration-batch khỏi `VisualStudio.tsx` — header "Sinh giọng đọc cho toàn bộ block"
(`kind="narration"`) và mục "Sinh lại TOÀN BỘ giọng đọc (kể cả đã có)" trong OverflowMenu
"⋯ Tuỳ chọn khác" (`kind="narration", force=true`); (2) thêm bản `force=true` tương ứng
vào Script Studio, cạnh nút không-force đã có sẵn (nút màu cảnh báo, cùng cách trình bày
đã dùng cho "Sinh lại TOÀN BỘ Visual" ở Visual Studio). `startAssetGeneration` (Visual
Studio) đơn giản hoá lại — bỏ tham số `kind` (giờ CHỈ còn sinh "visual"), chỉ còn nhận
`force: boolean`. Nút "Tạo giọng đọc" RIÊNG từng shot (cả 2 màn — `ShotCard` ở Visual
Studio, list block ở Script Studio) KHÔNG đổi, chỉ batch bị dời.

Bug thật phát hiện lúc sửa: `startNarrationBatch` (Script Studio) trước đây được gán
THẲNG làm `onClick={startNarrationBatch}` — thêm tham số `force = false` cho hàm này rồi
gọi y hệt sẽ khiến React truyền THẲNG `SyntheticEvent` (click event) làm giá trị `force`
(luôn truthy) thay vì `false` mặc định, biến nút "an toàn" thành force ÂM THẦM mỗi lần
bấm. Sửa bằng cách bọc `onClick={() => startNarrationBatch()}` (và `startNarrationBatch(true)`
cho nút force) — cùng lớp bug đã từng gặp ở nơi khác trong React (truyền thẳng hàm nhận
tham số tuỳ chọn làm handler).

### Chỉnh tốc độ giọng đọc — post-process file audio, KHÔNG phải tham số provider

Người dùng làm rõ khi được hỏi: "điều chỉnh tốc độ giọng đọc cho toàn bộ block ở bước
Script Studio là điều chỉnh tốc độ của file giọng đọc được tạo ra từ omnivoice" — tức
time-stretch FILE audio ĐÃ SINH, không phải 1 tham số API riêng của provider TTS. Quyết
định quan trọng vì rà soát trước đó cho thấy các provider TTS hỗ trợ speed RẤT KHÁC NHAU
(ElevenLabs có `voice_settings.speed`, Piper hỗ trợ qua `length_scale` nhưng adapter hiện
tại gọi overload đơn giản không nhận config, Gemini TTS không có tham số speed thật,
OmniVoice chưa rõ) — nếu làm theo hướng "tham số provider" sẽ phải sửa RIÊNG từng adapter
với hành vi khác nhau, có provider phải giả lập qua prompt (không đáng tin). Hướng
post-process file giải quyết GỌN toàn bộ vấn đề này 1 lần, hoạt động ĐỒNG NHẤT bất kể
provider nào.

**Backend**: `RenderState.narration_speed: float = 1.0` (mới, `schemas.py`) — field mức
PROJECT (không phải BrandProfile cấp kênh, không có khái niệm "kế thừa" — đơn giản đúng
phạm vi yêu cầu). `engine.py::_apply_narration_speed(path, speed)` (mới) — chạy ffmpeg
`filter:a atempo=<speed>` NGAY TẠI FILE trên đĩa, ghi ra file tạm CÙNG ĐUÔI gốc (`_speed_
tmp.<ext>`, không phải `.tmp` — ffmpeg suy muxer output từ đuôi file, đuôi lạ sẽ không tự
chọn được format) rồi `Path.replace()` đè lên file gốc. `speed==1.0` bỏ qua HOÀN TOÀN
(không tốn re-encode, không gọi `shutil.which`); thiếu ffmpeg hoặc lệnh lỗi — bỏ qua ÂM
THẦM, giữ file gốc CHƯA điều chỉnh (cùng nguyên tắc `media_probe.py::probe_duration_sec`:
xử lý phụ trợ không được chặn luồng generate chính). Gọi hàm này trong `generate_
narration_asset` NGAY SAU `write_bytes(path, data)`, TRƯỚC `_probe_audio_duration_sec` —
nhờ vậy `narration_duration_sec` tự động phản ánh ĐÚNG thời lượng đã điều chỉnh, mọi logic
downstream (segment duration lúc ghép, transcript .srt) không cần biết gì về "speed".
Endpoint mới `PATCH /projects/{id}/render/narration-speed` (body `{speed: float}`,
validate 0.5–2.0, 400 nếu ngoài khoảng — phạm vi giữ trong ngưỡng ffmpeg `atempo` 1 lần
filter xử lý tốt, không cần chain).

**Frontend**: Script Studio — thanh trượt "Tốc độ giọng đọc" (range 0.5–2.0, step 0.05,
lưu lúc `onMouseUp`/`onTouchEnd` — cùng pattern `BgMusicCard`/`OverlayEffectCard` đã dùng
cho volume/opacity), hiện giá trị hiện tại + ghi chú rõ "chỉ áp dụng cho giọng đọc SINH
MỚI sau khi chỉnh" (đúng nguyên tắc "không tự chạy ngầm" — đổi tốc độ KHÔNG tự sinh lại
narration đã có, người dùng tự bấm 1 trong 2 nút batch để áp dụng).

### Test

Backend: file mới `test_narration_speed.py` (14 test) — CRUD endpoint (lưu giá trị, 400
ngoài khoảng [0.5, 2.0], chấp nhận biên), `_apply_narration_speed` với ffmpeg THẬT (verify
duration đổi ĐÚNG tỷ lệ khi speed=2.0/0.5, no-op khi speed=1.0 — assert `shutil.which`
KHÔNG được gọi, bỏ qua an toàn khi thiếu ffmpeg), và 1 test tích hợp gọi thẳng
`generate_narration_asset()` với provider TTS giả (`_FakeOmniVoiceProvider`, trả WAV THẬT
sinh bằng ffmpeg — không phải bytes rác — để `atempo` thật sự chạy được) xác nhận
`narration_duration_sec` ghi lại ĐÚNG thời lượng file ĐÃ điều chỉnh. Full `pytest` **556
passed**. `tsc --noEmit` sạch. `specs/03_api.md`/`specs/04_data_schemas.md` cập nhật
endpoint mới + field `narration_speed` + ghi rõ UI narration-batch đã chuyển màn.

## 110. Nút "Dừng" sinh giọng đọc ở Script Studio + video nền chung hỗ trợ nhiều video/random loop/transition (2026-09-02)

Theo yêu cầu người dùng:
- "Khi bấm sinh giọng đọc toàn bộ ở màn Script Studio, cho phép user dừng chu trình sinh
  giọng đọc bất cứ khi nào. Hiện tại nút dừng vẫn đang ở màn Visual Studio... Nếu đúng
  [nút dùng chung cho sinh visual] thì cần tách riêng ra."
- "Ở bước visual studio, Block video nền chung: Cho phép upload nhiều video làm nền, cho
  phép set random loop (on/off), cho phép set hiệu ứng chuyển cảnh transition giữa các
  video."

### Nút "Dừng" ở Script Studio — KHÔNG cần tách backend, chỉ thiếu UI

Rà lại `engine.py` trước khi sửa: cờ "đang chạy"/"đã yêu cầu huỷ" (`_in_progress`/
`_cancel_requested`) là PER-PROJECT, KHÔNG tách theo `kind` — `run_asset_generation`
kiểm `is_cancel_requested(project_id)` TRƯỚC MỖI shot bất kể đang sinh visual hay
narration, và `_require_not_in_progress` (router) vốn đã chặn 2 batch chạy chồng (chỉ 1
batch/project tại 1 thời điểm). Nghĩa là giả thuyết người dùng nêu ("có thể nút này đang
dùng chung") đúng ở mức Ý NGHĨA (chỉ có 1 khái niệm "đang chạy" cho cả project) nhưng
KHÔNG có gì để "tách" ở tầng backend — không tồn tại 2 tiến trình visual+narration chạy
song song cần phân biệt. Vấn đề THẬT SỰ thuần là thiếu UI: Script Studio (quản lý CHÍNH
batch giọng đọc từ mục 109) chưa từng có nút gọi `POST render/cancel`, buộc người dùng
rời sang Visual Studio mới dừng được. Thêm nút "⏹ Dừng" vào `ScriptStudio.tsx` — gọi
ĐÚNG `api.cancelRender` y hệt Visual Studio, chỉ khác vị trí hiện (theo `hasInFlight`,
đã tính sẵn từ trước). Không đổi gì ở backend.

### Video nền chung — nhiều video, random loop, transition

**Schema** (`schemas.py::BackgroundVideoOverride`) — đổi `asset_path: str | null` (1 video)
thành `asset_paths: list[str]` (nhiều video, thứ tự = thứ tự upload) + 2 field mới
`random_order: bool` (mặc định `False`) và `transition: str` (mặc định `"cut"`, cùng
danh sách `TRANSITIONS` dùng cho shot-to-shot). KHÔNG giữ tương thích ngược — tính năng
gốc (mục 106) vừa build CÙNG NGÀY, chưa có dữ liệu thật cần migrate.

**Endpoint** (`routers/render.py`) — `POST .../upload` đổi từ "thay tại chỗ" sang "THÊM
vào danh sách" (tên file gắn mốc mili-giây + độ dài danh sách hiện tại làm hậu tố, tránh
đè file nếu 2 lần upload rơi trùng mili-giây). Thêm `DELETE .../background-video/{index}`
(bỏ đúng 1 video), `PATCH .../background-video` (`{random_order?, transition?}`, validate
`transition` theo `TRANSITIONS`, 400 nếu sai). `GET .../background-video/asset` đổi
thành `.../asset/{index}`. `DELETE .../background-video` (không kèm index) giữ nguyên ý
nghĩa cũ — bỏ HẲN toàn bộ.

**Assembly** (`assembly.py`) — hàm mới `_build_background_video_playlist`: nối NHIỀU
video thành 1 "playlist" TRƯỚC khi đưa vào `_build_background_video_master` (loop, KHÔNG
đổi) — scale/grade TỪNG clip rồi nối bằng filter `concat` (`transition=="cut"`) hoặc
`xfade` THẬT (video-only, không audio — khác `_xfade_chain` của pipeline chính vốn phải
blend cả audio track, nên viết hàm riêng đơn giản hơn thay vì tái dùng). Xfade chain
GỘP TRONG 1 LỆNH FFMPEG DUY NHẤT (khác `_xfade_chain`'s kỹ thuật "cắt head/blend tách
riêng" — không cần thiết ở quy mô video nền, thường chỉ vài clip B-roll, không phải
video tích luỹ dài hàng chục phút qua nhiều bước merge như pipeline chính). CHỈ gọi bước
playlist khi có ≥2 video — 1 video (case phổ biến nhất) bỏ qua hẳn, dùng thẳng video đó
làm nguồn cho `_build_background_video_master`, giữ NGUYÊN 100% hành vi/test mục 106,
không tốn thêm re-encode. `random_order=true` — `random.shuffle()` 1 bản COPY của
`asset_paths` mỗi lượt `assemble_video()` (không mutate thứ tự gốc hiện trên UI, không
xáo lại mỗi vòng lặp `-stream_loop -1` — đơn giản đúng yêu cầu, tránh dựng playlist động
phức tạp mỗi chu kỳ lặp).

**Progress** (mục 108, `AssemblyProgress`) — `bg_total` cộng thêm 1 đơn vị "playlist" khi
có ≥2 video (`2 (playlist + master) + số shot trống`, so với `1 + số shot trống` khi chỉ
1 video) — vẫn đúng nguyên tắc "đơn vị tự nhiên sẵn có", không cần ước lượng % giả.

**Frontend** (`VisualStudio.tsx::BackgroundVideoCard`) — viết lại hoàn toàn: danh sách
video (mỗi video 1 preview + nút "Bỏ video này" riêng), input `multiple` cho phép chọn
nhiều file cùng lúc (upload TUẦN TỰ, không `Promise.all` — mỗi lần APPEND vào render.json
qua đọc-sửa-ghi, song song thật sự có thể ghi đè nhau), checkbox "Random loop" + dropdown
"Chuyển cảnh giữa các video" (tái dùng `TRANSITION_OPTIONS` đã có sẵn cho shot-to-shot) —
2 control này CHỈ hiện khi có ≥2 video (không ý nghĩa với 0-1 video). `client.ts` thêm
`deleteProjectBackgroundVideoItem`/`patchProjectBackgroundVideoSettings`, đổi
`projectBackgroundVideoUrl` nhận thêm `index`.

### Test

Viết lại HẲN `test_background_video.py` (7 → 16 test, theo API mới): CRUD (upload append,
xoá theo index, xoá toàn bộ, xem theo index, 404, PATCH settings + validate transition),
2 unit test `_build_background_video_playlist` với ffmpeg THẬT (`"cut"` nối đúng thứ tự +
đúng tổng thời lượng; transition thật làm tổng NGẮN HƠN tổng thô, xác nhận có blend thật
— không phải giả định), 1 test end-to-end MỚI với 2 video nền thật (xanh lá + vàng) qua
`assemble_video()` xác nhận đúng thứ tự xuất hiện, và 2 test progress (case 1 video giữ
nguyên `bg_total = 1 + blank`, case nhiều video xác nhận `bg_total = 2 + blank` VÀ bước
playlist được spy đúng lúc). Full `pytest` **565 passed**. `tsc --noEmit` sạch.
`specs/03_api.md`/`specs/04_data_schemas.md` cập nhật đầy đủ schema/endpoint mới + ghi
chú rõ cơ chế "Dừng" là per-project (giải thích tại sao KHÔNG cần tách backend).

## 111. Điều tra + xử lý bug thật: project bị kẹt "assembling" mãi mãi + phòng tránh/UI xử lý (2026-09-02)

Người dùng báo: bấm ghép video cho project dài (~28 phút, 61 shot, dùng video nền chung
mục 106/110) nhưng không thấy progress chạy. Điều tra TRỰC TIẾP trên backend đang chạy
thật của người dùng (tìm đúng port qua `wmic`/`tasklist` — cổng mặc định 8756 tình cờ bị
1 service KHÔNG LIÊN QUAN chiếm, backend thật của StudioFlow nằm ở cổng Electron cấp phát
động), tìm đúng project qua `GET /channels` → `GET /channels/{id}/projects`, đọc `GET
.../render/status` thật:

- `assembly_status="assembling"`, `assembly_progress={stage: "background_video",
  current: 0, total: 62}`, đứng yên SUỐT ~4 phút.
- `tasklist` xác nhận KHÔNG có tiến trình `ffmpeg.exe` nào đang chạy — nhưng
  `renders/segments/_bg_master.mp4` (file dựng video nền chung) đã tồn tại THẬT, 3.4GB,
  mtime CÁCH ~2 phút sau lúc bắt đầu ghép và ĐỨNG YÊN từ đó — bằng chứng: bước dựng video
  nền đã DỰNG XONG THÀNH CÔNG, nhưng thread xử lý nó "chết lặng" NGAY SAU ĐÓ, trước khi
  kịp lưu tiến độ tiếp theo hay ghi lỗi. `assembly_status` bị KẸT vĩnh viễn — vì `start_
  assemble` (router) TRƯỚC ĐÂY chỉ tin field `assembly_status` ĐÃ LƯU, người dùng KHÔNG
  BẤM GHÉP LẠI ĐƯỢC NỮA (409) kể cả sau khi khởi động lại app (field nằm trong file, không
  phải bộ nhớ). Fix TẠM THỜI ngay lúc điều tra: reset thủ công qua chính module `engine.py`
  của backend (không sửa tay JSON) để người dùng bấm ghép lại được ngay.

Người dùng hỏi tiếp: "có cách nào để tránh lỗi tương tự xảy ra, hoặc giải pháp để xử lý ở
tầng UI cho user biết và làm" — 4 phần việc:

### 1. Khả nghi nguyên nhân gốc — encoding console Windows

Lúc thao tác reset thủ công, gặp NGAY `UnicodeEncodeError: 'charmap' codec can't encode
character...` khi in tiếng Việt ra console (mặc định cp1252 trên máy Windows này, không
phải UTF-8). `electron/src/backend-launcher.ts::startBackend` spawn Python KHÔNG set
`PYTHONIOENCODING`/`PYTHONUTF8` — nghĩa là `sys.stdout`/`stderr` của backend thừa hưởng
NGUYÊN codepage console mặc định của máy. Toàn bộ app dùng tiếng Việt (thông điệp lỗi,
docstring runtime...) — nếu BẤT KỲ đâu trong 1 luồng nền có in/log ra console 1 chuỗi có
dấu, `UnicodeEncodeError` có thể xảy ra NGOÀI phạm vi try/except Python thông thường (VD
trong chính cơ chế in traceback mặc định của interpreter khi 1 exception thật sự thoát ra
ngoài), khiến thread chết mà KHÔNG chạy tới được `except Exception` đang bọc sẵn trong
`assemble_video`. KHÔNG chứng minh được 100% đây là nguyên nhân THẬT của lần crash cụ
thể này (không có log lịch sử để đối chiếu), nhưng là rủi ro CÓ THẬT, chi phí sửa gần như
0, và đóng hẳn 1 lớp khả năng — thêm `PYTHONIOENCODING: "utf-8"` + `PYTHONUTF8: "1"` vào
`env` lúc spawn backend.

### 2. Tự phục hồi — `_assembly_in_progress` (cờ trong bộ nhớ, giống `_in_progress` đã có)

Root gap thật sự: `start_assemble` gate hoàn toàn dựa vào `state.assembly_status` ĐÃ LƯU
trong render.json — KHÁC `run_asset_generation` (dùng `_in_progress`, set TRONG BỘ NHỚ,
tự về rỗng khi backend khởi động lại — "tự phục hồi" đã có sẵn cho asset generation từ
trước, chỉ assembly chưa có). Thêm `engine.py::_assembly_in_progress`/`is_assembly_in_
progress`/`_mark_assembly_in_progress`/`_mark_assembly_done` (y hệt pattern cũ). `assembly.
py::assemble_video` tách thân hàm gốc thành `_assemble_video_impl` (giữ NGUYÊN 100% logic,
không re-indent 400 dòng) rồi bọc `_mark_assembly_in_progress`/`_mark_assembly_done` (try/
finally) NGOÀI CÙNG — cờ LUÔN được dọn khi hàm chạy xong dù thành công/lỗi/timeout mới
(mục 3), TRỪ KHI tiến trình bị kill cứng (trường hợp đó khởi động lại app cũng tự dọn vì
cờ nằm trong bộ nhớ tiến trình cũ). `start_assemble`: `if assembly_status=="assembling"
AND is_assembly_in_progress(): 409` — nếu field lưu nói "assembling" nhưng cờ bộ nhớ đã
`False` (đúng kịch bản kẹt vừa gặp), tự cho ghép lại, KHÔNG cần can thiệp tay nữa.

### 3. Timeout ffmpeg cho 2 lệnh "nặng nhất" — `_build_background_video_master`/`_playlist`

Phát hiện PHỤ lúc viết test cho mục 2: gọi `_build_segment` thật với bytes ảnh/video GIẢ
(test fixture) khiến ffmpeg treo >120s không đoán trước được — cho thấy KHÔNG có
`subprocess.run(...)` nào trong `assembly.py` (15 chỗ) từng có `timeout=`. Với ĐA SỐ lệnh
(build từng segment/run/concat...) rủi ro treo thấp (input do chính app tự sinh, đã qua
nhiều lớp validate) nên KHÔNG đổi hết 15 chỗ (tránh chọn timeout quá chặt gây fail oan cho
project dài hợp lệ). Ưu tiên ĐÚNG 2 hàm rủi ro cao nhất và liên quan trực tiếp tới sự cố
này — `_build_background_video_master`/`_build_background_video_playlist` (mục 106/110):
chạy 1 LỆNH FFMPEG DUY NHẤT xử lý CẢ project, KHÔNG có checkpoint/tiến trình con nào để tự
báo giữa chừng (khác Pass 2 — mỗi shot 1 lệnh riêng, dù 1 lệnh treo cũng không kẹt CẢ
project). Thêm `_BACKGROUND_VIDEO_FFMPEG_TIMEOUT_SEC = 7200` (2 giờ — rộng rãi, project
thật ~28 phút chỉ mất ~2 phút để dựng master, vẫn đặt 1 TRẦN cuối thay vì vô hạn). Except
mới `subprocess.TimeoutExpired` trong `assemble_video` — set `assembly_status="error"`
với thông điệp rõ ràng thay vì để `CalledProcessError`/`Exception` chung xử lý mơ hồ.

### 4. Giải pháp UI — nút "Đặt lại tiến trình bị treo"

Endpoint mới `POST /projects/{id}/render/assemble/reset` — đặt `assembly_status="error"`
kèm thông điệp rõ, 409 nếu `is_assembly_in_progress` vẫn `True` (chặn đặt lại nhầm 1 tiến
trình đang chạy bình thường), 400 nếu không có gì để đặt lại. KHÔNG xoá file trung gian đã
dựng dở (`renders/segments/`) — lần ghép lại tự ghi đè (`-y`), không cần dọn tay.

`RenderStudio.tsx` — nút "Đặt lại tiến trình bị treo" LUÔN hiện suốt lúc đang ghép (KHÔNG
gắn ngưỡng thời gian tự động cảnh báo) — cân nhắc kỹ: bước "background_video" với video
dài có thể ĐỨNG YÊN THẬT SỰ ở 0/N rất lâu (chính bản chất bug mục 108 đã mô tả, không phải
dấu hiệu treo), nên KHÔNG có ngưỡng "bao lâu là treo" đáng tin cậy để tự động báo mà không
báo nhầm cho project dài hợp lệ — thay vào đó luôn cho người dùng QUYỀN TỰ QUYẾT ngay khi
họ nghi ngờ, chỉ thêm gợi ý text SAU 5 phút ("có thể đặt lại nếu nghi treo"), backend tự
chối (409) nếu bấm nhầm lúc đang chạy thật.

### Test

`test_render.py` — 6 test mới: tự phục hồi khi status kẹt mà KHÔNG có cờ thật (không còn
409), vẫn chặn 409 khi cờ thật đang giữ, reset endpoint (thành công/409/400), và 1 test
spy xác nhận `_assembly_in_progress` đúng `True` lúc Pass 2 chạy + LUÔN `False` sau khi
xong (kể cả nhánh lỗi) — bài học viết test: dùng bytes ảnh/video GIẢ cho ffmpeg THẬT xử lý
dễ treo khó đoán, sửa bằng cách cho `_build_segment` raise NGAY sau khi ghi nhận cờ thay
vì gọi hàm thật. `test_background_video.py` — 1 test mới verify nhánh `TimeoutExpired`
(monkeypatch `subprocess.run` raise timeout) → `assembly_status="error"` với thông điệp rõ
+ cờ `_assembly_in_progress` vẫn được dọn đúng. `tsc -p electron/tsconfig.json` sạch.
Full `pytest` **572 passed**. `tsc --noEmit` (frontend) sạch. `specs/03_api.md` cập nhật
2 endpoint mới + ghi rõ cơ chế tự phục hồi.

## 112. Layer video định vị theo lưới 3x3 (VD voice wave) ở Visual Studio (2026-09-02)

Theo yêu cầu người dùng: "Tôi muốn có 1 tính năng cho phép thêm các layers vào khung
hình của video tại các vị trí khác nhau (chia khung hình thành 9 phần và cho phép lựa
chọn vị trí để đặt layer đó vào). Mục đích: tôi muốn thêm layer voice wave (dạng video
loop) vào bên trên video nền."

Đã trao đổi trước khi build 2 quyết định thiết kế chính: (1) nguồn layer LUÔN có sẵn kênh
alpha (WebM VP9/MOV ProRes4444 trong suốt — KHÔNG phải clip nền đen kiểu overlay hiện có)
→ dùng thẳng filter `overlay` + alpha thật, không cần kỹ thuật screen-blend phức tạp hơn;
(2) hỗ trợ NHIỀU layer cùng lúc (danh sách) ngay từ đầu, không chỉ 1 slot cố định.

### Data model + endpoint (mirror background-video mục 110, đơn giản hơn)

`schemas.py::VideoLayer` (mới) — `id`, `asset_path`, `position` (1 trong 9 giá trị lưới
3x3: `top/middle/bottom` × `left/center/right`), `width_pct` (mặc định 0.3 — % chiều
rộng khung hình xuất, chiều cao tự co theo tỉ lệ gốc), `opacity` (mặc định 1.0).
`RenderState.layers: list[VideoLayer]`. 4 endpoint mới (`routers/render.py`): `POST
.../layers/upload` (multipart `file` + form `position`/`width_pct`/`opacity`, THÊM 1
layer mỗi lần gọi — cùng tên file `layer_<ts>_<n>.<ext>` tránh đè như video nền), `PATCH
.../layers/{layer_id}` (partial update), `DELETE .../layers/{layer_id}`, `GET .../
layers/{layer_id}/asset`.

### Assembly (`assembly.py::_composite_layers`) — phần việc chính

Vị trí → toạ độ: dùng THẲNG biến RUNTIME của ffmpeg (`main_w`/`main_h`/`overlay_w`/
`overlay_h`) trong filter `overlay` (`_layer_position_expr`) — KHÔNG tính pixel cụ thể ở
Python, tự đúng tỉ lệ dù xuất 720p/1080p/4K, lề (margin) tính theo % khung hình
(`0.02*main_w`/`0.02*main_h`). Mỗi layer: `-stream_loop -1` cho nguồn (đủ dài dù clip
loop ngắn hơn nhiều lần) → `scale={pixel CHẴN}:-2` (kích thước TÍNH SẴN ở Python vì độ
phân giải xuất đã biết, khác x/y của `overlay` — biến đó chỉ có tại thời điểm composite)
→ `format=yuva420p` (đảm bảo có kênh alpha dù nguồn khác định dạng) →
`colorchannelmixer=aa={opacity}` (chỉnh độ mờ qua alpha CÓ SẴN — khác overlay hiệu ứng
lớp phủ phải giảm SÁNG vì `blend` screen không có alpha trực tiếp). Nhiều layer — chain
`overlay` NỐI TIẾP trong 1 lệnh ffmpeg DUY NHẤT (số layer thực tế nhỏ, an toàn bộ nhớ,
cùng lý do đã áp dụng cho `_build_background_video_playlist` mục 110). `shortest=1` trên
MỌI node `overlay` trong chain — bài học đã có từ `_mix_overlay_effect` (mục 68): nguồn
loop VÔ HẠN, thiếu cờ này sẽ treo vô thời hạn chờ EOF không bao giờ tới. Dùng lại
`_WHOLE_VIDEO_FFMPEG_TIMEOUT_SEC` (đổi tên từ `_BACKGROUND_VIDEO_FFMPEG_TIMEOUT_SEC`, mục
111 — giờ dùng chung cho MỌI lệnh ffmpeg xử lý CẢ project trong 1 lệnh duy nhất, không
chỉ riêng video nền) — cùng lưới an toàn chống treo vô hạn.

Gọi trong `_assemble_video_impl` NGAY SAU bước blend overlay hiệu ứng lớp phủ (nếu có) —
layer LUÔN nổi TRÊN CÙNG, không bị mưa/tuyết che — và TRƯỚC bước chuẩn hoá loudness cuối
cùng, cùng pattern ghi-đè-tại-chỗ (`final_path`) đã dùng cho bg_music/overlay. KHÔNG thêm
`assembly_progress` stage riêng cho bước này (khác video nền chung mục 108/110) — bước
này rẻ hơn nhiều (chỉ composite lên video ĐÃ ghép xong, không phải re-encode toàn bộ
timeline), đúng cùng mức độ với overlay/bg_music hiện có (2 bước đó cũng không có stage
riêng).

### Frontend (`VisualStudio.tsx`)

`PositionGridPicker` (mới, dùng chung) — lưới 9 ô bấm được, ô đang chọn tô sáng.
`LayersCard` (mới, đặt cạnh `BackgroundVideoCard`) — danh sách layer đã có (mỗi layer: 1
preview video, lưới chọn vị trí riêng — đổi ngay lập tức qua `PATCH`, 2 thanh trượt kích
thước/độ mờ — lưu lúc thả chuột giống `BgMusicCard`/`OverlayEffectCard`, nút bỏ layer) +
khối "Thêm layer mới" (chọn vị trí/kích thước/độ mờ TRƯỚC, rồi chọn file — 3 giá trị đó
gửi kèm ngay lúc upload). `client.ts` thêm `uploadProjectLayer`/`patchProjectLayer`/
`deleteProjectLayer`/`projectLayerAssetUrl`.

### Test

File mới `test_layers.py` (22 test) — CRUD đầy đủ (upload append/validate 5 trường hợp
sai, PATCH partial update/404/validate, DELETE/404, GET asset/404, mặc định danh sách
rỗng), 4 test `_composite_layers` với ffmpeg THẬT dùng clip WebM VP9 alpha thật (không
giả định) — xác nhận: định vị ĐÚNG ô lưới (vùng ngoài layer giữ nguyên màu nền), độ mờ
áp dụng ĐÚNG qua alpha (so khớp công thức "over" chuẩn: `fg*alpha + bg*(1-alpha)`), NHIỀU
layer cùng lúc không đè lên nhau ngoài vùng của chúng — và 1 test tích hợp `assemble_
video()` đầy đủ xác nhận layer thật sự xuất hiện trên video cuối cùng. Full `pytest`
**594 passed**. `tsc --noEmit` sạch. `specs/03_api.md`/`specs/04_data_schemas.md` cập
nhật đầy đủ schema/endpoint mới.

## 113. Layer định vị hỗ trợ nguồn nền đen (screen-blend) — không chỉ alpha (2026-09-02)

Ngay sau mục 112, người dùng thử dùng tính năng và báo: "tôi chỉ có video layer nền đen
thôi. Hãy process nền đen" — asset THẬT của người dùng KHÔNG có kênh alpha (khác giả
định đã XÁC NHẬN TRƯỚC lúc thiết kế mục 112 qua câu hỏi trực tiếp — thực tế sai với giả
định ban đầu, không phải lỗi code).

### Thiết kế — screen-blend CỤC BỘ, không phải toàn khung hình

`VideoLayer.blend_mode` (mới) — `"alpha"` (mặc định, giữ NGUYÊN hành vi mục 112) hoặc
`"screen"`. Chế độ `"screen"` dùng ĐÚNG kỹ thuật đã có ở `_mix_overlay_effect` (overlay
hiệu ứng lớp phủ mục 68 — nền đen "biến mất" khi `blend=all_mode=screen`, cùng bài học
màu tím sai đã ghi ở đó: PHẢI `format=gbrp` cả 2 nhánh trước blend, không được `yuv420p`/
`rgb24` thẳng) nhưng hàm ĐÓ blend TOÀN khung hình (2 input CÙNG kích thước) — layer ở đây
cần ĐỊNH VỊ tại 1 vùng nhỏ, nên thêm 2 bước bao quanh: (1) `crop` đúng vùng nền tương ứng
vị trí layer từ khung hình đang ghép, (2) blend screen giữa vùng đã cắt và layer (đã
scale cùng kích thước), ra 1 "miếng vá", (3) `overlay` miếng vá đó TRỞ LẠI đúng vị trí đã
cắt — vùng còn lại của khung hình giữ NGUYÊN không đụng tới.

**Vấn đề kỹ thuật phát sinh**: `crop` (khác `scale`) KHÔNG có cơ chế `-2` tự tính chiều
cao — cần biết TRƯỚC cả width lẫn height CỤ THỂ để cắt đúng. Thêm `media_probe.py::
probe_video_dimensions` (ffprobe, cùng nguyên tắc `probe_duration_sec` — lỗi/thiếu binary
rơi về giả định 16:9, không chặn luồng ghép) + `assembly.py::_layer_target_size` — đo tỉ
lệ khung hình GỐC của layer, tính width/height theo `width_pct`, KẸP không vượt quá khung
hình chính ở cả 2 chiều (layer nguồn dọc đặt `width_pct` lớn trên khung ngang có thể ra
chiều cao vượt khung hình chính, `crop` sẽ LỖI THẬT nếu vùng cắt lớn hơn nguồn bị cắt —
phát hiện lúc thiết kế, xử lý trước khi thành bug thật).

**Tái cấu trúc để tránh trùng lặp**: `_layer_position_expr` (mục 112, chỉ dùng cho
`overlay`) đổi thành `_grid_position_expr` TỔNG QUÁT — nhận tên biến runtime làm tham số
(`container_w/h`, `content_w/h`) thay vì hard-code `main_w/overlay_w` — dùng CHUNG cho cả
`overlay` (`main_w/main_h/overlay_w/overlay_h`) LẪN `crop` (`in_w/in_h/out_w/out_h`, mới),
công thức vị trí giống hệt nhau, chỉ khác tên biến ffmpeg cấp cho từng filter.

Độ mờ chế độ `screen` chỉnh qua `colorchannelmixer=rr/gg/bb={opacity}` (giảm SÁNG layer
TRƯỚC khi blend — cùng cách `_mix_overlay_effect` làm, vì `blend` screen không có tham số
alpha trực tiếp) — khác chế độ `alpha` chỉnh qua kênh alpha CÓ SẴN (`colorchannelmixer=
aa={opacity}`).

### Endpoint + Frontend

`POST/PATCH .../layers` thêm field `blend_mode` (validate 1 trong `{alpha, screen}`,
400 nếu sai). `LayersCard` (`VisualStudio.tsx`) — dropdown "Kiểu nguồn" ("Trong suốt
(alpha)" / "Nền đen (screen)") cho CẢ layer mới lẫn từng layer đã có (đổi tại chỗ qua
PATCH). Cập nhật copy hướng dẫn — không còn khẳng định "cần nền trong suốt" như mục 112,
giải thích rõ 2 lựa chọn tuỳ loại nguồn người dùng có.

### Test

7 test mới trong `test_layers.py`: CRUD cho `blend_mode` (mặc định `"alpha"`, chấp nhận
`"screen"`, từ chối giá trị lạ, PATCH đổi được), và 4 test `_composite_layers` chế độ
`screen` với ffmpeg THẬT dùng clip màu thuần KHÔNG alpha (`yuv420p` thường, giả lập ĐÚNG
loại nguồn người dùng có) — xác nhận: layer ĐEN THUẦN làm nền "biến mất" hoàn toàn (chỉ
còn thấy màu nền gốc), layer TRẮNG hiện rõ + vùng NGOÀI layer giữ nguyên màu nền (crop+
blend+overlay không lem ra ngoài vùng đã định vị), và độ mờ làm nhạt hiệu ứng đúng hướng.
Full `pytest` **601 passed**. `tsc --noEmit` sạch. `specs/03_api.md`/`specs/04_data_
schemas.md` cập nhật `blend_mode` + sửa lại tên hàm đã đổi (`_layer_position_expr` →
`_grid_position_expr`) trong ghi chú mục 112.

## 114. Bug thật: bấm "Bỏ layer" báo lỗi (Windows file lock từ preview `<video loop>`) (2026-09-02)

Người dùng báo: bấm "Bỏ layer" hiện lỗi "Có lỗi khi bỏ layer." — điều tra trực tiếp trên
backend đang chạy thật (tìm đúng cổng qua `wmic`, tìm đúng project qua `GET /channels` →
`GET .../projects` → `GET .../render/status`, đọc `layers[]` để lấy đúng `layer_id`), gọi
lại NGUYÊN VĂN request `DELETE .../render/layers/{layer_id}` mà frontend gửi — tái hiện
được `500 Internal Server Error`. Chạy lại chính logic đó bằng Python trực tiếp (thay vì
qua HTTP) để lấy traceback đầy đủ (HTTP 500 không trả chi tiết lỗi) — lộ nguyên nhân
THẬT: `PermissionError: [WinError 32] The process cannot access the file because it is
being used by another process` khi gọi `unlink_retrying` xoá file layer.

### Root cause

`unlink_retrying` (đã có từ mục "2026-08-23", xử lý ĐÚNG loại lỗi này cho overlay.mp4
trước đây) thử lại tối đa 10 lần × 150ms (~1.5s) — đủ cho 1 khoá THOÁNG QUA (VD trình
duyệt vừa stream xong preview, handle chưa kịp nhả ngay). Nhưng preview của layer
(`LayersCard`, mục 112) dùng `<video controls muted loop>` — CÓ `loop`, KHÁC MỌI preview
khác trong app (overlay/video nền/intro — xem lại toàn bộ `VisualStudio.tsx`, không nơi
nào khác dùng `loop`). Nếu người dùng bấm play để xem trước rồi bấm "Bỏ layer" NGAY LÚC
nó đang phát, `loop` khiến trình duyệt LIÊN TỤC tự request lại file — không phải 1 khoá
thoáng qua nữa mà là khoá ĐANG DIỄN RA liên tục, vượt xa cửa sổ thử lại 1.5s.

### Fix

`removeLayer` (`VisualStudio.tsx::LayersCard`) — thêm `videoRefs` (Map tới từng phần tử
`<video>` của mỗi layer, gán qua callback ref) — TRƯỚC khi gọi API xoá, chủ động
`.pause()` + `removeAttribute("src")` + `.load()` ép trình duyệt nhả file NGAY, thay vì
trông chờ hoàn toàn vào cửa sổ thử lại phía backend (giữ NGUYÊN `unlink_retrying`, không
đổi — vẫn hữu ích cho khoá thoáng qua bình thường, chỉ không đủ cho trường hợp `loop`
đang phát liên tục này). KHÔNG sửa `OverlayEffectCard`/`BackgroundVideoCard` (không có
`loop`, chưa từng gặp lại bug này kể từ lần fix gốc 2026-08-23) — giữ đúng phạm vi.

Layer bị kẹt của người dùng (`layer_1788369011492_0`, project `prj_1788352112897`) đã
gọi lại `DELETE` thành công qua backend đang chạy ngay lúc điều tra (khoá đã tự nhả) —
không cần can thiệp tay thêm.

### Test

Đây là bug hành vi trình duyệt (Windows file lock qua `<video>` streaming) — không có hạ
tầng test frontend trong repo (toàn bộ session dùng `tsc --noEmit` + pytest backend) và
backend không đổi gì (logic `unlink_retrying`/endpoint giữ nguyên) nên không có gì mới
để pytest verify — chỉ `tsc --noEmit` (sạch) cho phần sửa. Xác nhận thủ công qua
`DELETE` trực tiếp bằng Python (tái hiện lỗi thật, không suy đoán) trước khi sửa.

## 115. Layer ẢNH định vị (song song layer video) + hỗ trợ "full khung hình" (2026-09-02)

Theo yêu cầu người dùng:
- "Rename 'Layer định vị' thành 'Layer video định vị'."
- "Bổ sung thêm block ở bước visual studio để setup 'Layer ảnh định vị' với chức năng
  tương tự nhưng cho ảnh nền đen hoặc không có nền. Ngoài hỗ trợ 9 vị trí layer thì còn
  hỗ trợ thêm full khung hình."

Đổi tên tiêu đề card `LayersCard` (`VisualStudio.tsx`) từ "Layer định vị" → "Layer video
định vị" — rõ nghĩa hơn giờ có THÊM 1 loại layer khác (ảnh) đứng cạnh nó.

### Thiết kế — song song HOÀN TOÀN `VideoLayer`, danh sách RIÊNG

`schemas.py::ImageLayer` (mới) — CÙNG field/2 chế độ `blend_mode` (`"alpha"`/`"screen"`,
mục 113) với `VideoLayer`, chỉ khác 2 điểm: (1) nguồn LUÔN ảnh tĩnh PNG/JPEG/WEBP, (2)
`position` có thêm giá trị `"full"` (9 vị trí lưới cũ + "full" — phủ TOÀN khung hình).
`RenderState.image_layers: list[ImageLayer]` — DANH SÁCH RIÊNG, KHÔNG dùng chung
`layers` (2 loại asset xử lý ffmpeg khác hẳn nhau — video cần `-stream_loop -1`, ảnh cần
`-loop 1`).

**`assembly.py::_composite_image_layers`** (mới, song song `_composite_layers`) — tái
dùng NGUYÊN `_layer_target_size`/`_grid_position_expr` (mục 113, đã tổng quát hoá sẵn)
cho 9 vị trí lưới, CHỈ thêm nhánh `position=="full"`:
- Scale: `_scale_cover_filter(resolution)` (CÙNG hàm `_mix_overlay_effect` dùng — không
  phụ thuộc `BrandProfile.aspect_fill_mode`, layer là tính năng độc lập) thay vì
  `scale=W:-2`/`scale=W:H` theo `width_pct` — bỏ qua HẲN field này khi `"full"`.
- `blend_mode=="alpha"` + `"full"`: `overlay=x=0:y=0` thẳng (không cần `_grid_position_
  expr`, cover-scale đã khớp CHÍNH XÁC kích thước khung hình chính).
- `blend_mode=="screen"` + `"full"`: KHÔNG cần bước `crop` (vùng cần blend = TOÀN khung
  hình = chính `[prev]`, không phải 1 phần con) — blend THẲNG `[prev]` với layer đã
  scale-cover, ra LUÔN kết quả cuối. Nhận ra lúc thiết kế: đây CHÍNH LÀ `_mix_overlay_
  effect` áp dụng cho ẢNH TĨNH thay vì video loop — khác biệt DUY NHẤT là input dùng
  `-loop 1` thay `-stream_loop -1`.

Input mỗi layer: `-loop 1 -i asset_path` (khác `-stream_loop -1` của layer video) — cùng
kỹ thuật `_build_segment` dùng cho shot ảnh, tạo stream VÔ HẠN, `shortest=1` vẫn cần
nguyên lý cũ (bài học `_mix_overlay_effect`). Gọi trong `_assemble_video_impl` NGAY SAU
bước layer video (nếu có) — layer ẢNH LUÔN nổi TRÊN CÙNG mọi layer khác, cùng nguyên tắc
ghi-đè-tại-chỗ (`final_path`) đã dùng cho mọi bước hậu kỳ khác.

### Endpoint + Frontend

4 endpoint mới (`routers/render.py`, song song layer video) — `POST/PATCH/DELETE/GET
.../image-layers[/...]` — dùng lại NGUYÊN `_IMAGE_EXT_BY_CONTENT_TYPE`/`_IMAGE_EXT_BY_
SUFFIX` (map đã có sẵn cho upload ảnh shot) thay vì map video. `_IMAGE_LAYER_POSITIONS =
_LAYER_POSITIONS | {"full"}` cho validate.

`PositionGridPicker` (`VisualStudio.tsx`) — đổi thành GENERIC (`<P extends string>`) +
prop `allowFull` mới — dùng CHUNG được cho cả `LayerPosition` (layer video, giữ nguyên
không đổi — không truyền `allowFull`) lẫn `ImageLayerPosition` (layer ảnh, có `"full"`).
Nút "Toàn khung hình" render RIÊNG BÊN DƯỚI lưới 3x3 (không phải ô thứ 10 trong lưới —
"full" khác hẳn ý nghĩa 1 VỊ TRÍ, tách biệt thị giác cho rõ). `ImageLayersCard` (mới,
song song `LayersCard`, đặt ngay dưới nó) — ẩn thanh trượt "Kích thước" khi đang chọn
`"full"` (không có ý nghĩa gì để chỉnh).

### Test

File mới `test_image_layers.py` (27 test) — CRUD đầy đủ (song song `test_layers.py`,
thêm case `position="full"` được chấp nhận), và 7 test `_composite_image_layers` với
ffmpeg + Pillow THẬT: định vị đúng ô lưới (alpha), độ mờ qua alpha, nhiều layer cùng lúc,
**`"full"` phủ đúng CẢ 4 góc + tâm** (khác 9 vị trí chỉ phủ 1 vùng), screen-mode làm nền
đen biến mất + không lem ra ngoài vùng định vị, và **`"full"` + `"screen"`** ra màu XÁM
đúng công thức (không đen tuyệt đối — xác nhận blend thật xảy ra, không phải nền đen
"biến mất" trơ trọi) — cộng 1 test tích hợp `assemble_video()` đầy đủ. Full `pytest`
**628 passed**. `tsc --noEmit` sạch. `specs/03_api.md`/`specs/04_data_schemas.md` cập
nhật đầy đủ schema/endpoint mới.

## 116. Bug thật: xoá watermark cho ẢNH không xoá được logo Gemini góc dưới phải — 2 lớp nguyên nhân, đổi hẳn chiến lược định vị cho ảnh (2026-09-04)

Người dùng báo: "Phần xóa watermark cho ảnh ở bước visual studio đang không xóa được logo
gemini ở góc dưới bên phải ảnh", test với shot B01/B02 project "p" kênh "t". Tìm đúng
project qua backend THẬT đang chạy (`GET /channels` → `ch_1788363856758` tên "t" →
`GET .../projects` → `prj_1788363856772` tên "p"), đọc `visual_asset_path` 2 shot, xem
trực tiếp ảnh thật.

### Bug #3 — bbox lọt ngưỡng diện tích nhưng SAI HÌNH DẠNG (dải dọc gần trọn chiều cao)

Ảnh B01 (`B01_nowm.png`, 2752×1536) hiện MỘT DẢI MỜ/NHOÈ lớn phủ gần TRỌN chiều cao, chiếm
~31% chiều rộng bên phải ảnh — đo bằng phân tích độ nét (gradient) theo cột ảnh: sharpness
rơi mạnh từ x≈1600 tới x≈2450, phẳng ở mức thấp suốt chiều cao. 31% diện tích LỌT ngưỡng
`_MAX_BBOX_AREA_FRACTION=0.35` (mục 100) nên bị chấp nhận nhầm là watermark "hợp lý", dù rõ
ràng không phải 1 icon góc nhỏ (dải trải gần hết 1 chiều mà không mỏng ở chiều kia). Fix:
`detector.py::_bbox_has_plausible_shape` — thêm lọc HÌNH DẠNG bên cạnh diện tích, chỉ chấp
nhận bbox dạng (a) icon gọn — không vượt quá nửa MỖI chiều, hoặc (b) dải mỏng chạy dọc 1
cạnh — gần hết 1 chiều NHƯNG mỏng (≤20%) ở chiều còn lại. Bbox đo thật ở trên bị loại đúng
theo heuristic mới (test `test_detect_watermark_bboxes_robust_rejects_full_height_vertical_
strip`), dải chữ credit hợp lệ kiểu cũ (mục 100) vẫn được chấp nhận (test riêng khoá lại).
File gốc B01 đã bị `unlink_retrying` xoá vĩnh viễn sau lần chạy lỗi này (chỉ còn bản đã hỏng)
— **không khôi phục được nội dung gốc**, người dùng cần re-upload nếu còn giữ file gốc.

### Bug #4 — Florence-2 KHÔNG đủ khả năng định vị icon lấp lánh trong suốt trên nền minh hoạ chi tiết

Ảnh B02 (`B02_nowm.png`, 2816×1536) KHÔNG có dấu hiệu bị vá/mờ ở đâu (quét gradient 2D toàn
ảnh, không thấy vùng phẳng bất thường) nhưng icon lấp lánh Gemini vẫn NGUYÊN VẸN, sắc nét ở
góc dưới phải — xác nhận bằng lưới toạ độ chồng lên ảnh: icon thật nằm ở bbox
`(2470, 1220, 2600, 1330)`. Gọi TRỰC TIẾP `detect_watermark_bboxes` (model Florence-2 THẬT,
không mock) trên ảnh này với 8 prompt khác nhau (`"watermark"`, `"logo"`, `"small icon in
the corner"`, `"sparkle icon"`, `"star icon"`, `"four pointed star icon"`, `"white sparkle
logo watermark"`) VÀ thử crop sẵn góc dưới phải (20%/25% khung hình) trước khi đưa vào model
— **KHÔNG prompt/crop nào định vị đúng vị trí icon thật**, mọi bbox trả về đều rơi vào vùng
khác hẳn (quần áo, đồ vật trong tranh). Thử thêm `<DENSE_REGION_CAPTION>`/`<REGION_PROPOSAL>`
(task thuần visual saliency, không cần hiểu ngôn ngữ) — vẫn chỉ liệt kê vùng NGƯỜI trong
tranh, không tách được icon lấp lánh mờ/trong suốt này thành 1 vùng riêng. Kết luận: đây là
giới hạn THẬT của Florence-2-base (open-vocabulary, không train riêng cho watermark) với
loại watermark trong suốt/tương phản thấp trên nền minh hoạ nhiều chi tiết — không phải lỗi
ngưỡng/prompt có thể vá thêm được nữa (khác hẳn video Gemini/Veo mục 100, vốn định vị được
qua prompt `"small icon in the corner"`).

**Hỏi hướng xử lý qua `AskUserQuestion`** (không suy đoán, để user quyết định trade-off) —
user chọn: "chỉ cần hỗ trợ case của ảnh từ gemini logo, đúng vị trí đó và icon lấp lánh đó
của tất cả các ảnh" → bỏ AI định vị theo nội dung, dùng VỊ TRÍ TƯƠNG ĐỐI CỐ ĐỊNH theo quy
ước watermark Gemini/Nano Banana. Đo tâm icon TƯƠNG ĐỐI trên cả 2 ảnh thật (khác kích thước
hẳn nhau — xác nhận đây là %, không phải toạ độ tuyệt đối): B02 → tâm (90.0%, 83.0%) chiều
rộng/cao; B01 (đo thô hơn do đã bị mờ 1 phần) → tâm ước lượng (90.9%, 83.7%) — khớp nhau
trong sai số <1%, xác nhận watermark Gemini LUÔN ở cùng 1 vị trí tương đối bất kể nội dung
ảnh.

**Fix**: `detector.py::gemini_corner_bbox(image_size)` (mới) — bbox cố định tại tâm
(90%, 83%) chiều rộng/cao, phủ vùng ±4.5%/±5.5% (rộng hơn ~1.7× icon thật đo được để chừa
biên an toàn, vẫn chỉ ~1% diện tích khung hình — không rủi ro phá huỷ nội dung lớn như bug
#1/#2/#3). `pipeline.py::remove_watermark_from_image` **bỏ hẳn Florence-2 cho ảnh** — dùng
`gemini_corner_bbox` làm bbox mặc định khi không truyền `bboxes` tay; bỏ luôn param
`text_input` không còn dùng tới. Video KHÔNG đổi (`remove_watermark_from_video` vẫn dùng
Florence-2 — verify thật mục 100 xác nhận vẫn định vị đúng cho watermark Gemini/Veo trên
video, khác hẳn ảnh minh hoạ chi tiết ở đây).

**Verify**: 3 test mới khoá lại toạ độ đã đo thật (`test_gemini_corner_bbox_covers_measured_
icon_on_b02`, `test_gemini_corner_bbox_is_relative_not_absolute`, `test_gemini_corner_bbox_
is_small_relative_to_frame`) + cập nhật 3 test `remove_watermark_from_image` cũ (không còn
mock Florence-2, xác nhận KHÔNG gọi detect nữa) + 3 test hình dạng bug #3. Full `pytest`
**634 passed**. Không đổi API/schema — không cần cập nhật specs. Backend-only, cần khởi
động lại app: B02 sẽ xoá đúng logo khi bấm lại "Xoá watermark"; B01 vẫn còn phần bị mờ
KHÔNG khôi phục được (mất bản gốc), cần re-upload nếu còn giữ file.

## 117. Bug thật: nút "Xoá watermark toàn bộ slot" trông như chỉ xử lý shot đầu rồi dừng (2026-09-04)

Người dùng báo nút "Xoá watermark toàn bộ slot" chỉ chạy đúng B01 rồi dừng lại, không xử lý
tiếp các slot sau. Kiểm tra `watermark_scan_summary` thật qua backend đang chạy xác nhận
**backend đã xử lý ĐỦ cả batch thành công** (`scanned:3, cleaned:3`) — bug nằm ở tầng UI
không hiển thị đúng, không phải backend dừng giữa chừng.

**Root cause**: `VisualStudio.tsx::removeAllWatermarks` gọi endpoint chạy qua
`BackgroundTasks` (trả về response NGAY khi task còn chưa bắt đầu chạy), rồi chỉ poll lại
đúng 2 LẦN CỐ ĐỊNH (sau 1.2s và 3s) — thiết kế cũ giả định 1 trong 2 lần đó chắc chắn "bắt
được" ít nhất 1 shot đang `visual_status=="generating"` để tự bật vòng poll liên tục qua
`hasInFlight` (`useEffect` sẵn có, poll mỗi 3s tới khi hết shot "generating"). Ảnh giờ xử lý
rất nhanh (mục 116, không còn qua Florence-2) — batch nhiều shot dễ "lọt" đúng khoảng giữa 2
shot (shot trước đã "ready", shot sau chưa kịp chuyển "generating") ở đúng thời điểm 2 lần
poll cố định đó, khiến `hasInFlight` không bao giờ bật lên `true`, vòng poll liên tục không
tự kích hoạt, UI dừng cập nhật hẳn dù backend vẫn chạy tiếp phía sau.

**Fix**: đổi `removeAllWatermarks` sang poll liên tục (mỗi 1s, tối đa 60 lần) tới khi
`watermark_scan_summary.finished_at` đổi khác giá trị TRƯỚC lúc bấm — mốc thời gian
BackgroundTask ghi CHẮC CHẮN lúc thật sự xong toàn batch, không còn suy đoán qua trạng thái
`generating` của từng shot (vốn dễ "lọt" như trên). `tsc --noEmit` sạch. Frontend-only
(Vite hot-reload) — không cần khởi động lại app.

## 118. Bug thật (tiếp mục 116): vùng vá cố định cho watermark Gemini/Nano Banana quá hẹp với 1 số lượt sinh ảnh (2026-09-04)

Người dùng báo tiếp: "slot B02 xóa watermark gemini của ảnh nhưng không được, các slot khác
thì được" — với 1 ảnh test MỚI khác hẳn nội dung 2 ảnh đã dùng để đo vị trí ở mục 116.

**Verify trực tiếp trên đúng ảnh lỗi**: dựng lưới toạ độ + khung đỏ đúng bbox
`gemini_corner_bbox` đang dùng (half-size 4.5%/5.5%) chồng lên ảnh thật của user — xác nhận
vùng vá ĐÚNG vị trí tương đối (nằm giữa 2 mũi giáo trong ảnh, khớp toạ độ đã đo ở mục 116)
nhưng vết mờ/nhoè do LaMa để lại RÕ RÀNG tràn ra ngoài biên TRÊN và biên PHẢI của vùng đã vá
— icon lấp lánh của lượt sinh ảnh này to/lệch hơn 1 chút so với 2 ảnh dùng để đo ban đầu.
Kết luận: nền tảng "vị trí tương đối cố định" (mục 116) vẫn ĐÚNG hướng, chỉ cần vùng phủ
RỘNG RÃI hơn để chịu được biến thiên thực tế giữa các lượt sinh ảnh khác nhau của Gemini
(kích thước/vị trí icon không cố định tuyệt đối tới từng pixel).

**Fix**: `detector.py::_GEMINI_CORNER_HALF_SIZE` tăng từ `(0.045, 0.055)` → `(0.07, 0.09)`
— diện tích vùng phủ từ ~1% lên ~2.5% khung hình (vẫn rất nhỏ so ngưỡng "phá huỷ nội dung
lớn" ~31-35% đã thấy ở bug #1/#2/#3 mục 100/116). Verify lại bằng ảnh thật của user: dựng
lại khung với box MỚI — vùng vá cũ (đã tràn biên) giờ nằm TRỌN bên trong box mới.

**Test**: 1 test mới khoá lại half-size KHÔNG bị vô tình thu hẹp về mức cũ đã biết không đủ
(`test_gemini_corner_bbox_has_generous_margin_after_bug5`), nới ngưỡng "vùng phủ phải nhỏ"
từ <3% lên <5% cho phù hợp kích thước mới (`test_gemini_corner_bbox_is_small_relative_to_
frame`). Full `pytest` **635 passed**. Backend-only — cần khởi động lại app.

## 119. Giọng đọc đa ngôn ngữ cho thị trường nước ngoài (2026-09-04)

Theo yêu cầu người dùng: kênh phục vụ thị trường nước ngoài cần sinh giọng đọc/phụ đề cho
6 ngôn ngữ (Việt/Anh/Đức/Brazil-Bồ Đào Nha/Tây Ban Nha/Pháp), tải riêng SRT+MP3 từng ngôn
ngữ, hiện tag ngôn ngữ nào đã sẵn sàng ở từng block, Output Pack xuất đủ file các ngôn ngữ
đã sinh, video render/timestamp vẫn theo ĐÚNG 1 ngôn ngữ chính, và cấu hình ngôn ngữ chính
+ mẫu giọng clone theo từng ngôn ngữ ở BrandProfile.

### Thiết kế đã chốt qua 3 vòng trao đổi với người dùng

1. **Nguồn văn bản dịch**: ban đầu đề xuất AI tự dịch — người dùng chốt **CHỈ nhập tay**
   qua file import (không xây bước dịch AI). Sau đó làm rõ thêm: file import có sẵn
   **6 cột `VO (VI)`/`VO (EN)`/`VO (DE)`/`VO (PT-BR)`/`VO (ES)`/`VO (FR)`** (đã dịch sẵn
   ngoài app), không phải gõ tay từng block trong Script Studio.
2. **TTS engine**: chỉ OmniVoice cho voice cloning per-language (đã có sẵn hạ tầng
   `reference_audio`, zero-shot, không cần bước "tạo giọng" riêng như ElevenLabs) — không
   làm thêm ElevenLabs Instant Voice Cloning ở đợt này.
3. **UI Script Studio**: mỗi block hiện ngôn ngữ CHÍNH + tiếng Việt song song (chỉ tiếng
   Việt nếu ngôn ngữ chính đã là Việt) — bấm tag ngôn ngữ ở đầu trang thay UI panel ngôn
   ngữ chính, panel tiếng Việt tham chiếu vẫn giữ nguyên.

### Kiến trúc — additive HOÀN TOÀN, ngôn ngữ chính KHÔNG đổi field/hành vi nào

Theo đúng nguyên tắc "script core ⟂ render module" + tiền lệ `layers`/`background_video`
(thêm cấu trúc SONG SONG thay vì sửa field cũ):

- **`ProductionPack.script.body[].audio_by_lang: {lang: text}`** (mới) — văn bản dịch TẤT
  CẢ ngôn ngữ có trong file import. `audio` (field gốc, KHÔNG đổi tên/vị trí) LUÔN =
  `audio_by_lang[primary_language]` — mọi nơi ĐANG đọc `audio` (assembly, `_build_srt`,
  guardrail...) hoạt động y nguyên 100%, không sửa 1 dòng.
- **`BrandProfile.primary_language`** (mới, 1 trong 6, mặc định `"vi"`) — quyết định cột
  VO nào map vào `audio` lúc import (`script_import.py::parse_script_rows`), và ngôn ngữ
  nào dùng field `narration_*`/render/timestamp gốc. **`voice_clone_ref_paths: {lang:
  path}`** (mới) — thay `voice_clone_ref_path` đơn (field đó GIỮ NGUYÊN, đọc như mẫu của
  `primary_language` khi dict thiếu entry — tương thích ngược dữ liệu cũ, xem `engine.py::
  _read_voice_clone_ref_for_lang`).
- **`ShotRenderStatus.narration_translations: {lang: TranslatedNarrationStatus}`** (mới)
  — CHỈ chứa ngôn ngữ KHÁC ngôn ngữ chính (ngôn ngữ chính vẫn dùng `narration_status`/
  `narration_asset_path`/... gốc, y hệt cũ). Asset lưu tên `{shot_id}_{lang}.{ext}`
  (khác `{shot_id}.{ext}` của ngôn ngữ chính).

### Script Import (`script_import.py`) — tương thích ngược 100%

Cột VO đơn cũ ("Kịch bản Giọng đọc (VO Content)") parse y hệt trước — không bắt buộc đổi
sang nhiều cột. File dùng nhiều cột `VO (XX)` (regex `_VO_LANG_COLUMN_RE` bắt mã ngôn ngữ
trong ngoặc, map qua `_VO_LANG_COLUMN_TO_CODE`) — không bắt buộc đủ cả 6, thiếu cột nào
thì `audio_by_lang` thiếu đúng ngôn ngữ đó (rollout dịch dần theo tiến độ). Thêm
`build_template_workbook(multilang=True)` — mẫu 11 cột, nút riêng "Tải mẫu nhập đa ngôn
ngữ" ở Script Studio (chỉ hiện khi đang xem ngôn ngữ khác ngôn ngữ chính).

### Engine (`engine.py`) — hàm mới SONG SONG hàm gốc, không sửa hàm gốc

`generate_narration_translation`/`run_narration_translation_batch`/`regenerate_single_
narration_translation` — bản sao gần như y hệt `generate_narration_asset`/`run_asset_
generation`/`regenerate_single_narration`, chỉ khác nguồn text (`beat.audio_by_lang[lang]`
thay `beat.audio`) và nơi ghi (`status.narration_translations[lang]` thay field gốc). Vẫn
dùng CHUNG `get_tts_chain(db)` (mọi provider TTS đã cấu hình đều thử được — provider không
hỗ trợ `reference_audio` chỉ đơn giản bỏ qua tham số, vẫn sinh được giọng KHÔNG clone nhờ
tự nhận diện ngôn ngữ từ text). `build_narration_download` thêm tham số `lang` — với ngôn
ngữ khác, shot CHƯA dịch bị BỎ QUA (không tính "thiếu", khác ngôn ngữ chính vốn coi MỌI
shot phải có giọng đọc) vì rollout từng ngôn ngữ dần là bình thường; chỉ chặn khi shot ĐÃ
có văn bản nhưng chưa sinh xong.

**Bug thật tự phát hiện lúc tự rà soát lại thiết kế đã chốt (2026-09-04, cùng ngày)** —
người dùng yêu cầu đối chiếu lại từng điểm đã thống nhất, phát hiện: bản build đầu chỉ
dùng ĐÚNG thứ tự `get_tts_chain(db)` đã cấu hình ở Cài đặt — nếu provider MẶC ĐỊNH không
phải OmniVoice (VD ElevenLabs mặc định, OmniVoice chỉ là fallback), mẫu giọng vừa upload
cho 1 ngôn ngữ sẽ KHÔNG có tác dụng gì (ElevenLabs nhận `reference_audio` rồi ÂM THẦM bỏ
qua) — lệch với thiết kế đã chốt ("OmniVoice ưu tiên khi có `voice_clone_ref_paths[lang]`,
fallback theo chain hiện có khi không có"). **Fix**: khi `_read_voice_clone_ref_for_lang`
trả về khác `None` (CÓ mẫu giọng cho ngôn ngữ này), sắp lại `providers` đưa OmniVoice (nếu
có trong chain) lên ĐẦU trước khi thử — `sorted(providers, key=lambda pr: 0 if pr.
provider_name == "omnivoice" else 1)` (stable sort, giữ nguyên thứ tự tương đối phần còn
lại). KHÔNG đụng thứ tự khi không có mẫu giọng (giữ đúng lựa chọn provider của người dùng).
Chỉ sửa ở `generate_narration_translation` — **KHÔNG đụng `generate_narration_asset`**
(ngôn ngữ chính có CÙNG khoảng trống này từ trước, nhưng đó là hành vi ĐÃ CÓ SẴN/đã test
kỹ trước khi tính năng này tồn tại — sửa ở đó là thay đổi hành vi cũ ngoài phạm vi yêu cầu,
để riêng nếu người dùng muốn áp dụng luôn cho ngôn ngữ chính sau này). 2 test mới khoá lại
(`test_generate_narration_translation_prioritizes_omnivoice_when_voice_sample_configured`,
`..._keeps_configured_order_when_no_voice_sample`).

### Router — endpoint mới, endpoint gốc không đổi 1 dòng

`render.py`: `POST .../render/narration-translations/{lang}/start`, `POST .../render/
shots/{shot_id}/regenerate-narration-translation/{lang}`, `GET .../render/shots/{shot_id}/
asset/narration/{lang}`, `GET .../render/narration-download/{lang}`. `pipeline.py`:
`PATCH .../script/body/{index}/translation/{lang}`, `GET .../script/transcript-srt/{lang}`
(`_build_srt` thêm tham số `lang` — timeline theo giọng đọc THẬT của CHÍNH ngôn ngữ đó,
không dùng lại timeline ngôn ngữ chính), `GET .../script/import/template?multilang=true`.
`channels.py`: `POST/GET .../brandprofile/voice-sample/upload/{lang}`. Mọi endpoint mới
validate `lang` thuộc `NARRATION_LANGUAGES` (400 nếu sai).

### Pack Export (`pack_export.py`)

Xuất thêm `transcript_<lang>.srt` + `narration_full_<lang>.mp3` cho MỖI ngôn ngữ có ít
nhất 1 block đã dịch — ngôn ngữ chưa dùng tới (0 block nào có `audio_by_lang[lang]`) BỊ
BỎ QUA HOÀN TOÀN, không liệt kê ở `included` lẫn `skipped` (tránh rác cho ngôn ngữ dự án
không quan tâm). Ngôn ngữ có văn bản nhưng chưa sinh xong giọng đọc → srt vẫn xuất được
(fallback thời lượng ước tính), mp3 vào `skipped` kèm lý do rõ.

### Frontend — Script Studio, ChannelDialog

**ChannelDialog.tsx**: dropdown "Ngôn ngữ chính của kênh" (6 lựa chọn). Khối "Giọng đọc
thương hiệu" cũ đổi tên kèm ngôn ngữ chính hiện tại; thêm khối mới "Giọng đọc mẫu cho ngôn
ngữ khác" — 1 hàng/ngôn ngữ (component `VoiceSampleLangRow` tự quản lý state upload/xoá/
cache-bust riêng, tránh nhân bản 5 bộ `useState`).

**ScriptStudio.tsx**: thanh 6 tag ở đầu trang chọn `viewLang` (mặc định = ngôn ngữ chính)
— mọi nút hàng loạt (Sinh giọng đọc/Sinh lại toàn bộ/Nghe toàn bộ/Tải mp3/Tải srt) VÀ
panel Audio từng block đều theo `viewLang` này thay vì cố định ngôn ngữ chính. Khi
`viewLang === primaryLanguage`, mọi hàm gọi THẲNG endpoint gốc (`startRender`/
`regenerateShotNarration`/...) — **0 đổi hành vi cho channel chỉ dùng 1 ngôn ngữ, không
ai từng bấm tag nào**. Panel Tiếng Việt tham chiếu hiện SONG SONG khi ngôn ngữ chính khác
Việt VÀ đang xem ngôn ngữ khác Việt (đúng yêu cầu, không lặp panel khi đang xem chính
Việt). Tag trạng thái nhỏ/block (VI/EN/DE...) báo ngôn ngữ nào đã có giọng đọc ready —
độc lập với `viewLang` đang xem. **Bug thật tự phát hiện lúc rà soát**: `hasInFlight`
(quyết định có tự bật vòng poll liên tục 3s hay không) ban đầu chỉ theo dõi `narration_
status` gốc — batch dịch NGÔN NGỮ KHÁC chạy lâu sẽ không tự bật poll liên tục (cùng lớp
bug đã sửa ở `VisualStudio.tsx::removeAllWatermarks`, mục báo cáo trước đó cùng ngày) —
sửa thành kiểm tra CẢ `narration_translations` của mọi ngôn ngữ.

**`ScriptImportControls.tsx`** (nút "Nhập kịch bản từ file" + "Tải file mẫu" dùng ở
BriefEditor/Gate1Outline — lượt upload script ĐẦU TIÊN) — **sót thật phát hiện lúc rà
soát**: bản đầu chỉ thêm nút "Tải mẫu đa ngôn ngữ" ở Script Studio, trong khi lượt upload
THẬT SỰ đầu tiên (nơi người dùng cần chọn ĐÚNG mẫu trước khi điền) nằm ở component này,
KHÔNG phải Script Studio. Thêm nút "Mẫu đa ngôn ngữ" cạnh nút mẫu đơn ngôn ngữ ở đây.

### Test

File mới `test_narration_translations.py` (25 test) — engine (`generate_narration_
translation` bỏ qua đúng khi chưa dịch, sinh đúng khi có text, KHÔNG đụng field gốc,
ưu tiên OmniVoice khi có mẫu giọng/giữ nguyên thứ tự khi không có, `_read_voice_clone_
ref_for_lang` + tương thích ngược), router (batch/single generate, asset serving,
download báo thiếu đúng, SRT theo ngôn ngữ, sửa tay translation, upload mẫu giọng theo
ngôn ngữ), pack export (bundle đa ngôn ngữ đúng include/skip/bỏ qua). Thêm 7 test vào
`test_script_import.py` (cột đa ngôn ngữ, tương thích ngược, chọn `audio` theo `primary_
language`, template đa ngôn ngữ). Sửa 1 test cũ lệch do đổi thông điệp lỗi ("6 cột" →
"5 cột", phản ánh đúng 5 cột cố định + VO linh hoạt). Full `pytest` **667 passed** (635
trước đợt này + 32 mới — 25 ở file mới + 7 ở test_script_import.py). `tsc --noEmit` sạch
(frontend). Không đổi `electron/`. `specs/03_api.md`/`specs/04_data_schemas.md` cập nhật
đầy đủ.

**Lưu ý flakiness KHÔNG liên quan đợt này** — chạy full suite nhiều lần thấy thỉnh thoảng
`test_library.py`/`test_asset_vault.py` fail với `IntegrityError: UNIQUE constraint failed:
channel.id`/`asset.id` — xác nhận qua chạy lại RIÊNG các test đó (pass ngay, không đụng gì)
đây là race có sẵn từ trước (ID sinh theo `int(time.time()*1000)`, 2 request tạo liên tiếp
quá nhanh trong CÙNG 1 test session có thể trùng mili-giây) — không phải do thay đổi ở đợt
này, không sửa (ngoài phạm vi yêu cầu).

**Ngoài phạm vi đợt này (ghi nhận có chủ đích)**: dịch AI tự động, ElevenLabs Instant
Voice Cloning per-language, đồng bộ khung hình video theo timeline riêng từng ngôn ngữ
(video/hình ảnh LUÔN theo ngôn ngữ chính — các ngôn ngữ khác chỉ xuất audio track + srt
rời, đúng mô hình "nhiều audio track cho 1 video" của YouTube).

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được tính năng này.

## 120. Gỡ bỏ tính năng "ảnh tham chiếu phong cách" (IPAdapter) + thêm provider ảnh local Flux.1-dev (GGUF) cho kênh phong cách đặc thù (2026-09-09)

Theo yêu cầu người dùng: cấu hình visual style cho kênh mới "Warum Mensch" (whiteboard/
stick-figure + flat illustration kiểu Kurzgesagt) — 2 câu hỏi trong 1 yêu cầu: (1) hỗ trợ
2 LoRA cụ thể trên Civitai ("Stick Figure - CE" model 1730560, "Flat Illustration" model
2118658), (2) "ảnh tham chiếu còn work không?".

### Phần 1 — Gỡ bỏ hoàn toàn "ảnh tham chiếu phong cách" (IPAdapter)

Điều tra lại xác nhận: tính năng xây ở mục 75 (2026-08-23) dùng custom node
`ComfyUI_IPAdapter_plus` — custom node này **chưa từng được cài** trên máy người dùng, mọi
lần gọi âm thầm rơi vào nhánh fallback "không có IPAdapter" đã build sẵn cho trường hợp
ComfyUI từ chối job. Tính năng thực chất KHÔNG BAO GIỜ hoạt động kể từ khi build. Hỏi lại
người dùng qua `AskUserQuestion`, quyết định: **"nếu không work thì bỏ luôn tính năng ảnh
tham chiếu"** — không scope hẹp cho riêng kênh mới, bỏ TOÀN BỘ.

Đã xoá:
- Backend: `BrandProfile.style_reference_paths`/`style_reference_weight` (schema);
  `_add_ipadapter_nodes` + toàn bộ tham số `reference_images`/`style_reference_weight`
  (`image_comfy_sdxl.py`, cả `_build_txt2img_workflow`/`_build_img2img_workflow`/
  `generate`/`_generate_locked`, kể cả logic fallback-retry-không-IPAdapter khi ComfyUI
  từ chối job); toàn bộ cơ chế img2img của `image_localai.py` (CHỈ tồn tại để phục vụ
  tính năng này — `_virtual_model_name`/`_sync_model`/`_apply_model` bỏ tham số `img2img:
  bool`, trước đây tạo 2 model LocalAI riêng "studioflow-sdxl"/"studioflow-sdxl-img2img",
  giờ chỉ còn 1); 3 endpoint CRUD `/channels/{id}/brandprofile/style-references/*`
  (`routers/channels.py`); `_local_sdxl_kwargs(brand)` (`engine.py`) bỏ đọc
  `reference_images`/`style_reference_weight`.
- Frontend: `styleReferencePaths`/`styleReferenceWeight` (Draft, `ChannelDialog.tsx`);
  `uploadStyleReference`/`removeStyleReference` + state hooks liên quan; toàn bộ card UI
  "Ảnh tham chiếu phong cách" (upload/preview/weight-slider); `style_reference_paths`/
  `style_reference_weight` khỏi `BrandProfile` (`types.ts`) và payload PUT; 3 hàm client
  `uploadStyleReference`/`deleteStyleReference`/`styleReferenceUrl` (`client.ts`).
- Test: xoá 6 test IPAdapter (`test_image_comfy_sdxl.py`) + 4 test img2img
  (`test_image_localai.py`) + 1 test `_local_sdxl_kwargs` đọc style reference
  (`test_render.py`), cập nhật các test còn lại khớp signature/kwargs mới.

Tier-2 `reference_image` (số ít — cơ chế anchor/img2img RIÊNG dùng Thumbnail, đã build từ
trước mục 75) **KHÔNG bị ảnh hưởng** — cơ chế khác hẳn, không liên quan quyết định này.

### Phần 2 — Provider ảnh local Flux.1-dev (GGUF) mới: `local_flux`

Xác nhận qua Civitai: cả 2 LoRA người dùng yêu cầu đều kiến trúc **Flux.1-dev**, không
tương thích `local_sdxl` (SDXL). Hỏi người dùng chọn hướng checkpoint Flux qua
`AskUserQuestion` — người dùng giao lại: "research lora phù hợp cho visual style của
kênh" (không chọn preset có sẵn, uỷ quyền quyết định kỹ thuật).

Research xác nhận (WebFetch/WebSearch trực tiếp source code + tài liệu chính thức, không
suy đoán): stack nhiều LoRA trên checkpoint fp8 gộp 1 file (`flux1-dev-fp8.safetensors`,
~17.2GB) có rủi ro tràn VRAM tài liệu ghi rõ "kể cả trên RTX 4090"; UNet quantized GGUF
qua custom node `ComfyUI-GGUF` (github.com/city96/ComfyUI-GGUF) "tích hợp liền mạch với
LoRA" — chọn GGUF (mặc định `flux1-dev-Q8_0.gguf`, ~12.7GB, near-lossless) phù hợp hơn
cho GPU 16GB (RTX 5060 Ti) của người dùng khi chồng 2 LoRA cùng lúc.

File mới `backend/app/providers/image_comfy_flux.py` (`ComfyFluxImageProvider`,
`provider_name="local_flux"`) — graph ComfyUI hoàn toàn mới (Flux là flow-matching model,
khác hẳn diffusion U-Net của SDXL): `UnetLoaderGGUF` → `ModelSamplingFlux`
(`max_shift=1.15`/`base_shift=0.5`, bắt buộc, SDXL không cần) → `LoraLoaderModelOnly`
chain (không phải `LoraLoader` — LoRA Flux thường chỉ patch UNet, không patch CLIP) →
`KSampler` (`positive` từ `CLIPTextEncode`→`FluxGuidance(guidance=3.5)`, `negative` từ
`ConditioningZeroOut`, **`cfg` PHẢI = 1.0** — cfg thật nằm ở `FluxGuidance`, lẫn lộn 2 chỗ
là lỗi kinh điển) → `VAEDecode`/`SaveImage`. Dựng từ source code `city96/ComfyUI-GGUF`
(`UnetLoaderGGUF` nhận `unet_name`, không có LoRA node riêng) + docs.comfy.org
(`ModelSamplingFlux` defaults) + workflow JSON mẫu chính thức Comfy.org
(`flux_schnell_full_text_to_image`, cấu trúc `FluxGuidance`+`ConditioningZeroOut`+
`KSampler(cfg=1.0)`). **CHƯA verify thật trên GPU** — cùng quy ước "build từ research,
chưa verify" như Sora/Veo lúc mới build, ghi rõ trong docstring + `test_connection()`.

Wiring:
- `BrandProfile.flux_style_loras: list[StyleLoraEntry]` (schema mới, field RIÊNG khỏi
  `style_loras` — kiến trúc không tương thích chéo, mặc định `strength=0.5` khớp khoảng
  0.4-0.6 người dùng đề xuất khi chồng 2 LoRA).
- `engine.py`: `_LOCAL_FLUX_PROVIDER_NAMES = ("local_flux",)` tách RIÊNG khỏi
  `_LOCAL_IMAGE_PROVIDER_NAMES` (2 chỗ dùng tuple đó — anchor Wan, strip tag overlay chữ
  cho SDXL — mang ý nghĩa đặc thù SDXL, không áp dụng Flux); `_local_flux_kwargs(brand)`
  đọc `flux_style_loras` thành `{"loras": [...]}`, dispatch theo `provider.provider_name`.
- `factory.py`: đăng ký `"local_flux": ComfyFluxImageProvider` vào `_IMAGE_ADAPTERS`.
- `image_comfy_sdxl.py::list_comfyui_models` + `GET /providers/local-sdxl/models`: thêm
  `kind="unet_gguf"` (dùng CHUNG endpoint ComfyUI `GET /models/{kind}` có sẵn — thư mục
  `unet_gguf` do `ComfyUI-GGUF` tự đăng ký như 1 model kind bình thường).
- Frontend: `ChannelDialog.tsx` thêm card "Style LoRA cho ảnh local Flux.1-dev" (tái dùng
  `ComfyModelSelect kind="loras"` — LoRA Flux/SDXL sống chung thư mục ComfyUI); `types.ts`
  thêm `flux_style_loras`; `ProviderSettings.tsx` thêm entry "ComfyUI Flux (local GPU,
  GGUF) — CHƯA verify" vào `LOCAL_CATALOG.image` + nhánh `ComfyModelSelect
  kind="unet_gguf"` cho ô Model (cả màn sửa provider đã có lẫn dialog thêm provider mới).

### Test

File mới `test_image_comfy_flux.py` (11 test — GGUF unet name mặc định/tuỳ chỉnh,
`cfg=1.0`+`FluxGuidance`+`ConditioningZeroOut`, không/1/2 LoRA qua `LoraLoaderModelOnly`,
bucket vuông cố định cho mọi aspect_ratio, lỗi ComfyUI/interrupt, `test_connection`). Thêm
2 test `_local_flux_kwargs` (`test_render.py`), 1 test `kind=unet_gguf`
(`test_providers.py`). Full `pytest` **671 passed** (670 sau khi gỡ IPAdapter + thêm Flux
kwargs/provider tests, +1 test `unet_gguf`). `tsc --noEmit` sạch (frontend, kể cả sau khi
thêm UI Flux LoRA). `specs/03_api.md`/`04_data_schemas.md`/`05_ai_providers.md` (§8k cập
nhật ghi quyết định gỡ IPAdapter, §8m mới cho `local_flux`) đã cập nhật đầy đủ.

**Ngoài phạm vi đợt này (ghi nhận có chủ đích)**: verify thật `local_flux` trên GPU người
dùng (cần tự cài `ComfyUI-GGUF` + tải UNet GGUF/text encoder/VAE/2 LoRA Civitai trước);
tích hợp Flux vào anchor ảnh cho video Wan (`_try_generate_wan_anchor_image` vẫn chỉ dùng
`local_sdxl`); LoRA Flux cho `local_wan`/video (chỉ ảnh).

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được tính năng này.

## 121. Cài đặt + verify THẬT trên GPU cho provider `local_flux` (tiếp mục 120) — sửa lỗi tài liệu, phát hiện trigger word LoRA (2026-09-09)

Tiếp ngay sau mục 120 (build `local_flux` mới, "CHƯA verify thật trên GPU"), người dùng
yêu cầu triển khai thật: cài custom node + tải model + verify sinh ảnh. Toàn bộ phần này
làm trực tiếp trên máy người dùng qua Bash (không phải chỉ code) — ghi lại đầy đủ vì phát
hiện 2 vấn đề thật cần biết cho lần build provider ComfyUI tiếp theo.

### Bug tài liệu phát hiện lúc người dùng bấm "Thêm provider"

Người dùng bấm "Thêm provider" chọn "ComfyUI Flux" báo lỗi `404 Not Found` ở
`GET /models/unet_gguf`. Đào sâu source code `ComfyUI-GGUF/nodes.py` (đọc trực tiếp qua
WebFetch, không suy đoán) xác nhận 2 điều:
1. 404 (không phải 502) ở endpoint này là **hành vi ĐÚNG/dự kiến** khi ComfyUI đang chạy
   nhưng chưa cài custom node `ComfyUI-GGUF` — key "unet_gguf" chỉ được đăng ký vào
   `folder_paths.folder_names_and_paths` SAU KHI custom node đó được ComfyUI load lúc khởi
   động. KHÔNG chặn việc thêm provider (dropdown tự fallback ô nhập tay).
2. **Sai tài liệu ban đầu**: `"unet_gguf"` KHÔNG PHẢI 1 thư mục vật lý riêng cần tạo
   (từng ghi `ComfyUI/models/unet_gguf/`). Source thật:
   `update_folder_names_and_paths("unet_gguf", ["diffusion_models", "unet"])` — hàm này
   CHỈ ALIAS key "unet_gguf" trỏ vào path đã đăng ký sẵn cho `diffusion_models` — không tạo
   thư mục mới. File GGUF thật cần đặt ở `ComfyUI/models/diffusion_models/`. Đã sửa mọi
   docstring/hint liên quan (`image_comfy_flux.py`, `image_comfy_sdxl.py::
   list_comfyui_models`, `ProviderSettings.tsx` hint, `specs/05_ai_providers.md`) — không
   đổi code (endpoint/kind vẫn đúng, chỉ sai chỗ đặt file vật lý ghi trong tài liệu).

### Cài đặt thật thực hiện qua Bash (không qua tay người dùng, trừ phần bị khoá)

- `git clone` `city96/ComfyUI-GGUF` vào `custom_nodes/` + `pip install -r requirements.txt`
  vào `python_embeded` của ComfyUI portable (package `gguf>=0.13.0`).
- Tải 3 file CÔNG KHAI trực tiếp bằng `curl` chạy nền (~18GB tổng, verify trước bằng
  `curl -I` xác nhận không cần auth): `flux1-dev-Q8_0.gguf` (12.7GB, city96/FLUX.1-dev-gguf
  trên HuggingFace) → `models/diffusion_models/`; `t5xxl_fp8_e4m3fn.safetensors` (4.9GB),
  `clip_l.safetensors` (246MB) — cả 2 từ `comfyanonymous/flux_text_encoders` → `models/
  text_encoders/`. Theo dõi tiến độ qua 1 task nền poll 30s/lần đến khi đủ kích thước.
- `ae.safetensors` (335MB, VAE) — GATED bởi HuggingFace (`black-forest-labs/FLUX.1-dev`
  yêu cầu tài khoản đã "Agree and access" license, xác nhận qua `curl` trả 401) — người
  dùng tự tải + đặt vào `models/vae/`.
- 2 LoRA Civitai (mục 120, Civitai chặn tải ẩn danh 401) — người dùng tự tải + đặt vào
  `models/loras/` (thư mục CHUNG với LoRA SDXL, không tách theo kiến trúc — đúng thiết kế).
- Khởi động lại ComfyUI: StudioFlow backend lúc này đã tắt (app đóng) nên không dùng được
  API `/system/local-services/comfyui/*` — `taskkill` tiến trình ComfyUI cũ + relaunch
  đúng lệnh `local_services.py::SERVICES["comfyui"].start_cmd` dùng. Log xác nhận
  `ComfyUI-GGUF: Allowing full torch compile`, custom node load sạch 0.1s, không lỗi.
  `GET /models/unet_gguf` hết 404, trả đúng `["flux1-dev-Q8_0.gguf"]`.

### Verify THẬT qua GPU — không còn "CHƯA verify"

Chạy trực tiếp `ComfyFluxImageProvider.generate()` (không qua UI, gọi thẳng qua Python vì
backend app đang tắt) 2 lần qua RTX 5060 Ti (16GB VRAM, ~14.8GB free lúc test):
1. Không LoRA — txt2img thuần "a simple stick figure character waving, whiteboard style,
   minimalist line art" → PNG hợp lệ (401KB), 20/20 bước sampling, ~78s, đúng phong cách
   stick-figure đơn giản như prompt.
2. Có `flux_style_loras` (2 LoRA, strength 0.5/0.5 — khớp cấu hình đã lưu ở mục 120) —
   PNG hợp lệ, ~76-84s.

**Phát hiện quan trọng — trigger word LoRA**: lần test (2) ĐẦU TIÊN (chưa thêm trigger
word vào prompt) cho kết quả LoRA "Stick Figure - CE" gần như KHÔNG có tác dụng thấy được
— nhân vật vẫn là hoạt hình chi tiết bình thường, không mang nét stick-figure nào. Tra lại
Civitai API (model 1730560, version Flux.1 D id 1958580) xác nhận LoRA này cần trigger
word `stckfgrCE_style`/`a stick figure drawing` mới kích hoạt — tương tự "Flat
Illustration" cần `FlatIllustration`. Test lại VỚI trigger word cho kết quả rõ rệt khác
hẳn — đúng phong cách flat-illustration/Kurzgesagt (mảng màu tươi, viền đậm, mặt trời/mây
đơn giản, thân thiện). Đây KHÔNG phải lỗi code — là đặc tính phổ biến của LoRA Civitai
(nhiều LoRA train với trigger word riêng, chỉ load vào graph không đủ kích hoạt phong
cách). Vì `_local_flux_kwargs`/provider không thể biết trước trigger word của LoRA người
dùng chọn, đã cập nhật `BrandProfile.visual_style_prompt` của kênh "Warum Mensch" (cơ chế
CÓ SẴN từ trước, tự nối vào MỌI prompt sinh ảnh của kênh qua `_build_visual_prompt`) để
chứa sẵn 2 trigger word — người dùng chọn LoRA Flux khác cho kênh khác cần tự làm tương tự
(bước thủ công bắt buộc, không tự động hoá được vì app không biết trigger word của LoRA
tuỳ ý người dùng chọn).

**Kết quả style cuối cùng**: nhân vật ra hoạt hình phẳng đầy đủ chi tiết (mặt/tóc/quần áo),
KHÔNG phải que-tay nghĩa đen dù tên LoRA là "Stick Figure" — hỏi lại người dùng qua
`AskUserQuestion`, xác nhận CHẤP NHẬN kết quả này ở weight 0.5/0.5 (đúng tinh thần
"flat-illustration/Kurzgesagt" trong brief gốc kênh), không cần điều chỉnh weight thêm.

### Cấu hình cuối cùng đã áp dụng (qua DB trực tiếp, backend app đang tắt lúc này)

- Provider `local_flux` (đã có sẵn trong DB do người dùng tự bấm "Thêm provider" trước đó,
  dù gặp lỗi 404 dropdown — lỗi đó không chặn submit): set `model_name =
  flux1-dev-Q8_0.gguf`, đặt làm **provider mặc định cho task "image"** (thay `local_sdxl`,
  theo xác nhận người dùng — ảnh hưởng TOÀN APP, mọi kênh khác cũng chuyển sang sinh ảnh
  bằng Flux từ nay).
- `BrandProfile.flux_style_loras` (kênh Warum Mensch): giữ nguyên
  `[{StickFigure01c_CE_FLUX_AIT2k.safetensors: 0.5}, {878859794_-_FlatIllustration.
  safetensors: 0.5}]` từ mục trước.
- `BrandProfile.visual_style_prompt` (kênh Warum Mensch, version 25): thêm mới — chứa 2
  trigger word LoRA + mô tả phong cách whiteboard/flat-illustration theo brief gốc.

### Ngoài phạm vi đợt này

Test chỉ chạy qua gọi provider trực tiếp (backend app tắt lúc verify) — CHƯA test qua UI
Visual Studio thật (chọn shot → bấm sinh ảnh → xem kết quả trong app). Khuyến nghị người
dùng tự làm bước này sau khi mở lại app để xác nhận toàn luồng UI hoạt động đúng. Không
đổi code nào ở đợt này ngoài sửa docstring/hint (bug tài liệu unet_gguf) — mọi thay đổi
thật là cấu hình DB + file model trên máy, không phải code.

## 122. Tổng quát hoá trigger word LoRA — `StyleLoraEntry.trigger_words` thay hardcode riêng từng kênh (tiếp mục 121, 2026-09-09)

Mục 121 giải quyết tạm bằng cách gõ tay 2 trigger word thẳng vào
`BrandProfile.visual_style_prompt` của riêng kênh "Warum Mensch" — người dùng chỉ ra đúng
vấn đề: đây là hardcode 1 kênh, không tổng quát khi tạo kênh mới với LoRA khác. Sửa lại
theo hướng tổng quát: gắn trigger word VÀO TỪNG LoRA entry, app tự động áp dụng cho bất kỳ
kênh nào chọn đúng LoRA đó — không cần biết trước kênh nào dùng LoRA gì.

### Thiết kế

- `StyleLoraEntry` (`app/schemas/__init__.py`) thêm field `trigger_words: str = ""` —
  dùng CHUNG cho cả `style_loras` (SDXL) LẪN `flux_style_loras` (Flux, cùng type). Rỗng
  mặc định (nhiều LoRA không cần trigger word — không đổi hành vi cũ). App KHÔNG tự tra
  cứu trigger word (cần mạng + khớp đúng file/version Civitai qua hash, rủi ro sai/không
  ổn định) — người dùng tự điền khi thêm LoRA, thường đã đọc trang Civitai của LoRA đó để
  tải file nên đã sẵn thông tin.
- `app/render/engine.py::_lora_trigger_words(brand, *, field)` (hàm mới) — gộp
  `trigger_words` không rỗng của MỌI entry trong `brand[field]` thành 1 chuỗi cách nhau
  ", ". `_build_visual_prompt` thêm tham số `lora_trigger_words: str = ""` — caller tính
  SẴN (hàm build prompt không biết provider nào đang dùng nên không tự chọn field đúng),
  nối NGAY SAU `cultural_lock_positive` (cùng nhóm "token bắt buộc xuất hiện", khác
  `visual_style_prompt` — mô tả phong cách chung chung, không LoRA nào phụ thuộc trực
  tiếp từng từ trong đó).
- 2 call site cập nhật: dispatch chính trong `generate_visual_asset` (đọc
  `style_loras`/`flux_style_loras` theo ĐÚNG provider trong chain, giống
  `_local_sdxl_kwargs`/`_local_flux_kwargs`) và `_try_generate_wan_anchor_image` (anchor
  ảnh cho Wan LUÔN dùng `local_sdxl`, nên luôn đọc `style_loras`).

### Frontend

`ChannelDialog.tsx` — mỗi dòng LoRA (cả 2 card SDXL/Flux) đổi từ 1 hàng ngang (tên/weight/
xoá) sang 2 hàng: hàng 1 giữ nguyên, hàng 2 thêm ô nhập tự do "Trigger word của LoRA này
(tuỳ chọn, xem trang Civitai)". `types.ts` thêm `trigger_words: string` vào type LoRA của
`BrandProfile`.

### Migrate kênh "Warum Mensch" sang cơ chế mới

Chuyển 2 trigger word đã hardcode ở mục 121 (`visual_style_prompt`) sang đúng
`flux_style_loras[].trigger_words` per-entry; `visual_style_prompt` trở lại đúng vai trò
(chỉ mô tả phong cách chung chung, không còn trigger word). Verify lại: gọi thẳng
`_build_visual_prompt`/`_lora_trigger_words` với brand config đã migrate — prompt sinh ra
chứa ĐÚNG 2 trigger word y hệt lần test ảnh thật thành công ở mục 121 (không cần sinh ảnh
lại — logic ghép chuỗi đã unit test đầy đủ, chỉ cần xác nhận đúng input/output khớp).

### Test

5 test mới trong `test_render.py`: `_lora_trigger_words` (gộp đúng, bỏ qua entry rỗng,
brand rỗng trả rỗng), `_build_visual_prompt` với/không `lora_trigger_words`. Full `pytest`
**676 passed**. `tsc --noEmit` sạch (frontend, sau khi thêm ô trigger word + đổi layout
LoRA row).

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

## 123. Bug thật: `local_flux` sinh ảnh luôn vuông 1:1 bất kể aspect_ratio — sửa để khớp long-form (16:9)/short-form (9:16) (2026-09-09)

Người dùng phát hiện: ảnh sinh bằng provider `local_flux` mới (mục 120-122) luôn ra vuông
1:1, dù project là long-form (cần 16:9) hay short-form (cần 9:16). Hỏi thẳng "cần giải
pháp phù hợp".

### Nguyên nhân

`image_comfy_flux.py` lúc build (mục 120) đặt `_WIDTH = _HEIGHT = _WIDTH_VERTICAL =
_HEIGHT_VERTICAL = 1024` — TẤT CẢ giống nhau, bất kể `aspect_ratio` — theo lý luận ban đầu
"Flux không lệch bucket train cố định như SDXL (RoPE thay vì bucket) nên không cần cặp W/H
riêng, cứ để `assembly.py::aspect_fill_mode` (crop/blur) xử lý hậu kỳ". Lý luận này ĐÚNG
về mặt kỹ thuật huấn luyện (Flux thật sự linh hoạt hơn SDXL về độ phân giải) nhưng SAI về
hiệu quả thực tế: sinh vuông rồi crop về 16:9/9:16 MẤT ~44% nội dung ảnh mỗi chiều, dễ cắt
lẹm chủ thể đã được model canh giữa theo bố cục vuông — lãng phí khả năng sinh đúng khung
hình đích ngay từ đầu mà Flux vốn làm được.

### Sửa

Đổi `_WIDTH = 1344, _HEIGHT = 768` (16:9) và `_WIDTH_VERTICAL = 768, _HEIGHT_VERTICAL =
1344` (9:16) — tái dùng ĐÚNG cặp độ phân giải `local_sdxl` đang dùng
(`image_comfy_sdxl.py`, đã verify tốt trong app này: ~1MP, tỷ lệ 1.75 rất gần 16:9=1.778)
thay vì tự chọn số mới — nhất quán toàn app, không cần nghiên cứu lại từ đầu. Cả
`_build_txt2img_workflow`/`EmptyLatentImage`/`ModelSamplingFlux` đã parametrize sẵn theo
width/height truyền vào, chỉ cần đổi hằng số — không đổi logic graph.

Cập nhật docstring liên quan (mục đầu file — sửa 2 đoạn stale: đoạn nói "vuông 1024x1024
mặc định" VÀ đoạn nói trigger word "cần gõ vào `visual_style_prompt`" — đoạn sau đã lỗi
thời từ mục 122, tiện sửa luôn cho khớp cơ chế `trigger_words` mới).

### Verify THẬT qua GPU

Sinh 2 ảnh (cùng prompt "a scientist stick figure character standing next to a mountain"
+ trigger word 2 LoRA, seed=777) — 16:9 (1344x768, ~88s) và 9:16 (768x1344, ~46s). Xem
trực tiếp cả 2 ảnh: đúng khung hình, bố cục hợp lý cho từng định dạng (16:9 — nhân vật
lệch trái, nhiều không gian ngang cho cảnh nền; 9:16 — nhân vật căn giữa, đủ khoảng trống
đầu/chân) — không bị cắt lẹm như lo ngại nếu vẫn crop hậu kỳ từ ảnh vuông.

### Test

2 test workflow JSON cũ (`test_generate_aspect_ratio_9_16_still_uses_square_bucket`) đổi
thành 2 test mới: `test_generate_default_aspect_ratio_uses_landscape_resolution` (mặc định
1344x768) + `test_generate_aspect_ratio_9_16_uses_portrait_resolution` (768x1344). Full
`pytest` **677 passed**.

Backend có thay đổi — **cần khởi động lại app** để dùng được.

## 124. Visual Studio: hiện tiếng Việt tham chiếu dưới narration ngôn ngữ chính (2026-09-09)

Theo yêu cầu người dùng: "trong bước visual studio, tôi muốn hiển thị thêm phần text cho
tiếng việt để tham chiếu bên dưới text của ngôn ngữ chính cho mỗi block — tương [tự] cách
xử lý ở phần script studio". Script Studio đã có cơ chế này từ mục 119 (giọng đọc đa ngôn
ngữ) — Visual Studio (hiện shot card, không phải block editor) chưa có.

### Thiết kế

`pack.script.body` (đầy đủ `ScriptBodyItem[]`, kể cả `audio_by_lang`) ĐÃ được truyền sẵn
vào `VisualStudio.tsx` qua props — không cần fetch/endpoint mới, không đổi type nào ở
`Shot`/`ShotRenderStatus`/`ScriptBodyItem`.

- Thêm state `primaryLanguage` (mặc định `"vi"`) load từ `api.getBrandProfile(project.
  channel_id)` — y hệt cách Script Studio làm (`ScriptStudio.tsx`).
- **Bug tiềm ẩn nhân tiện sửa**: `snippetFor(ts)` cũ khớp shot↔block bằng
  `timestamp_sec === linked_timestamp_sec` — CÙNG LỚP bug đã fix ở Script Studio (mục 31
  IMPLEMENTATION_REPORT.md: giá trị này lệch được giữa lúc tạo shot và lúc script sửa/
  import lại, khớp `===` thất bại âm thầm). Đổi thành `bodyItemFor(shot)` — khớp bằng
  `block_id` TRƯỚC (ổn định, duy nhất, `Shot.block_id`/`ScriptBodyItem.block_id` đều có
  sẵn), fallback về `timestamp_sec` khi shot chưa có `block_id` (dữ liệu cũ, không đổi
  hành vi).
- `narrationTextsFor(shot)` trả `{primary, vi}` — `primary` = `b.audio` (không đổi hành vi
  hiện có), `vi` = `b.audio_by_lang?.vi`.
- `ShotCard` nhận thêm 2 prop: `viSnippet: string`, `showViSnippet: boolean`
  (`primaryLanguage !== "vi"` — tính sẵn ở component cha, ĐƠN GIẢN HƠN Script Studio 1
  chút vì Visual Studio không có khái niệm `viewLang` — luôn hiện đúng 1 bản ngôn ngữ
  chính, không có nút đổi ngôn ngữ xem như Script Studio). Panel tham chiếu render NGAY
  TRONG cùng khối `<div>` narration hiện có (dưới `snippet`), TÁI DÙNG chính xác recipe
  styling Script Studio đã dùng (viền chấm mờ phân cách, nhãn hoa nhỏ opacity 0.5, giá trị
  opacity 0.75, fallback "— chưa có —" khi rỗng) — nhất quán UI giữa 2 màn hình.

### Verify

`tsc --noEmit` sạch. Kiểm tra dữ liệu thật qua API (backend đang chạy sẵn): project
`prj_1788792523205` (kênh "Warum Mensch", `primary_language="de"`) có đủ 12 block với
`audio` (tiếng Đức) + `audio_by_lang.vi` (tiếng Việt) + `shots[].block_id` khớp đúng —
panel tham chiếu sẽ hiện ngay khi mở Visual Studio project này (Vite hot-reload, không cần
khởi động lại app). KHÔNG đổi backend — thuần frontend, dữ liệu đã có sẵn từ mục 119.

## 125. Cài đặt Comfy MCP làm công cụ dev-time + chứng minh giá trị qua research template chính thức (2026-09-09)

Người dùng đề xuất: ComfyUI có MCP server chính chủ (Comfy-Org) cho phép agent chủ động
search template/node và dựng workflow. Sau khi trao đổi (2-3 sentence exploratory answer),
người dùng chốt hướng: **dùng Comfy MCP làm công cụ DEV-TIME cho tôi (Claude Code) khi
build provider mới sau này — KHÔNG đưa vào runtime của Visual Studio** (agent tự dựng
workflow mỗi lần bấm sinh ảnh sẽ tốn thêm LLM call/độ trễ mỗi shot + graph không còn cố
định/tái lập được — lệch nguyên tắc "mỗi bước là hành động rõ ràng, pipeline local miễn
phí" của CLAUDE.md, và đúng loại rủi ro (sai tên node/tham số) mà cả phiên làm việc mục
120-123 tốn nhiều giờ để loại bỏ khỏi `local_sdxl`/`local_flux`). ComfyUI giữ đúng vai trò
backend sinh ảnh/video — không có agent nào trong vòng lặp runtime.

### Cài đặt

`comfy-mcp` (PyPI, package chính thức Comfy-Org, v0.10.0) + `comfy-cli` (v1.20.0, comfy-mcp
gọi qua binary `comfy` trên PATH, không tự kèm) — cài vào venv RIÊNG
`C:\Tools\comfy-mcp\.venv` (KHÔNG cài vào `.venv` backend app hay `python_embeded` của
ComfyUI portable — đây là công cụ dev-time tách biệt hoàn toàn, không phải dependency của
app). Đăng ký qua `.mcp.json` MỚI ở gốc repo (Claude Code tự nhận project-scoped MCP config
này ở phiên SAU — phiên hiện tại KHÔNG tự nhận tool mới giữa chừng, cần khởi động lại):
```json
{
  "mcpServers": {
    "comfy-mcp": {
      "command": "C:\Tools\comfy-mcp\.venv\Scripts\comfy-mcp.exe",
      "env": {
        "COMFY_BIN": "C:\Tools\comfy-mcp\.venv\Scripts\comfy.exe",
        "COMFY_LOCAL_URL": "http://127.0.0.1:8188"
      }
    }
  }
}
```
`COMFY_LOCAL_URL` trỏ THẲNG vào ComfyUI portable ĐANG CHẠY sẵn (`C:\Tools\ComfyUI_extract\
...`) — KHÔNG dùng `comfy install`/`comfy launch` của comfy-cli để quản lý 1 bản ComfyUI
riêng (tránh cài trùng, lãng phí đĩa/nhầm lẫn 2 instance).

### Chứng minh giá trị — research 1 template thật, đối chiếu với provider `local_flux` đã build

ComfyUI của người dùng đã có sẵn package `comfyui-workflow-templates` (thấy trong
`system_stats` từ trước) — 512 file JSON template chính thức nằm ngay trên đĩa
(`python_embeded/Lib/site-packages/comfyui_workflow_templates_json/templates/`), đúng
NGUỒN DỮ LIỆU mà `search_templates`/`get_template` của Comfy MCP đọc. Đọc trực tiếp
`flux_dev_full_text_to_image.json` (template chính thức "Text to Image (Flux.1 Dev)") và
`flux_schnell_full_text_to_image.json` (bản trước tôi dùng làm nguồn tham khảo gốc lúc
build `image_comfy_flux.py`, mục 120) để đối chiếu với graph đã hand-build.

**Phát hiện 1 (xác nhận đúng)**: cả 2 template đều xác nhận `ComfyUI/models/diffusion_
models/` là thư mục đúng cho UNet Flux — khớp bug đã tự sửa ở mục 121 (không phải
`models/unet_gguf/`).

**Phát hiện 2 (bug thật, đã sửa)**: cả 2 template dùng node `EmptySD3LatentImage` (16
channel — `comfy_extras/nodes_sd3.py::EmptySD3LatentImage.execute` —
`torch.zeros([batch,16,h,w])`), TÔI đã dùng nhầm `EmptyLatentImage` (core, CHỈ 4 channel —
`nodes.py::EmptyLatentImage.generate` — `torch.zeros([batch,4,h,w])`) — sai kiến trúc thật
(Flux dùng VAE 16-channel như SD3, không phải 4-channel như SDXL/SD1.5). Điều tra thêm lý
do KHÔNG lỗi visible ở 4 lần verify GPU trước đó (mục 121/123): ComfyUI có cơ chế tự sửa
`comfy/sample.py::fix_empty_latent_channels` (gọi bên trong `KSampler`, `nodes.py` dòng
~1570) — phát hiện latent sai channel_count thì REPEAT lên đủ 16 kênh; với latent RỖNG
(txt2img thuần, toàn số 0) repeat 4→16 kênh cho kết quả TOÁN HỌC GIỐNG HỆT dựng thẳng 16
kênh (0 lặp lại vẫn là 0) — nên ảnh ra ĐÚNG dù node sai, không có dấu hiệu lỗi nào để phát
hiện qua test hình ảnh. Đã đổi sang `EmptySD3LatentImage` — không đổi hành vi HIỆN TẠI
(vẫn đúng như trước, verify lại qua GPU thật xác nhận ảnh vẫn đúng) nhưng loại bỏ phụ thuộc
ngầm vào cơ chế tự sửa — quan trọng hơn nếu sau này mở rộng provider sang img2img (latent
khởi tạo KHÔNG toàn số 0, lúc đó repeat 4→16 sẽ KHÔNG còn tương đương, sai thật).

**Phát hiện 3 (ghi nhận, KHÔNG đổi)**: 2 template chính thức không dùng `ModelSamplingFlux`
(node tôi vẫn giữ) — vì cả 2 mặc định 1024x1024 (resolution mà shift công thức ít ảnh
hưởng). Giữ nguyên `ModelSamplingFlux` trong `local_flux` vì provider này giờ sinh ĐÚNG
1344x768/768x1344 (mục 123, không còn vuông cố định) — độ lệch resolution so với 1024
mặc định khiến node này CÓ ý nghĩa hơn, không phải thừa.

**Phát hiện 4 (ghi nhận, không áp dụng đợt này)**: node `CLIPTextEncodeFlux`
(`comfy_extras/nodes_flux.py`, core) gộp `CLIPTextEncode`+`FluxGuidance` thành 1 node
(nhận riêng `clip_l`/`t5xxl` text + `guidance` built-in) — đơn giản hoá graph, nhưng KHÔNG
đổi vì graph 3-node hiện tại (CLIPTextEncode+FluxGuidance+ConditioningZeroOut) đã verify
kỹ, đổi thuần vì gọn hơn không đáng công re-verify.

### Test

1 test mới `test_generate_uses_empty_sd3_latent_image_not_4_channel_variant`
(`test_image_comfy_flux.py`) khoá lại class_type đúng. Verify THẬT qua GPU (1 ảnh 16:9
sau khi sửa) — ảnh hợp lệ, đúng nội dung, không lỗi. Full `pytest` chạy lại xác nhận không
regression.

Backend có thay đổi — **cần khởi động lại app**. `.mcp.json` mới — **cần khởi động lại
Claude Code** để phiên sau nhận được tool Comfy MCP.

## 126. Điều tra lỗi timeout shot B03 (tràn VRAM) + thử nghiệm giữ đồng nhất nhân vật giữa các shot (2026-09-09)

### Phần A — Điều tra lỗi "ComfyUI không trả kết quả trong 300s" ở shot B03

Người dùng báo lỗi timeout thật khi sinh shot B03 (kênh Warum Mensch). Điều tra qua log
ComfyUI + `nvidia-smi` xác nhận: **không phải bug code** — GPU thật sự đang tính toán (100%
sử dụng) nhưng cực chậm (~140 giây/bước thay vì ~4.4 giây/bước bình thường, tức chậm hơn
30 lần) do VRAM gần cạn (337MB trống / 16.3GB) khiến ComfyUI phải tràn 1 phần model ra CPU
RAM ("loaded partially" thay vì "loaded completely" trong log) — với tốc độ đó, 1 job cần
~47 phút, vượt xa 300s timeout của provider.

Theo yêu cầu người dùng, gọi `POST /interrupt` trên ComfyUI để huỷ job treo — xác nhận
`GenerationInterrupted`/`raise_if_interrupted` (đã build từ trước, xem mục liên quan
`image_comfy_flux.py`) hoạt động đúng: `visual_status` chuyển "error" với thông điệp rõ
ràng "đã bị dừng", không phải lỗi kỹ thuật khó hiểu.

Điều tra thêm dấu hiệu GPU "cao" sau đó (Task Manager báo Dedicated GPU Memory > 14GB) —
xác nhận đây là hành vi BÌNH THƯỜNG của ComfyUI (giữ model ~12.2GB trong VRAM sau khi sinh
xong để lần sau khỏi tải lại từ đĩa, không phải rò rỉ) — người dùng chọn giữ nguyên cache
thay vì giải phóng ngay (`/free`).

### Phần B — Thử nghiệm giữ đồng nhất nhân vật giữa các shot

Người dùng nêu vấn đề thật: nhân vật đổi khác giữa các cảnh (mỗi shot sinh độc lập, không
có cơ chế "nhớ" thiết kế nhân vật trước đó). Thử 2 hướng:

**1. Flux Redux (core ComfyUI, không cần custom node)** — tải 2 file cần thiết
(`flux1-redux-dev.safetensors` 129MB → `models/style_models/`,
`sigclip_vision_patch14_384.safetensors` 856MB → `models/clip_vision/`, cả 2 công khai
trên HuggingFace `Comfy-Org`). Test 4 mức `StyleModelApply.strength` (0.15/0.3/0.5/1.0)
với cùng ảnh tham chiếu + prompt hành động khác (ngồi bàn viết sổ). Kết quả: **không dùng
được cho nhu cầu này** — strength 0.15/0.3 (mode "multiply") ra ảnh TRẮNG TRƠN (lỗi, không
phải suy giảm mượt như kỳ vọng); strength 0.5/1.0 giữ đúng phong cách nhân vật (tóc xoăn,
đầu tròn) nhưng ĐÈ LUÔN cả bố cục — bỏ qua hoàn toàn yêu cầu "ngồi bàn viết sổ", gần như
sao chép nguyên tư thế đứng vẫy tay của ảnh gốc. Kết luận: Redux vốn là công cụ "biến thể
của 1 ảnh" (giữ cả tư thế lẫn phong cách), không tách được "danh tính" khỏi "hành động" —
không phù hợp khi mỗi shot cần 1 hành động khác nhau nhưng cùng nhân vật.

**2. PuLID-Flux (custom node `balazik/ComfyUI-PuLID-Flux`, hỗ trợ Flux.1-dev + GGUF)** —
research xác nhận đúng model hỗ trợ, nhưng phát hiện BLOCKER trước khi cài (khác IPAdapter
— lần này phát hiện TRƯỚC khi lỡ cài): dependency `insightface` **KHÔNG có bản wheel dựng
sẵn cho Windows trên PyPI** (chỉ có source, cần trình biên dịch C++ MSVC) — xác nhận máy
người dùng CHƯA cài MSVC Build Tools. Trình bày rủi ro rõ ràng cho người dùng qua
`AskUserQuestion`, người dùng chọn **bỏ hướng này** thay vì cài thêm Build Tools (đúng tinh
thần thận trọng đã rút ra từ vụ IPAdapter — không cài thứ chưa chắc chạy được).

**3. Neo mô tả ngoại hình nhân vật vào `visual_style_prompt` (giải pháp cuối, THÀNH
CÔNG)** — không cần cơ chế/model mới, chỉ mô tả cụ thể ngoại hình nhân vật bằng chữ (đầu
tròn to, tóc xoăn thưa, mắt chấm tối giản, cười nhẹ, tay chân que thẳng) thêm vào đầu
`visual_style_prompt` của kênh Warum Mensch (cơ chế CÓ SẴN, tự nối vào MỌI prompt sinh ảnh
— xem `_build_visual_prompt`). **Verify THẬT qua GPU**: sinh 2 ảnh với 2 hành động HOÀN
TOÀN khác nhau (ngồi bàn viết sổ vs chạy ngoài trời dưới nắng, cùng seed=5555, qua đúng
pipeline `_build_visual_prompt`/`_lora_trigger_words`/`_local_flux_kwargs` thật) — CẢ 2 ảnh
đều giữ đúng thiết kế nhân vật (đầu tròn, tóc xoăn thưa, mắt chấm, cười nhẹ) ĐỒNG THỜI theo
đúng hành động riêng của từng prompt — đúng điều Redux không làm được. Đã áp dụng qua PUT
BrandProfile (version 28).

### Kết luận chung

Cách "mô tả chi tiết bằng chữ" tuy đơn giản nhưng cho kết quả tốt nhất trong 3 hướng thử —
không rủi ro cài đặt, không cần model/custom node mới, verify thật cho kết quả rõ ràng.
Không đổi code nào ở đợt này — chỉ đổi cấu hình `visual_style_prompt` qua API (không cần
khởi động lại app). Ghi nhận thêm 2 file model Redux đã tải (`style_models/
flux1-redux-dev.safetensors`, `clip_vision/sigclip_vision_patch14_384.safetensors`) —
giữ lại trên đĩa dù không dùng cho ca này (nhẹ, có thể hữu ích sau cho nhu cầu khác như
khoá màu sắc/phong cách nền không phụ thuộc tư thế nhân vật).

## 127. Tự động hoá "mô tả nhân vật tham khảo" ở Visual Studio — upload ảnh, tự sinh mô tả, tự nối vào prompt (2026-09-09)

Theo yêu cầu người dùng, tiếp nối mục 126: "Tôi muốn triển khai tính năng cho phép upload
ảnh nhân vật tham khảo ở màn Visual studio. Sau khi upload lên sẽ tự động sinh tag mô tả
về ảnh đó. Mô tả này sẽ được dùng để đưa vào prompt tương tự như cách bạn đã làm để giữ
nhân vật." — tự động hoá giải pháp "mô tả bằng chữ" đã verify hiệu quả thật ở mục 126
(lúc đó phải gõ tay vào `visual_style_prompt`).

### Thiết kế

Theo ĐÚNG 2 pattern có sẵn trong codebase (research qua Explore agent trước khi code, để
khớp kiến trúc thay vì tự nghĩ cách mới):

**1. `CharacterReferenceStatus`** (`app/render/schemas.py`, model mới) — theo mẫu
`IntroAssetStatus`/`BgMusicOverride`/`OverlayEffectOverride` (asset RIÊNG của project, sống
trong `RenderState`/`render.json`): `image_path`, `description` (mô tả tự sinh, nối vào
prompt), `caption_error` (lỗi sinh tự động, KHÔNG chặn upload). KHÁC 3 override kia ở 1
điểm: KHÔNG có field tương ứng ở BrandProfile — nhân vật tham khảo đặc thù từng project/
video cụ thể, không có khái niệm "mặc định chung cả kênh" hợp lý.

**2. Auto-caption qua `VisionProvider`** (`app/providers/base.py`, `get_vision()` factory)
— CÙNG cơ chế Channel Asset Vault dùng để caption clip (`app/asset_vault/ingest.py::
caption_clip`), viết prompt RIÊNG cho vision model tập trung vào ĐẶC ĐIỂM THIẾT KẾ nhân
vật (hình dạng đầu/thân, tóc, mặt/mắt, màu sắc, trang phục, phong cách vẽ) — CHỦ ĐỘNG dặn
KHÔNG mô tả tư thế/hành động/bối cảnh (vì mô tả này sẽ tái dùng cho NHIỀU cảnh khác nhau).
Độ dài ~30-50 từ (khớp độ dài mô tả thủ công đã verify hiệu quả ở mục 126).

Caption chạy **đồng bộ** ngay trong request upload (không cần status/polling — 1 ảnh, độ
trễ tương đương caption 1 keyframe clip ở Asset Vault) — đơn giản hơn cơ chế backgrounded
của Asset Vault (phù hợp vì đó là batch nhiều clip, đây chỉ 1 ảnh/lần).

### Backend

5 endpoint mới trong `app/routers/render.py` (cùng file/pattern intro):
- `POST .../character-reference/upload` — multipart, lưu ảnh + gọi
  `_caption_character_reference()` đồng bộ.
- `POST .../character-reference/recaption` — sinh lại mô tả từ ảnh ĐÃ CÓ, không upload lại
  (dùng khi lần trước lỗi hoặc đổi provider vision).
- `PATCH .../character-reference/description` — sửa tay (VisionProvider không phải lúc
  nào cũng mô tả đúng ý).
- `DELETE .../character-reference` — bỏ hẳn, xoá file.
- `GET .../character-reference/asset` — phục vụ preview (Range).

`_caption_character_reference()` bọc lỗi provider (`NoProviderConfiguredError` + lỗi
runtime khác) vào `caption_error` — KHÔNG raise ra ngoài, ảnh vẫn lưu được dù chưa cấu hình
Vision provider (người dùng tự gõ tay `description` qua PATCH, hoặc cấu hình provider rồi
bấm "Sinh lại mô tả").

`app/render/engine.py::_build_visual_prompt` thêm tham số `character_reference_desc` — nối
NGAY SAU `visual_fx` (nội dung cảnh), TRƯỚC `cultural_lock_positive`/`lora_trigger_words`
(gần "content" hơn "style", khác `visual_style_prompt` luôn đứng cuối). Dispatch trong
`generate_visual_asset`: đọc `state.character_reference.description`, CHỈ áp dụng cho ẢNH
(`is_video=False` — video/`local_wan` ngoài phạm vi đợt này, xem docstring đầy đủ lý do).

### Frontend

`CharacterReferenceCard` mới (`VisualStudio.tsx`, đặt ngay dưới `IntroShotCard`) — đơn
giản hơn `IntroShotCard` nhiều (không có brand-inheritance logic): preview ảnh, ô mô tả
(bấm vào để sửa tay — `textarea` ẩn/hiện), nút Upload/Thay ảnh, "Sinh lại mô tả", "Bỏ ảnh
tham khảo". Hiện rõ `caption_error` nếu có.

### Test

12 test mới `test_character_reference.py` (upload có/không Vision provider cấu hình sẵn,
từ chối file không phải ảnh/rỗng, thay ảnh, recaption không cần upload lại, sửa tay mô tả,
xoá, phục vụ asset, các trường hợp 404) — mock HTTP Vision provider qua `respx` cùng
convention `test_asset_vault.py`. 2 test mới cho `_build_visual_prompt` với
`character_reference_desc` (`test_render.py`). Full `pytest` **692 passed**. `tsc --noEmit`
sạch.

Backend + frontend đều có thay đổi — **cần khởi động lại app**. Chưa verify thật qua GPU +
Vision provider thật của người dùng (test chỉ mock HTTP) — khuyến nghị thử ngay ở Visual
Studio sau khi khởi động lại: upload 1 ảnh nhân vật, xem mô tả tự sinh ra có hợp lý không
(cần đã cấu hình 1 Vision provider ở Cài đặt → Provider AI, VD Ollama Vision/Gemini Vision
— nếu chưa cấu hình, `caption_error` sẽ hiện rõ lý do thay vì âm thầm rỗng).

## 128. So sánh chất lượng thật Q8_0 vs Q6_K, đổi mặc định `local_flux` sang Q6_K (2026-09-10)

Tiếp nối mục 123/126 (bug thật tràn VRAM ở shot B03) — người dùng hỏi đổi bản GGUF nhẹ hơn
có ảnh hưởng chất lượng không, tôi giải thích chung theo tài liệu rồi đề xuất verify thật.

### Verify thật qua GPU

Tải `flux1-dev-Q6_K.gguf` (9.86GB, công khai trên HuggingFace `city96/FLUX.1-dev-gguf`,
cùng nguồn Q8_0 đã dùng ở mục 121). Sinh 2 ảnh **cùng seed/prompt/2 LoRA** (chỉ đổi
`model_name`), đợi ComfyUI rảnh (không tranh chấp GPU với job người dùng đang chạy) trước
khi test:
- Q8_0: 96.3s, PNG hợp lệ.
- Q6_K: 130.4s (CHẬM HƠN Q8_0 dù file nhẹ hơn ~3GB — có thể do cách nén Q6_K nhiều block
  mixed-precision hơn, tốn thêm bước tính toán giải nén, bù lại phần tiết kiệm băng thông
  bộ nhớ), PNG hợp lệ.

So sánh trực tiếp 2 ảnh: bố cục/nhân vật/màu sắc gần như giống hệt, khó phân biệt bằng mắt
thường — khớp mô tả "near-lossless" trong tài liệu.

**Kết luận thực tế** (khác giả định ban đầu "nhẹ hơn = nhanh hơn"): Q6_K KHÔNG nhanh hơn
Q8_0 — lợi ích DUY NHẤT là tiết kiệm ~3GB VRAM. Người dùng chọn đặt Q6_K làm mặc định (đổi
đánh đổi: chấp nhận có thể chậm hơn 1 chút, đổi lấy giảm rủi ro tràn VRAM như vụ B03).

### Đã đổi

- Provider `local_flux` đang cấu hình (DB, qua API `PATCH /providers/{id}`): `model_name`
  → `flux1-dev-Q6_K.gguf`.
- `image_comfy_flux.py::_UNET_GGUF_NAME` (fallback mặc định trong code khi provider mới
  không cấu hình `model_name`) → `"flux1-dev-Q6_K.gguf"` (trước `flux1-dev-Q8_0.gguf`).
- `ProviderSettings.tsx` — hint text + 2 chỗ `emptyLabel` phản ánh đúng mặc định mới.
- **Nhân tiện dọn 1 chỗ lỗi thời phát hiện được**: `display_name` catalog "ComfyUI Flux
  (local GPU, GGUF) — CHƯA verify" — nhãn "CHƯA verify" đã sai từ lâu (đã verify kỹ qua
  GPU thật ở mục 121/123/125-127), gỡ bỏ hậu tố.
- Test cập nhật khớp mặc định mới (`test_image_comfy_flux.py`), `specs/05_ai_providers.md`
  cập nhật đầy đủ.

### Dọn dẹp

Xoá 2 script test tạm (`redux_test.py`/`redux_test2.py`) + 5 ảnh test Redux trong
scratchpad (thí nghiệm mục 126 không đạt kết quả tốt, xác nhận KHÔNG có code Redux nào
từng lọt vào codebase thật — chỉ 2 dòng ghi chú giải thích lý do chọn hướng khác, giữ
nguyên vì là ghi chú lịch sử hữu ích).

### Test

Full `pytest` **692 passed**, `tsc --noEmit` sạch.

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được mặc định mới
(provider đang cấu hình sẵn đã đổi qua API, có hiệu lực ngay không cần khởi động lại; chỉ
mặc định CODE cho provider mới cần khởi động lại mới áp dụng).

> **Ghi chú khôi phục (2026-09-11)** — các mục 129-133 dưới đây bị MẤT khỏi file này giữa
> chừng phiên làm việc (nghi do file bị ghi đè bởi 1 phiên bản cũ hơn đang mở song song,
> VD editor khác/tiến trình khác lưu đè — KHÔNG phải do code bị mất, đã verify lại: toàn
> bộ code/test của 5 mục này vẫn còn nguyên trong codebase). Nội dung dưới đây viết lại từ
> tóm tắt kỹ thuật đã ghi nhận lúc làm, không phải bản gốc nguyên văn 100%.

## 129. Tổng quát hoá "sinh ảnh trước rồi chuyển thành video" (T2I→I2V) sang cả Flux, không chỉ SDXL (2026-09-10)

`_try_generate_wan_anchor_image` (`engine.py`) trước đây hardcode chỉ dùng provider SDXL
local để sinh ảnh "anchor" (ảnh khởi đầu) cho luồng Wan2.2 image-to-video — tổng quát hoá
để tự chọn provider ảnh local ĐẦU TIÊN trong chain khớp SDXL HOẶC Flux
(`_LOCAL_IMAGE_PROVIDER_NAMES`/`_LOCAL_FLUX_PROVIDER_NAMES`), rẽ nhánh đúng kwargs/cách
dựng prompt theo kiến trúc (`is_flux`). Cũng luồn thêm `state: RenderState | None` để áp
`character_reference_desc` (mục 127) vào cả ảnh anchor, không chỉ ảnh shot thường. Verify
thật qua GPU: sinh ảnh anchor bằng Flux (114s) → Wan2.2 image-to-video chạy xong thành
công (xác nhận qua `/history/{job_id}` của ComfyUI sau khi máy tự sleep/resume giữa lúc
poll). Test mới trong `test_render.py` (nhánh Flux, thứ tự ưu tiên chain, truyền đúng
`character_reference_desc`).

## 130. Bulk edit "Chuyển cảnh sang shot kế tiếp" + "Chuyển động camera (ảnh tĩnh)" ở Visual Studio (2026-09-10)

Theo yêu cầu người dùng: chọn nhiều/tất cả block ở Visual Studio, áp 1 giá trị chung cho 2
field `transition_to_next`/`camera_motion` cùng lúc thay vì sửa tay từng shot. Backend:
`PATCH /projects/{id}/visual/shots/bulk` (`pipeline.py`, `ShotBulkPatchBody`) — đọc/ghi
`pack.json` 1 lần, 400 nếu thiếu field/giá trị không hợp lệ/không khớp shot nào. **Bug
route-ordering thật gặp lúc code**: route literal `/shots/bulk` PHẢI đăng ký TRƯỚC route
`/shots/{shot_id}` (FastAPI/Starlette khớp theo THỨ TỰ ĐĂNG KÝ, không theo độ cụ thể) —
đăng ký sai thứ tự làm mọi request bulk bị `{shot_id}` "nuốt" trước, hiểu nhầm "bulk" là 1
shot_id, trả 404. Frontend: `VisualStudio.tsx` thêm checkbox chọn từng shot + "chọn tất
cả" + 2 form mini (dropdown + nút áp dụng) độc lập cho 2 field. 7 test router mới, `tsc
--noEmit` sạch.

## 131. Bug thật: block mới re-import (K1-K8) bị dồn cuối danh sách shot thay vì đúng vị trí xen kẽ — sửa `_ensure_shots` (2026-09-10)

Người dùng báo: re-import script thêm block mã "K*" vào project "01-Warum sich die
Ahnungslosesten am sichersten fühlen" (kênh Tiefer Denken) — Script Studio hiện đủ, Visual
Studio "thiếu" (K1-K8 không có VO nhưng có visual, vẫn cần sinh ảnh).

**Điều tra**: `pack.shots` thực ra có đủ 152 shot (không thật sự thiếu) nhưng 8 shot K1-K8
bị dồn hết xuống CUỐI mảng thay vì đúng vị trí xen kẽ như trong `body` — khiến chúng "biến
mất" khỏi luồng duyệt shot ở Visual Studio, và quan trọng hơn: `assembly.py` duyệt
`pack.shots` ĐÚNG THEO THỨ TỰ MẢNG để dựng timeline video, nên nếu không phát hiện sẽ làm
8 clip K* xuất hiện dồn cục cuối video thay vì đúng vị trí kịch bản.

**Nguyên nhân gốc**: `_ensure_shots` (`pipeline.py`) — bản fix trước (mục 31, dùng
`existing + new_shots`, luôn APPEND shot mới vào cuối) chỉ đúng khi block mới xuất hiện ở
CUỐI `body`; sai khi block mới xen kẽ rải rác (đúng trường hợp thật: K1 ở đầu, K8 gần
cuối). **Sửa**: dựng LẠI mảng shots THEO ĐÚNG THỨ TỰ `body` — dùng lại shot đã có nếu khớp
`block_id` (giữ nguyên dữ liệu đã sinh), tạo mới nếu chưa có; shot cũ không còn khớp block
nào (hiếm — block bị xoá lúc re-import) giữ lại, nối cuối. Đã sửa TRỰC TIẾP dữ liệu thật
của project người dùng qua script (K1 → vị trí 0, K8 → vị trí 135, tổng vẫn 152, không mất
dữ liệu). 5 test đơn vị mới `test_pipeline_flow.py` (tái hiện đúng bug thật: chèn đúng vị
trí khi block mới xen kẽ). Full `pytest` 707 passed.

## 132. Bug thật: cột trạng thái Kho Tài Nguyên kẹt "đang cắt cảnh"/"đang gắn nhãn" dù đã xong thật (2026-09-10)

Người dùng báo: "Video đã cắt cảnh vẫn hiện đang cắt cảnh, đã gán nhãn nhưng vẫn hiện đang
gán nhãn" — cả 2 khu "Raw Library" và "Clip đã cắt" ở Kho Tài Nguyên cùng sai (đều đọc
chung `RawVideo.status`, xem `_clip_out` trong `routers/asset_vault.py`).

### Điều tra

Kiểm tra trực tiếp dữ liệu thật qua API đang chạy: 8 `RawVideo` — 7 video ở
status="detecting" đều có 0 clip con (mới upload, `progress_*` đã dọn sạch) — ĐÚNG là
trạng thái ban đầu, không phải bug; nhưng 1 video (`raw_1789050452744`) kẹt ở
status="tagging" dù **cả 36/36 clip con đã có caption** — xác nhận đây là bug thật, tái
hiện được.

### Nguyên nhân gốc

`auto_detect_scenes`/`caption_all_pending_clips` (`asset_vault/ingest.py`) chỉ ghi
`status` sang bước kế tiếp ở DÒNG CUỐI CÙNG của hàm — mọi việc con (cắt từng clip, caption
từng clip) đã commit DB tăng dần dọc đường. `_run()` wrapper bọc 2 hàm này trong
`BackgroundTasks` (`routers/asset_vault.py`) KHÔNG có try/except quanh lệnh gọi lõi — nếu
backend crash/tự khởi động lại giữa chừng (đã xảy ra nhiều lần khi dev, xem mục 131), task
nền chết lặng lẽ NGAY TRƯỚC dòng cập nhật status cuối cùng, để lại `status` kẹt vĩnh viễn
dù dữ liệu con thực chất đã xong.

### Sửa

Thêm `reconcile_raw_video_status(db, raw_video)` (`asset_vault/ingest.py`) — hàm tự phục
hồi (self-heal), CHỈ ĐỌC dữ liệu clip con có sẵn để SUY LẠI status đúng, không chạy job
nền nào mới:
- `status=="tagging"` mà TẤT CẢ clip con đã có `caption` hoặc `caption_error` → suy đúng
  logic cuối `caption_all_pending_clips` lẽ ra đã chạy ("error" nếu có clip lỗi, else
  "indexed").
- `status=="detecting"` mà ĐÃ có ≥1 clip con VÀ `progress_current`/`progress_total`/
  `progress_label` đều `None` (không có task nào đang chạy dở — task thật luôn có
  progress) → cắt cảnh rõ ràng đã xong (ít nhất 1 phần) nhưng chưa kịp ghi "tagging" → suy
  "tagging".
- Video "detecting" 0 clip (chưa xử lý lần nào) KHÔNG bị đụng tới — chỉ đi TỚI, không bao
  giờ tự đoán lùi hay gán "error" khi thiếu bằng chứng.

Gọi hàm này ở CẢ 2 endpoint đọc `GET /asset-vault/raw` và `GET /asset-vault/clips` (khớp
đúng 2 khu màn hình người dùng báo lỗi) — commit nếu có đổi, trước khi trả response.

### Test

7 test mới `test_asset_vault.py` — heal "tagging"→"indexed" khi đủ caption, heal
"tagging"→"error" khi có clip lỗi, KHÔNG heal "tagging" khi còn clip chưa caption (task
đang chạy thật), heal "detecting"→"tagging" khi đã có clip mà progress đã dọn sạch, KHÔNG
đụng "detecting" 0 clip (case thật của 7 video production), KHÔNG đụng "detecting" khi
progress đang chạy thật (dù đã có vài clip), heal áp dụng đúng qua CẢ endpoint
`/clips`. Full `pytest` **714 passed**.

### Áp dụng cho dữ liệu thật

Backend đang chạy khi sửa xong chưa nạp code mới (không hot-reload) nên gọi API sống chưa
tự sửa ngay được; do lỡ tay gọi `POST .../caption-all` để thử kích hoạt lại (tưởng nhầm là
gọi `GET` để trigger đường tự phục hồi) nên đã VÔ TÌNH kích hoạt 1 lượt gắn nhãn lại thật
sự cho cả 36 clip của `raw_1789050452744` qua Ollama Vision (local, không tốn phí cloud) —
lượt này tự chạy xong sẽ tự đưa status về "indexed" đúng bằng chính logic gốc (không cần
đường tự phục hồi mới can thiệp) khi backend khởi động lại lần tới; code fix áp dụng đầy đủ
cho MỌI video khác gặp tình huống tương tự kể từ lần khởi động lại kế tiếp.

## 133. Bug thật (tiếp mục 132): video raw MỚI upload đã hiện badge "Đang cắt cảnh" dù chưa chạy job nào (2026-09-10)

Người dùng hỏi lại: "Phần video raw mới upload sao lại hiện trạng thái là đang cắt cảnh
luôn nhỉ?" — khác mục 132 (data kẹt sai do crash giữa task), đây là bug THUẦN HIỂN THỊ:
`status="detecting"` mang 2 nghĩa (1) job cắt cảnh THẬT đang chạy (có
`progress_total`/`progress_current`), (2) mới upload/chưa cắt lần nào, đang CHỜ người
dùng tự bấm "Cắt cảnh tự động" (đúng nguyên tắc "mỗi bước tự bấm" của CLAUDE.md — cắt cảnh
KHÔNG tự chạy ngầm). `AssetVault.tsx::StatusBadge` (trước sửa) chỉ đọc `status`, hiện CỨNG
"Đang cắt cảnh" cho cả 2 case — trong khi phần nút hành động NGAY BÊN CẠNH (dòng cũ 591) đã
tự phân biệt đúng qua `progress_total == null` để quyết định hiện nút "Cắt cảnh tự động"
hay không — 2 phần UI cùng 1 hàng nói mâu thuẫn nhau (badge nói "đang chạy", nút nói "bấm
để bắt đầu").

### Sửa

`StatusBadge` nhận thêm `progressTotal` — khi `status=="detecting"` VÀ `progressTotal ==
null` (không có job nào đang chạy dở) → hiện "Chưa cắt cảnh" thay vì "Đang cắt cảnh". Cả 3
nơi gọi `StatusBadge` (dòng video gốc, cột trạng thái ở bảng Clip đã cắt, preview panel)
đều truyền `progress_total` của `RawVideo` tương ứng.

Case `status=="tagging"` có ambiguity TƯƠNG TỰ (đã cắt xong, chờ bấm "Gắn nhãn" vs đang
gắn nhãn thật) nhưng KHÔNG sửa trong mục này — `caption_all_pending_clips` không ghi
`progress_current`/`progress_total` trong lúc chạy (khác bước cắt cảnh), nên không có tín
hiệu sẵn có để phân biệt phía frontend; cần thêm field mới (VD đếm clip đã caption/tổng
clip) mới xử lý đúng — để lại làm sau nếu người dùng xác nhận cần.

### Test

Thay đổi thuần frontend (React component, không đổi API/schema) — `tsc --noEmit` sạch.
Không cần test backend mới (không đụng Python).

## 134. Chọn ngôn ngữ xuất video ở Render Studio + hậu tố ngôn ngữ trong tên file Pack Export (2026-09-11)

Theo yêu cầu người dùng: "phần xuất video, cho phép chọn ngôn ngữ xuất video, mặc định là
ngôn ngữ chính của kênh. Nếu giọng đọc của ngôn ngữ đc chọn chưa sinh hết, hiển thị cho
user biết. Time duration cho từng cảnh ăn theo duration của ngôn ngữ được chọn" — sau đó
làm rõ thêm: "và ko cho render" (chặn cứng thay vì chỉ cảnh báo), rồi tiếp "khi xuất pack
ở bước output, video render được đặt tên kèm hậu tố ngôn ngữ" + "tương tự với tên file
narration_full, cũng thêm hậu tố ngôn ngữ tương ứng".

### Chọn ngôn ngữ xuất video (Render Studio)

Trước đây `assemble_video`/`_assemble_video_impl` (`assembly.py`) LUÔN đọc giọng đọc theo
field PHẲNG trên `ShotRenderStatus` (ngôn ngữ chính của kênh) — không có cách nào ghép
video bằng ngôn ngữ khác dù đã có tính năng giọng đọc đa ngôn ngữ (mục 119).

**Backend**: `_narration_for_lang(status, lang, primary_language)` (helper mới,
`assembly.py`) — tra RAW field giọng đọc theo `lang` chỉ định: ngôn ngữ chính dùng field
phẳng, ngôn ngữ khác tra `status.narration_translations[lang]`. `_shot_base_duration`/
`_narration_floor`/logic chọn audio mux vào segment (Pass 1 + vòng build segment) đều
luồn thêm `lang`/`primary_language`, thay LUÔN cố định ngôn ngữ chính. `assemble_video`
nhận thêm `lang: str | None = None` (mặc định → ngôn ngữ chính). `AssembleBody` (router)
thêm field `lang` — validate 400 nếu không thuộc `NARRATION_LANGUAGES`, VÀ (theo yêu cầu
"ko cho render") 400 CỨNG nếu giọng đọc ngôn ngữ đã chọn CHƯA sinh xong cho MỌI shot
(cùng nguyên tắc gate visual đã có), liệt kê rõ số shot thiếu.

**Bug thật tự phát hiện lúc code**: `_narration_for_lang` bản đầu tự áp điều kiện "ready"
gộp CẢ `narration_status=="ready"` LẪN `bool(asset_path)` cho MỌI nơi gọi — nhưng
`_shot_base_duration`/`_narration_floor` (logic GỐC, trước tính năng này) chỉ cần
`duration_sec` có giá trị, KHÔNG đòi `asset_path`; gộp chung làm 2 test cũ
(`test_shot_base_duration_prefers_real_narration_over_beat_timestamp` dùng status
`ready` nhưng không set `asset_path`) FAIL — sửa: hàm trả RAW field
`(narration_status, asset_path, duration_sec)`, để từng nơi gọi tự áp ĐÚNG điều kiện gốc
của mình (khác nhau giữa "tính duration" và "chọn audio mux vào segment").

**Frontend**: `RenderStudio.tsx` — fetch `BrandProfile` (giống `ScriptStudio.tsx`) lấy
`primary_language` làm mặc định; dropdown "Ngôn ngữ giọng đọc" mới trong card "Cấu hình
xuất video"; `canAssemble` (gate nút "Ghép video") giờ cũng đòi `missingNarrationCount ==
0` — banner cảnh báo hiện số shot thiếu giọng đọc ngôn ngữ đã chọn.

### Hậu tố ngôn ngữ trong tên file Pack Export

`RenderState` thêm `final_video_lang: Optional[str]` — ghi lại NGAY lúc `assembly_status`
chuyển "done" (song song `final_video_path`), lưu ĐÚNG ngôn ngữ đã dùng cho lần ghép đó
(không phải luôn ngôn ngữ chính). `pack_export.py::export_pack_bundle`:
- `video_final_<lang>.*` — hậu tố = `state.final_video_lang` (fallback ngôn ngữ chính nếu
  `None`, tương thích render cũ trước tính năng này).
- `narration_full_<lang>.mp3` và `transcript_<lang>.srt` — **đổi**: trước đây ngôn ngữ
  CHÍNH xuất tên KHÔNG hậu tố (`narration_full.mp3`/`transcript.srt`), ngôn ngữ khác mới
  có hậu tố; giờ NHẤT QUÁN CẢ 3 loại file (video/narration/transcript), ngôn ngữ chính
  cũng có hậu tố — người dùng yêu cầu qua 2 lượt góp ý riêng (`video_final` trước,
  `narration_full`/`transcript` sau).

Lý do: xuất Pack nhiều lần (VD ghép "de" rồi export, sau đó ghép lại "vi" rồi export lần
2) vào CÙNG 1 thư mục đích trước đây sẽ GHI ĐÈ lẫn nhau vì tên file không phân biệt ngôn
ngữ, dễ tưởng nhầm vẫn còn bản cũ.

### Test

- `assembly.py`: test mới cho `_shot_base_duration` đọc translation khi `lang` khác ngôn
  ngữ chính; sửa 7 lời gọi `_reflow_video_durations`/`_shot_base_duration` trong test cũ
  để truyền `lang`/`primary_language`.
- End-to-end thật (ffmpeg thật): `assemble_video(..., lang="en")` ra video dài khớp giọng
  đọc "en" (2s) chứ không phải "vi" (5s, ngôn ngữ chính).
- Router: 400 khi `lang` không hợp lệ; 400 khi giọng đọc ngôn ngữ đã chọn chưa sinh hết
  (chặn cứng); 200 bình thường khi ngôn ngữ chính đã sẵn sàng.
- Pack export: hậu tố `video_final_<lang>`/`narration_full_<lang>`/`transcript_<lang>`
  khớp `lang` THẬT đã ghép (không phải luôn ngôn ngữ chính); fallback đúng ngôn ngữ chính
  khi `final_video_lang` là `None` (mô phỏng render.json cũ); cập nhật các test cũ khớp
  tên file mới.
- `tsc --noEmit` sạch (RenderStudio.tsx). Full `pytest` — xác nhận cùng lượt chạy cuối ở
  mục 135 bên dưới (không có regression từ mục này).

Backend có thay đổi — **cần khởi động lại app** để dùng được (không hot-reload).

## 135. Lưu ảnh/video từ Visual Studio vào Kho Tài Nguyên để tái sử dụng + Tự động điền từ Kho (2026-09-11)

Theo yêu cầu người dùng: "Với các ảnh/video đã tạo ra ở màn visual studio, tôi muốn lưu
vào Kho tài nguyên để tái sử dụng" — kèm 4 ý cụ thể (chọn 1-nhiều block để lưu, dùng field
Visual/FX làm caption, video nguồn = project, kênh = kênh project) và yêu cầu 1 section
RIÊNG trong Kho Tài Nguyên giống "Clip đã cắt". Sau khi lên plan (EnterPlanMode, xác nhận
qua AskUserQuestion: tái dùng `ProcessedClip` để gán lại được ngay vào shot khác — không
chỉ lưu trữ; chỉ dùng Visual/FX làm caption, không tự chạy AI Vision; lưu lại 1 shot đã
lưu → cập nhật đè), người dùng bổ sung thêm 1 tính năng lớn: "Tự động quét lọc ảnh/video
chất lượng tốt (score cao) trong kho tài nguyên... mở ra màn danh sách các shot đang có
kèm ảnh/video gợi ý... bỏ các ảnh match ko phù hợp và accept các ảnh phù hợp còn lại...
Ratio ảnh đc chọn phải khớp với định dạng của video" — xác nhận thêm qua AskUserQuestion:
chỉ quét shot CHƯA có visual, ngưỡng similarity RIÊNG cao hơn (không dùng chung 0.65).

### Thiết kế dữ liệu — tái dùng `ProcessedClip`, không tạo bảng mới

`ProcessedClip.raw_video_id` là FK NOT NULL — không thể lưu clip mà không có 1 `RawVideo`
cha. Thay vì đổi ràng buộc NOT NULL (dự án KHÔNG dùng Alembic, đổi ràng buộc cần "12-step"
rename-recreate table rủi ro hơn hẳn — xem tiền lệ `migration.py::
_migrate_legacy_channel_id`), tạo 1 `RawVideo` "ảo" ĐẠI DIỆN project
(`get_or_create_project_raw_video`, idempotent) — `original_filename`=tên project (khớp
thẳng ý "video nguồn chính là video project"), không có file thật, đánh dấu bằng cột mới
`source_project_id` để loại khỏi "Raw Library" (`list_raw_videos` lọc `IS NULL`).

3 cột mới (nullable, qua `migration.py::_add_missing_columns` — ALTER TABLE ADD COLUMN,
KHÔNG đổi ràng buộc cũ): `RawVideo.source_project_id`, `ProcessedClip.media_kind`
("video"/"image", **DEFAULT 'video' NGAY TRONG ALTER TABLE** để backfill đúng cho MỌI
clip cắt cảnh cũ — không chỉ default Python-level của ORM), `ProcessedClip.source_shot_id`
(nhận diện "shot đã lưu chưa" để cập nhật đè). `ShotRenderStatus` thêm
`saved_to_vault_clip_id` (chiều NGƯỢC `linked_clip_id` — shot đã lưu visual CỦA CHÍNH nó).

### Backend — lưu vào Kho

Module mới `asset_vault/from_visual_studio.py::save_shots_to_vault` — với mỗi shot: bỏ
qua (không chặn cả batch) nếu chưa `visual_status=="ready"` hoặc file mất trên đĩa; shot
ĐÃ từng lưu (`saved_to_vault_clip_id` còn trỏ tới clip tồn tại) → cập nhật đè (copy file
mới, refresh caption/duration/resolution, GIỮ tags/mood_tone/rights_status/usage_count đã
có); ngược lại tạo `ProcessedClip` mới. Endpoint `POST .../visual/shots/save-to-vault`
(`pipeline.py`, đăng ký TRƯỚC route `{shot_id}` — cùng bài học route-ordering mục 130).

### Backend — nới lỏng B-roll cho ẢNH

Kho giờ chứa CẢ ảnh lẫn video — `assign_vault_clip` đổi check từ "chỉ nhận video" (chặn
theo shot) sang tra clip TRƯỚC rồi so `shot.visual_type` với `clip.media_kind` của ĐÚNG
clip; logic copy file phía dưới giữ NGUYÊN 100% (chỉ `shutil.copy2` theo extension gốc,
đã media-kind-agnostic từ trước — verify qua code, không cần sửa). `matching.py` (4 hàm)
+ `get_vault_candidates` thêm filter `media_kind` (tham số optional, mặc định `None` =
không lọc, không đổi hành vi caller cũ). `VaultClipPicker.tsx` bỏ gate
`visual_type==="video"`, đổi nhãn "Video từ Kho"/"Ảnh từ Kho" theo `mediaKind` prop mới.

### Backend — Tự động điền từ Kho tài nguyên

2 endpoint mới: `GET vault-auto-fill-suggestions` quét CÁC SHOT CHƯA có visual sẵn sàng,
gợi ý 1 clip/shot qua `match_semantic` với `_AUTO_FILL_THRESHOLD=0.8` (RIÊNG, cao hơn
0.65 dùng cho gợi ý thủ công — tính năng bulk/tự động này cần match THẬT chắc), lọc thêm
`media_kind` + khung hình ngang/dọc khớp `project.format` (`_resolution_orientation_
matches`, suy từ `resolution="WxH"`, khoan dung khi thiếu dữ liệu — không loại oan). Dedup
CHỒNG 2 lớp: clip đã dùng trong project CỘNG clip vừa chọn cho shot TRƯỚC ĐÓ trong CHÍNH
lượt quét (2 shot không cùng nhận 1 gợi ý). `POST vault-auto-fill-apply` áp dụng ĐÚNG cặp
`(shot_id, clip_id)` client gửi lại (không tự truy vấn lại, tránh lệch dữ liệu) — tái dùng
`_assign_vault_clip_core` (tách từ `assign_vault_clip`, tránh copy-paste), lỗi 1 item
không chặn batch.

### Frontend

`VisualStudio.tsx`: nút bulk "Lưu vào Kho tài nguyên (N)" tái dùng NGUYÊN hạ tầng
bulk-select đã có (mục 130) — chọn 1 shot vẫn dùng được, không cần nút riêng từng shot.
Badge "✓ Đã lưu vào Kho" trên ShotCard. Nút "Tự động điền từ Kho tài nguyên" (menu "⋯ Tuỳ
chọn khác") → quét → modal review MỚI (`VaultAutoFillModal`, checkbox mặc định TICK —
người dùng BỎ tick dòng không phù hợp) → "Áp dụng".

`AssetVault.tsx`: section MỚI "Asset từ Visual Studio" — tái dùng NGUYÊN
`ProcessedClipLibrarySection` (thêm prop `title`/`emptyMessage`, KHÔNG tạo component
trùng lặp ~500 dòng) với `clips.filter(from_visual_studio)`. Nhân tiện sửa 1 chỗ chưa
đúng lộ ra khi thêm field mới: `ClipRow`'s status badge trước đây tra qua prop `rawVideos`
rời (`rawVideos.find(r => r.id === c.raw_video_id)`) — SAI cho clip có raw_video cha là
hàng "ảo" (bị lọc khỏi `GET /asset-vault/raw`), hiện nhầm "video gốc đã xoá". Đổi đọc
THẲNG `clip.raw_video_status` (đã tính sẵn server-side qua `_clip_out`, đúng cho MỌI
trường hợp). `PreviewPanelShell`/`ClipPreviewPanel` thêm nhánh `<img>` cho `media_kind==
"image"` (trước đó LUÔN render `<video>`).

### Test

15 test mới `test_visual_studio_vault.py`: save tạo mới đúng field (media_kind theo
visual_type, caption=visual_fx, raw_video_name=tên project); lưu lại → cập nhật đè, không
tạo dòng mới; shot chưa ready/file mất → skip không chặn batch; RawVideo ảo idempotent +
không lọt vào Raw Library; `assign_vault_clip` nhận ảnh cho shot ảnh, từ chối ảnh cho shot
video; `_clips_for_channel` lọc đúng media_kind; auto-fill chỉ quét shot thiếu visual, lọc
đúng ngưỡng 0.8, apply đúng cặp gửi lên + skip item lỗi không chặn batch; migration
backfill `media_kind="video"` đúng cho clip cũ trên schema mô phỏng THIẾU cột, idempotent
chạy lại lần 2. `tsc --noEmit` sạch. Full `pytest` **735 passed** (gộp cả mục 134).

### Bug thật tự phát hiện lúc chạy full suite: 1 test mới (mục 134) làm treo VÔ THỜI HẠN cả lượt chạy

Full `pytest` sau mục 134 bất ngờ chạy RẤT lâu (bình thường ~107-215s, có lượt phải
huỷ sau 15+ phút không xong) — điều tra bằng cách theo dõi tiến trình `ffmpeg.exe` thật
(CPU 100% liên tục nhưng file output 0 byte sau nhiều phút — xem log tiến trình qua
`wmic`/`Get-Process`), xác nhận KHÔNG phải do "xử lý nhiều cảnh" (đo lại chính lệnh ffmpeg
bị treo chạy ĐỘC LẬP ngoài pytest — xong trong 0.5s với input hợp lệ) mà do
`test_assemble_blocks_when_narration_not_ready_for_selected_lang` (mục 134): lượt gọi
thứ 2 (`resp2`, ngôn ngữ chính, kỳ vọng 200) gọi THẬT `POST .../render/assemble` không
giả lập thiếu ffmpeg — `TestClient` chạy BackgroundTasks ĐỒNG BỘ trong cùng request nên
assembly THẬT chạy ngay, dùng ảnh từ `_mock_asset_apis()` (`FAKE_PNG` — chuỗi byte giả có
magic header PNG nhưng không phải ảnh thật) — đúng bẫy ĐÃ được cảnh báo sẵn trong chính
file test này (docstring `test_assemble_works_without_output_enter`, dòng phía trên: "ảnh
ở đây là bytes ảnh GIẢ... để ffmpeg THẬT xử lý sẽ treo/lỗi không đoán trước được") nhưng
không áp dụng khi viết test mới. Fix: `monkeypatch.setattr(shutil, "which", lambda name:
None)` TRƯỚC lượt gọi thứ 2 — giả lập thiếu ffmpeg giống hệt test phía trên (test chỉ cần
xác nhận router CHẤP NHẬN request, không cần assembly thật sự chạy xong). Verify: test
riêng lẻ từ treo vô thời hạn → 2.27s; full suite từ "không xong sau 15+ phút" → **735
passed trong 213.62s** (đúng khoảng thời gian bình thường).

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

## 136. Nút tải kịch bản dạng .txt (không timestamp) ở Script Studio + Pack Export (2026-09-12)

Theo yêu cầu người dùng: "Thêm nút tải kịch bản dạng .txt không có timestamp ở màn script
studio cho mọi ngôn ngữ. Xuất pack cũng xuất các file này."

### Thiết kế

`pack_export.py::build_script_txt(pack, *, lang=None, primary_language="vi") -> str` —
hàm mới, xây ĐỘNG từ `pack.script.body[].audio`/`audio_by_lang[lang]`, nối các block
CÓ lời thoại bằng 1 dòng trống, KHÔNG timestamp/SRT numbering (khác `build_srt_text` cùng
file). CỐ Ý KHÔNG dùng `Script.full_text` có sẵn — field đó chỉ là snapshot NGÔN NGỮ
CHÍNH tại thời điểm import CSV/Excel ban đầu, không theo kịp khi người dùng sửa tay từng
block hoặc bổ sung bản dịch sau đó (đã verify qua đọc code — nguồn sự thật thật sự là
`body[].audio`/`audio_by_lang`, không phải field cache đó).

**Endpoint mới** (`pipeline.py`, mirror ĐÚNG cặp `transcript-srt`/`transcript-srt/{lang}`
đã có): `GET /projects/{id}/script/transcript-txt` (ngôn ngữ chính, `script.txt`) và
`GET /projects/{id}/script/transcript-txt/{lang}` (400 nếu `lang` không hợp lệ hoặc chưa
có nội dung ngôn ngữ đó).

**Pack Export**: `export_pack_bundle` thêm `script_<lang>.txt` — 1 cho ngôn ngữ chính
(hậu tố NGAY từ đầu, khớp quy ước mục 134/135: video/narration/transcript đều có hậu tố
ngôn ngữ dù là ngôn ngữ chính), và 1 cho MỖI ngôn ngữ khác có ít nhất 1 block đã dịch
(cùng vòng lặp đã có cho `transcript_<lang>.srt`/`narration_full_<lang>.mp3` — không cần
tạo vòng lặp riêng).

### Frontend

`ScriptStudio.tsx` — nút "Tải kịch bản (.txt)" mới, đặt cạnh nút "Tải transcript (.srt)"
đã có, dùng ĐÚNG `viewLang` (tab ngôn ngữ đang chọn) — cùng pattern chọn endpoint theo
`viewLang === primaryLanguage` như nút .srt.

### Test

13 test mới `test_transcript.py`: `build_script_txt` nối block đúng, bỏ qua block rỗng,
đọc đúng `audio_by_lang[lang]`, bỏ qua khi chưa dịch (không giữ chỗ như .srt vì không có
timeline); endpoint 400 khi chưa có script, trả đúng nội dung + `Content-Type: text/plain`
+ filename đúng, 400 khi `lang` không hợp lệ, 400 khi ngôn ngữ chưa có nội dung. Cập nhật
`test_narration_translations.py::test_export_pack_bundle_includes_translated_languages`
(thêm assert `script_en.txt`/`script_de.txt`) + 1 test cũ ở `test_render.py` dùng exact-
match `body["included"]` (thêm `script_vi.txt` đúng vị trí). `tsc --noEmit` sạch.

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

### Bug thật tự phát hiện lúc chạy full suite: ID sinh bằng millisecond timestamp có thể trùng nhau

Full suite thỉnh thoảng lỗi `UNIQUE constraint failed` (khác test bị lỗi mỗi lần chạy —
`test_asset_vault.py` lần 1, `test_short_form_projects.py` lần 2) — điều tra bằng cách
chạy lại KHÔNG qua `tail` (log trước đó bị cắt vì `tail -30` nằm TRONG lệnh chạy nền,
không phải lọc sau khi đọc), xác nhận traceback thật:
`sqlite3.IntegrityError: UNIQUE constraint failed: project.id` — 2 hàng cùng nhận ID
`prj_1789144843494` (trùng CẢ chuỗi số, không phải lệch 1 ký tự). Root cause: `_new_id()`
(và các bản copy giống hệt) chỉ dùng `int(time.time() * 1000)` làm hậu tố — 2 lệnh tạo
trong CÙNG 1 mili giây (test chạy nhanh, hoặc người dùng bấm tạo hàng loạt rất nhanh
ngoài đời) ra TRÙNG ID, không chỉ là vấn đề test flaky.

**Sửa** (10 vị trí dùng pattern này, KHÔNG đụng 3 chỗ sinh SEED ảnh/video ở
`image_comfy_flux.py`/`image_comfy_sdxl.py`/`video_comfy_wan.py` — mục đích khác hẳn,
seed không cần unique): thêm hậu tố `uuid.uuid4().hex[:6]` vào SAU timestamp ở
`asset_vault/ingest.py::_new_id`, `routers/channels.py::_new_id`,
`routers/projects.py::_new_id`, `routers/library.py::_new_id`,
`routers/settings.py` (prompt template id), `routers/render.py` (background_video
filename — vốn đã có `_{len(...)}` làm hậu tố phụ nhưng KHÔNG đủ an toàn cho 2 request
THẬT SỰ song song vì mỗi request tự đọc `len(...)` độc lập; layer_id/imglayer_id — cùng
lý do).

**Test**: 3 test mới (`test_projects_brief.py`, `test_channels.py`, `test_asset_vault.py`)
đóng băng `time.time()` (giả lập collision THẬT chứ không chỉ hy vọng không trùng lúc
chạy), sinh 50 ID liên tiếp, xác nhận không còn cái nào trùng — verify TRỰC TIẾP nguyên
nhân gốc, không chỉ verify triệu chứng qua full suite. Full `pytest` **746 passed** (bao
gồm cả mục 136 + fix này), chạy sạch không có error, không cần `tail` cắt bớt log để xác
nhận.

## 137. Xuất short-video 9:16 từ 1 khoảng block, ở Output Center (2026-09-12)

Theo yêu cầu người dùng: "Bổ sung thêm section ở bước Output để xuất short-video tỷ lệ
9:16. User nhập Mã block đầu và cuối và bấm render để xuất video" — cho phép chọn dùng
ảnh 16:9 đã sinh (letterbox viền đen) hoặc sinh lại ảnh đúng 9:16 (kèm progress bar), Pack
Export phải cover video short này với tên file rõ ràng, tối đa 3 short-video/project,
hiển thị đầy đủ cả 3 để xem lại bất kỳ lúc nào.

### Có tận dụng được "short-form sub-project" không?

Người dùng hỏi trực tiếp trước khi lên kế hoạch — verify bằng đọc code thật
(`routers/projects.py::create_project`): `Project.format=="short"`/`parent_project_id`
là 1 project **RIÊNG HOÀN TOÀN TRỐNG** (script/pack mới tinh), chỉ chia sẻ
`parent_project_id` để nhóm hiển thị trên UI — KHÔNG copy/tham chiếu block nào từ project
cha. Không có cơ chế "cắt 1 khoảng block thành short-video" nào để tái dùng NGUYÊN, nhưng
nhiều primitive tầng dưới của `assembly.py`/`engine.py` (không phụ thuộc intro/bg-music/
overlay/video nền) tái dùng được thẳng: `RESOLUTION_MAP_VERTICAL`, quy ước
`aspect_ratio="9:16"`, `_build_visual_prompt`, `_run_boundaries`/`_concat_fast`/
`_xfade_chain`/`_build_segment`/`resolve_video_codec`/`CRF_TABLE`/`_shot_base_duration`/
`_reflow_video_durations`/`_narration_for_lang`.

### Phạm vi đã chốt (hỏi trực tiếp người dùng qua AskUserQuestion)

- Short-video CHỈ gồm THUẦN shot trong khoảng đã chọn (ảnh/video + giọng đọc ngôn ngữ
  chính của kênh, giữ transition đã cấu hình) — KHÔNG kèm intro/nhạc nền/overlay thương
  hiệu như video chính (tránh tái dùng gần hết `_assemble_video_impl`).
- Shot dạng VIDEO trong khoảng LUÔN giữ nguyên bản gốc 16:9 + letterbox — KHÔNG BAO GIỜ
  sinh lại thành video 9:16 dù bật "Sinh lại ảnh" (sinh lại video tốn kém/chậm hơn hẳn
  ảnh, ngoài phạm vi yêu cầu — chỉ ẢNH mới thực sự được sinh lại).
- Đã đủ 3 short-video → chặn cứng (400) khi xuất thêm, yêu cầu xoá bớt 1 cái trước (nút
  Xoá trên UI).

### Thiết kế

**Schema** (`render/schemas.py`) — `ShortVideoExport` (id, start_block_id, end_block_id,
regenerate_images, status: pending/generating_images/assembling/done/error, error,
progress_current/total/label, video_path, created_at) + `RenderState.short_exports:
list[ShortVideoExport]`. `GET /render/status` (poll sẵn có) tự nhiên trả kèm field này —
không cần endpoint GET tiến độ riêng.

**`assembly.py`** — thêm chế độ letterbox thứ 3 cho `_resolve_scale_filter`:
`_scale_letterbox_filter(resolution)` = `scale=...force_original_aspect_ratio=decrease,
pad=...:color=black,setsar=1` (scale vừa khít khung, lấp phần thiếu bằng đen, KHÔNG crop
— khác `_scale_cover_filter`/`_scale_blurfill_filter` đã có). `"letterbox"` KHÔNG phải 1
giá trị thật của `BrandProfile.aspect_fill_mode` (schema đó vẫn chỉ nhận
`Literal["crop","blur"]`, không lộ ra UI Cấu hình kênh) — chỉ tồn tại trong 1 dict `brand`
TẠM THỜI do module mới tự dựng (copy brand thật, ghi đè đúng key này) để tái dùng
`_build_segment` nguyên vẹn.

**Module mới `app/render/short_export.py`** — điều phối luồng NGẮN HƠN
`_assemble_video_impl`, tái dùng primitive có sẵn thay vì viết lại:
- `_resolve_block_range(pack, start, end)` — tìm 2 index trong `pack.script.body`, lọc
  `pack.shots` khớp `block_id` trong khoảng (giữ nguyên thứ tự `shots`, mirror thứ tự
  `body` theo mục 131). Raise `ValueError` (400) nếu block không tồn tại/thứ tự ngược/
  khoảng rỗng.
- `create_short_export` — chặn cap 3 + validate range NGAY (400 tức thì, không đợi
  background task), tạo entry `status="pending"`.
- `run_short_export` (BackgroundTasks) — validate MỌI shot TRONG KHOẢNG đã
  `visual_status=="ready"` (KHÔNG đụng shot ngoài khoảng); nếu `regenerate_images`: với
  từng shot ẢNH (bỏ qua shot VIDEO) gọi `get_image_chain`/`_build_visual_prompt` (ép
  `aspect_ratio="9:16"`), lưu vào `renders/short/{id}/assets/` riêng (KHÔNG đụng
  `visual_asset_path` gốc), cập nhật `progress_current/total/label` sau MỖI ảnh; build
  segment (ảnh sinh lại → brand thật, cover-crop bình thường; ảnh gốc/mọi video → brand
  tạm ép `aspect_fill_mode="letterbox"`), nối bằng `_run_boundaries`/`_concat_fast`/
  `_xfade_chain` y hệt pipeline chính (kể cả đệm lead-in/out giọng đọc ở ranh giới
  transition — tái dùng đúng cơ chế đã sửa cho `assemble_video`, tránh lặp lại bug "nuốt
  chữ" đã từng gặp). Độ phân giải/codec/chất lượng CỐ ĐỊNH (1080p dọc/h264/medium) —
  không thêm UI chọn, giữ đơn giản.

**Router mới** (`routers/render.py`): `POST .../render/short-export` (400 cap/range),
`DELETE .../render/short-export/{id}` (xoá file + entry, giải phóng slot), `GET
.../render/short-export/{id}/download` (`range_file_response`, tên file
`short_<start>-<end>.<ext>`).

**Pack Export** (`pack_export.py::export_pack_bundle`): với mỗi `short_exports` có
`status=="done"`, copy vào bundle tên `short_<start_block_id>-<end_block_id>.<ext>` — chỉ
export ĐÃ xong mới xuất, export lỗi/đang chạy dở bị bỏ qua hoàn toàn (không phải nội dung
"thiếu", chỉ đơn giản chưa yêu cầu xuất).

### Frontend

File mới `ShortVideoExportCard.tsx` (render trong `OutputCenter.tsx`, ngay sau
`<RenderStudio>`): 2 ô nhập mã block đầu/cuối + checkbox "Sinh lại ảnh theo tỷ lệ 9:16" +
nút "Xuất short video (N/3)" (disabled khi N==3); poll `render/status` riêng, chỉ bật
vòng poll khi có export đang chạy dở (cùng pattern `RenderStudio.tsx`); danh sách đầy đủ
tối đa 3 short-video: `<video>` preview DỌC (tái dùng style `maxHeight:"70vh"` đã dùng
cho `project.format==="short"`), nhãn khoảng block, nút Tải về + Xoá; progress bar khi
`generating_images`/`assembling`. `api/types.ts` thêm `ShortVideoExport`/
`RenderState.short_exports`; `api/client.ts` thêm `createShortExport`/
`deleteShortExport`/`shortExportDownloadUrl`/`downloadShortExport`.

### Test

17 test mới `test_short_video_export.py`, chia 2 nhóm: (1) validate/cap/router — KHÔNG
cần ffmpeg thật (`_resolve_block_range` đúng/lỗi từng trường hợp, cap 3 chặn ở tầng module
LẪN router, xoá giải phóng slot + xoá đúng file, 404 khi xoá id không tồn tại, download
400 khi chưa xong); (2) pipeline ghép THẬT (`@pytest.mark.skipif` thiếu ffmpeg) — chỉ
validate đúng khoảng đã chọn (shot ngoài khoảng chưa ready không chặn), letterbox verify
bằng ffprobe THẬT (đo màu pixel viền trên phải gần đen, giữa khung phải đúng màu nội dung
gốc — không suy đoán), shot VIDEO không bao giờ bị sinh lại dù bật `regenerate_images`
(monkeypatch `get_image_chain` raise nếu bị gọi), ảnh sinh lại lưu ĐÚNG thư mục riêng
KHÔNG đụng asset gốc + đúng `aspect_ratio="9:16"` truyền cho provider, Pack Export xuất
đúng tên `short_<start>-<end>.<ext>`.

**Bẫy phát hiện lúc viết test (đã biết trước từ bug mục ffmpeg-hang cùng session, vẫn
suýt mắc lại)**: `client.post(...)` (Starlette TestClient) chạy `BackgroundTasks` NGAY
TRONG request — gọi tay `run_short_export(...)` THÊM 1 lần sau đó làm pipeline chạy 2 LẦN
(bắt được qua test đếm số lần gọi provider ảnh ra 2 thay vì 1). Sửa: bỏ hẳn lời gọi tay dư
thừa ở mọi test dùng `client.post`; đọc kết quả cuối cùng LUÔN từ `render.json` trên đĩa
(không phải từ JSON response của chính `client.post`, vì response được dựng TRƯỚC khi
`BackgroundTasks` chạy xong nên vẫn còn "pending").

`tsc --noEmit` sạch. Full `pytest` **763 passed** (746 cũ + 17 mới), không regressions.

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

## 138. Bug thật (tiếp mục 137): ảnh/video gốc 16:9 bị "co hẹp" ở short-video — đổi letterbox sang crop (2026-09-12)

Người dùng test thật báo: "ảnh gốc 16:9 đang bị co hẹp ở video short. Yêu cầu ko co ảnh
khi render, chỉ crop phần giữa để cắt về đúng tỷ lệ 9:16" — rồi xác nhận thêm áp dụng
CẢ shot dạng video ("làm tương tự với visual là loại video"). Bản mục 137 dùng letterbox
(scale-to-fit + viền đen) đúng như yêu cầu BAN ĐẦU ("ảnh ngang gốc của shot cần được hiển
thị full trong video, bên dưới và trên sẽ có khoảng đen") — nhưng test thật cho thấy
"hiện full" bị hiểu/nhìn thành "ảnh bị thu nhỏ lại" (thumbnail bé giữa 2 viền đen), không
đúng ý đồ thật của người dùng. Đổi hẳn sang crop-fill: phóng khung ngang lên vừa CHIỀU
CAO khung dọc rồi cắt bớt 2 bên — không co nhỏ nội dung, mất chi tiết rìa 2 bên thay vì
mất chi tiết trên/dưới.

### Sửa

`render/short_export.py` — nhánh dùng asset GỐC (ảnh không sinh lại, HOẶC mọi shot
video) đổi từ `{**brand, "aspect_fill_mode": "letterbox"}` sang `{**brand,
"aspect_fill_mode": "crop"}` — ép CỐ ĐỊNH "crop" (không đọc `brand.aspect_fill_mode` thật
của kênh), giữ hành vi short-video độc lập với tuỳ chọn crop/blur của video chính, luôn
nhất quán 1 kiểu. Ảnh ĐÃ sinh lại đúng 9:16 (`regenerate_images=True`) không đổi gì (đã
dùng brand thật, cover-crop không có tác dụng phụ vì ảnh đã đúng tỷ lệ).

`assembly.py` — `"letterbox"` KHÔNG còn nơi nào gọi tới nữa (chỉ mới được dựng riêng cho
tính năng này ở mục 137) — xoá hẳn `_scale_letterbox_filter` + nhánh `"letterbox"` khỏi
`_resolve_scale_filter`, không để lại code chết. `_resolve_scale_filter` quay về ĐÚNG 2
chế độ gốc (`"crop"`/`"blur"`, theo `BrandProfile.aspect_fill_mode` thật) như trước khi
có mục 137.

Docstring `ShortVideoExport` (schemas.py) + copy UI (`ShortVideoExportCard.tsx`) cập nhật
theo — không còn nhắc "viền đen"/letterbox.

### Test

Thay `test_run_short_export_letterboxes_original_16_9_asset_without_cropping` bằng
`test_run_short_export_crops_original_16_9_image_without_shrinking` — đảo ngược assertion:
dải TRÊN CÙNG khung hình giờ phải VẪN LÀ màu nội dung thật (đỏ), KHÔNG được gần đen (bug
letterbox cũ sẽ làm test này FAIL đúng ở dải trên). Thêm
`test_run_short_export_crops_original_16_9_video_without_shrinking` — cùng assertion
nhưng cho shot VIDEO (theo yêu cầu áp dụng cả video), verify bằng ffprobe/ffmpeg THẬT
(không suy đoán). Full `pytest` **764 passed** (763 mục 137 + 1 test video mới ở đây).

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

## 139. Bug thật (tiếp mục 138): fix crop-fill mục 138 vô tác dụng với shot có Camera Motion (Ken Burns) — root cause thật ở `camera_motion.py` (2026-09-12)

Người dùng test THẬT trên 1 project thật (dự án "01-Warum sich die Ahnungslosesten am
sichersten fühlen") báo: "test thử tạo short video... nhưng ảnh vẫn bị co lại theo chiều
dọc như cũ" — tức fix mục 138 (ép `aspect_fill_mode="crop"`) KHÔNG có tác dụng trên
project thật, dù mọi test mục 138 đều pass. Điều tra trực tiếp trên `pack.json` thật của
project này: **151/151 shot đều có `camera_motion` khác `"none"`** (147 `zoom_in`, còn
lại `pan_left`/`pan_right`/`zoom_out`) — 0 shot nào dùng `camera_motion="none"`. Đây
chính là lý do bug mục 138 "sửa nhưng không hết": test mục 138 dùng ảnh test THUẦN, không
gán `camera_motion`, nên chưa bao giờ đi qua đúng nhánh code path người dùng THẬT SỰ dùng.

### Root cause thật

`assembly.py::_build_segment` có **2 nhánh scale HOÀN TOÀN TÁCH BIỆT** cho shot ẢNH:
- `camera_motion=="none"` → `_resolve_scale_filter(resolution, brand)` — nhánh mục 138 đã
  sửa, tôn trọng `aspect_fill_mode`.
- `camera_motion!="none"` (Ken Burns) → `build_camera_motion_filter(...)` —
  **HOÀN TOÀN KHÔNG gọi `_resolve_scale_filter`**, tự dựng filter chain riêng
  (`camera_motion.py`). Override `aspect_fill_mode="crop"` ở `short_export.py` (mục 137/
  138) đi vào 1 dict `brand` chỉ `_resolve_scale_filter` đọc — nhánh Ken Burns không bao
  giờ nhìn thấy dict đó, nên vô tác dụng với BẤT KỲ shot nào bật camera motion (tức GẦN
  NHƯ MỌI shot thực tế — Ken Burns là lựa chọn phổ biến, xác nhận đúng 151/151 shot của
  project test thật).

`build_camera_motion_filter` cũ đưa THẲNG ảnh gốc (chỉ upscale 2x, không điều chỉnh tỷ lệ
khung) vào `zoompan` rồi ép cứng `s={out_w}x{out_h}` ở cuối. `zoompan`'s `s=` chỉ ép KÍCH
THƯỚC output cuối cùng, **không hề giữ tỷ lệ khung hình** — ảnh 16:9 đưa vào rồi ép
`s=1080x1920` (9:16) bị **BÓP MÉO** (chiều rộng co mạnh, chiều cao giãn mạnh) — đây chính
là hiện tượng người dùng mô tả "ảnh bị co lại theo chiều dọc" (nội dung gốc bị nén/kéo méo
tỷ lệ, không phải letterbox/crop bình thường).

### Sửa

`camera_motion.py::_cover_crop_to_target(out_w, out_h)` — hàm mới, cùng công thức
cover-crop `_scale_cover_filter` (`scale=...force_original_aspect_ratio=increase,
crop=out_w:out_h`) — ép ảnh nguồn về ĐÚNG tỷ lệ khung xuất TRƯỚC KHI vào `_UPSCALE`/
`zoompan`/`rotate`. Chèn `cover_crop` vào ĐẦU chuỗi filter ở **CẢ 4 nhánh** motion
(`zoom_in`/`zoom_out`, `pan_*`/`tilt_*`, `roll`, `orbit`) — theo yêu cầu người dùng xác
nhận thêm ("làm tương tự với visual là loại video" — áp dụng nhất quán, không riêng ảnh
tĩnh mà cả video vốn đã tự crop qua `_resolve_scale_filter`, phần này chỉ củng cố phía
camera-motion). Nhờ cover-crop trước, khung `zoompan` animate bên trong LUÔN cùng tỷ lệ
khung xuất — `s={out_w}x{out_h}` ở cuối chỉ còn là scale ĐỒNG NHẤT, không còn bóp méo.
Vô hại/gần no-op khi ảnh nguồn đã đúng tỷ lệ khung xuất (case phổ biến nhất — ảnh
long-form 16:9 ghép vào video 16:9), CHỈ thật sự cắt bớt khi tỷ lệ lệch nhau (đúng bug
này) — tiện thể sửa luôn 1 bug latent nhỏ khác: ảnh AI trả về kích thước lệch nhẹ khỏi
16:9 chuẩn (VD 1792x1024, không hiếm gặp với 1 số API) trước đây cũng bị zoompan bóp méo
nhẹ dù không ai để ý, giờ cover-crop luôn về đúng tỷ lệ.

### Test

`test_camera_motion_crops_to_target_aspect_instead_of_distorting` (`test_render.py`) —
dùng `_corner_test_image` (640x480, 4 ô màu góc) ghép vào khung DỌC hẹp `1080:1920`
(đúng độ phân giải short-export thật) với `camera_motion="zoom_in"`, verify rìa trái/phải
khung xuất phải là NỀN TRẮNG (đã cover-crop cắt mất 2 ô góc màu) — **verify NGƯỢC bằng
cách tạm revert fix, xác nhận test THẬT SỰ fail** (đo được pixel `(255,0,0)` — đúng màu ô
góc đỏ rò rỉ qua bóp méo) trước khi khôi phục lại fix, không chỉ tin test pass suông. Full
`pytest` **765 passed** (764 mục 138 + 1 test mới ở đây).

Backend đổi (frontend không đổi gì thêm ở mục này) — **cần khởi động lại app** để dùng
được.

## 140. Chọn ngôn ngữ giọng đọc khi xuất short-video, giống render long-video (2026-09-12)

Theo yêu cầu người dùng: "cho phép chọn ngôn ngữ khi xuất short-video, tương tự như khi
render long-video" — tính năng short-video (mục 137-139) trước đó LUÔN dùng ngôn ngữ
CHÍNH của kênh, không có lựa chọn nào, khác hẳn `assemble` chính đã có từ mục 134
(`AssembleBody.lang` + gate cứng nếu giọng đọc ngôn ngữ chọn chưa sinh xong).

### Thiết kế

`render/schemas.py::ShortVideoExport` thêm `lang: Optional[str] = None` — LUÔN đã
RESOLVE (không bao giờ `None` với export MỚI) — `run_short_export` đọc thẳng
`export.lang`, không tính lại. `None` chỉ còn gặp ở export CŨ tạo trước tính năng này
(field mặc định) — mọi nơi đọc lại đều fallback `export.lang or primary_language`.

`render/short_export.py::create_short_export` thêm tham số `lang: str | None = None` —
validate + gate NGAY tại đây (400 tức thì ở router, không đợi background task), theo
ĐÚNG thứ tự: cap 3 → khoảng block → `lang` hợp lệ (phải thuộc `NARRATION_LANGUAGES`) →
giọng đọc ngôn ngữ đã chọn phải `"ready"` cho MỌI shot **TRONG KHOẢNG ĐÃ CHỌN** (không
phải toàn project — khác biệt CÓ CHỦ Ý so với `assemble` chính, vì short-video vốn chỉ
dùng 1 phần nhỏ script). `run_short_export` thay MỌI lời gọi `_shot_base_duration`/
`_reflow_video_durations`/`_narration_for_lang` dùng `primary_language, primary_language`
(hardcode ngôn ngữ chính) sang `export_lang, primary_language` — đúng ngôn ngữ đã chọn
quyết định giọng đọc mux vào segment VÀ thời lượng từng shot (khớp cách `assemble_video`
chính đã làm từ mục 134).

`routers/render.py::ShortExportCreateBody` thêm field `lang: str | None = None`, truyền
thẳng vào `create_short_export(..., lang=body.lang)` — router KHÔNG tự validate lại
(giữ nguyên tắc validate tập trung ở module, router chỉ bắt `ValueError` → 400, xem mục
137).

**Tên file hậu tố ngôn ngữ** — mới, CẦN THIẾT (không chỉ nhất quán): 2 export CÙNG khoảng
block nhưng KHÁC ngôn ngữ (VD B01-B05 tiếng Đức + B01-B05 tiếng Anh, hợp lệ vì chiếm 2/3
slot khác nhau) trước đây sẽ ĐÈ TÊN FILE lên nhau trong Pack Export bundle
(`short_<start>-<end>.<ext>`, không phân biệt ngôn ngữ). Đổi thành
`short_<start>-<end>_<lang>.<ext>` — áp dụng CẢ ở `pack_export.py::export_pack_bundle`
LẪN endpoint tải riêng lẻ (`GET .../render/short-export/{id}/download`, filename qua
Content-Disposition — client `downloadFile()` ưu tiên tên NÀY hơn `fallbackFilename`
truyền vào, nên phải sửa ở backend mới có tác dụng thật).

### Frontend

`ShortVideoExportCard.tsx` thêm `<select>` "Ngôn ngữ giọng đọc" — CÙNG pattern
`RenderStudio.tsx` (mặc định ngôn ngữ chính của kênh, fetch qua `api.getBrandProfile`,
khởi tạo `null` rồi tự set 1 lần duy nhất không đè lựa chọn người dùng). KHÔNG precompute
cảnh báo "thiếu giọng đọc" phía client (khác `RenderStudio.tsx` — component đó có sẵn
`pack.shots` làm prop; `ShortVideoExportCard` chỉ nhận `project`, thêm precompute cần
truyền `pack` + lặp lại logic cắt khoảng block đã có ở backend — không đáng, lỗi 400 từ
backend đã đủ rõ, hiện thẳng trong khung `error` có sẵn). Mỗi export hiển thị kèm nhãn
ngôn ngữ trong danh sách đã xuất; nút Tải dùng đúng hậu tố ngôn ngữ trong tên file gợi ý.
`api/types.ts::ShortVideoExport` thêm `lang`; `api/client.ts::createShortExport` thêm
`lang` vào body, `downloadShortExport` thêm tham số `lang` cho tên file gợi ý (thực tế
server quyết định tên thật qua Content-Disposition, xem trên).

### Test

6 test mới `test_short_video_export.py`: mặc định `lang=None` → resolve về ngôn ngữ
chính; 400 khi `lang` không thuộc `NARRATION_LANGUAGES` (tầng module LẪN router); 400 khi
giọng đọc ngôn ngữ chọn chưa sinh xong, liệt kê đúng shot thiếu (tầng module LẪN router);
gate CHỈ soi shot TRONG khoảng đã chọn — giọng đọc "en" chỉ sinh cho 1 shot trong khoảng,
các shot NGOÀI khoảng thiếu "en" không chặn nhầm. Cập nhật fixture chung
(`_mark_shot_ready_fake`/`_mark_shot_ready_real`) thêm `narration_ready=True` mặc định
(giọng đọc ngôn ngữ chính "vi" luôn sẵn sàng) — bắt buộc SAU KHI thêm gate ngôn ngữ, mọi
test cũ trong file (không set narration) đều bắt đầu FAIL 400 "chưa sinh giọng đọc" khi
tạo short-export; `_mark_shot_ready_real` dựng audio CÂM THẬT qua `anullsrc` (không phải
bytes giả — `_build_segment` mux audio này qua ffmpeg thật, cùng bẫy FAKE_PNG đã biết cho
ảnh/video). Cập nhật 1 test cũ dùng exact-match tên file Pack Export
(`short_B01-B01.mp4` → `short_B01-B01_vi.mp4`). Full `pytest` **771 passed** (765 mục
139 + 6 mới). `tsc --noEmit` sạch.

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

## 141. Cắt nhỏ cue phụ đề dài trong transcript .srt, tránh tràn chữ khi hiển thị (2026-09-12)

Theo yêu cầu người dùng: "File transcript srt đang chia timestamp theo block. Vấn đề là
mỗi block có thể đọc quá dài nên việc hiển thị subtitle theo transcript bị tràn chữ. Cần
cắt ngắn xuống. Hãy định nghĩa logic và cắt ngắn số lượng chữ hiển thị 1 lần và chia nhỏ
timestamp của file srt ở độ dài phù hợp để có thể sử dụng sau này (ví dụ chèn caption vào
video khi render)" — sau đó xác nhận thêm: "cần khớp với VO giọng đọc của từng loại ngôn
ngữ".

### Phát hiện quan trọng lúc điều tra: có 2 hàm dựng SRT SONG SONG, không dùng chung

Grep toàn bộ codebase lộ ra **2 hàm xây SRT hoàn toàn độc lập**, cả 2 đều LUÔN gộp 1
block = 1 cue duy nhất (đúng nguyên nhân người dùng báo):
- `routers/pipeline.py::_build_srt` — dùng cho nút "Tải transcript (.srt)" ở Script
  Studio (`GET /projects/{id}/script/transcript-srt[/{lang}]`) — docstring CŨ ghi rõ "1
  cue/block (KHÔNG tự tách câu dài... đúng phạm vi yêu cầu)" — đúng giới hạn đã biết
  trước, giờ được gỡ theo yêu cầu mới.
- `render/pack_export.py::build_srt_text` — dùng RIÊNG cho `transcript_<lang>.srt` khi
  xuất Pack Export bundle.

Cả 2 hàm đều cần sửa — sửa 1 chỗ sẽ để sót đường còn lại (transcript tải trực tiếp ở
Script Studio VẪN sẽ tràn chữ dù Pack Export đã đúng, hoặc ngược lại).

### Thiết kế

**Module mới `app/render/captions.py`** — tách RIÊNG (không nhét vào `pack_export.py`
hay `pipeline.py`) vì đây là 1 mối quan tâm ĐỘC LẬP ("1 khoảng thời gian nói nên hiển thị
bao nhiêu chữ 1 lần"), và theo đúng yêu cầu người dùng cần TÁI DÙNG ĐƯỢC cho tính năng
khác sau này (chèn caption cứng lúc `assembly.py` ghép video — CHƯA build, để dành đúng
interface cho việc đó):
- `DEFAULT_MAX_CUE_CHARS = 84` — quy ước phổ biến cho phụ đề 2 dòng (~42 ký tự/dòng,
  kiểu hướng dẫn caption style Netflix/YouTube), áp dụng CHUNG mọi ngôn ngữ (giới hạn
  HIỂN THỊ không tràn khung hình, không phải giới hạn tốc độ nói).
- `split_text_into_cue_texts(text, max_chars)` — "greedy word wrap" chuẩn: gộp từ liên
  tiếp tới khi thêm từ tiếp theo vượt giới hạn thì xuống đoạn mới. CHỈ cắt tại ranh giới
  TỪ, KHÔNG BAO GIỜ cắt giữa 1 từ — 1 từ đơn lẻ dài hơn `max_chars` (hiếm — URL/số dài)
  vẫn giữ nguyên vẹn trên 1 đoạn riêng dù vượt giới hạn.
- `split_block_into_cues(text, start_sec, duration_sec, max_chars)` — cắt 1 block dài
  thành nhiều cue `(start, end, text)`, CHIA LẠI timestamp theo TỶ LỆ SỐ KÝ TỰ mỗi cue
  trên tổng ký tự của CHÍNH đoạn text đó (app chưa có forced alignment/ASR nên không có
  timestamp per-word thật — đây là xấp xỉ tốt nhất có thể). Cue LIÊN TỤC (không hở/đè),
  cue cuối luôn kết thúc ĐÚNG `start_sec+duration_sec` (tránh lệch số thập phân cộng dồn
  qua nhiều cue). Trả nguyên `[(start, start+duration, text)]` (không cắt) nếu text đã
  ngắn hơn `max_chars` — giữ NGUYÊN hành vi cũ cho block ngắn.

**Khớp ĐÚNG VO thật của TỪNG NGÔN NGỮ** (theo yêu cầu người dùng xác nhận thêm): hàm
`split_block_into_cues` KHÔNG tự giả định tốc độ đọc/nói theo ngôn ngữ nào — nó chỉ chia
lại 1 khoảng `(start, duration)` ĐÃ CÓ SẴN theo tỷ lệ ký tự. Caller (`_build_srt`/
`build_srt_text`) đã tự chọn ĐÚNG `text` (`audio`/`audio_by_lang[lang]`) VÀ ĐÚNG
`duration` (giọng đọc THẬT đo qua ffprobe của CHÍNH ngôn ngữ đó —
`narration_duration_sec`/`translation.narration_duration_sec`, không phải ước lượng)
TRƯỚC khi gọi — nên dù bản dịch 1 ngôn ngữ DÀI HƠN hẳn về số ký tự (VD tiếng Đức thường
dài hơn tiếng Việt cho cùng nội dung) nhưng giọng đọc đo thật lại NGẮN hơn/dài hơn khác
hẳn tỷ lệ ký tự, cue của ngôn ngữ đó vẫn LUÔN khớp đúng tổng thời lượng ĐO THẬT của CHÍNH
NÓ — không lẫn với ngôn ngữ khác.

**Áp dụng vào cả 2 hàm dựng SRT hiện có** — chỉ thêm 1 bước gọi `split_block_into_cues`
ngay tại điểm trước đây append 1 cue duy nhất, KHÔNG đổi logic tính `text`/`duration` gốc
(giữ nguyên mọi hành vi đa ngôn ngữ/intro-offset/fallback đã có):
- `routers/pipeline.py::_build_srt` — thêm tham số `max_cue_chars` (mặc định
  `DEFAULT_MAX_CUE_CHARS`), `cues.append((start, end, text))` → `cues.extend(split_block_
  into_cues(text, start, duration, max_chars=max_cue_chars))`.
- `render/pack_export.py::build_srt_text` — cùng thay đổi, thêm tham số `max_cue_chars`.

### Test

9 test mới `test_transcript.py`: `split_text_into_cue_texts` giữ nguyên text ngắn, không
bao giờ cắt giữa từ (ghép lại đúng nguyên văn), giữ nguyên 1 từ đơn lẻ dài hơn giới hạn;
`split_block_into_cues` trả 1 cue khi text ngắn, cue liên tục + khớp khít khoảng đưa vào
+ cue dài hơn (nhiều ký tự hơn) được cấp nhiều thời gian hơn tỷ lệ thuận (không chia đều
theo số cue), text rỗng trả `[]`, duration=0 không crash; `_build_srt` cắt đúng block dài
thành nhiều cue liên tục khớp đúng tổng thời lượng giọng đọc thật (không phải timestamp
kịch bản); `build_srt_text` (Pack Export) verify TRỰC TIẾP yêu cầu "khớp VO từng ngôn
ngữ" — bản dịch "de" dài hơn hẳn "vi" về ký tự nhưng giọng đọc đo thật NGẮN hơn, cue "de"
phải khớp đúng tổng thời lượng đo thật của "de" (không lẫn thời lượng "vi"). Toàn bộ
test cũ (`test_transcript.py`/`test_render.py`/`test_narration_translations.py`, dùng
text ngắn dưới 84 ký tự) PASS KHÔNG SỬA — xác nhận hành vi cũ giữ nguyên cho block ngắn
(nhánh "không cắt" của `split_block_into_cues`). Full `pytest` **780 passed** (771 mục
140 + 9 mới). `tsc --noEmit` không áp dụng (chỉ backend đổi).

Backend đổi (frontend không đổi gì — hiệu ứng tự động áp dụng cho MỌI lần tải transcript
.srt, không cần thao tác UI nào thêm) — **cần khởi động lại app** để dùng được.

## 142. Layer CAPTION (phụ đề cứng burn-in) ở Visual Studio, chọn vị trí/kích thước/độ mờ/ngôn ngữ (2026-09-12)

Theo yêu cầu người dùng: "Bổ sung tính năng cho phép user thêm caption vào video ở bước
visual studio. Thêm 1 layer cho việc hiển thị caption, user có thể chọn 9 vị trí, kích
thước, độ mờ tương tự phần Layer video định vị" — sau đó xác nhận thêm 2 lần: "cần khớp
với VO giọng đọc của từng loại ngôn ngữ" và "chọn cả loại ngôn ngữ nữa" (ngôn ngữ caption
chọn ĐỘC LẬP với ngôn ngữ giọng đọc). Dùng LẠI trực tiếp `app/render/captions.py` (mục
141, "để dành... chèn caption cứng lúc ghép video khi render") — đúng lúc cần tới.

Lên kế hoạch qua `EnterPlanMode` (quy mô tương đương tính năng short-video export) —
2 câu hỏi xác nhận qua AskUserQuestion: (1) áp dụng CHO CẢ short-video export lẫn video
chính — chọn CẢ 2 (nhất quán, tái dùng chung `_build_segment`); (2) ngôn ngữ caption mặc
định — theo ngôn ngữ đang ghép video (`export_lang`), đổi được sang ngôn ngữ khác.

### Quyết định kiến trúc: burn per-SEGMENT, không phải trên video đã ghép xong

Cân nhắc 2 hướng: (A) burn 1 lần trên video ĐÃ GHÉP XONG — cần mô phỏng lại TOÀN BỘ toán
học `_run_boundaries`/`_xfade_chain` (co giãn overlap transition, offset intro) bằng
Python thuần để tính mốc thời gian tuyệt đối từng shot, rủi ro lệch/trôi cao; (B) burn
NGAY TRONG từng segment (đã chọn) — mỗi shot đã có ĐÚNG `duration[i]` cấp cho
`_build_segment` (khớp 100% qua `-t duration` của ffmpeg), sinh 1 file caption RIÊNG cho
segment đó với timestamp CỤC BỘ `[0, duration[i])`, burn NGAY vào chính segment — vì
caption giờ là PIXEL THẬT bên trong segment, tự động đi theo segment qua mọi bước ghép
sau (concat/xfade), KHÔNG thể lệch. Intro KHÔNG có caption (không có nội dung script).

### Bug thật xác nhận bằng ffmpeg thật — `.srt` + `force_style` KHÔNG dùng được, phải tự viết `.ass`

Bản đầu dùng filter `subtitles=file.srt:original_size={out_w}x{out_h}:force_style=
'Fontsize=...'`, kỳ vọng `original_size` khiến `Fontsize` (đơn vị pixel trong
`force_style`) quy đổi ĐÚNG theo khung hình xuất thật. Verify bằng ffmpeg thật + trích
frame: SAI HẲN — 2 lỗi liên tiếp phát hiện qua test thật (không suy đoán):
1. Escape đường dẫn Windows (`E:\...`) chỉ escape dấu `:` KHÔNG ĐỦ — filter graph parser
   của ffmpeg đọc lố qua dấu đã escape, "nuốt" luôn phần `original_size=...` phía sau vào
   giá trị filename (`Unable to parse "original_size" option value`). Fix: bọc THÊM 1
   lớp nháy đơn quanh toàn bộ path đã escape.
2. Sau khi path đúng, `original_size` vẫn KHÔNG có tác dụng "quy Fontsize sang pixel
   thật" như kỳ vọng — dùng để scale font theo tỷ lệ khung hình GỐC ↔ khung hình ĐANG
   decode, không phải ý nghĩa đó. `.srt` thuần khiến libass tự chọn PlayRes mặc định —
   `Fontsize=96` trên khung 1080x1920 ra chữ KHỔNG LỒ chiếm gần hết chiều cao khung hình
   (xác nhận bằng ảnh trích frame thật).

**Fix triệt để**: bỏ hẳn `.srt` + `force_style`, tự viết 1 file `.ass` HOÀN CHỈNH
(`captions.py::write_shot_caption_ass`) — tự khai `[Script Info] PlayResX/PlayResY` =
ĐÚNG độ phân giải xuất, Style (Fontsize/màu/viền/lề/Alignment) khai TRỰC TIẾP trong
`[V4+ Styles]`. `Fontsize` giờ LUÔN đúng đơn vị pixel trong hệ toạ độ đã khai, không còn
phụ thuộc suy luận về hành vi mặc định của libass. Verify lại bằng ffmpeg thật: chữ ra
đúng cỡ hợp lý, đúng vị trí bottom-center (đếm pixel: dải dưới khung hình có nhiều pixel
khác nền hẳn dải trên, tỷ lệ NGƯỢC LẠI khi đổi sang "top-center") — bài học: dù tài liệu
ffmpeg gợi ý 1 cách làm nghe hợp lý, PHẢI verify thật bằng ffmpeg + trích frame trước khi
tin, không suy luận suông (cùng bài học đã ghi ở `_concat_intro_and_body`, mục 79).

### Thiết kế

`render/schemas.py::CaptionLayer` (mới) — `enabled`/`position` (tái dùng `LayerPosition`
9 ô lưới, không có `"full"`)/`size_pct` (cỡ chữ = % CHIỀU CAO khung hình, mặc định
0.045 — khác `width_pct` % chiều RỘNG của layer video/ảnh)/`opacity`/`lang`. `RenderState.
caption_layer: Optional[CaptionLayer]` — 1 CẤU HÌNH DUY NHẤT/project (KHÁC `layers`/
`image_layers` — list nhiều instance, upload file).

`captions.py::write_shot_caption_ass(path, text, duration_sec, *, position, size_pct,
opacity, out_w, out_h, max_chars)` — gộp cắt cue (tái dùng `split_block_into_cues`, mục
141) + dựng `.ass` hoàn chỉnh thành 1 hàm. `LAYER_POSITION_TO_ASS_ALIGNMENT` map 9 vị
trí sang "Alignment" kiểu numpad ASS/libass (khớp thẳng, không cần bảng tra phức tạp).

`assembly.py::_build_segment` thêm 1 kwarg tuỳ chọn `caption_ass_path` (mặc định `None`,
KHÔNG đổi hành vi caller cũ) — nối `,subtitles={escaped_path}` vào CUỐI chuỗi `-vf` đã
dựng (ở CẢ 3 nhánh: motion_filter/is_video/ảnh tĩnh). `_escape_ffmpeg_filter_path` (mới)
— escape `:` + bọc nháy đơn (xem bug thật ở trên).

Wiring vào **CẢ 2** pipeline (`_assemble_video_impl` VÀ `short_export.py::
run_short_export`) — cùng 1 đoạn chuẩn bị trước mỗi lần gọi `_build_segment`: đọc
`state.caption_layer`, resolve `caption_lang` (`state.caption_layer.lang` nếu hợp lệ,
không thì `export_lang`), lấy `beat.get("audio")`/`audio_by_lang[caption_lang]`, gọi
`write_shot_caption_ass` với `durations[i]` CHÍNH XÁC của shot đó.

Router `PATCH /projects/{id}/render/caption-layer` (mới, `routers/render.py`) — 1
endpoint DUY NHẤT (không có POST/DELETE — không upload file, tắt qua `enabled=false`),
partial update, lazy-create `state.caption_layer` (giống `bg_music`/`overlay`). Validate
`position` (9 giá trị), `size_pct` (0.01–0.3), `opacity` (0.0–1.0), `lang` (thuộc
`NARRATION_LANGUAGES` nếu khác rỗng/`null`).

### Frontend

`VisualStudio.tsx::CaptionLayerCard` (mới, cạnh `LayersCard`/`ImageLayersCard`) — TÁI
DÙNG `PositionGridPicker` đã có sẵn. Toggle bật/tắt, lưới 9 vị trí, slider kích thước
chữ (% chiều cao), slider độ mờ, `<select>` ngôn ngữ caption (`NARRATION_LANGUAGES` +
option "Theo ngôn ngữ đang ghép video" mặc định, value rỗng → `null`). `api/types.ts`
thêm `CaptionLayer` + `RenderState.caption_layer`; `api/client.ts` thêm
`patchCaptionLayer`.

### Test

21 test mới: `test_caption_layer.py` (19 test, file mới) — đơn vị thuần cho
`write_shot_caption_ass` (PlayRes khớp đúng độ phân giải, 9 vị trí → đúng Alignment,
Fontsize từ `size_pct*out_h`, opacity → alpha ASS đảo ngược, text rỗng → không ghi file,
text dài → nhiều dòng Dialogue); router PATCH (tạo mặc định, partial update, roundtrip
`lang`, 400 khi position/lang/size_pct/opacity sai, 404 project không tồn tại); burn-in
THẬT qua `_build_segment` (ffmpeg thật, đếm pixel: "bottom-center" tập trung dải dưới
gấp >5 lần dải trên, "top-center" ngược lại — verify ĐÚNG cả 2 hướng, không chỉ 1 hướng
"tình cờ đúng"). +1 test `test_render.py` (tích hợp qua CẢ `assemble_video()` thật —
status "done" + pixel caption thật xuất hiện). +1 test `test_short_video_export.py`
(tích hợp qua `run_short_export` thật, bật caption qua ĐÚNG endpoint PATCH giống người
dùng thao tác UI). Full `pytest` **801 passed** (780 mục 141 + 21 mới). `tsc --noEmit`
sạch.

## 143. Chỉ số YouTube tự động (kéo qua OAuth) theo kênh + theo video ở Dashboard (2026-09-12)

Theo yêu cầu người dùng: "đề xuất phương án triển khai tính năng thống kê các chỉ số cho
kênh, kéo dữ liệu từ youtube về" kèm bộ chỉ số cốt lõi cụ thể (§5.4 North-star: APV ≥45%
+ retention theo từng chương + Returning Viewers; chỉ số vận hành: RPM ≥€5/6 tháng, CTR
5-8%, retention giây 30 ≥70%, bình luận/1.000 view, tỷ trọng DE/AT/CH) — và yêu cầu bấm
vào kênh ở Dashboard phải thấy được các chỉ số này CẢ theo TOÀN KÊNH lẫn THEO TỪNG VIDEO.

Lên kế hoạch qua `EnterPlanMode`, 2 câu hỏi xác nhận: (1) RPM — quyền OAuth
`yt-analytics-monetary.readonly` rất khó xin cho app cá nhân (Google yêu cầu audit CMS/
Content Owner) → **giữ nhập tay** (chọn "Bỏ qua tự động, giữ nhập tay"); (2) sau khi
duyệt plan, hỏi tiếp có bắt đầu code Phase 1 ngay không dù còn phụ thuộc thiết lập ngoài
(Google Cloud Console) → **có, bắt đầu ngay**.

### Kiến trúc: OAuth loopback tự đăng ký, không nhúng client dùng chung

App KHÔNG nhúng sẵn 1 OAuth Client chung (rủi ro bảo mật khi phân phối + tranh chấp quota
giữa nhiều người dùng) — người dùng tự tạo 1 Google Cloud project + OAuth Client loại
"Desktop app", dán `client_id`/`client_secret` vào Settings → "Chỉ số YouTube" (mã hoá
qua `app/crypto.py`, TÁI DÙNG bảng `app_setting` key-value thay vì tạo bảng riêng — 2 key
`youtube_oauth_client`/`youtube_oauth`, đủ dùng cho Phase 1 chỉ 1 tài khoản Google, tránh
over-engineering — đây là 1 ĐIỂM LỆCH so với plan ban đầu, plan đề xuất 1 bảng
`YoutubeOAuthCredential` FK riêng nhưng lúc code thấy không cần thiết).

Luồng: nút "Kết nối tài khoản Google" → `window.studioflowNative.openExternal(url)` mở
trình duyệt HỆ THỐNG (không phải cửa sổ app, Google chặn embedded browser cho login) tới
URL consent (`access_type=offline&prompt=consent` để LUÔN nhận được `refresh_token`, kể
cả những lần đồng ý sau lần đầu) → Google redirect về `http://127.0.0.1:{port}/oauth/
callback` (chính backend FastAPI đang chạy phục vụ luôn route này — Google "Desktop app"
client chấp nhận BẤT KỲ `127.0.0.1:*` không cần đăng ký cổng trước) → đổi code lấy token
→ Settings tự POLL trạng thái mỗi 2s (không có cách nào khác để React app biết trình
duyệt ngoài đã hoàn tất). Scope: `youtube.readonly` + `yt-analytics.readonly` — KHÔNG xin
`yt-analytics-monetary.readonly`.

**Bug thật sửa lúc code** (không phải lúc verify sau): thiết kế ban đầu để `/oauth/
callback` nhận `redirect_uri` qua query param, kỳ vọng Google echo lại y nguyên — SAI,
OAuth 2.0 không đảm bảo Google echo query param tuỳ ý (chỉ đảm bảo `code`/`scope`/
`state`). Sửa: endpoint nhận `Request` object, tự suy `redirect_uri = f"{scheme}://
{netloc}{path}"` từ chính request — luôn khớp chính xác vì Google chỉ có thể điều hướng
trình duyệt tới ĐÚNG URL đã đăng ký.

Liên kết Channel↔kênh YouTube: gọi `channels.list(mine=true)` lấy `channel_id`/`title`
THẬT, KHÔNG bắt user tự dán ID. Liên kết Project↔video: dropdown ở `RetentionCard`
(Output Center), user TỰ CHỌN từ `playlistItems.list` trên "uploads" playlist (rẻ quota
hơn `search.list`, ~1 unit so với 100), KHÔNG tự đoán theo tên trùng khớp — đúng CLAUDE.md
"mỗi bước là hành động rõ ràng người dùng tự bấm".

### Đồng bộ: 1 nút thủ công, ghi snapshot mới mỗi lần (giữ lịch sử)

2 bảng mới `YoutubeChannelMetricsSnapshot`/`YoutubeVideoMetricsSnapshot` (tự tạo qua
`create_all()`) — mỗi lần bấm "Đồng bộ" (cấp KÊNH, đồng bộ TẤT CẢ video đã liên kết cùng
lúc) ghi 1 dòng MỚI, không update tại chỗ, đúng pattern `RetentionEntry` đã có. Analytics
API hỗ trợ batch nhiều video/1 request (`filters=video==id1,id2,...`) cho hầu hết metric,
RIÊNG report `audienceRetention` (đường cong retention) KHÔNG batch được — gọi riêng từng
video. Chỉ số cấp kênh tính TRUNG BÌNH CÓ TRỌNG SỐ theo view giữa các video (không phải
trung bình cộng đơn giản) qua helper `_weighted_avg`.

Retention theo từng chương: khớp `elapsedVideoTimeRatio` (report `audienceRetention`) với
`pack.script.body[]` theo TỶ LỆ CỘNG DỒN THỜI LƯỢNG THEO THỨ TỰ BLOCK (ưu tiên
`ShotRenderStatus.narration_duration_sec` THẬT nếu project từng render qua StudioFlow,
fallback ước tính kịch bản `end_sec - timestamp_sec`) — KHÔNG dùng giây tuyệt đối của
kịch bản gốc vì timeline video thật ăn theo giọng đọc thật, không khớp giây kịch bản ước
tính. Trả về + đánh dấu chương tụt mạnh nhất, CHỈ hiển thị thông tin, không tự feed ngược
vào guardrail.

**Returning Viewers**: cờ RỦI RO/CHƯA XÁC MINH trong plan — dimension `subscribedStatus`
công khai KHÔNG tương đương "new vs returning" (card đó chỉ thấy trong YouTube Studio UI,
khả năng chỉ expose ở cấp Content Owner/CMS) — CHƯA build, cần 1 spike xác nhận API thật
trước; nếu không tự động hoá được sẽ fallback nhập tay như RPM.

### Backend

`app/youtube_migration.py` (mới, ALTER TABLE thêm cột cho bảng cũ, theo pattern
`asset_vault/migration.py::_add_missing_columns`): `Channel.youtube_channel_id/title/
connected_at`, `Project.youtube_video_id`, `RetentionEntry.rpm`.

`app/youtube_analytics.py` (mới) — OAuth (`build_authorize_url`/
`exchange_code_for_credentials`/`load_credentials` tự refresh token hết hạn), Data API
(`fetch_channel_info`/`fetch_uploaded_videos`/`fetch_video_durations`), Analytics API
(`fetch_video_analytics` batch/`fetch_retention_curve` riêng từng video/
`fetch_country_breakdown`), logic thuần (`parse_iso8601_duration`, `retention_at_ratio`
nội suy tuyến tính, `correlate_retention_with_blocks`).

`app/routers/youtube_analytics.py` (mới) — toàn bộ endpoint liệt kê ở `specs/03_api.md`
§"Chỉ số YouTube". Dependency mới: `google-auth==2.35.0`, `google-auth-oauthlib==1.2.1`,
`google-api-python-client==2.149.0`.

`app/routers/guardrail.py::RetentionBody`/`get_retention` thêm field `rpm` (nhập/trả về).

### Frontend

`Dashboard.tsx` — thêm tab "Dự án"/"Chỉ số YouTube" trong panel mở rộng theo kênh (giữ
nguyên bảng project cũ, không dựng màn/route riêng). `components/YoutubeMetricsPanel.tsx`
(mới) — hiện nút kết nối kênh (nếu chưa gắn YouTube), nút Đồng bộ/Ngắt kết nối, thẻ
North-star + vận hành (cấp kênh), bảng video (cấp project) với nút "Theo chương" mở biểu
đồ thanh ngang đánh dấu chương tụt mạnh nhất. `screens/settings/YoutubeSettings.tsx`
(mới, thêm vào `SettingsShell.tsx`) — form OAuth Client + nút kết nối + poll trạng thái.
`screens/steps/OutputCenter.tsx::RetentionCard` — thêm `YoutubeVideoLinkPicker` (dropdown
chọn video YouTube) + field `rpm` vào form nhập tay. `electron/src/main.ts`/`preload.ts`
thêm IPC `openExternal` (bọc `shell.openExternal`).

### Test

25 test mới `test_youtube_analytics.py` — logic thuần (parse ISO 8601 duration, nội suy
retention tuyến tính, khớp block theo tỷ lệ cộng dồn — verify bằng số tính tay), OAuth
client roundtrip mã hoá, toàn bộ router (mock qua `monkeypatch.setattr("app.routers.
youtube_analytics.<fn>", ...)` vì `googleapiclient` không dùng httpx nên không mock được
qua `respx`) gồm cả bug redirect_uri đã sửa, và 1 test chi tiết verify ĐÚNG công thức
trung bình có trọng số + nội suy retention giây 30 bằng số liệu giả lập biết trước kết
quả. Full `pytest` **826 passed** (801 mục 142 + 25 mới). `tsc --noEmit` sạch sau cả
backend lẫn frontend (Dashboard/Settings/OutputCenter).

Cập nhật `specs/02_database.md` (cột mới + 2 bảng snapshot + `app_setting` key mới),
`specs/03_api.md` (§"Chỉ số YouTube"), `specs/08_retention_guardrail.md` (§7 đổi từ "lộ
trình chưa build" sang mô tả ĐÃ triển khai), `specs/09_sprint_tasks.md` (đánh dấu hạng
mục M4 liên quan đã build).

**Chưa build (ngoài phạm vi lần này, có ghi rõ trong spec)**: biểu đồ retention theo
chương ở UI dùng nguyên dữ liệu thô (endpoint backend đã có, hiển thị hiện tại là bar đơn
giản không phải chart đầy đủ tương tác); Returning Viewers (cần spike API trước).

Backend + frontend đều có thay đổi — **cần khởi động lại app** để dùng được.

## 144. Kho Tài Nguyên + Visual Studio — lọc video nguồn cho asset Visual Studio, progress bar auto-fill, thông tin đầy đủ ở Vault Clip Picker (2026-09-13)

Theo yêu cầu người dùng, 3 vấn đề UX phát sinh sau khi dùng các tính năng đã build trước
đó (mục 133-135): (1) dropdown "Video nguồn" ở bảng "Asset từ Visual Studio" trong Kho
Tài Nguyên không lọc đúng theo project sinh ra asset; (2) bấm "Tự động điền từ Kho tài
nguyên" không hiện tiến trình quét; (3) picker "Video từ Kho"/"Ảnh từ Kho" ở từng shot
thiếu thông tin, mọi candidate đều hiện "Chưa xác minh" không giúp gì cho việc chọn.

Lên kế hoạch qua `EnterPlanMode`, dùng 1 Explore agent đọc code thật xác nhận cả 3 root
cause trước khi viết plan (không suy đoán).

### 1. Lọc "Video nguồn" cho asset Visual Studio

Root cause: `GET /asset-vault/raw` (`asset_vault.py::list_raw_videos`) LUÔN loại hàng
`RawVideo` "ảo" đại diện project (`source_project_id IS NOT NULL`) ra khỏi kết quả — đúng
cho bảng Raw Library, nhưng `AssetVault.tsx` lại dùng CHUNG state đó để build dropdown
"Video nguồn" cho CẢ bảng "Asset từ Visual Studio", nên dropdown đó không bao giờ có
option nào trỏ đúng project, dù mỗi clip đã có sẵn `raw_video_id` trỏ đúng hàng ảo đó và
logic filter vốn đã đúng — chỉ thiếu option để chọn.

Fix: thêm query param `kind: str = "raw"|"project"` cho `list_raw_videos` (đảo filter khi
`kind="project"`); `AssetVault.tsx` gọi thêm 1 lượt `api.listRawVideos(undefined,
"project")` song song, lưu state `projectSourceRows` riêng, truyền cho ĐÚNG bảng "Asset từ
Visual Studio" thay vì `rawVideos` chung (đã xác nhận prop này trong
`ProcessedClipLibrarySection` chỉ dùng để build dropdown, không ảnh hưởng chỗ nào khác —
an toàn để tách). Thêm prop `rawFilterLabel` (mặc định "video gốc", "project" cho bảng
Visual Studio) để placeholder dropdown đúng ngữ cảnh.

### 2. Progress bar cho "Tự động điền từ Kho tài nguyên"

Root cause: `GET /projects/{id}/render/vault-auto-fill-suggestions` là 1 route ĐỒNG BỘ,
lặp qua từng shot gọi embedding AI thật (network round-trip mỗi shot) — không có bước
lưu/expose tiến trình nào, khác hẳn pattern `RawVideo.progress_current/total/label` +
`BackgroundTasks` đã dùng cho cắt cảnh/xoá watermark/tải URL. Với project nhiều shot +
provider cloud có độ trễ, quá trình có thể mất vài chục giây tới vài phút mà UI chỉ hiện
nhãn nút tĩnh.

Fix: thay 1 endpoint đồng bộ bằng 2 endpoint — `POST .../vault-auto-fill-scan` (khởi động
`BackgroundTasks`, không khởi động lại nếu đã có job "running" cho project đó) +
`GET .../vault-auto-fill-scan/status` (poll tiến trình). Tiến trình lưu trong 1 dict cấp
module `_AUTO_FILL_JOBS: dict[str, dict]` (key = project_id) — **quyết định kiến trúc**:
KHÔNG thêm bảng DB mới cho state tạm thời này, vì app single-user/local không cần bền
vững qua restart hay khoá đa tiến trình, đúng tinh thần "không over-engineer" của
CLAUDE.md. Logic quét bên trong giữ NGUYÊN (copy y hệt vòng lặp cũ), chỉ thêm cập nhật
`current`/`total`/`current_label` mỗi vòng lặp (`total` tính TRƯỚC vòng lặp = số shot
chưa `ready`, đúng ý "quét đến block nào" người dùng cần thấy) và bọc `try/except` quanh
toàn bộ để lỗi bất ngờ không treo job ở "running" mãi.

Frontend (`VisualStudio.tsx::openAutoFillScan`): POST khởi động job, sau đó
`window.setInterval` (ref riêng `autoFillPollRef`, không dùng chung `pollRef` đang phục
vụ `loadRenderStatus`) poll mỗi 800ms, render `<ProgressBar>` (component đã có sẵn, TÁI
DÙNG nguyên — đã dùng cho tiến trình xoá watermark từng shot ở cùng file) ngay cạnh nút.

### 3. Vault Clip Picker — thông tin đầy đủ để chọn đúng

Root cause kép: (a) `GET .../vault-candidates` chỉ trả `clip_id`/`caption`/
`duration_sec`/`match_score`/`rights_status` — các field khác đã có SẴN trên object
`ProcessedClip` đang cầm trong tay (`tags`/`mood_tone`/`resolution`/`usage_count`, đã hiện
đủ ở màn Kho Tài Nguyên qua `_clip_out()`) nhưng chưa từng đưa vào response picker này; (b)
`VaultClipPicker.tsx` không render thumbnail dù `VaultAutoFillModal` (cùng file
`VisualStudio.tsx`) đã có sẵn ĐÚNG pattern (`api.clipFileUrl` + `<img>`/`<video>` tuỳ
`media_kind`) — chỉ chưa được tái dùng; (c) badge "Chưa xác minh" (`rights_status` mặc
định) không sai nhưng vô nghĩa cho asset TỰ SINH từ Visual Studio (khái niệm "rights" chỉ
có ý nghĩa cho B-roll thật có nguồn/license) — cờ `from_visual_studio` đã tính sẵn ở
`_clip_out()` theo công thức `bool(c.raw_video and c.raw_video.source_project_id)`.

Fix: mở rộng response `get_vault_candidates` thêm 5 field (`resolution`, `tags`,
`mood_tone`, `usage_count`, `from_visual_studio` — tái dùng ĐÚNG công thức của
`_clip_out()`). `VaultClipPicker.tsx` thêm thumbnail 56×42 (copy y hệt pattern
`VaultAutoFillModal`), hiện chip tag/mood_tone, hiện `resolution` cho ảnh (trước đây để
trống hoàn toàn) + `usage_count` khi >0 ("Đã dùng N lần"), và ẩn HẲN badge rights khi
`from_visual_studio === true` (không còn hiện "Chưa xác minh" vô nghĩa cho asset tự sinh).

### Test

Backend: cập nhật 2 test cũ gọi trực tiếp endpoint đồng bộ đã xoá sang flow POST scan →
GET status (TestClient chạy `BackgroundTasks` đồng bộ trong cùng lời gọi nên poll ngay
sau POST đã thấy `status="done"`, không cần sleep/retry thật). Thêm 1 test `status=
"idle"` khi project chưa từng quét, 1 test xác nhận field mới xuất hiện đúng + badge ẩn
đúng cho clip từ Visual Studio (`from_visual_studio=True`), mở rộng 1 test có sẵn xác
nhận `from_visual_studio=False` cho clip B-roll thật. Full `pytest` **828 passed** (826
mục 143 + 2 mới ròng — vài test cũ được SỬA tại chỗ chứ không thêm mới thuần tuý).
`tsc --noEmit` sạch.

## 145. Vault Clip Picker — thêm match score cho nhánh keyword, sắp xếp giảm dần (2026-09-13)

Theo yêu cầu tiếp của người dùng sau mục 144: "cần thêm matching score và xếp theo thứ
tự giảm dần". Đọc lại code phát hiện 2 lỗ hổng cụ thể:

- `match_by_keyword` (`asset_vault/matching.py`) đã TỰ tính điểm khớp từ khoá nội bộ để
  sort, nhưng bỏ điểm đó khi trả về (`get_vault_candidates` gán cứng `(c, None)` cho mọi
  clip khớp keyword) — nên picker KHÔNG BAO GIỜ hiện badge "% match" khi chưa cấu hình
  Embedding provider (nhánh fallback từ khoá), dù nội bộ đã biết rõ mức độ khớp.
- Thứ tự candidate trả về CHỈ tình cờ đúng nhờ `match_semantic`/`match_by_keyword` đều
  tự sort nội bộ trước khi trả — `get_vault_candidates` chưa từng sort tường minh, nên
  riêng nhánh `fallback_neutral_broll` (B-roll trung tính, không có điểm) lẫn vào giữa
  danh sách theo thứ tự query DB ngẫu nhiên thay vì luôn ở cuối.

Fix: `match_by_keyword` đổi kiểu trả về từ `list[ProcessedClip]` sang `list[tuple[
ProcessedClip, float]]` — điểm chuẩn hoá `số từ khớp / tổng số từ mô tả` (thang 0-1,
ĐỒNG NHẤT với similarity 0-1 của `match_semantic`, để picker hiển thị/so sánh được cả 2
nguồn cùng 1 công thức "% match"). `get_vault_candidates` thêm 1 bước `sorted(...,
key=..., reverse=True)` TƯỜNG MINH ngay trước khi build response, đẩy candidate không có
điểm (fallback trung tính) xuống CUỐI thay vì lẫn giữa. Cập nhật 4 test cũ gọi trực tiếp
`match_by_keyword` (unpack tuple thay vì `ProcessedClip` trần) + thêm 1 test khẳng định
thứ tự VÀ điểm số đúng khi cố tình chèn clip điểm THẤP trước clip điểm CAO (loại trừ khả
năng test pass "ăn may" nhờ thứ tự insert). Frontend KHÔNG cần sửa gì — `VaultClipPicker.
tsx` đã render badge match score có điều kiện `!= null` từ mục 144, giờ điều kiện đó tự
đúng luôn cho cả nhánh keyword vì backend không còn trả `null`.

Full `pytest` **829 passed** (828 mục 144 + 1 mới). `tsc --noEmit` sạch (không đổi file
frontend nào).

## 146. Bug thật: asset lưu từ Visual Studio KHÔNG BAO GIỜ được index vào Chroma — "Tự động điền" bỏ sót MỌI asset tự sinh (2026-09-13)

Người dùng báo: block B07 trong 1 project có sẵn ảnh khớp **100% match** khi tự tìm bằng
tay ("Ảnh từ Kho"), nhưng "Tự động điền từ Kho tài nguyên" không hề gợi ý nó.

### Chẩn đoán trực tiếp trên workspace thật của người dùng

Tra thẳng `workspace/studioflow.db` (không suy đoán) — tìm đúng clip có caption khớp Y
HỆT mô tả B07 (`clip_17892794321681ab0d8`), phát hiện `vector_id = NULL`. Kiểm tra toàn
bộ DB: **152/152 ảnh lưu từ Visual Studio (mọi kênh) đều có `vector_id = NULL`** — trong
khi B-roll thật đã "Gắn nhãn" thì có 73/431 đã index. Đây là lỗi HỆ THỐNG, không riêng
B07.

**Root cause**: "Tự động điền" (`render.py::_run_vault_auto_fill_scan`) CHỈ tìm qua
`match_semantic` (Chroma) — KHÔNG có fallback từ khoá như nút "Video/Ảnh từ Kho" thủ công
(`get_vault_candidates`, mục 145 vừa thêm điểm cho nhánh keyword). `asset_vault/
from_visual_studio.py::save_shots_to_vault` (mục 135) lưu asset kèm caption có sẵn (từ
`visual_fx`) nhưng **chưa bao giờ gọi bước embed + upsert Chroma** — bước đó trước giờ chỉ
nằm gộp trong `ingest.py::caption_clip` (dành cho B-roll thật cần AI Vision chụp caption),
và vì asset Visual Studio không cần captioning AI nên toàn bộ hàm đó (kể cả phần embedding
đi kèm) bị bỏ qua luôn — một lỗ hổng chưa lường tới khi build mục 135.

### Fix

- `ingest.py`: tách `index_clip_embedding(db, clip)` ra khỏi `caption_clip` (dùng field
  `caption`/`tags`/`mood_tone` SẴN CÓ trên clip, không gọi Vision provider) — `caption_clip`
  gọi lại hàm này, hành vi cũ giữ nguyên 100%.
- `from_visual_studio.py::save_shots_to_vault`: gọi `index_clip_embedding` (bọc
  `_try_index_clip_embedding` nuốt lỗi) ở CẢ 2 nhánh — tạo clip mới và cập nhật đè clip đã
  lưu trước đó. Thiếu Embedding provider là trạng thái HỢP LỆ (không phải lỗi) — không
  được chặn hành động "Lưu vào Kho tài nguyên", đúng nguyên tắc try/except đã áp dụng cho
  `match_semantic` ở `get_vault_candidates`.
- **Backfill dữ liệu cũ**: chạy 1 script một-lần (không thêm vào migration tự động lúc
  khởi động — gọi embedding là network call thật, không giống các migration ALTER TABLE
  cục bộ tức thời khác trong app, chạy tự động mỗi lần mở app sẽ vi phạm nguyên tắc "không
  tự động chạy ngầm") trực tiếp trên `workspace/studioflow.db` thật của người dùng, dùng
  ĐÚNG `index_clip_embedding` vừa thêm — **152/152 clip backfill thành công, 0 lỗi**. Xác
  minh lại bằng `match_semantic` thật cho đúng mô tả B07: clip khớp giờ đạt **similarity
  0.937** (> ngưỡng auto-fill 0.8) — xác nhận fix giải quyết ĐÚNG vấn đề người dùng báo,
  không chỉ set field cho có.

### Test

2 test mới `test_visual_studio_vault.py`: `test_save_shots_to_vault_indexes_embedding_when_provider_configured`
(respx mock embedding provider, xác nhận `vector_id` được set ngay khi lưu, cả 2 shot) và
`test_save_shots_to_vault_succeeds_without_embedding_provider_configured` (không có
provider — lưu vẫn thành công, `vector_id` ở lại `None`, không lỗi). Full `pytest`
**831 passed** (829 mục 145 + 2 mới). `tsc --noEmit` sạch (không đổi frontend).

## 147. Visual Studio — upload cả folder ảnh/video, tự khớp tên file với mã block (2026-09-16)

Theo yêu cầu người dùng: "cho phép upload video từ folder chứa sẵn nhiều ảnh/video có
sẵn với tên file trùng với tên block ID (B01,B02,...). Sau khi upload, tự động map tên
file vào tên mã block và hiện popup báo đã upload và match thành công bnhieu file, bao
nhiêu file chưa match và liệt kê tên file chưa match".

Lên kế hoạch qua `EnterPlanMode`, nghiên cứu code thật trước khi viết plan (Explore
agent): xác nhận `shot_id` CHÍNH LÀ mã block (`pipeline.py::_seed_shot_from_beat`:
`"shot_id": beat.get("block_id") or ...`) — khớp tên file chỉ cần `Path(filename).stem`
so với `shot_id`, không cần bảng tra cứu riêng. Không có IPC Electron nào đọc nội dung
folder (`chooseFolder` hiện tại chỉ trả 1 đường dẫn, dùng chọn nơi XUẤT file) — dùng
`<input type="file" webkitdirectory multiple>` (chuẩn Chromium, Electron renderer chạy
Chromium nên dùng thẳng được, KHÔNG cần thêm IPC), đúng tinh thần tái dùng 2 tiền lệ
`<input type="file" multiple>` đã có (Asset Vault raw video upload, Visual Studio "Nhiều
video nền") thay vì tự dựng hạ tầng mới.

### Backend

`render.py::upload_shot_visual` (mục 42, upload 1 shot thủ công) tách phần lõi thành 2
hàm dùng chung: `_match_ext_for_shot(shot, filename, content_type)` (validate loại ảnh/
video khớp `shot.visual_type`, tái dùng 4 map `_..._EXT_BY_...` có sẵn) và
`_upload_shot_visual_core(pdir, status, shot_id, ext, data)` (ghi file + cập nhật
`ShotRenderStatus`, KHÔNG tự `save_render_state` — để batch dồn nhiều shot vào 1 lượt
ghi thay vì ghi lại `render.json` mỗi file). Endpoint đơn giữ NGUYÊN hành vi cũ 100%
(chỉ gọi lại 2 hàm trên).

Endpoint mới `POST /projects/{id}/render/shots/upload-visual-batch` (`files:
list[UploadFile]`): `_require_not_in_progress` 1 LẦN (không phải mỗi file) — với mỗi
file, lấy `Path(filename).stem` làm `shot_id`, không tìm thấy shot → `unmatched` kèm lý
do; tìm thấy nhưng sai loại (đuôi không khớp `shot.visual_type`, KHÔNG tự đổi
`visual_type` — đúng nguyên tắc endpoint đơn) → cũng `unmatched` kèm lý do; hợp lệ → gọi
`_upload_shot_visual_core`, thêm vào `matched`. Ghi đè shot ĐÃ `ready` nếu trùng tên
(reset `approved=False`) — nhất quán hành vi endpoint đơn, không thêm cờ "chỉ điền chỗ
trống" (không được yêu cầu). Trả `{matched: [{shot_id, filename}], unmatched:
[{filename, reason}], state}` — kèm `state` để frontend cập nhật ngay không cần gọi lại
`GET .../render/status`.

### Frontend

`VisualStudio.tsx` — thêm mục "Upload ảnh/video từ folder (theo mã block)" vào
`OverflowMenu` ("⋯ Tuỳ chọn khác", cạnh "Tự động điền từ Kho tài nguyên") — trigger 1
`<input type="file" webkitdirectory multiple>` ẩn. Sau khi chọn folder:
`api.uploadShotVisualBatch` → cập nhật `renderState` từ `result.state` + bump cache-bust
ảnh/video cho MỌI shot trong `matched` (để `<img>`/`<video>` refresh ngay, không cần
reload trang) → mở popup `ShotUploadBatchModal` (mới, cùng khung `.dialog-backdrop`/
`.dialog` như `VaultAutoFillModal` có sẵn — nhưng CHỈ báo cáo, không có bước "chọn rồi
áp dụng" vì upload đã xong khi popup mở): dòng tóm tắt "Đã khớp + upload N file, M file
chưa khớp" + danh sách file chưa khớp kèm lý do.

### Test

3 test mới `test_render.py`: `test_upload_shot_visual_batch_matches_by_filename_and_reports_unmatched`
(4 file: khớp ảnh đúng loại, khớp video đúng loại, tên không khớp shot nào, khớp tên
nhưng sai loại — xác nhận CẢ 2 nhóm `matched`/`unmatched` đúng, lý do đúng, shot không có
file khớp giữ nguyên "pending"), `test_upload_shot_visual_batch_overwrites_already_ready_shot`
(ghi đè shot đã có ảnh AI, `approved` reset về `False`), `test_upload_shot_visual_batch_rejected_while_in_progress`
(409 khi đang có BackgroundTasks sinh asset chạy). Bug thật gặp lúc viết test: quên
decorator `@respx.mock` ở 1 test gọi `_mock_asset_apis()` → HTTP mock không active →
provider call thật ra ngoài thất bại âm thầm → shot không bao giờ "ready" →
`StopIteration` khi tra shot — sửa bằng cách thêm lại decorator, đúng pattern mọi test
khác trong file đã dùng.

Full `pytest` **834 passed** (831 mục 146 + 3 mới). `tsc --noEmit` sạch.

## 148. Xoá watermark — nút riêng cho ảnh Gemini + phát hiện đa-frame cho video (2026-09-18)

Từ 1 cuộc trao đổi kỹ thuật về cách xoá watermark hiện tại (`app/watermark/`), người
dùng chỉ ra 2 vấn đề đáng sửa: (1) nút "Xoá watermark" cho ẢNH luôn áp cứng vị trí góc
Gemini/Nano Banana (`gemini_corner_bbox`) mà KHÔNG kiểm tra ảnh có thật sự từ Gemini
không — đề xuất tách 1 nút riêng; (2) phát hiện watermark VIDEO chỉ dựa 1 frame Florence-
2 duy nhất, đề xuất so khớp NHIỀU frame để tìm vùng pixel bất biến (watermark không di
chuyển, nội dung thật luôn đổi) — đáng tin hơn hẳn 1 model đoán semantic trên 1 frame.

### Phần 1 — Gate provider + nút "Xoá watermark Gemini" riêng

Xác nhận đúng nghi vấn: `engine.py::_remove_watermark_for_status` gọi
`remove_watermark_from_image` cho MỌI shot ảnh, không phân biệt `status.visual_provider`
— ảnh sinh bằng OpenAI/Flux/Midjourney hoặc upload tay bấm nhầm nút này sẽ bị LaMa vá 1
vùng góc dưới-phải không hề có watermark.

Fix: `routers/render.py::remove_shot_watermark` thêm query param `mode: "auto"|"gemini"`
(mặc định `"auto"`) — với ẢNH, `mode="auto"` CHỈ chạy nếu `visual_provider == "gemini"`,
ngược lại trả 400 rõ ràng NGAY (không mở BackgroundTasks); `mode="gemini"` (nút MỚI "Xoá
watermark Gemini", chỉ hiện cho shot ẢNH) ép chạy bất kể provider — dùng khi người dùng
chắc chắn ảnh có watermark Gemini nhưng metadata thiếu/sai (VD ảnh cũ tạo trước khi field
này được lưu). Video KHÔNG bị gate (tự định vị theo nội dung, không phụ thuộc provider).
`engine.py::remove_all_shots_watermark` (nút "cả block") áp CÙNG gate nhưng bỏ qua THẦM
LẶNG (không tính vào `scanned`) thay vì lỗi, đúng nguyên tắc "lỗi 1 phần không chặn cả
batch". Logic xoá ảnh Gemini (`remove_watermark_from_image`/`gemini_corner_bbox`) GIỮ
NGUYÊN 100% — chỉ gate ở tầng router/vòng lặp bulk.

### Phần 2 — Phát hiện video qua độ lệch chuẩn theo thời gian (nhiều frame)

Hàm mới `detector.py::detect_static_watermark_bbox(frame_paths, sample_count=16)` — lấy
mẫu N frame rải đều (đã tách sẵn ra JPG bởi `remove_watermark_from_video`, không cần
decode thêm), đọc grayscale, tính `std_map = stack.std(axis=0)` (độ lệch chuẩn theo THỜI
GIAN của từng pixel) — vùng pixel "tĩnh" (percentile thấp) qua lọc diện tích/hình dạng
(tái dùng nguyên `_bbox_area_fraction`/`_bbox_has_plausible_shape` đã có, không phụ thuộc
Florence-2) rồi chọn vùng GẦN GÓC khung hình nhất (quy ước đặt watermark thực tế) bằng
`cv2.connectedComponentsWithStats`. KHÔNG cần model AI/dependency mới — `numpy`+`cv2`
(OpenCV) đã có sẵn qua `scenedetect[opencv]` trong `requirements.txt`.

`pipeline.py::remove_watermark_from_video` dùng hàm này làm phương pháp CHÍNH; không tìm
được vùng đủ tin cậy (VD cảnh quay quá tĩnh khiến cả khung hình đều "tĩnh") → rơi về
Florence-2 trên 1 frame đại diện như CŨ (lưới an toàn, GIỮ NGUYÊN khả năng đã có, không
bớt gì).

**Verify thật trước khi viết test** (đúng tinh thần đã làm cho Florence-2/LaMa trước đây)
— dựng frame tổng hợp bằng numpy (nền nhiễu + trôi dần mô phỏng nội dung luôn đổi, cộng 1
vùng cố định mô phỏng watermark) chạy thử trực tiếp: watermark ĐẶC (opaque) → bbox khớp
CHÍNH XÁC tuyệt đối; watermark BÁN TRONG SUỐT (alpha-blend 45% với nền đổi liên tục, mô
phỏng đúng kiểu icon Gemini) → VẪN phát hiện đúng (độ lệch chuẩn vùng đó thấp hơn hẳn phần
còn lại dù không tuyệt đối bằng 0); video KHÔNG watermark → đúng trả `None`. Cả 3 case đều
khớp kỳ vọng ngay từ lần chạy đầu.

### Test

Backend: 4 test unit thuần cho `detect_static_watermark_bbox` (opaque/bán trong suốt/
không có watermark/quá ít frame — tái hiện đúng 3 kịch bản đã verify tay ở trên,
`test_watermark.py`) — không cần GPU/model. 4 test router mới cho gate provider
(`test_render.py`): `mode="auto"` từ chối ảnh non-Gemini (400, không đụng asset), `mode=
"gemini"` ép chạy thành công, video không bị gate, bulk bỏ qua thầm lặng ảnh non-Gemini
(scanned chỉ tính video). Cập nhật 4 test cũ (3 test đơn lẻ thêm `?mode=gemini` để giữ
đúng ý định gốc — test luồng xoá, không phải test gate; 1 test bulk ép `visual_provider=
"gemini"` cho mọi shot trước khi chạy để không bị gate mới làm sai kỳ vọng `scanned`).

Full `pytest` **842 passed** (834 mục 147 + 8 mới). `tsc --noEmit` sạch.

## 149. Nút "Xoá watermark Gemini" mở rộng sang video + bulk — và bài học thật về so khớp mẫu (template matching) (2026-09-19)

Người dùng phản hồi mục 148: (1) nút riêng "Xoá watermark Gemini" chỉ hiện cho ẢNH, và dù
không gate provider ở router vẫn KHÔNG có nhánh xử lý riêng cho VIDEO (bấm vẫn chạy y hệt
luồng chung đa-frame/Florence-2) — đúng ý người dùng, bấm nút này LÀ xác nhận chủ động
"chắc chắn có watermark Gemini", nên phải áp dụng cho CẢ ảnh lẫn video, không cần biết
`visual_provider`; (2) cần thêm bản BULK xử lý cả ảnh+video không gate; (3) đề xuất lưu 1
ảnh mẫu watermark Gemini thật để so khớp (template matching) định vị chính xác hơn thay
vì luôn vá 1 vùng cố định.

### Verify thật — vì sao BỎ ý tưởng so khớp mẫu

Trước khi code, dùng `EnterPlanMode` nghiên cứu + verify TRỰC TIẾP (không suy đoán, đúng
văn hoá module `app/watermark/`). Người dùng cung cấp 1 ảnh mẫu icon Gemini thật (ngôi sao
4 cánh trắng, tải từ 1 nguồn công khai) — cắt gọn thành template 470×470px. Test
`cv2.matchTemplate` (cả `TM_CCOEFF_NORMED` trên pixel thô LẪN trên bản đồ cạnh Canny, đa
tỉ lệ) trên **frame THẬT trích từ `B01.mp4`** của 1 project thật của người dùng (nền giấy
cũ có chữ Hán/Việt dày đặc): cả 2 cách so khớp đều cho điểm "tự tin" (0.49-0.59) nhưng
bbox trả về SAI — khớp nhầm vào hoạ tiết giấy/nét chữ thay vì icon sparkle thật (xác nhận
bằng mắt qua crop trực tiếp vùng bbox trả về). Thử thu hẹp vùng tìm kiếm về sát
`gemini_corner_bbox` hiện có VẪN sai. Nguyên nhân giống hệt lý do Florence-2 thất bại
trước đây (bug #4 `detector.py`): nền chi tiết có tương phản CAO HƠN hẳn icon mờ bán
trong suốt, khiến bất kỳ phép so khớp dựa trên tương phản/cạnh nào cũng bị hoạ tiết nền
"cướp" mất tín hiệu đúng.

Tin tốt từ chính lần verify này: đo trực tiếp vị trí icon THẬT trên frame đó xác nhận nó
nằm GỌN trong `gemini_corner_bbox` đã có (hàm cũ, verify từ bug #4/#5) — hàm này vẫn đáng
tin cho CẢ video, không cần thuật toán mới rủi ro. **Quyết định: bỏ hẳn ý tưởng template
matching, tái dùng `gemini_corner_bbox` cho video khi user xác nhận Gemini** — bài học ghi
lại ở đây để không ai lặp lại hướng đã thử-và-sai này.

### Thay đổi

`watermark/pipeline.py::remove_watermark_from_video` — thêm `force_gemini: bool = False`.
`True` → dùng THẲNG `gemini_corner_bbox(sample_image.size)` (bỏ qua đa-frame/Florence-2
hoàn toàn — user đã xác nhận Gemini nên không cần lớp phát hiện nội dung tổng quát).
`False` (mặc định) → giữ NGUYÊN hành vi cũ (đa-frame → Florence-2).

`render/engine.py`: `_remove_watermark_for_status`/`remove_shot_watermark`/
`remove_all_shots_watermark` đều nhận thêm `mode: str = "auto"`, truyền
`force_gemini=(mode=="gemini")` xuống video. `remove_all_shots_watermark`'s điều kiện bỏ
qua ảnh non-Gemini (mục 148) giờ CHỈ áp dụng khi `mode=="auto"` — `mode=="gemini"` xử lý
MỌI shot ready, không bỏ qua gì.

`routers/render.py`: `remove_shot_watermark` — sửa 1 chỗ THIẾU thật (đã viết gate ở mục
148 nhưng QUÊN truyền `mode` xuống `background_tasks.add_task`, khiến video không bao giờ
nhận được tín hiệu "gemini" dù gate đã đúng). `remove_all_shots_watermark` — thêm `mode`
param mới.

Frontend (`VisualStudio.tsx`, `client.ts`): bỏ điều kiện `shot.visual_type === "image"` ở
nút "Xoá watermark Gemini" — hiện cho MỌI shot ready (ảnh lẫn video). Thêm mục
`OverflowMenu` mới "Xoá watermark Gemini toàn bộ slot" (`mode="gemini"`) cạnh "Xoá
watermark toàn bộ slot" cũ (`mode="auto"`, không đổi). `removeAllShotsWatermark`/
`removeShotWatermark` (client.ts) nhận thêm tham số `mode`.

### Test

2 test mới `test_render.py`: `test_remove_shot_watermark_gemini_mode_uses_corner_bbox_for_video`
(spy `force_gemini` truyền đúng `True`/`False` theo mode), `test_remove_all_shots_watermark_gemini_mode_processes_all_shots_no_gate`
(bulk mode="gemini" xử lý MỌI shot, `scanned` = tổng số shot, không bỏ qua ảnh non-
Gemini). Cập nhật chữ ký 4 hàm giả (`_fake_wm_video_*`, `_dispatch_video`) thêm tham số
`force_gemini` để khớp chữ ký thật mới, không phá vỡ test cũ.

Full `pytest` **844 passed** (842 mục 148 + 2 mới). `tsc --noEmit` sạch.

## 150. Bug thật (tiếp mục 149): xoá watermark Gemini cho video báo lỗi "cannot access local variable 'bboxes'" (2026-09-19)

Người dùng báo lỗi thật khi bấm "Xoá watermark Gemini" cho shot B01 (video): "Xoá
watermark thất bại: cannot access local variable 'bboxes' where it is not associated with
a value". Root cause ở chính đoạn vừa sửa mục 149:
`watermark/pipeline.py::remove_watermark_from_video` kết thúc bằng `return bboxes`, nhưng
biến `bboxes` (số nhiều) CHỈ được gán bên trong nhánh dự phòng Florence-2 — 2 nhánh còn
lại (`force_gemini=True` dùng `gemini_corner_bbox`, hoặc `detect_static_watermark_bbox`
thành công ngay từ đầu, mục 148) chỉ gán biến `bbox` (số ít), không hề đụng tới `bboxes` —
`UnboundLocalError` xảy ra ngay khi 1 trong 2 nhánh phổ biến hơn đó chạy (thực ra lỗi này
đã tồn tại từ mục 148, chỉ chưa lộ ra vì mọi test trước đó đều gián tiếp đi qua nhánh
Florence-2 dự phòng — video test tổng hợp màu đặc luôn bị `detect_static_watermark_bbox`
từ chối vì "cả khung hình đều tĩnh", rơi về đúng nhánh có gán `bboxes`).

Fix: đổi `return bboxes` → `return [bbox]` (biến LUÔN có giá trị ở mọi nhánh, kiểu trả về
`list[tuple[int,int,int,int]]` không đổi — trước đây Florence-2 dự phòng cũng chỉ dùng
`bboxes[0]` để vá nên gói `bbox` vào 1 list là tương đương).

Thêm 1 test hồi quy `test_watermark.py::test_remove_watermark_from_video_force_gemini_uses_corner_bbox`
— gọi THẬT `remove_watermark_from_video(force_gemini=True)` (không mock
`detect_static_watermark_bbox`/`gemini_corner_bbox`, chỉ mock bước vá LaMa) để bắt lại
đúng lớp lỗi này nếu tái diễn — trước đây KHÔNG có test nào gọi hàm thật với
`force_gemini=True` hay để `detect_static_watermark_bbox` thành công không qua fallback,
nên lỗi lọt qua toàn bộ suite mục 148/149.

Full `pytest` **845 passed** (844 mục 149 + 1 mới). `tsc --noEmit` sạch (không đổi
frontend).

## 151. Bug thật (tiếp mục 150): xoá watermark Gemini xong nhưng preview video vẫn hiện watermark cũ (2026-09-19)

Người dùng báo tiếp: lỗi ở mục 150 đã hết, nhưng chạy xong "Xoá watermark Gemini" cho
shot B01 (video) thì preview trong Visual Studio VẪN hiện watermark. Điều tra trực tiếp
trên file THẬT (`B01_nowm.mp4` trên đĩa, không qua UI) — trích frame ở nhiều mốc thời gian
khác nhau (đầu/25%/50%/75%/cuối video) so với vị trí `gemini_corner_bbox` đã tính, xác
nhận **file trên đĩa ĐÃ được xoá watermark đúng và sạch** (crop trước/sau đặt cạnh nhau:
watermark biến mất hoàn toàn, LaMa vá liền mạch). Vậy backend làm đúng — bug nằm ở
FRONTEND không hiển thị lại file mới.

Root cause: `VisualStudio.tsx::removeShotWatermark` — MỌI hành động khác thay asset của 1
shot (`uploadVisualAsset`, `regenVisualAsset`, `assignVaultClip`) đều gọi
`bumpShotCacheBust(shotId)` để ép `<video>`/`<img>` refetch (vì `visual_asset_path` đổi
TÊN file — `B01.mp4` → `B01_nowm.mp4` — nhưng URL preview cố định theo `shot_id`, chỉ dựa
vào query string cache-bust để biết cần tải lại). Riêng `removeShotWatermark` (xây từ mục
96/97, và bản mở rộng "Xoá watermark Gemini" mục 148/149) **BỊ SÓT** lời gọi này từ đầu —
file trên đĩa đổi đúng, nhưng trình duyệt tiếp tục phát video đã cache CŨ vô thời hạn.
`removeAllShotsWatermark` (nút "cả block") có CÙNG lỗi — vòng lặp poll tới khi
`watermark_scan_summary.finished_at` đổi nhưng không bump cache-bust cho shot nào.

Fix: cả 2 hàm đều bump cache-bust — nhưng bump SAU KHI xác nhận xong (poll `loadRenderStatus`/
`finished_at`), KHÔNG bump ngay sau khi POST trả về (như các hàm khác đang làm) — vì
endpoint watermark chạy qua BackgroundTasks, file mới chỉ tồn tại SAU khi nền hoàn tất;
bump quá sớm sẽ khiến trình duyệt fetch lại NGAY nhưng vẫn nhận đúng file CŨ (do backend
chưa kịp đổi `visual_asset_path`) rồi cache luôn kết quả sai đó, cần đợi qua đợt bump nữa
mới đúng — dễ gây ảo giác "đã sửa nhưng vẫn sai" lần nữa. `removeAllShotsWatermark` bump
cho MỌI shot trong response cuối (đơn giản hơn tính đúng shot nào vừa "cleaned").

**Không cần test tự động** — đây là lỗi hiển thị UI thuần (cache-busting), không có hành
vi backend nào để unit test; đã verify bằng cách đọc trực tiếp file nhị phân trên đĩa
(không suy đoán qua log/status).

`tsc --noEmit` sạch. Không đổi backend — giữ nguyên **845 passed** từ mục 150.

## 152. Kéo thả sắp xếp lại thứ tự kênh/dự án trên Sidebar (2026-09-19)

Theo yêu cầu người dùng: "Cho phép kéo thả để sắp xếp lại thứ tự dự án/kênh trên
sidebar". Đây là tính năng HOÀN TOÀN MỚI — nghiên cứu xác nhận trước khi lên kế hoạch:
không có cột `order`/`position` nào trên `Channel`/`Project`, không `ORDER BY` nào ở
`GET /channels`/`GET /channels/{id}/projects` (phụ thuộc thứ tự vật lý SQLite, không phải
hợp đồng đảm bảo), không endpoint reorder nào cho bất kỳ entity nào trong app, và **không
có thư viện kéo thả nào** trong `frontend/package.json` (chỉ `react`/`react-dom`).

### Quyết định kiến trúc: HTML5 drag-and-drop THUẦN, không thêm dependency

Danh sách chỉ là 1 cột dọc đơn giản (không cần kéo giữa nhiều cột/lưới phức tạp), Electron
chạy Chromium nên HTML5 DnD (`draggable`/`onDragStart`/`onDragOver`/`onDrop`) hoạt động đầy
đủ — chọn cách này thay vì thêm `dnd-kit`/`react-beautiful-dnd`, giữ đúng tinh thần "không
thêm dependency khi không cần" (frontend hiện chỉ có đúng 2 gói).

### Backend — cột `order_index` mới + migration backfill

`models.py`: `Channel.order_index`/`Project.order_index` (`Column(Integer, default=0)`).
`app/order_migration.py` (mới, cùng idiom `youtube_migration.py`/`asset_vault/migration.py::
_add_missing_columns`) — ALTER TABLE ADD COLUMN idempotent, **backfill CHỈ chạy đúng 1
lần** (khi cột VỪA được thêm) theo `created_at` TĂNG DẦN, giữ nguyên thứ tự người dùng
đang thấy — lượt chạy SAU (cột đã tồn tại) KHÔNG backfill lại, tránh ghi đè thứ tự người
dùng đã tự kéo thả sắp xếp. Gọi từ `main.py` cạnh 2 migration hiện có.

`routers/channels.py`: `list_channels` thêm `.order_by(Channel.order_index)`;
`create_channel` gán `order_index` = max hiện có + 1 (kênh mới xuất hiện CUỐI, khớp hành
vi mặc định hiện tại — không có optimistic chèn đầu nào ở `ChannelDialog`); endpoint mới
`PATCH /channels/reorder` (`{channel_ids: [...]}`, gán `order_index` = vị trí trong danh
sách gửi lên, 404 nếu ID lạ).

`routers/projects.py`: `list_projects` thêm `.order_by(Project.order_index)`;
`create_project` gán `order_index` = min hiện có TRONG CÙNG NHÓM ANH EM (cùng
`channel_id` + `parent_project_id`) - 1 (project mới xuất hiện ĐẦU nhóm) — **khớp ĐÚNG lại**
hành vi optimistic đã có sẵn ở `Sidebar.tsx::handleNewProject` (chèn project mới lên đầu
local state, nhưng TRƯỚC ĐÂY không hề persist nên F5/mở lại kênh sẽ nhảy xuống cuối — sửa
lần này không phải hành vi mới, chỉ làm nó thật sự bền vững). Endpoint mới `PATCH
/channels/{channel_id}/projects/reorder` — dùng CHUNG cho cả sắp xếp project long-form
LẪN short-form con của 1 project (frontend tự gửi đúng danh sách ID của 1 nhóm mỗi lần
gọi, backend không cần biết/validate nhóm nào vì hiển thị luôn lọc theo nhóm TRƯỚC khi sắp
theo `order_index`).

### Frontend

`client.ts`: `reorderChannels`/`reorderProjects`. `AppContext.tsx`: action
`reorderChannels(orderedIds)` — optimistic sắp lại `channels` local rồi gọi API, lỗi thì
`refreshChannels()` refetch lại đúng trạng thái server.

`Sidebar.tsx` — 3 danh sách kéo thả ĐỘC LẬP (kênh, project long-form trong 1 kênh, short-
form con của 1 project), mỗi danh sách 1 "scope" riêng (`"channels"`, `` `projects:${chId}` ``,
`` `shorts:${parentId}` ``) để `onDrop` chỉ xử lý khi kéo/thả CÙNG scope, tránh kéo nhầm
giữa các nhóm khác nhau (VD thả 1 kênh vào danh sách project). CẢ ROW draggable (không cần
tay cầm kéo riêng — sidebar chỉ rộng 240px, không tốn thêm không gian; hành vi click điều
hướng hiện có không bị ảnh hưởng vì HTML5 drag chỉ kích hoạt sau khi chuột di chuyển đủ xa
lúc nhấn giữ). Chỉ báo thị giác nhẹ khi kéo qua 1 row (viền trên + mờ item đang kéo), không
animation phức tạp.

### Test

10 test mới: `test_order_migration.py` (backfill đúng thứ tự `created_at` — KHÔNG phải thứ
tự INSERT vật lý, idempotent không ghi đè thứ tự đã tự sắp, bỏ qua thầm lặng DB chưa có
bảng); `test_channels.py` (kênh mới xuất hiện cuối, reorder persist đúng, 404 ID lạ);
`test_projects_brief.py` (project mới xuất hiện đầu nhóm, reorder persist đúng, 404 khi
trộn ID khác kênh); `test_short_form_projects.py` (short-form mới chèn đầu ĐÚNG nhóm anh
em của riêng nó, không lẫn thứ tự long-form). Full `pytest` **855 passed** (845 mục 151 +
10 mới). `tsc --noEmit` sạch. Không có test tự động cho tương tác kéo thả UI (chưa có
frontend test runner nào thiết lập trong repo) — verify thủ công qua dev server.

## 153. Bug thật: Đồng bộ chỉ số YouTube lỗi HTTP 400 "Unknown identifier (impressions)" (2026-09-19)

Người dùng báo lỗi thật khi lần đầu bấm "Đồng bộ chỉ số YouTube" cho kênh "Người kể sử"
(lần đầu tiên tính năng mục 143 được dùng với OAuth Client Google thật):

```
Lỗi gọi API YouTube (HTTP 400): <HttpError 400 when requesting
https://youtubeanalytics.googleapis.com/v2/reports?...&metrics=views%2C
averageViewPercentage%2CaverageViewDuration%2Ccomments%2Cimpressions%2C
impressionClickThroughRate&dimensions=video&... returned "Unknown identifier
(impressions) given in field parameters.metrics.">
```

### Nguyên nhân gốc

Ở mục 143 (lúc chưa có OAuth Client thật để test), tên 2 metric `impressions` và
`impressionClickThroughRate` là suy đoán CHƯA VERIFY (đã ghi rõ trong comment code lúc đó
"CHƯA VERIFY bằng response THẬT"). Lần dùng thật đầu tiên này xác nhận: 2 metric đó KHÔNG
tồn tại trên YouTube Analytics API công khai.

**Verify thật** (không suy đoán) qua tài liệu chính thức Google:
- `developers.google.com/youtube/analytics/metrics` — danh sách đầy đủ metric hợp lệ chỉ
  có `annotationImpressions`, `annotationClickableImpressions`,
  `annotationClickThroughRate`, `cardImpressions`, `cardClickRate`,
  `cardTeaserImpressions`, `cardTeaserClickRate`, `adImpressions` (đổi tên từ `impressions`
  cũ, thuộc nhóm doanh thu quảng cáo, cần quyền `yt-analytics-monetary.readonly`), `cpm`,
  `totalSegmentImpressions` — KHÔNG có metric CTR/impression thumbnail nào.
- `developers.google.com/youtube/analytics/channel_reports` — không có report table nào
  kết hợp dimension/filter `video` với bất kỳ metric impression/CTR nào.
- 1 GitHub issue (PipedreamHQ/pipedream#20296) ban đầu tưởng là bằng chứng có metric
  `videoThumbnailImpressions`/`videoThumbnailImpressionsClickRate` — đọc kỹ lại thì đây là
  **feature request** xin Google BỔ SUNG các metric này, không phải xác nhận chúng đã tồn
  tại. Bài học: không tin ngay kết quả tóm tắt tự động của công cụ tra cứu, phải đọc lại
  nguồn gốc.

Kết luận: CTR thumbnail (mục tiêu 5-8% trong north-star ban đầu) **không thể tự động lấy
qua API công khai với bất kỳ tier tài khoản nào** trừ Content Owner/CMS + quyền doanh thu
— cùng nhóm với RPM và "Tỷ lệ Returning Viewers" đã xác định KHÔNG tự động hoá được ở mục
143/08_retention_guardrail.md.

### Fix

`backend/app/youtube_analytics.py::fetch_video_analytics` — bỏ `impressions,
impressionClickThroughRate` khỏi chuỗi `metrics=` gửi lên Google; hàm giờ chỉ trả về
`{views, avg_view_percentage, avg_view_duration_sec, comment_count}`. Docstring ghi rõ lý
do + nguồn verify để không ai vô tình thêm lại 2 metric sai này.

`backend/app/routers/youtube_analytics.py::sync_youtube_metrics` — bỏ tính `weighted_ctr`;
`YoutubeVideoMetricsSnapshot.impressions`/`impression_ctr` và
`YoutubeChannelMetricsSnapshot.avg_impression_ctr` giờ hardcode `None` (thay vì cố đọc từ
kết quả API), đúng pattern RPM/Returning-Viewers đã có — cột DB giữ nguyên (đã null-able
từ đầu), không cần migration.

`frontend/src/components/YoutubeMetricsPanel.tsx` — `MetricCard` thêm prop `note?: string`
tuỳ chọn (hiện thành tooltip `title` + dòng chữ nhỏ nghiêng dưới giá trị); card "CTR
thumbnail" gắn `note="YouTube không lộ chỉ số này qua API công khai — nhập tay ở Output
Center"` để người dùng hiểu ngay tại sao ô này luôn hiện "—" thay vì tưởng là bug.

`specs/02_database.md` + `specs/08_retention_guardrail.md` — cập nhật để không còn mô tả
CTR thumbnail/`impressions` như thể tự động lấy được; chuyển CTR thumbnail từ nhóm "Vận
hành (theo dõi)" sang nhóm "KHÔNG tự động hoá" cạnh RPM, ghi rõ đã verify thật (không còn
là "CHƯA verify" như lúc mục 143).

### Test

`backend/tests/test_youtube_analytics.py`: sửa test `test_sync_youtube_metrics_computes_
weighted_averages_and_saves_snapshots` (bỏ `impressions`/`impression_ctr` khỏi mock, thêm
assert các field này = `None`); thêm test mới
`test_fetch_video_analytics_does_not_request_nonexistent_impressions_metrics` — fake
`_build_analytics_client` để bắt CHÍNH XÁC chuỗi `metrics=` gửi lên Google, assert không
còn chứa `impressions`/`impressionClickThroughRate`, và kết quả trả về không còn 2 key đó
— khoá lại để không ai vô tình thêm nhầm lại các metric không tồn tại này. Full `pytest`
**856 passed** (855 mục 152 + 1 mới). `tsc --noEmit` sạch.

## 154. Kết nối YouTube RIÊNG cho từng kênh (thay vì 1 token dùng chung toàn app) (2026-09-19)

Người dùng nêu câu hỏi thật (không phải yêu cầu tính năng cụ thể, nhưng dẫn tới phát hiện
1 lỗ hổng thiết kế thật): "1 account có thể có nhiều kênh (gồm brand channel và các kênh
được share) — vậy làm sao gắn đúng kênh trên App với kênh của account Google đó?"

### Vấn đề đã xác nhận (đọc lại code, không suy đoán)

App (mục 143) chỉ lưu **1 token OAuth DÙNG CHUNG toàn app** (`AppSetting` key cố định
`"youtube_oauth"` — comment cũ ghi rõ "Phase 1 chỉ hỗ trợ 1 tài khoản Google"). Bấm "Kết
nối kênh này với YouTube" ở BẤT KỲ kênh StudioFlow nào cũng gọi `connect_channel_to_
youtube` → `load_credentials(db)` (đọc token CHUNG) → `channels.list(mine=true)` → lấy
`items[0]`. Nếu 2 kênh StudioFlow cùng bấm connect (cùng 1 tài khoản Google quản nhiều
kênh YouTube — brand channel/kênh được share), cả 2 sẽ nhận **CÙNG 1
`youtube_channel_id`** — sai hoàn toàn với tiền đề cốt lõi của app ("vận hành nhiều kênh
YouTube", CLAUDE.md).

**Verify THẬT** (không suy đoán) cơ chế đúng để phân biệt nhiều kênh: qua báo cáo thực tế
trên GitHub (`google/google-api-javascript-client#628` — người dùng khác xác nhận màn
hình đồng ý OAuth của Google TỰ hiện bộ chọn kênh/brand account khi tài khoản quản lý
nhiều kênh). Kết luận: cơ chế đúng là để MỖI kênh StudioFlow tự chạy 1 lượt OAuth RIÊNG
(chọn đúng kênh ở màn Google), lưu token RIÊNG cho kênh đó — chỉ có tác dụng nếu KHÔNG
dùng chung 1 token. Đã hỏi trực tiếp người dùng về đánh đổi (phải đăng nhập lại Google 1
lần cho MỖI kênh) — người dùng chấp nhận: "chỉ cần connect lần đầu tiên cho mỗi kênh thì
ko sao".

### Thiết kế

OAuth Client (`client_id`/`client_secret` — đăng ký Google Cloud project) **giữ nguyên
dùng chung toàn app** (chỉ là định danh của app, không phải danh tính người dùng). Token
truy cập (access/refresh) chuyển sang **RIÊNG theo từng kênh StudioFlow** — tái dùng bảng
`AppSetting` key-value sẵn có, đổi key cố định `"youtube_oauth"` thành
`f"youtube_oauth:{channel_id}"` — KHÔNG cần bảng/cột mới.

`backend/app/youtube_analytics.py`: `save_credentials`/`load_credentials`/`is_connected`
thêm tham số `channel_id`; thêm `delete_credentials(db, channel_id)` (dùng khi disconnect
— trước đây CỐ Ý không xoá token vì "dùng chung cho kênh khác", giờ không còn đúng).
`build_authorize_url` thêm tham số `state` — truyền `channel_id` vào
`flow.authorization_url(..., state=state)`; Google echo lại nguyên văn ở callback qua
query `state`, nhờ đó callback biết CHÍNH XÁC token vừa nhận thuộc kênh nào, không cần
bảng tạm lưu state↔channel_id. Đã verify qua đọc trực tiếp source
`google_auth_oauthlib/flow.py` (cài trong `.venv`): `authorization_url(**kwargs)` truyền
thẳng `state` xuống `oauth2session.authorization_url`; `fetch_token(code=code)` (cách đổi
code lấy token hiện tại) KHÔNG đọc lại `state` từ Flow — dùng Flow MỚI cho bước đổi code
(như code cũ đã làm) vẫn an toàn.

`backend/app/routers/youtube_analytics.py`: endpoint mới `GET /channels/{channel_id}/
youtube/authorize-url` (thay `GET /settings/youtube/authorize-url` cũ) và `GET /channels/
{channel_id}/youtube/oauth-status` (thay việc đọc `connected` từ `/settings/youtube/
status` — giờ chỉ còn `{has_oauth_client}`, không còn ý nghĩa ở cấp toàn app).
`GET /oauth/callback` đọc thêm `state` — nếu thiếu/không khớp kênh tồn tại → HTML lỗi rõ
ràng; nếu hợp lệ → lưu token riêng cho kênh đó **VÀ gán luôn `Channel.youtube_channel_id/
title/connected_at` ngay tại đây** (gộp việc mà `POST /channels/{id}/youtube/connect` cũ
làm — endpoint đó **bị xoá hẳn**, không còn ý nghĩa vì lúc này đã biết chắc `channel_id`
từ `state`). `POST /channels/{id}/youtube/disconnect` giờ gọi thêm `delete_credentials`.

**Migration dữ liệu nhẹ** (không đổi schema, chỉ copy data) — `youtube_migration.py::
migrate_youtube_token_to_per_channel`: nếu còn token CHUNG cũ và có kênh ĐÃ kết nối
(`youtube_channel_id` không rỗng) nhưng CHƯA có token riêng — copy token cũ sang cho kênh
đó, để người dùng ("Người kể sử", mục 153) không bị bắt làm lại OAuth ngay sau bản sửa
này. Idempotent tự nhiên (chỉ copy khi key riêng CHƯA tồn tại). Gọi từ `main.py` (cần mở
1 `SessionLocal()` vì đây là data migration, không phải schema như 2 migration ALTER
TABLE hiện có).

`frontend/src/screens/settings/YoutubeSettings.tsx`: bỏ hẳn khối "Bước 2 — Kết nối tài
khoản Google" (nút connect + polling toàn cục) — chỉ còn "Bước 1 — OAuth Client", hướng
người dùng sang Dashboard → từng kênh để kết nối. `frontend/src/components/
YoutubeMetricsPanel.tsx::connect()` viết lại — chuyển toàn bộ logic mở trình duyệt +
poll (trước đây ở `YoutubeSettings.connect()`) vào đây, dùng endpoint theo kênh mới; khi
poll thấy `connected: true` → gọi `onChannelUpdated()` (Channel lúc này đã được gán
`youtube_channel_id`/`title` ngay trong callback backend).

### Test

`backend/tests/test_youtube_analytics.py`: cập nhật toàn bộ test khớp chữ ký hàm mới
(`load_credentials(db, channel_id)` v.v.); sửa các test OAuth sang endpoint theo kênh,
thêm `_connect_channel()` helper mô phỏng ĐÚNG luồng OAuth per-channel thật (qua callback
với `state=channel_id`) dùng chung cho nhiều test; xoá 2 test của endpoint `POST /connect`
đã bị loại bỏ; thêm `test_oauth_callback_400_when_missing_or_invalid_state`; thêm
`test_migrate_youtube_token_to_per_channel_copies_legacy_token_once` (idempotent).
**Test cốt lõi** chứng minh đúng vấn đề người dùng nêu đã được sửa:
`test_two_channels_connect_to_different_youtube_channels_independently` — 2 kênh
StudioFlow tự OAuth riêng (`fetch_channel_info` mock trả 2 `youtube_channel_id` KHÁC
NHAU), assert cả 2 giữ đúng ID riêng, KHÔNG lẫn, và token lưu ở 2 dòng `AppSetting` TÁCH
BIỆT. Full `pytest` **858 passed** (856 mục 153 + 2 mới). `tsc --noEmit` sạch.

## 155. Provider ảnh local mới: Qwen-Image-2.1 qua ComfyUI (GGUF) (2026-09-24)

Người dùng hỏi "luồng tạo ảnh đang sử dụng mô hình gì" → "local đang chạy model nào" →
muốn dùng thêm model "Qwen Image", hỏi nên chọn bản nào phù hợp VRAM (RTX 5060 Ti, ~16GB,
verify thật qua `system_stats`) và cách triển khai.

### Quyết định đã chốt (hỏi trực tiếp người dùng qua nhiều vòng, có đổi ý)

1. **Chọn Qwen-Image-2.1** (Alibaba, 20/9/2026 — 7B tham số, nhẹ hơn hẳn bản gốc 20B,
   benchmark cao hơn 60.28 vs 49.23) thay vì bản gốc — đã báo rõ **license "Qwen
   Research" (CHỈ nghiên cứu, KHÔNG thương mại)**, khác bản gốc Apache 2.0. App đang vận
   hành kênh YouTube thật — người dùng tự quyết định chấp nhận rủi ro này.
2. Cân nhắc Nunchaku NVFP4 (tận dụng đúng kiến trúc Blackwell RTX 5060 Ti, nhanh hơn GGUF
   theo tài liệu) — người dùng CHỌN rồi **đổi ý loại bỏ** sau khi verify thật: MIT HAN Lab
   (tác giả gốc, `github.com/mit-han-lab/ComfyUI-nunchaku` — xác nhận qua đọc trực tiếp
   trang cài đặt, KHÁC các org "nunchaku-tech"/"nunchaku-ai"/"nunchux-ai" na ná dễ nhầm)
   CHƯA phát hành NVFP4 chính thức cho riêng 2.1. Bản cộng đồng (ModelsLab) yêu cầu
   `torch==2.12.1` (máy đang chạy `torch 2.8.0+cu129` — lệch 4 phiên bản) + không có wheel
   Windows dựng sẵn, phải build từ source — rủi ro cao ảnh hưởng Flux/SDXL/Wan đang chạy
   ổn. **Quyết định cuối: GGUF qua `ComfyUI-GGUF`** (đã cài sẵn, dùng cho `local_flux`) —
   an toàn cho môi trường hiện có.

### Trở ngại thật lúc verify — 2 bản ComfyUI khác nhau trên máy người dùng

`comfy-mcp`/`comfy-cli` mặc định quản lý 1 workspace RIÊNG (`Documents\comfy\ComfyUI`,
trống, không dùng) — KHÁC bản ComfyUI THẬT đang chạy (`C:\Tools\ComfyUI_extract\
ComfyUI_windows_portable`, tiến trình tên "python.exe" nên tìm "ComfyUI" trong Task
Manager không thấy). Mọi lệnh `update_comfyui`/`launch_comfyui`/`download_model` qua
comfy-mcp ban đầu đều nhắm NHẦM workspace — phát hiện qua `Get-NetTCPConnection`/
`Get-CimInstance Win32_Process` tìm đúng tiến trình giữ cổng 8188. Xử lý: người dùng tự
cập nhật ComfyUI core bằng đúng script của bản portable (`update\update_comfyui.bat`) +
khởi động lại bằng `run_nvidia_gpu.bat`; 3 file model tải bằng `curl` thẳng vào đúng thư
mục portable thay vì qua `download_model` (đã huỷ 3 lượt tải nhầm workspace trước khi tải
lại đúng chỗ, 0 byte lãng phí).

### Verify đồ thị workflow THẬT (không suy đoán) trước khi viết code provider

1. `TextEncodeQwenImage21` (node core cho 2.1) CHƯA có trong ComfyUI trước khi cập nhật
   core — đọc `object_info` thật SAU khi cập nhật xác nhận input thật: `clip`, `prompt`,
   `negative_prompt`, `resolution` (chỉ ảnh hưởng `latent` output CỦA CHÍNH NÓ, không dùng
   ở graph cuối), `images` (autogrow tối đa 16 ảnh — dành cho edit/multi-reference).
2. **Phát hiện quan trọng**: `comfy-cli validate_workflow` báo lỗi giả "`images` autogrow
   không có slot — server sẽ từ chối" khi bỏ trống — nhưng gọi THẲNG `POST /prompt` (bỏ
   qua lớp validate phía client) cho thấy ComfyUI thật CHẤP NHẬN job bình thường không cần
   `images`. Hạn chế đã biết của validator phía client cho nhóm autogrow, không phải giới
   hạn thật — quyết định KHÔNG truyền `images` trong provider.
3. Tải trực tiếp + đọc raw JSON workflow mẫu thật (`realrebelai/Qwen-Image-2.1_GGUFs`,
   file "QWEN IMAGE 2.1 T2I (Workflow).json") xác nhận `EmptyLatentImage` (core, RIÊNG,
   KHÔNG dùng `latent` output của `TextEncodeQwenImage21`) — cho phép kiểm soát tỷ lệ
   16:9/9:16 giống `local_sdxl`/`local_flux`. **Phát hiện thêm**: workflow mẫu này tham
   chiếu SAI tên file GGUF ("Qwen-Image-2.1-Q4_K_M-HQv3.gguf") — verify qua HuggingFace
   API (`api/models/{repo}`, liệt kê `siblings` thật) xác nhận tên THẬT chỉ là
   "Qwen-Image-2.1-Q4.gguf" — không tin mù tên file trong workflow tải về.
4. `KSampler` (`steps=25, cfg=1.0, sampler_name=euler, scheduler=simple, denoise=1.0`) —
   khớp CẢ 2 nguồn độc lập (template chính thức Comfy-Org + workflow mẫu thật) — `cfg=1.0`
   là ĐÚNG cho Qwen-Image-2.1 (không phải thiếu guidance).
5. **Chạy job THẬT qua GPU** (gọi thẳng `/prompt` → poll `/history`) — ra ảnh đúng (cáo
   trong tuyết, đúng prompt, đúng tỷ lệ 1344x768, ~68s/ảnh) — CHỈ SAU KHI có bằng chứng này
   mới viết code provider chính thức, đúng kỷ luật "verify thật" đã áp dụng cho Flux.

### File model đã tải (đặt đúng thư mục ComfyUI portable, không phải workspace comfy-cli)

`Qwen-Image-2.1-Q4.gguf` (5.96GB, `models/diffusion_models/`, cộng đồng
`realrebelai/Qwen-Image-2.1_GGUFs` — city96 chưa làm bản 2.1); `qwen3vl_8b_w4a8.safetensors`
(6.31GB, `models/text_encoders/`, CHÍNH THỨC `Comfy-Org/Qwen-Image-2.1`);
`qwen_image_2.1_vae_bf16.safetensors` (0.68GB, `models/vae/`, cùng repo Comfy-Org). Tổng
~13GB/16GB — dư nhiều hơn Flux hiện tại (~9.9GB) đang chạy ổn.

### Code

`backend/app/providers/image_comfy_qwen.py` (MỚI) — `ComfyQwenImageProvider`,
`provider_name="local_qwen"`, sao chép hạ tầng HTTP polling/`gpu_lock`/
`raise_if_interrupted`/`test_connection` từ `image_comfy_flux.py` (không đổi, cùng
ComfyUI), đồ thị workflow riêng theo đúng Bước verify ở trên. Không có LoRA/img2img/edit
ở đợt này (`reference_image` nhận cho đồng nhất chữ ký, không dùng).

`backend/app/providers/factory.py` — thêm `"local_qwen": ComfyQwenImageProvider` vào
`_IMAGE_ADAPTERS` (dùng chung nhánh `local_endpoint` với `local_flux`/`local_sdxl`, không
cần sửa `_build_asset_provider`).

`frontend/src/screens/settings/ProviderSettings.tsx` — thêm entry `local_qwen` vào
`LOCAL_CATALOG.image` (cạnh `local_flux`) với **cảnh báo license ngay tại UI** (không chỉ
lúc chat) + 2 nhánh `ComfyModelSelect kind="unet_gguf"` (dropdown chọn file GGUF thật từ
ComfyUI, tái dùng y hệt component có sẵn).

### Test

`backend/tests/test_image_comfy_qwen.py` (MỚI, 12 test, respx mock ComfyUI) — GGUF/CLIP/
VAE mặc định đúng, đổi được qua `model_name`, `CLIPLoader.type="qwen_image"`, KHÔNG gửi
`images` cho `TextEncodeQwenImage21` (khoá lại phát hiện ở mục "Verify" trên), KSampler
đúng tham số, `EmptyLatentImage` riêng biệt + đúng width/height theo aspect_ratio 16:9/
9:16, raise lỗi khi ComfyUI từ chối job/bị dừng, `test_connection` ok/lỗi. Full `pytest`
**870 passed** (858 mục 154 + 12 mới). `tsc --noEmit` sạch.

## 156. Xoá 5 provider local cũ (SDXL/Flux/Wan/LocalAI ảnh/LocalAI video) — chỉ giữ `local_qwen` (2026-09-24)

Sau khi build + test `local_qwen` (mục 155) và thấy tốc độ (giảm bước sampler xuống 15,
xem dưới) + chất lượng tốt hơn hẳn, người dùng nhận định chất lượng của TOÀN BỘ provider
local cũ (SDXL, Flux, Wan2.2, LocalAI ảnh, LocalAI video) đều kém — **quyết định xoá sạch**,
không giữ song song. Đã hỏi rõ 2 lần và xác nhận: (1) chấp nhận mất khả năng sinh **video
local hoàn toàn** (Wan là provider video local duy nhất, Qwen-Image-2.1 không sinh được
video — video giờ chỉ còn qua cloud: Runway/Sora/Veo/Flux); (2) xác nhận xoá LUÔN CẢ
`localai_image`/`localai_video` (không chỉ 3 cái ban đầu nêu) — vì logic của chúng đan xen
chung với SDXL/Wan trong `engine.py`, giữ lại nửa vời sẽ phức tạp hơn xoá sạch.

**Kết hợp thêm**: đổi mặc định số bước sampler của `local_qwen` từ 25 → **15** — verify
thật qua GPU (cùng seed/prompt "fox trong tuyết"): 41s/ảnh (so với ~68s ở 25 bước, nhanh
hơn ~40%), chất lượng không đổi thấy được bằng mắt.

### Entanglement phát hiện lúc research (Explore agent) — xử lý trước khi xoá file

`list_comfyui_models()` (hàm đọc danh sách checkpoint/LoRA/GGUF THẬT từ ComfyUI, dùng cho
dropdown "Model") nằm trong `image_comfy_sdxl.py` nhưng `local_qwen` CŨNG dùng chung hàm
này (dropdown `kind="unet_gguf"`) — đã CHUYỂN hàm này sang `image_comfy_qwen.py` TRƯỚC khi
xoá file SDXL, sửa lại import ở `routers/providers.py`.

### Backend — xoá file provider + gỡ đăng ký

Xoá hẳn 5 file: `image_comfy_sdxl.py`, `image_comfy_flux.py`, `video_comfy_wan.py`,
`image_localai.py`, `video_localai.py` (+ 5 file test tương ứng). `factory.py`: gỡ 5
import + 5 entry trong `_IMAGE_ADAPTERS`/`_VIDEO_ADAPTERS`.

`routers/providers.py`: đổi import `list_comfyui_models` sang `image_comfy_qwen`; đổi tên
endpoint `GET /providers/local-sdxl/models` → **`GET /providers/comfyui/models`** (tên cũ
gây hiểu nhầm khi SDXL không còn tồn tại — sửa cả backend lẫn frontend cùng lúc, app
single-user local không cần lo backward-compat API); xoá hẳn endpoint
`GET /providers/localai/models` (chỉ phục vụ `localai_image`/`localai_video`, nay chết).

`routers/pack.py`: gỡ entry `"local_sdxl"` khỏi `_IMAGE_COST_FN`, thay bằng `"local_qwen"`
(tiện thể sửa 1 bug thật phát hiện lúc dọn: `local_qwen` TRƯỚC ĐÓ hoàn toàn KHÔNG có mặt
trong `_IMAGE_COST_FN` của `engine.py`, khiến chi phí thumbnail sinh bằng `local_qwen` bị
tính nhầm rơi về fallback `estimate_openai_image_cost` — cùng lớp bug đã từng gặp với
`local_sdxl` trước đây, xem comment gốc trong file).

### Backend — dọn `render/engine.py` (surgery lớn nhất)

Vì CẢ 2 provider ảnh local (`local_sdxl`, `localai_image`) VÀ cả 2 provider video local
(`local_wan`, `localai_video`) đều bị xoá, toàn bộ khái niệm "local image/video provider
cần xử lý riêng" không còn ai dùng — xoá SẠCH: `_IMAGE_COST_FN`/`_VIDEO_COST_FN` (gỡ entry
+ import cũ), `_LOCAL_IMAGE_PROVIDER_NAMES`, `_LOCAL_FLUX_PROVIDER_NAMES`,
`_LOCAL_VIDEO_PROVIDER_NAMES`, `_LOCAL_SDXL_BRAND_STYLE_MAX_CHARS`,
`_LOCAL_SDXL_STYLE_PREFIX`, `_OTHER_BRACKET_TAG_RE`/`_VISUAL_TAG_RE`,
`_strip_text_overlay_tags()`, `_lora_trigger_words()`, `_build_video_motion_prompt()`,
`_local_sdxl_kwargs()`, `_local_flux_kwargs()`, `_try_generate_wan_anchor_image()` — cùng
import `re`/`gpu_lock` (không còn nơi nào dùng).

`_build_visual_prompt()`: xoá tham số `for_local_sdxl`/`lora_trigger_words` — chỉ còn
ĐÚNG 1 nhánh hành vi (câu văn tự nhiên) cho MỌI provider còn lại. GIỮ NGUYÊN
`character_reference_desc`/`cultural_lock_positive` (generic, không liên quan SDXL/Flux/
Wan). `generate_visual_asset()`: bỏ nhánh anchor Wan/motion-prompt cho video, bỏ lựa chọn
`extra_kwargs` theo provider — gọi `provider.generate(...)`/`provider.start_generation(...)`
PHẲNG cho mọi provider còn lại. Cùng surgery áp dụng cho bản sao logic trùng lặp phát hiện
thêm trong `render/short_export.py` (export short-form 9:16) — không có trong nghiên cứu
ban đầu của Explore agent, phát hiện qua lỗi `ModuleNotFoundError` khi chạy full `pytest`.

`cultural_lock_negative`: field này TRƯỚC ĐÂY chỉ được truyền thật cho 4 provider local
vừa xoá — sau khi xoá, **không còn được truyền cho bất kỳ provider nào nữa** (cloud chưa
từng nhận). QUYẾT ĐỊNH: giữ nguyên field/schema/UI (ngoài phạm vi yêu cầu) nhưng sửa
docstring ghi rõ "hiện chưa nối vào provider nào — để dành nối vào `local_qwen` sau nếu
cần (Qwen có `negative_prompt` thật, khác Flux)".

### Backend — schema

`schemas/__init__.py`: xoá class `StyleLoraEntry` (hết người dùng) + field
`BrandProfile.motion_tone`/`style_loras`/`flux_style_loras`.

### Backend — test

Xoá 5 file test tương ứng 5 provider. `test_render.py`: xoá NGUYÊN 2 khối test (~590
dòng tổng cộng — 1 test end-to-end `test_local_sdxl_generation_uses_style_loras_from_
brand_profile` phát hiện SAU đợt xoá lớn ban đầu, nằm TRƯỚC block chính) — an toàn xoá
TRỌN VẸN lần này (khác lúc research ban đầu còn phải cân nhắc giữ phần đụng
`localai_image`/`localai_video` vì lúc đó chưa xác nhận xoá luôn 2 cái này).
`test_providers.py`: SỬA (không xoá) 5 test `test_list_local_sdxl_*` → đổi tên bỏ "sdxl",
điều chỉnh theo endpoint `/providers/comfyui/models` mới. `test_channels.py`: sửa 2 test
`*_motion_tone_and_cultural_lock_negative` → bỏ phần `motion_tone` (field đã xoá), giữ
lại phần `cultural_lock_negative` (field vẫn tồn tại). `test_short_form_projects.py`: xoá
2 test workflow builder (`test_sdxl_workflow_builder_...`/`test_wan_workflow_builder_...`)
— tương đương đã có sẵn cho `local_qwen` ở `test_image_comfy_qwen.py`.
`test_pipeline_flow.py`/`test_short_video_export.py`: sửa 2 chỗ dùng tên provider cũ làm
giá trị fixture (không liên quan logic test) → đổi sang `local_qwen`.

### Frontend

`ProviderSettings.tsx`: xoá 5 entry trong `LOCAL_CATALOG.image`/`LOCAL_CATALOG.video` +
toàn bộ nhánh `ComfyModelSelect`/`LocalAIModelSelect` gắn với 5 provider_name này (2 chỗ
gọi — inline edit + dialog thêm mới); xoá hẳn component `LocalAIModelSelect` (không còn
nơi nào dùng); thêm thông báo "chưa có provider video local nào" khi mở tab Local cho
nhóm Video (mảng rỗng, tránh form trống khó hiểu). Đổi tên `api.listLocalSdxlModels` →
`api.listComfyUIModels`, xoá hẳn `api.listLocalAiModels` (dead).

`ChannelDialog.tsx`: xoá state/hydration/save-payload cho `motionTone`/`styleLoras`/
`fluxStyleLoras`; xoá 3 khối UI (ô "Tông chuyển động video AI local", 2 card "Style LoRA
cho ảnh local SDXL"/"Flux.1-dev"); sửa lại hint "Loại trừ văn hoá ngoại lai" (không còn
nhắc tên SDXL/Wan2.2 cụ thể, ghi rõ hiện chưa nối vào provider nào). `api/types.ts`: xoá
field tương ứng khỏi `BrandProfile` interface.

### Docs

`specs/05_ai_providers.md`: condense mục 8h/8i/8j (SDXL/Wan cải thiện chất lượng) +
8m (`local_flux`) thành ghi chú "ĐÃ XOÁ HOÀN TOÀN" ngắn gọn (giữ heading làm mốc lịch sử,
không renumbering); sửa mục 8k (chỉ phần cụ thể nhắc SDXL/Wan, giữ nguyên phần cơ chế
cultural lock chung); thêm **mục 8n MỚI** mô tả đầy đủ `local_qwen` (trước đó chỉ có
trong code comment + mục 155, chưa vào spec chính thức). `specs/03_api.md`: sửa mô tả
endpoint theo tên mới. `specs/04_data_schemas.md`: xoá mô tả `motion_tone`/`style_loras`/
`flux_style_loras`, sửa `cultural_lock_negative`. `specs/06_uiux.md`: các đoạn "Đã build"
lịch sử mô tả UI vừa xoá GIỮ NGUYÊN như lịch sử (không sửa changelog cũ, cùng cách đối xử
IMPLEMENTATION_REPORT.md).

### Test

Full `pytest` **774 passed** (giảm từ 870 — đúng bằng số test đã xoá/gộp, không có test
nào fail do đứt tham chiếu). `tsc --noEmit` sạch. Verify thủ công: `grep -rn` toàn bộ
`backend/app`/`frontend/src` xác nhận không còn tham chiếu chết nào tới 5 provider_name đã
xoá (chỉ còn comment lịch sử tường thuật quyết định).
