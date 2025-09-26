"""
Supabase Service for authentication, database, and storage operations
Handles user management, API metadata storage, and file uploads
"""

from typing import Optional, Dict, Any, List
import uuid
from datetime import datetime

try:
    from supabase import create_client, Client
    from supabase.lib.client_options import ClientOptions
except ImportError:
    create_client = None
    Client = None
    ClientOptions = None

from core.config import settings


class SupabaseService:
    def __init__(self):
        self.client: Optional[Client] = None
        self.admin_client: Optional[Client] = None
        self.connected = False

    def connect(self):
        """Connect to Supabase"""
        if create_client is None:
            print("ℹ️ supabase library not available; Supabase features disabled.")
            self.connected = False
            return

        try:
            # Client for user operations (uses anon key)
            if settings.supabase_url and settings.supabase_anon_key:
                self.client = create_client(
                    settings.supabase_url,
                    settings.supabase_anon_key
                )

            # Admin client for server-side operations (uses service role key)
            if settings.supabase_url and settings.supabase_service_role_key:
                self.admin_client = create_client(
                    settings.supabase_url,
                    settings.supabase_service_role_key
                )

            if self.client or self.admin_client:
                # Test the connection with a health check
                if self.health_check():
                    self.connected = True
                    print("✅ Connected to Supabase")
                else:
                    self.connected = False
                    print("❌ Supabase connection test failed")
            else:
                print("❌ Supabase configuration incomplete")
                self.connected = False

        except Exception as e:
            print(f"❌ Failed to connect to Supabase: {str(e)}")
            self.connected = False

    def disconnect(self):
        """Disconnect from Supabase"""
        # Supabase client doesn't need explicit disconnection
        self.client = None
        self.admin_client = None
        self.connected = False

    # Authentication Methods
    async def sign_up(self, email: str, password: str) -> Dict[str, Any]:
        """Sign up a new user"""
        if not self.client:
            return {"success": False, "error": "Supabase client not available"}

        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password
            })
            return {"success": True, "user": response.user, "session": response.session}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in a user"""
        if not self.client:
            return {"success": False, "error": "Supabase client not available"}

        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            return {"success": True, "user": response.user, "session": response.session}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def sign_out(self) -> Dict[str, Any]:
        """Sign out the current user"""
        if not self.client:
            return {"success": False, "error": "Supabase client not available"}

        try:
            self.client.auth.sign_out()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get the current authenticated user"""
        if not self.client:
            return None

        try:
            user = self.client.auth.get_user()
            return user.user if user else None
        except:
            return None

    # Database Methods - APIs Table
    async def save_api(self, api_data: Dict[str, Any]) -> bool:
        """Save API metadata to the apis table"""
        if not self.client:
            return False

        try:
            # Ensure user_id is set from current user
            user = self.get_current_user()
            if user:
                api_data["user_id"] = user["id"]

            response = self.client.table("apis").insert(api_data).execute()
            print(f"💾 Saved API to Supabase: {api_data.get('api_name', 'Unknown')}")
            return True
        except Exception as e:
            print(f"❌ Failed to save API: {str(e)}")
            return False

    async def get_user_apis(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all APIs for a specific user"""
        if not self.client:
            return []

        try:
            response = self.client.table("apis").select("*").eq("user_id", user_id).execute()
            return response.data
        except Exception as e:
            print(f"❌ Failed to get user APIs: {str(e)}")
            return []

    async def update_api(self, api_id: str, updates: Dict[str, Any]) -> bool:
        """Update an API record"""
        if not self.client:
            return False

        try:
            response = self.client.table("apis").update(updates).eq("id", api_id).execute()
            return True
        except Exception as e:
            print(f"❌ Failed to update API {api_id}: {str(e)}")
            return False

    async def delete_api(self, api_id: str) -> bool:
        """Delete an API record"""
        if not self.client:
            return False

        try:
            response = self.client.table("apis").delete().eq("id", api_id).execute()
            return True
        except Exception as e:
            print(f"❌ Failed to delete API {api_id}: {str(e)}")
            return False

    # Storage Methods
    async def upload_file(self, bucket_name: str, file_path: str, file_data: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
        """Upload a file to Supabase Storage"""
        if not self.client:
            return None

        try:
            # Upload file to storage
            response = self.client.storage.from_(bucket_name).upload(
                file_path,
                file_data,
                {"content-type": content_type}
            )

            if response.status_code == 200:
                # Get public URL
                public_url = self.client.storage.from_(bucket_name).get_public_url(file_path)
                print(f"📁 File uploaded to Supabase Storage: {file_path}")
                return public_url
            else:
                print(f"❌ Failed to upload file: {response}")
                return None

        except Exception as e:
            print(f"❌ Failed to upload file: {str(e)}")
            return None

    async def download_file(self, bucket_name: str, file_path: str) -> Optional[bytes]:
        """Download a file from Supabase Storage"""
        if not self.client:
            return None

        try:
            response = self.client.storage.from_(bucket_name).download(file_path)
            return response
        except Exception as e:
            print(f"❌ Failed to download file: {str(e)}")
            return None

    async def delete_file(self, bucket_name: str, file_path: str) -> bool:
        """Delete a file from Supabase Storage"""
        if not self.client:
            return False

        try:
            response = self.client.storage.from_(bucket_name).remove([file_path])
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Failed to delete file: {str(e)}")
            return False

    # Admin Methods (using service role)
    async def admin_get_all_apis(self) -> List[Dict[str, Any]]:
        """Admin method to get all APIs (bypasses RLS)"""
        if not self.admin_client:
            return []

        try:
            response = self.admin_client.table("apis").select("*").execute()
            return response.data
        except Exception as e:
            print(f"❌ Failed to get all APIs: {str(e)}")
            return []

    def health_check(self) -> bool:
        """Check Supabase health"""
        try:
            # Simple health check - try to get current user (will fail if not configured properly)
            if self.client:
                self.client.auth.get_user()
            return True
        except:
            return False


# Global Supabase service instance
supabase_service = SupabaseService()
