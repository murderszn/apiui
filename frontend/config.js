(function (global) {
    'use strict';

    const STORAGE_KEY = 'APIUI_BACKEND_URL';
    const LEGACY_STORAGE_KEY = 'apiui_backend_base_url';

    function isLocalOrLanHost(hostname) {
        if (!hostname) return true;
        const h = String(hostname).toLowerCase();
        return (
            h === 'localhost' ||
            h === '127.0.0.1' ||
            h === '[::1]' ||
            h === '::1' ||
            h.startsWith('192.168.') ||
            h.startsWith('10.') ||
            /^172\.(1[6-9]|2\d|3[0-1])\./.test(h) ||
            h.endsWith('.local')
        );
    }

    function normalizeBackendUrl(raw) {
        if (!raw || typeof raw !== 'string') return '';
        let url = raw.trim();
        if (!url) return '';
        if (!/^https?:\/\//i.test(url)) {
            const localHostMatch = /^(localhost|127\.0\.0\.1|192\.168\.|10\.|172\.(1[6-9]|2\d|3[0-1])\.|[^/:]+\.local)(:\d+)?(\/|$)/i.test(url);
            url = (localHostMatch ? 'http://' : 'https://') + url;
        }
        return url.replace(/\/+$/, '');
    }

    function readQueryBackendParam() {
        try {
            const params = new URLSearchParams(global.location.search || '');
            const fromSearch = params.get('backend') || params.get('api') || params.get('backendUrl');
            if (fromSearch) return normalizeBackendUrl(fromSearch);

            const hash = global.location.hash || '';
            const match = hash.match(/backend=([^&]+)/i);
            if (match) return normalizeBackendUrl(decodeURIComponent(match[1]));
        } catch (err) {
            // Ignore URL parsing errors
        }
        return '';
    }

    function readStoredBackendUrl() {
        try {
            const primary = global.localStorage.getItem(STORAGE_KEY);
            if (primary && !primary.includes('.run.app')) {
                return normalizeBackendUrl(primary);
            }
            const legacy = global.localStorage.getItem(LEGACY_STORAGE_KEY);
            if (legacy && !legacy.includes('.run.app')) {
                return normalizeBackendUrl(legacy);
            }
        } catch (err) {
            // Ignore storage access errors
        }
        return '';
    }

    function detectBackendUrl() {
        const queryOverride = readQueryBackendParam();
        if (queryOverride) {
            return queryOverride;
        }

        const storedOverride = readStoredBackendUrl();
        if (storedOverride) {
            return storedOverride;
        }

        try {
            const hostname = global.location.hostname || '';
            if (isLocalOrLanHost(hostname)) {
                return `http://${hostname || 'localhost'}:8000`;
            }
            if (global.location.origin && /^https?:\/\//i.test(global.location.origin)) {
                return global.location.origin.replace(/\/+$/, '');
            }
        } catch (err) {
            // Ignore location access errors
        }

        return 'http://localhost:8000';
    }

    function setSavedBackendUrl(url) {
        const normalized = normalizeBackendUrl(url);
        if (!normalized) {
            try {
                global.localStorage.removeItem(STORAGE_KEY);
                global.localStorage.removeItem(LEGACY_STORAGE_KEY);
            } catch (err) {
                // Ignore
            }
            const detected = detectBackendUrl();
            global.APIUI_AUTH_BASE_URL = detected;
            global.BACKEND_BASE_URL = detected;
            return detected;
        }

        try {
            global.localStorage.setItem(STORAGE_KEY, normalized);
            global.localStorage.setItem(LEGACY_STORAGE_KEY, normalized);
        } catch (err) {
            // Ignore storage access errors
        }
        global.APIUI_AUTH_BASE_URL = normalized;
        global.BACKEND_BASE_URL = normalized;
        return normalized;
    }

    const activeUrl = detectBackendUrl();
    global.APIUI_AUTH_BASE_URL = activeUrl;
    global.BACKEND_BASE_URL = activeUrl;
    global.APIUI_CONFIG = {
        STORAGE_KEY,
        isLocalOrLanHost,
        normalizeBackendUrl,
        detectBackendUrl,
        setSavedBackendUrl,
        getBackendUrl: function () {
            return global.BACKEND_BASE_URL || global.APIUI_AUTH_BASE_URL || detectBackendUrl();
        }
    };
})(window);
