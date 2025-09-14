# Vercel Deployment Guide for apiui

This guide will help you deploy your apiui application to Vercel.

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **Vercel CLI**: Install the Vercel CLI globally
   ```bash
   npm install -g vercel
   ```
3. **Environment Variables**: Configure your API keys and settings

## Quick Deployment

### 1. Login to Vercel
```bash
vercel login
```

### 2. Deploy to Vercel
```bash
vercel --prod
```

Follow the prompts to configure your project.

## Manual Setup (Alternative)

### 1. Clone and Setup
```bash
git clone <your-repo-url>
cd apiui
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Configure Environment Variables

In your Vercel dashboard or using the CLI:

```bash
# Set environment variables
vercel env add OPENAI_API_KEY
vercel env add MONGODB_URL
vercel env add SECRET_KEY
```

Or configure them in the Vercel dashboard under Project Settings > Environment Variables.

### 4. Deploy
```bash
vercel
```

## Environment Variables Required

Copy the values from `vercel-env.example` and set them in Vercel:

- `OPENAI_API_KEY`: Your OpenAI API key for AI-powered features
- `MONGODB_URL`: MongoDB connection string (optional, uses in-memory storage if not set)
- `SECRET_KEY`: Random string for JWT token signing
- `DATABASE_NAME`: Database name (default: apiui)
- `GCS_BUCKET_NAME`: Google Cloud Storage bucket name
- `GCS_PROJECT_ID`: Google Cloud Project ID
- `GCP_PROJECT_ID`: Google Cloud Project ID
- `GCP_REGION`: Google Cloud region (default: us-central1)
- `GOOGLE_AI_API_KEY`: Google AI API key (optional)
- `API_GATEWAY_URL`: API Gateway URL for production APIs

## Project Structure

```
/apiui/
├── frontend/          # Static HTML files
│   ├── index.html    # Landing page
│   ├── app.html      # Main application
│   └── docs.html     # Documentation
├── backend/          # Flask application
│   ├── main.py      # Main Flask app
│   ├── core/        # Configuration
│   └── services/    # Business logic
├── api/             # Vercel serverless functions
│   ├── index.py     # API entry point
│   └── requirements.txt
├── vercel.json      # Vercel configuration
├── package.json     # Frontend dependencies
└── .vercelignore   # Files to exclude from deployment
```

## API Routes

After deployment, your API will be available at:

- **Frontend**: `https://your-project.vercel.app/`
- **API Endpoints**: `https://your-project.vercel.app/api/`
- **App Page**: `https://your-project.vercel.app/app`
- **Documentation**: `https://your-project.vercel.app/docs`

## Troubleshooting

### Common Issues

1. **Flask App Not Loading**:
   - Check that `api/index.py` correctly imports your Flask app
   - Verify `PYTHONPATH` is set correctly in `vercel.json`

2. **Environment Variables Not Working**:
   - Use `vercel env ls` to check configured variables
   - Redeploy after adding new environment variables

3. **CORS Issues**:
   - CORS is enabled in the Flask app by default
   - Check browser console for CORS-related errors

4. **File Upload Issues**:
   - Vercel has a 50MB limit for serverless functions
   - Large files may need to be handled differently

### Logs and Debugging

```bash
# View deployment logs
vercel logs

# View function logs
vercel logs --follow
```

## Production Considerations

1. **Database**: Consider using MongoDB Atlas for production data persistence
2. **File Storage**: Use Google Cloud Storage or AWS S3 for file uploads
3. **Security**: Generate strong SECRET_KEY and API keys
4. **Monitoring**: Set up Vercel Analytics for performance monitoring

## Custom Domain

To use a custom domain:

1. Go to Vercel Dashboard > Project Settings > Domains
2. Add your custom domain
3. Configure DNS records as instructed

## Support

For Vercel-specific issues, check:
- [Vercel Documentation](https://vercel.com/docs)
- [Vercel Community](https://vercel.com/discord)

For apiui-specific issues, refer to the main README.md file.
