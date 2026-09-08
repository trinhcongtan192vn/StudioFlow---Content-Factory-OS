"""Xoá vùng ảnh đã khoanh (bbox) bằng LaMa (Large Mask Inpainting, `simple-lama-
inpainting` — bọc sẵn model LaMa, tự tải checkpoint ~196MB 1 lần từ GitHub Release lúc
gọi lần đầu, cache theo tiến trình cùng pattern `detector.py::_get_florence`).

2 hàm khác mục đích tốc độ:
- `inpaint_regions_full_frame` — chạy LaMa trên CẢ ảnh (đơn giản, đúng cho 1 ảnh ĐƠN LẺ
  — VD Visual Studio xoá watermark 1 ảnh user upload cho 1 shot, không tốn thời gian gì
  đáng kể dù chạy trên ảnh nguyên bản).
- `inpaint_region_cropped` — CHỈ chạy LaMa trên 1 CROP NHỎ quanh vùng cần xoá, dán lại
  đúng vị trí — bắt buộc dùng cho VIDEO (hàng nghìn frame, chạy LaMa trên ẢNH ĐẦY ĐỦ mỗi
  frame sẽ quá chậm — đo thật lúc verify: LaMa ~0.9s/lần cho ảnh 640×480; video 1080p dài
  vài phút có hàng chục nghìn frame, đo trên ảnh đầy đủ sẽ mất hàng giờ). Cắt còn vài trăm
  pixel quanh watermark giữ chi phí/frame thấp, khả thi xử lý video dài.
- `inpaint_regions_batch_cropped` — bản BATCH của `inpaint_region_cropped`: gộp N crop
  (cùng bbox, cùng kích thước vì mọi frame video cùng độ phân giải) thành 1 tensor
  `[N,C,H,W]`, chạy LaMa ĐÚNG 1 lượt forward cho cả batch thay vì N lượt tuần tự — bypass
  thẳng `SimpleLama.__call__` (chỉ nhận 1 ảnh/lần) để tự dựng batch qua
  `prepare_img_and_mask` + `torch.cat`, vì package `simple-lama-inpainting` không tự hỗ
  trợ batch (đọc source cài đặt trên máy xác nhận: `torch.jit.load` ra 1 model FCN thuần —
  bản thân model NHẬN batch dim bất kỳ bình thường, chỉ có wrapper Python là ép cứng
  batch=1 qua `unsqueeze(0)`). Đo thật trên GPU (RTX 5060 Ti, video 640×480, crop ~220×200
  quanh watermark, batch=8): 64 frame tuần tự 3.14s (49ms/frame) → theo batch 1.54s
  (24ms/frame) — nhanh gấp ~2 lần (KHÔNG phải suy đoán — số đo thật qua
  `wm_bench.py`, không nên ghi số cao hơn nếu chưa đo lại). `inpaint_region_cropped` giữ
  lại làm ca đặc biệt N=1 của hàm batch (dùng chung logic, không lặp code)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

_session: dict[str, object] = {}


def _get_lama():
    if "lama" not in _session:
        import torch
        from simple_lama_inpainting import SimpleLama

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _session["lama"] = SimpleLama(device=device)
    return _session["lama"]


def _build_mask(size: tuple[int, int], boxes: list[tuple[int, int, int, int]], pad: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    w, h = size
    for x1, y1, x2, y2 in boxes:
        draw.rectangle([max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)], fill=255)
    return mask


def inpaint_regions_full_frame(image: Image.Image, bboxes: list[tuple[int, int, int, int]], pad: int = 6) -> Image.Image:
    """Dùng cho ẢNH ĐƠN LẺ — gộp TẤT CẢ bbox vào 1 mask, chạy LaMa ĐÚNG 1 lượt (rẻ hơn
    chạy tuần tự N lượt cho N vùng nếu phát hiện nhiều watermark trong cùng 1 ảnh)."""
    lama = _get_lama()
    mask = _build_mask(image.size, bboxes, pad)
    return lama(image, mask)


def inpaint_region_cropped(image: Image.Image, bbox: tuple[int, int, int, int], pad: int = 6, context_pad: int = 40) -> Image.Image:
    """Dùng cho 1 ảnh/frame ĐƠN LẺ — ca đặc biệt N=1 của `inpaint_regions_batch_cropped`
    (giữ tên/chữ ký cũ để chỗ khác — VD Visual Studio sau này — gọi cho từng ảnh mà không
    cần biết tới batch)."""
    return inpaint_regions_batch_cropped([image], bbox, pad=pad, context_pad=context_pad)[0]


def inpaint_regions_batch_cropped(
    images: list[Image.Image], bbox: tuple[int, int, int, int], pad: int = 6, context_pad: int = 40,
) -> list[Image.Image]:
    """Vá CÙNG 1 `bbox` cho NHIỀU ảnh/frame trong 1 lượt forward LaMa duy nhất — xem
    docstring module để biết lý do/mức tăng tốc đã đo thật. YÊU CẦU mọi ảnh trong `images`
    CÙNG kích thước (đúng cho mọi frame của 1 video — cùng độ phân giải nguồn), vì chung 1
    bbox/context_pad sẽ luôn cắt ra cùng kích thước crop nên ghép batch được thẳng."""
    if not images:
        return []
    lama = _get_lama()
    x1, y1, x2, y2 = bbox
    w, h = images[0].size
    cx1, cy1 = max(0, x1 - context_pad), max(0, y1 - context_pad)
    cx2, cy2 = min(w, x2 + context_pad), min(h, y2 + context_pad)
    crops = [img.crop((cx1, cy1, cx2, cy2)) for img in images]
    mask = _build_mask(crops[0].size, [(x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1)], pad)

    import torch
    from simple_lama_inpainting.utils.util import prepare_img_and_mask

    prepared = [prepare_img_and_mask(crop, mask, lama.device) for crop in crops]
    image_batch = torch.cat([t[0] for t in prepared], dim=0)
    mask_batch = torch.cat([t[1] for t in prepared], dim=0)
    with torch.inference_mode():
        out = lama.model(image_batch, mask_batch)

    results = []
    for i, img in enumerate(images):
        arr = out[i].permute(1, 2, 0).detach().cpu().numpy()
        arr = np.clip(arr * 255, 0, 255).astype(np.uint8)
        patched_crop = Image.fromarray(arr)
        result = img.copy()
        result.paste(patched_crop, (cx1, cy1))
        results.append(result)
    return results
