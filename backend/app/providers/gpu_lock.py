"""Khoá dùng chung cho mọi tác vụ AI chạy trên GPU local trong tiến trình backend —
Ollama (LLM), ComfyUI (Image/Video). Máy 1 GPU (VD RTX 5060 Ti 16GB) không đủ VRAM để
chạy đồng thời nhiều model nặng (đo thật: qwen3:14b ~9.6GB + Wan2.2 TI2V-5B ~9.5GB vượt
16GB) — tranh chấp VRAM gây thrashing, có lần làm tốc độ sinh video chậm gấp ~2.4 lần
(21s/bước → 50s/bước), xem IMPLEMENTATION_REPORT.md mục 16.6b. Backend này chạy sync
(FastAPI route sync `def` + `BackgroundTasks` đều thực thi trong threadpool, không phải
async-native) nên dùng `threading.Lock`, không phải `asyncio.Lock`.

**Phạm vi khoá**: trong-tiến-trình backend, không phải khoá cấp hệ điều hành/driver GPU.
App 1 người dùng, backend là nơi duy nhất gọi cả Ollama lẫn ComfyUI nên giả định này đủ
dùng — nếu người dùng tự mở thêm ComfyUI UI/Ollama CLI riêng và chạy song song ngoài
app, khoá này không biết tới việc đó (giống ai-content-studio's `gpu_pool.py`, tham khảo
cách tiếp cận nhưng viết lại cho backend sync của repo này).

Không khoá TTS (Piper) — chạy CPU, không tranh VRAM với LLM/Image/Video.
"""
import threading

gpu_lock = threading.Lock()
