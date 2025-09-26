# 🚀 Cloud Run Deployment Guide for apiui

This guide will help you deploy your apiui application to Google Cloud Run with a public URL.

## 📋 Prerequisites

1. **Google Cloud Account** - [Sign up here](https://cloud.google.com/)
2. **Google Cloud SDK** - Install from [cloud.google.com/sdk](https://cloud.google.com/sdk)
3. **Docker** - Make sure Docker is running
4. **OpenAI API Key** (optional but recommended)

## 🏗️ Architecture Overview

### Option 1: Backend Only (Recommended)
- **Backend API** → Google Cloud Run
- **Frontend** → Firebase Hosting or Vercel
- **Database** → MongoDB Atlas (cloud) or Cloud Run + Cloud SQL

### Option 2: Full Stack
- **Backend + Frontend** → Single Cloud Run service
- **Database** → Cloud Run + Cloud SQL

## 🚀 Quick Deployment

### Step 1: Configure Your Settings

1. Open `cloudrun.env` and update it with your project values. The deploy script reads this file automatically:
```bash
# Required
PROJECT_ID=your-actual-gcp-project-id
REGION=us-central1
OPENAI_API_KEY=your-openai-api-key

# Storage (defaults to apiui-files-${PROJECT_ID})
USE_GCS_STORAGE=True
GCS_BUCKET_NAME=apiui-files-your-project

# Optional data persistence
MONGODB_URL=mongodb+srv://your-connection-string
DATABASE_NAME=apiui

# Optional custom domain override
API_GATEWAY_URL=https://api.yourdomain.com
```

### Step 2: Authenticate with Google Cloud

```bash
# Login to Google Cloud
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### Step 3: Deploy

```bash
# Make script executable (first time only)
chmod +x deploy-cloud-run.sh

# Deploy to Cloud Run
./deploy-cloud-run.sh
```

The script will:
- Load values from `cloudrun.env` (or the current shell) for `PROJECT_ID`, secrets, and runtime settings
- Build and push the container image via Cloud Build
- Deploy to Cloud Run with the environment variables you configured (OpenAI key, MongoDB URL, OAuth settings, etc.)

## 🌐 Public URL & Access

After deployment, Cloud Run will provide a public URL like:
```
https://apiui-backend-xxxxxxxxxx-uc.a.run.app
```

Your API endpoints will be available at:
- **Health Check**: `https://your-service.run.app/health`
- **API List**: `https://your-service.run.app/v1/apis`
- **File Upload**: `https://your-service.run.app/v1/generate` (POST)
- **Generated APIs**: `https://your-service.run.app/mock-api/{job_id}/data`

> The backend now inspects the incoming request and automatically builds fully qualified URLs in the job status responses. You no longer need to hard-code the Cloud Run domain in the code—whatever hostname hits `/v1/generate/status/{job_id}` is what will be returned for the generated API endpoints.

## 🎨 Frontend Deployment Options

### Option A: Firebase Hosting (Recommended)

1. **Install Firebase CLI**:
```bash
npm install -g firebase-tools
firebase login
```

2. **Initialize Firebase**:
```bash
cd frontend
firebase init hosting
```

3. **Configure `firebase.json`**:
```json
{
  "hosting": {
    "public": ".",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

4. **Update Frontend API Calls**:
In your frontend JavaScript, change:
```javascript
const API_BASE = 'http://localhost:8000';  // Local
```
To:
```javascript
const API_BASE = 'https://your-cloud-run-service.run.app';  // Production
```

5. **Deploy**:
```bash
firebase deploy
```

### Option B: Vercel

1. **Install Vercel CLI**:
```bash
npm install -g vercel
```

2. **Deploy**:
```bash
cd frontend
vercel --prod
```

3. **Configure API Proxy** (optional):
Create `vercel.json`:
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "https://your-cloud-run-service.run.app/api/$1" }
  ]
}
```

## 🔧 Environment Variables

Set these in Cloud Run console or via gcloud:

```bash
# Required for AI functionality
OPENAI_API_KEY=your-key-here

# Storage Configuration (choose one)
USE_GCS_STORAGE=True  # Set to True to use Google Cloud Storage
GCS_BUCKET_NAME=your-bucket-name  # Your GCS bucket name
GCS_PROJECT_ID=your-gcp-project-id  # Your GCP project ID

# Database (choose one - MongoDB recommended for persistence)
MONGODB_URL=mongodb+srv://...  # MongoDB Atlas connection string

# Optional
FLASK_DEBUG=False
PORT=8080
```

### Storage Options

1. **Google Cloud Storage (Recommended for production)**:
   - Set `USE_GCS_STORAGE=True`
   - Create a GCS bucket: `gsutil mb gs://your-bucket-name`
   - Set appropriate IAM permissions for Cloud Run service account

2. **Local Storage (Development only)**:
   - Keep `USE_GCS_STORAGE=False` (default)
   - Files stored in container's `/app/uploads` and `/app/generated_apis`
   - **Warning**: Data will be lost when container restarts in Cloud Run

### Custom Domains & Reverse Proxies

If you front the backend with a custom domain (Cloud Run custom domains, Cloudflare, API Gateway, etc.), set `API_GATEWAY_URL=https://api.yourdomain.com` in `cloudrun.env`. The backend will prefer that value when building absolute URLs for generated APIs. If it is left blank, the service automatically uses the request host and protocol it receives.

### Database Options

1. **MongoDB Atlas (Recommended)**:
   - Create cluster at [mongodb.com/atlas](https://mongodb.com/atlas)
   - Get connection string and set `MONGODB_URL`
   - Provides full persistence across container restarts

2. **No Database (Fallback)**:
   - Uses storage service for persistence
   - Less reliable but simpler setup

## 🗄️ Database Options

### Option 1: MongoDB Atlas (Easiest)
- Sign up at [mongodb.com/atlas](https://mongodb.com/atlas)
- Get connection string
- Set `MONGODB_URL` environment variable

### Option 2: Cloud Run + Cloud SQL
- Deploy MongoDB as separate Cloud Run service
- Use Cloud SQL for PostgreSQL
- More complex but fully serverless

## 📊 Monitoring & Scaling

Cloud Run automatically scales based on traffic:
- **Min instances**: 0 (scales to zero when no traffic)
- **Max instances**: 10 (configurable)
- **Concurrency**: 80 requests per instance
- **Memory**: 1GB per instance
- **CPU**: 1 vCPU per instance

## 🔒 Security & Best Practices

1. **Enable authentication** for production
2. **Use HTTPS** (Cloud Run provides automatically)
3. **Set up monitoring** in Google Cloud Console
4. **Configure CORS** for your frontend domain
5. **Use environment variables** for secrets

## 🐛 Troubleshooting

### Common Issues:

1. **Port Issues**: Make sure your app listens on port 8080
2. **Health Check Failures**: Ensure `/health` endpoint returns 200
3. **Memory Issues**: Increase memory allocation if needed
4. **CORS Errors**: Configure CORS in your Flask app

### Logs & Debugging:

```bash
# View Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=apiui-backend" --limit=50

# View service details
gcloud run services describe apiui-backend --region=us-central1
```

## 💰 Cost Optimization

- **Cloud Run**: Pay per request (~$0.000002/request)
- **Container Registry**: ~$0.026/GB/month for storage
- **MongoDB Atlas**: ~$0.08/GB/month
- **Firebase**: Free tier available

## 🎯 Next Steps

1. ✅ **Deploy Backend** to Cloud Run
2. ✅ **Deploy Frontend** to Firebase/Vercel
3. 🔄 **Test Integration** between frontend and backend
4. 🔄 **Set up Monitoring** and alerts
5. 🔄 **Configure Custom Domain** (optional)

---

**Your API will be publicly accessible at a URL like:**
`https://apiui-backend-xxxxxx.run.app`

**Ready to deploy? Run:**
```bash
./deploy-cloud-run.sh
```
