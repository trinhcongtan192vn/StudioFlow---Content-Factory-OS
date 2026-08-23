"""Flux Kontext qua fluxapi.ai — provider ẢNH THÊM MỚI (2026-08-22), theo yêu cầu người
dùng: người dùng có sẵn API key của **fluxapi.ai**, một dịch vụ BÊN THỨ 3 ĐỘC LẬP,
KHÔNG PHẢI Black Forest Labs chính thức (khác hẳn `image_flux.py`/`video_flux.py`/
`flux_common.py` — 3 file đó gọi thẳng `api.bfl.ai`, dùng key BFL riêng, KHÔNG dùng
chung được với key fluxapi.ai). Phát hiện qua điều tra thật: người dùng "điền API key
chuẩn" nhưng Test connection ở provider Flux (BFL) luôn lỗi — vì key đó là của
fluxapi.ai, hoàn toàn khác dịch vụ. Thêm SONG SONG (KHÔNG thay thế `image_flux.py`) —
giữ nguyên lựa chọn BFL chính thức cho ai có key thật, thêm lựa chọn này cho ai dùng
fluxapi.ai — đúng nguyên tắc "Provider AI thay thế được" (CLAUDE.md).

**Khác biệt kỹ thuật với BFL** (xác nhận THẬT bằng curl trực tiếp, không tin nguyên văn
tài liệu — tài liệu fluxapi.ai lúc research ghi endpoint credit sai đường dẫn, tự dò lại
mới ra đúng, xem bên dưới):
- Base URL riêng: `api.fluxapi.ai` (không phải `api.bfl.ai`).
- Header auth: `Authorization: Bearer <key>` (KHÔNG PHẢI `x-key` như BFL).
- Body dùng `aspectRatio` (string "16:9"/"9:16"/"1:1"...), KHÔNG PHẢI `width`/`height`
  số nguyên như BFL.
- **QUAN TRỌNG NHẤT — khác biệt lớn nhất so với BFL**: fluxapi.ai LUÔN trả HTTP 200 ở
  MỌI trường hợp (kể cả auth sai/lỗi tham số) — trạng thái THẬT nằm ở field `"code"`
  TRONG BODY JSON (200=thành công, 401=auth sai, khác = lỗi khác), không phải ở HTTP
  status code như BFL. Xác nhận bằng curl thật với key giả: `HTTP_STATUS:200` nhưng body
  `{"code":401,"msg":"Unauthorized..."}`. Code ở đây PHẢI đọc `data["code"]`, KHÔNG được
  chỉ dựa vào `resp.status_code`.
- Bất đồng bộ nhưng KHÔNG dùng `flux_common.py` (submit/poll shape hoàn toàn khác BFL,
  không tái dùng được) — tự viết poll riêng ở đây.

**Endpoint credit-check** (`GET /api/v1/common/credit`) — tài liệu fluxapi.ai lúc fetch
ghi nhầm là `/api/v1/chat/credit` (thử thật ra `404 Not Found`) — dò lại bằng cách thử
nhiều biến thể, `/api/v1/common/credit` mới là đường dẫn ĐÚNG (xác nhận qua response
thật `{"code":401,...}` thay vì 404). Dùng endpoint này cho `test_connection()` — MIỄN
PHÍ, không tốn credit như phải submit job ảnh thật (khác BFL — BFL không có endpoint
free nào nên phải submit job thật $0.0009/lần)."""
from __future__ import annotations

import time

import httpx

from app.providers.base import ImageProvider, ProviderStatus

_BASE = "https://api.fluxapi.ai/api/v1"
_POLL_INTERVAL_SEC = 2.0
_POLL_TIMEOUT_SEC = 180.0
_FAILED_FLAGS = {2, 3}  # CREATE_TASK_FAILED, GENERATE_FAILED (xem docs.fluxapi.ai/flux-kontext-api/get-image-details)


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


