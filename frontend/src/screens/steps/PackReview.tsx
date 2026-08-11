import { useState } from "react";
import { api } from "../../api/client";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

const TABS = [
  { key: "content", label: "Full Script & Shot List" },
  { key: "titles", label: "Title & Thumbnail" },
  { key: "repurpose", label: "Repurposing" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function PackReview({ project, pack, refresh, busy, setBusy }: StepProps) {
  const [tab, setTab] = useState<TabKey>("content");
  const [returnOpen, setReturnOpen] = useState(false);
  const [returnNote, setReturnNote] = useState("");

  const warnings = pack.retention_check?.warnings || [];
  const unresolvedCount = warnings.length;
  const gate2Approved = project.status === "ready_output" || project.status === "exported" || project.status === "published";

  async function approve() {
    setBusy(true);
    try {
      await api.gate2(project.id, { action: "approve" });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function submitReturn() {
    if (!returnNote.trim()) return;
    setBusy(true);
    try {
      await api.gate2(project.id, { action: "return", note: returnNote });
      setReturnOpen(false);
      setReturnNote("");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function goOutput() {
    await api.enterOutput(project.id);
    await refresh();
  }

  return (
    <div>
      <StepHeader
        title="Pack Review"
        actions={
          <>
            <button className="btn btn-primary" disabled={gate2Approved || busy} onClick={approve}>
              Approve
            </button>
            <button className="btn btn-secondary" onClick={() => setReturnOpen(true)} disabled={busy}>
              Trả về
            </button>
            {gate2Approved && (
              <button className="btn btn-ghost" onClick={goOutput}>
                Đi tới Output →
              </button>
            )}
          </>
        }
      />
      <div
        style={{
          display: "flex",
          gap: 10,
          alignItems: "flex-start",
          padding: "var(--space-3)",
          borderRadius: "var(--radius-md)",
          background: "var(--color-accent-900)",
          color: "var(--color-accent-100)",
          marginBottom: "var(--space-4)",
          fontSize: 13,
          maxWidth: 820,
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none", marginTop: 1 }}>
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <div>
          <strong style={{ fontFamily: "var(--font-heading)", fontWeight: 600 }}>★ Human Gate #2</strong> — {unresolvedCount > 0 ? `${unresolvedCount} cảnh báo chưa xử lý.` : "Không có cảnh báo."} Chỉ khi Approve mới mở khoá Output.
        </div>
      </div>

      <div className="seg" style={{ marginBottom: "var(--space-4)" }}>
        {TABS.map((t) => (
          <label key={t.key} className={`seg-opt ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
          </label>
        ))}
      </div>

      {tab === "content" && (
        <>
          <div className="field" style={{ marginBottom: "var(--space-3)" }}>
            <label>Full Script</label>
            <div style={{ fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", padding: 10, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>{pack.script?.full_text}</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
            {(pack.script?.body || []).map((b, i) => (
              <div key={i} className="card" style={{ gap: 4 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
                    {b.timestamp_sec}s
                  </span>
                  {b.warning && <span style={{ fontSize: 12, color: b.warning.severity === "red" ? "var(--color-danger)" : "var(--color-warning)" }}>{b.warning.message}</span>}
                </div>
                <div style={{ fontSize: 13 }}>{b.audio}</div>
                <div style={{ fontSize: 12, opacity: 0.7 }}>
                  Visual: {b.visual} · {b.direction}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div className="card-kicker">Shot List</div>
            {pack.shots.map((s) => (
              <div key={s.shot_id} className="card" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <span className="tag tag-neutral">{s.shot_id}</span>
                <span style={{ fontSize: 12, flex: 1 }}>{s.visual_fx}</span>
                <span className="tag tag-outline">{s.visual_type}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "titles" && (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: "var(--space-4)" }}>
            <div className="card-kicker">Title</div>
            {pack.titles.map((t, i) => (
              <div key={i} className="card" style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div style={{ fontSize: 13 }}>{t.text}</div>
                <span className="tag tag-outline">{t.angle}</span>
              </div>
            ))}
          </div>
          <div className="field" style={{ marginBottom: "var(--space-3)" }}>
            <label>Description (SEO)</label>
            <textarea className="input" rows={5} style={{ fontSize: 13 }} defaultValue={pack.youtube_meta?.description} />
          </div>
          <div style={{ marginBottom: "var(--space-3)" }}>
            <div className="card-kicker" style={{ marginBottom: 4 }}>
              Timeline / Chapters
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {(pack.youtube_meta?.chapters || []).map((c, i) => (
                <div key={i} style={{ display: "flex", gap: 8, fontSize: 13 }}>
                  <span style={{ fontFamily: "ui-monospace,monospace", opacity: 0.7 }}>{c.ts_sec}s</span>
                  <span>{c.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ marginBottom: "var(--space-4)" }}>
            <div className="card-kicker" style={{ marginBottom: 4 }}>
              Hashtags
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {(pack.youtube_meta?.hashtags || []).map((h) => (
                <span key={h} className="tag tag-neutral">
                  {h}
                </span>
              ))}
            </div>
          </div>
          <div>
            <div className="card-kicker" style={{ marginBottom: 6 }}>
              Thumbnail
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "var(--space-3)", alignItems: "flex-start" }}>
              <div style={{ height: 124, borderRadius: "var(--radius-sm)", background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: 11, opacity: 0.55 }}>Thumbnail preview</span>
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Mô tả thumbnail (prompt tạo ảnh)</label>
                <textarea className="input" rows={3} style={{ fontSize: 13 }} defaultValue={pack.youtube_meta?.thumbnail_description} />
              </div>
            </div>
          </div>
        </>
      )}

      {tab === "repurpose" && (
        <div className="card" style={{ alignItems: "flex-start", marginBottom: "var(--space-4)" }}>
          <span className="tag tag-neutral">Có ở M3</span>
          <div style={{ fontSize: 13, opacity: 0.75, marginTop: 4 }}>Repurposing Pack (short-form + Community Post) mở khoá khi lên GA.</div>
        </div>
      )}

      {returnOpen && (
        <div className="dialog-backdrop" onClick={() => setReturnOpen(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-title">Trả về Pack</div>
            <div className="dialog-body">Ghi chú lý do trả về — bắt buộc. Project sẽ quay lại Script Studio, giữ nguyên lịch sử.</div>
            <textarea className="input" rows={3} placeholder="VD: Hook chưa đủ mạnh, cần thêm anchor ở phút 2" value={returnNote} onChange={(e) => setReturnNote(e.target.value)} />
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setReturnOpen(false)}>
                Hủy
              </button>
              <button className="btn btn-primary" disabled={!returnNote.trim()} onClick={submitReturn}>
                Trả về
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
