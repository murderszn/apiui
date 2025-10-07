from flask import Flask, request, jsonify, redirect, session, make_response
from flask_cors import CORS
import uuid
import os
import json
import csv
from datetime import datetime, timedelta
import asyncio
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
import subprocess
import signal
import threading
import secrets
from urllib.parse import urlencode, urljoin
from typing import Optional
from collections import defaultdict
import time

import httpx

# SocketIO imports (commented out for now)
# from flask_socketio import SocketIO

# Add backend to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import settings
from services.supabase_service import supabase_service

# Initialize Supabase connection BEFORE any other service imports
# This ensures storage service can detect the connection
print("🔌 Connecting to Supabase...")
supabase_service.connect()
if supabase_service.connected:
    print("✅ Supabase connected successfully")
else:
    print("❌ Supabase connection failed")

from services.ai_service import AIService
from services.storage_service import storage_service
from services.database_service import db_service
from services.deployment_service import DeploymentService
from services.socket_service import socket_service

app = Flask(__name__)
app.secret_key = settings.secret_key
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
cookie_secure = any(
    url and url.startswith("https://")
    for url in (settings.github_redirect_uri, settings.google_redirect_uri)
)
app.config.setdefault("SESSION_COOKIE_SECURE", cookie_secure)
CORS(app, supports_credentials=True)  # Enable CORS for all routes with credentials

# Initialize SocketIO (commented out for testing)
# socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
socketio = None

# Metrics collection system
api_metrics = defaultdict(lambda: {
    'requests': [],
    'response_times': [],
    'errors': [],
    'last_updated': datetime.utcnow()
})

def record_api_request(job_id, method, status_code, response_time):
    """Record an API request for metrics"""
    now = datetime.utcnow()
    metrics = api_metrics[job_id]

    # Keep only last 24 hours of data
    cutoff = now - timedelta(hours=24)
    metrics['requests'] = [r for r in metrics['requests'] if r['timestamp'] > cutoff]
    metrics['response_times'] = [rt for rt in metrics['response_times'] if rt['timestamp'] > cutoff]
    metrics['errors'] = [e for e in metrics['errors'] if e['timestamp'] > cutoff]

    # Record request
    metrics['requests'].append({
        'timestamp': now,
        'method': method,
        'status_code': status_code
    })

    # Record response time
    metrics['response_times'].append({
        'timestamp': now,
        'response_time': response_time
    })

    # Record error if status >= 400
    if status_code >= 400:
        metrics['errors'].append({
            'timestamp': now,
            'status_code': status_code,
            'method': method
        })

    metrics['last_updated'] = now

@app.before_request
def track_api_metrics():
    """Middleware to track API requests for metrics"""
    # Only track API endpoints, not admin/health endpoints
    if request.path.startswith('/api/') or request.path.startswith('/mock-api/'):
        request.start_time = time.time()

@app.after_request
def record_metrics(response):
    """Record metrics after API requests"""
    if hasattr(request, 'start_time') and (request.path.startswith('/api/') or request.path.startswith('/mock-api/')):
        response_time = (time.time() - request.start_time) * 1000  # Convert to milliseconds

        # Extract job_id from path
        path_parts = request.path.strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[0] in ['api', 'mock-api']:
            job_id = path_parts[1]
            record_api_request(job_id, request.method, response.status_code, response_time)

    return response

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API = "https://api.github.com/user"
GITHUB_EMAILS_API = "https://api.github.com/user/emails"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def is_github_oauth_configured() -> bool:
    return bool(settings.github_client_id and settings.github_client_secret and settings.github_redirect_uri)


def is_google_oauth_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)


def set_authenticated_session(provider: str, user_info: dict, access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> None:
    session['auth_provider'] = provider
    session['auth_user'] = user_info
    if access_token:
        session['auth_access_token'] = access_token
    else:
        session.pop('auth_access_token', None)

    if refresh_token:
        session['auth_refresh_token'] = refresh_token
    else:
        session.pop('auth_refresh_token', None)

    if provider == 'github':
        session['github_user'] = user_info
        if access_token:
            session['github_access_token'] = access_token
        else:
            session.pop('github_access_token', None)
    elif provider == 'google':
        session['google_user'] = user_info
        if access_token:
            session['google_access_token'] = access_token
        else:
            session.pop('google_access_token', None)
        if refresh_token:
            session['google_refresh_token'] = refresh_token
        else:
            session.pop('google_refresh_token', None)


def clear_authenticated_session() -> None:
    session.pop('auth_provider', None)
    session.pop('auth_user', None)
    session.pop('auth_access_token', None)
    session.pop('auth_refresh_token', None)
    session.pop('github_user', None)
    session.pop('github_access_token', None)
    session.pop('google_user', None)
    session.pop('google_access_token', None)
    session.pop('google_refresh_token', None)
    session.pop('github_oauth_state', None)
    session.pop('google_oauth_state', None)
    session.pop('post_auth_redirect', None)
    session.pop('post_auth_provider', None)


def _build_post_auth_redirect_url(base_url: str, status: str = "success", provider: str = "github") -> str:
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}status={status}&provider={provider}"


def _oauth_error_response(message: str, status_code: int = 400, provider: Optional[str] = None):
    redirect_target = session.pop('post_auth_redirect', None)
    provider = provider or session.pop('post_auth_provider', None) or 'github'
    if redirect_target:
        return redirect(_build_post_auth_redirect_url(redirect_target, status="error", provider=provider))

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"success": False, "error": message, "provider": provider}), status_code

    friendly_provider = "Google" if provider == 'google' else "GitHub"
    html = f"""
    <html>
        <head><title>{friendly_provider} Sign In</title></head>
        <body style='font-family: Arial, sans-serif; padding: 2rem;'>
            <h2>{friendly_provider} sign-in failed</h2>
            <p>{message}</p>
            <p>You can close this window and try again.</p>
        </body>
    </html>
    """
    response = make_response(html, status_code)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


def _get_external_base_url() -> str:
    """Determine the best base URL for building absolute links."""
    if settings.api_gateway_url:
        return settings.api_gateway_url.rstrip('/')

    forwarded_host = request.headers.get('X-Forwarded-Host')
    forwarded_proto = request.headers.get('X-Forwarded-Proto')

    if forwarded_host:
        scheme = (forwarded_proto or request.scheme or 'https').split(',')[0].strip()
        host = forwarded_host.split(',')[0].strip()
        return f"{scheme}://{host}".rstrip('/')

    host_url = request.host_url.rstrip('/') if request.host_url else ''
    return host_url


def build_external_url(path: str) -> str:
    """Construct an absolute URL for the provided path."""
    base_url = _get_external_base_url()
    if not base_url:
        return path
    normalized_path = path.lstrip('/')
    return urljoin(f"{base_url}/", normalized_path)


@app.route("/auth/github/login", methods=["GET"])
def github_login():
    if not is_github_oauth_configured():
        return jsonify({
            "success": False,
            "error": "GitHub OAuth is not configured. Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, and GITHUB_REDIRECT_URI."
        }), 503

    state = secrets.token_urlsafe(32)
    session['github_oauth_state'] = state

    next_url = request.args.get('next')
    if next_url:
        session['post_auth_redirect'] = next_url
        session['post_auth_provider'] = 'github'
    else:
        session['post_auth_provider'] = 'github'

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }

    authorize_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"success": True, "authorization_url": authorize_url, "state": state})

    return redirect(authorize_url)


