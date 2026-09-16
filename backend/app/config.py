from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./resume_verifier.db"
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 10

    resend_api_key: str = ""
    otp_from_email: str = "Resume Verifier <onboarding@resend.dev>"

    ai_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    vector_db_path: str = "./.chroma"
    ai_top_k: int = 4

    frontend_url: str = "http://localhost:3000"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/social/google/callback"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/api/auth/social/microsoft/callback"

    auto_refresh_enabled: bool = False
    auto_refresh_sources: str = ""
    auto_refresh_interval_minutes: int = 60

    class Config:
        env_file = ".env"

settings = Settings()
