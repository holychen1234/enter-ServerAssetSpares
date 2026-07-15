"""Shared pytest fixtures for feishu_sync tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Part, PartItem, Server


@pytest.fixture(scope="function")
def engine():
    """In-memory SQLite engine with FK support, scoped per test."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _pragma(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture(scope="function")
def db(engine):
    """Session bound to the test engine. Rolled back after each test."""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


# ── Sample data fixtures ────────────────────────────────────────────


@pytest.fixture(scope="function")
def sample_server(db: Session) -> Server:
    """A server that can be the target of outbound movements."""
    s = Server(
        id=str(uuid.uuid4()),
        hostname="web-server-01",
        sn="SRV-SN-001",
        asset_tag="AT-001",
        manufacturer="Dell",
        model="PowerEdge R740",
        cpu_model="Intel Xeon Gold 6248R",
        cpu_count=2,
        memory_gb=256,
        disk_count=8,
        disk_slot_count=12,
        idc="北京",
        rack="A01",
        u_position="10-12",
        mgmt_ip="10.0.1.100",
        biz_ip="10.0.2.100",
        status="online",
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture(scope="function")
def sample_part(db: Session) -> Part:
    """A disk part in stock."""
    p = Part(
        id=str(uuid.uuid4()),
        category="disk",
        brand="Samsung",
        model="PM9A3",
        spec="960GB NVMe SSD 2.5\"",
        stock=2,
        safety_stock=1,
        unit="块",
        location="A区-3号柜",
        status="in_stock",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture(scope="function")
def sample_part_item(db: Session, sample_part: Part) -> PartItem:
    """An in-stock PartItem with a known SN."""
    it = PartItem(
        id=str(uuid.uuid4()),
        part_id=sample_part.id,
        sn="DISK-SN-001",
        location=sample_part.location,
        status="in_stock",
    )
    db.add(it)
    db.flush()
    return it


@pytest.fixture(scope="function")
def sample_part_item_in_use(db: Session, sample_part: Part, sample_server: Server) -> PartItem:
    """A PartItem that is already in use on a server."""
    it = PartItem(
        id=str(uuid.uuid4()),
        part_id=sample_part.id,
        sn="DISK-SN-002",
        location=sample_part.location,
        status="in_use",
        installed_server_id=sample_server.id,
    )
    db.add(it)
    db.flush()
    return it


@pytest.fixture(scope="function")
def sample_part_item_scrapped(db: Session, sample_part: Part) -> PartItem:
    """A PartItem that has been scrapped."""
    it = PartItem(
        id=str(uuid.uuid4()),
        part_id=sample_part.id,
        sn="DISK-SN-SCRAP",
        status="scrapped",
    )
    db.add(it)
    db.flush()
    return it
