# apiui

**🚀 Persistent API Generation Platform**

Generate REST APIs from CSV/Excel files with persistent storage and Cloud Run deployment.

## 🎯 Key Features

- **🔄 Persistent APIs**: APIs remain available after container restarts
- **☁️ Cloud Storage**: Google Cloud Storage, Supabase Storage, and local storage options
- **🗄️ Database Support**: MongoDB Atlas and Supabase PostgreSQL integration
- **🤖 AI-Powered**: OpenAI GPT-4 integration for intelligent API generation and chat
- **💬 Real-time Chat**: Socket.io-powered chat interface for natural language API queries
- **🔐 Authentication**: GitHub OAuth, Google OAuth, and Supabase Auth integration
- **🐳 Container Ready**: Optimized for Cloud Run, Docker Compose, and Kubernetes
- **🚀 Multi-Platform Deployment**: Firebase, Vercel, Netlify, and custom deployments
- **📊 Multi-Format Support**: CSV, JSON, Excel, Parquet, and text files
- **📈 Monitoring & Analytics**: Built-in metrics, health checks, and performance monitoring

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   Chat Server   │    │   Storage       │
│   (HTML/JS)     │◄──►│   (FastAPI)     │◄──►│   (Node.js)     │◄──►│   (GCS/MongoDB)│
│                 │    │                 │    │                 │    │                 │
│ • File Upload   │    │ • API Generation│    │ • Real-time Chat│    │ • File Storage  │
│ • API Testing   │    │ • Job Management│    │ • AI Responses  │    │ • Metadata      │
│ • Chat Interface│    │ • Auth (OAuth)  │    │ • Socket.io     │    │ • Persistence   │
│ • Documentation │    │ • Mock Endpoints│    │ • HTTP Fallback │    │ • Supabase      │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### 1. Prerequisites
- **Required**: OpenAI API Key (for AI features)
- **Storage Options** (choose one):
  - Google Cloud Account (for GCS storage)
  - Supabase Account (for Supabase storage)
  - Local development (filesystem storage)
- **Database Options** (choose one):
  - MongoDB Atlas account
  - Supabase account (includes PostgreSQL)
- **Deployment Options** (choose one):
  - Docker and Docker Compose (recommended)
  - Google Cloud Run
  - Firebase Hosting + Cloud Functions
  - Vercel/Netlify (static deployment)
- **Authentication** (optional):
  - GitHub OAuth App
  - Google OAuth credentials
  - Supabase project

### 2. Quick Setup with Docker Compose (Recommended)
```bash
# Clone and navigate to the project
cd /Users/jahflyx/apiui

# Set your OpenAI API key
export OPENAI_API_KEY='your-openai-api-key-here'

# Start all services (backend, chat server, MongoDB)
docker-compose up -d

# Access the application:
# - Frontend: http://localhost:8080
# - Backend API: http://localhost:8000
# - Chat Server: http://localhost:3001
# - API Documentation: http://localhost:8000/docs
```

### 3. Alternative Setup Options

#### Google Cloud Run Deployment
```bash
# Configure your project ID
export PROJECT_ID=your-gcp-project-id

# Run GCP setup script
./setup-gcp.sh

# Deploy to Cloud Run
./deploy-cloud-run.sh
```

#### Firebase Deployment
```bash
# Set up Firebase project
firebase login
firebase init

# Deploy frontend to Firebase Hosting
./deploy-firebase.sh
```

#### Local Development
```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

# Chat server setup (in another terminal)
cd chat-server
npm install
npm run chat-dev

# Frontend (in another terminal)
cd frontend
python -m http.server 8080
```

## 🔧 Configuration

### Environment Variables
```bash
# Required
OPENAI_API_KEY=your-openai-api-key

# Storage Options (choose one)
USE_GCS_STORAGE=True              # Google Cloud Storage (production)
GCS_BUCKET_NAME=your-bucket-name

USE_SUPABASE_STORAGE=True         # Supabase Storage (alternative)
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-key

USE_LOCAL_STORAGE=True            # Local filesystem (development only)

# Database Options (choose one)
MONGODB_URL=mongodb+srv://...     # MongoDB Atlas
DATABASE_NAME=apiui

# Supabase Database (alternative to MongoDB)
SUPABASE_DB_URL=postgresql://...  # If using Supabase PostgreSQL

# Authentication (optional)
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-secret
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-secret

# Chat Server Configuration
CHAT_PORT=3001
FLASK_BACKEND_URL=http://localhost:8000

# Application Settings
DEBUG=False
PORT=8000
SECRET_KEY=your-secret-key-here
```

### Storage Options

