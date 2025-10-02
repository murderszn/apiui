const functions = require('firebase-functions');
const admin = require('firebase-admin');
const express = require('express');
const cors = require('cors');
const axios = require('axios');
const OpenAI = require('openai');

// Initialize Firebase Admin
admin.initializeApp();

// Configuration
const FLASK_BACKEND_URL = functions.config().apiui?.flask_backend_url || 'https://apiui-backend-44565368406.us-central1.run.app';
const OPENAI_API_KEY = functions.config().apiui?.openai_api_key;

// Initialize Express app
const app = express();
app.use(cors({ origin: true }));
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
        const apisResponse = await axios.get(`${FLASK_BACKEND_URL}/v1/apis`);
        const api = apisResponse.data.apis.find(a => a.id === apiId);

        if (!api) {
            throw new Error(`API ${apiId} not found`);
        }

        // Get API metadata
        const apiUrl = api.url || `${FLASK_BACKEND_URL}/api/${apiId}`;
        console.log(`Fetching API metadata from: ${apiUrl}`);
        const apiResponse = await axios.get(apiUrl);

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
                const sampleResponse = await axios.get(sampleUrl);
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
    } catch (error) {
        console.error(`Error fetching API data for ${apiId}:`, error.message);
        throw error;
    }
}

// Build API context string
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

// Generate chat response
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

// Chat API endpoint
app.post('/chat', async (req, res) => {
    try {
        const { message, api_id, user_id = 'anonymous' } = req.body;

        if (!message || !api_id) {
            return res.status(400).json({ error: 'Missing message or api_id' });
        }

        console.log(`Chat request from ${user_id} for API ${api_id}: ${message}`);

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
        console.error('Chat API error:', error);
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

// API listing endpoint for chat-enabled APIs (proxy to Flask backend)
app.get('/apis', async (req, res) => {
    try {
        const response = await axios.get(`${FLASK_BACKEND_URL}/v1/apis`);
        res.json(response.data);
    } catch (error) {
        console.error('Error fetching APIs:', error.message);
        res.status(500).json({ error: 'Failed to fetch APIs' });
    }
});

// Export the Express app as a Firebase Function
exports.chat = functions.https.onRequest(app);
