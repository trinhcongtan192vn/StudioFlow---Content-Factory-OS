// Electron main process (§01 mục 1/7).
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import * as path from "path";
import { ChildProcessWithoutNullStreams } from "child_process";
import { findFreePort, startBackend, waitForHealth } from "./backend-launcher";

let backendProcess: ChildProcessWithoutNullStreams | null = null;
let mainWindow: BrowserWindow | null = null;

const isDev = !app.isPackaged;

async function createWindow() {
  const port = await findFreePort();
  const workspaceDir = isDev
    ? path.join(__dirname, "..", "..", "workspace")
    : path.join(app.getPath("userData"), "workspace");

  backendProcess = startBackend(port, workspaceDir, path.join(__dirname, ".."));
  await waitForHealth(port);

  process.env.STUDIOFLOW_API_PORT = String(port);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: "#161826",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    await mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    await mainWindow.loadFile(path.join(__dirname, "..", "..", "frontend", "dist", "index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// "Xuất Pack" (2026-08-26) — nút xuất bundle video ra 1 folder trên máy local cần
// dialog chọn thư mục NATIVE (backend ghi thẳng ra filesystem bằng đường dẫn tuyệt đối,
// không có File System Access API kiểu browser để làm việc này trong renderer). Trả về
// `null` khi người dùng bấm Huỷ — renderer tự xử lý, không coi là lỗi.
ipcMain.handle("choose-folder", async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory", "createDirectory"] });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

// "Mở thư mục lưu trữ" (Kho Tài Nguyên, 2026-08-27) — mở thư mục THẬT trên máy (Explorer/
// Finder) chứa video gốc/clip đã cắt, đường dẫn lấy từ backend (`GET /asset-vault/folders`)
// vì renderer không tự biết đường dẫn tuyệt đối filesystem. `shell.openPath` trả về chuỗi
// lỗi (rỗng nếu thành công) — KHÔNG throw, nên convert thành reject để renderer bắt được
// bằng try/catch như mọi lời gọi API khác.
ipcMain.handle("open-folder", async (_event, folderPath: string) => {
  const errorMessage = await shell.openPath(folderPath);
  if (errorMessage) throw new Error(errorMessage);
});

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
