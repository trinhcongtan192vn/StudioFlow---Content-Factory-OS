# 06 — UI/UX

Mục tiêu: thao tác mượt, giảm tải nhận thức. Công cụ vận hành hằng ngày → ưu tiên tốc độ và tính lặp lại.

## 1. Bố cục tổng thể (layout kiểu IDE)

Ba vùng cố định + stepper trên cùng:

> **Đã build (2026-08-17, mục 44 IMPLEMENTATION_REPORT.md) — bỏ hẳn AI Research/
> Outline/Hook/Full-Script + Pack Review/Gate #2, theo yêu cầu người dùng "tập trung
> vào luồng chính: upload script, tạo visual và voice, sau đó render".** Stepper còn
> ĐÚNG **4 bước**: **① Brief (tuỳ chọn) → ② Script Studio → ③ Visual Studio → ④
> Output**. Script chỉ còn 1 con đường: **upload file CSV/Excel** (§ mục Script Import,
> `03_api.md`) — không còn AI tự viết Outline/Hook/Full Script. KHÔNG còn gate duyệt
> bắt buộc nào giữa các bước — `render/assemble`/`export` tự kiểm shot đã sẵn sàng +
> đã duyệt trực tiếp, không cần trạng thái Pack riêng để "mở khoá". Nội dung bảng ①-⑧
> bên dưới (từ đặc tả gốc 7 bước, đã annotate qua nhiều đợt build) vẫn giữ nguyên để
> thấy được lịch sử tiến hoá của thiết kế — xem IMPLEMENTATION_REPORT.md mục 44 cho
> danh sách đầy đủ những gì đã xoá.