1. **Google Cloud Storage (Production)**:
   - Persistent across container restarts
   - Scalable and reliable
   - Recommended for production

2. **Local Storage (Development)**:
   - Files stored in container filesystem
   - Lost on container restart
   - Good for development/testing

### Database Options

1. **MongoDB Atlas (Recommended)**:
   - Full metadata persistence
   - Cross-container state management
   - Best for production

2. **Storage-Only (Fallback)**:
   - Uses GCS/Local for persistence
   - No database required
   - Simpler setup

## 📡 API Endpoints

### Core Endpoints
- `POST /v1/generate` - Upload file and generate API
- `GET /v1/generate/status/<job_id>` - Check generation status
- `GET /v1/apis` - List all generated APIs
- `GET /v1/apis/<api_id>` - Get API details
- `GET /mock-api/<job_id>/data` - Access generated API data (immediate)
- `GET /api/<job_id>/data` - Access deployed API data

### API Management
- `POST /v1/apis/<api_id>/start` - Start a stopped API
- `POST /v1/apis/<api_id>/stop` - Stop a running API
- `DELETE /v1/apis/<api_id>` - Delete an API
- `GET /v1/apis/<api_id>/status` - Get API running status
- `GET /v1/apis/<api_id>/docs` - Get API documentation
- `GET /v1/apis/<api_id>/metrics` - Get API usage metrics

### Chat & AI Features
- `POST /v1/chat` - Send chat messages (HTTP fallback)
- `WebSocket /socket.io/` - Real-time chat connection
- `GET /v1/apis/chat-enabled` - List APIs available for chat

### Authentication
- `GET /auth/github/login` - GitHub OAuth login
- `GET /auth/google/login` - Google OAuth login
- `POST /auth/supabase/signup` - Supabase user registration
- `POST /auth/supabase/signin` - Supabase user login
- `GET /auth/session` - Check current session
- `POST /auth/logout` - Logout user

### Health & Monitoring
- `GET /health` - Comprehensive health check with storage/database status

### Chat Server Endpoints (Port 3001)
- `GET /health` - Chat server health check
- `GET /api/apis` - List available APIs (proxied from backend)
- `POST /api/chat` - HTTP chat endpoint
- `WebSocket /` - Real-time Socket.io chat connection

## 🔍 Troubleshooting

### Common Issues

**APIs disappear after restart**:
- Ensure `USE_GCS_STORAGE=True` and bucket is configured
- Check MongoDB connection if using database

**File upload fails**:
- Verify GCS bucket permissions
- Check service account has `storage.objectAdmin` role

**Database connection issues**:
- Verify MongoDB Atlas connection string
- Check network connectivity and firewall rules

### Health Check
Check system status:
```bash
curl https://your-service-url/health
```

Expected response:
```json
{
  "status": "healthy",
  "storage": {"type": "GCS", "status": "available"},
  "database": {"type": "MongoDB", "status": "connected"},
  "jobs_count": 5,
  "apis_count": 3
}
```

## 🏗️ Development

### Local Development
```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py

# Frontend (separate terminal)
cd frontend
python -m http.server 8000
```

### Docker Development
```bash
# Build and run
docker build -f docker/backend.Dockerfile -t apiui-backend .
docker run -p 9999:9999 apiui-backend
```

## 🚀 Deployment

### Cloud Run (Recommended)
```bash
# Automated deployment
./deploy-cloud-run.sh

# Manual deployment
gcloud run deploy apiui-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --set-env-vars="OPENAI_API_KEY=your-key,USE_GCS_STORAGE=True"
```

### Other Platforms
The application supports deployment to multiple platforms:

#### Serverless & Cloud Platforms
- **Google Cloud Run**: Containerized deployment with auto-scaling
- **AWS Fargate**: Serverless container execution
- **Azure Container Instances**: Container deployment in Azure
- **Google App Engine**: Traditional PaaS deployment

#### Static Hosting + Functions
- **Firebase Hosting + Cloud Functions**: Frontend on Firebase, backend on Cloud Functions
- **Vercel**: Serverless functions with static frontend hosting
- **Netlify**: Static site hosting with serverless functions

#### Container Orchestration
- **Kubernetes**: Full container orchestration with Helm charts
- **Docker Swarm**: Native Docker clustering
- **Amazon ECS**: AWS container orchestration

#### Traditional Hosting
- **Heroku**: Git-based deployment
- **DigitalOcean App Platform**: Cloud-native deployment
- **Railway**: Infrastructure from code

## 📊 Monitoring

### Cloud Run Logs
```bash
gcloud logging read "resource.type=cloud_run_revision" --limit=50
```

### Storage Monitoring
```bash
# Check bucket contents
gsutil ls gs://your-bucket-name/

# View bucket usage
gsutil du -sh gs://your-bucket-name/
```

