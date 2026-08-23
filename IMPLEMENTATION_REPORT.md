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

## 6. File specs đã cập nhật

`01_architecture.md`, `02_database.md`, `03_api.md`, `04_data_schemas.md`, `05_ai_providers.md`, `06_uiux.md`, `07_prompt_templates.md`, `09_sprint_tasks.md` — mỗi chỗ lệch đánh dấu bằng blockquote `> **Đã build...`, giữ nguyên nội dung gốc bên cạnh để thấy được ý định ban đầu vs. thực tế.
