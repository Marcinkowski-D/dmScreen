// DOM Elements
const displayCanvas = document.getElementById('display-canvas');
const imageContainer = document.getElementById('image-container');

// Canvas context
const displayCtx = displayCanvas.getContext('2d');

// Helper function to draw an image on canvas in "contain" mode (16:9 aspect ratio)
function drawImageContain(ctx, img, canvasWidth, canvasHeight) {
    // Clear the canvas
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    
    // Calculate dimensions to fit the image within the canvas while maintaining aspect ratio
    const imgWidth = img.width;
    const imgHeight = img.height;
    const imgAspect = imgWidth / imgHeight;
    const canvasAspect = canvasWidth / canvasHeight;
    
    let drawWidth, drawHeight, offsetX, offsetY;
    
    if (imgAspect > canvasAspect) {
        // Image is wider than canvas (relative to height)
        drawWidth = canvasWidth;
        drawHeight = drawWidth / imgAspect;
        offsetX = 0;
        offsetY = (canvasHeight - drawHeight) / 2;
    } else {
        // Image is taller than canvas (relative to width)
        drawHeight = canvasHeight;
        drawWidth = drawHeight * imgAspect;
        offsetX = (canvasWidth - drawWidth) / 2;
        offsetY = 0;
    }
    
    // Draw the image
    ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
}

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
displayCanvas.classList.add('fade-in');

// Set canvas size to match viewport
function resizeCanvas() {
    displayCanvas.width = window.innerWidth;
    displayCanvas.height = window.innerHeight;
}

// Initial resize and add event listener for window resize
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

// Variables
let settings = {
    screensaver: null,
    current_image: null
};
let images = [];
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

    isTransitioning = true;
    
    // Determine which image to display
    let imageToShow = null;
    
    if (settings.current_image) {
        // Show the currently selected image
        imageToShow = images.find(img => img.id === settings.current_image);

    } else if (settings.screensaver) {
        // Show the screensaver image
        imageToShow = images.find(img => img.id === settings.screensaver);
    }
    
    // Track if we're switching from thumbnail to full image (no fade needed)
    const isSwitchingToFullImage = displayCanvas.dataset.loadingFullImage === 'true';
    
    if (!isSwitchingToFullImage) {
        // Fade out the current image (unless we're just switching from thumbnail to full)
        displayCanvas.classList.remove('fade-in');
        displayCanvas.classList.add('fade-out');
    } else {
        // When switching to full image, ensure we're not in fade-out state
        displayCanvas.classList.remove('fade-out');
    }
    
    // Function to load the image
    const loadImage = () => {
        if (imageToShow) {
            // If canvas was hidden, show it first
            displayCanvas.classList.remove('hidden');
            imageContainer.style.display = 'flex';
            
            // Always add timestamp to prevent caching, use a stronger timestamp for force refresh
            const timestamp = forceRefresh ? `?t=${Date.now()}&force=1` : `?t=${Date.now()}`;
            
            if (!isSwitchingToFullImage) {
                // First load the thumbnail
                const thumbnailPath = `/img/crop_thumb_${imageToShow.path}${timestamp}`;
                
                // Create a new Image object for the thumbnail
                const thumbnailImg = new Image();
                
                // When the thumbnail loads, draw it on the canvas and fade it in
                thumbnailImg.onload = () => {
                    // Draw the image on the canvas
                    drawImageContain(displayCtx, thumbnailImg, displayCanvas.width, displayCanvas.height);
                    
                    // Fade in the canvas
                    displayCanvas.classList.remove('fade-out');
                    displayCanvas.classList.add('fade-in');
                    
                    // Mark that we're now loading the full image
                    displayCanvas.dataset.loadingFullImage = 'true';
                    
                    // Reset transitioning state so the next updateDisplay call works
                    isTransitioning = false;
                    
                    // After thumbnail is displayed, load the full image
                    setTimeout(() => {
                        updateDisplay();
                    }, 100);
                };
                
                // Handle thumbnail load errors
                thumbnailImg.onerror = () => {
                    console.error('Failed to load thumbnail:', thumbnailPath);
                    // Fall back to loading the full image directly
                    displayCanvas.dataset.loadingFullImage = 'true';
                    // Reset transitioning state so the next updateDisplay call works
                    isTransitioning = false;
                    updateDisplay();
                };
                
                // Start loading the thumbnail
                thumbnailImg.src = thumbnailPath;
            } else {
                // Now load the full-size image
                const imagePath = `/img/crop_${imageToShow.path}${timestamp}`;
                
                // Create a new Image object for the full image
                const fullImg = new Image();
                
                // When the full image loads, draw it on the canvas and complete the transition
                fullImg.onload = () => {
                    // Draw the image on the canvas
                    drawImageContain(displayCtx, fullImg, displayCanvas.width, displayCanvas.height);
                    
                    // Fade in the canvas
                    displayCanvas.classList.remove('fade-out');
                    displayCanvas.classList.add('fade-in');
                    isTransitioning = false;
                    // Clear the loading flag
                    delete displayCanvas.dataset.loadingFullImage;
                };
                
                // Handle full image load errors
                fullImg.onerror = () => {
                    console.error('Failed to load image:', imagePath);
                    // Keep showing the thumbnail instead of showing nothing
                    displayCanvas.classList.remove('fade-out');
                    displayCanvas.classList.add('fade-in');
                    isTransitioning = false;
                    // Clear the loading flag
                    delete displayCanvas.dataset.loadingFullImage;
                };
                
                // Start loading the full image
                fullImg.src = imagePath;
            }
        } else {
            // No image to display - hide the element completely
            displayCanvas.classList.add('hidden');
            imageContainer.style.display = 'none';
            // Clear the canvas
            displayCtx.clearRect(0, 0, displayCanvas.width, displayCanvas.height);
            isTransitioning = false;
            // Clear the loading flag
            delete displayCanvas.dataset.loadingFullImage;
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