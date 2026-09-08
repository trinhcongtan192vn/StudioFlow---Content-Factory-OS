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
    // `PYTHONIOENCODING`/`PYTHONUTF8` — mới (2026-09-02, mục 111): toàn bộ app dùng
    // tiếng Việt (thông điệp lỗi, log...) — không set 2 biến này, `sys.stdout`/`stderr`
    // của Python thừa hưởng codepage console mặc định của máy Windows (thường cp1252,
    // KHÔNG mã hoá được ký tự có dấu tiếng Việt). Nghi ngờ đây là nguyên nhân 1 bug thật
    // đã gặp: 1 luồng nền (`assemble_video`) "chết lặng" giữa chừng không rõ lý do trên
    // máy người dùng — nếu bất kỳ đâu trong quá trình xử lý có in/log ra console 1 chuỗi
    // tiếng Việt (VD nội dung lỗi ffmpeg, tiêu đề project...), `UnicodeEncodeError` có
    // thể xảy ra NGOÀI try/except Python bình thường đang bọc (VD trong chính cơ chế in
    // traceback của interpreter) và làm chết hẳn thread đó. Ép UTF-8 loại bỏ hẳn khả
    // năng này — an toàn tuyệt đối kể cả nếu đây KHÔNG phải nguyên nhân thật (không đổi
    // hành vi gì khác của app).
    env: { ...process.env, STUDIOFLOW_WORKSPACE: workspaceDir, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
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
