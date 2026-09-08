from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import local_services
from app.db import get_db
from app.models import Channel, ProviderConfig

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/system/local-services")
def get_local_services():
    """Khu vực "Local Services & GPU Monitor" ở cuối trang Dashboard (2026-08-27, theo
    yêu cầu người dùng) — trạng thái bật/tắt Ollama/OmniVoice/ComfyUI + tổng quan GPU.
    Xem `app/local_services.py` cho chi tiết + giới hạn thật đã verify (Windows WDDM
    không báo VRAM per-process)."""
    return {"services": local_services.get_all_statuses(), "gpu": local_services.get_gpu_stats()}


@router.post("/system/local-services/{name}/start")
def start_local_service(name: str):
    if name not in local_services.SERVICES:
        raise HTTPException(404, f"Không rõ service '{name}'")
    return local_services.start_service(name)


@router.post("/system/local-services/{name}/stop")
def stop_local_service(name: str):
    if name not in local_services.SERVICES:
        raise HTTPException(404, f"Không rõ service '{name}'")
    return local_services.stop_service(name)


@router.get("/bootstrap")
def bootstrap(db: Session = Depends(get_db)):
    has_llm_provider = (
        db.query(ProviderConfig).filter(ProviderConfig.task == "llm", ProviderConfig.enabled == True).count() > 0  # noqa: E712
    )
    channels = db.query(Channel).filter(Channel.archived == False).count()  # noqa: E712
    return {
        "has_llm_provider": has_llm_provider,
        "channel_count": channels,
        "app_name": "StudioFlow",
    }
