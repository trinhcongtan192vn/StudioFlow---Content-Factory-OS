import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BrandProfile, NarrationLanguage } from "../api/types";
import { NARRATION_LANGUAGES, NARRATION_LANGUAGE_LABELS } from "../api/types";
import AddToLibraryButton from "./AddToLibraryButton";
import LibraryPicker from "./LibraryPicker";

interface Draft {
  name: string;
  niche: string;
  tone: string;
  pacing: string;
  pillarsText: string;
  taboosText: string;
  targetHookStrength: string;
  maxAnchorGapSec: string;
  targetBodyLenMin: string;
  visualStylePrompt: string;
  culturalLockPositive: string;
  culturalLockNegative: string;
  logoPath: string;
  voiceCloneRefPath: string;
  // Giọng đọc đa ngôn ngữ (mới 2026-09-04) — ngôn ngữ CHÍNH quyết định văn bản nào dùng
  // để render video/tính timestamp; mẫu giọng clone theo TỪNG ngôn ngữ (RIÊNG khỏi
  // `voiceCloneRefPath` đơn ở trên, dùng cho ngôn ngữ chính — xem UI bên dưới).
  primaryLanguage: NarrationLanguage;
  voiceCloneRefPaths: Partial<Record<NarrationLanguage, string>>;
  introVideoPath: string;
  introAudioPath: string;
  bgMusicPath: string;
  bgMusicVolume: string;
  overlayEffectPath: string;
  overlayEffectOpacity: string;
}

function emptyDraft(): Draft {
  return {
    name: "",
    niche: "",
    tone: "",
    pacing: "",
    pillarsText: "",
    taboosText: "",
    targetHookStrength: "0.7",
    maxAnchorGapSec: "45",
    targetBodyLenMin: "8",
    visualStylePrompt: "",
    culturalLockPositive: "",
    culturalLockNegative: "",
    logoPath: "",
    voiceCloneRefPath: "",
    primaryLanguage: "vi",
    voiceCloneRefPaths: {},
    introVideoPath: "",
    introAudioPath: "",
    bgMusicPath: "",
    bgMusicVolume: "0.3",
    overlayEffectPath: "",
    overlayEffectOpacity: "0.5",
  };
}

function draftFromProfile(name: string, niche: string, bp: BrandProfile): Draft {
  return {
    name,
    niche,
    tone: bp.brand_voice?.tone || "",
    pacing: bp.brand_voice?.pacing || "",
    pillarsText: (bp.content_pillars || []).map((p) => p.name).join(", "),
    taboosText: (bp.forbidden || []).join(", "),
    targetHookStrength: String(bp.retention_benchmark?.target_hook_strength ?? 0.7),
    maxAnchorGapSec: String(bp.retention_benchmark?.max_anchor_gap_sec ?? 45),
    targetBodyLenMin: String(bp.retention_benchmark?.target_body_len_min ?? 8),
    visualStylePrompt: bp.visual_style_prompt || "",
    culturalLockPositive: bp.cultural_lock_positive || "",
    // Bug thật (2026-09-02, user báo xoá trắng field rồi lưu — mở lại vẫn còn giá trị) —
    // TỪNG dùng `|| "<gợi ý mặc định>"` ở đây, khiến chuỗi rỗng THẬT SỰ đã lưu (falsy)
    // không phân biệt được với "chưa từng có giá trị" — form lại tự điền gợi ý cũ, TRÔNG
    // như chưa lưu được dù backend đã lưu đúng chuỗi rỗng. Đổi về `|| ""` (khớp mọi field
    // khác trong hàm này) — gợi ý cũ chuyển thành PLACEHOLDER (chỉ hiện mờ, không phải giá
    // trị thật) ở JSX bên dưới.
    culturalLockNegative: bp.cultural_lock_negative || "",
    logoPath: bp.logo_path || "",
    voiceCloneRefPath: bp.voice_clone_ref_path || "",
    primaryLanguage: bp.primary_language || "vi",
    voiceCloneRefPaths: bp.voice_clone_ref_paths || {},
    introVideoPath: bp.intro_video_path || "",
    introAudioPath: bp.intro_audio_path || "",
    bgMusicPath: bp.bg_music_path || "",
    bgMusicVolume: String(bp.bg_music_volume ?? 0.3),
    overlayEffectPath: bp.overlay_effect_path || "",
    overlayEffectOpacity: String(bp.overlay_effect_opacity ?? 0.5),
  };
}

