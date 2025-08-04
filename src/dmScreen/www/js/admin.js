// DOM Elements
const uploadForm = document.getElementById('upload-form');
const gallery = document.getElementById('gallery');
const screensaverSelect = document.getElementById('screensaver');
const saveSettingsBtn = document.getElementById('save-settings');
const wifiStatus = document.getElementById('wifi-status');
const wifiForm = document.getElementById('wifi-form');
const previewCanvas = document.getElementById('preview-canvas');
const previewStatus = document.getElementById('preview-status');
const resetDisplayBtn = document.getElementById('reset-display');
const imageFilesInput = document.getElementById('image-files');
const imagePreviewContainer = document.getElementById('image-preview-container');
const imagePreviewList = document.getElementById('image-preview-list');
const uploadButton = document.getElementById('upload-button');
const backdrop = document.getElementById('backdrop');
const backdropText = document.getElementById('backdrop-text');

// Crop Modal Elements
const cropModal = document.getElementById('crop-modal');
const cropPreviewContainer = document.getElementById('crop-preview-container');
const cropPreviewCanvas = document.getElementById('crop-preview-canvas');
const cropSelection = document.getElementById('crop-selection');
const mirrorHCheckbox = document.getElementById('mirror-h');
const mirrorVCheckbox = document.getElementById('mirror-v');
const rotate_0 = document.getElementById('rotate-0');
const rotate_90 = document.getElementById('rotate-90');
const rotate_180 = document.getElementById('rotate-180');
const rotate_270 = document.getElementById('rotate-270');

// Canvas context
const previewCtx = previewCanvas.getContext('2d');
const cropPreviewCtx = cropPreviewCanvas.getContext('2d');

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
    console.log(canvasWidth, canvasHeight);
    console.log(drawWidth, drawHeight, offsetX, offsetY);

    // Draw the image
    ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
}

const cropApplyBtn = document.getElementById('crop-apply-btn');
const cropCancelBtn = document.getElementById('crop-cancel-btn');

// Modal Dialog Elements
const alertModal = document.getElementById('alert-modal');
const alertTitle = document.getElementById('alert-title');
const alertMessage = document.getElementById('alert-message');
const alertOkBtn = document.getElementById('alert-ok-btn');

const confirmModal = document.getElementById('confirm-modal');
const confirmTitle = document.getElementById('confirm-title');
const confirmMessage = document.getElementById('confirm-message');
const confirmOkBtn = document.getElementById('confirm-ok-btn');
const confirmCancelBtn = document.getElementById('confirm-cancel-btn');

// Modal Dialog Functions
function showAlert(message, title = 'Information', callback = null) {
    alertTitle.textContent = title;
    alertMessage.textContent = message;

    // Set up the OK button event handler
    const okHandler = () => {
        alertModal.classList.remove('active');
        alertOkBtn.removeEventListener('click', okHandler);
        if (callback) callback(true);
    };

    alertOkBtn.addEventListener('click', okHandler);

    // Show the modal
    alertModal.classList.add('active');
}

async function showConfirm(message, title = 'Confirmation') {
    return new Promise((resolve, reject) => {
        confirmMessage.textContent = message;
        confirmTitle.textContent = title;

        // Set up the OK button event handler
        const okHandler = () => {
            confirmModal.classList.remove('active');
            confirmOkBtn.removeEventListener('click', okHandler);
            confirmCancelBtn.removeEventListener('click', cancelHandler);
            resolve();
        };

        // Set up the Cancel button event handler
        const cancelHandler = () => {
            confirmModal.classList.remove('active');
            confirmOkBtn.removeEventListener('click', okHandler);
            confirmCancelBtn.removeEventListener('click', cancelHandler);
            reject();
        };

        confirmOkBtn.addEventListener('click', okHandler);
        confirmCancelBtn.addEventListener('click', cancelHandler);

        // Show the modal
        confirmModal.classList.add('active');
    })

}

// Polling variables
let lastUpdateTimestamp = 0;
const POLLING_INTERVAL = 2000; // Poll every 2 seconds

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Request current state from server
    fetchCurrentState();

    // Start polling for updates
    startPolling();

    // Check WiFi status
    checkWifiStatus();

    // Add event listener for reset button
    resetDisplayBtn.addEventListener('click', resetDisplay);

    // Add event listener for file selection
    imageFilesInput.addEventListener('change', handleFileSelection);
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
        const response = await fetch('/api/current_state');
        const data = await response.json();

        // Update last timestamp
        lastUpdateTimestamp = data.timestamp;

        // Update UI
        updateGallery(data.images);
        updateSettings(data.settings);
    } catch (error) {
        console.error('Error fetching current state:', error);
    }
}

