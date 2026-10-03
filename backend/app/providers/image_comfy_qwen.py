"""ComfyUI + Qwen-Image-2.1 (local, GGUF quantized) — provider ảnh MỚI (2026-09-24), theo
yêu cầu người dùng: "muốn dùng model qwen image, nên chọn model nào phù hợp VRAM hiện tại
và cách triển khai" (RTX 5060 Ti, ~16GB — đã verify thật qua `system_stats`/comfy-mcp).

**Quyết định kiến trúc đã chốt lúc lên kế hoạch (hỏi trực tiếp người dùng qua nhiều vòng)**:
- Chọn **Qwen-Image-2.1** (Alibaba, 20/9/2026 — 7B tham số, benchmark cao hơn hẳn bản gốc
  20B) thay vì bản gốc — người dùng ĐÃ ĐƯỢC BÁO RÕ và CHẤP NHẬN rủi ro license
  **"Qwen Research" (chỉ dùng nghiên cứu, KHÔNG thương mại)** — khác bản gốc Apache 2.0.
  App đang dùng để vận hành kênh YouTube thật — người dùng tự chịu trách nhiệm quyết định
  này, KHÔNG phải app tự ý chọn.
- Cân nhắc rồi LOẠI BỎ Nunchaku NVFP4 (dù tận dụng đúng kiến trúc Blackwell của RTX 5060
  Ti, nhanh hơn GGUF) — verify thật xác nhận: (1) MIT HAN Lab (tác giả gốc Nunchaku,
  `github.com/mit-han-lab/ComfyUI-nunchaku`) CHƯA phát hành bản NVFP4 chính thức cho riêng
  2.1 (chỉ có bản gốc 20B) — bản cộng đồng (ModelsLab) yêu cầu `torch==2.12.1` (máy đang
  chạy `torch 2.8.0+cu129` — lệch 4 phiên bản) + không có wheel dựng sẵn cho Windows, phải
  build từ source (rủi ro cao, có thể hỏng Flux/SDXL/Wan đang chạy ổn cùng máy). Chọn
  **GGUF qua `ComfyUI-GGUF`** (custom node ĐÃ CÀI SẴN, đang dùng cho `local_flux` — xem
  `image_comfy_flux.py`) — không đổi gì môi trường hiện có.

**Đồ thị workflow — ĐÃ VERIFY THẬT qua GPU người dùng (2026-09-24)**, KHÔNG suy đoán:
1. Đọc trực tiếp template workflow CHÍNH THỨC từ Comfy-Org
   (`github.com/Comfy-Org/workflow_templates/.../image_qwen_image_2_1_t2i.json`) — nhưng
   phát hiện `TextEncodeQwenImage21` CHƯA có trong ComfyUI đang cài (core lúc đó chưa hỗ
   trợ 2.1, dù đã ra 4 ngày) — phải cập nhật ComfyUI core trước (`update_comfyui` qua
   comfy-mcp — gặp thêm trở ngại: có **2 bản ComfyUI khác nhau trên máy người dùng**, bản
   THẬT đang chạy là ComfyUI Windows portable (`C:\\Tools\\ComfyUI_extract\\
   ComfyUI_windows_portable`, tiến trình tên "python.exe" — dễ nhầm không có trong Task
   Manager), KHÁC bản comfy-cli tự quản lý riêng (`Documents\\comfy\\ComfyUI`, không dùng
   tới) — người dùng tự cập nhật bằng `update\\update_comfyui.bat` của đúng bản portable).
2. Đọc schema THẬT của `TextEncodeQwenImage21` qua `object_info` (không suy đoán tham số):
   nhận `clip`, `prompt`, `negative_prompt`, `resolution` (INT, mặc định 1024 — chỉ ảnh
   hưởng optional `latent` output của CHÍNH NÓ, KHÔNG dùng ở graph này), `images` (nhóm
   autogrow TỐI ĐA 16 ảnh tham chiếu — dùng cho edit/multi-reference, KHÔNG cần cho T2I
   thuần), `vae` (optional). Trả về CẢ `positive`+`negative` CONDITIONING (khác Flux dùng
   `CLIPTextEncode`+`ConditioningZeroOut` 2 node riêng) + 1 `latent` (KHÔNG DÙNG — xem
   dưới).
3. **Phát hiện quan trọng khi verify thật**: `comfy-cli validate_workflow` báo lỗi giả
   "`images` autogrow không có slot nào — server sẽ từ chối" nếu bỏ trống `images` — NHƯNG
   gọi THẲNG `POST /prompt` (bỏ qua lớp validate phía client của comfy-cli) cho thấy
   ComfyUI THẬT chấp nhận job bình thường, KHÔNG cần `images` — đã chạy xong job thật,
   ảnh ra đúng (fox trong tuyết, đúng prompt, đúng tỷ lệ 1344x768). Đây là hạn chế đã biết
   của validator phía client (over-strict cho nhóm autogrow), không phải giới hạn thật của
   ComfyUI — KHÔNG truyền `images` vào node này ở provider này.
4. Dùng `EmptyLatentImage` (core, TÁCH RIÊNG khỏi `latent` output của `TextEncodeQwenImage21`
   — xem bước 3 bên trên "QWEN IMAGE 2.1 T2I" workflow mẫu thật từ
   `realrebelai/Qwen-Image-2.1_GGUFs`, đã tải + đọc trực tiếp JSON, xác nhận node
   `EmptyLatentImage` với `width`/`height` riêng NHẬN ĐƯỢC nối vào `KSampler.latent_image`,
   KHÔNG dùng latent output của node text-encode) — cho phép kiểm soát tỷ lệ khung hình
   16:9/9:16 giống hệt cơ chế `local_sdxl`/`local_flux`, TÁI DÙNG đúng cặp `_WIDTH`/
   `_HEIGHT` đã verify tốt trong app.
5. `KSampler`: `steps=25, cfg=1.0, sampler_name="euler", scheduler="simple", denoise=1.0` —
   khớp CẢ 2 nguồn độc lập (template chính thức Comfy-Org LẪN workflow mẫu thật đã tải) —
   `cfg=1.0` đúng (không phải lỗi thiếu guidance như ban đầu nghi ngờ — Qwen-Image-2.1
   KHÔNG cần cfg thật như SDXL, guidance nằm trong chính model/text-encode).

**Model files** (đã tải THẬT + verify chạy được, đặt vào ĐÚNG thư mục ComfyUI portable
đang dùng — KHÔNG phải workspace comfy-cli riêng):
- `Qwen-Image-2.1-Q4.gguf` (5.96GB, `models/diffusion_models/`) — từ
  `huggingface.co/realrebelai/Qwen-Image-2.1_GGUFs` (repo CỘNG ĐỒNG — city96 chưa làm bản
  2.1, chỉ có bản gốc 20B — đã tự kiểm tra danh sách file THẬT qua HF API trước khi tải,
  KHÔNG tin mù tên file trong workflow mẫu vì phát hiện nó ghi SAI tên
  "Qwen-Image-2.1-Q4_K_M-HQv3.gguf" — tên thật trong repo chỉ là "Qwen-Image-2.1-Q4.gguf").
- `qwen3vl_8b_w4a8.safetensors` (6.31GB, `models/text_encoders/`) — CHÍNH THỨC từ
  `huggingface.co/Comfy-Org/Qwen-Image-2.1` (chọn bản W4A8 thay vì bf16 17.5GB/int8_convrot
  — cân bằng VRAM tốt nhất, đủ dư cho GGUF Q4 + VAE trong 16GB).
- `qwen_image_2.1_vae_bf16.safetensors` (0.68GB, `models/vae/`) — CHÍNH THỨC cùng repo
  Comfy-Org trên.
- Tổng VRAM ước tính ~13GB/16GB — dư nhiều hơn Flux hiện tại (~9.9GB) đang chạy ổn.

KHÔNG có LoRA/img2img/edit ở đợt này (`reference_image` nhận cho ĐỒNG NHẤT chữ ký
`ImageProvider.generate()` nhưng KHÔNG dùng — Qwen-Image-2.1 hỗ trợ multi-reference edit
thật qua chính `images` input của `TextEncodeQwenImage21`, để dành mở rộng sau nếu cần,
ngoài phạm vi yêu cầu ban đầu)."""
import time
import uuid

