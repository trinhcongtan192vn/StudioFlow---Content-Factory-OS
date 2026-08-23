"""ComfyUI + Wan2.2 TI2V-5B — sinh video local qua GPU thật, chế độ TEXT-TO-VIDEO
thuần (không phải image-to-video). Bất đồng bộ như Sora/Veo (`start_generation`/
`poll_generation`, app/providers/base.py::VideoProvider) — gọi từ app/render/engine.py
trong background task.

**Vì sao Wan2.2 5B, không phải LTX-Video** (khác lựa chọn ban đầu của
`ai-content-studio/apps/backend/app/adapters/video_gen/comfy_ltx.py`):
`VideoProvider.start_generation(prompt, seconds)` của repo này CHỈ nhận prompt text
(app/render/engine.py gọi `provider.start_generation(prompt, seconds=seconds)`, không
có ảnh shot nào truyền vào) — bắt buộc text-to-video thuần. Wan2.2 TI2V-5B có workflow
mẫu CHÍNH THỨC từ ComfyUI (`Comfy-Org/workflow_templates` repo,
`templates/video_wan2_2_5B_ti2v.json`, native — không phải custom node cộng đồng dễ
lệch tên như IPAdapter/LTX), nhẹ hơn LTX (~8GB VRAM so với ~13GB), NHẸ hơn nữa vì đây
là **workflow được publish sẵn từ dev ComfyUI**, không phải tự đoán theo tài liệu.

**Cách bỏ ảnh input để chạy T2V thuần**: workflow mẫu chính thức thực ra là TI2V (ảnh +
text) — node `Wan22ImageToVideoLatent` nhận `start_image` qua `LoadImage`. Đọc thẳng
source ComfyUI (`comfy_extras/nodes_wan.py::Wan22ImageToVideoLatent.define_schema()`)
xác nhận `start_image` là `io.Image.Input("start_image", optional=True)` — bỏ hẳn input
này (không nối `LoadImage`), node tự khởi tạo latent từ noise thuần (xem
`execute()`: `if start_image is None: ... return io.NodeOutput(out_latent)`), tức chạy
đúng T2V mà không cần custom workflow riêng — chỉ bớt đi phần image trong đúng workflow
chính thức, độ tin cậy cao hơn hẳn so với dựng T2V graph từ đầu.

Node graph còn lại port nguyên từ template chính thức (`UNETLoader` → `ModelSamplingSD3`
shift=8 → `KSampler` uni_pc/simple/steps=20/cfg=5 → `VAEDecode` → `CreateVideo` fps=24 →
`SaveVideo`), CHƯA verify sống trên máy có GPU thật lúc code (đang tải checkpoint song
song) — nếu request/response hoặc tên node lệch so với bản ComfyUI cài thực tế, sửa lại
theo lỗi thật khi test (ghi vào IMPLEMENTATION_REPORT.md).
"""
import time
import uuid

import httpx

from app.providers.base import ProviderStatus, VideoProvider

_DEFAULT_BASE_URL = "http://127.0.0.1:8188"
_MODEL_NAME = "wan2.2_ti2v_5B_fp16.safetensors"
_CLIP_NAME = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
_VAE_NAME = "wan2.2_vae.safetensors"
_NEGATIVE_PROMPT = "blurry, low quality, distorted, static, watermark, text, worst quality, deformed"
_FPS = 24
_WIDTH, _HEIGHT = 1280, 704  # đúng mặc định template chính thức
# Hoán đổi W/H (cùng chia hết 16, an toàn cho Wan) — mới (2026-08-21), cho project
# short-form (9:16).
_WIDTH_VERTICAL, _HEIGHT_VERTICAL = 704, 1280


