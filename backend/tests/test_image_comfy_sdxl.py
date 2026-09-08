"""Test app/providers/image_comfy_sdxl.py — checkpoint (`ckpt_name`) đổi được qua
`model_name` — **mới (2026-08-22)**, theo yêu cầu người dùng "cải thiện chất lượng ảnh
model local": trước đây `model_name` ở constructor tồn tại nhưng KHÔNG được dùng ở đâu cả
(field "chết"), checkpoint hardcode cứng `_CHECKPOINT_NAME`. Chưa có test nào cho file
này trước đợt này — respx mock ComfyUI (`/prompt`, `/history/{id}`, `/view`), không cần
GPU/ComfyUI thật, cùng convention respx đã dùng cho các adapter khác trong test_render.py.
"""
import json

import pytest
import respx
from httpx import Response

from app.providers.base import GenerationInterrupted
from app.providers.image_comfy_sdxl import _CHECKPOINT_NAME, _NEGATIVE_PROMPT, ComfySDXLImageProvider

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mock_comfyui_success(prompt_id: str = "job-1"):
    submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(200, json={"prompt_id": prompt_id}))
    respx.get(f"http://127.0.0.1:8188/history/{prompt_id}").mock(
        return_value=Response(200, json={prompt_id: {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
    )
    respx.get("http://127.0.0.1:8188/view").mock(return_value=Response(200, content=FAKE_PNG))
    return submit_route


def test_generate_raises_generation_interrupted_when_comfyui_reports_interrupted():
    """Bug thật (2026-08-23, phát hiện lúc điều tra shot B01 báo lỗi thật của người
    dùng): ComfyUI báo CẢ lỗi thực thi thật LẪN job bị Dừng (`/interrupt`) qua CÙNG
    `status_str == "error"` — chỉ phân biệt được qua message `execution_interrupted`
    trong `status.messages`. PHẢI raise `GenerationInterrupted` (không phải RuntimeError
    chung chung) để `engine.py` xử lý như huỷ thật, không dump lỗi kỹ thuật cho người
    dùng."""
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
                            "messages": [
                                ["execution_start", {}],
                                ["execution_interrupted", {"node_id": "3", "node_type": "KSampler"}],
                            ],
                        }
                    }
                },
            )
        )
        provider = ComfySDXLImageProvider()
        with pytest.raises(GenerationInterrupted):
            provider.generate("a cat", seed=42)


def test_generate_raises_plain_runtime_error_for_real_execution_error():
    """Đối chứng: lỗi thực thi THẬT (không có `execution_interrupted` trong messages)
    vẫn phải raise `RuntimeError` như cũ — không vô tình nuốt lỗi thật thành "đã dừng"."""
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
                            "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]],
                        }
                    }
                },
            )
        )
        provider = ComfySDXLImageProvider()
        with pytest.raises(RuntimeError) as exc_info:
            provider.generate("a cat", seed=42)
        assert not isinstance(exc_info.value, GenerationInterrupted)


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
# Style LoRA (đợt 2, 2026-08-22; STACK nhiều LoRA 2026-08-23) — chuỗi node LoraLoader
# (core ComfyUI, không phải custom node).
# ---------------------------------------------------------------------------
def test_generate_without_loras_has_no_lora_node():
    """Không cấu hình LoRA nào (mặc định) — workflow PHẢI giữ nguyên nối thẳng checkpoint
    → sampler, không có node LoraLoader — không đổi hành vi cho ai chưa cấu hình gì."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert "130" not in workflow
    assert workflow["3"]["inputs"]["model"] == ["4", 0]
    assert workflow["6"]["inputs"]["clip"] == ["4", 1]


def test_generate_with_1_lora_inserts_loraloader_node():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, loras=[{"name": "InkArtXL_1.2.safetensors", "strength": 0.8}])
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["130"]["class_type"] == "LoraLoader"
    assert workflow["130"]["inputs"]["lora_name"] == "InkArtXL_1.2.safetensors"
    assert workflow["130"]["inputs"]["strength_model"] == 0.8
    assert workflow["130"]["inputs"]["strength_clip"] == 0.8
    assert workflow["130"]["inputs"]["model"] == ["4", 0]
    assert workflow["130"]["inputs"]["clip"] == ["4", 1]
    # KSampler + cả 2 CLIPTextEncode (positive/negative) phải nối qua LoraLoader, không
    # còn nối thẳng checkpoint nữa.
    assert workflow["3"]["inputs"]["model"] == ["130", 0]
    assert workflow["6"]["inputs"]["clip"] == ["130", 1]
    assert workflow["7"]["inputs"]["clip"] == ["130", 1]


def test_generate_with_2_loras_chains_loraloader_nodes():
    """Bug thật đề xuất người dùng (2026-08-23) — 1 LoRA đơn không đủ vừa khoá chất liệu
    vừa ép đúng hướng văn hoá Việt — cần STACK được 2-3 LoRA cùng lúc."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate(
            "a cat", seed=42,
            loras=[{"name": "ClassipeintXL2.1.safetensors", "strength": 0.75}, {"name": "GuohuaSDXL.safetensors", "strength": 0.6}],
        )
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    # LoRA đầu nối từ checkpoint, LoRA sau nối tiếp LoRA TRƯỚC (không phải lại từ checkpoint).
    assert workflow["130"]["inputs"]["lora_name"] == "ClassipeintXL2.1.safetensors"
    assert workflow["130"]["inputs"]["model"] == ["4", 0]
    assert workflow["131"]["inputs"]["lora_name"] == "GuohuaSDXL.safetensors"
    assert workflow["131"]["inputs"]["model"] == ["130", 0]
    assert workflow["131"]["inputs"]["clip"] == ["130", 1]
    # Sampler/CLIPTextEncode phải nối qua LoRA CUỐI trong chuỗi.
    assert workflow["3"]["inputs"]["model"] == ["131", 0]
    assert workflow["6"]["inputs"]["clip"] == ["131", 1]
    assert workflow["7"]["inputs"]["clip"] == ["131", 1]