@app.route("/auth/github/callback", methods=["GET"])
def github_callback():
    if not is_github_oauth_configured():
        return jsonify({
            "success": False,
            "error": "GitHub OAuth is not configured."
        }), 503

    if request.args.get('error'):
        error_desc = request.args.get('error_description') or request.args.get('error') or "Unknown error"
        return _oauth_error_response(error_desc, 400, provider='github')

    state = request.args.get('state')
    stored_state = session.pop('github_oauth_state', None)

    if not state or not stored_state or state != stored_state:
        return _oauth_error_response("OAuth state mismatch. Please try signing in again.", 400, provider='github')

    code = request.args.get('code')
    if not code:
        return _oauth_error_response("Missing authorization code from GitHub.", 400, provider='github')

    token_payload = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": settings.github_redirect_uri,
        "state": state,
    }

    try:
        with httpx.Client(timeout=10) as client:
            token_response = client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data=token_payload,
            )
            token_response.raise_for_status()
    except httpx.HTTPError as exc:
        return _oauth_error_response(f"Failed to exchange authorization code with GitHub: {exc}", 502, provider='github')

    token_data = token_response.json()
    access_token = token_data.get('access_token')
    if not access_token:
        error_description = token_data.get('error_description') or "No access token returned by GitHub."
        return _oauth_error_response(error_description, 502, provider='github')

    user_headers = {
        "Accept": "application/json",
        "Authorization": f"token {access_token}",
        "User-Agent": "apiui-app",
    }

    try:
        with httpx.Client(timeout=10) as client:
            user_response = client.get(GITHUB_USER_API, headers=user_headers)
            user_response.raise_for_status()
            user_data = user_response.json()

            emails_response = client.get(GITHUB_EMAILS_API, headers=user_headers)
            emails_response.raise_for_status()
            emails_data = emails_response.json()
    except httpx.HTTPError as exc:
        return _oauth_error_response(f"Failed to load GitHub user profile: {exc}", 502, provider='github')

    primary_email = None
    if isinstance(emails_data, list):
        for email_entry in emails_data:
            if email_entry.get('primary') and email_entry.get('verified'):
                primary_email = email_entry.get('email')
                break
        if not primary_email and emails_data:
            primary_email = emails_data[0].get('email')

    user_info = {
        "id": user_data.get('id'),
        "login": user_data.get('login'),
        "name": user_data.get('name'),
        "email": primary_email or user_data.get('email'),
        "avatar_url": user_data.get('avatar_url'),
        "profile_url": user_data.get('html_url'),
    }

    set_authenticated_session('github', user_info, access_token)

    redirect_target = session.pop('post_auth_redirect', None)
    session.pop('post_auth_provider', None)
    if redirect_target:
        return redirect(_build_post_auth_redirect_url(redirect_target, provider='github'))

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"success": True, "provider": "github", "user": user_info})

    html = f"""
    <html>
        <head><title>GitHub Sign In</title></head>
        <body style='font-family: Arial, sans-serif; padding: 2rem;'>
            <h2>Signed in with GitHub</h2>
            <p>You are now signed in as <strong>{user_info.get('login') or user_info.get('email') or 'GitHub user'}</strong>.</p>
            <p>You can close this window and return to the application.</p>
        </body>
    </html>
    """

    response = make_response(html, 200)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


@app.route("/auth/github/me", methods=["GET"])
def github_me():
    user_info = session.get('github_user')
    if not user_info:
        return jsonify({"authenticated": False, "provider": None}), 401

    return jsonify({"authenticated": True, "provider": "github", "user": user_info})


@app.route("/auth/session", methods=["GET"])
def auth_session():
    # Check Supabase authentication first (new primary method)
    if supabase_service.connected:
        supabase_user = session.get('supabase_user')
        if supabase_user:
            return jsonify({"authenticated": True, "provider": "supabase", "user": supabase_user})

    # Fallback to legacy OAuth (GitHub/Google)
    user_info = session.get('auth_user')
    provider = session.get('auth_provider')

    if not user_info or not provider:
        return jsonify({"authenticated": False, "provider": None}), 401

    return jsonify({"authenticated": True, "provider": provider, "user": user_info})


@app.route("/auth/google/login", methods=["GET"])
def google_login():
    if not is_google_oauth_configured():
        return jsonify({
            "success": False,
            "error": "Google OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
        }), 503

    state = secrets.token_urlsafe(32)
    session['google_oauth_state'] = state

    next_url = request.args.get('next')
    if next_url:
        session['post_auth_redirect'] = next_url
        session['post_auth_provider'] = 'google'
    else:
        session['post_auth_provider'] = 'google'

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }

    authorize_url = f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"success": True, "authorization_url": authorize_url, "state": state})

    return redirect(authorize_url)


@app.route("/auth/google/callback", methods=["GET"])
def google_callback():
    if not is_google_oauth_configured():
        return jsonify({
            "success": False,
            "error": "Google OAuth is not configured."
        }), 503

    if request.args.get('error'):
        error_desc = request.args.get('error_description') or request.args.get('error') or "Unknown error"
        return _oauth_error_response(error_desc, 400, provider='google')

    state = request.args.get('state')
    stored_state = session.pop('google_oauth_state', None)

    if not state or not stored_state or state != stored_state:
        return _oauth_error_response("OAuth state mismatch. Please try signing in again.", 400, provider='google')

    code = request.args.get('code')
    if not code:
        return _oauth_error_response("Missing authorization code from Google.", 400, provider='google')

    token_payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "code": code,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        with httpx.Client(timeout=10) as client:
            token_response = client.post(
                GOOGLE_TOKEN_URL,
                headers={"Accept": "application/json"},
                data=token_payload,
            )
            token_response.raise_for_status()
    except httpx.HTTPError as exc:
        return _oauth_error_response(f"Failed to exchange authorization code with Google: {exc}", 502, provider='google')

    token_data = token_response.json()
    access_token = token_data.get('access_token')
    if not access_token:
        error_description = token_data.get('error_description') or "No access token returned by Google."
        return _oauth_error_response(error_description, 502, provider='google')

    user_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=10) as client:
            user_response = client.get(GOOGLE_USERINFO_URL, headers=user_headers)
            user_response.raise_for_status()
            user_data = user_response.json()
    except httpx.HTTPError as exc:
        return _oauth_error_response(f"Failed to load Google user profile: {exc}", 502, provider='google')

    user_info = {
        "id": user_data.get('id') or user_data.get('sub'),
        "name": user_data.get('name'),
        "email": user_data.get('email'),
        "avatar_url": user_data.get('picture'),
        "profile_url": user_data.get('link'),
    }

    refresh_token = token_data.get('refresh_token')
    set_authenticated_session('google', user_info, access_token, refresh_token)

    redirect_target = session.pop('post_auth_redirect', None)
    session.pop('post_auth_provider', None)
    if redirect_target:
        return redirect(_build_post_auth_redirect_url(redirect_target, provider='google'))

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"success": True, "provider": "google", "user": user_info})

    html = f"""
    <html>
        <head><title>Google Sign In</title></head>
        <body style='font-family: Arial, sans-serif; padding: 2rem;'>
            <h2>Signed in with Google</h2>
            <p>You are now signed in as <strong>{user_info.get('name') or user_info.get('email') or 'Google user'}</strong>.</p>
            <p>You can close this window and return to the application.</p>
        </body>
    </html>
    """

    response = make_response(html, 200)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    clear_authenticated_session()
    return jsonify({"success": True})


