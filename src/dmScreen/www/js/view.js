// DOM Elements
const displayImage = document.getElementById('display-image');
const imageContainer = document.getElementById('image-container');

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
    /* Prevent background visibility during image transitions */
    #display-image {
        background-color: black;
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
let lastUpdateTimestamp = 0;
const POLLING_INTERVAL = 2000; // Poll every 2 seconds

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Request current state from server
    fetchCurrentState();
    
    // Start polling for updates
    startPolling();
});

// Polling functions
function startPolling() {
    // Initial fetch
    fetchUpdates();
    
    // Set up interval for polling
    setInterval(fetchUpdates, POLLING_INTERVAL);
}

async function fetchUpdates() {
    try {
        const response = await fetch('/api/updates');
        const data = await response.json();
        
        // If there's a new update, fetch the current state
        if (data.timestamp > lastUpdateTimestamp) {
            lastUpdateTimestamp = data.timestamp;
            fetchCurrentState();
        }
    } catch (error) {
        console.error('Error checking for updates:', error);
    }
}

async function fetchCurrentState() {
    try {
        const response = await fetch('/api/current_state?t=' + Date.now());
        const data = await response.json();

        // Update last timestamp
        lastUpdateTimestamp = data.timestamp;
        
        // Check if images have changed
        const oldImages = images;
        const oldSettings = settings;
        
        // Update data
        settings = data.settings;
        images = data.images;
        
        // Handle image deletion
        if (oldImages.length > 0 && oldSettings.current_image) {
            const oldImage = oldImages.find(img => img.id === oldSettings.current_image);
            const newImage = images.find(img => img.id === oldSettings.current_image);
            
            if (oldImage && !newImage) {
                // Image was deleted, update display
                updateDisplay();
                return;
            }
        }
        
        // Handle settings changes
        if (oldSettings.current_image !== settings.current_image || 
            oldSettings.screensaver !== settings.screensaver) {
            updateDisplay();
            return;
        }
        
        // Handle image updates
        if (settings.current_image) {
            const oldImage = oldImages.find(img => img.id === settings.current_image);
            const newImage = images.find(img => img.id === settings.current_image);
            
            if (oldImage && newImage) {
                // Check if path or name changed
                if (oldImage.path !== newImage.path || oldImage.name !== newImage.name) {
                    updateDisplay(true);
                    return;
                }
                
                // If timestamp changed significantly and we're displaying this image,
                // force a refresh to handle rotated images
                if (settings.current_image) {
                    updateDisplay(true);
                    return;
                }
            }
        }
        
        // If this is the first load, update display
        if (oldImages.length === 0) {
            updateDisplay();
        }
    } catch (error) {
        console.error('Error fetching current state:', error);
    }
}

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
    
    // Track if we're switching from thumbnail to full image (no fade needed)
    const isSwitchingToFullImage = displayImage.dataset.loadingFullImage === 'true';
    
    if (!isSwitchingToFullImage) {
        // Fade out the current image (unless we're just switching from thumbnail to full)
        displayImage.classList.remove('fade-in');
        displayImage.classList.add('fade-out');
    } else {
        // When switching to full image, ensure we're not in fade-out state
        displayImage.classList.remove('fade-out');
    }
    
    // Function to apply transformations based on image metadata
    const applyTransformations = (image) => {
        // Reset all transformation classes
        displayImage.className = 'fullscreen-image';
        if (isSwitchingToFullImage) {
            displayImage.classList.add('fade-in');
        }
    };
    
    // Function to load the image
    const loadImage = () => {
        if (imageToShow) {
            // If image was hidden, show it first
            displayImage.classList.remove('hidden');
            imageContainer.style.display = 'flex';
            
            // Always add timestamp to prevent caching, use a stronger timestamp for force refresh
            const timestamp = forceRefresh ? `?t=${Date.now()}&force=1` : `?t=${Date.now()}`;
            
            if (!isSwitchingToFullImage) {
                // First load the thumbnail
                const thumbnailPath = `/img/crop_thumb_${imageToShow.path}${timestamp}`;
                displayImage.alt = imageToShow.name;
                
                // Set the src to load the thumbnail
                displayImage.src = thumbnailPath;
                
                // When the thumbnail loads, fade it in and then load the full image
                displayImage.onload = () => {
                    // Apply transformations
                    applyTransformations(imageToShow);
                    
                    displayImage.classList.remove('fade-out');
                    displayImage.classList.add('fade-in');
                    
                    // Mark that we're now loading the full image
                    displayImage.dataset.loadingFullImage = 'true';
                    
                    // Reset transitioning state so the next updateDisplay call works
                    isTransitioning = false;
                    
                    // After thumbnail is displayed, load the full image
                    setTimeout(() => {
                        updateDisplay();
                    }, 100);
                };
                
                // Handle thumbnail load errors
                displayImage.onerror = () => {
                    console.error('Failed to load thumbnail:', thumbnailPath);
                    // Fall back to loading the full image directly
                    displayImage.dataset.loadingFullImage = 'true';
                    // Reset transitioning state so the next updateDisplay call works
                    isTransitioning = false;
                    updateDisplay();
                };
            } else {
                // Now load the full-size image
                const imagePath = `/img/crop_${imageToShow.path}${timestamp}`;
                displayImage.alt = imageToShow.name;
                
                // Set the src to load the full image
                displayImage.src = imagePath;
                
                // When the full image loads, complete the transition
                displayImage.onload = () => {
                    // Apply transformations
                    applyTransformations(imageToShow);
                    
                    displayImage.classList.remove('fade-out');
                    displayImage.classList.add('fade-in');
                    isTransitioning = false;
                    // Clear the loading flag
                    delete displayImage.dataset.loadingFullImage;
                };
                
                // Handle full image load errors
                displayImage.onerror = () => {
                    console.error('Failed to load image:', imagePath);
                    // Keep showing the thumbnail instead of showing nothing
                    displayImage.classList.remove('fade-out');
                    displayImage.classList.add('fade-in');
                    isTransitioning = false;
                    // Clear the loading flag
                    delete displayImage.dataset.loadingFullImage;
                };
            }
        } else {
            // No image to display - hide the element completely
            displayImage.classList.add('hidden');
            imageContainer.style.display = 'none';
            displayImage.src = '';
            displayImage.alt = 'No image selected';
            isTransitioning = false;
            // Clear the loading flag
            delete displayImage.dataset.loadingFullImage;
        }
    };
    
    if (isSwitchingToFullImage || forceRefresh) {
        // If we're just switching from thumbnail to full image, do it immediately
        loadImage();
    } else {
        // Otherwise wait for fade out to complete
        setTimeout(loadImage, 500); // Match this with the CSS transition duration
    }
}