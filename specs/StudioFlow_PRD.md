# StudioFlow — Product Requirements Document

**Content Factory OS cho Media House đa kênh**
*Hệ điều hành sản xuất nội dung YouTube long-form bằng AI*

| | |
|---|---|
| **Phiên bản** | v1.5 — Final Draft |
| **Trạng thái** | For Review |
| **Ngày phát hành** | 10/08/2026 |
| **Chủ sở hữu** | Product Management |
| **Đối tượng đọc** | Eng, Design, Content Ops, Leadership |

---

## Mục lục

1. [Tổng quan sản phẩm](#1-tổng-quan-sản-phẩm)
2. [Người dùng & Personas](#2-người-dùng--personas)
3. [Kiến trúc khái niệm & Data Model](#3-kiến-trúc-khái-niệm--data-model)
4. [User Flow](#4-user-flow)
5. [Giao diện & UI/UX](#5-giao-diện--uiux)
6. [Màn hình Cấu hình & Quản trị (Admin)](#6-màn-hình-cấu-hình--quản-trị-admin)
7. [Yêu cầu chức năng theo module](#7-yêu-cầu-chức-năng-theo-module)
8. [Phân định Scope theo các mốc](#8-phân-định-scope-theo-các-mốc)
9. [Rủi ro, Guardrails & Yêu cầu phi chức năng](#9-rủi-ro-guardrails--yêu-cầu-phi-chức-năng)
10. [Quyết định thiết kế đã chốt](#10-quyết-định-thiết-kế-đã-chốt)

---

## 1. Tổng quan sản phẩm

### 1.1. Tóm tắt điều hành

StudioFlow là một hệ điều hành sản xuất nội dung (Content Factory OS) dành cho các media house vận hành nhiều kênh YouTube long-form tiếng Việt song song. Sản phẩm không tự nhận là công cụ "tạo video bằng AI" theo nghĩa một nút bấm sinh video; nó là dây chuyền sản xuất công nghiệp hoá, trong đó AI đảm nhận khối lượng tổng hợp và viết lách, còn con người giữ vai trò kiểm soát chất lượng và bản sắc tại các điểm chốt bắt buộc.

Giá trị lõi nằm ở Khối Sáng tạo & Kịch bản: biến brief kinh doanh và dữ liệu thô thành một **Production Pack** chuẩn hoá — tài sản trung tâm mà mọi khâu sản xuất downstream tiêu thụ. Khối Sản xuất (render, lồng tiếng, dựng) được xây như một lớp thực thi bám theo output của lõi, không phải một sản phẩm ngang hàng.

> **Một câu định vị:** StudioFlow giúp một media house sản xuất nội dung YouTube long-form ở quy mô nhiều kênh, nhanh gấp nhiều lần, mà không đánh mất bản sắc riêng của từng kênh và không rơi vào bẫy "AI slop".

### 1.2. Bối cảnh & Vấn đề

Với một media house đa kênh, nút thắt thực sự không phải "AI có viết được kịch bản hay không", mà là vận hành sản xuất ở quy mô lặp lại được, đồng nhất chất lượng, và giữ được DNA riêng của từng kênh. Ba nhóm vấn đề cụ thể:

- **Chi phí & nhân sự khối Sản xuất – Hậu kỳ:** đây là khối tốn nhân sự và ngân sách nhất (quay, âm thanh, editor, motion). Quy trình thủ công không scale khi số kênh tăng.
- **Hội chứng trang giấy trắng & tốc độ kịch bản:** biên kịch làm việc theo ngẫu hứng khiến sản lượng không ổn định, chất lượng phụ thuộc cá nhân, khó chuẩn hoá.
- **Đồng phục hoá & mất bản sắc:** khi tăng tốc bằng LLM thiếu kiểm soát, các kênh dễ nghe giống hệt nhau, generic, khiến retention tụt trên toàn bộ portfolio cùng lúc — rủi ro sống còn với media house.

### 1.3. Tầm nhìn & Mục tiêu

**Tầm nhìn:** trở thành lớp vận hành (operating layer) tiêu chuẩn cho các đơn vị sản xuất nội dung số đa kênh tại Việt Nam, nơi mỗi kênh vẫn giữ được giọng riêng trong khi toàn bộ dây chuyền được công nghiệp hoá.

| Mục tiêu | Chỉ số đo lường (định hướng) |
|---|---|
| Tăng sản lượng kịch bản đạt chuẩn | Số kịch bản qua human-gate / biên tập viên / ngày |
| Giữ chất lượng retention | Tỷ lệ video đạt hoặc vượt retention benchmark của kênh |
| Bảo toàn bản sắc kênh | Điểm brand-fit khi review; tỷ lệ kịch bản bị trả về vì lệch giọng |
| Rút ngắn brief → Production Pack | Thời gian trung bình mỗi Pack, so với thủ công |
| Giảm phụ thuộc hậu kỳ thủ công | Tỷ lệ shot được phục vụ bằng asset AI theo prompt chuẩn hoá |

### 1.4. Ngoài phạm vi (Non-Goals)

- Không phải công cụ chỉnh sửa video chuyên nghiệp thay thế Premiere/DaVinci; render in-app chỉ nhắm output "đủ tốt để đăng".
- Không phải mạng xã hội, CMS đăng bài, hay công cụ quản lý cộng đồng.
- Không phải công cụ cho creator cá nhân bán đại trà theo mô hình self-serve SaaS.
- Không tự động xuất bản end-to-end không có con người: mọi luồng đều có human-gate bắt buộc.

---

## 2. Người dùng & Personas

StudioFlow là công cụ nội bộ **single-user** — hiện chỉ một người vận hành, kiêm cả hai vai trò. Điều này bỏ nhu cầu phân quyền nhiều người (RBAC), nhưng ranh giới **hai loại công việc** vẫn giữ nguyên vì chúng khác nhau về bản chất và về màn hình:

- **Việc Business (vận hành nội dung):** làm hằng ngày trên dây chuyền sản xuất — brief, kịch bản, duyệt, output. Ưu tiên tốc độ và tính lặp lại.
- **Việc Admin (quản trị hệ thống):** thiết lập nền tảng để dây chuyền chạy trơn — cấu hình chung, kết nối provider AI, giám sát chi phí. Truy cập ít thường xuyên nhưng quyết định độ ổn định và ngân sách.

Các "persona" dưới đây vì thế là các **chế độ làm việc** của cùng một người, không phải người dùng riêng biệt:

| Chế độ | Loại việc | Nhu cầu chính |
|---|---|---|
| Định hướng | Business | Thiết lập Content Pillars, brand voice, retention benchmark cho từng kênh. |
| Lập kế hoạch | Business | Tạo brief chuẩn hoá, phân bổ theo ma trận nội dung, quản lý hàng đợi. |
| Biên kịch (human-gate) | Business | Chọn góc nhìn, biên tập Hook & storytelling; duyệt/trả về kịch bản AI. |
| Vận hành sản xuất | Business | Chạy sinh asset theo prompt, ghép Pack, kích hoạt render. |
| Quản trị nền tảng | Admin | Kết nối & thử API provider AI, cấu hình chung, prompt templates, audit log. |
| Giám sát chi phí | Admin | Theo dõi chi phí API theo kênh/Project, đặt cảnh báo ngân sách. |

### 2.1. Câu chuyện người dùng cốt lõi

- **Là Editorial Lead,** tôi muốn tạo brief từ template chuẩn hoá theo kênh, để biên kịch có đủ 4 nhóm input mà không cần họp lại.
- **Là Scriptwriter,** tôi muốn AI đề xuất dàn ý và các biến thể Hook theo đúng giọng kênh, để tôi tập trung chọn góc nhìn thay vì viết từ đầu.
- **Là Content Director,** tôi muốn hệ thống cảnh báo khi kịch bản lệch giọng kênh hoặc yếu về cấu trúc retention, để chất lượng portfolio không bị bào mòn khi tăng sản lượng.
- **Là AI Operator,** tôi muốn xuất Production Pack đầy đủ prompt để sinh toàn bộ asset mà không phải tự nghĩ câu lệnh cho từng shot.
- **Ở chế độ Admin,** tôi muốn cấu hình và test kết nối các provider AI ở một nơi tập trung, tách khỏi màn hình sản xuất, để khi đang viết nội dung không phải bận tâm tới API key hay model.
- **Ở chế độ Admin,** tôi muốn đặt hạn mức chi phí theo kênh và nhận cảnh báo khi sắp vượt, để ngân sách sản xuất không bị đội lên ngoài kiểm soát.

---

## 3. Kiến trúc khái niệm & Data Model

Toàn bộ sản phẩm xoay quanh một nguyên tắc: **Production Pack là artifact trung tâm.** Mọi khâu downstream chỉ đọc từ một schema chuẩn hoá, cho phép thay nhà cung cấp AI mà không phá vỡ quy trình, và version-control được từng lần chỉnh sửa.

### 3.1. Phân cấp thực thể

Multi-channel là công dân hạng nhất — không phải tính năng gắn thêm.

```
Organization
 └── Channel  (mang một BrandProfile)
      └── Project  (một video)
           └── ProductionPack
```

- **BrandProfile** = giọng văn, cấm kỵ, content pillars, style prompt visual, format hook ưa dùng, retention benchmark — được inject vào mọi agent AI.

### 3.2. Cấu trúc Production Pack

| Thành phần | Nội dung | Tiêu thụ bởi |
|---|---|---|
| Master Production Script | Kịch bản đa cột theo timeline (Âm thanh — Hình ảnh — Chỉ dẫn): Hook 3–5s, Body chia timestamp với emotional anchor mỗi 30–45s, CTA. | Narration/TTS, Editor |
| Shot List & AI Prompts | Danh sách shot; mỗi shot mang loại asset + prompt AI chuẩn hoá (Midjourney/Flux/Runway/TTS). | AI Operator, Render |
| Title & Thumbnail Concepts | 5–10 biến thể tiêu đề (SEO + CTR); mô tả concept thumbnail. | Growth, Thumbnail Designer |
| Repurposing Pack | Đánh dấu đoạn đắt giá cho short-form; nội dung Community Post/poll. | Distribution (mốc sau) |

> **Nguyên tắc thiết kế:** Downstream chỉ đọc schema, không đọc "file Word". Đây là điều kiện để thay được nhà cung cấp AI (Flux → Sora) và version-control từng thay đổi mà không vỡ luồng.

### 3.3. BrandProfile — cơ chế bảo toàn bản sắc

Inject vào mọi agent, đảm bảo mỗi kênh "nghe" khác nhau. Tối thiểu gồm: brand voice & tông giọng; content pillars & tỷ trọng ma trận nội dung; danh sách cấm kỵ; style prompt visual; format Hook ưa dùng & retention benchmark riêng.

---

## 4. User Flow

Phần này mô tả hành trình người dùng end-to-end. Nguyên tắc xuyên suốt: hệ thống dẫn dắt tuyến tính theo dây chuyền, nhưng **dừng lại tại hai human-gate bắt buộc** — không có nút "generate all" chạy một mạch.

### 4.1. Flow chính: từ Brief đến Production Pack

```
① CHỌN KÊNH
   Người dùng chọn Channel → hệ thống tự nạp BrandProfile.
        ↓
② TẠO BRIEF (Editorial Lead)
   Điền template 4 nhóm input. Trường thiếu được đánh dấu, không chặn cứng.
        ↓
③ AI RESEARCH (tự động)
   Hệ thống tổng hợp tài liệu + đề xuất 2–3 dàn ý (đã inject BrandProfile).
        ↓
┌─────────────────────────────────────────────┐
│ ★ HUMAN GATE #1 — Scriptwriter               │
│   Chọn 1 góc nhìn/dàn ý. Chọn 1 trong 3 Hook  │
│   variant, chỉnh sửa trực tiếp. BẮT BUỘC.     │
└─────────────────────────────────────────────┘
        ↓
④ AI GENERATION (tự động)
   Viết kịch bản đa cột chi tiết + sinh prompt cho từng shot.
        ↓
⑤ RETENTION CHECK (tự động, nền)
   Đối chiếu cấu trúc với benchmark kênh. Gắn cảnh báo inline (không chặn).
        ↓
┌─────────────────────────────────────────────┐
│ ★ HUMAN GATE #2 — Scriptwriter/Editor        │
│   Duyệt toàn bộ Pack. Xử lý cảnh báo. BẮT BUỘC │
│   Chỉ khi Approve mới mở khoá Output.         │
└─────────────────────────────────────────────┘
        ↓
⑥ OUTPUT (AI Operator)
   Chọn: (A) Export Pack (spec+prompts)  và/hoặc  (B) Render in-app.
```

### 4.2. Flow phụ

- **Thiết lập kênh (Content Director, một lần/khi cần):** Tạo Channel → điền BrandProfile qua wizard nhiều bước → đặt retention benchmark → lưu phiên bản. Có thể clone BrandProfile từ kênh sẵn có để đỡ nhập lại.
- **Trả về & sửa (loop):** Tại bất kỳ gate nào, người duyệt có thể **Trả về** kèm ghi chú → Project quay lại bước trước đó, giữ nguyên lịch sử. Không tạo bản mới, chỉ tăng version.
- **Quản lý hàng đợi (Editorial mode — GA):** Bảng Kanban các Project theo trạng thái; kéo-thả để đổi trạng thái.
- **Nạp retention thủ công (MVP):** sau khi video đã đăng, người dùng mở Project → nhập số liệu retention thực tế vào form đơn giản → hệ thống đối chiếu với benchmark của kênh và hiển thị chênh lệch, làm dữ liệu tham khảo cho các kịch bản sau.

### 4.3. Nguyên tắc thao tác

- **Không mất việc:** mọi thay đổi auto-save theo version; đóng app không mất tiến độ.
- **Không dead-end:** mỗi màn hình luôn có hành động kế tiếp rõ ràng (nút primary) và đường lùi.
- **Gate không bypass được:** nút Output bị khoá (disabled + tooltip lý do) đến khi Gate #2 được Approve.

---

## 5. Giao diện & UI/UX

Mục tiêu UX: **thao tác mượt, giảm tải nhận thức, và làm cho các human-gate trở thành điểm nhấn tự nhiên chứ không phải rào cản.** Sản phẩm là công cụ vận hành hằng ngày của đội nội bộ, nên ưu tiên tốc độ và tính lặp lại hơn là hào nhoáng.

### 5.1. Bố cục tổng thể

Layout ba vùng cố định, quen thuộc như một IDE nội dung:

- **Sidebar trái (điều hướng):** cây `Channel → Project`; badge trạng thái màu trên mỗi Project (Draft / Chờ Gate #1 / Chờ Gate #2 / Sẵn sàng Output). Nút "＋ Project mới" luôn hiển thị. **Góc dưới có icon ⚙ dẫn vào khu Cài đặt/Quản trị** (chỉ hiện với vai trò được cấp — xem §6).
- **Vùng làm việc giữa (canvas):** nội dung theo bước hiện tại (brief form, editor kịch bản, bảng shot…). Đây là nơi người dùng dành 90% thời gian.
- **Panel phải (ngữ cảnh):** hiển thị BrandProfile đang áp dụng, cảnh báo retention, và lịch sử version. Thu gọn được để lấy không gian.

Trên cùng là **thanh tiến trình (stepper)** 6 bước của flow chính — luôn cho biết đang ở đâu và còn gì phía trước.

### 5.2. Mô tả từng màn hình chính

**① Dashboard kênh.** Lưới thẻ từng Channel: ảnh đại diện, số Project đang chạy, số chờ duyệt. Một cái nhìn biết ngay kênh nào đang tắc.

**② Brief Editor.** Form chia 4 khối gập/mở (4 nhóm input). Trường bắt buộc thiếu hiện chip "cần bổ sung" màu hổ phách thay vì báo lỗi đỏ gắt. Nút primary "Bắt đầu Research" sáng lên khi đủ input tối thiểu.

**③ Script Studio (màn hình xương sống).** Bố cục hai cột:
- Cột trái: **editor kịch bản đa cột** (Audio / Visual / Direction) cuộn theo timeline, có timestamp.
- Cột phải: **Hook Variants** — 3 thẻ đặt cạnh nhau, mỗi thẻ ghi rõ kiểu tâm lý (không có điểm số). Người dùng bấm chọn một thẻ; thẻ được chọn nổi bật, các thẻ kia mờ đi. Chọn xong có thể sửa trực tiếp.
- Cảnh báo retention hiện dạng **gạch chân + ghi chú lề** ngay tại đoạn có vấn đề (ví dụ "khoảng trống anchor > 45s"), bấm vào để xem gợi ý — không phải popup chặn luồng.

**④ Production Pack Review (Gate #2).** Chế độ xem tổng hợp cả 4 thành phần Pack dạng tab. Một dải trạng thái trên đầu liệt kê số cảnh báo chưa xử lý. Hai nút lớn: **Approve** (mở khoá Output) và **Trả về** (kèm ô ghi chú bắt buộc).

**⑤ Output Center.** Hai thẻ lựa chọn lớn: "Export Pack" và "Render in-app" (thẻ thứ hai hiện "Beta" ở M2). Sau khi chạy, hiển thị tiến độ và link tải.

**⑥ Retention Nhập tay.** Trong Project đã đăng, một form gọn nhập bốn nhóm số liệu (§10.4); sau khi lưu, hiển thị chênh lệch so với benchmark kênh dạng thanh so sánh trực quan — làm tham chiếu cho kịch bản sau, không phải báo cáo phức tạp.

### 5.3. Nguyên tắc tương tác (đảm bảo mượt)

- **Auto-save + version im lặng:** không có nút "Lưu"; thay đổi tự ghi, version tăng ở nền, xem lại được ở panel phải.
- **Streaming rõ ràng:** khi AI đang sinh nội dung, chữ hiện dần theo luồng kèm nút "Dừng" — người dùng không phải nhìn spinner mù.
- **Phím tắt cho người dùng nặng:** `Cmd/Ctrl+Enter` để chạy bước kế; `Cmd/Ctrl+↵` tại gate để Approve; điều hướng shot bằng phím mũi tên.
- **Optimistic UI:** thao tác chọn Hook/duyệt phản hồi tức thì, đồng bộ nền — không chờ round-trip.
- **Trạng thái rỗng có hướng dẫn:** màn hình chưa có dữ liệu luôn kèm một câu chỉ dẫn + nút hành động, không để trống trơn.
- **Cảnh báo phân cấp màu:** hổ phách = gợi ý (bỏ qua được), đỏ = chạm cấm kỵ brand (nên xử lý). Không lạm dụng đỏ.

---

## 6. Màn hình Cấu hình & Quản trị (Admin)

Việc admin tách khỏi luồng sản xuất, sống trong một khu vực **Cài đặt** riêng, vào bằng **icon bánh răng (⚙)** ở góc dưới sidebar trái. Nguyên tắc: khi đang vận hành nội dung thì không phải thấy API key hay cấu hình hệ thống; khi vào chế độ admin thì không phải lội qua màn hình sản xuất. Vì sản phẩm là single-user nên không có phân quyền nhiều người — khu Cài đặt chỉ đơn giản là một không gian tách biệt để "vào phòng máy".

### 6.1. Điều hướng khu Cài đặt

Khu Cài đặt dùng **sidebar phụ dạng icon + nhãn**, mỗi mục một biểu tượng rõ nghĩa để nhận diện nhanh:

| Icon | Mục | Chức năng |
|---|---|---|
| ⚙ | **Cấu hình chung** | Tên tổ chức, ngôn ngữ mặc định, múi giờ, định dạng export mặc định, quy ước đặt tên Project. |
| 🔌 | **Provider AI** | Kết nối/quản lý nhà cung cấp (LLM, TTS, ảnh, video); nhập & che API key; chọn model mặc định cho từng tác vụ; **nút Test kết nối**; fallback provider. |
| 💳 | **Chi phí & Ngân sách** | Dashboard chi phí API theo kênh/Project/provider; đặt hạn mức & ngưỡng cảnh báo; xuất báo cáo. |
| 🎚 | **Tham số AI mặc định** | Đặt mặc định temperature, độ dài, số Hook variant, framework ưu tiên ở cấp hệ thống (kênh có thể override). |
| 🧩 | **Prompt Templates** | Thư viện prompt hệ thống cho từng loại asset; phiên bản hoá; đặt template mặc định. |
| 📜 | **Audit Log** | Nhật ký thao tác quan trọng: đổi provider, sửa hạn mức, thay đổi cấu hình — để tự truy vết khi có sự cố. |
| 🎨 | **Thương hiệu ứng dụng** | Logo, màu chủ đạo của workspace nội bộ (không phải BrandProfile của kênh). |

> **Phân biệt quan trọng:** *Tham số AI mặc định (🎚)* và *Prompt Templates (🧩)* là mặc định **cấp hệ thống** do admin đặt; còn *BrandProfile* (§3.3) là cấu hình **cấp kênh** do Content Director đặt và có quyền override. Ranh giới này tránh việc hai tuyến giẫm chân nhau.

### 6.2. Màn hình Provider AI — mô tả chi tiết

Đây là màn hình admin quan trọng nhất vì nó nuôi toàn bộ pipeline:

- **Danh sách provider** dạng thẻ, nhóm theo loại tác vụ (LLM / TTS / Image / Video). Mỗi nhóm hiển thị **nhiều thẻ provider có thể thêm song song** (ví dụ LLM: Claude, Gemini, OpenAI, và các model local), mỗi thẻ hiện: tên provider, loại kết nối (Cloud API / Local Endpoint), trạng thái kết nối (chấm xanh/đỏ), model đang chọn, và nút **Test** chạy một call thử. Một nhóm có thể có nhiều thẻ "đang bật" cùng lúc — người dùng chọn provider mặc định cho từng tác vụ qua dropdown riêng, không giới hạn chỉ một provider mỗi nhóm.
- **Thêm provider mới:** nút "+ Thêm provider" trong mỗi nhóm; với LLM có thêm lựa chọn loại kết nối — chọn `Cloud API` (nhập API key) hoặc `Local Endpoint` (nhập URL + tên model, dùng cho Qwen/DeepSeek/Kimi hay model local khác).
- **API key được che** (`sk-••••1234`), chỉ hiện khi bấm con mắt; lưu mã hoá, không bao giờ trả về client dạng thô. Local Endpoint không cần key, chỉ cần URL khả dụng.
- **Chọn model mặc định** cho từng tác vụ qua dropdown (danh sách gộp cả model cloud và model local đã cấu hình); đổi model có ghi vào Audit Log.
- **Fallback:** cho phép đặt provider dự phòng khi provider chính lỗi — phục vụ yêu cầu phi chức năng "thay thế provider mà không sửa lõi".
- **Trạng thái rỗng:** khi chưa cấu hình provider nào, hệ thống hiện cảnh báo rõ ràng và chặn tuyến business chạy AI (kèm thông báo "Cần cấu hình Provider AI"), thay vì để lỗi khó hiểu giữa luồng.

### 6.3. Nguyên tắc UX cho tuyến admin

- **Tách biệt trực quan:** khu Cài đặt có nền/khung khác với vùng sản xuất, để luôn biết mình đang ở "phòng máy" chứ không phải dây chuyền.
- **Thay đổi có hệ quả phải xác nhận:** đổi provider, hạ hạn mức đều qua modal xác nhận + ghi Audit Log.
- **An toàn mặc định:** thao tác phá huỷ (xoá key) tách khỏi thao tác thường, không đặt cạnh nút lưu.
- **Icon nhất quán:** mỗi mục cài đặt gắn một icon cố định, dùng lại đúng icon đó ở mọi nơi tham chiếu tới mục (breadcrumb, cảnh báo, log) để người dùng học một lần dùng mãi.

---

## 7. Yêu cầu chức năng theo module

**M1 — Channel & Brand Management.** Tạo/quản lý Organization & nhiều Channel; cấu hình BrandProfile đầy đủ, phiên bản hoá; thiết lập retention benchmark theo kênh.

**M2 — Brief & Intake.** Template brief bắt 4 nhóm input; gắn brief vào Channel để kế thừa BrandProfile; xác định điểm chuyển đổi (Affiliate / khóa học / Private Traffic) ngay từ brief.

**M3 — Script Studio (lõi giá trị).** AI Research + lập dàn ý (inject BrandProfile); **Human Gate #1 bắt buộc** (chọn góc nhìn, chỉnh Hook trước khi viết chi tiết, không bypass); sinh kịch bản đa cột; **Hook Variants** (3 kiểu tâm lý, không chấm điểm); ép framework (AIDA/PAS) + cài emotional anchor định kỳ.

**M4 — Retention Guardrail.** Đối chiếu cấu trúc với benchmark kênh (mật độ anchor, độ mạnh Hook, độ dài Body); cảnh báo (không chặn); brand-fit check khi lệch giọng hoặc chạm cấm kỵ.

**M5 — Production Pack Assembly & Prompt Builder.** Sinh Shot List, mỗi shot gắn prompt chuẩn hoá theo style của kênh; sinh Title/Thumbnail Concepts; **Human Gate #2 bắt buộc** duyệt trước export/render.

**M6 — Dual Output.**
- *Output A — Export Pack:* xuất spec + prompts (bản máy đọc + bản người đọc). **Bắt buộc, có sớm nhất.**
- *Output B — In-app Render:* sinh asset qua API, ghép & xuất MP4 "đủ đăng". **Thứ hai, module tách riêng, phát triển độc lập với script core.**

**M7 — Admin & Configuration.** Khu Cài đặt (§6): cấu hình chung, quản lý Provider AI (key, model, test, fallback), Chi phí & Ngân sách, Tham số AI mặc định, Prompt Templates, Audit Log, Thương hiệu ứng dụng. Vì single-user nên **không có phân quyền RBAC**. Toàn bộ khu Cài đặt nằm trong MVP (xem §8) — sản phẩm chỉ có một người dùng nên cấu hình đầy đủ ngay từ đầu vừa khả thi vừa cần thiết để tự vận hành.

---

## 8. Phân định Scope theo các mốc

Nguyên tắc phân mốc: ưu tiên số 1 là **chất lượng kịch bản/retention**, do đó lõi Script Studio đi trước; in-app render và các tính năng cần dữ liệu tích lũy đẩy về sau. Module render tách khỏi script để phát triển độc lập, tránh coupling khiến render kéo lùi lõi.

### 8.1. Bảng phân mốc tổng thể

| Mốc | Chủ đề | Đầu ra | Ranh giới scope |
|---|---|---|---|
| **M0** | Foundation | Data model Channel/BrandProfile/ProductionPack; khung ứng dụng; khung khu Cài đặt. | Chỉ hạ tầng; chưa có tính năng người dùng hoàn chỉnh. |
| **M1 (MVP)** | Script Core + Pack Export + Admin đầy đủ | Lõi tạo kịch bản đạt chuẩn retention theo kênh; xuất Pack (spec+prompts); **toàn bộ khu Cài đặt admin**. | **KHÔNG** render in-app, repurposing, correlation tự động. |
| **M2 (Beta)** | Production Layer | In-app render (dual output đầy đủ) + sinh asset qua API. | Render "đủ đăng", chưa tối ưu chất lượng điện ảnh. |
| **M3 (GA)** | Scale & Repurpose | Repurposing Pack; hàng đợi đa kênh; vận hành quy mô. | Chưa tối ưu dựa trên dữ liệu hiệu suất thực. |
| **M4 (Post-GA)** | Intelligence Loop | Content performance correlation; tinh chỉnh gợi ý. | Cần dữ liệu tích lũy từ nhiều video đã xuất bản. |

### 8.2. M1 — MVP (Trọng tâm: chất lượng retention)

MVP cắt phạm vi tới đúng thứ tạo ra retention. Lý do đẩy render ra khỏi MVP: in-app render là khối kỹ thuật nặng, nhiều edge case, và **không cải thiện chất lượng kịch bản chút nào** — mọi giờ công dồn vào render là giờ công lấy khỏi lõi giá trị.

**Trong phạm vi:**
- Channel & BrandProfile (thiếu nó thì multi-channel vô nghĩa).
- Brief intake chuẩn hoá 4 nhóm input.
- Pipeline Storytelling → Beat Sheet → Narration với Human Gate #1.
- Hook Variants (3 kiểu tâm lý, không chấm điểm).
- Retention Guardrail cơ bản (cấu trúc + brand-fit, dạng cảnh báo).
- Production Pack Assembly + Prompt Builder + Human Gate #2.
- Output A — Export Production Pack.
- **UI business:** Dashboard kênh, Brief Editor, Script Studio, Pack Review, Output Center (chỉ Export). Auto-save/version, streaming, phím tắt.
- **UI admin (đầy đủ):** toàn bộ khu Cài đặt §6 — Cấu hình chung (⚙), Provider AI (🔌), Chi phí & Ngân sách (💳), Tham số AI mặc định (🎚), Prompt Templates (🧩), Audit Log (📜), Thương hiệu ứng dụng (🎨). Không RBAC.
- **Retention: nạp thủ công.** Người dùng tự nhập số liệu retention thực tế của video đã đăng vào một form đơn giản để đối chiếu với benchmark — chưa tích hợp API tự động.

**Ngoài phạm vi MVP (đẩy về sau):**
- In-app MP4 render → M2.
- Repurposing Pack (short-form + Community Post) → M3.
- Content performance correlation **tự động** → M4. MVP chỉ có nạp thủ công (đối chiếu số nhập tay với benchmark); phần correlation tự động và tinh chỉnh gợi ý dựa trên dữ liệu tích lũy để sau.

> **Tiêu chí lọc scope MVP:** với mỗi hạng mục, hỏi đúng một câu — *"Nó có phục vụ trực tiếp chất lượng kịch bản/retention cho MVP không?"* Nếu không → chuyển sang mốc sau.

### 8.3. M2 — Beta (Production Layer)

Bổ sung Output B (in-app render): sinh asset qua API (TTS, ảnh, video giới hạn số shot), ghép & xuất MP4. Ranh giới: "đủ tốt để đăng", không grading chuyên nghiệp; giữ module render tách biệt khỏi script core; human review chất lượng asset trước khi ghép. Chi phí render mới phát sinh được theo dõi qua màn Chi phí & Ngân sách (💳) đã có sẵn từ MVP.

### 8.4. M3 — GA (Scale & Repurpose)

Repurposing Pack (đánh dấu đoạn short-form; sinh Community Post/poll); hàng đợi sản xuất đa kênh dạng Kanban; vận hành nhiều kênh song song với báo cáo tiến độ.

### 8.5. M4 — Post-GA (Intelligence Loop)

Nâng cấp từ nạp thủ công (đã có ở MVP) lên **correlation tự động**: tích hợp nguồn dữ liệu (ví dụ YouTube Analytics) để nạp retention thực tế thay vì nhập tay, đối chiếu benchmark, và tinh chỉnh gợi ý Hook/cấu trúc dựa trên dữ liệu tích lũy. Điều kiện kích hoạt: đủ khối lượng video xuất bản để dữ liệu có ý nghĩa thống kê.

---

## 9. Rủi ro, Guardrails & Yêu cầu phi chức năng

### 9.1. Rủi ro lớn nhất: "AI slop ở quy mô"

Sản xuất nhanh gấp nhiều lần nhưng ra nội dung đồng phục, generic, retention tụt — ăn mòn toàn bộ portfolio kênh cùng lúc. Ba cơ chế phòng, đưa thẳng vào spec:

| Cơ chế | Vai trò | Mốc |
|---|---|---|
| BrandProfile đủ mạnh | Mỗi kênh nghe khác nhau; inject vào mọi agent. | M1 |
| Human-gate bắt buộc | Không cho bypass ở điểm chọn góc nhìn & duyệt Pack. | M1 |
| Retention benchmark check | Biến "chất lượng" thành thứ đo được; cảnh báo khi lệch. | M1 |

### 9.2. Rủi ro dự án & xử lý

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| Dual output làm cùng lúc | Render kéo lùi tiến độ lõi | Tách module; Export ở M1, render sang M2. |
| Correlation build sớm | Lãng phí công, tính năng vô dụng | Đẩy sang M4 khi có dữ liệu thật. |
| Phụ thuộc provider AI | Đứt gãy khi đổi API/giá | Pack là schema chuẩn; provider là lớp thay thế được. |
| Chất lượng asset không đều | Video kém phát hành | Human review asset trước khi ghép (M2). |

### 9.3. Yêu cầu phi chức năng

- **Bảo mật thông tin nhạy cảm:** API key mã hoá at-rest, che khi hiển thị, không trả về client dạng thô.
- **Truy vết:** thao tác admin quan trọng ghi Audit Log (làm gì, khi nào) để tự truy vết khi có sự cố.
- **Thay thế provider:** hoán đổi nhà cung cấp AI (ảnh/video/TTS/LLM) mà không sửa lõi.
- **Version control:** mọi ProductionPack và BrandProfile phiên bản hoá, truy vết được.
- **Quản lý chi phí API:** theo dõi chi phí sinh asset theo kênh/Project.
- **Tách biệt dữ liệu** giữa các kênh trong cùng Organization.
- **Hiệu năng UX:** thao tác gate/chọn phản hồi < 100ms (optimistic); streaming AI bắt đầu hiện chữ < 2s.

---

## 10. Quyết định thiết kế đã chốt

Phần này chốt các điểm trước đây còn để mở, để PRD đủ điều kiện chuyển thẳng sang implementation. Mọi quyết định bám hai nguyên tắc: **ưu tiên chất lượng retention** và **tối giản cho bối cảnh single-user** (không over-engineer).

### 10.1. Schema chuẩn của ProductionPack & BrandProfile

Chốt định dạng **JSON** làm nguồn sự thật máy-đọc; bản người-đọc (Markdown/PDF) được sinh ra từ JSON, không phải ngược lại. Lý do: JSON version-control dễ, cho phép downstream và các provider thay thế nhau mà không vỡ luồng (§3.2).

**BrandProfile** (cấp kênh, inject vào mọi agent):

```json
{
  "channel_id": "ch_finance_01",
  "brand_voice": {
    "tone": "chuyên gia, gần gũi, không giáo điều",
    "formality": "trung tính",
    "pacing": "nhanh, câu ngắn",
    "sample_lines": ["...", "..."]
  },
  "content_pillars": [
    { "name": "Kiến thức nền", "weight": 0.7 },
    { "name": "Theo trend", "weight": 0.1 },
    { "name": "Khuyến mãi", "weight": 0.1 },
    { "name": "Tức thời", "weight": 0.1 }
  ],
  "forbidden": ["cam kết lợi nhuận", "từ ngữ giật gân X, Y"],
  "visual_style_prompt": "minimal, tông xanh–trắng, biểu đồ sạch",
  "hook_formats_preferred": ["câu hỏi gây sốc", "con số phản trực giác"],
  "retention_benchmark": {
    "target_hook_strength": 0.7,
    "max_anchor_gap_sec": 45,
    "target_body_len_min": 8
  },
  "version": 3
}
```

**ProductionPack** (cấp video, artifact trung tâm):

```json
{
  "project_id": "prj_2026_0142",
  "channel_id": "ch_finance_01",
  "brandprofile_version": 3,
  "status": "approved",
  "script": {
    "hook": { "spoken": "...", "visual": "...", "duration_sec": 4 },
    "body": [
      { "timestamp_sec": 5, "audio": "...", "visual": "...",
        "direction": "...", "anchor": true }
    ],
    "cta": { "spoken": "...", "conversion_point": "zalo_group" }
  },
  "shots": [
    { "shot_id": "s01", "asset_type": "broll_image",
      "provider": "flux", "prompt": "...", "linked_timestamp_sec": 5 }
  ],
  "titles": [ { "text": "...", "seo_score_hint": "...", "angle": "curiosity" } ],
  "thumbnail_concepts": [ { "metaphor": "...", "text_overlay": "...", "layout": "..." } ],
  "repurpose": { "shortform_marks": [], "community_post": null },
  "retention_check": { "hook_strength": 0.72, "max_anchor_gap_sec": 38, "warnings": [] },
  "version": 5
}
```

Nguyên tắc schema: các khối chưa thuộc mốc hiện tại (ví dụ `repurpose`) vẫn có mặt trong schema nhưng để `null` — tránh phải đổi schema khi mở mốc sau.

### 10.2. Bộ provider AI & ngưỡng chi phí

Vì Provider AI (🔌) đã thiết kế để **thay thế được**, danh sách dưới đây không phải một lựa chọn cố định mà là **danh mục** — mỗi tác vụ có nhiều provider được hỗ trợ sẵn, người dùng chọn provider + model mặc định trong màn Cấu hình, đổi bất kỳ lúc nào không sửa lõi.

| Tác vụ | Provider hỗ trợ | Mặc định đề xuất | Ghi chú |
|---|---|---|---|
| LLM (research + viết kịch bản) | Claude (Anthropic), Gemini (Google), OpenAI (GPT) | Claude | Lõi chất lượng — mặc định chọn provider mạnh nhất về tiếng Việt & viết dài tại thời điểm cấu hình, không cố định cứng theo tên. |
| TTS | Vbee, ElevenLabs, Gemini TTS | Vbee | Ưu tiên giọng Việt tự nhiên; Gemini TTS là lựa chọn thay thế khi cần đa ngôn ngữ. |
| Ảnh B-roll | Flux, Midjourney | Flux | Midjourney dùng khi cần chất lượng nghệ thuật cao hơn, chấp nhận chi phí/quy trình lâu hơn. |
| Video | Runway, Sora, Gemini (Veo) | Runway | Cả ba đều tốn kém — luôn giới hạn số shot/video theo cấu hình ở M2. |

**Ngưỡng chi phí:** đặt hạn mức mềm theo Project ở màn Chi phí & Ngân sách (💳); khi vượt ngưỡng, hệ thống cảnh báo (không chặn cứng) trước khi chạy bước sinh asset đắt tiền — đặc biệt video, vốn luôn là hạng mục tốn nhất. Cảnh báo để tự quyết, không cần luồng phê duyệt — đúng bối cảnh single-user.

### 10.2b. Model chạy local (Open-source)

Bổ sung một **loại kết nối thứ hai** cho LLM bên cạnh Cloud API: **Local Runtime** — trỏ tới một endpoint chạy tại máy/server riêng (kiểu Ollama/vLLM/LM Studio), phục vụ các model mã nguồn mở như **Qwen, DeepSeek, Kimi**.

- **Vì sao cần:** (1) chi phí bằng 0 cho các tác vụ chạy nhiều lần như AI Research/nháp dàn ý; (2) dữ liệu nhạy cảm (tài liệu nội bộ, ghi chú phỏng vấn) không rời máy; (3) không phụ thuộc uptime của bên thứ ba khi cần làm việc offline.
- **Cách cấu hình:** trong màn Provider AI, khi thêm một LLM, chọn loại kết nối `Cloud API` hoặc `Local Endpoint` (nhập URL + tên model, ví dụ `http://localhost:11434`, model `qwen2.5:32b`). Model local xuất hiện chung danh sách chọn với model cloud ở mọi nơi cần chọn LLM (AI Research, viết kịch bản, chấm Hook Strength).
- **Khuyến nghị dùng theo tác vụ:** model local phù hợp cho **AI Research** và **nháp dàn ý** (khối lượng lớn, chấp nhận chất lượng khá); vẫn khuyến nghị dùng model cloud mạnh nhất đã cấu hình cho bước **AI Generation kịch bản chi tiết sau Gate #1**, vì đây là nơi chất lượng ảnh hưởng trực tiếp retention — đúng ưu tiên số 1 của sản phẩm. Người dùng có thể override ở từng Project nếu muốn.
- **Giới hạn:** model local không áp dụng cho TTS/Ảnh/Video ở phạm vi PRD này — các tác vụ đó vẫn qua provider cloud tại §10.2.

### 10.3. Công thức đo cho Retention Guardrail

Chốt cách định lượng để guardrail (§ M4 module) đo được thay vì cảm tính. Hai chỉ số cốt lõi:

- **Hook Strength (0–1):** chấm bằng chính LLM theo rubric cố định — độ cụ thể, yếu tố tò mò/phản trực giác, độ liên quan tới pain point trong brief, độ dài ≤ ngưỡng. Cảnh báo khi thấp hơn `target_hook_strength` của kênh. (Lưu ý: đây là chấm điểm cho *guardrail cảnh báo*, khác với Hook Variants ở Gate #1 — variant vẫn **không** hiển thị điểm cho người dùng chọn, giữ đúng quyết định kiến trúc.)
- **Anchor Gap (giây):** khoảng cách lớn nhất giữa hai emotional anchor liên tiếp trong Body. Cảnh báo khi vượt `max_anchor_gap_sec` (mặc định 45s).

Bổ sung một cảnh báo cấu trúc: Body ngắn hơn `target_body_len_min` cũng gắn cờ. Tất cả đều là **cảnh báo phân cấp màu** (hổ phách/đỏ), không chặn luồng.

### 10.4. Form nạp retention thủ công (MVP)

Chốt bộ trường tối thiểu để đối chiếu có ý nghĩa mà không bắt nhập quá nhiều:

- **Retention tại các mốc %** của video: 0% (giữ chân sau Hook), 25%, 50%, 100% — bốn con số dễ đọc từ YouTube Studio.
- **Average View Duration** (giây hoặc %).
- **CTR của thumbnail** (%) — để đối chiếu với chất lượng Title/Thumbnail Concept.
- Ngày đăng (để sắp xếp theo thời gian).

Hệ thống lưu các số này vào Project, đối chiếu retention-tại-Hook với `target_hook_strength` và hiển thị chênh lệch như dữ liệu tham khảo cho kịch bản sau. Không tính toán phức tạp ở MVP — chỉ nhập, lưu, đối chiếu, hiển thị.

### 10.5. Lộ trình tự động hoá retention (M4)

Chốt hướng: M4 tích hợp **YouTube Analytics API** để tự kéo đúng bốn nhóm số liệu ở §10.4, thay thế bước nhập tay. Cùng dữ liệu, cùng cách đối chiếu — chỉ đổi nguồn nạp từ thủ công sang tự động, nên form thủ công ở MVP không bị lãng phí mà trở thành lớp fallback. Điều kiện kích hoạt giữ nguyên: đủ khối lượng video để dữ liệu có ý nghĩa.

### 10.6. Bước tiếp theo (implementation)

- Đóng băng JSON schema §10.1 làm hợp đồng dữ liệu giữa các module.
- Dựng wireframe cho màn hình chính (business §5 + khu Cài đặt §6).
- Phân rã M1 thành các sprint; ưu tiên thứ tự: data model → Provider AI → Script Studio → Retention Guardrail → Pack Export.
- Viết rubric chấm Hook Strength (§10.3) thành prompt cố định cho LLM.

---

*— Hết tài liệu PRD v1.5 —*
