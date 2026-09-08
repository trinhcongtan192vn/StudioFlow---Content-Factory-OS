"""ComfyUI + SDXL — sinh ảnh local qua GPU thật (ComfyUI chạy như service phụ, xem
IMPLEMENTATION_REPORT.md để cài đặt). Đồng bộ (`httpx.Client`, khớp convention các
adapter Image khác trong repo này — `image_openai.py`/`image_gemini.py`) — khác
`ai-content-studio` dùng async, ở đây build workflow rồi `POST /prompt` (queue) →
poll `GET /history/{id}` → `GET /view` (tải ảnh), không dùng websocket.

Khác `ai-content-studio/apps/backend/app/adapters/image_gen/comfy_sdxl.py`: BAN ĐẦU bỏ
hẳn IPAdapter Plus (custom node cộng đồng dễ lệch tên/version), dùng **img2img thuần
bằng node ComfyUI gốc** (`LoadImage`+`VAEEncode`+`KSampler(denoise<1)`) khi có
`reference_image` (Tier 2 — giữ nhất quán phong cách/nhân vật giữa các shot qua ảnh
"anchor", xem app/render/engine.py) — img2img này VẪN GIỮ NGUYÊN, không đổi.

**Đảo ngược 1 phần quyết định trên (2026-08-23)**: người dùng phát hiện checkpoint/LoRA
"Á Đông/thuỷ mặc" (tuyệt đại đa số train từ dữ liệu Nhật/Trung/Hàn trên Civitai) khiến
ảnh sinh ra mang nét Nhật/Hàn dù không yêu cầu — img2img/prompt không đủ mạnh để ép
ngược thiên lệch train. Thêm LẠI IPAdapter (`_add_ipadapter_nodes`) làm lớp "ảnh tham
chiếu phong cách" TÁCH BIỆT khỏi img2img/anchor ở trên — IPAdapter điều kiện hoá MODEL
(tách phong cách khỏi bố cục, nhận NHIỀU ảnh cùng lúc), khác img2img seed LATENT (1 ảnh,
bố cục/màu ảnh gốc ảnh hưởng trực tiếp). Người dùng đã xác nhận chấp nhận rủi ro custom
node đổi lại — CHƯA verify thật trên ComfyUI+IPAdapter (khác mọi tính năng ComfyUI khác
trong codebase, đều verify qua GPU thật) — có fallback tự động về không-IPAdapter nếu
ComfyUI từ chối node (xem `_generate_locked`).

Độ phân giải 1344x768 (~16:9, đúng 1 trong các bucket SDXL được train — khác OpenAI
Image dùng 1792x1024 vì SDXL ở scale đó chất lượng giảm rõ do lệch xa vùng train).
"""
import time
import uuid

import httpx

from app.providers.base import ImageProvider, ProviderStatus, raise_if_interrupted
from app.providers.gpu_lock import gpu_lock

