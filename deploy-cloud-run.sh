#!/bin/bash

# Cloud Run Deployment Script for apiui
# This script builds and deploys the API backend to Google Cloud Run

set -e

echo "🚀 Starting Cloud Run deployment for apiui..."

# Load configuration from cloudrun.env if available
ENV_FILE="cloudrun.env"
if [[ -f "${ENV_FILE}" ]]; then
    echo -e "${YELLOW}📄 Loading deployment configuration from ${ENV_FILE}${NC}"
    set -o allexport
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +o allexport
else
    echo -e "${YELLOW}⚠️  ${ENV_FILE} not found. Using current environment variables.${NC}"
fi

# Configuration
PROJECT_ID=${PROJECT_ID:-"aurablox-ai"}
SERVICE_NAME=${SERVICE_NAME:-"apiui-backend"}
REGION=${REGION:-"us-central1"}
IMAGE_NAME=${IMAGE_NAME:-"gcr.io/${PROJECT_ID}/${SERVICE_NAME}"}
IMAGE_TAG=${IMAGE_TAG:-"latest"}

if [[ -z "${PROJECT_ID}" ]]; then
    echo -e "${RED}❌ PROJECT_ID is not set. Update ${ENV_FILE} or export PROJECT_ID first.${NC}"
    exit 1
fi

if [[ -z "${REGION}" ]]; then
    echo -e "${RED}❌ REGION is not set. Update ${ENV_FILE} or export REGION first.${NC}"
    exit 1
fi

add_env_var() {
    local key="$1"
    local value="$2"
    if [[ -n "${value}" ]]; then
        ENV_VARS+=("${key}=${value}")
    fi
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI is not installed. Please install Google Cloud SDK first.${NC}"
    echo "Visit: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${RED}❌ Not authenticated with Google Cloud. Please run:${NC}"
    echo "gcloud auth login"
    exit 1
fi

# Set project
echo -e "${YELLOW}🔧 Setting project to: ${PROJECT_ID}${NC}"
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo -e "${YELLOW}🔌 Enabling required Google Cloud APIs...${NC}"
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Build and push Docker image using Cloud Build
echo -e "${YELLOW}🏗️  Building Docker image with Cloud Build...${NC}"
gcloud builds submit --config cloudbuild.yaml --timeout=900 .

# Build environment variable list
declare -a ENV_VARS
ENV_VARS+=("FLASK_DEBUG=False")
ENV_VARS+=("USE_GCS_STORAGE=${USE_GCS_STORAGE:-True}")

BUCKET_NAME=${GCS_BUCKET_NAME:-"apiui-files-${PROJECT_ID}"}
ENV_VARS+=("GCS_BUCKET_NAME=${BUCKET_NAME}")
ENV_VARS+=("GCS_PROJECT_ID=${GCS_PROJECT_ID:-${PROJECT_ID}}")

add_env_var "OPENAI_API_KEY" "${OPENAI_API_KEY}"
add_env_var "GOOGLE_AI_API_KEY" "${GOOGLE_AI_API_KEY}"
add_env_var "MONGODB_URL" "${MONGODB_URL}"
add_env_var "DATABASE_NAME" "${DATABASE_NAME}"
add_env_var "SECRET_KEY" "${SECRET_KEY}"
add_env_var "GCP_PROJECT_ID" "${GCP_PROJECT_ID:-${PROJECT_ID}}"
add_env_var "GCP_REGION" "${GCP_REGION:-${REGION}}"
add_env_var "API_GATEWAY_URL" "${API_GATEWAY_URL}"
add_env_var "GITHUB_CLIENT_ID" "${GITHUB_CLIENT_ID}"
add_env_var "GITHUB_CLIENT_SECRET" "${GITHUB_CLIENT_SECRET}"
add_env_var "GITHUB_REDIRECT_URI" "${GITHUB_REDIRECT_URI}"
add_env_var "GOOGLE_CLIENT_ID" "${GOOGLE_CLIENT_ID}"
add_env_var "GOOGLE_CLIENT_SECRET" "${GOOGLE_CLIENT_SECRET}"
add_env_var "GOOGLE_REDIRECT_URI" "${GOOGLE_REDIRECT_URI}"

ENV_VARS_STRING=$(printf "%s," "${ENV_VARS[@]}")
ENV_VARS_STRING=${ENV_VARS_STRING%,}

echo -e "${YELLOW}🚀 Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME}:${IMAGE_TAG} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --port 9999 \
    --memory 1Gi \
    --cpu 1 \
    --max-instances 10 \
    --concurrency 80 \
    --timeout 300 \
    --set-env-vars="${ENV_VARS_STRING}"

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")

echo -e "${GREEN}✅ Deployment successful!${NC}"
echo -e "${GREEN}🌐 Your API is available at: ${SERVICE_URL}${NC}"
echo ""
echo -e "${YELLOW}📚 API Documentation:${NC}"
echo -e "  Health Check: ${SERVICE_URL}/health"
echo -e "  API List: ${SERVICE_URL}/v1/apis"
echo -e "  Upload File: ${SERVICE_URL}/v1/generate (POST with file)"
echo ""
echo -e "${YELLOW}🔧 Environment Variables you can set:${NC}"
echo -e "  OPENAI_API_KEY - For AI-powered API generation"
echo -e "  MONGODB_URL - Database connection (if using external MongoDB)"
echo ""

# Optional: Set up custom domain
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "1. Consider setting up a custom domain in Cloud Run"
echo "2. Add OPENAI_API_KEY environment variable for better API generation"
echo "3. Set up monitoring and logging in Google Cloud Console"
echo "4. Consider using Firebase for the frontend deployment"