import httpx

from app.providers.base import ImageProvider, ProviderStatus, raise_if_interrupted
from app.providers.gpu_lock import gpu_lock

_DEFAULT_BASE_URL = "http://127.0.0.1:8188"
_UNET_GGUF_NAME = "Qwen-Image-2.1-Q4.gguf"
_CLIP_NAME = "qwen3vl_8b_w4a8.safetensors"
_VAE_NAME = "qwen_image_2.1_vae_bf16.safetensors"
_POLL_INTERVAL_SEC = 2.0
_POLL_TIMEOUT_SEC = 300.0
# Cùng cặp độ phân giải `local_sdxl`/`local_flux` đang dùng (~16:9 thật, đã verify tốt
# trong app) — TÁI DÙNG để nhất quán, không tự chọn số mới (xem docstring module).
_WIDTH = 1344
_HEIGHT = 768
_WIDTH_VERTICAL = 768
_HEIGHT_VERTICAL = 1344
# `steps=25` → `15` — **đổi 2026-09-24**, verify thật qua GPU người dùng: so sánh trực
# tiếp cùng seed/prompt ("fox trong tuyết") — 15 bước cho 41s/ảnh (so với ~68s ở 25 bước,
# nhanh hơn ~40%), chất lượng KHÔNG thấy khác biệt bằng mắt. Đổi mặc định thuần vì tốc độ,
# không phải bù đắp cho lỗi/thiếu gì — nếu sau này thấy prompt phức tạp cần chi tiết hơn,
# tăng lại qua hằng số này (chưa cho đổi qua Cài đặt — đủ dùng cho M1).
_STEPS = 15


