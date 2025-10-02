# Firebase Deployment Setup

This guide explains how to set up and deploy apiUI with Firebase Functions and Hosting.

## Prerequisites

1. **Firebase CLI**: Install Firebase CLI globally
   ```bash
   npm install -g firebase-tools
   ```

2. **Firebase Project**: Create a Firebase project at https://console.firebase.google.com/

3. **Firebase Login**:
   ```bash
   firebase login
   ```

## Environment Variables Setup

### 1. Set Firebase Functions Configuration

You need to set environment variables for the chat server functions:

```bash
# Set OpenAI API Key
firebase functions:config:set apiui.openai_api_key="your-openai-api-key-here"

# Set Flask Backend URL (your deployed backend)
firebase functions:config:set apiui.flask_backend_url="https://your-backend-url.run.app"
```

### 2. Alternative: Set via Firebase Console

1. Go to Firebase Console → Functions → Configuration
2. Add environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `FLASK_BACKEND_URL`: Your backend API URL

## Deployment

### Full Deployment (Functions + Hosting)

```bash
# Make the deploy script executable
chmod +x deploy-firebase.sh

# Run the deployment
./deploy-firebase.sh
```

### Manual Deployment

```bash
# Install functions dependencies
cd functions && npm install && cd ..

# Deploy functions
firebase deploy --only functions

# Deploy hosting
firebase deploy --only hosting
```

## Available Endpoints

After deployment, your app will be available at:

- **Frontend**: `https://ai-apiui.web.app/`
- **Chat API**: `https://us-central1-ai-apiui.cloudfunctions.net/chat`
- **Health Check**: `https://us-central1-ai-apiui.cloudfunctions.net/chat/health`
- **API List**: `https://us-central1-ai-apiui.cloudfunctions.net/chat/apis`

## API Usage

### Chat Endpoint
```javascript
const response = await fetch('/api/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    message: "Show me a sample of the data",
    api_id: "your-api-id",
    user_id: "optional-user-id"
  })
});
```

### Health Check
```javascript
const health = await fetch('/api/health');
const status = await health.json();
```

## Troubleshooting

### Common Issues

1. **Functions deployment fails**: Check that environment variables are set
2. **Chat not working**: Verify OpenAI API key is valid
3. **API not found**: Ensure Flask backend URL is correct

### Logs

Check function logs:
```bash
firebase functions:log
```

### Local Development

Test functions locally:
```bash
firebase emulators:start --only functions
```

## File Structure

```
apiui/
├── firebase.json          # Firebase configuration
├── .firebaserc           # Firebase project configuration
├── functions/            # Firebase Cloud Functions
│   ├── index.js         # Main functions code
│   └── package.json     # Functions dependencies
├── frontend/            # Static hosting files
└── deploy-firebase.sh   # Deployment script
```


