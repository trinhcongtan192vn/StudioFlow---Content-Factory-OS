import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { RenderState } from "../../api/types";
import AiErrorBanner from "../../components/AiErrorBanner";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

export default function ScriptStudio({ project, pack, refresh, busy, setBusy }: StepProps) {
  const script = pack.script;
  const [fullText, setFullText] = useState(script?.full_text || "");
  const [feedback, setFeedback] = useState("");
  const [lastFeedback, setLastFeedback] = useState("");
  const [editingAgain, setEditingAgain] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);

  const [renderState, setRenderState] = useState<RenderState | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [activeShotId, setActiveShotId] = useState<string | null>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [playQueue, setPlayQueue] = useState<string[]>([]);
  const [isPlayingAll, setIsPlayingAll] = useState(false);

  useEffect(() => {
    api
      .getRenderStatus(project.id)
      .then(setRenderState)
      .catch(() => {
        /* chưa từng sinh asset — bỏ qua, coi như chưa có giọng đọc nào */
      });
  }, [project.id]);

  const hasBody = (script?.body?.length || 0) > 0;
  const showEditor = !hasBody || editingAgain;

  function shotForTimestamp(ts: number | null) {
    return pack.shots.find((s) => s.linked_timestamp_sec === ts);
  }

  function narrationStatusFor(shotId: string | undefined) {
    if (!shotId) return undefined;
    return renderState?.shots.find((s) => s.shot_id === shotId);
  }

  function playShotAudio(shotId: string, queue: string[], all: boolean) {
    if (!audioRef.current) return;
    setActiveShotId(shotId);
    setPlayQueue(queue);
    setIsPlayingAll(all);
    audioRef.current.src = api.renderShotAssetUrl(project.id, shotId, "narration");
    audioRef.current.play();
  }

  function stopPlayback() {
    audioRef.current?.pause();
    setActiveShotId(null);
    setPlayQueue([]);
    setIsPlayingAll(false);
  }

  function togglePlaySingle(shotId: string) {
    if (activeShotId === shotId && isAudioPlaying) {
      audioRef.current?.pause();
      return;
    }
    if (activeShotId === shotId && !isAudioPlaying && audioRef.current) {
      setIsPlayingAll(false);
      audioRef.current.play();
      return;
    }
    playShotAudio(shotId, [], false);
  }

  function playAllNarration() {
    if (isPlayingAll) {
      stopPlayback();
      return;
    }
    const ordered = (script?.body || [])
      .map((b) => shotForTimestamp(b.timestamp_sec))
      .filter((s) => !!s && narrationStatusFor(s.shot_id)?.narration_status === "ready")
      .map((s) => s!.shot_id);
    if (!ordered.length) return;
    playShotAudio(ordered[0], ordered.slice(1), true);
  }

  function handleAudioEnded() {
    if (playQueue.length === 0) {
      setActiveShotId(null);
      setIsPlayingAll(false);
      return;
    }
    const [next, ...rest] = playQueue;
    playShotAudio(next, rest, true);
  }

  const readyNarrationCount = (script?.body || []).filter(
    (b) => narrationStatusFor(shotForTimestamp(b.timestamp_sec)?.shot_id)?.narration_status === "ready"
  ).length;

  function onTextChange(v: string) {
    setFullText(v);
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => api.editScriptText(project.id, v), 500);
  }

  async function regenerate() {
    if (!feedback.trim()) return;
    setBusy(true);
    setAiError(null);
    try {
      const updated = await api.regenerateScript(project.id, feedback);
      setFullText(updated.script?.full_text || "");
      setLastFeedback(feedback);
      setFeedback("");
    } catch (e) {
      setAiError(e instanceof ApiError ? e.message : "Có lỗi khi tạo lại Full Script.");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setAiError(null);
    try {
      await api.editScriptText(project.id, fullText);
      await api.approveScript(project.id);
      setEditingAgain(false);
      await refresh();
    } catch (e) {
      setAiError(e instanceof ApiError ? e.message : "Có lỗi khi duyệt Full Script.");
    } finally {
      setBusy(false);
    }
  }

  async function goVisualStudio() {
    setBusy(true);
    setAiError(null);
    try {
      await api.generateVisualShots(project.id);
      await refresh();
    } catch (e) {
      setAiError(e instanceof ApiError ? e.message : "Có lỗi khi sinh shot cho Visual Studio.");
    } finally {
      setBusy(false);
    }
  }

  const regenerateDisabled = !feedback.trim() || busy;
  const warningCount = (script?.body || []).filter((b) => b.warning).length;

  return (
    <div>
      <StepHeader
        title="Script Studio"
        description={
          <>
            Master Production Script — Âm thanh / Hình ảnh / Chỉ dẫn, theo timeline.
            {warningCount > 0 && <span style={{ marginLeft: 8 }}>· {warningCount} cảnh báo</span>}
          </>
        }
        actions={
          showEditor ? (
            <>
              <button className="btn btn-secondary" onClick={regenerate} disabled={regenerateDisabled}>
                {busy ? "Đang tạo lại..." : "Tạo lại theo góp ý"}
              </button>
              <button className="btn btn-primary" onClick={approve} disabled={busy || !fullText.trim()}>
                Duyệt Full Script &amp; bóc tách theo đoạn →
              </button>
            </>
          ) : (
            <>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: "5px 12px" }}
                onClick={playAllNarration}
                disabled={!isPlayingAll && readyNarrationCount === 0}
                title={readyNarrationCount === 0 ? "Chưa có giọng đọc nào sẵn sàng — sinh giọng đọc ở Visual Studio" : undefined}
              >
                {isPlayingAll ? "⏸ Dừng phát" : `▶ Nghe toàn bộ giọng đọc (${readyNarrationCount})`}
              </button>
              <button className="btn btn-primary" onClick={goVisualStudio} disabled={busy}>
                {busy ? "Đang sinh shot..." : "Đi tới Visual Studio →"}
              </button>
            </>
          )
        }
      />

      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} onEnded={handleAudioEnded} onPlay={() => setIsAudioPlaying(true)} onPause={() => setIsAudioPlaying(false)} style={{ display: "none" }} />

      {aiError && <AiErrorBanner message={aiError} onDismiss={() => setAiError(null)} />}
      {project.return_note && <ReturnBanner title="Đã trả về từ Pack Review:" text={project.return_note} />}

      {showEditor ? (
        <>
          {lastFeedback && <ReturnBanner title="Đã tạo lại theo góp ý:" text={lastFeedback} />}
          <div className="field">
            <label>Full Script — đọc và chỉnh câu từ trước khi bóc tách theo đoạn</label>
            <textarea className="input" rows={14} style={{ fontSize: 14, lineHeight: 1.6, fontFamily: "var(--font-body)" }} value={fullText} onChange={(e) => onTextChange(e.target.value)} />
          </div>
          <div className="field">
            <label>Góp ý chỉnh sửa (để AI tạo lại Full Script)</label>
            <textarea className="input" rows={2} placeholder="VD: Rút ngắn đoạn mở đầu, thêm số liệu cụ thể ở đoạn 2..." value={feedback} onChange={(e) => setFeedback(e.target.value)} />
          </div>
        </>
      ) : (
        <>
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setEditingAgain(true);
            }}
            style={{ fontSize: 12, display: "inline-block", marginBottom: "var(--space-3)" }}
          >
            ← Quay lại chỉnh Full Script
          </a>
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)", maxWidth: 900 }}>
            {(script?.body || []).map((b, i) => {
              const shot = shotForTimestamp(b.timestamp_sec);
              const narration = narrationStatusFor(shot?.shot_id);
              const isActive = !!shot && activeShotId === shot.shot_id;
              return (
              <div key={i} className="card elev-sm" style={{ gap: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  {b.block_id && (
                    <span className="tag tag-outline" style={{ fontFamily: "ui-monospace,monospace" }}>
                      {b.block_id}
                    </span>
                  )}
                  <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
                    {b.timestamp_sec}s{b.end_sec ? `–${b.end_sec}s` : ""}
                  </span>
                  {b.visual_type && <span className="tag tag-accent-2">{b.visual_type}</span>}
                  {narration?.narration_status === "ready" && shot && (
                    <button
                      type="button"
                      className="tag tag-accent"
                      style={{ cursor: "pointer", border: "none" }}
                      onClick={() => togglePlaySingle(shot.shot_id)}
                    >
                      {isActive && isAudioPlaying ? "⏸ Đang phát" : "▶ Nghe giọng đọc"}
                    </button>
                  )}
                  {narration?.narration_status === "generating" && (
                    <span className="tag tag-outline" style={{ fontSize: 10 }}>
                      Đang tạo giọng đọc…
                    </span>
                  )}
                  {b.warning && (
                    <>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: b.warning.severity === "red" ? "var(--color-danger)" : "var(--color-warning)" }} />
                      <span style={{ fontSize: 12, color: b.warning.severity === "red" ? "var(--color-danger)" : "var(--color-warning)" }}>{b.warning.message}</span>
                    </>
                  )}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-3)", fontSize: 13 }}>
                  <Col label="Audio" value={b.audio} underline={!!b.warning} />
                  <Col label="Visual" value={b.visual} />
                  <Col label={b.direction_label || "Direction"} value={b.direction} muted />
                </div>
              </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function Col({ label, value, underline, muted }: { label: string; value: string; underline?: boolean; muted?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", color: "color-mix(in srgb, var(--color-text) 50%, transparent)", marginBottom: 3 }}>{label}</div>
      <div style={{ textDecoration: underline ? "underline wavy var(--color-warning)" : "none", opacity: muted ? 0.75 : 1 }}>{value}</div>
    </div>
  );
}

function ReturnBanner({ title, text }: { title: string; text: string }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "var(--space-3)", borderRadius: "var(--radius-md)", background: "var(--color-neutral-800)", marginBottom: "var(--space-4)", fontSize: 13, maxWidth: 820 }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none" }}>
        <line x1="19" y1="12" x2="5" y2="12" />
        <polyline points="12 19 5 12 12 5" />
      </svg>
      <div>
        <strong style={{ fontFamily: "var(--font-heading)", fontWeight: 600 }}>{title}</strong> {text}
      </div>
    </div>
  );
}
