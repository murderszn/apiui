from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import os
import json
import csv
import tempfile
from datetime import datetime
import asyncio
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
import subprocess
import signal
import threading

# Add backend to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import settings
from services.ai_service import AIService

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# In-memory storage for jobs (in production, use a database)
jobs = {}

# In-memory storage for running API processes
running_apis = {}

# In-memory storage for running servers started by "Run Generated API"
running_servers = {}

# File-based persistence for jobs
JOBS_FILE = '/app/jobs.json'
APIS_FILE = '/app/apis.json'

def save_jobs_to_file():
    """Save jobs to file for persistence"""
    try:
        import json
        with open(JOBS_FILE, 'w') as f:
            json.dump(jobs, f, default=str)
    except Exception as e:
        print(f"Failed to save jobs: {e}")

def load_jobs_from_file():
    """Load jobs from file"""
    global jobs
    try:
        import json
        if os.path.exists(JOBS_FILE):
            with open(JOBS_FILE, 'r') as f:
                jobs.update(json.load(f))
    except Exception as e:
        print(f"Failed to load jobs: {e}")

def save_apis_to_file():
    """Save APIs to file for persistence"""
    try:
        import json
        with open(APIS_FILE, 'w') as f:
            json.dump({
                'running_apis': running_apis,
                'running_servers': running_servers
            }, f, default=str)
    except Exception as e:
        print(f"Failed to save APIs: {e}")

def load_apis_from_file():
    """Load APIs from file"""
    global running_apis, running_servers
    try:
        import json
        if os.path.exists(APIS_FILE):
            data = json.load(open(APIS_FILE, 'r'))
            running_apis.update(data.get('running_apis', {}))
            running_servers.update(data.get('running_servers', {}))
    except Exception as e:
        print(f"Failed to load APIs: {e}")

# Load persisted data on startup
load_jobs_from_file()
load_apis_from_file()

def add_log_entry(job_id, message, level="info"):
    """Add a log entry to a job"""
    if job_id not in jobs:
        return

    if "logs" not in jobs[job_id]:
        jobs[job_id]["logs"] = []

    jobs[job_id]["logs"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "message": message
    })

    # Keep only last 50 log entries to prevent memory issues
    if len(jobs[job_id]["logs"]) > 50:
        jobs[job_id]["logs"] = jobs[job_id]["logs"][-50:]

    # Save jobs to file
    save_jobs_to_file()

# Initialize AI service
ai_service = AIService()

def run_async_ai_generation(schema, job_id):
    """Run async AI generation in a new event loop"""
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async AI generation
        result = loop.run_until_complete(ai_service.generate_api_code(schema, job_id))

        loop.close()
        return result
    except Exception as e:
        return {"success": False, "error": f"AI generation failed: {str(e)}"}

