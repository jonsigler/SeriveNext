from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KBArticle(Base):
    """Knowledge base article - used for self-service and AI grounding."""

    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")
    summary: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(String(512), default="")  # space-separated
    published: Mapped[bool] = mapped_column(default=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    author = relationship("User", foreign_keys=[author_id])
