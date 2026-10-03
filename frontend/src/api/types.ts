// Kiểu dữ liệu khớp backend/app/schemas — xem specs/04_data_schemas.md (đã cập nhật).

export interface ChannelSummary {
  id: string;
  name: string;
  niche: string;
  letter: string;
  archived: boolean;
  brandprofile_version: number;
  running_count: number;
  // Chỉ số YouTube — mới (2026-09-12).
  youtube_channel_id: string | null;
  youtube_channel_title: string | null;
  youtube_connected_at: string | null;
}

export interface TrashProjectSummary extends ProjectSummary {
  channel_name: string;
}
export interface TrashOut {
  channels: ChannelSummary[];
  projects: TrashProjectSummary[];
}

export interface BrandVoice {
  tone: string;
  formality: string;
  pacing: string;
  sample_lines: string[];
}
export interface ContentPillar {
  name: string;
  weight: number;
}
export interface RetentionBenchmark {
  target_hook_strength: number;
  max_anchor_gap_sec: number;
  target_body_len_min: number;
}
// Giọng đọc đa ngôn ngữ (mới 2026-09-04) — 6 ngôn ngữ hỗ trợ, khớp
// `backend/app/render/schemas.py::NARRATION_LANGUAGES` (nguồn sự thật duy nhất).
export type NarrationLanguage = "vi" | "en" | "de" | "pt_br" | "es" | "fr";
export const NARRATION_LANGUAGES: NarrationLanguage[] = ["vi", "en", "de", "pt_br", "es", "fr"];
export const NARRATION_LANGUAGE_LABELS: Record<NarrationLanguage, string> = {
  vi: "Tiếng Việt",
  en: "Tiếng Anh",
  de: "Tiếng Đức",
  pt_br: "Tiếng Bồ Đào Nha (Brazil)",
  es: "Tiếng Tây Ban Nha",
  fr: "Tiếng Pháp",
};
export interface BrandProfile {
  channel_id: string;
  niche: string;
  brand_voice: BrandVoice;
  content_pillars: ContentPillar[];
  forbidden: string[];
  visual_style_prompt: string;
  // Cultural lock — mới (2026-08-23), theo yêu cầu người dùng chống thiên lệch văn hoá
  // Nhật/Hàn của checkpoint/LoRA "Á Đông" (đa số train từ dữ liệu Nhật/Trung/Hàn).
  // `cultural_lock_positive` — từ khoá Việt Nam cụ thể (trang phục theo triều đại, kiến
  // trúc, hoạ tiết) — áp dụng cho MỌI provider (cloud lẫn local). Rỗng mặc định — đặc thù
  // theo từng kênh/thời kỳ lịch sử.
  cultural_lock_positive: string;
  // `cultural_lock_negative` — loại trừ văn hoá ngoại lai. **Đợt dọn dẹp (2026-09-24)**:
  // hiện KHÔNG nối vào bất kỳ provider nào — trước đây chỉ có tác dụng qua negative-prompt
  // thật của 4 provider local đã xoá (SDXL/Flux/Wan/LocalAI, xem IMPLEMENTATION_REPORT.md)
  // — để dành nối vào provider local còn lại (`local_qwen`, có negative_prompt thật) sau
  // nếu cần.
  cultural_lock_negative: string;
  hook_formats_preferred: string[];
  retention_benchmark: RetentionBenchmark;
  // Logo kênh — mới (2026-08-22) — thuần hiển thị nhận diện thương hiệu, không dùng
  // trong pipeline sinh asset/ghép video.
  logo_path: string;
  voice_clone_ref_path: string;
  // Video/audio thương hiệu — mới (2026-08-20) — phát ở ĐẦU mọi video của kênh này khi
  // ghép MP4. CHỈ 1 trong 2 khác rỗng tại 1 thời điểm (server tự đảm bảo, xem client.ts
  // uploadBrandIntro).
  intro_video_path: string;
  intro_audio_path: string;
  // Nhạc nền MẶC ĐỊNH của kênh — mới (2026-08-20) — phát đè liên tục dưới toàn bộ video
  // (kể cả intro) khi ghép MP4, trừ khi project tự override riêng (RenderState.bg_music).
  bg_music_path: string;
  bg_music_volume: number;
  // Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) MẶC ĐỊNH của kênh — mới (2026-08-22) —
  // blend đè liên tục lên toàn bộ video (kể cả intro) khi ghép MP4, trừ khi project tự
  // override riêng (RenderState.overlay). LUÔN video (mp4/webm/mov).
  overlay_effect_path: string;
  overlay_effect_opacity: number;
  // Style normalization hậu kỳ (CHANGE_Semantic_BRoll_Asset_Vault.md §9b.2/§9b.3) — preset
  // màu CỐ ĐỊNH theo kênh (rỗng = mặc định cũ), film grain tuỳ chọn, cách xử lý khung hình
  // lệch tỷ lệ (crop = cũ, blur = nền mờ từ chính nội dung, không mất chi tiết rìa).
  visual_grade: string;
  grain_enabled: boolean;
  aspect_fill_mode: "crop" | "blur";
  // Auto-ducking nhạc nền (§9b.5) — tự giảm nhạc nền khi có giọng đọc, mặc định tắt.
  bg_music_ducking_enabled: boolean;
  // Giọng đọc đa ngôn ngữ cho thị trường nước ngoài — mới (2026-09-04). `primary_language`
  // quyết định ngôn ngữ nào dùng để render video/tính timestamp (field `audio`/
  // `narration_*` gốc, KHÔNG đổi). `voice_clone_ref_paths` — mẫu giọng clone RIÊNG từng
  // ngôn ngữ (thay `voice_clone_ref_path` đơn cũ, field đó GIỮ NGUYÊN để đọc dữ liệu cũ).
  primary_language: NarrationLanguage;
  voice_clone_ref_paths: Partial<Record<NarrationLanguage, string>>;
  version: number;
}
// Chỉ trả về từ POST voice-sample/upload — báo 1 lần mẫu có bị cắt ngắn không (mục 24
// IMPLEMENTATION_REPORT.md: mẫu >10s gây lẫn nội dung tham chiếu vào narration), KHÔNG
// phải field persist trong BrandProfile thật.
export interface VoiceSampleUploadResult extends BrandProfile {
  voice_sample_trimmed: boolean;
  voice_sample_original_duration_sec: number | null;
}

