// Client gọi REST tới FastAPI backend — specs/03_api.md.
import type {
  AssembleConfig,
  AuditLogEntry,
  BrandProfile,
  Brief,
  BudgetOut,
  ChannelSummary,
  CreativeAsset,
  CreativeAssetKind,
  GpuEncodeStatus,
  GpuStatus,
  ImportPreview,
  ProductionPack,
  ProjectSummary,
  PromptTemplateOut,
  ProviderOut,
  RenderState,
  RetentionOut,
  TrashOut,
  VoiceSampleUploadResult,
} from "./types";

declare global {
  interface Window {
    STUDIOFLOW_API_BASE?: string;
  }
}

const BASE = (typeof window !== "undefined" && window.STUDIOFLOW_API_BASE) || "http://127.0.0.1:8756";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = data?.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : msg;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Tải file về máy qua fetch → blob → `<a download>` tạm (blob: URL luôn same-origin,
 * KHÔNG dùng thẳng `<a href={url} download>` trỏ URL backend — backend chạy ở origin
 * KHÁC frontend (cổng riêng do Electron cấp phát, xem `electron/src/main.ts`), Chromium
 * ÂM THẦM BỎ QUA thuộc tính `download` với URL cross-origin (giới hạn bảo mật chuẩn),
 * rơi về hành vi ĐIỀU HƯỚNG thẳng cả cửa sổ sang URL ảnh/file — cửa sổ Electron kiểu
 * kiosk này không có nút Back/thanh địa chỉ nên coi như "kẹt", không tắt được (bug thật
 * người dùng báo ở nút "Tải ảnh" Thumbnail, Pack Review). */
async function downloadFile(path: string, fallbackFilename: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    // Đọc `detail` từ JSON body (giống req()) thay vì chỉ statusText chung chung — cần
    // cho lỗi có thông điệp cụ thể hữu ích (VD "Tải giọng đọc toàn bộ script" báo rõ
    // còn block nào chưa sinh xong, không chỉ "Bad Request").
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = data?.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : msg;
    } catch {
      /* ignore — không phải JSON (VD lỗi mạng), giữ statusText */
    }
    throw new ApiError(res.status, msg);
  }
  // Ưu tiên filename server trả qua Content-Disposition (VD render/download — đuôi file
  // đổi theo codec đã chọn, mp4/webm) — fallback về tên cố định nếu header không có.
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"; ]+)"?/);
  const filename = match ? match[1] : fallbackFilename;
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

