"""OpenAI Sora — provider Video đầu tiên thực thi sinh video THẬT (M2 Production
Layer). KHÁC HẲN TTS/Image: bất đồng bộ — gửi job, chờ 1-5+ phút, poll trạng thái,
tải kết quả khi xong. Dùng `start_generation`/`poll_generation` (app/providers/
base.py::VideoProvider), gọi từ app/render/engine.py trong background task — KHÔNG
gọi trực tiếp trong request handler.

CẢNH BÁO ĐỘ TIN CẬY: đây là điểm rủi ro cao nhất của M2 — request/response shape dưới
đây dựng theo pattern chung của các API job-based khác của OpenAI (submit → poll
status → tải kết quả), CHƯA được verify với key thật. Nếu request/response thực tế
lệch, sửa lại theo message lỗi thật trả về từ raise_for_status_with_body() khi người
dùng bấm thử trong Render Studio.
"""
import httpx

from app.providers.base import ProviderStatus, VideoProvider, raise_for_status_with_body

API_BASE = "https://api.openai.com/v1/videos"

# USD / giây video — theo bảng giá sora-2 720p đã research (specs/05_ai_providers.md).
PRICE_PER_SECOND = {
    "sora-2": 0.10,
    "sora-2-pro": 0.30,
}
DEFAULT_PRICE_PER_SECOND = 0.10


class SoraVideoProvider(VideoProvider):
    provider_name = "sora"

    def __init__(self, api_key: str = "", model_name: str = "sora-2"):
        self.api_key = api_key
        self.model_name = model_name or "sora-2"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def generate(self, prompt: str) -> bytes:
        raise NotImplementedError(
            "Sora là provider bất đồng bộ — dùng start_generation()/poll_generation() qua app/render/engine.py, không gọi generate() đồng bộ."
        )

    def start_generation(self, prompt: str, *, seconds: int = 8) -> str:
        body = {"model": self.model_name, "prompt": prompt, "seconds": str(seconds), "size": "1280x720"}
        with httpx.Client(timeout=30) as client:
            resp = client.post(API_BASE, headers=self._headers(), json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        return data["id"]

    def poll_generation(self, job_id: str) -> tuple[str, bytes | None]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{API_BASE}/{job_id}", headers=self._headers())
            raise_for_status_with_body(resp)
            data = resp.json()
        status = data.get("status", "unknown")
        if status != "completed":
            if status == "failed":
                raise RuntimeError(f"Sora job {job_id} thất bại: {data.get('error', 'không rõ lý do')}")
            return status, None
        with httpx.Client(timeout=120) as client:
            content_resp = client.get(f"{API_BASE}/{job_id}/content", headers=self._headers())
            raise_for_status_with_body(content_resp)
            return status, content_resp.content

    def test_connection(self) -> ProviderStatus:
        """Gọi GET /v1/models (miễn phí, dùng chung account OpenAI) thay vì submit 1
        job video thật — tránh tốn phí mỗi lần bấm "Test"."""
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {self.api_key}"})
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công (chưa xác nhận quyền truy cập Sora — chỉ verify API key hợp lệ)")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(seconds: int, model_name: str = "sora-2") -> float:
    return seconds * PRICE_PER_SECOND.get(model_name, DEFAULT_PRICE_PER_SECOND)
