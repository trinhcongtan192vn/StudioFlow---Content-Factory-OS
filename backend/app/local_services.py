"""Bật/tắt + theo dõi trạng thái các local model/server (Ollama/OmniVoice/ComfyUI) +
tổng quan GPU — cho khu vực "Local Services & GPU Monitor" ở cuối trang Dashboard
(2026-08-27, theo yêu cầu người dùng).

**Đã verify thật trên máy dev** (không suy đoán đường dẫn/lệnh — xem IMPLEMENTATION_REPORT.md
mục 89):
- `C:\\Tools\\Ollama\\ollama.exe serve` (cổng 11434), `C:\\Tools\\OmniVoice\\.venv\\
  Scripts\\python.exe backend/local_servers/omnivoice_server.py --port 8199` (cổng 8199),
  `C:\\Tools\\ComfyUI_extract\\ComfyUI_windows_portable\\python_embeded\\python.exe -s
  ComfyUI\\main.py --windows-standalone-build` (cổng 8188, đọc trực tiếp từ
  `run_nvidia_gpu.bat` có sẵn trong bản cài).
- `nvidia-smi --query-compute-apps=pid,used_memory` trả `[N/A]` cho MỌI PID trên máy này
  (Windows WDDM không báo VRAM per-process tin cậy được, khác Linux/TCC) — module này CHỈ
  báo tổng VRAM dùng/tổng + PID nào đang giữ GPU compute context, KHÔNG hứa hẹn breakdown
  MB/từng service.

**Đường dẫn HARDCODE theo đúng cách cài trên máy dev này** (khớp cách toàn bộ app đã giả
định 1 máy cụ thể — base_url mặc định `127.0.0.1:PORT` ở mọi provider local cũng vậy,
xem `image_comfy_sdxl.py`/`tts_omnivoice.py`/`local_openai_compat.py`) — đổi máy cần sửa
`SERVICES` bên dưới.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
import psutil

from app.config import REPO_ROOT, WORKSPACE_DIR

SERVICE_LOGS_DIR = WORKSPACE_DIR / "service_logs"


@dataclass(frozen=True)
class ServiceDef:
    display_name: str
    health_url: str
    port: int
    start_cmd: list[str]
    cwd: str | None
    extra_env: dict[str, str] | None = None


SERVICES: dict[str, ServiceDef] = {
    "ollama": ServiceDef(
        display_name="Ollama (LLM / Vision / Embedding)",
        health_url="http://127.0.0.1:11434/api/tags",
        port=11434,
        start_cmd=["C:\\Tools\\Ollama\\ollama.exe", "serve"],
        cwd=None,
        # **Bug thật phát hiện lúc verify (2026-08-27)**: bản Ollama cài trên máy này là
        # bản "portable", KHÔNG dùng thư mục model mặc định (`~/.ollama/models`) — dữ
        # liệu model thật nằm ở `C:\Tools\Ollama\data` (xác nhận có `manifests/` chứa cả
        # 3 model đã pull: moondream/nomic-embed-text/qwen3). Tiến trình `ollama.exe
        # serve` ĐANG chạy trước đó hẳn được khởi động với biến môi trường
        # `OLLAMA_MODELS` trỏ đúng thư mục này (qua wrapper/profile nào đó của người
        # dùng, không nằm trong control của app) — `subprocess.Popen` KHÔNG tự kế thừa
        # biến này (chỉ kế thừa env của tiến trình backend Python, vốn không có biến
        # đó), verify THẬT: sau khi `start_service` mà thiếu dòng này, `curl .../api/tags`
        # trả `{"models":[]}` dù blob model vẫn còn nguyên trên đĩa — chỉ set lại đúng
        # `OLLAMA_MODELS` mới thấy lại đủ 3 model.
        extra_env={"OLLAMA_MODELS": "C:\\Tools\\Ollama\\data"},
    ),
    "omnivoice": ServiceDef(
        display_name="OmniVoice (TTS local GPU)",
        health_url="http://127.0.0.1:8199/health",
        port=8199,
        start_cmd=[
            "C:\\Tools\\OmniVoice\\.venv\\Scripts\\python.exe",
            str(REPO_ROOT / "backend" / "local_servers" / "omnivoice_server.py"),
            "--port",
            "8199",
        ],
        cwd=str(REPO_ROOT),
    ),
    "comfyui": ServiceDef(
        display_name="ComfyUI (Image / Video local GPU)",
        health_url="http://127.0.0.1:8188/system_stats",
        port=8188,
        start_cmd=["python_embeded\\python.exe", "-s", "ComfyUI\\main.py", "--windows-standalone-build"],
        cwd="C:\\Tools\\ComfyUI_extract\\ComfyUI_windows_portable",
    ),
}


def check_status(name: str) -> bool:
    """`True` nếu health endpoint trả response KHÔNG lỗi kết nối — không parse body (mỗi
    service trả 1 format khác hẳn nhau: Ollama JSON model list, OmniVoice
    `{ok,model_loaded}`, ComfyUI `system_stats` — chỉ cần "có trả lời" là đủ biết server
    đang sống, không cần hiểu nội dung)."""
    svc = SERVICES[name]
    try:
        with httpx.Client(timeout=2.5) as client:
            client.get(svc.health_url)
        return True
    except Exception:  # noqa: BLE001
        return False


def get_all_statuses() -> list[dict]:
    return [{"name": name, "display_name": svc.display_name, "running": check_status(name)} for name, svc in SERVICES.items()]


def _find_pid_on_port(port: int) -> int | None:
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
            return conn.pid
    return None


def start_service(name: str) -> dict:
    if name not in SERVICES:
        return {"ok": False, "message": f"Không rõ service '{name}'."}
    svc = SERVICES[name]
    if check_status(name):
        return {"ok": True, "message": f"{svc.display_name} đã đang chạy."}
    exe = Path(svc.start_cmd[0])
    # Đường dẫn tương đối (VD "python_embeded\\python.exe" của ComfyUI) chỉ tồn tại XÉT
    # TRONG `cwd` — resolve đúng ngữ cảnh trước khi kiểm tra file có thật không.
    # **Bug thật phát hiện lúc verify (2026-08-27)**: `subprocess.Popen` trên Windows
    # KHÔNG tự resolve đường dẫn thực thi tương đối theo `cwd=` — nó tra theo cwd của
    # TIẾN TRÌNH CHA (backend) rồi mới tới PATH, không phải cwd CON sắp chạy — dùng
    # nguyên `svc.start_cmd` (còn tương đối) trực tiếp gây lỗi thật `[WinError 2] The
    # system cannot find the file specified` dù file tồn tại (kiểm tra `exe_path.exists()`
    # ở trên vẫn qua vì hàm đó TỰ resolve đúng, chỉ là kết quả không được dùng lại cho
    # Popen). Fix: dùng ĐÚNG `exe_path` đã resolve (tuyệt đối) làm phần tử đầu của lệnh.
    exe_path = exe if exe.is_absolute() else Path(svc.cwd or ".") / exe
    if not exe_path.exists():
        return {"ok": False, "message": f"Không tìm thấy {exe_path} — kiểm tra lại đường dẫn cài đặt {svc.display_name}."}
    resolved_cmd = [str(exe_path), *svc.start_cmd[1:]]

    SERVICE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SERVICE_LOGS_DIR / f"{name}.log"
    log_file = open(log_path, "a", encoding="utf-8")
    env = {**os.environ, **svc.extra_env} if svc.extra_env else None
    try:
        subprocess.Popen(
            resolved_cmd,
            cwd=svc.cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Không khởi động được {svc.display_name}: {e}"}
    return {"ok": True, "message": f"Đang khởi động {svc.display_name} — có thể mất vài giây tới vài chục giây (nạp model) trước khi sẵn sàng."}


def stop_service(name: str) -> dict:
    if name not in SERVICES:
        return {"ok": False, "message": f"Không rõ service '{name}'."}
    svc = SERVICES[name]
    pid = _find_pid_on_port(svc.port)
    if pid is None:
        return {"ok": True, "message": f"{svc.display_name} không thấy đang chạy (đã tắt sẵn)."}
    try:
        proc = psutil.Process(pid)
        procs = proc.children(recursive=True) + [proc]  # Ollama có thể có tiến trình runner con
        for p in procs:
            try:
                p.terminate()
            except psutil.NoSuchProcess:
                pass
        _gone, alive = psutil.wait_procs(procs, timeout=5)
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Có lỗi khi tắt {svc.display_name}: {e}"}
    return {"ok": True, "message": f"Đã tắt {svc.display_name}."}


def get_gpu_stats() -> dict:
    """Best-effort — `available: False` nếu không có `nvidia-smi` trên PATH (VD máy
    không có GPU NVIDIA). Xem giới hạn per-process VRAM ở docstring đầu file."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"available": False}
    try:
        overview = subprocess.run(
            [exe, "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        line = overview.stdout.strip().splitlines()[0]
        name, mem_used, mem_total, util, temp = [p.strip() for p in line.split(",")]

        apps = subprocess.run(
            [exe, "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        active_pids = {int(p.strip()) for p in apps.stdout.strip().splitlines() if p.strip().isdigit()}
        active_services = []
        for svc_name, svc in SERVICES.items():
            pid = _find_pid_on_port(svc.port)
            if pid is not None and pid in active_pids:
                active_services.append(svc_name)

        return {
            "available": True,
            "name": name,
            "memory_used_mb": int(mem_used),
            "memory_total_mb": int(mem_total),
            "utilization_pct": int(util),
            "temperature_c": int(temp),
            "services_using_gpu": active_services,
        }
    except Exception:  # noqa: BLE001
        return {"available": False}
