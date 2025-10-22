// Function to load header content
async function loadHeader() {
    try {
        const response = await fetch('/templates/header.html');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const headerContent = await response.text();
        
        // Extract user ID from the current page before processing header
        const userId = extractUserIdFromPage();
        
        // Create a temporary container to hold the HTML
        const tempContainer = document.createElement('div');
        tempContainer.innerHTML = headerContent;
        
        // Get the header element
        const headerElement = tempContainer.querySelector('header');
        if (headerElement) {
            // Try to insert the header before the container element
            const container = document.querySelector('.container');
            if (container && container.parentNode) {
                container.parentNode.insertBefore(headerElement, container);
            } else {
                // Fallback: Insert the header at the beginning of the body
                document.body.insertBefore(headerElement, document.body.firstChild);
            }
        }
        
        // Get the settings panel
        const settingsPanel = tempContainer.querySelector('.settings-panel');
        if (settingsPanel) {
            // Insert the settings panel at the end of the body
            document.body.appendChild(settingsPanel);
        }
        
        // Update navigation links with user ID after header is loaded
        if (userId) {
            updateNavigationWithUserId(userId);
        }
    } catch (error) {
        console.error('Error loading header:', error);
    }
}

// Extract user ID from various sources
function extractUserIdFromPage() {
    // Try to get from URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    let userId = urlParams.get('user_id');
    
    // If not in URL, try to get from localStorage
    if (!userId) {
        userId = localStorage.getItem('user_id');
    }
    
    // If not in localStorage, try to get from hidden input
    if (!userId) {
        const userInputElement = document.querySelector('#user_id');
        if (userInputElement && userInputElement.value) {
            userId = userInputElement.value;
        }
    }
    
    return userId;
}

// Update navigation links with user ID
function updateNavigationWithUserId(userId) {
    if (userId) {
        // Store user ID in localStorage for persistence
        localStorage.setItem('user_id', userId);
        
        // Update all navigation links to include user ID
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href && !href.includes('user_id=')) {
                // Add user_id parameter to the link
                const separator = href.includes('?') ? '&' : '?';
                link.setAttribute('href', `${href}${separator}user_id=${userId}`);
            }
        });
    }
}

// Load header when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadHeader);
} else {
    // DOM is already loaded
    loadHeader();
}

// Also try to load header after a small delay to ensure all elements are ready
setTimeout(loadHeader, 100);

// Additional function to update navigation links with user ID
function updateNavigationWithUserId() {
    const userId = extractUserIdFromPage();
    if (userId) {
        // Store user ID in localStorage for persistence
        localStorage.setItem('user_id', userId);
        
        // Update all navigation links to include user ID
        const navLinks = document.querySelectorAll('a.nav-link');
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href && !href.includes('user_id=')) {
                // Add user_id parameter to the link
                const separator = href.includes('?') ? '&' : '?';
                link.setAttribute('href', `${href}${separator}user_id=${userId}`);
            }
        });
    }
}

// Update navigation when DOM is loaded
document.addEventListener('DOMContentLoaded', updateNavigationWithUserId);