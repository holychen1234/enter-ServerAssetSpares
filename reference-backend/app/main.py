from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth_users, parts, servers
from app.db.base import SessionLocal
from app.db.models import Server
from app.services import bmc as bmc_svc
from app.settings import settings


async def _poll_all():
    db = SessionLocal()
    try:
        for s in db.query(Server).filter(Server.status == "online").all():
            try:
                await bmc_svc.get_status(s)
            except Exception:
                pass
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
