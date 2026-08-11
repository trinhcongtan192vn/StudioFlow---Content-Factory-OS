"""Bộ sinh nội dung dự phòng — dùng khi provider là mock hoặc khi provider thật trả
JSON không hợp lệ (an toàn hoá pipeline thay vì crash giữa luồng).

Nội dung sinh ra bám vào topic/insight của Brief để không bị vô nghĩa, nhưng đây
KHÔNG phải nội dung chất lượng sản xuất — mọi nơi gọi tới đây đều nên được thay bằng
provider AI thật (Claude/GPT/Gemini hoặc model local GPU) trước khi dùng để đăng bài.
"""
from __future__ import annotations


def fallback_outlines(topic: str) -> list[dict]:
    t = topic or "chủ đề video"
    return [
        {
            "id": "o1",
            "title": "Góc nhìn: Nguyên nhân gốc rễ",
            "points": [
                f'Mở bằng một chi tiết phản trực giác về "{t}"',
                "Truy về 2-3 nguyên nhân sâu, xếp theo mức độ bất ngờ",
                "Kết bằng câu hỏi mở cho người xem tự đối chiếu",
            ],
            "selected": False,
        },
        {
            "id": "o2",
            "title": "Góc nhìn: Theo dòng thời gian",
            "points": [
                f'Dựng lại trình tự sự kiện/quyết định liên quan tới "{t}"',
                "Nhấn vào 1-2 bước ngoặt then chốt",
                "So sánh kỳ vọng ban đầu với kết quả thực tế",
            ],
            "selected": False,
        },
        {
            "id": "o3",
            "title": "Góc nhìn: Phản biện quan niệm phổ biến",
            "points": [
                f'Nêu quan niệm sai phổ biến nhất về "{t}"',
                "Dùng bằng chứng/case study để lật lại quan niệm đó",
                "Đưa ra góc nhìn đúng kèm hành động cụ thể",
            ],
            "selected": False,
        },
    ]


HOOK_TYPES = ["Khoảng trống tò mò", "Đối lập bất ngờ", "Cảnh báo mất mát"]


def fallback_hooks(topic: str, pain_points: list[str]) -> list[dict]:
    t = topic or "điều này"
    pain = pain_points[0] if pain_points else "sai lầm phổ biến"
    texts = [
        f'Ít ai nhận ra "{t}" thực ra bắt nguồn từ {pain} — cho tới khi đã quá muộn.',
        f'Mọi người nghĩ "{t}" là chuyện bình thường. Sự thật hoàn toàn ngược lại.',
        f'Nếu còn tiếp tục {pain}, cái giá cho "{t}" sẽ lớn hơn bạn nghĩ rất nhiều.',
    ]
    return [
        {"id": f"h{i}", "psychological_type": HOOK_TYPES[i], "spoken": texts[i], "visual": "Cảnh mở đầu tương phản, nhịp nhanh.", "selected": False}
        for i in range(3)
    ]


def fallback_full_script(topic: str, insight: str, hook_text: str, framework: str = "AIDA") -> str:
    t = topic or "chủ đề video"
    ins = insight or "một góc nhìn ít người để ý"
    return (
        f"{hook_text}\n\n"
        f'Đằng sau "{t}" là {ins}. Phần lớn mọi người bỏ qua chi tiết này vì nó không hiển nhiên ngay từ đầu.\n\n'
        f"Nhìn kỹ hơn, có thể thấy một chuỗi lựa chọn nhỏ cộng dồn lại thành kết quả lớn — mỗi bước tưởng như vô hại "
        f"lại góp phần định hình toàn bộ câu chuyện.\n\n"
        f"Một ví dụ cụ thể minh hoạ rõ điều này: khi so sánh hai lựa chọn khác nhau ngay từ điểm khởi đầu, khoảng "
        f"cách kết quả sau một thời gian là rất rõ ràng.\n\n"
        f"Bài học rút ra không nằm ở việc đổ lỗi, mà ở việc nhận diện đúng thời điểm để thay đổi — càng sớm, cái giá "
        f"phải trả càng nhỏ."
    )


def fallback_breakdown(full_text: str, max_gap_sec: int = 45) -> list[dict]:
    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]
    body = []
    t = 0
    for i, para in enumerate(paragraphs):
        dur = max(6, min(max_gap_sec - 2, 8 + len(para) // 18))
        body.append(
            {
                "timestamp_sec": t,
                "end_sec": t + dur,
                "audio": para,
                "visual": "B-roll minh hoạ nội dung đoạn tương ứng, tông màu theo style kênh.",
                "direction": "Nhịp vừa, nhấn ở câu chốt." if i % 2 == 0 else "Chậm lại, để người xem kịp tiếp nhận.",
                "direction_label": "Direction",
                "anchor": i == 0 or dur >= max_gap_sec - 4,
            }
        )
        t += dur
    return body


def fallback_shots(body: list[dict]) -> list[dict]:
    emotions = ["Dứt khoát, tạo cảm giác cấp bách", "Thân thiện, gần gũi như đang tâm sự", "Chắc chắn, nhấn mạnh ý chính", "Ấm, khích lệ, chậm lại ở cuối"]
    shots = []
    for i, b in enumerate(body):
        shots.append(
            {
                "shot_id": f"S{i + 1:02d}",
                "asset_type": "broll_image" if i % 3 != 1 else "broll_video",
                "visual_type": "image" if i % 3 != 1 else "video",
                "provider": None,
                "visual_fx": f"cinematic {'wide shot' if i % 2 == 0 else 'close-up'}, muted tones, no text, style theo kênh — minh hoạ: {b['visual']}",
                "audio_sfx": emotions[i % len(emotions)],
                "block_id": b.get("block_id"),
                "linked_timestamp_sec": b["timestamp_sec"],
            }
        )
    return shots


def fallback_visual_fx(beat: dict) -> str:
    return f"cinematic shot, muted tones, no text, style theo kênh — minh hoạ: {beat.get('visual', '')}"


def fallback_audio_sfx(beat: dict) -> str:
    d = beat.get("direction", "")
    return d or "Nhịp vừa, giữ tông giọng theo BrandProfile kênh."


def fallback_titles(topic: str) -> list[dict]:
    t = topic or "chủ đề này"
    return [
        {"text": f'Sai lầm khiến nhiều người mất thời gian vì "{t}"', "seo_score_hint": "cao", "angle": "seo"},
        {"text": f'Không ai nói với bạn điều này về "{t}"', "seo_score_hint": "trung bình", "angle": "curiosity"},
        {"text": f'3 phút để hiểu đúng về "{t}"', "seo_score_hint": "cao", "angle": "benefit"},
    ]


def fallback_youtube_meta(topic: str, body: list[dict]) -> dict:
    chapters = [{"ts_sec": b["timestamp_sec"], "label": (b["audio"][:44] + "…") if len(b["audio"]) > 44 else b["audio"]} for b in body]
    return {
        "description": f'Video này khai thác một góc nhìn ít được nói tới về "{topic or "chủ đề"}", dựa trên phân tích thực tế, không suy diễn.',
        "hashtags": ["#StudioFlow", "#NoiDungChatLuong"],
        "chapters": chapters,
        "thumbnail_description": f'bold thumbnail concept, "{topic or "chủ đề"}" làm text overlay chính, high-contrast subject cutout, tối đa 3 màu, dễ đọc ở kích thước nhỏ',
    }
