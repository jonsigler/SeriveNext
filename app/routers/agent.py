from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ConfigurationItem,
    Role,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
)
from app.security import require_agent
from app.services import ai_agent, ticket_service
from app.templating import ctx, templates

router = APIRouter(prefix="/agent")


@router.get("")
def dashboard(request: Request, user: User = Depends(require_agent), db: Session = Depends(get_db)):
    def _count(*conds):
        q = select(func.count(Ticket.id))
        for c in conds:
            q = q.where(c)
        return db.scalar(q) or 0

    stats = {
        "open": _count(Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])),
        "mine": _count(Ticket.assignee_id == user.id, Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])),
        "unassigned": _count(Ticket.assignee_id.is_(None), Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])),
        "p1": _count(Ticket.priority == TicketPriority.P1, Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])),
        "auto_resolved": _count(Ticket.ai_auto_resolved.is_(True)),
    }
    recent = db.scalars(select(Ticket).order_by(Ticket.updated_at.desc()).limit(10)).all()
    return templates.TemplateResponse("agent/dashboard.html", ctx(request, stats=stats, recent=recent))


@router.get("/tickets")
def queue(
    request: Request,
    view: str = "all",
    status: str = "",
    priority: str = "",
    q: str = "",
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    query = select(Ticket)
    if view == "mine":
        query = query.where(Ticket.assignee_id == user.id)
    elif view == "unassigned":
        query = query.where(Ticket.assignee_id.is_(None))
    elif view == "open":
        query = query.where(
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])
        )
    if status:
        try:
            query = query.where(Ticket.status == TicketStatus(status))
        except ValueError:
            pass
    if priority:
        try:
            query = query.where(Ticket.priority == TicketPriority(priority))
        except ValueError:
            pass
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(
            or_(Ticket.subject.ilike(like), Ticket.description.ilike(like), Ticket.number.ilike(like))
        )
    tickets = db.scalars(query.order_by(Ticket.created_at.desc()).limit(200)).all()
    return templates.TemplateResponse(
        "agent/queue.html",
        ctx(request, tickets=tickets, view=view, status=status, priority=priority, q=q),
    )


@router.get("/tickets/{ticket_id}")
def ticket_detail(
    request: Request,
    ticket_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    agents = db.scalars(select(User).where(User.role.in_([Role.AGENT, Role.ADMIN])).order_by(User.full_name)).all()
    cis = db.scalars(select(ConfigurationItem).order_by(ConfigurationItem.name)).all()
    return templates.TemplateResponse(
        "agent/ticket.html",
        ctx(
            request,
            ticket=ticket,
            agents=agents,
            cis=cis,
            statuses=list(TicketStatus),
            priorities=list(TicketPriority),
            categories=list(TicketCategory),
        ),
    )


@router.post("/tickets/{ticket_id}/comment")
def ticket_comment(
    request: Request,
    ticket_id: int,
    body: str = Form(...),
    internal: str = Form(""),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    try:
        ticket_service.add_comment(db, ticket, author=user, body=body, is_internal=bool(internal))
    except ValueError:
        pass
    return RedirectResponse(f"/agent/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/update")
def ticket_update(
    request: Request,
    ticket_id: int,
    status: str = Form(""),
    priority: str = Form(""),
    category: str = Form(""),
    assignee_id: str = Form(""),
    affected_ci_id: str = Form(""),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)

    if priority:
        try:
            ticket.priority = TicketPriority(priority)
        except ValueError:
            pass
    if category:
        try:
            ticket.category = TicketCategory(category)
        except ValueError:
            pass
    if affected_ci_id == "":
        pass
    elif affected_ci_id == "none":
        ticket.affected_ci_id = None
    elif affected_ci_id.isdigit():
        ticket.affected_ci_id = int(affected_ci_id)

    if assignee_id == "none":
        ticket_service.assign(db, ticket, None, actor=user)
    elif assignee_id.isdigit():
        assignee = db.get(User, int(assignee_id))
        if assignee:
            ticket_service.assign(db, ticket, assignee, actor=user)

    if status:
        try:
            ticket_service.set_status(db, ticket, TicketStatus(status), actor=user)
        except ValueError:
            pass

    db.commit()
    return RedirectResponse(f"/agent/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/resolve")
def ticket_resolve(
    request: Request,
    ticket_id: int,
    resolution: str = Form(...),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    ticket_service.resolve(db, ticket, actor=user, resolution=resolution)
    return RedirectResponse(f"/agent/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/ai/retriage")
def ticket_retriage(
    request: Request,
    ticket_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    result = ai_agent.triage(db, ticket)
    ai_agent.apply_triage(db, ticket, result)
    db.commit()
    return RedirectResponse(f"/agent/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/ai/apply")
def ticket_apply_ai(
    request: Request,
    ticket_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """Post the AI's suggestion to the requester as an agent comment."""
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    if ticket.ai_suggestion:
        ticket_service.add_comment(
            db,
            ticket,
            author=user,
            body=ticket.ai_suggestion,
            is_internal=False,
        )
    return RedirectResponse(f"/agent/tickets/{ticket_id}", status_code=303)
