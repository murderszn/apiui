# MCP Chat - Chat with Your APIs Using Natural Language

## Overview

MCP Chat is a new feature that allows you to interact with your generated APIs using natural language. Built on top of the Model Context Protocol (MCP), it enables RAG-style conversations with your data across single or multiple APIs.

## Features

### ✨ Key Capabilities

1. **Multi-API Selection**
   - Select one or multiple APIs to chat with
   - Visual API selector with real-time updates
   - See API metadata (name, description, row count)

2. **Natural Language Queries**
   - Ask questions in plain English
   - Get AI-powered responses based on actual data
   - Context-aware conversations

3. **Cross-API Analysis**
   - Compare data across multiple APIs
   - Find relationships between datasets
   - Aggregate insights from multiple sources

4. **RAG-Style Architecture**
   - Real-time data retrieval from APIs
   - Schema-aware responses
   - Sample data for context

## Architecture

### Backend Components

#### 1. MCP API Service (`backend/services/mcp_api_service.py`)
- **Purpose**: Exposes all generated APIs as queryable MCP resources
- **Key Features**:
  - Lists all available APIs with metadata
  - Fetches sample data from each API
  - Queries single or multiple APIs
  - Combines results from multiple sources
  - Caching mechanism (60-second TTL)

#### 2. New MCP Endpoints (`backend/main.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp/apis` | GET | List all available APIs |
| `/mcp/apis/<api_id>` | GET | Get specific API details |
| `/mcp/apis/<api_id>/query` | GET/POST | Query a specific API |
| `/mcp/apis/query-multiple` | POST | Query multiple APIs at once |
| `/mcp/chat` | POST | Chat with selected APIs using AI |

### Frontend Component

#### MCP Chat Interface (`frontend/mcp-chat.html`)
- **API Selector**: Grid of selectable API cards
- **Chat Interface**: Real-time message display
- **Multi-selection**: Toggle multiple APIs
- **Loading States**: Visual feedback during processing
- **Error Handling**: User-friendly error messages

## Usage Guide

### For Users

1. **Navigate to MCP Chat**
   - Visit `/mcp-chat.html` or click "Chat" in the navigation
   - Or click "Chat with APIs" card on the MCP page

2. **Select APIs**
   - Click on one or more API cards to select them
   - Selected APIs will be highlighted in pink
   - Selected count is shown at the top

3. **Ask Questions**
   - Type your question in natural language
   - Examples:
     - "What are the columns in this data?"
     - "Show me a summary of the first 5 records"
     - "Compare sales data between API 1 and API 2"
     - "What's the total number of records?"

4. **Review Responses**
   - AI will analyze the selected APIs and respond
   - Response includes which APIs were used
   - Messages show in a clean chat interface

### Example Queries

#### Single API Queries
```
- "What columns are available?"
- "Show me the first 10 records"
- "What's the data type of each column?"
- "How many rows are in this dataset?"
- "Give me statistics about the data"
```

#### Multi-API Queries
```
- "Compare the schemas of the selected APIs"
- "Which API has the most records?"
- "Show me common columns across these datasets"
- "What's the total number of records across all selected APIs?"
- "Find relationships between these datasets"
```

## API Response Format

### `/mcp/apis` Response
```json
{
  "apis": [
    {
      "id": "abc123",
      "name": "Sales Data",
      "description": "Monthly sales records",
      "endpoint_url": "https://..../api/abc123/data",
      "schema": {
        "columns": [
          {
            "name": "date",
            "inferred_type": "string",
            "nullable": false
          }
        ],
        "row_count": 1000
      },
      "sample_data": [...],
      "created_at": "2025-01-15T10:30:00",
      "status": "ready"
    }
  ],
  "total": 1
}
```

### `/mcp/chat` Request
```json
{
  "message": "What are the columns in the data?",
  "api_ids": ["abc123", "def456"]
}
```

### `/mcp/chat` Response
```json
{
  "success": true,
  "message": "Based on the selected APIs, here are the columns available: ...",
  "apis_used": ["abc123", "def456"],
  "timestamp": "2025-01-15T10:35:00"
}
```

## Testing the System

### Manual Testing Steps

1. **Test API Discovery**
   ```bash
   curl https://apiui-backend-44565368406.us-central1.run.app/mcp/apis
   ```
   - Should return list of all available APIs
   - Verify metadata is present

2. **Test Single API Query**
   ```bash
   curl https://apiui-backend-44565368406.us-central1.run.app/mcp/apis/<api_id>/query
   ```
   - Should return data from the API
   - Verify sample_data is included

3. **Test Multi-API Query**
   ```bash
   curl -X POST https://apiui-backend-44565368406.us-central1.run.app/mcp/apis/query-multiple \
     -H "Content-Type: application/json" \
     -d '{"api_ids": ["api1", "api2"], "query_params": {"limit": 5}}'
   ```
   - Should return combined results
   - Verify both APIs are queried

4. **Test Chat Interface**
   ```bash
   curl -X POST https://apiui-backend-44565368406.us-central1.run.app/mcp/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What are the columns?", "api_ids": ["api1"]}'
   ```
   - Should return AI-generated response
   - Verify context includes schema information