def _frames_for_seconds(seconds: int) -> int:
    """`Wan22ImageToVideoLatent.length` phải dạng 4k+1 (nén thời gian của VAE causal,
    step=4 theo schema node) — làm tròn về gần nhất, tối thiểu 5 khung (~0.2s)."""
    raw = max(1, round(seconds * _FPS))
    return max(5, ((raw - 1) // 4) * 4 + 1)


def _build_txt2vid_workflow(*, prompt: str, seed: int, num_frames: int, ref_filename: str | None = None, width: int = _WIDTH, height: int = _HEIGHT) -> dict:
    latent_node: dict = {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["39", 0], "width": width, "height": height, "length": num_frames, "batch_size": 1}}
    workflow = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": _MODEL_NAME, "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": _CLIP_NAME, "type": "wan", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": _VAE_NAME}},
        "48": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["37", 0], "shift": 8}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["38", 0], "text": _NEGATIVE_PROMPT}},
        "55": latent_node,
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["48", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["55", 0],
                "seed": seed, "steps": 20, "cfg": 5, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1,
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "57": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": _FPS}},
        "58": {"class_type": "SaveVideo", "inputs": {"video": ["57", 0], "filename_prefix": "studioflow_video", "format": "auto", "codec": "auto"}},
    }
    if ref_filename:
        # Nối `start_image` (optional, để trống ở nhánh T2V thuần — xem docstring) khi
        # có ảnh anchor — Tier 2: hoạt ảnh video mở đầu bám theo đúng ảnh shot IMAGE đầu
        # tiên của project thay vì khởi tạo latent từ noise thuần, giữ nhất quán phong
        # cách/nhân vật giữa shot ảnh và shot video trong cùng project.
        workflow["60"] = {"class_type": "LoadImage", "inputs": {"image": ref_filename}}
        workflow["61"] = {"class_type": "ImageScale", "inputs": {"image": ["60", 0], "width": width, "height": height, "upscale_method": "lanczos", "crop": "disabled"}}
        latent_node["inputs"]["start_image"] = ["61", 0]
    return workflow


class ComfyWanVideoProvider(VideoProvider):
    provider_name = "local_wan"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model_name or "wan2.2-ti2v-5b"

    def generate(self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> bytes:
        raise NotImplementedError(
            "Wan2.2 (qua ComfyUI) là provider bất đồng bộ — dùng start_generation()/poll_generation() qua app/render/engine.py, không gọi generate() đồng bộ."
        )

    def start_generation(self, prompt: str, *, seconds: int = 8, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> str:
        num_frames = _frames_for_seconds(seconds)
        if seed is None:
            seed = int(time.time() * 1000) % (2**31)
        width, height = (_WIDTH_VERTICAL, _HEIGHT_VERTICAL) if aspect_ratio == "9:16" else (_WIDTH, _HEIGHT)
        with httpx.Client(timeout=30) as client:
            ref_filename = self._upload_image(client, reference_image) if reference_image is not None else None
            workflow = _build_txt2vid_workflow(prompt=prompt, seed=seed, num_frames=num_frames, ref_filename=ref_filename, width=width, height=height)
            resp = client.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": str(uuid.uuid4())})
            if resp.status_code >= 400:
                raise RuntimeError(f"ComfyUI từ chối job video: HTTP {resp.status_code}: {resp.text[:500]}")
            return resp.json()["prompt_id"]

    def _upload_image(self, client: httpx.Client, image_bytes: bytes) -> str:
        """Cùng cơ chế `POST /upload/image` như `image_comfy_sdxl.py::_upload_image`
        (ComfyUI dùng chung endpoint cho mọi node `LoadImage`, không phân biệt ảnh/video)."""
        files = {"image": ("anchor.png", image_bytes, "image/png")}
        resp = client.post(f"{self.base_url}/upload/image", files=files, data={"overwrite": "true"})
        if resp.status_code >= 400:
            raise RuntimeError(f"ComfyUI từ chối upload ảnh tham chiếu: HTTP {resp.status_code}: {resp.text[:500]}")
        info = resp.json()
        subfolder = info.get("subfolder") or ""
        return f"{subfolder}/{info['name']}" if subfolder else info["name"]

    def poll_generation(self, job_id: str) -> tuple[str, bytes | None]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.base_url}/history/{job_id}")
            if resp.status_code != 200:
                return "processing", None
            history = resp.json()
            entry = history.get(job_id)
            if not entry:
                return "processing", None
            status_str = entry.get("status", {}).get("status_str")
            if status_str == "error":
                raise RuntimeError(f"ComfyUI báo lỗi khi chạy workflow video (job {job_id}): {entry['status']}")
            outputs = entry.get("outputs")
            if not outputs:
                return "processing", None
            video_info = self._first_video_output(outputs)
            if not video_info:
                return "processing", None
            data = self._download(client, video_info)
            return "completed", data

    def _first_video_output(self, outputs: dict) -> dict | None:
        # SaveVideo (io.ComfyNode kiểu mới) serialize UI qua PreviewVideo — vẫn dùng
        # chung key "images" như SaveImage (xem comfy_api/latest/_ui.py::PreviewVideo),
        # không phải "videos"/"gifs" như node kiểu cũ.
        for node_output in outputs.values():
            images = node_output.get("images")
            if images:
                return images[0]
        return None

    def _download(self, client: httpx.Client, info: dict) -> bytes:
        resp = client.get(
            f"{self.base_url}/view",
            params={"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")},
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


def estimate_cost(seconds: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7).
    return 0.0
