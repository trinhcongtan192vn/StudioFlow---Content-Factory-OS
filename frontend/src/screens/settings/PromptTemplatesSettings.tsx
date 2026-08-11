import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { PromptTemplateOut } from "../../api/types";

const STAGE_LABEL: Record<string, string> = {
  brief: "Brief",
  outline_hook: "Outline & Hook (Gate 1)",
  script: "Script Studio",
  script_revise: "Script Studio — Tạo lại theo góp ý",
  script_breakdown: "Script Studio — Phân rã theo đoạn",
  visual_image: "Visual Studio — Hình ảnh",
  visual_video: "Visual Studio — Video",
  visual_tts: "Visual Studio — Giọng đọc (TTS)",
  thumbnail: "Title, Description & Thumbnail",
};
const STAGE_ORDER = Object.keys(STAGE_LABEL);

// Gom nhóm theo bước quy trình (khớp prototype: PROCESS_STEPS + stageStep()) thay vì
// liệt kê phẳng theo từng stage key — mỗi bước có thể chứa nhiều template.
const PROCESS_STEPS = ["Brief", "Outline & Hook", "Script Studio", "Visual Studio"];
const STAGE_TO_STEP: Record<string, string> = {
  brief: "Brief",
  outline_hook: "Outline & Hook",
  script: "Script Studio",
  script_revise: "Script Studio",
  script_breakdown: "Script Studio",
  visual_image: "Visual Studio",
  visual_video: "Visual Studio",
  visual_tts: "Visual Studio",
  thumbnail: "Visual Studio",
};

