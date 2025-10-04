from fastapi import APIRouter

router = APIRouter(tags=["users"])


@router.get("/users")
def list_users():
    return {
        "users": [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ]
    }

