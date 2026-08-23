"""Helper dùng chung cho image_flux.py + video_flux.py — cả 2 đều gọi API Black Forest
Labs (BFL) qua CÙNG 1 cơ chế submit-rồi-poll: `POST /v1/{model}` → `{id, polling_url}`
→ `GET /v1/get_result?id=...` lặp lại tới khi `status` là `"Ready"`/lỗi, xem
specs/05_ai_providers.md §8f. Tách file riêng vì đây là 2 adapter CÙNG 1 hãng CÙNG 1 cơ
chế polling — khác Sora/Veo (2 hãng khác nhau, không chung code được).

CHƯA verify với API key thật (không có key lúc code, 2026-08-16) — dựng theo đúng tài
liệu chính thức (docs.bfl.ai/api-reference, OpenAPI spec tại api.bfl.ai/openapi.json,
đọc trực tiếp lúc research) chứ không đoán, nhưng nếu request/response lệch so với API
thật, sửa lại theo lỗi thật khi test (ghi vào IMPLEMENTATION_REPORT.md, cùng quy ước đã
áp dụng cho Veo/Sora — xem docstring 2 file đó)."""
import time

import httpx

API_BASE = "https://api.bfl.ai/v1"
_POLL_INTERVAL_SEC = 2.0
_TERMINAL_FAILURE_STATUSES = {"Error", "Request Moderated", "Content Moderated", "Task not found"}


def headers(api_key: str) -> dict:
    return {"accept": "application/json", "x-key": api_key, "Content-Type": "application/json"}