export default function ChannelDialog({ mode, channelId, onClose, onSaved }: { mode: "create" | "edit"; channelId?: string; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);
  const [uploadingVoice, setUploadingVoice] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const voiceFileRef = useRef<HTMLInputElement | null>(null);
  // `api.voiceSampleUrl(id)`/`api.brandIntroUrl(id)` là URL CỐ ĐỊNH (không đổi theo lần
  // upload) — trình duyệt/thẻ <audio>/<video> KHÔNG tự refetch khi backend đã ghi đè
  // file mới, vẫn phát y hệt bản đã tải trước đó (bug thật người dùng báo, 2026-08-20 —
  // cùng lớp bug đã biết ở ThumbnailCard/IntroShotCard, xem ghi chú "cacheBust" ở đó).
  // Bump số này sau MỖI lần upload/xoá thành công, gắn vào query string để ép trình
  // duyệt coi là URL mới.
  const [voiceCacheBust, setVoiceCacheBust] = useState(0);
  const [introCacheBust, setIntroCacheBust] = useState(0);
  const [bgMusicCacheBust, setBgMusicCacheBust] = useState(0);
  const [logoCacheBust, setLogoCacheBust] = useState(0);
  const [overlayCacheBust, setOverlayCacheBust] = useState(0);

  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [logoError, setLogoError] = useState<string | null>(null);
  const logoFileRef = useRef<HTMLInputElement | null>(null);

  async function uploadBrandLogo(file: File) {
    if (!channelId) return;
    setUploadingLogo(true);
    setLogoError(null);
    try {
      const result = await api.uploadBrandLogo(channelId, file);
      set("logoPath", result.logo_path || "");
      setLogoCacheBust((n) => n + 1);
    } catch (e) {
      setLogoError(e instanceof ApiError ? e.message : "Có lỗi khi upload logo.");
    } finally {
      setUploadingLogo(false);
      if (logoFileRef.current) logoFileRef.current.value = "";
    }
  }

  async function removeBrandLogo() {
    if (!channelId) return;
    setUploadingLogo(true);
    setLogoError(null);
    try {
      const current = await api.getBrandProfile(channelId);
      const updated = await api.putBrandProfile(channelId, { ...current, logo_path: "" });
      set("logoPath", updated.logo_path || "");
      setLogoCacheBust((n) => n + 1);
    } catch (e) {
      setLogoError(e instanceof ApiError ? e.message : "Có lỗi khi xoá logo.");
    } finally {
      setUploadingLogo(false);
    }
  }

  async function uploadVoiceSample(file: File) {
    if (!channelId) return;
    setUploadingVoice(true);
    setVoiceError(null);
    setVoiceNotice(null);
    try {
      const result = await api.uploadVoiceSample(channelId, file);
      set("voiceCloneRefPath", result.voice_clone_ref_path || "");
      setVoiceCacheBust((n) => n + 1);
      // Mẫu >10s bị tự động cắt ngắn (mục 24 IMPLEMENTATION_REPORT.md — mẫu dài gây lẫn
      // nội dung tham chiếu vào narration sinh ra) — báo rõ cho người dùng, không âm thầm.
      if (result.voice_sample_trimmed) {
        const original = result.voice_sample_original_duration_sec;
        setVoiceNotice(`Đã tự động cắt mẫu còn 10 giây (mẫu gốc ${original ? original.toFixed(1) : "?"} giây) để đảm bảo chất lượng nhân bản giọng — mẫu quá dài sẽ khiến giọng đọc lẫn nội dung không mong muốn.`);
      }
    } catch (e) {
      setVoiceError(e instanceof ApiError ? e.message : "Có lỗi khi upload mẫu giọng.");
    } finally {
      setUploadingVoice(false);
      if (voiceFileRef.current) voiceFileRef.current.value = "";
    }
  }

  const [uploadingIntro, setUploadingIntro] = useState(false);
  const [introError, setIntroError] = useState<string | null>(null);
  const introVideoFileRef = useRef<HTMLInputElement | null>(null);
  const introAudioFileRef = useRef<HTMLInputElement | null>(null);

  async function uploadBrandIntro(file: File) {
    if (!channelId) return;
    setUploadingIntro(true);
    setIntroError(null);
    try {
      const result = await api.uploadBrandIntro(channelId, file);
      // Server tự đảm bảo chỉ 1 trong 2 khác rỗng (upload video xoá audio và ngược lại).
      set("introVideoPath", result.intro_video_path || "");
      set("introAudioPath", result.intro_audio_path || "");
      setIntroCacheBust((n) => n + 1);
    } catch (e) {
      setIntroError(e instanceof ApiError ? e.message : "Có lỗi khi upload video/audio thương hiệu.");
    } finally {
      setUploadingIntro(false);
      if (introVideoFileRef.current) introVideoFileRef.current.value = "";
      if (introAudioFileRef.current) introAudioFileRef.current.value = "";
    }
  }

  // **Bug thật người dùng báo (2026-08-20)**: nút "Xoá" trước đây CHỈ xoá draft cục bộ
  // — phải bấm "Lưu thay đổi" mới thật sự xoá ở server. Đổi thành PERSIST NGAY (PUT
  // luôn) — khớp kỳ vọng người dùng ("Xoá" = xoá thật, không phải "đánh dấu để xoá sau"),
  // tránh trạng thái lửng lơ (draft trống nhưng server vẫn còn) gây hiểu nhầm "vẫn còn
  // hiện lại nội dung cũ" khi tương tác tiếp (VD upload loại khác) trước khi kịp Lưu.
  async function removeBrandIntro() {
    if (!channelId) return;
    setUploadingIntro(true);
    setIntroError(null);
    try {
      const current = await api.getBrandProfile(channelId);
      const updated = await api.putBrandProfile(channelId, { ...current, intro_video_path: "", intro_audio_path: "" });
      set("introVideoPath", updated.intro_video_path || "");
      set("introAudioPath", updated.intro_audio_path || "");
      setIntroCacheBust((n) => n + 1);
    } catch (e) {
      setIntroError(e instanceof ApiError ? e.message : "Có lỗi khi xoá video/audio thương hiệu.");
    } finally {
      setUploadingIntro(false);
    }
  }

  const [uploadingBgMusic, setUploadingBgMusic] = useState(false);
  const [bgMusicError, setBgMusicError] = useState<string | null>(null);
  const bgMusicFileRef = useRef<HTMLInputElement | null>(null);

  async function uploadBgMusic(file: File) {
    if (!channelId) return;
    setUploadingBgMusic(true);
    setBgMusicError(null);
    try {
      const result = await api.uploadBrandBgMusic(channelId, file);
      set("bgMusicPath", result.bg_music_path || "");
      setBgMusicCacheBust((n) => n + 1);
    } catch (e) {
      setBgMusicError(e instanceof ApiError ? e.message : "Có lỗi khi upload nhạc nền.");
    } finally {
      setUploadingBgMusic(false);
      if (bgMusicFileRef.current) bgMusicFileRef.current.value = "";
    }
  }

  async function removeBgMusic() {
    if (!channelId) return;
    setUploadingBgMusic(true);
    setBgMusicError(null);
    try {
      const current = await api.getBrandProfile(channelId);
      const updated = await api.putBrandProfile(channelId, { ...current, bg_music_path: "" });
      set("bgMusicPath", updated.bg_music_path || "");
      setBgMusicCacheBust((n) => n + 1);
    } catch (e) {
      setBgMusicError(e instanceof ApiError ? e.message : "Có lỗi khi xoá nhạc nền.");
    } finally {
      setUploadingBgMusic(false);
    }
  }

  const [uploadingOverlay, setUploadingOverlay] = useState(false);
  const [overlayError, setOverlayError] = useState<string | null>(null);
  const overlayFileRef = useRef<HTMLInputElement | null>(null);

  async function uploadOverlay(file: File) {
    if (!channelId) return;
    setUploadingOverlay(true);
    setOverlayError(null);
    try {
      const result = await api.uploadBrandOverlay(channelId, file);
      set("overlayEffectPath", result.overlay_effect_path || "");
      setOverlayCacheBust((n) => n + 1);
    } catch (e) {
      setOverlayError(e instanceof ApiError ? e.message : "Có lỗi khi upload hiệu ứng lớp phủ.");
    } finally {
      setUploadingOverlay(false);
      if (overlayFileRef.current) overlayFileRef.current.value = "";
    }
  }

  async function removeOverlay() {
    if (!channelId) return;
    setUploadingOverlay(true);
    setOverlayError(null);
    try {
      const current = await api.getBrandProfile(channelId);
      const updated = await api.putBrandProfile(channelId, { ...current, overlay_effect_path: "" });
      set("overlayEffectPath", updated.overlay_effect_path || "");
      setOverlayCacheBust((n) => n + 1);
    } catch (e) {
      setOverlayError(e instanceof ApiError ? e.message : "Có lỗi khi xoá hiệu ứng lớp phủ.");
    } finally {
      setUploadingOverlay(false);
    }
  }

  useEffect(() => {
    if (mode === "edit" && channelId) {
      api.getChannel(channelId).then((ch) => {
        setDraft(draftFromProfile(ch.name, ch.niche, ch.brand_profile));
        setLoading(false);
      });
    }
  }, [mode, channelId]);

  function set<K extends keyof Draft>(k: K, v: Draft[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function save() {
    if (!draft.name.trim()) return;
    setSaving(true);
    try {
      const pillars = draft.pillarsText.split(",").map((s) => s.trim()).filter(Boolean);
      const taboos = draft.taboosText.split(",").map((s) => s.trim()).filter(Boolean);

      let id = channelId;
      if (mode === "create") {
        const ch = await api.createChannel({ name: draft.name.trim(), niche: draft.niche.trim() });
        id = ch.id;
      } else {
        await api.patchChannel(id!, { name: draft.name.trim(), niche: draft.niche.trim() });
      }

      const current = await api.getBrandProfile(id!);
      const nextProfile: BrandProfile = {
        ...current,
        niche: draft.niche.trim(),
        brand_voice: { ...current.brand_voice, tone: draft.tone, pacing: draft.pacing },
        content_pillars: pillars.map((name) => ({ name, weight: pillars.length ? Math.round((1 / pillars.length) * 100) / 100 : 0 })),
        forbidden: taboos,
        visual_style_prompt: draft.visualStylePrompt,
        cultural_lock_positive: draft.culturalLockPositive.trim(),
        cultural_lock_negative: draft.culturalLockNegative.trim(),
        logo_path: draft.logoPath,
        voice_clone_ref_path: draft.voiceCloneRefPath,
        primary_language: draft.primaryLanguage,
        voice_clone_ref_paths: draft.voiceCloneRefPaths,
        intro_video_path: draft.introVideoPath,
        intro_audio_path: draft.introAudioPath,
        bg_music_path: draft.bgMusicPath,
        bg_music_volume: parseFloat(draft.bgMusicVolume) || 0,
        overlay_effect_path: draft.overlayEffectPath,
        overlay_effect_opacity: parseFloat(draft.overlayEffectOpacity) || 0.5,
        retention_benchmark: {
          target_hook_strength: parseFloat(draft.targetHookStrength) || 0.7,
          max_anchor_gap_sec: parseInt(draft.maxAnchorGapSec) || 45,
          target_body_len_min: parseInt(draft.targetBodyLenMin) || 8,
        },
      };
      await api.putBrandProfile(id!, nextProfile);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(520px,100%)", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">{mode === "create" ? "Tạo kênh mới" : "Sửa BrandProfile"}</div>
        {loading ? (
          <div style={{ opacity: 0.6, fontSize: 13 }}>Đang tải...</div>
        ) : (
          <>
            <div className="field">
              <label>Tên kênh</label>
              <input className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="VD: Sử Việt Kể" />
            </div>
            <div className="field">
              <label>Thể loại (niche)</label>
              <input className="input" value={draft.niche} onChange={(e) => set("niche", e.target.value)} placeholder="VD: Lịch sử" />
            </div>
            <div className="field">
              <label>Tông giọng (brand voice)</label>
              <textarea className="input" rows={2} value={draft.tone} onChange={(e) => set("tone", e.target.value)} placeholder="VD: Trầm, kể chuyện, nhiều chi tiết cảm xúc" />
            </div>
            <div className="field">
              <label>Nhịp điệu</label>
              <input className="input" value={draft.pacing} onChange={(e) => set("pacing", e.target.value)} placeholder="VD: chậm, giàu hình ảnh" />
            </div>
            <div className="field">
              <label>Content pillars (phân tách bằng dấu phẩy)</label>
              <input className="input" value={draft.pillarsText} onChange={(e) => set("pillarsText", e.target.value)} placeholder="Nhân vật lịch sử, Bí ẩn chưa giải" />
            </div>
            <div className="field">
              <label>Danh sách cấm kỵ (phân tách bằng dấu phẩy)</label>
              <input className="input" value={draft.taboosText} onChange={(e) => set("taboosText", e.target.value)} placeholder="Xuyên tạc chính sử" />
            </div>
            <div className="field">
              <label>Style hình ảnh (visual_style_prompt)</label>
              <input className="input" value={draft.visualStylePrompt} onChange={(e) => set("visualStylePrompt", e.target.value)} placeholder="archival tone, muted sepia" />
            </div>
            {/* Cultural lock — mới (2026-08-23), theo yêu cầu người dùng: checkpoint/LoRA
                phong cách "Á Đông" tuyệt đại đa số train từ dữ liệu Nhật/Trung/Hàn — ảnh
                sinh ra dễ mang nét Nhật/Hàn dù không yêu cầu. 2 field này ép rõ hướng
                văn hoá Việt Nam. */}
            <div className="field">
              <label>Từ khoá văn hoá Việt Nam (bắt buộc xuất hiện)</label>
              <textarea
                className="input"
                rows={2}
                value={draft.culturalLockPositive}
                onChange={(e) => set("culturalLockPositive", e.target.value)}
                placeholder="áo tứ thân, áo giao lĩnh, khăn mỏ quạ, mái đình làng Bắc Bộ, ngói âm dương, hoạ tiết rồng thời Nguyễn..."
              />
              <span style={{ fontSize: 11.5, opacity: 0.6 }}>Ghi cụ thể theo đúng triều đại/bối cảnh video (trang phục, kiến trúc, hoạ tiết) — áp dụng cho MỌI provider (cloud lẫn local).</span>
            </div>
            <div className="field">
              <label>Loại trừ văn hoá ngoại lai (negative prompt)</label>
              <textarea
                className="input"
                rows={2}
                value={draft.culturalLockNegative}
                onChange={(e) => set("culturalLockNegative", e.target.value)}
                placeholder="japanese kimono, torii gate, korean hanbok, japanese architecture, korean architecture, anime style, manga, japanese art style"
              />
              <span style={{ fontSize: 11.5, opacity: 0.6 }}>Hiện chưa nối vào provider ảnh/video nào — để dành cho lần cải tiến sau (đợt dọn dẹp 2026-09-24 xoá các provider local cũ có hỗ trợ negative prompt, xem IMPLEMENTATION_REPORT.md).</span>
            </div>
            {mode === "edit" && (
              <div className="field">
                <label>Logo kênh</label>
                <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                  Thuần hiển thị nhận diện thương hiệu — không dùng khi sinh asset/ghép video. Không bắt buộc.
                </div>
                {draft.logoPath ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <img
                      alt="Logo kênh"
                      src={`${api.brandLogoUrl(channelId!)}?v=${logoCacheBust}`}
                      style={{ width: 56, height: 56, objectFit: "cover", borderRadius: "var(--radius-sm)", flex: "none" }}
                    />
                    <AddToLibraryButton kind="image" sourceUrl={`${api.brandLogoUrl(channelId!)}?v=${logoCacheBust}`} name="logo-thuong-hieu" />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px", flex: "none" }} onClick={removeBrandLogo} disabled={uploadingLogo}>
                      {uploadingLogo ? "Đang xoá..." : "Xoá"}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      ref={logoFileRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadBrandLogo(f);
                      }}
                    />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => logoFileRef.current?.click()} disabled={uploadingLogo}>
                      {uploadingLogo ? "Đang tải lên..." : "Upload logo"}
                    </button>
                    <LibraryPicker kinds={["image"]} disabled={uploadingLogo} onPick={uploadBrandLogo} />
                  </div>
                )}
                {logoError && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{logoError}</div>}
              </div>
            )}
            <div className="field">
              <label>Ngôn ngữ chính của kênh</label>
              <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                Quyết định ngôn ngữ dùng để render video/tính timestamp — kênh phục vụ thị trường nước ngoài vẫn có thể sinh thêm giọng đọc/phụ đề các ngôn ngữ khác ở Script Studio (chỉ xuất SRT/MP3 riêng, không đổi video đã render).
              </div>
              <select className="input" value={draft.primaryLanguage} onChange={(e) => set("primaryLanguage", e.target.value as NarrationLanguage)}>
                {NARRATION_LANGUAGES.map((lang) => (
                  <option key={lang} value={lang}>
                    {NARRATION_LANGUAGE_LABELS[lang]}
                  </option>
                ))}
              </select>
            </div>
            {mode === "edit" && (
              <div className="field">
                <label>Giọng đọc thương hiệu (voice cloning) — {NARRATION_LANGUAGE_LABELS[draft.primaryLanguage]}</label>
                <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                  Upload 1 mẫu audio giọng đọc — dùng làm giọng cố định cho MỌI video của kênh này khi sinh narration bằng provider hỗ trợ voice cloning (OmniVoice). Không bắt buộc — bỏ trống thì dùng giọng mặc định của provider. Đây là mẫu cho NGÔN NGỮ CHÍNH ở trên — mẫu cho các ngôn ngữ khác cấu hình ở mục riêng bên dưới.
                </div>
                {draft.voiceCloneRefPath ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <audio controls style={{ flex: 1, height: 32, minWidth: 160 }} src={`${api.voiceSampleUrl(channelId!)}?v=${voiceCacheBust}`} />
                    <AddToLibraryButton kind="voice" sourceUrl={`${api.voiceSampleUrl(channelId!)}?v=${voiceCacheBust}`} name="giong-thuong-hieu" />
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 12, padding: "5px 8px", flex: "none" }}
                      onClick={() => {
                        set("voiceCloneRefPath", "");
                        setVoiceNotice(null);
                      }}
                    >
                      Xoá
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      ref={voiceFileRef}
                      type="file"
                      accept="audio/wav,audio/mpeg,audio/mp3"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadVoiceSample(f);
                      }}
                    />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => voiceFileRef.current?.click()} disabled={uploadingVoice}>
                      {uploadingVoice ? "Đang tải lên..." : "Upload mẫu giọng"}
                    </button>
                    <LibraryPicker kinds={["voice"]} disabled={uploadingVoice} onPick={uploadVoiceSample} />
                  </div>
                )}
                {voiceNotice && <div style={{ fontSize: 12, color: "var(--color-accent)", marginTop: 4 }}>{voiceNotice}</div>}
                {voiceError && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{voiceError}</div>}
              </div>
            )}
            {mode === "edit" && (
              <div className="field">
                <label>Giọng đọc mẫu cho ngôn ngữ khác (thị trường nước ngoài)</label>
                <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                  Tuỳ chọn — mỗi ngôn ngữ 1 mẫu giọng clone riêng, dùng khi sinh giọng đọc ngôn ngữ đó ở Script Studio. Bỏ trống ngôn ngữ nào thì giọng đọc ngôn ngữ đó dùng giọng mặc định của provider (vẫn sinh được, chỉ không phải giọng nhân bản).
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {NARRATION_LANGUAGES.filter((lang) => lang !== draft.primaryLanguage).map((lang) => (
                    <VoiceSampleLangRow
                      key={lang}
                      channelId={channelId!}
                      lang={lang}
                      path={draft.voiceCloneRefPaths[lang] || ""}
                      onChange={(path) => set("voiceCloneRefPaths", { ...draft.voiceCloneRefPaths, [lang]: path })}
                    />
                  ))}
                </div>
              </div>
            )}
            {mode === "edit" && (
              <div className="field">
                <label>Video/Audio thương hiệu (intro)</label>
                <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                  Phát ở ĐẦU mọi video của kênh này khi ghép MP4. Chỉ được chọn 1 trong 2 — upload audio sẽ thay video (và ngược lại). Nếu chỉ có audio, sẽ dùng ảnh của shot đầu tiên trong từng project làm hình minh hoạ. Không bắt buộc. 1 project cụ thể có thể tự có shot mở đầu riêng (Visual Studio) để ghi đè mục này.
                </div>
                {draft.introVideoPath || draft.introAudioPath ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {draft.introVideoPath ? (
                      // eslint-disable-next-line jsx-a11y/media-has-caption
                      <video controls style={{ flex: 1, maxHeight: 120, minWidth: 160 }} src={`${api.brandIntroUrl(channelId!)}?v=${introCacheBust}`} />
                    ) : (
                      // eslint-disable-next-line jsx-a11y/media-has-caption
                      <audio controls style={{ flex: 1, height: 32, minWidth: 160 }} src={`${api.brandIntroUrl(channelId!)}?v=${introCacheBust}`} />
                    )}
                    <AddToLibraryButton
                      kind={draft.introVideoPath ? "video" : "music"}
                      sourceUrl={`${api.brandIntroUrl(channelId!)}?v=${introCacheBust}`}
                      name="intro-thuong-hieu"
                    />
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: 12, padding: "5px 8px", flex: "none" }}
                      onClick={removeBrandIntro}
                      disabled={uploadingIntro}
                    >
                      {uploadingIntro ? "Đang xoá..." : "Xoá"}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      ref={introVideoFileRef}
                      type="file"
                      accept="video/mp4,video/webm,video/quicktime"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadBrandIntro(f);
                      }}
                    />
                    <input
                      ref={introAudioFileRef}
                      type="file"
                      accept="audio/wav,audio/mpeg,audio/mp3"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadBrandIntro(f);
                      }}
                    />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => introVideoFileRef.current?.click()} disabled={uploadingIntro}>
                      {uploadingIntro ? "Đang tải lên..." : "Upload video"}
                    </button>
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => introAudioFileRef.current?.click()} disabled={uploadingIntro}>
                      {uploadingIntro ? "Đang tải lên..." : "Upload audio"}
                    </button>
                    <LibraryPicker kinds={["video", "music"]} disabled={uploadingIntro} onPick={uploadBrandIntro} />
                  </div>
                )}
                {introError && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{introError}</div>}
              </div>
            )}
            {mode === "edit" && (
              <div className="field">
                <label>Nhạc nền mặc định của kênh</label>
                <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                  Phát đè liên tục dưới TOÀN BỘ video (kể cả intro) khi ghép MP4 cho mọi project của kênh này. Không bắt buộc — 1 project cụ thể có thể tự override riêng ở Visual Studio.
                </div>
                {draft.bgMusicPath ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <audio controls style={{ flex: 1, height: 32, minWidth: 160 }} src={`${api.brandBgMusicUrl(channelId!)}?v=${bgMusicCacheBust}`} />
                    <AddToLibraryButton kind="music" sourceUrl={`${api.brandBgMusicUrl(channelId!)}?v=${bgMusicCacheBust}`} name="nhac-nen-kenh" />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px", flex: "none" }} onClick={removeBgMusic} disabled={uploadingBgMusic}>
                      {uploadingBgMusic ? "Đang xoá..." : "Xoá"}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      ref={bgMusicFileRef}
                      type="file"
                      accept="audio/wav,audio/mpeg,audio/mp3"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadBgMusic(f);
                      }}
                    />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => bgMusicFileRef.current?.click()} disabled={uploadingBgMusic}>
                      {uploadingBgMusic ? "Đang tải lên..." : "Upload nhạc nền"}
                    </button>
                    <LibraryPicker kinds={["music"]} disabled={uploadingBgMusic} onPick={uploadBgMusic} />
                  </div>
                )}
                {draft.bgMusicPath && (
                  <div style={{ marginTop: 8 }}>
                    <label style={{ fontSize: 11 }}>Âm lượng nhạc nền so với giọng đọc chính ({Math.round(parseFloat(draft.bgMusicVolume) * 100)}%)</label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={draft.bgMusicVolume}
                      onChange={(e) => set("bgMusicVolume", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>
                )}
                {bgMusicError && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{bgMusicError}</div>}
              </div>
            )}
            {mode === "edit" && (
              <div className="field">
                <label>Hiệu ứng lớp phủ mặc định của kênh (VD mưa/tuyết rơi)</label>
                <div style={{ fontSize: 11.5, opacity: 0.65, marginBottom: 6 }}>
                  1 video hiệu ứng (quay nền đen — mưa/tuyết/bụi/light leak...) blend đè liên tục lên TOÀN BỘ video (kể cả intro) khi ghép MP4 cho mọi project của kênh này. Không bắt buộc — 1 project cụ thể có thể tự override riêng ở Visual Studio.
                </div>
                {draft.overlayEffectPath ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <video controls muted style={{ flex: 1, maxHeight: 120, minWidth: 160 }} src={`${api.brandOverlayUrl(channelId!)}?v=${overlayCacheBust}`} />
                    <AddToLibraryButton kind="video" sourceUrl={`${api.brandOverlayUrl(channelId!)}?v=${overlayCacheBust}`} name="overlay-kenh" />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px", flex: "none" }} onClick={removeOverlay} disabled={uploadingOverlay}>
                      {uploadingOverlay ? "Đang xoá..." : "Xoá"}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      ref={overlayFileRef}
                      type="file"
                      accept="video/mp4,video/webm,video/quicktime"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadOverlay(f);
                      }}
                    />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => overlayFileRef.current?.click()} disabled={uploadingOverlay}>
                      {uploadingOverlay ? "Đang tải lên..." : "Upload hiệu ứng lớp phủ"}
                    </button>
                    <LibraryPicker kinds={["video"]} disabled={uploadingOverlay} onPick={uploadOverlay} />
                  </div>
                )}
                {draft.overlayEffectPath && (
                  <div style={{ marginTop: 8 }}>
                    <label style={{ fontSize: 11 }}>Cường độ hiệu ứng ({Math.round(parseFloat(draft.overlayEffectOpacity) * 100)}%)</label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={draft.overlayEffectOpacity}
                      onChange={(e) => set("overlayEffectOpacity", e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </div>
                )}
                {overlayError && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{overlayError}</div>}
              </div>
            )}
            <div className="field">
              <label>Retention Benchmark</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                <div>
                  <label style={{ fontSize: 11 }}>Hook Strength (0-1)</label>
                  <input className="input" type="number" min={0} max={1} step={0.05} value={draft.targetHookStrength} onChange={(e) => set("targetHookStrength", e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11 }}>Anchor gap (giây)</label>
                  <input className="input" type="number" min={5} value={draft.maxAnchorGapSec} onChange={(e) => set("maxAnchorGapSec", e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: 11 }}>Body tối thiểu (đoạn)</label>
                  <input className="input" type="number" min={1} value={draft.targetBodyLenMin} onChange={(e) => set("targetBodyLenMin", e.target.value)} />
                </div>
              </div>
            </div>
          </>
        )}
        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Hủy
          </button>
          <button className="btn btn-primary" disabled={!draft.name.trim() || saving || loading} onClick={save}>
            {saving ? "Đang lưu..." : mode === "create" ? "Tạo kênh" : "Lưu thay đổi"}
          </button>
        </div>
      </div>
    </div>
  );
}

