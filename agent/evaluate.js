'use strict';

// Small real-model smoke evaluation. Not a classification accuracy benchmark.
// Requires the APIUI Node server and local Ollama; never substitutes model outputs.
const examples = [
    { text: 'Show me the columns and data types in my customers API.', intent: 'inspect_schema', status: 'ready' },
    { text: 'Find customers in Texas and sort them by revenue.', intent: 'query_data', status: 'ready' },
    { text: 'Create a REST API from my uploaded sales CSV.', intent: 'generate_api', status: 'review' },
    { text: 'Delete my old inventory API.', intent: 'manage_api', status: 'review' },
    { text: 'Help me with that thing.', intent: 'other', status: 'clarify' }
];

async function main() {
    let passed = 0;
    const results = [];
    for (const example of examples) {
        const response = await fetch('http://localhost:8080/api/agent/classify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: example.text }),
            signal: AbortSignal.timeout(130000)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);
        const correct = result.intent === example.intent && result.status === example.status && result.action.executed === false;
        if (correct) passed++;
        results.push({ text: example.text, expected: example.intent, actual: result.intent,
            status: result.status, probability: result.probability, latency_ms: result.latency_ms, passed: correct });
    }
    console.table(results);
    console.log(`${passed}/${examples.length} real-model smoke cases passed.`);
    if (passed !== examples.length) process.exitCode = 1;
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
