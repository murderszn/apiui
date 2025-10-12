# ApiUI Architecture Documentation

## System Overview

ApiUI is a serverless platform that converts data files into production-ready REST APIs using AI-generated code deployed on Google Cloud Run.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              APIUI ARCHITECTURE                              │
└─────────────────────────────────────────────────────────────────────────────┘

                                   ┌──────────┐
                                   │  USER/   │
                                   │ FRONTEND │
                                   └─────┬────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
          Upload File              Query APIs              Chat with APIs
          (CSV/JSON/              (/api/{id})            (/mcp/chat)
           XLSX/Parquet)
                 │                       │                       │
                 ▼                       ▼                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         FLASK BACKEND (main.py)                            │
│                           Port 9999 (Docker)                               │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ File Upload  │  │ AI Service   │  │ Deployment   │  │ MCP Service  │ │
│  │ /v1/generate │  │ (OpenAI GPT) │  │ Service      │  │ /mcp/apis    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                 │                  │                  │         │
│         ▼                 ▼                  ▼                  ▼         │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    IN-MEMORY STATE LAYER                            │ │
│  │  • jobs{}         - All generation jobs & metadata                  │ │
│  │  • running_apis{} - Active Cloud Run deployments                    │ │
│  │  • api_metadata{} - Custom names/descriptions                       │ │
│  │  • api_metrics{}  - Request metrics & analytics                     │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└─────┬──────────────────────┬──────────────────────┬─────────────────┬─────┘
      │                      │                      │                 │
      │                      │                      │                 │
      ▼                      ▼                      ▼                 ▼
┌──────────┐        ┌─────────────────┐    ┌──────────────┐   ┌──────────┐
│  Google  │        │   Google Cloud  │    │  Supabase    │   │ Socket   │
│  Cloud   │        │   Run Services  │    │  Database    │   │ Service  │
│ Storage  │        │                 │    │ (Optional)   │   │ (Chat)   │
│  (GCS)   │        └─────────────────┘    └──────────────┘   └──────────┘
└────┬─────┘                 │                      │
     │                       │                      │
     │                       │                      │
     ▼                       ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENT STORAGE                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  GCS BUCKETS / LOCAL FILESYSTEM:                            │
│  ├─ uploads/                                                │
│  │  └─ {job_id}_{filename}        (Original files)         │
│  │                                                          │
│  ├─ generated_apis/                                         │
│  │  └─ {job_id}/                                           │
│  │     ├─ main.py                  (Generated FastAPI)     │
│  │     ├─ requirements.txt         (Dependencies)          │
│  │     ├─ dockerfile               (Container config)      │
│  │     └─ data.csv                 (Normalized data)       │
│  │                                                          │
│  └─ persistent_data/                                        │
│     ├─ jobs.json                   (Job state)             │
│     ├─ api_states.json             (Running APIs)          │
│     └─ api_metadata.json           (Custom metadata)       │
│                                                              │
│  SUPABASE TABLES:                                           │
│  ├─ apis                           (API records)            │
│  ├─ user_login_logs               (Auth logs)              │
│  └─ users                         (User accounts)          │
└──────────────────────────────────────────────────────────────┘
```

---

## Deployment Flow

```
═══════════════════════════════════════════════════════════════
                    DEPLOYMENT FLOW DIAGRAM
