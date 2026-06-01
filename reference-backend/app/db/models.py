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
        Enum("disk", "memory", "nic", "optical", "monitor", "other", name="part_category"),
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


class PartItem(Base):
    """Individual physical spare part with its own serial number."""
    __tablename__ = "part_items"
    id = Column(CHAR(36), primary_key=True)
    part_id = Column(
        CHAR(36), ForeignKey("parts.id", ondelete="CASCADE"), nullable=False
    )
    sn = Column(String(128), nullable=True, unique=True)
    status = Column(
        Enum(
            "in_stock", "allocated", "in_use", "scrapped",
            name="part_item_status",
        ),
        nullable=False,
        default="in_stock",
    )
    location = Column(String(128), nullable=True)
    installed_server_id = Column(
        CHAR(36), ForeignKey("servers.id", ondelete="SET NULL"), nullable=True
    )
    installed_workstation_id = Column(
        CHAR(36), ForeignKey("workstations.id", ondelete="SET NULL"), nullable=True
    )
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (CheckConstraint("quantity > 0"),)
    id = Column(CHAR(36), primary_key=True)
    part_id = Column(CHAR(36), ForeignKey("parts.id"), nullable=False)
    part_item_id = Column(
        CHAR(36), ForeignKey("part_items.id", ondelete="SET NULL"), nullable=True
    )
    type = Column(
        Enum("inbound", "outbound", "return", "scrap", name="movement_type"),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False)
    operator = Column(String(64), nullable=False)
    related_server_id = Column(
        CHAR(36), ForeignKey("servers.id", ondelete="SET NULL"), nullable=True
    )
    related_workstation_id = Column(
        CHAR(36), ForeignKey("workstations.id", ondelete="SET NULL"), nullable=True
    )
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)


class NetworkDevice(Base):
    __tablename__ = "network_devices"
    id = Column(CHAR(36), primary_key=True)
    hostname = Column(String(128), nullable=False)
    sn = Column(String(64), unique=True, nullable=False)
    asset_tag = Column(String(64), unique=True, nullable=False)
    device_type = Column(
        Enum("switch", "router", "firewall", "load_balancer", name="device_type"),
        nullable=False,
        default="switch",
    )
    manufacturer = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    firmware_version = Column(String(64), nullable=True)
    cpu_model = Column(String(128), nullable=True)
    cpu_count = Column(Integer, nullable=False, default=1)
    memory_gb = Column(Integer, nullable=False, default=0)
    flash_gb = Column(Integer, nullable=False, default=0)
    mgmt_ip = Column(String(64), nullable=False)
    mgmt_protocol = Column(
        Enum("ssh", "snmp", "telnet", name="mgmt_protocol"),
        nullable=False,
        default="ssh",
    )
    mgmt_port = Column(Integer, nullable=False, default=22)
    snmp_community = Column(String(64), nullable=True)
    ssh_username = Column(String(64), nullable=True)
    ssh_password = Column(String(255), nullable=True)
    biz_ip = Column(String(64), nullable=True)
    vlan = Column(String(32), nullable=True)
    port_count = Column(Integer, nullable=False, default=0)
    port_spec = Column(JSON, nullable=True)
    idc = Column(String(64), nullable=False)
    rack = Column(String(32), nullable=False)
    u_position = Column(String(32), nullable=False)
    status = Column(
        Enum("online", "offline", "maintenance", "retired", name="ndev_status"),
        nullable=False,
        default="online",
    )
    owner = Column(String(64), nullable=True)
    purchase_date = Column(DateTime, nullable=True)
    warranty_end = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)


class Workstation(Base):
    __tablename__ = "workstations"
    id = Column(CHAR(36), primary_key=True)
    hostname = Column(String(128), nullable=False)
    sn = Column(String(64), unique=True, nullable=False)
    asset_tag = Column(String(64), unique=True, nullable=False)
    manufacturer = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    cpu_model = Column(String(128), nullable=False)
    cpu_count = Column(Integer, nullable=False, default=1)
    memory_gb = Column(Integer, nullable=False, default=0)
    disk_type = Column(String(32), nullable=False, default="SSD")
    disk_capacity_gb = Column(Integer, nullable=False, default=0)
    mac_address = Column(String(17), nullable=True)
    os = Column(String(64), nullable=False, default="Windows 11")
    os_version = Column(String(64), nullable=True)
    biz_ip = Column(String(64), nullable=True)
    user_name = Column(String(64), nullable=True)
    department = Column(String(64), nullable=True)
    monitors = Column(JSON, nullable=True)
    office_building = Column(String(64), nullable=True)
    floor = Column(String(32), nullable=True)
    seat = Column(String(32), nullable=True)
    status = Column(
        Enum("online", "offline", "maintenance", "retired", name="ws_status"),
        nullable=False,
        default="online",
    )
    purchase_date = Column(DateTime, nullable=True)
    warranty_end = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)


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


class BmcSnapshot(Base):
    """Persisted BMC live-status snapshot — collected once per day or on manual
    refresh, so the UI never falls back to simulated data."""
    __tablename__ = "bmc_snapshots"
    id = Column(CHAR(36), primary_key=True)
    server_id = Column(
        CHAR(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False
    )
    collected_at = Column(DateTime, default=_utc_now, nullable=False)
    source = Column(String(16), nullable=False, default="live")
    protocol = Column(String(16), nullable=True)
    power = Column(String(8), nullable=True)
    health = Column(String(16), nullable=True)
    cpu_temp_c = Column(Integer, nullable=True)
    inlet_temp_c = Column(Integer, nullable=True)
    processor_summary = Column(JSON, nullable=True)
    memory_summary = Column(JSON, nullable=True)
    memory_modules = Column(JSON, nullable=True)
    drives = Column(JSON, nullable=True)
    fans = Column(JSON, nullable=True)
    psus = Column(JSON, nullable=True)
    recent_logs = Column(JSON, nullable=True)
    history = Column(JSON, nullable=True)
    alerts = Column(JSON, nullable=True)
