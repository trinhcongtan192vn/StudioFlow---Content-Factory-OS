"""Trích xuất transcript YouTube — dùng cho nguồn tham khảo Brief (§04 raw_knowledge).

Dựa trên youtube-transcript-api (https://github.com/jdepoix/youtube-transcript-api),
API v1.x (instance-based). Không cần API key — đọc trực tiếp caption công khai của video.
"""
from __future__ import annotations

import re

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

_ID_PATTERNS = [
    re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([0-9A-Za-z_-]{11})(?:[&?/]|$)"),
    re.compile(r"^([0-9A-Za-z_-]{11})$"),
]


def extract_video_id(url: str) -> str | None:
    url = url.strip()
    for pat in _ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def fetch_transcript_text(video_id: str) -> str:
    """Trả về transcript dạng text liền mạch. Ưu tiên tiếng Việt, fallback tiếng Anh
    hoặc bất kỳ ngôn ngữ nào có sẵn (kể cả transcript tự động sinh)."""
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=("vi", "en"))
    except NoTranscriptFound:
        try:
            transcript_list = api.list(video_id)
            transcript = next(iter(transcript_list))
            fetched = transcript.fetch()
        except Exception as e:  # noqa: BLE001
            raise ValueError("Video không có transcript ở bất kỳ ngôn ngữ nào") from e
    except TranscriptsDisabled as e:
        raise ValueError("Video đã tắt phụ đề/transcript") from e
    except VideoUnavailable as e:
        raise ValueError("Không tìm thấy video (link sai hoặc video riêng tư)") from e
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Lỗi khi lấy transcript: {e}") from e

    raw = fetched.to_raw_data()
    return " ".join(item["text"].strip() for item in raw if item.get("text", "").strip())
