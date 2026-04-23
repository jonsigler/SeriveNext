from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.models import Role, TicketPriority, TicketStatus

TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _status_badge(value: str | TicketStatus) -> str:
    v = value.value if isinstance(value, TicketStatus) else value
    return {
        "new": "bg-blue-100 text-blue-800",
        "triaged": "bg-cyan-100 text-cyan-800",
        "in_progress": "bg-amber-100 text-amber-800",
        "pending": "bg-purple-100 text-purple-800",
        "resolved": "bg-emerald-100 text-emerald-800",
        "closed": "bg-slate-200 text-slate-700",
        "cancelled": "bg-slate-200 text-slate-500",
    }.get(v, "bg-slate-100 text-slate-800")


def _priority_badge(value: str | TicketPriority) -> str:
    v = value.value if isinstance(value, TicketPriority) else value
    return {
        "p1": "bg-red-100 text-red-800 border border-red-300",
        "p2": "bg-orange-100 text-orange-800 border border-orange-300",
        "p3": "bg-yellow-100 text-yellow-800 border border-yellow-300",
        "p4": "bg-slate-100 text-slate-700 border border-slate-300",
    }.get(v, "bg-slate-100 text-slate-800")


def _pretty(value: str) -> str:
    return value.replace("_", " ").title()


templates.env.filters["status_badge"] = _status_badge
templates.env.filters["priority_badge"] = _priority_badge
templates.env.filters["pretty"] = _pretty


def ctx(request: Request, **extra) -> dict:
    """Common template context with current user bolted on."""
    from app.security import current_user_optional  # local import avoids cycle
    from app.database import SessionLocal

    user = None
    uid = request.session.get("user_id")
    if uid:
        with SessionLocal() as db:
            from app.models import User

            user = db.get(User, uid)
    return {
        "request": request,
        "user": user,
        "Role": Role,
        "TicketStatus": TicketStatus,
        "TicketPriority": TicketPriority,
        **extra,
    }
