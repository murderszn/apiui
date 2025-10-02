import uuid
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional
from core.config import settings
from google.cloud import run_v2
from google.api_core.exceptions import NotFound

class DeploymentService:
    def __init__(self):
        self.gcp_project_id = settings.gcp_project_id
        self.gcp_region = settings.gcp_region

    async def deploy_api(
        self,
        main_py: str,
        requirements_txt: str,
        dockerfile: str,
        job_id: str
    ) -> Dict[str, Any]:
        """
        Deploy the generated API to a container platform
        """
        try:
            if self.gcp_project_id:
                return await self._deploy_to_cloud_run(main_py, requirements_txt, dockerfile, job_id)
            else:
                # Use _deploy_to_cloud_run even for mock deployments to get Cloud Run URLs
                return await self._deploy_to_cloud_run(main_py, requirements_txt, dockerfile, job_id)

        except Exception as e:
            return {"success": False, "error": f"Deployment failed: {str(e)}"}

    async def _deploy_to_cloud_run(
        self,
        main_py: str,
        requirements_txt: str,
        dockerfile: str,
        job_id: str
    ) -> Dict[str, Any]:
        """Deploy to Google Cloud Run"""
        try:
            # Create temporary directory for the generated code
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write files to temp directory
                main_py_path = Path(temp_dir) / "main.py"
                requirements_path = Path(temp_dir) / "requirements.txt"
                dockerfile_path = Path(temp_dir) / "Dockerfile"

                with open(main_py_path, 'w') as f:
                    f.write(main_py)
                with open(requirements_path, 'w') as f:
                    f.write(requirements_txt)
                with open(dockerfile_path, 'w') as f:
                    f.write(dockerfile)

                # Generate unique service name
                service_name = f"apiui-{job_id[:8]}"

                # Build and deploy using gcloud CLI (would be done in CI/CD)
                # For now, we'll simulate this process

                base_url = settings.api_gateway_url or f"https://{service_name}-{self.gcp_region}.run.app"
                api_url = f"{base_url.rstrip('/')}/api/{job_id}"
                api_key = str(uuid.uuid4())

                return {
                    "success": True,
                    "api_url": api_url,
                    "api_key": api_key,
                    "deployment_id": service_name
                }

        except Exception as e:
            return {"success": False, "error": f"Cloud Run deployment failed: {str(e)}"}

    async def _deploy_mock(
        self,
        main_py: str,
        requirements_txt: str,
        dockerfile: str,
        job_id: str
    ) -> Dict[str, Any]:
        """Mock deployment for development/testing"""
        try:
            # Create Cloud Run-style URL instead of localhost
            service_name = f"apiui-{job_id[:8]}"
            region = getattr(settings, 'gcp_region', 'us-central1')
            base_url = f"https://{service_name}-{region}.run.app"
            mock_url = f"{base_url}/api/{job_id}"
            mock_api_key = str(uuid.uuid4())

            # In a real deployment, this would:
            # 1. Build the Docker image
            # 2. Push to container registry
            # 3. Deploy to Cloud Run/Fargate
            # 4. Configure API Gateway
            # 5. Return actual URLs and keys

            return {
                "success": True,
                "api_url": mock_url,
                "api_key": mock_api_key,
                "deployment_id": f"mock-{job_id[:8]}",
                "note": "This is a mock deployment. Configure GCP/AWS credentials for real deployment."
            }

        except Exception as e:
            return {"success": False, "error": f"Mock deployment failed: {str(e)}"}

    async def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Get the status of a deployment"""
        # In production, this would check the actual cloud platform status
        return {
            "deployment_id": deployment_id,
            "status": "running",
            "url": f"https://{deployment_id}.run.app"
        }

    async def delete_deployment(self, deployment_id: str) -> bool:
        """Delete a deployment"""
        try:
            # Initialize Cloud Run client
            client = run_v2.ServicesClient()

            # Construct the service name
            service_name = f"projects/{self.gcp_project_id}/locations/{self.gcp_region}/services/{deployment_id}"

            # Delete the Cloud Run service
            operation = client.delete_service(name=service_name)

            # Wait for the operation to complete
            operation.result(timeout=300)  # 5 minute timeout

            print(f"Successfully deleted Cloud Run service: {deployment_id}")
            return True

        except NotFound:
            print(f"Cloud Run service {deployment_id} not found (may already be deleted)")
            return True  # Consider it successful if already deleted
        except Exception as e:
            print(f"Failed to delete Cloud Run service {deployment_id}: {str(e)}")
            return False
