"""Seed dữ liệu khởi tạo — chạy 1 lần khi DB rỗng.

Bao gồm: app_setting mặc định, thư viện Prompt Templates (nội dung port từ design
StudioFlow Prototype.dc.html), 1 provider LLM mặc định (Mock — luôn sẵn sàng, xem
app/providers/mock.py), và dữ liệu demo 3 kênh + vài project ở các bước khác nhau
để trải nghiệm lần đầu giống hệt bản design.
"""
import json
import os

from app.config import channel_dir, project_dir
from app.db import SessionLocal
from app.filestore import write_json
from app.models import (
    AppSetting,
    Budget,
    Channel,
    Project,
    ProviderConfig,
    PromptTemplate,
    PromptTemplateVersion,
)
from app.schemas import Brief, ProductionPack

PROMPT_SEED = [
    ("pt_outline", "Sinh Outline (Research)", "outline", [
        ("v1", "Khởi tạo", "Hệ thống", "Từ Brief {{brief}} về chủ đề {{topic}}, sinh {{outline_count}} outline khác góc tiếp cận."),
        ("v2", "Ràng buộc bám sát BrandProfile", "Hệ thống", "Từ Brief {{brief}} về chủ đề {{topic}}, sinh {{outline_count}} outline khác góc tiếp cận, bám sát trụ cột nội dung {{content_pillars}} và giọng kênh {{channel}}, tránh {{forbidden}}."),
    ]),
    ("pt_hook", "Sinh Hook Variants", "hook", [
        ("v1", "Khởi tạo", "Hệ thống", "Từ dàn ý {{chosen_outline}}, viết {{hook_count}} biến thể hook theo các kiểu tâm lý khác nhau."),
        ("v2", "Ràng buộc hook dưới 12 từ", "Hệ thống", "Từ dàn ý {{chosen_outline}}, viết {{hook_count}} biến thể hook theo kiểu ưa dùng của kênh {{hook_formats}}. Mỗi hook dưới 12 từ, không clickbait sai sự thật, tránh {{forbidden}}."),
    ]),
    ("pt_script", "Viết Master Script", "script", [
        ("v1", "Khởi tạo", "Hệ thống", "Viết Master Script từ Outline {{outline}} và Hook {{hook}}, độ dài {{length}}."),
        ("v2", "Thêm chỉ dẫn nhịp câu ngắn", "Hệ thống", "Viết Master Script hoàn chỉnh từ Outline {{outline}} và Hook {{hook}}, giọng văn theo BrandProfile kênh {{channel}}, câu ngắn, tránh thuật ngữ khó, độ dài {{length}}, theo framework {{framework}}."),
    ]),
    ("pt_script_revise", "Tạo lại Full Script theo góp ý", "script_revise", [
        ("v1", "Khởi tạo", "Hệ thống", "Viết lại Full Script {{current_script}} theo góp ý của người dùng: {{user_feedback}}. Giữ nguyên giọng văn BrandProfile kênh {{channel}} và độ dài {{length}}, chỉ điều chỉnh đúng phần được góp ý, không thay đổi các đoạn khác."),
    ]),
    ("pt_script_breakdown", "Phân rã Full Script theo đoạn (Audio/Visual/Direction)", "script_breakdown", [
        ("v1", "Khởi tạo", "Hệ thống", "Phân rã Full Script {{script_text}} thành các đoạn theo timestamp, audio, visual và direction."),
        ("v2", "Giới hạn 8s/shot", "Hệ thống", "Phân rã Full Script {{script_text}} đã duyệt thành các đoạn theo timeline: mỗi đoạn gồm {timestamp, audio (nguyên văn lời đọc), visual (mô tả hình ảnh/video), direction (chỉ dẫn nhịp, cảm xúc)}, tối đa 8s/đoạn."),
    ]),
    ("pt_thumb", "Title, Description & Thumbnail concept", "thumbnail", [
        ("v1", "Khởi tạo", "Hệ thống", "Từ Brief {{brief}} và kịch bản {{script}}, sinh 5-10 tiêu đề tối ưu SEO+CTR, mô tả SEO, hashtags và concept thumbnail theo style kênh {{visual_style_prompt}}."),
    ]),
    ("pt_visual_shots_init", "Visual Studio — Khởi tạo danh sách Shot", "visual_shots_init", [
        ("v1", "Khởi tạo", "Hệ thống", "Từ toàn bộ script {{script}} và style kênh {{visual_style_prompt}}, sinh prompt hình ảnh/video cho từng shot: muted palette, single accent color, no text, aspect 16:9."),
    ]),
    ("pt_visual_image", "Visual Studio — Tạo lại Visual (ảnh)", "visual_image", [
        ("v1", "Khởi tạo", "Hệ thống", "Từ đoạn script {{script_snippet}} và mô tả visual hiện tại {{visual_description}}, sinh lại 1 prompt ảnh cho shot này theo style kênh {{visual_style_prompt}}: muted palette, single accent color, no text, aspect 16:9."),
    ]),
    ("pt_visual_video", "Visual Studio — Tạo lại Visual (video)", "visual_video", [
        ("v1", "Khởi tạo", "Hệ thống", "Từ đoạn script {{script_snippet}} và mô tả visual hiện tại {{visual_description}}, sinh video 6s loopable theo style kênh {{channel}}: muted color grade, grain overlay nhẹ, no on-screen text."),
    ]),
    ("pt_visual_tts", "Visual Studio — Tạo lại giọng đọc / Audio-SFX", "visual_tts", [
        ("v1", "Khởi tạo", "Hệ thống", "Đọc đoạn script {{script_snippet}} với giọng {{voice_profile}} theo emotion mô tả: {{emotion_description}}. Giữ tông BrandProfile kênh {{channel}}."),
    ]),
]

