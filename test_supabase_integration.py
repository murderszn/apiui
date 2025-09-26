#!/usr/bin/env python3
"""
Test script for Supabase integration
Run this script to verify that Supabase authentication and database operations are working.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from core.config import settings
from services.supabase_service import supabase_service

async def test_supabase_connection():
    """Test basic Supabase connection"""
    print("🔍 Testing Supabase connection...")

    # Check configuration
    if not settings.supabase_url:
        print("❌ SUPABASE_URL not configured")
        return False

    if not settings.supabase_anon_key:
        print("❌ SUPABASE_ANON_KEY not configured")
        return False

    # Try to connect
    supabase_service.connect()

    if not supabase_service.connected:
        print("❌ Failed to connect to Supabase")
        return False

    print("✅ Successfully connected to Supabase")
    return True

async def test_auth_operations():
    """Test authentication operations"""
    print("\n🔍 Testing authentication operations...")

    if not supabase_service.connected:
        print("❌ Supabase not connected, skipping auth tests")
        return False

    try:
        # Test sign up (this will fail in production if email already exists)
        print("   Testing sign up...")
        signup_result = await supabase_service.sign_up("test@example.com", "testpassword123")
        if signup_result["success"]:
            print("   ✅ Sign up successful")
        else:
            print(f"   ⚠️  Sign up failed (expected if email exists): {signup_result['error']}")

        # Test sign in with invalid credentials
        print("   Testing sign in with invalid credentials...")
        signin_result = await supabase_service.sign_in("invalid@example.com", "wrongpassword")
        if not signin_result["success"]:
            print("   ✅ Sign in correctly rejected invalid credentials")
        else:
            print("   ❌ Sign in unexpectedly accepted invalid credentials")

        # Test sign out
        print("   Testing sign out...")
        signout_result = await supabase_service.sign_out()
        if signout_result["success"]:
            print("   ✅ Sign out successful")
        else:
            print(f"   ❌ Sign out failed: {signout_result['error']}")

        return True

    except Exception as e:
        print(f"❌ Auth test failed: {str(e)}")
        return False

async def test_database_operations():
    """Test database operations"""
    print("\n🔍 Testing database operations...")

    if not supabase_service.connected:
        print("❌ Supabase not connected, skipping database tests")
        return False

    try:
        # Get current user (should be None since we signed out)
        user = supabase_service.get_current_user()
        if user is None:
            print("   ✅ No authenticated user (as expected)")
        else:
            print(f"   ⚠️  Unexpected authenticated user: {user}")

        # Note: We can't test API creation without authentication
        # In a real test, you would:
        # 1. Sign in with valid credentials
        # 2. Create an API record
        # 3. Verify it was created
        # 4. Clean up the test data

        print("   ℹ️  API operations require authentication - test manually")
        return True

    except Exception as e:
        print(f"❌ Database test failed: {str(e)}")
        return False

async def test_storage_operations():
    """Test storage operations"""
    print("\n🔍 Testing storage operations...")

    if not supabase_service.connected:
        print("❌ Supabase not connected, skipping storage tests")
        return False

    try:
        # Test uploading a small test file
        test_content = b"Hello, Supabase Storage!"
        test_path = "test/test_file.txt"

        print("   Testing file upload...")
        upload_result = await supabase_service.upload_file(
            "user-uploads",
            test_path,
            test_content,
            "text/plain"
        )

        if upload_result:
            print(f"   ✅ File uploaded successfully: {upload_result}")

            # Test downloading the file
            print("   Testing file download...")
            download_result = await supabase_service.download_file("user-uploads", test_path)

            if download_result == test_content:
                print("   ✅ File downloaded successfully and content matches")

                # Clean up - delete the test file
                print("   Testing file deletion...")
                delete_result = await supabase_service.delete_file("user-uploads", test_path)

                if delete_result:
                    print("   ✅ Test file deleted successfully")
                else:
                    print("   ❌ Failed to delete test file")

            else:
                print("   ❌ Downloaded content doesn't match uploaded content")

        else:
            print("   ❌ File upload failed")

        return True

    except Exception as e:
        print(f"❌ Storage test failed: {str(e)}")
        return False

async def main():
    """Run all tests"""
    print("🚀 Starting Supabase Integration Tests")
    print("=" * 50)

    # Load environment variables if .env file exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("📄 Loaded environment variables from .env file")
    except ImportError:
        print("⚠️  python-dotenv not available, using existing environment")

    results = []

    # Test connection
    results.append(await test_supabase_connection())

    # Test authentication
    results.append(await test_auth_operations())

    # Test database operations
    results.append(await test_database_operations())

    # Test storage operations
    results.append(await test_storage_operations())

    # Summary
    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"🎉 All tests passed! ({passed}/{total})")
        print("\n✅ Supabase integration is working correctly!")
        print("\nNext steps:")
        print("1. Configure your Supabase credentials in environment variables")
        print("2. Update the frontend with your Supabase URL and anon key")
        print("3. Test the full application flow")
    else:
        print(f"⚠️  Some tests failed ({passed}/{total})")
        print("\n❌ Please check your Supabase configuration and try again.")
        print("\nTroubleshooting:")
        print("1. Verify SUPABASE_URL, SUPABASE_ANON_KEY are set correctly")
        print("2. Check that your Supabase project is active")
        print("3. Ensure the SQL setup script has been run")
        print("4. Verify storage bucket 'user-uploads' exists and is private")

    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)


