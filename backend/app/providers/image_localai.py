"""LocalAI (github.com/mudler/LocalAI) — sinh ảnh local qua GPU thật, thay thế ComfyUI
(`image_comfy_sdxl.py`) — **mới (2026-08-25)**, theo `CHANGE_LocalAI_Migration.md`
(người dùng đưa) + kế hoạch migrate đã duyệt (xem plan). API OpenAI-compatible
(`POST /v1/images/generations`, response `data: [{b64_json}]`) — tái dùng đúng pattern
parse đã có ở `image_openai.py`, KHÁC hẳn `image_comfy_sdxl.py` (không cần build
node-graph JSON thủ công).

**ĐANG SONG SONG với `image_comfy_sdxl.py` (`local_sdxl`)** — theo quyết định "additive
trước, xoá ComfyUI sau khi verify thật qua GPU" (xem Cổng verify trong plan). File
`image_comfy_sdxl.py` KHÔNG bị xoá ở đợt này.

**Khác biệt kiến trúc quan trọng so với ComfyUI (per-request node injection)**:
LocalAI KHÔNG nhận LoRA/negative-prompt tuỳ ý mỗi request qua workflow JSON — LoRA là
khái niệm THUỘC VỀ 1 model đã ĐĂNG KÝ (`lora_adapters`/`lora_scales` trong YAML config
hoặc qua API quản lý model runtime `POST /models/apply`), không phải tham số sinh ảnh
per-call. `loras` (kwarg giữ NGUYÊN chữ ký như `ComfySDXLImageProvider.generate()` cho
tương thích `app/render/engine.py`) ở đây dùng để ĐỒNG BỘ 1 "model ảo" cố định tên theo
kênh (`_virtual_model_name`) — mỗi lần set LoRA THẬT SỰ đổi (so với lần gọi đồng bộ gần
nhất, cache trong `self._synced_lora_signature`) mới gọi lại API đồng bộ, tránh gọi thừa
mỗi lần sinh 1 shot.

**Ảnh tham chiếu phong cách (`reference_images`/`style_reference_weight`, thay IPAdapter
cũ) — đợt 2 (2026-08-25), qua img2img** (**KHÔNG PHẢI** IPAdapter — đợt 1 từng kết luận
"không có đường sang LocalAI", đợt 2 người dùng đưa research xác nhận LocalAI CÓ hỗ trợ
img2img trên chính checkpoint SDXL đang dùng, `pipeline_type: StableDiffusionImg2ImgPipeline`
+ field `image`). Khác IPAdapter cũ (điều kiện hoá MODEL, nhận nhiều ảnh, tách phong
cách khỏi bố cục) — img2img SEED LATENT bằng đúng 1 ảnh (chỉ dùng
`reference_images[0]`, bỏ qua ảnh còn lại nếu có nhiều — img2img LocalAI chỉ nhận 1
ảnh/lần), bố cục/màu ảnh gốc ảnh hưởng TRỰC TIẾP — CÙNG rủi ro đã gặp ở "Tier 2 anchor"
cũ trên ComfyUI (`image_comfy_sdxl.py::_IMG2IMG_DENOISE`, đã TẮT vì ảnh tham chiếu nhiều
chi tiết đồ hoạ dễ bị copy nguyên khung/chữ). Đăng ký RIÊNG 1 model img2img
(`_virtual_model_name(img2img=True)`) qua CÙNG cơ chế `/models/apply` đã có cho model
txt2img — cùng checkpoint+LoRA, chỉ khác `pipeline_type`.

**CHƯA verify thật trên LocalAI (khác mọi adapter ComfyUI trong codebase, đều đã verify
qua GPU thật trước khi coi là xong)** — các điểm cụ thể cần xác nhận lúc người dùng test
thật, đã ghi rõ trong code bên dưới thay vì suy đoán cứng:
1. Tên field negative-prompt của `/v1/images/generations` — đang dùng `negative_prompt`,
   độ tin cậy TĂNG đợt 2 (tài liệu `/video` chính thức xác nhận đúng tên field này cho
   video, cùng quy ước LocalAI) nhưng vẫn CHƯA verify trực tiếp cho endpoint ảnh.
2. Path/shape chính xác của API quản lý model runtime (`/models/apply`) — đang dùng
   đúng theo tài liệu LocalAI đọc được, CHƯA verify request/response thật.
3. `pipeline_type` chính xác cho img2img SDXL — tài liệu LocalAI chỉ có ví dụ SD1.5
   (`StableDiffusionImg2ImgPipeline`), đang GIẢ ĐỊNH biến thể XL là
   `StableDiffusionXLImg2ImgPipeline` (quy ước đặt tên chuẩn của thư viện `diffusers`,
   KHÔNG phải xác nhận trực tiếp từ tài liệu LocalAI) — CHƯA verify.
"""
from __future__ import annotations

