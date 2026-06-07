from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    POSTGRES_PASSWORD: str = ""

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # Security
    RSA_PRIVATE_KEY_PATH: Path
    RSA_PUBLIC_KEY_PATH: Path
    FERNET_KEY: str
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = True
    COOKIE_DOMAIN: str = ""

    # Storage
    STORAGE_PATH: Path = Path("/data/recordings")
    HLS_PATH: Path = Path("/data/hls")
    EXPORT_PATH: Path = Path("/data/exports")
    ALERT_CLIPS_PATH: Path = Path("/data/alerts")
    STORAGE_WARNING_PCT: int = 80
    STORAGE_CRITICAL_PCT: int = 90
    EXPORT_EXPIRY_HOURS: int = 48

    # CORS + Network
    CORS_ORIGINS: str = "http://localhost:5173"
    ALLOWED_HOSTS: str = "localhost"

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_STARTTLS: bool = True
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@example.com"

    # HaveIBeenPwned
    HIBP_API_KEY: str = ""

    # Detection
    DETECTION_CONFIDENCE: float = 0.5
    DETECTION_SAMPLE_FPS: int = 2
    DETECTION_MODEL_PATH: Path = Path("/models/yolov8n.pt")
    DETECTION_ALERT_COOLDOWN_S: int = 60

    # Application
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    FACILITY_NAME: str = "NVR Pro"
    DEFAULT_TIMEZONE: str = "UTC"
    DEFAULT_LANGUAGE: str = "en"

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_be_postgres(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must start with 'postgresql'")
        return v

    @model_validator(mode="after")
    def storage_pct_ordering(self) -> "Settings":
        if self.STORAGE_WARNING_PCT >= self.STORAGE_CRITICAL_PCT:
            raise ValueError("STORAGE_WARNING_PCT must be less than STORAGE_CRITICAL_PCT")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
