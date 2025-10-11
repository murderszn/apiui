# Deploy MCP Chat Updates

## Quick Deploy Guide

The MCP Chat feature requires backend deployment to Cloud Run. Follow these steps:

## Option 1: Full Cloud Run Deployment (Recommended)

### Prerequisites
- Google Cloud SDK installed (`gcloud`)
- Authenticated with Google Cloud
- Project ID: `aurablox-ai`

### Deploy Command

```bash
# Make sure you're in the project root
cd /Users/jahflyx/apiui

# Run the deployment script
./deploy-cloud-run.sh
```

This will:
1. Build the Docker image with Cloud Build
2. Deploy to Cloud Run with all environment variables
3. Make the new `/mcp/apis` endpoints available

### Verify Deployment

After deployment completes, test the new endpoints:

```bash
# Test the new MCP APIs endpoint
curl https://apiui-backend-44565368406.us-central1.run.app/mcp/apis

# Should return JSON with list of APIs
```

## Option 2: Quick Test (Local Development)

If you want to test locally first:

```bash
# Navigate to backend
cd /Users/jahflyx/apiui/backend

# Install dependencies (if not already done)
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-key-here"
export PORT=9999

# Run the backend locally
python main.py
```

Then update the frontend to use localhost:
```javascript
// In mcp-chat.html, temporarily change:
window.APIUI_AUTH_BASE_URL = 'http://localhost:9999';
```

## Option 3: Manual Cloud Run Update

If the deploy script doesn't work, manually update:

```bash
# Set your project
gcloud config set project aurablox-ai

# Build the image
gcloud builds submit --config cloudbuild.yaml --timeout=900 .

# Deploy
gcloud run deploy apiui-backend \
    --image gcr.io/aurablox-ai/apiui-backend:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --port 9999 \
    --memory 1Gi
```

## Troubleshooting

### 404 Error on `/mcp/apis`

**Problem**: `GET /mcp/apis` returns 404

**Cause**: Backend hasn't been deployed with new code

**Solution**: Run deployment script or check Cloud Run console to see if deployment succeeded

### Import Error in Backend

**Problem**: `ModuleNotFoundError: No module named 'services.mcp_api_service'`

**Cause**: New service file not included in deployment

**Solution**: 
1. Verify `backend/services/mcp_api_service.py` exists
2. Check it's not in `.dockerignore`
3. Redeploy

### No APIs Returned

**Problem**: `/mcp/apis` returns empty array

**Cause**: No APIs have been generated yet

**Solution**:
1. Go to `/app.html`
2. Upload a CSV/Excel file
3. Generate an API
4. Refresh MCP Chat page

## Verification Checklist

After deployment, verify:

- [ ] Backend health: `curl <url>/health`
- [ ] List APIs: `curl <url>/mcp/apis`
- [ ] Get API: `curl <url>/mcp/apis/<api_id>`
- [ ] Query API: `curl <url>/mcp/apis/<api_id>/query`
- [ ] Chat: `curl -X POST <url>/mcp/chat -H "Content-Type: application/json" -d '{"message":"test","api_ids":["id"]}'`
- [ ] Frontend loads: Open `mcp-chat.html` in browser
- [ ] APIs display in selector
- [ ] Can select/deselect APIs
- [ ] Can send chat messages
- [ ] Responses appear correctly

## Environment Variables Needed

Make sure these are set in Cloud Run:

```bash
OPENAI_API_KEY=sk-...          # Required for AI chat
USE_GCS_STORAGE=True           # For file storage
GCS_BUCKET_NAME=apiui-files-...  # Your GCS bucket
SUPABASE_URL=...               # If using Supabase
SUPABASE_ANON_KEY=...          # If using Supabase
```

## Quick Test Script

Use the included test script to verify everything works:

```bash
./test_mcp_chat.sh
```

This will test all endpoints and report any issues.

## Next Steps After Deployment

1. ✅ Verify backend is deployed
2. ✅ Test all endpoints with curl
3. ✅ Open `mcp-chat.html` in browser
4. ✅ Test with real APIs
5. ✅ Share with team

## Support

If you encounter issues:

1. Check Cloud Run logs:
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=apiui-backend" --limit 50 --format json
   ```

2. Check for errors in browser console

3. Run test script: `./test_mcp_chat.sh`

4. Verify files exist:
   - `backend/services/mcp_api_service.py`
   - `frontend/mcp-chat.html`

