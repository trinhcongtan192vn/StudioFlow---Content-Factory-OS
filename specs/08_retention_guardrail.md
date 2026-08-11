# 08 — Retention Guardrail & Nạp retention

Biến "chất lượng" thành thứ **đo được**. Guardrail chỉ **cảnh báo**, không chặn luồng — con người quyết định (giữ đúng nguyên tắc human-gate).

## 1. Hai chỉ số cốt lõi

### Hook Strength (0–1)
- Chấm bằng LLM theo rubric cố định (§07 mục 6): 4 tiêu chí ngang nhau (cụ thể, tò mò/phản trực giác, liên quan pain point, độ dài ≤5s).
- So với `retention_benchmark.target_hook_strength` của kênh (§04).
- Thấp hơn ngưỡng → cảnh báo.
- **Lưu ý:** điểm này chỉ cho guardrail. Ở bước Hook Variants (Gate #1), variant **không** hiển thị điểm — người dùng chọn theo cảm nhận. Đây là hai việc khác nhau, không mâu thuẫn.

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

- Tự động sau AI Generation, trước Gate #2 (§03 `/guardrail/check`).
- Kết quả hiển thị inline trong Script Studio (gạch chân + ghi chú lề) và tổng hợp ở Pack Review.
- Có thể chạy lại thủ công sau khi sửa.

## 6. Nạp retention thủ công (MVP)

Sau khi video đã đăng, người dùng nhập số liệu thực tế để đối chiếu benchmark. Form (§ màn ⑥ trong 06_uiux):

| Trường | Kiểu | Nguồn |
|---|---|---|
| Retention tại 0% (sau Hook) | % | YouTube Studio |
| Retention tại 25% / 50% / 100% | % | YouTube Studio |
| Average View Duration | giây hoặc % | YouTube Studio |
| Thumbnail CTR | % | YouTube Studio |
| Ngày đăng | date | |

- Lưu vào `retention_entry` (§02).
- Hệ thống đối chiếu **retention-tại-Hook** (mốc 0%) với `target_hook_strength` và hiển thị chênh lệch dạng thanh so sánh — dữ liệu tham khảo cho kịch bản sau.
- MVP **không** tính toán phức tạp: chỉ nhập → lưu → đối chiếu → hiển thị.

## 7. Lộ trình M4 (không build ở MVP)

M4 thay bước nhập tay bằng tích hợp **YouTube Analytics API** kéo đúng 4 nhóm số liệu trên. Cùng dữ liệu, cùng cách đối chiếu — form thủ công thành lớp fallback. Điều kiện: đủ khối lượng video để có ý nghĩa thống kê.
