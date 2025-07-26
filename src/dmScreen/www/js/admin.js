// Connect to WebSocket server
const socket = io();

// DOM Elements
const uploadForm = document.getElementById('upload-form');
const gallery = document.getElementById('gallery');
const screensaverSelect = document.getElementById('screensaver');
const saveSettingsBtn = document.getElementById('save-settings');
const wifiStatus = document.getElementById('wifi-status');
const wifiForm = document.getElementById('wifi-form');
const previewImage = document.getElementById('preview-image');
const previewStatus = document.getElementById('preview-status');
const resetDisplayBtn = document.getElementById('reset-display');
const imageFilesInput = document.getElementById('image-files');
const imagePreviewContainer = document.getElementById('image-preview-container');
const imagePreviewList = document.getElementById('image-preview-list');
const uploadButton = document.getElementById('upload-button');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Request current state from server
    socket.emit('request_current_state');
    
    // Check WiFi status
    checkWifiStatus();
    
    // Add event listener for reset button
    resetDisplayBtn.addEventListener('click', resetDisplay);
    
    // Add event listener for file selection
    imageFilesInput.addEventListener('change', handleFileSelection);
});

// Socket events
socket.on('current_state', (data) => {
    updateGallery(data.images);
    updateSettings(data.settings);
});

socket.on('image_added', (image) => {
    addImageToGallery(image);
    updateScreensaverOptions();
});

socket.on('image_deleted', (data) => {
    removeImageFromGallery(data.id);
    updateScreensaverOptions();
});

socket.on('image_updated', (data) => {
    // Refresh the image by adding a timestamp to the URL
    const imgElement = document.querySelector(`#image-${data.id} img`);
    if (imgElement) {
        const currentSrc = imgElement.src;
        imgElement.src = `${currentSrc.split('?')[0]}?t=${Date.now()}`;
        
        // Request current state to update the preview
        socket.emit('request_current_state');
    }
});

socket.on('settings_updated', (settings) => {
    updateSettings(settings);
});

socket.on('display_changed', (data) => {
    // Highlight the currently displayed image
    document.querySelectorAll('.gallery-item').forEach(item => {
        item.classList.remove('active');
    });
    
    if (data.image_id) {
        const item = document.getElementById(`image-${data.image_id}`);
        if (item) {
            item.classList.add('active');
        }
    }
});

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

// Form submissions
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Get all visible rows in the preview table
    const rows = imagePreviewList.querySelectorAll('tr');
    if (rows.length === 0) {
        alert('Please select at least one image to upload');
        return;
    }
    
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
        
        alert('Images uploaded successfully');
        
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
});

saveSettingsBtn.addEventListener('click', async () => {
    const settings = {
        screensaver: screensaverSelect.value || null
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        
        if (!response.ok) {
            throw new Error('Failed to save settings');
        }
        
        alert('Settings saved successfully');
        updatePreview(settings);
        
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
});

wifiForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const ssid = document.getElementById('wifi-ssid').value;
    const password = document.getElementById('wifi-password').value;
    
    try {
        const response = await fetch('/api/wifi/configure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ ssid, password })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('WiFi configured successfully');
            setTimeout(checkWifiStatus, 5000); // Check status after 5 seconds
        } else {
            alert(`Failed to configure WiFi: ${data.message}`);
        }
        
    } catch (error) {
        alert(`Error: ${error.message}`);
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
    const item = document.createElement('div');
    item.className = 'gallery-item';
    item.id = `image-${image.id}`;
    
    // Use thumbnail if available, otherwise use the original image
    const imagePath = image.thumb_path || image.path;
    
    item.innerHTML = `
        <img src="/img/${imagePath}?t=${Date.now()}" alt="${image.name}" class="gallery-image" data-original-path="${image.path}">
        <div class="gallery-controls">
            <div class="gallery-title" data-id="${image.id}">${image.name}</div>
            <div class="gallery-buttons">
                <button class="icon-btn display-btn" data-id="${image.id}" title="Display Image">👁️</button>
                <button class="icon-btn rename-btn" data-id="${image.id}" title="Rename Image">🖊️</button>
                <button class="icon-btn rotate-btn" data-id="${image.id}" title="Rotate Image">🔃</button>
                <button class="icon-btn delete-btn" data-id="${image.id}" title="Delete Image">🚮</button>
            </div>
        </div>
    `;
    
    gallery.appendChild(item);
    
    // Add event listeners
    item.querySelector('.display-btn').addEventListener('click', () => displayImage(image.id));
    item.querySelector('.rename-btn').addEventListener('click', () => showRenameInput(image.id));
    item.querySelector('.rotate-btn').addEventListener('click', () => rotateImage(image.id));
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
            body: JSON.stringify({ name: newName })
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
        alert(`Error: ${error.message}`);
        // Restore original name
        const titleElement = document.querySelector(`#image-${imageId} .gallery-title`);
        titleElement.textContent = titleElement.dataset.originalName || 'Unnamed Image';
    }
}

