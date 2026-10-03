# 08 — Retention Guardrail & Nạp retention

Biến "chất lượng" thành thứ **đo được**. Guardrail chỉ **cảnh báo**, không chặn luồng — con người quyết định (giữ đúng nguyên tắc human-gate).

## 1. Hai chỉ số cốt lõi

### Hook Strength (0–1)
- Chấm bằng LLM theo rubric cố định (§07 mục 6): 4 tiêu chí ngang nhau (cụ thể, tò mò/phản trực giác, liên quan pain point, độ dài ≤5s).
- So với `retention_benchmark.target_hook_strength` của kênh (§04).
- Thấp hơn ngưỡng → cảnh báo.
- **Lưu ý:** điểm này chỉ cho guardrail. Ở bước Hook Variants (Gate #1), variant **không** hiển thị điểm — người dùng chọn theo cảm nhận. Đây là hai việc khác nhau, không mâu thuẫn.
  > **Đã build lại (2026-08-17, mục 44):** Hook Variants/Gate #1 bỏ HẲN (xem `09_sprint_tasks.md`
  > EPIC 7) — kịch bản chỉ đến từ import, không có `hook_spoken` riêng nữa. `run_guardrail_check`
  > (`app/guardrail/check.py`) chỉ chấm Hook Strength khi `hook_spoken` khác rỗng — với script
  > import, giá trị này luôn rỗng nên **Hook Strength luôn `null`**, guardrail chỉ còn thật sự
  > tính Anchor Gap + body length + brand-fit. Code chấm điểm vẫn còn nguyên (không xoá, coi như
  > hạ tầng có thể tái dùng sau), chỉ không còn đường nào gọi tới với `hook_spoken` khác rỗng.

### Anchor Gap (giây)
- Duyệt `script.body[]`, tính khoảng cách lớn nhất giữa hai dòng liên tiếp có `anchor=true`.
- So với `retention_benchmark.max_anchor_gap_sec` (mặc định 45).
- Vượt ngưỡng → cảnh báo, chỉ rõ vị trí `at_timestamp_sec`.

## 2. Cảnh báo bổ sung

- **Body quá ngắn:** số beat < `target_body_len_min` → cờ.
- **Brand-fit / cấm kỵ:** kịch bản chạm từ trong `forbidden` (§04) → cảnh báo **đỏ** (nặng hơn).

## 3. Phân cấp severity

| Severity | Màu | Nghĩa | Ví dụ |
|---|---|---|---|
| `amber` | Hổ phách | Gợi ý, bỏ qua được | Anchor gap 48s, hook hơi thấp. |
| `red` | Đỏ | Nên xử lý | Chạm cấm kỵ brand. |

## 4. Output của check

Ghi vào `pack.retention_check` (§04):
```json
{
  "hook_strength": 0.72,
  "max_anchor_gap_sec": 38,
  "warnings": [
    { "type": "anchor_gap", "severity": "amber",
      "at_timestamp_sec": 120, "message": "Khoảng trống anchor 52s > 45s" }
  ]
}
```

## 5. Khi nào chạy

- ~~Tự động sau AI Generation, trước Gate #2 (§03 `/guardrail/check`).~~
- ~~Kết quả hiển thị inline trong Script Studio (gạch chân + ghi chú lề) và tổng hợp ở Pack Review.~~
- Có thể chạy lại thủ công sau khi sửa.

> **Đã build lại (2026-08-17, mục 44):** không còn "AI Generation"/Gate #2 — guardrail
> chạy tự động ngay lúc `/script/import/confirm` (import kịch bản). Kết quả vẫn hiển thị
> inline ở Script Studio; phần "tổng hợp ở Pack Review" không còn (màn đó đã xoá).

## 6. Nạp retention thủ công (MVP)

Sau khi video đã đăng, người dùng nhập số liệu thực tế để đối chiếu benchmark. Form (§ màn ⑥ trong 06_uiux):

| Trường | Kiểu | Nguồn |
|---|---|---|
| Retention tại 0% (sau Hook) | % | YouTube Studio |
| Retention tại 25% / 50% / 100% | % | YouTube Studio |
| Average View Duration | giây hoặc % | YouTube Studio |
| Thumbnail CTR | % | YouTube Studio |
| RPM (€/1.000 view) | số | YouTube Studio — **luôn nhập tay** (§7), không tự động hoá được |
| Ngày đăng | date | |

