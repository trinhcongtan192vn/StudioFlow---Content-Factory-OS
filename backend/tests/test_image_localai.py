"""Test app/providers/image_localai.py — provider ảnh LocalAI mới (2026-08-25, kế hoạch
migrate LocalAI đã duyệt). respx mock LocalAI (`/v1/images/generations`, `/models/apply`,
`/v1/models`), không cần LocalAI thật — CHỈ verify code build đúng request theo tài liệu
LocalAI đã research (xem docstring image_localai.py), KHÔNG verify được hành vi LocalAI
thật (cần GPU người dùng, xem Cổng verify trong plan).
"""
import base64
import json

import pytest
import respx
from httpx import Response

from app.providers.image_localai import LocalAIImageProvider, list_localai_models

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mock_generate_success():
    return respx.post("http://127.0.0.1:8080/v1/images/generations").mock(
        return_value=Response(200, json={"data": [{"b64_json": base64.b64encode(FAKE_PNG).decode()}]})
    )


@respx.mock
def test_generate_without_model_name_syncs_virtual_model_then_calls_images_endpoint():
    """Không cấu hình `model_name` (rỗng) — provider tự đăng ký/đồng bộ 1 "model ảo"
    (`studioflow-sdxl`) qua `/models/apply` TRƯỚC, rồi gọi sinh ảnh bằng đúng tên đó."""
    apply_route = respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    generate_route = _mock_generate_success()

    provider = LocalAIImageProvider()
    result = provider.generate("a cat", seed=42, loras=[{"name": "inkart.safetensors", "strength": 0.7}])

    assert result == FAKE_PNG
    assert apply_route.called
    apply_body = json.loads(apply_route.calls.last.request.content)
    assert apply_body["name"] == "studioflow-sdxl"
    assert apply_body["overrides"]["lora_adapters"] == ["inkart.safetensors"]
    assert apply_body["overrides"]["lora_scales"] == [0.7]

    generate_body = json.loads(generate_route.calls.last.request.content)
    assert generate_body["model"] == "studioflow-sdxl"
    assert generate_body["prompt"] == "a cat"
    assert generate_body["seed"] == 42


@respx.mock
def test_generate_with_configured_model_name_skips_lora_sync():
    """`model_name` đã cấu hình sẵn (người dùng tự đăng ký YAML) — dùng THẲNG, KHÔNG tự
    gọi `/models/apply` (tôn trọng cấu hình thủ công, không ghi đè)."""
    apply_route = respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    generate_route = _mock_generate_success()

    provider = LocalAIImageProvider(model_name="my-custom-sdxl")
    provider.generate("a cat", loras=[{"name": "inkart.safetensors", "strength": 0.7}])

    assert not apply_route.called
    generate_body = json.loads(generate_route.calls.last.request.content)
    assert generate_body["model"] == "my-custom-sdxl"


@respx.mock
def test_generate_caches_lora_sync_and_skips_repeat_apply_call_for_same_signature():
    """Gọi `generate()` 2 LẦN LIÊN TIẾP với CÙNG danh sách LoRA — `/models/apply` chỉ
    được gọi 1 LẦN (cache theo chữ ký LoRA), tránh gọi thừa mỗi lần sinh 1 shot."""
    apply_route = respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    _mock_generate_success()

    provider = LocalAIImageProvider()
    loras = [{"name": "inkart.safetensors", "strength": 0.7}]
    provider.generate("a cat", loras=loras)
    provider.generate("a dog", loras=loras)

    assert apply_route.call_count == 1


@respx.mock
def test_generate_resyncs_when_lora_signature_changes():
    """Đổi LoRA giữa 2 lần gọi — `/models/apply` phải được gọi LẠI (chữ ký đổi)."""
    apply_route = respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    _mock_generate_success()

    provider = LocalAIImageProvider()
    provider.generate("a cat", loras=[{"name": "inkart.safetensors", "strength": 0.7}])
    provider.generate("a dog", loras=[{"name": "oilpaint.safetensors", "strength": 0.8}])

    assert apply_route.call_count == 2


@respx.mock
def test_generate_maps_extra_negative_to_negative_prompt_field():
    generate_route = _mock_generate_success()
    respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))

    provider = LocalAIImageProvider()
    provider.generate("a cat", extra_negative="japanese kimono, anime style")

    body = json.loads(generate_route.calls.last.request.content)
    assert body["negative_prompt"] == "japanese kimono, anime style"


@respx.mock
def test_generate_with_reference_image_uses_img2img_model_and_encodes_image():
    """Đợt 2 (2026-08-25): `reference_images` giờ dùng img2img (KHÔNG PHẢI IPAdapter,
    khác kết luận đợt 1) — provider phải đăng ký/dùng model img2img RIÊNG (tên khác
    model txt2img), gửi field `image` (base64 ảnh ĐẦU TIÊN), KHÔNG lỗi."""
    apply_route = respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    generate_route = _mock_generate_success()

    provider = LocalAIImageProvider()
    result = provider.generate("a cat", reference_images=[b"fake-ref-image-bytes"], style_reference_weight=0.6)

    assert result == FAKE_PNG
    apply_body = json.loads(apply_route.calls.last.request.content)
    assert apply_body["name"] == "studioflow-sdxl-img2img"
    assert apply_body["overrides"]["pipeline_type"] == "StableDiffusionXLImg2ImgPipeline"

    body = json.loads(generate_route.calls.last.request.content)
    assert body["model"] == "studioflow-sdxl-img2img"
    assert body["image"] == base64.b64encode(b"fake-ref-image-bytes").decode()