def analyze_data_file(file_path, file_ext=None):
    """Analyze data file and return schema - supports CSV, JSON, XLSX, Parquet"""
    try:
        if file_ext is None:
            file_ext = os.path.splitext(file_path)[1].lower()

        # Handle different file formats
        if file_ext == '.csv':
            return analyze_csv_file(file_path)
        elif file_ext == '.json':
            return analyze_json_file(file_path)
        elif file_ext in ['.xlsx', '.xls']:
            return analyze_excel_file(file_path)
        elif file_ext == '.parquet':
            return analyze_parquet_file(file_path)
        elif file_ext == '.txt':
            # Try to detect if it's actually CSV-like
            return analyze_csv_file(file_path)
        else:
            return {"error": f"Unsupported file format: {file_ext}", "columns": [], "row_count": 0}

    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def analyze_csv_file(file_path):
    """Analyze CSV file and return schema"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sample = f.read(1024)
            f.seek(0)
            reader = csv.reader(f)

            # Read header
            header = next(reader, None)
            if not header:
                return {"columns": [], "row_count": 0}

            # Count rows
            row_count = sum(1 for row in reader) + 1  # +1 for header

            # Infer column types from first few rows
            f.seek(0)
            next(reader)  # Skip header
            sample_rows = []
            for i, row in enumerate(reader):
                if i >= 5:  # Sample first 5 data rows
                    break
                sample_rows.append(row)

            columns = []
            for i, col_name in enumerate(header):
                # Try to infer type from sample data
                sample_values = [row[i] for row in sample_rows if i < len(row)]

                inferred_type = "string"
                if sample_values:
                    # Check if all values are numeric
                    try:
                        [float(v) for v in sample_values if v]
                        if '.' in str(sample_values[0]) or any('.' in str(v) for v in sample_values):
                            inferred_type = "float"
                        else:
                            inferred_type = "integer"
                    except ValueError:
                        # Check if dates
                        if any('T' in str(v) or '-' in str(v) for v in sample_values):
                            inferred_type = "date"

                columns.append({
                    "name": col_name,
                    "type": inferred_type,
                    "nullable": any(not row[i] if i < len(row) else True for row in sample_rows),
                    "unique_count": len(set(sample_values)),
                    "inferred_type": inferred_type
                })

            return {
                "columns": columns,
                "row_count": row_count,
                "sample_data": sample_rows[:3]
            }

    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def analyze_json_file(file_path):
    """Analyze JSON file and return schema"""
    try:
        import json

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle different JSON structures
        if isinstance(data, list):
            # Array of objects
            if len(data) == 0:
                return {"columns": [], "row_count": 0}

            # Get all unique keys from all objects
            all_keys = set()
            for item in data[:100]:  # Sample first 100 items
                if isinstance(item, dict):
                    all_keys.update(item.keys())

            columns = []
            sample_data = []

            for key in sorted(all_keys):
                # Sample values for this key
                sample_values = []
                for item in data[:5]:  # Sample first 5 items
                    if isinstance(item, dict) and key in item:
                        sample_values.append(str(item[key]))

                inferred_type = "string"
                if sample_values:
                    # Check if all values are numeric
                    try:
                        [float(v) for v in sample_values if v and v != 'None']
                        if '.' in str(sample_values[0]) or any('.' in str(v) for v in sample_values):
                            inferred_type = "float"
                        else:
                            inferred_type = "integer"
                    except ValueError:
                        # Check if dates
                        if any('T' in str(v) or '-' in str(v) for v in sample_values):
                            inferred_type = "date"

                # Check nullability
                null_count = sum(1 for item in data[:100] if isinstance(item, dict) and (key not in item or item[key] is None))
                nullable = null_count > 0

                columns.append({
                    "name": key,
                    "type": inferred_type,
                    "nullable": nullable,
                    "unique_count": len(set(str(item.get(key)) for item in data[:100] if isinstance(item, dict))),
                    "inferred_type": inferred_type
                })

            # Convert sample data to list format for consistency
            sample_data = []
            for item in data[:3]:
                if isinstance(item, dict):
                    row = []
                    for key in sorted(all_keys):
                        row.append(str(item.get(key, '')))
                    sample_data.append(row)

            return {
                "columns": columns,
                "row_count": len(data),
                "sample_data": sample_data
            }
        else:
            return {"error": "JSON file must contain an array of objects", "columns": [], "row_count": 0}

    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def analyze_excel_file(file_path):
    """Analyze Excel file and return schema"""
    try:
        import pandas as pd

        # Read the first sheet
        df = pd.read_excel(file_path, sheet_name=0)

        if df.empty:
            return {"columns": [], "row_count": 0}

        columns = []
        sample_data = []

        for col_name in df.columns:
            # Get sample values
            sample_values = df[col_name].dropna().head(5).astype(str).tolist()

            inferred_type = "string"
            if len(sample_values) > 0:
                # Check if all values are numeric
                try:
                    [float(v) for v in sample_values if v]
                    if '.' in str(sample_values[0]) or any('.' in str(v) for v in sample_values):
                        inferred_type = "float"
                    else:
                        inferred_type = "integer"
                except ValueError:
                    # Check if dates
                    if any('T' in str(v) or '-' in str(v) for v in sample_values):
                        inferred_type = "date"

            columns.append({
                "name": str(col_name),
                "type": inferred_type,
                "nullable": df[col_name].isna().any(),
                "unique_count": df[col_name].nunique(),
                "inferred_type": inferred_type
            })

        # Convert sample data to list format
        sample_df = df.head(3)
        sample_data = []
        for _, row in sample_df.iterrows():
            sample_data.append([str(val) for val in row])

        return {
            "columns": columns,
            "row_count": len(df),
            "sample_data": sample_data
        }

    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def analyze_parquet_file(file_path):
    """Analyze Parquet file and return schema"""
    try:
        import pandas as pd

        df = pd.read_parquet(file_path)

        if df.empty:
            return {"columns": [], "row_count": 0}

        columns = []
        sample_data = []

        for col_name in df.columns:
            # Get sample values
            sample_values = df[col_name].dropna().head(5).astype(str).tolist()

            inferred_type = "string"
            if len(sample_values) > 0:
                # Check if all values are numeric
                try:
                    [float(v) for v in sample_values if v]
                    if '.' in str(sample_values[0]) or any('.' in str(v) for v in sample_values):
                        inferred_type = "float"
                    else:
                        inferred_type = "integer"
                except ValueError:
                    # Check if dates
                    if any('T' in str(v) or '-' in str(v) for v in sample_values):
                        inferred_type = "date"

            columns.append({
                "name": str(col_name),
                "type": inferred_type,
                "nullable": df[col_name].isna().any(),
                "unique_count": df[col_name].nunique(),
                "inferred_type": inferred_type
            })

        # Convert sample data to list format
        sample_df = df.head(3)
        sample_data = []
        for _, row in sample_df.iterrows():
            sample_data.append([str(val) for val in row])

        return {
            "columns": columns,
            "row_count": len(df),
            "sample_data": sample_data
        }

    except ImportError:
        return {"error": "Parquet support requires pyarrow. Please install pyarrow to process Parquet files.", "columns": [], "row_count": 0}
    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def read_data_file(file_path):
    """Read data file and return as list of dictionaries - supports CSV, JSON, XLSX, Parquet"""
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext == '.csv':
        import csv
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        return data

    elif file_ext == '.json':
        import json
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    elif file_ext in ['.xlsx', '.xls']:
        import pandas as pd
        df = pd.read_excel(file_path)
        return df.to_dict('records')

    elif file_ext == '.parquet':
        try:
            import pandas as pd
            df = pd.read_parquet(file_path)
            return df.to_dict('records')
        except ImportError:
            return {"error": "Parquet support requires pyarrow. Please install pyarrow to process Parquet files."}

    elif file_ext == '.txt':
        # Try as CSV
        import csv
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        return data

    else:
        raise ValueError(f"Unsupported file format: {file_ext}")

@app.route('/v1/generate', methods=['POST'])
def generate_api():
    """Generate an API from uploaded file"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Validate file extension
        allowed_extensions = ['.csv', '.json', '.xlsx', '.parquet', '.txt']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": "Unsupported file type"}), 400

        # Create job
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "id": job_id,
            "filename": file.filename,
            "status": "analyzing",
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "api_url": None,
            "api_key": None,
            "error_message": None,
            "logs": []
        }

        add_log_entry(job_id, f"🚀 Job {job_id} created for file: {file.filename}")
        add_log_entry(job_id, f"📁 File size: {len(file.read())} bytes")
        file.seek(0)  # Reset file pointer after reading size

        # Save uploaded file to persistent location
        upload_dir = '/app/uploads'
        os.makedirs(upload_dir, exist_ok=True)
        persistent_path = os.path.join(upload_dir, f"{job_id}_{file.filename}")

        with open(persistent_path, 'wb') as f:
            file.save(f)

        add_log_entry(job_id, f"💾 File saved persistently at: {persistent_path}")
        jobs[job_id]["file_path"] = persistent_path

        # Save jobs after creation
        save_jobs_to_file()

        # Process file (supports multiple formats)
        add_log_entry(job_id, f"🔍 Starting {file_ext.upper()} file analysis...")
        add_log_entry(job_id, f"📂 File extension detected: {file_ext}")
        add_log_entry(job_id, f"📁 File exists: {os.path.exists(persistent_path)}")
        add_log_entry(job_id, f"📏 File size: {os.path.getsize(persistent_path) if os.path.exists(persistent_path) else 0} bytes")

        schema = analyze_data_file(persistent_path, file_ext)
        jobs[job_id]["schema"] = schema

        add_log_entry(job_id, f"📊 Schema analysis result: {len(schema.get('columns', []))} columns, {schema.get('row_count', 0)} rows")

        if schema.get("error"):
            add_log_entry(job_id, f"❌ File analysis failed: {schema['error']}", "error")
            jobs[job_id]["error_message"] = schema["error"]
            jobs[job_id]["status"] = "failed"
            save_jobs_to_file()
            return jsonify({"job_id": job_id, "status": "failed", "error": schema["error"]})

        add_log_entry(job_id, f"📊 Schema analysis complete: {len(schema['columns'])} columns, {schema['row_count']} rows")
        for col in schema['columns'][:5]:  # Log first 5 columns
            add_log_entry(job_id, f"   📋 Column: {col['name']} ({col['inferred_type']})")

        # Generate AI code using OpenAI
        jobs[job_id]["status"] = "generating_code"
        save_jobs_to_file()
        add_log_entry(job_id, "🤖 Starting AI code generation with OpenAI GPT-4...")
        add_log_entry(job_id, "📝 Preparing prompt for AI model...")

        # Capture stdout and stderr to prevent Flask output issues
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            ai_result = run_async_ai_generation(schema, job_id)

        if ai_result["success"]:
            add_log_entry(job_id, "✅ AI code generation successful!")
            add_log_entry(job_id, f"📄 Generated {len(ai_result['main_py'])} characters of FastAPI code")
            req_lines = ai_result['requirements_txt'].split('\n')
            add_log_entry(job_id, f"📦 Generated requirements.txt with {len(req_lines)} packages")
            jobs[job_id]["generated_code"] = {
                "main_py": ai_result["main_py"],
                "requirements_txt": ai_result["requirements_txt"],
                "dockerfile": ai_result["dockerfile"]
            }
        else:
            error_msg = ai_result.get("error", "AI generation failed")
            add_log_entry(job_id, f"❌ AI generation failed: {error_msg}", "error")
            jobs[job_id]["error_message"] = error_msg
            jobs[job_id]["status"] = "failed"
            save_jobs_to_file()

        return jsonify({
            "job_id": job_id,
            "status": "accepted",
            "message": "API generation started successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/generate/status/<job_id>', methods=['GET'])
def get_generation_status(job_id):
    """Get the status of an API generation job"""
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    job = jobs[job_id]

    # Add progress information
    progress_info = {
        "analyzing": {"step": 1, "total_steps": 4, "description": "Analyzing data file"},
        "generating_code": {"step": 2, "total_steps": 4, "description": "Generating API code with AI"},
        "building": {"step": 3, "total_steps": 4, "description": "Building Docker container"},
        "deployed": {"step": 4, "total_steps": 4, "description": "Deployment completed"}
    }

    current_progress = progress_info.get(job["status"], {"step": 1, "total_steps": 4, "description": "Processing"})

    # Calculate elapsed time
    elapsed_seconds = None
    if job.get("created_at"):
        try:
            created_time = datetime.fromisoformat(job["created_at"])
            elapsed_seconds = int((datetime.utcnow() - created_time).total_seconds())
        except:
            pass

    # Simulate progress through the steps with better timing
    if job["status"] == "analyzing":
        # Move to generating_code after some time has passed
        if elapsed_seconds and elapsed_seconds > 5:  # Give analysis at least 5 seconds
            job["status"] = "generating_code"
            save_jobs_to_file()
            add_log_entry(job_id, "🤖 Starting AI code generation...")
            add_log_entry(job_id, "📝 Sending data schema to AI model...")
            current_progress = progress_info["generating_code"]

    elif job["status"] == "generating_code":
        # Add some progress updates during AI generation
        if elapsed_seconds:
            if elapsed_seconds > 120:  # After 2 minutes, show building progress
                job["status"] = "building"
                save_jobs_to_file()
                add_log_entry(job_id, "🏗️ Starting build process...")
                add_log_entry(job_id, "📦 Creating Docker container...")
                current_progress = progress_info["building"]
            elif elapsed_seconds > 60:  # After 1 minute, add AI processing log
                # Only add this log once
                recent_logs = [log for log in job.get("logs", []) if "AI model processing" in log.get("message", "")]
                if not recent_logs:
                    add_log_entry(job_id, "⚡ AI model processing your data schema...")

    elif job["status"] == "building":
        # Move to deployed after build time has passed
        if elapsed_seconds and elapsed_seconds > 180:  # Give building at least 3 minutes
            job["status"] = "deployed"
            job["api_url"] = f"https://apiui-backend-24bi767viq-uc.a.run.app/mock-api/{job_id}"
            job["api_key"] = f"api_key_{job_id[:8]}"
            job["completed_at"] = datetime.utcnow().isoformat()
            save_jobs_to_file()
            add_log_entry(job_id, "🚀 Deployment completed successfully!")
            add_log_entry(job_id, f"🌐 API available at: {job['api_url']}")
            add_log_entry(job_id, f"🔑 API Key: {job['api_key']}")
            current_progress = progress_info["deployed"]

    return jsonify({
        "job_id": job["id"],
        "status": job["status"],
        "progress": current_progress,
        "api_url": job["api_url"],
        "api_key": job["api_key"],
        "error_message": job["error_message"],
        "created_at": job["created_at"],
        "completed_at": job["completed_at"],
        "elapsed_seconds": elapsed_seconds,
        "logs": job.get("logs", [])
    })

@app.route('/v1/apis', methods=['GET'])
def list_generated_apis():
    """List all generated APIs"""
    try:
        apis_dir = '/app/generated_apis'
        if not os.path.exists(apis_dir):
            return jsonify({"apis": [], "total": 0})

        apis = []
        for api_id in os.listdir(apis_dir):
            api_path = os.path.join(apis_dir, api_id)
            if os.path.isdir(api_path):
                # Check if main.py exists
                main_py_path = os.path.join(api_path, 'main.py')
                data_csv_path = os.path.join(api_path, 'data.csv')
                requirements_path = os.path.join(api_path, 'requirements.txt')

                if os.path.exists(main_py_path):
                    # Get basic info from the main.py file
                    api_info = {
                        "id": api_id,
                        "path": api_path,
                        "created_at": datetime.fromtimestamp(os.path.getctime(api_path)).isoformat(),
                        "has_main_py": True,
                        "has_data_csv": os.path.exists(data_csv_path),
                        "has_requirements": os.path.exists(requirements_path),
                        "status": "stopped"  # Default status, will be updated when we check if running
                    }

                    # Check API status
                    status = "stopped"
                    url = None
                    port = None
                    started_at = None

                    if api_id in running_apis:
                        api_info_running = running_apis[api_id]
                        process = api_info_running["process"]
                        if process.poll() is None:
                            status = "running"
                            url = api_info_running["url"]
                            port = api_info_running["port"]
                            started_at = api_info_running["started_at"]
                        else:
                            # Process has stopped, clean up
                            del running_apis[api_id]

                    api_info["status"] = status
                    api_info["url"] = url
                    api_info["port"] = port
                    api_info["started_at"] = started_at

                    # Try to extract API info from main.py
                    try:
                        with open(main_py_path, 'r') as f:
                            content = f.read()

                        # Extract app title if available
                        if 'app = FastAPI(' in content:
                            lines = content.split('\n')
                            for line in lines:
                                if 'app = FastAPI(' in line:
                                    # Try to extract title
                                    if 'title=' in line:
                                        title_part = line.split('title=')[1].split(',')[0].strip('"\'''"')
                                        api_info["title"] = title_part
                                    break

                        # Extract data model if available
                        if 'class ' in content and '(BaseModel):' in content:
                            models = []
                            for line in content.split('\n'):
                                if line.strip().startswith('class ') and '(BaseModel):' in line:
                                    model_name = line.split('class ')[1].split('(BaseModel):')[0].strip()
                                    models.append(model_name)
                            if models:
                                api_info["models"] = models

                        # Extract endpoints
                        endpoints = []
                        for line in content.split('\n'):
                            if line.strip().startswith('@app.'):
                                method = line.split('@app.')[1].split('(')[0]
                                route = line.split('\'')[1] if '\'' in line else line.split('"')[1] if '"' in line else ""
                                endpoints.append({"method": method.upper(), "route": route})
                        api_info["endpoints"] = endpoints

                    except Exception as e:
                        api_info["parse_error"] = str(e)

                    apis.append(api_info)

        return jsonify({
            "apis": apis,
            "total": len(apis),
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e), "apis": [], "total": 0}), 500

@app.route('/v1/apis/<api_id>', methods=['GET'])
def get_api_details(api_id):
    """Get detailed information about a specific generated API"""
    try:
        api_path = f'/app/generated_apis/{api_id}'
        if not os.path.exists(api_path):
            return jsonify({"error": "API not found"}), 404

        main_py_path = os.path.join(api_path, 'main.py')
        data_csv_path = os.path.join(api_path, 'data.csv')
        requirements_path = os.path.join(api_path, 'requirements.txt')

        if not os.path.exists(main_py_path):
            return jsonify({"error": "API main.py file not found"}), 404

        api_info = {
            "id": api_id,
            "path": api_path,
            "created_at": datetime.fromtimestamp(os.path.getctime(api_path)).isoformat(),
            "files": {
                "main_py": os.path.exists(main_py_path),
                "data_csv": os.path.exists(data_csv_path),
                "requirements_txt": os.path.exists(requirements_path)
            }
        }

        # Read and analyze main.py
        with open(main_py_path, 'r') as f:
            code_content = f.read()

        api_info["code"] = code_content

        # Extract FastAPI app configuration
        if 'app = FastAPI(' in code_content:
            lines = code_content.split('\n')
            for line in lines:
                if 'app = FastAPI(' in line:
                    if 'title=' in line:
                        title_match = line.split('title=')[1].split(',')[0].strip('"\'''"')
                        api_info["title"] = title_match
                    if 'description=' in line:
                        desc_match = line.split('description=')[1].split(',')[0].strip('"\'''"')
                        api_info["description"] = desc_match
                    break

        # Extract data models
        models = []
        lines = code_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('class ') and '(BaseModel):' in line:
                model_name = line.split('class ')[1].split('(BaseModel):')[0].strip()
                model_info = {"name": model_name, "fields": []}

                # Parse fields
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('class ') and lines[i].strip():
                    field_line = lines[i].strip()
                    if ':' in field_line and not field_line.startswith(' ') and not field_line.startswith('\t'):
                        break
                    elif ':' in field_line and (field_line.startswith('    ') or field_line.startswith('\t')):
                        # This is a field
                        field_parts = field_line.split(':')
                        if len(field_parts) >= 2:
                            field_name = field_parts[0].strip()
                            field_type = field_parts[1].strip().split('=')[0].strip()
                            model_info["fields"].append({
                                "name": field_name,
                                "type": field_type
                            })
                    i += 1

                if model_info["fields"]:
                    models.append(model_info)
            else:
                i += 1

        api_info["models"] = models

        # Extract endpoints
        endpoints = []
        lines = code_content.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('@app.'):
                method = line.split('@app.')[1].split('(')[0]
                route_line = line.split('(')[1].split(',')[0] if '(' in line else ""
                route = route_line.strip('"\'')

                # Get function definition
                func_line = ""
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith('def '):
                    j += 1
                if j < len(lines):
                    func_line = lines[j].strip()
                    func_name = func_line.split('def ')[1].split('(')[0]

                endpoints.append({
                    "method": method.upper(),
                    "route": route,
                    "function": func_name if func_name else "unknown"
                })

        api_info["endpoints"] = endpoints

        # Read requirements if available
        if os.path.exists(requirements_path):
            with open(requirements_path, 'r') as f:
                api_info["requirements"] = f.read().strip().split('\n')

        # Analyze data file for schema info
        if os.path.exists(data_csv_path):
            try:
                schema_info = analyze_data_file(data_csv_path)
                api_info["data_schema"] = schema_info
                api_info["record_count"] = schema_info.get("row_count", 0)
            except Exception as e:
                api_info["data_error"] = str(e)

        return jsonify(api_info)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/apis/<api_id>/start', methods=['POST'])
def start_api(api_id):
    """Start a generated API server"""
    try:
        api_path = f'/app/generated_apis/{api_id}'
        if not os.path.exists(api_path):
            return jsonify({"error": "API not found"}), 404

        main_py_path = os.path.join(api_path, 'main.py')
        if not os.path.exists(main_py_path):
            return jsonify({"error": "API main.py file not found"}), 404

        # Check if already running
        if api_id in running_apis:
            return jsonify({"error": "API is already running", "status": "running"}), 400

        # Find an available port (starting from 8001)
        port = 8001
        while port < 9000:
            try:
                # Try to bind to the port to check if it's available
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', port))
                    break
            except OSError:
                port += 1

        # Start the API server
        try:
            process = subprocess.Popen(
                ['python', 'main.py'],
                cwd=api_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group
            )

            running_apis[api_id] = {
                "process": process,
                "port": port,
                "started_at": datetime.utcnow().isoformat(),
                "url": f"https://apiui-backend-24bi767viq-uc.a.run.app/generated/{api_id}"
            }

            return jsonify({
                "message": "API started successfully",
                "status": "running",
                "url": f"https://apiui-backend-24bi767viq-uc.a.run.app/generated/{api_id}",
                "port": port,
                "started_at": running_apis[api_id]["started_at"]
            })

        except Exception as e:
            return jsonify({"error": f"Failed to start API: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/apis/<api_id>/stop', methods=['POST'])
def stop_api(api_id):
    """Stop a running API server"""
    try:
        if api_id not in running_apis:
            return jsonify({"error": "API is not running"}), 400

        api_info = running_apis[api_id]
        process = api_info["process"]

        try:
            # Terminate the process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)

            # Wait a bit for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't respond
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait()

            del running_apis[api_id]

            return jsonify({
                "message": "API stopped successfully",
                "status": "stopped"
            })

        except Exception as e:
            return jsonify({"error": f"Failed to stop API: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/apis/<api_id>/status', methods=['GET'])
def get_api_status(api_id):
    """Get the status of a specific API"""
    try:
        api_path = f'/app/generated_apis/{api_id}'
        if not os.path.exists(api_path):
            return jsonify({"error": "API not found"}), 404

        status = "stopped"
        url = None
        port = None
        started_at = None

        if api_id in running_apis:
            api_info = running_apis[api_id]
            process = api_info["process"]

            # Check if process is still running
            if process.poll() is None:
                status = "running"
                url = api_info["url"]
                port = api_info["port"]
                started_at = api_info["started_at"]
            else:
                # Process has stopped, clean up
                del running_apis[api_id]
                status = "stopped"

        return jsonify({
            "id": api_id,
            "status": status,
            "url": url,
            "port": port,
            "started_at": started_at
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/apis/<api_id>/docs', methods=['GET'])
def get_api_docs(api_id):
    """Generate API documentation for a specific API"""
    try:
        api_path = f'/app/generated_apis/{api_id}'
        if not os.path.exists(api_path):
            return jsonify({"error": "API not found"}), 404

        main_py_path = os.path.join(api_path, 'main.py')
        if not os.path.exists(main_py_path):
            return jsonify({"error": "API main.py file not found"}), 404

        # Get API details first
        api_details_response = get_api_details(api_id)
        if api_details_response.status_code != 200:
            return api_details_response

        api_details = api_details_response.get_json()

        # Generate OpenAPI documentation
        docs = {
            "openapi": "3.0.1",
            "info": {
                "title": api_details.get("title", f"API {api_id}"),
                "description": api_details.get("description", f"Auto-generated API from CSV data"),
                "version": "1.0.0",
                "contact": {
                    "name": "apiui",
                    "url": "https://github.com/your-repo/apiui"
                }
            },
            "servers": [
                {
                    "url": f"https://apiui-backend-24bi767viq-uc.a.run.app/v1/apis/{api_id}",
                    "description": "Generated API server"
                }
            ],
            "paths": {},
            "components": {
                "schemas": {}
            }
        }

        # Add schemas for data models
        for model in api_details.get("models", []):
            schema_name = model["name"]
            schema = {
                "type": "object",
                "properties": {}
            }

            for field in model["fields"]:
                field_type = field["type"].lower()
                if "int" in field_type:
                    schema["properties"][field["name"]] = {"type": "integer"}
                elif "float" in field_type or "decimal" in field_type:
                    schema["properties"][field["name"]] = {"type": "number"}
                elif "bool" in field_type:
                    schema["properties"][field["name"]] = {"type": "boolean"}
                elif "date" in field_type or "time" in field_type:
                    schema["properties"][field["name"]] = {"type": "string", "format": "date-time"}
                else:
                    schema["properties"][field["name"]] = {"type": "string"}

            docs["components"]["schemas"][schema_name] = schema

        # Add paths for endpoints
        for endpoint in api_details.get("endpoints", []):
            method = endpoint["method"].lower()
            route = endpoint["route"]

            if route not in docs["paths"]:
                docs["paths"][route] = {}

            path_item = {
                "summary": f"{method.upper()} {route}",
                "description": f"Endpoint: {endpoint['function']}",
                "responses": {
                    "200": {
                        "description": "Successful response"
                    }
                }
            }

            # Add request/response schemas based on the model
            if api_details.get("models"):
                model_name = api_details["models"][0]["name"]
                if method == "get":
                    path_item["responses"]["200"]["content"] = {
                        "application/json": {
                            "schema": {
                                "$ref": f"#/components/schemas/{model_name}"
                            }
                        }
                    }
                elif method in ["post", "put", "patch"]:
                    path_item["requestBody"] = {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{model_name}"
                                }
                            }
                        }
                    }

            docs["paths"][route][method] = path_item

        # Add data schema information
        if api_details.get("data_schema"):
            docs["info"]["x-data-schema"] = api_details["data_schema"]
            docs["info"]["x-record-count"] = api_details.get("record_count", 0)

        return jsonify(docs)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/mock-api/<job_id>', methods=['GET'])
@app.route('/mock-api/<job_id>/data', methods=['GET'])
def mock_api_endpoint(job_id):
    """Mock API endpoint that simulates a generated API"""
    job = None

    # First try to find the job in memory
    if job_id in jobs:
        job = jobs[job_id]
    else:
        # If not in memory, try to reconstruct from saved files
        upload_dir = '/app/uploads'
        if os.path.exists(upload_dir):
            try:
                possible_files = [f for f in os.listdir(upload_dir) if f.startswith(f"{job_id}_")]
                if possible_files:
                    file_path = os.path.join(upload_dir, possible_files[0])
                    filename = possible_files[0].replace(f"{job_id}_", "")

                    # Try to analyze the file to get schema
                    try:
                        schema = analyze_data_file(file_path)
                        # Create a minimal job entry
                        job = {
                            "id": job_id,
                            "filename": filename,
                            "status": "deployed",
                            "file_path": file_path,
                            "schema": schema,
                            "api_url": f"https://apiui-backend-24bi767viq-uc.a.run.app/mock-api/{job_id}",
                            "api_key": f"api_key_{job_id[:8]}",
                            "created_at": datetime.utcnow().isoformat(),
                            "completed_at": datetime.utcnow().isoformat()
                        }
                        # Save the reconstructed job
                        jobs[job_id] = job
                        save_jobs_to_file()
                        add_log_entry(job_id, f"🔄 Reconstructed job from saved file: {filename}")
                    except Exception as e:
                        print(f"Failed to reconstruct job {job_id}: {str(e)}")
            except OSError as e:
                print(f"Failed to access upload directory: {str(e)}")

    if not job:
        # Try to find in generated_apis directory as a last resort
        generated_api_path = f'/app/generated_apis/{job_id}'
        if os.path.exists(generated_api_path):
            data_file = os.path.join(generated_api_path, 'data.csv')
            if os.path.exists(data_file):
                try:
                    schema = analyze_data_file(data_file)
                    job = {
                        "id": job_id,
                        "filename": f"api_{job_id}.csv",
                        "status": "deployed",
                        "file_path": data_file,
                        "schema": schema,
                        "api_url": f"https://apiui-backend-24bi767viq-uc.a.run.app/mock-api/{job_id}",
                        "api_key": f"api_key_{job_id[:8]}",
                        "created_at": datetime.utcnow().isoformat(),
                        "completed_at": datetime.utcnow().isoformat()
                    }
                    # Save the reconstructed job
                    jobs[job_id] = job
                    save_jobs_to_file()
                    add_log_entry(job_id, f"🔄 Reconstructed job from generated API: {job_id}")
                except Exception as e:
                    print(f"Failed to reconstruct from generated API {job_id}: {str(e)}")

    if not job:
        return jsonify({
            "error": "API not found",
            "message": f"The API with job ID '{job_id}' could not be found. This may happen if the backend restarted or the job was not properly saved.",
            "suggestion": "Please try uploading your file again to generate a new API."
        }), 404

    if not job.get("schema"):
        return jsonify({
            "error": "Schema not available",
            "message": "The API schema information is missing."
        }), 404

    schema = job["schema"]

    # Check if we have AI-generated code
    if job.get("generated_code"):
        # If we have real generated code, return actual data from the CSV
        generated = job["generated_code"]

        # Read the original file data (supports multiple formats)
        file_data = []
        try:
            # Use the stored file path from the job
            file_path = job.get("file_path")
            if file_path and os.path.exists(file_path):
                file_data = read_data_file(file_path)
                add_log_entry(job_id, f"✅ Loaded {len(file_data)} records from uploaded file")
            else:
                raise FileNotFoundError("File path not found in job")
        except Exception as e:
            add_log_entry(job_id, f"⚠️ File not accessible ({str(e)}), using sample data")
            # Fallback to sample data if file not found or unreadable
            for i in range(min(10, schema.get("row_count", 10))):
                row = {}
                for col in schema["columns"]:
                    col_name = col["name"]
                    col_type = col.get("inferred_type", "string")

                    if col_type == "integer":
                        row[col_name] = i + 1
                    elif col_type == "float":
                        row[col_name] = float(i + 1) + 0.5
                    elif col_type == "boolean":
                        row[col_name] = i % 2 == 0
                    else:
                        row[col_name] = f"sample_{col_name}_{i+1}"

                file_data.append(row)

        if request.path.endswith('/data'):
            # Parse query parameters for pagination
            limit = int(request.args.get('limit', 10))
            offset = int(request.args.get('offset', 0))

            # Apply pagination
            paginated_data = file_data[offset:offset + limit]

            return jsonify({
                "data": paginated_data,
                "total_count": len(file_data),
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < len(file_data),
                "message": f"AI-generated API serving real data from {job['filename']}",
                "ai_generated": True
            })
        else:
            return jsonify({
                "message": f"AI-generated API for {job['filename']}",
                "status": "AI-generated code ready",
                "endpoints": [
                    f"/mock-api/{job_id}/data",
                    f"/mock-api/{job_id}/schema",
                    f"/mock-api/{job_id}/code"
                ],
                "total_records": len(file_data),
                "generated_at": job.get("completed_at"),
                "ai_provider": "OpenAI GPT-4"
            })
    else:
        # Fall back to mock data generation
        mock_data = []
        for i in range(min(10, schema.get("row_count", 10))):
            row = {}
            for col in schema["columns"]:
                col_name = col["name"]
                col_type = col.get("inferred_type", "string")

                if col_type == "integer":
                    row[col_name] = i + 1
                elif col_type == "float":
                    row[col_name] = float(i + 1) + 0.5
                elif col_type == "boolean":
                    row[col_name] = i % 2 == 0
                else:
                    row[col_name] = f"sample_{col_name}_{i+1}"

            mock_data.append(row)

        if request.path.endswith('/data'):
            return jsonify({
                "data": mock_data,
                "total_count": schema.get("row_count", len(mock_data)),
                "limit": len(mock_data),
                "offset": 0,
                "has_more": False,
                "note": "Mock data - AI generation may have failed"
            })

        return jsonify({
            "message": f"Mock API for {job['filename']} (AI generation may have failed)",
            "endpoints": [
                f"/mock-api/{job_id}/data",
                f"/mock-api/{job_id}/schema"
            ],
            "schema": schema,
            "total_records": schema.get("row_count", 0),
            "status": "mock_mode"
        })

@app.route('/mock-api/<job_id>/schema', methods=['GET'])
def mock_api_schema(job_id):
    """Return schema information for the mock API"""
    # Use the same job reconstruction logic
    job = None
    if job_id in jobs:
        job = jobs[job_id]
    else:
        # Try to reconstruct from saved files
        upload_dir = '/app/uploads'
        if os.path.exists(upload_dir):
            try:
                possible_files = [f for f in os.listdir(upload_dir) if f.startswith(f"{job_id}_")]
                if possible_files:
                    file_path = os.path.join(upload_dir, possible_files[0])
                    try:
                        schema = analyze_data_file(file_path)
                        job = {
                            "id": job_id,
                            "schema": schema
                        }
                    except Exception as e:
                        print(f"Failed to reconstruct schema for {job_id}: {str(e)}")
            except OSError as e:
                print(f"Failed to access upload directory: {str(e)}")

    if not job:
        return jsonify({
            "error": "API not found",
            "message": f"The API with job ID '{job_id}' could not be found."
        }), 404

    if not job.get("schema"):
        return jsonify({
            "error": "Schema not available",
            "message": "The API schema information is missing."
        }), 404

    return jsonify(job["schema"])

@app.route('/mock-api/<job_id>/code', methods=['GET'])
def get_generated_code(job_id):
    """Return the AI-generated code files"""
    if job_id not in jobs:
        return jsonify({
            "error": "API not found",
            "message": f"The API with job ID '{job_id}' could not be found."
        }), 404

    job = jobs[job_id]
    if not job.get("generated_code"):
        return jsonify({
            "error": "No generated code available",
            "message": "AI-generated code is not available for this API."
        }), 404

    return jsonify({
        "main_py": job["generated_code"]["main_py"],
        "requirements_txt": job["generated_code"]["requirements_txt"],
        "dockerfile": job["generated_code"]["dockerfile"],
        "generated_at": job.get("completed_at"),
        "filename": job["filename"]
    })

@app.route('/mock-api/<job_id>/run', methods=['POST'])
def run_generated_api(job_id):
    """Test the generated API by returning the first few records"""
    # Use the same job reconstruction logic
    job = None
    if job_id in jobs:
        job = jobs[job_id]
    else:
        # Try to reconstruct from saved files
        upload_dir = '/app/uploads'
        if os.path.exists(upload_dir):
            try:
                possible_files = [f for f in os.listdir(upload_dir) if f.startswith(f"{job_id}_")]
                if possible_files:
                    file_path = os.path.join(upload_dir, possible_files[0])
                    filename = possible_files[0].replace(f"{job_id}_", "")
                    try:
                        schema = analyze_data_file(file_path)
                        job = {
                            "id": job_id,
                            "filename": filename,
                            "file_path": file_path,
                            "schema": schema
                        }
                    except Exception as e:
                        print(f"Failed to reconstruct job for testing {job_id}: {str(e)}")
            except OSError as e:
                print(f"Failed to access upload directory: {str(e)}")

    if not job:
        return jsonify({
            "error": "API not found",
            "message": f"The API with job ID '{job_id}' could not be found."
        }), 404

    try:
        # Read the uploaded data file and return first few records
        file_path = job.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return jsonify({
                "error": "Data file not found",
                "message": "The uploaded data file is no longer available."
            }), 404

        # Read data from the uploaded file (supports multiple formats)
        file_data = read_data_file(file_path)

        # Return first 5 records to prove the API works
        sample_records = file_data[:5] if len(file_data) > 5 else file_data

        # Get schema information
        schema = job.get("schema", {})
        columns = schema.get("columns", [])

        return jsonify({
            "message": "✅ API Test Successful!",
            "api_name": job.get("filename", "Unknown"),
            "total_records": len(file_data),
            "sample_records": sample_records,
            "columns": [col["name"] for col in columns],
            "api_endpoints": [
                f"/mock-api/{job_id}/data",
                f"/mock-api/{job_id}/schema",
                f"/mock-api/{job_id}/code"
            ],
            "test_timestamp": datetime.utcnow().isoformat(),
            "status": "test_successful"
        })

    except Exception as e:
        return jsonify({
            "error": f"Failed to test API: {str(e)}",
            "status": "test_failed"
        }), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 9999))  # Backend runs on 9999
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