- Lưu vào `retention_entry` (§02).
- Hệ thống đối chiếu **retention-tại-Hook** (mốc 0%) với `target_hook_strength` và hiển thị chênh lệch dạng thanh so sánh — dữ liệu tham khảo cho kịch bản sau.
- MVP **không** tính toán phức tạp: chỉ nhập → lưu → đối chiếu → hiển thị.
- Form này vẫn tồn tại song song với §7 — chỉ còn thực sự CẦN cho RPM (chỉ số duy nhất
  không tự động hoá được); các trường còn lại có thể để trống nếu kênh đã kết nối YouTube
  và đồng bộ tự động.

## 7. Chỉ số cốt lõi tự động từ YouTube Analytics API — **đã triển khai 2026-09-12 (Phase 1 của lộ trình M4 trước đây)**

Thay vì chỉ nhập tay, kênh có thể **kết nối OAuth** (Settings → "Chỉ số YouTube") để kéo
tự động 6/7 chỉ số cốt lõi từ §5.4:

- **North-star (dẫn đường)**: APV (Average Percentage Viewed) trung bình có TRỌNG SỐ
  theo view giữa các video đã liên kết — mục tiêu ≥45%. Retention THEO TỪNG CHƯƠNG (không
  chỉ APV tổng) — khớp `retention_curve` (dimension `elapsedVideoTimeRatio` của report
  `audienceRetention`) với `pack.script.body[]` theo tỷ lệ cộng dồn thời lượng từng block,
  hiển thị biểu đồ + đánh dấu chương tụt mạnh nhất (`GET /projects/{id}/youtube/
  retention-chapters`) — dữ liệu THAM KHẢO cho Tiefen-Test đề tài sau, KHÔNG tự động feed
  ngược vào guardrail.
- **Vận hành (theo dõi)**: retention giây 30 (≥70%), bình luận/1.000 view, tỷ trọng lưu
  lượng DE/AT/CH — đều trọng số theo view ở cấp kênh, riêng lẻ ở cấp video.
- **KHÔNG tự động hoá**: RPM (quyền `yt-analytics-monetary.readonly` khó xin cho app cá
  nhân — Google thường yêu cầu audit CMS/Content Owner) — vẫn nhập tay qua §6. **CTR
  thumbnail (mục tiêu 5-8%)** — ĐÃ VERIFY THẬT (không chỉ suy đoán, xem
  IMPLEMENTATION_REPORT.md mục 153) rằng YouTube Analytics API công khai KHÔNG có metric
  `impressions`/`impressionClickThroughRate` cho bất kỳ dimension nào — gọi thẳng metric
  này trả lỗi HTTP 400 "Unknown identifier". Không có cách tự động lấy CTR thumbnail qua
  API công khai; nhập tay qua `RetentionEntry.thumbnail_ctr` ở Output Center, y như RPM.
  **Tỷ lệ Returning Viewers** cũng CHƯA tự động hoá — dimension `subscribedStatus` công
  khai KHÔNG tương đương "new vs returning viewers" (card đó chỉ có ở YouTube Studio UI,
  khả năng chỉ expose qua API cấp Content Owner/CMS) — cần 1 spike xác nhận trước khi
  build, xem IMPLEMENTATION_REPORT.md mục tương ứng; nếu không tự động hoá được sẽ
  fallback nhập tay như RPM.

Kiến trúc, endpoint, bảng DB: xem `specs/02_database.md` (bảng `youtube_channel_metrics_
snapshot`/`youtube_video_metrics_snapshot`), `specs/03_api.md` (§"Chỉ số YouTube"),
`app/youtube_analytics.py`, `app/routers/youtube_analytics.py`. Đồng bộ là hành động BẤM
NÚT thủ công (không polling nền, đúng CLAUDE.md nguyên tắc 3), mỗi lần bấm ghi 1 snapshot
mới (giữ lịch sử, không update tại chỗ) — hiển thị ở Dashboard → bấm vào kênh → tab "Chỉ
số YouTube" (cả cấp kênh lẫn từng video).
