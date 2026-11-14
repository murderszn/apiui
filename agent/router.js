'use strict';

const express = require('express');
const { createAgentService } = require('./service');

function createAgentRouter(service = createAgentService()) {
    const router = express.Router();
    let busy = false;

    router.use((req, res, next) => {
        res.set('Cache-Control', 'no-store');
        const loopback = ['127.0.0.1', '::1', '::ffff:127.0.0.1'];
        // Local POC only. Do not expose the local model through the public web server.
        if (!loopback.includes(req.socket.remoteAddress)) {
            return res.status(403).json({ error: 'The agent POC is available on this machine only.' });
        }
        const host = req.get('host');
        if (!/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/.test(host || '')) {
            return res.status(403).json({ error: 'Open the agent using localhost.' });
        }
        if (req.get('origin') && req.get('origin') !== `http://${host}`) {
            return res.status(403).json({ error: 'Open the agent from this local application.' });
        }
        next();
    });

    router.get('/config', async (req, res) => {
        try {
            res.json(await service.config());
        } catch (error) {
            res.status(error.status || 500).json({ error: error.status ? error.message : 'Unable to load the agent configuration.' });
        }
    });

    router.post('/classify', async (req, res) => {
        if (!req.is('application/json')) return res.status(415).json({ error: 'Send the request as JSON.' });
        if (busy) return res.status(429).json({ error: 'A classification is already running. Try again when it completes.' });
        busy = true;
        try {
            res.json(await service.classify(req.body));
        } catch (error) {
            res.status(error.status || 500).json({ error: error.status ? error.message : 'Unable to classify this request.' });
        } finally {
            busy = false;
        }
    });
    return router;
}

module.exports = { createAgentRouter };
