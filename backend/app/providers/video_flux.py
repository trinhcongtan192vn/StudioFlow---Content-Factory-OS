"""FLUX 3 Video (Black Forest Labs) — provider Video thật (đợt research 2026-08-16,
người dùng hỏi thẳng "Flux có dùng được để tạo video không?"). BẤT ĐỒNG BỘ đúng nghĩa
`VideoProvider` (start_generation/poll_generation, không phải generate() đồng bộ) — cơ
chế submit/poll ở tầng HTTP giống hệt Image (cùng hãng, cùng flux_common.py::submit),
nhưng `poll_generation()` ở đây CHỈ gọi 1 lần rồi trả về ngay (không tự lặp bên trong,
KHÔNG dùng `flux_common.poll_until_ready`) — vòng lặp chờ thật nằm ở
`render/engine.py::_poll_video_until_done`, đúng convention Sora/Veo (tránh block worker
thread quá lâu ở tầng adapter).

**Đánh giá "Flux có tạo được video không?" — CÓ.** FLUX 3 (ra mắt 23/7/2026) là model
multimodal đầu tiên của BFL vừa sinh ảnh vừa video (tới 20 giây/clip, có audio đồng bộ),
"generally available" qua API (không chỉ early access) tính tới lúc research 2026-08-16
— không phải hàng chờ/waitlist. Endpoint RIÊNG (`/v1/flux-3-video`), KHÁC hẳn dòng
FLUX.2 Image (`image_flux.py`) — 2 sản phẩm độc lập cùng hãng, KHÔNG phải "model ảnh
cũng tạo được video luôn". So sánh chất lượng công bố: FLUX 3 được người đánh giá chọn
hơn Luma Ray 3.2 (93% lượt so sánh) và Runway Gen-4.5 (77%) — đáng cân nhắc làm lựa chọn
video cloud chính, cạnh Sora/Veo đã có sẵn trong app.

**`generate_audio=False` CỐ ĐỊNH**: FLUX 3 Video sinh audio đồng bộ (thoại, SFX) ngay
trong clip — nhưng `render/assembly.py::_build_segment` LUÔN ghép `-map 0:v:0 -map
1:a:0` (chỉ lấy stream VIDEO từ asset, audio luôn lấy riêng từ narration TTS + không có
BGM overlay ở tầng shot) — audio BFL sinh ra sẽ bị bỏ hẳn lúc ghép, tắt hẳn để khỏi trả
phí/thời gian sinh audio vô ích (video-only rẻ hơn đáng kể theo bảng giá BFL).

Nguồn: docs.bfl.ai, OpenAPI spec api.bfl.ai/openapi.json (research 2026-08-16) — CHƯA
verify với API key thật, cùng mức rủi ro đã ghi ở video_veo.py/video_sora.py.
"""
import httpx

from app.providers.base import ProviderStatus, VideoProvider
from app.providers.flux_common import API_BASE, check_auth, headers, submit

# USD / giây — bảng giá FLUX 3 Video KHÔNG-draft, text-to-video/image-to-video
# (docs.bfl.ai/pricing, research 2026-08-16): $0.17/s (HD 720p), $0.29/s (FHD 1080p).
PRICE_PER_SECOND: dict[str, float] = {"flux-3-video-hd": 0.17, "flux-3-video-fhd": 0.29}
DEFAULT_PRICE_PER_SECOND = 0.17
_RESOLUTION_BY_MODEL = {"flux-3-video-hd": "hd", "flux-3-video-fhd": "fhd"}
_TERMINAL_FAILURE_STATUSES = {"Error", "Request Moderated", "Content Moderated", "Task not found"}


class FluxVideoProvider(VideoProvider):
    provider_name = "flux"

    def __init__(self, api_key: str = "", model_name: str = "flux-3-video-hd"):
        self.api_key = api_key
        self.model_name = model_name or "flux-3-video-hd"

    def generate(self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> bytes:
        raise NotImplementedError(
            "Flux Video là provider bất đồng bộ — dùng start_generation()/poll_generation() qua app/render/engine.py, không gọi generate() đồng bộ."
        )

    def start_generation(self, prompt: str, *, seconds: int = 8, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> str:
        # `aspect_ratio` (2026-08-21, project short-form) — nhận rồi KHÔNG dùng: OpenAPI
        # spec BFL research được (docs.bfl.ai/openapi.json) chỉ có `resolution` (tier
        # hd/fhd, KHÔNG phải orientation), không thấy tham số width/height/aspect_ratio
        # nào cho flux-3-video — coi như provider này CHƯA hỗ trợ khung dọc, giống
        # image_gemini.py, dựa vào crop-to-fill ở bước ghép MP4 để ra đúng khung 9:16.
        duration = max(5, min(20, seconds))  # FLUX 3 Video chỉ nhận 5-20s (rộng hơn 1 chút so với _video_duration_sec's 4s floor)
        body: dict = {
            "mode": "t2v",
            "prompt": prompt,
            "duration": duration,
            "resolution": _RESOLUTION_BY_MODEL.get(self.model_name, "hd"),
            "generate_audio": False,
        }
        if seed is not None:
            body["seed"] = seed
        with httpx.Client(timeout=30) as client:
            return submit(client, self.api_key, "flux-3-video", body)

    def poll_generation(self, job_id: str) -> tuple[str, bytes | None]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{API_BASE}/get_result", headers=headers(self.api_key), params={"id": job_id})
            if resp.status_code >= 400:
                raise RuntimeError(f"BFL lỗi khi poll job video {job_id}: HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            status = data.get("status", "")
            if status == "Ready":
                result = data.get("result") or {}
                sample_url = result.get("sample")
                if not sample_url:
                    raise RuntimeError(f"Flux Video báo Ready nhưng thiếu result.sample: {str(result)[:300]}")
                video_resp = client.get(sample_url)
                if video_resp.status_code >= 400:
                    raise RuntimeError(f"Không tải được video từ Flux (signed URL): HTTP {video_resp.status_code}")
                return "completed", video_resp.content
            if status in _TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(f"Flux Video job {job_id} thất bại (status={status}): {str(data.get('details') or data)[:500]}")
            return "processing", None

    def test_connection(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                ok, message = check_auth(client, self.api_key)
            return ProviderStatus(ok=ok, message=message)
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(seconds: int, model_name: str = "flux-3-video-hd") -> float:
    return seconds * PRICE_PER_SECOND.get(model_name, DEFAULT_PRICE_PER_SECOND)