// Handle file selection
function handleFileSelection(e) {
    const files = e.target.files;

    if (files.length === 0) {
        imagePreviewContainer.style.display = 'none';
        uploadButton.disabled = true;
        return;
    }

    // Clear previous previews
    imagePreviewList.innerHTML = '';

    // Show preview container
    imagePreviewContainer.style.display = 'block';
    uploadButton.disabled = false;

    // Add each file to the preview
    Array.from(files).forEach((file, index) => {
        // Create a preview row
        const row = document.createElement('tr');
        row.dataset.index = index;

        // Get file name without extension for default name
        const fileName = file.name.replace(/\.[^/.]+$/, "");

        // Create a URL for the image preview
        const imageUrl = URL.createObjectURL(file);

        row.innerHTML = `
            <td><img src="${imageUrl}" alt="${file.name}" class="preview-image"></td>
            <td><input type="text" class="image-name-input" value="${fileName}" data-index="${index}"></td>
            <td class="image-preview-actions">
                <button type="button" class="icon-btn remove-image-btn" data-index="${index}">🚮</button>
            </td>
        `;

        imagePreviewList.appendChild(row);

        // Add event listener for remove button
        row.querySelector('.remove-image-btn').addEventListener('click', () => removeImagePreview(index));
    });
}

// Remove image from preview
function removeImagePreview(index) {
    const row = document.querySelector(`tr[data-index="${index}"]`);
    if (row) {
        row.remove();
    }

    // If no images left, hide preview container and disable upload button
    if (imagePreviewList.children.length === 0) {
        imagePreviewContainer.style.display = 'none';
        uploadButton.disabled = true;
        imageFilesInput.value = ''; // Clear file input
    }
}

function showBackdrop(text = "") {
    // Show backdrop loading screen
    backdropText.textContent = text;
    backdrop.classList.add('active');
}

function hideBackdrop() {
    backdropText.textContent = "";
    backdrop.classList.remove('active');
}

// Form submissions
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get all visible rows in the preview table
    const rows = imagePreviewList.querySelectorAll('tr');
    if (rows.length === 0) {
        showAlert('Please select at least one image to upload');
        return;
    }

    showBackdrop('Uploading images...');

    imagePreviewContainer.style.display = 'none';
    imagePreviewList.innerHTML = '';
    // Disable upload button and show loading spinner
    uploadButton.disabled = true;
    uploadButton.innerHTML = '<span class="spinner"></span> Uploading...';

    const formData = new FormData();
    const files = imageFilesInput.files;

    // Add each file and its name to the form data
    rows.forEach(row => {
        const index = parseInt(row.dataset.index);
        const file = files[index];
        const nameInput = row.querySelector('.image-name-input');
        // Use the input value or extract filename without extension as fallback
        const name = nameInput.value.trim() || file.name.replace(/\.[^/.]+$/, "");

        formData.append('files[]', file);
        formData.append('names[]', name);
    });

    try {
        const response = await fetch('/api/images', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to upload images');
        }

        // Reset form and preview
        uploadForm.reset();
        imagePreviewContainer.style.display = 'none';
        imagePreviewList.innerHTML = '';
        uploadButton.disabled = true;
        // Reset button text
        uploadButton.innerHTML = 'Upload Selected Images';

        hideBackdrop();

        showAlert('Images uploaded successfully', 'Success');
        fetchCurrentState();

    } catch (error) {
        // Reset button state on error
        uploadButton.disabled = false;
        uploadButton.innerHTML = 'Upload Selected Images';

        hideBackdrop();

        showAlert(`${error.message}`, 'Error');
    }
});

saveSettingsBtn.addEventListener('click', async () => {
    const settings = {
        screensaver: screensaverSelect.value || null
    };

    try {
        showBackdrop('Saving settings...');
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        hideBackdrop();

        if (!response.ok) {
            throw new Error('Failed to save settings');
        }

        showAlert('Settings saved successfully', 'Success');
        updatePreview(settings);

    } catch (error) {
        showAlert(`${error.message}`, 'Error');
    }
});

wifiForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const ssid = document.getElementById('wifi-ssid').value;
    const password = document.getElementById('wifi-password').value;

    try {
        showBackdrop('Setting up WiFi...');
        const response = await fetch('/api/wifi/configure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ssid, password})
        });
        hideBackdrop();

        const data = await response.json();

        if (data.success) {
            showAlert('WiFi configured successfully');
            setTimeout(checkWifiStatus, 5000); // Check status after 5 seconds
        } else {
            showAlert(`Failed to configure WiFi: ${data.message}`);
        }

    } catch (error) {
        showAlert(`Error: ${error.message}`);
    }
});

// Helper functions
async function checkWifiStatus() {
    try {
        const response = await fetch('/api/wifi/status');
        const data = await response.json();

        if (data.connected) {
            wifiStatus.innerHTML = `<span class="connected">Connected to: ${data.ssid}</span>`;
        } else {
            wifiStatus.innerHTML = `<span class="disconnected">Not connected to WiFi</span>`;
        }

    } catch (error) {
        wifiStatus.innerHTML = `<span class="disconnected">Error checking WiFi status</span>`;
    }
}

function updateGallery(images) {
    gallery.innerHTML = '';

    if (images.length === 0) {
        gallery.innerHTML = '<p>No images uploaded yet.</p>';
        return;
    }

    images.forEach(image => {
        addImageToGallery(image);
    });

    updateScreensaverOptions();
}

function addImageToGallery(image) {
    // Remove "No images uploaded yet" message if it exists
    const noImagesMessage = gallery.querySelector('p');
    if (noImagesMessage && noImagesMessage.textContent === 'No images uploaded yet.') {
        gallery.innerHTML = '';
    }

    const item = document.createElement('div');
    item.className = 'gallery-item';
    item.id = `image-${image.id}`;

    // Use thumbnail if available, otherwise use the original image
    const imagePath = image.thumb_path || image.path;

    item.innerHTML = `
        <div class="thumb-container">
        <img src="/img/crop_${imagePath}?t=${Date.now()}" alt="${image.name}" class="gallery-image" data-original-path="${image.path}" data-thumb-path="${imagePath}">
        </div>
        <div class="gallery-controls">
            <div class="gallery-title" data-id="${image.id}">${image.name}</div>
            <div class="gallery-buttons">
                <button class="icon-btn display-btn" data-id="${image.id}" title="Display Image">👁️</button>
                <button class="icon-btn rename-btn" data-id="${image.id}" title="Rename Image">🖊️</button>
                <button class="icon-btn crop-btn" data-id="${image.id}" title="Edit Image">✂️</button>
                <button class="icon-btn delete-btn" data-id="${image.id}" title="Delete Image">🚮</button>
            </div>
        </div>
    `;

    gallery.appendChild(item);

    // Add event listeners
    item.querySelector('.display-btn').addEventListener('click', () => displayImage(image.id));
    item.querySelector('.rename-btn').addEventListener('click', () => showRenameInput(image.id));
    item.querySelector('.crop-btn').addEventListener('click', () => openCropModal(image.id));
    item.querySelector('.delete-btn').addEventListener('click', () => deleteImage(image.id));

    // Add to screensaver options
    const option = document.createElement('option');
    option.value = image.id;
    option.textContent = image.name;
    screensaverSelect.appendChild(option);
}

// Show rename input for an image
function showRenameInput(imageId) {
    const titleElement = document.querySelector(`#image-${imageId} .gallery-title`);
    const currentName = titleElement.textContent;

    // Create input element
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'rename-input';
    input.value = currentName;

    // Replace title with input
    titleElement.innerHTML = '';
    titleElement.appendChild(input);

    // Focus the input
    input.focus();

    // Add event listeners for saving on enter or blur
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            saveImageName(imageId, input.value);
        } else if (e.key === 'Escape') {
            cancelRename(titleElement, currentName);
        }
    });

    input.addEventListener('blur', () => {
        saveImageName(imageId, input.value);
    });
}

