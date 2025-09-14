#!/bin/bash

echo "🚀 Deploying apiui to Vercel..."
echo ""

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "❌ Vercel CLI is not installed. Please install it first:"
    echo "npm install -g vercel"
    exit 1
fi

# Check if user is logged in
if ! vercel whoami &> /dev/null; then
    echo "🔐 Please login to Vercel first:"
    vercel login
fi

echo "📦 Deploying to production..."
vercel --prod

echo ""
echo "✅ Deployment complete!"
echo "📝 Don't forget to set your environment variables in the Vercel dashboard:"
echo "   - OPENAI_API_KEY"
echo "   - MONGODB_URL (optional)"
echo "   - SECRET_KEY"
echo ""
echo "🔗 Your app will be available at the URL shown above."
