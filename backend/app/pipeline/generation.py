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


def generate_research(llm: LLMProvider, db: Session, brand: dict, brief: dict, usage: list | None = None) -> dict:
    ctx = {**_brand_ctx(brand), "topic": brief.get("topic", ""), "brief": json.dumps(brief, ensure_ascii=False), "outline_count": 3}
    tpl = get_template_body(db, "outline") or "Từ Brief {{brief}}, sinh {{outline_count}} outline khác góc tiếp cận."
    prompt = render(tpl, ctx) + JSON_SUFFIX + '\nCấu trúc: {"synthesis": "...", "outlines": [{"id","title","points":[...]}]}'
    try:
        result = llm.complete("Bạn là trợ lý nghiên cứu nội dung YouTube tiếng Việt.", [LLMMessage("user", prompt)], max_tokens=1500)
        parsed = _extract_json(result.text)
        if parsed and parsed.get("outlines"):
            _record(usage, "research", llm, result)
            for o in parsed["outlines"]:
                o.setdefault("selected", False)
            parsed.setdefault("synthesis", "")
            return parsed
    except Exception:  # noqa: BLE001
        pass
    return {"synthesis": f"Tổng hợp tự động từ tư liệu Brief cho chủ đề \"{brief.get('topic', '')}\".", "outlines": fb.fallback_outlines(brief.get("topic", ""))}


def generate_hooks(llm: LLMProvider, db: Session, brand: dict, brief: dict, chosen_outline: dict, usage: list | None = None) -> list[dict]:
    ctx = {**_brand_ctx(brand), "chosen_outline": json.dumps(chosen_outline, ensure_ascii=False), "hook_count": 3}
    tpl = get_template_body(db, "hook") or "Viết 3 biến thể HOOK theo 3 kiểu tâm lý khác nhau."
    prompt = render(tpl, ctx) + JSON_SUFFIX + '\nCấu trúc: {"hooks": [{"id","psychological_type","spoken","visual"}]}'
    try:
        result = llm.complete("Bạn là biên kịch hook video YouTube tiếng Việt.", [LLMMessage("user", prompt)], max_tokens=800)
        parsed = _extract_json(result.text)
        if parsed and parsed.get("hooks"):
            _record(usage, "hooks", llm, result)
            for h in parsed["hooks"]:
                h.setdefault("selected", False)
            return parsed["hooks"]
    except Exception:  # noqa: BLE001
        pass
    pain_points = brief.get("audience", {}).get("pain_points", [])
    return fb.fallback_hooks(brief.get("topic", ""), pain_points)


def generate_full_script(llm: LLMProvider, db: Session, brand: dict, brief: dict, outline: dict, hook: dict, framework: str, length_label: str, usage: list | None = None) -> str:
    ctx = {
        **_brand_ctx(brand),
        "outline": json.dumps(outline, ensure_ascii=False),
        "hook": json.dumps(hook, ensure_ascii=False),
        "framework": framework,
        "length": length_label,
    }
    tpl = get_template_body(db, "script") or "Viết Master Script hoàn chỉnh từ Outline {{outline}} và Hook {{hook}}."
    prompt = render(tpl, ctx) + "\n\nTrả về đoạn văn bản kịch bản liền mạch (Full Script), KHÔNG bóc tách theo timestamp ở bước này, KHÔNG dùng JSON."
    try:
        result = llm.complete("Bạn là biên kịch kịch bản video YouTube tiếng Việt, giọng văn tự nhiên.", [LLMMessage("user", prompt)], max_tokens=1800)
        if result.text and len(result.text.strip()) > 40:
            _record(usage, "script", llm, result)
            return result.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return fb.fallback_full_script(brief.get("topic", ""), brief.get("insight", ""), hook.get("spoken", ""), framework)


def regenerate_full_script(llm: LLMProvider, db: Session, brand: dict, current_script: str, user_feedback: str, length_label: str, usage: list | None = None) -> str:
    ctx = {**_brand_ctx(brand), "current_script": current_script, "user_feedback": user_feedback, "length": length_label}
    tpl = get_template_body(db, "script_revise") or "Viết lại Full Script {{current_script}} theo góp ý: {{user_feedback}}."
    prompt = render(tpl, ctx) + "\n\nTrả về đoạn văn bản kịch bản liền mạch đã sửa, KHÔNG dùng JSON."
    try:
        result = llm.complete("Bạn là biên tập kịch bản video YouTube tiếng Việt.", [LLMMessage("user", prompt)], max_tokens=1800)
        if result.text and len(result.text.strip()) > 40:
            _record(usage, "script_revise", llm, result)
            return result.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return current_script + f"\n\n[Đã điều chỉnh theo góp ý: {user_feedback}]"


