import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { RenderState } from "../../api/types";
import { computeRealStats } from "../../components/packStats";
import StatsBar from "../../components/StatsBar";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

const TABS = [
  { key: "content", label: "Full Script & Shot List" },
  { key: "titles", label: "Title & Thumbnail" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

function formatTimestamp(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="btn btn-icon btn-secondary"
      title="Copy"
      style={{ width: 26, height: 26, flex: "none" }}
      onClick={async (e) => {
        e.stopPropagation();
        if (await copyToClipboard(text)) {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }
      }}
    >
      {copied ? (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
      )}
    </button>
  );
}

export default function PackReview({ project, pack, refresh, busy, setBusy }: StepProps) {
  const [tab, setTab] = useState<TabKey>("content");
  const [returnOpen, setReturnOpen] = useState(false);
  const [returnNote, setReturnNote] = useState("");
  const [description, setDescription] = useState(pack.youtube_meta?.description || "");
  const [thumbDesc, setThumbDesc] = useState(pack.youtube_meta?.thumbnail_description || "");
  const [generatingThumb, setGeneratingThumb] = useState(false);
  const [thumbError, setThumbError] = useState<string | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const [renderState, setRenderState] = useState<RenderState | null>(null);

  useEffect(() => {
    setDescription(pack.youtube_meta?.description || "");
    setThumbDesc(pack.youtube_meta?.thumbnail_description || "");
  }, [pack.youtube_meta?.description, pack.youtube_meta?.thumbnail_description]);

  useEffect(() => {
    api
      .getRenderStatus(project.id)
      .then(setRenderState)
      .catch(() => {
        /* chưa từng sinh asset — bỏ qua, thời lượng thật hiện "—" */
      });
  }, [project.id]);

  function saveYoutubeMeta(patch: Partial<NonNullable<typeof pack.youtube_meta>>) {
    if (!pack.youtube_meta) return;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      api.patchPack(project.id, { youtube_meta: { ...pack.youtube_meta!, ...patch } });
    }, 500);
  }

  async function generateThumbnail() {
    setGeneratingThumb(true);
    setThumbError(null);
    try {
      await api.patchPack(project.id, { youtube_meta: { ...pack.youtube_meta!, thumbnail_description: thumbDesc } });
      await api.generateThumbnail(project.id);
      await refresh();
    } catch (e) {
      setThumbError(e instanceof ApiError ? e.message : "Có lỗi khi sinh ảnh thumbnail.");
    } finally {
      setGeneratingThumb(false);
    }
  }

  const timelineText = (pack.youtube_meta?.chapters || []).map((c) => `${formatTimestamp(c.ts_sec)} - ${c.label}`).join("\n");
  const hashtagsText = (pack.youtube_meta?.hashtags || []).join(" ");
  const fullDescriptionText = [description, timelineText, hashtagsText].filter((s) => s.trim()).join("\n\n");

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
        description={<StatsBar {...computeRealStats(pack, renderState)} />}
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
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: "var(--space-4)", maxWidth: 820 }}>
            <div className="card-kicker">Title</div>
            {pack.titles.map((t, i) => (
              <div key={i} className="card" style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div style={{ fontSize: 13, flex: 1 }}>{t.text}</div>
                <span className="tag tag-outline">{t.angle}</span>
                <CopyButton text={t.text} />
              </div>
            ))}
          </div>

          <div style={{ marginBottom: "var(--space-4)", maxWidth: 820 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <label style={{ margin: 0 }}>Description (gồm SEO + Timeline + Hashtags — sẵn sàng copy vào YouTube Studio)</label>
              <CopyButton text={fullDescriptionText} />
            </div>
            <textarea
              className="input"
              rows={5}
              style={{ fontSize: 13 }}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                saveYoutubeMeta({ description: e.target.value });
              }}
              placeholder="Mô tả SEO cho video..."
            />
            {(pack.youtube_meta?.chapters?.length || pack.youtube_meta?.hashtags?.length) && (
              <div style={{ fontSize: 12, background: "var(--color-bg)", borderRadius: "var(--radius-sm)", padding: 8, marginTop: 6, whiteSpace: "pre-wrap", opacity: 0.75 }}>
                {[timelineText, hashtagsText].filter((s) => s.trim()).join("\n\n")}
                <div style={{ fontSize: 10.5, opacity: 0.7, marginTop: 4 }}>↑ Timeline &amp; Hashtags — tự động gộp cùng Description khi bấm Copy ở trên.</div>
              </div>
            )}
          </div>

          <div style={{ maxWidth: 820 }}>
            <div className="card-kicker" style={{ marginBottom: 6 }}>
              Thumbnail
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "var(--space-3)", alignItems: "flex-start" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ height: 124, borderRadius: "var(--radius-sm)", background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                  {pack.youtube_meta?.thumbnail_status === "ready" ? (
                    <img alt="Thumbnail" src={api.thumbnailUrl(project.id)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  ) : (
                    <span style={{ fontSize: 11, opacity: 0.55, textAlign: "center", padding: 6 }}>
                      {pack.youtube_meta?.thumbnail_status === "generating" ? "Đang sinh ảnh…" : "Chưa có ảnh thumbnail"}
                    </span>
                  )}
                </div>
                <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={generateThumbnail} disabled={generatingThumb || !thumbDesc.trim()}>
                  {generatingThumb ? "Đang tạo..." : "Tạo ảnh Thumbnail bằng AI"}
                </button>
                {pack.youtube_meta?.thumbnail_status === "ready" && (
                  <a className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px", textAlign: "center" }} href={api.thumbnailUrl(project.id)} download="thumbnail.png">
                    Tải ảnh
                  </a>
                )}
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Mô tả thumbnail (prompt tạo ảnh)</label>
                <textarea
                  className="input"
                  rows={3}
                  style={{ fontSize: 13 }}
                  value={thumbDesc}
                  onChange={(e) => {
                    setThumbDesc(e.target.value);
                    saveYoutubeMeta({ thumbnail_description: e.target.value });
                  }}
                />
                {thumbError && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{thumbError}</div>}
                {pack.youtube_meta?.thumbnail_status === "error" && !thumbError && (
                  <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{pack.youtube_meta.thumbnail_error}</div>
                )}
              </div>
            </div>
          </div>
        </>
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
