# APIUI Chat Setup Guide

This comprehensive guide explains how to set up and run the Node.js chat server alongside your FastAPI backend for real-time AI-powered conversations with your generated APIs.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │ FastAPI Backend │    │ Chat Server     │
│   (HTML/JS)     │◄──►│ (Port 8000)     │◄──►│ (Node.js:3001)  │
│                 │    │ • API Generation│    │ • Socket.io Chat │
│ • File Upload   │    │ • Data Serving  │    │ • AI Responses   │
│ • API Testing   │    │ • Auth & Mgmt   │    │ • Real-time      │
│ • Chat Interface│    │ • Mock Endpoints│    │ • HTTP Fallback │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Component Roles

- **FastAPI Backend**: Core API generation, data persistence, authentication, and API management
- **Node.js Chat Server**: Real-time chat interface, AI-powered responses, Socket.io connections
- **Frontend**: Unified interface connecting to both backend services

## Setup Instructions

### 1. Install Node.js Dependencies

```bash
npm install
```

This installs all the chat server dependencies including Socket.io, Express, OpenAI client, etc.

### 2. Configure Environment Variables

Create a `.env` file in the `chat-server/` directory with your configuration:

```bash
cd chat-server
cat > .env << EOF
# Chat Server Configuration
CHAT_PORT=3001
FLASK_BACKEND_URL=http://localhost:8000
OPENAI_API_KEY=your-openai-api-key-here

# Optional: Database for chat history (future feature)
# DATABASE_URL=postgresql://user:pass@localhost:5432/chatdb

# Optional: Redis for scaling (future feature)
# REDIS_URL=redis://localhost:6379
EOF
```

**Important Notes:**
- Use the same OpenAI API key configured in your FastAPI backend
- Default backend port is `8000` (not `9999`)
- The chat server will proxy API requests to your FastAPI backend
- Ensure both servers can communicate (same network/firewall rules)

### 3. Running Both Servers

#### Option A: Run Separately (Recommended for Development)

**Terminal 1 - FastAPI Backend:**
```bash
# Navigate to backend directory
cd backend

# Activate virtual environment (if using venv)
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies if needed
pip install -r requirements.txt

# Run the FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Node.js Chat Server:**
```bash
# Navigate to chat server directory
cd chat-server

# Development mode with auto-restart
npm run chat-dev

# Or production mode
npm run chat-server
```

#### Option B: Docker Compose (Easiest Setup)

```bash
# Set your OpenAI API key
export OPENAI_API_KEY='your-openai-api-key-here'

# Start all services (backend, chat server, MongoDB)
docker-compose up -d

# Services will be available at:
# - Frontend: http://localhost:8080
# - FastAPI Backend: http://localhost:8000
# - Chat Server: http://localhost:3001
# - API Documentation: http://localhost:8000/docs
```

#### Option C: Use the Convenience Script

```bash
# Set your OpenAI API key
export OPENAI_API_KEY='your-openai-api-key-here'

# Ensure FastAPI backend is running first, then:
./start-chat-server.sh
```

## Testing the Setup

### 1. Test FastAPI Backend
```bash
# Health check
curl http://localhost:8000/health

# Expected response includes storage and database status:
{
  "status": "healthy",
  "storage": {"type": "GCS", "status": "available"},
  "database": {"type": "MongoDB", "status": "connected"},
  "jobs_count": 5,
  "apis_count": 3
}
```

### 2. Test Chat Server
```bash
# Health check
curl http://localhost:3001/health

# Expected response:
{
  "status": "healthy",
  "openai": true,
  "backend_connected": true,
  "uptime": "0d 0h 5m 23s"
}
```

### 3. Test API Communication
```bash
# Get list of available APIs
curl http://localhost:3001/api/apis