_DEFAULT_BASE_URL = "http://127.0.0.1:8188"
# Checkpoint MẶC ĐỊNH khi provider chưa cấu hình `model_name` riêng — cơ chế "field
# `model_name` điều khiển checkpoint thật" đã build ở đợt 1 (2026-08-22). **Đổi giá trị
# đợt 2 (2026-08-22)**, theo `StudioFlow_Style_Checkpoint_Proposal.md`: base gốc
# `sd_xl_base_1.0` đổi sang **"Painter's Checkpoint" v1.1**
# (`paintersCheckpointOilPaint_v11.safetensors`, CivitAI model 240154, SDXL 1.0 fine-tune
# hướng "alla prima, gestural, atmospheric... far from clean sharp photorealism") — khớp
# ĐÚNG art direction kênh (tranh vẽ tay/sơn dầu, KHÔNG photoreal) — quyết định THAY THẾ
# hẳn hướng "chờ người dùng chốt giữa Juggernaut/RealVisXL/DreamShaper" ở đợt 1 (2 trong 3
# lựa chọn đó là photoreal, SAI hướng cho kênh này — xem tài liệu đề xuất đợt 2). File đã
# tải THẬT vào `ComfyUI/models/checkpoints/` (xem IMPLEMENTATION_REPORT.md để biết cách
# tải nếu cần cài lại). Đổi checkpoint khác vẫn làm được qua Cài đặt → Provider AI → ô
# "Model" như đợt 1, không cần sửa code.
_CHECKPOINT_NAME = "paintersCheckpointOilPaint_v11.safetensors"
# Mở rộng (2026-08-22), theo yêu cầu người dùng (đợt 2 cải thiện chất lượng ảnh local —
# StudioFlow_Style_Checkpoint_Proposal.md): thêm 2 nhóm từ khoá negative CỐ ĐỊNH —
# (1) "title card, caption, subtitle" — chuyển "no text, no title card, no captions" TỪ
# prompt DƯƠNG (app/render/engine.py::_build_visual_prompt, đợt 1) SANG ĐÚNG chỗ negative
# prompt thật (nơi nó luôn thuộc về — negative conditioning hiệu quả hơn hẳn câu phủ định
# nhét trong prompt dương); (2) "3d render, plastic, cgi, glossy, photorealistic, smooth
# plastic surface" — chặn hướng "3D nhựa hoá giả tạo" mà kênh minh hoạ lịch sử (phong cách
# vẽ tay/sơn dầu) CẤM kỵ, theo đúng art direction trong tài liệu đề xuất.
_NEGATIVE_PROMPT = "blurry, low quality, distorted, watermark, text, deformed, title card, caption, subtitle, 3d render, plastic, cgi, glossy, photorealistic, smooth plastic surface"
# Negative prompt THÊM riêng cho img2img (nối vào _NEGATIVE_PROMPT, không áp dụng cho
# txt2img thuần) — anchor giờ là ảnh Thumbnail (§05 mục 8d/18), vốn CỐ TÌNH thiết kế
# nhiều chữ/khung/mũi tên chú thích (thumbnail YouTube: "bold, high-contrast", xem
# app/routers/pack.py::generate_thumbnail) — img2img có xu hướng "kéo" nguyên khung/chữ
# đó vào MỌI shot (chữ bị vẽ lại thành ký tự vô nghĩa vì model không hiểu là chữ thật),
# phát hiện thật lúc người dùng test (ảnh shot nào cũng dính khung gỗ + chữ rác giống
# hệt thumbnail). Thêm từ khoá chặn cụ thể loại "chảy" này — generic "text" trong
# _NEGATIVE_PROMPT không đủ mạnh khi latent khởi tạo (VAEEncode) đã mã hoá sẵn cấu trúc
# chữ/khung từ ảnh gốc.
_IMG2IMG_EXTRA_NEGATIVE = "caption, subtitle, label, ornate frame, border, sign, plaque, infographic, map legend, callout box, arrow annotation, ruler markings"
_POLL_INTERVAL_SEC = 2.0
_POLL_TIMEOUT_SEC = 300.0  # SDXL local ~5-15s/ảnh bình thường trên GPU rời, rộng rãi cho máy yếu
_WIDTH = 1344
_HEIGHT = 768
# Cặp kích thước DỌC tương ứng — mới (2026-08-21), cho project short-form (9:16). Hoán
# đổi trực tiếp W/H của bucket SDXL đã chọn (768x1344) — vẫn là bucket SDXL được train,
# chỉ đổi chiều, không lệch vùng train như bucket 16:9 (xem docstring đầu file).
_WIDTH_VERTICAL = 768
_HEIGHT_VERTICAL = 1344
# denoise = mức nhiễu thêm vào latent TRƯỚC khi denoise lại — 1.0 = noise hoàn toàn,
# BỎ QUA ảnh gốc (= txt2img thuần); 0.0 = không noise, ảnh ra gần như y nguyên ảnh gốc.
# CÀNG THẤP → CÀNG BÁM ảnh anchor (ngược trực giác, dễ nhầm — chính là lỗi đã mắc ở
# bản sửa đầu tiên 2026-08-16: hạ từ 0.6 xuống 0.45 tưởng sẽ GIẢM copy chi tiết ảnh gốc,
# thực tế đo qua GPU thật lại làm ảnh giống ảnh gốc HƠN — xem IMPLEMENTATION_REPORT.md).
#
# 0.6 (giá trị gốc) đã đủ thấp để tái tạo gần nguyên khung/chữ khi anchor là ảnh nhiều
# chi tiết đồ hoạ (VD Thumbnail dạng bản đồ minh hoạ, xem _IMG2IMG_EXTRA_NEGATIVE) — bug
# thật người dùng báo "ảnh shot giống hệt nhau, không thấy ảnh hưởng từ thumbnail" (thực
# ra NGƯỢC LẠI: ảnh hưởng QUÁ NHIỀU, đủ để lấn át nội dung riêng từng shot). Test thật
# qua GPU nhiều mức: 0.45/0.25 còn tệ hơn (gần như copy nguyên), 0.8 gần như bỏ qua hẳn
# anchor (kể cả màu sắc). **0.7** là điểm cân bằng xác nhận qua GPU thật: vẫn giữ rõ
# tông màu/bố cục tổng thể khi anchor là ảnh sạch (ảnh chụp/minh hoạ đơn giản — verify
# lại bằng ảnh hải đăng ở Tier 2 gốc, kết quả vẫn nhất quán tốt), đồng thời giảm mạnh
# việc copy nguyên khung/chữ khi anchor là ảnh nhiều chi tiết đồ hoạ như Thumbnail.
_IMG2IMG_DENOISE = 0.7
# Ảnh tham chiếu phong cách (IPAdapter) — **mới (2026-08-23)**, xem docstring đầu file
# (đảo ngược 1 phần quyết định "không dùng IPAdapter"). 2 tên model NGƯỜI DÙNG PHẢI TỰ
# TẢI đặt đúng thư mục ComfyUI trước khi dùng (xem IMPLEMENTATION_REPORT.md) — đây là
# LỰA CHỌN PHỔ BIẾN NHẤT đi kèm bản IPAdapter SDXL ("plus", không phải "plus face" —
# dùng cho phong cách tổng thể, không phải khoá khuôn mặt nhân vật), CHƯA thể xác nhận
# đúng 100% khớp mọi phiên bản `ComfyUI_IPAdapter_plus` đã cài trên máy người dùng.
_IPADAPTER_CLIP_VISION_NAME = "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
_IPADAPTER_MODEL_NAME = "ip-adapter-plus_sdxl_vit-h.safetensors"