const get = <T>(path: string) => req<T>(path);
const post = <T>(path: string, body?: unknown) => req<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
const put = <T>(path: string, body: unknown) => req<T>(path, { method: "PUT", body: JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) => req<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(path: string) => req<T>(path, { method: "DELETE" });

export const api = {
  base: BASE,
  bootstrap: () => get<{ has_llm_provider: boolean; channel_count: number; app_name: string }>("/bootstrap"),

  // Channels
  listChannels: () => get<ChannelSummary[]>("/channels"),
  createChannel: (body: { name: string; niche: string }) => post<ChannelSummary>("/channels", body),
  getChannel: (id: string) => get<ChannelSummary & { brand_profile: BrandProfile }>(`/channels/${id}`),
  patchChannel: (id: string, body: Partial<{ name: string; niche: string; archived: boolean }>) => patch<ChannelSummary>(`/channels/${id}`, body),
  restoreChannel: (id: string) => post<ChannelSummary>(`/channels/${id}/restore`),
  deleteChannelPermanent: (id: string) => del<{ ok: boolean }>(`/channels/${id}/permanent`),
  getBrandProfile: (id: string) => get<BrandProfile>(`/channels/${id}/brandprofile`),
  putBrandProfile: (id: string, body: BrandProfile) => put<BrandProfile>(`/channels/${id}/brandprofile`, body),
  cloneBrandProfile: (id: string, src: string) => post<BrandProfile>(`/channels/${id}/brandprofile/clone-from/${src}`),
  uploadBrandLogo: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<BrandProfile>(`/channels/${id}/brandprofile/logo/upload`, { method: "POST", body: form });
  },
  brandLogoUrl: (id: string) => `${BASE}/channels/${id}/brandprofile/logo`,
  uploadVoiceSample: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<VoiceSampleUploadResult>(`/channels/${id}/brandprofile/voice-sample/upload`, { method: "POST", body: form });
  },
  voiceSampleUrl: (id: string) => `${BASE}/channels/${id}/brandprofile/voice-sample`,
  uploadBrandIntro: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<BrandProfile>(`/channels/${id}/brandprofile/intro/upload`, { method: "POST", body: form });
  },
  brandIntroUrl: (id: string) => `${BASE}/channels/${id}/brandprofile/intro`,
  uploadBrandBgMusic: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<BrandProfile>(`/channels/${id}/brandprofile/bg-music/upload`, { method: "POST", body: form });
  },
  brandBgMusicUrl: (id: string) => `${BASE}/channels/${id}/brandprofile/bg-music`,
  uploadBrandOverlay: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<BrandProfile>(`/channels/${id}/brandprofile/overlay/upload`, { method: "POST", body: form });
  },
  brandOverlayUrl: (id: string) => `${BASE}/channels/${id}/brandprofile/overlay`,

  // Projects
  listProjects: (channelId: string) => get<ProjectSummary[]>(`/channels/${channelId}/projects`),
  createProject: (channelId: string, title: string, parentProjectId?: string) =>
    post<ProjectSummary>(`/channels/${channelId}/projects`, { title, parent_project_id: parentProjectId }),
  getProject: (id: string) => get<ProjectSummary>(`/projects/${id}`),
  patchProject: (id: string, body: Partial<{ title: string; status: string; step: number; return_note: string }>) =>
    patch<ProjectSummary>(`/projects/${id}`, body),
  archiveProject: (id: string) => del<{ ok: boolean }>(`/projects/${id}`),
  restoreProject: (id: string) => post<ProjectSummary>(`/projects/${id}/restore`),
  deleteProjectPermanent: (id: string) => del<{ ok: boolean }>(`/projects/${id}/permanent`),

  // Thùng rác — gộp kênh + project đã xoá (archived) để khôi phục/xoá vĩnh viễn
  getTrash: () => get<TrashOut>("/trash"),

  // Brief
  getBrief: (id: string) => get<{ brief: Brief; missing_groups: string[] }>(`/projects/${id}/brief`),
  putBrief: (id: string, body: Brief) => put<{ brief: Brief; missing_groups: string[] }>(`/projects/${id}/brief`, body),
  addBriefYoutubeSource: (id: string, youtube_url: string) => {
    const form = new FormData();
    form.append("youtube_url", youtube_url);
    return req<Brief>(`/projects/${id}/brief/sources`, { method: "POST", body: form });
  },
  addBriefFileSource: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<Brief>(`/projects/${id}/brief/sources`, { method: "POST", body: form });
  },
  removeBriefSource: (id: string, sourceId: string) => del<Brief>(`/projects/${id}/brief/sources/${sourceId}`),

  // Pipeline
  editScriptBlockAudio: (id: string, index: number, audio: string) => patch<ProductionPack>(`/projects/${id}/script/body/${index}/audio`, { audio }),
  downloadScriptImportTemplate: (id: string) => downloadFile(`/projects/${id}/script/import/template`, "mau-nhap-kich-ban.xlsx"),
  downloadTranscriptSrt: (id: string) => downloadFile(`/projects/${id}/script/transcript-srt`, "transcript.srt"),
  ensureShotsForNarration: (id: string) => post<ProductionPack>(`/projects/${id}/visual/ensure-shots-for-narration`),
  importScriptParse: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<ImportPreview>(`/projects/${id}/script/import/parse`, { method: "POST", body: form });
  },
  importScriptConfirm: (id: string, beats: unknown[], full_text: string) =>
    post<ProductionPack>(`/projects/${id}/script/import/confirm`, { beats, full_text }),
  generateVisualShots: (id: string) => post<ProductionPack>(`/projects/${id}/visual/generate`),
  patchShot: (id: string, shotId: string, body: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string; transition_to_next: string; camera_motion: string }>) =>
    patch<ProductionPack>(`/projects/${id}/visual/shots/${shotId}`, body),
  regenerateShotVisual: (id: string, shotId: string) => post<ProductionPack>(`/projects/${id}/visual/shots/${shotId}/regenerate-visual`),
  regenerateShotAudio: (id: string, shotId: string) => post<ProductionPack>(`/projects/${id}/visual/shots/${shotId}/regenerate-audio`),
  generateAllVisual: (id: string) => post<ProductionPack>(`/projects/${id}/visual/generate-all-visual`),
  generateAllTts: (id: string) => post<ProductionPack>(`/projects/${id}/visual/generate-all-tts`),
  enterOutput: (id: string) => post<{ step: number }>(`/projects/${id}/output/enter`),

  // Pack
  getPack: (id: string) => get<ProductionPack>(`/projects/${id}/pack`),
  patchPack: (id: string, patchBody: Partial<ProductionPack>) => patch<ProductionPack>(`/projects/${id}/pack`, patchBody),
  generateThumbnail: (id: string) => post<ProductionPack>(`/projects/${id}/pack/thumbnail/generate`),
  uploadThumbnail: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<ProductionPack>(`/projects/${id}/pack/thumbnail/upload`, { method: "POST", body: form });
  },
  approveThumbnail: (id: string, approved = true) => post<ProductionPack>(`/projects/${id}/pack/thumbnail/approve`, { approved }),
  thumbnailUrl: (id: string) => `${BASE}/projects/${id}/pack/thumbnail`,
  downloadThumbnail: (id: string) => downloadFile(`/projects/${id}/pack/thumbnail`, "thumbnail.png"),

  // Guardrail + retention
  guardrailCheck: (id: string) => post<{ hook_strength: number | null; max_anchor_gap_sec: number | null; warnings: unknown[] }>(`/projects/${id}/guardrail/check`),
  getRetention: (id: string) => get<RetentionOut>(`/projects/${id}/retention`),
  putRetention: (id: string, body: Record<string, number | string | null>) => put<RetentionOut>(`/projects/${id}/retention`, body),

  // Export
  exportPack: (id: string, format: "markdown" | "pdf" | "json") => post<{ path: string; filename: string }>(`/projects/${id}/export`, { format }),
  downloadUrl: (id: string, filename: string) => `${BASE}/projects/${id}/exports/${filename}`,
  downloadExportFile: (id: string, filename: string) => downloadFile(`/projects/${id}/exports/${filename}`, filename),

  // Render Studio (M2 Production Layer — sinh asset thật + ghép MP4)
  startRender: (id: string, kind: "both" | "visual" | "narration" = "both", force = false) =>
    post<RenderState>(`/projects/${id}/render/start?kind=${kind}${force ? "&force=true" : ""}`),
  cancelRender: (id: string) => post<RenderState>(`/projects/${id}/render/cancel`),
  getRenderStatus: (id: string) => get<RenderState>(`/projects/${id}/render/status`),
  getGpuStatus: (id: string) => get<GpuStatus>(`/projects/${id}/render/gpu-status`),
  getGpuEncodeStatus: () => get<GpuEncodeStatus>(`/render/gpu-encode-status`),
  approveShotAsset: (id: string, shotId: string, approved = true) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/approve`, { approved }),
  approveAllShots: (id: string) => post<RenderState>(`/projects/${id}/render/approve-all`),
  regenerateShotVisualAsset: (id: string, shotId: string) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/regenerate-visual`),
  uploadShotVisual: (id: string, shotId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/shots/${shotId}/upload-visual`, { method: "POST", body: form });
  },
  regenerateShotNarration: (id: string, shotId: string) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/regenerate-narration`),
  assembleVideo: (id: string, config?: AssembleConfig) => post<RenderState>(`/projects/${id}/render/assemble`, config),
  renderShotAssetUrl: (id: string, shotId: string, kind: "visual" | "narration") => `${BASE}/projects/${id}/render/shots/${shotId}/asset/${kind}`,
  renderDownloadUrl: (id: string) => `${BASE}/projects/${id}/render/download`,
  downloadRenderFile: (id: string) => downloadFile(`/projects/${id}/render/download`, "final.mp4"),
  downloadNarrationFull: (id: string) => downloadFile(`/projects/${id}/render/narration-download`, "narration_full.mp3"),
  uploadIntroVisual: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/intro/upload-visual`, { method: "POST", body: form });
  },
  uploadIntroAudio: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/intro/upload-audio`, { method: "POST", body: form });
  },
  deleteIntro: (id: string) => del<RenderState>(`/projects/${id}/render/intro`),
  enableIntroInherit: (id: string) => patch<RenderState>(`/projects/${id}/render/intro/inherit`, {}),
  patchIntroTransition: (id: string, transition_to_next: string) => patch<RenderState>(`/projects/${id}/render/intro/transition`, { transition_to_next }),
  introAssetUrl: (id: string, kind: "visual" | "audio") => `${BASE}/projects/${id}/render/intro/asset/${kind}`,
  uploadProjectBgMusic: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/bg-music/upload`, { method: "POST", body: form });
  },
  patchProjectBgMusicVolume: (id: string, volume: number) =>
    patch<RenderState>(`/projects/${id}/render/bg-music`, { volume }),
  deleteProjectBgMusic: (id: string) => del<RenderState>(`/projects/${id}/render/bg-music`),
  projectBgMusicUrl: (id: string) => `${BASE}/projects/${id}/render/bg-music/asset`,
  uploadProjectOverlay: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/overlay/upload`, { method: "POST", body: form });
  },
  patchProjectOverlayOpacity: (id: string, opacity: number) =>
    patch<RenderState>(`/projects/${id}/render/overlay`, { opacity }),
  deleteProjectOverlay: (id: string) => del<RenderState>(`/projects/${id}/render/overlay`),
  projectOverlayUrl: (id: string) => `${BASE}/projects/${id}/render/overlay/asset`,

  // Thư viện Creative Asset (nhạc nền/video/ảnh/giọng đọc dùng lại nhiều nơi)
  listLibraryAssets: (kind?: CreativeAssetKind) => get<CreativeAsset[]>(`/library/assets${kind ? `?kind=${kind}` : ""}`),
  uploadLibraryAsset: (kind: CreativeAssetKind, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<CreativeAsset>(`/library/assets/upload?kind=${kind}`, { method: "POST", body: form });
  },
  renameLibraryAsset: (assetId: string, name: string) => patch<CreativeAsset>(`/library/assets/${assetId}`, { name }),
  deleteLibraryAsset: (assetId: string) => del<{ ok: boolean }>(`/library/assets/${assetId}`),
  libraryAssetUrl: (assetId: string) => `${BASE}/library/assets/${assetId}/file`,

  // Providers
  listProviders: () => get<ProviderOut[]>("/providers"),
  createProvider: (body: {
    task: string;
    provider_name: string;
    display_name: string;
    connection_type: string;
    api_key?: string;
    endpoint_url?: string;
    model_name?: string;
  }) => post<ProviderOut>("/providers", body),
  patchProvider: (id: number, body: Partial<{ display_name: string; model_name: string; endpoint_url: string; api_key: string; is_default: boolean; is_fallback: boolean; enabled: boolean }>) =>
    patch<ProviderOut>(`/providers/${id}`, body),
  deleteProvider: (id: number) => del<{ ok: boolean }>(`/providers/${id}`),
  testProvider: (id: number) => post<{ ok: boolean; message: string }>(`/providers/${id}/test`),
  listLocalSdxlModels: (kind: "checkpoints" | "loras", baseUrl?: string) => {
    const params = new URLSearchParams({ kind });
    if (baseUrl) params.set("base_url", baseUrl);
    return get<{ models: string[] }>(`/providers/local-sdxl/models?${params.toString()}`);
  },

  // Settings
  getSettings: () => get<{ general: Record<string, unknown>; ai_params: Record<string, unknown>; app_branding: Record<string, unknown> }>("/settings"),
  putSettings: (body: Record<string, unknown>) => put("/settings", body),

  // Prompt templates
  listPromptTemplates: () => get<PromptTemplateOut[]>("/prompt-templates"),
  createPromptTemplate: (body: { name: string; task: string; body: string }) => post<PromptTemplateOut>("/prompt-templates", body),
  patchPromptTemplate: (
    id: string,
    body: Partial<{ name: string; task: string; active_version: string; new_version_body: string; new_version_note: string }>
  ) => patch<PromptTemplateOut>(`/prompt-templates/${id}`, body),
  deletePromptTemplate: (id: string) => del<{ ok: boolean }>(`/prompt-templates/${id}`),

  // Audit log
  getAuditLog: (type?: string) => get<AuditLogEntry[]>(`/audit-log${type ? `?type=${type}` : ""}`),

  // Budget
  getBudget: () => get<BudgetOut[]>("/budget"),
  patchBudget: (channelId: string, body: Partial<{ soft_limit: number; threshold_pct: number }>) => patch<BudgetOut>(`/budget/${channelId}`, body),
  getBudgetDetail: (channelId: string) =>
    get<{ channel_name: string; rows: { project: string; provider: string; request_count: number; cost_total: number; requests: { time: string; model: string; tokens_label: string; cost: number }[] }[] }>(
      `/budget/${channelId}/detail`
    ),
};

export { ApiError };
