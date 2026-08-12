// Kiểu dữ liệu khớp backend/app/schemas — xem specs/04_data_schemas.md (đã cập nhật).

export interface ChannelSummary {
  id: string;
  name: string;
  niche: string;
  letter: string;
  archived: boolean;
  brandprofile_version: number;
  running_count: number;
  review_count: number;
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
  version: number;
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

export interface Outline {
  id: string;
  title: string;
  points: string[];
  selected: boolean;
}
export interface HookVariant {
  id: string;
  psychological_type: string;
  spoken: string;
  visual: string;
  selected: boolean;
}
export interface ResearchBlock {
  synthesis: string;
  outlines: Outline[];
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
export interface TitleConcept {
  text: string;
  seo_score_hint: string | null;
  angle: string | null;
}
export interface YoutubeChapter {
  ts_sec: number;
  label: string;
}
export interface YoutubeMeta {
  description: string;
  hashtags: string[];
  chapters: YoutubeChapter[];
  thumbnail_description: string;
  thumbnail_status: "pending" | "generating" | "ready" | "error";
  thumbnail_asset_path: string | null;
  thumbnail_provider: string | null;
  thumbnail_error: string | null;
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
  research: ResearchBlock | null;
  hooks: HookVariant[];
  script: Script | null;
  shots: Shot[];
  titles: TitleConcept[];
  thumbnail_concepts: { metaphor?: string; text_overlay?: string; layout?: string; prompt: string }[];
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
  approved: boolean;
  narration_status: AssetStatus;
  narration_asset_path: string | null;
  narration_provider: string | null;
  narration_error: string | null;
  narration_duration_sec: number | null;
}
export interface RenderState {
  project_id: string;
  shots: ShotRenderStatus[];
  assembly_status: AssemblyStatus;
  assembly_error: string | null;
  final_video_path: string | null;
}
