import uuid
from typing import Dict, Any
from core.config import settings
from services.storage_service import storage_service


class DeploymentService:
    """Self-hosted API deployment service (serves APIs directly from this backend)."""

    def __init__(self):
        self.gcp_project_id = settings.gcp_project_id
        self.gcp_region = settings.gcp_region

    def _get_base_url(self) -> str:
        """Resolve base URL from API_GATEWAY_URL or local host/port settings."""
        if settings.api_gateway_url:
            return settings.api_gateway_url.rstrip("/")
        host = settings.host if settings.host and settings.host != "0.0.0.0" else "localhost"
        return f"http://{host}:{settings.port}"

    async def deploy_api(
        self,
        main_py: str,
        requirements_txt: str,
        dockerfile: str,
        job_id: str,
    ) -> Dict[str, Any]:
        """Register and activate a generated API on this self-hosted backend."""
        try:
            service_name = f"apiui-{job_id[:8]}"
            base_url = self._get_base_url()
            api_url = f"{base_url}/api/{job_id}"
            api_key = str(uuid.uuid4())

            # Persist generated API files locally when available
            files_to_save = {}
            if main_py:
                files_to_save["main.py"] = main_py
            if requirements_txt:
                files_to_save["requirements.txt"] = requirements_txt
            if dockerfile:
                files_to_save["Dockerfile"] = dockerfile
            if files_to_save:
                storage_service.save_generated_api(job_id, files_to_save)

            return {
                "success": True,
                "mode": "self-hosted",
                "api_url": api_url,
                "api_key": api_key,
                "deployment_id": service_name,
                "api_endpoints": {
                    "data": f"{api_url}/data",
                    "schema": f"{api_url}/schema",
                    "code": f"{api_url}/code",
                },
                "note": f"Self-hosted API active at {api_url}",
            }
        except Exception as e:
            return {"success": False, "error": f"Self-hosted deployment failed: {str(e)}"}

    async def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Get the status of a self-hosted deployment."""
        base_url = self._get_base_url()
        return {
            "deployment_id": deployment_id,
            "mode": "self-hosted",
            "status": "running",
            "url": f"{base_url}/api/{deployment_id}",
        }

    async def delete_deployment(self, deployment_id: str) -> bool:
        """Delete a self-hosted deployment."""
        storage_service.delete_generated_api(deployment_id)
        return True
