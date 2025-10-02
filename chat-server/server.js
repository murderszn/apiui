const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const cors = require('cors');
const axios = require('axios');
const OpenAI = require('openai');
require('dotenv').config();

// Configuration
const PORT = process.env.CHAT_PORT || 3001;
const FLASK_BACKEND_URL = process.env.FLASK_BACKEND_URL || 'http://localhost:9999';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;

// Initialize Express app
const app = express();
const server = http.createServer(app);

// Initialize Socket.io with CORS
const io = socketIo(server, {
    cors: {
        origin: ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://localhost:9999", "http://127.0.0.1:9999"],
        methods: ["GET", "POST"],
        credentials: true
    }
});

// Middleware
app.use(cors({
    origin: true, // Allow all origins
    credentials: true
}));
app.use(express.json());

// Initialize OpenAI client
let openai = null;
if (OPENAI_API_KEY) {
    openai = new OpenAI({
        apiKey: OPENAI_API_KEY,
    });
    console.log('✅ OpenAI client initialized');
} else {
    console.log('⚠️  OpenAI API key not found, using mock responses');
}

// Axios configuration for handling Cloud Run SSL certificates
const axiosConfig = {
    httpsAgent: new (require('https').Agent)({
        rejectUnauthorized: false, // Allow self-signed certificates for Cloud Run
    }),
    timeout: 30000, // 30 second timeout
};

// Cache for API data
const apiCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// Helper function to get API data from Flask backend
async function getApiData(apiId) {
    try {
        // Check cache first
        const cached = apiCache.get(apiId);
        if (cached && (Date.now() - cached.timestamp) < CACHE_TTL) {
            return cached.data;
        }

        // First check if API exists in the list
        const apisResponse = await axios.get(`${FLASK_BACKEND_URL}/v1/apis`, axiosConfig);
        const api = apisResponse.data.apis.find(a => a.id === apiId);

        if (!api) {
            throw new Error(`API ${apiId} not found`);
        }

        // Get API metadata
        const apiUrl = api.url; // e.g., "http://localhost:9999/api/{apiId}"
        console.log(`Fetching API metadata from: ${apiUrl}`);
        const apiResponse = await axios.get(apiUrl, axiosConfig);

        if (!apiResponse.data) {
            throw new Error(`Failed to fetch API metadata`);
        }

        console.log(`API metadata fetched successfully`);

        if (apiResponse.status === 200) {
            // Try to get sample data
            let sampleData = null;
            try {
                const sampleUrl = `${FLASK_BACKEND_URL}/api/${apiId}/data?limit=5`;
                console.log(`Fetching sample data from: ${sampleUrl}`);
                const sampleResponse = await axios.get(sampleUrl, axiosConfig);
                if (sampleResponse.status === 200 && sampleResponse.data.data) {
                    sampleData = sampleResponse.data.data;
                    console.log(`Sample data fetched: ${sampleData.length} records`);
                } else {
                    console.log(`No sample data in response`);
                }
            } catch (error) {
                console.log(`No sample data available for API ${apiId}:`, error.message);
            }

            const apiData = {
                ...apiResponse.data,
                sampleData: sampleData,
                lastFetched: Date.now()
            };

            // Cache the data
            apiCache.set(apiId, {
                data: apiData,
                timestamp: Date.now()
            });

            return apiData;
        }

        throw new Error(`API ${apiId} not found`);
    } catch (error) {
        console.error(`Error fetching API data for ${apiId}:`, error.message);
        throw error;
    }
}

// Build context for OpenAI
function buildApiContext(apiData) {
    const context = [];

    // Basic API info
    context.push(`API Title: ${apiData.title || 'Untitled API'}`);
    context.push(`API ID: ${apiData.id}`);

    // Data schema info
    if (apiData.data_schema && apiData.data_schema.columns) {
        context.push(`Number of columns: ${apiData.data_schema.columns.length}`);
        context.push('Columns:');

        apiData.data_schema.columns.slice(0, 10).forEach(col => {
            const type = col.inferred_type || 'unknown';
            const nullable = col.nullable ? 'nullable' : 'required';
            context.push(`  - ${col.name}: ${type} (${nullable})`);
        });

        if (apiData.data_schema.columns.length > 10) {
            context.push(`  ... and ${apiData.data_schema.columns.length - 10} more columns`);
        }
    }

    // Record count
    if (apiData.record_count) {
        context.push(`Total records: ${apiData.record_count}`);
    }

    // Sample data
    if (apiData.sampleData && apiData.sampleData.length > 0) {
        context.push(`Sample records available: ${apiData.sampleData.length} shown`);
        context.push('');
        context.push('Here are the sample records:');
        apiData.sampleData.slice(0, 5).forEach((record, index) => {
            context.push(`${index + 1}. ${JSON.stringify(record)}`);
        });
    }

    return context.join('\n');
}

// Generate AI chat response
async function generateChatResponse(message, apiData) {
    if (!openai) {
        // Mock response when no OpenAI key
        return generateMockResponse(message, apiData);
    }

    try {
        const context = buildApiContext(apiData);

        const systemPrompt = `You are a data API assistant. You have access to a dataset with the following information:

${context}

Your role is to provide structured, data-focused responses to help developers work with this dataset. Always format data as clean JSON when showing records. Be direct and technical in your responses. Focus on providing actionable data insights rather than conversational explanations.

When showing data:
- Format records as properly indented JSON
- Include field types and descriptions when relevant
- Be concise and data-oriented
- Avoid unnecessary conversational language`;

        const completion = await openai.chat.completions.create({
            model: "gpt-4",
            messages: [
                {
                    role: "system",
                    content: systemPrompt
                },
                {
                    role: "user",
                    content: message
                }
            ],
            max_tokens: 1000,
            temperature: 0.7
        });

        return completion.choices[0].message.content.trim();
    } catch (error) {
        console.error('OpenAI API error:', error);
        return generateMockResponse(message, apiData);
    }
}

