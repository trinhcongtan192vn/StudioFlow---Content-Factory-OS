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
});
