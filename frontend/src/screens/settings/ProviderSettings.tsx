import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { ProviderOut } from "../../api/types";

const GROUPS = ["llm", "tts", "image", "video"] as const;
const GROUP_LABEL: Record<string, string> = { llm: "LLM", tts: "TTS", image: "Image", video: "Video" };

// Khớp CLOUD_MODELS trong backend/app/routers/providers.py — danh sách model hiện có
// mỗi provider, chọn ngay lúc thêm thay vì phải sửa lại sau (phản hồi phần "còn thiếu"
// mục 3a: triển khai hỗ trợ model API ngay từ bước thêm provider).
const CLOUD_CATALOG: Record<string, { provider_name: string; display_name: string; models: string[] }[]> = {
  llm: [
    { provider_name: "claude", display_name: "Anthropic Claude", models: ["claude-sonnet-4-5", "claude-haiku-4-5"] },
    { provider_name: "openai", display_name: "OpenAI GPT", models: ["gpt-4.1", "gpt-4.1-mini"] },
    { provider_name: "gemini", display_name: "Google Gemini", models: ["gemini-2.5-pro", "gemini-2.5-flash"] },
  ],
  tts: [
    { provider_name: "vbee", display_name: "Vbee", models: ["vbee-female-01", "vbee-male-01"] },
    { provider_name: "elevenlabs", display_name: "ElevenLabs", models: ["eleven_v3", "eleven_turbo"] },
  ],
  image: [
    { provider_name: "flux", display_name: "Flux", models: ["flux-1.1-pro", "flux-schnell"] },
    { provider_name: "midjourney", display_name: "Midjourney", models: ["v6"] },
  ],
  video: [
    { provider_name: "runway", display_name: "Runway", models: ["gen-4", "gen-3-alpha"] },
    { provider_name: "sora", display_name: "Sora", models: ["sora-1"] },
  ],
};

export default function ProviderSettings() {
  const [group, setGroup] = useState<(typeof GROUPS)[number]>("llm");
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});

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
    await api.testProvider(id);
    await load();
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
                <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => test(pv.id)}>
                  Test
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

            {pv.connection_type === "local_endpoint" && pv.provider_name !== "mock" ? (
              <div className="field" style={{ margin: 0 }}>
                <label>Endpoint URL (Ollama/vLLM/LM Studio)</label>
                <input className="input" defaultValue={pv.endpoint_url || ""} onBlur={(e) => api.patchProvider(pv.id, { endpoint_url: e.target.value }).then(load)} placeholder="http://localhost:11434/v1" />
                <label style={{ marginTop: 6 }}>Model</label>
                <input className="input" defaultValue={pv.model_name || ""} onBlur={(e) => api.patchProvider(pv.id, { model_name: e.target.value }).then(load)} placeholder="qwen2.5:32b" />
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
                {group !== "video" && group !== "image" && (
                  <>
                    <label style={{ marginTop: 6 }}>API Key</label>
                    <div style={{ display: "flex", gap: 6 }}>
                      <input className="input" readOnly value={revealed[pv.id] ? "(ẩn — nhập lại để đổi)" : pv.key_display || "(chưa có key)"} />
                      <button className="btn btn-icon btn-secondary" onClick={() => setRevealed((r) => ({ ...r, [pv.id]: !r[pv.id] }))}>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      </button>
                    </div>
                  </>
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
  const [endpointUrl, setEndpointUrl] = useState("http://localhost:11434/v1");
  const [localDisplayName, setLocalDisplayName] = useState("Local GPU (Ollama)");
  const [modelName, setModelName] = useState("qwen2.5:32b");
  const [saving, setSaving] = useState(false);

  const selectedCatalog = CLOUD_CATALOG[group].find((c) => c.provider_name === providerName);

  async function save() {
    setSaving(true);
    try {
      if (connectionType === "cloud_api") {
        await api.createProvider({ task: group, provider_name: providerName, display_name: displayName, connection_type: "cloud_api", api_key: apiKey, model_name: cloudModel });
      } else {
        await api.createProvider({ task: "llm", provider_name: "local", display_name: localDisplayName, connection_type: "local_endpoint", endpoint_url: endpointUrl, model_name: modelName });
      }
      onCreated();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(460px,100%)" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">Thêm provider — {GROUP_LABEL[group]}</div>
        {group === "llm" && (
          <div className="field">
            <label>Loại kết nối</label>
            <div className="seg">
              <label className={`seg-opt ${connectionType === "cloud_api" ? "active" : ""}`}>
                <input type="radio" checked={connectionType === "cloud_api"} onChange={() => setConnectionType("cloud_api")} />
                Cloud API
              </label>
              <label className={`seg-opt ${connectionType === "local_endpoint" ? "active" : ""}`}>
                <input type="radio" checked={connectionType === "local_endpoint"} onChange={() => setConnectionType("local_endpoint")} />
                Local Endpoint (GPU)
              </label>
            </div>
          </div>
        )}

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
            <div style={{ fontSize: 12, opacity: 0.75 }}>
              Dùng cho model mã nguồn mở chạy tại máy có GPU (Qwen, DeepSeek, Kimi…) qua endpoint OpenAI-compatible — Ollama, vLLM, LM Studio. Chi phí $0, dữ liệu không rời máy (PRD §10.2b).
            </div>
            <div className="field">
              <label>Tên hiển thị</label>
              <input className="input" value={localDisplayName} onChange={(e) => setLocalDisplayName(e.target.value)} />
            </div>
            <div className="field">
              <label>Endpoint URL</label>
              <input className="input" value={endpointUrl} onChange={(e) => setEndpointUrl(e.target.value)} placeholder="http://localhost:11434/v1" />
            </div>
            <div className="field">
              <label>Tên model</label>
              <input className="input" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="qwen2.5:32b" />
            </div>
          </>
        )}

        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Hủy
          </button>
          <button className="btn btn-primary" disabled={saving} onClick={save}>
            {saving ? "Đang lưu..." : "Thêm provider"}
          </button>
        </div>
      </div>
    </div>
  );
}