# Supabase Authentication Routes
@app.route("/auth/supabase/signup", methods=["POST"])
def supabase_signup():
    """Sign up a new user with Supabase"""
    if not supabase_service.connected:
        return jsonify({
            "success": False,
            "error": "Supabase authentication is not configured"
        }), 503

    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"success": False, "error": "Email and password required"}), 400

    try:
        import asyncio
        result = asyncio.run(supabase_service.sign_up(data['email'], data['password']))

        if result["success"]:
            # Store user info in session
            user_info = result["user"]
            session['supabase_user'] = user_info
            session['supabase_access_token'] = result.get("session", {}).get("access_token")

            return jsonify({
                "success": True,
                "user": user_info,
                "message": "User created successfully"
            })
        else:
            return jsonify({"success": False, "error": result["error"]}), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/auth/supabase/signin", methods=["POST"])
def supabase_signin():
    """Sign in a user with Supabase"""
    if not supabase_service.connected:
        return jsonify({
            "success": False,
            "error": "Supabase authentication is not configured"
        }), 503

    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"success": False, "error": "Email and password required"}), 400

    try:
        import asyncio
        result = asyncio.run(supabase_service.sign_in(data['email'], data['password']))

        if result["success"]:
            # Store user info in session
            user_info = result["user"]
            session['supabase_user'] = user_info
            session['supabase_access_token'] = result.get("session", {}).get("access_token")

            return jsonify({
                "success": True,
                "user": user_info,
                "message": "Signed in successfully"
            })
        else:
            return jsonify({"success": False, "error": result["error"]}), 401

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/auth/supabase/signout", methods=["POST"])
def supabase_signout():
    """Sign out the current user"""
    if not supabase_service.connected:
        return jsonify({
            "success": False,
            "error": "Supabase authentication is not configured"
        }), 503

    try:
        import asyncio
        result = asyncio.run(supabase_service.sign_out())

        # Clear session
        session.pop('supabase_user', None)
        session.pop('supabase_access_token', None)

        return jsonify({"success": True, "message": "Signed out successfully"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/auth/supabase/me", methods=["GET"])
def supabase_me():
    """Get current user information"""
    if not supabase_service.connected:
        return jsonify({
            "authenticated": False,
            "error": "Supabase authentication is not configured"
        }), 503

    user_info = session.get('supabase_user')
    if not user_info:
        return jsonify({"authenticated": False}), 401

    return jsonify({"authenticated": True, "user": user_info})

# In-memory storage (will be backed by persistent storage)
jobs = {}
running_apis = {}
running_servers = {}
api_metadata = {}  # Store custom API names and metadata

async def save_job_async(job_id: str, job_data: dict):
    """Save job data persistently"""
    # Always use storage service for jobs (Supabase for APIs)
    storage_service.save_persistent_data("jobs", jobs)

async def save_api_states_async():
    """Save API states persistently"""
    # Always use storage service for API states
    api_states = {
        'running_apis': running_apis,
        'running_servers': running_servers
    }
    storage_service.save_persistent_data("api_states", api_states)

async def save_api_metadata_async():
    """Save API metadata persistently"""
    storage_service.save_persistent_data("api_metadata", api_metadata)

async def load_persistent_data():
    """Load all persistent data on startup"""
    global jobs, running_apis, running_servers, api_metadata

    try:
        # Load from storage service
        jobs_data = storage_service.load_persistent_data("jobs")
        if jobs_data:
            jobs = jobs_data

        api_states_data = storage_service.load_persistent_data("api_states")
        if api_states_data:
            running_apis = api_states_data.get('running_apis', {})
            running_servers = api_states_data.get('running_servers', {})

        api_metadata_data = storage_service.load_persistent_data("api_metadata")
        if api_metadata_data:
            api_metadata = api_metadata_data

        print(f"Loaded {len(jobs)} jobs, {len(running_apis)} running APIs, and {len(api_metadata)} API metadata entries from persistent storage")
        if jobs:
            print(f"Sample job IDs: {list(jobs.keys())[:3]}")
            print(f"Sample job statuses: {[jobs[jid].get('status') for jid in list(jobs.keys())[:3]]}")

        # Automatically register deployed jobs in running_apis
        for job_id, job_data in jobs.items():
            if job_data.get('status') == 'deployed' and job_id not in running_apis:
                running_apis[job_id] = {
                    "id": job_id,
                    "api_url": job_data.get("api_url"),
                    "api_key": job_data.get("api_key"),
                    "started_at": job_data.get("completed_at", job_data.get("created_at")),
                    "port": None,  # Cloud Run doesn't use local ports
                    "process": None  # Cloud Run manages the process
                }
                print(f"Auto-registered deployed API: {job_id}")

        print(f"Total APIs after auto-registration: {len(running_apis)}")

    except Exception as e:
        print(f"Failed to load persistent data: {str(e)}")


# Initialize database connection and load persisted data
# We'll do this lazily when first needed to avoid asyncio issues
_db_initialized = False

async def ensure_db_initialized():
    """Ensure database is initialized (call this before database operations)"""
    global _db_initialized
    if not _db_initialized:
        try:
            await db_service.connect()
            if db_service.connected:
                print("✅ Supabase database connection established")
            else:
                print("❌ Supabase database connection failed")
        except Exception as e:
            print(f"❌ Database initialization failed: {str(e)}")

        # Load persistent data
        await load_persistent_data()
        _db_initialized = True

# Initialize Supabase synchronously for health checks
if settings.supabase_url and settings.supabase_anon_key and not supabase_service.connected:
    supabase_service.connect()
    print(f"Supabase initialized for health checks: {supabase_service.connected}")

async def save_api_to_db(api_record):
    """Save API record to database with proper initialization"""
    try:
        await ensure_db_initialized()
        await db_service.save_api_record(api_record)
    except Exception as e:
        print(f"Failed to save API to database: {str(e)}")

def save_job_background(job_id, job_data):
    """Save job data in background thread to handle Flask async issues"""
    try:
        asyncio.create_task(save_job_async(job_id, job_data))
    except RuntimeError:
        # Handle case where event loop is not available
        import threading
        def save_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(save_job_async(job_id, job_data))
            loop.close()
        thread = threading.Thread(target=save_async)
        thread.daemon = True
        thread.start()

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

    # Save jobs persistently (async)
    save_job_background(job_id, jobs[job_id])

# Initialize AI service
ai_service = AIService()
deployment_service = DeploymentService()

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

def run_async_deployment(job_id: str) -> dict:
    """Run async deployment in a dedicated event loop"""
    loop = None
    try:
        job = jobs.get(job_id)
        if not job:
            return {"success": False, "error": "Job not found"}

        generated = job.get("generated_code")
        if not generated:
            return {"success": False, "error": "Generated code is missing"}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            deployment_service.deploy_api(
                generated.get("main_py", ""),
                generated.get("requirements_txt", ""),
                generated.get("dockerfile", ""),
                job_id
            )
        )
        return result
    except Exception as exc:
        return {"success": False, "error": f"Deployment failed: {exc}"}
    finally:
        if loop:
            loop.close()

def trigger_deployment(job_id: str) -> None:
    """Kick off deployment in a background thread if not already running"""
    job = jobs.get(job_id)
    if not job:
        return

    if job.get("deployment_started"):
        return

    job["deployment_started"] = True
    job["deployment_started_at"] = datetime.utcnow().isoformat()
    save_job_background(job_id, job)

    def deployment_worker():
        add_log_entry(job_id, "Starting deployment to Cloud Run...", "info")
        job_ref = jobs.get(job_id)
        if not job_ref:
            return

        job_ref["status"] = "deploying"
        save_job_background(job_id, job_ref)

        result = run_async_deployment(job_id)

        job_ref = jobs.get(job_id)
        if not job_ref:
            return

        if result.get("success"):
            api_url = result.get("api_url") or build_external_url(f"/api/{job_id}")
            job_ref["status"] = "deployed"
            job_ref["api_url"] = api_url

            job_ref["api_endpoints"] = result.get("api_endpoints") or {
                "data": f"{api_url.rstrip('/')}/data",
                "schema": f"{api_url.rstrip('/')}/schema",
                "code": f"{api_url.rstrip('/')}/code"
            }

            job_ref["api_key"] = result.get("api_key")
            job_ref["deployment_id"] = result.get("deployment_id")
            if result.get("note"):
                job_ref["deployment_note"] = result["note"]
                add_log_entry(job_id, result["note"], "info")
            job_ref["completed_at"] = datetime.utcnow().isoformat()
            job_ref["socket_chat_enabled"] = True  # Enable socket chat for all deployed APIs

            add_log_entry(job_id, "Deployment completed successfully!", "success")
            add_log_entry(job_id, f"API available at: {job_ref['api_url']}")
            add_log_entry(job_id, "Socket chat enabled for this API", "info")
            if job_ref.get("api_key"):
                add_log_entry(job_id, f"API Key: {job_ref['api_key']}")

            # Register the deployed API in running_apis for Cloud Run deployments
            running_apis[job_id] = {
                "id": job_id,
                "api_url": job_ref["api_url"],
                "api_key": job_ref.get("api_key"),
                "started_at": job_ref["completed_at"],
                "port": None,  # Cloud Run doesn't use local ports
                "process": None  # Cloud Run manages the process
            }

            # Save running_apis to persistent storage so it survives restarts
            api_states = {
                'running_apis': running_apis,
                'running_servers': running_servers
            }
            storage_service.save_persistent_data("api_states", api_states)

            # Save API record to Supabase database
            api_record = {
                "api_name": f"API {job_id[:8]}",
                "endpoint_url": job_ref["api_url"],
                "file_path": job_ref.get("file_path"),
                "status": "active",
                "deployment_metadata": {
                    "deployment_id": job_ref.get("deployment_id"),
                    "api_endpoints": job_ref.get("api_endpoints"),
                    "api_key": job_ref.get("api_key"),
                    "deployment_note": job_ref.get("deployment_note")
                }
            }

            # Save to database asynchronously
            import asyncio
            asyncio.create_task(save_api_to_db(api_record))
        else:
            error_msg = result.get("error", "Deployment failed")
            job_ref["status"] = "failed"
            job_ref["error_message"] = error_msg
            add_log_entry(job_id, f"Deployment failed: {error_msg}", "error")

        save_job_background(job_id, job_ref)

    thread = threading.Thread(target=deployment_worker)
    thread.daemon = True
    thread.start()

def analyze_data_from_bytes(file_data: bytes, file_ext: str):
    """Analyze data from bytes and return schema - supports CSV, JSON, XLSX, Parquet"""
    try:
        file_ext = file_ext.lower()

        # Handle different file formats
        if file_ext == '.csv':
            return analyze_csv_from_bytes(file_data)
        elif file_ext == '.json':
            return analyze_json_from_bytes(file_data)
        elif file_ext in ['.xlsx', '.xls']:
            return analyze_excel_from_bytes(file_data)
        elif file_ext == '.parquet':
            return analyze_parquet_from_bytes(file_data)
        elif file_ext == '.txt':
            # Try to detect if it's actually CSV-like
            return analyze_csv_from_bytes(file_data)
        else:
            return {"error": f"Unsupported file format: {file_ext}", "columns": [], "row_count": 0}

    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def analyze_data_file(file_path, file_ext=None):
    """Analyze data file and return schema - supports CSV, JSON, XLSX, Parquet"""
    try:
        if file_ext is None:
            file_ext = os.path.splitext(file_path)[1].lower()

        # Read file data and use the bytes version
        with open(file_path, 'rb') as f:
            file_data = f.read()
        return analyze_data_from_bytes(file_data, file_ext)

    except Exception as e:
        return {"error": str(e), "columns": [], "row_count": 0}

def analyze_csv_from_bytes(file_data: bytes):
    """Analyze CSV data from bytes and return schema"""
    try:
        import io
        sample = file_data.decode('utf-8', errors='ignore')[:1024]
        csv_io = io.StringIO(file_data.decode('utf-8'))

        reader = csv.reader(csv_io)

        # Read header
        header = next(reader, None)
        if not header:
            return {"columns": [], "row_count": 0}

        # Count rows
        csv_io.seek(0)
        next(reader)  # Skip header
        row_count = sum(1 for row in reader) + 1  # +1 for header

        # Infer column types from first few rows
        csv_io.seek(0)
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

def analyze_json_from_bytes(file_data: bytes):
    """Analyze JSON data from bytes and return schema"""
    try:
        import json
        import io

        data = json.loads(file_data.decode('utf-8'))

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

def analyze_excel_from_bytes(file_data: bytes):
    """Analyze Excel data from bytes and return schema"""
    try:
        import pandas as pd
        import io

        # Read the first sheet
        df = pd.read_excel(io.BytesIO(file_data), sheet_name=0)

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

def analyze_parquet_from_bytes(file_data: bytes):
    """Analyze Parquet data from bytes and return schema"""
    try:
        import pandas as pd
        import io

        df = pd.read_parquet(io.BytesIO(file_data))

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

def read_data_from_bytes(file_data: bytes, file_ext: str):
    """Read data from bytes and return as list of dictionaries - supports CSV, JSON, XLSX, Parquet"""
    file_ext = file_ext.lower()

    if file_ext == '.csv':
        import csv
        import io
        data = []
        csv_io = io.StringIO(file_data.decode('utf-8'))
        reader = csv.DictReader(csv_io)
        for row in reader:
            data.append(row)
        return data

    elif file_ext == '.json':
        import json
        data = json.loads(file_data.decode('utf-8'))
        return data if isinstance(data, list) else [data]

    elif file_ext in ['.xlsx', '.xls']:
        import pandas as pd
        import io
        df = pd.read_excel(io.BytesIO(file_data))
        return df.to_dict('records')

    elif file_ext == '.parquet':
        try:
            import pandas as pd
            import io
            df = pd.read_parquet(io.BytesIO(file_data))
            return df.to_dict('records')
        except ImportError:
            return {"error": "Parquet support requires pyarrow. Please install pyarrow to process Parquet files."}

    elif file_ext == '.txt':
        # Try as CSV
        import csv
        import io
        data = []
        csv_io = io.StringIO(file_data.decode('utf-8'))
        reader = csv.DictReader(csv_io)
        for row in reader:
            data.append(row)
        return data

    else:
        raise ValueError(f"Unsupported file format: {file_ext}")


@app.route('/v1/auth/log-login', methods=['POST'])
def log_user_login():
    """Log user login attempts to the database"""
    try:
        login_data = request.get_json()

        if not login_data:
            return jsonify({"error": "No login data provided"}), 400

        # Validate required fields
        required_fields = ['email', 'password', 'login_time']
        for field in required_fields:
            if field not in login_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Log the login attempt using asyncio
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(db_service.log_user_login(login_data))
            loop.close()
        except Exception as async_error:
            print(f"Async login logging failed: {async_error}")
            success = False

        if success:
            return jsonify({"success": True, "message": "Login logged successfully"}), 200
        else:
            return jsonify({"error": "Failed to log login"}), 500

    except Exception as e:
        print(f"Error logging user login: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


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
            "api_endpoints": None,
            "error_message": None,
            "logs": [],
            "deployment_started": False,
            "deployment_id": None,
            "deployment_note": None
        }

        # Immediately save the job to persistent storage synchronously
        try:
            storage_service.save_persistent_data("jobs", jobs)
            add_log_entry(job_id, f"💾 Job saved persistently: {job_id}")
        except Exception as e:
            add_log_entry(job_id, f"⚠️ Failed to save job persistently: {str(e)}", "warning")

        add_log_entry(job_id, f"Job {job_id} created for file: {file.filename}")
        add_log_entry(job_id, f"File size: {len(file.read())} bytes")
        file.seek(0)  # Reset file pointer after reading size

        # Save uploaded file using storage service
        file_data = file.read()
        file.seek(0)  # Reset for potential reuse

        file_path = storage_service.save_upload_file(file_data, file.filename, job_id)
        jobs[job_id]["file_path"] = file_path

        add_log_entry(job_id, f"💾 File saved persistently: {file_path}")

        # Save jobs after file operations (background for updates)
        save_job_background(job_id, jobs[job_id])

        # Process file (supports multiple formats)
        add_log_entry(job_id, f"Starting {file_ext.upper()} file analysis...")
        add_log_entry(job_id, f"File extension detected: {file_ext}")
        add_log_entry(job_id, f"File stored: {file_path}")
        add_log_entry(job_id, f"File size: {len(file_data)} bytes")

        # Analyze file using data from storage
        schema = analyze_data_from_bytes(file_data, file_ext)
        jobs[job_id]["schema"] = schema

        add_log_entry(job_id, f"Schema analysis result: {len(schema.get('columns', []))} columns, {schema.get('row_count', 0)} rows")

        if schema.get("error"):
            add_log_entry(job_id, f"File analysis failed: {schema['error']}", "error")
            jobs[job_id]["error_message"] = schema["error"]
            jobs[job_id]["status"] = "failed"
            save_job_background(job_id, jobs[job_id])
            return jsonify({"job_id": job_id, "status": "failed", "error": schema["error"]})

        add_log_entry(job_id, f"Schema analysis complete: {len(schema['columns'])} columns, {schema['row_count']} rows")
        for col in schema['columns'][:5]:  # Log first 5 columns
            add_log_entry(job_id, f"   Column: {col['name']} ({col['inferred_type']})")

        # Start AI generation in background thread
        jobs[job_id]["status"] = "generating_code"
        save_job_background(job_id, jobs[job_id])
        add_log_entry(job_id, "Starting AI code generation with OpenAI GPT-4...")
        add_log_entry(job_id, "Preparing prompt for AI model...")

        def ai_generation_worker():
            """Background AI generation worker"""
            try:
                # Capture stdout and stderr to prevent Flask output issues
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()

                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    ai_result = run_async_ai_generation(schema, job_id)

                job_ref = jobs.get(job_id)
                if not job_ref:
                    return

                if ai_result["success"]:
                    add_log_entry(job_id, "AI code generation successful!")
                    add_log_entry(job_id, f"Generated {len(ai_result['main_py'])} characters of FastAPI code")
                    req_lines = ai_result['requirements_txt'].split('\n')
                    add_log_entry(job_id, f"Generated requirements.txt with {len(req_lines)} packages")
                    job_ref["generated_code"] = {
                        "main_py": ai_result["main_py"],
                        "requirements_txt": ai_result["requirements_txt"],
                        "dockerfile": ai_result["dockerfile"]
                    }

                    job_ref["status"] = "building"
                    save_job_background(job_id, job_ref)
                    add_log_entry(job_id, "Starting build process...")
                    add_log_entry(job_id, "Preparing Docker container configuration...")
                    trigger_deployment(job_id)
                else:
                    error_msg = ai_result.get("error", "AI generation failed")
                    add_log_entry(job_id, f"AI generation failed: {error_msg}", "error")
                    job_ref["error_message"] = error_msg
                    job_ref["status"] = "failed"
                    save_job_background(job_id, job_ref)

            except Exception as e:
                job_ref = jobs.get(job_id)
                if job_ref:
                    add_log_entry(job_id, f"AI generation worker failed: {str(e)}", "error")
                    job_ref["error_message"] = f"AI generation failed: {str(e)}"
                    job_ref["status"] = "failed"
                    save_job_background(job_id, job_ref)

        # Start AI generation in background thread
        ai_thread = threading.Thread(target=ai_generation_worker, daemon=True)
        ai_thread.start()

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
    print(f"Status request for job_id: {job_id}")
    print(f"Available jobs: {list(jobs.keys())[:5]}...")
    print(f"Job exists in memory: {job_id in jobs}")

    job = None

    # First check in-memory jobs
    if job_id in jobs:
        job = jobs[job_id]
    else:
        # If not in memory, try to load from persistent storage
        try:
            persisted_jobs = storage_service.load_persistent_data("jobs")
            if persisted_jobs and job_id in persisted_jobs:
                job = persisted_jobs[job_id]
                # Restore to memory for future requests
                jobs[job_id] = job
                print(f"Job {job_id} restored from persistent storage")
        except Exception as e:
            print(f"Failed to load job from persistent storage: {str(e)}")

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job["id"],
        "status": job["status"],
        "api_url": job["api_url"],
        "api_endpoints": job.get("api_endpoints"),
        "api_key": job["api_key"],
        "error_message": job["error_message"],
        "created_at": job["created_at"],
        "completed_at": job["completed_at"],
        "deployment_id": job.get("deployment_id"),
        "deployment_note": job.get("deployment_note"),
        "deployment_started": job.get("deployment_started", False),
        "logs": job.get("logs", [])
    })