DEMO_CHANNELS = [
    {"id": "ch_sik", "name": "Sử Việt Kể", "niche": "Lịch sử",
     "voice": {"tone": "Trầm, kể chuyện, nhiều chi tiết cảm xúc; tránh hài hước.", "formality": "trang trọng", "pacing": "chậm, giàu hình ảnh", "sample_lines": []},
     "pillars": [{"name": "Nhân vật lịch sử", "weight": 0.5}, {"name": "Bí ẩn chưa giải", "weight": 0.3}, {"name": "Chiến dịch quân sự", "weight": 0.2}],
     "forbidden": ["Xuyên tạc chính sử", "Đùa cợt về nhân vật đã khuất"],
     "visual_style_prompt": "archival tone, muted sepia, cinematic historical",
     "hook_formats": ["Khoảng trống tò mò", "Đối lập bất ngờ"],
     "benchmark": {"target_hook_strength": 0.7, "max_anchor_gap_sec": 40, "target_body_len_min": 6}},
    {"id": "ch_tk", "name": "Tiền Khôn", "niche": "Tài chính cá nhân",
     "voice": {"tone": "Thẳng, dùng số liệu, hài hước nhẹ; nói như bạn thân tư vấn.", "formality": "trung tính", "pacing": "nhanh, câu ngắn", "sample_lines": []},
     "pillars": [{"name": "Đầu tư cơ bản", "weight": 0.4}, {"name": "Sai lầm tài chính", "weight": 0.4}, {"name": "Case study thực tế", "weight": 0.2}],
     "forbidden": ["Khuyên mua/bán cổ phiếu cụ thể", "Hứa hẹn lợi nhuận"],
     "visual_style_prompt": "minimal, tông xanh–trắng, biểu đồ sạch",
     "hook_formats": ["câu hỏi gây sốc", "con số phản trực giác"],
     "benchmark": {"target_hook_strength": 0.7, "max_anchor_gap_sec": 35, "target_body_len_min": 8}},
    {"id": "ch_tlh", "name": "Tâm Lý Học Đời Thường", "niche": "Tâm lý học",
     "voice": {"tone": "Gần gũi, đồng cảm, dẫn chứng khoa học nhẹ.", "formality": "thân mật", "pacing": "vừa, nhiều khoảng lặng", "sample_lines": []},
     "pillars": [{"name": "Mối quan hệ", "weight": 0.4}, {"name": "Nhận thức bản thân", "weight": 0.4}, {"name": "Thao túng tâm lý", "weight": 0.2}],
     "forbidden": ["Chẩn đoán bệnh lý cụ thể", "Đưa lời khuyên y tế"],
     "visual_style_prompt": "soft light, warm tone, minimal diagram",
     "hook_formats": ["tình huống gây đồng cảm", "câu hỏi tự soi"],
     "benchmark": {"target_hook_strength": 0.65, "max_anchor_gap_sec": 45, "target_body_len_min": 6}},
]


