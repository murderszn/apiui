(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const history = [];
    let connected = false;
    let running = false;
    let configuring = false;
    const percent = value => `${(value * 100).toFixed(1)}%`;
    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        if (className) node.className = className;
        return node;
    }
    async function api(path, body) {
        const response = await fetch(`/api/agent/${path}`, {
            method: body ? 'POST' : 'GET',
            headers: body ? { 'Content-Type': 'application/json' } : {},
            body: body ? JSON.stringify(body) : undefined,
            signal: AbortSignal.timeout(body ? 130000 : 10000)
        });
        if (!(response.headers.get('content-type') || '').includes('application/json')) {
            throw new Error('Agent routes are unavailable. Run npm start and open http://localhost:8080/agent.html.');
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'The agent request failed.');
        return data;
    }
    function controls() {
        $('run').disabled = !connected || running || configuring;
        $('model').disabled = !connected || running || configuring;
        $('threshold').disabled = running;
        $('request').disabled = running;
        $('reconnect').disabled = running || configuring;
        document.querySelectorAll('[data-example]').forEach(button => { button.disabled = running; });
    }
    async function connect() {
        configuring = true;
        connected = false;
        controls();
        $('error').hidden = true;
        $('connection').textContent = 'Checking installed local decision models…';
        $('model').replaceChildren(element('option', 'Connecting…'));
        try {
            const config = await api('config');
            $('model').replaceChildren(...config.models.map(model => {
                const option = element('option', model.name);
                option.value = model.name;
                return option;
            }));
            if (!config.models.length) {
                $('model').append(element('option', 'No local decision models'));
                throw new Error('No local decision model found. Run ollama pull clef-flash, then refresh the connection.');
            }
            $('model').value = config.default_model;
            $('routes').replaceChildren(...config.routes.flatMap(route => [element('dt', route.label), element('dd', route.description)]));
            connected = true;
            $('connection').textContent = 'Ollama connected · Model listed; first run verifies inference.';
        } catch (error) {
            $('model').replaceChildren(element('option', 'Connection unavailable'));
            $('connection').textContent = 'Local agent unavailable';
            showError(error);
        } finally {
            configuring = false;
            controls();
        }
    }
    function showError(error) {
        $('error').textContent = error.name === 'TimeoutError'
            ? 'The request timed out. The model may still be loading. Try again shortly.' : error.message;
        $('error').hidden = false;
    }
    function render(data) {
        $('empty').hidden = true;
        $('result').hidden = false;
        $('result-status').textContent = { ready: 'ROUTE READY', review: 'REVIEW NEEDED', clarify: 'CLARIFY' }[data.status];
        $('intent').textContent = data.label;
        $('probability').textContent = percent(data.probability);
        $('metrics').textContent = `${data.model} · ${data.latency_ms.toLocaleString()} ms · Threshold ${percent(data.threshold)} · Margin ${percent(data.margin)}`;
        $('probabilities').replaceChildren(...data.probabilities.map(item => {
            const row = element('div', undefined, 'prob-row');
            const label = element('div', undefined, 'prob-label');
            label.append(element('span', item.label), element('span', percent(item.probability)));
            const bar = element('div', undefined, 'prob-bar');
            const fill = element('div', undefined, 'prob-fill');
            fill.style.width = `${item.probability * 100}%`;
            bar.append(fill);
            row.append(label, bar);
            return row;
        }));
        $('tool').textContent = data.action.tool || 'request.clarify';
        $('reason').textContent = data.reason;
        $('next').textContent = data.action.next;
        $('action-link').hidden = !data.action.href;
        $('action-link').href = 'app.html';
        $('trace').replaceChildren(...data.trace.map(item => {
            const li = element('li');
            li.append(element('b', item.step), element('span', item.detail));
            return li;
        }));
        $('raw').textContent = JSON.stringify(data.raw, null, 2);
    }
    function renderHistory() {
        $('history-empty').hidden = history.length > 0;
        $('history').replaceChildren(...history.map(item => {
            const button = element('button', undefined, 'history-item');
            button.type = 'button';
            button.title = item.text;
            button.append(element('span', item.text), element('span', item.label), element('span', percent(item.probability)));
            button.addEventListener('click', () => {
                if (running) return;
                $('request').value = item.text;
                render(item);
            });
            return button;
        }));
    }
    $('agent-form').addEventListener('submit', async event => {
        event.preventDefault();
        if (running || !connected) return;
        running = true;
        controls();
        $('error').hidden = true;
        $('result').hidden = true;
        $('empty').hidden = false;
        $('empty').querySelector('h3').textContent = 'Classifying your request…';
        $('empty').querySelector('p').textContent = 'The first request may take longer while Ollama loads the model.';
        $('result-status').textContent = 'RUNNING';
        document.querySelector('.output-panel').setAttribute('aria-busy', 'true');
        $('run').textContent = 'Classifying…';
        try {
            const data = await api('classify', { text: $('request').value, model: $('model').value, threshold: Number($('threshold').value) / 100 });
            render(data);
            history.unshift(data);
            history.length = Math.min(history.length, 8);
            renderHistory();
        } catch (error) {
            showError(error);
            $('result-status').textContent = 'ERROR';
            $('empty').querySelector('h3').textContent = 'No decision returned.';
            $('empty').querySelector('p').textContent = 'Check the error in the request panel and retry.';
        } finally {
            running = false;
            document.querySelector('.output-panel').setAttribute('aria-busy', 'false');
            $('run').textContent = 'Classify & route ↗';
            controls();
        }
    });
    document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => {
        $('request').value = button.dataset.example;
        $('request').focus();
    }));
    $('threshold').addEventListener('input', () => { $('threshold-value').textContent = `${$('threshold').value}%`; });
    $('reconnect').addEventListener('click', connect);
    $('clear').addEventListener('click', () => { history.length = 0; renderHistory(); });
    connect();
})();
