#!/usr/bin/env python3
"""
Script to check and create PostgreSQL tables for all APIs on Cloud Run
"""
import os
import sys
from pathlib import Path

# Add the backend directory to the path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from core.config import settings
from services.database_service import db_service
import json
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_table_for_api(api_metadata):
    """Create a PostgreSQL table for a specific API"""
    try:
        from core.postgresql_db import engine

        table_name = api_metadata.db_table_name
        schema_def = api_metadata.schema_definition

        logger.info(f"Creating table {table_name} for API {api_metadata.api_id}")

        # Build column definitions
        columns = []

        # Always add record_id as primary key
        columns.append(Column('record_id', Integer, primary_key=True, autoincrement=True))

        # Add columns from schema definition
        for col_name, col_def in schema_def.items():
            col_type = col_def.get('type', 'string')
            nullable = col_def.get('nullable', True)

            if col_type == 'integer':
                columns.append(Column(col_name, Integer, nullable=nullable))
            elif col_type == 'float':
                columns.append(Column(col_name, Float, nullable=nullable))
            elif col_type == 'boolean':
                columns.append(Column(col_name, Boolean, nullable=nullable))
            elif col_type == 'datetime':
                columns.append(Column(col_name, DateTime, nullable=nullable))
            else:  # string or text
                if col_def.get('max_length', 0) > 255:
                    columns.append(Column(col_name, Text, nullable=nullable))
                else:
                    columns.append(Column(col_name, String(255), nullable=nullable))

        # Create the table
        from sqlalchemy import Table, MetaData
        metadata = MetaData()
        table = Table(table_name, metadata, *columns)

        # Create the table
        metadata.create_all(engine, tables=[table])

        logger.info(f"✅ Successfully created table {table_name}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to create table {table_name}: {str(e)}")
        return False

def check_and_create_all_tables():
    """Check all APIs and create missing tables"""
    print("🔌 Connecting to PostgreSQL...")

    if not init_postgresql_db():
        print("❌ Failed to connect to PostgreSQL")
        return False

    session = get_postgresql_session()
    if not session:
        print("❌ Failed to get database session")
        return False

    try:
        # Get database engine for table inspection
        from core.postgresql_db import engine
        inspector = inspect(engine)

        # Get all existing table names
        existing_tables = set(inspector.get_table_names())
        print(f"📋 Found {len(existing_tables)} existing tables in database")

        # Get all APIs from metadata table
        apis = session.query(APIMetadata).all()
        print(f"📊 Found {len(apis)} APIs in metadata table")

        if len(apis) == 0:
            print("⚠️  No APIs found in metadata table. Migration may be needed.")
            return False

        # Check each API
        tables_created = 0
        tables_already_exist = 0

        for api in apis:
            table_name = api.db_table_name

            if table_name in existing_tables:
                print(f"✅ Table {table_name} already exists for API {api.api_id} ({api.name})")
                tables_already_exist += 1
            else:
                print(f"🔄 Creating table {table_name} for API {api.api_id} ({api.name})")
                if create_table_for_api(api):
                    tables_created += 1
                else:
                    print(f"❌ Failed to create table {table_name}")

        print("""
📈 Summary:""")
        print(f"   • APIs in metadata: {len(apis)}")
        print(f"   • Tables already existed: {tables_already_exist}")
        print(f"   • Tables created: {tables_created}")
        print(f"   • Total tables: {tables_already_exist + tables_created}")

        if tables_created == 0 and len(apis) > 0:
            print("🎉 All APIs already have tables!")
        elif tables_created > 0:
            print(f"✅ Successfully created {tables_created} missing tables!")

        return True

    except Exception as e:
        print(f"❌ Error during table check/creation: {str(e)}")
        return False
    finally:
        session.close()

async def create_user_logins_table():
    """Ensure the user_logins table exists"""
    try:
        # Connect to Supabase
        await db_service.connect()

        if not db_service.connected:
            logger.error("❌ Cannot check user_logins table - Supabase not connected")
            return False

        logger.info("Checking user_logins table...")

        # Use the database service method to ensure table exists
        success = await db_service.ensure_user_logins_table()

        if success:
            logger.info("✅ user_logins table exists and is ready")
        else:
            logger.info("⚠️  user_logins table needs to be created manually in Supabase dashboard")

        return success

    except Exception as e:
        logger.error(f"❌ Failed to check user_logins table: {str(e)}")
        return False

def migrate_legacy_apis_if_needed():
    """Check if we need to run migration for legacy APIs"""
    print("\n🔄 Checking for legacy APIs that need migration...")

    if not init_postgresql_db():
        print("❌ Cannot check for legacy APIs - PostgreSQL not connected")
        return

    session = get_postgresql_session()
    if not session:
        return

    try:
        # Check if there are any data_ tables that aren't in api_metadata
        from core.postgresql_db import engine
        inspector = inspect(engine)

        table_names = inspector.get_table_names()
        data_tables = [name for name in table_names if name.startswith('data_')]

        # Get api_ids from metadata
        api_metadata = session.query(APIMetadata).all()
        metadata_api_ids = {api.api_id for api in api_metadata}

        unmigrated_tables = []
        for table_name in data_tables:
            api_id = table_name.replace('data_', '')
            if api_id not in metadata_api_ids:
                unmigrated_tables.append((table_name, api_id))

        if unmigrated_tables:
            print(f"⚠️  Found {len(unmigrated_tables)} unmigrated tables:")
            for table_name, api_id in unmigrated_tables:
                print(f"   • {table_name} (API ID: {api_id})")
            print("\n💡 Consider running migration script to populate api_metadata table")
        else:
            print("✅ All data tables are properly migrated")

    except Exception as e:
        print(f"❌ Error checking for legacy APIs: {str(e)}")
    finally:
        session.close()

if __name__ == "__main__":
    print("🔍 Checking and creating PostgreSQL tables for all APIs...")
    print("=" * 60)

    success = check_and_create_all_tables()

    if success:
        migrate_legacy_apis_if_needed()

        # Create user_logins table if it doesn't exist
        print("\n🔐 Checking user_logins table...")
        try:
            import asyncio
            success = asyncio.run(create_user_logins_table())
            if success:
                print("✅ User logins table is ready!")
            else:
                print("⚠️  User logins table needs manual creation in Supabase dashboard")
        except Exception as e:
            print(f"❌ Error checking user logins table: {e}")

    print("\n" + "=" * 60)
    if success:
        print("✅ Table check and creation completed!")
    else:
        print("❌ Table check and creation failed!")
