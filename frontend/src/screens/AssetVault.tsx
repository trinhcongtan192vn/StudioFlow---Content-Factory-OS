import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { api, ApiError } from "../api/client";
import { useApp } from "../store/AppContext";
import type { ClipRightsStatus, ProcessedClip, RawVideo } from "../api/types";
import ProgressBar from "../components/ProgressBar";

/** Kho Tài Nguyên — màn RIÊNG ở sidebar (2026-08-27, thay cho tab cũ trong ChannelDialog)
 * — hiện TẤT CẢ video/clip từ MỌI kênh, lọc theo kênh qua dropdown. 1 video gốc gắn được
 * NHIỀU kênh dạng tag (bắt buộc ≥1 lúc import). Human-gate giữ nguyên: mọi hành động AI
 * (cắt cảnh, gắn nhãn) đều do người dùng TỰ BẤM, không có gì chạy nền tự động khi mở màn
 * này. */
export default function AssetVault() {
  const [rawVideos, setRawVideos] = useState<RawVideo[]>([]);
  const [clips, setClips] = useState<ProcessedClip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [raw, clipList] = await Promise.all([api.listRawVideos(), api.listProcessedClips()]);
      setRawVideos(raw);
      setClips(clipList);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi tải Kho tài nguyên.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll nhẹ khi có video đang xử lý (detecting/tagging) — badge/thanh tiến trình tự cập
  // nhật, không cần bấm tải lại thủ công (cùng pattern RenderStudio.tsx).
  useEffect(() => {
    const hasPending = rawVideos.some((r) => r.status === "detecting" || r.status === "tagging");
    if (!hasPending) return;
    const id = window.setInterval(load, 2500);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawVideos]);

  return (
    <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "var(--space-8)" }}>
      <div style={{ marginBottom: "var(--space-2)" }}>
        <h2 style={{ marginBottom: 2 }}>Kho Tài nguyên</h2>
        <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, margin: 0 }}>
          Video gốc + clip B-roll đã cắt cảnh từ mọi kênh — gắn nhiều kênh dạng tag cho 1 video gốc, dùng lại clip khi ghép Visual Studio. Mỗi bảng bên dưới có bộ lọc kênh riêng.
        </p>
      </div>

      {error && (
        <div style={{ fontSize: 12.5, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "6px 8px", marginBottom: "var(--space-4)" }}>{error}</div>
      )}

      {loading ? (
        <div style={{ opacity: 0.6, fontSize: 13 }}>Đang tải...</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <RawLibrarySection rawVideos={rawVideos} clips={clips} onChanged={load} />
          <ProcessedClipLibrarySection clips={clips} rawVideos={rawVideos} onChanged={load} />
        </div>
      )}
    </div>
  );
}

const _STATUS_LABEL: Record<string, { text: string; color: string }> = {
  detecting: { text: "Đang cắt cảnh", color: "var(--color-accent)" },
  tagging: { text: "Đang gắn nhãn", color: "var(--color-warning)" },
  indexed: { text: "Đã lập chỉ mục", color: "#4ade80" },
  error: { text: "Lỗi", color: "var(--color-danger)" },
};

function StatusBadge({ status }: { status: string }) {
  const info = _STATUS_LABEL[status] || { text: status, color: "var(--color-text)" };
  return (
    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: `color-mix(in srgb, ${info.color} 18%, transparent)`, color: info.color, whiteSpace: "nowrap" }}>
      {info.text}
    </span>
  );
}

const _RIGHTS_LABEL: Record<ClipRightsStatus, { text: string; color: string }> = {
  unverified: { text: "Chưa xác minh", color: "var(--color-warning)" },
  licensed_verified: { text: "Đã xác minh", color: "#4ade80" },
  public_domain: { text: "Public domain", color: "#4ade80" },
};

function RightsBadge({ status }: { status: ClipRightsStatus }) {
  const info = _RIGHTS_LABEL[status];
  return (
    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999, background: `color-mix(in srgb, ${info.color} 18%, transparent)`, color: info.color, whiteSpace: "nowrap" }}>
      {info.text}
    </span>
  );
}

function ChannelChips({ channels }: { channels: { id: string; name: string }[] }) {
  if (!channels.length) return null;
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {channels.map((c) => (
        <span key={c.id} style={{ fontSize: 10, padding: "1px 6px", borderRadius: 999, background: "color-mix(in srgb, var(--color-accent) 15%, transparent)", color: "var(--color-accent)", whiteSpace: "nowrap" }}>
          {c.name}
        </span>
      ))}
    </div>
  );
}

/** Multi-select checkbox kênh — bắt buộc ≥1 trước khi import (đúng yêu cầu "gắn tên Kênh
 * TRƯỚC KHI cắt cảnh"). */
function ChannelMultiSelect({ selected, onChange }: { selected: Set<string>; onChange: (next: Set<string>) => void }) {
  const app = useApp();
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", padding: "6px 8px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--color-text) 4%, transparent)" }}>
      {app.channels.length === 0 ? (
        <span style={{ fontSize: 12, opacity: 0.6 }}>Chưa có kênh nào — tạo kênh trước ở Dashboard.</span>
      ) : (
        app.channels.map((c) => {
          const checked = selected.has(c.id);
          return (
            <label key={c.id} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={checked}
                onChange={() => {
                  const next = new Set(selected);
                  if (checked) next.delete(c.id);
                  else next.add(c.id);
                  onChange(next);
                }}
              />
              {c.name}
            </label>
          );
        })
      )}
    </div>
  );
}

