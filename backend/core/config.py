from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Server settings (self-hosted / local / LAN)
    host: str = "0.0.0.0"
    port: int = 8000
    api_gateway_url: Optional[str] = None

    # Supabase settings
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    # Storage settings (relative to repo root by default)
    uploads_dir: str = str(BASE_DIR / "uploads")
    generated_apis_dir: str = str(BASE_DIR / "generated_apis")
    jobs_file: str = str(BASE_DIR / "backend" / "jobs.json")
    apis_file: str = str(BASE_DIR / "backend" / "apis.json")
    api_states_file: str = str(BASE_DIR / "backend" / "api_states.json")
    api_metadata_file: str = str(BASE_DIR / "backend" / "api_metadata.json")
    reset_state_on_start: bool = False
    admin_state_reset_token: Optional[str] = None

    # Google Cloud Storage settings
    gcs_bucket_name: Optional[str] = None
    gcs_project_id: Optional[str] = None

    # Cloud Run Configuration (legacy / optional)
    gcp_project_id: Optional[str] = None
    gcp_region: Optional[str] = None

    @property
    def use_gcs_storage(self) -> bool:
        """Check if GCS storage should be used"""
        return bool(self.gcs_bucket_name and self.gcs_project_id)

    # AI Service settings
    openai_api_key: Optional[str] = None  # Must be set via OPENAI_API_KEY environment variable

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
        env_file = (str(BASE_DIR / ".env"), str(BASE_DIR / "backend" / ".env"), ".env")
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from environment variables


settings = Settings()
