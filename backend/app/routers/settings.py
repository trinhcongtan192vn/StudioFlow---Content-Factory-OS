"""Cấu hình khác (Admin) — specs/03_api.md + specs/06_uiux.md mục 3.

Ghi chú triển khai: `app_setting` là key-value chung (§02) — dùng cho Cấu hình
chung (key `general`), Tham số AI mặc định (key `ai_params`), và **Thương hiệu
ứng dụng** (key `app_branding`, 🎨) — màn này có trong design (state/handler
`appBranding`, `onBrandNameChange`, `selectBrandSwatch`) nhưng KHÔNG có UI hiển thị
trong file .dc.html (chỉ còn state mồ côi). Vì specs/06_uiux.md §3 và PRD §7 M7 liệt
kê nó là bắt buộc trong "toàn bộ khu Cài đặt admin" ở M1, ta bổ sung UI tối giản dùng
lại đúng handler đó (xem IMPLEMENTATION_REPORT.md mục "Bổ sung ngoài design").

Billing/chi phí: xem router budget bên dưới — ghi log chi phí tự động theo từng lệnh
gọi AI CHƯA được nối vào pipeline ở bản này (giới hạn đã biết, ghi trong report);
schema (Budget.spent, AuditLog type='expense') đã sẵn sàng để nối tiếp.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppSetting, AuditLog, Budget, Channel, PromptTemplate, PromptTemplateVersion

router = APIRouter(tags=["settings"])

DEFAULT_SETTINGS = {
    "general": {"org_name": "Media House VN", "language": "vi", "timezone": "Asia/Ho_Chi_Minh", "export_format": "markdown", "naming_convention": "[Kênh]_[YYMMDD]_[Chủ đề ngắn]"},
    "ai_params": {"temperature": 0.7, "length": "3-6 phút", "hook_count": 3, "framework": "AIDA"},
    "app_branding": {"name": "Media House VN", "accent_swatch": 0},
}


def _get_setting(db: Session, key: str) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        return json.loads(row.value)
    return DEFAULT_SETTINGS.get(key, {})


def _put_setting(db: Session, key: str, value: dict):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    encoded = json.dumps(value, ensure_ascii=False)
    if row:
        row.value = encoded
    else:
        db.add(AppSetting(key=key, value=encoded))


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return {k: _get_setting(db, k) for k in DEFAULT_SETTINGS}


@router.put("/settings")
def put_settings(body: dict, db: Session = Depends(get_db)):
    for key, value in body.items():
        _put_setting(db, key, value)
    db.add(AuditLog(action="Sửa cấu hình", detail=", ".join(body.keys())))
    db.commit()
    return {k: _get_setting(db, k) for k in DEFAULT_SETTINGS}


# ---------------------------------------------------------------------------
# Prompt templates (§07, §06 mục 3 🧩)
# ---------------------------------------------------------------------------
def _tpl_out(db: Session, t: PromptTemplate) -> dict:
    versions = db.query(PromptTemplateVersion).filter(PromptTemplateVersion.template_id == t.id).order_by(PromptTemplateVersion.id.desc()).all()
    active = next((v for v in versions if v.version == t.active_version), versions[0] if versions else None)
    return {
        "id": t.id,
        "name": t.name,
        "task": t.task,
        "active_version": t.active_version,
        "body": active.content if active else "",
        "updated_by": active.updated_by if active else "",
        "updated_at": active.created_at.isoformat() if active else "",
        "versions": [
            {"version": v.version, "note": v.note, "updated_by": v.updated_by, "updated_at": v.created_at.isoformat(), "is_active": v.version == t.active_version}
            for v in versions
        ],
    }


@router.get("/prompt-templates")
def list_prompt_templates(db: Session = Depends(get_db)):
    return [_tpl_out(db, t) for t in db.query(PromptTemplate).all()]


class PromptTemplateCreate(BaseModel):
    name: str
    task: str
    body: str


@router.post("/prompt-templates")
def create_prompt_template(body: PromptTemplateCreate, db: Session = Depends(get_db)):
    import time

    tid = f"pt_{int(time.time() * 1000)}"
    t = PromptTemplate(id=tid, name=body.name, task=body.task, active_version="v1")
    db.add(t)
    db.add(PromptTemplateVersion(template_id=tid, version="v1", content=body.body, note="Khởi tạo", updated_by="Bạn"))
    db.add(AuditLog(action="Tạo prompt template", detail=body.name))
    db.commit()
    return _tpl_out(db, t)


class PromptTemplatePatch(BaseModel):
    name: str | None = None
    task: str | None = None
    active_version: str | None = None
    new_version_body: str | None = None
    new_version_note: str | None = None


@router.patch("/prompt-templates/{template_id}")
def patch_prompt_template(template_id: str, body: PromptTemplatePatch, db: Session = Depends(get_db)):
    t = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "Không tìm thấy template")
    if body.name is not None:
        t.name = body.name
    if body.task is not None:
        t.task = body.task
    if body.new_version_body:
        existing = db.query(PromptTemplateVersion).filter(PromptTemplateVersion.template_id == t.id).all()
        next_num = max([int(v.version.lstrip("v")) for v in existing], default=0) + 1
        version = f"v{next_num}"
        db.add(PromptTemplateVersion(template_id=t.id, version=version, content=body.new_version_body, note=body.new_version_note or "Cập nhật", updated_by="Bạn"))
        t.active_version = version
        db.add(AuditLog(action="Thêm phiên bản prompt", detail=t.name))
    if body.active_version is not None:
        t.active_version = body.active_version
        db.add(AuditLog(action="Đặt phiên bản mặc định", detail=f"{t.name} → {body.active_version}"))
    db.commit()
    return _tpl_out(db, t)


@router.delete("/prompt-templates/{template_id}")
def delete_prompt_template(template_id: str, db: Session = Depends(get_db)):
    t = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()
    if not t:
        raise HTTPException(404, "Không tìm thấy template")
    db.add(AuditLog(action="Xóa prompt template", detail=t.name))
    db.delete(t)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit log (§06 mục 3 📜)
# ---------------------------------------------------------------------------
@router.get("/audit-log")
def get_audit_log(type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if type:
        q = q.filter(AuditLog.type == type)
    rows = q.limit(200).all()
    return [
        {
            "time": r.created_at.strftime("%d/%m/%Y %H:%M"),
            "user": "Bạn",
            "action": r.action,
            "detail": r.detail,
            "entity": r.entity,
            "type": r.type,
            "cost": r.cost,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Chi phí & Ngân sách (§06 mục 3 💳)
# ---------------------------------------------------------------------------
@router.get("/budget")
def get_budget(db: Session = Depends(get_db)):
    out = []
    for ch in db.query(Channel).filter(Channel.archived == False).all():  # noqa: E712
        b = db.query(Budget).filter(Budget.channel_id == ch.id).first()
        if not b:
            b = Budget(channel_id=ch.id, soft_limit=8, threshold_pct=60, spent=0)
            db.add(b)
            db.flush()
        out.append(
            {
                "id": b.id,
                "channel_id": ch.id,
                "channel_name": ch.name,
                "soft_limit": b.soft_limit,
                "threshold_pct": b.threshold_pct,
                "spent": b.spent,
                "over_threshold": b.soft_limit > 0 and (b.spent / b.soft_limit * 100) >= b.threshold_pct,
            }
        )
    db.commit()
    return out


class BudgetPatch(BaseModel):
    soft_limit: float | None = None
    threshold_pct: int | None = None


@router.patch("/budget/{channel_id}")
def patch_budget(channel_id: str, body: BudgetPatch, db: Session = Depends(get_db)):
    b = db.query(Budget).filter(Budget.channel_id == channel_id).first()
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not b:
        b = Budget(channel_id=channel_id, soft_limit=8, threshold_pct=60, spent=0)
        db.add(b)
    if body.soft_limit is not None:
        b.soft_limit = body.soft_limit
        db.add(AuditLog(action="Sửa hạn mức", detail=f"{ch.name if ch else channel_id} → ${body.soft_limit}"))
    if body.threshold_pct is not None:
        b.threshold_pct = body.threshold_pct
    db.commit()
    return {"id": b.id, "channel_id": channel_id, "soft_limit": b.soft_limit, "threshold_pct": b.threshold_pct, "spent": b.spent}


@router.get("/budget/{channel_id}/detail")
def get_budget_detail(channel_id: str, db: Session = Depends(get_db)):
    """Chi tiết chi phí theo project/provider, breakdown từng request — khớp màn
    "Xem chi tiết" trong design (đọc từ AuditLog(type='expense'), ghi bởi
    routers/pipeline.py::record_usage — xem IMPLEMENTATION_REPORT.md)."""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    channel_name = ch.name if ch else channel_id
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.type == "expense", AuditLog.entity == channel_name)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    groups: dict[tuple[str, str], dict] = {}
    for r in rows:
        try:
            d = json.loads(r.detail)
        except Exception:  # noqa: BLE001
            continue
        key = (d.get("project", "—"), d.get("provider", "LLM"))
        g = groups.setdefault(key, {"project": key[0], "provider": key[1], "requests": []})
        g["requests"].append({"time": r.created_at.strftime("%d/%m %H:%M"), "model": d.get("model", ""), "tokens_label": d.get("tokens", ""), "cost": r.cost or 0})

    out = []
    for g in groups.values():
        out.append({**g, "request_count": len(g["requests"]), "cost_total": round(sum(x["cost"] for x in g["requests"]), 4)})
    out.sort(key=lambda g: g["cost_total"], reverse=True)
    return {"channel_name": channel_name, "rows": out}