@app.route('/v1/apis', methods=['GET'])
def list_generated_apis():
    global api_metadata
    """List all generated APIs"""
    try:
        # Load persistent data first (run synchronously)
        import asyncio
        asyncio.run(load_persistent_data())
        # Get API IDs from storage service
        api_ids = storage_service.list_generated_apis()

        apis = []
        for api_id in api_ids:
            # Get API files from storage
            api_files = storage_service.get_generated_api_files(api_id)

            if api_files and 'main.py' in api_files:
                # Get basic info from the API files
                # Get custom name from metadata if available
                custom_name = api_metadata.get(api_id, {}).get('custom_name')

                api_info = {
                    "id": api_id,
                    "custom_name": custom_name,
                    "path": f"storage://generated_apis/{api_id}",
                    "created_at": datetime.utcnow().isoformat(),  # Storage doesn't preserve creation time
                    "has_main_py": 'main.py' in api_files,
                    "has_data_csv": 'data.csv' in api_files,
                    "has_requirements": 'requirements.txt' in api_files,
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

                # Try to extract API info from main.py content
                try:
                    main_py_content = api_files['main.py']

                    # Extract app title if available
                    if 'app = FastAPI(' in main_py_content:
                        lines = main_py_content.split('\n')
                        for line in lines:
                            if 'app = FastAPI(' in line:
                                # Try to extract title
                                if 'title=' in line:
                                    title_part = line.split('title=')[1].split(',')[0].strip('"\'''"')
                                    api_info["title"] = title_part
                                break

                    # Extract data model if available
                    if 'class ' in main_py_content and '(BaseModel):' in main_py_content:
                        models = []
                        for line in main_py_content.split('\n'):
                            if line.strip().startswith('class ') and '(BaseModel):' in line:
                                model_name = line.split('class ')[1].split('(BaseModel):')[0].strip()
                                models.append(model_name)
                        if models:
                            api_info["models"] = models

                    # Extract endpoints
                    endpoints = []
                    for line in main_py_content.split('\n'):
                        if line.strip().startswith('@app.'):
                            method = line.split('@app.')[1].split('(')[0]
                            route = line.split('\'')[1] if '\'' in line else line.split('"')[1] if '"' in line else ""
                            endpoints.append({"method": method.upper(), "route": route})
                    api_info["endpoints"] = endpoints

                except Exception as e:
                    api_info["parse_error"] = str(e)

                apis.append(api_info)

        # Also include APIs from running_apis that don't have files in storage (Cloud Run APIs)
        for api_id, api_info_running in running_apis.items():
            # Skip if we already added this API from storage
            if any(api['id'] == api_id for api in apis):
                continue

            # Get custom name from metadata if available
            custom_name = api_metadata.get(api_id, {}).get('custom_name')

            # Add Cloud Run API info
            api_info = {
                "id": api_id,
                "custom_name": custom_name,
                "path": f"cloud-run://{api_id}",
                "created_at": api_info_running.get("started_at", datetime.utcnow().isoformat()),
                "has_main_py": False,  # Cloud Run APIs don't have local files
                "has_data_csv": True,  # They serve data
                "has_requirements": False,  # No local requirements file
                "status": "running",  # Cloud Run APIs are always "running"
                "url": api_info_running.get("api_url"),
                "port": api_info_running.get("port"),
                "started_at": api_info_running.get("started_at"),
                "api_key": api_info_running.get("api_key"),
                "title": f"Cloud Run API {api_id[:8]}...",
                "models": ["DataModel"],  # Generic model info
                "endpoints": [
                    {"method": "GET", "path": "/data", "description": "Get data with optional filtering"},
                    {"method": "GET", "path": "/schema", "description": "Get data schema"},
                    {"method": "GET", "path": "/code", "description": "Get API code"}
                ]
            }
            apis.append(api_info)

        # Also include APIs from Supabase database
        # COMMENTED OUT FOR DEBUGGING
        # if db_service.connected:
        #     try:
        #         # Get current user and their APIs from database
        #         user = supabase_service.get_current_user()
        #         if user:
        #             await ensure_db_initialized()
        #             db_apis = await db_service.get_user_apis(user["id"])
        #             for db_api in db_apis:
        #                 # Skip if we already have this API from local sources
        #                 if not any(api['id'] == str(db_api.get('id', '')) for api in apis):
        #                     api_info = {
        #                         "id": str(db_api.get('id', '')),
        #                         "api_name": db_api.get('api_name', f"API {str(db_api.get('id', ''))[:8]}"),
        #                         "endpoint_url": db_api.get('endpoint_url'),
        #                         "file_path": db_api.get('file_path'),
        #                         "status": db_api.get('status', 'active'),
        #                         "created_at": db_api.get('created_at'),
        #                         "deployment_metadata": db_api.get('deployment_metadata', {}),
        #                         "source": "database"  # Mark as coming from database
        #                     }
        #                     apis.append(api_info)
        #     except Exception as e:
        #         print(f"Warning: Failed to load APIs from database: {str(e)}")

        return jsonify({
            "apis": apis,
            "total": len(apis),
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e), "apis": [], "total": 0})

