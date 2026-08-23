"""Bộ sinh nội dung dự phòng — dùng khi provider là mock hoặc khi provider thật trả
JSON không hợp lệ (an toàn hoá pipeline thay vì crash giữa luồng).

Nội dung sinh ra bám vào topic/insight của Brief để không bị vô nghĩa, nhưng đây
KHÔNG phải nội dung chất lượng sản xuất — mọi nơi gọi tới đây đều nên được thay bằng
provider AI thật (Claude/GPT/Gemini hoặc model local GPU) trước khi dùng để đăng bài.
"""
from __future__ import annotations


def fallback_visual_fx(beat: dict) -> str:
    return f"cinematic shot, muted tones, no text, style theo kênh — minh hoạ: {beat.get('visual', '')}"


def fallback_audio_sfx(beat: dict) -> str:
    d = beat.get("direction", "")
    return d or "Nhịp vừa, giữ tông giọng theo BrandProfile kênh."