def _add_ipadapter_nodes(workflow: dict, *, image_filenames: list[str], weight: float) -> None:
    """Chèn IPAdapter (CUSTOM NODE `ComfyUI_IPAdapter_plus`, KHÁC mọi node khác trong file
    này — đều là core ComfyUI) làm lớp "ảnh tham chiếu phong cách" — điều kiện hoá MODEL
    (tách phong cách khỏi bố cục), KHÁC img2img (`_build_img2img_workflow`) seed LATENT
    (1 ảnh, bố cục/màu ảnh gốc ảnh hưởng trực tiếp). Đọc THẲNG `workflow["3"]["inputs"]
    ["model"]` hiện tại làm input — nếu gọi SAU `_add_lora_nodes` (đúng thứ tự trong
    `_build_txt2img_workflow`/`_build_img2img_workflow`), IPAdapter tự động áp SAU LoRA
    (LoRA khoá "chữ ký kỹ thuật" trước, IPAdapter khoá "cảm hứng thị giác" sau) — không
    cần biết LoRA có được dùng hay không, chỉ cần nối tiếp link hiện có.

    NHIỀU ảnh cùng lúc: `LoadImage` từng ảnh rồi chain `ImageBatch` (core ComfyUI, ghép
    ĐÚNG 2 ảnh/lần) tuần tự — đúng cách ComfyUI xử lý "nhiều ảnh style cùng lúc" cho
    IPAdapter (IPAdapter tự trung bình hoá embedding của cả batch)."""
    workflow["90"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": _IPADAPTER_CLIP_VISION_NAME}}
    workflow["91"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": _IPADAPTER_MODEL_NAME}}
    image_link: list | None = None
    for i, filename in enumerate(image_filenames):
        load_id = f"92{i}"
        workflow[load_id] = {"class_type": "LoadImage", "inputs": {"image": filename}}
        if image_link is None:
            image_link = [load_id, 0]
        else:
            batch_id = f"93{i}"
            workflow[batch_id] = {"class_type": "ImageBatch", "inputs": {"image1": image_link, "image2": [load_id, 0]}}
            image_link = [batch_id, 0]
    workflow["94"] = {
        "class_type": "IPAdapterApply",
        "inputs": {
            "ipadapter": ["91", 0], "clip_vision": ["90", 0], "image": image_link,
            "model": workflow["3"]["inputs"]["model"], "weight": weight,
            "weight_type": "linear", "start_at": 0.0, "end_at": 1.0,
        },
    }
    workflow["3"]["inputs"]["model"] = ["94", 0]


def _add_lora_nodes(workflow: dict, *, loras: list[dict], clip_encode_node_ids: list[str]) -> None:
    """Chèn CHUỖI node `LoraLoader` (CÓ SẴN trong ComfyUI core, KHÔNG phải custom node —
    khác IPAdapter Plus đã cố tình bỏ, xem docstring đầu file) giữa `CheckpointLoaderSimple`
    (node "4") và mọi node dùng `model`/`clip` của nó — **mới (2026-08-22, đổi sang STACK
    NHIỀU LoRA 2026-08-23)**: 1 LoRA đơn không đủ vừa khoá chất liệu (VD sơn dầu) vừa ép
    đúng hướng văn hoá Việt (VD thuỷ mặc Trung Quốc thuần khác thuỷ mặc Nhật) — theo đề
    xuất người dùng chống thiên lệch văn hoá Nhật/Hàn, stack 2-3 LoRA. Mỗi `LoraLoader`
    nối tiếp node TRƯỚC (không phải luôn từ checkpoint trực tiếp) — đúng cách ComfyUI
    stack nhiều LoRA. `loras` rỗng (mặc định) → hàm KHÔNG được gọi, workflow giữ nguyên
    nối thẳng checkpoint → sampler như trước, không đổi hành vi cho ai chưa cấu hình LoRA
    nào (tương thích ngược hoàn toàn với trường hợp 1 LoRA cũ)."""
    model_link = ["4", 0]
    clip_link = ["4", 1]
    for i, lora in enumerate(loras):
        node_id = f"13{i}"
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {"lora_name": lora["name"], "strength_model": lora["strength"], "strength_clip": lora["strength"], "model": model_link, "clip": clip_link},
        }
        model_link = [node_id, 0]
        clip_link = [node_id, 1]
    workflow["3"]["inputs"]["model"] = model_link
    for node_id in clip_encode_node_ids:
        workflow[node_id]["inputs"]["clip"] = clip_link


def _negative_prompt_text(base: str, extra_negative: str = "") -> str:
    """Nối `extra_negative` (VD `cultural_lock_negative` — mới 2026-08-23) vào negative
    prompt gốc — dùng chung cho cả txt2img/img2img, tránh lặp logic ghép chuỗi."""
    return f"{base}, {extra_negative}" if extra_negative else base


def _build_txt2img_workflow(
    *, prompt: str, seed: int, ckpt_name: str = _CHECKPOINT_NAME, loras: list[dict] | None = None, extra_negative: str = "",
    width: int = _WIDTH, height: int = _HEIGHT, style_reference_filenames: list[str] | None = None, style_reference_weight: float = 0.6,
) -> dict:
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 7.0, "denoise": 1.0, "latent_image": ["5", 0], "model": ["4", 0],
                "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "dpmpp_2m",
                "scheduler": "karras", "seed": seed, "steps": 30,
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": height, "width": width}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": _negative_prompt_text(_NEGATIVE_PROMPT, extra_negative)}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studioflow", "images": ["8", 0]}},
    }
    if loras:
        _add_lora_nodes(workflow, loras=loras, clip_encode_node_ids=["6", "7"])
    if style_reference_filenames:
        _add_ipadapter_nodes(workflow, image_filenames=style_reference_filenames, weight=style_reference_weight)
    return workflow


