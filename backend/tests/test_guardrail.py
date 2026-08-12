"""Unit test thuần cho app/guardrail/check.py — không cần DB/HTTP client."""
from app.guardrail.check import (
    check_brand_fit,
    compute_anchor_gap,
    run_guardrail_check,
    score_hook_strength,
)
from app.providers.base import LLMResult
from app.providers.mock import MockLLMProvider


class _JsonLLM:
    """Provider giả trả đúng JSON hook_strength — kiểm tra nhánh parse thành công."""

    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, score: float):
        self.score = score

    def complete(self, system, messages, **kwargs):
        return LLMResult(text=f'{{"hook_strength": {self.score}, "reasons": ["ok"]}}', input_tokens=10, output_tokens=5, estimated_cost_usd=0.01, model="fake-model")

    def test_connection(self):
        raise NotImplementedError


class _BrokenLLM:
    provider_name = "broken"
    model_name = "broken"

    def complete(self, system, messages, **kwargs):
        raise RuntimeError("provider lỗi mạng")

    def test_connection(self):
        raise NotImplementedError


def test_compute_anchor_gap_basic():
    body = [
        {"timestamp_sec": 0, "anchor": True},
        {"timestamp_sec": 20, "anchor": False},
        {"timestamp_sec": 50, "anchor": True},
        {"timestamp_sec": 55, "anchor": True},
    ]
    assert compute_anchor_gap(body) == 50  # khoảng lớn nhất giữa 2 anchor liên tiếp: 0 -> 50


def test_compute_anchor_gap_fewer_than_2_anchors():
    assert compute_anchor_gap([{"timestamp_sec": 0, "anchor": True}]) == 0
    assert compute_anchor_gap([{"timestamp_sec": 0, "anchor": False}]) == 0
    assert compute_anchor_gap([]) == 0


def test_check_brand_fit_detects_forbidden_word_case_insensitive():
    body = [{"timestamp_sec": 10, "audio": "Cam kết Lợi Nhuận chắc chắn 20%/tháng", "direction": ""}]
    warnings = check_brand_fit(body, ["cam kết lợi nhuận"])
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "red"
    assert warnings[0]["at_timestamp_sec"] == 10


def test_check_brand_fit_no_match():
    body = [{"timestamp_sec": 0, "audio": "Nội dung an toàn", "direction": ""}]
    assert check_brand_fit(body, ["từ cấm không xuất hiện"]) == []


def test_check_brand_fit_ignores_empty_forbidden_entries():
    body = [{"timestamp_sec": 0, "audio": "abc", "direction": ""}]
    assert check_brand_fit(body, ["", None]) == []  # type: ignore[list-item]


def test_score_hook_strength_parses_valid_json():
    score = score_hook_strength(_JsonLLM(0.85), "Hook mạnh", [])
    assert score == 0.85


def test_score_hook_strength_clamps_out_of_range():
    assert score_hook_strength(_JsonLLM(1.5), "x", []) == 1.0
    assert score_hook_strength(_JsonLLM(-0.5), "x", []) == 0.0


def test_score_hook_strength_records_usage_on_success():
    usage: list = []
    score_hook_strength(_JsonLLM(0.7), "Hook", [], usage=usage)
    assert len(usage) == 1
    assert usage[0]["stage"] == "guardrail"
    assert usage[0]["cost"] == 0.01


def test_score_hook_strength_fallback_heuristic_on_provider_error():
    # provider lỗi -> heuristic thuần code, không crash, không ghi usage
    usage: list = []
    score = score_hook_strength(_BrokenLLM(), "Ngắn?", ["pain"], usage=usage)
    assert 0.0 <= score <= 1.0
    assert usage == []


def test_score_hook_strength_mock_provider_uses_fallback():
    # MockLLMProvider không trả JSON -> luôn rơi vào fallback heuristic, không raise
    score = score_hook_strength(MockLLMProvider(), "Hook bất kỳ", [])
    assert 0.0 <= score <= 1.0


def test_run_guardrail_check_flags_low_hook_strength():
    result = run_guardrail_check(
        llm=_JsonLLM(0.3),
        hook_spoken="Hook yếu",
        body=[{"timestamp_sec": 0, "audio": "a", "direction": "", "anchor": True}] * 8,
        benchmark={"target_hook_strength": 0.7, "max_anchor_gap_sec": 45, "target_body_len_min": 8},
        forbidden=[],
        pain_points=[],
    )
    assert result["hook_strength"] == 0.3
    types = [w["type"] for w in result["warnings"]]
    assert "hook_strength" in types


def test_run_guardrail_check_flags_anchor_gap_and_body_length():
    body = [
        {"timestamp_sec": 0, "audio": "a", "direction": "", "anchor": True},
        {"timestamp_sec": 100, "audio": "b", "direction": "", "anchor": True},
    ]
    result = run_guardrail_check(
        llm=_JsonLLM(0.9),
        hook_spoken="",
        body=body,
        benchmark={"target_hook_strength": 0.7, "max_anchor_gap_sec": 45, "target_body_len_min": 8},
        forbidden=[],
        pain_points=[],
    )
    assert result["max_anchor_gap_sec"] == 100
    types = {w["type"] for w in result["warnings"]}
    assert "anchor_gap" in types
    assert "body_length" in types  # chỉ 2 đoạn, dưới target_body_len_min=8
    # hook_spoken rỗng -> không chấm hook_strength
    assert result["hook_strength"] is None


def test_run_guardrail_check_brand_fit_red_severity():
    body = [{"timestamp_sec": 0, "audio": "hứa hẹn lợi nhuận cố định", "direction": "", "anchor": True}] * 8
    result = run_guardrail_check(
        llm=_JsonLLM(0.9),
        hook_spoken="",
        body=body,
        benchmark={"target_hook_strength": 0.7, "max_anchor_gap_sec": 45, "target_body_len_min": 4},
        forbidden=["hứa hẹn lợi nhuận"],
        pain_points=[],
    )
    red_warnings = [w for w in result["warnings"] if w["severity"] == "red"]
    assert len(red_warnings) >= 1