export interface ProjectSummary {
  id: string;
  channel_id: string;
  title: string;
  status: string;
  step: number;
  max_step_reached: number;
  pack_version: number;
  return_note: string;
  archived: boolean;
  // Short-form (9:16, YouTube Shorts/TikTok) — mới (2026-08-21): sub-project ĐỘC LẬP
  // nội dung, lồng dưới 1 project long-form CÙNG kênh chỉ để nhóm hiển thị (Sidebar/
  // Dashboard). `parent_project_id` null = long-form; có giá trị = short-form.
  parent_project_id: string | null;
  format: "long" | "short";
  youtube_video_id: string | null; // mới (2026-09-12), xem YoutubeVideosAvailable
  created_at: string;
  updated_at: string;
}

export interface BriefSource {
  id: string;
  kind: "youtube" | "file";
  label: string;
  status: "extracting" | "done" | "error";
  char_count?: number | null;
  content_path?: string | null;
  error?: string | null;
}
export interface Brief {
  project_id: string;
  channel_id: string;
  topic: string;
  insight: string;
  strategy: { content_matrix_slot: string; growth_objective: string; conversion_point: string };
  audience: { seo_keywords: string[]; retention_notes: string; pain_points: string[]; description: string };
  raw_knowledge: { documents: BriefSource[]; expert_notes: string; key_message: string };
  conversion_note: string;
  brand_voice_override: BrandVoice | null;
}