def _build_img2img_workflow(
    *, prompt: str, seed: int, ref_filename: str, ckpt_name: str = _CHECKPOINT_NAME, loras: list[dict] | None = None, extra_negative: str = "",
    width: int = _WIDTH, height: int = _HEIGHT, style_reference_filenames: list[str] | None = None, style_reference_weight: float = 0.6,
) -> dict:
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 7.0, "denoise": _IMG2IMG_DENOISE, "latent_image": ["10", 0], "model": ["4", 0],
                "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "dpmpp_2m",
                "scheduler": "karras", "seed": seed, "steps": 30,
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": _negative_prompt_text(f"{_NEGATIVE_PROMPT}, {_IMG2IMG_EXTRA_NEGATIVE}", extra_negative)}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studioflow", "images": ["8", 0]}},
        "10": {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": ref_filename}},
        # ImageScale BẮT BUỘC (không chỉ phòng vệ) — anchor giờ ưu tiên lấy từ ảnh
        # Thumbnail (§05 mục 8d/18), có thể khác kích thước width x height (thumbnail
        # sinh ở tỉ lệ riêng, hoặc người dùng tự upload ảnh kích thước bất kỳ).
        "12": {"class_type": "ImageScale", "inputs": {"image": ["11", 0], "width": width, "height": height, "upscale_method": "lanczos", "crop": "disabled"}},
    }
    if loras:
        _add_lora_nodes(workflow, loras=loras, clip_encode_node_ids=["6", "7"])
    if style_reference_filenames:
        _add_ipadapter_nodes(workflow, image_filenames=style_reference_filenames, weight=style_reference_weight)
    return workflow


