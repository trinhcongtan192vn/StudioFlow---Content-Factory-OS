import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ProviderOut } from "../../api/types";

const GROUPS = ["llm", "tts", "image", "video"] as const;
const GROUP_LABEL: Record<string, string> = { llm: "LLM", tts: "TTS", image: "Image", video: "Video" };

// Khớp CLOUD_MODELS trong backend/app/routers/providers.py — danh sách model hiện có
// mỗi provider, chọn ngay lúc thêm thay vì phải sửa lại sau (phản hồi phần "còn thiếu"
// mục 3a: triển khai hỗ trợ model API ngay từ bước thêm provider). Đối chiếu lại với
// tài liệu chính thức từng hãng 2026-08-12 — xem PRICING trong từng adapter backend
// (app/providers/claude.py|openai_provider.py|gemini.py) để biết giá mỗi model.
const CLOUD_CATALOG: Record<string, { provider_name: string; display_name: string; models: string[] }[]> = {
  llm: [
    { provider_name: "claude", display_name: "Anthropic Claude", models: ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"] },
    { provider_name: "openai", display_name: "OpenAI GPT", models: ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"] },
    { provider_name: "gemini", display_name: "Google Gemini", models: ["gemini-3.6-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"] },
  ],
  tts: [
    { provider_name: "vbee", display_name: "Vbee", models: ["vbee-female-01", "vbee-male-01"] },
    { provider_name: "elevenlabs", display_name: "ElevenLabs", models: ["eleven_v3", "eleven_turbo"] },
    { provider_name: "openai", display_name: "OpenAI TTS", models: ["gpt-4o-mini-tts", "tts-1-hd", "tts-1"] },
    { provider_name: "gemini", display_name: "Gemini TTS", models: ["gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts", "gemini-2.5-flash-preview-tts"] },
  ],
  image: [
    { provider_name: "flux", display_name: "Flux (Black Forest Labs)", models: ["flux-2-pro", "flux-2-max", "flux-2-flex", "flux-2-klein-9b", "flux-2-klein-4b"] },
    { provider_name: "flux_kontext", display_name: "Flux Kontext (fluxapi.ai)", models: ["flux-kontext-pro", "flux-kontext-max"] },
    { provider_name: "midjourney", display_name: "Midjourney", models: ["v6"] },
    { provider_name: "openai", display_name: "OpenAI Image (GPT Image)", models: ["gpt-image-2", "gpt-image-1-mini"] },
    { provider_name: "gemini", display_name: "Gemini Image (Nano Banana)", models: ["gemini-3-pro-image", "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image"] },
  ],
  video: [
    { provider_name: "runway", display_name: "Runway", models: ["gen-4", "gen-3-alpha"] },
    { provider_name: "sora", display_name: "Sora (OpenAI)", models: ["sora-2", "sora-2-pro"] },
    { provider_name: "veo", display_name: "Google Veo", models: ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"] },
    { provider_name: "flux", display_name: "Flux 3 Video (Black Forest Labs)", models: ["flux-3-video-hd", "flux-3-video-fhd"] },
  ],
};

// Provider local (connection_type="local_endpoint") theo từng nhóm task — mở rộng từ
// chỉ LLM (Ollama/vLLM/LM Studio) sang cả tts/image/video (piper/local_sdxl/local_wan),
// xem backend/app/providers/factory.py::_build_asset_provider + IMPLEMENTATION_REPORT.md.
// MẢNG (không phải 1 lựa chọn/nhóm) — từ khi có OmniVoice làm lựa chọn TTS local THỨ 2
// (song song Piper), cùng dạng CLOUD_CATALOG (có <select> chọn provider khi >1 lựa chọn).
type LocalCatalogEntry = { provider_name: string; display_name: string; endpoint_url: string; model_name: string; needs_endpoint: boolean; hint: string };
const LOCAL_CATALOG: Record<string, LocalCatalogEntry[]> = {
  llm: [
    {
      provider_name: "local",
      display_name: "Local GPU (Ollama)",
      endpoint_url: "http://localhost:11434/v1",
      model_name: "qwen3:14b",
      needs_endpoint: true,
      hint: "Dùng cho model mã nguồn mở chạy tại máy có GPU (Qwen, DeepSeek, Kimi…) qua endpoint OpenAI-compatible — Ollama, vLLM, LM Studio. Chi phí $0, dữ liệu không rời máy.",
    },
  ],
  tts: [
    {
      provider_name: "piper",
      display_name: "Piper TTS (local, CPU)",
      endpoint_url: "",
      model_name: "vi_VN-vais1000-medium",
      needs_endpoint: false,
      hint: "Piper chạy in-process (không cần endpoint mạng) — tải giọng .onnx về backend/models/piper/ trước (xem IMPLEMENTATION_REPORT.md). Điền đúng tên file giọng (không kèm .onnx) vào ô Model.",
    },
    {
      provider_name: "omnivoice",
      display_name: "OmniVoice (local GPU, voice cloning)",
      endpoint_url: "http://127.0.0.1:8199",
      model_name: "omnivoice",
      needs_endpoint: true,
      hint: "Nhân bản giọng (zero-shot voice cloning) từ audio mẫu — cần cài + chạy OmniVoice server riêng trước (mặc định cổng 8199, venv tách biệt — xem IMPLEMENTATION_REPORT.md). Dùng chung giọng thương hiệu qua BrandProfile nếu có cấu hình.",
    },
  ],
  image: [
    {
      provider_name: "local_sdxl",
      display_name: "ComfyUI SDXL (local GPU)",
      endpoint_url: "http://127.0.0.1:8188",
      // Trước là "sdxl" (placeholder không phải tên file thật, chưa từng có tác dụng) —
      // mới (2026-08-22): field này giờ ĐIỀU KHIỂN THẬT checkpoint dùng để sinh ảnh, để
      // trống dùng mặc định của app (xem hint bên dưới).
      model_name: "",
      needs_endpoint: true,
      hint: "Cần cài + chạy ComfyUI trước (mặc định cổng 8188). Để trống ô Model dùng checkpoint mặc định của app — hoặc điền ĐÚNG tên file .safetensors đang có trong thư mục ComfyUI/models/checkpoints (VD sau khi đổi sang checkpoint fine-tune) để đổi checkpoint mà không cần sửa code.",
    },
  ],
  video: [
    {
      provider_name: "local_wan",
      display_name: "ComfyUI Wan2.2 (local GPU)",
      endpoint_url: "http://127.0.0.1:8188",
      model_name: "wan2.2-ti2v-5b",
      needs_endpoint: true,
      hint: "Cùng ComfyUI với Image (cổng 8188) — cần checkpoint Wan2.2 TI2V-5B đã tải sẵn.",
    },
  ],
};

/** Dropdown checkpoint/LoRA THẬT lấy từ ComfyUI đang chạy — **mới (2026-08-22)**, theo
 * yêu cầu người dùng: cho CHỌN thay vì phải tự gõ đúng tên file (dễ gõ sai, không biết
 * ComfyUI thật đang có file nào). Dùng chung cho ô "Model" của provider `local_sdxl`
 * (kind="checkpoints") LẪN ô "Style LoRA" ở ChannelDialog.tsx (kind="loras") — cùng 1
 * ComfyUI, cùng cơ chế liệt kê (xem `api.listLocalSdxlModels`).
 * ComfyUI chưa chạy/không kết nối được → fallback về ô nhập tay (KHÔNG chặn cấu hình,
 * chỉ mất tiện ích chọn nhanh) kèm thông báo lỗi rõ ràng. */
export function ComfyModelSelect({
  kind, value, baseUrl, onChange, placeholder, emptyLabel,
}: {
  kind: "checkpoints" | "loras";
  value: string;
  baseUrl: string;
  onChange: (v: string) => void;
  placeholder?: string;
  emptyLabel: string;
}) {
  const [models, setModels] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listLocalSdxlModels(kind, baseUrl || undefined)
      .then((res) => {
        if (!cancelled) {
          setModels(res.models);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "Không kết nối được ComfyUI để lấy danh sách.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [kind, baseUrl]);

  if (loading) {
    return <input className="input" value={value} disabled placeholder="Đang tải danh sách từ ComfyUI..." />;
  }
  if (error || !models) {
    return (
      <div>
        <input className="input" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
        <div style={{ fontSize: 11, color: "var(--color-danger)", marginTop: 4 }}>{error || "Không lấy được danh sách — nhập tay tên file."}</div>
      </div>
    );
  }
  // Giá trị hiện có nhưng ComfyUI không (còn) thấy file đó (VD đã xoá/đổi tên) — vẫn hiện
  // trong dropdown để không "mất" cấu hình đang lưu, không tự ý reset về rỗng.
  const options = value && !models.includes(value) ? [value, ...models] : models;
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{emptyLabel}</option>
      {options.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
    </select>
  );
}

export default function ProviderSettings() {
  const [group, setGroup] = useState<(typeof GROUPS)[number]>("llm");
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [testing, setTesting] = useState<Record<number, boolean>>({});
  const [testResult, setTestResult] = useState<Record<number, { ok: boolean; message: string }>>({});
  const [editingKey, setEditingKey] = useState<Record<number, boolean>>({});
  const [keyDraft, setKeyDraft] = useState<Record<number, string>>({});
  const [savingKey, setSavingKey] = useState<Record<number, boolean>>({});

  async function load() {
    setProviders(await api.listProviders());
  }
  useEffect(() => {
    load();
  }, []);

  const inGroup = providers.filter((p) => p.task === group);
  const defaultProvider = inGroup.find((p) => p.is_default);
  const fallbackProvider = inGroup.find((p) => p.is_fallback);

  async function test(id: number) {
    setProviders((ps) => ps.map((p) => (p.id === id ? { ...p, status: "untested" } : p)));
    setTesting((t) => ({ ...t, [id]: true }));
    try {
      const result = await api.testProvider(id);
      setTestResult((r) => ({ ...r, [id]: result }));
    } catch (e) {
      setTestResult((r) => ({ ...r, [id]: { ok: false, message: e instanceof ApiError ? e.message : "Có lỗi khi test kết nối." } }));
    } finally {
      setTesting((t) => ({ ...t, [id]: false }));
      await load();
    }
  }

  async function setDefault(id: number) {
    await api.patchProvider(id, { is_default: true });
    await load();
  }
  async function setFallback(id: number | null) {
    if (id) await api.patchProvider(id, { is_fallback: true });
    else {
      const cur = inGroup.find((p) => p.is_fallback);
      if (cur) await api.patchProvider(cur.id, { is_fallback: false });
    }
    await load();
  }
  async function remove(id: number) {
    if (!confirm("Xóa provider này? Thao tác không hoàn tác được.")) return;
    await api.deleteProvider(id);
    await load();
  }

  function startEditKey(id: number) {
    setKeyDraft((d) => ({ ...d, [id]: "" }));
    setEditingKey((e) => ({ ...e, [id]: true }));
  }
  function cancelEditKey(id: number) {
    setEditingKey((e) => ({ ...e, [id]: false }));
  }
  async function saveKey(id: number) {
    const value = (keyDraft[id] || "").trim();
    if (!value) return;
    setSavingKey((s) => ({ ...s, [id]: true }));
    try {
      await api.patchProvider(id, { api_key: value });
      setEditingKey((e) => ({ ...e, [id]: false }));
      await load();
    } finally {
      setSavingKey((s) => ({ ...s, [id]: false }));
    }
  }

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Provider AI</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-4)" }}>Kết nối &amp; test provider. Đội nội dung không bao giờ chạm API key.</p>

      <div className="seg" style={{ marginBottom: "var(--space-4)", maxWidth: 340 }}>
        {GROUPS.map((g) => (
          <label key={g} className={`seg-opt ${group === g ? "active" : ""}`} onClick={() => setGroup(g)}>
            {GROUP_LABEL[g]}
          </label>
        ))}
      </div>

      <div className="card elev-sm" style={{ gap: "var(--space-2)", marginBottom: "var(--space-3)", maxWidth: 640 }}>
        <div className="card-kicker">Mặc định cho {GROUP_LABEL[group]}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Provider mặc định</label>
            <select className="input" value={defaultProvider?.id ?? ""} onChange={(e) => setDefault(Number(e.target.value))}>
              <option value="" disabled>
                — chọn —
              </option>
              {inGroup
                .filter((p) => p.enabled)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name} ({p.model_name || "chưa chọn model"})
                  </option>
                ))}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label>Fallback</label>
            <select className="input" value={fallbackProvider?.id ?? ""} onChange={(e) => setFallback(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Không có</option>
              {inGroup
                .filter((p) => p.enabled && p.id !== defaultProvider?.id)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
            </select>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", maxWidth: 640, marginBottom: "var(--space-2)" }}>
        <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => setAddOpen(true)}>
          + Thêm provider
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: "var(--space-3)", maxWidth: 640 }}>
        {inGroup.map((pv) => (
          <div key={pv.id} className="card elev-sm" style={{ gap: "var(--space-2)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: pv.status === "ok" ? "var(--color-accent)" : pv.status === "error" ? "var(--color-danger)" : "var(--color-neutral-600)", flex: "none" }} />
                <span className="card-title" style={{ fontSize: 14 }}>
                  {pv.display_name}
                </span>
                <span className="tag tag-outline" style={{ fontSize: 10 }}>
                  {pv.connection_type === "local_endpoint" ? "Local" : "Cloud"}
                </span>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => test(pv.id)} disabled={testing[pv.id]}>
                  {testing[pv.id] ? "Đang test..." : "Test"}
                </button>
                <button className="btn btn-icon btn-secondary" style={{ width: 28, height: 28, color: "var(--color-danger)" }} title="Xóa" onClick={() => remove(pv.id)}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18" />
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  </svg>
                </button>
              </div>
            </div>

            {!testing[pv.id] && testResult[pv.id] && (
              <div
                style={{
                  fontSize: 12,
                  padding: "6px 8px",
                  borderRadius: "var(--radius-sm)",
                  background: testResult[pv.id].ok ? "var(--color-accent-900)" : "var(--color-danger-bg)",
                  color: testResult[pv.id].ok ? "var(--color-accent-100)" : "var(--color-danger)",
                }}
              >
                {testResult[pv.id].ok ? "✓ " : "✗ "}
                {testResult[pv.id].message}
              </div>
            )}

            {pv.connection_type === "local_endpoint" && pv.provider_name !== "mock" ? (
              <div className="field" style={{ margin: 0 }}>
                {(() => {
                  const localEntry = LOCAL_CATALOG[pv.task]?.find((c) => c.provider_name === pv.provider_name);
                  return (
                    <>
                      {localEntry?.needs_endpoint !== false && (
                        <>
                          <label>Endpoint URL</label>
                          <input className="input" defaultValue={pv.endpoint_url || ""} onBlur={(e) => api.patchProvider(pv.id, { endpoint_url: e.target.value }).then(load)} placeholder={localEntry?.endpoint_url} />
                        </>
                      )}
                      <label style={{ marginTop: 6 }}>Model</label>
                      {pv.provider_name === "local_sdxl" ? (
                        <ComfyModelSelect
                          kind="checkpoints"
                          value={pv.model_name || ""}
                          baseUrl={pv.endpoint_url || ""}
                          onChange={(v) => api.patchProvider(pv.id, { model_name: v }).then(load)}
                          emptyLabel="— Mặc định app (Painter's Checkpoint) —"
                        />
                      ) : (
                        <input className="input" defaultValue={pv.model_name || ""} onBlur={(e) => api.patchProvider(pv.id, { model_name: e.target.value }).then(load)} placeholder={localEntry?.model_name} />
                      )}
                    </>
                  );
                })()}
              </div>
            ) : pv.available_models.length > 0 ? (
              <div className="field" style={{ margin: 0 }}>
                <label>Model mặc định</label>
                <select className="input" value={pv.model_name || ""} onChange={(e) => api.patchProvider(pv.id, { model_name: e.target.value }).then(load)}>
                  {pv.available_models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
                <label style={{ marginTop: 6 }}>API Key</label>
                {editingKey[pv.id] ? (
                  <div style={{ display: "flex", gap: 6 }}>
                    <input
                      className="input"
                      type="password"
                      autoFocus
                      placeholder="sk-..."
                      value={keyDraft[pv.id] || ""}
                      onChange={(e) => setKeyDraft((d) => ({ ...d, [pv.id]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveKey(pv.id);
                        if (e.key === "Escape") cancelEditKey(pv.id);
                      }}
                    />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "0 10px", flex: "none" }} onClick={() => cancelEditKey(pv.id)}>
                      Hủy
                    </button>
                    <button
                      className="btn btn-primary"
                      style={{ fontSize: 12, padding: "0 10px", flex: "none" }}
                      onClick={() => saveKey(pv.id)}
                      disabled={!keyDraft[pv.id]?.trim() || savingKey[pv.id]}
                    >
                      {savingKey[pv.id] ? "Đang lưu..." : "Lưu"}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 6 }}>
                    <input className="input" readOnly value={pv.key_display || "(chưa có key)"} />
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "0 10px", flex: "none" }} onClick={() => startEditKey(pv.id)}>
                      Sửa
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.5, padding: "var(--space-2)", borderRadius: "var(--radius-sm)", background: "var(--color-neutral-800)", color: "color-mix(in srgb, var(--color-text) 75%, transparent)" }}>
                <div>Chưa cấu hình đầy đủ. Dùng "+ Thêm provider" để nhập key/endpoint.</div>
              </div>
            )}
            <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
              {pv.is_default && <span className="tag tag-accent">Mặc định</span>}
              {pv.is_fallback && <span className="tag tag-neutral">Fallback</span>}
            </div>
          </div>
        ))}
        {inGroup.length === 0 && (
          <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.5, padding: "var(--space-2)", borderRadius: "var(--radius-sm)", background: "var(--color-neutral-800)" }}>
            Chưa có provider {GROUP_LABEL[group]} nào. Bấm "+ Thêm provider" để kết nối.
          </div>
        )}
      </div>

      {addOpen && (
        <AddProviderDialog
          group={group}
          onClose={() => setAddOpen(false)}
          onCreated={async () => {
            await load();
            setAddOpen(false);
          }}
        />
      )}
    </div>
  );
}

