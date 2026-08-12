import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { RenderState, Shot, ShotRenderStatus } from "../../api/types";
import AiErrorBanner from "../../components/AiErrorBanner";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

export default function VisualStudio({ project, pack, refresh, busy, setBusy }: StepProps) {
  const [aiError, setAiError] = useState<string | null>(null);
  const [renderState, setRenderState] = useState<RenderState | null>(null);
  const [startingRender, setStartingRender] = useState(false);
  const pollRef = useRef<number | undefined>(undefined);
  const body = pack.script?.body || [];

  function describeAiError(e: unknown, fallback: string): string {
    return e instanceof ApiError ? e.message : fallback;
  }

  async function loadRenderStatus() {
    try {
      setRenderState(await api.getRenderStatus(project.id));
    } catch {
      /* chưa từng sinh asset — bỏ qua, hiện trạng thái "chưa sinh" mặc định */
    }
  }

  useEffect(() => {
    loadRenderStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const hasInFlight = !!renderState && renderState.shots.some((s) => s.visual_status === "generating" || s.narration_status === "generating");

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (hasInFlight) {
      pollRef.current = window.setInterval(loadRenderStatus, 3000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInFlight]);

  function statusFor(shotId: string): ShotRenderStatus | undefined {
    return renderState?.shots.find((s) => s.shot_id === shotId);
  }

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

  async function startAssetGeneration() {
    setStartingRender(true);
    setAiError(null);
    try {
      setRenderState(await api.startRender(project.id));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi bắt đầu sinh asset."));
    } finally {
      setStartingRender(false);
    }
  }

  async function regenVisualAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.regenerateShotVisualAsset(project.id, shotId));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi sinh ảnh/video cho shot này."));
    }
  }

  async function regenNarrationAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.regenerateShotNarration(project.id, shotId));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi sinh giọng đọc cho shot này."));
    }
  }

  async function approveAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.approveShotAsset(project.id, shotId, true));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi duyệt shot."));
    }
  }

  async function goPackReview() {
    setBusy(true);
    setAiError(null);
    try {
      await api.buildPack(project.id);
      await refresh();
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi tổng hợp Production Pack."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <StepHeader
        title="Visual Studio"
        description="Viết mô tả, sinh ảnh/video và giọng đọc THẬT cho từng shot — theo đúng đoạn script tương ứng. Duyệt shot sau khi sinh xong, ghép MP4 ở Output Center."
        actions={
          <>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={startAssetGeneration} disabled={startingRender || hasInFlight}>
              {startingRender || hasInFlight ? "Đang sinh asset..." : "Sinh asset (ảnh/video/giọng đọc) cho toàn bộ block"}
            </button>
            <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={goPackReview} disabled={busy}>
              {busy ? "Đang tổng hợp Pack..." : "Xem Production Pack →"}
            </button>
          </>
        }
      />

      {aiError && <AiErrorBanner message={aiError} onDismiss={() => setAiError(null)} />}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 900 }}>
        {pack.shots.map((v) => (
          <ShotCard
            key={v.shot_id}
            projectId={project.id}
            shot={v}
            status={statusFor(v.shot_id)}
            snippet={snippetFor(v.linked_timestamp_sec)}
            onToggleType={() => toggleType(v.shot_id, v.visual_type)}
            onPatchShot={(patch) => patchShot(v.shot_id, patch)}
            onGenerateVisualAsset={() => regenVisualAsset(v.shot_id)}
            onGenerateNarrationAsset={() => regenNarrationAsset(v.shot_id)}
            onApprove={() => approveAsset(v.shot_id)}
          />
        ))}
      </div>
    </div>
  );
}

function ShotCard({
  projectId,
  shot,
  status,
  snippet,
  onToggleType,
  onPatchShot,
  onGenerateVisualAsset,
  onGenerateNarrationAsset,
  onApprove,
}: {
  projectId: string;
  shot: Shot;
  status: ShotRenderStatus | undefined;
  snippet: string;
  onToggleType: () => void;
  onPatchShot: (patch: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string }>) => void;
  onGenerateVisualAsset: () => void;
  onGenerateNarrationAsset: () => void;
  onApprove: () => void;
}) {
  const visualStatus = status?.visual_status || "pending";
  const narrationStatus = status?.narration_status || "pending";

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
          {shot.shot_id} · {shot.linked_timestamp_sec}s
        </span>
        <span className={`tag ${shot.visual_type === "video" ? "tag-accent-2" : "tag-accent"}`} onClick={onToggleType} style={{ cursor: "pointer" }}>
          {shot.visual_type === "video" ? "Video" : "Image"}
        </span>
        <StatusTag label="Visual" status={visualStatus} />
        <StatusTag label="Giọng đọc" status={narrationStatus} />
        {status?.approved && <span className="tag tag-accent">Đã duyệt</span>}
      </div>
      <div style={{ fontSize: 13, opacity: 0.8, padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>{snippet}</div>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "var(--space-3)", alignItems: "flex-start" }}>
        <ShotPreview projectId={projectId} shot={shot} status={status} />
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Hình ảnh &amp; Hiệu ứng (Visual/FX)</label>
            <textarea className="input" rows={2} style={{ fontSize: 13 }} defaultValue={shot.visual_fx} onBlur={(e) => onPatchShot({ visual_fx: e.target.value })} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label>Âm thanh &amp; Nhạc nền (Audio/SFX)</label>
            <textarea className="input" rows={2} style={{ fontSize: 13 }} defaultValue={shot.audio_sfx} onBlur={(e) => onPatchShot({ audio_sfx: e.target.value })} />
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={onGenerateVisualAsset} disabled={visualStatus === "generating"}>
              {visualStatus === "generating" ? "Đang sinh…" : `Tạo ${shot.visual_type === "video" ? "video" : "ảnh"}`}
            </button>
            <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={onGenerateNarrationAsset} disabled={narrationStatus === "generating"}>
              {narrationStatus === "generating" ? "Đang sinh…" : "Tạo giọng đọc"}
            </button>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={onApprove} disabled={visualStatus !== "ready" || status?.approved}>
              {status?.approved ? "Đã duyệt" : "Duyệt"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ShotPreview({ projectId, shot, status }: { projectId: string; shot: Shot; status: ShotRenderStatus | undefined }) {
  if (status?.visual_status === "ready") {
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
        height: 124,
        borderRadius: "var(--radius-sm)",
        background: "var(--color-bg)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: 6,
        fontSize: 11,
        opacity: 0.6,
        color: status?.visual_status === "error" ? "var(--color-danger)" : undefined,
      }}
    >
      {status?.visual_status === "error" ? status.visual_error : status?.visual_status === "generating" ? "Đang sinh…" : `${shot.visual_type === "video" ? "Video" : "Image"} — chưa sinh`}
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