export default function PromptTemplatesSettings() {
  const [templates, setTemplates] = useState<PromptTemplateOut[]>([]);
  const [stepFilter, setStepFilter] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<PromptTemplateOut | null>(null);
  const [addingVersion, setAddingVersion] = useState<string | null>(null);
  const [versionDraft, setVersionDraft] = useState({ body: "", note: "" });

  async function load() {
    setTemplates(await api.listPromptTemplates());
  }
  useEffect(() => {
    load();
  }, []);

  const steps = stepFilter === "all" ? PROCESS_STEPS : [stepFilter];
  const groups = steps
    .map((step) => ({ step, items: templates.filter((t) => (STAGE_TO_STEP[t.task] || t.task) === step) }))
    .filter((g) => g.items.length > 0);

  async function setActiveVersion(id: string, version: string) {
    await api.patchPromptTemplate(id, { active_version: version });
    await load();
  }
  async function saveVersion(id: string) {
    if (!versionDraft.body.trim()) return;
    await api.patchPromptTemplate(id, { new_version_body: versionDraft.body, new_version_note: versionDraft.note });
    setAddingVersion(null);
    setVersionDraft({ body: "", note: "" });
    await load();
  }
  async function remove(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!confirm("Xóa prompt template này?")) return;
    await api.deletePromptTemplate(id);
    await load();
  }

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Prompt Templates</h3>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-4)" }}>Thư viện prompt hệ thống, gom theo bước sản xuất — phiên bản hoá, đặt phiên bản mặc định.</p>
        <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px", flex: "none" }} onClick={() => setCreateOpen(true)}>
          + Template mới
        </button>
      </div>
      <div className="seg" style={{ marginBottom: "var(--space-4)", maxWidth: "100%", overflowX: "auto" }}>
        <label className={`seg-opt ${stepFilter === "all" ? "active" : ""}`} onClick={() => setStepFilter("all")} style={{ whiteSpace: "nowrap" }}>
          Tất cả
        </label>
        {PROCESS_STEPS.map((s) => (
          <label key={s} className={`seg-opt ${stepFilter === s ? "active" : ""}`} onClick={() => setStepFilter(s)} style={{ whiteSpace: "nowrap" }}>
            {s}
          </label>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", maxWidth: 720 }}>
        {groups.map((g) => (
          <div key={g.step}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".06em", opacity: 0.55, marginBottom: "var(--space-2)" }}>{g.step}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              {g.items.map((t) => {
                const isOpen = expanded === t.id;
                return (
                  <div key={t.id} className="card">
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <div onClick={() => setExpanded(isOpen ? null : t.id)} style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, cursor: "pointer", flex: 1 }}>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" style={{ transform: isOpen ? "rotate(90deg)" : "none", flex: "none" }}>
                          <polyline points="9 18 15 12 9 6" />
                        </svg>
                        <div style={{ minWidth: 0 }}>
                          <div className="card-title" style={{ fontSize: 14 }}>
                            {t.name}
                          </div>
                          <div style={{ fontSize: 11, opacity: 0.6 }}>
                            {STAGE_LABEL[t.task] || t.task} · {t.active_version} · sửa bởi {t.updated_by}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 4, alignItems: "center", flex: "none" }}>
                        <button
                          className="btn btn-icon btn-secondary"
                          title="Sửa"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditing(t);
                          }}
                          style={{ width: 28, height: 28 }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 20h9" />
                            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                          </svg>
                        </button>
                        <button className="btn btn-icon btn-secondary" title="Xóa" onClick={(e) => remove(e, t.id)} style={{ width: 28, height: 28, color: "var(--color-danger)" }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M3 6h18" />
                            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    {isOpen && (
                      <div style={{ marginTop: "var(--space-2)", paddingTop: "var(--space-2)", borderTop: "1px solid var(--color-divider)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                        <div>
                          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", opacity: 0.55, marginBottom: 3 }}>Prompt đang dùng ({t.active_version})</div>
                          <div style={{ fontFamily: "ui-monospace,monospace", fontSize: 12, background: "var(--color-bg)", borderRadius: "var(--radius-sm)", padding: 8, opacity: 0.85 }}>{t.body}</div>
                        </div>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 3 }}>
                            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", opacity: 0.55 }}>Lịch sử phiên bản</div>
                            <a
                              href="#"
                              onClick={(e) => {
                                e.preventDefault();
                                setAddingVersion(t.id);
                              }}
                              style={{ fontSize: 11 }}
                            >
                              + Phiên bản mới
                            </a>
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            {t.versions.map((v) => (
                              <div key={v.version} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, padding: "4px 0" }}>
                                <span style={{ fontFamily: "ui-monospace,monospace", opacity: 0.8, flex: "none", width: 28 }}>{v.version}</span>
                                <span style={{ opacity: 0.7, flex: 1, minWidth: 0 }}>
                                  {v.note} <span style={{ opacity: 0.55 }}>· {v.updated_by} · {v.updated_at}</span>
                                </span>
                                {v.is_active ? (
                                  <span className="tag tag-accent" style={{ flex: "none" }}>
                                    Mặc định
                                  </span>
                                ) : (
                                  <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px", flex: "none" }} onClick={() => setActiveVersion(t.id, v.version)}>
                                    Đặt mặc định
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                        {addingVersion === t.id && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 6, background: "var(--color-bg)", borderRadius: "var(--radius-sm)", padding: 8 }}>
                            <div className="field" style={{ margin: 0 }}>
                              <label style={{ fontSize: 11 }}>Nội dung prompt</label>
                              <textarea className="input" rows={3} style={{ fontFamily: "ui-monospace,monospace", fontSize: 12 }} value={versionDraft.body} onChange={(e) => setVersionDraft((d) => ({ ...d, body: e.target.value }))} />
                            </div>
                            <div className="field" style={{ margin: 0 }}>
                              <label style={{ fontSize: 11 }}>Ghi chú thay đổi</label>
                              <input className="input" value={versionDraft.note} onChange={(e) => setVersionDraft((d) => ({ ...d, note: e.target.value }))} />
                            </div>
                            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setAddingVersion(null)}>
                                Hủy
                              </button>
                              <button className="btn btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => saveVersion(t.id)}>
                                Lưu phiên bản
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        {groups.length === 0 && <div style={{ opacity: 0.6, fontSize: 13 }}>Chưa có template nào ở bước này.</div>}
      </div>

      {createOpen && (
        <TemplateDialog
          mode="create"
          onClose={() => setCreateOpen(false)}
          onSaved={async () => {
            await load();
            setCreateOpen(false);
          }}
        />
      )}
      {editing && (
        <TemplateDialog
          mode="edit"
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            await load();
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function TemplateDialog({
  mode,
  initial,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  initial?: PromptTemplateOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [task, setTask] = useState(initial?.task || "brief");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!name.trim()) return;
    if (mode === "create" && !body.trim()) return;
    setSaving(true);
    try {
      if (mode === "create") {
        await api.createPromptTemplate({ name: name.trim(), task, body: body.trim() });
      } else {
        await api.patchPromptTemplate(initial!.id, { name: name.trim(), task });
      }
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(520px,100%)" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">{mode === "create" ? "Template mới" : "Sửa template"}</div>
        <div className="field">
          <label>Tên template</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Bước sử dụng trong quy trình</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {STAGE_ORDER.map((s) => (
              <span key={s} className="tag" onClick={() => setTask(s)} style={{ cursor: "pointer", ...(task === s ? { background: "var(--color-accent-800)", color: "var(--color-accent-100)", border: "1px solid var(--color-accent)" } : {}) }}>
                {STAGE_LABEL[s]}
              </span>
            ))}
          </div>
        </div>
        {mode === "create" && (
          <div className="field">
            <label>Nội dung prompt (v1)</label>
            <textarea className="input" rows={4} style={{ fontFamily: "ui-monospace,monospace", fontSize: 12 }} value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
        )}
        {mode === "edit" && (
          <div style={{ fontSize: 11, opacity: 0.6 }}>Sửa nội dung prompt qua "+ Phiên bản mới" trong danh sách — giữ lịch sử phiên bản cũ.</div>
        )}
        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Hủy
          </button>
          <button className="btn btn-primary" disabled={!name.trim() || (mode === "create" && !body.trim()) || saving} onClick={save}>
            {saving ? "Đang lưu..." : mode === "create" ? "Tạo template" : "Lưu thay đổi"}
          </button>
        </div>
      </div>
    </div>
  );
}
