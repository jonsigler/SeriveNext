"""Minimal JSON API for integrations (e.g. email-to-ticket gateways, chatbots)."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ticket, TicketCategory, TicketPriority, TicketSource, User
from app.security import current_user, require_agent
from app.services import ai_agent, ticket_service

router = APIRouter(prefix="/api/v1")


class TicketIn(BaseModel):
    subject: str = Field(..., max_length=255)
    description: str
    category: TicketCategory = TicketCategory.OTHER
    priority: TicketPriority = TicketPriority.P3
    source: TicketSource = TicketSource.API
    affected_ci_id: int | None = None


class TicketOut(BaseModel):
    id: int
    number: str
    subject: str
    status: str
    priority: str
    category: str
    ai_triaged: bool
    ai_auto_resolved: bool
    ai_confidence: float | None
    ai_suggestion: str | None


@router.post("/tickets", response_model=TicketOut)
def api_create_ticket(
    payload: TicketIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = ticket_service.create_ticket(
        db,
        requester=user,
        subject=payload.subject,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
        source=payload.source,
        affected_ci_id=payload.affected_ci_id,
    )
    result = ai_agent.triage(db, ticket)
    ai_agent.apply_triage(db, ticket, result)
    ai_agent.maybe_auto_resolve(db, ticket, result)
    db.commit()
    db.refresh(ticket)
    return _ticket_out(ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def api_get_ticket(
    ticket_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    if ticket.requester_id != user.id and not user.is_agent:
        raise HTTPException(status_code=403)
    return _ticket_out(ticket)


@router.post("/tickets/{ticket_id}/retriage", response_model=TicketOut)
def api_retriage(
    ticket_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
) -> TicketOut:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404)
    result = ai_agent.triage(db, ticket)
    ai_agent.apply_triage(db, ticket, result)
    ai_agent.maybe_auto_resolve(db, ticket, result)
    db.commit()
    db.refresh(ticket)
    return _ticket_out(ticket)


def _ticket_out(t: Ticket) -> TicketOut:
    return TicketOut(
        id=t.id,
        number=t.number,
        subject=t.subject,
        status=t.status.value,
        priority=t.priority.value,
        category=t.category.value,
        ai_triaged=t.ai_triaged,
        ai_auto_resolved=t.ai_auto_resolved,
        ai_confidence=t.ai_confidence,
        ai_suggestion=t.ai_suggestion,
    )