def submit(client: httpx.Client, api_key: str, model_path: str, body: dict) -> str:
    resp = client.post(f"{API_BASE}/{model_path}", headers=headers(api_key), json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"BFL từ chối job ({model_path}): HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    request_id = data.get("id")
    if not request_id:
        raise RuntimeError(f"BFL không trả về id job ({model_path}) — response: {str(data)[:300]}")
    return request_id


def poll_until_ready(client: httpx.Client, api_key: str, request_id: str, *, timeout_sec: float) -> dict:
    """Chỉ dùng cho provider ĐỒNG BỘ (Image — `generate()` block tới khi xong). Video
    KHÔNG dùng hàm này — `VideoProvider.poll_generation()` chỉ poll 1 lần rồi trả ngay,
    vòng lặp chờ thật nằm ở `render/engine.py::_poll_video_until_done` (đúng convention
    Sora/Veo, tránh block worker thread quá lâu ở tầng adapter)."""
    waited = 0.0
    while waited < timeout_sec:
        resp = client.get(f"{API_BASE}/get_result", headers=headers(api_key), params={"id": request_id})
        if resp.status_code >= 400:
            raise RuntimeError(f"BFL lỗi khi poll job {request_id}: HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        status = data.get("status", "")
        if status == "Ready":
            result = data.get("result")
            if not result:
                raise RuntimeError(f"BFL báo Ready nhưng thiếu 'result': {str(data)[:300]}")
            return result
        if status in _TERMINAL_FAILURE_STATUSES:
            raise RuntimeError(f"BFL job {request_id} thất bại (status={status}): {str(data.get('details') or data)[:500]}")
        time.sleep(_POLL_INTERVAL_SEC)
        waited += _POLL_INTERVAL_SEC
    raise RuntimeError(f"BFL job {request_id} quá thời gian chờ ({timeout_sec:.0f}s).")


_AUTH_CHECK_MODEL = "flux-2-klein-4b"  # rẻ nhất dòng Image ($0.014/MP) — dùng chung để
# xác thực key cho CẢ Image lẫn Video (cùng 1 key/tài khoản BFL, xem docstring dưới).
_AUTH_CHECK_SIZE = 256  # 256x256 = 0.0655MP — kích thước nhỏ hợp lệ, chi phí ~$0.0009/lần.


def check_auth(client: httpx.Client, api_key: str) -> tuple[bool, str]:
    """**Xác nhận THẬT qua API thật (2026-08-16, gọi bằng key giả để dò hành vi) — BFL
    KHÔNG có endpoint xác thực key miễn phí**, khác giả định ban đầu: `GET /v1/get_result`
    trả `404 "Task not found"` GIỐNG HỆT NHAU dù key đúng/sai/KHÔNG GỬI KEY — endpoint
    này không hề kiểm tra auth khi id không tồn tại, không dùng được để test kết nối.

    Cách DUY NHẤT xác nhận key hợp lệ là POST submit 1 job THẬT. Dùng model RẺ NHẤT
    (`flux-2-klein-4b`) + kích thước nhỏ nhất còn hợp lệ (256x256) để chi phí gần như 0
    (~$0.0009/lần bấm Test) — nhưng đây là chi phí THẬT, không miễn phí tuyệt đối như
    OpenAI/Gemini (`test_connection()` ở image_flux.py/video_flux.py có ghi rõ điều này
    trong message trả về cho người dùng biết). Dùng CHUNG cho cả `video_flux.py` — cùng
    1 key/tài khoản BFL, không cần submit job video thật ($0.85+/lần ở mức tối thiểu 5s)
    chỉ để test kết nối.

    Xác nhận thật bằng key giả: key sai định dạng UUID -> `422 "Invalid API key
    format"`; đúng định dạng nhưng sai -> `403 "Not authenticated"`. Key đúng -> BFL
    CHẤP NHẬN job (trả `id`), ảnh 256x256 THẬT được sinh và tính phí thật."""
    # `x-key` chứa control character (khoảng trắng/xuống dòng thừa lúc copy-paste) làm
    # httpx tự raise `LocalProtocolError` NGAY LÚC GỬI (chưa kịp có response/status code)
    # — bug thật phát hiện (2026-08-22): 1 trong 2 đường lưu API key ở frontend
    # (`ProviderSettings.tsx::AddProviderDialog.save()`) trước đây KHÔNG `.trim()` (khác
    # 2 đường còn lại đã có) — key dính thêm ký tự trắng vẫn lưu được, lúc Test mới lộ ra
    # bằng lỗi cực khó hiểu ("Illegal header value b'...\\n'", không nói gì tới "khoảng
    # trắng"/"API key"). Bắt riêng để dịch sang thông điệp tiếng Việt rõ ràng — dù đã fix
    # chặn ở nguồn (`app/crypto.py::encrypt_secret` tự strip), vẫn giữ lưới an toàn này
    # cho key ĐÃ LỠ lưu trước khi có fix, hoặc provider khác lỡ dính lỗi tương tự sau này.
    try:
        resp = client.post(
            f"{API_BASE}/{_AUTH_CHECK_MODEL}",
            headers=headers(api_key),
            json={"prompt": "connection test", "width": _AUTH_CHECK_SIZE, "height": _AUTH_CHECK_SIZE},
        )
    except httpx.LocalProtocolError:
        return False, "API key chứa khoảng trắng/ký tự xuống dòng thừa (thường do copy-paste dính thêm) — xoá key, dán lại rồi lưu lại."
    except httpx.HTTPError as e:
        return False, f"Không kết nối được tới BFL ({type(e).__name__}) — kiểm tra mạng/tường lửa rồi thử lại: {e}"

    if resp.status_code in (401, 403):
        return False, "API key không hợp lệ (BFL từ chối xác thực — HTTP 403 Not authenticated)"
    if resp.status_code == 422:
        return False, f"API key sai định dạng: {resp.text[:200]}"
    if resp.status_code in (402, 429):
        # Key ĐÚNG (BFL đã xác thực được danh tính, mới biết chặn vì thiếu credit/vượt
        # rate limit) — KHÁC HẲN "key sai" — tách riêng để không làm người dùng tưởng
        # nhầm phải nhập lại key trong khi vấn đề thật là tài khoản BFL chưa nạp tiền/
        # đang bị giới hạn tần suất.
        reason = "tài khoản BFL hết credit hoặc chưa liên kết phương thức thanh toán" if resp.status_code == 402 else "gọi API quá nhanh (rate limit) — đợi 1 lát rồi thử lại"
        return False, f"API key ĐÚNG nhưng BFL từ chối job (HTTP {resp.status_code}: {reason}). Kiểm tra số dư credit tại bfl.ai/dashboard. Chi tiết: {resp.text[:200]}"
    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return True, "Kết nối thành công — đã gửi 1 job ảnh nhỏ (256x256, model rẻ nhất) để xác thực THẬT, chi phí ~$0.0009 (không miễn phí tuyệt đối, BFL không có endpoint auth-check riêng)"
