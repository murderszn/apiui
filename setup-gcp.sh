#!/bin/bash

# Setup script for Google Cloud Platform resources
# This script helps configure GCS bucket and permissions for apiui

set -e

echo "🚀 Setting up Google Cloud Platform resources for apiui..."
echo ""

# Configuration
PROJECT_ID=${PROJECT_ID:-"aurablox-ai"}
BUCKET_NAME=${BUCKET_NAME:-"apiui-files-${PROJECT_ID}"}
REGION=${REGION:-"us-central1"}

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
gcloud services enable storage.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Create GCS bucket
echo -e "${YELLOW}📦 Creating GCS bucket: gs://${BUCKET_NAME}${NC}"
if gsutil ls -b gs://${BUCKET_NAME} &> /dev/null; then
    echo -e "${GREEN}✅ Bucket gs://${BUCKET_NAME} already exists${NC}"
else
    gsutil mb -p ${PROJECT_ID} -l ${REGION} gs://${BUCKET_NAME}
    echo -e "${GREEN}✅ Created bucket: gs://${BUCKET_NAME}${NC}"
fi

# Set bucket permissions for public access (adjust as needed for your security requirements)
echo -e "${YELLOW}🔒 Configuring bucket permissions...${NC}"

# Create a service account for Cloud Run
SERVICE_ACCOUNT_NAME="apiui-backend-sa"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo -e "${YELLOW}👤 Creating service account: ${SERVICE_ACCOUNT_EMAIL}${NC}"
if gcloud iam service-accounts describe ${SERVICE_ACCOUNT_EMAIL} &> /dev/null; then
    echo -e "${GREEN}✅ Service account already exists${NC}"
else
    gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
        --description="Service account for apiui backend" \
        --display-name="apiui Backend Service Account"
    echo -e "${GREEN}✅ Created service account${NC}"
fi

# Grant Storage Object Admin role to the service account
echo -e "${YELLOW}🔑 Granting GCS permissions to service account...${NC}"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectAdmin"

echo -e "${GREEN}✅ Granted Storage Object Admin permissions${NC}"

# Set bucket CORS (for web access if needed)
echo -e "${YELLOW}🌐 Setting bucket CORS policy...${NC}"
cat > cors-config.json << EOF
[
  {
    "origin": ["*"],
    "method": ["GET", "POST", "PUT", "DELETE"],
    "responseHeader": ["Content-Type", "Authorization"],
    "maxAgeSeconds": 3600
  }
]
EOF

gsutil cors set cors-config.json gs://${BUCKET_NAME}
rm cors-config.json

echo -e "${GREEN}✅ Set CORS policy${NC}"

# Display setup summary
echo ""
echo -e "${GREEN}🎉 Google Cloud Platform setup complete!${NC}"
echo ""
echo -e "${YELLOW}📋 Summary:${NC}"
echo -e "  Project ID: ${PROJECT_ID}"
echo -e "  GCS Bucket: gs://${BUCKET_NAME}"
echo -e "  Service Account: ${SERVICE_ACCOUNT_EMAIL}"
echo -e "  Region: ${REGION}"
echo ""
echo -e "${YELLOW}🔧 Next steps:${NC}"
echo "1. Set these environment variables in Cloud Run:"
echo "   USE_GCS_STORAGE=True"
echo "   GCS_BUCKET_NAME=${BUCKET_NAME}"
echo "   GCS_PROJECT_ID=${PROJECT_ID}"
echo ""
echo "2. For MongoDB (optional but recommended):"
echo "   Set MONGODB_URL=mongodb+srv://..."
echo ""
echo "3. Deploy your application:"
echo "   ./deploy-cloud-run.sh"
echo ""
echo -e "${YELLOW}📚 Useful commands:${NC}"
echo "  Check bucket contents: gsutil ls gs://${BUCKET_NAME}/"
echo "  View bucket permissions: gsutil iam get gs://${BUCKET_NAME}"
echo "  View service logs: gcloud logging read \"resource.type=cloud_run_revision\" --limit=10"
