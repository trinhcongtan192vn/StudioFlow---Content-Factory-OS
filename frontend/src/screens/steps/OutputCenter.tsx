import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { RetentionOut } from "../../api/types";
import type { StepProps } from "../ProjectView";

export default function OutputCenter({ project }: StepProps) {
  const [exporting, setExporting] = useState(false);
  const [files, setFiles] = useState<{ format: string; filename: string }[]>([]);

  async function doExport(format: "json" | "markdown" | "pdf") {
    setExporting(true);
    try {
      const r = await api.exportPack(project.id, format);
      setFiles((f) => [...f.filter((x) => x.format !== format), { format, filename: r.filename }]);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Output Center</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-6)" }}>Chọn cách xuất Production Pack.</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", maxWidth: 720, marginBottom: "var(--space-6)" }}>
        <div className="card elev-sm" style={{ gap: "var(--space-2)" }}>
          <div className="card-kicker">Output A</div>
          <div className="card-title">Export Pack</div>
          <div className="card-body">Xuất spec + prompts — bản máy đọc (JSON) và bản người đọc.</div>
          {files.length === 0 ? (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button className="btn btn-primary btn-block" onClick={() => doExport("markdown")} disabled={exporting}>
                {exporting ? "Đang xuất..." : "Xuất Pack"}
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
              {files.map((f) => (
                <a key={f.format} href={api.downloadUrl(project.id, f.filename)} style={{ fontSize: 12 }} target="_blank" rel="noreferrer">
                  {f.filename}
                </a>
              ))}
              <a
                href="#"
                style={{ fontSize: 12, opacity: 0.7 }}
                onClick={(e) => {
                  e.preventDefault();
                  doExport("json");
                }}
              >
                + xuất JSON
              </a>
            </div>
          )}
        </div>
        <div className="card" style={{ gap: "var(--space-2)", opacity: 0.6 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div className="card-kicker">Output B</div>
            <span className="tag tag-outline">Beta · M2</span>
          </div>
          <div className="card-title">Render in-app</div>
          <div className="card-body">Sinh asset qua API, ghép &amp; xuất MP4 "đủ đăng". Module tách riêng, phát triển độc lập.</div>
          <button className="btn btn-secondary btn-block" disabled>
            Chưa sẵn sàng
          </button>
        </div>
      </div>

      <RetentionCard projectId={project.id} />
    </div>
  );
}

function RetentionCard({ projectId }: { projectId: string }) {
  const [data, setData] = useState<RetentionOut | null>(null);
  const [form, setForm] = useState({ published_at: "", ret_0: "", ret_25: "", ret_50: "", ret_100: "", avg_view_duration: "", thumbnail_ctr: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getRetention(projectId).then(setData);
  }, [projectId]);

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, number | string | null> = { published_at: form.published_at || null };
      for (const k of ["ret_0", "ret_25", "ret_50", "ret_100", "avg_view_duration", "thumbnail_ctr"] as const) {
        body[k] = form[k] === "" ? null : parseFloat(form[k]);
      }
      const r = await api.putRetention(projectId, body);
      setData(r);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ maxWidth: 560, gap: "var(--space-3)" }}>
      <div className="card-kicker">Retention nạp thủ công</div>
      <div style={{ fontSize: 13, opacity: 0.75, marginTop: -4 }}>Sau khi video đã đăng, nhập số liệu thực tế từ YouTube Studio để đối chiếu benchmark kênh.</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "var(--space-2)" }}>
        <NumField label="Ret. 0% (Hook)" value={form.ret_0} onChange={(v) => setForm((f) => ({ ...f, ret_0: v }))} />
        <NumField label="Ret. 25%" value={form.ret_25} onChange={(v) => setForm((f) => ({ ...f, ret_25: v }))} />
        <NumField label="Ret. 50%" value={form.ret_50} onChange={(v) => setForm((f) => ({ ...f, ret_50: v }))} />
        <NumField label="Ret. 100%" value={form.ret_100} onChange={(v) => setForm((f) => ({ ...f, ret_100: v }))} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-2)" }}>
        <NumField label="AVD (giây)" value={form.avg_view_duration} onChange={(v) => setForm((f) => ({ ...f, avg_view_duration: v }))} />
        <NumField label="Thumbnail CTR (%)" value={form.thumbnail_ctr} onChange={(v) => setForm((f) => ({ ...f, thumbnail_ctr: v }))} />
        <div className="field" style={{ margin: 0 }}>
          <label>Ngày đăng</label>
          <input className="input" type="date" value={form.published_at} onChange={(e) => setForm((f) => ({ ...f, published_at: e.target.value }))} />
        </div>
      </div>
      <button className="btn btn-secondary" style={{ alignSelf: "flex-start" }} onClick={save} disabled={saving}>
        {saving ? "Đang lưu..." : "Lưu số liệu"}
      </button>

      {data?.entry && (
        <div style={{ marginTop: "var(--space-2)" }}>
          <div className="hr" style={{ margin: "var(--space-2) 0" }} />
          <div style={{ fontSize: 12, opacity: 0.8 }}>
            Retention tại Hook thực tế: <strong>{data.entry.ret_0 ?? "—"}%</strong> · Benchmark kênh: <strong>{data.target_hook_strength != null ? Math.round(data.target_hook_strength * 100) : "—"}%</strong>
          </div>
          {data.diff_vs_benchmark != null && (
            <div style={{ height: 6, borderRadius: 4, background: "var(--color-neutral-800)", marginTop: 6, overflow: "hidden", position: "relative" }}>
              <div
                style={{
                  height: "100%",
                  width: `${Math.min(100, Math.max(0, 50 + data.diff_vs_benchmark * 100))}%`,
                  background: data.diff_vs_benchmark >= 0 ? "var(--color-accent)" : "var(--color-danger)",
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function NumField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="field" style={{ margin: 0 }}>
      <label>{label}</label>
      <input className="input" type="number" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
