from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./resume_verifier.db"
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 10

    class Config:
        env_file = ".env"

settings = Settings()
