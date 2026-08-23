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
    Text,
)
from sqlalchemy.orm import relationship

from app.db import Base


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


class Budget(Base):
    __tablename__ = "budget"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, ForeignKey("channel.id"), nullable=True)
    project_id = Column(String, ForeignKey("project.id"), nullable=True)
    soft_limit = Column(Float, default=0)
    threshold_pct = Column(Integer, default=80)
    spent = Column(Float, default=0)
