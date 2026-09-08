"""LocalAI (github.com/mudler/LocalAI) — sinh video local qua GPU thật (Wan2.2), thay
thế ComfyUI (`video_comfy_wan.py`) — **mới (2026-08-25)**, theo
`CHANGE_LocalAI_Migration.md` + kế hoạch migrate đã duyệt. Hỗ trợ image-to-video qua
field `start_image`, khớp cơ chế ảnh anchor per-shot đã build ở
`app/render/engine.py::_try_generate_wan_anchor_image` (KHÔNG đổi cơ chế đó, chỉ đổi nơi
ảnh anchor được gửi tới).

**ĐANG SONG SONG với `video_comfy_wan.py` (`local_wan`)** — cùng nguyên tắc additive đã
ghi ở `image_localai.py`, KHÔNG xoá `video_comfy_wan.py` ở đợt này.

**Đợt 2 (2026-08-25) — SỬA LẠI TOÀN BỘ so với đợt 1**: đợt 1 code theo SUY ĐOÁN
(`POST /v1/videos`, field `input_reference`, nhánh job-poll bất đồng bộ) vì lúc đó chưa
có tài liệu LocalAI chính thức cho video. Người dùng đưa bản research xác nhận THẬT qua
`localai.io/docs/features/video-generation/` — endpoint đúng là:

- `POST {base_url}/video` (**KHÔNG có tiền tố `/v1`** — khác `/v1/images/generations`
  của ảnh, khác giả định `/v1/videos` đợt 1).
- Field: `model`, `prompt`, `negative_prompt`, `start_image` (base64/data-URI/URL —
  dùng data-URI, khớp cách `image_localai.py` không cần endpoint upload riêng), `width`/
  `height`, `seconds` (đơn giản hơn tự tính `num_frames`/`fps` như code Wan cũ —
  LocalAI/backend Wan tự lo phần đó), `seed`, `response_format` (`"url"` mặc định hoặc
  `"b64_json"` — CHỌN `"b64_json"` để khỏi phải tải thêm request tới `url`).
- **Response ĐỒNG BỘ** (`{created, id, data: [{url}]}` hoặc `[{b64_json}]`) — KHÔNG cần
  poll job. Nhánh "job bất đồng bộ GET /v1/videos/{job_id}" của đợt 1 đã XOÁ HẲN — sai
  hoàn toàn theo bằng chứng mới, không phải chỉ 1 khả năng cần dự phòng nữa.

**CHƯA verify được** (khác mọi tính năng ComfyUI trong dự án, đều verify qua GPU thật):
bản thân chất lượng/tốc độ sinh video Wan2.2 QUA LocalAI's backend — endpoint/field đã
CONFIRM qua tài liệu chính thức (không còn thuần suy đoán), nhưng hành vi thật (model có
nạp đúng không, `start_image` có hoạt động đúng ý image-to-video không) cần người dùng
tự test qua GPU thật (xem Cổng verify trong plan)."""
from __future__ import annotations

import base64
import time

import httpx

from app.providers.base import ProviderStatus, VideoProvider

_DEFAULT_BASE_URL = "http://127.0.0.1:8080"
_MODEL_NAME = "wan2.2-ti2v-5b"
_WIDTH, _HEIGHT = 1344, 768
_WIDTH_VERTICAL, _HEIGHT_VERTICAL = 768, 1344


class LocalAIVideoProvider(VideoProvider):
    provider_name = "localai_video"

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self.model_name = model_name or _MODEL_NAME
        # Response `/video` ĐỒNG BỘ (xác nhận thật, xem docstring) — không có job thật
        # để poll, nhưng `VideoProvider` interface (base.py) vẫn theo mô hình
        # start_generation()→job_id, poll_generation(job_id)→(status, bytes). Cache
        # bytes tải xong NGAY ở `start_generation` theo job_id GIẢ tự sinh
        # (`sync:{uuid}`), `poll_generation` đọc ra rồi xoá khỏi cache — giữ tương thích
        # `engine.py::_poll_video_until_done` mà không cần sửa gì ở đó.
        self._sync_results: dict[str, bytes] = {}

    def generate(self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> bytes:
        raise NotImplementedError(
            "LocalAI video dùng interface bất đồng bộ của VideoProvider (dù response /video thật ra đồng bộ) — dùng start_generation()/poll_generation() qua app/render/engine.py."
        )

    def start_generation(
        self, prompt: str, *, seconds: int = 8, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9",
        extra_negative: str = "",
    ) -> str:
        width, height = (_WIDTH_VERTICAL, _HEIGHT_VERTICAL) if aspect_ratio == "9:16" else (_WIDTH, _HEIGHT)
        body: dict = {
            "model": self.model_name, "prompt": prompt, "width": width, "height": height,
            "seconds": seconds, "response_format": "b64_json",
        }
        if seed is not None:
            body["seed"] = seed
        if extra_negative:
            body["negative_prompt"] = extra_negative
        if reference_image is not None:
            b64 = base64.b64encode(reference_image).decode("ascii")
            body["start_image"] = f"data:image/png;base64,{b64}"

        with httpx.Client(timeout=600) as client:
            resp = client.post(f"{self.base_url}/video", json=body)
            if resp.status_code >= 400:
                raise RuntimeError(f"LocalAI từ chối job video: HTTP {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            video_bytes = self._extract_video_bytes(data, client)

        if video_bytes is None:
            raise RuntimeError(f"LocalAI trả response video không nhận diện được (thiếu cả b64_json lẫn url): {data!r}")
        job_id = f"sync:{data.get('id') or time.time_ns()}"
        self._sync_results[job_id] = video_bytes
        return job_id

    def poll_generation(self, job_id: str) -> tuple[str, bytes | None]:
        data = self._sync_results.pop(job_id, None)
        return ("completed", data) if data is not None else ("failed", None)

    def _extract_video_bytes(self, data: dict, client: httpx.Client) -> bytes | None:
        items = data.get("data") or []
        if not items:
            return None
        item = items[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        url = item.get("url")
        if url:
            resp = client.get(url if url.startswith("http") else f"{self.base_url}{url}")
            resp.raise_for_status()
            return resp.content
        return None

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


def estimate_cost(seconds: int, model_name: str = "") -> float:
    # Local — chi phí $0 (specs/05_ai_providers.md §7).
    return 0.0