// Save the new image name
async function saveImageName(imageId, newName) {
    if (!newName.trim()) {
        // Don't allow empty names
        const titleElement = document.querySelector(`#image-${imageId} .gallery-title`);
        titleElement.textContent = titleElement.dataset.originalName || 'Unnamed Image';
        return;
    }

    try {
        const response = await fetch(`/api/images/${imageId}/rename`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({name: newName})
        });

        if (!response.ok) {
            throw new Error('Failed to rename image');
        }

        // Update the title element
        const titleElement = document.querySelector(`#image-${imageId} .gallery-title`);
        titleElement.textContent = newName;

        // Update screensaver option
        const option = Array.from(screensaverSelect.options).find(opt => opt.value === imageId);
        if (option) {
            option.textContent = newName;
        }

    } catch (error) {
        showAlert(`Error: ${error.message}`);
        // Restore original name
        const titleElement = document.querySelector(`#image-${imageId} .gallery-title`);
        titleElement.textContent = titleElement.dataset.originalName || 'Unnamed Image';
    }
}

// Cancel rename operation
function cancelRename(titleElement, originalName) {
    titleElement.textContent = originalName;
}

function updateScreensaverOptions() {
    // Save current selection
    const currentValue = screensaverSelect.value;

    // Clear all options except the first one (None)
    while (screensaverSelect.options.length > 1) {
        screensaverSelect.remove(1);
    }

    // Add options from gallery
    document.querySelectorAll('.gallery-item').forEach(item => {
        const id = item.id.replace('image-', '');
        const title = item.querySelector('.gallery-title').textContent;

        const option = document.createElement('option');
        option.value = id;
        option.textContent = title;
        screensaverSelect.appendChild(option);
    });

    // Restore selection if possible
    if (currentValue) {
        screensaverSelect.value = currentValue;
    }
}

function updateSettings(settings) {
    // Update screensaver selection
    if (settings.screensaver) {
        screensaverSelect.value = settings.screensaver;
    } else {
        screensaverSelect.value = '';
    }

    // Highlight current display image
    document.querySelectorAll('.gallery-item').forEach(item => {
        item.classList.remove('active');
    });

    if (settings.current_image) {
        const item = document.getElementById(`image-${settings.current_image}`);
        if (item) {
            item.classList.add('active');
        }
    }

    // Update preview area
    updatePreview(settings);
}

function updatePreview(settings) {
    // Clear the canvas
    previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);

    if (settings.current_image) {
        // Find the image in the gallery
        const galleryImg = document.querySelector(`#image-${settings.current_image} img`);
        if (galleryImg) {
            // Use the original image path for the preview
            const thumb_path = galleryImg.dataset.thumbPath;
            const imgUrl = `/img/crop_${thumb_path}?t=${Date.now()}`;

            // Load the image and draw it on the canvas
            const img = new Image();
            img.onload = function () {
                drawImageContain(previewCtx, img, previewCanvas.width, previewCanvas.height);
            };
            img.src = imgUrl;

            previewStatus.textContent = `Currently displaying: ${galleryImg.alt}`;
        } else {
            previewStatus.textContent = 'Error: Selected image not found in gallery.';
        }
    } else if (settings.screensaver) {
        // Find the screensaver image
        const screensaverOption = Array.from(screensaverSelect.options).find(opt => opt.value === settings.screensaver);
        const screensaverName = screensaverOption ? screensaverOption.textContent : 'Unknown';

        // Find the image in the gallery
        const galleryImg = document.querySelector(`#image-${settings.screensaver} img`);
        if (galleryImg) {
            // Use the original image path for the preview
            const thumb_path = galleryImg.dataset.thumbPath;
            const imgUrl = `/img/crop_${thumb_path}?t=${Date.now()}`;

            // Load the image and draw it on the canvas
            const img = new Image();
            img.onload = function () {
                drawImageContain(previewCtx, img, previewCanvas.width, previewCanvas.height);
            };
            img.src = imgUrl;

            previewStatus.textContent = `Showing screensaver: ${screensaverName}`;
        } else {
            previewStatus.textContent = 'Error: Screensaver image not found in gallery.';
        }
    } else {
        // No image is displayed
        previewStatus.textContent = 'No image is currently displayed.';
    }
}

async function displayImage(imageId) {
    try {
        const response = await fetch('/api/display', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({image_id: imageId})
        });
        fetchCurrentState()


        if (!response.ok) {
            throw new Error('Failed to display image');
        }

    } catch (error) {
        showAlert(`Error: ${error.message}`);
    }
}

async function deleteImage(imageId) {
    try {
        await showConfirm('Are you sure you want to delete this image?', 'Delete Image')

        try {
            const response = await fetch(`/api/images/${imageId}`, {
                method: 'DELETE'
            });
            fetchCurrentState();

            if (!response.ok) {
                throw new Error('Failed to delete image');
            }

        } catch (error) {
            showAlert(`Error: ${error.message}`);
        }
    } catch (err) {

    }
}

