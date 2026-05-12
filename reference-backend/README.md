# CMDB Reference Backend (FastAPI + MySQL)

A self-contained reference implementation of the CMDB backend designed for
**internal/private deployment**. It mirrors the Enter Cloud Postgres schema
the frontend uses and exposes the same JSON shapes so you can run the platform
fully offline with `docker compose up`.

## Stack

- **FastAPI** + **SQLAlchemy 2** + **Alembic-free** (init-db SQL bundled)
- **MySQL 8** for assets / parts / users / audit / movements
- **Redfish mockup server** (DMTF reference) for end-to-end BMC testing
- **JWT** auth, bcrypt password hashing
- **APScheduler** for periodic Redfish polling (optional)

## Quick start

```bash
cd reference-backend
cp .env.example .env
docker compose up --build
```

Then:

- API:           http://localhost:8000/docs
- MySQL:         localhost:3306 (cmdb / cmdb123, db: cmdb)
- Redfish mock:  http://localhost:8001/redfish/v1

## Seed accounts

| 用户名     | 密码      | 角色     |
| ---------- | --------- | -------- |
| `admin`    | `admin123`| admin    |
| `operator` | `123456`  | operator |
| `viewer`   | `123456`  | viewer   |

## Layout

```
reference-backend/
├── app/
│   ├── main.py                # FastAPI entrypoint, CORS, router wiring
│   ├── settings.py            # Env-driven config
│   ├── auth.py                # JWT issue/verify, role guards
│   ├── db/
│   │   ├── base.py            # SQLAlchemy engine & session
│   │   └── models.py          # ORM models (servers/parts/movements/...)
│   ├── schemas/               # Pydantic schemas
│   ├── services/
│   │   ├── inventory.py       # stock movement business rules
│   │   └── bmc.py             # Redfish + IPMI proxy / collector
│   └── api/                   # Routers (servers, parts, movements, ...)
├── init-db/
│   ├── 01_schema.sql
│   └── 02_seed.sql
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Frontend integration

Switch the frontend from Enter Cloud (Supabase) to this backend by setting
`VITE_USE_INTERNAL_API=1` in `.env.local` once a `internalApi.ts` adapter is
written that calls these REST endpoints. The shapes match `src/types/cmdb.ts`.
