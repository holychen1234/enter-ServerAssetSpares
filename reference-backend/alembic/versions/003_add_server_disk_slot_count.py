"""add disk_slot_count to servers

Revision ID: 003_add_server_disk_slot_count
Revises: 002_add_memory_disk_slots
Create Date: 2026-06-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_add_server_disk_slot_count"
down_revision: Union[str, None] = "002_add_memory_disk_slots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "servers",
        sa.Column("disk_slot_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("servers", "disk_slot_count")
