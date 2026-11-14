"""
Storage Service for handling file persistence
Supports Supabase Storage (primary), Google Cloud Storage, and local storage (fallback)
"""

import os
import json
import asyncio
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
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
from core.config import settings, BASE_DIR
from services.supabase_service import supabase_service


def _run_async(coro):
    """Run an async coroutine safely whether or not an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class StorageService:
    def __init__(self):
        self.use_gcs = settings.use_gcs_storage
        self.local_uploads_dir = settings.uploads_dir
        self.local_apis_dir = settings.generated_apis_dir
        self._supabase_list_cache = None
        self._supabase_list_cache_ts = 0.0
        self._persist_lock = threading.Lock()

        # Always ensure local directories exist for self-hosted / fallback mode
        os.makedirs(self.local_uploads_dir, exist_ok=True)
        os.makedirs(self.local_apis_dir, exist_ok=True)

        # Priority: Supabase > GCS > Local
        if supabase_service.connected:
            print(f"✅ Using Supabase Storage (with local fallback: {self.local_uploads_dir})")
        elif self.use_gcs:
            if storage is None:
                raise RuntimeError("Google Cloud Storage requested but google-cloud-storage package is not installed")
            try:
                self.gcs_client = storage.Client(project=settings.gcs_project_id)
                self.bucket = self.gcs_client.bucket(settings.gcs_bucket_name)
                print(f"✅ Using Google Cloud Storage: {settings.gcs_bucket_name}")
            except Exception as e:
                print(f"❌ GCS initialization failed: {e}")
                print("🔄 Falling back to local storage")
                self.use_gcs = False
                print(f"✅ Using local storage: {self.local_uploads_dir}")
        else:
            print(f"✅ Using local storage: {self.local_uploads_dir}")

    def _persistent_file_path(self, data_type: str) -> str:
        """Resolve local persistent JSON path dynamically relative to repo root."""
        return getattr(settings, f"{data_type}_file", str(BASE_DIR / "backend" / f"{data_type}.json"))

    def save_upload_file(self, file_data: bytes, filename: str, job_id: str) -> str:
        """Save uploaded file with persistent storage"""
        file_path = f"uploads/{job_id}_{filename}"

        if supabase_service.connected:
            try:
                result = _run_async(supabase_service.upload_file(
                    "user-uploads",
                    file_path,
                    file_data,
                    self._get_content_type(filename)
                ))
                if result:
                    print(f"📤 Uploaded to Supabase Storage: {file_path}")
                    # Also keep a local copy for fast/offline self-hosted access
                    full_path = os.path.join(self.local_uploads_dir, f"{job_id}_{filename}")
                    with open(full_path, 'wb') as f:
                        f.write(file_data)
                    return file_path
                else:
                    print("❌ Supabase upload failed, falling back to GCS/local")
            except Exception as e:
                print(f"❌ Supabase upload error: {str(e)}, falling back to GCS/local")

        if self.use_gcs:
            blob = self.bucket.blob(file_path)
            blob.upload_from_string(file_data, content_type='application/octet-stream')
            print(f"📤 Uploaded to GCS: {file_path}")
        else:
            os.makedirs(self.local_uploads_dir, exist_ok=True)
            full_path = os.path.join(self.local_uploads_dir, f"{job_id}_{filename}")
            with open(full_path, 'wb') as f:
                f.write(file_data)
            print(f"💾 Saved locally: {full_path}")

        return file_path

    def get_upload_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve uploaded file (checks local disk first for speed/offline resilience, then remote)."""
        try:
            # Check local uploads directory first (instant and works offline)
            local_candidates = [
                os.path.join(self.local_uploads_dir, os.path.basename(file_path)),
                os.path.join(self.local_uploads_dir, file_path),
            ]
            for full_path in local_candidates:
                if os.path.isfile(full_path):
                    with open(full_path, 'rb') as f:
                        return f.read()

            if supabase_service.connected:
                try:
                    result = _run_async(supabase_service.download_file("user-uploads", file_path))
                    if result:
                        return result
                except Exception as e:
                    print(f"⚠️ Supabase download fallback failed for {file_path}: {e}")

            if self.use_gcs:
                blob = self.bucket.blob(file_path)
                return blob.download_as_bytes()
        except (NotFound, FileNotFoundError):
            return None
        return None

    def _get_content_type(self, filename: str) -> str:
        """Get content type based on file extension"""
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.parquet': 'application/parquet',
            '.txt': 'text/plain'
        }
        return content_types.get(ext, 'application/octet-stream')

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

    def get_generated_api_file_bytes(self, api_id: str, filename: str) -> Optional[bytes]:
        """Retrieve a generated API file as raw bytes"""
        try:
            if self.use_gcs:
                blob = self.bucket.blob(f"generated_apis/{api_id}/{filename}")
                if blob.exists():
                    return blob.download_as_bytes()
            else:
                file_path = os.path.join(self.local_apis_dir, api_id, filename)
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        return f.read()
        except Exception as e:
            print(f"❌ Failed to retrieve generated API file {api_id}/{filename}: {str(e)}")
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
        """Save persistent data (jobs, apis, etc.) atomically and thread-safely."""
        try:
            file_path = f"persistent/{data_type}.json"
            with self._persist_lock:
                json_data = json.dumps(dict(data), default=str, indent=2)

                if self.use_gcs:
                    blob = self.bucket.blob(file_path)
                    blob.upload_from_string(json_data, content_type='application/json')
                else:
                    local_file = self._persistent_file_path(data_type)
                    target_dir = os.path.dirname(local_file)
                    os.makedirs(target_dir, exist_ok=True)
                    fd, tmp_path = tempfile.mkstemp(prefix=f".{data_type}_", suffix=".tmp", dir=target_dir)
                    try:
                        with os.fdopen(fd, 'w', encoding='utf-8') as f:
                            f.write(json_data)
                        os.replace(tmp_path, local_file)
                    except Exception:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        raise

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
                local_file = self._persistent_file_path(data_type)
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

    def list_uploaded_files(self) -> List[Dict[str, Any]]:
        """List all uploaded files with metadata (includes local fallback files)."""
        try:
            files = []
            seen_names = set()

            if supabase_service.connected:
                try:
                    import time
                    now = time.monotonic()
                    if self._supabase_list_cache is not None and (now - self._supabase_list_cache_ts) < 5.0:
                        file_list = self._supabase_list_cache
                    else:
                        file_list = _run_async(supabase_service.list_files("user-uploads")) or []
                        self._supabase_list_cache = file_list
                        self._supabase_list_cache_ts = now
                    if file_list:
                        for file_info in file_list:
                            name = os.path.basename(file_info.get('name', ''))
                            if name and name not in seen_names:
                                seen_names.add(name)
                                files.append({
                                    'name': name,
                                    'path': file_info.get('name', ''),
                                    'size': file_info.get('size', 0),
                                    'last_modified': file_info.get('updated_at', datetime.now().isoformat()),
                                    'storage': 'supabase'
                                })
                except Exception as e:
                    print(f"⚠️ Supabase list_files failed, using local uploads: {e}")

            if self.use_gcs:
                blobs = self.bucket.list_blobs(prefix="uploads/")
                for blob in blobs:
                    if blob.name.startswith("uploads/"):
                        filename = os.path.basename(blob.name)
                        if filename and filename not in seen_names:
                            seen_names.add(filename)
                            files.append({
                                'name': filename,
                                'path': blob.name,
                                'size': blob.size or 0,
                                'last_modified': blob.updated.isoformat() if blob.updated else datetime.now().isoformat(),
                                'storage': 'gcs'
                            })

            # Always include local uploads directory files not already listed
            if os.path.exists(self.local_uploads_dir):
                for filename in sorted(os.listdir(self.local_uploads_dir)):
                    if filename.startswith('.'):
                        continue
                    file_path = os.path.join(self.local_uploads_dir, filename)
                    if os.path.isfile(file_path) and filename not in seen_names:
                        seen_names.add(filename)
                        stat = os.stat(file_path)
                        files.append({
                            'name': filename,
                            'path': file_path,
                            'size': stat.st_size,
                            'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'storage': 'local'
                        })

            return files
        except Exception as e:
            print(f"❌ Failed to list uploaded files: {str(e)}")
            return []

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

    def clear_persistent_data(self, data_type: str) -> bool:
        """Remove persisted data for the given type."""
        try:
            if self.use_gcs:
                file_path = f"persistent/{data_type}.json"
                blob = self.bucket.blob(file_path)
                if blob.exists(client=self.gcs_client):
                    blob.delete()
            else:
                local_file = self._persistent_file_path(data_type)
                if os.path.exists(local_file):
                    os.remove(local_file)
            print(f"🧹 Cleared persistent data: {data_type}")
            return True
        except Exception as e:
            print(f"❌ Failed to clear persistent data {data_type}: {str(e)}")
            return False


# Global storage service instance
storage_service = StorageService()
