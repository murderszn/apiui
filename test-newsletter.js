#!/usr/bin/env node

/**
 * Newsletter Signup Test Script
 * 
 * Tests the /api/signup endpoint to verify email sending works
 * Usage: node test-newsletter.js your-email@example.com
 */

const http = require('http');

// Get email from command line argument
const testEmail = process.argv[2];

if (!testEmail) {
    console.error('❌ Error: Please provide an email address');
    console.log('\nUsage: node test-newsletter.js your-email@example.com');
    process.exit(1);
}

// Validate email format
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
if (!emailRegex.test(testEmail)) {
    console.error('❌ Error: Invalid email format');
    console.log('\nPlease provide a valid email address like: user@example.com');
    process.exit(1);
}

console.log('\n🧪 Testing Newsletter Signup');
console.log('═══════════════════════════════════════');
console.log(`📧 Email: ${testEmail}`);
console.log(`🌐 Endpoint: http://localhost:8080/api/signup`);
console.log('═══════════════════════════════════════\n');

const postData = JSON.stringify({
    email: testEmail
});

const options = {
    hostname: 'localhost',
    port: 8080,
    path: '/api/signup',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData)
    }
};

console.log('⏳ Sending request...\n');

const req = http.request(options, (res) => {
    let data = '';

    res.on('data', (chunk) => {
        data += chunk;
    });

    res.on('end', () => {
        console.log(`📊 Response Status: ${res.statusCode}`);
        console.log('─────────────────────────────────────\n');

        try {
            const response = JSON.parse(data);
            
            if (res.statusCode === 200 && response.success) {
                console.log('✅ SUCCESS! Newsletter signup completed\n');
                console.log('📬 Response:', response.message);
                console.log('\n💡 Check your email inbox for the welcome message!');
                console.log('   (Don\'t forget to check spam folder if not found)\n');
            } else {
                console.log('❌ FAILED! Newsletter signup unsuccessful\n');
                console.log('Error:', response.error || 'Unknown error');
                console.log('\nTroubleshooting:');
                console.log('1. Make sure the server is running (npm start)');
                console.log('2. Check your .env file has GMAIL_USER and GMAIL_APP_PASSWORD');
                console.log('3. Verify your Gmail App Password is correct');
                console.log('4. Check server logs for more details\n');
            }
        } catch (error) {
            console.log('❌ ERROR: Failed to parse server response\n');
            console.log('Raw response:', data);
            console.log('\nError:', error.message, '\n');
        }
    });
});

req.on('error', (error) => {
    console.log('❌ CONNECTION ERROR\n');
    console.log('Error:', error.message);
    console.log('\nTroubleshooting:');
    console.log('1. Make sure the server is running: npm start');
    console.log('2. Verify the server is running on port 8080');
    console.log('3. Check for any firewall blocking localhost connections\n');
});

req.write(postData);
req.end();

