from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Admin
    ADMIN_PHONE: str

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # Security
    SECRET_KEY: str
    OTP_EXPIRY_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3
    SESSION_EXPIRY_HOURS: int = 12
    SKIP_OTP_VERIFICATION: bool = False  # Set to True to skip OTP in development (admin only)
    SKIP_USER_OTP_VERIFICATION: bool = False  # Set to True to skip OTP for users only
    BOT_SECRET: str = "change-this-in-production"  # Secret for Telegram bot communication
    TELEGRAM_BOT_URL: str = "http://localhost:5000"  # URL for Telegram bot

    # Business Logic
    MAX_BOOKINGS_PER_USER: int = 6
    CANCELLATION_HOURS_BEFORE: int = 48
    BOOKING_MONTHS_AHEAD: int = 2

    # Timezone
    TZ: str = "Europe/Kiev"

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    ENVIRONMENT: str = "development"
    ENABLE_METRICS: bool = True

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = False
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
