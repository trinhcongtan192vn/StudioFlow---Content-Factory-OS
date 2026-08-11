import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ImportPreview } from "../../api/types";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

export default function Gate1Outline({ project, pack, refresh, busy, setBusy }: StepProps) {
  const outlines = pack.research?.outlines || [];
  const hooks = pack.hooks || [];
  const [selectedOutline, setSelectedOutline] = useState<string | null>(outlines.find((o) => o.selected)?.id || null);
  const [selectedHook, setSelectedHook] = useState<string | null>(hooks.find((h) => h.selected)?.id || null);
  const [editedHookText, setEditedHookText] = useState<string | null>(null);
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const chosenHook = hooks.find((h) => h.id === selectedHook);
  const hookText = editedHookText !== null ? editedHookText : chosenHook?.spoken || "";
  const ctaDisabled = !selectedOutline || !selectedHook || busy;

  function selectHook(id: string) {
    setSelectedHook(id);
    setEditedHookText(null);
  }

  async function approve() {
    if (!selectedOutline || !selectedHook) return;
    setBusy(true);
    try {
      await api.approveGate1(project.id, {
        chosen_outline_id: selectedOutline,
        chosen_hook_id: selectedHook,
        edited_hook_text: editedHookText || undefined,
      });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function onImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImporting(true);
    setImportError(null);
    setImportPreview(null);
    try {
      const preview = await api.importScriptParse(project.id, file);
      setImportPreview(preview);
    } catch (err) {
      setImportError(err instanceof ApiError ? err.message : "Không đọc được file. Kiểm tra định dạng CSV/Excel và thử lại.");
    } finally {
      setImporting(false);
    }
  }

  async function confirmImport() {
    if (!importPreview) return;
    setConfirming(true);
    try {
      await api.importScriptConfirm(project.id, importPreview.beats, importPreview.full_text);
      setImportPreview(null);
      await refresh();
    } finally {
      setConfirming(false);
    }
  }

  function closeImportDialog() {
    if (importing) return;
    setImportPreview(null);
    setImportError(null);
  }

  return (
    <div>
      <StepHeader
        title="Outline & Hook"
        description="Chọn 1 dàn ý & 1 Hook trước khi viết kịch bản chi tiết."
        actions={
          <>
            <button className="btn btn-primary" disabled={ctaDisabled} onClick={approve}>
              Duyệt &amp; viết kịch bản chi tiết →
            </button>
            <span style={{ fontSize: 12, opacity: 0.5 }}>hoặc</span>
            <label className="btn btn-secondary" style={{ cursor: importing ? "default" : "pointer", margin: 0, display: "flex", alignItems: "center", gap: 6, fontSize: 13, opacity: importing ? 0.6 : 1 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              {importing ? "Đang đọc file..." : "Nhập kịch bản từ file (CSV/Excel)"}
              <input type="file" accept=".csv,.xlsx,.xls" style={{ display: "none" }} disabled={importing} onChange={onImportFile} />
            </label>
          </>
        }
        extra={
          <div style={{ fontSize: 11.5, opacity: 0.55, marginBottom: "var(--space-3)" }}>
            Bảng 6 cột: Mã block, Thời lượng, Loại Visual, Visual/FX, Audio/SFX, Kịch bản Giọng đọc (VO)
          </div>
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
          <strong style={{ fontFamily: "var(--font-heading)", fontWeight: 600 }}>★ Human Gate #1</strong> — Chọn 1 dàn ý &amp; 1 Hook. Bắt buộc trước khi viết kịch bản chi tiết.
        </div>
      </div>

      <h4 style={{ marginBottom: "var(--space-2)" }}>AI Research — Dàn ý đề xuất</h4>
      {pack.research?.synthesis && <p style={{ fontSize: 13, opacity: 0.75, marginTop: -4 }}>{pack.research.synthesis}</p>}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        {outlines.map((o) => (
          <div key={o.id} className="card" onClick={() => setSelectedOutline(o.id)} style={{ cursor: "pointer", border: selectedOutline === o.id ? "1px solid var(--color-accent)" : "1px solid transparent" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 14, height: 14, borderRadius: "50%", border: `1.5px solid ${selectedOutline === o.id ? "var(--color-accent)" : "var(--color-divider)"}`, background: selectedOutline === o.id ? "var(--color-accent)" : "transparent", flex: "none" }} />
              <div className="card-title" style={{ fontSize: 14 }}>
                {o.title}
              </div>
            </div>
            <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, opacity: 0.8 }}>
              {o.points.map((pt, i) => (
                <li key={i}>{pt}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <h4 style={{ marginBottom: "var(--space-2)" }}>Hook Variants</h4>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}>
        {hooks.map((h) => (
          <div
            key={h.id}
            className="card"
            onClick={() => selectHook(h.id)}
            style={{ cursor: "pointer", border: selectedHook === h.id ? "1px solid var(--color-accent)" : "1px solid transparent", opacity: selectedHook && selectedHook !== h.id ? 0.55 : 1 }}
          >
            <div className="card-kicker">{h.psychological_type}</div>
            <div className="card-body" style={{ fontSize: 14, opacity: 1 }}>
              {h.spoken}
            </div>
          </div>
        ))}
      </div>

      {selectedHook && (
        <div className="field" style={{ maxWidth: 640, marginBottom: "var(--space-4)" }}>
          <label>Chỉnh sửa trực tiếp Hook đã chọn</label>
          <textarea className="input" rows={2} value={hookText} onChange={(e) => setEditedHookText(e.target.value)} />
        </div>
      )}

      {busy && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--color-accent)", fontSize: 13, padding: "var(--space-2) 0" }}>
          <svg className="sf-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a9 9 0 11-6.219-8.56" />
          </svg>
          AI đang viết kịch bản đa cột &amp; sinh prompt shot...
        </div>
      )}

      {(importPreview || importError) && (
        <div className="dialog-backdrop" onClick={closeImportDialog}>
          <div className="dialog" onClick={(e) => e.stopPropagation()} style={{ width: "min(440px,100%)" }}>
            {importError ? (
              <>
                <div className="dialog-title">Không thể nhập file</div>
                <div className="dialog-body">{importError}</div>
                <div className="dialog-actions">
                  <button className="btn btn-secondary" onClick={() => setImportError(null)}>
                    Đóng
                  </button>
                </div>
              </>
            ) : (
              importPreview && (
                <>
                  <div className="dialog-title">Xác nhận nhập kịch bản</div>
                  <div className="dialog-body">File hợp lệ — thông tin script hiện tại sẽ được thay thế bằng nội dung sau:</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, margin: "var(--space-2) 0 var(--space-3)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                      <span style={{ opacity: 0.65 }}>Số block</span>
                      <span style={{ fontFamily: "ui-monospace,monospace" }}>{importPreview.stats.block_count}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                      <span style={{ opacity: 0.65 }}>Số từ trong kịch bản</span>
                      <span style={{ fontFamily: "ui-monospace,monospace" }}>{importPreview.stats.word_count}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                      <span style={{ opacity: 0.65 }}>Thời lượng video (ước tính)</span>
                      <span style={{ fontFamily: "ui-monospace,monospace" }}>{importPreview.stats.duration_label}</span>
                    </div>
                  </div>
                  <div className="dialog-actions">
                    <button className="btn btn-secondary" onClick={() => setImportPreview(null)} disabled={confirming}>
                      Hủy
                    </button>
                    <button className="btn btn-primary" onClick={confirmImport} disabled={confirming}>
                      {confirming ? "Đang nhập..." : "Xác nhận nhập"}
                    </button>
                  </div>
                </>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
