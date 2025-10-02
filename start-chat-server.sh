#!/bin/bash

# Start the APIUI Chat Server
echo "🚀 Starting APIUI Chat Server..."
echo "Make sure your Flask backend is running on http://localhost:9999"
echo ""

# Set environment variables if not set
export CHAT_PORT=${CHAT_PORT:-3001}
export FLASK_BACKEND_URL=${FLASK_BACKEND_URL:-http://localhost:9999}

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set. The chat server will use mock responses."
    echo "   To enable AI responses, set your OpenAI API key:"
    echo "   export OPENAI_API_KEY='your-api-key-here'"
    echo ""
fi

echo "📡 Chat Server will run on: http://localhost:$CHAT_PORT"
echo "🔗 Flask Backend: $FLASK_BACKEND_URL"
echo ""

# Start the chat server
cd chat-server
npm run chat-server
