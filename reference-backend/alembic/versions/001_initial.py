"""initial

Revision ID: 001
Revises:
Create Date: 2026-06-12 10:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # profiles
    op.create_table(
        "profiles",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("email", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "operator", "viewer", name="app_role"), nullable=False, server_default="viewer"),
        sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_deleted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("password_change_required", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime, nullable=True),
        sa.Column("last_login", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    # servers
    op.create_table(
        "servers",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("hostname", sa.String(128), nullable=False),
        sa.Column("sn", sa.String(64), unique=True, nullable=False),
        sa.Column("asset_tag", sa.String(64), unique=True, nullable=False),
        sa.Column("manufacturer", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("cpu_model", sa.String(128), nullable=False),
        sa.Column("cpu_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("memory_gb", sa.Integer, nullable=False, server_default="0"),
        sa.Column("disk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idc", sa.String(64), nullable=False),
        sa.Column("rack", sa.String(32), nullable=False),
        sa.Column("u_position", sa.String(32), nullable=False),
        sa.Column("mgmt_ip", sa.String(64), nullable=False),
        sa.Column("biz_ip", sa.String(64), nullable=False),
        sa.Column("bmc_protocol", sa.Enum("redfish", "ipmi", name="bmc_protocol"), nullable=False, server_default="redfish"),
        sa.Column("bmc_user", sa.String(64), nullable=False, server_default="admin"),
        sa.Column("bmc_password", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("online", "offline", "maintenance", "retired", name="server_status"), nullable=False, server_default="online"),
        sa.Column("owner", sa.String(64), nullable=True),
        sa.Column("purchase_date", sa.DateTime, nullable=True),
        sa.Column("warranty_end", sa.DateTime, nullable=True),
        sa.Column("tags", mysql.JSON, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    # parts
    op.create_table(
        "parts",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("category", sa.Enum("disk", "memory", "nic", "optical", "other", name="part_category"), nullable=False),
        sa.Column("brand", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("spec", sa.String(255), nullable=False),
        sa.Column("sn", sa.String(128), nullable=True),
        sa.Column("stock", sa.Integer, nullable=False, server_default="0"),
        sa.Column("safety_stock", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unit", sa.String(16), nullable=False, server_default="块"),
        sa.Column("location", sa.String(128), nullable=False),
        sa.Column("status", sa.Enum("in_stock", "allocated", "in_use", "scrapped", name="part_status"), nullable=False, server_default="in_stock"),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("stock >= 0"),
    )
    # part_items
    op.create_table(
        "part_items",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("part_id", sa.CHAR(36), sa.ForeignKey("parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sn", sa.String(128), nullable=True, unique=True),
        sa.Column("status", sa.Enum("in_stock", "allocated", "in_use", "scrapped", name="part_item_status"), nullable=False, server_default="in_stock"),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("installed_server_id", sa.CHAR(36), sa.ForeignKey("servers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    # stock_movements
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("part_id", sa.CHAR(36), sa.ForeignKey("parts.id"), nullable=False),
        sa.Column("part_item_id", sa.CHAR(36), sa.ForeignKey("part_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.Enum("inbound", "outbound", "return", "scrap", name="movement_type"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("operator", sa.String(64), nullable=False),
        sa.Column("related_server_id", sa.CHAR(36), sa.ForeignKey("servers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("quantity > 0"),
    )
    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(128), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("level", sa.Enum("info", "warn", "danger", name="audit_level"), nullable=False, server_default="info"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    # bmc_snapshots
    op.create_table(
        "bmc_snapshots",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("server_id", sa.CHAR(36), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collected_at", sa.DateTime, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("protocol", sa.String(16), nullable=True),
        sa.Column("power", sa.String(8), nullable=True),
        sa.Column("health", sa.String(16), nullable=True),
        sa.Column("cpu_temp_c", sa.Integer, nullable=True),
        sa.Column("inlet_temp_c", sa.Integer, nullable=True),
        sa.Column("processor_summary", mysql.JSON, nullable=True),
        sa.Column("memory_summary", mysql.JSON, nullable=True),
        sa.Column("memory_modules", mysql.JSON, nullable=True),
        sa.Column("drives", mysql.JSON, nullable=True),
        sa.Column("fans", mysql.JSON, nullable=True),
        sa.Column("psus", mysql.JSON, nullable=True),
        sa.Column("recent_logs", mysql.JSON, nullable=True),
        sa.Column("history", mysql.JSON, nullable=True),
        sa.Column("alerts", mysql.JSON, nullable=True),
    )
    # terminal_assets
    op.create_table(
        "terminal_assets",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("hostname", sa.String(128), nullable=False),
        sa.Column("sn", sa.String(64), unique=True, nullable=False),
        sa.Column("asset_tag", sa.String(64), unique=True, nullable=False),
        sa.Column("manufacturer", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("cpu_model", sa.String(128), nullable=False),
        sa.Column("cpu_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("memory_gb", sa.Integer, nullable=False, server_default="0"),
        sa.Column("disk_type", sa.String(32), nullable=False, server_default="SSD"),
        sa.Column("disk_capacity_gb", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mac_address", sa.String(17), nullable=True),
        sa.Column("os", sa.String(64), nullable=False, server_default="Windows 11"),
        sa.Column("os_version", sa.String(64), nullable=True),
        sa.Column("biz_ip", sa.String(64), nullable=True),
        sa.Column("user_name", sa.String(64), nullable=True),
        sa.Column("status", sa.Enum("online", "offline", "maintenance", "retired", name="ta_status"), nullable=False, server_default="online"),
        sa.Column("purchase_date", sa.DateTime, nullable=True),
        sa.Column("warranty_end", sa.DateTime, nullable=True),
        sa.Column("tags", mysql.JSON, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("terminal_assets")
    op.drop_table("bmc_snapshots")
    op.drop_table("audit_logs")
    op.drop_table("stock_movements")
    op.drop_table("part_items")
    op.drop_table("parts")
    op.drop_table("servers")
    op.drop_table("profiles")
