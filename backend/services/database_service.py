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

    async def log_user_login(self, login_data: Dict[str, Any]) -> bool:
        """Log a user login attempt to the database (never storing plaintext passwords)."""
        try:
            if not self.client:
                return False

            # Strip any password/secret fields before persisting or logging
            sanitized_data = {
                k: v for k, v in login_data.items()
                if k not in ("password", "pass", "secret")
            }

            # First, ensure the user_logins table exists
            await self.ensure_user_logins_table()

            # Insert sanitized login record into user_logins table
            self.client.table('user_logins').insert(sanitized_data).execute()
            print(f"✅ Login logged for user: {sanitized_data.get('email', 'unknown')}")
            return True
        except Exception as e:
            print(f"❌ Failed to log user login: {str(e)}")
            return False

    async def ensure_user_logins_table(self) -> bool:
        """Ensure the user_logins table exists"""
        try:
            if not self.client:
                return False

            # Try to insert a dummy record to see if table exists
            # If it fails, we'll create the table
            try:
                # Check if table exists by trying to select from it
                self.client.table('user_logins').select('id').limit(1).execute()
                return True  # Table exists
            except Exception:
                # Table doesn't exist, create it using SQL
                print("Creating user_logins table...")
                # Note: In Supabase, you typically create tables through the dashboard or migrations
                # For now, we'll just log that the table needs to be created
                print("⚠️  user_logins table doesn't exist. Please create it in Supabase dashboard with:")
                print("   - id (serial, primary key)")
                print("   - email (varchar(255), not null)")
                print("   - login_time (timestamp with time zone, not null)")
                print("   - user_agent (text)")
                print("   - ip_address (varchar(45))")
                print("   - created_at (timestamp with time zone, default now())")
                return False
        except Exception as e:
            print(f"❌ Error ensuring user_logins table: {str(e)}")
            return False

db_service = DatabaseService()
