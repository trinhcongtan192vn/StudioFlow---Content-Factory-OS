"""Test app/providers/video_comfy_wan.py::poll_generation — phân biệt job bị Dừng
(`/interrupt`) với lỗi thực thi thật, cùng bug/fix áp dụng cho `image_comfy_sdxl.py`
(2026-08-23, phát hiện lúc điều tra shot B01 báo lỗi thật của người dùng, project
"Nguyễn Trãi và án Lệ Chi Viên"). Chưa có test nào cho file này trước đợt này.
"""
import json

import pytest
import respx
from httpx import Response

from app.providers.base import GenerationInterrupted
from app.providers.video_comfy_wan import _HEIGHT, _HEIGHT_VERTICAL, _NEGATIVE_PROMPT, _WIDTH, _WIDTH_VERTICAL, ComfyWanVideoProvider


# ---------------------------------------------------------------------------
# Phase A (2026-08-23, StudioFlow_Video_Improvement_Plan.md) — tinh chỉnh tham số.
# ---------------------------------------------------------------------------
def test_resolution_matches_sdxl_bucket_exactly():
    """Đổi (2026-08-23): độ phân giải PHẢI khớp CHÍNH XÁC bucket SDXL
    (`image_comfy_sdxl.py::_WIDTH/_HEIGHT` = 1344×768) — để ảnh anchor (Phase B)
    không cần `ImageScale` co/crop trước khi nạp làm `start_image`."""
    from app.providers.image_comfy_sdxl import _HEIGHT as sdxl_height
    from app.providers.image_comfy_sdxl import _WIDTH as sdxl_width

    assert (_WIDTH, _HEIGHT) == (sdxl_width, sdxl_height)
    assert (_WIDTH_VERTICAL, _HEIGHT_VERTICAL) == (sdxl_height, sdxl_width)  # xoay dọc đúng


def test_negative_prompt_blocks_temporal_flicker_and_face_warp():
    """Đổi (2026-08-23): thêm cụm chống lỗi ĐẶC THÙ video (nhấp nháy/méo khuôn mặt giữa
    frame) — khác lỗi ảnh tĩnh đã có sẵn."""
    for keyword in ("flickering", "morphing", "warping face", "jittery motion"):
        assert keyword in _NEGATIVE_PROMPT


def test_start_generation_appends_extra_negative_to_negative_prompt():
    """`cultural_lock_negative` (mới 2026-08-23, chống thiên lệch văn hoá Nhật/Hàn) —
    nối vào negative prompt THẬT gửi Wan, cùng cơ chế đã thêm cho image_comfy_sdxl.py."""
    with respx.mock:
        submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": "job-1"}))
        provider = ComfyWanVideoProvider()
        provider.start_generation("a cat", seed=1, extra_negative="japanese kimono, korean hanbok")

    body = json.loads(submit_route.calls[0].request.content)
    negative_text = body["prompt"]["7"]["inputs"]["text"]
    assert "japanese kimono, korean hanbok" in negative_text
    assert _NEGATIVE_PROMPT in negative_text


def test_start_generation_caps_frame_count_at_max_generate_seconds():
    """Đổi (2026-08-23): dù `seconds` (thời lượng thật của shot) lớn hơn nhiều, số khung
    THỰC SỰ gửi cho Wan phải bị chặn ở `_MAX_GENERATE_SECONDS` (4s) — assembly.py tự lặp
    video ngắn để lấp đầy thời lượng thật (an toàn, đã xác nhận qua `_reflow_video_durations`)."""
    with respx.mock:
        submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": "job-1"}))
        provider = ComfyWanVideoProvider()
        provider.start_generation("a cat running", seconds=20, seed=1)

    body = json.loads(submit_route.calls[0].request.content)
    length = body["prompt"]["55"]["inputs"]["length"]
    # 4s @ 24fps ≈ 96 khung, làm tròn về dạng 4k+1 gần nhất — PHẢI nhỏ hơn hẳn so với
    # số khung nếu dùng thẳng 20s (~480 khung).
    assert length < 100, f"length={length} — có vẻ chưa bị chặn ở _MAX_GENERATE_SECONDS"


def test_poll_generation_raises_generation_interrupted_when_comfyui_reports_interrupted():
    """Tái hiện đúng bug thật: shot B01 chạy KSampler ~9 phút rồi bị Dừng — ComfyUI
    `/history` trả `status_str: "error"` kèm message `execution_interrupted` (không phải
    exception thật) — PHẢI raise `GenerationInterrupted`, không phải RuntimeError chung
    chung (mới hiện lỗi kỹ thuật dump ra cho người dùng dù họ chỉ bấm Dừng)."""
    with respx.mock:
        respx.get("http://127.0.0.1:8188/history/job-1").mock(
            return_value=Response(
                200,
                json={
                    "job-1": {
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [
                                ["execution_start", {"prompt_id": "job-1"}],
                                ["execution_cached", {"nodes": []}],
                                ["execution_interrupted", {"node_id": "3", "node_type": "KSampler"}],
                            ],
                        }
                    }
                },
            )
        )
        provider = ComfyWanVideoProvider()
        with pytest.raises(GenerationInterrupted):
            provider.poll_generation("job-1")


def test_poll_generation_raises_plain_runtime_error_for_real_execution_error():
    """Đối chứng: lỗi thực thi THẬT (VD CUDA OOM, thiếu node) vẫn raise RuntimeError như
    cũ — không vô tình nuốt lỗi thật thành "đã dừng"."""
    with respx.mock:
        respx.get("http://127.0.0.1:8188/history/job-1").mock(
            return_value=Response(
                200,
                json={
                    "job-1": {
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]],
                        }
                    }
                },
            )
        )
        provider = ComfyWanVideoProvider()
        with pytest.raises(RuntimeError) as exc_info:
            provider.poll_generation("job-1")
        assert not isinstance(exc_info.value, GenerationInterrupted)


def test_poll_generation_returns_processing_when_still_running():
    with respx.mock:
        respx.get("http://127.0.0.1:8188/history/job-1").mock(return_value=Response(200, json={}))
        provider = ComfyWanVideoProvider()
        status, data = provider.poll_generation("job-1")
    assert status == "processing"
    assert data is None
