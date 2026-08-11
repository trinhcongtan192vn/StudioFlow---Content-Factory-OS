from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Channel, ProviderConfig

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


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
