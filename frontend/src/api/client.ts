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
  ImageLayerPosition,
  ImportPreview,
  LayerBlendMode,
  LayerPosition,
  LocalServicesResponse,
  NarrationLanguage,
  ClipRightsStatus,
  ProcessedClip,
  ProductionPack,
  ProjectSummary,
  PromptTemplateOut,
  ProviderOut,
  RawVideo,
  RenderState,
  RetentionOut,
  SaveShotsToVaultResult,
  TrashOut,
  ShotUploadBatchResult,
  VaultAutoFillApplyResult,
  VaultAutoFillScanStatus,
  VaultCandidatesResult,
  VoiceSampleUploadResult,
  YoutubeChannelMetricsOut,
  YoutubeChannelOAuthStatus,
  YoutubeRetentionChapter,
  YoutubeSettingsStatus,
  YoutubeVideoAvailable,
} from "./types";

declare global {
  interface Window {
    STUDIOFLOW_API_BASE?: string;
    // "Xuất Pack" (2026-08-26) — cầu chọn thư mục native, CHỈ tồn tại khi chạy trong
    // Electron (xem electron/src/preload.ts). Chạy dev server thuần trình duyệt (`npm
    // run dev:frontend`) sẽ KHÔNG có global này — UI tự fallback về ô nhập đường dẫn
    // tay, xem OutputCenter.tsx.
    studioflowNative?: { chooseFolder: () => Promise<string | null>; openFolder: (folderPath: string) => Promise<void>; openExternal: (url: string) => Promise<void> };
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
  // "Local Services & GPU Monitor" — cuối trang Dashboard (2026-08-27).
  getLocalServices: () => get<LocalServicesResponse>("/system/local-services"),
  startLocalService: (name: string) => post<{ ok: boolean; message: string }>(`/system/local-services/${name}/start`, {}),
  stopLocalService: (name: string) => post<{ ok: boolean; message: string }>(`/system/local-services/${name}/stop`, {}),

  // Channels
  listChannels: () => get<ChannelSummary[]>("/channels"),
  createChannel: (body: { name: string; niche: string }) => post<ChannelSummary>("/channels", body),
  getChannel: (id: string) => get<ChannelSummary & { brand_profile: BrandProfile }>(`/channels/${id}`),
  patchChannel: (id: string, body: Partial<{ name: string; niche: string; archived: boolean }>) => patch<ChannelSummary>(`/channels/${id}`, body),
  // Kéo thả sắp xếp Sidebar — mới (2026-09-19).
  reorderChannels: (channelIds: string[]) => patch<{ ok: boolean }>("/channels/reorder", { channel_ids: channelIds }),
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
  // Giọng đọc đa ngôn ngữ (mới 2026-09-04) — mẫu giọng clone RIÊNG cho từng ngôn ngữ
  // (khác voice-sample đơn ở trên, dùng cho ngôn ngữ CHÍNH).
  uploadVoiceSampleLang: (id: string, lang: NarrationLanguage, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<VoiceSampleUploadResult>(`/channels/${id}/brandprofile/voice-sample/upload/${lang}`, { method: "POST", body: form });
  },
  voiceSampleLangUrl: (id: string, lang: NarrationLanguage) => `${BASE}/channels/${id}/brandprofile/voice-sample/${lang}`,
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
  // Kéo thả sắp xếp Sidebar — mới (2026-09-19). Dùng CHUNG cho cả project long-form lẫn
  // short-form con của 1 project — truyền ĐÚNG danh sách ID của 1 nhóm anh em.
  reorderProjects: (channelId: string, projectIds: string[]) => patch<{ ok: boolean }>(`/channels/${channelId}/projects/reorder`, { project_ids: projectIds }),
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
  // Giọng đọc đa ngôn ngữ (mới 2026-09-04) — sửa tay bản dịch VO của 1 block/1 ngôn ngữ.
  editScriptBlockTranslation: (id: string, index: number, lang: NarrationLanguage, text: string) =>
    patch<ProductionPack>(`/projects/${id}/script/body/${index}/translation/${lang}`, { text }),
  downloadScriptImportTemplate: (id: string, multilang = false) =>
    downloadFile(`/projects/${id}/script/import/template${multilang ? "?multilang=true" : ""}`, multilang ? "mau-nhap-kich-ban-da-ngon-ngu.xlsx" : "mau-nhap-kich-ban.xlsx"),
  downloadTranscriptSrt: (id: string) => downloadFile(`/projects/${id}/script/transcript-srt`, "transcript.srt"),
  downloadTranscriptSrtLang: (id: string, lang: NarrationLanguage) => downloadFile(`/projects/${id}/script/transcript-srt/${lang}`, `transcript_${lang}.srt`),
  // Kịch bản .txt thuần, không timestamp — mới (2026-09-12).
  downloadTranscriptTxt: (id: string) => downloadFile(`/projects/${id}/script/transcript-txt`, "script.txt"),
  downloadTranscriptTxtLang: (id: string, lang: NarrationLanguage) => downloadFile(`/projects/${id}/script/transcript-txt/${lang}`, `script_${lang}.txt`),
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
  // Bulk edit transition_to_next/camera_motion cho nhiều shot cùng lúc — mới (2026-09-10).
  patchShotsBulk: (id: string, shotIds: string[], body: Partial<{ transition_to_next: string; camera_motion: string }>) =>
    patch<ProductionPack>(`/projects/${id}/visual/shots/bulk`, { shot_ids: shotIds, ...body }),
  // Lưu ảnh/video đã sinh của 1-nhiều shot vào Kho Tài Nguyên để tái sử dụng — mới (2026-09-11).
  saveShotsToVault: (id: string, shotIds: string[]) => post<SaveShotsToVaultResult>(`/projects/${id}/visual/shots/save-to-vault`, { shot_ids: shotIds }),
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

  // Chỉ số YouTube (Data API v3 + Analytics API v2) — mới (2026-09-12), theo yêu cầu
  // người dùng: kéo dữ liệu thật từ YouTube. Xem `backend/app/routers/youtube_analytics.py`.
  // OAuth giờ RIÊNG theo từng kênh (mục 154, 2026-09-19) — xem
  // `getYoutubeChannelAuthorizeUrl`/`getYoutubeChannelOAuthStatus` bên dưới.
  saveYoutubeOAuthClient: (client_id: string, client_secret: string) => post<{ ok: boolean }>("/settings/youtube/oauth-client", { client_id, client_secret }),
  getYoutubeSettingsStatus: () => get<YoutubeSettingsStatus>("/settings/youtube/status"),
  getYoutubeChannelAuthorizeUrl: (channelId: string, redirect_uri: string) => get<{ url: string }>(`/channels/${channelId}/youtube/authorize-url?redirect_uri=${encodeURIComponent(redirect_uri)}`),
  getYoutubeChannelOAuthStatus: (channelId: string) => get<YoutubeChannelOAuthStatus>(`/channels/${channelId}/youtube/oauth-status`),
  // `${BASE}/oauth/callback` — cổng backend đang chạy, ĐÚNG cổng nhận được redirect từ
  // Google (xem docstring backend `youtube_analytics.py`).
  youtubeOAuthCallbackUrl: () => `${BASE}/oauth/callback`,
  disconnectChannelFromYoutube: (channelId: string) => post<{ ok: boolean }>(`/channels/${channelId}/youtube/disconnect`),
  syncYoutubeMetrics: (channelId: string) => post<YoutubeChannelMetricsOut>(`/channels/${channelId}/youtube/sync`),
  getYoutubeChannelMetrics: (channelId: string) => get<YoutubeChannelMetricsOut>(`/channels/${channelId}/youtube/metrics`),
  getYoutubeVideosAvailable: (projectId: string) => get<{ videos: YoutubeVideoAvailable[]; current_video_id: string | null }>(`/projects/${projectId}/youtube-videos-available`),
  patchYoutubeLink: (projectId: string, videoId: string | null) => patch<{ youtube_video_id: string | null }>(`/projects/${projectId}/youtube-link`, { video_id: videoId }),
  getRetentionChapters: (projectId: string) => get<{ video_duration_sec: number | null; chapters: YoutubeRetentionChapter[] }>(`/projects/${projectId}/youtube/retention-chapters`),

  // Export — "Xuất Pack" (2026-08-26, thay "Output A" cũ): gói SRT + assets + giọng đọc
  // full + video đã ghép (nếu có) ra 1 folder trên máy local, xem app/render/pack_export.py.
  exportPackBundle: (id: string, destDir: string) =>
    post<{ dest_dir: string; included: string[]; skipped: { item: string; reason: string }[] }>(`/projects/${id}/export/pack-bundle`, { dest_dir: destDir }),

  // Render Studio (M2 Production Layer — sinh asset thật + ghép MP4)
  startRender: (id: string, kind: "both" | "visual" | "narration" = "both", force = false) =>
    post<RenderState>(`/projects/${id}/render/start?kind=${kind}${force ? "&force=true" : ""}`),
  cancelRender: (id: string) => post<RenderState>(`/projects/${id}/render/cancel`),
  getRenderStatus: (id: string) => get<RenderState>(`/projects/${id}/render/status`),
  // Tốc độ giọng đọc TOÀN BỘ block — nút ở Script Studio (2026-09-02, mục 109). Chỉ
  // lưu giá trị, áp dụng cho lần (re)generate narration TIẾP THEO (time-stretch file
  // audio sau khi sinh — xem backend `engine.py::_apply_narration_speed`).
  patchNarrationSpeed: (id: string, speed: number) => patch<RenderState>(`/projects/${id}/render/narration-speed`, { speed }),
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
  // Upload cả folder ảnh/video khớp theo mã block — mới (2026-09-16).
  uploadShotVisualBatch: (id: string, files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    return req<ShotUploadBatchResult>(`/projects/${id}/render/shots/upload-visual-batch`, { method: "POST", body: form });
  },
  // Xoá ảnh/video đã sinh/upload/gán cho 1 shot (Visual Studio, 2026-09-02, theo yêu cầu
  // người dùng — cho phép bỏ 1 asset không ưng ý mà không bị buộc sinh/upload cái khác
  // ngay). Trả shot về "pending" như chưa từng sinh.
  removeShotVisual: (id: string, shotId: string) => del<RenderState>(`/projects/${id}/render/shots/${shotId}/visual`),
  regenerateShotNarration: (id: string, shotId: string) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/regenerate-narration`),
  // Giọng đọc đa ngôn ngữ (mới 2026-09-04) — 1 ngôn ngữ (khác ngôn ngữ chính) cho MỌI
  // shot đã có văn bản dịch, hoặc RIÊNG 1 shot. Cùng pattern startRender/
  // regenerateShotNarration ở trên.
  startNarrationTranslationBatch: (id: string, lang: NarrationLanguage, force = false) =>
    post<RenderState>(`/projects/${id}/render/narration-translations/${lang}/start${force ? "?force=true" : ""}`),
  regenerateShotNarrationTranslation: (id: string, shotId: string, lang: NarrationLanguage) =>
    post<RenderState>(`/projects/${id}/render/shots/${shotId}/regenerate-narration-translation/${lang}`),
  renderShotNarrationTranslationAssetUrl: (id: string, shotId: string, lang: NarrationLanguage) =>
    `${BASE}/projects/${id}/render/shots/${shotId}/asset/narration/${lang}`,
  downloadNarrationFullLang: (id: string, lang: NarrationLanguage) =>
    downloadFile(`/projects/${id}/render/narration-download/${lang}`, `narration_full_${lang}.mp3`),
  // Xoá watermark (Visual Studio, 2026-08-28) — tái dùng module app/watermark/ đã build
  // cho Kho Tài Nguyên. "Không phát hiện watermark" KHÔNG phải lỗi, xem
  // ShotRenderStatus.visual_watermark_note.
  // `mode` — **mới (2026-09-18)**: "auto" (mặc định) chỉ tự xoá ảnh nếu rõ nguồn Gemini,
  // "gemini" ép chạy bất kể provider (nút "Xoá watermark Gemini" riêng) — xem docstring
  // backend `render.py::remove_shot_watermark`.
  removeShotWatermark: (id: string, shotId: string, mode: "auto" | "gemini" = "auto") =>
    post<RenderState>(`/projects/${id}/render/shots/${shotId}/remove-watermark?mode=${mode}`),
  // `mode` — xem chú thích `removeShotWatermark` ở trên.
  removeAllShotsWatermark: (id: string, mode: "auto" | "gemini" = "auto") =>
    post<RenderState>(`/projects/${id}/render/remove-watermark-all?mode=${mode}`),
  // Video Slot nguồn "Video từ Kho" (CHANGE_Semantic_BRoll_Asset_Vault.md §7.3).
  getVaultCandidates: (id: string, shotId: string) => get<VaultCandidatesResult>(`/projects/${id}/render/shots/${shotId}/vault-candidates`),
  assignVaultClip: (id: string, shotId: string, clipId: string) => post<RenderState>(`/projects/${id}/render/shots/${shotId}/assign-vault-clip`, { clip_id: clipId }),
  // Tự động điền block còn thiếu từ Kho Tài Nguyên — mới (2026-09-11), chuyển sang job
  // nền poll được (2026-09-13) để hiện progress bar (xem `VaultAutoFillScanStatus`).
  startVaultAutoFillScan: (id: string) => post<VaultAutoFillScanStatus>(`/projects/${id}/render/vault-auto-fill-scan`),
  getVaultAutoFillScanStatus: (id: string) => get<VaultAutoFillScanStatus>(`/projects/${id}/render/vault-auto-fill-scan/status`),
  applyVaultAutoFill: (id: string, items: { shot_id: string; clip_id: string }[]) =>
    post<VaultAutoFillApplyResult>(`/projects/${id}/render/vault-auto-fill-apply`, { items }),
  assembleVideo: (id: string, config?: AssembleConfig) => post<RenderState>(`/projects/${id}/render/assemble`, config),
  // Xuất short-video 9:16 từ 1 khoảng block — mới (2026-09-12), Output Center. Tối đa 3
  // cái/project (400 khi bấm xuất thêm — xem `render/short_export.py`). Không có endpoint
  // GET tiến độ riêng — `getRenderStatus`/`RenderState.short_exports` (poll sẵn có) đã đủ.
  createShortExport: (id: string, body: { start_block_id: string; end_block_id: string; regenerate_images: boolean; lang?: NarrationLanguage | null }) =>
    post<RenderState>(`/projects/${id}/render/short-export`, body),
  deleteShortExport: (id: string, exportId: string) => del<RenderState>(`/projects/${id}/render/short-export/${exportId}`),
  shortExportDownloadUrl: (id: string, exportId: string) => `${BASE}/projects/${id}/render/short-export/${exportId}/download`,
  downloadShortExport: (id: string, exportId: string, startBlockId: string, endBlockId: string, lang: string) =>
    downloadFile(`/projects/${id}/render/short-export/${exportId}/download`, `short_${startBlockId}-${endBlockId}_${lang}.mp4`),
  // "Đặt lại tiến trình bị treo" — mới (2026-09-02, mục 111). 409 nếu tiến trình vẫn
  // đang chạy THẬT SỰ (không phải kẹt) — xem docstring backend `reset_stuck_assembly`.
  resetStuckAssembly: (id: string) => post<RenderState>(`/projects/${id}/render/assemble/reset`),
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
  // Ảnh nhân vật tham khảo — mới (2026-09-09, mục 127).
  uploadCharacterReference: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/character-reference/upload`, { method: "POST", body: form });
  },
  recaptionCharacterReference: (id: string) => post<RenderState>(`/projects/${id}/render/character-reference/recaption`, {}),
  patchCharacterReferenceDescription: (id: string, description: string) => patch<RenderState>(`/projects/${id}/render/character-reference/description`, { description }),
  deleteCharacterReference: (id: string) => del<RenderState>(`/projects/${id}/render/character-reference`),
  characterReferenceAssetUrl: (id: string) => `${BASE}/projects/${id}/render/character-reference/asset`,
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
  enableOverlayInherit: (id: string) => patch<RenderState>(`/projects/${id}/render/overlay/inherit`, {}),
  projectOverlayUrl: (id: string) => `${BASE}/projects/${id}/render/overlay/asset`,
  // Video nền chung cho toàn bộ block (2026-09-02) — xem types.ts::BackgroundVideoOverride.
  // Nhiều video (mới 2026-09-02, mục 110) — mỗi lần upload THÊM 1 video vào asset_paths.
  uploadProjectBackgroundVideo: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<RenderState>(`/projects/${id}/render/background-video/upload`, { method: "POST", body: form });
  },
  deleteProjectBackgroundVideoItem: (id: string, index: number) => del<RenderState>(`/projects/${id}/render/background-video/${index}`),
  deleteProjectBackgroundVideo: (id: string) => del<RenderState>(`/projects/${id}/render/background-video`),
  patchProjectBackgroundVideoSettings: (id: string, body: Partial<{ random_order: boolean; transition: string }>) =>
    patch<RenderState>(`/projects/${id}/render/background-video`, body),
  projectBackgroundVideoUrl: (id: string, index: number) => `${BASE}/projects/${id}/render/background-video/asset/${index}`,
  // Layer video định vị theo lưới 3x3 (VD voice wave, logo) — mới (2026-09-02, mục 112)
  // — xem types.ts::VideoLayer. `blend_mode` — mới (mục 113): "alpha" (mặc định, nguồn
  // CÓ SẴN kênh alpha — WebM VP9/MOV ProRes4444) hoặc "screen" (nguồn NỀN ĐEN ĐẶC,
  // không alpha — cùng kỹ thuật overlay hiệu ứng lớp phủ nhưng định vị cục bộ).
  uploadProjectLayer: (id: string, file: File, position: LayerPosition, widthPct: number, opacity: number, blendMode: LayerBlendMode) => {
    const form = new FormData();
    form.append("file", file);
    form.append("position", position);
    form.append("width_pct", String(widthPct));
    form.append("opacity", String(opacity));
    form.append("blend_mode", blendMode);
    return req<RenderState>(`/projects/${id}/render/layers/upload`, { method: "POST", body: form });
  },
  patchProjectLayer: (id: string, layerId: string, body: Partial<{ position: LayerPosition; width_pct: number; opacity: number; blend_mode: LayerBlendMode }>) =>
    patch<RenderState>(`/projects/${id}/render/layers/${layerId}`, body),
  deleteProjectLayer: (id: string, layerId: string) => del<RenderState>(`/projects/${id}/render/layers/${layerId}`),
  projectLayerAssetUrl: (id: string, layerId: string) => `${BASE}/projects/${id}/render/layers/${layerId}/asset`,
  // Layer ẢNH định vị — mới (2026-09-02, mục 115) — xem types.ts::ImageLayer. Song song
  // layer video ở trên, chỉ khác: nhận ảnh (PNG/JPEG/WEBP), position có thêm "full".
  uploadProjectImageLayer: (id: string, file: File, position: ImageLayerPosition, widthPct: number, opacity: number, blendMode: LayerBlendMode) => {
    const form = new FormData();
    form.append("file", file);
    form.append("position", position);
    form.append("width_pct", String(widthPct));
    form.append("opacity", String(opacity));
    form.append("blend_mode", blendMode);
    return req<RenderState>(`/projects/${id}/render/image-layers/upload`, { method: "POST", body: form });
  },
  patchProjectImageLayer: (id: string, layerId: string, body: Partial<{ position: ImageLayerPosition; width_pct: number; opacity: number; blend_mode: LayerBlendMode }>) =>
    patch<RenderState>(`/projects/${id}/render/image-layers/${layerId}`, body),
  deleteProjectImageLayer: (id: string, layerId: string) => del<RenderState>(`/projects/${id}/render/image-layers/${layerId}`),
  projectImageLayerAssetUrl: (id: string, layerId: string) => `${BASE}/projects/${id}/render/image-layers/${layerId}/asset`,
  // Layer CAPTION (phụ đề cứng burn-in) — mới (2026-09-12). 1 cấu hình duy nhất/project,
  // không có upload — PATCH duy nhất, `lang: null`/`""` = theo ngôn ngữ đang ghép video.
  patchCaptionLayer: (id: string, body: Partial<{ enabled: boolean; position: LayerPosition; size_pct: number; opacity: number; lang: NarrationLanguage | null }>) =>
    patch<RenderState>(`/projects/${id}/render/caption-layer`, body),

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

  // Kho Tài Nguyên / Asset Vault (CHANGE_Semantic_BRoll_Asset_Vault.md) — kho tư liệu
  // video TOÀN CỤC (2026-08-27, khác Thư viện Creative Asset ở trên), 1 video gốc gắn
  // được NHIỀU kênh dạng tag — lọc theo kênh qua `channelId` tuỳ chọn.
  listRawVideos: (channelId?: string, kind?: "raw" | "project") => {
    const params = new URLSearchParams();
    if (channelId) params.set("channel_id", channelId);
    if (kind) params.set("kind", kind);
    const qs = params.toString();
    return get<RawVideo[]>(`/asset-vault/raw${qs ? `?${qs}` : ""}`);
  },
  getAssetVaultFolders: () => get<{ raw_dir: string; clips_dir: string }>("/asset-vault/folders"),
  uploadRawVideo: (channelIds: string[], file: File, importNote = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("channel_ids", JSON.stringify(channelIds));
    if (importNote) form.append("import_note", importNote);
    return req<RawVideo>("/asset-vault/raw/upload", { method: "POST", body: form });
  },
  importRawVideoFromUrl: (channelIds: string[], url: string, importNote = "") =>
    post<RawVideo>("/asset-vault/raw/import-url", { url, channel_ids: channelIds, import_note: importNote }),
  patchRawVideoChannels: (rawId: string, channelIds: string[]) =>
    patch<RawVideo>(`/asset-vault/raw/${rawId}/channels`, { channel_ids: channelIds }),
  deleteRawVideo: (rawId: string) => del<{ ok: boolean }>(`/asset-vault/raw/${rawId}`),
  rawVideoFileUrl: (rawId: string) => `${BASE}/asset-vault/raw/${rawId}/file`,
  batchTagRawVideoChannels: (rawIds: string[], channelIds: string[]) =>
    post<RawVideo[]>("/asset-vault/raw/batch-tag-channels", { raw_ids: rawIds, channel_ids: channelIds }),
  batchDeleteRawVideos: (rawIds: string[]) => post<{ ok: boolean; deleted: number }>("/asset-vault/raw/batch-delete", { raw_ids: rawIds }),
  detectScenes: (rawId: string) => post<RawVideo>(`/asset-vault/raw/${rawId}/detect-scenes`),
  manualCutClip: (rawId: string, startSec: number, endSec: number) =>
    post<ProcessedClip>(`/asset-vault/raw/${rawId}/manual-cut`, { start_sec: startSec, end_sec: endSec }),
  captionAllClips: (rawId: string) => post<RawVideo>(`/asset-vault/raw/${rawId}/caption-all`),
  // Xoá watermark trước khi cắt cảnh (app/watermark/, Florence-2 + LaMa) — chạy nền, poll
  // qua listRawVideos() để theo dõi progress_current/total giống detect-scenes.
  removeWatermark: (rawId: string) => post<RawVideo>(`/asset-vault/raw/${rawId}/remove-watermark`),
  listProcessedClips: (filters?: { channel_id?: string; raw_video_id?: string; rights_status?: string; tag?: string; mood_tone?: string }) => {
    const qs = filters ? Object.entries(filters).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&") : "";
    return get<ProcessedClip[]>(`/asset-vault/clips${qs ? `?${qs}` : ""}`);
  },
  clipFileUrl: (clipId: string) => `${BASE}/asset-vault/clips/${clipId}/file`,
  patchProcessedClip: (clipId: string, body: Partial<{ caption: string; tags: string[]; mood_tone: string; rights_status: ClipRightsStatus; rights_note: string; active: boolean }>) =>
    patch<ProcessedClip>(`/asset-vault/clips/${clipId}`, body),
  batchPatchProcessedClips: (body: { clip_ids: string[]; rights_status?: ClipRightsStatus; add_tag?: string; active?: boolean }) =>
    post<ProcessedClip[]>("/asset-vault/clips/batch", body),
  // Tag kênh RIÊNG của clip (2026-08-28) — độc lập với raw_video cha, xem
  // IMPLEMENTATION_REPORT.md mục 98.
  patchClipChannels: (clipId: string, channelIds: string[]) =>
    patch<ProcessedClip>(`/asset-vault/clips/${clipId}/channels`, { channel_ids: channelIds }),
  batchTagClipChannels: (clipIds: string[], channelIds: string[]) =>
    post<ProcessedClip[]>("/asset-vault/clips/batch-tag-channels", { clip_ids: clipIds, channel_ids: channelIds }),
  captionClipsBatch: (clipIds: string[]) => post<{ ok: boolean; count: number }>("/asset-vault/clips/caption-batch", { clip_ids: clipIds }),
  deleteProcessedClip: (clipId: string) => del<{ ok: boolean }>(`/asset-vault/clips/${clipId}`),
  batchDeleteProcessedClips: (clipIds: string[]) => post<{ ok: boolean; deleted: number }>("/asset-vault/clips/batch-delete", { clip_ids: clipIds }),

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
  // Đổi tên từ `listLocalSdxlModels`/`/providers/local-sdxl/models` — đợt dọn dẹp
  // 2026-09-24 xoá `local_sdxl` (tên cũ gây hiểu nhầm khi SDXL không còn tồn tại), giờ
  // dùng chung cho `local_qwen` (provider ComfyUI duy nhất còn lại).
  listComfyUIModels: (kind: "checkpoints" | "loras" | "unet_gguf", baseUrl?: string) => {
    const params = new URLSearchParams({ kind });
    if (baseUrl) params.set("base_url", baseUrl);
    return get<{ models: string[] }>(`/providers/comfyui/models?${params.toString()}`);
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
