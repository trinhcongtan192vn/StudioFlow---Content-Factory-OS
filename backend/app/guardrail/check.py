"""Retention Guardrail — specs/08_retention_guardrail.md.

Chỉ CẢNH BÁO, không chặn luồng (nguyên tắc human-gate). Hai chỉ số cốt lõi:
Hook Strength (LLM chấm theo rubric §07 mục 6) và Anchor Gap (tính thuần code).
Cộng thêm: Body quá ngắn, brand-fit (chạm forbidden) → cảnh báo đỏ.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.providers.base import LLMMessage, LLMProvider
from app.providers.factory import get_llm

HOOK_RUBRIC_SYSTEM = (
    "Bạn là bộ chấm điểm nội bộ cho guardrail retention. KHÔNG hiển thị điểm này cho người dùng ở bước chọn Hook — "
    "chỉ dùng để cảnh báo chất lượng. Chấm điểm HOOK theo thang 0.0-1.0, cộng điểm theo 4 tiêu chí ngang nhau: "
    "(1) Độ cụ thể — không chung chung. (2) Yếu tố tò mò/phản trực giác. (3) Liên quan trực tiếp pain point. "
    "(4) Độ dài đạt yêu cầu (≤5 giây khi đọc). Trả JSON thuần: {\"hook_strength\": 0.0-1.0, \"reasons\": [\"...\"]}. "
    "Không thêm chữ nào khác ngoài JSON."
)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:  # noqa: BLE001
                return None
        return None


def score_hook_strength(llm: LLMProvider, hook_spoken: str, pain_points: list[str], usage: list | None = None) -> float:
    user = f"HOOK: {hook_spoken}\nPain points liên quan: {', '.join(pain_points) or '(không có)'}"
    try:
        result = llm.complete(HOOK_RUBRIC_SYSTEM, [LLMMessage(role="user", content=user)], max_tokens=300)
        parsed = _extract_json(result.text)
        if parsed and "hook_strength" in parsed:
            if usage is not None:
                usage.append({"stage": "guardrail", "provider": llm.provider_name, "model": result.model or llm.model_name, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "cost": result.estimated_cost_usd})
            return max(0.0, min(1.0, float(parsed["hook_strength"])))
    except Exception:  # noqa: BLE001
        pass
    # Fallback heuristic đơn giản, thuần code — không chặn guardrail khi provider lỗi.
    score = 0.4
    if len(hook_spoken) <= 90:
        score += 0.15
    if any(p and p.lower() in hook_spoken.lower() for p in pain_points):
        score += 0.2
    if "?" in hook_spoken or re.search(r"\d", hook_spoken):
        score += 0.15
    return round(min(1.0, score), 2)


def compute_anchor_gap(body: list[dict]) -> int:
    """Khoảng cách lớn nhất (giây) giữa hai dòng liên tiếp có anchor=true (§08 mục 1)."""
    anchors = [b["timestamp_sec"] for b in body if b.get("anchor")]
    if len(anchors) < 2:
        return 0
    return max(b - a for a, b in zip(anchors, anchors[1:]))


def check_brand_fit(body: list[dict], forbidden: list[str]) -> list[dict]:
    warnings = []
    for word in forbidden:
        if not word:
            continue
        for b in body:
            haystack = f"{b.get('audio', '')} {b.get('direction', '')}".lower()
            if word.lower() in haystack:
                warnings.append(
                    {
                        "type": "brand_fit",
                        "severity": "red",
                        "at_timestamp_sec": b["timestamp_sec"],
                        "message": f'Chạm cấm kỵ brand: "{word}"',
                    }
                )
    return warnings


def run_guardrail_check(
    *,
    hook_spoken: str,
    body: list[dict],
    benchmark: dict,
    forbidden: list[str],
    pain_points: list[str],
    llm: LLMProvider | None = None,
    db: Session | None = None,
    usage: list | None = None,
) -> dict:
    """Truyền `db` (khuyến nghị, dùng ở router) để CHỈ gọi `get_llm()` — có thể raise
    `NoProviderConfiguredError` — khi thật sự cần chấm Hook Strength (`hook_spoken`
    khác rỗng); script import không có hook nên không đòi hỏi cấu hình Provider AI mới
    chạy được guardrail. Truyền `llm` trực tiếp khi đã có sẵn provider (test thuần,
    không cần DB)."""
    hook_strength = None
    if hook_spoken:
        resolved_llm = llm if llm is not None else (get_llm(db, task_role="guardrail") if db is not None else None)
        if resolved_llm is None:
            raise ValueError("run_guardrail_check cần truyền `llm` hoặc `db` khi hook_spoken khác rỗng")
        hook_strength = score_hook_strength(resolved_llm, hook_spoken, pain_points, usage=usage)
    max_gap = compute_anchor_gap(body)
    warnings: list[dict] = []

    target_hook = benchmark.get("target_hook_strength", 0.7)
    if hook_strength is not None and hook_strength < target_hook:
        warnings.append(
            {
                "type": "hook_strength",
                "severity": "amber",
                "at_timestamp_sec": 0,
                "message": f"Hook Strength {hook_strength:.2f} thấp hơn benchmark {target_hook:.2f}",
            }
        )

    max_gap_bench = benchmark.get("max_anchor_gap_sec", 45)
    if max_gap > max_gap_bench:
        # gắn vị trí ở điểm bắt đầu khoảng trống dài nhất
        anchors = [b["timestamp_sec"] for b in body if b.get("anchor")]
        at = 0
        for a, b in zip(anchors, anchors[1:]):
            if b - a == max_gap:
                at = a
                break
        warnings.append(
            {
                "type": "anchor_gap",
                "severity": "amber",
                "at_timestamp_sec": at,
                "message": f"Khoảng trống anchor {max_gap}s > {max_gap_bench}s",
            }
        )

    target_len = benchmark.get("target_body_len_min", 8)
    if len(body) < target_len:
        warnings.append(
            {
                "type": "body_length",
                "severity": "amber",
                "at_timestamp_sec": None,
                "message": f"Body chỉ có {len(body)} đoạn, dưới mức tối thiểu {target_len}",
            }
        )

    warnings.extend(check_brand_fit(body, forbidden))

    return {"hook_strength": hook_strength, "max_anchor_gap_sec": max_gap, "warnings": warnings}


def annotate_body_with_warnings(body: list[dict], warnings: list[dict]) -> list[dict]:
    """Gắn warning gần nhất vào từng dòng body để hiển thị inline (gạch chân + ghi chú lề, §06 màn ③)."""
    by_ts = {w["at_timestamp_sec"]: w for w in warnings if w.get("at_timestamp_sec") is not None}
    for item in body:
        item["warning"] = by_ts.get(item["timestamp_sec"])
    return body
