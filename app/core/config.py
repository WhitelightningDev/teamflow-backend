import os
from dotenv import load_dotenv


class Settings:
    def __init__(self) -> None:
        # Load variables from .env into environment
        load_dotenv()
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "changeme")


settings = Settings()

