import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CreativeAsset, CreativeAssetKind } from "../api/types";

const SECTIONS: { kind: CreativeAssetKind; label: string; accept: string }[] = [
  { kind: "music", label: "Nhạc nền", accept: "audio/wav,audio/mpeg,audio/mp3" },
  { kind: "video", label: "Video", accept: "video/mp4,video/webm,video/quicktime" },
  { kind: "image", label: "Ảnh", accept: "image/png,image/jpeg,image/webp" },
  { kind: "voice", label: "Giọng đọc", accept: "audio/wav,audio/mpeg,audio/mp3" },
];

export default function Library() {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-8)" }}>
      <h2 style={{ marginBottom: 2 }}>Thư viện</h2>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-6)" }}>
        Nhạc nền/video/ảnh/giọng đọc dùng lại được ở nhiều nơi trong app — upload 1 lần, chọn lại nhanh thay vì tìm lại file trên máy mỗi lần (xem nút "Chọn từ thư viện" ở các màn upload).
      </p>
      {SECTIONS.map((s) => (
        <LibrarySection key={s.kind} kind={s.kind} label={s.label} accept={s.accept} />
      ))}
    </div>
  );
}

function LibrarySection({ kind, label, accept }: { kind: CreativeAssetKind; label: string; accept: string }) {
  const [assets, setAssets] = useState<CreativeAsset[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function load() {
    setAssets(await api.listLibraryAssets(kind));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadLibraryAsset(kind, file);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function remove(id: string, name: string) {
    if (!confirm(`Xoá "${name}" khỏi thư viện? File trên đĩa sẽ mất — không thể hoàn tác.`)) return;
    setBusyId(id);
    try {
      await api.deleteLibraryAsset(id);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div style={{ marginBottom: "var(--space-8)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
        <h4 style={{ margin: 0 }}>{label} {assets && `(${assets.length})`}</h4>
        <div>
          <input ref={fileRef} type="file" accept={accept} style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
          <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Đang tải lên..." : `+ Upload ${label.toLowerCase()}`}
          </button>
        </div>
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--color-danger)", marginBottom: 8 }}>{error}</div>}
      {assets === null ? (
        <div style={{ opacity: 0.6, fontSize: 13 }}>Đang tải...</div>
      ) : assets.length === 0 ? (
        <div style={{ opacity: 0.55, fontSize: 13 }}>Chưa có {label.toLowerCase()} nào trong thư viện.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "var(--space-3)" }}>
          {assets.map((a) => (
            <AssetCard key={a.id} kind={kind} asset={a} busy={busyId === a.id} onRenamed={load} onDelete={() => remove(a.id, a.name)} />
          ))}
        </div>
      )}
    </div>
  );
}

/** 1 card asset — preview + tên (chỉnh trực tiếp tại chỗ, **mới 2026-08-21** theo yêu
 * cầu người dùng) + nút Xoá. */
function AssetCard({
  kind,
  asset,
  busy,
  onRenamed,
  onDelete,
}: {
  kind: CreativeAssetKind;
  asset: CreativeAsset;
  busy: boolean;
  onRenamed: () => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState(asset.name);
  const [renaming, setRenaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!nameDraft.trim()) return;
    setRenaming(true);
    setError(null);
    try {
      await api.renameLibraryAsset(asset.id, nameDraft.trim());
      await onRenamed();
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi đổi tên.");
    } finally {
      setRenaming(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: 6, padding: 8 }}>
      <AssetPreview kind={kind} asset={asset} />
      {editing ? (
        <div style={{ display: "flex", gap: 4 }}>
          <input
            className="input"
            style={{ fontSize: 12, padding: "3px 6px", flex: 1, minWidth: 0 }}
            value={nameDraft}
            autoFocus
            onChange={(e) => setNameDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") {
                setNameDraft(asset.name);
                setEditing(false);
              }
            }}
          />
        </div>
      ) : (
        <div style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={asset.name}>
          {asset.name}
        </div>
      )}
      {error && <div style={{ fontSize: 11, color: "var(--color-danger)" }}>{error}</div>}
      <div style={{ display: "flex", gap: 6 }}>
        {editing ? (
          <>
            <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={save} disabled={renaming || !nameDraft.trim()}>
              {renaming ? "Đang lưu..." : "Lưu"}
            </button>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 11, padding: "3px 8px" }}
              onClick={() => {
                setNameDraft(asset.name);
                setEditing(false);
              }}
              disabled={renaming}
            >
              Huỷ
            </button>
          </>
        ) : (
          <>
            <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => setEditing(true)}>
              Sửa tên
            </button>
            <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px", color: "var(--color-danger)" }} onClick={onDelete} disabled={busy}>
              {busy ? "Đang xoá..." : "Xoá"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function AssetPreview({ kind, asset }: { kind: CreativeAssetKind; asset: CreativeAsset }) {
  const url = api.libraryAssetUrl(asset.id);
  if (kind === "image") {
    return <img alt={asset.name} src={url} style={{ width: "100%", height: 100, objectFit: "cover", borderRadius: "var(--radius-sm)", background: "var(--color-bg)" }} />;
  }
  if (kind === "video") {
    // eslint-disable-next-line jsx-a11y/media-has-caption
    return <video controls style={{ width: "100%", height: 100, borderRadius: "var(--radius-sm)", background: "var(--color-bg)" }} src={url} />;
  }
  // eslint-disable-next-line jsx-a11y/media-has-caption
  return <audio controls style={{ width: "100%" }} src={url} />;
}
