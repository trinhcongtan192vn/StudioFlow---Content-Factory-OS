// Kiểu dữ liệu khớp backend/app/schemas — xem specs/04_data_schemas.md (đã cập nhật).

export interface ChannelSummary {
  id: string;
  name: string;
  niche: string;
  letter: string;
  archived: boolean;
  brandprofile_version: number;
  running_count: number;
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
export interface BrandProfile {
  channel_id: string;
  niche: string;
  brand_voice: BrandVoice;
  content_pillars: ContentPillar[];
  forbidden: string[];
  visual_style_prompt: string;
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
  // Style LoRA khoá "chữ ký hình ảnh" cho ảnh local SDXL — mới (2026-08-22). Tên file
  // THẬT trong thư mục ComfyUI/models/loras/ (không phải đường dẫn tuyệt đối) — rỗng =
  // không dùng LoRA. Chỉ áp dụng cho provider local_sdxl, provider khác bỏ qua.
  style_lora_path: string;
  style_lora_strength: number;
  // Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) MẶC ĐỊNH của kênh — mới (2026-08-22) —
  // blend đè liên tục lên toàn bộ video (kể cả intro) khi ghép MP4, trừ khi project tự
  // override riêng (RenderState.overlay). LUÔN video (mp4/webm/mov).
  overlay_effect_path: string;
  overlay_effect_opacity: number;
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
}
export interface RetentionOut {
  entry: RetentionEntry | null;
  target_hook_strength: number | null;
  guardrail_hook_strength: number | null;
  diff_vs_benchmark: number | null;
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
  approved: boolean;
  narration_status: AssetStatus;
  narration_asset_path: string | null;
  narration_provider: string | null;
  narration_error: string | null;
  narration_duration_sec: number | null;
  narration_started_at: string | null;
}
export interface GpuStatus {
  reachable: boolean;
  queue_running: number;
  queue_pending: number;
  gpu_name: string | null;
}
export interface AssemblyProgress {
  stage: "segments" | "concat";
  current: number;
  total: number;
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
}
export interface RenderState {
  project_id: string;
  shots: ShotRenderStatus[];
  intro: IntroAssetStatus | null;
  bg_music: BgMusicOverride | null;
  overlay: OverlayEffectOverride | null;
  assembly_status: AssemblyStatus;
  assembly_error: string | null;
  assembly_progress: AssemblyProgress | null;
  assembly_started_at: string | null;
  final_video_path: string | null;
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
export type ExportResolution = "720p" | "1080p" | "4k";
export type ExportCodec = "h264" | "h265" | "vp9";
export type ExportQuality = "low" | "medium" | "high";
export interface AssembleConfig {
  resolution: ExportResolution;
  codec: ExportCodec;
  quality: ExportQuality;
  use_gpu: boolean;
}
export interface GpuEncodeStatus {
  available: boolean;
  message: string;
}
