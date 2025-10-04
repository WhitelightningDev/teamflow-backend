from fastapi import APIRouter
from app.services.team_service import list_teams

router = APIRouter(tags=["teams"])


@router.get("/teams")
def get_teams():
    return {"teams": list_teams()}