export interface Warning {
  type: string;
  severity: "amber" | "red";
  at_timestamp_sec: number | null;
  message: string;
}
export interface ScriptBodyItem {
  timestamp_sec: number;
  end_sec: number | null;
  audio: string;
  visual: string;
  direction: string;
  direction_label?: string;
  block_id?: string | null;
  visual_type?: string | null;
  anchor: boolean;
  warning: Warning | null;
  // Giọng đọc đa ngôn ngữ (mới 2026-09-04) — văn bản VO đã dịch cho TỪNG ngôn ngữ, đọc từ
  // file import (cột "VO (VI)"/"VO (DE)"/...) hoặc sửa tay ở Script Studio. `audio` (field
  // gốc, trên) luôn là bản dịch của `BrandProfile.primary_language`.
  audio_by_lang: Partial<Record<NarrationLanguage, string>>;
}
export interface Script {
  hook: { spoken: string; visual: string; duration_sec: number } | null;
  body: ScriptBodyItem[];
  cta: { spoken: string; conversion_point: string } | null;
  full_text: string;
  source?: "ai" | "import";
}
export interface Shot {
  shot_id: string;
  asset_type: string;
  visual_type: "image" | "video";
  provider: string | null;
  visual_fx: string;
  audio_sfx: string;
  block_id?: string | null;
  linked_timestamp_sec: number | null;
  transition_to_next: string;
  camera_motion: string;
}
export interface ImportedBeat {
  block_id: string;
  ts_label: string;
  timestamp_sec: number;
  end_sec: number | null;
  visual_type: string;
  visual: string;
  direction: string;
  direction_label: string;
  audio: string;
  anchor: boolean;
  // Giọng đọc đa ngôn ngữ (mới 2026-09-04) — populated khi file import dùng cột "VO (XX)"
  // thay vì 1 cột VO đơn (xem app/pipeline/script_import.py). Rỗng {} với file cũ.
  audio_by_lang: Partial<Record<NarrationLanguage, string>>;
}
export interface ImportPreview {
  beats: ImportedBeat[];
  stats: { block_count: number; word_count: number; duration_label: string };
  full_text: string;
}
export interface YoutubeMeta {
  thumbnail_description: string;
  thumbnail_status: "pending" | "generating" | "ready" | "error";
  thumbnail_asset_path: string | null;
  thumbnail_provider: string | null;
  thumbnail_error: string | null;
  thumbnail_approved: boolean;
}
export interface RetentionCheck {
  hook_strength: number | null;
  max_anchor_gap_sec: number | null;
  warnings: Warning[];
}
export interface ProductionPack {
  project_id: string;
  channel_id: string;
  brandprofile_version: number;
  status: string;
  script: Script | null;
  shots: Shot[];
  youtube_meta: YoutubeMeta | null;
  repurpose: unknown | null;
  retention_check: RetentionCheck | null;
  version: number;
}

export interface ProviderOut {
  id: number;
  task: "llm" | "tts" | "image" | "video";
  provider_name: string;
  display_name: string;
  connection_type: "cloud_api" | "local_endpoint";
  endpoint_url: string | null;
  model_name: string | null;
  available_models: string[];
  is_default: boolean;
  is_fallback: boolean;
  enabled: boolean;
  status: "ok" | "error" | "untested";
  key_display: string;
  has_key: boolean;
}

export interface AuditLogEntry {
  time: string;
  user: string;
  action: string;
  detail: string;
  entity: string | null;
  type: string;
  cost: number | null;
}

export interface BudgetOut {
  id: number;
  channel_id: string;
  channel_name: string;
  soft_limit: number;
  threshold_pct: number;
  spent: number;
  over_threshold: boolean;
}

export interface PromptTemplateOut {
  id: string;
  name: string;
  task: string;
  active_version: string;
  body: string;
  updated_by: string;
  updated_at: string;
  versions: { version: string; note: string; updated_by: string; updated_at: string; is_active: boolean }[];
}

