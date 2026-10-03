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
    # Chỉ số YouTube — mới (2026-09-12), theo yêu cầu người dùng: kéo dữ liệu thật từ
    # YouTube thay "Nạp retention thủ công" (xem `RetentionEntry` dưới). Gán SAU khi OAuth
    # thành công (`routers/youtube_analytics.py::connect_channel`) — đọc THẬT từ Data API
    # `channels.list(mine=true)`, KHÔNG bắt người dùng tự tìm/dán Channel ID. `None` =
    # kênh StudioFlow này CHƯA kết nối YouTube (bình thường — không bắt buộc).
    youtube_channel_id = Column(String, nullable=True)
    youtube_channel_title = Column(String, nullable=True)
    youtube_connected_at = Column(String, nullable=True)  # ISO string (vn_isoformat)
    # Thứ tự hiển thị TUỲ CHỌN người dùng trên Sidebar — mới (2026-09-19), theo yêu cầu
    # "cho phép kéo thả để sắp xếp lại thứ tự". Trước đây KHÔNG có `ORDER BY` nào ở
    # `GET /channels` (phụ thuộc thứ tự vật lý SQLite, không phải hợp đồng đảm bảo) — giờ
    # `list_channels` sort theo cột này. Kênh mới luôn nhận giá trị LỚN NHẤT hiện có + 1
    # (xuất hiện cuối danh sách), xem `routers/channels.py::create_channel`.
    order_index = Column(Integer, default=0)

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
    # Video YouTube tương ứng — mới (2026-09-12). Người dùng TỰ CHỌN từ danh sách video
    # thật của kênh đã kết nối OAuth (`GET /projects/{id}/youtube-videos-available`) —
    # KHÔNG tự đoán theo tên trùng khớp (rủi ro gán nhầm project khác video). `None` =
    # project chưa publish/chưa liên kết.
    youtube_video_id = Column(String, nullable=True)
    # Thứ tự hiển thị TUỲ CHỌN người dùng trên Sidebar — mới (2026-09-19), cùng lý do
    # `Channel.order_index`. Project mới nhận giá trị NHỎ NHẤT hiện có TRONG CÙNG NHÓM
    # anh em (cùng `channel_id` và `parent_project_id`) - 1 (xuất hiện ĐẦU danh sách nhóm
    # đó — khớp đúng hành vi optimistic đã có ở `Sidebar.tsx::handleNewProject`, chèn lên
    # đầu local state nhưng trước đây KHÔNG hề persist). Xem `routers/projects.py::
    # create_project`.
    order_index = Column(Integer, default=0)

    channel = relationship("Channel", back_populates="projects")
    pack_versions = relationship("PackVersion", back_populates="project", cascade="all, delete-orphan")
    retention_entries = relationship("RetentionEntry", back_populates="project", cascade="all, delete-orphan")
    youtube_video_metrics = relationship("YoutubeVideoMetricsSnapshot", back_populates="project", cascade="all, delete-orphan")


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
    # RPM (doanh thu ước tính/1.000 view) — mới (2026-09-12). GIỮ NHẬP TAY (không tự động
    # hoá như 5 field ret_0/25/50/100 và các chỉ số ở YoutubeVideoMetricsSnapshot) — quyền
    # OAuth `yt-analytics-monetary.readonly` cần cho dữ liệu doanh thu THỰC TẾ rất khó xin
    # cho app cá nhân/nhỏ (Google yêu cầu audit CMS/Content Owner), quyết định đã chốt lúc
    # lên kế hoạch tính năng chỉ số YouTube — xem `app/youtube_analytics.py`.
    rpm = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="retention_entries")


class YoutubeChannelMetricsSnapshot(Base):
    """1 lượt "Đồng bộ chỉ số YouTube" cấp KÊNH — **mới (2026-09-12)**, theo yêu cầu
    người dùng: hiển thị chỉ số cốt lõi (North-star) theo TOÀN KÊNH ở Dashboard. LUÔN
    INSERT dòng MỚI mỗi lần đồng bộ (KHÔNG update tại chỗ) — cùng nguyên tắc
    `RetentionEntry` (giữ lịch sử theo thời gian; UI đọc dòng MỚI NHẤT để hiển thị hiện
    tại). Các chỉ số tổng hợp (APV/CTR/retention giây 30/DE-AT-CH trung bình) tính TRUNG
    BÌNH CÓ TRỌNG SỐ theo lượt xem của từng video — KHÔNG phải trung bình cộng đơn giản
    (video nhiều view ảnh hưởng đúng tỷ trọng thật của nó tới sức khoẻ kênh)."""
    __tablename__ = "youtube_channel_metrics_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, ForeignKey("channel.id"), nullable=False)
    synced_at = Column(String, nullable=False)  # ISO string (vn_isoformat)
    subscriber_count = Column(Integer, nullable=True)
    total_views = Column(Integer, nullable=True)
    video_count = Column(Integer, nullable=True)
    avg_view_percentage = Column(Float, nullable=True)  # APV trung bình có trọng số theo view
    avg_impression_ctr = Column(Float, nullable=True)
    avg_retention_at_30s = Column(Float, nullable=True)
    comments_per_1000_views = Column(Float, nullable=True)
    de_at_ch_views_pct = Column(Float, nullable=True)  # % view từ DE+AT+CH trên tổng view đã đồng bộ

    channel = relationship("Channel")


