from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # MongoDB settings
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "apiui"

    # Cloud Storage settings
    gcs_bucket_name: str = "apiui-files"
    gcs_project_id: Optional[str] = None

    # AI Service settings
    openai_api_key: Optional[str] = None  # Must be set via OPENAI_API_KEY environment variable
    google_ai_api_key: Optional[str] = None  # Not using Google AI, only OpenAI

    # Cloud Run settings
    gcp_project_id: Optional[str] = None
    gcp_region: str = "us-central1"

    # API Gateway settings
    api_gateway_url: Optional[str] = None

    # Security
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from environment variables

settings = Settings()
