#!/bin/bash

# Quick deploy script for MCP Chat updates
# This deploys the backend with new MCP API endpoints

set -e

echo "╔════════════════════════════════════════╗"
echo "║  Deploying MCP Chat to Cloud Run      ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI not found${NC}"
    echo "Please install Google Cloud SDK first:"
    echo "https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${RED}❌ Not authenticated with Google Cloud${NC}"
    echo "Please run: gcloud auth login"
    exit 1
fi

# Configuration
PROJECT_ID="aurablox-ai"
SERVICE_NAME="apiui-backend"
REGION="us-central1"

echo -e "${BLUE}→ Project: $PROJECT_ID${NC}"
echo -e "${BLUE}→ Service: $SERVICE_NAME${NC}"
echo -e "${BLUE}→ Region: $REGION${NC}"
echo ""

# Set project
echo -e "${YELLOW}[1/4] Setting Google Cloud project...${NC}"
gcloud config set project $PROJECT_ID

# Build with Cloud Build
echo -e "${YELLOW}[2/4] Building Docker image (this may take 2-3 minutes)...${NC}"
gcloud builds submit --config cloudbuild.yaml --timeout=900 .

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Build successful${NC}"
echo ""

# Deploy to Cloud Run
echo -e "${YELLOW}[3/4] Deploying to Cloud Run...${NC}"

# Get current environment variables
CURRENT_ENV=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "")

if [ -z "$CURRENT_ENV" ]; then
    echo -e "${YELLOW}⚠  No existing environment variables found${NC}"
    echo -e "${YELLOW}   Deploying with minimal config...${NC}"
    
    gcloud run deploy $SERVICE_NAME \
        --image gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
        --platform managed \
        --region $REGION \
        --allow-unauthenticated \
        --port 9999 \
        --memory 1Gi \
        --cpu 1 \
        --max-instances 10 \
        --timeout 300
else
    echo -e "${GREEN}✓ Using existing environment variables${NC}"
    
    gcloud run deploy $SERVICE_NAME \
        --image gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
        --platform managed \
        --region $REGION \
        --allow-unauthenticated \
        --port 9999 \
        --memory 1Gi \
        --cpu 1 \
        --max-instances 10 \
        --timeout 300
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Deployment failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Deployment successful${NC}"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

# Test the new endpoints
echo -e "${YELLOW}[4/4] Testing new MCP API endpoints...${NC}"

# Test 1: Health check
echo -e "${BLUE}→ Testing /health...${NC}"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/health")
if [ "$HEALTH_STATUS" -eq 200 ]; then
    echo -e "${GREEN}  ✓ Health check passed${NC}"
else
    echo -e "${RED}  ✗ Health check failed (HTTP $HEALTH_STATUS)${NC}"
fi

# Test 2: New MCP APIs endpoint
echo -e "${BLUE}→ Testing /mcp/apis...${NC}"
MCP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/mcp/apis")
if [ "$MCP_STATUS" -eq 200 ]; then
    echo -e "${GREEN}  ✓ MCP APIs endpoint working${NC}"
    
    # Count APIs
    API_COUNT=$(curl -s "$SERVICE_URL/mcp/apis" | grep -o '"id"' | wc -l | tr -d ' ')
    echo -e "${GREEN}  → Found $API_COUNT API(s)${NC}"
else
    echo -e "${RED}  ✗ MCP APIs endpoint failed (HTTP $MCP_STATUS)${NC}"
fi

echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Deployment Complete! 🎉               ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}Service URL:${NC} $SERVICE_URL"
echo ""
echo -e "${YELLOW}New Endpoints Available:${NC}"
echo "  • $SERVICE_URL/mcp/apis"
echo "  • $SERVICE_URL/mcp/apis/<api_id>"
echo "  • $SERVICE_URL/mcp/apis/<api_id>/query"
echo "  • $SERVICE_URL/mcp/apis/query-multiple"
echo "  • $SERVICE_URL/mcp/chat"
echo ""
echo -e "${YELLOW}Frontend URLs:${NC}"
echo "  • https://apiui.web.app/mcp-chat.html"
echo "  • https://apiui.web.app/mcp.html"
echo ""
echo -e "${GREEN}Next Steps:${NC}"
echo "1. Open ${BLUE}https://apiui.web.app/mcp-chat.html${NC}"
echo "2. Select APIs from the grid"
echo "3. Start chatting with your data!"
echo ""
echo -e "${YELLOW}💡 Tip: Run ./test_mcp_chat.sh to test all endpoints${NC}"

