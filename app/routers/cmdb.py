from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CIType, ConfigurationItem, User
from app.security import require_agent
from app.templating import ctx, templates

router = APIRouter(prefix="/agent/cmdb")


@router.get("")
def cmdb_list(
    request: Request,
    q: str = "",
    ci_type: str = "",
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    query = select(ConfigurationItem)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                ConfigurationItem.name.ilike(like),
                ConfigurationItem.asset_tag.ilike(like),
                ConfigurationItem.serial_number.ilike(like),
                ConfigurationItem.ip_address.ilike(like),
            )
        )
    if ci_type:
        try:
            query = query.where(ConfigurationItem.ci_type == CIType(ci_type))
        except ValueError:
            pass
    cis = db.scalars(query.order_by(ConfigurationItem.name).limit(500)).all()
    return templates.TemplateResponse(
        "agent/cmdb_list.html",
        ctx(request, cis=cis, q=q, ci_type=ci_type, ci_types=list(CIType)),
    )


@router.get("/new")
def cmdb_new(request: Request, user: User = Depends(require_agent), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.full_name)).all()
    return templates.TemplateResponse(
        "agent/cmdb_form.html",
        ctx(request, ci=None, users=users, ci_types=list(CIType)),
    )


@router.post("/new")
def cmdb_create(
    request: Request,
    name: str = Form(...),
    ci_type: str = Form(...),
    status: str = Form("in_use"),
    asset_tag: str = Form(""),
    serial_number: str = Form(""),
    manufacturer: str = Form(""),
    model: str = Form(""),
    location: str = Form(""),
    ip_address: str = Form(""),
    os: str = Form(""),
    owner_id: str = Form(""),
    description: str = Form(""),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ci = ConfigurationItem(
        name=name.strip(),
        ci_type=CIType(ci_type),
        status=status,
        asset_tag=asset_tag.strip() or None,
        serial_number=serial_number.strip() or None,
        manufacturer=manufacturer.strip() or None,
        model=model.strip() or None,
        location=location.strip() or None,
        ip_address=ip_address.strip() or None,
        os=os.strip() or None,
        owner_id=int(owner_id) if owner_id.isdigit() else None,
        description=description.strip() or None,
    )
    db.add(ci)
    db.commit()
    return RedirectResponse(f"/agent/cmdb/{ci.id}", status_code=303)


@router.get("/{ci_id}")
def cmdb_detail(
    request: Request,
    ci_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ci = db.get(ConfigurationItem, ci_id)
    if not ci:
        raise HTTPException(status_code=404)
    from app.models import Ticket

    related_tickets = db.scalars(
        select(Ticket).where(Ticket.affected_ci_id == ci.id).order_by(Ticket.created_at.desc()).limit(25)
    ).all()
    users = db.scalars(select(User).order_by(User.full_name)).all()
    return templates.TemplateResponse(
        "agent/cmdb_detail.html",
        ctx(request, ci=ci, related_tickets=related_tickets, users=users, ci_types=list(CIType)),
    )


@router.post("/{ci_id}/update")
def cmdb_update(
    request: Request,
    ci_id: int,
    name: str = Form(...),
    ci_type: str = Form(...),
    status: str = Form("in_use"),
    asset_tag: str = Form(""),
    serial_number: str = Form(""),
    manufacturer: str = Form(""),
    model: str = Form(""),
    location: str = Form(""),
    ip_address: str = Form(""),
    os: str = Form(""),
    owner_id: str = Form(""),
    description: str = Form(""),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ci = db.get(ConfigurationItem, ci_id)
    if not ci:
        raise HTTPException(status_code=404)
    ci.name = name.strip()
    ci.ci_type = CIType(ci_type)
    ci.status = status
    ci.asset_tag = asset_tag.strip() or None
    ci.serial_number = serial_number.strip() or None
    ci.manufacturer = manufacturer.strip() or None
    ci.model = model.strip() or None
    ci.location = location.strip() or None
    ci.ip_address = ip_address.strip() or None
    ci.os = os.strip() or None
    ci.owner_id = int(owner_id) if owner_id.isdigit() else None
    ci.description = description.strip() or None
    db.commit()
    return RedirectResponse(f"/agent/cmdb/{ci.id}", status_code=303)
