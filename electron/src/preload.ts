// Preload — truyền cổng backend cho renderer qua window.STUDIOFLOW_API_BASE (§01).
import { contextBridge, ipcRenderer } from "electron";

const port = process.env.STUDIOFLOW_API_PORT || "8756";

contextBridge.exposeInMainWorld("STUDIOFLOW_API_BASE", `http://127.0.0.1:${port}`);

// "Xuất Pack" (2026-08-26) — cầu nối dialog chọn thư mục native cho renderer (khớp
// pattern optional `window.STUDIOFLOW_API_BASE` — chỉ tồn tại khi chạy trong Electron,
// frontend tự fallback về ô nhập đường dẫn tay khi chạy dev server thuần trình duyệt).
contextBridge.exposeInMainWorld("studioflowNative", {
  chooseFolder: (): Promise<string | null> => ipcRenderer.invoke("choose-folder"),
  openFolder: (folderPath: string): Promise<void> => ipcRenderer.invoke("open-folder", folderPath),
  // Kết nối tài khoản Google (chỉ số YouTube, 2026-09-12) — mở URL đồng ý OAuth trong
  // trình duyệt hệ thống, cùng pattern optional `window.studioflowNative` (chỉ tồn tại
  // trong Electron — frontend tự fallback báo "chỉ dùng được trong app desktop" khi
  // chạy dev server thuần trình duyệt, vì URL localhost callback không hoạt động đúng
  // ngoài ngữ cảnh Electron).
  openExternal: (url: string): Promise<void> => ipcRenderer.invoke("open-external", url),
});
