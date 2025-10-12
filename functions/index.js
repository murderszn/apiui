const functions = require('firebase-functions');
const admin = require('firebase-admin');
const express = require('express');
const cors = require('cors');
const axios = require('axios');
const OpenAI = require('openai');
const nodemailer = require('nodemailer');

// Initialize Firebase Admin
admin.initializeApp();

// Configuration
const FLASK_BACKEND_URL = functions.config().apiui?.flask_backend_url || 'https://apiui-backend-44565368406.us-central1.run.app';
const OPENAI_API_KEY = functions.config().apiui?.openai_api_key;
const GMAIL_USER = functions.config().gmail?.user || process.env.GMAIL_USER;
const GMAIL_APP_PASSWORD = functions.config().gmail?.app_password || process.env.GMAIL_APP_PASSWORD;

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

// Initialize Nodemailer transporter
let transporter = null;
if (GMAIL_USER && GMAIL_APP_PASSWORD) {
    transporter = nodemailer.createTransport({
        service: 'gmail',
        auth: {
            user: GMAIL_USER,
            pass: GMAIL_APP_PASSWORD
        }
    });
    console.log('✅ Email transporter initialized');
} else {
    console.log('⚠️  Gmail credentials not found, email features disabled');
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

// Newsletter signup endpoint
app.post('/signup', async (req, res) => {
    const { email } = req.body;

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return res.status(400).json({
            success: false,
            error: 'Invalid email address'
        });
    }

    if (!transporter) {
        return res.status(503).json({
            success: false,
            error: 'Email service not configured'
        });
    }

    console.log(`📧 New newsletter signup: ${email}`);

    try {
        // Email to the user (Thank you message)
        const userMailOptions = {
            from: `"APIUI" <${GMAIL_USER}>`,
            to: email,
            subject: '🎉 Welcome to APIUI Newsletter!',
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Pixelify+Sans:wght@600;700&display=swap" rel="stylesheet">
                    <style>
                        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background-color: #f8fafc; }
                        .container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 2px solid #0f172a; box-shadow: 4px 4px 0 rgba(15, 23, 42, 0.25); }
                        .header { background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); padding: 40px 20px; text-align: center; border-bottom: 2px solid #0f172a; position: relative; }
                        .header::after { content: ''; position: absolute; top: 0; right: 0; width: 12px; height: 12px; background-image: linear-gradient(90deg, #ec4899 50%, transparent 50%), linear-gradient(180deg, #ec4899 50%, transparent 50%); background-size: 4px 4px; }
                        .header h1 { color: #ffffff; margin: 0; font-size: 32px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; font-family: 'Pixelify Sans', monospace; }
                        .header .tagline { color: rgba(255, 255, 255, 0.9); font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; margin-top: 8px; font-weight: 600; }
                        .content { padding: 40px 30px; background-image: linear-gradient(rgba(236, 72, 153, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(236, 72, 153, 0.02) 1px, transparent 1px); background-size: 24px 24px; }
                        .eyebrow { color: #ec4899; font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; font-weight: 700; margin-bottom: 12px; font-family: 'Pixelify Sans', monospace; }
                        .content h2 { color: #0f172a; font-size: 28px; margin-bottom: 20px; font-weight: 700; line-height: 1.3; }
                        .content p { color: #64748b; line-height: 1.8; margin-bottom: 15px; font-size: 16px; }
                        .features { background-color: #ffffff; border: 2px solid #0f172a; box-shadow: 2px 2px 0 rgba(236, 72, 153, 0.25); padding: 24px; margin: 25px 0; position: relative; }
                        .features::after { content: ''; position: absolute; top: 0; right: 0; width: 10px; height: 10px; background-image: linear-gradient(90deg, #ec4899 50%, transparent 50%), linear-gradient(180deg, #ec4899 50%, transparent 50%); background-size: 3px 3px; }
                        .features li { color: #475569; margin: 12px 0; line-height: 1.6; font-size: 15px; }
                        .cta-button { display: inline-block; background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); color: #ffffff !important; padding: 16px 40px; text-decoration: none; border-radius: 0; border: 2px solid #ffffff; box-shadow: 0 0 0 2px #0f172a, 4px 4px 0 rgba(15, 23, 42, 0.45); font-weight: 700; margin: 20px 0; text-transform: uppercase; letter-spacing: 0.08em; font-size: 14px; }
                        .divider { height: 1px; background-image: linear-gradient(90deg, rgba(15, 23, 42, 0.12) 0, transparent 50%, rgba(15, 23, 42, 0.12) 100%); background-size: 24px 1px; margin: 30px 0; }
                        .footer { background-color: #f8fafc; padding: 30px; text-align: center; color: #94a3b8; font-size: 13px; border-top: 1px solid rgba(15, 23, 42, 0.1); }
                        .footer-logo { font-family: 'Pixelify Sans', monospace; font-size: 14px; letter-spacing: 0.32em; text-transform: uppercase; color: #0f172a; margin-bottom: 8px; }
                        .footer-logo span { color: #ec4899; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>API<span style="color: #fbbf24;">UI</span></h1>
                            <div class="tagline">AN AURABLOX COMPANY</div>
                        </div>
                        <div class="content">
                            <div class="eyebrow">WELCOME</div>
                            <h2>Thank You for Subscribing! 🚀</h2>
                            <p>Welcome to the APIUI community! We're excited to have you on board.</p>
                            <p><strong>You'll now receive updates about:</strong></p>
                            <div class="features">
                                <ul style="margin: 0; padding-left: 20px;">
                                    <li><strong>🆕 New Features</strong> – Platform improvements and enhancements</li>
                                    <li><strong>🎁 Beta Access</strong> – Early access to upcoming tools</li>
                                    <li><strong>📚 Best Practices</strong> – API development tips and tutorials</li>
                                    <li><strong>🎯 Exclusive Resources</strong> – Guides and documentation</li>
                                </ul>
                            </div>
                            <div class="divider"></div>
                            <p style="text-align: center; margin-bottom: 20px;"><strong>Ready to transform your data into powerful APIs?</strong></p>
                            <div style="text-align: center;">
                                <a href="https://ai-apiui.web.app/app.html" class="cta-button" style="color: #ffffff;">Start Building APIs</a>
                            </div>
                            <p style="margin-top: 30px; color: #94a3b8; font-size: 13px; text-align: center;">Questions? We're here to help! Just reply to this email.</p>
                        </div>
                        <div class="footer">
                            <div class="footer-logo">api<span>UI</span></div>
                            <p>© ${new Date().getFullYear()} APIUI by AURABLOX. All rights reserved.</p>
                            <p style="margin-top: 12px; font-size: 12px;">You can unsubscribe at any time by replying to this email.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        // Email to admin
        const adminMailOptions = {
            from: `"APIUI Signup" <${GMAIL_USER}>`,
            to: GMAIL_USER,
            subject: `New Newsletter Signup: ${email}`,
            text: `New subscriber: ${email}\nTimestamp: ${new Date().toISOString()}`
        };

        // Send emails
        await transporter.sendMail(userMailOptions);
        console.log(`✅ Thank you email sent to: ${email}`);

        if (process.env.SEND_ADMIN_NOTIFICATIONS !== 'false') {
            await transporter.sendMail(adminMailOptions);
            console.log(`📬 Admin notification sent`);
        }

        res.json({
            success: true,
            message: 'Successfully subscribed! Check your email for confirmation.'
        });

    } catch (error) {
        console.error('❌ Email sending error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to send confirmation email. Please try again.'
        });
    }
});

// Beta signup endpoint
app.post('/beta-signup', async (req, res) => {
    const { email } = req.body;

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return res.status(400).json({
            success: false,
            error: 'Invalid email address'
        });
    }

    if (!transporter) {
        return res.status(503).json({
            success: false,
            error: 'Email service not configured'
        });
    }

    console.log(`🎁 New beta signup: ${email}`);

    try {
        // Email to the user (Beta signup confirmation)
        const userMailOptions = {
            from: `"APIUI" <${GMAIL_USER}>`,
            to: email,
            subject: '🎁 You\'re on the APIUI Beta List!',
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Pixelify+Sans:wght@600;700&display=swap" rel="stylesheet">
                    <style>
                        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background-color: #f8fafc; }
                        .container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 2px solid #0f172a; box-shadow: 4px 4px 0 rgba(15, 23, 42, 0.25); }
                        .header { background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); padding: 40px 20px; text-align: center; border-bottom: 2px solid #0f172a; position: relative; }
                        .header::after { content: ''; position: absolute; top: 0; right: 0; width: 12px; height: 12px; background-image: linear-gradient(90deg, #ec4899 50%, transparent 50%), linear-gradient(180deg, #ec4899 50%, transparent 50%); background-size: 4px 4px; }
                        .header h1 { color: #ffffff; margin: 0; font-size: 32px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; font-family: 'Pixelify Sans', monospace; }
                        .header .tagline { color: rgba(255, 255, 255, 0.9); font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; margin-top: 8px; font-weight: 600; }
                        .beta-badge { display: inline-block; background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); color: #0f172a; padding: 8px 16px; font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; border: 2px solid #0f172a; box-shadow: 2px 2px 0 rgba(15, 23, 42, 0.3); margin: 16px 0; }
                        .content { padding: 40px 30px; background-image: linear-gradient(rgba(236, 72, 153, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(236, 72, 153, 0.02) 1px, transparent 1px); background-size: 24px 24px; }
                        .eyebrow { color: #ec4899; font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; font-weight: 700; margin-bottom: 12px; font-family: 'Pixelify Sans', monospace; }
                        .content h2 { color: #0f172a; font-size: 28px; margin-bottom: 20px; font-weight: 700; line-height: 1.3; }
                        .content p { color: #64748b; line-height: 1.8; margin-bottom: 15px; font-size: 16px; }
                        .features { background-color: #ffffff; border: 2px solid #0f172a; box-shadow: 2px 2px 0 rgba(236, 72, 153, 0.25); padding: 24px; margin: 25px 0; position: relative; }
                        .features::after { content: ''; position: absolute; top: 0; right: 0; width: 10px; height: 10px; background-image: linear-gradient(90deg, #ec4899 50%, transparent 50%), linear-gradient(180deg, #ec4899 50%, transparent 50%); background-size: 3px 3px; }
                        .features li { color: #475569; margin: 12px 0; line-height: 1.6; font-size: 15px; }
                        .cta-button { display: inline-block; background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); color: #ffffff !important; padding: 16px 40px; text-decoration: none; border-radius: 0; border: 2px solid #ffffff; box-shadow: 0 0 0 2px #0f172a, 4px 4px 0 rgba(15, 23, 42, 0.45); font-weight: 700; margin: 20px 0; text-transform: uppercase; letter-spacing: 0.08em; font-size: 14px; }
                        .divider { height: 1px; background-image: linear-gradient(90deg, rgba(15, 23, 42, 0.12) 0, transparent 50%, rgba(15, 23, 42, 0.12) 100%); background-size: 24px 1px; margin: 30px 0; }
                        .footer { background-color: #f8fafc; padding: 30px; text-align: center; color: #94a3b8; font-size: 13px; border-top: 1px solid rgba(15, 23, 42, 0.1); }
                        .footer-logo { font-family: 'Pixelify Sans', monospace; font-size: 14px; letter-spacing: 0.32em; text-transform: uppercase; color: #0f172a; margin-bottom: 8px; }
                        .footer-logo span { color: #ec4899; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>API<span style="color: #fbbf24;">UI</span></h1>
                            <div class="tagline">AN AURABLOX COMPANY</div>
                        </div>
                        <div class="content">
                            <div class="eyebrow">WELCOME</div>
                            <h2>Thank You for Subscribing! 🚀</h2>
                            <p>Welcome to the APIUI community! We're excited to have you on board.</p>
                            <p><strong>You'll now receive updates about:</strong></p>
                            <div class="features">
                                <ul style="margin: 0; padding-left: 20px;">
                                    <li><strong>🆕 New Features</strong> – Platform improvements and enhancements</li>
                                    <li><strong>🎁 Beta Access</strong> – Early access to upcoming tools</li>
                                    <li><strong>📚 Best Practices</strong> – API development tips and tutorials</li>
                                    <li><strong>🎯 Exclusive Resources</strong> – Guides and documentation</li>
                                </ul>
                            </div>
                            <div class="divider"></div>
                            <p style="text-align: center; margin-bottom: 20px;"><strong>Ready to transform your data into powerful APIs?</strong></p>
                            <div style="text-align: center;">
                                <a href="https://ai-apiui.web.app/app.html" class="cta-button" style="color: #ffffff;">Start Building APIs</a>
                            </div>
                            <p style="margin-top: 30px; color: #94a3b8; font-size: 13px; text-align: center;">Questions? We're here to help! Just reply to this email.</p>
                        </div>
                        <div class="footer">
                            <div class="footer-logo">api<span>UI</span></div>
                            <p>© ${new Date().getFullYear()} APIUI by AURABLOX. All rights reserved.</p>
                            <p style="margin-top: 12px; font-size: 12px;">You can unsubscribe at any time by replying to this email.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        // Email to admin
        const adminMailOptions = {
            from: `"APIUI Signup" <${GMAIL_USER}>`,
            to: GMAIL_USER,
            subject: `New Newsletter Signup: ${email}`,
            text: `New subscriber: ${email}\nTimestamp: ${new Date().toISOString()}`
        };

        // Send emails
        await transporter.sendMail(userMailOptions);
        console.log(`✅ Thank you email sent to: ${email}`);

        await transporter.sendMail(adminMailOptions);
        console.log(`📬 Admin notification sent`);

        res.json({
            success: true,
            message: 'Successfully subscribed! Check your email for confirmation.'
        });

    } catch (error) {
        console.error('❌ Email sending error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to send confirmation email. Please try again.'
        });
    }
});

// Beta signup endpoint
app.post('/beta-signup', async (req, res) => {
    const { email } = req.body;

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return res.status(400).json({
            success: false,
            error: 'Invalid email address'
        });
    }

    if (!transporter) {
        return res.status(503).json({
            success: false,
            error: 'Email service not configured'
        });
    }

    console.log(`🎁 New beta signup: ${email}`);

    try {
        // Email to the user (Beta signup confirmation)
        const userMailOptions = {
            from: `"APIUI" <${GMAIL_USER}>`,
            to: email,
            subject: '🎁 You\'re on the APIUI Beta List!',
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Pixelify+Sans:wght@600;700&display=swap" rel="stylesheet">
                    <style>
                        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 0; background-color: #f8fafc; }
                        .container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 2px solid #0f172a; box-shadow: 4px 4px 0 rgba(15, 23, 42, 0.25); }
                        .header { background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); padding: 40px 20px; text-align: center; border-bottom: 2px solid #0f172a; position: relative; }
                        .header::after { content: ''; position: absolute; top: 0; right: 0; width: 12px; height: 12px; background-image: linear-gradient(90deg, #ec4899 50%, transparent 50%), linear-gradient(180deg, #ec4899 50%, transparent 50%); background-size: 4px 4px; }
                        .header h1 { color: #ffffff; margin: 0; font-size: 32px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; font-family: 'Pixelify Sans', monospace; }
                        .header .tagline { color: rgba(255, 255, 255, 0.9); font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; margin-top: 8px; font-weight: 600; }
                        .beta-badge { display: inline-block; background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); color: #0f172a; padding: 8px 16px; font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; border: 2px solid #0f172a; box-shadow: 2px 2px 0 rgba(15, 23, 42, 0.3); margin: 16px 0; }
                        .content { padding: 40px 30px; background-image: linear-gradient(rgba(236, 72, 153, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(236, 72, 153, 0.02) 1px, transparent 1px); background-size: 24px 24px; }
                        .eyebrow { color: #ec4899; font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; font-weight: 700; margin-bottom: 12px; font-family: 'Pixelify Sans', monospace; }
                        .content h2 { color: #0f172a; font-size: 28px; margin-bottom: 20px; font-weight: 700; line-height: 1.3; }
                        .content p { color: #64748b; line-height: 1.8; margin-bottom: 15px; font-size: 16px; }
                        .features { background-color: #ffffff; border: 2px solid #0f172a; box-shadow: 2px 2px 0 rgba(236, 72, 153, 0.25); padding: 24px; margin: 25px 0; position: relative; }
                        .features::after { content: ''; position: absolute; top: 0; right: 0; width: 10px; height: 10px; background-image: linear-gradient(90deg, #ec4899 50%, transparent 50%), linear-gradient(180deg, #ec4899 50%, transparent 50%); background-size: 3px 3px; }
                        .features li { color: #475569; margin: 12px 0; line-height: 1.6; font-size: 15px; }
                        .cta-button { display: inline-block; background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); color: #ffffff !important; padding: 16px 40px; text-decoration: none; border-radius: 0; border: 2px solid #ffffff; box-shadow: 0 0 0 2px #0f172a, 4px 4px 0 rgba(15, 23, 42, 0.45); font-weight: 700; margin: 20px 0; text-transform: uppercase; letter-spacing: 0.08em; font-size: 14px; }
                        .divider { height: 1px; background-image: linear-gradient(90deg, rgba(15, 23, 42, 0.12) 0, transparent 50%, rgba(15, 23, 42, 0.12) 100%); background-size: 24px 1px; margin: 30px 0; }
                        .footer { background-color: #f8fafc; padding: 30px; text-align: center; color: #94a3b8; font-size: 13px; border-top: 1px solid rgba(15, 23, 42, 0.1); }
                        .footer-logo { font-family: 'Pixelify Sans', monospace; font-size: 14px; letter-spacing: 0.32em; text-transform: uppercase; color: #0f172a; margin-bottom: 8px; }
                        .footer-logo span { color: #ec4899; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>API<span style="color: #fbbf24;">UI</span></h1>
                            <div class="tagline">AN AURABLOX COMPANY</div>
                        </div>
                        <div class="content">
                            <div style="text-align: center; margin-bottom: 24px;">
                                <div class="beta-badge">🎁 BETA ACCESS</div>
                            </div>
                            <div class="eyebrow">BETA PROGRAM</div>
                            <h2>You're On The List! 🚀</h2>
                            <p>Thank you for signing up for <strong>APIUI Beta Access</strong>! We're thrilled to have you as an early adopter.</p>
                            <p><strong>What happens next?</strong></p>
                            <div class="features">
                                <ul style="margin: 0; padding-left: 20px;">
                                    <li><strong>📅 December 2025</strong> – Beta launch notification</li>
                                    <li><strong>🎁 Early Access</strong> – Get access before public launch</li>
                                    <li><strong>💎 Exclusive Features</strong> – Test new features first</li>
                                    <li><strong>💬 Direct Feedback</strong> – Shape the product with your input</li>
                                </ul>
                            </div>
                            <div class="divider"></div>
                            <p style="text-align: center; margin-bottom: 20px;"><strong>Want to get started now? Try the current version:</strong></p>
                            <div style="text-align: center;">
                                <a href="https://ai-apiui.web.app/app.html" class="cta-button" style="color: #ffffff;">Start Building APIs</a>
                            </div>
                            <p style="margin-top: 30px; color: #94a3b8; font-size: 13px; text-align: center;">Questions about the beta? Just reply to this email!</p>
                        </div>
                        <div class="footer">
                            <div class="footer-logo">api<span>UI</span></div>
                            <p>© ${new Date().getFullYear()} APIUI by AURABLOX. All rights reserved.</p>
                            <p style="margin-top: 12px; font-size: 12px;">You're receiving this because you signed up for beta access.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        // Email to admin (Beta signup notification)
        const adminMailOptions = {
            from: `"APIUI Beta Signup" <${GMAIL_USER}>`,
            to: GMAIL_USER,
            subject: `🎁 New Beta Signup: ${email}`,
            text: `New beta subscriber: ${email}\nTimestamp: ${new Date().toISOString()}\nSource: app.html beta form`
        };

        // Send emails
        await transporter.sendMail(userMailOptions);
        console.log(`✅ Beta confirmation email sent to: ${email}`);

        await transporter.sendMail(adminMailOptions);
        console.log(`📬 Beta signup notification sent to admin`);

        res.json({
            success: true,
            message: 'Successfully signed up for beta! Check your email for confirmation.'
        });

    } catch (error) {
        console.error('❌ Beta signup email error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to send beta confirmation email. Please try again.'
        });
    }
});

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

// Newsletter signup endpoint
app.post('/api/signup', async (req, res) => {
    try {
        const { email } = req.body;
        
        if (!email) {
            return res.status(400).json({ success: false, error: 'Email is required' });
        }
        
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return res.status(400).json({ success: false, error: 'Invalid email format' });
        }
        
        if (!transporter) {
            console.error('Email transporter not configured');
            return res.status(500).json({ success: false, error: 'Email service not configured' });
        }
        
        // Welcome email to subscriber
        const userMailOptions = {
            from: GMAIL_USER,
            to: email,
            subject: 'Welcome to APIUI Newsletter!',
            html: `
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            max-width: 600px;
            margin: 40px auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .header {
            text-align: center;
            padding-bottom: 30px;
            border-bottom: 2px solid #667eea;
        }
        .logo {
            font-size: 32px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        .content {
            padding: 30px 0;
            color: #2d3748;
            line-height: 1.8;
        }
        .highlight {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        .cta-button {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white !important;
            padding: 15px 40px;
            text-decoration: none;
            border-radius: 50px;
            font-weight: 600;
            margin: 20px 0;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
            transition: transform 0.3s ease;
        }
        .cta-button:hover {
            transform: translateY(-2px);
        }
        .footer {
            text-align: center;
            padding-top: 30px;
            border-top: 2px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }
        .pixel-dots {
            text-align: center;
            letter-spacing: 8px;
            color: #667eea;
            font-size: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">APIUI</div>
            <div class="pixel-dots">• • •</div>
        </div>
        
        <div class="content">
            <h2 style="color: #2d3748;">Welcome aboard! 🚀</h2>
            
            <p>Thank you for subscribing to the APIUI newsletter! You've just joined a community of developers who are transforming how APIs are built.</p>
            
            <div class="highlight">
                <strong>What to expect:</strong>
                <ul style="margin: 10px 0;">
                    <li>Weekly insights on API development</li>
                    <li>Exclusive early access to new features</li>
                    <li>Tips & tricks from our engineering team</li>
                    <li>Community success stories</li>
                </ul>
            </div>
            
            <p>Ready to get started? Try APIUI and see how it can streamline your API development workflow.</p>
            
            <div style="text-align: center;">
                <a href="https://ai-apiui.web.app/app.html" class="cta-button">Get Started Now</a>
            </div>
            
            <p style="margin-top: 30px;">Questions? Just reply to this email - we're here to help!</p>
        </div>
        
        <div class="footer">
            <p>You're receiving this because you signed up at apiui.web.app</p>
            <p style="margin-top: 10px;">APIUI - Simplify your API development</p>
        </div>
    </div>
</body>
</html>
            `
        };
        
        // Admin notification
        const adminMailOptions = {
            from: GMAIL_USER,
            to: GMAIL_USER,
            subject: 'New Newsletter Signup',
            text: `New newsletter signup: ${email}`
        };
        
        await transporter.sendMail(userMailOptions);
        await transporter.sendMail(adminMailOptions);
        
        console.log(`Newsletter signup email sent to: ${email}`);
        res.json({ success: true, message: 'Subscription successful' });
        
    } catch (error) {
        console.error('Newsletter signup error:', error);
        res.status(500).json({ success: false, error: 'Failed to process subscription' });
    }
});

// Beta signup endpoint
app.post('/api/beta-signup', async (req, res) => {
    try {
        const { email } = req.body;
        
        if (!email) {
            return res.status(400).json({ success: false, error: 'Email is required' });
        }
        
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return res.status(400).json({ success: false, error: 'Invalid email format' });
        }
        
        if (!transporter) {
            console.error('Email transporter not configured');
            return res.status(500).json({ success: false, error: 'Email service not configured' });
        }
        
        // Beta confirmation email to user
        const userMailOptions = {
            from: GMAIL_USER,
            to: email,
            subject: "You're on the APIUI Beta List!",
            html: `
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            max-width: 600px;
            margin: 40px auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .header {
            text-align: center;
            padding-bottom: 30px;
            border-bottom: 2px solid #667eea;
        }
        .logo {
            font-size: 32px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        .badge {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 20px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            margin-top: 10px;
        }
        .content {
            padding: 30px 0;
            color: #2d3748;
            line-height: 1.8;
        }
        .feature-box {
            background: #f7fafc;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .cta-button {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white !important;
            padding: 15px 40px;
            text-decoration: none;
            border-radius: 50px;
            font-weight: 600;
            margin: 20px 0;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .footer {
            text-align: center;
            padding-top: 30px;
            border-top: 2px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">APIUI</div>
            <div class="badge">BETA ACCESS</div>
        </div>
        
        <div class="content">
            <h2 style="color: #2d3748;">🎉 You're on the list!</h2>
            
            <p>Congratulations! You've successfully joined the APIUI Beta program. You're now part of an exclusive group that will get early access to our most powerful features.</p>
            
            <div class="feature-box">
                <strong>🚀 What's included in Beta:</strong>
                <ul style="margin: 10px 0;">
                    <li>Early access to new features</li>
                    <li>Priority support from our team</li>
                    <li>Direct feedback channel to influence product development</li>
                    <li>Exclusive beta community access</li>
                </ul>
            </div>
            
            <p><strong>What's next?</strong></p>
            <p>We'll notify you as soon as your beta access is ready. In the meantime, feel free to explore APIUI and let us know what features you're most excited about!</p>
            
            <div style="text-align: center;">
                <a href="https://ai-apiui.web.app/app.html" class="cta-button">Explore APIUI</a>
            </div>
            
            <p style="margin-top: 30px;">Have questions? Reply to this email anytime!</p>
        </div>
        
        <div class="footer">
            <p>You're receiving this because you signed up for APIUI Beta access</p>
            <p style="margin-top: 10px;">APIUI - Simplify your API development</p>
        </div>
    </div>
</body>
</html>
            `
        };
        
        // Admin notification
        const adminMailOptions = {
            from: GMAIL_USER,
            to: GMAIL_USER,
            subject: 'New Beta Signup',
            text: `New beta signup: ${email}`
        };
        
        await transporter.sendMail(userMailOptions);
        await transporter.sendMail(adminMailOptions);
        
        console.log(`Beta signup email sent to: ${email}`);
        res.json({ success: true, message: 'Beta signup successful' });
        
    } catch (error) {
        console.error('Beta signup error:', error);
        res.status(500).json({ success: false, error: 'Failed to process beta signup' });
    }
});

// Export the Express app as a Firebase Function
exports.chat = functions.https.onRequest(app);
