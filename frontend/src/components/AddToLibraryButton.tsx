import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { CreativeAsset, CreativeAssetKind } from "../api/types";

/** Nút "Thêm vào thư viện" — hiện SAU khi user đã upload thành công 1 asset ở đâu đó
 * trong app (voice sample, intro, shot visual, bg music...): `fetch()` blob từ CHÍNH
 * URL đang hiển thị asset đó, POST thẳng sang `/library/assets/upload` — lưu lại để
 * dùng nhanh ở nơi khác sau này, không cần chọn lại file từ máy. Tên gợi ý ban đầu
 * (`name`) chỉ mang tính đặt tạm theo ngữ cảnh (VD "shot-mo-dau") — **mới (2026-08-21)**,
 * theo yêu cầu người dùng: cho sửa lại NGAY sau khi thêm thành công (không cần vòng qua
 * màn Thư viện mới đổi được tên). */
export default function AddToLibraryButton({ kind, sourceUrl, name }: { kind: CreativeAssetKind; sourceUrl: string; name: string }) {
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [asset, setAsset] = useState<CreativeAsset | null>(null);
  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [renaming, setRenaming] = useState(false);

  async function add() {
    setState("saving");
    setError(null);
    try {
      const res = await fetch(sourceUrl);
      if (!res.ok) throw new Error("Không đọc được file để thêm vào thư viện.");
      const blob = await res.blob();
      const file = new File([blob], name, { type: blob.type });
      const created = await api.uploadLibraryAsset(kind, file);
      setAsset(created);
      setState("done");
    } catch (e) {
      setState("error");
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Có lỗi khi thêm vào thư viện.");
    }
  }

  async function saveRename() {
    if (!asset || !nameDraft.trim()) return;
    setRenaming(true);
    setError(null);
    try {
      const updated = await api.renameLibraryAsset(asset.id, nameDraft.trim());
      setAsset(updated);
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi đổi tên.");
    } finally {
      setRenaming(false);
    }
  }

  if (state === "done" && asset) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {editing ? (
          <>
            <input
              className="input"
              style={{ fontSize: 12, padding: "3px 6px", width: 150 }}
              value={nameDraft}
              autoFocus
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveRename();
                if (e.key === "Escape") setEditing(false);
              }}
            />
            <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={saveRename} disabled={renaming || !nameDraft.trim()}>
              {renaming ? "Đang lưu..." : "Lưu"}
            </button>
            <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => setEditing(false)} disabled={renaming}>
              Huỷ
            </button>
          </>
        ) : (
          <span style={{ fontSize: 12 }}>
            Đã thêm vào thư viện: <strong>{asset.name}</strong>{" "}
            <button
              className="btn btn-secondary"
              style={{ fontSize: 11, padding: "2px 6px" }}
              onClick={() => {
                setNameDraft(asset.name);
                setEditing(true);
              }}
            >
              Sửa tên
            </button>
          </span>
        )}
        {error && <span style={{ fontSize: 11, color: "var(--color-danger)" }}>{error}</span>}
      </span>
    );
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={add} disabled={state === "saving"}>
        {state === "saving" ? "Đang thêm..." : "Thêm vào thư viện"}
      </button>
      {error && <span style={{ fontSize: 11, color: "var(--color-danger)" }}>{error}</span>}
    </span>
  );
}
