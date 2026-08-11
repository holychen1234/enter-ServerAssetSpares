"""
Pre-start script that ensures the alembic migration tracking table is in
sync with the actual database schema before ``alembic upgrade head`` runs.

Problem this solves
-------------------
Existing deployments created their tables via ``init-db/*.sql`` scripts
*without* ever running alembic.  When the Docker container starts and
executes ``alembic upgrade head``, alembic tries to create every table
from migration 001 onward — but they already exist → the migration fails,
the container restarts, and the API is unreachable.

This script inspects the database and stamps the alembic revision to
match the current schema so that only *new* migrations (e.g. the
``board_fru`` column) are applied.
"""

import sys

from sqlalchemy import create_engine, text

from app.settings import settings

# ── helpers ──────────────────────────────────────────────────────────


def _db_url() -> str:
    """Build a synchronous SQLAlchemy URL from settings."""
    return (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )


def _table_exists(engine, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = :db AND table_name = :tbl"
            ),
            {"db": settings.mysql_database, "tbl": table},
        ).scalar()
        return bool(row)


def _column_exists(engine, table: str, column: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = :db AND table_name = :tbl "
                "AND column_name = :col"
            ),
            {"db": settings.mysql_database, "tbl": table, "col": column},
        ).scalar()
        return bool(row)


def _alembic_has_entries(engine) -> bool:
    if not _table_exists(engine, "alembic_version"):
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE TABLE alembic_version ("
                    "    version_num VARCHAR(32) NOT NULL PRIMARY KEY"
                    ")"
                )
            )
            conn.commit()
        return False
    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()
        return bool(cnt)


def _stamp(engine, revision: str) -> None:
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": revision},
        )
        conn.commit()


# ── detection logic ──────────────────────────────────────────────────


def _detect_current_revision(engine) -> str:
    """Inspect the database to guess which alembic revision it matches.

    We use progressively newer schema features to decide:
      * 002 added ``memory_slots`` + ``disk_slots`` to bmc_snapshots
      * 003 added ``disk_slot_count`` to servers
      * 004 added ``board_fru`` to bmc_snapshots
    """

    # If the bmc_snapshots table doesn't exist at all, the DB is empty → 000
    if not _table_exists(engine, "bmc_snapshots"):
        print("[prestart] bmc_snapshots table not found → stamping to '001' (base)")
        return "001"

    # 004: board_fru column
    if _column_exists(engine, "bmc_snapshots", "board_fru"):
        # Also check for memory_slots/disk_slots in case 004 was manually added
        if _column_exists(engine, "bmc_snapshots", "memory_slots"):
            print("[prestart] board_fru + memory_slots exist → stamping to '004'")
            return "004"

    # 003: disk_slot_count on servers
    if _column_exists(engine, "servers", "disk_slot_count"):
        # Could be 003 or 004; we already checked 004 above
        if _column_exists(engine, "bmc_snapshots", "memory_slots"):
            print("[prestart] disk_slot_count + memory_slots exist → stamping to '003'")
            return "003"
        print("[prestart] disk_slot_count exists → stamping to '003'")
        return "003"

    # 002: memory_slots + disk_slots on bmc_snapshots
    if _column_exists(engine, "bmc_snapshots", "memory_slots"):
        print("[prestart] memory_slots column exists → stamping to '002'")
        return "002"

    # Fallback: basic schema (001)
    print("[prestart] basic schema detected → stamping to '001'")
    return "001"


# ── main ─────────────────────────────────────────────────────────────


def main() -> None:
    print("[prestart] Connecting to database …")
    engine = create_engine(_db_url())

    try:
        if _alembic_has_entries(engine):
            with engine.connect() as conn:
                current = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
            print(f"[prestart] alembic already stamped at {current} — nothing to do")
            return

        print("[prestart] alembic_version is empty — detecting schema state …")
        revision = _detect_current_revision(engine)
        _stamp(engine, revision)
        print(f"[prestart] Stamped alembic to {revision}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