export interface RetentionEntry {
  published_at: string | null;
  ret_0: number | null;
  ret_25: number | null;
  ret_50: number | null;
  ret_100: number | null;
  avg_view_duration: number | null;
  thumbnail_ctr: number | null;
  // RPM (doanh thu ước tính/1.000 view) — mới (2026-09-12). GIỮ NHẬP TAY (không tự động
  // hoá như các chỉ số YouTube khác, xem `YoutubeVideoMetrics` dưới) — quyền doanh thu
  // YouTube (`yt-analytics-monetary.readonly`) khó xin cho app cá nhân.
  rpm: number | null;
}
export interface RetentionOut {
  entry: RetentionEntry | null;
  target_hook_strength: number | null;
  guardrail_hook_strength: number | null;
  diff_vs_benchmark: number | null;
}

// Chỉ số YouTube (Data API v3 + Analytics API v2) — mới (2026-09-12), theo yêu cầu
// người dùng: kéo dữ liệu thật từ YouTube thay "Nạp retention thủ công". Xem
// `backend/app/youtube_analytics.py`/`backend/app/routers/youtube_analytics.py`.
export interface YoutubeSettingsStatus {
  has_oauth_client: boolean;
}
// "Đã kết nối" giờ RIÊNG theo từng kênh — mục 154 (2026-09-19), xem
// `api.getYoutubeChannelOAuthStatus`.
export interface YoutubeChannelOAuthStatus {
  connected: boolean;
}
export interface YoutubeVideoAvailable {
  video_id: string;
  title: string;
  published_at: string;
}
export interface YoutubeVideoMetrics {
  project_id: string;
  synced_at: string;
  views: number | null;
  avg_view_percentage: number | null; // APV (%)
  avg_view_duration_sec: number | null;
  retention_at_30s: number | null; // %
  impressions: number | null;
  impression_ctr: number | null; // %
  comment_count: number | null;
  comments_per_1000_views: number | null;
  video_duration_sec: number | null;
  views_by_country: Record<string, number> | null;
}
export interface YoutubeChannelSnapshot {
  synced_at: string;
  subscriber_count: number | null;
  total_views: number | null;
  video_count: number | null;
  avg_view_percentage: number | null;
  avg_impression_ctr: number | null;
  avg_retention_at_30s: number | null;
  comments_per_1000_views: number | null;
  de_at_ch_views_pct: number | null;
}
export interface YoutubeVideoRow {
  project_id: string;
  project_title: string;
  youtube_video_id: string;
  metrics: YoutubeVideoMetrics | null;
}
export interface YoutubeChannelMetricsOut {
  youtube_channel_id: string | null;
  youtube_channel_title: string | null;
  channel_snapshot: YoutubeChannelSnapshot | null;
  videos: YoutubeVideoRow[];
}
export interface YoutubeRetentionChapter {
  block_id: string;
  start_ratio: number;
  end_ratio: number;
  avg_retention: number;
}

