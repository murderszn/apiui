# apiui

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
├── backend/                 # FastAPI backend
│   ├── main.py             # Main application
│   ├── core/               # Core functionality
│   │   ├── config.py       # Configuration management
│   │   └── database.py     # Database connection
│   ├── models/             # Pydantic models
│   │   └── job.py          # Job status model
│   ├── services/           # Business logic
│   │   ├── file_service.py     # File processing
│   │   ├── ai_service.py       # AI code generation
│   │   └── deployment_service.py # Container deployment
│   ├── requirements.txt    # Python dependencies
│   └── env.example         # Environment template
├── frontend/               # Web interface
│   └── index.html          # Single-page application
├── docker/                 # Docker configurations
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── nginx.conf
├── docker-compose.yml      # Development environment
└── README.md
```

## 🛠️ Architecture Overview

### Core Components

1. **File Processing Service**
   - Supports CSV, JSON, Excel, and Parquet files
   - Automatic schema inference with data type detection
   - Sample data extraction for AI context

2. **AI Code Generation**
   - Integration with OpenAI GPT-4 or Google Gemini
   - Generates complete FastAPI applications
   - Includes pagination, filtering, and sorting
   - Container-ready with Dockerfile

3. **Deployment Pipeline**
   - Docker containerization
   - Cloud Run/Fargate deployment (configurable)
   - API Gateway integration
   - Automatic SSL and security configuration

4. **Web Interface**
   - Drag-and-drop file upload
   - Real-time progress tracking
   - Status polling with visual feedback
   - API endpoint and key management

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

### Milestone 1: Core Backend & AI Generation ✅
- File upload and processing
- Schema inference
- AI-powered code generation
- Basic deployment simulation

### Milestone 2: Automated Infrastructure & Deployment
- Docker container builds
- Cloud Run/Fargate integration
- CI/CD pipeline
- API Gateway configuration

### Milestone 3: Frontend Integration & User Experience
- Enhanced UI/UX
- Real-time status updates
- API testing interface
- Error handling improvements

### Milestone 4: Production Readiness
- User authentication (Firebase/Auth0)
- Database integration for users/APIs
- Billing integration (Stripe)
- Monitoring and logging
- Multi-tenant architecture

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
