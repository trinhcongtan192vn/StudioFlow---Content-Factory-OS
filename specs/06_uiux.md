# 06 — UI/UX

Mục tiêu: thao tác mượt, giảm tải nhận thức, biến 2 human-gate thành điểm nhấn tự nhiên chứ không phải rào cản. Công cụ vận hành hằng ngày → ưu tiên tốc độ và tính lặp lại.

## 1. Bố cục tổng thể (layout kiểu IDE)

Ba vùng cố định + stepper trên cùng:

> **Đã build — stepper thực tế 6 bước** (khác 7 bước ghi dưới đây), khớp
> `StudioFlow Prototype.dc.html`: **① Brief → ② Outline & Hook (Gate 1) → ③ Script
> Studio → ④ Visual Studio → ⑤ Pack Review (Gate 2) → ⑥ Output**. AI Research không
> có bước stepper riêng — chạy ngầm khi bấm "Bắt đầu Research" ở cuối bước ①, kết quả
> hiển thị gộp cùng Hook Variants ở bước ②. "Visual Studio" là bước MỚI so với đặc tả
> gốc — mỗi shot vừa sinh prompt hình/video vừa mô tả cảm xúc giọng đọc (TTS), tương
> tác trực tiếp thay vì chỉ xem trong Pack Review. Xem IMPLEMENTATION_REPORT.md.

```
┌───────────────────────────────────────────────┐
│  Stepper: ① Brief ② Research ③ Gate1 ④ Gen     │
│           ⑤ Check ⑥ Gate2 ⑦ Output             │
├──────────┬──────────────────────────┬──────────┤
│ Sidebar  │   Canvas (vùng làm việc) │  Panel   │
│ trái     │                          │  phải    │
│          │                          │  (ngữ    │
│ Channel  │                          │  cảnh)   │
│  └Project│                          │          │
│          │                          │ Brand    │
│ [+ mới]  │                          │ warnings │
│ ⚙ Cài đặt│                          │ version  │
└──────────┴──────────────────────────┴──────────┘
```

- **Sidebar trái:** cây `Channel → Project`; badge trạng thái màu theo enum (§02). Nút "+ Project mới" luôn hiện. Góc dưới **icon ⚙** dẫn vào khu Cài đặt (§ khu admin).
- **Canvas giữa:** nội dung theo bước hiện tại. 90% thời gian ở đây.
- **Panel phải:** BrandProfile đang áp dụng, cảnh báo retention, lịch sử version. Thu gọn được.

> **Đã build vòng 4 (2026-08-12) — header sticky:** cả 5 màn trong luồng project (①-⑤
> ở bảng dưới) đưa nút hành động chính lên **header dính đầu canvas** (tiêu đề + mô tả
> trái, nút phải, dính khi cuộn) thay vì đặt cuối trang như trước — đỡ phải cuộn xuống
> mới thao tác được với kịch bản/shot list dài. Dùng chung 1 component
> (`frontend/src/components/StepHeader.tsx`).

## 2. Màn hình nghiệp vụ (business)

