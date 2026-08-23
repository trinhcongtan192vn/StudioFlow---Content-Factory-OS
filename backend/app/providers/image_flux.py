"""FLUX (Black Forest Labs) Image — provider Image thật, thay thế stub cũ ở stubs.py
(đợt research 2026-08-16, theo yêu cầu người dùng "đảm bảo model dùng là model phù hợp
nhất đang có trên thị trường"). BẤT ĐỒNG BỘ ở tầng HTTP (submit → poll, xem
flux_common.py) nhưng `generate()` vẫn ĐỒNG BỘ (block tới khi xong) để khớp
`ImageProvider.generate()` — cùng cách `render/engine.py::generate_visual_asset` đã gọi
cho OpenAI/Gemini Image (chạy trong background task, block ở đây không sao).

**Model mặc định — `flux-2-pro`** (KHÔNG phải `-preview`): research 2026-08-16 xác nhận
FLUX.2 là thế hệ hiện hành của BFL (thay FLUX.1/FLUX1.1 Kontext cũ — catalog cũ ở
stubs.py/frontend ghi "flux-1.1-pro" đã lỗi thời), `[pro]` là mức cân bằng chất lượng/
giá tốt nhất cho ảnh chụp thật (mô tả là dẫn đầu photorealism 2026). `-preview` là alias
LUÔN TRỎ TỚI BẢN MỚI NHẤT (có thể đổi hành vi bất ngờ giữa các lần gọi khác nhau) trong
khi tên KHÔNG có `-preview` là bản ĐÓNG BĂNG (pinned) — chọn bản pinned để kết quả ổn
định, đúng khuyến nghị tái lập kết quả của chính BFL. `[max]` chất lượng cao hơn nữa
(~2.3x giá `[pro]`) — expose qua `model_name` để người dùng tự đổi nếu cần, không ép mặc
định vì tăng chi phí/project không nhỏ (project dài có 10-20 shot ảnh).

Nguồn: docs.bfl.ai, OpenAPI spec api.bfl.ai/openapi.json (research trực tiếp lúc code,
2026-08-16) — CHƯA verify với API key thật (không có key), theo đúng quy ước ghi rõ độ
tin cậy như video_veo.py/video_sora.py.
"""
import base64

import httpx

from app.providers.base import ImageProvider, ProviderStatus
from app.providers.flux_common import check_auth, submit, poll_until_ready

# USD / megapixel — bảng giá BFL FLUX.2 text-to-image (docs.bfl.ai/pricing, research
# 2026-08-16). Khác OpenAI/Gemini (giá cố định/ảnh) — Flux tính theo diện tích thật.
PRICE_PER_MP: dict[str, float] = {
    "flux-2-klein-4b": 0.014,
    "flux-2-klein-9b": 0.015,
    "flux-2-pro": 0.03,
    "flux-2-flex": 0.05,
    "flux-2-max": 0.07,
}
DEFAULT_PRICE_PER_MP = 0.03

# ~16:9 (1.76), chia hết 32 (an toàn trong giới hạn kích thước đã biết chắc của dòng
# Flux Pro cũ, 256-1440/cạnh — BFL chưa công bố giới hạn riêng cho FLUX.2 lúc research
# nên giữ trong vùng đã xác nhận hoạt động thay vì đoán rộng hơn).
_WIDTH, _HEIGHT = 1408, 800
# Hoán đổi W/H — cùng diện tích (megapixel, nên giá không đổi), chia hết 32 — mới
# (2026-08-21), cho project short-form (9:16).
_WIDTH_VERTICAL, _HEIGHT_VERTICAL = 800, 1408
_MEGAPIXELS = (_WIDTH * _HEIGHT) / 1_000_000
_POLL_TIMEOUT_SEC = 180.0


class FluxImageProvider(ImageProvider):
    provider_name = "flux"

    def __init__(self, api_key: str = "", model_name: str = "flux-2-pro"):
        self.api_key = api_key
        self.model_name = model_name or "flux-2-pro"

    def generate(self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> bytes:
        width, height = (_WIDTH_VERTICAL, _HEIGHT_VERTICAL) if aspect_ratio == "9:16" else (_WIDTH, _HEIGHT)
        body: dict = {"prompt": prompt, "width": width, "height": height}
        if seed is not None:
            body["seed"] = seed
        if reference_image is not None:
            # FLUX.2 nhận ảnh tham chiếu qua input_image (base64) — dùng cho Tier 2 nếu
            # bật lại sau này (hiện tắt toàn app, xem IMPLEMENTATION_REPORT.md mục 21).
            body["input_image"] = base64.b64encode(reference_image).decode("ascii")
        with httpx.Client(timeout=30) as client:
            request_id = submit(client, self.api_key, self.model_name, body)
            result = poll_until_ready(client, self.api_key, request_id, timeout_sec=_POLL_TIMEOUT_SEC)
            sample_url = result.get("sample")
            if not sample_url:
                raise RuntimeError(f"Flux báo Ready nhưng không có result.sample: {str(result)[:300]}")
            img_resp = client.get(sample_url)
            if img_resp.status_code >= 400:
                raise RuntimeError(f"Không tải được ảnh từ Flux (signed URL): HTTP {img_resp.status_code}")
            return img_resp.content

    def test_connection(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                ok, message = check_auth(client, self.api_key)
            return ProviderStatus(ok=ok, message=message)
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(image_count: int, model_name: str = "flux-2-pro") -> float:
    return image_count * _MEGAPIXELS * PRICE_PER_MP.get(model_name, DEFAULT_PRICE_PER_MP)
