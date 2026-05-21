from datetime import datetime, timezone


def _utc_now():
    """Return a timezone-aware UTC datetime so JSON serialization includes
    the offset (+00:00) and browsers can correctly convert to local time."""
    return datetime.now(timezone.utc)
from sqlalchemy import (
    JSON,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.db.base import Base


class Profile(Base):
    __tablename__ = "profiles"
    id = Column(CHAR(36), primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    email = Column(String(128), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        Enum("admin", "operator", "viewer", name="app_role"),
        nullable=False,
        default="viewer",
    )
    enabled = Column(Integer, nullable=False, default=1)
    is_deleted = Column(Integer, nullable=False, default=0)
    password_change_required = Column(Integer, nullable=False, default=0)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)


class Server(Base):
    __tablename__ = "servers"
    id = Column(CHAR(36), primary_key=True)
    hostname = Column(String(128), nullable=False)
    sn = Column(String(64), unique=True, nullable=False)
    asset_tag = Column(String(64), unique=True, nullable=False)
    manufacturer = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    cpu_model = Column(String(128), nullable=False)
    cpu_count = Column(Integer, nullable=False, default=1)
    memory_gb = Column(Integer, nullable=False, default=0)
    disk_count = Column(Integer, nullable=False, default=0)
    idc = Column(String(64), nullable=False)
    rack = Column(String(32), nullable=False)
    u_position = Column(String(32), nullable=False)
    mgmt_ip = Column(String(64), nullable=False)
    biz_ip = Column(String(64), nullable=False)
    bmc_protocol = Column(
        Enum("redfish", "ipmi", name="bmc_protocol"),
        nullable=False,
        default="redfish",
    )
    bmc_user = Column(String(64), nullable=False, default="admin")
    bmc_password = Column(String(255), nullable=True)
    status = Column(
        Enum("online", "offline", "maintenance", "retired", name="server_status"),
        nullable=False,
        default="online",
    )
    owner = Column(String(64), nullable=True)
    purchase_date = Column(DateTime, nullable=True)
    warranty_end = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime, default=_utc_now, onupdate=_utc_now, nullable=False
    )


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (CheckConstraint("stock >= 0"),)
    id = Column(CHAR(36), primary_key=True)
    category = Column(
        Enum("disk", "memory", "nic", "optical", "other", name="part_category"),
        nullable=False,
    )
    brand = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    spec = Column(String(255), nullable=False)
    sn = Column(String(128), nullable=True)
    stock = Column(Integer, nullable=False, default=0)
    safety_stock = Column(Integer, nullable=False, default=0)
    unit = Column(String(16), nullable=False, default="块")
    location = Column(String(128), nullable=False)
    status = Column(
        Enum(
            "in_stock", "allocated", "in_use", "scrapped", name="part_status"
        ),
        nullable=False,
        default="in_stock",
    )
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (CheckConstraint("quantity > 0"),)
    id = Column(CHAR(36), primary_key=True)
    part_id = Column(CHAR(36), ForeignKey("parts.id"), nullable=False)
    type = Column(
        Enum("inbound", "outbound", "return", "scrap", name="movement_type"),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False)
    operator = Column(String(64), nullable=False)
    related_server_id = Column(
        CHAR(36), ForeignKey("servers.id", ondelete="SET NULL"), nullable=True
    )
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(CHAR(36), primary_key=True)
    actor = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)
    target = Column(String(128), nullable=False)
    detail = Column(Text, nullable=True)
    level = Column(
        Enum("info", "warn", "danger", name="audit_level"),
        nullable=False,
        default="info",
    )
    created_at = Column(DateTime, default=_utc_now, nullable=False)
