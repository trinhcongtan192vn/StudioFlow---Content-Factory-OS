"""Pydantic schemas — hợp đồng dữ liệu theo specs/04_data_schemas.md.

Đây là bản đã cập nhật theo design thực tế (StudioFlow Prototype.dc.html).
Mọi lệch so với 04_data_schemas.md gốc được liệt kê trong IMPLEMENTATION_REPORT.md
và đã đồng bộ ngược lại vào specs/04_data_schemas.md.

Tóm tắt các điểm mở rộng chính:
- `Brief.raw_knowledge.documents` đổi từ list[str] path sang list[BriefSource] có
  trạng thái trích xuất (extracting/done) — khớp UI upload file/link YouTube trong
  Brief Editor của design (không có trong đặc tả gốc).
- `Brief.strategy.conversion_point` rút gọn enum còn
  none|affiliate|course|private_traffic (bỏ email_list, gộp zalo_group thành
  private_traffic tổng quát hơn) — khớp UI segmented control trong design.
- `ProductionPack` thêm khối `research` (synthesis + outlines) và `hooks` ở cấp
  pack — lưu kết quả AI Research/Hook Variants làm một phần vòng đời của cùng một
  tài liệu Pack thay vì một artifact tạm rời rạc, giữ đúng nguyên tắc
  "Pack JSON là artifact trung tâm" khi work-in-progress trước Gate #1.
- `ProductionPack.shots` thêm `tts_emotion`, `visual_type` — khớp màn Visual Studio
  (mỗi shot vừa có prompt hình/video vừa có mô tả cảm xúc giọng đọc cùng lúc).
- `ProductionPack.youtube_meta` (mới) — description SEO, chapters, hashtags —
  cần thiết cho quy trình đăng YouTube thật, rộng hơn titles/thumbnail_concepts gốc.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# BrandProfile (§04 mục 1)
# ---------------------------------------------------------------------------
class BrandVoice(BaseModel):
    tone: str = ""
    formality: str = "trung tính"
    pacing: str = ""
    sample_lines: list[str] = Field(default_factory=list)


class ContentPillar(BaseModel):
    name: str
    weight: float = 0.0


class RetentionBenchmark(BaseModel):
    target_hook_strength: float = 0.7
    max_anchor_gap_sec: int = 45
    target_body_len_min: int = 8


class BrandProfile(BaseModel):
    channel_id: str
    niche: str = ""
    brand_voice: BrandVoice = Field(default_factory=BrandVoice)
    content_pillars: list[ContentPillar] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    visual_style_prompt: str = ""
    hook_formats_preferred: list[str] = Field(default_factory=list)
    retention_benchmark: RetentionBenchmark = Field(default_factory=RetentionBenchmark)
    version: int = 1


# ---------------------------------------------------------------------------
# Brief (§04 mục 2)
# ---------------------------------------------------------------------------
class BriefStrategy(BaseModel):
    content_matrix_slot: str = ""
    growth_objective: str = ""  # "Nhận diện thương hiệu" | "Tăng tương tác" | "Chuyển đổi"
    conversion_point: Literal["none", "affiliate", "course", "private_traffic"] = "none"


class BriefAudience(BaseModel):
    seo_keywords: list[str] = Field(default_factory=list)
    retention_notes: str = ""
    pain_points: list[str] = Field(default_factory=list)
    description: str = ""


class BriefSource(BaseModel):
    id: str
    kind: Literal["youtube", "file"]
    label: str
    status: Literal["extracting", "done", "error"] = "extracting"
    char_count: Optional[int] = None
    content_path: Optional[str] = None  # tên file text đã trích xuất, nằm trong sources/ cạnh brief.json
    error: Optional[str] = None


class BriefRawKnowledge(BaseModel):
    documents: list[BriefSource] = Field(default_factory=list)
    expert_notes: str = ""
    key_message: str = ""


class Brief(BaseModel):
    project_id: str
    channel_id: str
    topic: str = ""
    insight: str = ""
    strategy: BriefStrategy = Field(default_factory=BriefStrategy)
    audience: BriefAudience = Field(default_factory=BriefAudience)
    raw_knowledge: BriefRawKnowledge = Field(default_factory=BriefRawKnowledge)
    conversion_note: str = ""
    brand_voice_override: Optional[BrandVoice] = None


# ---------------------------------------------------------------------------
# ProductionPack (§04 mục 3) — mở rộng theo design
# ---------------------------------------------------------------------------
class Outline(BaseModel):
    id: str
    title: str
    points: list[str] = Field(default_factory=list)
    selected: bool = False


class HookVariant(BaseModel):
    id: str
    psychological_type: str
    spoken: str
    visual: str = ""
    selected: bool = False


class ResearchBlock(BaseModel):
    synthesis: str = ""
    outlines: list[Outline] = Field(default_factory=list)


class ScriptHook(BaseModel):
    spoken: str = ""
    visual: str = ""
    duration_sec: int = 4


class Warning(BaseModel):
    type: str
    severity: Literal["amber", "red"]
    at_timestamp_sec: Optional[int] = None
    message: str


class ScriptBodyItem(BaseModel):
    timestamp_sec: int
    end_sec: Optional[int] = None
    audio: str = ""
    visual: str = ""
    direction: str = ""
    direction_label: str = "Direction"  # "Audio/SFX" khi block đến từ import (§ đã build vòng 4)
    block_id: Optional[str] = None  # "Mã block" từ file import CSV/Excel
    visual_type: Optional[str] = None  # "Loại Visual" từ file import (Image/Video, gợi ý — khác Shot.visual_type)
    anchor: bool = False
    warning: Optional[Warning] = None


class ScriptCta(BaseModel):
    spoken: str = ""
    conversion_point: str = "none"


class Script(BaseModel):
    hook: Optional[ScriptHook] = None
    body: list[ScriptBodyItem] = Field(default_factory=list)
    cta: Optional[ScriptCta] = None
    full_text: str = ""  # bản Full Script liền mạch trước khi bóc tách theo đoạn
    source: Literal["ai", "import"] = "ai"  # đã build vòng 4 — xem IMPLEMENTATION_REPORT.md


class Shot(BaseModel):
    shot_id: str
    asset_type: Literal["broll_image", "motion_graphic", "stock_footage", "broll_video"] = "broll_image"
    visual_type: Literal["image", "video"] = "image"
    provider: Optional[str] = None
    visual_fx: str = ""  # đổi tên từ `prompt` — khớp cột "Hình ảnh & Hiệu ứng (Visual/FX)" trong import
    audio_sfx: str = ""  # đổi tên từ `tts_emotion` — khớp cột "Âm thanh & Nhạc nền (Audio/SFX)" trong import
    block_id: Optional[str] = None
    linked_timestamp_sec: Optional[int] = None


class TitleConcept(BaseModel):
    text: str
    seo_score_hint: Optional[str] = None
    angle: Optional[str] = None


class ThumbnailConcept(BaseModel):
    metaphor: Optional[str] = None
    text_overlay: Optional[str] = None
    layout: Optional[str] = None
    prompt: str = ""


class YoutubeChapter(BaseModel):
    ts_sec: int
    label: str


class YoutubeMeta(BaseModel):
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    chapters: list[YoutubeChapter] = Field(default_factory=list)
    thumbnail_description: str = ""
    # Thumbnail sinh ảnh THẬT (M2, tái dùng OpenAI Image adapter — §05 mục 8c) —
    # bổ sung theo yêu cầu người dùng ở Pack Review, KHÔNG dùng render.json riêng như
    # Visual Studio vì thumbnail là dữ liệu Pack-level (Title/Thumbnail Concepts đã
    # thuộc phạm vi EPIC 9/M1), không phải asset theo từng shot.
    thumbnail_status: Literal["pending", "generating", "ready", "error"] = "pending"
    thumbnail_asset_path: Optional[str] = None
    thumbnail_provider: Optional[str] = None
    thumbnail_error: Optional[str] = None


class RetentionCheck(BaseModel):
    hook_strength: Optional[float] = None
    max_anchor_gap_sec: Optional[int] = None
    warnings: list[Warning] = Field(default_factory=list)


class ProductionPack(BaseModel):
    project_id: str
    channel_id: str
    brandprofile_version: int = 1
    status: str = "draft"

    research: Optional[ResearchBlock] = None
    hooks: list[HookVariant] = Field(default_factory=list)

    script: Optional[Script] = None
    shots: list[Shot] = Field(default_factory=list)
    titles: list[TitleConcept] = Field(default_factory=list)
    thumbnail_concepts: list[ThumbnailConcept] = Field(default_factory=list)
    youtube_meta: Optional[YoutubeMeta] = None
    repurpose: Optional[dict] = None
    retention_check: Optional[RetentionCheck] = None

    version: int = 1