═══════════════════════════════════════════════════════════════

    1. FILE UPLOAD
       │
       ├──> Save to GCS: uploads/{job_id}_{filename}
       ├──> Analyze schema (CSV/JSON/XLSX/Parquet)
       └──> Create job record
            │
            ▼
    2. AI CODE GENERATION (OpenAI GPT-4)
       │
       ├──> Generate main.py (FastAPI app)
       ├──> Generate requirements.txt
       ├──> Generate dockerfile
       └──> Save to: generated_apis/{job_id}/
            │
            ▼
    3. CLOUD RUN DEPLOYMENT
       │
       ├──> Build Docker container
       ├──> Push to Google Container Registry
       ├──> Deploy as Cloud Run service
       └──> Service name: apiui-{job_id[:8]}
            │
            ▼
    4. LIVE API (Cloud Run)
       │
       ├──> Public URL: https://apiui-{id}-{hash}.run.app
       ├──> Endpoints:
       │    ├─ GET /data       (paginated records)
       │    ├─ GET /schema     (column info)
       │    └─ GET /code       (view source)
       │
       └──> Proxied through: /api/{job_id}/*
```

---

## Request Flow Examples

### Example 1: Query API Data
```
User → GET /api/{job_id}/data?limit=100
     ↓
Backend checks running_apis[job_id]
     ↓
Routes to Cloud Run service OR local mock
     ↓
Reads data from embedded file in container
     ↓
Returns JSON: {data: [...], total_count: N}
```

### Example 2: Chat with API
```
User → POST /mcp/chat 
       {message: "Show me sales over $1000",
        api_ids: ["abc-123"]}
     ↓
Load API schema and sample data
     ↓
Send to OpenAI with context
     ↓
AI interprets query and formats response
     ↓
Returns: Natural language answer + data
```

### Example 3: List All APIs
```
User → GET /v1/apis
     ↓
Load persistent data (jobs, running_apis)
     ↓
Combine with GCS-stored APIs
     ↓
Query Supabase for user's APIs (optional)
     ↓
Returns: [{id, name, status, endpoints}]
```

---

## Key Components

### Backend Services (`backend/services/`)

| Service | Purpose |
|---------|---------|
| `ai_service.py` | OpenAI GPT-4 integration for code generation |
| `storage_service.py` | GCS/Local file management abstraction |
| `deployment_service.py` | Cloud Run deployments and management |
| `supabase_service.py` | Database connection and authentication |
| `mcp_api_service.py` | Model Context Protocol resource exposure |
| `socket_service.py` | WebSocket chat (currently disabled) |
| `cloud_metrics_service.py` | Cloud Run metrics and monitoring |

### API Endpoints

#### Core Generation
- `POST /v1/generate` - Upload file and create API
- `GET /v1/generate/status/{job_id}` - Check generation progress

#### API Management
- `GET /v1/apis` - List all generated APIs
- `GET /v1/apis/{api_id}` - Get API details
- `PUT /v1/apis/{api_id}/name` - Update custom name
- `PUT /v1/apis/{api_id}/summary` - Update description
- `DELETE /v1/apis/{api_id}` - Delete API
- `GET /v1/apis/{api_id}/metrics` - Get analytics
- `GET /v1/apis/{api_id}/download` - Download API assets

#### API Proxy (Routes to Cloud Run)
- `GET /api/{job_id}` - API info
- `GET /api/{job_id}/data` - Query data with pagination
- `GET /api/{job_id}/schema` - Get data schema
- `GET /api/{job_id}/code` - View generated code
- `POST /api/{job_id}/run` - Test API

#### Model Context Protocol (MCP)
- `GET /mcp/apis` - List APIs as MCP resources
- `GET /mcp/apis/{api_id}` - Get API resource details
- `GET /mcp/apis/{api_id}/query` - Query API via MCP
- `POST /mcp/chat` - Chat with multiple APIs using AI

#### Authentication
- `GET /auth/github/login` - GitHub OAuth
- `GET /auth/google/login` - Google OAuth
- `POST /auth/supabase/signup` - Email/password signup
- `POST /auth/supabase/signin` - Email/password signin
- `GET /auth/session` - Check auth status

#### Health & Monitoring
- `GET /health` - Service health check
- `GET /v1/analytics/requests` - Total request count

---

## Data Flow Architecture

### File-Based Storage
**ApiUI does NOT use traditional database tables for data storage.** Instead:

1. **Original files** are stored in GCS/filesystem
2. **Generated APIs** serve data directly from embedded files
3. **Each API** is a self-contained FastAPI application
4. **Data persists** in the container filesystem on Cloud Run

### State Persistence
In-memory state is persisted to JSON files in GCS:
- `jobs.json` - All generation jobs
- `api_states.json` - Running API registry
- `api_metadata.json` - Custom names and descriptions

### Optional Supabase Usage
Supabase is used for:
- User authentication
- Login logs
- API registry (metadata only, not data)

---

## Technology Stack

### Backend
- **Framework**: Flask (Python)
- **AI**: OpenAI GPT-4
- **Storage**: Google Cloud Storage
- **Deployment**: Google Cloud Run
- **Container**: Docker
- **Database**: Supabase (optional)

### Generated APIs
- **Framework**: FastAPI (generated by AI)
- **Runtime**: Python 3.x
- **Container**: Docker
- **Platform**: Google Cloud Run

### Frontend
- **Stack**: Vanilla JavaScript, HTML, CSS
- **Hosting**: Firebase Hosting
- **UI**: Custom responsive design

---

## Key Architectural Decisions

### 1. File-Based vs Database
**Choice**: Store data in files, serve directly
**Rationale**: 
- Simplicity for rapid prototyping
- No database setup required
- Self-contained deployments
- Easy to download and migrate

### 2. Serverless Deployment
**Choice**: Google Cloud Run
**Rationale**:
- Auto-scaling from 0 to N instances
- Pay only for actual usage
- Built-in HTTPS and domains
- No server management

### 3. AI Code Generation
**Choice**: GPT-4 generates FastAPI code
**Rationale**:
- Production-ready code
- Follows best practices
- Customizable and readable
- Users can modify generated code

### 4. Proxy Architecture
**Choice**: Backend proxies requests to Cloud Run services
**Rationale**:
- Centralized authentication
- Request tracking and metrics
- Unified API namespace
- Easy API management

### 5. In-Memory State with Persistence
**Choice**: Keep state in memory, periodically save to GCS
**Rationale**:
- Fast access
- Simple implementation
- Survives backend restarts
- No database overhead for metadata

---

## Scalability Considerations

### Current Limitations
- In-memory state limits horizontal scaling of backend
- File size limits for uploads (typically ~100MB)
- No sharding or distributed state

### Future Improvements
- Redis for distributed state
- Database for large datasets
- CDN for static assets
- Message queue for async processing

---

## Security Features

1. **API Keys**: Each generated API has unique key
2. **OAuth**: GitHub and Google authentication
3. **CORS**: Configured for specific origins
4. **Cloud Run**: Automatic HTTPS and isolation
5. **Supabase**: Row-level security policies

---

## Monitoring & Observability

### Metrics Tracked
- Request counts per API
- Response times
- Error rates
- Uptime percentage

### Data Sources
1. **In-memory**: Request middleware tracking
2. **Cloud Run**: Google Cloud Monitoring API
3. **Logs**: Backend logging for debugging

---

## Development Workflow

```
Local Development:
  ├─ Backend: Python Flask on port 9999
  ├─ Frontend: Firebase serve on port 5000
  └─ APIs: Mock endpoints in backend

Production:
  ├─ Backend: Docker container on Cloud Run
  ├─ Frontend: Firebase Hosting (CDN)
  └─ APIs: Individual Cloud Run services
```

---

## File Formats Supported

- **CSV** - Comma-separated values
- **JSON** - Array of objects
- **XLSX** - Excel spreadsheets
- **XLS** - Legacy Excel format
- **Parquet** - Columnar storage format
- **TXT** - Plain text (treated as CSV)

---

## Environment Variables

See `.env.example` or deployment documentation for:
- `OPENAI_API_KEY` - AI code generation
- `GCP_PROJECT_ID` - Google Cloud project
- `GOOGLE_APPLICATION_CREDENTIALS` - GCS access
- `SUPABASE_URL` - Database URL
- `SUPABASE_ANON_KEY` - Public API key
- OAuth credentials (GitHub, Google)

---

## Related Documentation

- `README.md` - Main project documentation
- `CLOUD_RUN_DEPLOYMENT.md` - Deployment guide
- `MCP_CHAT_README.md` - MCP integration details
- `README-Chat-Setup.md` - Chat feature setup

---

**Last Updated**: 2025-10-12  
**Version**: 1.0

