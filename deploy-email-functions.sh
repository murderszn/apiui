#!/bin/bash

# Deploy Email Functions to Firebase
# This script sets up Gmail credentials and deploys the functions

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       🚀 Firebase Email Functions Deployment Script           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo ""
    echo "Please create a .env file with your Gmail credentials:"
    echo "  GMAIL_USER=your-email@gmail.com"
    echo "  GMAIL_APP_PASSWORD=your-app-password"
    echo ""
    exit 1
fi

# Load .env file
echo -e "${BLUE}📁 Loading environment variables from .env...${NC}"
export $(cat .env | grep -v '^#' | xargs)

# Check if Gmail credentials are set
if [ -z "$GMAIL_USER" ] || [ -z "$GMAIL_APP_PASSWORD" ]; then
    echo -e "${RED}❌ Gmail credentials not found in .env!${NC}"
    echo ""
    echo "Make sure your .env file contains:"
    echo "  GMAIL_USER=your-email@gmail.com"
    echo "  GMAIL_APP_PASSWORD=your-app-password"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ Gmail credentials found${NC}"
echo -e "   Email: ${GMAIL_USER}"
echo ""

# Set Firebase config
echo -e "${BLUE}🔧 Setting Firebase Functions configuration...${NC}"
firebase functions:config:set \
  gmail.user="${GMAIL_USER}" \
  gmail.app_password="${GMAIL_APP_PASSWORD}"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to set Firebase config${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Firebase config updated${NC}"
echo ""

# Show current config
echo -e "${BLUE}📋 Current Firebase configuration:${NC}"
firebase functions:config:get
echo ""

# Ask for confirmation
echo -e "${YELLOW}Ready to deploy email functions to Firebase?${NC}"
echo -e "   This will deploy:"
echo -e "   • Newsletter signup endpoint (/api/signup)"
echo -e "   • Beta signup endpoint (/api/beta-signup)"
echo -e "   • MCP chat endpoint (/api/chat)"
echo ""
read -p "Continue? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⏸️  Deployment cancelled${NC}"
    exit 0
fi

# Deploy functions
echo ""
echo -e "${BLUE}🚀 Deploying Firebase Functions...${NC}"
firebase deploy --only functions

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Deployment successful!${NC}"
    echo ""
    echo -e "${BLUE}📝 Next steps:${NC}"
    echo ""
    echo "  1. Test newsletter signup:"
    echo -e "     ${YELLOW}curl -X POST https://ai-apiui.web.app/api/signup \\${NC}"
    echo -e "     ${YELLOW}  -H \"Content-Type: application/json\" \\${NC}"
    echo -e "     ${YELLOW}  -d '{\"email\":\"test@example.com\"}'${NC}"
    echo ""
    echo "  2. Test beta signup:"
    echo -e "     ${YELLOW}curl -X POST https://ai-apiui.web.app/api/beta-signup \\${NC}"
    echo -e "     ${YELLOW}  -H \"Content-Type: application/json\" \\${NC}"
    echo -e "     ${YELLOW}  -d '{\"email\":\"test@example.com\"}'${NC}"
    echo ""
    echo "  3. Visit your site:"
    echo -e "     ${YELLOW}https://ai-apiui.web.app/${NC}"
    echo ""
    echo "  4. Check function logs:"
    echo -e "     ${YELLOW}firebase functions:log --only chat${NC}"
    echo ""
    echo -e "${GREEN}🎉 Your email systems are now live on Firebase!${NC}"
else
    echo ""
    echo -e "${RED}❌ Deployment failed${NC}"
    echo ""
    echo "Check the error messages above and try again."
    echo ""
    echo "Common issues:"
    echo "  • Firebase CLI not logged in (run: firebase login)"
    echo "  • Wrong project selected (run: firebase use --add)"
    echo "  • Missing permissions (check Firebase console)"
    exit 1
fi








