"""add memory_slots and disk_slots JSON columns to bmc_snapshots

Revision ID: 002_add_memory_disk_slots
Revises: 001_initial
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "002_add_memory_disk_slots"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bmc_snapshots", sa.Column("memory_slots", mysql.JSON, nullable=True))
    op.add_column("bmc_snapshots", sa.Column("disk_slots", mysql.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("bmc_snapshots", "disk_slots")
    op.drop_column("bmc_snapshots", "memory_slots")
