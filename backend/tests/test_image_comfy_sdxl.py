"""Test app/providers/image_comfy_sdxl.py — checkpoint (`ckpt_name`) đổi được qua
`model_name` — **mới (2026-08-22)**, theo yêu cầu người dùng "cải thiện chất lượng ảnh
model local": trước đây `model_name` ở constructor tồn tại nhưng KHÔNG được dùng ở đâu cả
(field "chết"), checkpoint hardcode cứng `_CHECKPOINT_NAME`. Chưa có test nào cho file
này trước đợt này — respx mock ComfyUI (`/prompt`, `/history/{id}`, `/view`), không cần
GPU/ComfyUI thật, cùng convention respx đã dùng cho các adapter khác trong test_render.py.
"""
import json

import respx
from httpx import Response

from app.providers.image_comfy_sdxl import _CHECKPOINT_NAME, _NEGATIVE_PROMPT, ComfySDXLImageProvider

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mock_comfyui_success(prompt_id: str = "job-1"):
    submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": prompt_id}))
    respx.get(f"http://127.0.0.1:8188/history/{prompt_id}").mock(
        return_value=Response(200, json={prompt_id: {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
    )
    respx.get("http://127.0.0.1:8188/view").mock(return_value=Response(200, content=FAKE_PNG))
    return submit_route


def test_generate_uses_custom_model_name_as_checkpoint():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider(model_name="juggernautXL_v9.safetensors")
        data = provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert data == FAKE_PNG
    assert sent_body["prompt"]["4"]["inputs"]["ckpt_name"] == "juggernautXL_v9.safetensors"


def test_generate_falls_back_to_default_checkpoint_when_model_name_empty():
    """Chưa cấu hình `model_name` (rỗng) — PHẢI dùng đúng checkpoint mặc định cũ, không
    đổi hành vi cho ai chưa cấu hình gì."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert sent_body["prompt"]["4"]["inputs"]["ckpt_name"] == _CHECKPOINT_NAME
    assert _CHECKPOINT_NAME == "paintersCheckpointOilPaint_v11.safetensors"  # đợt 2 — đổi từ sd_xl_base_1.0 sang checkpoint painterly


def test_generate_img2img_also_uses_custom_checkpoint():
    """Nhánh img2img (có reference_image) cũng phải dùng đúng ckpt_name — 2 workflow
    builder riêng (`_build_txt2img_workflow`/`_build_img2img_workflow`) dễ lệch nhau nếu
    chỉ sửa 1 trong 2."""
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "anchor.png", "subfolder": ""}))
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider(model_name="realvisxl_v5.safetensors")
        provider.generate("a cat", seed=42, reference_image=FAKE_PNG)
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert sent_body["prompt"]["4"]["inputs"]["ckpt_name"] == "realvisxl_v5.safetensors"


# ---------------------------------------------------------------------------
# Style LoRA (đợt 2, 2026-08-22) — node LoraLoader (core ComfyUI, không phải custom node)
# ---------------------------------------------------------------------------
def test_generate_without_lora_name_has_no_lora_node():
    """Không cấu hình LoRA (mặc định) — workflow PHẢI giữ nguyên nối thẳng checkpoint →
    sampler, không có node LoraLoader — không đổi hành vi cho ai chưa cấu hình gì."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert "13" not in workflow
    assert workflow["3"]["inputs"]["model"] == ["4", 0]
    assert workflow["6"]["inputs"]["clip"] == ["4", 1]


def test_generate_with_lora_name_inserts_loraloader_node():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, lora_name="InkArtXL_1.2.safetensors", lora_strength=0.8)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["13"]["class_type"] == "LoraLoader"
    assert workflow["13"]["inputs"]["lora_name"] == "InkArtXL_1.2.safetensors"
    assert workflow["13"]["inputs"]["strength_model"] == 0.8
    assert workflow["13"]["inputs"]["strength_clip"] == 0.8
    assert workflow["13"]["inputs"]["model"] == ["4", 0]
    assert workflow["13"]["inputs"]["clip"] == ["4", 1]
    # KSampler + cả 2 CLIPTextEncode (positive/negative) phải nối qua LoraLoader, không
    # còn nối thẳng checkpoint nữa.
    assert workflow["3"]["inputs"]["model"] == ["13", 0]
    assert workflow["6"]["inputs"]["clip"] == ["13", 1]
    assert workflow["7"]["inputs"]["clip"] == ["13", 1]


def test_generate_img2img_with_lora_name_inserts_loraloader_node():
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "anchor.png", "subfolder": ""}))
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, reference_image=FAKE_PNG, lora_name="ClassipeintXL2.1.safetensors", lora_strength=1.0)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["13"]["inputs"]["lora_name"] == "ClassipeintXL2.1.safetensors"
    assert workflow["3"]["inputs"]["model"] == ["13", 0]
    assert workflow["6"]["inputs"]["clip"] == ["13", 1]
    assert workflow["7"]["inputs"]["clip"] == ["13", 1]


def test_negative_prompt_blocks_text_overlay_and_3d_plastic_look():
    """Đợt 2: 'no text/title card/caption' CHUYỂN từ prompt dương (đợt 1) sang negative
    prompt thật; thêm mới chặn hướng 3D nhựa hoá (art direction painterly/sơn dầu)."""
    for kw in ("title card", "caption", "subtitle", "3d render", "plastic", "photorealistic"):
        assert kw in _NEGATIVE_PROMPT