```
┌───────────────────────────────────────────────┐
│  Stepper: ① Brief ② Script Studio              │
│           ③ Visual Studio ④ Output             │
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

- **Sidebar trái:** cây `Channel → Project`; badge trạng thái màu theo enum (§02). Nút "+ Project mới" luôn hiện. Góc dưới **icon 📚 Thư viện** (mới, 2026-08-20, mục 53 — xem bên dưới) + **icon 🗑 Thùng rác** (đã build 2026-08-16, xem mục Thùng rác bên dưới) + **icon ⚙** dẫn vào khu Cài đặt (§ khu admin). **Đã build thêm (2026-08-21, mục 58) — cấp lồng thứ 3 `Channel → Project long-form → Short-form`:** mỗi project long-form có Chevron phụ mở rộng danh sách short-form (9:16) con, kèm badge "9:16", nút "+ Short mới" ngay dưới danh sách — xem mục Short-form bên dưới.
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
| ① | **Dashboard kênh** | Lưới thẻ Channel: ảnh, số project đang chạy. Thấy ngay kênh nào tắc. **Đã build (2026-08-17):** bỏ "số chờ duyệt" (`review_count`, gắn với 2 status gate đã xoá — mục 44). |
| ② | **Brief Editor** | Form 4 khối gập/mở (4 nhóm input §04), tuỳ chọn — không bắt buộc điền trước khi upload script. Trường thiếu → chip "cần bổ sung" màu hổ phách (không lỗi đỏ). ~~Nút "Bắt đầu Research" sáng khi đủ input tối thiểu.~~ **Đã build (2026-08-17):** bỏ hẳn nút "Bắt đầu Research"/luồng AI Research — nút "Nhập kịch bản từ file (CSV/Excel)" (`ScriptImportControls`) giờ là hành động DUY NHẤT ở header (mục 44). |
| ~~③~~ | ~~**Outline & Hook (Gate #1)**~~ | **Đã XOÁ hẳn (2026-08-17, mục 44)** — cùng lúc bỏ toàn bộ luồng AI Research/Outline/Hook/Full-Script. Nội dung gốc: Dàn ý AI Research (chọn 1) + Hook Variants (3 thẻ kiểu tâm lý, không điểm số) hiển thị cùng màn, chọn xong sửa trực tiếp hook, duyệt → sinh Full Script. Đường "Nhập kịch bản từ file" từng có ở màn này đã dời hẳn về Brief Editor (②) — xem `03_api.md` mục Script Import. |
| ④ | **Script Studio** (xương sống) | ~~Trước duyệt: 1 cột Full Script liền mạch + ô góp ý "tạo lại".~~ **Đã build (2026-08-17):** bỏ hẳn trạng thái "chưa bóc tách" (`showEditor`) — script import LUÔN có `body` sẵn ngay khi vào màn này, không còn đường nào tạo ra script "chỉ có Full Script, chưa bóc tách" nữa (mục 44). Màn giờ LUÔN hiện kịch bản đa cột theo timeline (Audio/Visual/Direction), 1 cột. Cảnh báo retention = **gạch chân + ghi chú lề** tại đoạn có vấn đề — không popup chặn. |
| ⑤ | **Visual Studio** — **đã build, màn mới** | 1 card/shot (= 1 beat script): Visual/FX + Audio/SFX cùng lúc, toggle Image⇄Video. Khớp nguyên tắc "shot chuẩn hoá" nhưng tương tác trực tiếp thay vì chỉ liệt kê trong Pack Review (đã xoá — xem dưới). **Đã build 2026-08-13:** thêm thẻ **Thumbnail** ở ĐẦU trang (Tạo bằng AI / Upload ảnh từ máy / Duyệt). |
| ~~⑥~~ | ~~**Pack Review (Gate #2)**~~ | **Đã XOÁ hẳn (2026-08-17, mục 44)**, theo yêu cầu người dùng — cả 2 việc màn này từng làm đều bỏ: (1) sinh Title/Description bằng AI (`pack/titles-meta`) — bỏ hẳn, không giữ ở đâu khác; (2) gate duyệt bắt buộc trước Output — bỏ hẳn, `render/assemble`/`export` tự kiểm shot đã sẵn sàng+đã duyệt thay vì dựa `project.status`. Thumbnail (ảnh thật) KHÔNG bị ảnh hưởng — đã sống độc lập ở `ThumbnailCard` (Visual Studio, ⑤) từ trước, không phụ thuộc màn này. Nút "Đi tới Output →" ở Visual Studio (trước là "Xem Production Pack →") giờ đi thẳng luôn. |
| ⑦ | **Output Center** | 2 thẻ lớn: "Export Pack" và "Render in-app" (thẻ 2 nhãn "Beta · M2"). Sau khi chạy: tiến độ + link tải. |

> **Đã build (2026-08-12, cập nhật):** sinh asset thật (ảnh/video/giọng đọc) đã CHUYỂN
> sang **Visual Studio** (§5) — người dùng phản hồi "Render in-app" ở Output Center
> (chỉ mở được SAU Gate #2) sai vị trí, cần sinh + duyệt ngay khi đang thao tác từng
> shot. Visual Studio giờ có: preview thật `<img>`/`<video>`/`<audio>` (KHÔNG còn
> placeholder text), nút "Tạo ảnh/video"/"Tạo giọng đọc" (gọi OpenAI Image/Gemini
> Image/Sora/Veo/ElevenLabs/Gemini TTS THẬT, có fallback tự động — xem
> `specs/05_ai_providers.md` §8c), nút "Duyệt" per-shot, nút hàng loạt "Sinh asset cho
> toàn bộ block". 2 nút cũ "Tạo lại Visual"/"Tạo lại giọng đọc" đổi tên "✎ Viết lại mô
> tả bằng AI" (chỉ sửa PROMPT text qua LLM, không sinh asset thật).
>
> Thẻ "Render in-app" ở Output Center KHÔNG còn `disabled`, giờ CHỈ còn bước **ghép
> MP4** — mở `RenderStudio.tsx` (thay thế 2 thẻ, nút "← Quay lại"), đọc lại đúng trạng
> thái asset đã duyệt ở Visual Studio (tóm tắt "X/Y shot đã duyệt"), nút "Ghép MP4"
> (ffmpeg, chỉ bấm được khi MỌI shot đã duyệt) → preview + tải file cuối. **Đã build
> (2026-08-17, mục 44):** bỏ hẳn yêu cầu "qua Gate #2" — điều kiện DUY NHẤT còn lại là
> mọi shot đã sinh xong visual VÀ đã duyệt (kiểm trực tiếp trên `render.json`, không
> còn phụ thuộc `project.status`).
> Xem `specs/05_ai_providers.md` §8c.
>
> **Đã build (2026-08-17):** mỗi `ShotCard` ở Visual Studio (trừ shot cuối) có thêm
> dropdown chọn **transition** sang shot kế tiếp (`cut` mặc định, `fade`/`fadeblack`/
> `dissolve`/`wipeleft`/`wiperight`/`smoothleft`/`smoothright`) — ghép video (`ffmpeg
> xfade`/`acrossfade`) chỉ re-encode ở đúng ranh giới có transition, giữ nguyên tốc độ
> ghép nhanh (stream-copy) cho phần còn lại. Thêm nút hàng loạt **"Duyệt toàn bộ
> block"** cạnh "Sinh Visual"/"Sinh giọng đọc" — duyệt 1 lần mọi shot đã sinh visual
> xong (`visual_status == "ready"`) thay vì bấm "Duyệt" từng shot.
>
> **Đã build (2026-08-17, tiếp theo):** mỗi `ShotCard` có thêm nút **"↑ Upload
> ảnh/video"** cạnh nút "Tạo ảnh/video" — người dùng chọn sinh bằng AI HOẶC tự upload
> ảnh/video có sẵn từ máy cho shot đó, thay thế TẠI CHỖ (cùng `shot_id`, cùng slot file,
> reset `Đã duyệt`) để đồng bộ với Output Center giống hệt asset AI sinh —
> xem `03_api.md` mục `render/shots/{shot_id}/upload-visual`. Loại file phải khớp
> Image/Video đang chọn ở tag đầu thẻ shot (đổi tag trước nếu muốn đổi loại). Preview
> ảnh/video ở mỗi `ShotCard` giờ có cache-bust (`?v=`) — sinh lại/upload xong đổi ngay,
> không cần refresh thủ công mới thấy asset mới (cùng bug/cùng fix đã áp dụng cho
> Thumbnail).
| ⑧ | **Retention Nhập tay** — **đã build, đặt lại vị trí** | Design KHÔNG có màn riêng cho mục này (thiếu so với PRD §10.4/MVP bắt buộc) — bản build đặt dưới dạng card gọn ngay trong **Output Center** (⑦), sau khi Pack đã export. Form nhập 4 nhóm số liệu (§08); sau lưu hiện thanh so sánh chênh lệch vs benchmark. |

> **Đã build (2026-08-16) — Thùng rác:** màn mới `frontend/src/screens/Trash.tsx`, vào
> bằng icon 🗑 ở Sidebar (ngang hàng Dashboard/⚙, không thuộc luồng project ①-⑧). Gộp 2
> danh sách: **Kênh đã xoá** + **Project đã xoá** (mỗi project kèm tên kênh cho rõ ngữ
> cảnh, vì Thùng rác trộn project từ nhiều kênh khác nhau). Mỗi dòng có 2 nút: **Khôi
> phục** (đưa trở lại bình thường ngay) và **Xoá vĩnh viễn** (dialog xác nhận — xoá DB +
> file trên đĩa, không hoàn tác được, xem `specs/02_database.md` §4 + `03_api.md` mục
> Thùng rác). Nút "Xoá kênh" (Dashboard) và nút "Xoá dự án" (mới thêm ở header
> `ProjectView.tsx`, TRƯỚC ĐÓ project hoàn toàn KHÔNG có UI để xoá) đều chỉ chuyển vào
> Thùng rác — không mất dữ liệu ngay.

> **Đã build (2026-08-20, mục 53) — Thư viện + nhạc nền:** màn mới
> `frontend/src/screens/Library.tsx`, vào bằng icon 📚 ở Sidebar (ngang hàng Dashboard/
> Thùng rác/⚙). 4 mục theo `kind` (Nhạc nền/Video/Ảnh/Giọng đọc), mỗi mục là lưới card
> preview (`<audio>`/`<video>`/`<img>` tuỳ kind) + nút Xoá + nút "+ Upload" trực tiếp.
> Component dùng chung mới: `LibraryPicker.tsx` (nút "Chọn từ thư viện" mở modal liệt kê
> asset theo kind, chọn xong tự nạp vào đúng luồng upload sẵn có ở nơi gọi — KHÔNG có UI
> "chọn từ thư viện" nào tách biệt) và `AddToLibraryButton.tsx` (nút "Thêm vào thư viện"
> hiện SAU khi upload thành công ở nơi khác). Cả 2 component này đã gắn vào MỌI màn có
> upload media hiện có trong app: mẫu giọng thương hiệu + video/audio thương hiệu (sửa
> BrandProfile), shot mở đầu project + ảnh/video từng shot + Thumbnail (Visual Studio) —
> không chỉ 2 tính năng mới bên dưới.
>
> **Đã build thêm (2026-08-21, mục 54) — đổi tên asset:** `AddToLibraryButton.tsx` sau
> khi thêm thành công hiện TÊN THẬT + nút "Sửa tên" (input inline, Enter=Lưu/Esc=Huỷ) —
> sửa được NGAY không cần vòng qua màn Thư viện. Mỗi card ở `Library.tsx` cũng có nút
> "Sửa tên" cạnh "Xoá", cùng cơ chế inline.
>
> **Nhạc nền — mới cùng đợt:** màn "Sửa BrandProfile" thêm mục "Nhạc nền mặc định của
> kênh" (upload/nghe lại/xoá + thanh trượt âm lượng, cùng cấu trúc mục "Video/Audio
> thương hiệu" đã có). Visual Studio thêm thẻ `BgMusicCard` (ngay dưới `IntroShotCard`,
> đầu trang) — override nhạc nền riêng cho project này, cùng thanh trượt âm lượng (chỉ
> PATCH khi thả chuột/rời tay, không PATCH liên tục theo pixel kéo).
>
> **Đã build thêm (2026-08-21, mục 55) — chuyển cảnh cho intro:** `IntroShotCard` thêm
> dropdown "Chuyển cảnh sang shot đầu tiên" (tái dùng đúng danh sách `TRANSITION_OPTIONS`
> đã có cho transition giữa 2 shot thường) — trước đây intro LUÔN ghép cắt cứng vào thân
> video, không cấu hình được.
>
> **Đã build thêm (2026-08-21, mục 55) — gộp nút "Chọn từ thư viện":** mỗi mục chỉ còn
> ĐÚNG 1 nút (trước đây "Video/Audio thương hiệu" và "Shot mở đầu" có 2-3 nút riêng, mỗi
> nút ứng với 1 loại file chấp nhận) — bấm vào mở modal liệt kê GỘP asset của mọi loại
> mục đó chấp nhận (kèm nhãn loại nếu >1), chọn xong tự route đúng luồng upload theo
> loại file thật của asset đã chọn.
>
> **Đã build thêm (2026-08-23, mục 75) — Cultural lock + multi-LoRA + ảnh tham chiếu
> IPAdapter:** theo phát hiện của người dùng ("ảnh tạo ra từ local model đang mang nét
> văn hoá Hàn Quốc/Nhật Bản, không đậm sắc Việt Nam"). `ChannelDialog.tsx` ("Sửa
> BrandProfile") thêm 2 textarea cạnh "Style hình ảnh kênh": "Từ khoá văn hoá Việt Nam
> (bắt buộc xuất hiện)" (positive, để trống mặc định, gợi ý ví dụ áo tứ thân/áo giao
> lĩnh/khăn mỏ quạ/mái đình làng Bắc Bộ/ngói âm dương/hoạ tiết rồng thời Nguyễn) và "Loại
> trừ văn hoá ngoại lai" (negative, đã có default sẵn) — kèm ghi chú phần loại trừ CHỈ có
> tác dụng đầy đủ với ảnh/video sinh bằng model LOCAL (Wan2.2/SDXL), phần từ khoá dương
> vẫn giúp ích cho cloud. Mục "Style LoRA" (dropdown đơn, mục 64) đổi thành DANH SÁCH
> nhiều dòng thêm/bớt được (mỗi dòng `ComfyModelSelect` + số trọng số + nút xoá, nút
> "+ Thêm LoRA" ở cuối) — cho phép stack 2-3 LoRA cùng lúc (VD LoRA sơn dầu + LoRA thuỷ
> mặc riêng). Mục MỚI "Ảnh tham chiếu phong cách — IPAdapter" (chỉ hiện khi đang sửa kênh
> đã tồn tại): lưới ảnh đã upload (mỗi ảnh có nút xoá) + nút "+ Thêm ảnh tham chiếu"
> (upload, không cache-bust vì mỗi ảnh có filename vĩnh viễn — khác mọi asset khác của
> BrandProfile) + thanh trượt trọng số dùng chung cả bộ ảnh, kèm ghi chú cần cài
> `ComfyUI_IPAdapter_plus` + tải model CLIP-Vision/IPAdapter trước khi dùng, nếu ComfyUI
> lỗi thì ảnh vẫn sinh được nhưng KHÔNG áp style tham chiếu. Xem chi tiết cơ chế backend ở
> `specs/05_ai_providers.md` §8k.
>
> **Đã build thêm (2026-08-23, mục 74) — Rà soát UX luồng tạo video:** theo yêu cầu
> người dùng ("nhiều nút bấm bố trí chưa consistent", "right sidebar không để làm gì").
> `RightPanel.tsx` (sidebar phải, dùng chung mọi màn) hiện lại Kênh+niche/Định dạng/Số
> shot/Cảnh báo guardrail thay vì chỉ 1 dòng "Phiên bản Pack". Header Visual Studio tách
> 2 cấp: 2 nút "Sinh lại TOÀN BỘ..." (tốn phí, bỏ duyệt) gom vào menu thả xuống "⋯ Tuỳ
> chọn khác" (component mới `OverflowMenu`). `ShotCard` chỉ còn đúng 1 `btn-primary`/hàng
> ("Tạo ảnh/video", "Tạo giọng đọc" đổi về secondary). `OutputCenter` dùng lại
> `StepHeader` (trước tự viết riêng), bỏ nhãn "Beta · M2" đã lỗi thời. Xoá project
> (`ProjectView.tsx`) bỏ `window.confirm()` — nơi duy nhất dùng dialog xác nhận trình
> duyệt, nay theo đúng quy ước "label rõ đủ" của phần còn lại app (hành động chỉ chuyển
> vào Thùng rác, khôi phục được).
>
> **Sửa lại cùng ngày (mục 74b) — người dùng báo "mất nút Duyệt toàn bộ":** đợt đầu đưa
> "Duyệt toàn bộ block" xuống cạnh danh sách shot (lý do lúc đó: đứng cạnh thứ nó tác
> động vào), nhưng vị trí đó nằm DƯỚI Thumbnail/Intro/BgMusic/Overlay card + banner GPU —
> phải cuộn qua hết mới thấy. Đây là hành động dùng THƯỜNG XUYÊN (duyệt ngay sau khi sinh
> xong), không phải hành động hiếm như "Sinh lại TOÀN BỘ" — chuyển LẠI vào header, cạnh
> "Đi tới Output", giữ nguyên các phần khác của đợt rà soát UX.
>
> **Đã build thêm (2026-08-23, mục 73) — Motion tone cho video AI local:**
> `ChannelDialog.tsx` ("Sửa BrandProfile") thêm field "Tông chuyển động video AI local
> (motion_tone)" cạnh "Style hình ảnh kênh" — ràng buộc chuyển động (VD "chậm, tinh tế,
> không giật gân") CHỈ áp dụng khi sinh video bằng provider `local_wan` (Wan2.2), provider
> cloud (Sora/Veo/Flux) bỏ qua. **Khuyến nghị chọn "Loại Visual" khi soạn script**: chỉ
> đặt `Video` cho shot THỰC SỰ cần chuyển động thật (khói, sương, đám đông xa...) — phần
> lớn shot minh hoạ tĩnh (chân dung, hiện vật, bản đồ) nên dùng `Image` + "Hiệu ứng
> chuyển động camera" (Ken Burns zoom/pan/orbit đã có sẵn, xem mục camera motion) thay vì
> tốn GPU cho video AI dễ lệch phong cách hơn ảnh.
>
> **Đã build thêm (2026-08-23, mục 70) — Nhạc nền/overlay riêng hiển thị rõ kế thừa
> BrandProfile:** `BgMusicCard`/`OverlayEffectCard` (Visual Studio) giờ HIỂN THỊ THẬT
> nhạc nền/overlay mặc định cấp kênh làm preview khi project chưa có asset riêng (tag
> "Kế thừa từ hồ sơ thương hiệu") — cùng cách `IntroShotCard` đã làm ở mục 61, trước đây
> 2 card này hiện trống dù thực tế vẫn dùng brand default lúc ghép MP4.
>
> **Đã build thêm (2026-08-23, mục 71) — Chỉnh âm lượng nhạc nền riêng kể cả khi kế
> thừa:** thanh trượt "Âm lượng nhạc nền so với giọng đọc chính" ở `BgMusicCard` (Visual
> Studio) giờ hiện NGAY CẢ KHI project đang kế thừa nhạc nền brand (trước đó chỉ hiện khi
> có asset riêng) — cho phép chỉnh âm lượng riêng cho project mà KHÔNG cần upload lại
> file nhạc, giá trị khởi điểm = volume hiện tại của brand (không phải mặc định cứng).
>
> **Đã build thêm (2026-08-22, mục 68) — Hiệu ứng lớp phủ (overlay — mưa/tuyết rơi...):**
> màn "Sửa BrandProfile" thêm mục "Hiệu ứng lớp phủ mặc định của kênh (VD mưa/tuyết rơi)"
> (upload video/xem lại/xoá + thanh trượt cường độ), cùng cấu trúc mục "Nhạc nền mặc định
> của kênh" đã có (audio→video). Visual Studio thêm thẻ `OverlayEffectCard` (cạnh
> `BgMusicCard`, đầu trang) — override overlay riêng cho project này, cùng thanh trượt
> cường độ (chỉ PATCH khi thả chuột/rời tay). Người dùng TỰ upload bất kỳ video hiệu ứng
> nào (không có preset rain/snow dựng sẵn trong app) — blend đè liên tục lên TOÀN BỘ video
> khi ghép MP4 bằng kỹ thuật `blend=all_mode=screen` (nền đen của clip effect tự "biến
> mất"), không chỉ đoạn intro. Xem IMPLEMENTATION_REPORT.md mục 68, `specs/04_data_
> schemas.md` §1/§3b.
>
> **Đã build thêm (2026-08-22, mục 67) — Sinh lại TOÀN BỘ block (force regenerate):**
> Visual Studio thêm 2 nút MỚI cạnh "Sinh Visual/giọng đọc cho toàn bộ block" hiện có (2
> nút cũ GIỮ NGUYÊN — chỉ lấp chỗ pending/error, bỏ qua shot đã ready, dùng để resume sau
> lỗi): **"Sinh lại TOÀN BỘ Visual (kể cả đã có)"** / **"Sinh lại TOÀN BỘ giọng đọc (kể cả
> đã có)"** (`render/start?force=true`) — màu cảnh báo, dùng khi đổi BrandProfile sang
> giọng/style ảnh mới và cần sinh lại hàng loạt. Không có dialog xác nhận (app này không
> dùng pattern đó ở đâu cả) — label + tooltip đã đủ rõ ý "tốn phí lại + bỏ duyệt".
>
> **Đã build thêm (2026-08-22, mục 65) — Chọn checkpoint/LoRA bằng dropdown:** ô "Model"
> của provider `local_sdxl` (Cài đặt → Provider AI, cả lúc sửa lẫn lúc thêm mới) VÀ ô
> "Style LoRA" (Sửa BrandProfile, mục 64) đổi từ nhập tay tự do sang `<select>` liệt kê
> file THẬT đang có trong ComfyUI (`ComfyModelSelect`, component dùng chung 2 màn — xem
> `GET /providers/local-sdxl/models`). ComfyUI chưa chạy → tự rơi về ô nhập tay (không
> chặn cấu hình) kèm thông báo lỗi.
>
> **Đã build thêm (2026-08-22, mục 64) — Style LoRA cho ảnh local SDXL:** `ChannelDialog.
> tsx` ("Sửa BrandProfile") thêm mục "Style LoRA cho ảnh local SDXL" (text tên file LoRA +
> số trọng số) — cùng convention app (mọi field BrandProfile có UI). Chỉ có tác dụng khi
> provider ảnh là `local_sdxl` (ComfyUI) — provider cloud bỏ qua. Xem IMPLEMENTATION_
> REPORT.md mục 64, `specs/05_ai_providers.md` §8i.
>
> **Đã build thêm (2026-08-22, mục 62) — Logo kênh + bỏ mục BrandProfile ở sidebar phải:**
> `ChannelDialog.tsx` ("Sửa BrandProfile") thêm mục "Logo kênh" (upload/xem/xoá, cùng
> pattern intro/nhạc nền — PNG/JPEG/WEBP, thuần hiển thị nhận diện thương hiệu, KHÔNG
> dùng trong pipeline sinh asset/ghép video). **Ngược lại**, `RightPanel.tsx` (sidebar
> phải trong luồng tạo video project — Brief/Script/Visual/Output) BỎ HẲN mục tóm tắt
> BrandProfile (tông giọng, content pillars, cấm kỵ, retention benchmark) theo yêu cầu
> người dùng ("không cần thiết", đã có màn Sửa BrandProfile đầy đủ hơn) — chỉ còn lại
> "Phiên bản Pack" + khung panel thu/phóng.
>
> **Đã build thêm (2026-08-22, mục 61) — Shot mở đầu kế thừa BrandProfile:**
> `IntroShotCard` giờ HIỂN THỊ THẬT video/audio thương hiệu cấp kênh làm preview mặc định
> khi project chưa có asset riêng (nhãn "Kế thừa từ hồ sơ thương hiệu") — trước đây fallback
> này chỉ áp dụng NGẦM lúc ghép MP4, card hiện trống dù thực tế vẫn sẽ có intro. Nút "Bỏ
> shot mở đầu" giờ tắt HẲN (kể cả brand có cấu hình) thay vì chỉ xoá asset riêng; nút mới
> "Dùng lại mặc định thương hiệu" quay lại kế thừa. Mọi thao tác CHỈ ghi vào `render.json`
> của TỪNG project, không bao giờ đụng BrandProfile cấp kênh — xem `app/render/schemas.py::
> IntroAssetStatus.disabled`.
>
> **Đã build thêm (2026-08-21, mục 58) — Short-form sub-project (9:16):** project
> short-form (YouTube Shorts/TikTok) là sub-project ĐỘC LẬP nội dung, lồng dưới 1
> project long-form CÙNG kênh chỉ để nhóm hiển thị (KHÔNG PHẢI auto-repurpose, xem §09
> mốc M3) — tự đi qua đúng luồng Brief→Script Studio→Visual Studio→Output như long-form,
> chỉ khác tỷ lệ khung DỌC 9:16. Tạo mới qua nút "+ Short mới" ở Sidebar (dưới danh sách
> short-form con của 1 project long-form đang mở rộng). **Dashboard kênh (①):** bảng
> project của kênh đang chọn giờ group long-form + short-form con indent ngay dưới,
> thêm cột "Loại" (badge "Long-form"/"Short 9:16"). **ProjectView:** breadcrumb thêm 1
> đoạn tên project long-form cha khi đang mở short-form con + badge "Short 9:16" cạnh
> tên project. **Visual Studio:** khung preview (`ShotCard`/`IntroShotCard`) đổi tỷ lệ
> cột/box (140px/249px thay vì 220px/124px) cho project short-form, khớp khung dọc —
> `ThumbnailCard` GIỮ NGUYÊN 16:9 (thumbnail YouTube luôn ngang bất kể project).
> **Render Studio:** nhãn độ phân giải đổi theo format (VD "1080p (1080×1920 dọc)").

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
- **Đã build (2026-08-12):** Test connection chạy **NGAY sau khi thêm provider**
  (trong dialog "+ Thêm provider", không cần đóng dialog rồi tự bấm Test riêng ở thẻ
  sau đó) — kết quả (✓/✗ + message) hiện ngay trong dialog; nếu fail, cho sửa lại API
  Key và "Lưu & Test lại" ngay tại chỗ, không bắt đóng dialog trước. Nút Test ở từng
  thẻ VẪN giữ (re-verify sau này, VD xoay key/hết quota), chỉ không còn là bước bắt
  buộc ngay sau khi thêm.
- API key che (`sk-••••1234`); nút **"Sửa"** bật ô nhập key mới thật sự nhập được +
  nút Lưu/Hủy (trước đây có nút "mắt" nhưng ô luôn `readOnly` — không sửa được dù chữ
  ghi "nhập lại để đổi", đã sửa bug này).
- Dropdown chọn **provider mặc định** cho từng task (gộp cả model cloud + local) + dropdown **Fallback** — với `tts`/`image`/`video`, fallback THẬT SỰ được dùng: provider mặc định gọi API lỗi → tự động thử provider fallback (xem `specs/05_ai_providers.md` §8c). `llm` chưa có fallback thật (chỉ lưu cờ).
- Trạng thái rỗng: chưa có provider → chặn tuyến sản xuất, điều hướng tới đây kèm thông báo "Cần cấu hình Provider AI".

## 5. Nguyên tắc tương tác (đảm bảo mượt)

- **Auto-save + version im lặng:** không nút "Lưu"; thay đổi tự ghi, version tăng ở nền, xem lại ở panel phải.
- **Streaming rõ ràng:** AI sinh nội dung → chữ hiện dần (SSE §03) + nút "Dừng". Không spinner mù.
- **Phím tắt power-user:** `Cmd/Ctrl+Enter` chạy bước kế; mũi tên điều hướng shot. ~~tại gate = Approve~~ (không còn gate — mục 44).
- **Optimistic UI:** duyệt shot phản hồi tức thì (<100ms), đồng bộ nền.
- **Trạng thái rỗng có hướng dẫn:** luôn kèm 1 câu chỉ dẫn + nút hành động.
- **Cảnh báo phân cấp màu:** hổ phách = gợi ý (bỏ qua được), đỏ = chạm cấm kỵ brand (nên xử lý). Không lạm dụng đỏ.
- ~~**Gate không bypass:** nút Output disabled + tooltip lý do đến khi Gate #2 Approve.~~ **Đã build (2026-08-17, mục 44):** bỏ hẳn — Output/Export/`render/assemble` không còn gate nào chặn, chỉ tự kiểm dữ liệu (shot ready+approved) ngay tại điểm dùng.
- **Không dead-end:** mỗi màn luôn có nút primary bước kế + đường lùi.

## 6. Thao tác phá huỷ (admin)

Xoá provider/key qua modal xác nhận, tách khỏi nút lưu, ghi Audit Log.

## 7. Design system

Xem skill `frontend-design` khi dựng component. Tone: công cụ chuyên nghiệp, gọn, ưu tiên rõ ràng hơn hào nhoáng. Tailwind; React + TypeScript.
