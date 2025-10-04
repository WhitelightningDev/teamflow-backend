from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


_mongo_client: Optional[AsyncIOMotorClient] = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        # Use certifi CA bundle to avoid SSL verify errors with Atlas
        client_kwargs = {"serverSelectionTimeoutMS": 30000}
        try:
            import certifi  # type: ignore
            client_kwargs["tlsCAFile"] = certifi.where()
        except Exception:
            pass
        _mongo_client = AsyncIOMotorClient(settings.MONGODB_URI, **client_kwargs)
    return _mongo_client


def get_mongo_db() -> AsyncIOMotorDatabase:
    client = get_mongo_client()
    return client[settings.MONGODB_DB_NAME]


def close_mongo_client() -> None:
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