/** Mở thư mục lưu trữ thật trên máy (Explorer/Finder) — CHỈ hiện khi chạy trong Electron
 * (`window.studioflowNative` không tồn tại lúc chạy dev server thuần trình duyệt, cùng
 * pattern `hasNativePicker` ở OutputCenter.tsx). Đường dẫn lấy lười (lúc bấm, không fetch
 * sẵn) — hành động hiếm dùng, không đáng 1 request mỗi lần mở màn. */
function OpenFolderButton({ getPath, label }: { getPath: () => Promise<string>; label: string }) {
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (typeof window === "undefined" || !window.studioflowNative) return null;

  async function handleClick() {
    setOpening(true);
    setError(null);
    try {
      const path = await getPath();
      await window.studioflowNative!.openFolder(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Có lỗi khi mở thư mục.");
    } finally {
      setOpening(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {error && (
        <span style={{ fontSize: 11, color: "var(--color-danger)" }} title={error}>
          Lỗi mở thư mục
        </span>
      )}
      <button type="button" className="btn btn-secondary" style={{ fontSize: 11, padding: "2px 8px" }} disabled={opening} onClick={handleClick} title={label}>
        {opening ? "Đang mở..." : "Mở thư mục"}
      </button>
    </div>
  );
}

function RawLibrarySection({ rawVideos, clips, onChanged }: { rawVideos: RawVideo[]; clips: ProcessedClip[]; onChanged: () => void }) {
  const app = useApp();
  const [uploading, setUploading] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [importNote, setImportNote] = useState("");
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [filterChannel, setFilterChannel] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [previewRaw, setPreviewRaw] = useState<RawVideo | null>(null);
  const [bulkAddingChannel, setBulkAddingChannel] = useState(false);
  const [bulkChannelDraft, setBulkChannelDraft] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const channelIds = Array.from(selectedChannels);

  // Upload nhiều file 1 lúc (2026-08-27) — xử lý TUẦN TỰ, mỗi file lỗi được cô lập (báo
  // lỗi kèm tên file, không chặn các file còn lại), đúng nguyên tắc "1 phần lỗi không
  // chặn cả batch" đã dùng cho gắn nhãn hàng loạt clip. Tên file gốc được BE lưu nguyên
  // vào `original_filename` (xem `_raw_video_name`) — người dùng luôn biết đã upload file
  // nào, kể cả khi tên trên đĩa có thêm mã ID.
  async function handleFilesPicked(files: File[]) {
    if (channelIds.length === 0) {
      setLocalError("Phải chọn ít nhất 1 kênh trước khi upload video.");
      return;
    }
    setUploading(true);
    setLocalError(null);
    const failed: string[] = [];
    for (const file of files) {
      try {
        await api.uploadRawVideo(channelIds, file, importNote);
      } catch (e) {
        failed.push(`${file.name}: ${e instanceof ApiError ? e.message : "lỗi upload"}`);
      }
    }
    if (failed.length) setLocalError(`${failed.length}/${files.length} file lỗi — ${failed.join("; ")}`);
    else setImportNote("");
    setUploading(false);
    onChanged();
  }

  async function handleImportUrl() {
    if (!urlInput.trim()) return;
    if (channelIds.length === 0) {
      setLocalError("Phải chọn ít nhất 1 kênh trước khi tải video.");
      return;
    }
    setUploading(true);
    setLocalError(null);
    try {
      await api.importRawVideoFromUrl(channelIds, urlInput.trim(), importNote);
      setUrlInput("");
      setImportNote("");
      onChanged();
    } catch (e) {
      setLocalError(e instanceof ApiError ? e.message : "Có lỗi khi tải video từ URL.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDetectScenes(rawId: string) {
    setBusyId(rawId);
    try {
      await api.detectScenes(rawId);
      onChanged();
    } finally {
      setBusyId(null);
    }
  }

  async function handleCaptionAll(rawId: string) {
    setBusyId(rawId);
    try {
      await api.captionAllClips(rawId);
      onChanged();
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemoveWatermark(rawId: string) {
    setBusyId(rawId);
    try {
      await api.removeWatermark(rawId);
      onChanged();
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(rawId: string) {
    if (!confirm("Xoá video gốc này? Clip đã cắt từ video này KHÔNG bị xoá theo.")) return;
    await api.deleteRawVideo(rawId);
    onChanged();
  }

  async function handleRetag(raw: RawVideo, nextIds: Set<string>) {
    if (nextIds.size === 0) return;
    await api.patchRawVideoChannels(raw.id, Array.from(nextIds));
    onChanged();
  }

  const filtered = rawVideos.filter((r) => !filterChannel || r.channels.some((c) => c.id === filterChannel));
  const allSelected = filtered.length > 0 && filtered.every((r) => selected.has(r.id));

  function toggleSelectAll() {
    setSelected((s) => {
      const next = new Set(s);
      if (allSelected) filtered.forEach((r) => next.delete(r.id));
      else filtered.forEach((r) => next.add(r.id));
      return next;
    });
  }
  function toggleSelect(rawId: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(rawId)) next.delete(rawId);
      else next.add(rawId);
      return next;
    });
  }

  async function handleBulkAddChannels() {
    if (bulkChannelDraft.size === 0) return;
    setBulkBusy(true);
    setBulkError(null);
    try {
      await api.batchTagRawVideoChannels(Array.from(selected), Array.from(bulkChannelDraft));
      setBulkAddingChannel(false);
      setBulkChannelDraft(new Set());
      onChanged();
    } catch (e) {
      setBulkError(e instanceof ApiError ? e.message : "Có lỗi khi gắn kênh hàng loạt.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleBulkDelete() {
    if (!confirm(`Xoá ${selected.size} video gốc đã chọn? Clip đã cắt từ các video này KHÔNG bị xoá theo.`)) return;
    setBulkBusy(true);
    setBulkError(null);
    try {
      await api.batchDeleteRawVideos(Array.from(selected));
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setBulkError(e instanceof ApiError ? e.message : "Có lỗi khi xoá hàng loạt.");
    } finally {
      setBulkBusy(false);
    }
  }

  // Cắt cảnh / gắn nhãn / xoá watermark hàng loạt — KHÔNG có endpoint batch riêng ở BE
  // (chỉ gắn kênh + xoá mới có, xem client.ts), nên lặp gọi endpoint đơn từng video, cô
  // lập lỗi từng video (không chặn các video còn lại), giống hệt nguyên tắc dùng cho
  // upload nhiều file.
  async function handleBulkRun(action: (rawId: string) => Promise<unknown>, eligible: RawVideo[]) {
    setBulkBusy(true);
    setBulkError(null);
    const failed: string[] = [];
    for (const r of eligible) {
      try {
        await action(r.id);
      } catch (e) {
        failed.push(`${rawVideoLabel(r)}: ${e instanceof ApiError ? e.message : "lỗi"}`);
      }
    }
    if (failed.length) setBulkError(`${failed.length}/${eligible.length} video lỗi — ${failed.join("; ")}`);
    setBulkBusy(false);
    onChanged();
  }

  const selectedRaws = filtered.filter((r) => selected.has(r.id));
  const selectedDetecting = selectedRaws.filter((r) => r.status === "detecting" && r.progress_total == null);
  const selectedTagging = selectedRaws.filter((r) => r.status === "tagging");

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-2)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div className="card-kicker">Video gốc (Raw Library)</div>
        <OpenFolderButton getPath={async () => (await api.getAssetVaultFolders()).raw_dir} label="Mở thư mục video gốc" />
      </div>
      <div style={{ fontSize: 11.5, opacity: 0.65 }}>Chọn kênh gắn tag trước khi import:</div>
      <ChannelMultiSelect selected={selectedChannels} onChange={setSelectedChannels} />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <input className="input" style={{ flex: 1, minWidth: 160 }} placeholder="Ghi chú nguồn/license (tuỳ chọn)" value={importNote} onChange={(e) => setImportNote(e.target.value)} />
        <label className="btn btn-secondary" style={{ cursor: uploading ? "not-allowed" : "pointer" }}>
          {uploading ? "Đang xử lý..." : "+ Upload video (chọn nhiều được)"}
          <input
            type="file"
            multiple
            accept="video/mp4,video/webm,video/quicktime"
            style={{ display: "none" }}
            disabled={uploading}
            onChange={(e) => {
              const files = Array.from(e.target.files || []);
              e.target.value = "";
              if (files.length) handleFilesPicked(files);
            }}
          />
        </label>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input className="input" style={{ flex: 1 }} placeholder="Dán URL video (tải về khi bấm xác nhận)" value={urlInput} onChange={(e) => setUrlInput(e.target.value)} />
        <button className="btn btn-secondary" onClick={handleImportUrl} disabled={uploading || !urlInput.trim()}>
          Tải về
        </button>
      </div>
      {localError && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{localError}</div>}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <select className="input" style={{ width: "auto" }} value={filterChannel} onChange={(e) => setFilterChannel(e.target.value)}>
          <option value="">Mọi kênh</option>
          {app.channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {bulkError && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{bulkError}</div>}

      {selected.size > 0 && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5, padding: "6px 8px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--color-accent) 10%, transparent)", flexWrap: "wrap" }}>
          <span>{selected.size} video đã chọn</span>
          {bulkAddingChannel ? (
            <>
              <ChannelMultiSelect selected={bulkChannelDraft} onChange={setBulkChannelDraft} />
              <button className="btn btn-primary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy || bulkChannelDraft.size === 0} onClick={handleBulkAddChannels}>
                Lưu
              </button>
              <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => { setBulkAddingChannel(false); setBulkChannelDraft(new Set()); }}>
                Huỷ
              </button>
            </>
          ) : (
            <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy} onClick={() => setBulkAddingChannel(true)}>
              + Thêm kênh
            </button>
          )}
          {selectedDetecting.length > 0 && (
            <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy} onClick={() => handleBulkRun(api.detectScenes, selectedDetecting)}>
              Cắt cảnh tự động ({selectedDetecting.length})
            </button>
          )}
          {selectedTagging.length > 0 && (
            <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy} onClick={() => handleBulkRun(api.captionAllClips, selectedTagging)}>
              Gắn nhãn ({selectedTagging.length})
            </button>
          )}
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy} onClick={() => handleBulkRun(api.removeWatermark, selectedRaws)}>
            Xoá watermark ({selectedRaws.length})
          </button>
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy} onClick={handleBulkDelete}>
            Xoá
          </button>
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkBusy} onClick={() => setSelected(new Set())}>
            Bỏ chọn
          </button>
        </div>
      )}

      {filtered.length === 0 ? (
        <div style={{ fontSize: 12.5, opacity: 0.65 }}>Chưa có video gốc nào khớp bộ lọc — upload hoặc dán URL ở trên.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-divider)", textAlign: "left" }}>
                <Th style={{ width: 24 }}>
                  <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
                </Th>
                <Th style={{ width: 36 }}></Th>
                <Th>Tên file</Th>
                <Th>Kênh</Th>
                <Th>Trạng thái</Th>
                <Th>Ghi chú</Th>
                <Th>Ngày tạo</Th>
                <Th>Hành động</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <RawVideoRow
                  key={r.id}
                  raw={r}
                  hasClips={clips.some((c) => c.raw_video_id === r.id)}
                  selected={selected.has(r.id)}
                  busy={busyId === r.id}
                  onToggleSelect={() => toggleSelect(r.id)}
                  onPreview={() => setPreviewRaw(r)}
                  onRetag={(next) => handleRetag(r, next)}
                  onDetectScenes={() => handleDetectScenes(r.id)}
                  onCaptionAll={() => handleCaptionAll(r.id)}
                  onRemoveWatermark={() => handleRemoveWatermark(r.id)}
                  onDelete={() => handleDelete(r.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {previewRaw && <RawVideoPreviewPanel raw={previewRaw} onClose={() => setPreviewRaw(null)} />}
    </div>
  );
}

function RawVideoRow({
  raw,
  hasClips,
  selected,
  busy,
  onToggleSelect,
  onPreview,
  onRetag,
  onDetectScenes,
  onCaptionAll,
  onRemoveWatermark,
  onDelete,
}: {
  raw: RawVideo;
  hasClips: boolean;
  selected: boolean;
  busy: boolean;
  onToggleSelect: () => void;
  onPreview: () => void;
  onRetag: (next: Set<string>) => void;
  onDetectScenes: () => void;
  onCaptionAll: () => void;
  onRemoveWatermark: () => void;
  onDelete: () => void;
}) {
  return (
    <tr style={{ borderBottom: "1px solid var(--color-divider)" }}>
      <Td>
        <input type="checkbox" checked={selected} onChange={onToggleSelect} />
      </Td>
      <Td>
        <button
          type="button"
          className="btn btn-icon btn-secondary"
          title="Xem trước video"
          onClick={onPreview}
          style={{ width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="6 3 20 12 6 21 6 3" />
          </svg>
        </button>
      </Td>
      <Td style={{ maxWidth: 220 }}>
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={raw.original_filename || rawVideoLabel(raw)}>
          {rawVideoLabel(raw)}
        </div>
      </Td>
      <Td style={{ maxWidth: 150 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
          <ChannelChips channels={raw.channels} />
          <ChannelRetag channels={raw.channels} onRetag={onRetag} />
        </div>
      </Td>
      <Td>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
          <StatusBadge status={raw.status} />
          {raw.progress_total != null && raw.progress_current != null && (
            <ProgressBar current={raw.progress_current} total={raw.progress_total} label={raw.progress_label} />
          )}
          {raw.status === "error" && raw.error_message && (
            <span style={{ color: "var(--color-danger)", fontSize: 10.5 }} title={raw.error_message}>
              {raw.error_message.slice(0, 60)}
            </span>
          )}
        </div>
      </Td>
      <Td style={{ maxWidth: 180 }}>
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", opacity: 0.75 }} title={raw.import_note}>
          {raw.import_note || "—"}
        </div>
      </Td>
      <Td style={{ whiteSpace: "nowrap", fontSize: 11, opacity: 0.7 }}>{new Date(raw.created_at).toLocaleDateString("vi-VN")}</Td>
      <Td style={{ whiteSpace: "nowrap" }}>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {raw.status === "detecting" && raw.progress_total == null && (
            <>
              <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} disabled={busy} onClick={onDetectScenes}>
                Cắt cảnh tự động
              </button>
              <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} disabled={busy} onClick={onRemoveWatermark} title="Xoá watermark trước khi cắt cảnh (Florence-2 + LaMa)">
                Xoá watermark
              </button>
            </>
          )}
          {raw.status === "tagging" && (
            <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} disabled={busy} onClick={onCaptionAll}>
              Gắn nhãn
            </button>
          )}
          {raw.status === "error" && (
            <>
              {hasClips ? (
                <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} disabled={busy} onClick={onCaptionAll}>
                  Gắn nhãn lại
                </button>
              ) : (
                <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} disabled={busy} onClick={onDetectScenes}>
                  Cắt cảnh lại
                </button>
              )}
            </>
          )}
          <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} disabled={busy} onClick={onDelete}>
            Xoá
          </button>
        </div>
      </Td>
    </tr>
  );
}