import base64
import logging

import httpx

from app.providers.base import ImageProvider, ProviderStatus, raise_for_status_with_body
from app.providers.gpu_lock import gpu_lock

_DEFAULT_BASE_URL = "http://127.0.0.1:8080"
_TIMEOUT_SEC = 180.0

logger = logging.getLogger(__name__)


class LocalAIImageProvider(ImageProvider):
    provider_name = "localai_image"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        # Tên model ĐÃ ĐĂNG KÝ trong LocalAI (YAML `models.d/` hoặc qua API) — KHÁC
        # `local_sdxl` (tên file checkpoint .safetensors trực tiếp) vì LocalAI gọi model
        # theo TÊN LOGIC, không theo đường dẫn file. Rỗng → dùng `_virtual_model_name`
        # (đồng bộ động, xem bên dưới) làm tên model mặc định.
        self.model_name = model_name
        # Cache chữ ký LoRA đã đồng bộ lần gần nhất, RIÊNG theo model (txt2img/img2img
        # là 2 model KHÁC NHAU trong LocalAI, dù cùng checkpoint+LoRA) — tránh gọi
        # `/models/apply` thừa mỗi lần sinh 1 shot khi BrandProfile.style_loras không
        # đổi giữa các lần gọi. Key = tên model, value = chữ ký LoRA đã đồng bộ.
        self._synced_lora_signatures: dict[str, tuple] = {}

    def generate(
        self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9",
        loras: list[dict] | None = None, extra_negative: str = "",
        reference_images: list[bytes] | None = None, style_reference_weight: float = 0.6,
    ) -> bytes:
        # gpu_lock — cùng lý do đã áp cho `local_sdxl`: LocalAI chạy CHUNG 1 process cho
        # LLM+ảnh+video (khác 2 process tách biệt Ollama/ComfyUI trước đây), nhưng CHƯA
        # có bằng chứng LocalAI tự xử lý tốt nhiều request đồng thời trên 1 GPU — giữ
        # khoá cho an toàn, chấp nhận có thể hơi thừa nếu sau này xác nhận LocalAI tự
        # queue tốt (xem gpu_lock.py).
        with gpu_lock:
            return self._generate_locked(
                prompt, seed=seed, aspect_ratio=aspect_ratio, loras=loras, extra_negative=extra_negative,
                reference_images=reference_images, style_reference_weight=style_reference_weight,
            )

    def _generate_locked(
        self, prompt: str, *, seed: int | None, aspect_ratio: str, loras: list[dict] | None, extra_negative: str,
        reference_images: list[bytes] | None = None, style_reference_weight: float = 0.6,
    ) -> bytes:
        # CHỈ ảnh ĐẦU TIÊN được dùng — img2img LocalAI nhận đúng 1 ảnh/lần (xem docstring
        # đầu file), khác thiết kế nhiều-ảnh của IPAdapter cũ. Ảnh còn lại (nếu người
        # dùng lỡ upload nhiều qua UI cũ trước khi UI đổi thành 1 ô) bị bỏ qua im lặng.
        reference_image_bytes = reference_images[0] if reference_images else None
        use_img2img = reference_image_bytes is not None
        model_name = self._sync_model(loras, img2img=use_img2img)
        size = "768x1344" if aspect_ratio == "9:16" else "1344x768"
        body: dict = {"model": model_name, "prompt": prompt, "size": size}
        if seed is not None:
            body["seed"] = seed
        if extra_negative:
            # Xem docstring đầu file mục (1) — tên field CHƯA verify thật, dùng quy ước
            # phổ biến nhất của pipeline diffusers OpenAI-compatible.
            body["negative_prompt"] = extra_negative
        if use_img2img:
            body["image"] = base64.b64encode(reference_image_bytes).decode("ascii")
            # `strength` (diffusers img2img) — HƯỚNG NGƯỢC `style_reference_weight`:
            # `strength` cao = THÊM NHIỀU nhiễu = ÍT giữ ảnh gốc (1.0 gần như bỏ qua hẳn
            # ảnh); `style_reference_weight` cao = người dùng muốn ảnh hưởng phong cách
            # NHIỀU = cần `strength` THẤP hơn. Khoảng [0.3, 0.85] mượn kinh nghiệm tune
            # thật cho Tier 2 ComfyUI (`image_comfy_sdxl.py::_IMG2IMG_DENOISE=0.7` —
            # "0.45/0.25 gần như copy nguyên ảnh gốc, 0.8 gần như bỏ qua hẳn anchor") —
            # CHƯA verify lại trên LocalAI thật, chỉ là điểm khởi đầu hợp lý.
            body["strength"] = max(0.3, min(0.85, 1.0 - style_reference_weight))
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            resp = client.post(f"{self.base_url}/v1/images/generations", json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        b64 = data["data"][0]["b64_json"]
        return base64.b64decode(b64)

    def _virtual_model_name(self, *, img2img: bool = False) -> str:
        """Tên model "ảo" dùng khi `self.model_name` rỗng — đồng bộ động theo LoRA hiện
        tại của BrandProfile (xem `_sync_model`), KHÔNG cố định 1 checkpoint như
        `local_sdxl`. `img2img=True` trả tên RIÊNG (model KHÁC trong LocalAI — cùng
        checkpoint+LoRA nhưng `pipeline_type` khác, xem `_apply_model`) dùng khi có ảnh
        tham chiếu phong cách. Không theo kênh (provider này không biết `channel_id`,
        `engine.py` chỉ truyền `model_name` qua constructor) — ĐỦ DÙNG cho single-user 1
        kênh active tại 1 thời điểm; nếu sau này cần multi-kênh đồng thời, cần truyền
        `channel_id` riêng vào đây."""
        return "studioflow-sdxl-img2img" if img2img else "studioflow-sdxl"

    def _sync_model(self, loras: list[dict] | None, *, img2img: bool = False) -> str:
        """Đồng bộ LoRA hiện tại vào model LocalAI TRƯỚC khi sinh — CHỈ gọi API khi chữ
        ký LoRA (tên+trọng số, sắp theo thứ tự) THỰC SỰ đổi so với lần gọi gần nhất CHO
        ĐÚNG MODEL đó (cache `self._synced_lora_signatures`, theo tên model — txt2img và
        img2img đồng bộ ĐỘC LẬP nhau vì là 2 model khác nhau trong LocalAI), tránh gọi
        `/models/apply` thừa mỗi lần sinh 1 shot.

        Nếu `self.model_name` đã cấu hình sẵn (người dùng tự đăng ký model qua YAML,
        không muốn app tự quản lý) — dùng THẲNG tên đó cho CẢ 2 trường hợp (txt2img và
        img2img), KHÔNG tự đồng bộ LoRA qua API (tôn trọng cấu hình thủ công — người
        dùng tự chịu trách nhiệm model đó có đúng `pipeline_type` img2img hay không nếu
        dùng ảnh tham chiếu)."""
        if self.model_name:
            return self.model_name
        model_name = self._virtual_model_name(img2img=img2img)
        signature = tuple((lora.get("name", ""), lora.get("strength", 0.8)) for lora in (loras or []))
        if signature == self._synced_lora_signatures.get(model_name):
            return model_name
        try:
            self._apply_model(model_name, loras or [], img2img=img2img)
            self._synced_lora_signatures[model_name] = signature
        except Exception as e:  # noqa: BLE001
            # Best-effort — đồng bộ LoRA lỗi (VD API path lệch, xem docstring đầu file
            # mục (2)) KHÔNG được chặn việc sinh ảnh; ảnh vẫn ra được bằng model đã đăng
            # ký sẵn (dù có thể chưa đúng LoRA mới nhất), tốt hơn chặn hẳn shot.
            logger.warning("Đồng bộ LoRA vào LocalAI model '%s' lỗi (%s) — sinh ảnh bằng cấu hình model hiện có.", model_name, e)
        return model_name

    def _apply_model(self, model_name: str, loras: list[dict], *, img2img: bool = False) -> None:
        """Đăng ký/cập nhật model `model_name` trong LocalAI qua API quản lý model
        runtime — CHƯA verify thật (xem docstring đầu file mục 2). Theo tài liệu LocalAI
        đọc được: `POST /models/apply` áp dụng 1 model definition, hỗ trợ chỉnh sửa
        runtime không cần restart. `img2img=True` thêm `pipeline_type` — xem docstring
        đầu file mục (3), CHƯA verify tên class chính xác cho SDXL."""
        overrides: dict = {
            "backend": "diffusers",
            "parameters": {"model": self._base_checkpoint_name()},
            "lora_adapters": [lora.get("name", "") for lora in loras],
            "lora_scales": [lora.get("strength", 0.8) for lora in loras],
        }
        if img2img:
            overrides["pipeline_type"] = "StableDiffusionXLImg2ImgPipeline"
        body = {"id": model_name, "name": model_name, "overrides": overrides}
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/models/apply", json=body)
            raise_for_status_with_body(resp)

    def _base_checkpoint_name(self) -> str:
        """Checkpoint nền dùng khi đăng ký model ảo — CÙNG checkpoint mặc định đã chọn
        cho `local_sdxl` (`paintersCheckpointOilPaint_v11.safetensors`, xem
        `image_comfy_sdxl.py::_CHECKPOINT_NAME`) để giữ nhất quán phong cách khi chuyển
        đổi giữa 2 provider trong lúc verify."""
        from app.providers.image_comfy_sdxl import _CHECKPOINT_NAME

        return _CHECKPOINT_NAME

    def test_connection(self) -> ProviderStatus:
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/v1/models")
                resp.raise_for_status()
            return ProviderStatus(ok=True, message="LocalAI đang chạy (local)")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(
                ok=False,
                message=f"Không kết nối được tới LocalAI ở {self.base_url}. Cần cài + chạy LocalAI trước. Lỗi: {e}",
            )


def estimate_cost(image_count: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7).
    return 0.0


def list_localai_models(base_url: str = "") -> list[str]:
    """Liệt kê model ĐÃ ĐĂNG KÝ trong LocalAI (`GET /v1/models`, OpenAI-compatible) —
    dùng cho dropdown "Model" ở Cài đặt → Provider AI, tương tự `list_comfyui_models()`
    (`image_comfy_sdxl.py`) nhưng khác nguồn: đây là DANH SÁCH MODEL LOGIC đã đăng ký
    (YAML hoặc qua `/models/apply`), KHÔNG PHẢI file checkpoint thô trên đĩa (ComfyUI có
    endpoint liệt kê file trực tiếp, LocalAI thì không — model phải đăng ký trước mới
    liệt kê được).

    Raise `RuntimeError` nếu LocalAI không phản hồi được — router gọi hàm này tự dịch
    sang HTTP 502, cùng convention `list_comfyui_models()`."""
    url = f"{(base_url or _DEFAULT_BASE_URL).rstrip('/')}/v1/models"
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Không lấy được danh sách model từ LocalAI ({url}): {e}") from e
