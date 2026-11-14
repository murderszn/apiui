# Local classification agent POC

Start Ollama with an installed decision model and serve APIUI:

```sh
ollama pull clef-flash
npm start
```

Open <http://localhost:8080/agent.html>, or select **Agent Lab** in the console sidebar. The Node server is required; a static file server or the Python backend alone does not provide the agent endpoints. No Python backend, database, or cloud API key is needed for this POC. Node 20+ is required.

The flow is request → Clef intent classification → deterministic routing checks → proposed action. This POC tests classification and routing; it does not execute tools or resolve target APIs and parameters. Its five fixed labels are defined in `service.js`. Changing a label's criteria changes the model's classification task without training.

`GET /api/agent/config` discovers installed models with the `decision` capability. `POST /api/agent/classify` accepts:

```json
{"text":"Show the columns in my customers API", "model":"clef-flash:latest", "threshold":0.75}
```

The service calls Ollama at `http://127.0.0.1:11434/v1/systemone`. It allows installed local decision models only. No fallback to chat models, cloud models, or mock decisions is used. The API is restricted to loopback clients and local Host headers, rejects cross-origin browser requests, and permits one active inference at a time.

A route is ready when its top-label probability meets the chosen threshold (default 0.75) and leads the runner-up by at least 0.15. API generation and management routes require review. Uncertain or unrelated requests ask for clarification. These are experimental routing rules; model probabilities and the separate raw `confidence` value are not guarantees of correctness. Every result includes the score distribution, trace, proposed tool name, inference latency, and raw model response. Request history is held only in the current tab's memory.

The first classification can take longer while the model loads; inference times out after 120 seconds. If Ollama reports an unsupported model format, refresh it with `ollama pull clef-flash:latest`.

Run `npm run test:agent` for service and HTTP boundary tests. These use controlled responses to check routing logic. Run `npm run eval:agent` while the Node server and Ollama are running to exercise the five UI examples through the real model. This small smoke evaluation is not an accuracy benchmark; evaluate classification quality separately with representative requests.

Protocol reference: [Ollama decision models](https://docs.ollama.com/capabilities/decision), [Clef Flash](https://ollama.com/library/clef-flash).