/** Sửa lại tag kênh — bấm để mở popover chọn lại (PATCH ghi đè toàn bộ danh sách). Dùng
 * chung cho cả video gốc (`api.patchRawVideoChannels` — cascade xuống clip con, xem
 * IMPLEMENTATION_REPORT.md mục 98) lẫn 1 clip riêng lẻ (`api.patchClipChannels` — độc lập
 * với raw_video cha, không cascade) — `channels` là giá trị BAN ĐẦU để mở popover, caller
 * tự quyết định gọi API nào trong `onRetag`. */
function ChannelRetag({ channels, onRetag }: { channels: { id: string; name: string }[]; onRetag: (next: Set<string>) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Set<string>>(new Set(channels.map((c) => c.id)));

  if (!open) {
    return (
      <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => { setDraft(new Set(channels.map((c) => c.id))); setOpen(true); }}>
        Sửa tag kênh
      </button>
    );
  }
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <ChannelMultiSelect selected={draft} onChange={setDraft} />
      <button
        className="btn btn-primary"
        style={{ padding: "2px 8px", fontSize: 11 }}
        onClick={() => {
          onRetag(draft);
          setOpen(false);
        }}
        disabled={draft.size === 0}
      >
        Lưu
      </button>
      <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setOpen(false)}>
        Huỷ
      </button>
    </div>
  );
}

