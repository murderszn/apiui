#!/usr/bin/env python3
"""
Test script to run a local CRUD-enabled API for testing the data editor.
This API includes CORS support and full CRUD operations.
"""

import asyncio
from services.ai_service import AIService
import tempfile
import os
import subprocess
import sys

async def create_test_api():
    ai_service = AIService()
    schema = {
        'columns': [
            {'name': 'id', 'inferred_type': 'integer', 'nullable': False},
            {'name': 'name', 'inferred_type': 'string', 'nullable': False},
            {'name': 'email', 'inferred_type': 'string', 'nullable': True},
            {'name': 'age', 'inferred_type': 'integer', 'nullable': True},
            {'name': 'active', 'inferred_type': 'boolean', 'nullable': False}
        ],
        'row_count': 10
    }

    result = await ai_service._generate_mock_code(schema, 'test-crud')

    # Create test directory
    test_dir = '/tmp/apiui-test-crud'
    os.makedirs(test_dir, exist_ok=True)

    # Write the generated files
    with open(os.path.join(test_dir, 'main.py'), 'w') as f:
        f.write(result['main_py'])

    with open(os.path.join(test_dir, 'requirements.txt'), 'w') as f:
        f.write(result['requirements_txt'])

    # Create sample CSV data
    with open(os.path.join(test_dir, 'data.csv'), 'w') as f:
        f.write('id,name,email,age,active\n')
        f.write('1,John Doe,john@example.com,30,true\n')
        f.write('2,Jane Smith,jane@example.com,25,false\n')
        f.write('3,Bob Johnson,bob@example.com,35,true\n')
        f.write('4,Alice Brown,alice@example.com,28,true\n')
        f.write('5,Charlie Wilson,charlie@example.com,42,false\n')

    print(f"✅ Created test CRUD API in: {test_dir}")
    print("📁 Files created:")
    print("  - main.py (FastAPI app with CORS and full CRUD)")
    print("  - requirements.txt (dependencies)")
    print("  - data.csv (sample data)")
    print()
    print("🚀 To test the API locally:")
    print(f"cd {test_dir}")
    print("pip install -r requirements.txt")
    print("python main.py")
    print()
    print("📖 Then visit:")
    print("  - API Documentation: http://localhost:8000/docs")
    print("  - Test Data Editor: Open http://localhost:8080/app.html and create a new API")
    print("    (or modify the data-editor.html to point to http://localhost:8000)")
    print()
    print("🔧 Available endpoints:")
    print("  GET  /data          - List all data")
    print("  POST /data          - Create new record")
    print("  GET  /data/{id}     - Get single record")
    print("  PUT  /data/{id}     - Update entire record")
    print("  PATCH /data/{id}    - Partially update record")
    print("  DELETE /data/{id}   - Delete record")
    print("  GET  /schema        - Get data schema")

    return test_dir

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--run':
        # Run the test API
        test_dir = '/tmp/apiui-test-crud'
        if os.path.exists(test_dir):
            print(f"Starting test API from {test_dir}...")
            os.chdir(test_dir)
            subprocess.run([sys.executable, 'main.py'])
        else:
            print("Test API not found. Run without --run first to create it.")
    else:
        # Create the test API
        asyncio.run(create_test_api())

if __name__ == '__main__':
    main()
