from enum import Enum
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from core.database import get_db

class JobStatus(str, Enum):
    ANALYZING = "analyzing"
    GENERATING_CODE = "generating_code"
    BUILDING = "building"
    DEPLOYED = "deployed"
    FAILED = "failed"

class Job(BaseModel):
    id: str
    filename: str
    status: JobStatus
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    @classmethod
    async def get_by_id(cls, job_id: str) -> Optional['Job']:
        """Get job by ID from database"""
        db = await get_db()
        job_data = await db.jobs.find_one({"id": job_id})
        if job_data:
            return cls(**job_data)
        return None

    async def save(self):
        """Save job to database"""
        db = await get_db()
        job_data = self.dict()
        if self.status in [JobStatus.DEPLOYED, JobStatus.FAILED]:
            job_data["completed_at"] = datetime.utcnow()
        await db.jobs.replace_one({"id": self.id}, job_data, upsert=True)
