from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError

from app.api import ai_query, auth_users, network_devices, parts, servers, workstations
from app.db.base import SessionLocal
from app.db.models import Server
from app.services import bmc as bmc_svc
from app.settings import settings


async def _poll_all():
    """Daily background poller — collects BMC data for every online server
    and persists a snapshot to the database.  Runs once every 24 hours so
    the UI always has fresh-enough data without hammering the BMC."""
    import asyncio as _asyncio
    import logging as _logging
    _log = _logging.getLogger("bmc.poll")

    db = SessionLocal()
    try:
        servers = db.query(Server).filter(Server.status == "online").all()
        if not servers:
            return

        async def _poll_one(s):
            try:
                await _asyncio.wait_for(
                    bmc_svc.collect_and_save(s),
                    timeout=settings.redfish_timeout_seconds + 10,
                )
            except _asyncio.TimeoutError:
                _log.warning(
                    "poll timeout for %s (%s, mgmt_ip=%s)",
                    s.id, s.manufacturer, s.mgmt_ip,
                )
            except Exception:
                pass

        tasks = [_poll_one(s) for s in servers]
        await _asyncio.gather(*tasks, return_exceptions=True)
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
app.include_router(network_devices.router, prefix="/api")
app.include_router(workstations.router, prefix="/api")
app.include_router(parts.router, prefix="/api")
app.include_router(ai_query.router, prefix="/api")
