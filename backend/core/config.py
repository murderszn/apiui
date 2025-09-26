from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Supabase settings
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    # Storage settings
    uploads_dir: str = "/Users/jahflyx/apiui/uploads"
    generated_apis_dir: str = "/Users/jahflyx/apiui/generated_apis"
    jobs_file: str = "/Users/jahflyx/apiui/backend/jobs.json"
    apis_file: str = "/Users/jahflyx/apiui/backend/apis.json"
    reset_state_on_start: bool = False
    admin_state_reset_token: Optional[str] = None

    # Google Cloud Storage settings
    gcs_bucket_name: Optional[str] = None
    gcs_project_id: Optional[str] = None

    # Cloud Run Configuration
    gcp_project_id: Optional[str] = None
    gcp_region: Optional[str] = None

    @property
    def use_gcs_storage(self) -> bool:
        """Check if GCS storage should be used"""
        return bool(self.gcs_bucket_name and self.gcs_project_id)

    # AI Service settings
    openai_api_key: Optional[str] = None  # Must be set via OPENAI_API_KEY environment variable

    # API Gateway
    api_gateway_url: Optional[str] = None

    # Security
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # OAuth Providers
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    github_redirect_uri: Optional[str] = None

    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from environment variables

settings = Settings()
