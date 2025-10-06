const express = require('express');
const path = require('path');
const app = express();
const port = 8080;

// Serve static files from the frontend directory
app.use(express.static(path.join(__dirname, 'frontend')));

// Serve index.html for the root route
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

// Start the server
app.listen(port, () => {
    console.log(`🚀 Frontend server running at http://localhost:${port}`);
    console.log(`📁 Serving files from: ${path.join(__dirname, 'frontend')}`);
});