# Should return APIs from FastAPI backend:
[
  {
    "id": "api-123",
    "name": "Sales Data API",
    "status": "running",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

### 4. Test Chat Functionality
```bash
# HTTP chat endpoint
curl -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How many records are in the dataset?",
    "api_id": "your-api-id",
    "user_id": "test-user"
  }'

# Expected AI-powered response about your data
```

### 5. Test WebSocket Chat (Advanced)
```javascript
// In browser console or Node.js
const socket = io('http://localhost:3001');

// Connect and join API chat room
socket.emit('join_api', {
  api_id: 'your-api-id',
  user_id: 'test-user'
});

// Send a message
socket.emit('chat_message', {
  message: "Show me the data schema",
  api_id: "your-api-id",
  user_id: "test-user"
});

// Listen for responses
socket.on('chat_response', (data) => {
  console.log('AI Response:', data.message);
});
```

## Socket.io Chat Interface

### Using the Dedicated Chat Interface

1. **Start all services** using Docker Compose (recommended):
   ```bash
   docker-compose up -d
   ```

2. **Open the chat interface** in your browser:
   - `http://localhost:8080/socket-chat.html` (from frontend directory)
   - Or `http://localhost:3000/socket-chat.html` (if serving frontend separately)

3. **Select an API** from the dropdown (automatically populated from your backend)

4. **Click "Connect to API"** - establishes Socket.io connection to chat server

5. **Start chatting** with natural language queries:
   - "How many records are there?"
   - "Show me sales by region"
   - "What columns does this dataset have?"
   - "Filter data where age > 25"

### Using the Main Application Interface

The main application (`http://localhost:8080`) now includes integrated chat functionality:

1. **Upload and generate an API** as usual
2. **Click on "Chat with API"** button in the API management section
3. **Ask questions** about your data using natural language
4. **Get AI-powered insights** and data analysis

### Chat Features

- **Real-time Responses**: Instant answers powered by WebSocket connections
- **Context Awareness**: AI understands your API schema and data structure
- **Multi-API Support**: Chat with different APIs simultaneously
- **Error Handling**: Graceful fallbacks when AI services are unavailable
- **Persistent Sessions**: Chat history maintained during your session

## API Endpoints

### Chat Server HTTP Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with OpenAI and backend status |
| `GET` | `/api/apis` | List available APIs (proxied from FastAPI backend) |
| `POST` | `/api/chat` | HTTP fallback for chat messages |
| `GET` | `/metrics` | Chat server metrics and statistics |

### WebSocket Events (Socket.io)

#### Client → Server Events
| Event | Payload | Description |
|-------|---------|-------------|
| `join_api` | `{api_id, user_id}` | Join a specific API chat room |
| `chat_message` | `{message, api_id, user_id}` | Send chat message to AI |
| `leave_api` | `{api_id, user_id}` | Leave API chat room |
| `ping` | `{}` | Keep connection alive |

#### Server → Client Events
| Event | Payload | Description |
|-------|---------|-------------|
| `chat_response` | `{message, api_id, timestamp}` | AI response to chat message |
| `error` | `{message, code}` | Error message |
| `pong` | `{}` | Ping response |
| `api_joined` | `{api_id, schema}` | Confirmation of API room join |
| `api_left` | `{api_id}` | Confirmation of API room leave |

### Example Usage

#### HTTP Chat
```bash
curl -X POST "http://localhost:3001/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the average price in the dataset?",
    "api_id": "sales-api-123",
    "user_id": "user-456"
  }'
```

#### WebSocket Chat
```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:3001');

// Join API room
socket.emit('join_api', {
  api_id: 'sales-api-123',
  user_id: 'user-456'
});

// Send message
socket.emit('chat_message', {
  message: 'Show me sales by category',
  api_id: 'sales-api-123',
  user_id: 'user-456'
});

// Listen for responses
socket.on('chat_response', (data) => {
  console.log('AI:', data.message);
});
```

## Troubleshooting

### Chat Server Won't Start
- **Port 3001 unavailable**: Check if another service is using the port
- **Dependencies missing**: Run `npm install` in the chat-server directory
- **OpenAI API key missing**: Ensure `OPENAI_API_KEY` is set in `.env`
- **Node.js version**: Requires Node.js 16+ for Socket.io compatibility

### Can't Connect to Chat
- **Backend not running**: Ensure FastAPI backend is running on port 8000
- **Network issues**: Check if both servers can communicate (firewall rules)
- **CORS errors**: Verify CORS settings in browser console
- **WebSocket blocked**: Some networks/proxies block WebSocket connections

### No AI Responses
- **OpenAI API key invalid**: Check API key format and credits
- **Rate limiting**: OpenAI has request limits - responses may be delayed
- **Network timeout**: AI requests may timeout on slow connections
- **Fallback mode**: Server provides mock responses when AI fails

### API Not Found Errors
- **API doesn't exist**: Verify the API ID in your FastAPI backend
- **Backend URL wrong**: Check `FLASK_BACKEND_URL` in chat server `.env`
- **Authentication issues**: Some APIs require authentication
- **API not deployed**: Ensure the API is in "running" status

### Performance Issues
- **High latency**: Check network connection between services
- **Memory usage**: Monitor Node.js process memory consumption
- **Concurrent connections**: Socket.io handles multiple users but has limits
- **Database queries**: Complex queries may slow down responses

### Common Error Messages
- `"OpenAI API key not configured"`: Set `OPENAI_API_KEY` environment variable
- `"Backend connection failed"`: Ensure FastAPI backend is running and accessible
- `"API not found"`: Verify API exists and is accessible
- `"WebSocket connection failed"`: Check network/firewall settings

## Production Deployment

### Docker Deployment (Recommended)

1. **Build and run with Docker Compose**:
   ```bash
   # Set production environment variables
   export OPENAI_API_KEY='your-production-key'
   export NODE_ENV=production

   # Deploy all services
   docker-compose -f docker-compose.yml up -d
   ```

2. **Use reverse proxy** (nginx example):
   ```nginx
   # nginx.conf
   upstream fastapi_backend {
       server backend:8000;
   }

   upstream chat_server {
       server chat-server:3001;
   }

   server {
       listen 80;
       server_name your-domain.com;

       # FastAPI backend
       location /api/ {
           proxy_pass http://fastapi_backend;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }

       # Chat server
       location /chat/ {
           proxy_pass http://chat_server;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
       }

       # Frontend
       location / {
           try_files $uri $uri/ /index.html;
           root /usr/share/nginx/html;
       }
   }
   ```

### Cloud Deployment Options

#### Google Cloud Run
```bash
# Deploy backend
gcloud run deploy apiui-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --set-env-vars="OPENAI_API_KEY=your-key"

# Deploy chat server separately
gcloud run deploy apiui-chat \
  --source ./chat-server \
  --platform managed \
  --region us-central1 \
  --set-env-vars="OPENAI_API_KEY=your-key,FLASK_BACKEND_URL=https://backend-url"
```

#### Firebase
```bash
# Deploy frontend to Firebase Hosting
firebase deploy --only hosting

# Deploy backend functions
firebase deploy --only functions
```

#### Kubernetes
```yaml
# k8s deployment example
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chat-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: chat-server
  template:
    metadata:
      labels:
        app: chat-server
    spec:
      containers:
      - name: chat-server
        image: your-chat-server-image
        ports:
        - containerPort: 3001
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openai
        - name: FLASK_BACKEND_URL
          value: "http://backend-service:8000"
```

### Production Configuration

1. **Environment Variables**:
   ```bash
   NODE_ENV=production
   OPENAI_API_KEY=your-production-key
   FLASK_BACKEND_URL=https://your-backend-domain.com
   CHAT_PORT=3001
   ```

2. **Security**:
   - Use HTTPS/WSS for all connections
   - Configure CORS for your domain only
   - Set up authentication middleware
   - Use secrets management (not environment variables)

3. **Monitoring**:
   - Set up health checks for both services
   - Monitor WebSocket connection counts
   - Track AI API usage and costs
   - Set up error logging and alerting

4. **Scaling**:
   - Use PM2 for Node.js process management
   - Configure horizontal scaling for high traffic
   - Set up Redis for session storage (future feature)
   - Monitor resource usage and adjust accordingly

## Development Workflow

### Local Development Setup

1. **FastAPI Backend**:
   ```bash
   cd backend
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Chat Server**:
   ```bash
   cd chat-server
   npm install
   npm run chat-dev  # Auto-restart on file changes
   ```

3. **Frontend**:
   ```bash
   cd frontend
   python -m http.server 8080
   # Or use any static file server
   ```

4. **Test the Integration**:
   - **Main App**: `http://localhost:8080`
   - **Chat Interface**: `http://localhost:8080/socket-chat.html`
   - **API Docs**: `http://localhost:8000/docs`
   - **Chat Server Health**: `http://localhost:3001/health`

### Docker Development (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Testing Chat Features

1. **Upload a dataset** through the main interface
2. **Generate an API** and wait for completion
3. **Open the chat interface** and select your API
4. **Try these queries**:
   - "How many records are there?"
   - "What columns does this data have?"
   - "Show me the first 5 records"
   - "What's the average value of [column_name]?"

### Code Changes

- **Backend changes**: Restart FastAPI server (auto-reload enabled)
- **Chat server changes**: Auto-restart with `npm run chat-dev`
- **Frontend changes**: Refresh browser (or set up live reload)

The chat server automatically proxies API requests to your FastAPI backend and provides intelligent AI-powered responses using your data schema and content!