def _build_txt2img_workflow(*, prompt: str, seed: int, unet_name: str, clip_name: str, vae_name: str, width: int = _WIDTH, height: int = _HEIGHT) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet_name}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "qwen_image"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        # KHÔNG truyền `images` — nhóm autogrow chỉ cần cho multi-reference edit, KHÔNG
        # cần cho T2I thuần (đã verify thật gọi thẳng /prompt, xem docstring module mục 3).
        "6": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["4", 0], "prompt": prompt, "negative_prompt": "", "resolution": 1024}},
        "10": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "positive": ["6", 0], "negative": ["6", 1], "latent_image": ["10", 0],
                "seed": seed, "steps": _STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["5", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studioflow_qwen", "images": ["9", 0]}},
    }


class ComfyQwenImageProvider(ImageProvider):
    provider_name = "local_qwen"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        # Tên file UNet GGUF THẬT — rỗng dùng `_UNET_GGUF_NAME` mặc định. Text encoder/VAE
        # CHƯA cho đổi qua Cài đặt (chỉ 1 lựa chọn chính thức phù hợp VRAM đã chọn — xem
        # docstring module) — đủ dùng cho M1, mở rộng sau nếu cần đổi.
        self.model_name = model_name

    def generate(
        self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9",
    ) -> bytes:
        # `reference_image` nhận cho ĐỒNG NHẤT chữ ký nhưng KHÔNG dùng — xem docstring
        # module (multi-reference edit thật của Qwen-Image-2.1 để dành mở rộng sau).
        with gpu_lock:
            return self._generate_locked(prompt, seed=seed, aspect_ratio=aspect_ratio)

    def _generate_locked(self, prompt: str, *, seed: int | None, aspect_ratio: str = "16:9") -> bytes:
        if seed is None:
            seed = int(time.time() * 1000) % (2**31)
        client_id = str(uuid.uuid4())
        width, height = (_WIDTH_VERTICAL, _HEIGHT_VERTICAL) if aspect_ratio == "9:16" else (_WIDTH, _HEIGHT)
        unet_name = self.model_name or _UNET_GGUF_NAME
        workflow = _build_txt2img_workflow(prompt=prompt, seed=seed, unet_name=unet_name, clip_name=_CLIP_NAME, vae_name=_VAE_NAME, width=width, height=height)

        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": client_id})
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
                        # Cùng bug thật đã sửa cho local_sdxl/local_flux — kiểm tra
                        # status_str=="error" TRƯỚC, độc lập với outputs.
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
            return ProviderStatus(ok=True, message="ComfyUI đang chạy (local) — CHƯA xác nhận có UnetLoaderGGUF/checkpoint Qwen-Image-2.1, chỉ kiểm tra kết nối ComfyUI cơ bản.")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(
                ok=False,
                message=f"Không kết nối được tới ComfyUI ở {self.base_url}. Cần cài + chạy ComfyUI + custom node ComfyUI-GGUF trước (xem IMPLEMENTATION_REPORT.md). Lỗi: {e}",
            )


def estimate_cost(image_count: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7).
    return 0.0


def list_comfyui_models(kind: str, base_url: str = "") -> list[str]:
    """Liệt kê file `.safetensors`/`.gguf` THẬT đang có trong ComfyUI — **chuyển sang đây
    (2026-09-24, dọn dẹp xoá 5 provider local cũ)** từ `image_comfy_sdxl.py` (đã xoá) —
    hàm này KHÔNG hề đổi hành vi, chỉ đổi chỗ ở vì `local_qwen` giờ là provider ComfyUI
    DUY NHẤT còn lại cần dropdown "Model" (`kind="unet_gguf"`). `kind="checkpoints"`/
    `"loras"` vẫn giữ nguyên hỗ trợ (không dùng ở app hiện tại nhưng vô hại, không lý do
    xoá 1 nhánh generic của hàm đọc thẳng từ ComfyUI). ComfyUI có sẵn endpoint riêng
    `GET /models/{kind}` cho từng loại — xác nhận thật lúc điều tra đợt cải thiện ảnh local
    (IMPLEMENTATION_REPORT.md mục 63/64).

    Raise `RuntimeError` nếu ComfyUI không phản hồi được (chưa cài/chưa chạy) — router
    gọi hàm này tự dịch sang HTTP 502 kèm thông điệp rõ ràng, KHÔNG âm thầm trả danh sách
    rỗng (dễ gây hiểu nhầm "chưa có file nào" trong khi thực ra là chưa kết nối được)."""
    if kind not in ("checkpoints", "loras", "unet_gguf"):
        raise ValueError(f"kind không hợp lệ: {kind}")
    url = f"{(base_url or _DEFAULT_BASE_URL).rstrip('/')}/models/{kind}"
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Không lấy được danh sách {kind} từ ComfyUI ({url}): {e}") from e
