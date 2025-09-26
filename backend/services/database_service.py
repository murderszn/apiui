"""
Database Service for Supabase integration
Handles persistent storage of jobs, APIs, and metadata
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from core.config import settings
from services.supabase_service import supabase_service


class DatabaseService:
    def __init__(self):
        self.connected = False

    async def connect(self):
        """Connect to Supabase database"""
        if settings.supabase_url and settings.supabase_anon_key:
            supabase_service.connect()
            if supabase_service.connected:
                self.connected = True
                print("✅ Connected to Supabase database")
                return

        print("❌ Failed to connect to Supabase database")
        self.connected = False

    async def disconnect(self):
        """Disconnect from database"""
        supabase_service.disconnect()
        self.connected = False

    async def save_api_state(self, api_states: Dict[str, Any]) -> bool:
        """Save API states to Supabase (not implemented - using storage service)"""
        # API states are handled by storage service for now
        return True

    async def load_api_state(self) -> Optional[Dict[str, Any]]:
        """Load API states from Supabase (not implemented - using storage service)"""
        # API states are handled by storage service for now
        return None

    async def list_api_metadata(self) -> List[Dict[str, Any]]:
        """List all API metadata from Supabase"""
        if not self.connected:
            return []

        try:
            # Get current user and their APIs
            user = supabase_service.get_current_user()
            if user:
                return await supabase_service.get_user_apis(user["id"])
            return []
        except Exception as e:
            print(f"❌ Failed to list API metadata: {str(e)}")
            return []

    async def save_api_record(self, api_data: Dict[str, Any]) -> bool:
        """Save API record to Supabase apis table"""
        if not self.connected:
            return False

        return await supabase_service.save_api(api_data)

    async def get_user_apis(self, user_id: str) -> List[Dict[str, Any]]:
        """Get APIs for a specific user from Supabase"""
        if not self.connected:
            return []

        return await supabase_service.get_user_apis(user_id)

    async def update_api_record(self, api_id: str, updates: Dict[str, Any]) -> bool:
        """Update API record in Supabase"""
        if not self.connected:
            return False

        return await supabase_service.update_api(api_id, updates)

    async def delete_api_record(self, api_id: str) -> bool:
        """Delete API record from Supabase"""
        if not self.connected:
            return False

        return await supabase_service.delete_api(api_id)

    async def health_check(self) -> bool:
        """Check database health"""
        if not self.connected:
            return False

        return supabase_service.health_check()


# Global database service instance
db_service = DatabaseService()