class FluxKontextImageProvider(ImageProvider):
    provider_name = "flux_kontext"

    def __init__(self, api_key: str = "", model_name: str = "flux-kontext-pro"):
        self.api_key = api_key
        self.model_name = model_name or "flux-kontext-pro"

    def generate(self, prompt: str, *, seed: int | None = None, reference_image: bytes | None = None, aspect_ratio: str = "16:9") -> bytes:
        # `reference_image` KHÔNG hỗ trợ — Kontext nhận ảnh tham chiếu qua `inputImage`
        # là 1 URL CÔNG KHAI (không nhận bytes trực tiếp), app này (desktop, chạy local)
        # không có nơi host URL tạm — bỏ qua tham số, coi như provider chưa hỗ trợ (Tier
        # 2 hiện TẮT mặc định toàn app, xem app/render/engine.py::generate_visual_asset).
        body = {"prompt": prompt, "model": self.model_name, "aspectRatio": aspect_ratio, "outputFormat": "png"}
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{_BASE}/flux/kontext/generate", headers=_headers(self.api_key), json=body)
            data = self._unwrap(resp, context="submit")
            task_id = ((data.get("data") or {}).get("taskId"))
            if not task_id:
                raise RuntimeError(f"fluxapi.ai không trả về taskId — response: {str(data)[:300]}")

            waited = 0.0
            while waited < _POLL_TIMEOUT_SEC:
                poll_resp = client.get(f"{_BASE}/flux/kontext/record-info", headers=_headers(self.api_key), params={"taskId": task_id})
                poll_data = self._unwrap(poll_resp, context=f"poll task {task_id}")
                inner = poll_data.get("data") or {}
                flag = inner.get("successFlag")
                if flag == 1:
                    url = (inner.get("response") or {}).get("resultImageUrl")
                    if not url:
                        raise RuntimeError(f"fluxapi.ai báo SUCCESS nhưng thiếu resultImageUrl: {str(inner)[:300]}")
                    img_resp = client.get(url)
                    if img_resp.status_code >= 400:
                        raise RuntimeError(f"Không tải được ảnh từ fluxapi.ai: HTTP {img_resp.status_code}")
                    return img_resp.content
                if flag in _FAILED_FLAGS:
                    raise RuntimeError(f"fluxapi.ai job {task_id} thất bại (successFlag={flag}): {inner.get('errorMessage') or inner.get('errorCode')}")
                time.sleep(_POLL_INTERVAL_SEC)
                waited += _POLL_INTERVAL_SEC
            raise RuntimeError(f"fluxapi.ai job {task_id} quá thời gian chờ ({_POLL_TIMEOUT_SEC:.0f}s).")

    @staticmethod
    def _unwrap(resp: httpx.Response, *, context: str) -> dict:
        """fluxapi.ai LUÔN trả HTTP 200 (trừ lỗi hạ tầng thật — 404 sai đường dẫn, 5xx
        server) — trạng thái THẬT nằm ở `data["code"]`. Kiểm CẢ 2 lớp (HTTP status VÀ
        code trong body) để an toàn với mọi kiểu lỗi có thể gặp."""
        if resp.status_code >= 400:
            raise RuntimeError(f"fluxapi.ai lỗi HTTP khi {context}: {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"fluxapi.ai trả response không phải JSON khi {context}: {resp.text[:300]}") from e
        code = data.get("code")
        if code is not None and code != 200:
            raise RuntimeError(f"fluxapi.ai từ chối khi {context} (code={code}): {data.get('msg', '')}")
        return data

    def test_connection(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(ok=False, message="Thiếu API key")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"{_BASE}/common/credit", headers=_headers(self.api_key))
            if resp.status_code >= 400:
                return ProviderStatus(ok=False, message=f"HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            code = data.get("code")
            if code == 401:
                return ProviderStatus(ok=False, message="API key không hợp lệ (fluxapi.ai từ chối xác thực)")
            if code is not None and code != 200:
                return ProviderStatus(ok=False, message=f"fluxapi.ai từ chối (code={code}): {data.get('msg', '')}")
            credits = data.get("data")
            return ProviderStatus(ok=True, message=f"Kết nối thành công — còn {credits} credit (kiểm tra miễn phí, không tốn phí sinh ảnh)" if credits is not None else "Kết nối thành công")
        except httpx.HTTPError as e:
            return ProviderStatus(ok=False, message=f"Không kết nối được tới fluxapi.ai ({type(e).__name__}): {e}")


def estimate_cost(image_count: int, model_name: str = "flux-kontext-pro") -> float:
    # fluxapi.ai chưa công khai bảng giá cụ thể theo model lúc tích hợp (đợt thêm nhanh
    # theo yêu cầu người dùng, khác BFL đã có bảng giá chính thức research kỹ ở
    # image_flux.py) — trả 0.0 TẠM THỜI, KHÔNG bịa số — cập nhật khi có số liệu THẬT
    # (VD người dùng đối chiếu hoá đơn thật, hoặc research sau khi cần chính xác cho
    # màn Chi phí & Ngân sách).
    return 0.0
