"""Test app/providers/image_comfy_qwen.py — provider ảnh Qwen-Image-2.1 (GGUF, qua
ComfyUI) MỚI (2026-09-24). respx mock ComfyUI (`/prompt`, `/history/{id}`, `/view`,
`/system_stats`) — KHÔNG cần GPU thật cho test tự động, nhưng đồ thị workflow trong
`_build_txt2img_workflow` ĐÃ được verify thật trên GPU người dùng trước khi viết provider
(xem docstring `image_comfy_qwen.py` — chạy thật qua `/prompt` trực tiếp, ra ảnh đúng)."""
import json

import pytest
import respx
from httpx import Response

from app.providers.base import GenerationInterrupted
from app.providers.image_comfy_qwen import _CLIP_NAME, _UNET_GGUF_NAME, _VAE_NAME, ComfyQwenImageProvider

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mock_comfyui_success(prompt_id: str = "job-1"):
    submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": prompt_id}))
    respx.get(f"http://127.0.0.1:8188/history/{prompt_id}").mock(
        return_value=Response(200, json={prompt_id: {"outputs": {"11": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
    )
    respx.get("http://127.0.0.1:8188/view").mock(return_value=Response(200, content=FAKE_PNG))
    return submit_route


def test_generate_uses_default_gguf_and_clip_and_vae_when_model_name_empty():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        data = provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert data == FAKE_PNG
    workflow = sent_body["prompt"]
    assert workflow["1"]["inputs"]["unet_name"] == _UNET_GGUF_NAME
    assert _UNET_GGUF_NAME == "Qwen-Image-2.1-Q4.gguf"
    assert workflow["4"]["inputs"]["clip_name"] == _CLIP_NAME
    assert workflow["5"]["inputs"]["vae_name"] == _VAE_NAME


def test_generate_uses_custom_model_name_as_gguf_unet():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider(model_name="Qwen-Image-2.1-Q6.gguf")
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert sent_body["prompt"]["1"]["inputs"]["unet_name"] == "Qwen-Image-2.1-Q6.gguf"


def test_generate_clip_loader_uses_qwen_image_type():
    """`type="qwen_image"` bắt buộc trên `CLIPLoader` — sai giá trị này là lỗi kinh điển
    khi build workflow Qwen (đã verify thật qua object_info + workflow mẫu thật)."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert sent_body["prompt"]["4"]["class_type"] == "CLIPLoader"
    assert sent_body["prompt"]["4"]["inputs"]["type"] == "qwen_image"


def test_generate_text_encode_qwen_image_21_does_not_send_images_input():
    """Đã verify thật (gọi thẳng /prompt, bỏ qua lớp validate quá khắt khe của comfy-cli
    với nhóm autogrow `images`) — KHÔNG truyền `images` vẫn chạy đúng cho T2I thuần, xem
    docstring `image_comfy_qwen.py` mục 3. Test này khoá lại để không ai vô tình thêm
    nhầm `images` rỗng/None vào — có thể phá format mà ComfyUI thật chấp nhận."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["6"]["class_type"] == "TextEncodeQwenImage21"
    assert "images" not in workflow["6"]["inputs"]
    assert workflow["6"]["inputs"]["prompt"] == "a cat"
    assert workflow["6"]["inputs"]["negative_prompt"] == ""


def test_generate_ksampler_uses_cfg_1_euler_simple_15_steps():
    """Tham số KSampler khớp CẢ 2 nguồn độc lập đã verify (template chính thức Comfy-Org
    + workflow mẫu thật `realrebelai/Qwen-Image-2.1_GGUFs`) — `cfg=1.0` là ĐÚNG cho
    Qwen-Image-2.1 (không phải thiếu guidance, khác nghi ngờ ban đầu). `steps=15` (đổi từ
    25, 2026-09-24) — verify thật qua GPU: nhanh hơn ~40%, chất lượng không đổi thấy được."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    ksampler = sent_body["prompt"]["3"]
    assert ksampler["class_type"] == "KSampler"
    assert ksampler["inputs"]["cfg"] == 1.0
    assert ksampler["inputs"]["steps"] == 15
    assert ksampler["inputs"]["sampler_name"] == "euler"
    assert ksampler["inputs"]["scheduler"] == "simple"
    assert ksampler["inputs"]["denoise"] == 1.0
    assert ksampler["inputs"]["positive"] == ["6", 0]
    assert ksampler["inputs"]["negative"] == ["6", 1]


def test_generate_uses_empty_latent_image_separate_from_text_encode_node():
    """`EmptyLatentImage` RIÊNG (không dùng `latent` output của chính
    `TextEncodeQwenImage21`) — cho phép kiểm soát tỷ lệ khung hình 16:9/9:16, đã verify
    qua workflow mẫu thật (xem docstring module)."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["10"]["class_type"] == "EmptyLatentImage"
    assert workflow["3"]["inputs"]["latent_image"] == ["10", 0]


def test_generate_default_aspect_ratio_uses_landscape_resolution():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["10"]["inputs"]["width"] == 1344
    assert workflow["10"]["inputs"]["height"] == 768


def test_generate_aspect_ratio_9_16_uses_portrait_resolution():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfyQwenImageProvider()
        provider.generate("a cat", seed=42, aspect_ratio="9:16")
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["10"]["inputs"]["width"] == 768
    assert workflow["10"]["inputs"]["height"] == 1344


def test_generate_raises_when_comfyui_rejects_job():
    with respx.mock:
        respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(400, json={"error": "unet_gguf node missing"}))
        provider = ComfyQwenImageProvider()
        with pytest.raises(RuntimeError, match="ComfyUI từ chối job"):
            provider.generate("a cat", seed=42)


def test_generate_raises_generation_interrupted_when_comfyui_reports_interrupted():
    with respx.mock:
        respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": "job-1"}))
        respx.get("http://127.0.0.1:8188/history/job-1").mock(
            return_value=Response(
                200,
                json={
                    "job-1": {
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [["execution_interrupted", {"node_id": "3", "node_type": "KSampler"}]],
                        }
                    }
                },
            )
        )
        provider = ComfyQwenImageProvider()
        with pytest.raises(GenerationInterrupted):
            provider.generate("a cat", seed=42)


def test_test_connection_ok():
    with respx.mock:
        respx.get("http://127.0.0.1:8188/system_stats").mock(return_value=Response(200, json={}))
        status = ComfyQwenImageProvider().test_connection()
    assert status.ok


def test_test_connection_unreachable():
    with respx.mock:
        respx.get("http://127.0.0.1:8188/system_stats").mock(side_effect=Exception("connection refused"))
        status = ComfyQwenImageProvider().test_connection()
    assert not status.ok
    assert "ComfyUI" in status.message
