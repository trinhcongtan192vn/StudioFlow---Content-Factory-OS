# Implementation Report — StudioFlow M1 (MVP)

Ngày build: 2026-08-11. Nguồn thiết kế: Claude Design project "UI UX prototype cho PRD" (`StudioFlow Prototype.dc.html`, design system Nocturne). Nguồn nghiệp vụ: `CLAUDE.md` + `specs/*.md` + `specs/StudioFlow_PRD.md`.

Nguyên tắc thực thi theo đúng 4 yêu cầu đã nhận:
1. Build đúng design Nocturne — màu, spacing, component, layout port trực tiếp từ `styles.css` của design.
2. Khi design ≠ specs → ưu tiên design, cập nhật specs cho khớp thực tế (xem mục 2 và các file `specs/*.md` đã sửa).
3. Khi cần quyết định mà không có nguồn nào nói rõ → tự quyết định, ghi lại ở mục 3.
4. Model local (GPU) — code kiến trúc sẵn sàng, KHÔNG thực thi/test thật vì máy dev không có GPU (mục 5).

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

**Chưa cập nhật (ngoài phạm vi vòng này):** danh sách model TTS/Image/Video (`elevenlabs`, `vbee`, `flux`, `midjourney`, `runway`, `sora`) — các nhóm này chỉ khai báo interface, chưa dùng thật ở M1 (§05 mục 9), nên không research lại lần này; để làm khi bắt đầu M2 (render thật).

Verify: tạo 1 provider Claude qua API thật (không truyền `model_name`) → xác nhận `model_name` mặc định trả về là `claude-opus-5` (model đầu danh sách mới) và `available_models` đúng 4 model mới; dọn provider tạm sau khi test. Restart lại backend dev (8756) + Electron (backend con của Electron không tự nhận code mới vì chạy `uvicorn` không có `--reload`) để code mới thật sự có hiệu lực trên app đang chạy. Tổng vẫn **103 test, tất cả pass**, frontend typecheck sạch.

## 6. File specs đã cập nhật

`02_database.md`, `03_api.md`, `04_data_schemas.md`, `05_ai_providers.md`, `06_uiux.md`, `07_prompt_templates.md`, `09_sprint_tasks.md` — mỗi chỗ lệch đánh dấu bằng blockquote `> **Đã build...`, giữ nguyên nội dung gốc bên cạnh để thấy được ý định ban đầu vs. thực tế.
