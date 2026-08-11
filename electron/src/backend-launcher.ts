// Spawn & quản lý tiến trình FastAPI backend (§01 mục 1/7).
import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import * as net from "net";
import * as path from "path";
import * as fs from "fs";

export function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const address = srv.address();
      if (address && typeof address === "object") {
        const port = address.port;
        srv.close(() => resolve(port));
      } else {
        srv.close(() => reject(new Error("Không lấy được cổng trống")));
      }
    });
    srv.on("error", reject);
  });
}

function backendDir(appRoot: string): string {
  // Dev: chạy từ repo (electron/../backend). Prod (đóng gói): backend nằm cạnh resources.
  const devPath = path.join(appRoot, "..", "backend");
  if (fs.existsSync(devPath)) return devPath;
  return path.join(appRoot, "backend");
}

function pythonExecutable(backend: string): string {
  const isWin = process.platform === "win32";
  const venvPython = path.join(backend, ".venv", isWin ? "Scripts/python.exe" : "bin/python");
  if (fs.existsSync(venvPython)) return venvPython;
  return isWin ? "python" : "python3";
}

export function startBackend(port: number, workspaceDir: string, appRoot: string): ChildProcessWithoutNullStreams {
  const backend = backendDir(appRoot);
  const python = pythonExecutable(backend);
  const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--port", String(port), "--host", "127.0.0.1"], {
    cwd: backend,
    env: { ...process.env, STUDIOFLOW_WORKSPACE: workspaceDir },
  });
  child.stdout.on("data", (d) => console.log(`[backend] ${d}`));
  child.stderr.on("data", (d) => console.error(`[backend] ${d}`));
  return child;
}

export async function waitForHealth(port: number, timeoutMs = 30000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/health`);
      if (res.ok) return;
    } catch {
      /* backend chưa sẵn sàng, thử lại */
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("Backend không phản hồi /health sau " + timeoutMs + "ms");
}
