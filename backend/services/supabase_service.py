from supabase import create_client, Client
from typing import Optional, Dict, Any
from core.config import settings

class SupabaseService:
    def __init__(self):
        self.client: Optional[Client] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Connect to Supabase"""
        try:
            if not settings.supabase_url or not settings.supabase_anon_key:
                print("❌ Supabase URL or anon key not configured")
                return False

            self.client = create_client(settings.supabase_url, settings.supabase_anon_key)
            self._connected = True
            print("✅ Connected to Supabase")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Supabase: {str(e)}")
            self._connected = False
            return False

    async def sign_up(self, email: str, password: str) -> Dict[str, Any]:
        """Sign up a new user"""
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password
            })
            return {
                "success": True,
                "user": response.user.model_dump() if response.user else None,
                "session": response.session.model_dump() if response.session else None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in a user"""
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            return {
                "success": True,
                "user": response.user.model_dump() if response.user else None,
                "session": response.session.model_dump() if response.session else None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def sign_out(self) -> Dict[str, Any]:
        """Sign out the current user"""
        try:
            self.client.auth.sign_out()
            return {
                "success": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get the current authenticated user"""
        try:
            user = self.client.auth.get_user()
            return user.user.model_dump() if user.user else None
        except Exception:
            return None

    async def download_file(self, bucket_name: str, file_path: str) -> Optional[bytes]:
        """Download a file from Supabase Storage"""
        try:
            if not self.client:
                return None

            # Remove any leading slashes from file_path
            file_path = file_path.lstrip('/')

            # Get the file from Supabase storage
            response = self.client.storage.from_(bucket_name).download(file_path)

            if response:
                return response
            return None

        except Exception as e:
            print(f"❌ Failed to download file {file_path} from {bucket_name}: {str(e)}")
            return None

    async def upload_file(self, bucket_name: str, file_path: str, file_data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Upload a file to Supabase Storage"""
        try:
            if not self.client:
                return False

            # Remove any leading slashes from file_path
            file_path = file_path.lstrip('/')

            # Upload the file to Supabase storage
            response = self.client.storage.from_(bucket_name).upload(
                file_path,
                file_data,
                {"content-type": content_type}
            )

            return True

        except Exception as e:
            print(f"❌ Failed to upload file {file_path} to {bucket_name}: {str(e)}")
            return False

supabase_service = SupabaseService()
