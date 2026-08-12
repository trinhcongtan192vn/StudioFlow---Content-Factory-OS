import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Brief } from "../../api/types";
import AiErrorBanner from "../../components/AiErrorBanner";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

const GOAL_OPTIONS = ["Nhận diện thương hiệu", "Tăng tương tác", "Chuyển đổi"];
const CONVERSION_OPTIONS: { value: string; label: string }[] = [
  { value: "none", label: "Không có" },
  { value: "affiliate", label: "Affiliate" },
  { value: "course", label: "Khóa học" },
  { value: "private_traffic", label: "Private Traffic" },
];

function emptyBrief(projectId: string, channelId: string): Brief {
  return {
    project_id: projectId,
    channel_id: channelId,
    topic: "",
    insight: "",
    strategy: { content_matrix_slot: "", growth_objective: "", conversion_point: "none" },
    audience: { seo_keywords: [], retention_notes: "", pain_points: [], description: "" },
    raw_knowledge: { documents: [], expert_notes: "", key_message: "" },
    conversion_note: "",
    brand_voice_override: null,
  };
}

export default function BriefEditor({ project, refresh, busy, setBusy }: StepProps) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [youtubeDraft, setYoutubeDraft] = useState("");
  const [addingYoutube, setAddingYoutube] = useState(false);
  const [addingFile, setAddingFile] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    api.getBrief(project.id).then((r) => setBrief(r.brief.topic !== undefined ? r.brief : emptyBrief(project.id, project.channel_id)));
  }, [project.id, project.channel_id]);

  function save(next: Brief) {
    setBrief(next);
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      api.putBrief(project.id, next);
    }, 400);
  }

  if (!brief) return <div style={{ opacity: 0.6 }}>Đang tải...</div>;

  const missingGroup1 = !brief.topic || !brief.insight;
  const missingGroup2 = !brief.audience.description || !brief.strategy.growth_objective;
  const ctaDisabled = !brief.topic || !brief.audience.description || !brief.strategy.growth_objective || busy;

  async function startResearch() {
    setBusy(true);
    setAiError(null);
    try {
      await api.putBrief(project.id, brief!);
      await api.runResearch(project.id);
      await refresh();
    } catch (e) {
      setAiError(e instanceof ApiError ? e.message : "Có lỗi khi chạy Research.");
    } finally {
      setBusy(false);
    }
  }

  async function addYoutube() {
    if (!youtubeDraft.trim()) return;
    setSourceError(null);
    setAddingYoutube(true);
    try {
      const updated = await api.addBriefYoutubeSource(project.id, youtubeDraft.trim());
      setBrief(updated);
      setYoutubeDraft("");
      const last = updated.raw_knowledge.documents[updated.raw_knowledge.documents.length - 1];
      if (last?.status === "error") setSourceError(last.error || "Không lấy được transcript từ video này.");
    } catch (e) {
      setSourceError(e instanceof Error ? e.message : "Có lỗi khi thêm link YouTube.");
    } finally {
      setAddingYoutube(false);
    }
  }

  async function addFile(files: FileList | null) {
    if (!files || !files.length) return;
    setSourceError(null);
    setAddingFile(true);
    try {
      let updated = brief!;
      for (const f of Array.from(files)) {
        updated = await api.addBriefFileSource(project.id, f);
      }
      setBrief(updated);
    } catch (e) {
      setSourceError(e instanceof Error ? e.message : "Có lỗi khi tải file lên.");
    } finally {
      setAddingFile(false);
    }
  }

  async function removeSource(id: string) {
    const updated = await api.removeBriefSource(project.id, id);
    setBrief(updated);
  }

  return (
    <div>
      <StepHeader
        title="Brief Editor"
        description="Điền 4 nhóm input. Trường thiếu được đánh dấu, không chặn cứng."
        actions={
          <button className="btn btn-primary" disabled={ctaDisabled} onClick={startResearch}>
            Bắt đầu Research
          </button>
        }
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 640 }}>
        {aiError && <AiErrorBanner message={aiError} onDismiss={() => setAiError(null)} />}
        <div className="card" style={{ gap: "var(--space-3)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div className="card-kicker">1 · Chủ đề &amp; Insight</div>
            {missingGroup1 && <span className="tag tag-warning">cần bổ sung</span>}
          </div>
          <div className="field">
            <label>Chủ đề video</label>
            <input className="input" type="text" placeholder="VD: Vì sao ta luôn trì hoãn" value={brief.topic} onChange={(e) => save({ ...brief, topic: e.target.value })} />
          </div>
          <div className="field">
            <label>Insight chính (điều gì khiến chủ đề này đáng xem)</label>
            <textarea className="input" rows={2} placeholder="Insight cốt lõi..." value={brief.insight} onChange={(e) => save({ ...brief, insight: e.target.value })} />
          </div>
        </div>

        <div className="card" style={{ gap: "var(--space-3)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div className="card-kicker">2 · Đối tượng &amp; Mục tiêu</div>
            {missingGroup2 && <span className="tag tag-warning">cần bổ sung</span>}
          </div>
          <div className="field">
            <label>Đối tượng khán giả</label>
            <textarea
              className="input"
              rows={2}
              placeholder="Ai sẽ xem video này?"
              value={brief.audience.description}
              onChange={(e) => save({ ...brief, audience: { ...brief.audience, description: e.target.value } })}
            />
          </div>
          <div className="field">
            <label>Mục tiêu kinh doanh</label>
            <div className="seg">
              {GOAL_OPTIONS.map((g) => (
                <label key={g} className="seg-opt">
                  <input type="radio" name="goal" checked={brief.strategy.growth_objective === g} onChange={() => save({ ...brief, strategy: { ...brief.strategy, growth_objective: g } })} />
                  {g}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="card" style={{ gap: "var(--space-3)" }}>
          <div className="card-kicker">3 · Điểm chuyển đổi</div>
          <div className="field">
            <label>Loại chuyển đổi</label>
            <div className="seg">
              {CONVERSION_OPTIONS.map((c) => (
                <label key={c.value} className="seg-opt">
                  <input type="radio" name="conv" checked={brief.strategy.conversion_point === c.value} onChange={() => save({ ...brief, strategy: { ...brief.strategy, conversion_point: c.value } })} />
                  {c.label}
                </label>
              ))}
            </div>
          </div>
          <div className="field">
            <label>Ghi chú CTA</label>
            <input className="input" type="text" placeholder="VD: link khóa học ở mô tả" value={brief.conversion_note} onChange={(e) => save({ ...brief, conversion_note: e.target.value })} />
          </div>
        </div>

        <div className="card" style={{ gap: "var(--space-3)" }}>
          <div className="card-kicker">4 · Tư liệu tham khảo (tùy chọn)</div>
          <div className="field">
            <label>Ghi chú, số liệu, nguồn tham khảo</label>
            <textarea
              className="input"
              rows={2}
              placeholder="Link, số liệu, nguồn tham khảo..."
              value={brief.raw_knowledge.expert_notes}
              onChange={(e) => save({ ...brief, raw_knowledge: { ...brief.raw_knowledge, expert_notes: e.target.value } })}
            />
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
            <div className="field" style={{ flex: 1, minWidth: 200, margin: 0 }}>
              <label>Link YouTube</label>
              <input className="input" type="text" placeholder="https://youtube.com/watch?v=..." value={youtubeDraft} onChange={(e) => setYoutubeDraft(e.target.value)} />
            </div>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "7px 12px" }} onClick={addYoutube} disabled={addingYoutube || !youtubeDraft.trim()}>
              {addingYoutube ? "Đang lấy transcript..." : "+ Thêm link"}
            </button>
            <label className="btn btn-secondary" style={{ fontSize: 12, padding: "7px 12px", cursor: addingFile ? "default" : "pointer", margin: 0, opacity: addingFile ? 0.6 : 1 }}>
              {addingFile ? "Đang tải..." : "+ Tải file lên"}
              <input type="file" accept=".pdf,.doc,.docx,.txt,.md,.markdown" multiple style={{ display: "none" }} disabled={addingFile} onChange={(e) => addFile(e.target.files)} />
            </label>
          </div>
          <div style={{ fontSize: 11, opacity: 0.5 }}>Hỗ trợ PDF, Word, TXT, Markdown hoặc link YouTube — hệ thống tự động trích xuất text làm nguồn tham khảo (transcript YouTube lấy thật qua youtube-transcript-api).</div>
          {sourceError && (
            <div style={{ fontSize: 12, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "6px 8px" }}>{sourceError}</div>
          )}
          {brief.raw_knowledge.documents.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {brief.raw_knowledge.documents.map((src) => (
                <div key={src.id} style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12, background: "var(--color-bg)", borderRadius: "var(--radius-sm)", padding: "6px 8px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="tag tag-neutral" style={{ flex: "none" }}>
                      {src.kind === "youtube" ? "YouTube" : "File"}
                    </span>
                    <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{src.label}</span>
                    <span style={{ fontSize: 11, opacity: 0.7, color: src.status === "error" ? "var(--color-danger)" : undefined }}>
                      {src.status === "done" ? (src.char_count ? `${src.char_count} ký tự` : "đã lưu") : src.status === "error" ? "lỗi" : "đang xử lý…"}
                    </span>
                    <button className="btn btn-icon btn-secondary" style={{ flex: "none", width: 22, height: 22 }} title="Gỡ" onClick={() => removeSource(src.id)}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                  {src.status === "error" && src.error && <div style={{ fontSize: 11, color: "var(--color-danger)", paddingLeft: 2 }}>{src.error}</div>}
                </div>
              ))}
            </div>
          )}
        </div>

        {busy && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--color-accent)", fontSize: 13, padding: "var(--space-2) 0" }}>
            <svg className="sf-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12a9 9 0 11-6.219-8.56" />
            </svg>
            Đang tổng hợp tài liệu &amp; tạo dàn ý...
          </div>
        )}
      </div>
    </div>
  );
}