// M2 Production Layer — khớp backend/app/render/schemas.py. State này sống trong
// render.json riêng, KHÔNG phải 1 phần của ProductionPack (module render tách biệt
// script core — specs/09).
export type AssetStatus = "pending" | "generating" | "ready" | "error";
export type AssemblyStatus = "not_started" | "assembling" | "done" | "error";
export interface ShotRenderStatus {
  shot_id: string;
  visual_status: AssetStatus;
  visual_asset_path: string | null;
  visual_provider: string | null;
  visual_error: string | null;
  visual_started_at: string | null;
  // Set lúc sinh/upload THÀNH CÔNG (không bị xoá về null sau đó) — dùng làm cache-bust
  // bền cho URL ảnh/video cố định theo shot_id (xem VisualStudio.tsx::ShotPreview) và để
  // phát hiện video đã ghép có cũ hơn shot này không (OutputCenter.tsx).
  visual_updated_at: string | null;
  approved: boolean;
  // Channel Asset Vault (CHANGE_Semantic_BRoll_Asset_Vault.md) — set khi
  // `visual_provider === "asset_vault"`, trỏ tới ProcessedClip.clip_id đã gán.
  linked_clip_id: string | null;
  // Chiều NGƯỢC lại linked_clip_id — mới (2026-09-11) — set khi visual CỦA CHÍNH shot
  // này đã được lưu vào Kho Tài Nguyên (nút "Lưu vào Kho tài nguyên").
  saved_to_vault_clip_id: string | null;
  // Xoá watermark (2026-08-28) — "quét xong, không tìm thấy" KHÔNG phải lỗi (asset gốc
  // giữ nguyên), nên tách khỏi visual_error — hiện thông báo trung tính riêng.
  visual_watermark_note: string | null;
  // Tiến trình THẬT (2026-09-02) — chỉ có giá trị khi đang xoá watermark cho shot VIDEO
  // (ảnh vá 1 lượt duy nhất, quá nhanh để cần %) — dùng cho ProgressBar dùng chung với
  // Kho Tài Nguyên.
  visual_watermark_progress_current: number | null;
  visual_watermark_progress_total: number | null;
  visual_watermark_progress_label: string | null;
  narration_status: AssetStatus;
  narration_asset_path: string | null;
  narration_provider: string | null;
  narration_error: string | null;
  narration_duration_sec: number | null;
  narration_started_at: string | null;
  narration_updated_at: string | null;
  // Giọng đọc CÁC NGÔN NGỮ KHÁC ngôn ngữ chính — mới (2026-09-04). Ngôn ngữ chính dùng
  // field `narration_*` gốc ở trên (không đổi).
  narration_translations: Partial<Record<NarrationLanguage, TranslatedNarrationStatus>>;
}
export interface TranslatedNarrationStatus {
  narration_status: AssetStatus;
  narration_asset_path: string | null;
  narration_provider: string | null;
  narration_error: string | null;
  narration_duration_sec: number | null;
  narration_updated_at: string | null;
}
export interface GpuStatus {
  reachable: boolean;
  queue_running: number;
  queue_pending: number;
  gpu_name: string | null;
}
// Dashboard "Local Services & GPU Monitor" (2026-08-27) — KHÁC GpuStatus ở trên (đó là
// trạng thái hàng đợi ComfyUI riêng cho Visual Studio); đây là tổng quan phần cứng GPU +
// bật/tắt Ollama/OmniVoice/ComfyUI cấp toàn app. Xem app/local_services.py.
export interface LocalServiceStatus {
  name: string;
  display_name: string;
  running: boolean;
}
export interface GpuHardwareStats {
  available: boolean;
  name?: string;
  memory_used_mb?: number;
  memory_total_mb?: number;
  utilization_pct?: number;
  temperature_c?: number;
  services_using_gpu?: string[];
}
export interface LocalServicesResponse {
  services: LocalServiceStatus[];
  gpu: GpuHardwareStats;
}
export interface AssemblyProgress {
  stage: "background_video" | "segments" | "concat";
  current: number;
  total: number;
  stage_started_at: string | null;
}
// Shot mở đầu RIÊNG của project — mới (2026-08-20) — override video/audio thương hiệu
// cấp kênh khi "đủ" (video, HOẶC ảnh + audio đi kèm bắt buộc).
export interface IntroAssetStatus {
  kind: "image" | "video";
  visual_asset_path: string | null;
  audio_asset_path: string | null;
  // Hiệu ứng chuyển cảnh intro→shot đầu tiên — mới (2026-08-21), cùng bảng giá trị
  // TRANSITION_OPTIONS dùng cho transition_to_next giữa 2 shot thường.
  transition_to_next: string;
  // Người dùng chủ động bỏ hẳn shot mở đầu (không dùng cả video/audio thương hiệu kênh)
  // — mới (2026-08-22). Mặc định false = ngầm kế thừa brand khi chưa có asset riêng.
  disabled: boolean;
}
// Nhạc nền RIÊNG của project — mới (2026-08-20) — override hẳn nhạc nền mặc định cấp
// kênh khi có asset_path.
export interface BgMusicOverride {
  asset_path: string | null;
  volume: number;
}
// Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) RIÊNG của project — mới (2026-08-22) —
// override hẳn overlay mặc định cấp kênh khi có asset_path.
export interface OverlayEffectOverride {
  asset_path: string | null;
  opacity: number;
  // Tắt hẳn overlay cho project này (2026-09-02) — không dùng overlay nào cả, kể cả brand
  // đã cấu hình. Cùng khái niệm IntroAssetStatus.disabled.
  disabled: boolean;
}
// Ảnh nhân vật tham khảo RIÊNG của project — mới (2026-09-09, mục 127) — upload xong tự
// sinh `description` qua VisionProvider, nối vào MỌI prompt sinh ảnh của project (giữ
// nhân vật đồng nhất giữa các shot). KHÔNG có cấp kênh (khác Intro/BgMusic/Overlay) — đặc
// thù từng project/video. `caption_error` — lỗi sinh mô tả tự động (KHÔNG chặn upload,
// ảnh vẫn lưu được) — người dùng tự sửa `description` qua PATCH hoặc bấm sinh lại.
export interface CharacterReferenceStatus {
  image_path: string | null;
  description: string;
  caption_error: string | null;
}
// Tóm tắt 1 lượt "Xoá watermark toàn bộ slot" (2026-08-28) — banner hiện SAU khi bulk
// chạy xong, gộp thay vì rải thông báo riêng từng shot (dễ bỏ sót với nhiều shot).
export interface WatermarkScanSummary {
  scanned: number;
  cleaned: number;
  no_watermark: number;
  failed: number;
  finished_at: string;
}
// Video nền CHUNG cho toàn bộ block (2026-09-02) — KHÁC bg_music/overlay: KHÔNG có cấp
// kênh mặc định để kế thừa (thuần override project), KHÔNG có volume/opacity (chỉ hình).
// Nhiều video (mới 2026-09-02, mục 110) — asset_paths (list, thứ tự upload), nối thành 1
// "playlist" lúc ghép (xáo trộn 1 lần/lượt ghép nếu random_order, blend bằng `transition`
// giữa các video liên tiếp — cùng danh sách TRANSITIONS dùng cho shot-to-shot).
export interface BackgroundVideoOverride {
  asset_paths: string[];
  random_order: boolean;
  transition: string;
}
// Layer video ĐỊNH VỊ theo lưới 3x3 (VD voice wave, logo) — mới (2026-09-02, mục 112).
// `blend_mode` (mới, mục 113): "alpha" (mặc định) — nguồn CÓ SẴN kênh alpha (WebM VP9 /
// MOV ProRes4444 trong suốt), composite thẳng bằng filter overlay. "screen" — nguồn NỀN
// ĐEN ĐẶC (không alpha), screen-blend CỤC BỘ đúng vùng layer — KHÁC overlay hiệu ứng lớp
// phủ (screen-blend TOÀN khung hình). Nhiều layer cùng lúc — RenderState.layers là 1
// DANH SÁCH, mỗi layer có thể dùng blend_mode khác nhau.
export type LayerPosition = "top-left" | "top-center" | "top-right" | "middle-left" | "center" | "middle-right" | "bottom-left" | "bottom-center" | "bottom-right";
export type LayerBlendMode = "alpha" | "screen";
export interface VideoLayer {
  id: string;
  asset_path: string;
  position: LayerPosition;
  width_pct: number; // % chiều rộng khung hình xuất, mặc định 0.3
  opacity: number;
  blend_mode: LayerBlendMode;
}
// Layer ẢNH định vị — mới (2026-09-02, mục 115). Song song VideoLayer, chỉ khác: nguồn
// LUÔN ảnh tĩnh (PNG/JPEG/WEBP), và `position` có thêm "full" (phủ toàn khung hình, bỏ
// qua width_pct) — KHÔNG có ở VideoLayer.
export type ImageLayerPosition = LayerPosition | "full";
export interface ImageLayer {
  id: string;
  asset_path: string;
  position: ImageLayerPosition;
  width_pct: number; // bỏ qua khi position === "full"
  opacity: number;
  blend_mode: LayerBlendMode;
}
// Layer CAPTION (phụ đề cứng burn-in) — mới (2026-09-12), theo yêu cầu người dùng:
// "thêm caption vào video ở bước visual studio... chọn 9 vị trí, kích thước, độ mờ
// tương tự phần Layer video định vị". KHÁC VideoLayer/ImageLayer (list, upload file) —
// đây là 1 CẤU HÌNH DUY NHẤT/project, không có asset upload (nội dung lấy từ script).
export interface CaptionLayer {
  enabled: boolean;
  position: LayerPosition;
  size_pct: number; // cỡ chữ = % CHIỀU CAO khung hình xuất (khác width_pct — % chiều RỘNG — của VideoLayer/ImageLayer)
  opacity: number;
  // null = dùng ĐÚNG ngôn ngữ đang ghép video (export_lang) — khác đi thì dùng ngôn ngữ
  // người dùng tự chọn riêng cho caption, độc lập ngôn ngữ giọng đọc.
  lang: NarrationLanguage | null;
}
// Xuất short-video 9:16 từ 1 khoảng block — mới (2026-09-12), theo yêu cầu người dùng:
// repurpose 1 đoạn của project long-form thành YouTube Shorts/TikTok mà KHÔNG cần tạo 1
// project short-form riêng (khác hẳn `Project.format==="short"`/`parent_project_id`).
// Tối đa 3 cái/project (chặn 400 ở backend khi bấm xuất thêm — xem `render/short_export.py`).
export type ShortVideoExportStatus = "pending" | "generating_images" | "assembling" | "done" | "error";
export interface ShortVideoExport {
  id: string;
  start_block_id: string;
  end_block_id: string;
  regenerate_images: boolean;
  // Ngôn ngữ giọng đọc dùng để xuất — mới (2026-09-12). `null` chỉ gặp ở export CŨ tạo
  // trước tính năng chọn ngôn ngữ (fallback ngôn ngữ chính của kênh khi hiển thị).
  lang: NarrationLanguage | null;
  status: ShortVideoExportStatus;
  error: string | null;
  progress_current: number | null;
  progress_total: number | null;
  progress_label: string | null;
  video_path: string | null;
  created_at: string | null;
}
export interface RenderState {
  project_id: string;
  shots: ShotRenderStatus[];
  layers: VideoLayer[]; // mới (2026-09-02, mục 112)
  image_layers: ImageLayer[]; // mới (2026-09-02, mục 115)
  caption_layer: CaptionLayer | null; // mới (2026-09-12)
  narration_speed: number; // 1.0 = tốc độ gốc — mới (2026-09-02, mục 109), chỉnh ở Script Studio
  intro: IntroAssetStatus | null;
  character_reference: CharacterReferenceStatus | null;
  bg_music: BgMusicOverride | null;
  overlay: OverlayEffectOverride | null;
  background_video: BackgroundVideoOverride | null;
  assembly_status: AssemblyStatus;
  assembly_error: string | null;
  assembly_progress: AssemblyProgress | null;
  assembly_started_at: string | null;
  // Set lúc ghép THÀNH CÔNG lần gần nhất — so sánh với `visual_updated_at`/
  // `narration_updated_at` của từng shot để cảnh báo "đã sinh lại asset SAU lần ghép
  // này" (xem OutputCenter.tsx).
  assembly_completed_at: string | null;
  final_video_path: string | null;
  watermark_scan_summary: WatermarkScanSummary | null;
  short_exports: ShortVideoExport[];
}

