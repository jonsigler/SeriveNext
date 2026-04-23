import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CIType(str, enum.Enum):
    """Configuration Item types - mirrors ServiceNow CMDB classes."""

    SERVER = "server"
    WORKSTATION = "workstation"
    LAPTOP = "laptop"
    NETWORK_DEVICE = "network_device"
    PRINTER = "printer"
    MOBILE_DEVICE = "mobile_device"
    APPLICATION = "application"
    SERVICE = "service"
    DATABASE = "database"
    OTHER = "other"


class ConfigurationItem(Base):
    """A tracked asset or service in the CMDB."""

    __tablename__ = "configuration_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    ci_type: Mapped[CIType] = mapped_column(Enum(CIType), default=CIType.OTHER)
    status: Mapped[str] = mapped_column(String(32), default="in_use")  # in_use | in_stock | retired | maintenance
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_tag: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", foreign_keys=[owner_id])
    outgoing_relationships = relationship(
        "CIRelationship",
        foreign_keys="CIRelationship.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    incoming_relationships = relationship(
        "CIRelationship",
        foreign_keys="CIRelationship.target_id",
        back_populates="target",
        cascade="all, delete-orphan",
    )


class CIRelationship(Base):
    """Links between CIs: depends_on, runs_on, hosted_by, connects_to, etc."""

    __tablename__ = "ci_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("configuration_items.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("configuration_items.id"))
    rel_type: Mapped[str] = mapped_column(String(32), default="depends_on")

    source = relationship(
        "ConfigurationItem", foreign_keys=[source_id], back_populates="outgoing_relationships"
    )
    target = relationship(
        "ConfigurationItem", foreign_keys=[target_id], back_populates="incoming_relationships"
    )
