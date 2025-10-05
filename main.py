import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.users import router as users_router
from app.api.v1.teams import router as teams_router
from app.api.v1.auth import router as auth_router
from app.api.v1.employees import router as employees_router
from app.api.v1.leaves import router as leaves_router
from app.api.v1.documents import router as documents_router
from app.api.v1.settings import router as settings_router
from app.api.v1.lookups import router as lookups_router
from app.api.v1.attendance import router as attendance_router
from app.api.v1.announcements import router as announcements_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.me import router as me_router
from app.db.mongo import get_mongo_client, close_mongo_client
from app.db.mongo_indexes import ensure_indexes

app = FastAPI(title="TeamsFlow Backend")

# CORS for local frontend dev
# Build CORS allowlist from local dev + configured origins
_base_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://0.0.0.0:5173",
    "https://teamflow-pearl.vercel.app/",
}
if settings.FRONTEND_BASE_URL:
    _base_origins.add(settings.FRONTEND_BASE_URL)
for o in settings.ALLOWED_ORIGINS:
    _base_origins.add(o)
# Normalize by stripping trailing slashes to match Origin header format
_allowed_origins = sorted({o.rstrip('/') for o in _base_origins if o})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^http(s)?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Welcome to TeamsFlow Backend"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Mount API routers
app.include_router(users_router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(employees_router, prefix="/api/v1")
app.include_router(leaves_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(lookups_router, prefix="/api/v1")
app.include_router(attendance_router, prefix="/api/v1")
app.include_router(announcements_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(me_router, prefix="/api/v1")


@app.on_event("startup")
async def on_startup():
    # Initialize Mongo client
    get_mongo_client()
    # Create required indexes (non-fatal on failure)
    try:
        await ensure_indexes()
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning(
            "Mongo index initialization failed: %s", exc
        )


@app.on_event("shutdown")
async def on_shutdown():
    # Close Mongo client
    close_mongo_client()
