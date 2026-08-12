from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_bytes, write_json, write_versioned
from app.models import PackVersion, Project
from app.providers.factory import NoProviderConfiguredError, get_image
from app.providers.image_openai import estimate_cost as estimate_image_cost
from app.routers.pipeline import record_asset_usage

router = APIRouter(tags=["pack"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Không tìm thấy project")
    return p


@router.get("/projects/{project_id}/pack")
def get_pack(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pack = read_json(project_dir(p.channel_id, project_id) / "pack.json")
    if pack is None:
        raise HTTPException(404, "Chưa có Pack")
    return pack


@router.patch("/projects/{project_id}/pack")
def patch_pack(project_id: str, patch: dict, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    pack.update(patch)
    version = (p.pack_version or 1) + 1
    pack["version"] = version
    write_versioned(pdir, "pack", pack, version)
    p.pack_version = version
    db.add(PackVersion(project_id=project_id, version=version, file_path=str(pdir / f"pack.v{version}.json"), status_at_save=pack.get("status", "")))
    db.commit()
    return pack


@router.post("/projects/{project_id}/pack/thumbnail/generate")
def generate_thumbnail(project_id: str, db: Session = Depends(get_db)):
    """Sinh ảnh thumbnail THẬT từ `youtube_meta.thumbnail_description` (M2 — tái dùng
    OpenAI Image adapter, §05 mục 8c). Đồng bộ (1 ảnh, không cần BackgroundTasks như
    Render Studio nhiều shot) — theo đúng nút "Tạo ảnh Thumbnail bằng AI" ở Pack Review."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    ym = pack.get("youtube_meta") or {}
    brand = read_json(pdir.parent.parent / "brandprofile.json") or {}

    desc = (ym.get("thumbnail_description") or "").strip()
    if not desc:
        raise HTTPException(400, "Chưa có mô tả thumbnail để sinh ảnh — điền 'Mô tả thumbnail' trước")
    title_text = (pack.get("titles") or [{}])[0].get("text", "")
    prompt_parts = [desc]
    if title_text:
        prompt_parts.append(f'Có thể lồng chữ overlay ngắn gợi ý từ tiêu đề: "{title_text}"')
    style = brand.get("visual_style_prompt", "")
    if style:
        prompt_parts.append(f"Style hình ảnh kênh: {style}")
    prompt = ". ".join(prompt_parts) + ". YouTube thumbnail, bold, high-contrast, dễ đọc ở kích thước nhỏ, aspect 16:9."

    ym["thumbnail_status"] = "generating"
    pack["youtube_meta"] = ym
    write_json(pdir / "pack.json", pack)

    try:
        provider = get_image(db)
        data = provider.generate(prompt)
        path = pdir / "assets" / "thumbnail.png"
        write_bytes(path, data)
        ym.update(thumbnail_status="ready", thumbnail_asset_path=str(path), thumbnail_provider=provider.provider_name, thumbnail_error=None)
        record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="thumbnail", unit_label="1 ảnh", cost=estimate_image_cost(1))
    except NoProviderConfiguredError as e:
        ym.update(thumbnail_status="error", thumbnail_error=str(e))
    except Exception as e:  # noqa: BLE001
        ym.update(thumbnail_status="error", thumbnail_error=str(e))

    pack["youtube_meta"] = ym
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


@router.get("/projects/{project_id}/pack/thumbnail")
def get_thumbnail_asset(project_id: str, db: Session = Depends(get_db)):
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    path = (pack.get("youtube_meta") or {}).get("thumbnail_asset_path")
    if not path:
        raise HTTPException(404, "Chưa sinh thumbnail")
    return FileResponse(path)


@router.get("/projects/{project_id}/pack/versions")
def pack_versions(project_id: str, db: Session = Depends(get_db)):
    versions = db.query(PackVersion).filter(PackVersion.project_id == project_id).order_by(PackVersion.version.desc()).all()
    return [{"version": v.version, "status_at_save": v.status_at_save, "created_at": v.created_at.isoformat()} for v in versions]
