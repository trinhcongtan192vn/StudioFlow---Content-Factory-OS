"""Điều phối pipeline AI — specs/07_prompt_templates.md.

Mỗi hàm: dựng prompt (system cố định ép JSON + nội dung template DB người dùng
chỉnh được), gọi provider, parse JSON; nếu lỗi/không parse được → dùng
fallback_content (xem module đó) để pipeline không bao giờ crash giữa luồng.

Tham số `usage` (tuỳ chọn) — nếu truyền 1 list rỗng vào, mỗi lệnh gọi LLM THẬT thành
công (không rơi vào fallback) sẽ append 1 dict {stage, provider, model, input_tokens,
output_tokens, cost} vào đó. Router (`routers/pipeline.py`) đọc list này sau khi gọi
để ghi Audit Log chi phí + cộng dồn Budget.spent — xem IMPLEMENTATION_REPORT.md mục
billing.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.models import PromptTemplate, PromptTemplateVersion
from app.pipeline import fallback_content as fb
from app.providers.base import LLMMessage, LLMProvider, LLMResult


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        match = re.search(r"[\{\[].*[\}\]]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:  # noqa: BLE001
                return None
        return None


def _record(usage: list | None, stage: str, llm: LLMProvider, result: LLMResult) -> None:
    if usage is None:
        return
    usage.append(
        {
            "stage": stage,
            "provider": llm.provider_name,
            "model": result.model or llm.model_name,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost": result.estimated_cost_usd,
        }
    )


def get_template_body(db: Session, task_key: str) -> str:
    tpl = db.query(PromptTemplate).filter(PromptTemplate.task == task_key).first()
    if not tpl:
        return ""
    ver = (
        db.query(PromptTemplateVersion)
        .filter(PromptTemplateVersion.template_id == tpl.id, PromptTemplateVersion.version == tpl.active_version)
        .first()
    )
    return ver.content if ver else ""


def render(body: str, ctx: dict) -> str:
    out = body
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v) if v is not None else "")
    return out


def _brand_ctx(brand: dict) -> dict:
    return {
        "channel": brand.get("channel_id", ""),
        "brand_voice": json.dumps(brand.get("brand_voice", {}), ensure_ascii=False),
        "forbidden": ", ".join(brand.get("forbidden", [])),
        "content_pillars": ", ".join(p["name"] for p in brand.get("content_pillars", [])),
        "hook_formats": ", ".join(brand.get("hook_formats_preferred", [])),
        "visual_style_prompt": brand.get("visual_style_prompt", ""),
        "retention_benchmark": json.dumps(brand.get("retention_benchmark", {}), ensure_ascii=False),
    }


JSON_SUFFIX = "\n\nChỉ trả JSON thuần theo đúng cấu trúc yêu cầu, không markdown fence, không thêm chữ nào khác."


def regenerate_shot_visual_fx(llm: LLMProvider, db: Session, brand: dict, beat: dict, visual_type: str = "image", usage: list | None = None) -> str:
    """Sinh lại RIÊNG trường Visual/FX cho 1 shot (đã build vòng 4 — tách khỏi TTS/Audio-SFX,
    khớp 2 nút "Tạo lại Visual" / "Tạo lại giọng đọc" riêng biệt trong design).

    `visual_type` ("image"/"video") chọn đúng template kênh `visual_image`/`visual_video`
    (2 task key riêng, khớp toggle Image/Video ở Visual Studio) — trước đây luôn dùng
    `visual_image` bất kể loại shot, khiến template `visual_video` không bao giờ được
    gọi tới (xem specs/07 mục 7)."""
    ctx = {**_brand_ctx(brand), "script_snippet": beat.get("audio", ""), "visual_description": beat.get("visual", "")}
    task_key = "visual_video" if visual_type == "video" else "visual_image"
    tpl = get_template_body(db, task_key) or "Sinh prompt hình ảnh cho shot theo style kênh {{channel}}, mô tả: {{visual_description}}."
    prompt = render(tpl, ctx) + "\n\nTrả về DUY NHẤT 1 đoạn prompt hình ảnh/video, KHÔNG dùng JSON, không thêm chữ giải thích."
    try:
        result = llm.complete("Bạn là AI Operator sinh prompt shot chuẩn hoá.", [LLMMessage("user", prompt)], max_tokens=300)
        if result.text and result.text.strip():
            _record(usage, "visual_fx", llm, result)
            return result.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return fb.fallback_visual_fx(beat)


def regenerate_shot_audio_sfx(llm: LLMProvider, db: Session, brand: dict, beat: dict, usage: list | None = None) -> str:
    """Sinh lại RIÊNG trường Audio/SFX (âm thanh, nhạc nền, emotion giọng đọc) cho 1 shot."""
    ctx = {**_brand_ctx(brand), "script_snippet": beat.get("audio", ""), "emotion_description": beat.get("direction", ""), "voice_profile": brand.get("brand_voice", {}).get("tone", "")}
    tpl = get_template_body(db, "visual_tts") or "Mô tả âm thanh/nhạc nền/emotion giọng đọc cho shot theo style kênh {{channel}}."
    prompt = render(tpl, ctx) + "\n\nTrả về DUY NHẤT 1 đoạn mô tả ngắn, KHÔNG dùng JSON, không thêm chữ giải thích."
    try:
        result = llm.complete("Bạn là đạo diễn âm thanh cho video YouTube.", [LLMMessage("user", prompt)], max_tokens=200)
        if result.text and result.text.strip():
            _record(usage, "audio_sfx", llm, result)
            return result.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return fb.fallback_audio_sfx(beat)
