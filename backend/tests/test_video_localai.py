"""Test app/providers/video_localai.py — provider video LocalAI, **sửa lại đợt 2
(2026-08-25)** theo endpoint THẬT đã xác nhận qua tài liệu chính thức
(`localai.io/docs/features/video-generation/`, người dùng đưa) — `POST /video` (không
`/v1`), field `start_image`, response ĐỒNG BỘ (không job-poll như giả định đợt 1).
respx mock LocalAI, không cần LocalAI thật — CHỈ verify code build đúng request/parse
đúng response theo tài liệu đã research, KHÔNG verify được hành vi LocalAI thật (cần GPU
người dùng, xem Cổng verify trong plan).
"""
import base64
import json

import pytest
import respx
from httpx import Response

from app.providers.video_localai import LocalAIVideoProvider

FAKE_MP4 = b"\x00\x00\x00\x18ftyp" + b"\x00" * 32


@respx.mock
def test_start_generation_posts_to_video_without_v1_prefix():
    """respx chỉ mock ĐÚNG path `/video` (không `/v1`) — nếu code lỡ gọi nhầm endpoint
    đợt 1 (`/v1/videos`), respx sẽ raise lỗi "no route matched" thay vì match được ở
    đây, tự nhiên bắt được regression."""
    submit_route = respx.post("http://127.0.0.1:8080/video").mock(
        return_value=Response(200, json={"id": "vid-1", "data": [{"b64_json": base64.b64encode(FAKE_MP4).decode()}]})
    )
    provider = LocalAIVideoProvider()
    provider.start_generation("a dog running", seconds=4)

    assert submit_route.called


@respx.mock
def test_start_generation_response_is_synchronous_no_polling_needed():
    """Response `/video` THẬT là đồng bộ — `poll_generation` phải trả "completed" +
    bytes NGAY LẦN GỌI ĐẦU, không có nhánh chờ/job-status nào (khác thiết kế đợt 1)."""
    respx.post("http://127.0.0.1:8080/video").mock(
        return_value=Response(200, json={"id": "vid-1", "data": [{"b64_json": base64.b64encode(FAKE_MP4).decode()}]})
    )
    provider = LocalAIVideoProvider()
    job_id = provider.start_generation("a dog running", seconds=4)

    status, data = provider.poll_generation(job_id)
    assert status == "completed"
    assert data == FAKE_MP4


@respx.mock
def test_start_generation_sends_correct_body_fields():
    submit_route = respx.post("http://127.0.0.1:8080/video").mock(
        return_value=Response(200, json={"id": "vid-1", "data": [{"b64_json": base64.b64encode(FAKE_MP4).decode()}]})
    )
    provider = LocalAIVideoProvider(model_name="wan2.2-ti2v-5b")
    provider.start_generation("a dog running", seconds=6, seed=42, extra_negative="blurry, flickering")

    body = json.loads(submit_route.calls.last.request.content)
    assert body["model"] == "wan2.2-ti2v-5b"
    assert body["prompt"] == "a dog running"
    assert body["seconds"] == 6
    assert body["seed"] == 42
    assert body["negative_prompt"] == "blurry, flickering"
    assert body["response_format"] == "b64_json"
    assert "start_image" not in body


@respx.mock
def test_start_generation_encodes_reference_image_as_start_image_data_uri():
    submit_route = respx.post("http://127.0.0.1:8080/video").mock(
        return_value=Response(200, json={"id": "vid-1", "data": [{"b64_json": base64.b64encode(FAKE_MP4).decode()}]})
    )
    provider = LocalAIVideoProvider()
    provider.start_generation("a dog running", reference_image=b"fake-png-bytes")

    body = json.loads(submit_route.calls.last.request.content)
    assert body["start_image"].startswith("data:image/png;base64,")
    assert base64.b64decode(body["start_image"].split(",", 1)[1]) == b"fake-png-bytes"


@respx.mock
def test_start_generation_size_matches_aspect_ratio():
    submit_route = respx.post("http://127.0.0.1:8080/video").mock(
        return_value=Response(200, json={"id": "vid-1", "data": [{"b64_json": base64.b64encode(FAKE_MP4).decode()}]})
    )
    provider = LocalAIVideoProvider()
    provider.start_generation("a dog running", aspect_ratio="9:16")

    body = json.loads(submit_route.calls.last.request.content)
    assert (body["width"], body["height"]) == (768, 1344)


@respx.mock
def test_start_generation_downloads_video_from_url_when_no_b64():
    """`response_format="b64_json"` được yêu cầu, nhưng vẫn giữ fallback đọc `url` phòng
    khi bản LocalAI nào đó bỏ qua tham số này và chỉ trả url."""
    respx.post("http://127.0.0.1:8080/video").mock(return_value=Response(200, json={"id": "vid-2", "data": [{"url": "/generated-videos/out.mp4"}]}))
    respx.get("http://127.0.0.1:8080/generated-videos/out.mp4").mock(return_value=Response(200, content=FAKE_MP4))

    provider = LocalAIVideoProvider()
    job_id = provider.start_generation("a dog running")
    status, data = provider.poll_generation(job_id)

    assert status == "completed"
    assert data == FAKE_MP4


@respx.mock
def test_start_generation_raises_when_localai_rejects_job():
    respx.post("http://127.0.0.1:8080/video").mock(return_value=Response(400, text="model not found"))

    provider = LocalAIVideoProvider()
    with pytest.raises(RuntimeError, match="model not found"):
        provider.start_generation("a dog running")


@respx.mock
def test_start_generation_raises_when_response_has_neither_b64_nor_url():
    respx.post("http://127.0.0.1:8080/video").mock(return_value=Response(200, json={"id": "vid-3", "data": [{}]}))

    provider = LocalAIVideoProvider()
    with pytest.raises(RuntimeError, match="không nhận diện được"):
        provider.start_generation("a dog running")


def test_generate_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        LocalAIVideoProvider().generate("a dog running")


def test_test_connection_ok():
    with respx.mock:
        respx.get("http://127.0.0.1:8080/v1/models").mock(return_value=Response(200, json={"data": []}))
        status = LocalAIVideoProvider().test_connection()
    assert status.ok


def test_test_connection_unreachable():
    with respx.mock:
        respx.get("http://127.0.0.1:8080/v1/models").mock(side_effect=Exception("connection refused"))
        status = LocalAIVideoProvider().test_connection()
    assert not status.ok