class ComfySDXLImageProvider(ImageProvider):
    provider_name = "local_sdxl"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        # `model_name` giờ là tên file checkpoint THẬT (VD "sd_xl_base_1.0.safetensors"),
        # dùng trực tiếp làm `ckpt_name` trong workflow — KHÔNG còn fallback về chuỗi giả
        # "sdxl" (giá trị cũ chưa từng là tên file hợp lệ, chỉ là placeholder chết vì
        # trước đây field này không được dùng ở đâu cả). Rỗng → dùng `_CHECKPOINT_NAME`
        # (xem `_generate_locked`), giữ nguyên hành vi mặc định cho ai chưa cấu hình gì.
        self.model_name = model_name

    def generate(
        self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9",
        loras: list[dict] | None = None, extra_negative: str = "",
        reference_images: list[bytes] | None = None, style_reference_weight: float = 0.6,
    ) -> bytes:
        # gpu_lock: chặn chạy đồng thời với LLM local (Ollama)/Video local trên cùng GPU
        # — xem app/providers/gpu_lock.py + IMPLEMENTATION_REPORT.md mục 16.6b.
        # `loras`/`extra_negative`/`reference_images`/`style_reference_weight` — **mới
        # (2026-08-22, mở rộng 2026-08-23)** — KHÔNG khai báo trên `ImageProvider.
        # generate()` (base.py) như `seed`/`reference_image`/`aspect_ratio` vì đây là
        # khái niệm CHỈ có ý nghĩa với local_sdxl (Style LoRA/cultural lock/ảnh tham
        # chiếu IPAdapter từ BrandProfile, xem app/render/engine.py) — không muốn ép MỌI
        # provider khác (OpenAI/Gemini/Flux) nhận thêm tham số chết không dùng tới.
        # `reference_images` (SỐ NHIỀU, IPAdapter) KHÁC HẲN `reference_image` (SỐ ÍT,
        # img2img/anchor Tier 2 có sẵn) — 2 cơ chế ĐỘC LẬP, dùng CÙNG lúc được (IPAdapter
        # áp SAU LoRA lên model, img2img seed latent — không xung đột nhau).
        with gpu_lock:
            return self._generate_locked(
                prompt, seed=seed, reference_image=reference_image, aspect_ratio=aspect_ratio, loras=loras, extra_negative=extra_negative,
                reference_images=reference_images, style_reference_weight=style_reference_weight,
            )

    def _generate_locked(
        self, prompt: str, *, seed: int | None, reference_image: bytes | None, aspect_ratio: str = "16:9",
        loras: list[dict] | None = None, extra_negative: str = "",
        reference_images: list[bytes] | None = None, style_reference_weight: float = 0.6,
    ) -> bytes:
        if seed is None:
            seed = int(time.time() * 1000) % (2**31)
        client_id = str(uuid.uuid4())
        width, height = (_WIDTH_VERTICAL, _HEIGHT_VERTICAL) if aspect_ratio == "9:16" else (_WIDTH, _HEIGHT)
        ckpt_name = self.model_name or _CHECKPOINT_NAME

        def _build(*, with_ipadapter: bool, upload_client: httpx.Client) -> dict:
            style_ref_filenames = None
            if with_ipadapter and reference_images:
                style_ref_filenames = [self._upload_image(upload_client, img) for img in reference_images]
            if reference_image is not None:
                ref_filename = self._upload_image(upload_client, reference_image)
                return _build_img2img_workflow(
                    prompt=prompt, seed=seed, ref_filename=ref_filename, ckpt_name=ckpt_name, loras=loras, extra_negative=extra_negative,
                    width=width, height=height, style_reference_filenames=style_ref_filenames, style_reference_weight=style_reference_weight,
                )
            return _build_txt2img_workflow(
                prompt=prompt, seed=seed, ckpt_name=ckpt_name, loras=loras, extra_negative=extra_negative,
                width=width, height=height, style_reference_filenames=style_ref_filenames, style_reference_weight=style_reference_weight,
            )

        with httpx.Client(timeout=30) as client:
            workflow = _build(with_ipadapter=True, upload_client=client)
            resp = client.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": client_id})
            if resp.status_code >= 400:
                # Fallback (2026-08-23) — IPAdapter là custom node cộng đồng CHƯA verify
                # thật trên máy người dùng (xem docstring đầu file); nếu ComfyUI từ chối
                # (thường "node type not found" khi chưa cài đúng `ComfyUI_IPAdapter_
                # plus`/model), thử lại NGAY 1 lần KHÔNG IPAdapter thay vì chặn hẳn việc
                # sinh ảnh — ảnh vẫn ra được (đúng phong cách LoRA/prompt), chỉ thiếu
                # phần "ảnh tham chiếu".
                if reference_images:
                    workflow = _build(with_ipadapter=False, upload_client=client)
                    resp = client.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": str(uuid.uuid4())})
                if resp.status_code >= 400:
                    raise RuntimeError(f"ComfyUI từ chối job: HTTP {resp.status_code}: {resp.text[:500]}")
            prompt_id = resp.json()["prompt_id"]

        elapsed = 0.0
        with httpx.Client(timeout=30) as client:
            while elapsed < _POLL_TIMEOUT_SEC:
                resp = client.get(f"{self.base_url}/history/{prompt_id}")
                if resp.status_code == 200:
                    history = resp.json()
                    entry = history.get(prompt_id)
                    if entry:
                        # Bug thật (2026-08-23, phát hiện lúc viết test cho
                        # `GenerationInterrupted`): kiểm tra `status_str == "error"`
                        # TRƯỚC ĐÂY nằm LỒNG bên trong `if entry.get("outputs")` — job
                        # lỗi/bị Dừng THẬT SỰ hầu như KHÔNG BAO GIỜ có `outputs` (đó
                        # chính là ý nghĩa của "lỗi", chưa kịp render xong), nên nhánh
                        # raise KHÔNG BAO GIỜ chạy tới — job lỗi bị coi nhầm là "đang
                        # chạy" cho tới khi hết hẳn `_POLL_TIMEOUT_SEC` mới báo lỗi
                        # chung chung "không trả kết quả", che mất lý do lỗi thật. Kiểm
                        # tra `status_str` ĐỘC LẬP với `outputs`, TRƯỚC khi cần outputs.
                        if entry.get("status", {}).get("status_str") == "error":
                            raise_if_interrupted(entry["status"], prompt_id)
                            raise RuntimeError(f"ComfyUI báo lỗi khi chạy workflow: {entry['status']}")
                        if entry.get("outputs"):
                            image_info = self._first_image_output(entry["outputs"])
                            if image_info:
                                return self._download_image(client, image_info)
                time.sleep(_POLL_INTERVAL_SEC)
                elapsed += _POLL_INTERVAL_SEC

        raise RuntimeError(f"ComfyUI không trả kết quả trong {_POLL_TIMEOUT_SEC:.0f}s (job {prompt_id}).")

    def _upload_image(self, client: httpx.Client, image_bytes: bytes) -> str:
        """Tải ảnh anchor lên ComfyUI (`POST /upload/image`) để node `LoadImage` trong
        workflow đọc được — ComfyUI chỉ chấp nhận `LoadImage.image` là tên file đã có
        sẵn trong `input/` của chính nó, không nhận bytes trực tiếp qua workflow JSON."""
        files = {"image": ("anchor.png", image_bytes, "image/png")}
        resp = client.post(f"{self.base_url}/upload/image", files=files, data={"overwrite": "true"})
        if resp.status_code >= 400:
            raise RuntimeError(f"ComfyUI từ chối upload ảnh tham chiếu: HTTP {resp.status_code}: {resp.text[:500]}")
        info = resp.json()
        subfolder = info.get("subfolder") or ""
        return f"{subfolder}/{info['name']}" if subfolder else info["name"]

    def _first_image_output(self, outputs: dict) -> dict | None:
        for node_output in outputs.values():
            images = node_output.get("images")
            if images:
                return images[0]
        return None

    def _download_image(self, client: httpx.Client, image_info: dict) -> bytes:
        resp = client.get(
            f"{self.base_url}/view",
            params={"filename": image_info["filename"], "subfolder": image_info.get("subfolder", ""), "type": image_info.get("type", "output")},
        )
        resp.raise_for_status()
        return resp.content

    def test_connection(self) -> ProviderStatus:
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/system_stats")
                resp.raise_for_status()
            return ProviderStatus(ok=True, message="ComfyUI đang chạy (local)")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(
                ok=False,
                message=f"Không kết nối được tới ComfyUI ở {self.base_url}. Cần cài + chạy ComfyUI trước (xem IMPLEMENTATION_REPORT.md). Lỗi: {e}",
            )


