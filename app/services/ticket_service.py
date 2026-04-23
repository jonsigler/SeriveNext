from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Ticket,
    TicketCategory,
    TicketEvent,
    TicketPriority,
    TicketSource,
    TicketStatus,
    User,
)

TERMINAL = {TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED}


def next_ticket_number(db: Session) -> str:
    # INC0001001 style
    count = db.scalar(select(func.count(Ticket.id))) or 0
    return f"INC{1001 + count:07d}"


def create_ticket(
    db: Session,
    *,
    requester: User,
    subject: str,
    description: str,
    category: TicketCategory = TicketCategory.OTHER,
    priority: TicketPriority = TicketPriority.P3,
    source: TicketSource = TicketSource.PORTAL,
    affected_ci_id: int | None = None,
) -> Ticket:
    t = Ticket(
        number=next_ticket_number(db),
        subject=subject.strip()[:255],
        description=description.strip(),
        category=category,
        priority=priority,
        source=source,
        requester_id=requester.id,
        affected_ci_id=affected_ci_id,
    )
    db.add(t)
    db.flush()
    _log(
        db,
        t,
        author_id=requester.id,
        kind="system",
        body=f"Ticket created by {requester.full_name} via {source.value}.",
    )
    db.commit()
    db.refresh(t)
    return t


def add_comment(
    db: Session,
    ticket: Ticket,
    *,
    author: User,
    body: str,
    is_internal: bool = False,
) -> TicketEvent:
    body = body.strip()
    if not body:
        raise ValueError("Comment cannot be empty")
    event = _log(
        db,
        ticket,
        author_id=author.id,
        kind="comment",
        body=body,
        is_internal=is_internal,
    )
    # If a requester replies to a PENDING ticket, move it back to IN_PROGRESS.
    if ticket.status == TicketStatus.PENDING and author.id == ticket.requester_id:
        set_status(db, ticket, TicketStatus.IN_PROGRESS, actor=author, reason="Requester replied")
    db.commit()
    db.refresh(event)
    return event


def set_status(
    db: Session,
    ticket: Ticket,
    new_status: TicketStatus,
    *,
    actor: User | None,
    reason: str = "",
) -> None:
    if ticket.status == new_status:
        return
    old = ticket.status
    ticket.status = new_status
    now = datetime.utcnow()
    if new_status == TicketStatus.RESOLVED and ticket.resolved_at is None:
        ticket.resolved_at = now
    if new_status == TicketStatus.CLOSED and ticket.closed_at is None:
        ticket.closed_at = now
    _log(
        db,
        ticket,
        author_id=actor.id if actor else None,
        kind="status",
        body=f"Status: {old.value} -> {new_status.value}{f' ({reason})' if reason else ''}",
    )


def assign(db: Session, ticket: Ticket, assignee: User | None, *, actor: User) -> None:
    old = ticket.assignee.full_name if ticket.assignee else "Unassigned"
    ticket.assignee_id = assignee.id if assignee else None
    new = assignee.full_name if assignee else "Unassigned"
    _log(db, ticket, author_id=actor.id, kind="assignment", body=f"Assigned: {old} -> {new}")


def resolve(db: Session, ticket: Ticket, *, actor: User, resolution: str) -> None:
    ticket.resolution = resolution.strip()
    set_status(db, ticket, TicketStatus.RESOLVED, actor=actor, reason="Resolved")
    db.commit()


def _log(
    db: Session,
    ticket: Ticket,
    *,
    author_id: int | None,
    kind: str,
    body: str,
    is_internal: bool = False,
) -> TicketEvent:
    event = TicketEvent(
        ticket_id=ticket.id,
        author_id=author_id,
        kind=kind,
        body=body,
        is_internal=is_internal,
    )
    db.add(event)
    db.flush()
    return event
