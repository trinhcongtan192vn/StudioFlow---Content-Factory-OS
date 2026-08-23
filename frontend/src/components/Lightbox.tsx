import { useEffect } from "react";

/** Nút "phóng to" đặt đè góc trên-phải 1 khung preview ảnh/video — dùng riêng thay vì
 * click thẳng vào `<video controls>` vì click trên video sẽ đụng control gốc của
 * trình duyệt (play/pause/tua). Semi-transparent, chỉ hiện rõ khi hover khung cha (CSS
 * `:hover` ở nơi gọi, xem VisualStudio.tsx/PackReview.tsx). */
export function ExpandButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      className="btn btn-icon btn-secondary"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title="Xem full-size"
      style={{ position: "absolute", top: 6, right: 6, width: 24, height: 24, opacity: 0.85, zIndex: 1 }}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="15 3 21 3 21 9" />
        <polyline points="9 21 3 21 3 15" />
        <line x1="21" y1="3" x2="14" y2="10" />
        <line x1="3" y1="21" x2="10" y2="14" />
      </svg>
    </button>
  );
}

/** Xem full-size ảnh/video (shot visual, Thumbnail) — bấm mở từ preview nhỏ ở Visual
 * Studio/Pack Review, đóng bằng nút X, bấm ra ngoài, hoặc phím Esc. Dùng chung
 * `.dialog-backdrop` (nocturne.css) cho overlay, tự vẽ khung media lớn thay vì `.dialog`
 * (khung dialog cố định 440px, không phù hợp để xem ảnh/video). */
export default function Lightbox({ src, kind, onClose }: { src: string; kind: "image" | "video"; onClose: () => void }) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="dialog-backdrop" style={{ padding: "var(--space-6)" }} onClick={onClose}>
      <div style={{ position: "relative", maxWidth: "min(1100px, 100%)", maxHeight: "100%" }} onClick={(e) => e.stopPropagation()}>
        <button
          className="btn btn-icon btn-secondary"
          onClick={onClose}
          title="Đóng"
          style={{ position: "absolute", top: -14, right: -14, width: 30, height: 30, borderRadius: "50%", zIndex: 1 }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        {kind === "video" ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video controls autoPlay src={src} style={{ maxWidth: "100%", maxHeight: "85vh", borderRadius: "var(--radius-sm)", display: "block" }} />
        ) : (
          <img alt="Xem full-size" src={src} style={{ maxWidth: "100%", maxHeight: "85vh", borderRadius: "var(--radius-sm)", display: "block", objectFit: "contain" }} />
        )}
      </div>
    </div>
  );
}
