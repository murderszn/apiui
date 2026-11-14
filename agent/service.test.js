'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createAgentService, buildResult, ROUTES, validateInput } = require('./service');
const { createAgentRouter } = require('./router');
const express = require('express');
const http = require('node:http');

function decision(choice = 'inspect_schema', winning = 0.96) {
    return { answers: { intent: { type: 'choice', choice, confidence: 0.9,
        probabilities: Object.fromEntries(Object.keys(ROUTES).map(key => [key, key === choice ? winning : (1 - winning) / 4])) } } };
}
const input = { text: 'Show the schema', model: 'clef-flash:latest', threshold: 0.75 };

test('routes a clear read request to a preview and preserves the raw decision', () => {
    const raw = decision();
    const result = buildResult(raw, input, 125);
    assert.equal(result.status, 'ready');
    assert.equal(result.action.tool, 'schema.inspect');
    assert.equal(result.action.executed, false);
    assert.equal(result.raw, raw);
});

test('requires review for mutations even when the classification is certain', () => {
    for (const intent of ['generate_api', 'manage_api']) {
        assert.equal(buildResult(decision(intent), input, 0).status, 'review');
    }
});

test('asks for clarification on unrelated, low-probability, or close decisions', () => {
    assert.equal(buildResult(decision('other'), input, 0).action.tool, null);
    assert.equal(buildResult(decision('query_data', 0.6), input, 0).status, 'clarify');
    const raw = decision();
    raw.answers.intent.probabilities = { inspect_schema: 0.54, query_data: 0.44, generate_api: 0.01, manage_api: 0.005, other: 0.005 };
    assert.equal(buildResult(raw, { ...input, threshold: 0.5 }, 0).status, 'clarify');
});

test('rejects missing scores, unknown labels, invalid probabilities, and inconsistent winners', () => {
    const missing = decision();
    delete missing.answers.intent.probabilities.other;
    const unknown = decision();
    unknown.answers.intent.choice = '__proto__';
    const invalid = decision();
    invalid.answers.intent.probabilities.inspect_schema = NaN;
    const wrongWinner = decision();
    wrongWinner.answers.intent.choice = 'query_data';
    const badSum = decision();
    badSum.answers.intent.probabilities.other = 0.5;
    for (const raw of [missing, unknown, invalid, wrongWinner, badSum, {}]) {
        assert.throws(() => buildResult(raw, input, 0), error => error.status === 502);
    }
});

test('validates user input before calling Ollama', () => {
    for (const body of [null, {}, { text: '  ' }, { text: 'x'.repeat(12001) }, { text: 'hi', threshold: '0.75' }, { text: 'hi', threshold: 0.2 }, { text: 'hi', model: {} }]) {
        assert.throws(() => validateInput(body), error => error.status === 400);
    }
});

test('uses the System One API and only allows installed local decision models', async () => {
    const calls = [];
    const service = createAgentService({ fetchImpl: async (url, options) => {
        calls.push({ url, options });
        return { ok: true, json: async () => url.endsWith('/api/tags') ? { models: [
            { name: 'gemma4:latest', capabilities: ['completion'] },
            { name: 'clef:cloud', capabilities: ['decision'] },
            { name: 'clef:27b-cloud', capabilities: ['decision'] },
            { name: 'remote:latest', capabilities: ['decision'], remote_model: 'clef' },
            { name: 'clef-flash:latest', capabilities: ['decision'] }
        ] } : decision() };
    } });
    const config = await service.config();
    assert.deepEqual(config.models.map(model => model.name), ['clef-flash:latest']);
    await assert.rejects(service.classify({ text: 'hi', model: 'gemma4:latest' }), error => error.status === 400);
    const result = await service.classify({ text: 'show schema' });
    assert.equal(result.intent, 'inspect_schema');
    const request = calls.at(-1);
    assert.equal(request.url, 'http://127.0.0.1:11434/v1/systemone');
    const payload = JSON.parse(request.options.body);
    assert.equal(payload.questions.intent.type, 'choice');
    assert.equal(payload.state.user_request, 'show schema');
    assert.equal(payload.model, 'clef-flash:latest');
});

test('reports offline Ollama, timeouts, and incompatible models', async () => {
    for (const [name, status] of [['TypeError', 503], ['TimeoutError', 504]]) {
        const service = createAgentService({ fetchImpl: async () => { const error = new Error(); error.name = name; throw error; } });
        await assert.rejects(service.config(), error => error.status === status);
    }
    const service = createAgentService({ fetchImpl: async () => ({ ok: false, json: async () => ({ error: 'format no longer supported' }) }) });
    await assert.rejects(service.config(), /ollama pull clef-flash/);
});

test('handles an empty installed-model list without falling back to a cloud model', async () => {
    const service = createAgentService({ fetchImpl: async () => ({ ok: true, json: async () => ({ models: [] }) }) });
    assert.equal((await service.config()).default_model, null);
    await assert.rejects(service.classify({ text: 'show schema' }), error => error.status === 400);
});

test('HTTP boundary enforces same-origin access, JSON, and a single active inference', async t => {
    let finish;
    const app = express();
    app.use(express.json());
    app.use('/api/agent', createAgentRouter({
        config: async () => ({ mode: 'preview' }),
        classify: () => new Promise(resolve => { finish = resolve; })
    }));
    const server = app.listen(0, '127.0.0.1');
    await new Promise(resolve => server.once('listening', resolve));
    t.after(() => { server.closeAllConnections(); server.close(); });
    const base = `http://127.0.0.1:${server.address().port}/api/agent`;
    assert.equal((await fetch(`${base}/config`)).status, 200);
    assert.equal((await fetch(`${base}/config`, { headers: { Origin: 'https://unrelated.example' } })).status, 403);
    // Node fetch derives Host from the URL; use the HTTP client to send a custom Host.
    const badHostStatus = await new Promise((resolve, reject) => {
        const request = http.get(`${base}/config`, { headers: { Host: 'unrelated.example' } }, response => {
            response.resume();
            resolve(response.statusCode);
        });
        request.on('error', reject);
    });
    assert.equal(badHostStatus, 403);
    assert.equal((await fetch(`${base}/classify`, { method: 'POST', body: 'text' })).status, 415);
    const first = fetch(`${base}/classify`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"text":"schema"}' });
    // Wait for the handler to begin before issuing the competing request.
    while (!finish) await new Promise(resolve => setImmediate(resolve));
    const second = await fetch(`${base}/classify`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"text":"schema"}' });
    assert.equal(second.status, 429);
    finish({ intent: 'inspect_schema' });
    assert.equal((await first).status, 200);
});
