// Connect to WebSocket server
const socket = io();

// DOM Elements
const displayImage = document.getElementById('display-image');

// Add CSS for fade transitions
const style = document.createElement('style');
style.textContent = `
    .fade-out {
        opacity: 0;
        transition: opacity 0.5s ease-out;
    }
    .fade-in {
        opacity: 1;
        transition: opacity 0.5s ease-in;
    }
    .hidden {
        display: none;
    }
`;
document.head.appendChild(style);

// Set initial state
displayImage.classList.add('fade-in');

// Variables
let settings = {
    screensaver: null,
    current_image: null
};
let images = [];
let screensaverTimeout = null;
let isTransitioning = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Request current state from server
    socket.emit('request_current_state');
});

// Socket events
socket.on('current_state', (data) => {
    settings = data.settings;
    images = data.images;
    updateDisplay();
});

socket.on('settings_updated', (newSettings) => {
    settings = newSettings;
    updateDisplay();
});

socket.on('image_added', (image) => {
    images.push(image);
});

socket.on('image_deleted', (data) => {
    images = images.filter(img => img.id !== data.id);
    
    // If the deleted image was being displayed, update the display
    if (settings.current_image === data.id || settings.screensaver === data.id) {
        updateDisplay();
    }
});

socket.on('image_updated', (data) => {
    // Refresh the image if it's currently displayed
    if (settings.current_image === data.id) {
        updateDisplay(true);
    }
});

// Functions
function updateDisplay(forceRefresh = false) {
    // If already transitioning, don't start another transition
    if (isTransitioning) return;
    
    clearTimeout(screensaverTimeout);
    isTransitioning = true;
    
    // Determine which image to display
    let imageToShow = null;
    
    if (settings.current_image) {
        // Show the currently selected image
        imageToShow = images.find(img => img.id === settings.current_image);
        
        // Set timeout to show screensaver after 5 minutes of inactivity
        screensaverTimeout = setTimeout(() => {
            settings.current_image = null;
            updateDisplay();
        }, 5 * 60 * 1000);
    } else if (settings.screensaver) {
        // Show the screensaver image
        imageToShow = images.find(img => img.id === settings.screensaver);
    }
    
    // First fade out the current image
    displayImage.classList.remove('fade-in');
    displayImage.classList.add('fade-out');
    
    // Wait for fade out to complete
    setTimeout(() => {
        if (imageToShow) {
            // If image was hidden, show it first
            displayImage.classList.remove('hidden');
            
            // Add timestamp to prevent caching if force refresh
            const timestamp = forceRefresh ? `?t=${Date.now()}` : '';
            
            // Two-stage loading process:
            // 1. First load the thumbnail with fade-in effect
            const thumbPath = imageToShow.thumb_path || `thumb_${imageToShow.path}`;
            displayImage.src = `/img/${thumbPath}${timestamp}`;
            displayImage.alt = imageToShow.name;
            
            // Wait for the thumbnail to load before fading in
            displayImage.onload = () => {
                // Show the thumbnail with fade-in effect
                displayImage.classList.remove('fade-out');
                displayImage.classList.add('fade-in');
                
                // 2. Then load the full-size image in the background
                const fullImage = new Image();
                fullImage.src = `/img/${imageToShow.path}${timestamp}`;
                
                // When the full-size image is loaded, replace the thumbnail without fade effects
                fullImage.onload = () => {
                    // Replace the thumbnail with the full-size image (no transition)
                    displayImage.src = fullImage.src;
                    isTransitioning = false;
                };
                
                fullImage.onerror = () => {
                    console.error('Failed to load full-size image:', imageToShow.path);
                    isTransitioning = false;
                };
            };
            
            // Handle thumbnail load errors
            displayImage.onerror = () => {
                console.error('Failed to load thumbnail:', thumbPath);
                
                // Fallback to loading the original image directly
                displayImage.src = `/img/${imageToShow.path}${timestamp}`;
                displayImage.onload = () => {
                    displayImage.classList.remove('fade-out');
                    displayImage.classList.add('fade-in');
                    isTransitioning = false;
                };
                
                displayImage.onerror = () => {
                    console.error('Failed to load image:', imageToShow.path);
                    isTransitioning = false;
                };
            };
        } else {
            // No image to display - hide the element completely
            displayImage.classList.add('hidden');
            displayImage.src = '';
            displayImage.alt = 'No image selected';
            isTransitioning = false;
        }
    }, 500); // Match this with the CSS transition duration
}