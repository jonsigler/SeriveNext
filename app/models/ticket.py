import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TicketStatus(str, enum.Enum):
    NEW = "new"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"  # waiting on requester
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TicketPriority(str, enum.Enum):
    P1 = "p1"  # critical
    P2 = "p2"  # high
    P3 = "p3"  # moderate
    P4 = "p4"  # low


class TicketCategory(str, enum.Enum):
    ACCESS = "access"  # passwords, MFA, group membership
    HARDWARE = "hardware"
    SOFTWARE = "software"
    NETWORK = "network"
    EMAIL = "email"
    PHONE = "phone"
    FACILITIES = "facilities"
    SECURITY = "security"
    REQUEST = "request"
    OTHER = "other"


class TicketSource(str, enum.Enum):
    PORTAL = "portal"
    EMAIL = "email"
    PHONE = "phone"
    CHAT = "chat"
    AGENT = "agent"
    API = "api"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # INC0001001
    subject: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)

    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.NEW, index=True)
    priority: Mapped[TicketPriority] = mapped_column(Enum(TicketPriority), default=TicketPriority.P3)
    category: Mapped[TicketCategory] = mapped_column(Enum(TicketCategory), default=TicketCategory.OTHER)
    source: Mapped[TicketSource] = mapped_column(Enum(TicketSource), default=TicketSource.PORTAL)

    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    affected_ci_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_items.id"), nullable=True
    )

    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Agentic AI fields
    ai_triaged: Mapped[bool] = mapped_column(default=False)
    ai_auto_resolved: Mapped[bool] = mapped_column(default=False)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    requester = relationship("User", foreign_keys=[requester_id])
    assignee = relationship("User", foreign_keys=[assignee_id])
    affected_ci = relationship("ConfigurationItem", foreign_keys=[affected_ci_id])
    events = relationship(
        "TicketEvent",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketEvent.created_at",
    )


class TicketEvent(Base):
    """Unified activity stream: comments, status changes, AI actions, assignments."""

    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # comment | system | ai | status | assignment
    is_internal: Mapped[bool] = mapped_column(default=False)  # hidden from end user
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ticket = relationship("Ticket", back_populates="events")
    author = relationship("User", foreign_keys=[author_id])
