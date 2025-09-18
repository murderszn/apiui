from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # MongoDB settings
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "apiui"

    # Cloud Storage settings
    gcs_bucket_name: str = "apiui-files"
    gcs_project_id: Optional[str] = None
    use_gcs_storage: bool = False  # Set to True to use GCS instead of local storage

    # AI Service settings
    openai_api_key: Optional[str] = None  # Must be set via OPENAI_API_KEY environment variable

    # Cloud Run settings
    gcp_project_id: Optional[str] = None
    gcp_region: str = "us-central1"

    # API Gateway settings
    api_gateway_url: Optional[str] = None

    # Security
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # OAuth providers
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    github_redirect_uri: Optional[str] = None

    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None

    # Storage settings
    uploads_dir: str = "/Users/jahflyx/apiui/uploads"
    generated_apis_dir: str = "/Users/jahflyx/apiui/generated_apis"
    jobs_file: str = "/Users/jahflyx/apiui/backend/jobs.json"
    apis_file: str = "/Users/jahflyx/apiui/backend/apis.json"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from environment variables

settings = Settings()
