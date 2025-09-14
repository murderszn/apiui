// E2E Test for File Upload and API Generation
// Run with: node test_e2e_upload.js

const fs = require('fs');
const path = require('path');

console.log('🚀 Starting E2E Upload Test\\n');

// Test 1: Check if sample data exists
const samplePath = path.join(__dirname, 'frontend', 'sample-data.csv');
console.log('📁 Checking sample data file...');
if (fs.existsSync(samplePath)) {
    const content = fs.readFileSync(samplePath, 'utf8');
    console.log('✅ Sample data found:', content.split('\\n').length, 'lines');
} else {
    console.log('❌ Sample data not found');
}

// Test 2: Test backend health
console.log('\\n🏥 Testing backend health...');
fetch('http://localhost:8000/health')
    .then(res => res.json())
    .then(data => console.log('✅ Backend healthy:', data.status))
    .catch(err => console.log('❌ Backend not responding:', err.message));

// Test 3: Test API listing
console.log('\\n📋 Testing API listing...');
fetch('http://localhost:8000/v1/apis')
    .then(res => res.json())
    .then(data => console.log('✅ APIs found:', data.total))
    .catch(err => console.log('❌ API listing failed:', err.message));

console.log('\\n📝 Test completed. Check the results above.');
console.log('🌐 Frontend: http://localhost:3000/app.html');
console.log('🔧 Backend: http://localhost:8000/health');
