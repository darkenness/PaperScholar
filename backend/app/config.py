import warnings
from typing import List
from pydantic_settings import BaseSettings

_DEFAULT_SECRET = "paperscholar-dev-secret-change-me-in-production-env"
_DEFAULT_JWT_SECRET = "paperscholar-dev-jwt-secret-change-me-in-production-env"


class Settings(BaseSettings):
    APP_NAME: str = "PaperScholar"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = _DEFAULT_SECRET
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://paperscholar:paperscholar@localhost:5432/paperscholar"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = _DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # API Key Encryption
    API_KEY_ENCRYPTION_KEY: str = ""

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 20

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@paperscholar.local"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# Warn if using default secrets (tokens/encryption will break across deployments)
if settings.SECRET_KEY == _DEFAULT_SECRET or settings.JWT_SECRET_KEY == _DEFAULT_JWT_SECRET:
    warnings.warn(
        "\n[PaperScholar] WARNING: Using default SECRET_KEY / JWT_SECRET_KEY!\n"
        "  Set SECRET_KEY and JWT_SECRET_KEY in .env for production.\n"
        "  Without this, JWT tokens and encrypted API keys will break across restarts on different machines.",
        stacklevel=2,
    )
