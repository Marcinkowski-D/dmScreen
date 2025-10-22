// DOM Elements
const displayCanvas1 = document.getElementById('display-canvas-1');
const displayCanvas2 = document.getElementById('display-canvas-2');
const imageContainer = document.getElementById('image-container');
const ipOverlay = document.getElementById('ip-overlay');

// Canvas contexts
const displayCtx1 = displayCanvas1.getContext('2d');
const displayCtx2 = displayCanvas2.getContext('2d');

// Track which canvas is currently active
let activeCanvas = displayCanvas1;
let activeCtx = displayCtx1;
let inactiveCanvas = displayCanvas2;
let inactiveCtx = displayCtx2;

let INSTANCE_ID = null;

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
    .fade-visible {
        opacity: 1;
        transition: opacity 0.5s ease-in-out;
    }
    .fade-hidden {
        opacity: 0;
        transition: opacity 0.5s ease-in-out;
    }
    .hidden {
        display: none;
    }
`;
document.head.appendChild(style);

// Set initial state - canvas 1 visible, canvas 2 hidden
displayCanvas1.style.opacity = '1';
displayCanvas2.style.opacity = '0';

// Set canvas size to match viewport
function resizeCanvas() {
    displayCanvas1.width = window.innerWidth;
    displayCanvas1.height = window.innerHeight;
    displayCanvas2.width = window.innerWidth;
    displayCanvas2.height = window.innerHeight;
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
// Long polling is now used instead of fixed interval polling

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Request current state from server
    fetchCurrentState();

    // Start polling for updates
    startPolling();
});

// Long polling functions
function startPolling() {
    // Start long polling loop
    fetchUpdates();
}

async function fetchUpdates() {
    try {
        // Long polling: pass current timestamp to server
        const response = await fetch(`/api/updates?timestamp=${lastUpdateTimestamp}`);
        const data = await response.json();

        if (!INSTANCE_ID) {
            // initialize instance id on first response
            INSTANCE_ID = data.instance_id;
        } else if (INSTANCE_ID !== data.instance_id) {
            // server restarted -> reload view to reinitialize state
            location.reload();
        }


        // If there's a new update, fetch the current state
        if (data.timestamp > lastUpdateTimestamp) {
            lastUpdateTimestamp = data.timestamp;
            fetchCurrentState();
        }
        if (data.admin_connected) {
            ipOverlay.classList.add('hidden')
        } else {
            const parts = ["Server: " + data.ip];
            if (data.wifi_connected && data.ssid) {
                parts.push("WLAN: " + data.ssid);
            } else if (data.adhoc_active) {
                parts.push("Ad-hoc: SSID " + (data.adhoc_ssid || 'dmscreen') + " | Passwort " + (data.adhoc_password || 'dmscreen'));
            }
            ipOverlay.textContent = parts.join(' | ');
            ipOverlay.classList.remove('hidden')
        }
    } catch (error) {
        console.error('Error checking for updates:', error);
        // Wait a bit before retrying on error
        await new Promise(resolve => setTimeout(resolve, 5000));
    }
    
    // Immediately start next long poll request
    fetchUpdates();
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

    // Track if we're switching from thumbnail to full image (no cross-fade needed)
    const isSwitchingToFullImage = activeCanvas.dataset.loadingFullImage === 'true';

    // Function to load the image
    const loadImage = async () => {
        if (imageToShow) {
            // Make sure container is visible
            imageContainer.style.display = 'flex';

            try {
                if (!isSwitchingToFullImage) {
                    // First load the thumbnail by fetching the URL from the server
                    const response = await fetch(`/api/image/${imageToShow.id}/url?thumb=true&crop=true&t=${Date.now()}`);
                    if (!response.ok) {
                        throw new Error('Failed to fetch thumbnail URL');
                    }

                    const data = await response.json();
                    const thumbnailUrl = data.url;

                    // Create a new Image object for the thumbnail
                    const thumbnailImg = new Image();

                    // When the thumbnail loads, draw it on the inactive canvas and cross-fade
                    thumbnailImg.onload = () => {
                        // Draw the image on the inactive canvas
                        drawImageContain(inactiveCtx, thumbnailImg, inactiveCanvas.width, inactiveCanvas.height);

                        // Cross-fade: fade in inactive canvas
                        inactiveCanvas.style.opacity = '1';
                        
                        // After transition completes, swap canvases
                        setTimeout(() => {
                            // Fade out the now-old active canvas
                            activeCanvas.style.opacity = '0';
                            
                            // Swap references
                            const tempCanvas = activeCanvas;
                            const tempCtx = activeCtx;
                            activeCanvas = inactiveCanvas;
                            activeCtx = inactiveCtx;
                            inactiveCanvas = tempCanvas;
                            inactiveCtx = tempCtx;

                            // Mark that we're now loading the full image
                            activeCanvas.dataset.loadingFullImage = 'true';

                            // Reset transitioning state so the next updateDisplay call works
                            isTransitioning = false;

                            // After thumbnail is displayed, load the full image
                            setTimeout(() => {
                                updateDisplay();
                            }, 100);
                        }, 500); // Wait for fade transition
                    };

                    // Handle thumbnail load errors
                    thumbnailImg.onerror = () => {
                        console.error('Failed to load thumbnail:', thumbnailUrl);
                        // Fall back to loading the full image directly
                        activeCanvas.dataset.loadingFullImage = 'true';
                        isTransitioning = false;
                        updateDisplay();
                    };

                    // Start loading the thumbnail
                    thumbnailImg.src = thumbnailUrl;
                } else {
                    // Now load the full-size image - draw on same canvas, no cross-fade
                    const forceParam = forceRefresh ? '&force=1' : '';
                    const response = await fetch(`/api/image/${imageToShow.id}/url?crop=true&t=${Date.now()}${forceParam}`);
                    if (!response.ok) {
                        throw new Error('Failed to fetch image URL');
                    }

                    const data = await response.json();
                    const imageUrl = data.url;

                    // Create a new Image object for the full image
                    const fullImg = new Image();

                    // When the full image loads, draw it on the same active canvas (replace thumbnail)
                    fullImg.onload = () => {
                        // Draw the image on the active canvas (replaces thumbnail smoothly)
                        drawImageContain(activeCtx, fullImg, activeCanvas.width, activeCanvas.height);

                        isTransitioning = false;
                        // Clear the loading flag
                        delete activeCanvas.dataset.loadingFullImage;
                    };

                    // Handle full image load errors
                    fullImg.onerror = () => {
                        console.error('Failed to load image:', imageUrl);
                        // Keep showing the thumbnail
                        isTransitioning = false;
                        // Clear the loading flag
                        delete activeCanvas.dataset.loadingFullImage;
                    };

                    // Start loading the full image
                    fullImg.src = imageUrl;
                }
            } catch (error) {
                console.error('Error fetching image URL:', error);
                isTransitioning = false;
                delete activeCanvas.dataset.loadingFullImage;
            }
        } else {
            // No image to display - hide the container
            imageContainer.style.display = 'none';
            // Clear both canvases
            activeCtx.clearRect(0, 0, activeCanvas.width, activeCanvas.height);
            inactiveCtx.clearRect(0, 0, inactiveCanvas.width, inactiveCanvas.height);
            isTransitioning = false;
            // Clear the loading flag
            delete activeCanvas.dataset.loadingFullImage;
        }
    };

    // Start loading immediately (no pre-fade needed with cross-fade approach)
    loadImage();
}