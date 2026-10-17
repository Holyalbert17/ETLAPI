from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/integrator"
    REDIS_URL: str = ""
    SECRET_KEY: str = "change-me"
    ENCRYPTION_KEY: str = "0123456789abcdef0123456789abcdef"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BATCH_SIZE: int = 500
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 1
    USER_AGENT: str = "DataIntegratorBot/1.0 (+contact@example.com)"
    LOG_LEVEL: str = "INFO"
    ENABLE_SCHEDULER: bool = True
    AUTO_CREATE_SCHEMA: bool = True
    WORKERS: int = 4
    CORS_ORIGINS: str = "*"
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_EMAIL: str = "admin@example.com"
    ERROR_WEBHOOK_URL: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        raw = [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]
        return raw or ["*"]


settings = Settings()