async function resetDisplay() {
    try {
        const response = await fetch('/api/display/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        fetchCurrentState();

        if (!response.ok) {
            throw new Error('Failed to reset display');
        }


    } catch (error) {
        showAlert(`Error: ${error.message}`);
    }
}

// Crop Modal Variables
let currentCropImageId = null;
let currentImageData = null;
let currentImageElement = null; // Holds the Image object for the current crop preview
let cropDragging = false;
let cropResizing = false;
let currentResizeHandle = null;
let cropStartX = 0;
let cropStartY = 0;
let cropSelectionX = 0;
let cropSelectionY = 0;
let cropSelectionWidth = 0;
let cropSelectionHeight = 0;
let currentRotation = 0;
const ASPECT_RATIO = 16 / 9; // 16:9 aspect ratio

// Open the crop modal for an image
async function openCropModal(imageId) {
    try {
        // Get the image data from the database
        const response = await fetch('/api/current_state');
        const data = await response.json();

        // Find the image
        currentImageData = data.images.find(img => img.id === imageId);
        if (!currentImageData) {
            throw new Error('Image not found');
        }

        // Show the modal
        cropModal.classList.add('active');

        setTimeout(() => {
            cropPreviewContainer.style.width = '95%';
            cropPreviewContainer.style.aspectRatio = '16/9';
            cropPreviewContainer.style.height = ((cropPreviewContainer.clientWidth / 16)*9) + 'px';

            // Set up event listeners for crop selection dragging
            setupCropDragListeners();
        }, 10);

        currentCropImageId = imageId;

        // Load the image into the crop preview
        const imgUrl = `/img/${currentImageData.path}?t=${Date.now()}`;

        // Create a new Image object
        currentImageElement = new Image();

        // Wait for image to load to get its dimensions
        currentImageElement.onload = () => {
            const containerRect = cropPreviewContainer.getBoundingClientRect();

            // Set initial crop selection based on stored values or defaults
            if (currentImageData.crop) {
                const scale = containerRect.width / 1920;
                cropSelectionWidth = currentImageData.crop.w * scale;
                currentImageData.crop.h = Math.round(currentImageData.crop.w / ASPECT_RATIO);
                cropSelectionHeight = currentImageData.crop.h * scale;
                cropSelectionX = currentImageData.crop.x * scale;
                cropSelectionY = currentImageData.crop.y * scale;
            } else {
                // Default to full preview with 16:9 aspect ratio (1920x1080)
                // Calculate the size to fit the container
                cropSelectionWidth = containerRect.width;
                cropSelectionHeight = containerRect.height;
                cropSelectionX = 0;
                cropSelectionY = 0;
            }

            cropSelection.style.width = `${cropSelectionWidth}px`;
            cropSelection.style.height = `${cropSelectionHeight}px`;
            // Position the crop selection
            cropSelection.style.left = `${cropSelectionX}px`;
            cropSelection.style.top = `${cropSelectionY}px`;

            // Draw the image on the canvas with transformations
            drawImageContain(cropPreviewCtx, currentImageElement, cropPreviewCanvas.width, cropPreviewCanvas.height);

            // Apply transformations to the preview image
            applyPreviewTransformations();
        };

        // Set the image source to start loading
        currentImageElement.src = imgUrl;

        // Set mirror checkboxes based on stored values
        if (currentImageData.mirror) {
            mirrorHCheckbox.checked = currentImageData.mirror.h;
            mirrorVCheckbox.checked = currentImageData.mirror.v;
        } else {
            mirrorHCheckbox.checked = false;
            mirrorVCheckbox.checked = false;
        }

        // Set rotation based on stored value
        currentRotation = currentImageData.rotate || 0;



    } catch (error) {
        showAlert(`Error: ${error.message}`);
    }
}

// Apply transformations to the preview image
function applyPreviewTransformations() {
    // Clear the canvas
    cropPreviewCtx.clearRect(0, 0, cropPreviewCanvas.width, cropPreviewCanvas.height);

    // If no image is loaded yet, return
    if (!currentImageElement) return;

    // Apply rotation button highlighting
    rotate_0.classList.remove('active');
    rotate_90.classList.remove('active');
    rotate_180.classList.remove('active');
    rotate_270.classList.remove('active');
    let flip_wh = false
    if (currentRotation === 90) {
        rotate_90.classList.add('active');
        flip_wh = true;
    } else if (currentRotation === 180) {
        rotate_180.classList.add('active');
    } else if (currentRotation === 270) {
        rotate_270.classList.add('active');
        flip_wh = true;
    } else {
        rotate_0.classList.add('active');
    }

    // Save the canvas state
    cropPreviewCtx.save();

    // Move to the center of the canvas
    cropPreviewCtx.translate(cropPreviewCanvas.width / 2, cropPreviewCanvas.height / 2);

    // Apply rotation
    cropPreviewCtx.rotate(currentRotation * Math.PI / 180);

    // Apply mirroring
    const scaleX = mirrorHCheckbox.checked ? -1 : 1;
    const scaleY = mirrorVCheckbox.checked ? -1 : 1;
    cropPreviewCtx.scale(scaleX, scaleY);

    // Draw the image centered
    let drawWidth, drawHeight, offsetX, offsetY;

    let imgAspect = currentImageElement.naturalWidth / currentImageElement.naturalHeight;
    if (flip_wh) {
        imgAspect = 1 / imgAspect;
    }
    const canvasAspect = cropPreviewCanvas.width / cropPreviewCanvas.height;
    const canvasWidth = cropPreviewCanvas.width;
    const canvasHeight = cropPreviewCanvas.height;

    if (imgAspect > canvasAspect) {
        // Image is wider than canvas (relative to height)
        drawWidth = canvasWidth;
        drawHeight = drawWidth / imgAspect;
        if(flip_wh){
            ([drawHeight, drawWidth] = [drawWidth, drawHeight]);
        }
        offsetX = 0;
        offsetY = (canvasHeight - drawHeight) / 2;
    } else {
        // Image is taller than canvas (relative to width)
        drawHeight = canvasHeight;
        drawWidth = drawHeight * imgAspect;
        if(flip_wh){
            ([drawHeight, drawWidth] = [drawWidth, drawHeight]);
        }
        offsetX = (canvasWidth - drawWidth) / 2;
        offsetY = 0;
    }


    cropPreviewCtx.drawImage(
        currentImageElement,
        -drawWidth / 2,
        -drawHeight / 2,
        drawWidth,
        drawHeight
    );

    // Restore the canvas state
    cropPreviewCtx.restore();
}

// Set up event listeners for crop selection dragging and resizing
function setupCropDragListeners() {
    // Mouse down on crop selection (for dragging)
    cropSelection.addEventListener('mousedown', (e) => {
        // Ignore if clicked on a resize handle
        if (e.target.classList.contains('resize-handle')) return;

        cropDragging = true;
        cropStartX = e.clientX - cropSelectionX;
        cropStartY = e.clientY - cropSelectionY;
        e.preventDefault();
    });

    // Mouse down on resize handles
    const resizeHandles = cropSelection.querySelectorAll('.resize-handle');
    resizeHandles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            cropResizing = true;
            currentResizeHandle = e.target.classList[1]; // Get the position class (top-left, etc.)
            cropStartX = e.clientX;
            cropStartY = e.clientY;
            e.preventDefault();
            e.stopPropagation(); // Prevent dragging from starting
        });
    });

    // Mouse move (drag or resize)
    document.addEventListener('mousemove', (e) => {
        // Handle dragging
        if (cropDragging) {
            // Calculate new position
            let newX = e.clientX - cropStartX;
            let newY = e.clientY - cropStartY;

            // Get container dimensions
            const containerRect = cropPreviewContainer.getBoundingClientRect();

            // Constrain to container
            // newX = Math.max(0, Math.min(newX, containerRect.width - cropSelectionWidth));
            // newY = Math.max(0, Math.min(newY, containerRect.height - cropSelectionHeight));

            // Update position
            cropSelectionX = newX;
            cropSelectionY = newY;
            cropSelection.style.left = `${newX}px`;
            cropSelection.style.top = `${newY}px`;
        }

        // Handle resizing
        if (cropResizing) {
            const containerRect = cropPreviewContainer.getBoundingClientRect();
            const deltaX = e.clientX - cropStartX;
            const deltaY = e.clientY - cropStartY;

            // Calculate new dimensions based on which handle is being dragged
            let newWidth = cropSelectionWidth;
            let newHeight = cropSelectionHeight;
            let newX = cropSelectionX;
            let newY = cropSelectionY;

            // Determine resize direction and calculate new dimensions
            if (currentResizeHandle === 'top-left') {
                // Resize from top-left corner
                newWidth = cropSelectionWidth - deltaX;
                newHeight = newWidth / ASPECT_RATIO;
                newX = cropSelectionX + deltaX;
                newY = cropSelectionY + (cropSelectionHeight - newHeight);
            } else if (currentResizeHandle === 'top-right') {
                // Resize from top-right corner
                newWidth = cropSelectionWidth + deltaX;
                newHeight = newWidth / ASPECT_RATIO;
                newY = cropSelectionY + (cropSelectionHeight - newHeight);
            } else if (currentResizeHandle === 'bottom-left') {
                // Resize from bottom-left corner
                newWidth = cropSelectionWidth - deltaX;
                newHeight = newWidth / ASPECT_RATIO;
                newX = cropSelectionX + deltaX;
            } else if (currentResizeHandle === 'bottom-right') {
                // Resize from bottom-right corner
                newWidth = cropSelectionWidth + deltaX;
                newHeight = newWidth / ASPECT_RATIO;
            }

            // Enforce minimum size (100px width)
            if (newWidth < 50) {
                newWidth = 50;
                newHeight = newWidth / ASPECT_RATIO;

                // Adjust position if resizing from left or top
                if (currentResizeHandle.includes('left')) {
                    newX = cropSelectionX + cropSelectionWidth - newWidth;
                }
                if (currentResizeHandle.includes('top')) {
                    newY = cropSelectionY + cropSelectionHeight - newHeight;
                }
            }

            // Update crop selection
            cropSelectionWidth = newWidth;
            cropSelectionHeight = newHeight;
            cropSelectionX = newX;
            cropSelectionY = newY;

            cropSelection.style.width = `${newWidth}px`;
            cropSelection.style.height = `${newHeight}px`;
            cropSelection.style.left = `${newX}px`;
            cropSelection.style.top = `${newY}px`;

            // Update start position for next move
            cropStartX = e.clientX;
            cropStartY = e.clientY;
        }
    });

    // Mouse up (end drag or resize)
    document.addEventListener('mouseup', () => {
        cropDragging = false;
        cropResizing = false;
        currentResizeHandle = null;
    });

    // Rotation buttons
    rotate_0.addEventListener('click', () => {
        currentRotation = 0;
        applyPreviewTransformations();
    });
    rotate_90.addEventListener('click', () => {
        currentRotation = 90;
        applyPreviewTransformations();
    });
    rotate_180.addEventListener('click', () => {
        currentRotation = 180;
        applyPreviewTransformations();
    });
    rotate_270.addEventListener('click', () => {
        currentRotation = 270;
        applyPreviewTransformations();
    });

    // Mirror checkboxes
    mirrorHCheckbox.addEventListener('change', applyPreviewTransformations);
    mirrorVCheckbox.addEventListener('change', applyPreviewTransformations);

    // Reset crop button
    const resetCropBtn = document.getElementById('reset-crop-btn');
    const centerCropBtn = document.getElementById('set-center-btn');
    const centerHCropBtn = document.getElementById('set-center-h-btn');
    const centerVCropBtn = document.getElementById('set-center-v-btn');
    const fillCropBtn = document.getElementById('crop-fill-btn');

    fillCropBtn.addEventListener('click', () => {
        const containerRect = cropPreviewContainer.getBoundingClientRect();

        // Use the canvas dimensions instead of image rect
        const canvasRect = cropPreviewCanvas.getBoundingClientRect();

        // Calculate the dimensions of the image as drawn on the canvas
        const flip_wh = currentRotation === 90 || currentRotation === 270;
        const imgWidth = flip_wh ? currentImageElement.height : currentImageElement.width;
        const imgHeight = flip_wh ? currentImageElement.width : currentImageElement.height;
        let imgAspect = imgWidth / imgHeight;
        const canvasAspect = canvasRect.width / canvasRect.height;

        let drawWidth, drawHeight;

        if (imgAspect > canvasAspect) {
            // Image is wider than canvas (relative to height)
            drawWidth = canvasRect.width;
            drawHeight = drawWidth / imgAspect;
        } else {
            // Image is taller than canvas (relative to width)
            drawHeight = canvasRect.height;
            drawWidth = drawHeight * imgAspect;
        }

        // Set crop selection to match the image size with 16:9 aspect ratio
        cropSelectionWidth = drawWidth;
        cropSelectionHeight = cropSelectionWidth / ASPECT_RATIO;
        if (cropSelectionHeight > drawHeight) {
            cropSelectionHeight = drawHeight;
            cropSelectionWidth = cropSelectionHeight * ASPECT_RATIO;
        }
        if (cropSelectionWidth > drawWidth) {
            cropSelectionWidth = drawWidth;
            cropSelectionHeight = cropSelectionWidth / ASPECT_RATIO;
        }

        cropSelectionX = (containerRect.width - cropSelectionWidth) / 2;
        cropSelectionY = (containerRect.height - cropSelectionHeight) / 2;

        console.log('current image size', currentImageElement.width, currentImageElement.height);
        console.log('canvas size', canvasRect.width, canvasRect.height);
        console.log('draw image size', drawWidth, drawHeight);
        console.log('crop selection for contain', cropSelectionX, cropSelectionY, cropSelectionWidth, cropSelectionHeight);

        cropSelection.style.left = `${cropSelectionX}px`;
        cropSelection.style.top = `${cropSelectionY}px`;
        cropSelection.style.width = `${cropSelectionWidth}px`;
        cropSelection.style.height = `${cropSelectionHeight}px`;
    })

    centerCropBtn.addEventListener('click', () => {
        const containerRect = cropPreviewContainer.getBoundingClientRect();
        // Center the crop selection
        cropSelectionX = (containerRect.width - cropSelectionWidth) / 2;
        cropSelectionY = (containerRect.height - cropSelectionHeight) / 2;

        cropSelection.style.left = `${cropSelectionX}px`;
        cropSelection.style.top = `${cropSelectionY}px`;
    });

    centerHCropBtn.addEventListener('click', () => {
        const containerRect = cropPreviewContainer.getBoundingClientRect();
        // Center the crop selection
        cropSelectionX = (containerRect.width - cropSelectionWidth) / 2;

        cropSelection.style.left = `${cropSelectionX}px`;
    });

    centerVCropBtn.addEventListener('click', () => {
        const containerRect = cropPreviewContainer.getBoundingClientRect();
        // Center the crop selection
        cropSelectionY = (containerRect.height - cropSelectionHeight) / 2;

        cropSelection.style.top = `${cropSelectionY}px`;
    });

    resetCropBtn.addEventListener('click', () => {
        // Get container dimensions
        const containerRect = cropPreviewContainer.getBoundingClientRect();
        cropSelectionWidth = containerRect.width;
        cropSelectionHeight = containerRect.height;

        // Center the crop selection
        cropSelectionX = 0;
        cropSelectionY = 0;

        // Update the crop selection element
        cropSelection.style.width = `${cropSelectionWidth}px`;
        cropSelection.style.height = `${cropSelectionHeight}px`;
        cropSelection.style.left = `${cropSelectionX}px`;
        cropSelection.style.top = `${cropSelectionY}px`;
    });

    // Cancel button
    cropCancelBtn.addEventListener('click', () => {
        cropModal.classList.remove('active');
        // Remove event listeners
        document.removeEventListener('mousemove', null);
        document.removeEventListener('mouseup', null);
    });

    // Apply button
    cropApplyBtn.addEventListener('click', saveCropSettings);
}

// Save crop settings
async function saveCropSettings() {
    try {
        // Get crop dimensions
        const containerRect = cropPreviewContainer.getBoundingClientRect();
        const cropWidth = 1920 * (cropSelectionWidth / containerRect.width);
        const x = 1920 * (cropSelectionX / containerRect.width);
        const y = 1080 * (cropSelectionY / containerRect.height);

        // Prepare transformation data
        const transformData = {
            rotate: currentRotation,
            mirror: {
                h: mirrorHCheckbox.checked,
                v: mirrorVCheckbox.checked
            },
            crop: {
                w: Math.round(cropWidth),
                x: Math.round(x),
                y: Math.round(y)
            }
        };

        // Send to server
        const response = await fetch(`/api/images/${currentCropImageId}/transform`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(transformData)
        });

        if (!response.ok) {
            throw new Error('Failed to save transformation settings');
        }

        // Close modal and refresh
        cropModal.classList.remove('active');
        fetchCurrentState();

    } catch (error) {
        showAlert(`Error: ${error.message}`);
    }
}