// Thư viện Creative Asset — mới (2026-08-20) — nhạc nền/video/ảnh/giọng đọc dùng lại
// được ở nhiều nơi thay vì upload lại từ máy mỗi lần.
export type CreativeAssetKind = "music" | "video" | "image" | "voice";
export interface CreativeAsset {
  id: string;
  kind: CreativeAssetKind;
  name: string;
  created_at: string;
}

// Kho Tài Nguyên / Asset Vault (CHANGE_Semantic_BRoll_Asset_Vault.md) — kho tư liệu video
// TOÀN CỤC (2026-08-27), 1 video gốc gắn được NHIỀU kênh dạng tag (`channels`), khác
// CreativeAsset (dùng lại nguyên vẹn, không gắn kênh nào).
export type RawVideoStatus = "detecting" | "tagging" | "indexed" | "error";
export interface VaultChannelTag {
  id: string;
  name: string;
}
export interface RawVideo {
  id: string;
  channels: VaultChannelTag[];
  source_url: string | null;
  original_filename: string | null;
  import_note: string;
  status: RawVideoStatus;
  error_message: string | null;
  progress_current: number | null;
  progress_total: number | null;
  progress_label: string | null;
  created_at: string;
}
export type ClipRightsStatus = "unverified" | "licensed_verified" | "public_domain";
export interface ProcessedClip {
  clip_id: string;
  channels: VaultChannelTag[];
  raw_video_id: string;
  raw_video_name: string;
  raw_video_status: RawVideoStatus | null;
  duration_sec: number;
  resolution: string;
  caption: string;
  tags: string[];
  mood_tone: string;
  usage_count: number;
  last_used_at: string | null;
  active: boolean;
  rights_status: ClipRightsStatus;
  rights_note: string;
  created_at: string;
  caption_error: string | null;
  // Lưu ảnh/video từ Visual Studio vào Kho Tài Nguyên — mới (2026-09-11). "video" cho
  // MỌI clip cắt cảnh cũ + mới; "image" cho ảnh lưu từ Visual Studio.
  media_kind: "video" | "image";
  from_visual_studio: boolean;
}
export interface VaultCandidate {
  clip_id: string;
  caption: string;
  duration_sec: number;
  match_score: number | null;
  rights_status: ClipRightsStatus;
  resolution: string;
  tags: string[];
  mood_tone: string;
  usage_count: number;
  from_visual_studio: boolean;
}
export interface VaultCandidatesResult {
  used_semantic: boolean;
  candidates: VaultCandidate[];
}
// Lưu shot vào Kho Tài Nguyên (2026-09-11) — xem api.saveShotsToVault.
export interface SaveShotsToVaultResult {
  saved: string[];
  updated: string[];
  skipped: { shot_id: string; reason: string }[];
}
// Tự động điền block còn thiếu từ Kho Tài Nguyên (2026-09-11).
export interface VaultAutoFillSuggestion {
  shot_id: string;
  visual_fx: string;
  clip_id: string;
  caption: string;
  media_kind: "video" | "image";
  resolution: string;
  match_score: number | null;
}
export interface VaultAutoFillSuggestionsResult {
  suggestions: VaultAutoFillSuggestion[];
  scanned_count: number;
  matched_count: number;
}
// Tiến trình quét "Tự động điền từ Kho tài nguyên" — **mới (2026-09-13)** — job nền poll
// được, xem `api.startVaultAutoFillScan`/`getVaultAutoFillScanStatus`.
export interface VaultAutoFillScanStatus {
  status: "idle" | "running" | "done" | "error";
  current?: number;
  total?: number;
  current_label?: string | null;
  elapsed_sec?: number;
  error?: string | null;
  result?: VaultAutoFillSuggestionsResult | null;
}
export interface VaultAutoFillApplyResult {
  applied: string[];
  skipped: { shot_id: string; reason: string }[];
}
// Upload cả folder ảnh/video khớp theo mã block — mới (2026-09-16), theo yêu cầu người
// dùng: tên file (bỏ đuôi) trùng shot_id/mã block, xem `render.py::upload_shot_visual_batch`.
export interface ShotUploadBatchResult {
  matched: { shot_id: string; filename: string }[];
  unmatched: { filename: string; reason: string }[];
  state: RenderState;
}
export type ExportResolution = "720p" | "1080p" | "4k";
export type ExportCodec = "h264" | "h265" | "vp9";
export type ExportQuality = "low" | "medium" | "high";
export interface AssembleConfig {
  resolution: ExportResolution;
  codec: ExportCodec;
  quality: ExportQuality;
  use_gpu: boolean;
  // Ngôn ngữ xuất video (2026-09-11) — null/undefined → ngôn ngữ chính của kênh
  // (BrandProfile.primary_language). Thời lượng từng cảnh ăn theo giọng đọc ngôn ngữ
  // này, xem app/render/assembly.py::assemble_video.
  lang?: NarrationLanguage | null;
}
export interface GpuEncodeStatus {
  available: boolean;
  message: string;
}
