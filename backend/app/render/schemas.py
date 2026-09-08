"""Schema trạng thái render (M2 — Production Layer) — cố ý TÁCH khỏi
app/schemas/__init__.py::ProductionPack (specs/09 mục "Ràng buộc xuyên suốt": "Chống
coupling: script core ⟂ render module"). Module render CHỈ ĐỌC pack.json (script/shots
đã duyệt), không bao giờ ghi field mới vào đó — mọi trạng thái sinh asset/ghép video
sống trong file riêng `render.json` (xem app/config.py::project_dir, app/render/engine.py).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

AssetStatus = Literal["pending", "generating", "ready", "error"]
AssemblyStatus = Literal["not_started", "assembling", "done", "error"]


class ShotRenderStatus(BaseModel):
    shot_id: str
    visual_status: AssetStatus = "pending"
    visual_asset_path: Optional[str] = None
    visual_provider: Optional[str] = None
    visual_error: Optional[str] = None
    visual_started_at: Optional[str] = None  # ISO datetime — set lúc chuyển "generating", None khi xong. Frontend tự tính thời gian đã trôi (đồng hồ đếm) — UX cho video local chạy 7-18 phút, xem IMPLEMENTATION_REPORT.md.
    # **Mới (2026-08-23)** — set lúc `visual_status` chuyển "ready" THÀNH CÔNG (KHÔNG bị
    # xoá về None sau đó, khác `visual_started_at`) — bug thật người dùng báo: sinh lại
    # ảnh cho 1 shot xong, ảnh mới hiện đúng ngay, nhưng chuyển project khác rồi quay lại
    # thì hiện ảnh CŨ. Nguyên nhân: `assets/{shot_id}.png` bị ĐÈ TẠI CHỖ (cùng tên file
    # mỗi lần sinh lại), URL ảnh ở frontend cố định theo shot_id — cache-bust trước đây
    # dựa vào 1 counter local trong component (`shotCacheBust`), RESET VỀ 0 mỗi lần màn
    # Visual Studio unmount (chuyển project) — browser thấy lại ĐÚNG URL đã cache trước
    # đó, trả thẳng bytes cũ không gọi mạng. Field này bền trong render.json (refetch mới
    # mỗi lần mount), dùng làm cache-bust query param THẬT thay cho counter local — xem
    # `frontend/src/screens/steps/VisualStudio.tsx::ShotPreview`. Cũng dùng để phát hiện
    # video đã ghép (`RenderState.assembly_completed_at`) có CŨ HƠN lần sinh gần nhất
    # không — xem `OutputCenter.tsx`.
    visual_updated_at: Optional[str] = None
    approved: bool = False  # human review bắt buộc trước khi ghép (specs/09 M2)
    # Channel Asset Vault (CHANGE_Semantic_BRoll_Asset_Vault.md) — set khi shot dùng clip
    # B-roll từ kho tư liệu kênh thay vì AI sinh/upload rời (`visual_provider=
    # "asset_vault"` cùng lúc). Trỏ tới `ProcessedClip.clip_id` — dùng để (1) tăng
    # `usage_count`/`last_used_at` cho dedup, (2) tra `rights_status` cho cảnh báo
    # Guardrail (`app/routers/guardrail.py`). Đặt ở ĐÂY (render.json, không phải
    # pack.json's Shot) để việc "gán clip vào shot" đi ĐÚNG con đường `upload-visual` đã
    # có (render.py chỉ đọc pack.json, không bao giờ ghi lại — xem docstring đầu file đó).
    linked_clip_id: Optional[str] = None
    # Xoá watermark (2026-08-28, tái dùng `app/watermark/` từ Kho Tài Nguyên) — "quét
    # xong, KHÔNG tìm thấy watermark" KHÔNG phải lỗi (asset gốc vẫn hợp lệ, giữ nguyên),
    # nên KHÔNG dùng `visual_error` (field đó gắn với UI báo lỗi đỏ, dành cho lỗi thật) —
    # field riêng để UI hiện thông báo rõ ràng, trung tính, tách biệt khỏi lỗi. Xoá (None)
    # ngay khi bắt đầu 1 lượt quét mới, hoặc khi asset được thay (sinh lại/upload).
    visual_watermark_note: Optional[str] = None
    # Tiến trình THẬT lúc vá watermark cho VIDEO (frame đã vá / tổng số frame) — **mới
    # (2026-09-02, theo yêu cầu người dùng: "tương tự thanh tiến trình ở Kho Tài Nguyên")**.
    # Chỉ có ý nghĩa cho shot VIDEO (ảnh vá 1 lượt Florence-2+LaMa duy nhất, quá nhanh để
    # cần thanh tiến trình) — null khi không có lượt xoá watermark nào đang chạy. Cùng đơn
    # vị/callback với `RawVideo.progress_current/total/label` (Kho Tài Nguyên) nhưng KHÔNG
    # dùng lại field `visual_started_at`/đồng hồ đếm giây đã có (đó đo THỜI GIAN, cái này đo
    # SỐ LƯỢNG frame — cần cả 2 để UI vừa có % vừa có ước lượng thời gian).
    visual_watermark_progress_current: Optional[int] = None
    visual_watermark_progress_total: Optional[int] = None
    visual_watermark_progress_label: Optional[str] = None

    narration_status: AssetStatus = "pending"
    narration_asset_path: Optional[str] = None
    narration_provider: Optional[str] = None
    narration_error: Optional[str] = None
    narration_duration_sec: Optional[float] = None  # đo thật qua ffprobe — dùng cho thời lượng video THỰC ở Pack Review
    narration_started_at: Optional[str] = None
    narration_updated_at: Optional[str] = None  # cùng lý do/cách dùng `visual_updated_at` ở trên, áp cho giọng đọc


class IntroAssetStatus(BaseModel):
    """Shot mở đầu RIÊNG của project — **mới (2026-08-20)**, theo yêu cầu người dùng.
    KHÔNG phải AI sinh (khác `ShotRenderStatus`) — người dùng tự upload trực tiếp, nên
    không cần các field `*_status`/`*_provider`/`*_started_at`. Khi đầy đủ (video, HOẶC
    ảnh+audio đi kèm), override HẲN video/audio thương hiệu ở cấp kênh (BrandProfile) —
    xem `app/render/assembly.py::_resolve_intro_source`."""
    kind: Literal["image", "video"] = "image"
    visual_asset_path: Optional[str] = None
    # CHỈ áp dụng/bắt buộc khi kind=="image" (video tự có audio riêng, không cần audio
    # rời) — xem app/routers/render.py::upload_intro_audio (400 nếu kind=="video").
    audio_asset_path: Optional[str] = None
    # Hiệu ứng chuyển cảnh GIỮA intro và shot đầu tiên của kịch bản — **mới (2026-08-21)**,
    # theo yêu cầu người dùng. Cùng bảng giá trị `app/render/transitions.py::TRANSITIONS`
    # dùng cho `transition_to_next` giữa 2 shot thường — "cut" (mặc định) đi đường ghép
    # CŨ (`_concat_intro_and_body`, filter concat không xfade); giá trị khác dùng
    # `_xfade_chain` (cùng cơ chế xfade/acrossfade đã có cho shot-to-shot) — xem
    # `app/render/assembly.py::assemble_video`.
    transition_to_next: str = "cut"
    # Người dùng CHỦ ĐỘNG bỏ hẳn shot mở đầu cho project này — **mới (2026-08-22)**,
    # theo yêu cầu người dùng: Visual Studio giờ HIỂN THỊ rõ video/audio thương hiệu cấp
    # kênh làm shot mở đầu MẶC ĐỊNH (kế thừa — hành vi fallback vốn đã có ở
    # `resolve_intro_source`, trước đây chỉ áp dụng NGẦM lúc ghép, không hiện gì ở UI).
    # `disabled=True` là cách DUY NHẤT tắt hẳn intro cho project này — kể cả khi kênh CÓ
    # cấu hình thương hiệu — phân biệt với trạng thái mặc định "project chưa có asset
    # riêng" (ngầm định kế thừa brand). Set field này CHỈ ghi vào `render.json` của TỪNG
    # project — KHÔNG BAO GIỜ đụng tới BrandProfile cấp kênh (xem app/routers/render.py::
    # delete_intro/enable_intro_inherit — 2 endpoint DUY NHẤT đổi field này).
    disabled: bool = False


class BgMusicOverride(BaseModel):
    """Nhạc nền RIÊNG của project — **mới (2026-08-20)**, theo yêu cầu người dùng: khi
    có `asset_path`, OVERRIDE HẲN nhạc nền mặc định cấp kênh (`BrandProfile.bg_music_
    path`) — xem `app/render/bg_music.py::resolve_bg_music_source`. `volume` (0.0=câm,
    1.0=to bằng giọng đọc chính) áp dụng cho CHÍNH override này, không dùng chung
    `bg_music_volume` cấp kênh (project có thể muốn mix khác channel)."""
    asset_path: Optional[str] = None
    volume: float = 0.3


class OverlayEffectOverride(BaseModel):
    """Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) RIÊNG của project — **mới
    (2026-08-22)**, theo yêu cầu người dùng: khi có `asset_path`, OVERRIDE HẲN overlay
    mặc định cấp kênh (`BrandProfile.overlay_effect_path`) — xem `app/render/overlay.py::
    resolve_overlay_source`. `opacity` (0.0=tắt hẳn, 1.0=full cường độ) áp dụng cho CHÍNH
    override này, không dùng chung `overlay_effect_opacity` cấp kênh (project có thể
    muốn cường độ khác channel) — cùng nguyên tắc `BgMusicOverride.volume` ở trên.
    `disabled` — **mới (2026-09-02)**, theo yêu cầu người dùng: TRƯỚC ĐÂY không có cách
    nào tắt hẳn overlay khi đang KẾ THỪA overlay mặc định cấp kênh (chỉ xoá được override
    RIÊNG của project qua `DELETE .../render/overlay`, nhưng xoá xong lại tự quay về dùng
    overlay kênh — không có lối "không dùng overlay nào cả" cho project này). Cùng khái
    niệm/2 endpoint DUY NHẤT đổi field này (`delete_project_overlay`/`enable_overlay_
    inherit`) như `IntroAssetStatus.disabled` ở trên."""
    asset_path: Optional[str] = None
    opacity: float = 0.5
    disabled: bool = False


class BackgroundVideoOverride(BaseModel):
    """Video nền CHUNG cho toàn bộ block (mới 2026-09-02, theo yêu cầu người dùng) — loop
    theo đúng tổng thời lượng timeline shot list (KHÔNG phân biệt ranh giới từng shot —
    xem `app/render/assembly.py::assemble_video`, phần dựng `_bg_master`). Shot NÀO CHƯA
    cấu hình visual riêng (chưa sinh/upload ảnh/video) sẽ tự lấy đúng đoạn video nền tương
    ứng trên timeline làm nội dung — shot ĐÃ có visual riêng THAY THẾ TOÀN MÀN HÌNH cho
    đúng khoảng thời gian của shot đó (cắt cảnh về nền ngay sau khi hết shot), khác hẳn
    overlay (đè MỜ liên tục suốt video, không thay thế nội dung). KHÁC bg_music/overlay —
    KHÔNG có cấp kênh mặc định (thuần project, theo đúng phạm vi yêu cầu), và KHÔNG có
    field âm lượng/cường độ — audio LUÔN bỏ qua hẳn (video nền chỉ lấy hình, giọng đọc/
    nhạc nền vẫn là nguồn audio duy nhất, giống mọi visual video khác trong app).

    **Nhiều video (mới 2026-09-02, mục 110)** — theo yêu cầu người dùng: `asset_paths`
    (đổi từ `asset_path` đơn — KHÔNG giữ tương thích ngược, tính năng vừa build cùng
    ngày, chưa có dữ liệu thật cần migrate) cho phép upload NHIỀU video, nối lại thành 1
    "playlist" rồi mới loop theo tổng thời lượng timeline (xem `assembly.py::_build_
    background_video_playlist`, chạy TRƯỚC `_build_background_video_master`). Thứ tự
    trong `asset_paths` LUÔN là thứ tự upload (không tự sắp lại) — `random_order` chỉ
    XÁO TRỘN 1 LẦN lúc build playlist cho MỖI LẦN ghép (không phải xáo lại mỗi vòng lặp
    khi loop), giữ đơn giản đúng yêu cầu "random loop on/off" mà không cần dựng lại
    playlist động phức tạp mỗi chu kỳ lặp. `transition` (cùng danh sách `TRANSITIONS`
    dùng cho shot-to-shot, `transitions.py`) áp dụng GIỮA các video liên tiếp trong
    playlist — `"cut"` (mặc định) nối cứng bằng filter `concat`, giá trị khác dùng
    `xfade` thật (video-only, không audio) giữa từng cặp liên tiếp."""
    asset_paths: list[str] = Field(default_factory=list)
    random_order: bool = False
    transition: str = "cut"


LayerPosition = Literal[
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
]


LayerBlendMode = Literal["alpha", "screen"]


class VideoLayer(BaseModel):
    """Layer video ĐỊNH VỊ theo lưới 3×3 — **mới (2026-09-02, mục 112)**, theo yêu cầu
    người dùng: "thêm layer voice wave (dạng video loop) vào bên trên video nền". KHÁC
    `OverlayEffectOverride` (phủ TOÀN MÀN HÌNH liên tục — mưa/tuyết/bụi) — layer ở đây
    ĐỊNH VỊ tại 1 trong 9 ô lưới, kích thước % khung hình (watermark/logo/waveform
    decorative, không phải VFX khí quyển phủ đè cả khung hình).

    `blend_mode` — **mới (2026-09-02, mục 113)**, theo yêu cầu người dùng ("tôi chỉ có
    video layer nền đen thôi, hãy process nền đen"): asset thật của người dùng KHÔNG có
    kênh alpha (khác giả định ban đầu lúc thiết kế mục 112) — thêm chế độ `"screen"` xử
    lý clip nền ĐEN ĐẶC (cùng kỹ thuật `_mix_overlay_effect` dùng cho overlay hiệu ứng
    lớp phủ — nền đen "biến mất" khi blend screen), khác `"alpha"` (mặc định, mục 112 —
    dùng kênh alpha CÓ SẴN của nguồn qua filter `overlay` thẳng). `"screen"` phức tạp
    hơn (cần cắt đúng vùng nền tương ứng để blend TRƯỚC khi ghép lại đúng vị trí — xem
    `assembly.py::_composite_layers`) nhưng không đòi hỏi nguồn phải có alpha.

    Nhiều layer cùng lúc — `RenderState.layers: list[VideoLayer]` (list, không phải 1
    field đơn) — cho phép VD vừa có voice wave góc dưới vừa có logo góc trên cùng lúc,
    mỗi layer có thể dùng `blend_mode` khác nhau. Áp dụng NGAY SAU overlay hiệu ứng lớp
    phủ (nếu có) trong hậu kỳ cuối cùng — xem `assembly.py::_composite_layers` — nên
    layer LUÔN nổi TRÊN CÙNG, không bị mưa/tuyết che."""
    id: str
    asset_path: str
    position: LayerPosition = "bottom-center"
    # % chiều RỘNG khung hình xuất — chiều cao tự co theo đúng tỉ lệ khung hình gốc của
    # layer (không ép méo). 0.3 = 30% bề rộng, đủ rõ cho 1 dải waveform ngang mà không
    # chiếm quá nhiều diện tích.
    width_pct: float = 0.3
    opacity: float = 1.0
    blend_mode: LayerBlendMode = "alpha"


ImageLayerPosition = Literal[
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
    "full",
]


class ImageLayer(BaseModel):
    """Layer ẢNH ĐỊNH VỊ — **mới (2026-09-02, mục 115)**, theo yêu cầu người dùng: "bổ
    sung thêm block... setup Layer ảnh định vị với chức năng tương tự nhưng cho ảnh nền
    đen hoặc không có nền. Ngoài hỗ trợ 9 vị trí layer thì còn hỗ trợ thêm full khung
    hình". Song song `VideoLayer` (mục 112/113) — CÙNG 2 chế độ `blend_mode` (`"alpha"`
    nguồn CÓ SẴN kênh alpha PNG/WEBP trong suốt; `"screen"` nguồn ẢNH NỀN ĐEN ĐẶC, screen-
    blend cùng kỹ thuật `_mix_overlay_effect`) — chỉ khác 2 điểm: (1) nguồn LUÔN ảnh tĩnh
    (PNG/JPEG/WEBP, dùng `-loop 1` thay `-stream_loop -1` khi ghép — xem `assembly.py::
    _composite_image_layers`), (2) `position` có thêm giá trị `"full"` — phủ TOÀN KHUNG
    HÌNH (scale cover đúng tỉ lệ xuất, KHÔNG dùng `width_pct`) thay vì ĐỊNH VỊ tại 1 ô
    lưới — hợp cho ảnh khung viền/vignette/watermark toàn màn hình, khác 9 vị trí còn lại
    (logo góc, watermark nhỏ...).

    Nhiều layer cùng lúc — `RenderState.image_layers: list[ImageLayer]` (list riêng,
    KHÔNG chung với `layers` — 2 loại asset khác nhau, xử lý ffmpeg khác nhau). Áp dụng
    NGAY SAU layer video (nếu có) trong hậu kỳ cuối cùng — xem `assembly.py::_composite_
    image_layers` — nên layer ảnh LUÔN nổi TRÊN CÙNG mọi layer khác."""
    id: str
    asset_path: str
    position: ImageLayerPosition = "bottom-center"
    # Bỏ qua hoàn toàn khi position=="full" (scale cover đúng khung hình xuất).
    width_pct: float = 0.3
    opacity: float = 1.0
    blend_mode: LayerBlendMode = "alpha"


class AssemblyProgress(BaseModel):
    """Tiến trình ghép MP4 theo đơn vị TỰ NHIÊN sẵn có — mỗi shot 1 segment ffmpeg
    riêng, không cần parse `-progress` real-time của ffmpeg (phức tạp hơn nhiều, không
    cần thiết vì số segment đã đủ chi tiết để hiện % + ước lượng thời gian còn lại).

    `stage="background_video"` — **mới (2026-09-02, mục 108)**: bước dựng video nền
    chung (`_build_background_video_master` + cắt chunk cho từng shot trống) chạy TRƯỚC
    Pass 2 (segment thật) khi project có cấu hình video nền — trước đây KHÔNG có stage
    riêng, `assembly_progress` vẫn đứng yên ở `stage="segments", current=0` suốt bước
    này (đặt SỚM ở đầu hàm cho có total ngay), khiến UI hiện nhầm "Đang ghép cảnh 0/N..."
    dù chưa có segment nào thật sự bắt đầu — xem `RenderStudio.tsx`."""
    stage: Literal["background_video", "segments", "concat"] = "segments"
    current: int = 0
    total: int = 0
    # **Mới (2026-09-02, mục 108)** — mốc thời gian bước hiện tại BẮT ĐẦU (khác
    # `RenderState.assembly_started_at` — mốc TOÀN BỘ assembly, dùng hiện "Đã chạy: X").
    # Ước lượng thời gian còn lại (`RenderStudio.tsx::remainingSec`) PHẢI tính theo thời
    # gian trôi từ khi stage "segments" bắt đầu, KHÔNG PHẢI từ lúc assembly bắt đầu —
    # nếu có bước dựng video nền chung chạy trước (có thể mất vài phút với video dài),
    # gộp chung vào elapsed sẽ làm ước lượng trung bình/segment bị thổi phồng sai lệch.
    stage_started_at: Optional[str] = None


class WatermarkScanSummary(BaseModel):
    """Tóm tắt 1 lượt "Xoá watermark toàn bộ slot" (2026-08-28) — người dùng yêu cầu rõ
    "nếu ảnh nào không phát hiện watermark thì có thông báo rõ ràng"; với hàng LOẠT shot,
    hiện từng thông báo riêng lẻ (như `ShotRenderStatus.visual_watermark_note`) dễ bị bỏ
    sót — field này gộp lại 1 banner tóm tắt duy nhất sau khi quét xong cả block. Ghi đè
    mỗi lần chạy lại (không cần lịch sử nhiều lượt — chỉ cần biết kết quả lượt GẦN NHẤT)."""
    scanned: int
    cleaned: int
    no_watermark: int
    failed: int
    finished_at: str


class RenderState(BaseModel):
    project_id: str
    shots: list[ShotRenderStatus] = Field(default_factory=list)
    # **Mới (2026-09-02, mục 109)** — tốc độ phát giọng đọc cho TOÀN BỘ block của project
    # này, chỉnh ở Script Studio (nút "Sinh giọng đọc cho toàn bộ block" đứng cạnh thanh
    # trượt tốc độ). ÁP DỤNG BẰNG CÁCH TIME-STRETCH file audio SAU khi provider TTS sinh
    # xong (ffmpeg `atempo`, xem `engine.py::_apply_narration_speed`) — KHÔNG phải tham
    # số API riêng của từng provider TTS (ElevenLabs/Gemini/Piper/OmniVoice có/không hỗ
    # trợ khác nhau) — theo yêu cầu người dùng: "điều chỉnh tốc độ của file giọng đọc
    # được tạo ra", áp dụng ĐỒNG NHẤT bất kể provider nào đang cấu hình. Chỉ áp dụng cho
    # lần sinh MỚI (khi (re)generate) — đổi giá trị này KHÔNG tự sinh lại narration đã có
    # sẵn, đúng nguyên tắc "không tự chạy ngầm, người dùng tự bấm sinh lại". 1.0 = tốc độ
    # gốc (mặc định, không xử lý gì thêm).
    narration_speed: float = 1.0
    intro: Optional[IntroAssetStatus] = None
    bg_music: Optional[BgMusicOverride] = None
    overlay: Optional[OverlayEffectOverride] = None
    background_video: Optional[BackgroundVideoOverride] = None
    # Layer video định vị theo lưới 3x3 (VD voice wave, logo) — mới (2026-09-02, mục 112).
    layers: list[VideoLayer] = Field(default_factory=list)
    # Layer ẢNH định vị theo lưới 3x3 HOẶC toàn khung hình — mới (2026-09-02, mục 115).
    image_layers: list[ImageLayer] = Field(default_factory=list)
    assembly_status: AssemblyStatus = "not_started"
    assembly_error: Optional[str] = None
    assembly_progress: Optional[AssemblyProgress] = None
    assembly_started_at: Optional[str] = None
    # **Mới (2026-08-23)** — set lúc `assembly_status` chuyển "done" THÀNH CÔNG (không bị
    # xoá về None sau đó — khác `assembly_started_at`). So sánh với `visual_updated_at`/
    # `narration_updated_at` của từng shot để phát hiện "video đã ghép nhưng có shot sinh
    # lại SAU lần ghép này" — xem `OutputCenter.tsx`.
    assembly_completed_at: Optional[str] = None
    final_video_path: Optional[str] = None
    watermark_scan_summary: Optional[WatermarkScanSummary] = None
