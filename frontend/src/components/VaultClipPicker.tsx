import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { VaultCandidate } from "../api/types";

const _RIGHTS_LABEL: Record<string, { text: string; color: string }> = {
  unverified: { text: "Chưa xác minh", color: "var(--color-warning)" },
  licensed_verified: { text: "Đã xác minh", color: "#4ade80" },
  public_domain: { text: "Public domain", color: "#4ade80" },
};

/** Nút "Video từ Kho" ở Visual Studio (CHANGE_Semantic_BRoll_Asset_Vault.md §7.3) — mở
 * modal gợi ý clip từ Channel Asset Vault khớp mô tả Visual/FX của shot. Cùng khung mẫu
 * `LibraryPicker.tsx` (modal liệt kê, bấm để chọn) — khác ở nguồn dữ liệu (matching AI,
 * không phải asset tự upload) và có thêm Match Score/badge rights.
 *
 * Human-gate GIỮ NGUYÊN: chỉ GỢI Ý (kèm match score), người dùng luôn là người bấm chọn
 * — không có candidate nào tự động gán. */
export default function VaultClipPicker({
  projectId,
  shotId,
  onPick,
  disabled,
}: {
  projectId: string;
  shotId: string;
  onPick: (clipId: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState<VaultCandidate[] | null>(null);
  const [usedSemantic, setUsedSemantic] = useState(false);
  const [pickingId, setPickingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCandidates(null);
    setError(null);
    api
      .getVaultCandidates(projectId, shotId)
      .then((res) => {
        setCandidates(res.candidates);
        setUsedSemantic(res.used_semantic);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Có lỗi khi tìm clip khớp."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId, shotId]);

  function pick(clip: VaultCandidate) {
    setPickingId(clip.clip_id);
    onPick(clip.clip_id);
    setOpen(false);
    setPickingId(null);
  }

  return (
    <>
      <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setOpen(true)} disabled={disabled} title="Gợi ý clip B-roll từ Kho tư liệu của kênh, khớp mô tả Visual/FX của shot này">
        Video từ Kho
      </button>
      {open && (
        <div className="dialog-backdrop" onClick={() => setOpen(false)}>
          <div className="dialog" style={{ width: "min(480px,100%)", maxHeight: "70vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
            <div className="dialog-title">Chọn clip từ Kho tư liệu</div>
            {error && (
              <div style={{ fontSize: 12, color: "var(--color-danger)", marginBottom: 8 }}>
                {error}
                {error.includes("mô tả") && (
                  <div style={{ marginTop: 4, opacity: 0.8 }}>Điền "Hình ảnh &amp; Hiệu ứng (Visual/FX)" cho shot này trước khi tìm clip khớp.</div>
                )}
              </div>
            )}
            {candidates === null ? (
              <div style={{ opacity: 0.6, fontSize: 13 }}>Đang tìm clip khớp...</div>
            ) : candidates.length === 0 ? (
              <div style={{ opacity: 0.6, fontSize: 13 }}>
                Kho tư liệu của kênh này chưa có clip nào khớp — thêm video trong{" "}
                <strong>Cấu hình kênh → Kho Tài nguyên</strong>.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {!usedSemantic && (
                  <div style={{ fontSize: 11, opacity: 0.6 }}>Đang gợi ý theo từ khoá (chưa cấu hình Embedding provider để tìm ngữ nghĩa).</div>
                )}
                {candidates.map((c) => {
                  const rights = _RIGHTS_LABEL[c.rights_status] || { text: c.rights_status, color: "var(--color-text)" };
                  return (
                    <div
                      key={c.clip_id}
                      onClick={() => pick(c)}
                      style={{
                        display: "flex", flexDirection: "column", gap: 4, padding: "8px 10px",
                        borderRadius: "var(--radius-sm)", cursor: pickingId ? "default" : "pointer", background: "var(--color-bg)",
                        opacity: pickingId && pickingId !== c.clip_id ? 0.5 : 1,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{c.caption || c.clip_id}</span>
                        {c.match_score != null && (
                          <span className="tag tag-accent" style={{ fontSize: 10.5, flex: "none" }}>
                            {Math.round(c.match_score * 100)}% match
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, opacity: 0.75 }}>
                        <span>{c.duration_sec.toFixed(1)}s</span>
                        <span style={{ color: rights.color }}>{rights.text}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setOpen(false)}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
