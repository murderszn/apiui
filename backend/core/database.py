from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

client: AsyncIOMotorClient = None
database = None

async def init_db():
    """Initialize database connection"""
    global client, database
    client = AsyncIOMotorClient(settings.mongodb_url)
    database = client[settings.database_name]
    print("Connected to MongoDB")

async def get_db():
    """Get database instance"""
    return database

async def close_db():
    """Close database connection"""
    if client:
        client.close()