// Generate mock responses when OpenAI is not available
function generateMockResponse(message, apiData) {
    const msg = message.toLowerCase();

    if (msg.includes('count') || msg.includes('how many')) {
        const count = apiData.record_count || apiData.data_schema?.row_count || 'unknown';
        return `Dataset record count: ${count}`;
    }

    if (msg.includes('columns') || msg.includes('fields')) {
        const columns = apiData.data_schema?.columns || [];
        const columnInfo = columns.map(col => `${col.name} (${col.inferred_type})`).slice(0, 10);
        return `Available columns (${columns.length} total):\n${columnInfo.join('\n')}${columns.length > 10 ? `\n... and ${columns.length - 10} more` : ''}`;
    }

    if (msg.includes('sample') || msg.includes('show me') || msg.includes('examples')) {
        if (apiData.sampleData && apiData.sampleData.length > 0) {
            return `Sample records (${apiData.sampleData.length}):\n${JSON.stringify(apiData.sampleData, null, 2)}`;
        } else {
            return "Sample data not available.";
        }
    }

    if (msg.includes('describe') || msg.includes('summary')) {
        const columns = apiData.data_schema?.columns || [];
        const count = apiData.record_count || 'unknown';
        return `Dataset: ${count} records, ${columns.length} columns\nSchema: ${columns.map(col => `${col.name}:${col.inferred_type}`).join(', ')}`;
    }

    return "Available queries: count, columns, sample, describe";
}

// Socket.io connection handling
io.on('connection', (socket) => {
    console.log(`Client connected: ${socket.id}`);

    socket.on('chat_message', async (data) => {
        try {
            const { message, api_id, user_id = 'anonymous' } = data;

            if (!message || !api_id) {
                socket.emit('error', { message: 'Missing message or api_id' });
                return;
            }

            console.log(`Chat message from ${user_id} for API ${api_id}: ${message}`);

            // Get API data
            const apiData = await getApiData(api_id);

            // Generate response
            const response = await generateChatResponse(message, apiData);

            // Send response
            socket.emit('chat_response', {
                type: 'success',
                message: response,
                timestamp: new Date().toISOString(),
                api_id: api_id
            });

        } catch (error) {
            console.error('Chat message error:', error);
            socket.emit('error', {
                message: error.message || 'Failed to process chat message'
            });
        }
    });

    socket.on('query_data', async (data) => {
        try {
            const { api_id, query = {} } = data;

            if (!api_id) {
                socket.emit('error', { message: 'Missing api_id' });
                return;
            }

            // For now, just return sample data or basic info
            const apiData = await getApiData(api_id);

            socket.emit('query_result', {
                type: 'success',
                data: apiData.sampleData || [],
                total_count: apiData.record_count || 0,
                api_id: api_id
            });

        } catch (error) {
            console.error('Query data error:', error);
            socket.emit('error', {
                message: error.message || 'Failed to query data'
            });
        }
    });

    socket.on('ping', () => {
        socket.emit('pong');
    });

    socket.on('disconnect', () => {
        console.log(`Client disconnected: ${socket.id}`);
    });
});

// HTTP endpoints for fallback
app.post('/api/chat', async (req, res) => {
    try {
        const { message, api_id, user_id = 'anonymous' } = req.body;

        if (!message || !api_id) {
            return res.status(400).json({ error: 'Missing message or api_id' });
        }

        // Get API data
        let apiData;
        try {
            apiData = await getApiData(api_id);
        } catch (error) {
            console.error(`Failed to get API data for ${api_id}:`, error.message);
            return res.status(404).json({
                type: 'error',
                message: `API ${api_id} not found or unavailable. Please check your API ID.`
            });
        }

        // Generate response
        const response = await generateChatResponse(message, apiData);

        res.json({
            type: 'success',
            message: response,
            timestamp: new Date().toISOString(),
            api_id: api_id
        });

    } catch (error) {
        console.error('HTTP Chat error:', error);
        res.status(500).json({
            type: 'error',
            message: error.message || 'Failed to process chat message'
        });
    }
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        openai: !!openai,
        flask_backend: FLASK_BACKEND_URL
    });
});

// API listing endpoint (proxy to Flask backend)
app.get('/api/apis', async (req, res) => {
    try {
        const response = await axios.get(`${FLASK_BACKEND_URL}/v1/apis`, axiosConfig);
        res.json(response.data);
    } catch (error) {
        console.error('Error fetching APIs:', error.message);
        res.status(500).json({ error: 'Failed to fetch APIs' });
    }
});

// Start server
server.listen(PORT, () => {
    console.log(`🚀 Chat server running on port ${PORT}`);
    console.log(`🔗 Socket.io endpoint: ws://localhost:${PORT}`);
    console.log(`🌐 HTTP fallback: http://localhost:${PORT}/api/chat`);
    console.log(`🏥 Health check: http://localhost:${PORT}/health`);
    console.log(`🤖 OpenAI integration: ${openai ? 'Enabled' : 'Disabled (using mock responses)'}`);
    console.log(`🔗 Flask backend: ${FLASK_BACKEND_URL}`);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('Shutting down chat server...');
    server.close(() => {
        console.log('Chat server stopped');
        process.exit(0);
    });
});