def estimate_cost(image_count: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7).
    return 0.0


def list_comfyui_models(kind: str, base_url: str = "") -> list[str]:
    """Liệt kê file `.safetensors` THẬT đang có trong ComfyUI — **mới (2026-08-22)**, theo
    yêu cầu người dùng: cho CHỌN checkpoint/LoRA (dropdown) thay vì phải tự gõ đúng tên
    file (dễ gõ sai, không biết ComfyUI thật đang có file nào). `kind` = `"checkpoints"`
    hoặc `"loras"` — ComfyUI có sẵn 2 endpoint riêng `GET /models/{kind}`, xác nhận thật
    lúc điều tra đợt 2 cải thiện ảnh local (IMPLEMENTATION_REPORT.md mục 63/64). Dùng
    CHUNG cho cả `routers/providers.py` (chọn checkpoint cho provider `local_sdxl`) LẪN
    `routers/channels.py` (chọn Style LoRA cho BrandProfile, mục 64) — cùng 1 ComfyUI,
    cùng cơ chế liệt kê file, không cần 2 hàm riêng.

    Raise `RuntimeError` nếu ComfyUI không phản hồi được (chưa cài/chưa chạy) — router
    gọi hàm này tự dịch sang HTTP 502 kèm thông điệp rõ ràng, KHÔNG âm thầm trả danh sách
    rỗng (dễ gây hiểu nhầm "chưa có file nào" trong khi thực ra là chưa kết nối được)."""
    if kind not in ("checkpoints", "loras"):
        raise ValueError(f"kind không hợp lệ: {kind}")
    url = f"{(base_url or _DEFAULT_BASE_URL).rstrip('/')}/models/{kind}"
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Không lấy được danh sách {kind} từ ComfyUI ({url}): {e}") from e