## 🔒 Security

### Best Practices
- Use environment variables for secrets
- Enable Cloud Run authentication for production
- Set up VPC for database access
- Configure CORS for your frontend domain
- Use service accounts with minimal permissions

### IAM Permissions Required
- `storage.objectAdmin` - GCS bucket access
- `run.invoker` - Cloud Run invocation
- MongoDB Atlas network access

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with both local and GCS storage
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/apiui/issues)
- **Documentation**: [Cloud Run Deployment Guide](CLOUD_RUN_DEPLOYMENT.md)
- **Health Check**: `/health` endpoint for system status

---

**🎉 Your APIs are now persistent and production-ready!**

**Turn your data files into production-ready APIs with AI-generated FastAPI applications**

apiui is a platform that automatically generates secure, scalable REST APIs from your data files (CSV, JSON, Excel, Parquet) using artificial intelligence. Upload your data, and get a fully functional API with pagination, filtering, and sorting capabilities.

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- MongoDB (for local development)

### Using Docker Compose (Recommended)

1. **Clone and navigate to the project:**
   ```bash
   cd /Users/jahflyx/apiui
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

3. **Open your browser:**
   - Frontend: http://localhost:8080
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

4. **Upload a data file** through the web interface and watch your API get generated!

### Local Development Setup

1. **Set up Python environment:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Start MongoDB:**
   ```bash
   # Using Docker
   docker run -d -p 27017:27017 --name mongodb mongo:7.0

   # Or install MongoDB locally
   ```

3. **Configure environment:**
   ```bash
   cp env.example .env
   # Edit .env with your configuration
   ```

4. **Run the backend:**
   ```bash
   uvicorn main:app --reload
   ```

5. **Open the frontend:**
   ```bash
   # Simply open frontend/index.html in your browser
   # Or serve it with a local server
   python -m http.server 8080
   ```

## 📁 Project Structure

```
apiui/
├── backend/                    # FastAPI backend
│   ├── main.py                # Main application with all endpoints
│   ├── app.py                 # Alternative FastAPI app entry point
│   ├── core/                  # Core functionality
│   │   ├── config.py          # Configuration management
│   │   └── database.py        # Database connection
│   ├── models/                # Pydantic models
│   │   └── job.py             # Job status model
│   ├── services/              # Business logic services
│   │   ├── ai_service.py      # OpenAI integration for code generation
│   │   ├── database_service.py # Database operations
│   │   ├── deployment_service.py # Container deployment
│   │   ├── file_service.py    # File processing and validation
│   │   ├── storage_service.py # GCS, Supabase, and local storage
│   │   ├── supabase_service.py # Supabase integration
│   │   └── socket_service.py  # WebSocket services
│   ├── requirements.txt       # Python dependencies
│   ├── env.example           # Environment variables template
│   └── venv/                 # Python virtual environment
├── chat-server/              # Node.js chat server
│   ├── server.js             # Socket.io chat server
│   ├── README.md             # Chat server documentation
│   └── package.json          # Node.js dependencies
├── frontend/                 # Web interface
│   ├── index.html            # Main application interface
│   ├── docs.html             # Documentation page
│   ├── api-hub.html          # API management interface
│   ├── socket-chat.html      # Chat interface
│   ├── api-docs.html         # API documentation viewer
│   └── dist/                 # Built assets
├── docker/                   # Docker configurations
│   ├── backend.Dockerfile    # Backend container
│   ├── cloudrun.Dockerfile   # Cloud Run optimized
│   ├── frontend.Dockerfile   # Frontend container
│   ├── nginx.conf           # Nginx configuration
│   └── mongo-init/          # MongoDB initialization
├── functions/                # Firebase Cloud Functions
│   ├── index.js             # Cloud Functions code
│   └── package.json         # Dependencies
├── firebase.json            # Firebase configuration
├── docker-compose.yml       # Multi-service development environment
├── deploy-*.sh              # Deployment scripts for various platforms
├── setup-gcp.sh            # GCP resource setup
├── supabase-setup.sql      # Supabase database schema
├── test_*.py               # Backend tests
├── test_*.js               # Frontend tests
└── README.md               # This file
```

## 🛠️ Architecture Overview

### Core Components

1. **File Processing Service**
   - Supports CSV, JSON, Excel, Parquet, and text files
   - Automatic schema inference with intelligent data type detection
   - Sample data extraction for AI context and validation

2. **AI Code Generation & Chat**
   - OpenAI GPT-4 integration for intelligent API code generation
   - Real-time chat interface powered by Socket.io
   - Natural language queries for data exploration
   - Context-aware responses using API schemas and data

3. **Multi-Storage Backend**
   - Google Cloud Storage for production persistence
   - Supabase Storage as an alternative cloud storage
   - Local filesystem storage for development
   - MongoDB Atlas and Supabase PostgreSQL database options

4. **Authentication & Security**
   - GitHub OAuth, Google OAuth, and Supabase Auth
   - API key authentication for generated APIs
   - JWT tokens and session management
   - CORS protection and rate limiting

5. **Deployment & Orchestration**
   - Docker Compose for local development
   - Cloud Run, Firebase, Vercel, and Netlify deployment
   - Kubernetes and container orchestration support
   - Multi-platform deployment scripts

6. **Web Interface & API Hub**
   - Drag-and-drop file upload with progress tracking
   - Real-time status updates and API management
   - Interactive chat interface for data exploration
   - Comprehensive documentation and testing tools
   - API metrics and monitoring dashboard

## 🔧 Configuration

### Environment Variables

Copy `backend/env.example` to `backend/.env` and configure:

```env
# Database
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=apiui

