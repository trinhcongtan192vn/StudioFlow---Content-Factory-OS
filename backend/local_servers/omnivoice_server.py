"""Wrapper HTTP cho OmniVoice (k2-fsa/OmniVoice — TTS zero-shot voice cloning, GPU) —
xem IMPLEMENTATION_REPORT.md mục OmniVoice để biết cách cài đặt + lý do kiến trúc.

**Vì sao có wrapper riêng thay vì gọi thẳng trong tiến trình backend chính**: OmniVoice
không có HTTP server sẵn (chỉ Python API + Gradio demo), nhưng dùng `torch`+CUDA — đưa
thẳng vào venv backend (hiện chỉ có `onnxruntime` CPU cho Piper) sẽ làm phình + dễ xung
đột version, và biến API server (luôn phải phản hồi nhanh) thành nơi giữ model nặng
thường trực. Chạy như 1 service HTTP riêng (giống Ollama/ComfyUI) — venv RIÊNG, tách
biệt hoàn toàn khỏi `backend/.venv` — cho phép `app/providers/tts_omnivoice.py` (backend
chính) gọi qua `httpx` + `gpu_lock`, đúng pattern đã dùng cho ComfyUI (image/video local).

**Cài đặt** (venv riêng, KHÔNG dùng chung `backend/.venv`):
    python -m venv .venv
    .venv\\Scripts\\pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu129
    .venv\\Scripts\\pip install omnivoice fastapi uvicorn python-multipart

    Dùng cu129 (KHÔNG theo gợi ý cu128 của README OmniVoice) — máy RTX 5060 Ti
    (Blackwell/sm_120) đã xác nhận cu126 thiếu kernel cho sm_120, cu130 crash với driver
    hiện tại, chỉ cu129 chạy đúng (xem IMPLEMENTATION_REPORT.md mục 16.2) — cu128 CHƯA
    được OmniVoice test trên Blackwell, rủi ro lặp lại lỗi cu126.

**Chạy**: .venv\\Scripts\\python backend/local_servers/omnivoice_server.py --port 8199
"""
from __future__ import annotations

import argparse
import io
import tempfile
from pathlib import Path

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import Response

app = FastAPI(title="OmniVoice local TTS server")

_model = None  # load lười ở startup event, không phải import-time — giữ file import nhanh cho các script test khác nếu cần


@app.on_event("startup")
def _load_model() -> None:
    global _model
    from omnivoice import OmniVoice  # import trễ — model + deps nặng, chỉ cần khi thật sự chạy server

    _model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda:0", dtype=torch.float16)


@app.get("/health")
def health() -> dict:
    # `ok` = server process sống (đủ để dùng — `/synthesize` tự nạp lại model nếu cần,
    # xem `/unload`). Model KHÔNG nạp sẵn không phải lỗi — đây là trạng thái bình thường
    # sau khi `_free_local_tts_vram` (factory.py) gọi `/unload` để nhường VRAM cho LLM
    # local, xem IMPLEMENTATION_REPORT.md mục 22. `model_loaded` chỉ mang tính thông tin.
    return {"ok": True, "model_loaded": _model is not None}


@app.post("/unload")
def unload() -> dict:
    """Giải phóng model khỏi VRAM — dùng khi backend chính cần dồn VRAM cho LLM/Image/
    Video local khác (VD Ollama nạp qwen3:14b cho lúc chạy Research/Script — đo thật lúc
    verify: ComfyUI SDXL + OmniVoice cùng thường trú chiếm ~12.1GB/16GB, cộng thêm
    qwen3:14b (~9.6GB) làm tràn VRAM, Research THẤT BẠI hẳn chứ không chỉ chậm — xem
    IMPLEMENTATION_REPORT.md mục 22). `/synthesize` sau đó TỰ NẠP LẠI khi có request mới
    (model đã cache sẵn trên đĩa, nạp lại nhanh — không cần giữ server sống riêng biệt
    theo trạng thái loaded/unloaded phức tạp)."""
    global _model
    if _model is not None:
        del _model
        _model = None
        torch.cuda.empty_cache()
    return {"ok": True}


@app.post("/synthesize")
async def synthesize(
    text: str = Form(...),
    ref_audio: UploadFile | None = File(None),
    ref_text: str | None = Form(None),
    instruct: str | None = Form(None),
) -> Response:
    """Sinh giọng đọc — 3 chế độ của OmniVoice tuỳ tham số truyền vào (đúng thiết kế gốc
    của model, xem README OmniVoice mục Python API):
    - CÓ `ref_audio` → Voice Cloning (nhân bản giọng mẫu). Không kèm `ref_text` → model
      tự dùng Whisper ASR phiên âm mẫu (không cần người dùng gõ tay).
    - CÓ `instruct`, KHÔNG `ref_audio` → Voice Design (mô tả giọng bằng chữ).
    - Không có gì cả → Auto Voice (model tự chọn giọng)."""
    if _model is None:  # bị /unload giải phóng — nạp lại (nhanh, model đã cache sẵn)
        _load_model()
    kwargs: dict = {}
    tmp_path: Path | None = None
    if ref_audio is not None:
        suffix = Path(ref_audio.filename or "ref.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await ref_audio.read())
            tmp_path = Path(tmp.name)
        kwargs["ref_audio"] = str(tmp_path)
        if ref_text:
            kwargs["ref_text"] = ref_text
    elif instruct:
        kwargs["instruct"] = instruct

    try:
        audios = _model.generate(text=text, **kwargs)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    # `generate()` trả về LIST 1 phần tử (numpy array) — không phải array trực tiếp,
    # sample rate đọc từ `model.sampling_rate` (không phải `sample_rate` — phát hiện
    # thật lúc test, xem docstring `omnivoice/models/omnivoice.py::generate`:
    # `soundfile.write("out.wav", audios[0], model.sampling_rate)`).
    buf = io.BytesIO()
    sf.write(buf, audios[0], samplerate=_model.sampling_rate, format="WAV")
    return Response(content=buf.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8199)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
