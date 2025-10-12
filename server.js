const express = require('express');
const path = require('path');
const nodemailer = require('nodemailer');
require('dotenv').config();

const app = express();
const port = 8080;

// Middleware to parse JSON body
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static files from the frontend directory
app.use(express.static(path.join(__dirname, 'frontend')));

// Configure Nodemailer transporter with Gmail
const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.GMAIL_USER, // Your Gmail address
        pass: process.env.GMAIL_APP_PASSWORD // Gmail App Password (not regular password)
    }
});

// Verify transporter configuration on startup
transporter.verify((error, success) => {
    if (error) {
        console.log('❌ Email transporter error:', error);
        console.log('⚠️  Make sure GMAIL_USER and GMAIL_APP_PASSWORD are set in .env');
    } else {
        console.log('✅ Email transporter ready to send messages');
    }
});

// Newsletter signup webhook endpoint
app.post('/api/signup', async (req, res) => {
    const { email } = req.body;

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return res.status(400).json({
            success: false,
            error: 'Invalid email address'
        });
    }

    console.log(`📧 New newsletter signup: ${email}`);

    try {
        // Email to the user (Thank you message)
        const userMailOptions = {
            from: `"APIUI" <${process.env.GMAIL_USER}>`,
            to: email,
            subject: '🎉 Welcome to APIUI Newsletter!',
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Pixelify+Sans:wght@600;700&display=swap" rel="stylesheet">
                    <style>
                        body { 
                            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                            margin: 0; 
                            padding: 0; 
                            background-color: #f8fafc; 
                        }
                        .container { 
                            max-width: 600px; 
                            margin: 0 auto; 
                            background-color: #ffffff;
                            border: 2px solid #0f172a;
                            box-shadow: 4px 4px 0 rgba(15, 23, 42, 0.25);
                        }
                        .header { 
                            background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); 
                            padding: 40px 20px; 
                            text-align: center;
                            border-bottom: 2px solid #0f172a;
                            position: relative;
                        }
                        .header::after {
                            content: '';
                            position: absolute;
                            top: 0;
                            right: 0;
                            width: 12px;
                            height: 12px;
                            background-image: 
                                linear-gradient(90deg, #ec4899 50%, transparent 50%), 
                                linear-gradient(180deg, #ec4899 50%, transparent 50%);
                            background-size: 4px 4px;
                        }
                        .header h1 { 
                            color: #ffffff; 
                            margin: 0; 
                            font-size: 32px; 
                            font-weight: 700; 
                            letter-spacing: 0.14em; 
                            text-transform: uppercase;
                            font-family: 'Pixelify Sans', monospace;
                        }
                        .header .tagline {
                            color: rgba(255, 255, 255, 0.9);
                            font-size: 11px;
                            letter-spacing: 0.32em;
                            text-transform: uppercase;
                            margin-top: 8px;
                            font-weight: 600;
                        }
                        .pixel-dot {
                            display: inline-block;
                            width: 12px;
                            height: 12px;
                            background-image: 
                                repeating-linear-gradient(90deg, #ec4899 0, #ec4899 2px, transparent 2px, transparent 4px), 
                                repeating-linear-gradient(#ec4899 0, #ec4899 2px, transparent 2px, transparent 4px);
                            margin-right: 8px;
                            vertical-align: middle;
                        }
                        .content { 
                            padding: 40px 30px;
                            background-image: 
                                linear-gradient(rgba(236, 72, 153, 0.02) 1px, transparent 1px), 
                                linear-gradient(90deg, rgba(236, 72, 153, 0.02) 1px, transparent 1px);
                            background-size: 24px 24px;
                        }
                        .eyebrow {
                            color: #ec4899;
                            font-size: 11px;
                            letter-spacing: 0.32em;
                            text-transform: uppercase;
                            font-weight: 700;
                            margin-bottom: 12px;
                            font-family: 'Pixelify Sans', monospace;
                        }
                        .content h2 { 
                            color: #0f172a; 
                            font-size: 28px; 
                            margin-bottom: 20px;
                            font-weight: 700;
                            line-height: 1.3;
                        }
                        .content p { 
                            color: #64748b; 
                            line-height: 1.8; 
                            margin-bottom: 15px;
                            font-size: 16px;
                        }
                        .features { 
                            background-color: #ffffff; 
                            border: 2px solid #0f172a;
                            box-shadow: 2px 2px 0 rgba(236, 72, 153, 0.25);
                            padding: 24px;
                            margin: 25px 0;
                            position: relative;
                        }
                        .features::after {
                            content: '';
                            position: absolute;
                            top: 0;
                            right: 0;
                            width: 10px;
                            height: 10px;
                            background-image: 
                                linear-gradient(90deg, #ec4899 50%, transparent 50%), 
                                linear-gradient(180deg, #ec4899 50%, transparent 50%);
                            background-size: 3px 3px;
                        }
                        .features li { 
                            color: #475569; 
                            margin: 12px 0;
                            line-height: 1.6;
                            font-size: 15px;
                        }
                        .cta-button { 
                            display: inline-block; 
                            background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%);
                            color: #ffffff !important; 
                            padding: 16px 40px; 
                            text-decoration: none; 
                            border-radius: 0;
                            border: 2px solid #ffffff;
                            box-shadow: 0 0 0 2px #0f172a, 4px 4px 0 rgba(15, 23, 42, 0.45);
                            font-weight: 700; 
                            margin: 20px 0;
                            text-transform: uppercase;
                            letter-spacing: 0.08em;
                            font-size: 14px;
                            transition: all 0.2s ease;
                        }
                        .divider {
                            height: 1px;
                            background-image: linear-gradient(90deg, rgba(15, 23, 42, 0.12) 0, transparent 50%, rgba(15, 23, 42, 0.12) 100%);
                            background-size: 24px 1px;
                            margin: 30px 0;
                        }
                        .footer { 
                            background-color: #f8fafc; 
                            padding: 30px; 
                            text-align: center; 
                            color: #94a3b8; 
                            font-size: 13px;
                            border-top: 1px solid rgba(15, 23, 42, 0.1);
                        }
                        .footer-logo {
                            font-family: 'Pixelify Sans', monospace;
                            font-size: 14px;
                            letter-spacing: 0.32em;
                            text-transform: uppercase;
                            color: #0f172a;
                            margin-bottom: 8px;
                        }
                        .footer-logo span {
                            color: #ec4899;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>API<span style="color: #fbbf24;">UI</span></h1>
                            <div class="tagline">AN AURABLOX COMPANY</div>
                        </div>
                        <div class="content">
                            <div class="eyebrow">
                                <span class="pixel-dot"></span>WELCOME
                            </div>
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
                            <p style="text-align: center; margin-bottom: 20px;">
                                <strong>Ready to transform your data into powerful APIs?</strong>
                            </p>
                            <div style="text-align: center;">
                                <a href="https://ai-apiui.web.app/app.html" class="cta-button" style="color: #ffffff;">Start Building APIs</a>
                            </div>
                            <p style="margin-top: 30px; color: #94a3b8; font-size: 13px; text-align: center;">
                                Questions? We're here to help! Just reply to this email.
                            </p>
                        </div>
                        <div class="footer">
                            <div class="footer-logo">api<span>UI</span></div>
                            <p>© ${new Date().getFullYear()} APIUI by AURABLOX. All rights reserved.</p>
                            <p style="margin-top: 12px; font-size: 12px;">
                                You can unsubscribe at any time by replying to this email.
                            </p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        // Optional: Email to yourself (notification)
        const adminMailOptions = {
            from: `"APIUI Signup" <${process.env.GMAIL_USER}>`,
            to: process.env.GMAIL_USER,
            subject: `New Newsletter Signup: ${email}`,
            text: `New subscriber: ${email}\nTimestamp: ${new Date().toISOString()}`
        };

        // Send both emails
        await transporter.sendMail(userMailOptions);
        console.log(`✅ Thank you email sent to: ${email}`);

        // Optionally send admin notification (comment out if you don't want this)
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

// Beta signup webhook endpoint
app.post('/api/beta-signup', async (req, res) => {
    const { email } = req.body;

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return res.status(400).json({
            success: false,
            error: 'Invalid email address'
        });
    }

    console.log(`🎁 New beta signup: ${email}`);

    try {
        // Email to the user (Beta signup confirmation)
        const userMailOptions = {
            from: `"APIUI" <${process.env.GMAIL_USER}>`,
            to: email,
            subject: '🎁 You\'re on the APIUI Beta List!',
            html: `
                <!DOCTYPE html>
                <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Pixelify+Sans:wght@600;700&display=swap" rel="stylesheet">
                    <style>
                        body { 
                            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                            margin: 0; 
                            padding: 0; 
                            background-color: #f8fafc; 
                        }
                        .container { 
                            max-width: 600px; 
                            margin: 0 auto; 
                            background-color: #ffffff;
                            border: 2px solid #0f172a;
                            box-shadow: 4px 4px 0 rgba(15, 23, 42, 0.25);
                        }
                        .header { 
                            background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%); 
                            padding: 40px 20px; 
                            text-align: center;
                            border-bottom: 2px solid #0f172a;
                            position: relative;
                        }
                        .header::after {
                            content: '';
                            position: absolute;
                            top: 0;
                            right: 0;
                            width: 12px;
                            height: 12px;
                            background-image: 
                                linear-gradient(90deg, #ec4899 50%, transparent 50%), 
                                linear-gradient(180deg, #ec4899 50%, transparent 50%);
                            background-size: 4px 4px;
                        }
                        .header h1 { 
                            color: #ffffff; 
                            margin: 0; 
                            font-size: 32px; 
                            font-weight: 700; 
                            letter-spacing: 0.14em; 
                            text-transform: uppercase;
                            font-family: 'Pixelify Sans', monospace;
                        }
                        .header .tagline {
                            color: rgba(255, 255, 255, 0.9);
                            font-size: 11px;
                            letter-spacing: 0.32em;
                            text-transform: uppercase;
                            margin-top: 8px;
                            font-weight: 600;
                        }
                        .beta-badge {
                            display: inline-block;
                            background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
                            color: #0f172a;
                            padding: 8px 16px;
                            font-size: 12px;
                            font-weight: 700;
                            letter-spacing: 0.1em;
                            text-transform: uppercase;
                            border: 2px solid #0f172a;
                            box-shadow: 2px 2px 0 rgba(15, 23, 42, 0.3);
                            margin: 16px 0;
                        }
                        .pixel-dot {
                            display: inline-block;
                            width: 12px;
                            height: 12px;
                            background-image: 
                                repeating-linear-gradient(90deg, #ec4899 0, #ec4899 2px, transparent 2px, transparent 4px), 
                                repeating-linear-gradient(#ec4899 0, #ec4899 2px, transparent 2px, transparent 4px);
                            margin-right: 8px;
                            vertical-align: middle;
                        }
                        .content { 
                            padding: 40px 30px;
                            background-image: 
                                linear-gradient(rgba(236, 72, 153, 0.02) 1px, transparent 1px), 
                                linear-gradient(90deg, rgba(236, 72, 153, 0.02) 1px, transparent 1px);
                            background-size: 24px 24px;
                        }
                        .eyebrow {
                            color: #ec4899;
                            font-size: 11px;
                            letter-spacing: 0.32em;
                            text-transform: uppercase;
                            font-weight: 700;
                            margin-bottom: 12px;
                            font-family: 'Pixelify Sans', monospace;
                        }
                        .content h2 { 
                            color: #0f172a; 
                            font-size: 28px; 
                            margin-bottom: 20px;
                            font-weight: 700;
                            line-height: 1.3;
                        }
                        .content p { 
                            color: #64748b; 
                            line-height: 1.8; 
                            margin-bottom: 15px;
                            font-size: 16px;
                        }
                        .features { 
                            background-color: #ffffff; 
                            border: 2px solid #0f172a;
                            box-shadow: 2px 2px 0 rgba(236, 72, 153, 0.25);
                            padding: 24px;
                            margin: 25px 0;
                            position: relative;
                        }
                        .features::after {
                            content: '';
                            position: absolute;
                            top: 0;
                            right: 0;
                            width: 10px;
                            height: 10px;
                            background-image: 
                                linear-gradient(90deg, #ec4899 50%, transparent 50%), 
                                linear-gradient(180deg, #ec4899 50%, transparent 50%);
                            background-size: 3px 3px;
                        }
                        .features li { 
                            color: #475569; 
                            margin: 12px 0;
                            line-height: 1.6;
                            font-size: 15px;
                        }
                        .cta-button { 
                            display: inline-block; 
                            background: linear-gradient(135deg, #0f172a 0%, #ec4899 48%, #7c3aed 100%);
                            color: #ffffff !important; 
                            padding: 16px 40px; 
                            text-decoration: none; 
                            border-radius: 0;
                            border: 2px solid #ffffff;
                            box-shadow: 0 0 0 2px #0f172a, 4px 4px 0 rgba(15, 23, 42, 0.45);
                            font-weight: 700; 
                            margin: 20px 0;
                            text-transform: uppercase;
                            letter-spacing: 0.08em;
                            font-size: 14px;
                        }
                        .divider {
                            height: 1px;
                            background-image: linear-gradient(90deg, rgba(15, 23, 42, 0.12) 0, transparent 50%, rgba(15, 23, 42, 0.12) 100%);
                            background-size: 24px 1px;
                            margin: 30px 0;
                        }
                        .footer { 
                            background-color: #f8fafc; 
                            padding: 30px; 
                            text-align: center; 
                            color: #94a3b8; 
                            font-size: 13px;
                            border-top: 1px solid rgba(15, 23, 42, 0.1);
                        }
                        .footer-logo {
                            font-family: 'Pixelify Sans', monospace;
                            font-size: 14px;
                            letter-spacing: 0.32em;
                            text-transform: uppercase;
                            color: #0f172a;
                            margin-bottom: 8px;
                        }
                        .footer-logo span {
                            color: #ec4899;
                        }
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
                                <div class="beta-badge">
                                    🎁 BETA ACCESS
                                </div>
                            </div>
                            <div class="eyebrow">
                                <span class="pixel-dot"></span>BETA PROGRAM
                            </div>
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
                            <p style="text-align: center; margin-bottom: 20px;">
                                <strong>Want to get started now? Try the current version:</strong>
                            </p>
                            <div style="text-align: center;">
                                <a href="https://ai-apiui.web.app/app.html" class="cta-button" style="color: #ffffff;">Start Building APIs</a>
                            </div>
                            <p style="margin-top: 30px; color: #94a3b8; font-size: 13px; text-align: center;">
                                Questions about the beta? Just reply to this email!
                            </p>
                        </div>
                        <div class="footer">
                            <div class="footer-logo">api<span>UI</span></div>
                            <p>© ${new Date().getFullYear()} APIUI by AURABLOX. All rights reserved.</p>
                            <p style="margin-top: 12px; font-size: 12px;">
                                You're receiving this because you signed up for beta access.
                            </p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        // Email to admin (Beta signup notification)
        const adminMailOptions = {
            from: `"APIUI Beta Signup" <${process.env.GMAIL_USER}>`,
            to: process.env.GMAIL_USER,
            subject: `🎁 New Beta Signup: ${email}`,
            text: `New beta subscriber: ${email}\nTimestamp: ${new Date().toISOString()}\nSource: app.html beta form`
        };

        // Send both emails
        await transporter.sendMail(userMailOptions);
        console.log(`✅ Beta confirmation email sent to: ${email}`);

        // Send admin notification
        if (process.env.SEND_ADMIN_NOTIFICATIONS !== 'false') {
            await transporter.sendMail(adminMailOptions);
            console.log(`📬 Beta signup notification sent to admin`);
        }

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

// Serve index.html for the root route
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Start the server
app.listen(port, () => {
    console.log(`🚀 Frontend server running at http://localhost:${port}`);
    console.log(`📁 Serving files from: ${path.join(__dirname, 'frontend')}`);
    console.log(`📧 Newsletter endpoint: http://localhost:${port}/api/signup`);
    console.log(`🎁 Beta signup endpoint: http://localhost:${port}/api/beta-signup`);
});
