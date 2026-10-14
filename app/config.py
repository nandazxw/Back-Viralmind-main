from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ViralMind API"
    database_url: str = "sqlite:///./viralmind.db"
    jwt_secret: str = "viral-mind-dev-secret-change-this"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    groq_api_key: str = "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"
    groq_model: str = "openai/gpt-oss-120b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()