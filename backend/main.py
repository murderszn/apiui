from flask import Flask, request, jsonify, redirect, session, make_response, has_request_context
from flask_cors import CORS
import uuid
import os
import re
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
from services.cloud_metrics_service import CloudMetricsService
from services.mcp_service import mcp_service
from services.mcp_api_service import mcp_api_service

app = Flask(__name__)
app.secret_key = settings.secret_key
app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
app.config.setdefault("PERMANENT_SESSION_LIFETIME", 2592000)  # 30 days in seconds
app.config.setdefault("SESSION_PERMANENT", True)
cookie_secure = any(
    url and url.startswith("https://")
    for url in (settings.github_redirect_uri, settings.google_redirect_uri)
)
app.config.setdefault("SESSION_COOKIE_SECURE", cookie_secure)
cors_origins = [
    re.compile(r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$"),
    re.compile(r"^https?://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$"),
    re.compile(r"^https?://[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.local(:\d+)?$"),
    re.compile(r"^https?://[a-zA-Z0-9-]+\.ts\.net(:\d+)?$"),
    "https://apiui.web.app",
    "https://ai-apiui.web.app",
]
if settings.api_gateway_url:
    cors_origins.append(settings.api_gateway_url.rstrip("/"))
extra_cors = os.environ.get("CORS_ORIGINS", "")
for _origin in [o.strip() for o in extra_cors.split(",") if o.strip()]:
    cors_origins.append(_origin)

CORS(app,
     origins=cors_origins,
     supports_credentials=True,
     methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Mcp-Session-Id", "Accept"],
     expose_headers=["Content-Disposition", "Mcp-Session-Id"]
)

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

    if has_request_context():
        forwarded_host = request.headers.get('X-Forwarded-Host')
        forwarded_proto = request.headers.get('X-Forwarded-Proto')

        if forwarded_host:
            scheme = (forwarded_proto or request.scheme or 'http').split(',')[0].strip()
            host = forwarded_host.split(',')[0].strip()
            return f"{scheme}://{host}".rstrip('/')

        host_url = request.host_url.rstrip('/') if request.host_url else ''
        if host_url:
            return host_url

    host = settings.host if settings.host and settings.host != '0.0.0.0' else 'localhost'
    return f"http://{host}:{settings.port}"


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


@app.route("/auth/status", methods=["GET"])
def auth_status():
    """Check if user is currently authenticated"""
    auth_provider = session.get('auth_provider')
    auth_user = session.get('auth_user')
    github_user = session.get('github_user')
    google_user = session.get('google_user')

    if auth_provider and auth_user:
        return jsonify({
            "authenticated": True,
            "provider": auth_provider,
            "user": auth_user
        })
    elif github_user:
        return jsonify({
            "authenticated": True,
            "provider": "github",
            "user": github_user
        })
    elif google_user:
        return jsonify({
            "authenticated": True,
            "provider": "google",
            "user": google_user
        })
    else:
        return jsonify({
            "authenticated": False
        })


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

        # Normalize any legacy Cloud Run URLs in running_apis to self-hosted endpoints
        for api_id, api_info in list(running_apis.items()):
            existing_url = api_info.get("api_url", "")
            if not existing_url or ".run.app" in existing_url:
                api_info["api_url"] = build_external_url(f"/api/{api_id}")

        # Automatically register deployed jobs in running_apis
        for job_id, job_data in jobs.items():
            if job_data.get('status') == 'deployed' and job_id not in running_apis:
                running_apis[job_id] = {
                    "id": job_id,
                    "api_url": build_external_url(f"/api/{job_id}"),
                    "api_key": job_data.get("api_key"),
                    "started_at": job_data.get("completed_at", job_data.get("created_at")),
                    "port": None,
                    "process": None
                }
                print(f"Auto-registered deployed API: {job_id}")

        print(f"Total APIs after auto-registration: {len(running_apis)}")
        
        # Set MCP API service references after data is loaded
        print(f"[DEBUG] Setting MCP API service references: jobs={len(jobs)}, running_apis={len(running_apis)}")
        mcp_api_service.set_jobs_reference(jobs)
        mcp_api_service.set_running_apis_reference(running_apis)
        mcp_api_service.set_api_metadata_reference(api_metadata)
        print(f"MCP API service references updated with {len(jobs)} jobs, {len(running_apis)} running APIs")
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
    """Save job data atomically in a background daemon thread."""
    def _save():
        storage_service.save_persistent_data("jobs", jobs)
    thread = threading.Thread(target=_save, daemon=True)
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
cloud_metrics_service = CloudMetricsService()

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
        add_log_entry(job_id, "Activating self-hosted API...", "info")
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
                "api_url": build_external_url(f"/api/{job_id}"),
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
                "endpoint_url": build_external_url(f"/api/{job_id}"),
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


def _get_job_record(api_id: str):
    """Retrieve a job record for a generated API, loading persisted jobs if needed"""
    job = jobs.get(api_id)
    if job:
        return job

    try:
        persisted_jobs = storage_service.load_persistent_data("jobs") or {}
        if api_id in persisted_jobs:
            jobs[api_id] = persisted_jobs[api_id]
            return jobs[api_id]
    except Exception as e:
        print(f"Failed to load job record for {api_id}: {str(e)}")

    return None


def _normalize_records(records):
    """Ensure records are a list of dictionaries for serialization"""
    if not records:
        return []

    normalized = []
    for idx, item in enumerate(records, start=1):
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, (list, tuple)):
            normalized.append({f"column_{i+1}": value for i, value in enumerate(item)})
        else:
            normalized.append({"value": item, "index": idx})

    return normalized


