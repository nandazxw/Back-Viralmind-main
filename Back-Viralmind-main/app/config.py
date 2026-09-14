from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ViralMind API"
    database_url: str = "sqlite:///./viralmind.db"
    jwt_secret: str = "viral-mind-dev-secret-change-this"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"  # Atualizado para o modelo oficial

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()