class YoutubeVideoMetricsSnapshot(Base):
    """1 lượt "Đồng bộ chỉ số YouTube" cho ĐÚNG 1 video ĐÃ LIÊN KẾT project — **mới
    (2026-09-12)**. LUÔN INSERT dòng MỚI (không update tại chỗ), cùng nguyên tắc
    `YoutubeChannelMetricsSnapshot`/`RetentionEntry` — UI đọc dòng MỚI NHẤT theo
    `project_id`. `retention_curve` — JSON `[{ratio, watch_ratio}]` (dimension
    `elapsedVideoTimeRatio` của Analytics API), dùng dựng biểu đồ retention theo TỪNG
    CHƯƠNG (khớp `pack.script.body[]` theo TỶ LỆ vị trí, không phải giây tuyệt đối của
    kịch bản gốc — xem docstring `youtube_analytics.py::correlate_retention_with_blocks`)."""
    __tablename__ = "youtube_video_metrics_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, ForeignKey("project.id"), nullable=False)
    synced_at = Column(String, nullable=False)  # ISO string (vn_isoformat)
    views = Column(Integer, nullable=True)
    avg_view_percentage = Column(Float, nullable=True)  # APV (%)
    avg_view_duration_sec = Column(Float, nullable=True)
    retention_at_30s = Column(Float, nullable=True)  # % người xem còn lại tại giây 30
    impressions = Column(Integer, nullable=True)
    impression_ctr = Column(Float, nullable=True)  # % CTR thumbnail
    comment_count = Column(Integer, nullable=True)
    video_duration_sec = Column(Float, nullable=True)
    views_by_country = Column(Text, nullable=True)  # JSON {"DE": n, "AT": n, "CH": n, ...}
    retention_curve = Column(Text, nullable=True)  # JSON [{ratio, watch_ratio}, ...]

    project = relationship("Project", back_populates="youtube_video_metrics")


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
    # Đánh dấu hàng "ảo" (2026-09-11) — KHÔNG phải video thật user upload/dán URL, mà là
    # 1 hàng đại diện 1 `Project` (Visual Studio) để thoả FK NOT NULL của
    # `ProcessedClip.raw_video_id` khi lưu ảnh/video sinh ở Visual Studio vào Kho Tài
    # Nguyên (không có file thật để "cắt cảnh" — `file_path` chỉ là placeholder không
    # tồn tại trên đĩa). `original_filename` set = tên project, khớp đúng ý người dùng
    # "video nguồn chính là video project". Loại khỏi "Raw Library" (`list_raw_videos`
    # lọc `source_project_id IS NULL`) vì không có hành động cắt cảnh/xoá watermark nào
    # áp dụng được cho hàng này. Xem `asset_vault/from_visual_studio.py::
    # get_or_create_project_raw_video`.
    source_project_id = Column(String, nullable=True)

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
    # Loại tài liệu (2026-09-11) — "video" (mặc định, khớp NGUYÊN mọi clip cắt cảnh cũ +
    # mới — B-roll cắt từ RawVideo LUÔN là video) hoặc "image" (asset ảnh lưu từ Visual
    # Studio, xem `source_shot_id` dưới). Dùng để lọc đúng loại khi gợi ý/gán vào shot
    # (`assign_vault_clip`/`matching.py` — shot ảnh chỉ nhận clip "image", shot video chỉ
    # nhận "video").
    media_kind = Column(String, default="video")
    # `shot_id` GỐC (2026-09-11) — chỉ có giá trị khi clip này được LƯU từ Visual Studio
    # (không phải cắt từ RawVideo thật), cùng `raw_video_id` trỏ tới RawVideo "ảo" của
    # project đó — dùng để nhận diện "shot này đã lưu vào Kho chưa" (cập nhật đè thay vì
    # tạo dòng mới khi lưu lại). Xem `asset_vault/from_visual_studio.py::
    # save_shots_to_vault`.
    source_shot_id = Column(String, nullable=True)

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