function AddProviderDialog({ group, onClose, onCreated }: { group: string; onClose: () => void; onCreated: () => void }) {
  const [connectionType, setConnectionType] = useState<"cloud_api" | "local_endpoint">("cloud_api");
  const [providerName, setProviderName] = useState(CLOUD_CATALOG[group][0]?.provider_name || "");
  const [displayName, setDisplayName] = useState(CLOUD_CATALOG[group][0]?.display_name || "");
  const [cloudModel, setCloudModel] = useState(CLOUD_CATALOG[group][0]?.models[0] || "");
  const [apiKey, setApiKey] = useState("");
  const localCatalog = LOCAL_CATALOG[group] || [];
  const [localProviderName, setLocalProviderName] = useState(localCatalog[0]?.provider_name || "");
  const selectedLocalCatalog = localCatalog.find((c) => c.provider_name === localProviderName);
  const [endpointUrl, setEndpointUrl] = useState(localCatalog[0]?.endpoint_url || "");
  const [localDisplayName, setLocalDisplayName] = useState(localCatalog[0]?.display_name || "");
  const [modelName, setModelName] = useState(localCatalog[0]?.model_name || "");
  const [saving, setSaving] = useState(false);

  // Sau khi thêm, test connection NGAY trong dialog (không bắt tự bấm Test riêng sau
  // khi đã đóng dialog) — createdId != null nghĩa là đã lưu provider, dialog chuyển
  // sang hiển thị kết quả test thay vì form nhập liệu.
  const [createdId, setCreatedId] = useState<number | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [retryKey, setRetryKey] = useState("");
  const [retrying, setRetrying] = useState(false);

  const selectedCatalog = CLOUD_CATALOG[group].find((c) => c.provider_name === providerName);

  async function runTest(id: number) {
    setTesting(true);
    try {
      setTestResult(await api.testProvider(id));
    } catch (e) {
      setTestResult({ ok: false, message: e instanceof ApiError ? e.message : "Có lỗi khi test kết nối." });
    } finally {
      setTesting(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      const pv =
        connectionType === "cloud_api"
          ? await api.createProvider({ task: group, provider_name: providerName, display_name: displayName, connection_type: "cloud_api", api_key: apiKey.trim(), model_name: cloudModel })
          : await api.createProvider({ task: group, provider_name: localProviderName, display_name: localDisplayName, connection_type: "local_endpoint", endpoint_url: endpointUrl, model_name: modelName });
      setCreatedId(pv.id);
      await runTest(pv.id);
    } finally {
      setSaving(false);
    }
  }

  async function saveAndRetry() {
    if (!createdId || !retryKey.trim()) return;
    setRetrying(true);
    try {
      await api.patchProvider(createdId, { api_key: retryKey.trim() });
      setRetryKey("");
      await runTest(createdId);
    } finally {
      setRetrying(false);
    }
  }

  if (createdId != null) {
    return (
      <div className="dialog-backdrop" onClick={onCreated}>
        <div className="dialog" style={{ width: "min(460px,100%)" }} onClick={(e) => e.stopPropagation()}>
          <div className="dialog-title">Kết quả kết nối — {displayName || GROUP_LABEL[group]}</div>
          {testing ? (
            <div className="dialog-body">Đang test kết nối...</div>
          ) : (
            testResult && (
              <div
                style={{
                  fontSize: 13,
                  padding: "8px 10px",
                  borderRadius: "var(--radius-sm)",
                  background: testResult.ok ? "var(--color-accent-900)" : "var(--color-danger-bg)",
                  color: testResult.ok ? "var(--color-accent-100)" : "var(--color-danger)",
                }}
              >
                {testResult.ok ? "✓ " : "✗ "}
                {testResult.message}
              </div>
            )
          )}
          {!testing && testResult && !testResult.ok && (
            <div className="field" style={{ marginTop: "var(--space-3)" }}>
              <label>Sửa lại API Key &amp; thử lại</label>
              <div style={{ display: "flex", gap: 6 }}>
                <input className="input" type="password" value={retryKey} onChange={(e) => setRetryKey(e.target.value)} placeholder="sk-..." />
                <button className="btn btn-secondary" style={{ flex: "none" }} disabled={!retryKey.trim() || retrying} onClick={saveAndRetry}>
                  {retrying ? "Đang thử..." : "Lưu & Test lại"}
                </button>
              </div>
            </div>
          )}
          <div className="dialog-actions">
            <button className="btn btn-primary" onClick={onCreated}>
              {testResult?.ok ? "Xong" : "Đóng (vẫn giữ provider đã lưu)"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(460px,100%)" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">Thêm provider — {GROUP_LABEL[group]}</div>
        <div className="field">
          <label>Loại kết nối</label>
          <div className="seg">
            <label className={`seg-opt ${connectionType === "cloud_api" ? "active" : ""}`}>
              <input type="radio" checked={connectionType === "cloud_api"} onChange={() => setConnectionType("cloud_api")} />
              Cloud API
            </label>
            <label className={`seg-opt ${connectionType === "local_endpoint" ? "active" : ""}`}>
              <input type="radio" checked={connectionType === "local_endpoint"} onChange={() => setConnectionType("local_endpoint")} />
              Local (GPU/CPU)
            </label>
          </div>
        </div>

        {connectionType === "cloud_api" ? (
          <>
            <div className="field">
              <label>Nhà cung cấp</label>
              <select
                className="input"
                value={providerName}
                onChange={(e) => {
                  const next = CLOUD_CATALOG[group].find((c) => c.provider_name === e.target.value);
                  setProviderName(e.target.value);
                  setDisplayName(next?.display_name || e.target.value);
                  setCloudModel(next?.models[0] || "");
                }}
              >
                {CLOUD_CATALOG[group].map((c) => (
                  <option key={c.provider_name} value={c.provider_name}>
                    {c.display_name}
                  </option>
                ))}
              </select>
            </div>
            {selectedCatalog && selectedCatalog.models.length > 0 && (
              <div className="field">
                <label>Model</label>
                <select className="input" value={cloudModel} onChange={(e) => setCloudModel(e.target.value)}>
                  {selectedCatalog.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="field">
              <label>API Key</label>
              <input className="input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />
            </div>
          </>
        ) : (
          <>
            {localCatalog.length > 1 && (
              <div className="field">
                <label>Engine</label>
                <select
                  className="input"
                  value={localProviderName}
                  onChange={(e) => {
                    const next = localCatalog.find((c) => c.provider_name === e.target.value);
                    setLocalProviderName(e.target.value);
                    setLocalDisplayName(next?.display_name || e.target.value);
                    setEndpointUrl(next?.endpoint_url || "");
                    setModelName(next?.model_name || "");
                  }}
                >
                  {localCatalog.map((c) => (
                    <option key={c.provider_name} value={c.provider_name}>
                      {c.display_name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div style={{ fontSize: 12, opacity: 0.75 }}>{selectedLocalCatalog?.hint}</div>
            <div className="field">
              <label>Tên hiển thị</label>
              <input className="input" value={localDisplayName} onChange={(e) => setLocalDisplayName(e.target.value)} />
            </div>
            {selectedLocalCatalog?.needs_endpoint && (
              <div className="field">
                <label>Endpoint URL</label>
                <input className="input" value={endpointUrl} onChange={(e) => setEndpointUrl(e.target.value)} placeholder={selectedLocalCatalog.endpoint_url} />
              </div>
            )}
            <div className="field">
              <label>Tên model</label>
              {localProviderName === "local_sdxl" ? (
                <ComfyModelSelect
                  kind="checkpoints"
                  value={modelName}
                  baseUrl={endpointUrl}
                  onChange={setModelName}
                  emptyLabel="— Mặc định app (Painter's Checkpoint) —"
                />
              ) : (
                <input className="input" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder={selectedLocalCatalog?.model_name} />
              )}
            </div>
          </>
        )}

        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Hủy
          </button>
          <button className="btn btn-primary" disabled={saving} onClick={save}>
            {saving ? "Đang lưu & test..." : "Thêm provider"}
          </button>
        </div>
      </div>
    </div>
  );
}
