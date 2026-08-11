import { useState } from "react";
import { api } from "../../api/client";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

export default function VisualStudio({ project, pack, refresh, busy, setBusy }: StepProps) {
  const [regeneratingVisual, setRegeneratingVisual] = useState<Record<string, boolean>>({});
  const [regeneratingAudio, setRegeneratingAudio] = useState<Record<string, boolean>>({});
  const [bulkVisualLoading, setBulkVisualLoading] = useState(false);
  const [bulkTtsLoading, setBulkTtsLoading] = useState(false);
  const body = pack.script?.body || [];

  function snippetFor(ts: number | null) {
    return body.find((b) => b.timestamp_sec === ts)?.audio || "";
  }

  async function patchShot(shotId: string, patch: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string }>) {
    await api.patchShot(project.id, shotId, patch);
  }

  async function toggleType(shotId: string, current: string) {
    const next = current === "image" ? "video" : "image";
    await api.patchShot(project.id, shotId, { visual_type: next });
    await refresh();
  }

  async function regenerateVisual(shotId: string) {
    setRegeneratingVisual((s) => ({ ...s, [shotId]: true }));
    try {
      await api.regenerateShotVisual(project.id, shotId);
      await refresh();
    } finally {
      setRegeneratingVisual((s) => ({ ...s, [shotId]: false }));
    }
  }

  async function regenerateAudio(shotId: string) {
    setRegeneratingAudio((s) => ({ ...s, [shotId]: true }));
    try {
      await api.regenerateShotAudio(project.id, shotId);
      await refresh();
    } finally {
      setRegeneratingAudio((s) => ({ ...s, [shotId]: false }));
    }
  }

  async function generateAllVisual() {
    setBulkVisualLoading(true);
    try {
      await api.generateAllVisual(project.id);
      await refresh();
    } finally {
      setBulkVisualLoading(false);
    }
  }

  async function generateAllTts() {
    setBulkTtsLoading(true);
    try {
      await api.generateAllTts(project.id);
      await refresh();
    } finally {
      setBulkTtsLoading(false);
    }
  }

  async function goPackReview() {
    setBusy(true);
    try {
      await api.buildPack(project.id);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <StepHeader
        title="Visual Studio"
        description="Tạo hình ảnh, video và giọng đọc cho từng shot — theo đúng đoạn script tương ứng."
        actions={
          <>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={generateAllVisual} disabled={bulkVisualLoading}>
              {bulkVisualLoading ? "Đang tạo Visual..." : "Tạo Visual cho toàn bộ block"}
            </button>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={generateAllTts} disabled={bulkTtsLoading}>
              {bulkTtsLoading ? "Đang tạo giọng đọc..." : "Tạo giọng đọc (TTS) cho toàn bộ block"}
            </button>
            <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={goPackReview} disabled={busy}>
              {busy ? "Đang tổng hợp Pack..." : "Xem Production Pack →"}
            </button>
          </>
        }
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 900 }}>
        {pack.shots.map((v) => (
          <div key={v.shot_id} className="card elev-sm" style={{ gap: "var(--space-3)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
                {v.shot_id} · {v.linked_timestamp_sec}s
              </span>
              <span className={`tag ${v.visual_type === "video" ? "tag-accent-2" : "tag-accent"}`} onClick={() => toggleType(v.shot_id, v.visual_type)} style={{ cursor: "pointer" }}>
                {v.visual_type === "video" ? "Video" : "Image"}
              </span>
            </div>
            <div style={{ fontSize: 13, opacity: 0.8, padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>{snippetFor(v.linked_timestamp_sec)}</div>

            <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "var(--space-3)", alignItems: "flex-start" }}>
              <div style={{ height: 100, borderRadius: "var(--radius-sm)", background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", padding: 6 }}>
                <span style={{ fontSize: 11, opacity: regeneratingVisual[v.shot_id] ? 0.75 : 0.55 }}>{regeneratingVisual[v.shot_id] ? "Đang tạo…" : `${v.visual_type === "video" ? "Video" : "Image"} preview`}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                <div className="field" style={{ margin: 0 }}>
                  <label>Hình ảnh &amp; Hiệu ứng (Visual/FX)</label>
                  <textarea className="input" rows={2} style={{ fontSize: 13 }} defaultValue={v.visual_fx} onBlur={(e) => patchShot(v.shot_id, { visual_fx: e.target.value })} />
                </div>
                <div className="field" style={{ margin: 0 }}>
                  <label>Âm thanh &amp; Nhạc nền (Audio/SFX)</label>
                  <textarea className="input" rows={2} style={{ fontSize: 13 }} defaultValue={v.audio_sfx} onBlur={(e) => patchShot(v.shot_id, { audio_sfx: e.target.value })} />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => regenerateVisual(v.shot_id)} disabled={regeneratingVisual[v.shot_id]}>
                    {regeneratingVisual[v.shot_id] ? "Đang tạo lại..." : "Tạo lại Visual"}
                  </button>
                  <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => regenerateAudio(v.shot_id)} disabled={regeneratingAudio[v.shot_id]}>
                    {regeneratingAudio[v.shot_id] ? "Đang tạo lại..." : "Tạo lại giọng đọc"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