// 1 hàng mẫu giọng clone cho 1 NGÔN NGỮ (khác ngôn ngữ chính) — giọng đọc đa ngôn ngữ,
// mới 2026-09-04. Tự quản lý state upload/xoá/cache-bust RIÊNG (thay vì nhân bản 5 bộ
// useState trong component cha) — chỉ báo lại path mới cho draft qua `onChange`, xoá là
// cục bộ (persist thật khi bấm "Lưu thay đổi" ở form cha, cùng nguyên tắc `voiceCloneRefPath`
// đơn — KHÁC `removeBrandIntro`/`removeBgMusic`/`removeOverlay` vốn persist NGAY vì đó là
// field ĐƠN dễ gây trạng thái lửng lơ hơn khi có nhiều upload khác xen giữa).
function VoiceSampleLangRow({ channelId, lang, path, onChange }: { channelId: string; lang: NarrationLanguage; path: string; onChange: (path: string) => void }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const result = await api.uploadVoiceSampleLang(channelId, lang, file);
      onChange(result.voice_clone_ref_paths?.[lang] || "");
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload mẫu giọng.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span style={{ fontSize: 12, width: 168, flex: "none" }}>{NARRATION_LANGUAGE_LABELS[lang]}</span>
      {path ? (
        <>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio controls style={{ flex: 1, height: 28, minWidth: 140 }} src={`${api.voiceSampleLangUrl(channelId, lang)}?v=${cacheBust}`} />
          <button className="btn btn-secondary" style={{ fontSize: 11.5, padding: "4px 8px", flex: "none" }} onClick={() => onChange("")}>
            Xoá
          </button>
        </>
      ) : (
        <>
          <input
            ref={fileRef}
            type="file"
            accept="audio/wav,audio/mpeg,audio/mp3"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
            }}
          />
          <button className="btn btn-secondary" style={{ fontSize: 11.5, padding: "4px 8px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Đang tải lên..." : "Upload mẫu giọng"}
          </button>
        </>
      )}
      {error && <div style={{ fontSize: 11, color: "var(--color-danger)", width: "100%" }}>{error}</div>}
    </div>
  );
}
