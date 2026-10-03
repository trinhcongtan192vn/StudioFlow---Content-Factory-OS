from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import project_dir
from app.db import get_db
from app.filestore import read_json, write_bytes, write_json, write_versioned
from app.models import PackVersion, Project
from app.providers.factory import NoProviderConfiguredError, get_image_chain
from app.providers.image_comfy_qwen import estimate_cost as estimate_local_qwen_cost
from app.providers.image_gemini import estimate_cost as estimate_gemini_image_cost
from app.providers.image_openai import estimate_cost as estimate_openai_image_cost
from app.routers.pipeline import record_asset_usage
from app.timeutil import vn_isoformat

# Bảng riêng của thumbnail (KHÁC _IMAGE_COST_FN trong app/render/engine.py, dùng cho
# ảnh shot) — thiếu provider local ở đây từng làm sinh thumbnail bằng SDXL local (đã xoá,
# xem đợt dọn dẹp 2026-09-24) bị tính nhầm $0.06 (rơi về fallback
# estimate_openai_image_cost) dù chi phí thật là $0, phát hiện lúc người dùng test thật
# (IMPLEMENTATION_REPORT.md) — giữ nguyên tắc đó cho `local_qwen`.
_IMAGE_COST_FN = {"openai": estimate_openai_image_cost, "gemini": estimate_gemini_image_cost, "local_qwen": estimate_local_qwen_cost}

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
    ym["thumbnail_approved"] = False  # ảnh mới → cần duyệt lại, xem YoutubeMeta.thumbnail_approved
    pack["youtube_meta"] = ym
    write_json(pdir / "pack.json", pack)

    try:
        providers = get_image_chain(db)
    except NoProviderConfiguredError as e:
        ym.update(thumbnail_status="error", thumbnail_error=str(e))
        pack["youtube_meta"] = ym
        write_json(pdir / "pack.json", pack)
        db.commit()
        return pack

    errors = []
    for provider in providers:
        try:
            data = provider.generate(prompt)
            path = pdir / "assets" / "thumbnail.png"
            write_bytes(path, data)
            ym.update(thumbnail_status="ready", thumbnail_asset_path=str(path), thumbnail_provider=provider.provider_name, thumbnail_error=None)
            cost = _IMAGE_COST_FN.get(provider.provider_name, estimate_openai_image_cost)(1, getattr(provider, "model_name", ""))
            record_asset_usage(db, p.channel_id, p.title, provider=provider.provider_name, stage="thumbnail", unit_label="1 ảnh", cost=cost)
            break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider.provider_name}: {e}")
    else:
        ym.update(thumbnail_status="error", thumbnail_error="; ".join(errors))

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
    # `Cache-Control: no-cache` — cùng lý do đã thêm ở `range_file_response`
    # (app/rangefile.py, 2026-08-23): file bị ĐÈ TẠI CHỖ mỗi lần sinh lại, không có header
    # này trình duyệt có thể trả bytes cũ từ cache mà không revalidate.
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


_UPLOAD_EXT_BY_CONTENT_TYPE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@router.post("/projects/{project_id}/pack/thumbnail/upload")
async def upload_thumbnail(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Thay cho sinh bằng AI — người dùng tự upload ảnh thumbnail có sẵn từ máy. Cùng
    vai trò "anchor" như ảnh AI sinh (xem `approve_thumbnail` bên dưới +
    app/render/engine.py::_read_anchor_image) — không cần thumbnail_description, không
    tốn phí provider."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    ym = pack.get("youtube_meta") or {}

    ext = _UPLOAD_EXT_BY_CONTENT_TYPE.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "Chỉ nhận ảnh PNG/JPEG/WEBP")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File ảnh rỗng")

    path = pdir / "assets" / f"thumbnail.{ext}"
    write_bytes(path, data)
    ym.update(thumbnail_status="ready", thumbnail_asset_path=str(path), thumbnail_provider="upload", thumbnail_error=None, thumbnail_approved=False)
    pack["youtube_meta"] = ym
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


class ThumbnailApproveBody(BaseModel):
    approved: bool = True


@router.post("/projects/{project_id}/pack/thumbnail/approve")
def approve_thumbnail(project_id: str, body: ThumbnailApproveBody, db: Session = Depends(get_db)):
    """Duyệt ảnh thumbnail (AI sinh hoặc upload tay) — điều kiện BẮT BUỘC để Visual
    Studio mở khoá nút sinh asset ảnh/video từng shot (xem app/routers/render.py::
    _require_thumbnail_approved), vì ảnh này trở thành "anchor" tham chiếu xuyên suốt
    project (Tier 2 — nhất quán phong cách/nhân vật giữa các shot)."""
    p = _get_project_or_404(db, project_id)
    pdir = project_dir(p.channel_id, project_id)
    pack = read_json(pdir / "pack.json") or {}
    ym = pack.get("youtube_meta") or {}
    if body.approved and ym.get("thumbnail_status") != "ready":
        raise HTTPException(400, "Chưa có ảnh thumbnail sẵn sàng để duyệt")
    ym["thumbnail_approved"] = body.approved
    pack["youtube_meta"] = ym
    write_json(pdir / "pack.json", pack)
    db.commit()
    return pack


@router.get("/projects/{project_id}/pack/versions")
def pack_versions(project_id: str, db: Session = Depends(get_db)):
    versions = db.query(PackVersion).filter(PackVersion.project_id == project_id).order_by(PackVersion.version.desc()).all()
    return [{"version": v.version, "status_at_save": v.status_at_save, "created_at": vn_isoformat(v.created_at)} for v in versions]