// Cancel rename operation
function cancelRename(titleElement, originalName) {
    titleElement.textContent = originalName;
}

function removeImageFromGallery(imageId) {
    const item = document.getElementById(`image-${imageId}`);
    if (item) {
        item.remove();
    }
    
    // Remove from screensaver options
    const option = Array.from(screensaverSelect.options).find(opt => opt.value === imageId);
    if (option) {
        option.remove();
    }
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
    if (settings.current_image) {
        // Find the image in the gallery
        const image = document.querySelector(`#image-${settings.current_image} img`);
        if (image) {
            console.log(image);
            // Use the original image path for the preview
            const originalPath = image.dataset.originalPath;
            previewImage.src = `/img/${originalPath}?t=${Date.now()}`;
            previewImage.alt = image.alt;
            previewImage.style.display = 'block';
            previewStatus.textContent = `Currently displaying: ${image.alt}`;
        } else {
            previewImage.src = '';
            previewImage.alt = 'Image not found';
            previewImage.style.display = 'none';
            previewStatus.textContent = 'Error: Selected image not found in gallery.';
        }
    } else if (settings.screensaver) {
        // Find the screensaver image
        const screensaverOption = Array.from(screensaverSelect.options).find(opt => opt.value === settings.screensaver);
        const screensaverName = screensaverOption ? screensaverOption.textContent : 'Unknown';
        
        // Find the image in the gallery
        const image = document.querySelector(`#image-${settings.screensaver} img`);
        if (image) {
            // Use the original image path for the preview
            const originalPath = image.dataset.originalPath;
            previewImage.src = `/img/${originalPath}?t=${Date.now()}`;
            previewImage.alt = image.alt;
            previewImage.style.display = 'block';
            previewStatus.textContent = `Showing screensaver: ${screensaverName}`;
        } else {
            previewImage.src = '';
            previewImage.alt = 'Screensaver not found';
            previewImage.style.display = 'none';
            previewStatus.textContent = 'Error: Screensaver image not found in gallery.';
        }
    } else {
        // No image is displayed
        previewImage.src = '';
        previewImage.alt = 'No image displayed';
        previewImage.style.display = 'none';
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
            body: JSON.stringify({ image_id: imageId })
        });
        
        if (!response.ok) {
            throw new Error('Failed to display image');
        }
        
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

async function rotateImage(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/rotate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ angle: 90 })
        });
        
        if (!response.ok) {
            throw new Error('Failed to rotate image');
        }
        
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

async function deleteImage(imageId) {
    if (!confirm('Are you sure you want to delete this image?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/images/${imageId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error('Failed to delete image');
        }
        
    } catch (error) {
        alert(`Error: ${error.message}`);
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
        
        if (!response.ok) {
            throw new Error('Failed to reset display');
        }
        
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}