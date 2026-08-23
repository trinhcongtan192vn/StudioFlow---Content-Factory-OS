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
- `ProductionPack.shots` thêm `visual_fx`/`audio_sfx`, `visual_type` — khớp màn Visual
  Studio (mỗi shot vừa có prompt hình/video vừa có mô tả âm thanh/nhạc nền cùng lúc).
- `ProductionPack.youtube_meta` giờ CHỈ còn `thumbnail_*` (chỉnh tay + sinh ảnh thật ở
  Visual Studio) — `research`/`hooks`/`titles`/`description`/`hashtags`/`chapters` đã
  bỏ HẲN (2026-08-17, mục 44 IMPLEMENTATION_REPORT.md, cùng lúc bỏ AI Research/Outline/
  Hook + Pack Review/Gate #2 — xem `specs/04_data_schemas.md` §3 để biết lịch sử).
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
    # Logo kênh — **mới (2026-08-22)**, theo yêu cầu người dùng. Thuần hiển thị nhận diện
    # thương hiệu ở màn Cài đặt/Sửa BrandProfile (VD avatar kênh) — KHÔNG dùng trong pipeline
    # sinh asset/ghép video (khác `intro_video_path`/`voice_clone_ref_path`), nên không cần
    # đọc ở app/render/*. Đường dẫn trên đĩa, cùng thư mục channel_dir(channel_id) — rỗng
    # nếu chưa upload.
    logo_path: str = ""
    # Mẫu giọng đọc thương hiệu (audio) — dùng làm reference_audio cho voice cloning
    # (OmniVoice, xem app/providers/tts_omnivoice.py) khi sinh narration cho MỌI project
    # của kênh này, giữ giọng nhất quán xuyên suốt portfolio. Đường dẫn trên đĩa, cùng
    # thư mục channel_dir(channel_id) — rỗng nếu chưa upload (fallback: giọng provider
    # mặc định, không phải lỗi).
    voice_clone_ref_path: str = ""
    # Video/audio thương hiệu — **mới (2026-08-20)**, theo yêu cầu người dùng: phát ở
    # ĐẦU MỌI video của kênh này khi ghép MP4 (xem app/render/assembly.py::_resolve_intro_
    # source). CHỈ 1 trong 2 được khác rỗng tại 1 thời điểm (endpoint upload tự xoá cái
    # còn lại — xem app/routers/channels.py::upload_brand_intro) — người dùng chỉ được
    # chọn 1 loại. Nếu chỉ có `intro_audio_path` (không có video), lúc ghép sẽ dùng ẢNH
    # của shot ĐẦU TIÊN (đã sinh xong) trong project làm hình minh hoạ khi audio phát.
    # Có thể bị GHI ĐÈ (override) bởi shot mở đầu riêng của TỪNG project (`RenderState.
    # intro`, ưu tiên cao hơn) — xem app/render/schemas.py::IntroAssetStatus.
    intro_video_path: str = ""
    intro_audio_path: str = ""
    # Nhạc nền (background music) MẶC ĐỊNH của kênh — **mới (2026-08-20)**, theo yêu
    # cầu người dùng: phát ĐÈ LIÊN TỤC dưới TOÀN BỘ video (kể cả intro) khi ghép MP4, âm
    # lượng chỉnh được tương đối so với giọng đọc chính qua `bg_music_volume` (0.0 =
    # câm, 1.0 = to bằng giọng đọc — mặc định 0.3, êm dưới nền như thực hành thường
    # thấy). Có thể bị GHI ĐÈ bởi nhạc nền riêng của TỪNG project (`RenderState.
    # bg_music`, ưu tiên cao hơn) — xem `app/render/bg_music.py::resolve_bg_music_source`.
    bg_music_path: str = ""
    bg_music_volume: float = 0.3
    # Style LoRA khoá "chữ ký hình ảnh" cho ảnh local SDXL — **mới (2026-08-22)**, theo
    # yêu cầu người dùng (đợt 2 cải thiện chất lượng ảnh local, xem IMPLEMENTATION_REPORT.
    # md): 1 checkpoint painterly đơn thuần vẫn dao động phong cách giữa các lần sinh —
    # Style LoRA là lớp khoá mạnh nhất. `style_lora_path` là TÊN FILE (không phải đường
    # dẫn tuyệt đối — khác `logo_path`/`intro_video_path`, vì LoRA sống trong thư mục
    # ComfyUI (`ComfyUI/models/loras/`), KHÔNG PHẢI thư mục channel_dir như các asset khác
    # — path tuyệt đối cross-machine không có ý nghĩa ở đây, chỉ cần đúng tên file ComfyUI
    # tìm thấy). Rỗng = không dùng LoRA (hành vi cũ, không đổi cho ai chưa cấu hình). CHỈ
    # áp dụng cho `local_sdxl` (`ImageProvider.generate()` — provider khác nhận rồi bỏ
    # qua, xem app/providers/base.py). Mỗi kênh chọn LoRA khác nhau tuỳ phong cách riêng.
    style_lora_path: str = ""
    style_lora_strength: float = 0.8
    # Hiệu ứng lớp phủ (overlay) MẶC ĐỊNH của kênh — **mới (2026-08-22)**, theo yêu cầu
    # người dùng: 1 video hiệu ứng (VD mưa rơi, tuyết rơi...) blend ĐÈ LIÊN TỤC lên TOÀN
    # BỘ video (kể cả intro) khi ghép MP4 — cùng cách bg_music hoạt động (KHÁC intro, vốn
    # chỉ áp dụng cho đoạn mở đầu), xem `app/render/overlay.py::resolve_overlay_source`.
    # `overlay_effect_opacity` (0.0=tắt hẳn, 1.0=full cường độ, mặc định 0.5) điều khiển
    # độ sáng overlay TRƯỚC khi blend `screen` — xem `app/render/assembly.py::
    # _mix_overlay_effect`. Có thể bị GHI ĐÈ bởi override riêng của TỪNG project
    # (`RenderState.overlay`, ưu tiên cao hơn). File LUÔN là VIDEO (mp4/webm/mov) — không
    # có preset "loại hiệu ứng" nào có sẵn, người dùng tự upload bất kỳ clip nào (tự do
    # như `intro_video_path`).
    overlay_effect_path: str = ""
    overlay_effect_opacity: float = 0.5
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
    # "ai" giữ lại trong Literal chỉ để đọc được project CŨ đã lưu trên đĩa từ trước
    # 2026-08-17 (mục 44) — luồng AI Research/Outline/Hook/Full-Script đã bỏ hẳn, script
    # MỚI luôn là "import" (con đường duy nhất còn lại để có script).
    source: Literal["ai", "import"] = "import"


class Shot(BaseModel):
    shot_id: str
    asset_type: Literal["broll_image", "motion_graphic", "stock_footage", "broll_video"] = "broll_image"
    visual_type: Literal["image", "video"] = "image"
    provider: Optional[str] = None
    visual_fx: str = ""  # đổi tên từ `prompt` — khớp cột "Hình ảnh & Hiệu ứng (Visual/FX)" trong import
    audio_sfx: str = ""  # đổi tên từ `tts_emotion` — khớp cột "Âm thanh & Nhạc nền (Audio/SFX)" trong import
    block_id: Optional[str] = None
    linked_timestamp_sec: Optional[int] = None
    # Hiệu ứng chuyển cảnh SANG shot kế tiếp (không áp dụng cho shot cuối) — mặc định
    # "cut" (cắt cứng, giữ nguyên hành vi ghép cũ, không tốn re-encode thêm). Danh sách
    # giá trị hợp lệ: `render/assembly.py::TRANSITIONS` (nguồn sự thật duy nhất — đổi ở
    # đây thì đổi cả bên đó). 2026-08-17, theo yêu cầu người dùng ở Visual Studio.
    transition_to_next: str = "cut"
    # Hiệu ứng chuyển động camera (Ken Burns: zoom/pan/tilt/roll/orbit) áp cho ẢNH TĨNH
    # khi ghép MP4 — mặc định "none" (ảnh đứng yên, hành vi cũ). CHỈ có tác dụng khi
    # `visual_type == "image"` (video đã có chuyển động thật sẵn). Danh sách giá trị hợp
    # lệ: `render/camera_motion.py::CAMERA_MOTIONS` (nguồn sự thật duy nhất). 2026-08-19,
    # theo yêu cầu người dùng ở Visual Studio.
    camera_motion: str = "none"


class YoutubeMeta(BaseModel):
    # `description`/`hashtags`/`chapters` (sinh bằng AI cùng `titles`) đã bỏ 2026-08-17
    # (mục 44) cùng lúc bỏ Pack Review — chỉ còn `thumbnail_description` (chỉnh tay,
    # xem VisualStudio.tsx::ThumbnailCard) và các field thumbnail_* bên dưới.
    thumbnail_description: str = ""
    # Thumbnail sinh ảnh THẬT (M2, tái dùng OpenAI Image adapter — §05 mục 8c) —
    # bổ sung theo yêu cầu người dùng ở Pack Review, KHÔNG dùng render.json riêng như
    # Visual Studio vì thumbnail là dữ liệu Pack-level (Title/Thumbnail Concepts đã
    # thuộc phạm vi EPIC 9/M1), không phải asset theo từng shot.
    thumbnail_status: Literal["pending", "generating", "ready", "error"] = "pending"
    thumbnail_asset_path: Optional[str] = None
    thumbnail_provider: Optional[str] = None
    thumbnail_error: Optional[str] = None
    # Duyệt Thumbnail — BẮT BUỘC trước khi Visual Studio cho sinh asset ảnh/video của
    # từng shot (xem app/routers/render.py::_require_thumbnail_approved), vì ảnh
    # thumbnail (AI sinh hoặc người dùng tự upload) đóng vai trò ảnh "anchor" cho toàn
    # bộ project (Tier 2 — nhất quán phong cách/nhân vật, xem app/render/engine.py). Tự
    # reset về False mỗi khi thumbnail đổi (sinh lại bằng AI hoặc upload ảnh khác) — ảnh
    # cũ đã duyệt không còn đúng nữa, cần duyệt lại ảnh mới.
    thumbnail_approved: bool = False


class RetentionCheck(BaseModel):
    hook_strength: Optional[float] = None
    max_anchor_gap_sec: Optional[int] = None
    warnings: list[Warning] = Field(default_factory=list)


class ProductionPack(BaseModel):
    project_id: str
    channel_id: str
    brandprofile_version: int = 1
    status: str = "draft"

    script: Optional[Script] = None
    shots: list[Shot] = Field(default_factory=list)
    youtube_meta: Optional[YoutubeMeta] = None
    repurpose: Optional[dict] = None
    retention_check: Optional[RetentionCheck] = None

    version: int = 1
