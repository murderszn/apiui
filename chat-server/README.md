# APIUI Chat Server

A Node.js Socket.io server that provides real-time AI-powered chat functionality for APIUI, enabling natural language interactions with generated APIs.

## Features

- **Real-time Chat**: Socket.io-powered instant messaging with APIs
- **AI-Powered Responses**: OpenAI GPT integration for intelligent data analysis
- **Natural Language Queries**: Ask questions about your data in plain English
- **Context Awareness**: AI understands API schemas and data structures
- **HTTP Fallback**: REST API endpoints for compatibility
- **Multi-API Support**: Chat with multiple APIs simultaneously
- **CORS Support**: Cross-origin requests for web clients
- **Error Handling**: Graceful fallbacks when AI services are unavailable
- **Health Monitoring**: Comprehensive system status checks

## Quick Start

### Docker Compose (Recommended)
```bash
# From project root
export OPENAI_API_KEY='your-openai-api-key'
docker-compose up -d

# Chat server available at http://localhost:3001
```

### Manual Setup
```bash
# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run development server
npm run chat-dev
```

## Environment Configuration

Create a `.env` file in the chat-server directory:

```env
# Server Configuration
CHAT_PORT=3001
NODE_ENV=development

# Backend Integration
FLASK_BACKEND_URL=http://localhost:8000

# AI Configuration
OPENAI_API_KEY=your-openai-api-key-here

# Optional: Future features
# REDIS_URL=redis://localhost:6379
# DATABASE_URL=postgresql://user:pass@localhost:5432/chatdb
```

## Running the Server

### Development Mode
```bash
npm run chat-dev
```
- Auto-restarts on file changes
- Detailed logging
- Development-friendly error messages

### Production Mode
```bash
npm run chat-server
```
- Optimized for production
- Minimal logging
- Error handling for stability

## API Reference

### HTTP Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server health and connectivity status |
| `GET` | `/api/apis` | List available APIs from backend |
| `POST` | `/api/chat` | Send chat message via HTTP |
| `GET` | `/metrics` | Server metrics and statistics |

#### Health Check Response
```json
{
  "status": "healthy",
  "openai": true,
  "backend_connected": true,
  "uptime": "0d 0h 5m 23s",
  "version": "1.0.0"
}
```

#### Chat via HTTP
```bash
curl -X POST "http://localhost:3001/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How many records are in the dataset?",
    "api_id": "your-api-id",
    "user_id": "user123"
  }'
```

### WebSocket Events

#### Client → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `join_api` | `{api_id: string, user_id: string}` | Join API chat room |
| `chat_message` | `{message: string, api_id: string, user_id: string}` | Send chat message |
| `leave_api` | `{api_id: string, user_id: string}` | Leave API chat room |
| `ping` | `{}` | Keep connection alive |

#### Server → Client

| Event | Payload | Description |
|-------|---------|-------------|
| `chat_response` | `{message: string, api_id: string, timestamp: string}` | AI response |
| `error` | `{message: string, code: string}` | Error notification |
| `api_joined` | `{api_id: string, schema: object}` | Join confirmation |
| `pong` | `{}` | Ping response |

## Usage Examples

### JavaScript Client
```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:3001');

// Join API chat room
socket.emit('join_api', {
  api_id: 'sales-api-123',
  user_id: 'user-456'
});

// Send a natural language query
socket.emit('chat_message', {
  message: 'What are the top 5 products by sales?',
  api_id: 'sales-api-123',
  user_id: 'user-456'
});

// Listen for AI responses
socket.on('chat_response', (data) => {
  console.log('AI:', data.message);
});

// Handle errors
socket.on('error', (error) => {
  console.error('Chat error:', error.message);
});
```

### React Hook Example
```javascript
import { useEffect, useState } from 'react';
import io from 'socket.io-client';

function useAPIChat(apiId, userId) {
  const [messages, setMessages] = useState([]);
  const [socket, setSocket] = useState(null);

  useEffect(() => {
    const newSocket = io('http://localhost:3001');
    setSocket(newSocket);

    // Join API room
    newSocket.emit('join_api', { api_id: apiId, user_id: userId });

    // Listen for responses
    newSocket.on('chat_response', (data) => {
      setMessages(prev => [...prev, { type: 'ai', ...data }]);
    });

    return () => newSocket.close();
  }, [apiId, userId]);

  const sendMessage = (message) => {
    socket?.emit('chat_message', {
      message,
      api_id: apiId,
      user_id: userId
    });
    setMessages(prev => [...prev, { type: 'user', message }]);
  };

  return { messages, sendMessage };
}
```

## Integration with APIUI Backend

The chat server integrates seamlessly with the FastAPI backend:

1. **API Discovery**: Fetches available APIs from `/v1/apis` endpoint
2. **Schema Access**: Retrieves data schemas for context-aware responses
3. **Data Queries**: Proxies complex queries to backend APIs
4. **Authentication**: Respects backend authentication and permissions
5. **Metrics**: Reports usage statistics back to backend

## Troubleshooting

### Common Issues

- **"Backend connection failed"**: Ensure FastAPI backend is running on port 8000
- **"OpenAI API key not configured"**: Set `OPENAI_API_KEY` in environment
- **WebSocket connection fails**: Check firewall settings and CORS configuration
- **No AI responses**: Verify OpenAI API key validity and network connectivity

### Debug Mode
```bash
# Enable detailed logging
DEBUG=chat-server:* npm run chat-dev
```

### Health Checks
```bash
# Check server status
curl http://localhost:3001/health

# Check backend connectivity
curl http://localhost:3001/api/apis
```

## Production Deployment

### Docker Deployment
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3001
CMD ["npm", "run", "chat-server"]
```

### Process Management
```bash
# Using PM2
npm install -g pm2
pm2 start server.js --name "apiui-chat"
pm2 save
pm2 startup
```

### Environment Variables for Production
```env
NODE_ENV=production
CHAT_PORT=3001
FLASK_BACKEND_URL=https://your-backend-domain.com
OPENAI_API_KEY=your-production-key
```

## Development

### Project Structure
```
chat-server/
├── server.js          # Main server file
├── package.json       # Dependencies and scripts
├── .env.example       # Environment template
└── README.md         # This file
```

### Adding New Features
1. **WebSocket Events**: Add to server.js event handlers
2. **HTTP Endpoints**: Add Express routes in server.js
3. **AI Features**: Modify OpenAI integration in chat handlers
4. **Backend Integration**: Update API calls to FastAPI backend

### Testing
```bash
# Run tests (when implemented)
npm test

# Manual testing with curl
curl -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"test","api_id":"test","user_id":"test"}'
```

## Contributing

1. Follow the existing code style
2. Add error handling for new features
3. Update this README for API changes
4. Test with both WebSocket and HTTP interfaces
5. Ensure compatibility with existing APIUI integrations

## License

This project is part of APIUI and follows the same license terms.