function rawVideoLabel(r: RawVideo): string {
  if (r.original_filename) return r.original_filename;
  if (r.import_note) return r.import_note;
  if (r.source_url) return r.source_url.replace(/\/+$/, "").split("/").pop() || r.source_url;
  return r.id;
}

const _RAW_STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "detecting", label: "Đang cắt cảnh" },
  { value: "tagging", label: "Đang gắn nhãn" },
  { value: "indexed", label: "Đã lập chỉ mục" },
  { value: "error", label: "Lỗi" },
];

function ProcessedClipLibrarySection({
  clips,
  rawVideos,
  onChanged,
}: {
  clips: ProcessedClip[];
  rawVideos: RawVideo[];
  onChanged: () => void;
}) {
  const app = useApp();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filterChannel, setFilterChannel] = useState("");
  const [filterRights, setFilterRights] = useState("");
  const [filterRaw, setFilterRaw] = useState("");
  const [filterUnlabeled, setFilterUnlabeled] = useState(false);
  const [filterRawStatus, setFilterRawStatus] = useState("");
  const [previewClip, setPreviewClip] = useState<ProcessedClip | null>(null);
  const [bulkCaptioning, setBulkCaptioning] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [bulkAddingChannel, setBulkAddingChannel] = useState(false);
  const [bulkChannelDraft, setBulkChannelDraft] = useState<Set<string>>(new Set());
  const [bulkTaggingChannel, setBulkTaggingChannel] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  // Đang gắn nhãn hàng loạt — tự poll (tái dùng `onChanged` của cha) tới khi MỌI clip vừa
  // gửi đều có `caption`/`caption_error` mới (chạy nền server-side, xem
  // `api.captionClipsBatch`), KHÔNG cần 1 field trạng thái riêng ở BE — suy ra tiến trình
  // trực tiếp từ chính dữ liệu clip đã có.
  const [pendingCaptionIds, setPendingCaptionIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (pendingCaptionIds.size === 0) return;
    const id = window.setInterval(onChanged, 2000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingCaptionIds.size]);

  useEffect(() => {
    if (pendingCaptionIds.size === 0) return;
    setPendingCaptionIds((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const clipId of prev) {
        const clip = clips.find((c) => c.clip_id === clipId);
        if (clip && (clip.caption || clip.caption_error)) {
          next.delete(clipId);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clips]);

  const filtered = clips.filter(
    (c) =>
      (!filterChannel || c.channels.some((ch) => ch.id === filterChannel)) &&
      (!filterRights || c.rights_status === filterRights) &&
      (!filterRaw || c.raw_video_id === filterRaw) &&
      (!filterUnlabeled || !c.caption) &&
      (!filterRawStatus || c.raw_video_status === filterRawStatus),
  );

  const allSelected = filtered.length > 0 && filtered.every((c) => selected.has(c.clip_id));
  function toggleSelectAll() {
    setSelected((s) => {
      const next = new Set(s);
      if (allSelected) filtered.forEach((c) => next.delete(c.clip_id));
      else filtered.forEach((c) => next.add(c.clip_id));
      return next;
    });
  }
  function toggleSelect(clipId: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(clipId)) next.delete(clipId);
      else next.add(clipId);
      return next;
    });
  }

  async function batchSetRights(status: ClipRightsStatus) {
    await api.batchPatchProcessedClips({ clip_ids: Array.from(selected), rights_status: status });
    setSelected(new Set());
    onChanged();
  }

  async function handleBulkCaption() {
    const ids = Array.from(selected);
    setBulkCaptioning(true);
    setBulkError(null);
    try {
      await api.captionClipsBatch(ids);
      setPendingCaptionIds((s) => new Set([...s, ...ids]));
      setSelected(new Set());
    } catch (e) {
      setBulkError(e instanceof ApiError ? e.message : "Có lỗi khi gắn nhãn hàng loạt.");
    } finally {
      setBulkCaptioning(false);
    }
  }

  async function handleBulkAddChannels() {
    if (bulkChannelDraft.size === 0) return;
    setBulkTaggingChannel(true);
    setBulkError(null);
    try {
      await api.batchTagClipChannels(Array.from(selected), Array.from(bulkChannelDraft));
      setBulkAddingChannel(false);
      setBulkChannelDraft(new Set());
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setBulkError(e instanceof ApiError ? e.message : "Có lỗi khi gắn kênh hàng loạt.");
    } finally {
      setBulkTaggingChannel(false);
    }
  }

  async function handleRetagClip(clipId: string, nextIds: Set<string>) {
    if (nextIds.size === 0) return;
    await api.patchClipChannels(clipId, Array.from(nextIds));
    onChanged();
  }

  async function handleDeleteClip(clipId: string) {
    if (!confirm("Xoá clip này khỏi Kho tài nguyên?")) return;
    await api.deleteProcessedClip(clipId);
    onChanged();
  }

  async function handleBulkDeleteClips() {
    if (!confirm(`Xoá ${selected.size} clip đã chọn khỏi Kho tài nguyên? Không thể hoàn tác.`)) return;
    setBulkDeleting(true);
    setBulkError(null);
    try {
      await api.batchDeleteProcessedClips(Array.from(selected));
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setBulkError(e instanceof ApiError ? e.message : "Có lỗi khi xoá hàng loạt.");
    } finally {
      setBulkDeleting(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-2)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div className="card-kicker">Clip đã cắt (Processed Clip Library)</div>
        <OpenFolderButton getPath={async () => (await api.getAssetVaultFolders()).clips_dir} label="Mở thư mục clip đã cắt" />
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <select className="input" style={{ width: "auto" }} value={filterChannel} onChange={(e) => setFilterChannel(e.target.value)}>
          <option value="">Mọi kênh</option>
          {app.channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className="input" style={{ width: "auto" }} value={filterRights} onChange={(e) => setFilterRights(e.target.value)}>
          <option value="">Mọi trạng thái rights</option>
          <option value="unverified">Chưa xác minh</option>
          <option value="licensed_verified">Đã xác minh</option>
          <option value="public_domain">Public domain</option>
        </select>
        <select className="input" style={{ width: "auto" }} value={filterRawStatus} onChange={(e) => setFilterRawStatus(e.target.value)}>
          <option value="">Mọi trạng thái video gốc</option>
          {_RAW_STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select className="input" style={{ width: "auto" }} value={filterRaw} onChange={(e) => setFilterRaw(e.target.value)}>
          <option value="">Mọi video gốc</option>
          {rawVideos.map((r) => (
            <option key={r.id} value={r.id}>
              {rawVideoLabel(r)}
            </option>
          ))}
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12.5, cursor: "pointer" }}>
          <input type="checkbox" checked={filterUnlabeled} onChange={(e) => setFilterUnlabeled(e.target.checked)} />
          Chưa gắn nhãn
        </label>
      </div>

      {bulkError && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{bulkError}</div>}

      {selected.size > 0 && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5, padding: "6px 8px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--color-accent) 10%, transparent)", flexWrap: "wrap" }}>
          <span>{selected.size} clip đã chọn</span>
          <button className="btn btn-primary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkCaptioning} onClick={handleBulkCaption}>
            {bulkCaptioning ? "Đang gửi..." : "Gắn nhãn (AI)"}
          </button>
          {bulkAddingChannel ? (
            <>
              <ChannelMultiSelect selected={bulkChannelDraft} onChange={setBulkChannelDraft} />
              <button className="btn btn-primary" style={{ padding: "2px 8px", fontSize: 11.5 }} disabled={bulkTaggingChannel || bulkChannelDraft.size === 0} onClick={handleBulkAddChannels}>
                Lưu
              </button>
              <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => { setBulkAddingChannel(false); setBulkChannelDraft(new Set()); }}>
                Huỷ
              </button>
            </>
          ) : (
            <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => setBulkAddingChannel(true)}>
              + Thêm kênh
            </button>
          )}
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => batchSetRights("licensed_verified")}>
            Đặt: Đã xác minh
          </button>
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => batchSetRights("public_domain")}>
            Đặt: Public domain
          </button>
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5, color: "var(--color-danger)" }} disabled={bulkDeleting} onClick={handleBulkDeleteClips}>
            {bulkDeleting ? "Đang xoá..." : "Xoá"}
          </button>
          <button className="btn btn-secondary" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => setSelected(new Set())}>
            Bỏ chọn
          </button>
        </div>
      )}
      {pendingCaptionIds.size > 0 && (
        <div style={{ fontSize: 12, color: "var(--color-accent)" }}>Đang gắn nhãn {pendingCaptionIds.size} clip trong nền...</div>
      )}

      {filtered.length === 0 ? (
        <div style={{ fontSize: 12.5, opacity: 0.65 }}>Chưa có clip nào khớp bộ lọc — cắt cảnh + gắn nhãn video gốc ở trên trước.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-divider)", textAlign: "left" }}>
                <Th style={{ width: 24 }}>
                  <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
                </Th>
                <Th style={{ width: 36 }}></Th>
                <Th>Video nguồn</Th>
                <Th>Kênh</Th>
                <Th style={{ minWidth: 220 }}>Caption</Th>
                <Th>Tags / Mood</Th>
                <Th>Rights</Th>
                <Th>Thời lượng</Th>
                <Th>Độ phân giải</Th>
                <Th>Dùng</Th>
                <Th>Trạng thái</Th>
                <Th>Ngày tạo</Th>
                <Th>Hành động</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <ClipRow
                  key={c.clip_id}
                  clip={c}
                  rawVideo={rawVideos.find((r) => r.id === c.raw_video_id)}
                  selected={selected.has(c.clip_id)}
                  pendingCaption={pendingCaptionIds.has(c.clip_id)}
                  onToggleSelect={() => toggleSelect(c.clip_id)}
                  onChanged={onChanged}
                  onDelete={() => handleDeleteClip(c.clip_id)}
                  onPreview={() => setPreviewClip(c)}
                  onRetag={(next) => handleRetagClip(c.clip_id, next)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {previewClip && <ClipPreviewPanel clip={previewClip} onClose={() => setPreviewClip(null)} />}
    </div>
  );
}

