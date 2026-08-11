"""add board_fru JSON column to bmc_snapshots

Revision ID: 004_add_bmc_board_fru
Revises: 003_add_server_disk_slot_count
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "004_add_bmc_board_fru"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: skip if the column already exists (e.g. the DB was
    # created via the updated init-db SQL script or the column was added
    # manually to recover from a failed deployment).
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'bmc_snapshots' "
            "AND column_name = 'board_fru'"
        )
    ).scalar()
    if row:
        return
    op.add_column("bmc_snapshots", sa.Column("board_fru", mysql.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("bmc_snapshots", "board_fru")