def run_seed():
    """Seed từng nhóm ĐỘC LẬP theo bảng rỗng hay không — KHÔNG dùng chung 1 điều kiện
    "Channel rỗng" cho tất cả như bản đầu (bug: xoá hết kênh rồi restart app sẽ chạy
    lại toàn bộ seed, đụng primary key cố định của app_setting/prompt_template/
    provider_config → crash). Nhờ vậy, xoá hết kênh/project để test lại từ đầu (không
    đụng cấu hình admin) là thao tác an toàn — khởi động lại app không hề gì.

    Cờ `STUDIOFLOW_SKIP_SEED=1` (dùng khi vận hành/dọn dữ liệu, KHÔNG dùng cho cài đặt
    thật) bỏ qua luôn cả seed dữ liệu demo (3 kênh mẫu) — dùng khi muốn app khởi động ở
    trạng thái trắng hoàn toàn thay vì tự có lại 3 kênh demo.
    """
    skip_demo = os.environ.get("STUDIOFLOW_SKIP_SEED", "").lower() in ("1", "true", "yes")
    db = SessionLocal()
    try:
        if db.query(AppSetting).count() == 0:
            for key, value in {
                "general": {"org_name": "Media House VN", "language": "vi", "timezone": "Asia/Ho_Chi_Minh", "export_format": "markdown", "naming_convention": "[Kênh]_[YYMMDD]_[Chủ đề ngắn]"},
                "ai_params": {"temperature": 0.7, "length": "3-6 phút", "hook_count": 3, "framework": "AIDA"},
                "app_branding": {"name": "Media House VN", "accent_swatch": 0},
            }.items():
                db.add(AppSetting(key=key, value=json.dumps(value, ensure_ascii=False)))

        if db.query(PromptTemplate).count() == 0:
            for tid, name, task, versions in PROMPT_SEED:
                active = versions[-1][0]
                db.add(PromptTemplate(id=tid, name=name, task=task, active_version=active))
                for version, note, updated_by, body in versions:
                    db.add(PromptTemplateVersion(template_id=tid, version=version, content=body, note=note, updated_by=updated_by))

        # KHÔNG seed provider Mock mặc định (đổi theo yêu cầu người dùng) — cài đặt mới
        # phải chủ động vào Cài đặt → Provider AI kết nối Claude/GPT/Gemini hoặc model
        # local (GPU) thật. Thiếu provider → mọi bước cần AI trả lỗi rõ ràng thay vì
        # âm thầm sinh nội dung giả lập (xem app/providers/factory.py
        # NoProviderConfiguredError, IMPLEMENTATION_REPORT.md).

        db.commit()

        if skip_demo or db.query(Channel).count() > 0:
            return

        # kênh + brandprofile + budget demo
        for c in DEMO_CHANNELS:
            ch = Channel(id=c["id"], name=c["name"], niche=c["niche"], brandprofile_version=1)
            db.add(ch)
            from app.schemas import BrandProfile

            profile = BrandProfile(
                channel_id=c["id"], niche=c["niche"], brand_voice=c["voice"], content_pillars=c["pillars"],
                forbidden=c["forbidden"], visual_style_prompt=c["visual_style_prompt"], hook_formats_preferred=c["hook_formats"],
                retention_benchmark=c["benchmark"], version=1,
            )
            cdir = channel_dir(c["id"])
            write_json(cdir / "brandprofile.json", profile.model_dump())
            write_json(cdir / "brandprofile.v1.json", profile.model_dump())
            ch.brandprofile_path = str(cdir / "brandprofile.json")
            db.add(Budget(channel_id=c["id"], soft_limit=8, threshold_pct=60, spent=0))

        db.flush()

        # 1 project draft mẫu / kênh, để Dashboard không trống ngay lần đầu chạy
        demo_projects = [
            ("ch_sik", "prj_demo_sik", "Vì sao triều Nguyễn mất Nam Kỳ chỉ trong 20 năm", "Không phải vì yếu quân sự, mà vì một loạt quyết định ngoại giao sai thời điểm."),
            ("ch_tk", "prj_demo_tk", "Sai lầm khiến người trẻ mất tiền năm đầu đi làm", "Ai cũng nghĩ lỗi ở lương thấp, thật ra lỗi ở cách chi tiêu tuần đầu nhận lương."),
            ("ch_tlh", "prj_demo_tlh", "Vì sao ta luôn yêu sai người", "Ta không lặp lại sai lầm — ta lặp lại một khuôn mẫu gắn bó từ nhỏ."),
        ]
        for channel_id, pid, title, insight in demo_projects:
            pdir = project_dir(channel_id, pid)
            brief = Brief(project_id=pid, channel_id=channel_id, topic=title, insight=insight)
            write_json(pdir / "brief.json", brief.model_dump())
            pack = ProductionPack(project_id=pid, channel_id=channel_id, brandprofile_version=1, status="draft")
            write_json(pdir / "pack.json", pack.model_dump())
            write_json(pdir / "pack.v1.json", pack.model_dump())
            db.add(Project(id=pid, channel_id=channel_id, title=title, status="draft", step=0, max_step_reached=0,
                            brief_path=str(pdir / "brief.json"), pack_path=str(pdir / "pack.json"), pack_version=1))

        db.commit()
    finally:
        db.close()