@respx.mock
def test_generate_with_reference_image_only_uses_first_of_multiple():
    """img2img LocalAI chỉ nhận 1 ảnh/lần — nếu `reference_images` có nhiều (dữ liệu cũ
    từ UI IPAdapter trước đây), CHỈ ảnh đầu tiên được dùng, không lỗi vì "quá nhiều ảnh"."""
    respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    generate_route = _mock_generate_success()

    provider = LocalAIImageProvider()
    provider.generate("a cat", reference_images=[b"first-image", b"second-image"])

    body = json.loads(generate_route.calls.last.request.content)
    assert body["image"] == base64.b64encode(b"first-image").decode()


@respx.mock
def test_generate_maps_style_reference_weight_to_inverse_strength():
    """`strength` (diffusers) HƯỚNG NGƯỢC `style_reference_weight` — weight cao (muốn
    giữ phong cách ảnh tham chiếu NHIỀU) phải ra `strength` THẤP (ít thêm nhiễu)."""
    respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    generate_route = _mock_generate_success()

    provider = LocalAIImageProvider()
    provider.generate("a cat", reference_images=[b"ref"], style_reference_weight=0.8)
    body_high_weight = json.loads(generate_route.calls.last.request.content)

    provider.generate("a cat", reference_images=[b"ref"], style_reference_weight=0.2)
    body_low_weight = json.loads(generate_route.calls.last.request.content)

    assert body_high_weight["strength"] < body_low_weight["strength"]
    assert 0.3 <= body_high_weight["strength"] <= 0.85
    assert 0.3 <= body_low_weight["strength"] <= 0.85


@respx.mock
def test_generate_without_reference_image_uses_txt2img_model_no_image_field():
    generate_route = _mock_generate_success()
    respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))

    provider = LocalAIImageProvider()
    provider.generate("a cat", loras=[{"name": "inkart.safetensors", "strength": 0.7}])

    body = json.loads(generate_route.calls.last.request.content)
    assert body["model"] == "studioflow-sdxl"
    assert "image" not in body
    assert "strength" not in body


@respx.mock
def test_txt2img_and_img2img_model_sync_caches_are_independent():
    """Đồng bộ LoRA cho model txt2img KHÔNG được coi là "đã đồng bộ" cho model img2img
    (2 model KHÁC NHAU trong LocalAI) — cả 2 phải tự gọi `/models/apply` lần đầu dùng."""
    apply_route = respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))
    _mock_generate_success()

    provider = LocalAIImageProvider()
    loras = [{"name": "inkart.safetensors", "strength": 0.7}]
    provider.generate("a cat", loras=loras)  # txt2img — đồng bộ lần 1
    provider.generate("a cat", loras=loras, reference_images=[b"ref"])  # img2img — model KHÁC, phải đồng bộ lần 2
    provider.generate("a cat", loras=loras)  # txt2img lại — signature không đổi, KHÔNG gọi lại
    provider.generate("a cat", loras=loras, reference_images=[b"ref"])  # img2img lại — KHÔNG gọi lại

    assert apply_route.call_count == 2


@respx.mock
def test_generate_size_matches_aspect_ratio():
    generate_route = _mock_generate_success()
    respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(200, json={"status": "ok"}))

    provider = LocalAIImageProvider()
    provider.generate("a cat", aspect_ratio="9:16")

    body = json.loads(generate_route.calls.last.request.content)
    assert body["size"] == "768x1344"


@respx.mock
def test_generate_falls_back_gracefully_when_model_sync_fails():
    """`/models/apply` lỗi (VD API path lệch — CHƯA verify thật, xem docstring) KHÔNG
    được chặn việc sinh ảnh — best-effort, vẫn thử sinh ảnh bằng model hiện có."""
    respx.post("http://127.0.0.1:8080/models/apply").mock(return_value=Response(404, text="not found"))
    generate_route = _mock_generate_success()

    provider = LocalAIImageProvider()
    result = provider.generate("a cat", loras=[{"name": "inkart.safetensors", "strength": 0.7}])

    assert result == FAKE_PNG
    assert generate_route.called


def test_test_connection_ok():
    with respx.mock:
        respx.get("http://127.0.0.1:8080/v1/models").mock(return_value=Response(200, json={"data": []}))
        status = LocalAIImageProvider().test_connection()
    assert status.ok


def test_test_connection_unreachable():
    with respx.mock:
        respx.get("http://127.0.0.1:8080/v1/models").mock(side_effect=Exception("connection refused"))
        status = LocalAIImageProvider().test_connection()
    assert not status.ok
    assert "LocalAI" in status.message


def test_list_localai_models_returns_ids():
    with respx.mock:
        respx.get("http://127.0.0.1:8080/v1/models").mock(return_value=Response(200, json={"data": [{"id": "studioflow-sdxl"}, {"id": "qwen2.5"}]}))
        models = list_localai_models()
    assert models == ["studioflow-sdxl", "qwen2.5"]


def test_list_localai_models_raises_runtime_error_when_unreachable():
    with respx.mock:
        respx.get("http://127.0.0.1:8080/v1/models").mock(side_effect=Exception("connection refused"))
        with pytest.raises(RuntimeError):
            list_localai_models()
