"""
Storage Service for handling file persistence in Cloud Run
Supports both local storage (for development) and Google Cloud Storage (for production)
"""

import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
try:
    from google.cloud import storage
    from google.api_core.exceptions import NotFound
except ImportError:  # pragma: no cover - optional dependency
    storage = None

    class NotFound(Exception):
        """Fallback NotFound when google cloud libraries are unavailable."""
        pass
from core.config import settings


class StorageService:
    def __init__(self):
        self.use_gcs = settings.use_gcs_storage
        self.local_uploads_dir = settings.uploads_dir
        self.local_apis_dir = settings.generated_apis_dir

        if self.use_gcs:
            if storage is None:
                raise RuntimeError("Google Cloud Storage requested but google-cloud-storage package is not installed")
            self.gcs_client = storage.Client(project=settings.gcs_project_id)
            self.bucket = self.gcs_client.bucket(settings.gcs_bucket_name)
            print(f"✅ Using Google Cloud Storage: {settings.gcs_bucket_name}")
        else:
            # Ensure local directories exist
            os.makedirs(self.local_uploads_dir, exist_ok=True)
            os.makedirs(self.local_apis_dir, exist_ok=True)
            print(f"✅ Using local storage: {self.local_uploads_dir}")

    def save_upload_file(self, file_data: bytes, filename: str, job_id: str) -> str:
        """Save uploaded file with persistent storage"""
        file_path = f"uploads/{job_id}_{filename}"

        if self.use_gcs:
            blob = self.bucket.blob(file_path)
            blob.upload_from_string(file_data, content_type='application/octet-stream')
            print(f"📤 Uploaded to GCS: {file_path}")
        else:
            full_path = os.path.join(self.local_uploads_dir, f"{job_id}_{filename}")
            with open(full_path, 'wb') as f:
                f.write(file_data)
            print(f"💾 Saved locally: {full_path}")

        return file_path

    def get_upload_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve uploaded file"""
        try:
            if self.use_gcs:
                blob = self.bucket.blob(file_path)
                return blob.download_as_bytes()
            else:
                full_path = os.path.join(self.local_uploads_dir, os.path.basename(file_path))
                if os.path.exists(full_path):
                    with open(full_path, 'rb') as f:
                        return f.read()
        except (NotFound, FileNotFoundError):
            return None
        return None

    def save_generated_api(self, api_id: str, files: Dict[str, str]) -> bool:
        """Save generated API files"""
        try:
            if self.use_gcs:
                for filename, content in files.items():
                    blob = self.bucket.blob(f"generated_apis/{api_id}/{filename}")
                    blob.upload_from_string(content, content_type='text/plain')
            else:
                api_dir = os.path.join(self.local_apis_dir, api_id)
                os.makedirs(api_dir, exist_ok=True)

                for filename, content in files.items():
                    file_path = os.path.join(api_dir, filename)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

            print(f"💾 Saved generated API: {api_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to save generated API {api_id}: {str(e)}")
            return False

    def get_generated_api_files(self, api_id: str) -> Optional[Dict[str, str]]:
        """Retrieve generated API files"""
        try:
            files = {}
            if self.use_gcs:
                blobs = self.bucket.list_blobs(prefix=f"generated_apis/{api_id}/")
                for blob in blobs:
                    filename = os.path.basename(blob.name)
                    content = blob.download_as_text()
                    files[filename] = content
            else:
                api_dir = os.path.join(self.local_apis_dir, api_id)
                if os.path.exists(api_dir):
                    for filename in os.listdir(api_dir):
                        file_path = os.path.join(api_dir, filename)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            files[filename] = f.read()

            return files if files else None
        except Exception as e:
            print(f"❌ Failed to retrieve generated API {api_id}: {str(e)}")
            return None

    def list_generated_apis(self) -> List[str]:
        """List all generated API IDs"""
        try:
            if self.use_gcs:
                blobs = self.bucket.list_blobs(prefix="generated_apis/")
                api_ids = set()
                for blob in blobs:
                    parts = blob.name.split('/')
                    if len(parts) >= 3:
                        api_ids.add(parts[1])
                return list(api_ids)
            else:
                if os.path.exists(self.local_apis_dir):
                    return [d for d in os.listdir(self.local_apis_dir)
                           if os.path.isdir(os.path.join(self.local_apis_dir, d))]
                return []
        except Exception as e:
            print(f"❌ Failed to list generated APIs: {str(e)}")
            return []

    def save_persistent_data(self, data_type: str, data: Dict[str, Any]) -> bool:
        """Save persistent data (jobs, apis, etc.)"""
        try:
            file_path = f"persistent/{data_type}.json"
            json_data = json.dumps(data, default=str, indent=2)

            if self.use_gcs:
                blob = self.bucket.blob(file_path)
                blob.upload_from_string(json_data, content_type='application/json')
            else:
                # Save to local file
                local_file = getattr(settings, f"{data_type}_file", f"/Users/jahflyx/apiui/backend/{data_type}.json")
                os.makedirs(os.path.dirname(local_file), exist_ok=True)
                with open(local_file, 'w') as f:
                    f.write(json_data)

            print(f"💾 Saved persistent data: {data_type}")
            return True
        except Exception as e:
            print(f"❌ Failed to save persistent data {data_type}: {str(e)}")
            return False

    def load_persistent_data(self, data_type: str) -> Optional[Dict[str, Any]]:
        """Load persistent data (jobs, apis, etc.)"""
        try:
            if self.use_gcs:
                file_path = f"persistent/{data_type}.json"
                blob = self.bucket.blob(file_path)
                json_data = blob.download_as_text()
            else:
                local_file = getattr(settings, f"{data_type}_file", f"/Users/jahflyx/apiui/backend/{data_type}.json")
                if not os.path.exists(local_file):
                    return None
                with open(local_file, 'r') as f:
                    json_data = f.read()

            return json.loads(json_data)
        except (NotFound, FileNotFoundError):
            return None
        except Exception as e:
            print(f"❌ Failed to load persistent data {data_type}: {str(e)}")
            return None

    def delete_generated_api(self, api_id: str) -> bool:
        """Delete a generated API"""
        try:
            if self.use_gcs:
                blobs = self.bucket.list_blobs(prefix=f"generated_apis/{api_id}/")
                for blob in blobs:
                    blob.delete()
            else:
                api_dir = os.path.join(self.local_apis_dir, api_id)
                if os.path.exists(api_dir):
                    import shutil
                    shutil.rmtree(api_dir)

            print(f"🗑️  Deleted API: {api_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to delete API {api_id}: {str(e)}")
            return False


# Global storage service instance
storage_service = StorageService()
