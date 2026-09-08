"""Test "Local Services & GPU Monitor" (Dashboard, 2026-08-27). `app/local_services.py`
đã được VERIFY THẬT tay-1-lần với Ollama/OmniVoice/ComfyUI thật đang chạy trên máy dev
trước khi viết test này (xem IMPLEMENTATION_REPORT.md mục 89 — bắt được 2 bug thật lúc
verify: thiếu `OLLAMA_MODELS` env cho bản Ollama portable, và đường dẫn thực thi tương
đối không được `subprocess.Popen` tự resolve theo `cwd` trên Windows). Test tự động ở
đây MOCK `httpx`/`subprocess`/`psutil` (không tốn thời gian khởi động GPU service thật
mỗi lần chạy `pytest`) — đúng lý do plan đã nêu, không thay thế cho lượt verify tay đã
làm."""
from unittest.mock import MagicMock, patch

from app import local_services as ls


def test_check_status_true_when_health_responds(monkeypatch):
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return MagicMock()

    with patch("httpx.Client", return_value=FakeClient()):
        assert ls.check_status("ollama") is True


def test_check_status_false_when_connection_fails():
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            raise ConnectionError("refused")

    with patch("httpx.Client", return_value=FakeClient()):
        assert ls.check_status("ollama") is False


def test_get_all_statuses_returns_all_registered_services():
    with patch.object(ls, "check_status", return_value=True):
        statuses = ls.get_all_statuses()
    assert {s["name"] for s in statuses} == set(ls.SERVICES.keys())
    assert all(s["running"] for s in statuses)


def test_start_service_rejects_unknown_name():
    result = ls.start_service("khong-ton-tai")
    assert result["ok"] is False


def test_start_service_no_op_when_already_running():
    with patch.object(ls, "check_status", return_value=True):
        result = ls.start_service("ollama")
    assert result["ok"] is True
    assert "đã đang chạy" in result["message"]


def test_start_service_fails_gracefully_when_exe_missing(tmp_path):
    fake_svc = ls.ServiceDef(display_name="Fake", health_url="http://127.0.0.1:1/health", port=1, start_cmd=[str(tmp_path / "khong-ton-tai.exe")], cwd=None)
    with patch.object(ls, "check_status", return_value=False), patch.dict(ls.SERVICES, {"fake": fake_svc}):
        result = ls.start_service("fake")
    assert result["ok"] is False
    assert "Không tìm thấy" in result["message"]


def test_start_service_resolves_relative_exe_against_cwd(tmp_path):
    """Regression test cho bug thật đã bắt được lúc verify tay: đường dẫn thực thi
    TƯƠNG ĐỐI (như ComfyUI dùng) phải được resolve thành TUYỆT ĐỐI trước khi đưa vào
    `subprocess.Popen` — Windows KHÔNG tự làm việc này theo `cwd=`."""
    exe_dir = tmp_path / "sub"
    exe_dir.mkdir()
    fake_exe = exe_dir / "python.exe"
    fake_exe.write_text("fake")
    fake_svc = ls.ServiceDef(display_name="Fake", health_url="http://127.0.0.1:1/health", port=1, start_cmd=["sub\\python.exe", "-s", "main.py"], cwd=str(tmp_path))

    with patch.object(ls, "check_status", return_value=False), patch.dict(ls.SERVICES, {"fake": fake_svc}), patch("subprocess.Popen") as mock_popen:
        result = ls.start_service("fake")

    assert result["ok"] is True
    called_cmd = mock_popen.call_args.args[0]
    assert called_cmd[0] == str(fake_exe)  # phải là đường dẫn TUYỆT ĐỐI đã resolve, không phải "sub\\python.exe"


def test_start_service_passes_extra_env(tmp_path):
    """Regression test cho bug thật thứ 2 đã bắt được: Ollama portable cần
    `OLLAMA_MODELS` trỏ đúng thư mục — thiếu biến này server vẫn chạy nhưng báo 0 model."""
    fake_exe = tmp_path / "ollama.exe"
    fake_exe.write_text("fake")
    fake_svc = ls.ServiceDef(
        display_name="Fake", health_url="http://127.0.0.1:1/health", port=1,
        start_cmd=[str(fake_exe), "serve"], cwd=None, extra_env={"OLLAMA_MODELS": "C:\\custom"},
    )
    with patch.object(ls, "check_status", return_value=False), patch.dict(ls.SERVICES, {"fake": fake_svc}), patch("subprocess.Popen") as mock_popen:
        ls.start_service("fake")

    called_env = mock_popen.call_args.kwargs["env"]
    assert called_env["OLLAMA_MODELS"] == "C:\\custom"


def test_stop_service_no_op_when_not_running():
    with patch.object(ls, "_find_pid_on_port", return_value=None):
        result = ls.stop_service("ollama")
    assert result["ok"] is True
    assert "không thấy đang chạy" in result["message"]


def test_stop_service_terminates_process_and_children():
    mock_proc = MagicMock()
    mock_proc.children.return_value = []
    with patch.object(ls, "_find_pid_on_port", return_value=12345), patch("psutil.Process", return_value=mock_proc), patch("psutil.wait_procs", return_value=([mock_proc], [])):
        result = ls.stop_service("ollama")
    assert result["ok"] is True
    mock_proc.terminate.assert_called_once()


def test_get_gpu_stats_unavailable_when_nvidia_smi_missing():
    with patch("shutil.which", return_value=None):
        result = ls.get_gpu_stats()
    assert result == {"available": False}


def test_get_gpu_stats_parses_real_csv_format():
    """Đúng format thật đã verify tay qua `nvidia-smi` thật:
    `NVIDIA GeForce RTX 5060 Ti, 5741, 16311, 5, 36`."""
    overview = MagicMock(stdout="NVIDIA GeForce RTX 5060 Ti, 5741, 16311, 5, 36\n")
    apps = MagicMock(stdout="")
    with patch("shutil.which", return_value="nvidia-smi"), patch("subprocess.run", side_effect=[overview, apps]), patch.object(ls, "_find_pid_on_port", return_value=None):
        result = ls.get_gpu_stats()
    assert result["available"] is True
    assert result["name"] == "NVIDIA GeForce RTX 5060 Ti"
    assert result["memory_used_mb"] == 5741
    assert result["memory_total_mb"] == 16311
    assert result["utilization_pct"] == 5
    assert result["temperature_c"] == 36
    assert result["services_using_gpu"] == []


# --- HTTP endpoint tests (routers/system.py) ---


def test_get_local_services_endpoint(client):
    with patch.object(ls, "get_all_statuses", return_value=[{"name": "ollama", "display_name": "Ollama", "running": True}]), patch.object(ls, "get_gpu_stats", return_value={"available": False}):
        resp = client.get("/system/local-services")
    assert resp.status_code == 200
    body = resp.json()
    assert body["services"][0]["name"] == "ollama"
    assert body["gpu"]["available"] is False


def test_start_local_service_endpoint_404_for_unknown_name(client):
    resp = client.post("/system/local-services/khong-ton-tai/start")
    assert resp.status_code == 404


def test_stop_local_service_endpoint_calls_stop_service(client):
    with patch.object(ls, "stop_service", return_value={"ok": True, "message": "Đã tắt."}) as mock_stop:
        resp = client.post("/system/local-services/ollama/stop")
    assert resp.status_code == 200
    mock_stop.assert_called_once_with("ollama")
