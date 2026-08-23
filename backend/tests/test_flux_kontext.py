"""Test app/providers/image_flux_kontext.py — provider Flux Kontext qua fluxapi.ai
(bên thứ 3, KHÁC hẳn BFL chính thức đang dùng ở image_flux.py/video_flux.py). respx
mock, không gọi API thật, không tốn phí — theo đúng convention test_render.py.

Điểm quan trọng nhất cần test: fluxapi.ai LUÔN trả HTTP 200 (xác nhận THẬT bằng curl lúc
điều tra, xem IMPLEMENTATION_REPORT.md) — trạng thái thật nằm ở field "code" trong body
JSON. `_unwrap()`/`test_connection()` PHẢI đọc `code`, không được chỉ tin
`resp.status_code`. Test giả lập đúng hành vi thật này (HTTP 200 + code=401 trong body)
để bắt regression nếu sau này ai đó lỡ đổi lại sang chỉ check `resp.status_code`.
"""
import respx
from httpx import Response

from app.providers.image_flux_kontext import FluxKontextImageProvider

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_generate_submits_then_polls_and_downloads_image():
    with respx.mock:
        respx.post("https://api.fluxapi.ai/api/v1/flux/kontext/generate").mock(
            return_value=Response(200, json={"code": 200, "msg": "success", "data": {"taskId": "task-123"}})
        )
        respx.get("https://api.fluxapi.ai/api/v1/flux/kontext/record-info").mock(
            return_value=Response(200, json={"code": 200, "data": {"successFlag": 1, "response": {"resultImageUrl": "https://cdn.fluxapi.ai/task-123.png"}}})
        )
        respx.get("https://cdn.fluxapi.ai/task-123.png").mock(return_value=Response(200, content=FAKE_PNG))

        data = FluxKontextImageProvider(api_key="fx-test-key").generate("a cat wearing a hat", aspect_ratio="9:16")

        submit_req = respx.calls[0].request
        assert submit_req.headers["authorization"] == "Bearer fx-test-key"
        import json as _json

        body = _json.loads(submit_req.content)
        assert body["aspectRatio"] == "9:16"

    assert data == FAKE_PNG


def test_generate_raises_on_job_failure():
    with respx.mock:
        respx.post("https://api.fluxapi.ai/api/v1/flux/kontext/generate").mock(
            return_value=Response(200, json={"code": 200, "data": {"taskId": "task-fail"}})
        )
        respx.get("https://api.fluxapi.ai/api/v1/flux/kontext/record-info").mock(
            return_value=Response(200, json={"code": 200, "data": {"successFlag": 2, "errorMessage": "content moderated"}})
        )
        try:
            FluxKontextImageProvider(api_key="fx-test-key").generate("bad prompt")
            assert False, "phải raise RuntimeError khi successFlag báo lỗi"
        except RuntimeError as e:
            assert "content moderated" in str(e) or "task-fail" in str(e)


def test_unwrap_checks_body_code_even_when_http_status_is_200():
    """fluxapi.ai trả HTTP 200 NGAY CẢ KHI auth sai — code lỗi thật nằm trong body.
    Đây là hành vi xác nhận THẬT (không phải giả định) qua curl trực tiếp lúc điều tra."""
    with respx.mock:
        respx.post("https://api.fluxapi.ai/api/v1/flux/kontext/generate").mock(
            return_value=Response(200, json={"code": 401, "msg": "Unauthorized"})
        )
        try:
            FluxKontextImageProvider(api_key="key-sai").generate("a cat")
            assert False, "phải raise RuntimeError dù HTTP status là 200"
        except RuntimeError as e:
            assert "401" in str(e) or "Unauthorized" in str(e)


def test_test_connection_success_reports_credit_balance():
    with respx.mock:
        respx.get("https://api.fluxapi.ai/api/v1/common/credit").mock(return_value=Response(200, json={"code": 200, "data": 42}))
        status = FluxKontextImageProvider(api_key="fx-good-key").test_connection()
    assert status.ok is True
    assert "42" in status.message


def test_test_connection_bad_key_returns_ok_false_despite_http_200():
    with respx.mock:
        respx.get("https://api.fluxapi.ai/api/v1/common/credit").mock(
            return_value=Response(200, json={"code": 401, "msg": "Unauthorized – Authentication failed."})
        )
        status = FluxKontextImageProvider(api_key="key-sai").test_connection()
    assert status.ok is False
    assert "hợp lệ" in status.message or "Unauthorized" in status.message


def test_test_connection_missing_key_short_circuits_without_http_call():
    status = FluxKontextImageProvider(api_key="").test_connection()
    assert status.ok is False