def test_generate_img2img_with_lora_inserts_loraloader_node():
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "anchor.png", "subfolder": ""}))
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, reference_image=FAKE_PNG, loras=[{"name": "ClassipeintXL2.1.safetensors", "strength": 1.0}])
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["130"]["inputs"]["lora_name"] == "ClassipeintXL2.1.safetensors"
    assert workflow["3"]["inputs"]["model"] == ["130", 0]
    assert workflow["6"]["inputs"]["clip"] == ["130", 1]
    assert workflow["7"]["inputs"]["clip"] == ["130", 1]


def test_generate_with_extra_negative_appends_to_negative_prompt():
    """`cultural_lock_negative` (mới 2026-08-23) — nối vào negative prompt THẬT."""
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, extra_negative="japanese kimono, korean hanbok")
        sent_body = json.loads(submit_route.calls[0].request.content)

    negative_text = sent_body["prompt"]["7"]["inputs"]["text"]
    assert "japanese kimono, korean hanbok" in negative_text
    assert _NEGATIVE_PROMPT in negative_text


def test_negative_prompt_blocks_text_overlay_and_3d_plastic_look():
    """Đợt 2: 'no text/title card/caption' CHUYỂN từ prompt dương (đợt 1) sang negative
    prompt thật; thêm mới chặn hướng 3D nhựa hoá (art direction painterly/sơn dầu)."""
    for kw in ("title card", "caption", "subtitle", "3d render", "plastic", "photorealistic"):
        assert kw in _NEGATIVE_PROMPT


# ---------------------------------------------------------------------------
# Ảnh tham chiếu phong cách (IPAdapter) — mới (2026-08-23), theo yêu cầu người dùng
# chống thiên lệch văn hoá Nhật/Hàn. CHƯA thể verify thật trên ComfyUI+IPAdapter (custom
# node cộng đồng) — test này chỉ xác nhận WORKFLOW JSON build đúng cấu trúc mong đợi.
# ---------------------------------------------------------------------------
FAKE_PNG_2 = b"\x89PNG\r\n\x1a\n" + b"\x11" * 32


def test_generate_with_1_reference_image_inserts_ipadapter_nodes():
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "ref_1.png", "subfolder": ""}))
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, reference_images=[FAKE_PNG], style_reference_weight=0.6)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert workflow["90"]["class_type"] == "CLIPVisionLoader"
    assert workflow["91"]["class_type"] == "IPAdapterModelLoader"
    assert workflow["920"]["class_type"] == "LoadImage"
    assert workflow["920"]["inputs"]["image"] == "ref_1.png"
    assert "930" not in workflow  # chỉ 1 ảnh — không cần ImageBatch
    assert workflow["94"]["class_type"] == "IPAdapterApply"
    assert workflow["94"]["inputs"]["image"] == ["920", 0]
    assert workflow["94"]["inputs"]["weight"] == 0.6
    # KSampler phải nối qua IPAdapterApply, không còn nối thẳng checkpoint.
    assert workflow["3"]["inputs"]["model"] == ["94", 0]


