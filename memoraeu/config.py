from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Identité MVP (désactivé en prod via env)
    default_org_id: str = ""
    default_org_slug: str = ""
    default_org_name: str = ""
    default_user_id: str = ""
    default_user_name: str = ""

    # Mistral AI
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_model: str = "mistral-small-latest"

    # Auth
    registration_open: bool = True
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30  # 30 jours
    admin_emails: str = ""

    # Ollama
    ollama_url: str = "http://localhost:11434"

    # Embedding
    embed_provider: str = "ollama"
    embed_model: str = "nomic-embed-text"
    embed_url: str = "http://localhost:11434"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "memories"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    smtp_from: str = "MemoraEU <contact@memoraeu.com>"
    app_url: str = "https://app.memoraeu.com"

    # SQLite
    sqlite_path: str = "./memoraeu.db"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False  # F1 — jamais True en production

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_set(cls, v: str) -> str:
        if v == "change-me-in-production":
            raise ValueError("JWT_SECRET must be changed from default value")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()
