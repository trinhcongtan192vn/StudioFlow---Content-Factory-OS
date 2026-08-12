import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ProductionPack, ProjectSummary, RenderState, ShotRenderStatus } from "../../api/types";

/** M2 Production Layer — sinh ảnh/video + giọng đọc THẬT cho từng shot (ElevenLabs/
 * OpenAI Image/Sora), human review trước khi ghép MP4 (ffmpeg, backend). Nhúng trong
 * Output Center (thẻ "Render in-app"), không phải 1 step riêng trong Stepper — khớp
 * specs/06_uiux.md §7. */
export default function RenderStudio({ project, pack, onClose }: { project: ProjectSummary; pack: ProductionPack; onClose: () => void }) {
  const [state, setState] = useState<RenderState | null>(null);
  const [starting, setStarting] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | undefined>(undefined);

  async function load() {
    try {
      setState(await api.getRenderStatus(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi tải trạng thái render.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const hasInFlight =
    !!state && (state.shots.some((s) => s.visual_status === "generating" || s.narration_status === "generating") || state.assembly_status === "assembling");

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (hasInFlight) {
      pollRef.current = window.setInterval(load, 3000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInFlight]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      setState(await api.startRender(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bắt đầu sinh asset.");
    } finally {
      setStarting(false);
    }
  }

  async function approve(shotId: string) {
    setError(null);
    try {
      setState(await api.approveShotAsset(project.id, shotId, true));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi duyệt shot.");
    }
  }

  async function regenVisual(shotId: string) {
    setError(null);
    try {
      setState(await api.regenerateShotVisualAsset(project.id, shotId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi tạo lại visual.");
    }
  }

  async function regenNarration(shotId: string) {
    setError(null);
    try {
      setState(await api.regenerateShotNarration(project.id, shotId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi tạo lại giọng đọc.");
    }
  }

  async function assemble() {
    setAssembling(true);
    setError(null);
    try {
      setState(await api.assembleVideo(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi ghép video.");
    } finally {
      setAssembling(false);
    }
  }

  const shots = pack.shots || [];
  const allApproved = !!state && state.shots.length > 0 && state.shots.every((s) => s.visual_status === "ready" && s.approved);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
        <div>
          <h3 style={{ marginBottom: 2 }}>Render Studio</h3>
          <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13 }}>
            Sinh ảnh/video + giọng đọc thật cho từng shot (tốn phí API), duyệt từng shot rồi ghép thành 1 MP4.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={onClose}>
          ← Quay lại
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 13, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "8px 10px", marginBottom: "var(--space-3)" }}>
          {error}
        </div>
      )}

      {!state || state.shots.length === 0 ? (
        <button className="btn btn-primary" onClick={start} disabled={starting}>
          {starting ? "Đang bắt đầu..." : "Bắt đầu sinh asset"}
        </button>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-4)" }}>
            {shots.map((shot) => {
              const st = state.shots.find((s) => s.shot_id === shot.shot_id);
              if (!st) return null;
              return (
                <div key={shot.shot_id} className="card elev-sm" style={{ gap: "var(--space-2)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
                      {shot.shot_id}
                    </span>
                    <StatusTag label="Visual" status={st.visual_status} />
                    <StatusTag label="Giọng đọc" status={st.narration_status} />
                    {st.approved && <span className="tag tag-accent">Đã duyệt</span>}
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "var(--space-3)" }}>
                    <ShotPreview projectId={project.id} shot={shot} status={st} />
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ fontSize: 12, opacity: 0.8 }}>{shot.visual_fx}</div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => regenVisual(shot.shot_id)} disabled={st.visual_status === "generating"}>
                          Tạo lại Visual
                        </button>
                        <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => regenNarration(shot.shot_id)} disabled={st.narration_status === "generating"}>
                          Tạo lại giọng đọc
                        </button>
                        <button className="btn btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => approve(shot.shot_id)} disabled={st.visual_status !== "ready" || st.approved}>
                          {st.approved ? "Đã duyệt" : "Duyệt"}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {state.assembly_status === "done" && state.final_video_path ? (
            <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 640 }}>
              <div className="card-title">Video hoàn chỉnh</div>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video controls style={{ width: "100%", borderRadius: "var(--radius-sm)" }} src={api.renderDownloadUrl(project.id)} />
              <a className="btn btn-primary btn-block" href={api.renderDownloadUrl(project.id)} target="_blank" rel="noreferrer">
                Tải MP4
              </a>
            </div>
          ) : (
            <>
              <button className="btn btn-primary" onClick={assemble} disabled={!allApproved || assembling || state.assembly_status === "assembling"}>
                {state.assembly_status === "assembling" ? "Đang ghép video..." : "Ghép MP4"}
              </button>
              {!allApproved && <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>Cần duyệt (Visual đã sẵn sàng + bấm "Duyệt") toàn bộ shot trước khi ghép.</div>}
            </>
          )}
          {state.assembly_status === "error" && state.assembly_error && (
            <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 6, maxWidth: 640 }}>{state.assembly_error}</div>
          )}
        </>
      )}
    </div>
  );
}

function ShotPreview({
  projectId,
  shot,
  status,
}: {
  projectId: string;
  shot: ProductionPack["shots"][number];
  status: ShotRenderStatus;
}) {
  if (status.visual_status === "ready") {
    return (
      <div>
        {shot.visual_type === "video" ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video controls style={{ width: "100%", borderRadius: "var(--radius-sm)" }} src={api.renderShotAssetUrl(projectId, shot.shot_id, "visual")} />
        ) : (
          <img alt={shot.shot_id} style={{ width: "100%", borderRadius: "var(--radius-sm)", display: "block" }} src={api.renderShotAssetUrl(projectId, shot.shot_id, "visual")} />
        )}
        {status.narration_status === "ready" && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <audio controls style={{ width: "100%", marginTop: 6 }} src={api.renderShotAssetUrl(projectId, shot.shot_id, "narration")} />
        )}
        {status.narration_status === "error" && <div style={{ fontSize: 11, color: "var(--color-danger)", marginTop: 4 }}>{status.narration_error}</div>}
      </div>
    );
  }
  return (
    <div
      style={{
        height: 120,
        borderRadius: "var(--radius-sm)",
        background: "var(--color-bg)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 11,
        opacity: 0.65,
        textAlign: "center",
        padding: 6,
        color: status.visual_status === "error" ? "var(--color-danger)" : undefined,
      }}
    >
      {status.visual_status === "error" ? status.visual_error : status.visual_status === "generating" ? "Đang sinh…" : "Chưa sinh"}
    </div>
  );
}

function StatusTag({ label, status }: { label: string; status: string }) {
  const color =
    status === "ready" ? "var(--color-accent)" : status === "error" ? "var(--color-danger)" : status === "generating" ? "var(--color-warning)" : "var(--color-neutral-600)";
  return (
    <span className="tag tag-outline" style={{ fontSize: 10, color }}>
      {label}: {status}
    </span>
  );
}
