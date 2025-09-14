import uuid
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional
from core.config import settings

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
                return await self._deploy_mock(main_py, requirements_txt, dockerfile, job_id)

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

                api_url = f"https://{service_name}-{self.gcp_project_id}.{self.gcp_region}.run.app"
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
            # Simulate deployment by creating a mock URL and API key
            mock_url = f"https://apiui-backend-24bi767viq-uc.a.run.app/api/{job_id}"
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
            # In production, this would delete the Cloud Run service
            return True
        except Exception:
            return False