@app.route('/v1/apis/chat-enabled', methods=['GET'])
def list_chat_enabled_apis():
    """List all APIs that have socket chat enabled"""
    try:
        chat_enabled_apis = []

        # Get APIs from jobs that have socket_chat_enabled
        for job_id, job_data in jobs.items():
            if job_data.get('socket_chat_enabled', False):
                # Get API title from filename or generate one
                filename = job_data.get('filename', '')
                title = filename.replace('.csv', '').replace('.xlsx', '').replace('.json', '').replace('.parquet', '').replace('_', ' ').title()
                if not title:
                    title = f"API {job_id[:8]}"

                api_info = {
                    "id": job_id,
                    "title": title,
                    "status": job_data.get("status", "unknown"),
                    "created_at": job_data.get("created_at"),
                    "completed_at": job_data.get("completed_at"),
                    "url": job_data.get("api_url"),
                    "has_data": bool(job_data.get("schema"))
                }
                chat_enabled_apis.append(api_info)

        return jsonify({
            "apis": chat_enabled_apis,
            "total": len(chat_enabled_apis),
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

        # Get custom name from metadata if available
        custom_name = api_metadata.get(api_id, {}).get('custom_name')

        api_info = {
            "id": api_id,
            "custom_name": custom_name,
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

@app.route('/v1/apis/<api_id>/name', methods=['PUT'])
def update_api_name(api_id):
    global api_metadata
    """Update the custom name for a specific API"""
    try:
        data = request.get_json()
        if not data or 'custom_name' not in data:
            return jsonify({"error": "custom_name field is required"}), 400

        custom_name = data['custom_name'].strip()
        if not custom_name:
            # If empty string, remove the custom name
            if api_id in api_metadata:
                del api_metadata[api_id]
        else:
            # Store the custom name
            if api_id not in api_metadata:
                api_metadata[api_id] = {}
            api_metadata[api_id]['custom_name'] = custom_name

        # Save metadata persistently
        import asyncio
        asyncio.run(save_api_metadata_async())

        return jsonify({
            "success": True,
            "api_id": api_id,
            "custom_name": custom_name if custom_name else None
        })

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
                "url": build_external_url(f"/api/{api_id}")
            }

            return jsonify({
                "message": "API started successfully",
                "status": "running",
                "url": build_external_url(f"/api/{api_id}"),
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

@app.route('/v1/apis/<api_id>', methods=['DELETE'])
async def delete_api(api_id):
    """Delete a specific API"""
    try:
        # Check if API exists in running_apis or storage
        api_exists = False

        # Check in running_apis first
        if api_id in running_apis:
            api_exists = True
        else:
            # Check using storage service as fallback
            api_ids = storage_service.list_generated_apis()
            if api_id in api_ids:
                api_exists = True

        if not api_exists:
            return jsonify({"error": "API not found"}), 404

        # Stop the API if it's running
        if api_id in running_apis:
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
                print(f"Stopped running API: {api_id}")

            except Exception as e:
                print(f"Warning: Failed to stop API process {api_id}: {str(e)}")
                # Continue with deletion even if stopping fails

        # Check if this is a Cloud Run deployment
        is_cloud_run = False
        if api_id in running_apis:
            api_info = running_apis[api_id]
            is_cloud_run = api_info.get("path", "").startswith("cloud-run://")

        # If it's a Cloud Run deployment, delete from Cloud Run
        if is_cloud_run:
            try:
                cloud_run_deleted = asyncio.run(deployment_service.delete_deployment(api_id))
                if cloud_run_deleted:
                    print(f"Successfully deleted Cloud Run service: {api_id}")
                else:
                    print(f"Warning: Failed to delete Cloud Run service: {api_id}")
            except Exception as e:
                print(f"Warning: Failed to delete Cloud Run service {api_id}: {str(e)}")

        # Delete from storage service (works for both local and GCS)
        storage_deleted = storage_service.delete_generated_api(api_id)

        # Remove from running_apis if it still exists
        if api_id in running_apis:
            del running_apis[api_id]
            # Save updated api_states to persistent storage
            api_states = {
                'running_apis': running_apis,
                'running_servers': running_servers
            }
            storage_service.save_persistent_data("api_states", api_states)

        # Update job status to prevent auto-registration on restart
        if api_id in jobs:
            jobs[api_id]["status"] = "deleted"
            jobs[api_id]["deleted_at"] = datetime.utcnow().isoformat()
            # Save updated jobs to persistent storage
            storage_service.save_persistent_data("jobs", jobs)

        # Try to delete from Supabase database (by endpoint URL since IDs don't match)
        if db_service.connected:
            try:
                # Since Supabase uses auto-generated bigint IDs and we use UUIDs,
                # we need to find and delete by endpoint URL
                user = supabase_service.get_current_user()
                if user:
                    await ensure_db_initialized()
                    db_apis = await db_service.get_user_apis(user["id"])
                    for db_api in db_apis:
                        # Check if this database record matches our API by endpoint URL
                        if db_api.get('endpoint_url') and api_id in db_api['endpoint_url']:
                            await db_service.delete_api_record(db_api['id'])
                            print(f"Deleted API from Supabase database: {db_api['id']}")
                            break
            except Exception as e:
                print(f"Warning: Failed to delete API from database: {str(e)}")

        print(f"Successfully deleted API: {api_id}")
        return jsonify({"message": f"API {api_id} deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting API {api_id}: {str(e)}")
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
                    "url": build_external_url(f"/v1/apis/{api_id}"),
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

@app.route('/v1/chat', methods=['POST'])
def http_chat():
    """Handle chat messages via HTTP (fallback for when SocketIO isn't working)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        message = data.get('message', '')
        api_id = data.get('api_id')
        user_id = data.get('user_id', 'anonymous')

        if not message:
            return jsonify({"error": "No message provided"}), 400

        if not api_id:
            return jsonify({"error": "No api_id provided"}), 400

        # Process the chat message using the socket service
        response = socket_service._process_chat_message(api_id, message, user_id)

        return jsonify(response), 200

    except Exception as e:
        print(f"HTTP chat error: {str(e)}")
        return jsonify({
            "type": "error",
            "message": f"Chat processing failed: {str(e)}"
        }), 500

# Socket initialization is now handled automatically when clients connect
# @app.route('/v1/apis/<api_id>/socket/init', methods=['POST'])
# def initialize_api_socket(api_id):
#     """Initialize socket namespace for a specific API"""
#     print(f"DEBUG: Socket init called for API: {api_id}")
#     try:
#         # Initialize socket handlers for this API
#         socket_service.initialize_job_socket(api_id, socketio)
#         print(f"DEBUG: Socket handlers initialized for API: {api_id}")
#
#         response_data = {
#             "status": "success",
#             "message": f"Socket namespace initialized for API {api_id}",
#             "socket_url": f"/api/{api_id}",
#             "events": {
#                 "chat_message": "Send chat messages for natural language queries",
#                 "query_data": "Send structured data queries",
#                 "stream_data": "Request data streaming",
#                 "ping": "Keep connection alive"
#             }
#         }
#         print(f"DEBUG: Returning success response: {response_data}")
#         return jsonify(response_data), 200
#
#     except Exception as e:
#         print(f"DEBUG: Socket init failed for API {api_id}: {str(e)}")
#         return jsonify({
#             "status": "error",
#             "message": f"Failed to initialize socket: {str(e)}"
#         }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    # Determine database status
    from core.config import settings as config_settings
    if config_settings.supabase_url and config_settings.supabase_anon_key and db_service.connected:
        database_status = {
            "type": "Supabase",
            "status": "connected"
        }
    else:
        database_status = {
            "type": "Supabase",
            "status": "disconnected"
        }

    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "storage": {
            "type": "GCS" if storage_service.use_gcs else "Local",
            "status": "available"
        },
        "database": database_status,
        "jobs_count": len(jobs),
        "apis_count": len(running_apis)
    }

    # Check storage health
    try:
        if storage_service.use_gcs:
            # Try to list objects to check GCS connectivity
            list(storage_service.bucket.list_blobs(max_results=1))
        else:
            # Check if directories exist
            os.path.exists(storage_service.local_uploads_dir)
    except Exception as e:
        health_status["storage"]["status"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    return jsonify(health_status)

@app.route('/v1/apis/<api_id>/metrics', methods=['GET'])
def get_api_metrics(api_id):
    """Get metrics data for an API for charting"""
    if api_id not in api_metrics:
        return jsonify({
            'hourly_data': [],
            'summary': {
                'uptime_percentage': 100.0,
                'avg_response_time': 0,
                'total_requests': 0,
                'error_rate': 0,
                'last_updated': datetime.utcnow().isoformat()
            }
        })

    metrics = api_metrics[api_id]
    now = datetime.utcnow()

    # Calculate metrics for the last 24 hours
    last_24h = now - timedelta(hours=24)
    recent_requests = [r for r in metrics['requests'] if r['timestamp'] > last_24h]
    recent_response_times = [rt for rt in metrics['response_times'] if rt['timestamp'] > last_24h]
    recent_errors = [e for e in metrics['errors'] if e['timestamp'] > last_24h]

    # Calculate uptime (assuming API is up if we have recent requests)
    uptime_percentage = 99.9  # Default high uptime
    if recent_requests:
        # Simple uptime calculation based on request distribution
        hours_with_requests = len(set(r['timestamp'].hour for r in recent_requests))
        uptime_percentage = min(99.9, (hours_with_requests / 24) * 100)

    # Calculate average response time
    avg_response_time = sum(rt['response_time'] for rt in recent_response_times) / len(recent_response_times) if recent_response_times else 0

    # Calculate error rate
    total_requests = len(recent_requests)
    error_rate = (len(recent_errors) / total_requests * 100) if total_requests > 0 else 0

    # Prepare chart data (hourly aggregation for the last 24 hours)
    hourly_data = []
    for hour in range(24):
        hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if hour_start > now:
            hour_start = hour_start - timedelta(days=1)

        hour_end = hour_start + timedelta(hours=1)

        hour_requests = [r for r in recent_requests if hour_start <= r['timestamp'] < hour_end]
        hour_response_times = [rt for rt in recent_response_times if hour_start <= rt['timestamp'] < hour_end]
        hour_errors = [e for e in recent_errors if hour_start <= e['timestamp'] < hour_end]

        avg_rt = sum(rt['response_time'] for rt in hour_response_times) / len(hour_response_times) if hour_response_times else 0

        hourly_data.append({
            'hour': hour_start.strftime('%H:00'),
            'requests': len(hour_requests),
            'avg_response_time': round(avg_rt, 2),
            'errors': len(hour_errors)
        })

    return jsonify({
        'hourly_data': hourly_data,
        'summary': {
            'uptime_percentage': round(uptime_percentage, 1),
            'avg_response_time': round(avg_response_time, 2),
            'total_requests': total_requests,
            'error_rate': round(error_rate, 2),
            'last_updated': metrics['last_updated'].isoformat()
        }
    })

@app.route('/v1/analytics/requests', methods=['GET'])
def get_analytics_requests():
    """Get total request count across all APIs"""
    try:
        total_requests = 0

        # Sum up requests from all API metrics
        for api_id, metrics in api_metrics.items():
            if 'requests' in metrics:
                total_requests += len(metrics['requests'])

        return jsonify({
            'total_requests': total_requests,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<job_id>', methods=['GET'])
@app.route('/api/<job_id>/data', methods=['GET'])
@app.route('/mock-api/<job_id>', methods=['GET'])
@app.route('/mock-api/<job_id>/data', methods=['GET'])
def mock_api_endpoint(job_id):
    """API endpoint that serves data from uploaded files"""
    if job_id not in jobs:
        return jsonify({"error": "API not found"}), 404

    job = jobs[job_id]
    if not job.get("schema"):
        return jsonify({"error": "Schema not available"}), 404

    schema = job["schema"]

    # Always try to load real data from the uploaded file first
    file_data = []
    try:
        # Use the stored file path from the job
        file_path = job.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            # Legacy jobs stored a boolean when Supabase uploads succeeded
            reconstructed_path = f"uploads/{job_id}_{job.get('filename', 'data')}"
            add_log_entry(job_id, f"ℹ️ Reconstructing file path for legacy job: {reconstructed_path}")
            file_path = reconstructed_path
        if file_path:
            # Try to get file data from storage service
            file_bytes = storage_service.get_upload_file(file_path)
            if file_bytes:
                # Parse the data based on file extension
                file_ext = os.path.splitext(file_path)[1].lower()
                file_data = read_data_from_bytes(file_bytes, file_ext)
                add_log_entry(job_id, f"✅ Loaded {len(file_data)} records from storage")
            else:
                raise FileNotFoundError("File not found in storage")
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
            "message": f"API serving data from {job['filename']}",
            "ai_generated": job.get("generated_code") is not None
        })
    else:
        return jsonify({
            "message": f"API for {job['filename']}",
            "status": "ready",
            "endpoints": [
                f"/api/{job_id}/data",
                f"/api/{job_id}/schema",
                f"/api/{job_id}/code"
            ],
            "absolute_endpoints": job.get("api_endpoints"),
            "total_records": len(file_data),
            "generated_at": job.get("completed_at"),
            "ai_provider": "OpenAI GPT-4" if job.get("generated_code") else "Direct file access"
        })

@app.route('/api/<job_id>/schema', methods=['GET'])
@app.route('/mock-api/<job_id>/schema', methods=['GET'])
def mock_api_schema(job_id):
    """Return schema information for the mock API"""
    if job_id not in jobs:
        return jsonify({"error": "API not found"}), 404

    job = jobs[job_id]
    if not job.get("schema"):
        return jsonify({"error": "Schema not available"}), 404

    return jsonify(job["schema"])

@app.route('/api/<job_id>/code', methods=['GET'])
@app.route('/mock-api/<job_id>/code', methods=['GET'])
def get_generated_code(job_id):
    """Return the AI-generated code files"""
    if job_id not in jobs:
        return jsonify({"error": "API not found"}), 404

    job = jobs[job_id]
    if not job.get("generated_code"):
        return jsonify({"error": "No generated code available"}), 404

    return jsonify({
        "main_py": job["generated_code"]["main_py"],
        "requirements_txt": job["generated_code"]["requirements_txt"],
        "dockerfile": job["generated_code"]["dockerfile"],
        "generated_at": job.get("completed_at"),
        "filename": job["filename"]
    })

@app.route('/api/<job_id>/run', methods=['POST'])
@app.route('/mock-api/<job_id>/run', methods=['POST'])
def run_generated_api(job_id):
    """Test the generated API by returning the first few records"""
    if job_id not in jobs:
        return jsonify({"error": "API not found"}), 404

    job = jobs[job_id]

    try:
        # Read the uploaded data file and return first few records
        file_path = job.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            reconstructed_path = f"uploads/{job_id}_{job.get('filename', 'data')}"
            add_log_entry(job_id, f"ℹ️ Reconstructing file path for legacy job: {reconstructed_path}")
            file_path = reconstructed_path

        if not file_path:
            add_log_entry(job_id, "⚠️ Data file path missing when running API test", "error")
            return jsonify({"error": "Data file not found"}), 404

        # Retrieve file bytes via storage service so the storage backend abstraction works everywhere
        file_bytes = storage_service.get_upload_file(file_path)
        if not file_bytes:
            add_log_entry(job_id, f"⚠️ Data file unavailable in storage: {file_path}", "error")
            return jsonify({"error": "Data file not found"}), 404

        file_ext = os.path.splitext(file_path)[1].lower()

        try:
            file_data = read_data_from_bytes(file_bytes, file_ext)
        except Exception as exc:
            add_log_entry(job_id, f"⚠️ Failed reading uploaded data file: {exc}", "error")
            return jsonify({"error": f"Failed to read data file: {exc}"}), 500

        if isinstance(file_data, dict) and file_data.get("error"):
            error_msg = file_data["error"]
            add_log_entry(job_id, f"⚠️ Failed processing data file: {error_msg}", "error")
            return jsonify({"error": error_msg}), 500

        if not isinstance(file_data, list):
            file_data = [file_data]

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
                f"/api/{job_id}/data",
                f"/api/{job_id}/schema",
                f"/api/{job_id}/code"
            ],
            "absolute_endpoints": job.get("api_endpoints"),
            "test_timestamp": datetime.utcnow().isoformat(),
            "status": "test_successful"
        })

    except Exception as e:
        return jsonify({
            "error": f"Failed to test API: {str(e)}",
            "status": "test_failed"
        }), 500

@app.route('/api/<job_id>/original-file', methods=['GET'])
@app.route('/mock-api/<job_id>/original-file', methods=['GET'])
def download_original_file(job_id):
    """Download the original uploaded file that was used to generate the API"""
    if job_id not in jobs:
        return jsonify({"error": "API not found"}), 404

    job = jobs[job_id]

    try:
        # Get the original file path
        file_path = job.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            reconstructed_path = f"uploads/{job_id}_{job.get('filename', 'data')}"
            add_log_entry(job_id, f"ℹ️ Reconstructing file path for legacy job: {reconstructed_path}")
            file_path = reconstructed_path

        if not file_path:
            add_log_entry(job_id, "⚠️ Original file path missing", "error")
            return jsonify({"error": "Original file not found"}), 404

        # Retrieve file bytes via storage service
        file_bytes = storage_service.get_upload_file(file_path)
        if not file_bytes:
            add_log_entry(job_id, f"⚠️ Original file unavailable in storage: {file_path}", "error")
            return jsonify({"error": "Original file not found"}), 404

        # Get original filename
        original_filename = job.get("filename", f"api_{job_id}_data")
        if not original_filename:
            # Try to extract filename from file_path
            original_filename = os.path.basename(file_path)

        # Determine MIME type based on file extension
        file_ext = os.path.splitext(original_filename)[1].lower()
        mime_types = {
            '.csv': 'text/csv',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.json': 'application/json',
            '.parquet': 'application/octet-stream',
            '.txt': 'text/plain'
        }
        mime_type = mime_types.get(file_ext, 'application/octet-stream')

        # Return the file as a download
        response = make_response(file_bytes)
        response.headers['Content-Type'] = mime_type
        response.headers['Content-Disposition'] = f'attachment; filename="{original_filename}"'
        response.headers['Content-Length'] = len(file_bytes)

        return response

    except Exception as e:
        add_log_entry(job_id, f"⚠️ Failed to download original file: {e}", "error")
        return jsonify({"error": f"Failed to download original file: {str(e)}"}), 500

# Initialize socket service with global handlers (only if SocketIO is enabled)
if socketio:
    socket_service.register_global_handlers(socketio)

# Socket endpoints for API management (only if SocketIO is enabled)
if socketio:
    @socketio.on('get_connection_stats')
    def handle_get_stats():
        """Get real-time connection statistics"""
        stats = socket_service.get_connection_stats()
        emit('connection_stats', stats)

    @socketio.on('cleanup_data')
    def handle_cleanup():
        """Trigger cleanup of old cached data"""
        socket_service.cleanup_old_data()
        emit('cleanup_complete', {'message': 'Data cleanup completed'})
else:
    # Dummy functions for when SocketIO is disabled
    def handle_get_stats():
        pass

    def handle_cleanup():
        pass

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 9999))  # Docker container port
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    print(f"🚀 Starting ApiUI Backend Server...")
    print(f"📡 Port: {port}")
    print(f"🔧 Debug mode: {debug}")
    print(f"🌐 Host: 0.0.0.0")

    if socketio:
        print("📡 Starting server with SocketIO support...")
        print(f"✅ Server starting on http://0.0.0.0:{port}")
        socketio.run(app, host='0.0.0.0', port=port, debug=debug)
    else:
        print("🌐 Starting server without SocketIO (HTTP-only mode)...")
        print(f"✅ Server starting on http://0.0.0.0:{port}")
        app.run(host='0.0.0.0', port=port, debug=debug)
