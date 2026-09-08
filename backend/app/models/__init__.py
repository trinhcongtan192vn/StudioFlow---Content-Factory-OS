"""SQLAlchemy models — theo specs/02_database.md.

SQLite là index/metadata store; nội dung Pack/BrandProfile đầy đủ nằm ở file JSON
trên đĩa (workspace/), DB chỉ giữ path + version + trạng thái (§01, §02 nguyên tắc 4).

Lệch so với 02_database.md gốc (ghi lại chi tiết trong IMPLEMENTATION_REPORT.md):
- `budget`: thêm `channel_id` + `threshold_pct` — màn Chi phí & Ngân sách trong design
  đặt hạn mức theo KÊNH (không phải theo project như bản spec gốc chỉ có project_id).
- `prompt_template`: tách thành 2 bảng (`prompt_template`, `prompt_template_version`)
  thay vì 1 bảng có version rời rạc — cần lịch sử nhiều version mỗi template với
  nội dung khác nhau (đúng yêu cầu "phiên bản hoá" trong spec, bản gốc mô tả chưa đủ
  chỗ chứa lịch sử nhiều bản ghi cho cùng 1 template).
- `app_setting`: dùng thêm key `app_branding` (JSON: {name, accent_swatch}) — không
  cần bảng riêng cho khu Thương hiệu ứng dụng (🎨).
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import relationship

from app.db import Base

# Kho Tài Nguyên (Asset Vault) — chuyển sang màn TOÀN CỤC (2026-08-27, theo yêu cầu người
# dùng): 1 RawVideo giờ gắn được NHIỀU kênh (dạng tag), KHÔNG còn 1 FK đơn như bản thiết
# kế ban đầu (channel_id trên RawVideo/ProcessedClip). Đây là bảng m2m (secondary=) ĐẦU
# TIÊN của dự án — đã grep xác nhận không có tiền lệ nào khác để theo trước khi build.
raw_video_channel = Table(
    "raw_video_channel",
    Base.metadata,
    Column("raw_video_id", String, ForeignKey("raw_video.id"), primary_key=True),
    Column("channel_id", String, ForeignKey("channel.id"), primary_key=True),
)

# Bug thật (2026-08-28, user tự phát hiện): kênh của ProcessedClip TỪNG chỉ suy ra qua
# JOIN `raw_video_id` -> RawVideo -> raw_video_channel (không có tag riêng, xem docstring
# cũ của ProcessedClip) — xoá RawVideo cha (hành vi BÌNH THƯỜNG, không cascade xoá clip
# con) làm clip mất SẠCH thông tin kênh (không chỉ hiển thị rỗng — còn biến mất khỏi MỌI
# kết quả matching B-roll của MỌI kênh vì `matching.py::_clips_for_channel` INNER JOIN
# qua raw_video). Fix: ProcessedClip có tag kênh RIÊNG (m2m này), sao chép từ raw_video
# lúc cắt cảnh (`ingest.py::_create_clip`) — clip độc lập thật sự với raw_video cha, kể cả
# sau khi raw_video bị xoá. Cho phép sửa lại tay (đơn lẻ + bulk, xem routers/asset_vault.py).
processed_clip_channel = Table(
    "processed_clip_channel",
    Base.metadata,
    Column("clip_id", String, ForeignKey("processed_clip.clip_id"), primary_key=True),
    Column("channel_id", String, ForeignKey("channel.id"), primary_key=True),
)


class ProjectStatus(str, enum.Enum):
    # "researching"/"await_gate1"/"await_gate2" đã bỏ (2026-08-17, mục 44
    # IMPLEMENTATION_REPORT.md) cùng lúc bỏ AI Research/Outline/Hook + Pack Review/
    # Gate #2 — không còn gate duyệt bắt buộc nào giữa các bước.
    draft = "draft"
    generating = "generating"
    ready_output = "ready_output"
    exported = "exported"
    published = "published"


class Channel(Base):
    __tablename__ = "channel"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    niche = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    brandprofile_path = Column(String, nullable=True)
    brandprofile_version = Column(Integer, default=0)
    archived = Column(Boolean, default=False)

    projects = relationship("Project", back_populates="channel", cascade="all, delete-orphan")
    brandprofile_versions = relationship(
        "BrandProfileVersion", back_populates="channel", cascade="all, delete-orphan"
    )
    # m2m qua raw_video_channel — KHÔNG cascade delete: Kho Tài Nguyên giờ là kho TOÀN
    # CỤC (như CreativeAsset/Thư viện), 1 video có thể gắn NHIỀU kênh — xoá 1 kênh chỉ
    # bỏ tag (xoá dòng ở raw_video_channel, SQLAlchemy tự làm khi xoá Channel), KHÔNG
    # xoá RawVideo/ProcessedClip (có thể vẫn đang gắn kênh khác).
    raw_videos = relationship("RawVideo", secondary=raw_video_channel, back_populates="channels")
    # m2m qua processed_clip_channel (2026-08-28) — clip có tag kênh RIÊNG, độc lập với
    # raw_video cha (xem docstring `processed_clip_channel` ở trên).
    processed_clips = relationship("ProcessedClip", secondary=processed_clip_channel, back_populates="channels")


class BrandProfileVersion(Base):
    __tablename__ = "brandprofile_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, ForeignKey("channel.id"), nullable=False)
    version = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text, default="")

    channel = relationship("Channel", back_populates="brandprofile_versions")


class Project(Base):
    __tablename__ = "project"

    id = Column(String, primary_key=True)
    channel_id = Column(String, ForeignKey("channel.id"), nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, default=ProjectStatus.draft.value)
    # Short-form (9:16, YouTube Shorts/TikTok) là sub-project ĐỘC LẬP nội dung, chỉ lồng
    # dưới 1 long-form project để nhóm hiển thị — **mới (2026-08-21)**, theo yêu cầu
    # người dùng. KHÔNG PHẢI auto-repurpose (đó là M3, xem specs/09_sprint_tasks.md) —
    # short-form tự đi qua lại đúng luồng Brief→Script Studio→Visual Studio→Output như
    # long-form, chỉ khác tỷ lệ khung sinh ảnh/video (`app/render/engine.py`,
    # `app/render/assembly.py`). `parent_project_id` NULL = long-form (project gốc);
    # có giá trị = short-form, LUÔN trỏ tới 1 project `format=="long"` CÙNG kênh (validate
    # ở `POST /channels/{id}/projects`, không ràng buộc DB — cùng quy ước nullable FK
    # như `Budget.channel_id`/`project_id`, không cần `relationship()` riêng vì chỉ dùng
    # qua query trực tiếp). Không lồng quá 1 cấp — short-form không có short-form con.
    parent_project_id = Column(String, ForeignKey("project.id"), nullable=True)
    format = Column(String, default="long")  # "long" | "short"
    step = Column(Integer, default=0)  # 0..5, khớp UI stepper (design)
    max_step_reached = Column(Integer, default=0)
    brief_path = Column(String, nullable=True)
    pack_path = Column(String, nullable=True)
    pack_version = Column(Integer, default=0)
    return_note = Column(Text, default="")
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    channel = relationship("Channel", back_populates="projects")
    pack_versions = relationship("PackVersion", back_populates="project", cascade="all, delete-orphan")
    retention_entries = relationship("RetentionEntry", back_populates="project", cascade="all, delete-orphan")


class PackVersion(Base):
    __tablename__ = "pack_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, ForeignKey("project.id"), nullable=False)
    version = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    status_at_save = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="pack_versions")


class RetentionEntry(Base):
    __tablename__ = "retention_entry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, ForeignKey("project.id"), nullable=False)
    published_at = Column(String, nullable=True)  # ISO date string
    ret_0 = Column(Float, nullable=True)
    ret_25 = Column(Float, nullable=True)
    ret_50 = Column(Float, nullable=True)
    ret_100 = Column(Float, nullable=True)
    avg_view_duration = Column(Float, nullable=True)
    thumbnail_ctr = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="retention_entries")


class ProviderConfig(Base):
    __tablename__ = "provider_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task = Column(String, nullable=False)  # llm | tts | image | video
    provider_name = Column(String, nullable=False)  # claude|gemini|openai|local|vbee|elevenlabs|...
    display_name = Column(String, nullable=False)
    connection_type = Column(String, nullable=False)  # cloud_api | local_endpoint
    api_key_encrypted = Column(Text, nullable=True)
    endpoint_url = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    available_models = Column(Text, default="[]")  # JSON list, cloud providers khai báo sẵn
    is_default = Column(Boolean, default=False)
    is_fallback = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    status = Column(String, default="untested")  # ok | error | untested
    created_at = Column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_setting"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)  # JSON-encoded


class PromptTemplate(Base):
    __tablename__ = "prompt_template"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    task = Column(String, nullable=False)  # khớp PROMPT_STAGES key trong design
    active_version = Column(String, default="v1")
    created_at = Column(DateTime, default=datetime.utcnow)

    versions = relationship(
        "PromptTemplateVersion", back_populates="template", cascade="all, delete-orphan"
    )


class PromptTemplateVersion(Base):
    __tablename__ = "prompt_template_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(String, ForeignKey("prompt_template.id"), nullable=False)
    version = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    note = Column(Text, default="")
    updated_by = Column(String, default="Bạn")
    created_at = Column(DateTime, default=datetime.utcnow)

    template = relationship("PromptTemplate", back_populates="versions")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String, nullable=False)
    detail = Column(Text, default="")
    entity = Column(String, nullable=True)  # tên kênh/project liên quan, hiển thị cột "Người dùng/Kênh"
    type = Column(String, default="system")  # system | expense
    cost = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CreativeAsset(Base):
    """Thư viện Creative Asset — **mới (2026-08-20)**, theo yêu cầu người dùng: upload
    1 lần (nhạc nền/video/ảnh/giọng đọc), dùng lại được ở NHIỀU nơi thay vì phải upload
    lại từ máy mỗi lần. Đứng ĐỘC LẬP (không FK tới channel/project nào) — dùng chung
    toàn app, khớp entry point "Thư viện" ở sidebar ngang hàng Dashboard."""
    __tablename__ = "creative_asset"

    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)  # "music" | "video" | "image" | "voice"
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RawVideo(Base):
    """Video gốc do user import vào Kho Tài Nguyên (CHANGE_Semantic_BRoll_Asset_
    Vault.md §4, đổi thành màn TOÀN CỤC 2026-08-27) — chưa cắt cảnh. Gắn được NHIỀU kênh
    (dạng tag, `channels` m2m qua `raw_video_channel`) — khác thiết kế ban đầu (1 FK đơn
    `channel_id`). Vẫn tách biệt khỏi `CreativeAsset` (thư viện dùng lại nguyên vẹn) vì
    đây là NGUYÊN LIỆU THÔ sẽ bị cắt thành nhiều `ProcessedClip` con, mục đích/vòng đời
    khác hẳn."""
    __tablename__ = "raw_video"

    id = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    source_url = Column(String, nullable=True)  # null nếu upload trực tiếp, khác null nếu tải qua yt-dlp
    # Tên file THẬT lúc user upload (2026-08-27) — `file_path` trên đĩa đặt theo `id` (bất
    # biến, không đổi dù đổi tên gốc) nhưng người dùng cần biết ĐÃ upload đúng file nào —
    # giữ nguyên chuỗi gốc (kể cả ký tự đặc biệt) ở đây, KHÔNG sanitize (chỉ dùng để hiển
    # thị, không dùng làm tên file thật trên đĩa). Null nếu tải qua URL (source_url đã đủ
    # để biết nguồn).
    original_filename = Column(String, nullable=True)
    import_note = Column(Text, default="")
    status = Column(String, default="detecting")  # detecting | tagging | indexed | error
    error_message = Column(Text, nullable=True)
    # Tiến trình THẬT (2026-08-27) — null khi không có tác vụ nền nào đang chạy.
    # `progress_current`/`progress_total` cùng đơn vị tuỳ bước (byte lúc tải yt-dlp, số
    # clip lúc cắt cảnh) — xem app/asset_vault/ingest.py.
    progress_current = Column(Integer, nullable=True)
    progress_total = Column(Integer, nullable=True)
    progress_label = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    channels = relationship("Channel", secondary=raw_video_channel, back_populates="raw_videos")


class ProcessedClip(Base):
    """Clip đã cắt cảnh từ `RawVideo`, mang caption/tags/mood_tone (AI hoặc tay) +
    rights_status — đơn vị thật được gợi ý khớp vào shot (`ShotRenderStatus.
    linked_clip_id`, app/render/schemas.py). Có tag kênh RIÊNG (`channels` m2m qua
    `processed_clip_channel`, mới 2026-08-28) — SAO CHÉP từ `raw_video.channels` lúc cắt
    cảnh (`ingest.py`), rồi ĐỘC LẬP với raw_video cha từ đó (sửa lại tay không ảnh hưởng
    raw_video, và ngược lại raw_video bị xoá không làm mất tag của clip — trước đây kênh
    CHỈ suy ra qua JOIN `raw_video_id`, xoá raw_video cha làm mất sạch tag + clip biến mất
    khỏi mọi kết quả matching B-roll, xem IMPLEMENTATION_REPORT.md mục 98)."""
    __tablename__ = "processed_clip"

    clip_id = Column(String, primary_key=True)
    raw_video_id = Column(String, ForeignKey("raw_video.id"), nullable=False)
    storage_url = Column(String, nullable=False)
    duration_sec = Column(Float, default=0.0)
    resolution = Column(String, default="")
    caption = Column(Text, default="")
    tags = Column(Text, default="[]")  # JSON array (string) — đơn giản, không cần bảng con
    mood_tone = Column(String, default="")
    vector_id = Column(String, nullable=True)  # id trong Chroma collection TOÀN CỤC (2026-08-27), null nếu chưa embed
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True)
    rights_status = Column(String, default="unverified")  # unverified | licensed_verified | public_domain
    rights_note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    # Lỗi gắn nhãn lần gần nhất (nếu có) — mới (2026-08-27, bulk gắn nhãn theo lựa chọn tự
    # do ở Kho Tài Nguyên) — khác `RawVideo.error_message` (gắn nhãn CẢ video gốc, không
    # phân biệt clip nào lỗi); field này cho phép hiện lỗi RIÊNG từng clip khi gắn nhãn
    # 1 tập clip tuỳ ý (có thể trải nhiều raw_video khác nhau, không có 1 "raw_video" chung
    # để gắn cờ lỗi). Null = chưa từng lỗi hoặc lần gần nhất đã thành công (xoá khi thành
    # công, xem `ingest.py::caption_clips`).
    caption_error = Column(Text, nullable=True)

    # Chỉ đọc, không cần back_populates (RawVideo không cần collection ngược
    # `.processed_clips`, chưa nơi nào trong app cần dùng chiều đó) — dùng để hiện "video
    # nguồn" (tên/trạng thái) trong UI, KHÔNG còn dùng để tra kênh (xem `channels` dưới).
    raw_video = relationship("RawVideo")
    channels = relationship("Channel", secondary=processed_clip_channel, back_populates="processed_clips")


class Budget(Base):
    __tablename__ = "budget"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, ForeignKey("channel.id"), nullable=True)
    project_id = Column(String, ForeignKey("project.id"), nullable=True)
    soft_limit = Column(Float, default=0)
    threshold_pct = Column(Integer, default=80)
    spent = Column(Float, default=0)