| # | Màn hình | Nội dung chính |
|---|---|---|
| ① | **Dashboard kênh** | Lưới thẻ Channel: ảnh, số project đang chạy, số chờ duyệt. Thấy ngay kênh nào tắc. |
| ② | **Brief Editor** | Form 4 khối gập/mở (4 nhóm input §04). Trường thiếu → chip "cần bổ sung" màu hổ phách (không lỗi đỏ). Nút "Bắt đầu Research" sáng khi đủ input tối thiểu. |
| ③ | **Outline & Hook (Gate #1)** — **đã build, tách khỏi Script Studio** | Dàn ý AI Research (chọn 1) + **Hook Variants** (3 thẻ kiểu tâm lý, **không điểm số**) hiển thị CÙNG màn, chọn xong sửa trực tiếp hook. Duyệt → mới sinh Full Script. **Đã build vòng 4:** header có thêm nút "Nhập kịch bản từ file (CSV/Excel)" — đường tắt bỏ qua toàn bộ chọn outline/hook + AI viết Full Script, nhảy thẳng Script Studio với script đã có sẵn (xem `03_api.md` mục Script Import). Dialog xác nhận hiện số block/số từ/thời lượng ước tính trước khi ghi đè. |
| ④ | **Script Studio** (xương sống) | Trước duyệt: 1 cột Full Script liền mạch + ô góp ý "tạo lại". Sau duyệt & bóc tách: kịch bản đa cột theo timeline (Audio/Visual/Direction), 1 cột (đã build vòng 4: bỏ mini-panel Hook đang dùng — xem ghi chú dưới). Cảnh báo retention = **gạch chân + ghi chú lề** tại đoạn có vấn đề — không popup chặn. |
| ⑤ | **Visual Studio** — **đã build, màn mới** | 1 card/shot (= 1 beat script): Visual/FX + Audio/SFX cùng lúc (đã build vòng 4: đổi tên field, tách 2 nút "Tạo lại Visual"/"Tạo lại giọng đọc"), toggle Image⇄Video. Khớp nguyên tắc "shot chuẩn hoá" nhưng tương tác trực tiếp thay vì chỉ liệt kê trong Pack Review. |
| ⑥ | **Pack Review** (Gate #2) | Xem tổng hợp Pack dạng tab: Full Script & Shot List / Title & Thumbnail / Repurposing (khoá tới M3). Dải trạng thái đầu trang liệt kê số cảnh báo chưa xử lý. 2 nút: **Approve** (mở khoá Output) / **Trả về** (ô ghi chú bắt buộc, quay lại Script Studio). |
| ⑦ | **Output Center** | 2 thẻ lớn: "Export Pack" và "Render in-app" (thẻ 2 nhãn "Beta · M2"). Sau khi chạy: tiến độ + link tải. |

> **Đã build 1 phần M2 (2026-08-12):** thẻ "Render in-app" không còn `disabled` — bấm
> mở `RenderStudio.tsx` (thay thế 2 thẻ, có nút "← Quay lại"), KHÔNG phải step Stepper
> mới. Luồng: "Bắt đầu sinh asset" → sinh ảnh/video (OpenAI Image/Sora) + giọng đọc
> (ElevenLabs) thật cho từng shot, poll tiến độ mỗi 3s (trạng thái pending/generating/
> ready/error hiện qua tag màu) → mỗi shot xem trước ảnh/video/audio thật (`<img>`/
> `<video>`/`<audio>`, KHÔNG còn placeholder text như Visual Studio §5) + nút "Tạo lại
> Visual"/"Tạo lại giọng đọc" riêng lẻ + nút "Duyệt" (human review bắt buộc trước khi
> ghép) → khi mọi shot đã duyệt, nút "Ghép MP4" (ffmpeg) → preview + tải file cuối.
> Xem `specs/05_ai_providers.md` §8c.
| ⑧ | **Retention Nhập tay** — **đã build, đặt lại vị trí** | Design KHÔNG có màn riêng cho mục này (thiếu so với PRD §10.4/MVP bắt buộc) — bản build đặt dưới dạng card gọn ngay trong **Output Center** (⑦), sau khi Pack đã export. Form nhập 4 nhóm số liệu (§08); sau lưu hiện thanh so sánh chênh lệch vs benchmark. |

## 3. Khu Cài đặt (Admin) — sidebar icon

Vào bằng ⚙. Sidebar phụ dạng **icon + nhãn** (single-user, không RBAC):

| Icon | Mục | Nội dung |
|---|---|---|
| ⚙ | Cấu hình chung | Tên tổ chức, ngôn ngữ, múi giờ, định dạng export mặc định, quy ước đặt tên. |
| 🔌 | **Provider AI** | (màn quan trọng nhất — §4 dưới) |
| 💳 | Chi phí & Ngân sách | Dashboard chi phí theo project/provider; hạn mức + ngưỡng cảnh báo. |
| 🎚 | Tham số AI mặc định | temperature, độ dài, số Hook variant, framework ưu tiên (kênh override được). |
| 🧩 | Prompt Templates | Thư viện prompt (§07); phiên bản hoá; đặt mặc định. |
| 📜 | Audit Log | Nhật ký thao tác quan trọng. |
| 🎨 | Thương hiệu ứng dụng | Logo, màu workspace (khác BrandProfile kênh). |

**Tách biệt trực quan:** khu Cài đặt có nền/khung khác vùng sản xuất.

> **Đã build — bổ sung mục 🎨 Thương hiệu ứng dụng:** `StudioFlow Prototype.dc.html`
> có sẵn state/handler cho màn này (`appBranding`, `onBrandNameChange`,
> `selectBrandSwatch`) nhưng KHÔNG có UI hiển thị trong file thiết kế (mồ côi). Vì
> PRD §7 M7 và mục lục §3 ở trên liệt kê nó là bắt buộc trong "toàn bộ khu Cài đặt
> admin" ở M1, bản build bổ sung màn tối giản dùng đúng các handler đó: đổi tên tổ
> chức hiển thị + chọn màu chủ đạo workspace (áp dụng runtime lên `--color-accent`).

## 4. Màn Provider AI (chi tiết)

- Nhóm theo task (LLM / TTS / Image / Video). Mỗi nhóm có **nhiều thẻ provider bật song song**; mỗi thẻ: tên, loại kết nối (Cloud API / Local Endpoint), trạng thái (chấm xanh/đỏ), model đang chọn, nút **Test**.
- Nút **"+ Thêm provider"**: với LLM cho chọn `Cloud API` (nhập key) hoặc `Local Endpoint` (nhập URL + model — cho Qwen/DeepSeek/Kimi).
  > **Đã build — bổ sung ngoài design:** `StudioFlow Prototype.dc.html` chỉ có danh
  > sách provider cố định (8 thẻ mock) với link "Kết nối ngay" đổi `connected:false`
  > → `true` bằng dữ liệu giả, KHÔNG có form "+ Thêm provider" hay lựa chọn Cloud/Local
  > thật. Vì đây là yêu cầu bắt buộc của PRD §10.2b (model local GPU-ready) và yêu
  > cầu triển khai #4, bản build bổ sung dialog "+ Thêm provider" đúng như mô tả gốc.
- API key che (`sk-••••1234`), hiện khi bấm mắt.
- Dropdown chọn **provider mặc định** cho từng task (gộp cả model cloud + local).
- Trạng thái rỗng: chưa có provider → chặn tuyến sản xuất, điều hướng tới đây kèm thông báo "Cần cấu hình Provider AI".

## 5. Nguyên tắc tương tác (đảm bảo mượt)

- **Auto-save + version im lặng:** không nút "Lưu"; thay đổi tự ghi, version tăng ở nền, xem lại ở panel phải.
- **Streaming rõ ràng:** AI sinh nội dung → chữ hiện dần (SSE §03) + nút "Dừng". Không spinner mù.
- **Phím tắt power-user:** `Cmd/Ctrl+Enter` chạy bước kế; tại gate = Approve; mũi tên điều hướng shot.
- **Optimistic UI:** chọn Hook/duyệt phản hồi tức thì (<100ms), đồng bộ nền.
- **Trạng thái rỗng có hướng dẫn:** luôn kèm 1 câu chỉ dẫn + nút hành động.
- **Cảnh báo phân cấp màu:** hổ phách = gợi ý (bỏ qua được), đỏ = chạm cấm kỵ brand (nên xử lý). Không lạm dụng đỏ.
- **Gate không bypass:** nút Output disabled + tooltip lý do đến khi Gate #2 Approve.
- **Không dead-end:** mỗi màn luôn có nút primary bước kế + đường lùi.

## 6. Thao tác phá huỷ (admin)

Xoá provider/key qua modal xác nhận, tách khỏi nút lưu, ghi Audit Log.

## 7. Design system

Xem skill `frontend-design` khi dựng component. Tone: công cụ chuyên nghiệp, gọn, ưu tiên rõ ràng hơn hào nhoáng. Tailwind; React + TypeScript.
