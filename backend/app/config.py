from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./resume_verifier.db"
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 10

    resend_api_key: str = ""
    otp_from_email: str = "Resume Verifier <onboarding@resend.dev>"

    resend_api_key: str = ""
    otp_from_email: str = "Resume Verifier <onboarding@resend.dev>"

    class Config:
        env_file = ".env"

settings = Settings()
