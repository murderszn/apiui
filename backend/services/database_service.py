from supabase import create_client, Client
from typing import Optional, Dict, Any, List
from core.config import settings

class DatabaseService:
    def __init__(self):
        self.client: Optional[Client] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to Supabase database"""
        try:
            if not settings.supabase_url or not settings.supabase_service_role_key:
                print("❌ Supabase URL or service role key not configured")
                return False

            self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            self._connected = True
            print("✅ Connected to Supabase database")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Supabase database: {str(e)}")
            self._connected = False
            return False

    async def save_api_record(self, api_record: Dict[str, Any]) -> bool:
        """Save an API record to the database"""
        try:
            if not self.client:
                return False

            # Insert or upsert the API record
            response = self.client.table('apis').upsert(api_record).execute()
            return True
        except Exception as e:
            print(f"❌ Failed to save API record: {str(e)}")
            return False

    async def get_user_apis(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all APIs for a user"""
        try:
            if not self.client:
                return []

            response = self.client.table('apis').select('*').eq('user_id', user_id).execute()
            return response.data or []
        except Exception as e:
            print(f"❌ Failed to get user APIs: {str(e)}")
            return []

    async def delete_api_record(self, api_id: str) -> bool:
        """Delete an API record from the database"""
        try:
            if not self.client:
                return False

            # Convert string ID to integer if needed
            try:
                api_id_int = int(api_id)
            except ValueError:
                api_id_int = api_id

            response = self.client.table('apis').delete().eq('id', api_id_int).execute()
            return True
        except Exception as e:
            print(f"❌ Failed to delete API record: {str(e)}")
            return False

db_service = DatabaseService()
