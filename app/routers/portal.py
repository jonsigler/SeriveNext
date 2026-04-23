from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConfigurationItem, KBArticle, Ticket, TicketSource, User
from app.security import current_user
from app.services import ai_agent, ticket_service
from app.templating import ctx, templates

router = APIRouter(prefix="/portal")


@router.get("")
def home(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    my_tickets = db.scalars(
        select(Ticket).where(Ticket.requester_id == user.id).order_by(Ticket.created_at.desc()).limit(25)
    ).all()
    popular_articles = db.scalars(
        select(KBArticle).where(KBArticle.published.is_(True)).order_by(KBArticle.views.desc()).limit(6)
    ).all()
    return templates.TemplateResponse(
        "portal/home.html",
        ctx(request, my_tickets=my_tickets, popular_articles=popular_articles),
    )


@router.get("/new")
def new_ticket_page(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    my_cis = db.scalars(
        select(ConfigurationItem).where(ConfigurationItem.owner_id == user.id).order_by(ConfigurationItem.name)
    ).all()
    return templates.TemplateResponse("portal/new.html", ctx(request, my_cis=my_cis))


@router.post("/new")
def submit_ticket(
    request: Request,
    subject: str = Form(...),
    description: str = Form(...),
    affected_ci_id: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ci_id = int(affected_ci_id) if affected_ci_id.strip().isdigit() else None
    ticket = ticket_service.create_ticket(
        db,
        requester=user,
        subject=subject,
        description=description,
        affected_ci_id=ci_id,
        source=TicketSource.PORTAL,
    )
    # Run the AI agent synchronously so the end user sees an instant self-service
    # answer where possible.
    result = ai_agent.triage(db, ticket)
    ai_agent.apply_triage(db, ticket, result)
    ai_agent.maybe_auto_resolve(db, ticket, result)
    db.commit()
    return RedirectResponse(f"/portal/tickets/{ticket.id}", status_code=303)


@router.get("/tickets/{ticket_id}")
def ticket_detail(
    request: Request,
    ticket_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    visible_events = [e for e in ticket.events if not e.is_internal]
    return templates.TemplateResponse(
        "portal/ticket.html",
        ctx(request, ticket=ticket, events=visible_events),
    )


@router.post("/tickets/{ticket_id}/comment")
def ticket_comment(
    request: Request,
    ticket_id: int,
    body: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        ticket_service.add_comment(db, ticket, author=user, body=body, is_internal=False)
    except ValueError:
        pass
    return RedirectResponse(f"/portal/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/reopen")
def ticket_reopen(
    request: Request,
    ticket_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.models import TicketStatus

    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.requester_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        ticket_service.set_status(
            db,
            ticket,
            TicketStatus.IN_PROGRESS,
            actor=user,
            reason="Reopened by requester",
        )
        db.commit()
    return RedirectResponse(f"/portal/tickets/{ticket_id}", status_code=303)


@router.get("/kb")
def kb_search(
    request: Request,
    q: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(KBArticle).where(KBArticle.published.is_(True))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                KBArticle.title.ilike(like),
                KBArticle.summary.ilike(like),
                KBArticle.keywords.ilike(like),
                KBArticle.body.ilike(like),
            )
        )
    articles = db.scalars(query.order_by(KBArticle.views.desc()).limit(50)).all()
    return templates.TemplateResponse("portal/kb.html", ctx(request, articles=articles, q=q))


@router.get("/kb/{article_id}")
def kb_article(
    request: Request,
    article_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    article = db.get(KBArticle, article_id)
    if not article or not article.published:
        raise HTTPException(status_code=404)
    article.views += 1
    db.commit()
    return templates.TemplateResponse("portal/kb_article.html", ctx(request, article=article))
