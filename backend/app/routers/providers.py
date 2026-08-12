import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.db import get_db
from app.models import AuditLog, ProviderConfig
from app.providers.factory import _IMAGE_ADAPTERS, _TTS_ADAPTERS, _VIDEO_ADAPTERS, build_llm_provider

router = APIRouter(tags=["providers"])

# Danh sách model hiện có mỗi provider — đối chiếu lại với tài liệu chính thức từng
# hãng 2026-08-12 (docs.claude.com, developers.openai.com/api/docs, ai.google.dev/
# gemini-api/docs). Giá tương ứng xem `PRICING` trong từng adapter
# (app/providers/claude.py|openai_provider.py|gemini.py) — 2 nơi này phải khớp nhau
# khi cập nhật model mới. Khớp CLOUD_CATALOG ở
# frontend/src/screens/settings/ProviderSettings.tsx.
CLOUD_MODELS = {
    "claude": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
    "openai": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
    "gemini": ["gemini-3.6-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
    "elevenlabs": ["eleven_v3", "eleven_turbo"],
    "vbee": ["vbee-female-01", "vbee-male-01"],
    "flux": ["flux-1.1-pro", "flux-schnell"],
    "midjourney": ["v6"],
    "runway": ["gen-4", "gen-3-alpha"],
    "sora": ["sora-2", "sora-2-pro"],
}

# OpenAI/Gemini xuất hiện ở NHIỀU task khác nhau (llm ở trên + tts/image ở dưới) —
# cùng provider_name nhưng model list riêng theo task, tra theo (task, provider_name).
# Anthropic không có model TTS/Image/Video công khai nên không có mục nào ở đây.
CLOUD_MODELS_BY_TASK = {
    ("tts", "openai"): ["gpt-4o-mini-tts", "tts-1-hd", "tts-1"],
    ("tts", "gemini"): ["gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts", "gemini-2.5-flash-preview-tts"],
    ("image", "openai"): ["gpt-image-2", "gpt-image-1-mini"],
    ("image", "gemini"): ["gemini-3-pro-image", "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image"],
    ("video", "veo"): ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"],
}


def _cloud_models_for(task: str, provider_name: str) -> list[str]:
    return CLOUD_MODELS_BY_TASK.get((task, provider_name)) or CLOUD_MODELS.get(provider_name, [])


def _out(pv: ProviderConfig) -> dict:
    return {
        "id": pv.id,
        "task": pv.task,
        "provider_name": pv.provider_name,
        "display_name": pv.display_name,
        "connection_type": pv.connection_type,
        "endpoint_url": pv.endpoint_url,
        "model_name": pv.model_name,
        "available_models": json.loads(pv.available_models or "[]"),
        "is_default": pv.is_default,
        "is_fallback": pv.is_fallback,
        "enabled": pv.enabled,
        "status": pv.status,
        "key_display": mask_secret(decrypt_secret(pv.api_key_encrypted)) if pv.api_key_encrypted else "",
        "has_key": bool(pv.api_key_encrypted),
    }


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    return [_out(p) for p in db.query(ProviderConfig).all()]


class ProviderCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task: str  # llm | tts | image | video
    provider_name: str
    display_name: str
    connection_type: str  # cloud_api | local_endpoint
    api_key: str | None = None
    endpoint_url: str | None = None
    model_name: str | None = None


@router.post("/providers")
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)):
    if body.connection_type not in ("cloud_api", "local_endpoint"):
        raise HTTPException(400, "connection_type phải là cloud_api hoặc local_endpoint")
    if body.connection_type == "local_endpoint" and body.task != "llm":
        raise HTTPException(400, "Local Endpoint hiện chỉ áp dụng cho LLM (§05 mục 9 / §10.2b PRD)")
    models = _cloud_models_for(body.task, body.provider_name)
    pv = ProviderConfig(
        task=body.task,
        provider_name=body.provider_name,
        display_name=body.display_name,
        connection_type=body.connection_type,
        api_key_encrypted=encrypt_secret(body.api_key) if body.api_key else None,
        endpoint_url=body.endpoint_url,
        model_name=body.model_name or (models[0] if models else ""),
        available_models=json.dumps(models, ensure_ascii=False),
        status="untested",
    )
    db.add(pv)
    db.flush()
    db.add(AuditLog(action="Thêm provider", detail=f"{body.display_name} ({body.connection_type})"))
    db.commit()
    return _out(pv)


class ProviderPatch(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    display_name: str | None = None
    model_name: str | None = None
    endpoint_url: str | None = None
    api_key: str | None = None
    is_default: bool | None = None
    is_fallback: bool | None = None
    enabled: bool | None = None


@router.patch("/providers/{provider_id}")
def patch_provider(provider_id: int, body: ProviderPatch, db: Session = Depends(get_db)):
    pv = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if not pv:
        raise HTTPException(404, "Không tìm thấy provider")
    if body.is_default:
        # chỉ 1 default mỗi task
        db.query(ProviderConfig).filter(ProviderConfig.task == pv.task, ProviderConfig.id != pv.id).update({"is_default": False})
    if body.display_name is not None:
        pv.display_name = body.display_name
    if body.model_name is not None:
        pv.model_name = body.model_name
        db.add(AuditLog(action="Đổi model", detail=f"{pv.display_name} → {body.model_name}"))
    if body.endpoint_url is not None:
        pv.endpoint_url = body.endpoint_url
    if body.api_key is not None:
        pv.api_key_encrypted = encrypt_secret(body.api_key)
    if body.is_default is not None:
        pv.is_default = body.is_default
    if body.is_fallback is not None:
        pv.is_fallback = body.is_fallback
    if body.enabled is not None:
        pv.enabled = body.enabled
    db.commit()
    return _out(pv)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    pv = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if not pv:
        raise HTTPException(404, "Không tìm thấy provider")
    db.add(AuditLog(action="Xóa provider", detail=pv.display_name))
    db.delete(pv)
    db.commit()
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_db)):
    pv = db.query(ProviderConfig).filter(ProviderConfig.id == provider_id).first()
    if not pv:
        raise HTTPException(404, "Không tìm thấy provider")
    try:
        if pv.task == "llm":
            adapter = build_llm_provider(pv)
        else:
            key = decrypt_secret(pv.api_key_encrypted) if pv.api_key_encrypted else ""
            registry = {"tts": _TTS_ADAPTERS, "image": _IMAGE_ADAPTERS, "video": _VIDEO_ADAPTERS}[pv.task]
            adapter_cls = registry.get(pv.provider_name)
            if not adapter_cls:
                raise ValueError("Không hỗ trợ provider này")
            adapter = adapter_cls(api_key=key)
        status = adapter.test_connection()
    except Exception as e:  # noqa: BLE001
        status = None
        pv.status = "error"
        db.add(AuditLog(action="Test kết nối", detail=f"{pv.display_name} — lỗi: {e}"))
        db.commit()
        return {"ok": False, "message": str(e)}

    pv.status = "ok" if status.ok else "error"
    db.add(AuditLog(action="Test kết nối", detail=f"{pv.display_name} — {'thành công' if status.ok else status.message}"))
    db.commit()
    return {"ok": status.ok, "message": status.message}
