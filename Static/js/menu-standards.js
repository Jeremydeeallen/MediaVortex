/* MediaVortex Menu Standards JavaScript */
/* Consistent button interactions across all pages */

class MenuStandards {
    constructor() {
        this.initializeStandardHandlers();
    }

    initializeStandardHandlers() {
        // Standard button loading states
        this.setupLoadingStates();
        
        // Standard button click feedback
        this.setupClickFeedback();
        
        // Standard keyboard navigation
        this.setupKeyboardNavigation();
    }

    setupLoadingStates() {
        // Add loading state to buttons when clicked (exclude menu navigation)
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn[data-loading="true"]:not(.nav-link)')) {
                this.setButtonLoading(e.target, true);
            }
        });
    }

    setupClickFeedback() {
        // Add visual feedback to all buttons (exclude menu navigation)
        document.addEventListener('click', (e) => {
            if (e.target.matches('.btn:not(.nav-link)')) {
                this.addClickFeedback(e.target);
            }
        });
    }

    setupKeyboardNavigation() {
        // Enable keyboard navigation for buttons (exclude menu navigation)
        document.addEventListener('keydown', (e) => {
            if (e.target.matches('.btn:not(.nav-link)') && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                e.target.click();
            }
        });
    }

    setButtonLoading(button, isLoading) {
        if (isLoading) {
            button.classList.add('btn-loading');
            button.disabled = true;
            const text = button.querySelector('.btn-text');
            if (text) text.style.opacity = '0.7';
        } else {
            button.classList.remove('btn-loading');
            button.disabled = false;
            const text = button.querySelector('.btn-text');
            if (text) text.style.opacity = '1';
        }
    }

    addClickFeedback(button) {
        // Add ripple effect
        const ripple = document.createElement('span');
        ripple.classList.add('btn-ripple');
        ripple.style.cssText = `
            position: absolute;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.6);
            transform: scale(0);
            animation: ripple 0.6s linear;
            pointer-events: none;
        `;
        
        const rect = button.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = (event.clientX - rect.left - size / 2) + 'px';
        ripple.style.top = (event.clientY - rect.top - size / 2) + 'px';
        
        button.style.position = 'relative';
        button.style.overflow = 'hidden';
        button.appendChild(ripple);
        
        setTimeout(() => ripple.remove(), 600);
    }

    // Standard button state management
    setButtonState(buttonId, state) {
        const button = document.getElementById(buttonId);
        if (!button) return;

        // Remove all state classes
        button.classList.remove('btn-loading', 'btn-success-state', 'btn-error-state');
        
        switch (state) {
            case 'loading':
                this.setButtonLoading(button, true);
                break;
            case 'success':
                button.classList.add('btn-success-state');
                setTimeout(() => button.classList.remove('btn-success-state'), 2000);
                break;
            case 'error':
                button.classList.add('btn-error-state');
                setTimeout(() => button.classList.remove('btn-error-state'), 2000);
                break;
            case 'normal':
                this.setButtonLoading(button, false);
                break;
        }
    }

    // Standard event listener setup
    addStandardEventListener(elementId, eventType, handler, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.warn(`Element with id '${elementId}' not found`);
            return;
        }

        // Add loading state if specified
        if (options.loading) {
            element.setAttribute('data-loading', 'true');
        }

        element.addEventListener(eventType, handler);
    }
}

// Add ripple animation CSS
const rippleCSS = `
@keyframes ripple {
    to {
        transform: scale(4);
        opacity: 0;
    }
}
`;

// Inject CSS
const style = document.createElement('style');
style.textContent = rippleCSS;
document.head.appendChild(style);

// Initialize menu standards when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.MenuStandards = new MenuStandards();
});

// Export for use in other scripts
window.MenuStandards = MenuStandards;
