"""Seed dữ liệu khởi tạo — chạy 1 lần khi DB rỗng.

Bao gồm: app_setting mặc định, thư viện Prompt Templates (nội dung port từ design
StudioFlow Prototype.dc.html), 1 provider LLM mặc định (Mock — luôn sẵn sàng, xem
app/providers/mock.py), và dữ liệu demo 3 kênh + vài project ở các bước khác nhau
để trải nghiệm lần đầu giống hệt bản design.
"""
import json

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
    ("pt_brief", "Gợi ý Brief từ ý tưởng", "brief", [
        ("v1", "Khởi tạo", "Hải Yến", "Từ chủ đề {{topic}}, gợi ý insight, đối tượng khán giả và mục tiêu nội dung phù hợp kênh {{channel}}."),
        ("v2", "Thêm câu hỏi gợi insight", "Hải Yến", "Từ chủ đề {{topic}} và BrandProfile kênh {{channel}}, gợi ý insight, đối tượng khán giả và mục tiêu nội dung. Đặt 1 câu hỏi giúp làm rõ insight nếu chủ đề còn mơ hồ."),
    ]),
    ("pt_outline", "Sinh Outline & Hook variants", "outline_hook", [
        ("v1", "Khởi tạo", "Hải Yến", "Từ Brief {{brief}}, sinh outline và hook variants."),
        ("v2", "Thêm tham số framework", "Minh Anh", "Từ Brief {{brief}}, sinh {{outline_count}} outline và {{hook_count}} biến thể hook theo framework {{framework}}."),
        ("v3", "Ràng buộc hook dưới 12 từ", "Hải Yến", "Từ Brief {{brief}}, sinh {{outline_count}} outline khác góc tiếp cận và {{hook_count}} biến thể hook theo framework {{framework}}. Mỗi hook dưới 12 từ, không clickbait sai sự thật."),
    ]),
    ("pt_script", "Viết Master Script", "script", [
        ("v1", "Khởi tạo", "Hải Yến", "Viết Master Script từ Outline {{outline}} và Hook {{hook}}, độ dài {{length}}."),
        ("v2", "Thêm chỉ dẫn nhịp câu ngắn", "Đức Long", "Viết Master Script hoàn chỉnh từ Outline {{outline}} và Hook {{hook}}, giọng văn theo BrandProfile {{channel}}, câu ngắn, tránh thuật ngữ khó, độ dài {{length}}."),
    ]),
    ("pt_script_revise", "Tạo lại Full Script theo góp ý", "script_revise", [
        ("v1", "Khởi tạo", "Đức Long", "Viết lại Full Script {{current_script}} theo góp ý của người dùng: {{user_feedback}}. Giữ nguyên giọng văn BrandProfile {{channel}} và độ dài {{length}}, chỉ điều chỉnh đúng phần được góp ý, không thay đổi các đoạn khác."),
    ]),
    ("pt_script_breakdown", "Phân rã Full Script theo đoạn (Audio/Visual/Direction)", "script_breakdown", [
        ("v1", "Khởi tạo", "Hải Yến", "Phân rã Full Script {{script_text}} thành các đoạn theo timestamp, audio, visual và direction."),
        ("v2", "Giới hạn 8s/shot", "Hải Yến", "Phân rã Full Script {{script_text}} đã duyệt thành các đoạn theo timeline: mỗi đoạn gồm {timestamp, audio (nguyên văn lời đọc), visual (mô tả hình ảnh/video), direction (chỉ dẫn nhịp, cảm xúc)}, tối đa 8s/đoạn."),
    ]),
    ("pt_thumb", "Title, Description & Thumbnail concept", "thumbnail", [
        ("v1", "Khởi tạo", "Minh Anh", "Từ Brief {{brief}} và kịch bản {{script}}, sinh 5-10 tiêu đề tối ưu SEO+CTR, mô tả SEO, hashtags và concept thumbnail theo style kênh {{visual_style_prompt}}."),
    ]),
    ("pt_visual_image", "Visual Studio — Image prompt theo shot", "visual_image", [
        ("v1", "Khởi tạo", "Hải Yến", "Từ đoạn script {{script}} và style kênh {{visual_style_prompt}}, sinh prompt ảnh cho từng shot: muted palette, single accent color, no text, aspect 16:9."),
    ]),
    ("pt_visual_video", "Visual Studio — Video prompt theo shot", "visual_video", [
        ("v1", "Khởi tạo", "Hải Yến", "Từ đoạn script {{script_snippet}} và mô tả visual {{visual_description}}, sinh video 6s loopable theo style kênh {{channel}}: muted color grade, grain overlay nhẹ, no on-screen text."),
    ]),
    ("pt_visual_tts", "Visual Studio — TTS theo emotion mô tả", "visual_tts", [
        ("v1", "Khởi tạo", "Đức Long", "Đọc đoạn script {{script_snippet}} với giọng {{voice_profile}} theo emotion mô tả: {{emotion_description}}. Giữ tông BrandProfile kênh {{channel}}."),
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
    db = SessionLocal()
    try:
        if db.query(Channel).count() > 0:
            return  # đã seed trước đó

        # app_setting mặc định
        for key, value in {
            "general": {"org_name": "Media House VN", "language": "vi", "timezone": "Asia/Ho_Chi_Minh", "export_format": "markdown", "naming_convention": "[Kênh]_[YYMMDD]_[Chủ đề ngắn]"},
            "ai_params": {"temperature": 0.7, "length": "3-6 phút", "hook_count": 3, "framework": "AIDA"},
            "app_branding": {"name": "Media House VN", "accent_swatch": 0},
        }.items():
            db.add(AppSetting(key=key, value=json.dumps(value, ensure_ascii=False)))

        # prompt templates
        for tid, name, task, versions in PROMPT_SEED:
            active = versions[-1][0]
            db.add(PromptTemplate(id=tid, name=name, task=task, active_version=active))
            for version, note, updated_by, body in versions:
                db.add(PromptTemplateVersion(template_id=tid, version=version, content=body, note=note, updated_by=updated_by))

        # provider mock mặc định — luôn sẵn sàng, không cần key/GPU (xem app/providers/mock.py)
        db.add(ProviderConfig(task="llm", provider_name="mock", display_name="Local Mock (Dev)", connection_type="local_endpoint",
                               endpoint_url=None, model_name="mock-deterministic", available_models="[]",
                               is_default=True, enabled=True, status="ok"))

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
