from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ViralMind API"
    database_url: str = "sqlite:///./viralmind.db"
    jwt_secret: str = "viral-mind-dev-secret-change-this"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Google OAuth 2.0 Credentials
    google_client_id: str = "240358657816-eh64ad30n05mpv56ugtosff2rm1mlqko.apps.googleusercontent.com"
    google_client_secret: str = "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"
    google_redirect_uri: str = "https://back-viralmind-main-production.up.railway.app/api/auth/google/callback"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
