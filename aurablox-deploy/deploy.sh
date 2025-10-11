#!/bin/bash

echo "🚀 Deploying AURABLOX to Firebase Hosting..."
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

echo "📦 Deploying AURABLOX to Firebase Hosting..."
firebase deploy --only hosting

echo ""
echo "✅ AURABLOX deployment complete!"
echo ""
echo "🔗 Your AURABLOX site will be available at:"
echo "   https://daedalus-9f477.web.app/"
echo ""
echo "🔧 To manage your deployment:"
echo "   Firebase Console: https://console.firebase.google.com/project/daedalus-9f477/hosting"
echo ""
