import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CreativeAsset, CreativeAssetKind } from "../api/types";

const KIND_LABEL: Record<CreativeAssetKind, string> = {
  music: "nhạc nền",
  video: "video",
  image: "ảnh",
  voice: "giọng đọc",
};

/** Nút "Chọn từ thư viện" — mở modal liệt kê asset đã lưu trong Thư viện Creative, chọn
 * 1 → tự `fetch()` bytes qua URL serve sẵn có rồi gói lại thành `File`, gọi THẲNG
 * `onPick` (dùng chung API upload đã có ở nơi gọi, giống hệt người dùng tự chọn file từ
 * máy) — KHÔNG cần endpoint "-from-library" riêng nào (xem docstring
 * `app/routers/library.py` — quyết định kiến trúc chung, 2026-08-20).
 *
 * `kinds` nhận NHIỀU loại cùng lúc (VD `["video","music"]` cho mục "Video/Audio thương
 * hiệu" — 1 slot chấp nhận CẢ 2 loại) — **đổi từ `kind` đơn sang `kinds` mảng, mới
 * (2026-08-21)**, theo yêu cầu người dùng: mỗi MỤC chỉ giữ ĐÚNG 1 nút "Chọn từ thư
 * viện", danh sách trong modal gộp asset của MỌI kind được truyền vào (kèm nhãn loại
 * để phân biệt khi có >1 kind), thay vì trước đây phải bấm 1 nút RIÊNG cho từng kind. */
export default function LibraryPicker({ kinds, onPick, disabled }: { kinds: CreativeAssetKind[]; onPick: (file: File) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [assets, setAssets] = useState<CreativeAsset[] | null>(null);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const kindsKey = kinds.join(",");

  useEffect(() => {
    if (!open) return;
    setAssets(null);
    setError(null);
    Promise.all(kinds.map((k) => api.listLibraryAssets(k)))
      .then((lists) => setAssets(lists.flat().sort((a, b) => b.created_at.localeCompare(a.created_at))))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Có lỗi khi tải thư viện."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kindsKey]);

  async function pick(asset: CreativeAsset) {
    setFetchingId(asset.id);
    setError(null);
    try {
      const res = await fetch(api.libraryAssetUrl(asset.id));
      if (!res.ok) throw new Error("Không tải được asset từ thư viện.");
      const blob = await res.blob();
      const file = new File([blob], asset.name, { type: blob.type });
      onPick(file);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Có lỗi khi lấy asset từ thư viện.");
    } finally {
      setFetchingId(null);
    }
  }

  const kindLabels = kinds.map((k) => KIND_LABEL[k]).join("/");

  return (
    <>
      <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => setOpen(true)} disabled={disabled} title={`Chọn ${kindLabels} đã có sẵn trong Thư viện`}>
        Chọn từ thư viện
      </button>
      {open && (
        <div className="dialog-backdrop" onClick={() => setOpen(false)}>
          <div className="dialog" style={{ width: "min(440px,100%)", maxHeight: "70vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
            <div className="dialog-title">Chọn {kindLabels} từ thư viện</div>
            {error && <div style={{ fontSize: 12, color: "var(--color-danger)", marginBottom: 8 }}>{error}</div>}
            {assets === null ? (
              <div style={{ opacity: 0.6, fontSize: 13 }}>Đang tải...</div>
            ) : assets.length === 0 ? (
              <div style={{ opacity: 0.6, fontSize: 13 }}>Thư viện chưa có {kindLabels} nào — upload từ máy rồi bấm "Thêm vào thư viện" để dùng lại sau.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {assets.map((a) => (
                  <div
                    key={a.id}
                    onClick={() => pick(a)}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 10px",
                      borderRadius: "var(--radius-sm)", cursor: fetchingId ? "default" : "pointer", background: "var(--color-bg)",
                      opacity: fetchingId && fetchingId !== a.id ? 0.5 : 1,
                    }}
                  >
                    <span style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                    <span style={{ display: "flex", alignItems: "center", gap: 8, flex: "none" }}>
                      {kinds.length > 1 && <span className="tag tag-outline" style={{ fontSize: 10 }}>{KIND_LABEL[a.kind]}</span>}
                      {fetchingId === a.id && <span style={{ fontSize: 11, opacity: 0.6 }}>Đang tải...</span>}
                    </span>
                  </div>
                ))}
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
