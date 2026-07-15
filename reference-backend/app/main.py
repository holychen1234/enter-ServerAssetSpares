from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError

from app.api import ai_query, auth_users, feishu, parts, servers, terminal_assets
from app.db.base import SessionLocal
from app.db.models import Server
from app.services import bmc as bmc_svc
from app.settings import settings


async def _poll_all():
    """Weekly gentle poller — staggers BMC polls one-by-one to avoid
    flooding the network, and respects a cooldown so recently-unreachable
    hosts are only retried after a back-off period.

    Successful results are persisted to the database immediately.
    Manual refreshes always bypass this cooldown."""
    import asyncio as _asyncio
    import logging as _logging
    _log = _logging.getLogger("bmc.poll")

    db = SessionLocal()
    try:
        servers = db.query(Server).filter(Server.status == "online").all()
        if not servers:
            return

        _log.info("gentle weekly poll starting for %d servers", len(servers))
        ok = 0
        failed = 0
        skipped = 0

        for i, s in enumerate(servers):
            # Honour per-host cooldown so we don't hammer dead BMCs every week
            if bmc_svc._in_cooldown(s.mgmt_ip):
                skipped += 1
                continue

            # Gentle stagger: 2–4 s between each server so BMCs and switches
            # are never hit with a connection flood
            if i > 0:
                await _asyncio.sleep(3)

            try:
                snap = await _asyncio.wait_for(
                    bmc_svc.collect_and_save(s),
                    timeout=settings.redfish_timeout_seconds + 10,
                )
                if snap:
                    ok += 1
                    bmc_svc._clear_cooldown(s.mgmt_ip)
                else:
                    failed += 1
                    bmc_svc._set_cooldown(s.mgmt_ip)
            except _asyncio.TimeoutError:
                failed += 1
                bmc_svc._set_cooldown(s.mgmt_ip)
            except Exception:
                failed += 1
                bmc_svc._set_cooldown(s.mgmt_ip)

        _log.info(
            "gentle poll finished: %d ok, %d failed, %d skipped (cooldown), of %d total",
            ok, failed, skipped, len(servers),
        )
    finally:
        db.close()


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.poll_interval_seconds > 0:
        scheduler.add_job(
            _poll_all,
            "interval",
            seconds=settings.poll_interval_seconds,
            id="bmc-poll",
        )
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="CMDB Reference API", version="0.1.0", lifespan=lifespan)


# ── Unified exception handlers ──────────────────────────────

@app.exception_handler(IntegrityError)
@app.exception_handler(DataError)
@app.exception_handler(ProgrammingError)
async def sqlalchemy_exc_handler(_request: Request, exc: Exception) -> JSONResponse:
    detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
    return JSONResponse(status_code=422, content={"detail": f"数据库错误: {detail}"})


@app.exception_handler(Exception)
async def generic_exc_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误: {str(exc)}"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"ok": True}


app.include_router(auth_users.router, prefix="/api")
app.include_router(servers.router, prefix="/api")
app.include_router(parts.router, prefix="/api")
app.include_router(terminal_assets.router, prefix="/api")
app.include_router(ai_query.router, prefix="/api")
app.include_router(feishu.router, prefix="/api")
