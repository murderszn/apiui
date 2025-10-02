#!/bin/bash

echo "🚀 Deploying apiUI to Firebase (Functions + Hosting)..."
echo ""

# Check if Firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo "❌ Firebase CLI is not installed. Please install it first:"
    echo "npm install -g firebase-tools"
    exit 1
fi

# Check if user is logged in
if ! firebase projects:list &> /dev/null; then
    echo "🔐 Please login to Firebase first:"
    firebase login
fi

echo "🔧 Setting up Firebase Functions environment variables..."
echo "   Note: Make sure to set these in Firebase Console:"
echo "   - OPENAI_API_KEY: Your OpenAI API key"
echo "   - FLASK_BACKEND_URL: Your backend API URL"
echo ""

# Install functions dependencies
echo "📦 Installing Functions dependencies..."
cd functions && npm install && cd ..

echo ""
echo "🚀 Deploying Firebase Functions..."
firebase deploy --only functions

echo ""
echo "📦 Deploying Firebase Hosting..."
firebase deploy --only hosting

echo ""
echo "✅ Firebase deployment complete!"
echo ""
echo "🔗 Your app will be available at:"
echo "   - Frontend: https://ai-apiui.web.app/"
echo "   - Chat API: https://us-central1-ai-apiui.cloudfunctions.net/chat"
echo ""
echo "📝 Available endpoints:"
echo "   - Chat API: https://us-central1-ai-apiui.cloudfunctions.net/chat"
echo "   - Health Check: https://us-central1-ai-apiui.cloudfunctions.net/chat/health"
echo "   - API List: https://us-central1-ai-apiui.cloudfunctions.net/chat/apis"
echo ""
echo "🔧 To manage your deployment:"
echo "   - Firebase Console: https://console.firebase.google.com/project/ai-apiui/"
echo "   - Functions: https://console.firebase.google.com/project/ai-apiui/functions"
echo "   - Hosting: https://console.firebase.google.com/project/ai-apiui/hosting"
echo ""
echo "⚙️  Environment Variables Setup:"
echo "   Go to Firebase Console > Functions > Configuration"
echo "   Add these environment variables:"
echo "   - OPENAI_API_KEY: [your-openai-key]"
echo "   - FLASK_BACKEND_URL: [your-backend-url]"
