"""
Application settings loaded from environment variables / .env file.

Keeping this in one place means every other module imports a single
`settings` instance instead of scattering `os.getenv()` calls around
the codebase.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- VAPID / Web Push ---
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "mailto:you@example.com"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./mindpulse.db"

    # --- App ---
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    environment: str = "development"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def async_database_url(self) -> str:
        """Render/Railway hand out plain `postgres://`/`postgresql://` URLs,
        but SQLAlchemy's async engine needs an explicit async driver.
        Rewrite transparently so .env only needs the plain connection string."""
        url = self.database_url
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://"):]
        return url

    @property
    def vapid_claims(self) -> dict:
        return {"sub": self.vapid_claims_email}


@lru_cache
def get_settings() -> Settings:
    """Cached so we parse the environment once per process."""
    return Settings()


settings = get_settings()