def test_generate_with_multiple_reference_images_chains_imagebatch():
    with respx.mock:
        upload_route = respx.post("http://127.0.0.1:8188/upload/image").mock(
            side_effect=[Response(200, json={"name": "ref_1.png", "subfolder": ""}), Response(200, json={"name": "ref_2.png", "subfolder": ""}), Response(200, json={"name": "ref_3.png", "subfolder": ""})]
        )
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, reference_images=[FAKE_PNG, FAKE_PNG_2, FAKE_PNG])
        sent_body = json.loads(submit_route.calls[0].request.content)

    assert upload_route.call_count == 3
    workflow = sent_body["prompt"]
    assert workflow["920"]["inputs"]["image"] == "ref_1.png"
    assert workflow["921"]["inputs"]["image"] == "ref_2.png"
    assert workflow["922"]["inputs"]["image"] == "ref_3.png"
    # ImageBatch chain: ảnh 1+2 trước, rồi kết quả + ảnh 3.
    assert workflow["931"]["class_type"] == "ImageBatch"
    assert workflow["931"]["inputs"] == {"image1": ["920", 0], "image2": ["921", 0]}
    assert workflow["932"]["inputs"] == {"image1": ["931", 0], "image2": ["922", 0]}
    assert workflow["94"]["inputs"]["image"] == ["932", 0]


def test_ipadapter_applies_after_lora_when_both_used():
    """LoRA khoá 'chữ ký kỹ thuật' TRƯỚC, IPAdapter khoá 'cảm hứng thị giác' SAU — theo
    đúng thứ tự gọi trong _build_txt2img_workflow (_add_lora_nodes rồi _add_ipadapter_nodes)."""
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "ref_1.png", "subfolder": ""}))
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42, loras=[{"name": "InkArtXL_1.2.safetensors", "strength": 0.8}], reference_images=[FAKE_PNG])
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    # IPAdapter input model PHẢI trỏ tới output LoRA (không phải checkpoint trực tiếp).
    assert workflow["94"]["inputs"]["model"] == ["130", 0]
    assert workflow["3"]["inputs"]["model"] == ["94", 0]


def test_generate_falls_back_to_no_ipadapter_when_comfyui_rejects_node():
    """Bug thật CÓ THỂ gặp (2026-08-23) — custom node IPAdapter chưa cài/lệch version:
    ComfyUI từ chối job (400, VD 'node type not found') KHÔNG được chặn hẳn sinh ảnh —
    phải thử lại NGAY 1 lần không có IPAdapter."""
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "ref_1.png", "subfolder": ""}))
        submit_route = respx.post("http://127.0.0.1:8188/prompt").mock(
            side_effect=[Response(400, json={"error": "node type not found: IPAdapterApply"}), Response(200, json={"prompt_id": "job-1"})]
        )
        respx.get("http://127.0.0.1:8188/history/job-1").mock(
            return_value=Response(200, json={"job-1": {"outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
        )
        respx.get("http://127.0.0.1:8188/view").mock(return_value=Response(200, content=FAKE_PNG))
        provider = ComfySDXLImageProvider()
        data = provider.generate("a cat", seed=42, reference_images=[FAKE_PNG])

    assert data == FAKE_PNG
    assert submit_route.call_count == 2
    second_body = json.loads(submit_route.calls[1].request.content)
    assert "94" not in second_body["prompt"]  # lần retry KHÔNG có IPAdapter


def test_generate_raises_when_fallback_also_fails():
    with respx.mock:
        respx.post("http://127.0.0.1:8188/upload/image").mock(return_value=Response(200, json={"name": "ref_1.png", "subfolder": ""}))
        respx.post("http://127.0.0.1:8188/prompt").mock(return_value=Response(400, json={"error": "still broken"}))
        provider = ComfySDXLImageProvider()
        with pytest.raises(RuntimeError, match="ComfyUI từ chối job"):
            provider.generate("a cat", seed=42, reference_images=[FAKE_PNG])


def test_generate_without_reference_images_has_no_ipadapter_nodes():
    with respx.mock:
        submit_route = _mock_comfyui_success()
        provider = ComfySDXLImageProvider()
        provider.generate("a cat", seed=42)
        sent_body = json.loads(submit_route.calls[0].request.content)

    workflow = sent_body["prompt"]
    assert "90" not in workflow
    assert "94" not in workflow
