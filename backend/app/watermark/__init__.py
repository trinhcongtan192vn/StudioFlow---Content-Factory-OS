"""Module xoá watermark khỏi ảnh/video — TÁI SỬ DỤNG ĐƯỢC (Kho Tài Nguyên §RawLibrary
"Xoá watermark" trước khi cắt cảnh + dự kiến dùng lại ở Visual Studio sau này để xoá
watermark ảnh/video user tự upload cho từng shot).

Kiến trúc THAM KHẢO github.com/D-Ogi/WatermarkRemover-AI (đã xác nhận qua đọc README dự
án đó, không suy đoán): Florence-2 (Microsoft, open-vocabulary object detection) phát
hiện VÙNG watermark bằng prompt text ("watermark"), rồi LaMa (Large Mask Inpainting)
lấp lại vùng đó bằng nội dung hợp lý theo ngữ cảnh xung quanh — xem `detector.py`/
`remover.py`. `pipeline.py` gộp thành 2 hàm cấp cao dùng trực tiếp: 1 ảnh
(`remove_watermark_from_image`) và 1 video (`remove_watermark_from_video`, phát hiện 1
lần trên frame đại diện rồi áp cho mọi frame — watermark stock footage hầu hết CỐ ĐỊNH vị
trí suốt video, xem docstring `pipeline.py`).

**Cập nhật 2026-09-04 (bug thật #4, `detector.py`)**: Florence-2 chỉ đáng tin cho VIDEO —
với ẢNH minh hoạ chi tiết (VD ảnh Gemini/Nano Banana), verify thật xác nhận Florence-2-base
KHÔNG đủ khả năng định vị icon lấp lánh trong suốt (thử 8+ prompt/crop khác nhau đều sai).
`remove_watermark_from_image` giờ dùng `detector.gemini_corner_bbox` — vị trí tương đối CỐ
ĐỊNH đã đo thật (Gemini/Nano Banana luôn đặt watermark ở cùng 1 vị trí tương đối bất kể nội
dung ảnh) — thay cho Florence-2 làm mặc định.

**Verify thật trước khi build** (không suy đoán API/model có hoạt động không): dựng ảnh
test tổng hợp (gradient + nhiễu mô phỏng ảnh thật, watermark chữ trắng bán trong suốt góc
dưới phải) — Florence-2 phát hiện ĐÚNG bbox watermark (khớp toạ độ đã vẽ, sai lệch <5px),
LaMa lấp lại cho kết quả liền mạch, không thấy viền/artifact — cả 2 model tải + chạy được
thật trên GPU máy dev (RTX 5060 Ti, `torch==2.8.0+cu129` khớp bản ComfyUI đã dùng)."""
