from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me-before-deploying!"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field("development", alias="APP_ENV")
    database_url: str = "postgresql+asyncpg://provenn:provenn@localhost:5432/provenn"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_hours: int = 12
    cors_origins: str = "http://localhost:3000"

    # S3-compatible storage. Leave the keys empty on AWS to use the instance role.
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str | None = "provenn"
    s3_secret_key: str | None = "provenn-secret"
    s3_bucket: str = "provenn"

    run_worker: bool = False  # run the job loop inside the api process
    worker_poll_seconds: float = 1.0
    max_upload_mb: int = 20

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.env == "production" and (
            self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must be set (32+ chars) when APP_ENV=production")
        # Hosts like Render/Neon hand out postgres:// URLs; use the async driver.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+asyncpg://" + self.database_url[len(prefix) :]
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
