"""Unit test thuần cho app/youtube.py::extract_video_id — không gọi mạng."""
import pytest

from app.youtube import extract_video_id

VALID_CASES = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
    ("http://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=10", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),  # dán thẳng video ID
]


@pytest.mark.parametrize("url,expected", VALID_CASES)
def test_extract_video_id_valid_formats(url, expected):
    assert extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "khong phai link youtube",
        "https://vimeo.com/12345678",
        "https://www.youtube.com/",
        "https://www.youtube.com/channel/UCxxxxx",
    ],
)
def test_extract_video_id_invalid_returns_none(url):
    assert extract_video_id(url) is None


def test_extract_video_id_strips_whitespace():
    assert extract_video_id("  https://youtu.be/dQw4w9WgXcQ  ") == "dQw4w9WgXcQ"