# AI Services (choose one)
OPENAI_API_KEY=your-openai-api-key
GOOGLE_AI_API_KEY=your-google-ai-api-key

# Cloud Deployment
GCP_PROJECT_ID=your-gcp-project-id
GCS_BUCKET_NAME=apiui-files
```

### Supported File Formats

- **CSV**: Comma-separated values with automatic delimiter detection
- **JSON**: JSON arrays or single objects
- **Excel**: .xlsx and .xls files
- **Parquet**: Columnar storage format

## 🚀 API Usage

### Generate an API

```bash
curl -X POST "http://localhost:8000/v1/generate" \
     -F "file=@your-data.csv"
```

Response:
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "accepted",
  "message": "API generation started successfully"
}
```

### Check Status

```bash
curl "http://localhost:8000/v1/generate/status/123e4567-e89b-12d3-a456-426614174000"
```

Response:
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "deployed",
  "api_url": "https://your-generated-api.com",
  "api_key": "your-api-key",
  "created_at": "2024-01-15T10:30:00Z"
}
```

## 📚 Generated API Features

Your generated APIs include:

- **Pagination**: `?limit=10&offset=0`
- **Filtering**: `?column_name=value`
- **Sorting**: `?sort_by=column&sort_order=asc`
- **Schema endpoint**: `/schema`
- **Individual records**: `/data/{id}`

Example generated API usage:
```bash
# Get paginated data
curl "https://your-api.com/data?limit=5&offset=0"

# Filter by column
curl "https://your-api.com/data?name=John"

# Sort data
curl "https://your-api.com/data?sort_by=age&sort_order=desc"
```

## 🔒 Security Features

- API key authentication
- Rate limiting
- CORS protection
- Input validation
- Sandboxed container execution

## 📈 Development Roadmap

### ✅ Milestone 1: Core Backend & AI Generation (Completed)
- File upload and processing (CSV, JSON, Excel, Parquet)
- Intelligent schema inference and data type detection
- AI-powered FastAPI code generation
- Mock API endpoints for immediate testing
- Container-ready deployments

### ✅ Milestone 2: Real-time Chat & AI Interaction (Completed)
- Socket.io-powered real-time chat interface
- Natural language API queries and data exploration
- Node.js chat server with OpenAI integration
- Context-aware AI responses using API schemas
- HTTP fallback endpoints for compatibility

### ✅ Milestone 3: Multi-Platform Authentication & Storage (Completed)
- GitHub OAuth, Google OAuth, and Supabase Auth integration
- Multiple storage backends (GCS, Supabase, Local)
- Database options (MongoDB Atlas, Supabase PostgreSQL)
- Session management and JWT tokens
- Secure API key generation

### ✅ Milestone 4: Deployment & Orchestration (Completed)
- Docker Compose for local development
- Cloud Run, Firebase, and multi-platform deployment
- Kubernetes-ready container configurations
- Automated deployment scripts
- Environment-based configuration management

### 🔄 Milestone 5: Advanced Features & Production Optimization
- Enhanced monitoring and analytics dashboard
- API usage metrics and performance tracking
- Advanced filtering and query capabilities
- Webhook integrations and notifications
- Batch processing and large dataset support

### 🔮 Milestone 6: Enterprise Features (Future)
- Multi-tenant architecture with user isolation
- Billing integration and usage limits
- Advanced security and compliance features
- Team collaboration and API sharing
- Custom domain support and white-labeling

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Issues**: GitHub Issues
- **Documentation**: This README and inline code comments
- **API Docs**: Available at `/docs` when running the backend

---

**Built with ❤️ using FastAPI, MongoDB, and AI**