### UI Testing

1. **Load MCP Chat Page**
   - Open `/mcp-chat.html`
   - Verify APIs load successfully
   - Check for visual issues

2. **Test API Selection**
   - Click multiple APIs
   - Verify selection highlighting
   - Check selected count updates

3. **Test Chat Functionality**
   - Send a simple question
   - Verify loading indicator appears
   - Check response displays correctly
   - Verify "Used data from" section shows

4. **Test Error Handling**
   - Try sending without selecting APIs
   - Try with network issues
   - Verify error messages are user-friendly

5. **Test Multi-API Chat**
   - Select 2-3 APIs
   - Ask comparative questions
   - Verify all APIs are used in response

## Configuration

### Backend Configuration

The MCP API service is automatically configured when the backend starts:

```python
# In backend/main.py
mcp_api_service.set_jobs_reference(jobs)
mcp_api_service.set_running_apis_reference(running_apis)
mcp_api_service.set_api_metadata_reference(api_metadata)
```

### Frontend Configuration

The frontend automatically detects the environment:

```javascript
const isLocalhost = window.location.hostname === 'localhost' || 
                   window.location.hostname === '127.0.0.1';
window.APIUI_AUTH_BASE_URL = 'https://apiui-backend-44565368406.us-central1.run.app';
```

## Troubleshooting

### APIs Not Loading

**Problem**: API selector shows loading forever or error

**Solutions**:
1. Check backend is running: `curl https://apiui-backend-44565368406.us-central1.run.app/health`
2. Verify `/mcp/apis` endpoint: `curl https://apiui-backend-44565368406.us-central1.run.app/mcp/apis`
3. Check browser console for errors
4. Verify CORS is configured correctly

### Chat Not Responding

**Problem**: Messages send but no response appears

**Solutions**:
1. Check that APIs are selected (count > 0)
2. Verify AI service is configured with API key
3. Check backend logs for errors
4. Test `/mcp/chat` endpoint directly with curl

### Sample Data Not Showing

**Problem**: APIs load but show 0 rows or no data

**Solutions**:
1. Verify API endpoints are accessible
2. Check that APIs actually have data
3. Test API directly: `curl <api_endpoint>/data?limit=5`
4. Check for SSL certificate issues (should auto-disable verification)

### Multiple API Selection Issues

**Problem**: Selecting multiple APIs doesn't work correctly

**Solutions**:
1. Clear browser cache
2. Check JavaScript console for errors
3. Verify selectedAPIIds Set is updating
4. Test with a single API first

## Performance Considerations

### Caching
- API resources are cached for 60 seconds
- Reduces load on backend
- Automatically refreshes when needed

### Sample Data Limits
- Maximum 5 records per API for chat context
- Keeps AI prompts manageable
- Reduces response time

### Query Limits
- Default limit of 10 records per query
- Can be adjusted via query parameters
- Prevents overwhelming the client

## Future Enhancements

### Planned Features
1. **Conversation History**: Save and resume chat sessions
2. **Data Visualization**: Generate charts from chat queries
3. **Export Results**: Download chat responses as files
4. **Advanced Filters**: Apply filters through natural language
5. **Streaming Responses**: Real-time AI responses
6. **API Recommendations**: Suggest relevant APIs based on questions
7. **Query Templates**: Pre-built question templates
8. **Collaborative Chat**: Share chat sessions with team

### Integration Ideas
1. **Slack/Discord Bot**: Chat with APIs from messaging platforms
2. **API Keys**: Per-API authentication for secure access
3. **Rate Limiting**: Prevent API abuse
4. **Analytics**: Track popular queries and APIs
5. **Feedback System**: Improve AI responses based on user feedback

## Technical Details

### Dependencies

**Backend**:
- `requests`: HTTP requests to APIs
- `pandas`: Data manipulation
- `asyncio`: Async operations
- `dataclasses`: Data structures

**Frontend**:
- Vanilla JavaScript (no framework)
- TailwindCSS: Styling
- Native Fetch API: HTTP requests

### Security

1. **Input Validation**: All user inputs are validated
2. **Error Handling**: Comprehensive error catching
3. **CORS**: Properly configured for frontend access
4. **SSL**: Disabled verification for Cloud Run APIs (internal use)
5. **No Authentication Yet**: Public access (to be added)

## Contributing

To add new features or fix bugs:

1. **Backend Changes**:
   - Edit `backend/services/mcp_api_service.py` for service logic
   - Add new endpoints in `backend/main.py`
   - Update this README with new endpoints

2. **Frontend Changes**:
   - Edit `frontend/mcp-chat.html` for UI changes
   - Follow existing styling patterns
   - Test on multiple screen sizes

3. **Testing**:
   - Add manual test cases to this document
   - Test all edge cases
   - Verify error handling

## License

Part of the APIUI project by AURABLOX.

## Support

For issues or questions:
1. Check this README first
2. Review backend logs
3. Test endpoints with curl
4. Check browser console for errors

