import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { VaultCandidate } from "../api/types";

const _RIGHTS_LABEL: Record<string, { text: string; color: string }> = {
  unverified: { text: "Chưa xác minh", color: "var(--color-warning)" },
  licensed_verified: { text: "Đã xác minh", color: "#4ade80" },
  public_domain: { text: "Public domain", color: "#4ade80" },
};

/** Nút "Video từ Kho"/"Ảnh từ Kho" ở Visual Studio (CHANGE_Semantic_BRoll_Asset_Vault.md
 * §7.3) — mở modal gợi ý clip/ảnh từ Channel Asset Vault khớp mô tả Visual/FX của shot.
 * Cùng khung mẫu `LibraryPicker.tsx` (modal liệt kê, bấm để chọn) — khác ở nguồn dữ liệu
 * (matching AI, không phải asset tự upload) và có thêm Match Score/badge rights.
 *
 * `mediaKind` — **mới (2026-09-11)** — Kho Tài Nguyên giờ chứa CẢ ảnh (lưu từ Visual
 * Studio) lẫn video (cắt B-roll), backend đã lọc đúng loại khớp shot đang mở picker này
 * (xem `routers/render.py::get_vault_candidates`) — chỉ dùng để đổi NHÃN hiển thị cho
 * đúng ngữ cảnh, không ảnh hưởng logic tìm kiếm.
 *
 * Human-gate GIỮ NGUYÊN: chỉ GỢI Ý (kèm match score), người dùng luôn là người bấm chọn
 * — không có candidate nào tự động gán. */
export default function VaultClipPicker({
  projectId,
  shotId,
  mediaKind,
  onPick,
  disabled,
}: {
  projectId: string;
  shotId: string;
  mediaKind: "video" | "image";
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
      <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setOpen(true)} disabled={disabled} title={`Gợi ý ${mediaKind === "video" ? "clip video" : "ảnh"} từ Kho tư liệu của kênh, khớp mô tả Visual/FX của shot này`}>
        {mediaKind === "video" ? "Video từ Kho" : "Ảnh từ Kho"}
      </button>
      {open && (
        <div className="dialog-backdrop" onClick={() => setOpen(false)}>
          <div className="dialog" style={{ width: "min(480px,100%)", maxHeight: "70vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
            <div className="dialog-title">Chọn {mediaKind === "video" ? "clip" : "ảnh"} từ Kho tư liệu</div>
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
                Kho tư liệu của kênh này chưa có {mediaKind === "video" ? "clip" : "ảnh"} nào khớp — thêm{" "}
                {mediaKind === "video" ? "video" : "ảnh"} trong <strong>Kho Tài Nguyên</strong>.
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
                        display: "flex", gap: 10, padding: "8px 10px",
                        borderRadius: "var(--radius-sm)", cursor: pickingId ? "default" : "pointer", background: "var(--color-bg)",
                        opacity: pickingId && pickingId !== c.clip_id ? 0.5 : 1,
                      }}
                    >
                      <div style={{ width: 56, height: 42, flex: "none", borderRadius: 4, overflow: "hidden", background: "var(--color-neutral-800)" }}>
                        {mediaKind === "image" ? (
                          // eslint-disable-next-line jsx-a11y/alt-text
                          <img src={api.clipFileUrl(c.clip_id)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        ) : (
                          // eslint-disable-next-line jsx-a11y/media-has-caption
                          <video src={api.clipFileUrl(c.clip_id)} preload="metadata" muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        )}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{c.caption || c.clip_id}</span>
                          {c.match_score != null && (
                            <span className="tag tag-accent" style={{ fontSize: 10.5, flex: "none" }}>
                              {Math.round(c.match_score * 100)}% match
                            </span>
                          )}
                        </div>
                        {(c.tags.length > 0 || c.mood_tone) && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {c.mood_tone && (
                              <span className="tag tag-outline" style={{ fontSize: 10 }}>
                                {c.mood_tone}
                              </span>
                            )}
                            {c.tags.slice(0, 3).map((t) => (
                              <span key={t} className="tag tag-outline" style={{ fontSize: 10 }}>
                                {t}
                              </span>
                            ))}
                          </div>
                        )}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, opacity: 0.75, gap: 8 }}>
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {mediaKind === "video" ? `${c.duration_sec.toFixed(1)}s` : c.resolution || ""}
                            {c.usage_count > 0 ? ` · Đã dùng ${c.usage_count} lần` : ""}
                          </span>
                          {!c.from_visual_studio && (
                            <span style={{ color: rights.color, flex: "none" }}>{rights.text}</span>
                          )}
                        </div>
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
