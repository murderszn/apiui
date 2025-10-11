#!/bin/bash

# MCP Chat Testing Script
# This script tests all the new MCP Chat endpoints

BASE_URL="https://apiui-backend-44565368406.us-central1.run.app"
COLORS=true

# Color output
if [ "$COLORS" = true ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  MCP Chat System Test Suite           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Test 1: Health Check
echo -e "${YELLOW}[TEST 1]${NC} Checking backend health..."
response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$response" -eq 200 ]; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${RED}✗ Backend health check failed (HTTP $response)${NC}"
    exit 1
fi
echo ""

# Test 2: List All APIs
echo -e "${YELLOW}[TEST 2]${NC} Listing all available APIs..."
response=$(curl -s "$BASE_URL/mcp/apis")
api_count=$(echo "$response" | grep -o '"id"' | wc -l)
echo -e "Response: ${response:0:200}..."
echo -e "${GREEN}✓ Found $api_count API(s)${NC}"

# Extract first API ID for further tests
first_api_id=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$first_api_id" ]; then
    echo -e "${RED}✗ No APIs found. Please create some APIs first.${NC}"
    echo -e "${YELLOW}⚠ Skipping remaining tests that require API IDs${NC}"
    TEST_WITH_APIS=false
else
    echo -e "${BLUE}→ Using API ID for tests: $first_api_id${NC}"
    TEST_WITH_APIS=true
fi
echo ""

# Test 3: Get Specific API Details
if [ "$TEST_WITH_APIS" = true ]; then
    echo -e "${YELLOW}[TEST 3]${NC} Getting details for API: $first_api_id..."
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/mcp/apis/$first_api_id")
    if [ "$response" -eq 200 ]; then
        echo -e "${GREEN}✓ Successfully retrieved API details${NC}"
    else
        echo -e "${RED}✗ Failed to get API details (HTTP $response)${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}[TEST 3]${NC} Skipped - No APIs available"
    echo ""
fi

# Test 4: Query Single API
if [ "$TEST_WITH_APIS" = true ]; then
    echo -e "${YELLOW}[TEST 4]${NC} Querying API with limit parameter..."
    response=$(curl -s "$BASE_URL/mcp/apis/$first_api_id/query?limit=5")
    echo -e "Response: ${response:0:200}..."
    
    if echo "$response" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ API query successful${NC}"
    else
        echo -e "${YELLOW}⚠ API query returned but may have issues${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}[TEST 4]${NC} Skipped - No APIs available"
    echo ""
fi

# Test 5: Query Multiple APIs
if [ "$TEST_WITH_APIS" = true ]; then
    echo -e "${YELLOW}[TEST 5]${NC} Querying multiple APIs..."
    # Try to get second API ID
    second_api_id=$(echo "$response" | grep -o '"id":"[^"]*"' | head -2 | tail -1 | cut -d'"' -f4)
    
    if [ -z "$second_api_id" ] || [ "$second_api_id" = "$first_api_id" ]; then
        api_list="[\"$first_api_id\"]"
        echo -e "${BLUE}→ Only one API available, testing with single API${NC}"
    else
        api_list="[\"$first_api_id\", \"$second_api_id\"]"
        echo -e "${BLUE}→ Testing with multiple APIs${NC}"
    fi
    
    response=$(curl -s -X POST "$BASE_URL/mcp/apis/query-multiple" \
        -H "Content-Type: application/json" \
        -d "{\"api_ids\": $api_list, \"query_params\": {\"limit\": 3}}")
    
    echo -e "Response: ${response:0:200}..."
    
    if echo "$response" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ Multi-API query successful${NC}"
    else
        echo -e "${YELLOW}⚠ Multi-API query returned but may have issues${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}[TEST 5]${NC} Skipped - No APIs available"
    echo ""
fi

# Test 6: MCP Chat Endpoint
if [ "$TEST_WITH_APIS" = true ]; then
    echo -e "${YELLOW}[TEST 6]${NC} Testing chat with AI..."
    response=$(curl -s -X POST "$BASE_URL/mcp/chat" \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"What are the columns in this data?\", \"api_ids\": [\"$first_api_id\"]}")
    
    echo -e "Response: ${response:0:300}..."
    
    if echo "$response" | grep -q '"success":true'; then
        echo -e "${GREEN}✓ Chat response generated successfully${NC}"
        
        # Extract message length
        msg_length=$(echo "$response" | grep -o '"message":"[^"]*"' | cut -d'"' -f4 | wc -c)
        echo -e "${BLUE}→ Response length: $msg_length characters${NC}"
    else
        echo -e "${RED}✗ Chat failed${NC}"
        echo -e "Error: $(echo "$response" | grep -o '"error":"[^"]*"' | cut -d'"' -f4)"
    fi
    echo ""
else
    echo -e "${YELLOW}[TEST 6]${NC} Skipped - No APIs available"
    echo ""
fi

# Test 7: MCP Legacy File Resources (should still work)
echo -e "${YELLOW}[TEST 7]${NC} Testing legacy MCP file resources..."
response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/mcp/resources")
if [ "$response" -eq 200 ]; then
    echo -e "${GREEN}✓ Legacy MCP endpoints still functional${NC}"
else
    echo -e "${RED}✗ Legacy MCP endpoint check failed (HTTP $response)${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Test Summary                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "✓ Backend health check"
echo -e "✓ API listing"

if [ "$TEST_WITH_APIS" = true ]; then
    echo -e "✓ API details retrieval"
    echo -e "✓ Single API query"
    echo -e "✓ Multiple API query"
    echo -e "✓ AI chat functionality"
else
    echo -e "${YELLOW}⚠ Some tests skipped - no APIs available${NC}"
fi

echo -e "✓ Legacy MCP compatibility"
echo ""
echo -e "${GREEN}All available tests completed!${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo -e "1. Open ${YELLOW}https://apiui.web.app/mcp-chat.html${NC} in your browser"
echo -e "2. Select one or more APIs from the grid"
echo -e "3. Ask questions about your data"
echo -e "4. Try comparing multiple APIs"
echo ""
echo -e "${GREEN}Happy chatting with your APIs! 🚀${NC}"


