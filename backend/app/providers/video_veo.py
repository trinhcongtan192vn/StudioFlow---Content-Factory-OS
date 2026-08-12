"""Google Veo — provider Video thứ 2 thực thi sinh video THẬT (đợt 2). BẤT ĐỒNG BỘ
như Sora (app/providers/video_sora.py) nhưng theo pattern "long-running operation"
riêng của Gemini API (khác REST job-polling của OpenAI):

  1. POST .../{model}:predictLongRunning -> trả {"name": "<operation name>"}
  2. GET .../{operation_name} lặp lại tới khi "done": true
  3. Kết quả nằm ở response.generateVideoResponse.generatedSamples[0].video.uri —
     GET riêng URI đó (kèm key) để tải bytes video thật.

CẢNH BÁO ĐỘ TIN CẬY — RỦI RO CAO NHẤT trong đợt này (tương tự Sora ở M2): request/
response shape trên suy luận theo tài liệu pattern chung "long-running operation" của
Gemini API, CHƯA verify với key thật lúc code. Nếu lệch, sửa theo message lỗi thật trả
về từ raise_for_status_with_body() khi thử trong Visual Studio.
"""
import httpx

from app.providers.base import ProviderStatus, VideoProvider, raise_for_status_with_body

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# USD / giây video — ước tính theo khoảng $0.05–$0.60/giây đã research ở M2
# (specs/05_ai_providers.md §8c), Veo 3.1 generate ở mức cao hơn fast.
PRICE_PER_SECOND: dict[str, float] = {
    "veo-3.1-generate-preview": 0.40,
    "veo-3.1-fast-generate-preview": 0.15,
}
DEFAULT_PRICE_PER_SECOND = 0.25


class VeoVideoProvider(VideoProvider):
    provider_name = "veo"

    def __init__(self, api_key: str = "", model_name: str = "veo-3.1-generate-preview"):
        self.api_key = api_key
        self.model_name = model_name or "veo-3.1-generate-preview"

    def generate(self, prompt: str) -> bytes:
        raise NotImplementedError(
            "Veo là provider bất đồng bộ — dùng start_generation()/poll_generation() qua app/render/engine.py, không gọi generate() đồng bộ."
        )

    def start_generation(self, prompt: str, *, seconds: int = 8) -> str:
        url = f"{API_BASE}/models/{self.model_name}:predictLongRunning?key={self.api_key}"
        body = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": "16:9", "durationSeconds": seconds}}
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=body)
            raise_for_status_with_body(resp)
            data = resp.json()
        name = data.get("name")
        if not name:
            raise RuntimeError(f"Veo không trả về operation name — response: {str(data)[:300]}")
        return name

    def poll_generation(self, job_id: str) -> tuple[str, bytes | None]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{API_BASE}/{job_id}?key={self.api_key}")
            raise_for_status_with_body(resp)
            data = resp.json()
        if not data.get("done"):
            return "processing", None
        error = data.get("error")
        if error:
            raise RuntimeError(f"Veo job {job_id} thất bại: {error.get('message', error)}")
        samples = (((data.get("response") or {}).get("generateVideoResponse") or {}).get("generatedSamples")) or []
        uri = (samples[0].get("video") or {}).get("uri") if samples else None
        if not uri:
            raise RuntimeError(f"Veo báo done nhưng không có video.uri trong response: {str(data)[:300]}")
        sep = "&" if "?" in uri else "?"
        with httpx.Client(timeout=120) as client:
            video_resp = client.get(f"{uri}{sep}key={self.api_key}")
            raise_for_status_with_body(video_resp)
            return "completed", video_resp.content

    def test_connection(self) -> ProviderStatus:
        """Gọi GET /v1beta/models (miễn phí) thay vì submit 1 job video thật."""
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{API_BASE}/models?key={self.api_key}")
                raise_for_status_with_body(resp)
            return ProviderStatus(ok=True, message="Kết nối thành công (chưa xác nhận quyền truy cập Veo — chỉ verify API key hợp lệ)")
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(ok=False, message=str(e))


def estimate_cost(seconds: int, model_name: str = "veo-3.1-generate-preview") -> float:
    return seconds * PRICE_PER_SECOND.get(model_name, DEFAULT_PRICE_PER_SECOND)