def _serialize_records_to_csv(records):
    """Convert list of dict records into CSV bytes"""
    import csv
    import io

    normalized = _normalize_records(records)
    if not normalized:
        return b""

    fieldnames = []
    for record in normalized:
        for key in record.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for record in normalized:
        writer.writerow({field: record.get(field, '') for field in fieldnames})

    return buffer.getvalue().encode('utf-8')


def _determine_mime_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        '.csv': 'text/csv',
        '.json': 'application/json',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.parquet': 'application/octet-stream',
        '.txt': 'text/plain'
    }.get(ext, 'application/octet-stream')


def _build_download_response(content: bytes, filename: str, mime_type: str):
    response = make_response(content)
    response.headers['Content-Type'] = mime_type
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Content-Length'] = str(len(content))
    response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
    return response


@app.route('/v1/auth/log-login', methods=['POST'])
def log_user_login():
    """Log user login attempts to the database (never logging or storing plaintext passwords)."""
    try:
        login_data = request.get_json()

        if not login_data:
            return jsonify({"error": "No login data provided"}), 400

        # Validate required fields (never require or accept plaintext passwords)
        required_fields = ['email', 'login_time']
        for field in required_fields:
            if field not in login_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        sanitized_login_data = {
            k: v for k, v in login_data.items()
            if k not in ('password', 'pass', 'secret')
        }

        if not db_service.connected:
            print(f"ℹ️ Local login audit recorded for: {sanitized_login_data.get('email', 'unknown')}")
            return jsonify({"success": True, "message": "Login logged (local mode)", "storage": "local"}), 200

        # Log the login attempt using asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(db_service.log_user_login(sanitized_login_data))
            loop.close()
        except Exception as async_error:
            print(f"Async login logging failed: {async_error}")
            success = False

        if success:
            return jsonify({"success": True, "message": "Login logged successfully"}), 200
        else:
            return jsonify({"success": True, "message": "Login acknowledged (database unavailable)", "storage": "local"}), 200

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
        "api_url": build_external_url(f"/api/{job['id']}"),
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
                summary = api_metadata.get(api_id, {}).get('summary')

                api_info = {
                    "id": api_id,
                    "custom_name": custom_name,
                    "summary": summary,
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
                    process = api_info_running.get("process")
                    if process is None or process.poll() is None:
                        status = "running"
                        url = api_info_running.get("api_url") or api_info_running.get("url") or build_external_url(f"/api/{api_id}")
                        port = api_info_running.get("port")
                        started_at = api_info_running.get("started_at")
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

        # Also include APIs from running_apis that don't have files in storage
        for api_id, api_info_running in running_apis.items():
            # Skip if we already added this API from storage
            if any(api['id'] == api_id for api in apis):
                continue

            # Get custom name from metadata if available
            custom_name = api_metadata.get(api_id, {}).get('custom_name')
            summary = api_metadata.get(api_id, {}).get('summary')
            job_filename = jobs.get(api_id, {}).get('filename')

            # Add self-hosted API info
            api_info = {
                "id": api_id,
                "custom_name": custom_name,
                "summary": summary,
                "path": f"self-hosted://{api_id}",
                "created_at": api_info_running.get("started_at", datetime.utcnow().isoformat()),
                "has_main_py": False,
                "has_data_csv": True,
                "has_requirements": False,
                "status": "running",
                "url": build_external_url(f"/api/{api_id}"),
                "port": api_info_running.get("port"),
                "started_at": api_info_running.get("started_at"),
                "api_key": api_info_running.get("api_key"),
                "title": custom_name or job_filename or f"API {api_id[:8]}...",
                "models": ["DataModel"],
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
                    "url": build_external_url(f"/api/{job_id}"),
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
        api_path = os.path.join(settings.generated_apis_dir, api_id)
        if not os.path.exists(api_path):
            return jsonify({"error": "API not found"}), 404

        main_py_path = os.path.join(api_path, 'main.py')
        data_csv_path = os.path.join(api_path, 'data.csv')
        requirements_path = os.path.join(api_path, 'requirements.txt')

        if not os.path.exists(main_py_path):
            return jsonify({"error": "API main.py file not found"}), 404

        # Get custom name from metadata if available
        custom_name = api_metadata.get(api_id, {}).get('custom_name')
        summary = api_metadata.get(api_id, {}).get('summary')

        api_info = {
            "id": api_id,
            "custom_name": custom_name,
            "summary": summary,
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


@app.route('/v1/apis/<api_id>/download', methods=['GET'])
def download_generated_api_asset(api_id):
    """Download assets for a generated API (original file, CSV, JSON)"""
    try:
        format_option = (request.args.get('format') or 'original').lower()
        if format_option not in {'original', 'csv', 'json'}:
            return jsonify({"error": f"Unsupported format '{format_option}'"}), 400

        def load_dataset():
            csv_bytes = storage_service.get_generated_api_file_bytes(api_id, 'data.csv')
            if csv_bytes:
                try:
                    records = read_data_from_bytes(csv_bytes, '.csv')
                    if isinstance(records, dict) and records.get('error'):
                        raise ValueError(records['error'])
                    return records, '.csv', csv_bytes
                except Exception as csv_error:
                    print(f"Failed to parse stored CSV for {api_id}: {csv_error}")

            job_record = _get_job_record(api_id)
            if not job_record:
                return None, None, None

            file_path = job_record.get('file_path')
            if not file_path:
                return None, None, None

            file_bytes = storage_service.get_upload_file(file_path)
            if not file_bytes:
                return None, None, None

            source_ext = os.path.splitext(file_path)[1].lower() or '.csv'
            try:
                records = read_data_from_bytes(file_bytes, source_ext)
                if isinstance(records, dict) and records.get('error'):
                    raise ValueError(records['error'])
                return records, source_ext, file_bytes
            except Exception as original_error:
                print(f"Failed to parse original file for {api_id}: {original_error}")
                return None, None, None

        if format_option == 'original':
            job_record = _get_job_record(api_id)
            if not job_record:
                return jsonify({"error": "Original file not available for this API"}), 404

            file_path = job_record.get('file_path')
            if not file_path:
                return jsonify({"error": "Original file path missing for this API"}), 404

            file_bytes = storage_service.get_upload_file(file_path)
            if not file_bytes:
                return jsonify({"error": "Original file not found"}), 404

            filename = job_record.get('filename') or os.path.basename(file_path) or f"api_{api_id}_data"
            if '.' not in filename:
                filename = f"{filename}.dat"
            mime_type = _determine_mime_type(filename)
            return _build_download_response(file_bytes, filename, mime_type)

        records, source_ext, csv_bytes = load_dataset()
        if records is None:
            return jsonify({"error": "Dataset not available for this API"}), 404

        normalized_records = records
        if not isinstance(normalized_records, list):
            normalized_records = [normalized_records]
        if normalized_records and not isinstance(normalized_records[0], dict):
            normalized_records = _normalize_records(normalized_records)

        if format_option == 'json':
            json_payload = json.dumps(normalized_records, indent=2)
            return _build_download_response(json_payload.encode('utf-8'), f"{api_id}.json", 'application/json')

        if source_ext == '.csv' and csv_bytes:
            csv_payload = csv_bytes
        else:
            csv_payload = _serialize_records_to_csv(normalized_records)

        return _build_download_response(csv_payload, f"{api_id}.csv", 'text/csv')

    except Exception as e:
        return jsonify({"error": f"Failed to download asset: {str(e)}"}), 500


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
        print(f"Error updating API name: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/v1/apis/<api_id>/summary', methods=['PUT'])
def update_api_summary(api_id):
    global api_metadata
    """Update the custom summary for a specific API"""
    try:
        data = request.get_json()
        if not data or 'summary' not in data:
            return jsonify({"error": "summary field is required"}), 400

        summary = data['summary'].strip()
        if not summary:
            # If empty string, remove the custom summary
            if api_id in api_metadata and 'summary' in api_metadata[api_id]:
                del api_metadata[api_id]['summary']
        else:
            # Store the custom summary
            if api_id not in api_metadata:
                api_metadata[api_id] = {}
            api_metadata[api_id]['summary'] = summary

        # Save metadata persistently
        import asyncio
        asyncio.run(save_api_metadata_async())

        return jsonify({
            "success": True,
            "api_id": api_id,
            "summary": summary if summary else None
        })

    except Exception as e:
        print(f"Error updating API summary: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/v1/apis/<api_id>/start', methods=['POST'])
def start_api(api_id):
    """Start a generated API server"""
    try:
        api_path = os.path.join(settings.generated_apis_dir, api_id)
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
        api_path = os.path.join(settings.generated_apis_dir, api_id)
        if not os.path.exists(api_path):
            return jsonify({"error": "API not found"}), 404

        status = "stopped"
        url = None
        port = None
        started_at = None

        if api_id in running_apis:
            api_info = running_apis[api_id]
            process = api_info.get("process")

            # Check if process is still running (None means served directly by this backend)
            if process is None or process.poll() is None:
                status = "running"
                url = api_info.get("api_url") or api_info.get("url") or build_external_url(f"/api/{api_id}")
                port = api_info.get("port")
                started_at = api_info.get("started_at")
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
        api_path = os.path.join(settings.generated_apis_dir, api_id)
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
    """Health check endpoint - never 500s, reports self-hosted status."""
    storage_mode = "supabase" if supabase_service.connected else ("gcs" if storage_service.use_gcs else "local")
    storage_status = "available"
    overall_status = "healthy"

    try:
        if storage_service.use_gcs:
            list(storage_service.bucket.list_blobs(max_results=1))
        else:
            os.makedirs(storage_service.local_uploads_dir, exist_ok=True)
            if not os.path.isdir(storage_service.local_uploads_dir):
                storage_status = "unavailable"
                overall_status = "degraded"
    except Exception as e:
        storage_status = f"error: {str(e)}"
        overall_status = "degraded"

    try:
        db_connected = bool(settings.supabase_url and settings.supabase_anon_key and db_service.connected)
    except Exception:
        db_connected = False

    try:
        jobs_count = len(jobs)
    except Exception:
        jobs_count = 0

    try:
        apis_count = len(running_apis)
    except Exception:
        apis_count = 0

    return jsonify({
        "status": overall_status,
        "mode": "self-hosted",
        "self_hosted": True,
        "timestamp": datetime.utcnow().isoformat(),
        "storage_mode": storage_mode,
        "storage": {
            "mode": storage_mode,
            "type": "Supabase" if supabase_service.connected else ("GCS" if storage_service.use_gcs else "Local"),
            "status": storage_status
        },
        "database": {
            "type": "Supabase" if db_connected else "Local JSON",
            "status": "connected" if db_connected else "local_fallback"
        },
        "jobs_count": jobs_count,
        "loaded_jobs_count": jobs_count,
        "apis_count": apis_count,
        "running_apis_count": apis_count
    }), 200

@app.route('/v1/apis/<api_id>/metrics', methods=['GET'])
def get_api_metrics(api_id):
    """Get metrics data for an API for charting"""
    try:
        # First try to get real Cloud Run metrics
        if hasattr(settings, 'gcp_project_id') and settings.gcp_project_id:
            service_name = f"apiui-{api_id[:8]}"
            try:
                # Run async function in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cloud_metrics = loop.run_until_complete(
                    cloud_metrics_service.get_cloud_run_metrics(service_name, hours=24)
                )
                loop.close()

                # If we got real metrics with actual data, return them
                if cloud_metrics.get('source') == 'cloud_monitoring':
                    return jsonify(cloud_metrics)

            except Exception as e:
                print(f"Failed to fetch Cloud Run metrics for {api_id}: {str(e)}")
                # Fall back to in-memory metrics

        # Fall back to in-memory metrics if Cloud Run metrics fail or aren't available
        if api_id not in api_metrics:
            return jsonify({
                'hourly_data': [],
                'summary': {
                    'uptime_percentage': 100.0,
                    'avg_response_time': 0,
                    'total_requests': 0,
                    'error_rate': 0,
                    'last_updated': datetime.utcnow().isoformat()
                },
                'source': 'fallback'
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
            },
            'source': 'in_memory'
        })

    except Exception as e:
        print(f"Error in get_api_metrics for {api_id}: {str(e)}")
        return jsonify({
            'hourly_data': [],
            'summary': {
                'uptime_percentage': 100.0,
                'avg_response_time': 0,
                'total_requests': 0,
                'error_rate': 0,
                'last_updated': datetime.utcnow().isoformat()
            },
            'source': 'error',
            'error': str(e)
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

def _apply_query_params(records, args):
    """Filter, search, sort, and paginate a list of record dicts."""
    filtered = list(records)
    reserved = {'_search', '_sort', '_order', 'limit', '_limit', 'offset', '_offset'}

    # Map lowercase column names to actual keys across sampled records
    col_map = {}
    for row in filtered[:50]:
        if isinstance(row, dict):
            for k in row.keys():
                col_map.setdefault(str(k).lower(), k)

    # Column-level filtering for any non-reserved query param
    applied_filters = {}
    for key, val in args.items():
        if key in reserved or val == "":
            continue
        if col_map and key.lower() not in col_map:
            continue
        actual_col = col_map.get(key.lower(), key)
        applied_filters[actual_col] = val
        val_norm = str(val).strip().lower()
        next_rows = []
        for row in filtered:
            if not isinstance(row, dict):
                continue
            cell = row.get(actual_col)
            if cell is None:
                if val_norm in ("null", "none"):
                    next_rows.append(row)
                continue
            if str(cell).strip().lower() == val_norm:
                next_rows.append(row)
                continue
            try:
                if float(cell) == float(val):
                    next_rows.append(row)
            except (ValueError, TypeError):
                pass
        filtered = next_rows

    # Global case-insensitive substring search across all columns
    search_term = (args.get('_search') or '').strip().lower()
    if search_term:
        filtered = [
            row for row in filtered
            if isinstance(row, dict) and any(
                search_term in str(v).lower() for v in row.values() if v is not None
            )
        ]

    # Sorting (_sort and _order)
    sort_col_param = (args.get('_sort') or '').strip()
    sort_order = (args.get('_order') or 'asc').strip().lower()
    if sort_col_param and filtered:
        actual_sort_col = col_map.get(sort_col_param.lower(), sort_col_param)
        if actual_sort_col in col_map.values():
            reverse = (sort_order == 'desc')

            def _sort_key(row):
                v = row.get(actual_sort_col) if isinstance(row, dict) else None
                if v is None or v == "":
                    return (2, 0.0, "")
                try:
                    return (0, float(v), str(v))
                except (ValueError, TypeError):
                    return (1, 0.0, str(v).lower())

            filtered.sort(key=_sort_key, reverse=reverse)

    # Pagination (limit/_limit and offset/_offset)
    raw_limit = args.get('limit') if args.get('limit') is not None else args.get('_limit')
    raw_offset = args.get('offset') if args.get('offset') is not None else args.get('_offset')
    try:
        limit = max(0, int(raw_limit)) if raw_limit is not None else 100
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = max(0, int(raw_offset)) if raw_offset is not None else 0
    except (ValueError, TypeError):
        offset = 0

    total_count = len(filtered)
    paginated = filtered[offset:offset + limit] if limit > 0 else []

    return paginated, total_count, limit, offset, applied_filters, sort_col_param or None, sort_order


@app.route('/api/<job_id>', methods=['GET'])
@app.route('/api/<job_id>/data', methods=['GET'])
@app.route('/mock-api/<job_id>', methods=['GET'])
@app.route('/mock-api/<job_id>/data', methods=['GET'])
def mock_api_endpoint(job_id):
    """API endpoint that serves data from uploaded files with filtering, search, sorting, and pagination."""
    job = _get_job_record(job_id)
    if not job:
        return jsonify({"error": "API not found"}), 404

    schema = job.get("schema")

    # Always try to load real data from the uploaded file first
    file_data = []
    try:
        file_path = job.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            if job.get("filename"):
                reconstructed_path = f"uploads/{job_id}_{job.get('filename')}"
                add_log_entry(job_id, f"ℹ️ Reconstructing file path for legacy job: {reconstructed_path}")
                file_path = reconstructed_path
        if file_path:
            file_bytes = storage_service.get_upload_file(file_path)
            if file_bytes:
                file_ext = os.path.splitext(file_path)[1].lower()
                parsed = read_data_from_bytes(file_bytes, file_ext)
                if isinstance(parsed, list):
                    file_data = parsed
                    add_log_entry(job_id, f"✅ Loaded {len(file_data)} records from storage")
                else:
                    raise ValueError(parsed.get("error", "Invalid parsed data"))
            else:
                raise FileNotFoundError("File not found in storage")
        else:
            raise FileNotFoundError("File path not found in job")
    except Exception as e:
        if not schema:
            return jsonify({"error": "Schema and backing dataset not available"}), 404
        add_log_entry(job_id, f"⚠️ File not accessible ({str(e)}), using sample data")
        col_names = [col["name"] for col in schema.get("columns", [])]
        raw_samples = schema.get("sample_data") or []
        if raw_samples and col_names:
            for row_vals in raw_samples:
                if isinstance(row_vals, dict):
                    file_data.append(row_vals)
                elif isinstance(row_vals, list):
                    file_data.append({col_names[idx]: row_vals[idx] if idx < len(row_vals) else None for idx in range(len(col_names))})
        else:
            for i in range(min(10, schema.get("row_count", 10))):
                row = {}
                for col in schema.get("columns", []):
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

    filename = job.get('filename', f'api_{job_id[:8]}')
    if request.path.endswith('/data'):
        paginated_data, total_count, limit, offset, applied_filters, sort_col, sort_order = _apply_query_params(
            file_data, request.args
        )

        return jsonify({
            "data": paginated_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count,
            "filters": applied_filters,
            "sort": sort_col,
            "order": sort_order,
            "message": f"API serving data from {filename}",
            "ai_generated": job.get("generated_code") is not None
        })
    else:
        return jsonify({
            "message": f"API for {filename}",
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
    socket_service.set_jobs_reference(jobs)

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

# Set jobs reference for socket service (needed for HTTP chat endpoints)
socket_service.set_jobs_reference(jobs)

# Set references for MCP API service
mcp_api_service.set_jobs_reference(jobs)
mcp_api_service.set_running_apis_reference(running_apis)
mcp_api_service.set_api_metadata_reference(api_metadata)

# MCP (Model Context Protocol) endpoints
@app.route('/mcp/resources', methods=['GET'])
def get_mcp_resources():
    """List available MCP resources (uploaded files)"""
    try:
        # Run async function in sync context
        resources = asyncio.run(mcp_service.list_resources())

        # Convert to the format expected by the frontend
        result = {
            "resources": [
                {
                    "name": r.name,
                    "description": r.description,
                    "size": r.size,
                    "lastModified": r.last_modified
                } for r in resources
            ]
        }

        return jsonify(result)
    except Exception as e:
        print(f"Error in MCP resources endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/mcp/resources/<filename>', methods=['GET'])
def get_mcp_resource(filename):
    """Get a specific MCP resource (file content)"""
    try:
        # Construct URI from filename
        uri = f"file://{filename}"

        # Run async function in sync context
        content = asyncio.run(mcp_service.read_resource(uri))

        if content is None or "error" in content:
            return jsonify({"error": "File not found"}), 404

        return jsonify(content)
    except Exception as e:
        print(f"Error in MCP resource endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/mcp/ping', methods=['GET'])
def mcp_ping():
    """Simple ping endpoint to test deployment"""
    return jsonify({"status": "MCP endpoints deployed", "timestamp": datetime.utcnow().isoformat()})

# MCP API endpoints - Expose generated APIs as queryable resources
@app.route('/mcp/apis', methods=['GET'])
def get_mcp_apis():
    print(f"[DEBUG] MCP APIs endpoint hit at {datetime.utcnow()}")
    return get_mcp_apis_impl()

def get_mcp_apis_impl():
    """List all available APIs as MCP resources"""
    try:
        # Load persistent data first to ensure MCP API service has references
        print(f"[DEBUG] MCP APIs endpoint called")
        asyncio.run(load_persistent_data())
        print(f"[DEBUG] Data loaded, calling MCP API service")

        resources = asyncio.run(mcp_api_service.list_api_resources())
        print(f"[DEBUG] Got {len(resources)} resources from MCP API service")
        
        result = {
            "apis": [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "endpoint_url": r.endpoint_url,
                    "schema": r.schema,
                    "sample_data": r.sample_data,
                    "created_at": r.created_at,
                    "status": r.status
                } for r in resources
            ],
            "total": len(resources)
        }
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in MCP APIs endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/mcp/apis/<api_id>', methods=['GET'])
def get_mcp_api(api_id):
    """Get a specific API resource"""
    try:
        # Load persistent data first to ensure MCP API service has references
        asyncio.run(load_persistent_data())

        resource = asyncio.run(mcp_api_service.get_api_resource(api_id))
        
        if not resource:
            return jsonify({"error": "API not found"}), 404
        
        return jsonify({
            "id": resource.id,
            "name": resource.name,
            "description": resource.description,
            "endpoint_url": resource.endpoint_url,
            "schema": resource.schema,
            "sample_data": resource.sample_data,
            "created_at": resource.created_at,
            "status": resource.status
        })
    except Exception as e:
        print(f"Error in MCP API endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/mcp/apis/<api_id>/query', methods=['GET', 'POST'])
def query_mcp_api(api_id):
    """Query a specific API"""
    try:
        # Load persistent data first to ensure MCP API service has references
        asyncio.run(load_persistent_data())

        # Get query parameters from request
        query_params = {}

        if request.method == 'GET':
            query_params = dict(request.args)
        elif request.method == 'POST':
            query_params = request.get_json() or {}

        result = asyncio.run(mcp_api_service.query_api(api_id, query_params))
        
        return jsonify(result)
    except Exception as e:
        print(f"Error querying MCP API: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/mcp/apis/query-multiple', methods=['POST'])
def query_multiple_mcp_apis():
    """Query multiple APIs at once"""
    try:
        # Load persistent data first to ensure MCP API service has references
        asyncio.run(load_persistent_data())

        data = request.get_json() or {}
        api_ids = data.get('api_ids', [])
        query_params = data.get('query_params', {})

        if not api_ids:
            return jsonify({"error": "No API IDs provided"}), 400

        result = asyncio.run(mcp_api_service.query_multiple_apis(api_ids, query_params))
        
        return jsonify(result)
    except Exception as e:
        print(f"Error querying multiple APIs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/mcp/test', methods=['GET'])
def test_mcp_service():
    """Test MCP API service functionality"""
    try:
        print(f"[DEBUG] Test endpoint called")
        asyncio.run(load_persistent_data())

        if hasattr(mcp_api_service, 'jobs') and mcp_api_service.jobs:
            print(f"[DEBUG] MCP service has {len(mcp_api_service.jobs)} jobs")
        else:
            print(f"[DEBUG] MCP service has no jobs reference")

        if hasattr(mcp_api_service, 'running_apis') and mcp_api_service.running_apis:
            print(f"[DEBUG] MCP service has {len(mcp_api_service.running_apis)} running_apis")
        else:
            print(f"[DEBUG] MCP service has no running_apis reference")

        return jsonify({
            "jobs_count": len(mcp_api_service.jobs) if mcp_api_service.jobs else 0,
            "running_apis_count": len(mcp_api_service.running_apis) if mcp_api_service.running_apis else 0,
            "has_jobs_ref": hasattr(mcp_api_service, 'jobs') and mcp_api_service.jobs is not None,
            "has_running_apis_ref": hasattr(mcp_api_service, 'running_apis') and mcp_api_service.running_apis is not None
        })
    except Exception as e:
        print(f"[DEBUG] Test endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

# MCP Chat endpoint - Chat with APIs using AI
@app.route('/mcp/chat', methods=['POST'])
def mcp_chat():
    """Chat with selected APIs using AI"""
    try:
        # Load persistent data first to ensure MCP API service has references
        asyncio.run(load_persistent_data())

        data = request.get_json() or {}
        message = data.get('message', '')
        api_ids = data.get('api_ids', [])

        if not message:
            return jsonify({"error": "No message provided"}), 400

        if not api_ids:
            return jsonify({"error": "No APIs selected"}), 400
        
        # Get API resources
        api_resources = []
        for api_id in api_ids:
            resource = asyncio.run(mcp_api_service.get_api_resource(api_id))
            if resource:
                api_resources.append(resource)
        
        if not api_resources:
            return jsonify({"error": "No valid APIs found"}), 404
        
        # Build context for AI
        context = mcp_api_service.format_for_chat_context(api_resources)
        
        # Use AI service to generate response
        ai_service = AIService()

        # Build schema information combining all APIs
        combined_schema = {
            "row_count": 0,
            "columns": [],
            "api_details": [],
            "api_count": len(api_resources)
        }

        all_sample_data = []
        seen_columns = set()

        for resource in api_resources:
            schema = resource.schema or {}
            row_count = schema.get('row_count')
            if isinstance(row_count, (int, float)):
                combined_schema["row_count"] += int(row_count)

            combined_schema["api_details"].append({
                "id": resource.id,
                "name": resource.name,
                "description": resource.description,
                "row_count": row_count,
                "column_count": len(schema.get('columns', []) or []),
                "endpoint_url": resource.endpoint_url,
                "status": resource.status
            })

            for column in schema.get('columns', []) or []:
                col_name = column.get('name')
                if not col_name:
                    continue

                # Keep duplicate column names per API separate so context includes origin
                col_key = (resource.id, col_name)
                if col_key in seen_columns:
                    continue
                seen_columns.add(col_key)

                combined_schema["columns"].append({
                    "name": col_name,
                    "inferred_type": column.get('inferred_type'),
                    "nullable": column.get('nullable', False),
                    "source_api": resource.id,
                    "source_api_name": resource.name
                })

            # Annotate sample rows with their source so downstream responses can reference it
            annotated_samples = []
            for record in (resource.sample_data or [])[:3]:
                if isinstance(record, dict):
                    sample_record = {
                        "__api_id": resource.id,
                        "__api_name": resource.name,
                        **record
                    }
                else:
                    sample_record = {
                        "__api_id": resource.id,
                        "__api_name": resource.name,
                        "values": record
                    }
                annotated_samples.append(sample_record)

            if annotated_samples:
                all_sample_data.extend(annotated_samples)

        print(
            f"[MCP Chat] Message received for {len(api_resources)} API(s). "
            f"Combined rows: {combined_schema['row_count']}, "
            f"columns tracked: {len(combined_schema['columns'])}, "
            f"samples gathered: {len(all_sample_data)}"
        )

        response = asyncio.run(
            ai_service.chat_with_data(
                f"{context}\n\nUser question: {message}",
                combined_schema,
                all_sample_data
            )
        )
        
        return jsonify({
            "success": True,
            "message": response,
            "apis_used": [r.id for r in api_resources],
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f"Error in MCP chat: {e}")
        return jsonify({"error": str(e)}), 500

# GitHub Contributions Update Endpoint
@app.route('/api/github/contributions/update', methods=['POST'])
def update_github_contributions():
    """Update GitHub contributions data and refresh the resume"""
    try:
        import os
        import json
        import subprocess
        import tempfile

        # Get GitHub token from environment
        github_token = os.getenv('GITHUB_TOKEN') or os.getenv('PERSONAL_ACCESS_TOKEN')
        if not github_token:
            return jsonify({"error": "GitHub token not configured"}), 500

        # GitHub GraphQL query
        query = """
        query {
            user(login: "murderszn") {
                contributionsCollection {
                    contributionCalendar {
                        totalContributions
                        weeks {
                            contributionDays {
                                contributionCount
                                date
                            }
                        }
                    }
                }
            }
        }"""

        # Make GraphQL request
        response = httpx.post(
            'https://api.github.com/graphql',
            headers={
                'Authorization': f'Bearer {github_token}',
                'Content-Type': 'application/json'
            },
            json={'query': query}
        )

        if response.status_code != 200:
            return jsonify({"error": f"GitHub API error: {response.status_code}"}), 500

        data = response.json()

        if 'errors' in data:
            return jsonify({"error": f"GraphQL errors: {data['errors']}"}), 500

        # Extract contributions data
        weeks = data['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
        contributions = []
        for week in weeks:
            for day in week['contributionDays']:
                contributions.append({
                    'date': day['date'],
                    'count': day['contributionCount']
                })

        total_contributions = sum(c['count'] for c in contributions)

        # Create JavaScript data file
        js_content = f"// Static GitHub contributions data (fetched {datetime.utcnow().strftime('%Y-%m-%d')})\n"
        js_content += "function getStaticContributions() {\n"
        js_content += f"    return {json.dumps(contributions, indent=12)};\n"
        js_content += "}\n"

        # Write to frontend data file
        frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')
        data_file = os.path.join(frontend_dir, 'github-contributions-data.js')
        with open(data_file, 'w') as f:
            f.write(js_content)

        # Update resume.html
        resume_file = os.path.join(frontend_dir, 'resume.html')
        with open(resume_file, 'r') as f:
            resume_content = f.read()

        # Find and replace the getStaticContributions function
        import re
        pattern = r'function getStaticContributions\(\) \{\s*return \[[\s\S]*?\];\s*\}'
        new_function = f'function getStaticContributions() {{\n            return {json.dumps(contributions, indent=12)};\n        }}'

        if re.search(pattern, resume_content):
            resume_content = re.sub(pattern, new_function, resume_content)

            # Write updated resume
            with open(resume_file, 'w') as f:
                f.write(resume_content)

        return jsonify({
            "success": True,
            "message": f"Updated GitHub contributions: {total_contributions} total contributions",
            "total_contributions": total_contributions,
            "days_processed": len(contributions),
            "last_updated": datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"Error updating GitHub contributions: {e}")
        return jsonify({"error": str(e)}), 500

# Load persistent data on startup so jobs, running_apis, and MCP services are ready immediately
try:
    asyncio.run(load_persistent_data())
except Exception as e:
    print(f"⚠️ Failed initial persistent data load: {e}")

try:
    from services.mcp_protocol import register_mcp_routes
    register_mcp_routes(app, load_persistent_data)
    print("✅ Registered spec-compliant MCP protocol routes")
except Exception as e:
    print(f"⚠️ Could not register MCP protocol routes: {e}")

if __name__ == '__main__':
    host = os.environ.get('HOST', settings.host or '0.0.0.0')
    port = int(os.environ.get('PORT', settings.port or 8000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    print(f"🚀 Starting ApiUI Self-Hosted Backend Server...")
    print(f"📡 Port: {port}")
    print(f"🔧 Debug mode: {debug}")
    print(f"🌐 Host: {host}")

    if socketio:
        print("📡 Starting server with SocketIO support...")
        print(f"✅ Server starting on http://{host}:{port}")
        socketio.run(app, host=host, port=port, debug=debug)
    else:
        print("🌐 Starting server (threaded HTTP mode)...")
        print(f"✅ Server starting on http://{host}:{port}")
        app.run(host=host, port=port, debug=debug, threaded=True)
