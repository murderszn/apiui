"""
Database Service for MongoDB integration
Handles persistent storage of jobs, APIs, and metadata
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
except ImportError:  # pragma: no cover - optional dependency
    AsyncIOMotorClient = None
    AsyncIOMotorDatabase = None
from core.config import settings


class DatabaseService:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        self.connected = False

    async def connect(self):
        """Connect to MongoDB"""
        if AsyncIOMotorClient is None:
            print("ℹ️ motor library not available; MongoDB features disabled.")
            self.connected = False
            return

        try:
            self.client = AsyncIOMotorClient(settings.mongodb_url)
            self.database = self.client[settings.database_name]
            # Test connection
            await self.client.admin.command('ping')
            self.connected = True
            print(f"✅ Connected to MongoDB: {settings.database_name}")
        except Exception as e:
            print(f"❌ Failed to connect to MongoDB: {str(e)}")
            self.connected = False

    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            self.connected = False

    async def save_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Save job data to database"""
        if not self.connected:
            return False

        try:
            # Convert datetime objects to ISO strings for JSON serialization
            job_data_copy = self._serialize_for_mongo(job_data)

            await self.database.jobs.update_one(
                {"_id": job_id},
                {"$set": job_data_copy},
                upsert=True
            )
            print(f"💾 Saved job to MongoDB: {job_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to save job {job_id}: {str(e)}")
            return False

    async def load_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job data from database"""
        if not self.connected:
            return None

        try:
            job_data = await self.database.jobs.find_one({"_id": job_id})
            if job_data:
                # Remove MongoDB _id field and return
                job_data.pop('_id', None)
            return job_data
        except Exception as e:
            print(f"❌ Failed to load job {job_id}: {str(e)}")
            return None

    async def load_all_jobs(self) -> Dict[str, Any]:
        """Load all jobs from database"""
        if not self.connected:
            return {}

        try:
            jobs = {}
            async for job in self.database.jobs.find():
                job_id = job.pop('_id')
                jobs[job_id] = job
            return jobs
        except Exception as e:
            print(f"❌ Failed to load all jobs: {str(e)}")
            return {}

    async def save_api_state(self, api_states: Dict[str, Any]) -> bool:
        """Save API states to database"""
        if not self.connected:
            return False

        try:
            api_states_copy = self._serialize_for_mongo(api_states)

            await self.database.api_states.update_one(
                {"_id": "current_state"},
                {"$set": {
                    "running_apis": api_states_copy.get("running_apis", {}),
                    "running_servers": api_states_copy.get("running_servers", {}),
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
            print("💾 Saved API states to MongoDB")
            return True
        except Exception as e:
            print(f"❌ Failed to save API states: {str(e)}")
            return False

    async def load_api_state(self) -> Optional[Dict[str, Any]]:
        """Load API states from database"""
        if not self.connected:
            return None

        try:
            state = await self.database.api_states.find_one({"_id": "current_state"})
            if state:
                state.pop('_id', None)
                state.pop('updated_at', None)
            return state
        except Exception as e:
            print(f"❌ Failed to load API states: {str(e)}")
            return None

    async def save_api_metadata(self, api_id: str, metadata: Dict[str, Any]) -> bool:
        """Save API metadata to database"""
        if not self.connected:
            return False

        try:
            metadata_copy = self._serialize_for_mongo(metadata)

            await self.database.api_metadata.update_one(
                {"_id": api_id},
                {"$set": metadata_copy},
                upsert=True
            )
            print(f"💾 Saved API metadata: {api_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to save API metadata {api_id}: {str(e)}")
            return False

    async def load_api_metadata(self, api_id: str) -> Optional[Dict[str, Any]]:
        """Load API metadata from database"""
        if not self.connected:
            return None

        try:
            metadata = await self.database.api_metadata.find_one({"_id": api_id})
            if metadata:
                metadata.pop('_id', None)
            return metadata
        except Exception as e:
            print(f"❌ Failed to load API metadata {api_id}: {str(e)}")
            return None

    async def list_api_metadata(self) -> List[Dict[str, Any]]:
        """List all API metadata"""
        if not self.connected:
            return []

        try:
            apis = []
            async for api in self.database.api_metadata.find():
                api_id = api.pop('_id')
                api['id'] = api_id
                apis.append(api)
            return apis
        except Exception as e:
            print(f"❌ Failed to list API metadata: {str(e)}")
            return []

    def _serialize_for_mongo(self, data: Any) -> Any:
        """Convert data to MongoDB-compatible format"""
        if isinstance(data, dict):
            return {k: self._serialize_for_mongo(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._serialize_for_mongo(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data

    async def health_check(self) -> bool:
        """Check database health"""
        if not self.connected:
            return False

        try:
            await self.client.admin.command('ping')
            return True
        except:
            return False


# Global database service instance
db_service = DatabaseService()
