import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ImportPreview, ProjectSummary } from "../api/types";

/** Nút "Nhập kịch bản từ file" + "Tải file mẫu" + dialog xác nhận — dùng chung ở
 * BriefEditor.tsx (bỏ qua Brief & Research, nhập kịch bản luôn) và Gate1Outline.tsx
 * (nhập thay cho chọn Outline/Hook). Cả 2 endpoint backend (`script/import/parse`,
 * `/confirm`) KHÔNG yêu cầu đã qua Research/Gate 1 — `confirm` tự nhảy thẳng step→2
 * (Script Studio) bất kể project đang ở step nào, nên gọi được an toàn từ cả 2 màn. */
export default function ScriptImportControls({ project, refresh }: { project: ProjectSummary; refresh: () => Promise<void> }) {
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [confirming, setConfirming] = useState(false);

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
    <>
      <label className="btn btn-secondary" style={{ cursor: importing ? "default" : "pointer", margin: 0, display: "flex", alignItems: "center", gap: 6, fontSize: 13, opacity: importing ? 0.6 : 1 }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        {importing ? "Đang đọc file..." : "Nhập kịch bản từ file (CSV/Excel)"}
        <input type="file" accept=".csv,.xlsx,.xls" style={{ display: "none" }} disabled={importing} onChange={onImportFile} />
      </label>
      <button
        className="btn btn-secondary"
        style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}
        onClick={() => api.downloadScriptImportTemplate(project.id)}
        title="Tải file Excel mẫu đúng 6 cột để điền kịch bản trước khi nhập"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        Tải file mẫu
      </button>

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
    </>
  );
}
