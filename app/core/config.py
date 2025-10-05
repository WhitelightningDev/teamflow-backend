import os
from dotenv import load_dotenv


class Settings:
    def __init__(self) -> None:
        # Load variables from .env into environment
        load_dotenv()
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "changeme")
        self.MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "teamflow")
        # Frontend base URL (used in CORS and building links)
        # Default to local Vite dev server
        self.FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "https://teamflow-pearl.vercel.app/")
        # Optional comma-separated list of additional allowed origins for CORS
        self.ALLOWED_ORIGINS: list[str] = [
            o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
        ]


settings = Settings()
