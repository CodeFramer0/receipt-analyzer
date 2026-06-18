from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    uploads_dir: Path = Path("./uploads")
    reports_dir: Path = Path("./reports")
    references_dir: Path = Path("./references")


settings = Settings()
