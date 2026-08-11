// Electron main process (§01 mục 1/7).
import { app, BrowserWindow } from "electron";
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
