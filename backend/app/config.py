from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./resume_verifier.db"
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 10

    email_provider: str = "resend"
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_sender_email: str = ""
    gmail_admin_email: str = ""
    gmail_encryption_key: str = ""
    gmail_redirect_uri: str = "https://resume-ai-checker-wlsh.onrender.com/api/admin/gmail/callback"

    resend_api_key: str = ""
    otp_from_email: str = "Resume Verifier <onboarding@resend.dev>"

    class Config:
        env_file = ".env"

settings = Settings()
