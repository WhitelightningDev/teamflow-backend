from fastapi import FastAPI
from app.api.v1.users import router as users_router
from app.api.v1.teams import router as teams_router

app = FastAPI(title="TeamsFlow Backend")


@app.get("/")
def read_root():
    return {"message": "Welcome to TeamsFlow Backend"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Mount API routers
app.include_router(users_router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1")
