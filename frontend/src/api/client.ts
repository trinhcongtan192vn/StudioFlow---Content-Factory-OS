// Client gọi REST tới FastAPI backend — specs/03_api.md.
import type {
  AuditLogEntry,
  BrandProfile,
  Brief,
  BudgetOut,
  ChannelSummary,
  ImportPreview,
  ProductionPack,
  ProjectSummary,
  PromptTemplateOut,
  ProviderOut,
  RenderState,
  RetentionOut,
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
  getBrandProfile: (id: string) => get<BrandProfile>(`/channels/${id}/brandprofile`),
  putBrandProfile: (id: string, body: BrandProfile) => put<BrandProfile>(`/channels/${id}/brandprofile`, body),
  cloneBrandProfile: (id: string, src: string) => post<BrandProfile>(`/channels/${id}/brandprofile/clone-from/${src}`),

  // Projects
  listProjects: (channelId: string) => get<ProjectSummary[]>(`/channels/${channelId}/projects`),
  createProject: (channelId: string, title: string) => post<ProjectSummary>(`/channels/${channelId}/projects`, { title }),
  getProject: (id: string) => get<ProjectSummary>(`/projects/${id}`),
  patchProject: (id: string, body: Partial<{ title: string; status: string; step: number; return_note: string }>) =>
    patch<ProjectSummary>(`/projects/${id}`, body),
  archiveProject: (id: string) => del<{ ok: boolean }>(`/projects/${id}`),

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
  runResearch: (id: string) => post<ProductionPack>(`/projects/${id}/research`),
  approveGate1: (id: string, body: { chosen_outline_id: string; chosen_hook_id: string; edited_hook_text?: string }) =>
    post<ProductionPack>(`/projects/${id}/gate1`, body),
  regenerateScript: (id: string, feedback: string) => post<ProductionPack>(`/projects/${id}/script/regenerate`, { feedback }),
  editScriptText: (id: string, full_text: string) => patch<ProductionPack>(`/projects/${id}/script/text`, { full_text }),
  approveScript: (id: string) => post<ProductionPack>(`/projects/${id}/script/approve`),
  importScriptParse: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<ImportPreview>(`/projects/${id}/script/import/parse`, { method: "POST", body: form });
  },
  importScriptConfirm: (id: string, beats: unknown[], full_text: string) =>
    post<ProductionPack>(`/projects/${id}/script/import/confirm`, { beats, full_text }),
  generateVisualShots: (id: string) => post<ProductionPack>(`/projects/${id}/visual/generate`),
  patchShot: (id: string, shotId: string, body: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string }>) =>
    patch<ProductionPack>(`/projects/${id}/visual/shots/${shotId}`, body),
  regenerateShotVisual: (id: string, shotId: string) => post<ProductionPack>(`/projects/${id}/visual/shots/${shotId}/regenerate-visual`),
  regenerateShotAudio: (id: string, shotId: string) => post<ProductionPack>(`/projects/${id}/visual/shots/${shotId}/regenerate-audio`),
  generateAllVisual: (id: string) => post<ProductionPack>(`/projects/${id}/visual/generate-all-visual`),
  generateAllTts: (id: string) => post<ProductionPack>(`/projects/${id}/visual/generate-all-tts`),
  buildPack: (id: string) => post<ProductionPack>(`/projects/${id}/pack/build`),
  gate2: (id: string, body: { action: "approve" | "return"; note?: string }) =>
    post<{ project: { step: number; status: string; return_note: string }; pack: ProductionPack }>(`/projects/${id}/gate2`, body),
  enterOutput: (id: string) => post<{ step: number }>(`/projects/${id}/output/enter`),

  // Pack
  getPack: (id: string) => get<ProductionPack>(`/projects/${id}/pack`),
  patchPack: (id: string, patchBody: Partial<ProductionPack>) => patch<ProductionPack>(`/projects/${id}/pack`, patchBody),

  // Guardrail + retention
  guardrailCheck: (id: string) => post<{ hook_strength: number | null; max_anchor_gap_sec: number | null; warnings: unknown[] }>(`/projects/${id}/guardrail/check`),
  getRetention: (id: string) => get<RetentionOut>(`/projects/${id}/retention`),
  putRetention: (id: string, body: Record<string, number | string | null>) => put<RetentionOut>(`/projects/${id}/retention`, body),

  // Export
  exportPack: (id: string, format: "markdown" | "pdf" | "json") => post<{ path: string; filename: string }>(`/projects/${id}/export`, { format }),
  downloadUrl: (id: string, filename: string) => `${BASE}/projects/${id}/exports/${filename}`,

  // Render Studio (M2 Production Layer — sinh asset thật + ghép MP4)
  startRender: (id: string) => post<RenderState>(`/projects/${id}/render/start`),
  getRenderStatus: (id: string) => get<RenderState>(`/projects/${id}/render/status`),
  approveShotAsset: (id: string, shotId: string, approved = true) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/approve`, { approved }),
  regenerateShotVisualAsset: (id: string, shotId: string) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/regenerate-visual`),
  regenerateShotNarration: (id: string, shotId: string) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/regenerate-narration`),
  assembleVideo: (id: string) => post<RenderState>(`/projects/${id}/render/assemble`),
  renderShotAssetUrl: (id: string, shotId: string, kind: "visual" | "narration") => `${BASE}/projects/${id}/render/shots/${shotId}/asset/${kind}`,
  renderDownloadUrl: (id: string) => `${BASE}/projects/${id}/render/download`,

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
