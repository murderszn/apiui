/**
 * Cookie Consent Modal for apiUI
 * Shows a cookie policy acceptance modal on first visit
 * Uses localStorage to track acceptance
 */

(function() {
    'use strict';

    // Configuration
    const COOKIE_CONSENT_KEY = 'apiui_cookie_consent_accepted';
    const COOKIE_CONSENT_VERSION = '1.0'; // Increment this if you update the policy

    // Modal HTML template
    const modalHTML = `
        <div id="cookie-consent-modal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-50" style="display: none;">
            <div class="pixel-card bg-white max-w-lg w-full mx-4 shadow-2xl border-2 border-black">
                <div class="p-6">
                    <!-- Header -->
                    <div class="flex items-center mb-4">
                        <div class="pixel-icon w-10 h-10 mr-3 bg-pink-500 text-white flex items-center justify-center">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                        </div>
                        <h3 class="arcade-title text-lg text-black">Cookie Policy</h3>
                    </div>

                    <!-- Content -->
                    <div class="pixel-body text-gray-700 mb-6 leading-relaxed">
                        <p class="mb-3">
                            We use cookies and similar technologies to enhance your experience on apiUI. By continuing to use our platform, you agree to our use of cookies.
                        </p>
                        <p class="text-sm text-gray-600">
                            You can learn more about how we use cookies in our <a href="cookie-policy.html" class="text-pink-500 hover:text-pink-600 underline">Cookie Policy</a>.
                        </p>
                    </div>

                    <!-- Buttons -->
                    <div class="flex flex-col sm:flex-row gap-3">
                        <button id="accept-cookies" class="pixel-btn pixel-btn-primary flex-1">
                            Accept Cookies
                        </button>
                        <a href="cookie-policy.html" class="pixel-btn pixel-btn-secondary flex-1 text-center">
                            Learn More
                        </a>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Modal CSS styles (injected dynamically)
    const modalStyles = `
        #cookie-consent-modal {
            animation: modal-fade-in 0.3s ease-out;
        }

        #cookie-consent-modal .pixel-card {
            animation: modal-slide-up 0.3s ease-out;
        }

        @keyframes modal-fade-in {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @keyframes modal-slide-up {
            from {
                opacity: 0;
                transform: translateY(20px) scale(0.95);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }

        /* Ensure modal appears above all content */
        #cookie-consent-modal {
            z-index: 9999 !important;
        }
    `;

    /**
     * Check if user has already accepted cookies
     * @returns {boolean} True if cookies have been accepted
     */
    function hasAcceptedCookies() {
        try {
            const consent = localStorage.getItem(COOKIE_CONSENT_KEY);
            if (!consent) return false;

            const consentData = JSON.parse(consent);
            return consentData.accepted && consentData.version === COOKIE_CONSENT_VERSION;
        } catch (error) {
            console.warn('Error checking cookie consent:', error);
            return false;
        }
    }

    /**
     * Store cookie acceptance in localStorage
     */
    function acceptCookies() {
        try {
            const consentData = {
                accepted: true,
                version: COOKIE_CONSENT_VERSION,
                timestamp: new Date().toISOString(),
                userAgent: navigator.userAgent
            };
            localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify(consentData));
        } catch (error) {
            console.error('Error storing cookie consent:', error);
        }
    }

    /**
     * Show the cookie consent modal
     */
    function showCookieModal() {
        const modal = document.getElementById('cookie-consent-modal');
        if (modal) {
            modal.style.display = 'flex';

            // Prevent background scrolling when modal is open
            document.body.style.overflow = 'hidden';

            // Focus management
            modal.setAttribute('aria-hidden', 'false');
            const acceptBtn = document.getElementById('accept-cookies');
            if (acceptBtn) {
                acceptBtn.focus();
            }
        }
    }

    /**
     * Hide the cookie consent modal
     */
    function hideCookieModal() {
        const modal = document.getElementById('cookie-consent-modal');
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';

            // Focus management
            modal.setAttribute('aria-hidden', 'true');
        }
    }

    /**
     * Initialize the cookie consent modal
     */
    function initCookieConsent() {
        // Check if user has already accepted cookies
        if (hasAcceptedCookies()) {
            return; // Don't show modal if already accepted
        }

        // Inject styles
        const style = document.createElement('style');
        style.textContent = modalStyles;
        document.head.appendChild(style);

        // Inject modal HTML
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Set up event listeners
        const acceptBtn = document.getElementById('accept-cookies');
        const modal = document.getElementById('cookie-consent-modal');

        if (acceptBtn) {
            acceptBtn.addEventListener('click', function() {
                acceptCookies();
                hideCookieModal();
            });
        }

        // Close modal when clicking outside
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    // Optional: You could make clicking outside NOT close the modal
                    // to ensure users make a conscious choice
                    // hideCookieModal();
                }
            });
        }

        // Handle escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
                // Optional: Allow escape to close modal
                // hideCookieModal();
            }
        });

        // Show the modal after a short delay to ensure page is loaded
        setTimeout(function() {
            showCookieModal();
        }, 1000);
    }

    /**
     * Reset cookie consent (useful for testing)
     */
    window.resetCookieConsent = function() {
        try {
            localStorage.removeItem(COOKIE_CONSENT_KEY);
            console.log('Cookie consent reset. Refresh the page to see the modal again.');
        } catch (error) {
            console.error('Error resetting cookie consent:', error);
        }
    };

    /**
     * Get current cookie consent status
     */
    window.getCookieConsentStatus = function() {
        return {
            accepted: hasAcceptedCookies(),
            data: hasAcceptedCookies() ? JSON.parse(localStorage.getItem(COOKIE_CONSENT_KEY)) : null
        };
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCookieConsent);
    } else {
        initCookieConsent();
    }

})();
