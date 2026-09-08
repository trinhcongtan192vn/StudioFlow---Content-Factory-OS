/** Thanh tiến trình dùng chung — ban đầu chỉ có ở Kho Tài Nguyên (cắt cảnh/xoá watermark
 * video gốc), tách ra thành component riêng (2026-09-02) để Visual Studio dùng lại nguyên
 * cho tiến trình xoá watermark từng shot, theo yêu cầu người dùng ("tương tự thanh tiến
 * trình ở phần Kho tài nguyên") thay vì tự vẽ 1 kiểu khác. */
export default function ProgressBar({ current, total, label }: { current: number; total: number; label: string | null }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 140, flex: "none" }}>
      <progress value={current} max={total} style={{ width: "100%", height: 6 }} />
      <span style={{ fontSize: 10.5, opacity: 0.65 }}>{label || `${current}/${total}`}</span>
    </div>
  );
}