def breakdown_script(llm: LLMProvider, db: Session, full_text: str, max_gap_sec: int, usage: list | None = None) -> list[dict]:
    ctx = {"script_text": full_text}
    tpl = get_template_body(db, "script_breakdown") or "Phân rã Full Script {{script_text}} thành các đoạn theo timestamp, audio, visual và direction."
    prompt = render(tpl, ctx) + JSON_SUFFIX + '\nCấu trúc: {"body": [{"timestamp_sec":int,"end_sec":int,"audio","visual","direction","anchor":bool}]}'
    try:
        result = llm.complete("Bạn là trợ lý dựng kịch bản đa cột cho video YouTube.", [LLMMessage("user", prompt)], max_tokens=2000)
        parsed = _extract_json(result.text)
        if parsed and parsed.get("body"):
            _record(usage, "script_breakdown", llm, result)
            for item in parsed["body"]:
                item.setdefault("direction_label", "Direction")
            return parsed["body"]
    except Exception:  # noqa: BLE001
        pass
    return fb.fallback_breakdown(full_text, max_gap_sec)


def generate_shots(llm: LLMProvider, db: Session, brand: dict, body: list[dict], usage: list | None = None) -> list[dict]:
    """Sinh HÀNG LOẠT toàn bộ shot ban đầu từ script — khác `regenerate_shot_visual_fx`
    (sinh lại 1 shot riêng lẻ) nên dùng task key riêng `visual_shots_init`, tránh tái sử
    dụng `visual_image`/`visual_video` với 2 bộ tham số khác nhau cho cùng 1 task key
    (từng gây lỗi `{{placeholder}}` không được thay thế — xem specs/07 mục 7)."""
    ctx = {**_brand_ctx(brand), "script": json.dumps(body, ensure_ascii=False)}
    tpl = get_template_body(db, "visual_shots_init") or "Sinh prompt hình ảnh/video cho từng shot theo style kênh {{channel}}."
    prompt = render(tpl, ctx) + JSON_SUFFIX + '\nCấu trúc: {"shots": [{"shot_id","asset_type","visual_type","visual_fx","audio_sfx","linked_timestamp_sec"}]}'
    try:
        result = llm.complete("Bạn là AI Operator sinh prompt shot chuẩn hoá.", [LLMMessage("user", prompt)], max_tokens=1500)
        parsed = _extract_json(result.text)
        if parsed and parsed.get("shots"):
            _record(usage, "shots", llm, result)
            return parsed["shots"]
    except Exception:  # noqa: BLE001
        pass
    return fb.fallback_shots(body)


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


def generate_titles_and_meta(llm: LLMProvider, db: Session, brand: dict, brief: dict, body: list[dict], usage: list | None = None) -> dict:
    ctx = {**_brand_ctx(brand), "brief": json.dumps(brief, ensure_ascii=False), "script": json.dumps(body, ensure_ascii=False)}
    tpl = get_template_body(db, "thumbnail") or "Tạo 5-10 tiêu đề tối ưu SEO+CTR và concept thumbnail."
    prompt = render(tpl, ctx) + JSON_SUFFIX + '\nCấu trúc: {"titles":[{"text","seo_score_hint","angle"}], "thumbnail_description":"...", "youtube_description":"...", "hashtags":["..."]}'
    try:
        result = llm.complete("Bạn là chuyên gia SEO YouTube tiếng Việt.", [LLMMessage("user", prompt)], max_tokens=1200)
        parsed = _extract_json(result.text)
        if parsed and parsed.get("titles"):
            _record(usage, "titles", llm, result)
            chapters = [{"ts_sec": b["timestamp_sec"], "label": (b["audio"][:44] + "…") if len(b["audio"]) > 44 else b["audio"]} for b in body]
            return {
                "titles": parsed["titles"],
                "youtube_meta": {
                    "description": parsed.get("youtube_description", ""),
                    "hashtags": parsed.get("hashtags", []),
                    "chapters": chapters,
                    "thumbnail_description": parsed.get("thumbnail_description", ""),
                },
            }
    except Exception:  # noqa: BLE001
        pass
    topic = brief.get("topic", "")
    return {"titles": fb.fallback_titles(topic), "youtube_meta": fb.fallback_youtube_meta(topic, body)}