function Th({ children, style }: { children?: ReactNode; style?: CSSProperties }) {
  return (
    <th style={{ padding: "6px 8px", fontSize: 11, textTransform: "uppercase", letterSpacing: ".02em", opacity: 0.6, fontWeight: 600, whiteSpace: "nowrap", ...style }}>
      {children}
    </th>
  );
}

function Td({ children, style }: { children?: ReactNode; style?: CSSProperties }) {
  return <td style={{ padding: "6px 8px", verticalAlign: "top", ...style }}>{children}</td>;
}

function ClipRow({
  clip,
  rawVideo,
  selected,
  pendingCaption,
  onToggleSelect,
  onChanged,
  onDelete,
  onPreview,
  onRetag,
}: {
  clip: ProcessedClip;
  rawVideo: RawVideo | undefined;
  selected: boolean;
  pendingCaption: boolean;
  onToggleSelect: () => void;
  onChanged: () => void;
  onDelete: () => void;
  onPreview: () => void;
  onRetag: (next: Set<string>) => void;
}) {
  async function toggleActive() {
    await api.patchProcessedClip(clip.clip_id, { active: !clip.active });
    onChanged();
  }

  return (
    <tr style={{ borderBottom: "1px solid var(--color-divider)", opacity: clip.active ? 1 : 0.5 }}>
      <Td>
        <input type="checkbox" checked={selected} onChange={onToggleSelect} />
      </Td>
      <Td>
        <button
          type="button"
          className="btn btn-icon btn-secondary"
          title="Xem trước video"
          onClick={onPreview}
          style={{ width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="6 3 20 12 6 21 6 3" />
          </svg>
        </button>
      </Td>
      <Td style={{ maxWidth: 160 }}>
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={clip.raw_video_name}>
          {clip.raw_video_name}
        </div>
      </Td>
      <Td style={{ maxWidth: 150 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
          <ChannelChips channels={clip.channels} />
          {/* Sửa tag kênh RIÊNG của clip này (không cascade sang clip anh em/raw_video cha)
              — hoạt động cả khi raw_video cha đã bị xoá (clip mồ côi), xem mục 98. */}
          <ChannelRetag channels={clip.channels} onRetag={onRetag} />
        </div>
      </Td>
      <Td style={{ minWidth: 220 }}>
        <ClipCaptionCell clip={clip} onChanged={onChanged} />
      </Td>
      <Td style={{ maxWidth: 160 }}>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {clip.tags.map((t) => (
            <span key={t} style={{ fontSize: 10, padding: "1px 6px", borderRadius: 999, background: "color-mix(in srgb, var(--color-text) 10%, transparent)" }}>
              {t}
            </span>
          ))}
          {clip.mood_tone && (
            <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 999, background: "color-mix(in srgb, var(--color-accent) 15%, transparent)", color: "var(--color-accent)" }}>
              {clip.mood_tone}
            </span>
          )}
        </div>
      </Td>
      <Td>
        <select
          className="input"
          style={{ fontSize: 11, padding: "2px 4px" }}
          value={clip.rights_status}
          onChange={(e) => api.patchProcessedClip(clip.clip_id, { rights_status: e.target.value as ClipRightsStatus }).then(onChanged)}
        >
          <option value="unverified">Chưa xác minh</option>
          <option value="licensed_verified">Đã xác minh</option>
          <option value="public_domain">Public domain</option>
        </select>
      </Td>
      <Td style={{ whiteSpace: "nowrap" }}>{clip.duration_sec.toFixed(1)}s</Td>
      <Td style={{ whiteSpace: "nowrap" }}>{clip.resolution || "—"}</Td>
      <Td style={{ whiteSpace: "nowrap" }}>{clip.usage_count} lần</Td>
      <Td style={{ whiteSpace: "nowrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
          {rawVideo ? <StatusBadge status={rawVideo.status} /> : <span style={{ fontSize: 11, opacity: 0.5 }}>video gốc đã xoá</span>}
          {pendingCaption && <span style={{ fontSize: 10.5, color: "var(--color-accent)" }}>Đang gắn nhãn...</span>}
          {!pendingCaption && clip.caption_error && (
            <span style={{ fontSize: 10.5, color: "var(--color-danger)" }} title={clip.caption_error}>
              Lỗi gắn nhãn
            </span>
          )}
        </div>
      </Td>
      <Td style={{ whiteSpace: "nowrap", fontSize: 11, opacity: 0.7 }}>{new Date(clip.created_at).toLocaleDateString("vi-VN")}</Td>
      <Td style={{ whiteSpace: "nowrap" }}>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} onClick={toggleActive}>
            {clip.active ? "Tắt" : "Bật"}
          </button>
          <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 11 }} onClick={onDelete}>
            Xoá
          </button>
        </div>
      </Td>
    </tr>
  );
}

function ClipCaptionCell({ clip, onChanged }: { clip: ProcessedClip; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(clip.caption);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api.patchProcessedClip(clip.clip_id, { caption: draft });
      setEditing(false);
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <textarea
        className="input"
        rows={2}
        style={{ fontSize: 12, width: "100%", minWidth: 200 }}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        autoFocus
        disabled={saving}
      />
    );
  }
  return (
    <div
      style={{ cursor: "text", minHeight: 20, maxWidth: 320, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
      onClick={() => {
        setDraft(clip.caption);
        setEditing(true);
      }}
      title={clip.caption || "Bấm để nhập caption"}
    >
      {clip.caption || <span style={{ opacity: 0.5 }}>Chưa có caption — bấm để nhập</span>}
    </div>
  );
}

/** Khung panel xem trước dùng chung — trượt vào từ mép phải màn hình, dùng cho cả clip đã
 * cắt và video gốc. Tự chứa, KHÔNG dùng chung `RightPanel.tsx` (component đó gắn chặt vào
 * layout `ProjectView`, không tái dùng được ở màn top-level như Kho Tài nguyên). Nội dung
 * metadata
 * (caption/kênh/rights...) khác nhau giữa clip đã cắt và video gốc nên truyền qua
 * `children`, chỉ phần khung + video player là dùng chung. */
function PreviewPanelShell({ title, videoSrc, onClose, children }: { title: string; videoSrc: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="dialog-backdrop" onClick={onClose} style={{ display: "flex", justifyContent: "flex-end", padding: 0 }}>
      <div
        className="dialog elev-md"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(420px, 92vw)", height: "100vh", maxHeight: "100vh", margin: 0, borderRadius: 0, overflowY: "auto", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
          <div className="dialog-title" style={{ margin: 0 }}>
            {title}
          </div>
          <button className="btn btn-icon btn-secondary" onClick={onClose} title="Đóng">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video src={videoSrc} controls autoPlay style={{ width: "100%", borderRadius: "var(--radius-sm)", background: "#000" }} />
        <div style={{ fontSize: 12.5, display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
      </div>
    </div>
  );
}

function ClipPreviewPanel({ clip, onClose }: { clip: ProcessedClip; onClose: () => void }) {
  return (
    <PreviewPanelShell title="Xem trước clip" videoSrc={api.clipFileUrl(clip.clip_id)} onClose={onClose}>
      <div>
        <span style={{ opacity: 0.6 }}>Video nguồn: </span>
        {clip.raw_video_name}
      </div>
      <ChannelChips channels={clip.channels} />
      <div>{clip.caption || <span style={{ opacity: 0.5 }}>Chưa có caption</span>}</div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {clip.tags.map((t) => (
          <span key={t} style={{ fontSize: 10.5, padding: "1px 6px", borderRadius: 999, background: "color-mix(in srgb, var(--color-text) 10%, transparent)" }}>
            {t}
          </span>
        ))}
      </div>
      <div style={{ opacity: 0.65 }}>
        {clip.duration_sec.toFixed(1)}s · {clip.resolution || "—"} · dùng {clip.usage_count} lần
      </div>
      <RightsBadge status={clip.rights_status} />
    </PreviewPanelShell>
  );
}

function RawVideoPreviewPanel({ raw, onClose }: { raw: RawVideo; onClose: () => void }) {
  return (
    <PreviewPanelShell title="Xem trước video gốc" videoSrc={api.rawVideoFileUrl(raw.id)} onClose={onClose}>
      <div>
        <span style={{ opacity: 0.6 }}>Tên file: </span>
        {rawVideoLabel(raw)}
      </div>
      <ChannelChips channels={raw.channels} />
      {raw.import_note && (
        <div>
          <span style={{ opacity: 0.6 }}>Ghi chú: </span>
          {raw.import_note}
        </div>
      )}
      <StatusBadge status={raw.status} />
    </PreviewPanelShell>
  );
}
