// DOM Elements
const uploadForm = document.getElementById('upload-form');
const gallery = document.getElementById('gallery');
const screensaverSelect = document.getElementById('screensaver');
const removeScreensaverBtn = document.getElementById('remove-screensaver');
const wifiStatus = document.getElementById('wifi-status');
const wifiForm = document.getElementById('wifi-form');
const wifiSSIDInput = document.getElementById('wifi-ssid');
const wifiPasswordInput = document.getElementById('wifi-password');
const wifiScanBtn = document.getElementById('wifi-scan-btn');
const wifiSSIDList = document.getElementById('wifi-ssid-list');
const wifiDisconnectBtn = document.getElementById('wifi-disconnect-btn');
const previewCanvas = document.getElementById('preview-canvas');
const previewStatus = document.getElementById('preview-status');
const resetDisplayBtn = document.getElementById('reset-display');
const imageFilesInput = document.getElementById('image-files');
const imagePreviewContainer = document.getElementById('image-preview-container');
const imagePreviewList = document.getElementById('image-preview-list');
const uploadButton = document.getElementById('upload-button');
const backdrop = document.getElementById('backdrop');
const backdropText = document.getElementById('backdrop-text');
const newFolderBtn = document.getElementById('new-folder-btn');
const folderSelect = document.getElementById('folder-select');

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
            resolve(true);
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

        // Add event listeners for Enter key
        const handleKeypress = (e) => {
            if (e.key === 'Enter') {
                if (document.activeElement === confirmOkBtn) {
                    okHandler();
                } else if (document.activeElement === confirmCancelBtn) {
                    cancelHandler();
                }
            }
        };

        confirmOkBtn.addEventListener('keypress', handleKeypress);
        confirmCancelBtn.addEventListener('keypress', handleKeypress);

        confirmOkBtn.focus();

        // Show the modal
        confirmModal.classList.add('active');
    })

}

// Polling variables
let lastUpdateTimestamp = 0;
const POLLING_INTERVAL = 2000; // Poll every 2 seconds

// Track previous network signature to detect changes
let _prevNetworkSignature = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {

    currentFolderId = localStorage.getItem('currentFolder');
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

    // Add event listeners for folder management
    newFolderBtn.addEventListener('click', showCreateFolderDialog);
    folderSelect.addEventListener('change', updateUploadFolder);
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

        // Detect network change signature
        const netSig = JSON.stringify({
            instance_id: data.instance_id || null,
            wifi_connected: data.wifi_connected || false,
            ssid: data.ssid || null,
            adhoc_active: data.adhoc_active || false,
            ip: data.ip || null
        });
        if (_prevNetworkSignature === null) {
            _prevNetworkSignature = netSig;
        } else if (_prevNetworkSignature !== netSig) {
            _prevNetworkSignature = netSig;
            // Network conditions changed: refresh WiFi status in admin area
            if (typeof checkWifiStatus === 'function') {
                try { checkWifiStatus(); } catch (_) {}
            }
        }

        // If AP/Adhoc is active, populate the SSID datalist for combo input
        if (data.adhoc_active && Array.isArray(data.scanned_ssids) && wifiSSIDList) {
            // Clear existing options
            if (wifiSSIDList.children.length === 0){
                const seen = new Set();
                data.scanned_ssids.forEach(ssid => {
                    const s = String(ssid || '').trim();
                    if (!s || seen.has(s)) return;
                    seen.add(s);
                    const opt = document.createElement('option');
                    opt.value = s;
                    wifiSSIDList.appendChild(opt);
                });
            }
        }

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

        // Store all folders for reference
        if (data.folders) {
            allFolders = data.folders;
            
            // Initialize folderPath if currentFolderId is set from localStorage
            if (currentFolderId && folderPath.length === 0) {
                // Build path from root to current folder
                const path = [];
                let currentFolder = allFolders.find(f => f.id === currentFolderId);

                while (currentFolder) {
                    path.unshift(currentFolder);
                    currentFolder = allFolders.find(f => f.id === currentFolder.parent);
                }

                folderPath = path;
            }
        }

        // Update UI
        updateGallery(data.images, data.folders);
        updateSettings(data.settings);
    } catch (error) {
        console.error('Error fetching current state:', error);
    }
}

// Folder navigation function
async function navigateToFolder(folderId) {
    currentFolderId = folderId;

    // Update folder path
    if (folderId === null) {
        // Root folder
        folderPath = [];
    } else {
        // Build path from root to current folder
        const path = [];
        let currentFolder = allFolders.find(f => f.id === folderId);

        while (currentFolder) {
            path.unshift(currentFolder);
            currentFolder = allFolders.find(f => f.id === currentFolder.parent);
        }

        folderPath = path;
    }
    if (folderId === null) {
        localStorage.removeItem('currentFolder');
    } else {
        localStorage.setItem('currentFolder', currentFolderId);
    }

    // Fetch current state to update the gallery
    await fetchCurrentState();
}

// Update folder path breadcrumb
function updateFolderPath() {
    const folderPathElement = document.getElementById('folder-path');
    folderPathElement.innerHTML = '';

    // Add root item
    const rootItem = document.createElement('span');
    rootItem.className = 'folder-path-item';
    rootItem.dataset.folderId = '';
    rootItem.textContent = '/';
    rootItem.addEventListener('click', () => navigateToFolder(null));
    folderPathElement.appendChild(rootItem);

    // Add path items
    folderPath.forEach((folder, index) => {
        // Add separator
        const separator = document.createElement('span');
        separator.className = 'folder-path-separator';
        separator.textContent = ' > ';
        folderPathElement.appendChild(separator);

        // Add folder item
        const folderItem = document.createElement('span');
        folderItem.className = 'folder-path-item';
        folderItem.dataset.folderId = folder.id;
        folderItem.textContent = folder.name;

        // Only add click event for parent folders, not the current folder
        const isCurrentFolder = index === folderPath.length - 1;
        if (!isCurrentFolder) {
            folderItem.addEventListener('click', () => navigateToFolder(folder.id));
            folderItem.style.cursor = 'pointer';
        } else {
            // Current folder is displayed as plain text
            folderItem.className = 'folder-path-item current-folder';
        }

        folderPathElement.appendChild(folderItem);
    });
}

// Update folder selection dropdown
function updateFolderSelect() {
    const folderSelect = document.getElementById('folder-select');
    folderSelect.innerHTML = '';

    // Add root option
    const rootOption = document.createElement('option');
    rootOption.value = '';
    rootOption.textContent = '/';
    folderSelect.appendChild(rootOption);

    // Build folder options with complete paths
    function addFolderOptions(parentId, level = 0) {
        const folders = allFolders
            .filter(f => f.parent === parentId)
            .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));

        folders.forEach(folder => {
            const option = document.createElement('option');
            option.value = folder.id;

            // Use the full path for the folder
            const fullPath = getFolderPath(folder.id);
            option.textContent = fullPath;

            // Select current folder if we're in one
            if (folder.id === currentFolderId) {
                option.selected = true;
            }

            folderSelect.appendChild(option);

            // Add child folders recursively
            addFolderOptions(folder.id, level + 1);
        });
    }

    addFolderOptions(null);
}

// Update upload folder when selection changes
function updateUploadFolder() {
    // This function is called when the folder selection dropdown changes
    // The selected folder will be sent with the upload form
    console.log('Upload folder changed to:', folderSelect.value);

    // If we're in a folder, set the folder select to that folder by default
    if (currentFolderId && !folderSelect.value) {
        folderSelect.value = currentFolderId;
    }
}

// Show dialog to create a new folder
async function showCreateFolderDialog() {
    const folderName = await showPrompt('Enter folder name:', 'New Folder');

    if (folderName && folderName.trim()) {
        createFolder(folderName.trim());
    }
}

// Create a new folder
async function createFolder(name) {
    try {
        showBackdrop('Creating folder...');

        const response = await fetch('/api/folders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                parent: currentFolderId
            })
        });

        if (!response.ok) {
            throw new Error('Failed to create folder');
        }

        hideBackdrop();

        // Refresh the gallery
        fetchCurrentState();
    } catch (error) {
        hideBackdrop();
        showAlert(`Error: ${error.message}`, 'Error');
    }
}

// Show rename folder input
function showRenameFolderInput(folderId) {
    const folderElement = document.querySelector(`#folder-${folderId} .folder-name`);
    const currentName = folderElement.textContent;

    // Create input element
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'rename-input';
    input.value = currentName;

    // Replace folder name with input
    folderElement.innerHTML = '';
    folderElement.appendChild(input);

    // Focus the input
    input.focus();

    // Add event listeners for saving on enter or blur
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            renameFolder(folderId, input.value);
        } else if (e.key === 'Escape') {
            folderElement.textContent = currentName;
        }
    });

    input.addEventListener('blur', () => {
        renameFolder(folderId, input.value);
    });
}

// Rename a folder
async function renameFolder(folderId, newName) {
    if (!newName.trim()) {
        // Don't allow empty names
        const folderElement = document.querySelector(`#folder-${folderId} .folder-name`);
        folderElement.textContent = folderElement.dataset.originalName || 'Unnamed Folder';
        return;
    }

    try {
        const response = await fetch(`/api/folders/${folderId}/rename`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({name: newName})
        });

        if (!response.ok) {
            throw new Error('Failed to rename folder');
        }

        // Update the folder name in the UI
        const folderElement = document.querySelector(`#folder-${folderId} .folder-name`);
        folderElement.textContent = newName;

        // Refresh the gallery to update all references
        fetchCurrentState();
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'Error');

        // Restore original name
        const folderElement = document.querySelector(`#folder-${folderId} .folder-name`);
        folderElement.textContent = folderElement.dataset.originalName || 'Unnamed Folder';
    }
}

// Delete a folder
async function deleteFolder(folderId) {
    const confirmed = await showConfirm('Are you sure you want to delete this folder? All contents will be moved to the parent folder.');

    if (!confirmed) {
        return;
    }

    try {
        showBackdrop('Deleting folder...');

        const response = await fetch(`/api/folders/${folderId}`, {
            method: 'DELETE'
        });

        hideBackdrop()
        if (!response.ok) {
            throw new Error('Failed to delete folder');
        }


        // Refresh the gallery
        fetchCurrentState();
    } catch (error) {
        hideBackdrop();
        showAlert(`Error: ${error.message}`, 'Error');
    }
}

// Show dialog to move a folder
async function showMoveFolderDialog(folderId) {
    // Create a modal dialog with folder selection
    const folderToMove = allFolders.find(f => f.id === folderId);

    if (!folderToMove) {
        showAlert('Folder not found', 'Error');
        return;
    }

    const modalContent = document.createElement('div');
    modalContent.innerHTML = `
        <h3>Move Folder: ${folderToMove.name}</h3>
        <p>Select destination folder:</p>
        <select id="move-destination-folder" class="folder-select">
            <option value="">/</option>
        </select>
    `;

    // Add folder options
    const selectElement = modalContent.querySelector('#move-destination-folder');

    function addFolderOptions(parentId, level = 0, excludeFolderId) {
        const folders = allFolders
            .filter(f => f.parent === parentId && f.id !== excludeFolderId)
            .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));

        folders.forEach(folder => {
            // Skip the folder being moved and its children
            if (folder.id === excludeFolderId || isChildFolder(folder.id, excludeFolderId)) {
                return;
            }

            const option = document.createElement('option');
            option.value = folder.id;

            // Use the full path for the folder
            const fullPath = getFolderPath(folder.id);
            option.textContent = fullPath;

            selectElement.appendChild(option);

            // Add child folders recursively
            addFolderOptions(folder.id, level + 1, excludeFolderId);
        });
    }

    // Check if a folder is a child of another folder
    function isChildFolder(folderId, parentId) {
        const folder = allFolders.find(f => f.id === folderId);
        if (!folder) return false;
        if (folder.parent === parentId) return true;
        if (folder.parent === null) return false;
        return isChildFolder(folder.parent, parentId);
    }

    addFolderOptions(null, 0, folderId);

    // Show the modal
    const result = await showCustomModal(modalContent, 'Move Folder');

    if (result) {
        const destinationFolderId = selectElement.value || null;
        moveFolder(folderId, destinationFolderId);
    }
}

// Move a folder
async function moveFolder(folderId, destinationFolderId) {
    try {
        showBackdrop('Moving folder...');

        const response = await fetch(`/api/folders/${folderId}/move`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({parent: destinationFolderId})
        });

        if (!response.ok) {
            throw new Error('Failed to move folder');
        }

        hideBackdrop();

        // Refresh the gallery
        fetchCurrentState();
    } catch (error) {
        hideBackdrop();
        showAlert(`Error: ${error.message}`, 'Error');
    }
}

// Show dialog to move an image
async function showMoveImageDialog(imageId) {
    // Create a modal dialog with folder selection
    const imageToMove = allImages.find(img => img.id === imageId);

    if (!imageToMove) {
        showAlert('Image not found', 'Error');
        return;
    }

    const modalContent = document.createElement('div');
    modalContent.innerHTML = `
        <h3>Move Image: ${imageToMove.name}</h3>
        <p>Select destination folder:</p>
        <select id="move-destination-folder" class="folder-select">
            <option value="">/</option>
        </select>
    `;

    // Add folder options
    const selectElement = modalContent.querySelector('#move-destination-folder');

    function addFolderOptions(parentId, level = 0) {
        const folders = allFolders
            .filter(f => f.parent === parentId)
            .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));

        folders.forEach(folder => {
            const option = document.createElement('option');
            option.value = folder.id;

            // Use the full path for the folder
            const fullPath = getFolderPath(folder.id);
            option.textContent = fullPath;

            selectElement.appendChild(option);

            // Add child folders recursively
            addFolderOptions(folder.id, level + 1);
        });
    }

    addFolderOptions(null);

    // Show the modal
    const result = await showCustomModal(modalContent, 'Move Image');

    if (result) {
        const destinationFolderId = selectElement.value || null;
        moveImage(imageId, destinationFolderId);
    }
}

// Move an image
async function moveImage(imageId, folderId) {
    try {
        showBackdrop('Moving image...');

        const response = await fetch(`/api/images/${imageId}/move`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({folder: folderId})
        });

        if (!response.ok) {
            throw new Error('Failed to move image');
        }

        hideBackdrop();

        // Refresh the gallery
        fetchCurrentState();
    } catch (error) {
        hideBackdrop();
        showAlert(`Error: ${error.message}`, 'Error');
    }
}

// Helper function to get the full path of a folder
function getFolderPath(folderId) {
    if (!folderId) return '/';

    const path = [];
    let currentFolder = allFolders.find(f => f.id === folderId);

    // Build path from current folder up to root
    while (currentFolder) {
        path.unshift(currentFolder.name);
        currentFolder = allFolders.find(f => f.id === currentFolder.parent);
    }

    return '/' + path.join('/');
}

// Helper function to show a custom modal with content
async function showCustomModal(content, title = 'Dialog') {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'backdrop active';

        modal.innerHTML = `
            <div class="backdrop-content modal-dialog">
                <div class="modal-header">
                    <h3>${title}</h3>
                </div>
                <div class="modal-body" id="custom-modal-body">
                </div>
                <div class="modal-footer">
                    <button id="custom-modal-cancel" class="btn">Cancel</button>
                    <button id="custom-modal-ok" class="btn">OK</button>
                </div>
            </div>
        `;

        // Add content to the modal body
        const modalBody = modal.querySelector('#custom-modal-body');
        if (typeof content === 'string') {
            modalBody.innerHTML = content;
        } else {
            modalBody.appendChild(content);
        }

        // Add event listeners
        const cancelBtn = modal.querySelector('#custom-modal-cancel');
        const okBtn = modal.querySelector('#custom-modal-ok');

        cancelBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve(false);
        });

        okBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve(true);
        });

        // Add to the document
        document.body.appendChild(modal);
    });
}

// Helper function to show a prompt dialog
async function showPrompt(message, defaultValue = '') {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'backdrop active';

        modal.innerHTML = `
            <div class="backdrop-content modal-dialog">
                <div class="modal-header">
                    <h3>Input Required</h3>
                </div>
                <div class="modal-body">
                    <p>${message}</p>
                    <input type="text" id="prompt-input" class="rename-input" value="${defaultValue}">
                </div>
                <div class="modal-footer">
                    <button id="prompt-cancel" class="btn">Cancel</button>
                    <button id="prompt-ok" class="btn">OK</button>
                </div>
            </div>
        `;

        // Add event listeners
        const input = modal.querySelector('#prompt-input');
        const cancelBtn = modal.querySelector('#prompt-cancel');
        const okBtn = modal.querySelector('#prompt-ok');

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                document.body.removeChild(modal);
                resolve(input.value);
            } else if (e.key === 'Escape') {
                document.body.removeChild(modal);
                resolve(null);
            }
        });

        cancelBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve(null);
        });

        okBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
            resolve(input.value);
        });

        // Add to the document and focus the input
        document.body.appendChild(modal);
        input.focus();
        input.select();
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

// WebP Konvertierungsfunktionen
function convertImageToWebP(file, quality = 0.8) {
    return new Promise((resolve, reject) => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const img = new Image();

        img.onload = function () {
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);

            // Konvertierung zu WebP
            canvas.toBlob((blob) => {
                if (blob) {
                    // Erstelle eine neue Datei mit WebP-Format
                    const webpFile = new File([blob], file.name.replace(/\.[^/.]+$/, '.webp'), {
                        type: 'image/webp',
                        lastModified: Date.now()
                    });
                    resolve(webpFile);
                } else {
                    reject(new Error('WebP-Konvertierung fehlgeschlagen'));
                }
            }, 'image/webp', quality);
        };

        img.onerror = () => reject(new Error('Fehler beim Laden des Bildes'));
        img.src = URL.createObjectURL(file);
    });
}

// Überprüfe WebP-Unterstützung des Browsers
function checkWebPSupport() {
    return new Promise((resolve) => {
        const webP = new Image();
        webP.onload = webP.onerror = function () {
            resolve(webP.height === 2);
        };
        webP.src = 'data:image/webp;base64,UklGRjoAAABXRUJQVlA4IC4AAACyAgCdASoCAAIALmk0mk0iIiIiIgBoSygABc6WWgAA/veff/0PP8bA//LwYAAA';
    });
}

// Batch-Konvertierung mehrerer Bilder
async function convertImagesToWebP(files, quality = 0.8, onProgress = null) {
    const supportedFormats = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp'];
    const convertedFiles = [];

    for (let i = 0; i < files.length; i++) {
        const file = files[i];

        if (onProgress) {
            onProgress(i + 1, files.length, file.name);
        }

        try {
            if (supportedFormats.includes(file.type) && file.type !== 'image/webp') {
                console.log(`Konvertiere ${file.name} zu WebP...`);
                const webpFile = await convertImageToWebP(file, quality);
                convertedFiles.push(webpFile);
            } else if (file.type === 'image/webp') {
                // Bereits WebP, keine Konvertierung nötig
                convertedFiles.push(file);
            } else {
                // Nicht unterstütztes Format, original beibehalten
                console.warn(`Format ${file.type} wird nicht für WebP-Konvertierung unterstützt`);
                convertedFiles.push(file);
            }
        } catch (error) {
            console.error(`Fehler bei der Konvertierung von ${file.name}:`, error);
            // Bei Fehler das Original verwenden
            convertedFiles.push(file);
        }
    }

    return convertedFiles;
}

// Modifizierte Upload-Funktion mit WebP-Konvertierung
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get all visible rows in the preview table
    const rows = imagePreviewList.querySelectorAll('tr');
    if (rows.length === 0) {
        showAlert('Bitte wählen Sie mindestens ein Bild zum Upload aus');
        return;
    }

    // WebP-Unterstützung prüfen
    const supportsWebP = await checkWebPSupport();
    if (!supportsWebP) {
        console.warn('Browser unterstützt WebP nicht vollständig, verwende Originalformate');
    }

    showBackdrop('Konvertiere Bilder zu WebP...');

    imagePreviewContainer.style.display = 'none';
    imagePreviewList.innerHTML = '';
    uploadButton.disabled = true;
    uploadButton.innerHTML = '<span class="spinner"></span> Konvertiere und lade hoch...';

    try {
        const files = Array.from(imageFilesInput.files);

        // Konvertiere Bilder zu WebP (falls unterstützt)
        let convertedFiles = files;
        if (supportsWebP) {
            convertedFiles = await convertImagesToWebP(files, 0.8, (current, total, fileName) => {
                showBackdrop(`Konvertiere Bild ${current}/${total}: ${fileName}`);
            });
        }

        showBackdrop('Lade Bilder hoch...');

        const formData = new FormData();

        // Add folder ID if selected
        if (folderSelect.value) {
            formData.append('folder', folderSelect.value);
        }

        // Add each converted file and its name to the form data
        rows.forEach((row, index) => {
            const rowIndex = parseInt(row.dataset.index);
            const file = convertedFiles[rowIndex];
            const nameInput = row.querySelector('.image-name-input');
            // Use the input value or extract filename without extension as fallback
            const name = nameInput.value.trim() || file.name.replace(/\.[^/.]+$/, "");

            formData.append('files[]', file);
            formData.append('names[]', name);
        });

        const response = await fetch('/api/images', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Fehler beim Upload der Bilder');
        }

        // Reset form and preview
        uploadForm.reset();
        imagePreviewContainer.style.display = 'none';
        imagePreviewList.innerHTML = '';
        uploadButton.disabled = true;
        uploadButton.innerHTML = 'Ausgewählte Bilder hochladen';

        hideBackdrop();

        const savedBytes = calculateSavedBytes(files, convertedFiles);
        showAlert('Bilder erfolgreich hochgeladen!', 'Erfolg');

        fetchCurrentState();

    } catch (error) {
        uploadButton.disabled = false;
        uploadButton.innerHTML = 'Ausgewählte Bilder hochladen';
        hideBackdrop();
        showAlert(`Fehler: ${error.message}`, 'Fehler');
    }
});

// Hilfsfunktionen
function calculateSavedBytes(originalFiles, convertedFiles) {
    let originalSize = 0;
    let convertedSize = 0;

    for (let i = 0; i < originalFiles.length; i++) {
        originalSize += originalFiles[i].size;
        convertedSize += convertedFiles[i].size;
    }

    return Math.max(0, originalSize - convertedSize);
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Erweiterte handleFileSelection-Funktion mit WebP-Vorschau
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

        // Bestimme ob das Bild zu WebP konvertiert wird
        const willConvert = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp'].includes(file.type);

        row.innerHTML = `
            <td><img src="${imageUrl}" alt="${file.name}" class="preview-image"></td>
            <td>
                <input type="text" class="image-name-input" value="${fileName}" data-index="${index}">
                <small class="format-info">${formatBytes(file.size)}</small>
            </td>
            <td class="image-preview-actions">
                <button type="button" class="icon-btn remove-image-btn" data-index="${index}">🚮</button>
            </td>
        `;

        imagePreviewList.appendChild(row);

        // Add event listener for remove button
        row.querySelector('.remove-image-btn').addEventListener('click', () => removeImagePreview(index));
    });
}

// Form submissions
//uploadForm.addEventListener('submit', async (e) => {
//    e.preventDefault();
//
//    // Get all visible rows in the preview table
//    const rows = imagePreviewList.querySelectorAll('tr');
//    if (rows.length === 0) {
//        showAlert('Please select at least one image to upload');
//        return;
//    }
//
//    showBackdrop('Uploading images...');
//
//    imagePreviewContainer.style.display = 'none';
//    imagePreviewList.innerHTML = '';
//    // Disable upload button and show loading spinner
//    uploadButton.disabled = true;
//    uploadButton.innerHTML = '<span class="spinner"></span> Uploading...';
//
//    const formData = new FormData();
//    const files = imageFilesInput.files;
//
//    // Add each file and its name to the form data
//    rows.forEach(row => {
//        const index = parseInt(row.dataset.index);
//        const file = files[index];
//        const nameInput = row.querySelector('.image-name-input');
//        // Use the input value or extract filename without extension as fallback
//        const name = nameInput.value.trim() || file.name.replace(/\.[^/.]+$/, "");
//
//        formData.append('files[]', file);
//        formData.append('names[]', name);
//    });
//
//    try {
//        const response = await fetch('/api/images', {
//            method: 'POST',
//            body: formData
//        });
//
//        if (!response.ok) {
//            throw new Error('Failed to upload images');
//        }
//
//        // Reset form and preview
//        uploadForm.reset();
//        imagePreviewContainer.style.display = 'none';
//        imagePreviewList.innerHTML = '';
//        uploadButton.disabled = true;
//        // Reset button text
//        uploadButton.innerHTML = 'Upload Selected Images';
//
//        hideBackdrop();
//
//        showAlert('Images uploaded successfully', 'Success');
//        fetchCurrentState();
//
//    } catch (error) {
//        // Reset button state on error
//        uploadButton.disabled = false;
//        uploadButton.innerHTML = 'Upload Selected Images';
//
//        hideBackdrop();
//
//        showAlert(`${error.message}`, 'Error');
//    }
//});

// Remove screensaver button
removeScreensaverBtn.addEventListener('click', async () => {
    // Clear the screensaver selection
    screensaverSelect.value = '';

    // Update the UI
    const screensaverImg = document.getElementById('screensaver-preview-img');
    const screensaverText = document.getElementById('screensaver-preview-text');

    screensaverText.textContent = 'No screensaver selected';
    screensaverText.style.display = 'block';
    screensaverImg.style.display = 'none';

    // Save the settings
    const settings = {
        screensaver: null
    };

    try {
        showBackdrop('Removing screensaver...');
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        hideBackdrop();

        if (!response.ok) {
            throw new Error('Failed to remove screensaver');
        }

        // Remove screensaver indicator from all gallery images
        document.querySelectorAll('.gallery-item .thumb-container').forEach(container => {
            container.classList.remove('screensaver-image');
        });

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
            showAlert(data.message || "Connected. The new IP address is shown on the device's screen. You can close this tab.");
            setTimeout(checkWifiStatus, 5000); // Check status after 5 seconds
        } else {
            showAlert(data.message ? `Failed to configure WiFi: ${data.message}` : 'Failed to configure WiFi');
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
            if (wifiForm) wifiForm.style.display = 'none';
            if (wifiDisconnectBtn) wifiDisconnectBtn.style.display = 'inline-block';
        } else {
            wifiStatus.innerHTML = `<span class="disconnected">Not connected to WiFi</span>`;
            if (wifiForm) wifiForm.style.display = 'block';
            if (wifiDisconnectBtn) wifiDisconnectBtn.style.display = 'none';
        }

    } catch (error) {
        wifiStatus.innerHTML = `<span class="disconnected">Error checking WiFi status</span>`;
        if (wifiForm) wifiForm.style.display = 'block';
        if (wifiDisconnectBtn) wifiDisconnectBtn.style.display = 'none';
    }
}

// Global variables for folder management
let currentFolderId = null;
let folderPath = [];
let allFolders = [];
let allImages = [];

function updateGallery(images, folders) {
    gallery.innerHTML = '';

    // Store all folders and images for reference
    if (folders) {
        allFolders = folders;
    }

    if (images) {
        allImages = images;
    }

    // Get folders for the current level
    const currentFolders = allFolders.filter(folder => folder.parent === currentFolderId);

    // Get images for the current folder
    const currentImages = allImages.filter(image => image.parent === currentFolderId);

    if (currentFolders.length === 0 && currentImages.length === 0) {
        gallery.innerHTML = '<p>This folder is empty.</p>';

        // Still update folder path and select even if folder is empty
        updateScreensaverOptions();
        updateFolderPath();
        updateFolderSelect();
        return;
    }

    // Sort folders alphabetically
    currentFolders.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));

    // Sort images alphabetically
    currentImages.sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));

    // Add folders first
    currentFolders.forEach(folder => {
        addFolderToGallery(folder);
    });

    // Then add images
    currentImages.forEach(image => {
        addImageToGallery(image);
    });

    updateScreensaverOptions();
    updateFolderPath();
    updateFolderSelect();
}

function addFolderToGallery(folder) {
    // Remove empty folder message if it exists
    const emptyMessage = gallery.querySelector('p');
    if (emptyMessage && emptyMessage.textContent === 'This folder is empty.') {
        gallery.innerHTML = '';
    }

    const item = document.createElement('div');
    item.className = 'folder-item';
    item.id = `folder-${folder.id}`;

    item.innerHTML = `
        <div class="folder-icon" data-id="${folder.id}">📁</div>
        <div class="folder-name">${folder.name}</div>
        <div class="folder-controls">
            <button class="icon-btn rename-folder-btn" data-id="${folder.id}" title="Rename Folder">🖊️</button>
            <button class="icon-btn move-folder-btn" data-id="${folder.id}" title="Move Folder">📦</button>
            <button class="icon-btn delete-folder-btn" data-id="${folder.id}" title="Delete Folder">🚮</button>
        </div>
    `;

    gallery.appendChild(item);

    // Add event listeners
    item.querySelector('.folder-icon').addEventListener('click', () => navigateToFolder(folder.id));
    item.querySelector('.rename-folder-btn').addEventListener('click', () => showRenameFolderInput(folder.id));
    item.querySelector('.move-folder-btn').addEventListener('click', () => showMoveFolderDialog(folder.id));
    item.querySelector('.delete-folder-btn').addEventListener('click', () => deleteFolder(folder.id));
}

function addImageToGallery(image) {
    // Remove empty folder message if it exists
    const emptyMessage = gallery.querySelector('p');
    if (emptyMessage && (emptyMessage.textContent === 'This folder is empty.' || emptyMessage.textContent === 'No images uploaded yet.')) {
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
                <button class="icon-btn screensaver-btn" data-id="${image.id}" title="Set as Screensaver">🖼️</button>
                <button class="icon-btn rename-btn" data-id="${image.id}" title="Rename Image">🖊️</button>
                <button class="icon-btn move-btn" data-id="${image.id}" title="Move Image">📦</button>
                <button class="icon-btn crop-btn" data-id="${image.id}" title="Edit Image">✂️</button>
                <button class="icon-btn delete-btn" data-id="${image.id}" title="Delete Image">🚮</button>
            </div>
        </div>
    `;

    gallery.appendChild(item);

    // Add event listeners
    item.querySelector('.display-btn').addEventListener('click', () => displayImage(image.id));
    item.querySelector('.screensaver-btn').addEventListener('click', () => setAsScreensaver(image.id));
    item.querySelector('.rename-btn').addEventListener('click', () => showRenameInput(image.id));
    item.querySelector('.move-btn').addEventListener('click', () => showMoveImageDialog(image.id));
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

        // Update screensaver preview
        const screensaverImg = document.getElementById('screensaver-preview-img');
        const screensaverText = document.getElementById('screensaver-preview-text');

        // Fetch the image URL from the server
        fetch(`/api/image/${settings.screensaver}/url?thumb=true&t=${Date.now()}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to fetch screensaver image URL');
                }
                return response.json();
            })
            .then(data => {
                const imgUrl = data.url;
                const imageName = data.name;
                
                screensaverImg.src = imgUrl;
                screensaverImg.alt = imageName;
                screensaverImg.style.display = 'block';
                screensaverText.style.display = 'none';
            })
            .catch(error => {
                console.error('Error fetching screensaver image URL:', error);
                // If image not found, show text
                screensaverText.textContent = 'Selected screensaver image not found';
                screensaverText.style.display = 'block';
                screensaverImg.style.display = 'none';
            });
    } else {
        screensaverSelect.value = '';

        // Show "No screensaver selected" text
        const screensaverImg = document.getElementById('screensaver-preview-img');
        const screensaverText = document.getElementById('screensaver-preview-text');

        screensaverText.textContent = 'No screensaver selected';
        screensaverText.style.display = 'block';
        screensaverImg.style.display = 'none';
    }

    // Highlight current display image
    document.querySelectorAll('.gallery-item').forEach(item => {
        item.classList.remove('active');

        // Remove screensaver indicator
        const thumbContainer = item.querySelector('.thumb-container');
        if (thumbContainer) {
            thumbContainer.classList.remove('screensaver-image');
        }
    });

    // Mark current screensaver image in gallery
    if (settings.screensaver) {
        const screensaverItem = document.getElementById(`image-${settings.screensaver}`);
        if (screensaverItem) {
            const thumbContainer = screensaverItem.querySelector('.thumb-container');
            if (thumbContainer) {
                thumbContainer.classList.add('screensaver-image');
            }
        }
    }

    if (settings.current_image) {
        const item = document.getElementById(`image-${settings.current_image}`);
        if (item) {
            item.classList.add('active');
        }
    }

    // Update preview area
    updatePreview(settings);
}

async function updatePreview(settings) {
    // Clear the canvas
    previewCtx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
    const w = previewCanvas.clientWidth;

    if (settings.current_image) {
        try {
            // Fetch the image URL from the server with cache-busting timestamp
            const response = await fetch(`/api/image/${settings.current_image}/url?w=${w}&t=${Date.now()}`);
            if (!response.ok) {
                throw new Error('Failed to fetch image URL');
            }
            
            const data = await response.json();
            const imgUrl = data.url;
            const imageName = data.name;

            // Load the image and draw it on the canvas
            const img = new Image();
            img.onload = function () {
                drawImageContain(previewCtx, img, previewCanvas.width, previewCanvas.height);
            };
            img.src = imgUrl;

            previewStatus.textContent = `Currently displaying: ${imageName}`;
        } catch (error) {
            console.error('Error fetching image URL:', error);
            previewStatus.textContent = 'Error loading preview';
        }
    } else if (settings.screensaver) {
        try {
            // Find the screensaver name from the select element
            const screensaverOption = Array.from(screensaverSelect.options).find(opt => opt.value === settings.screensaver);
            const screensaverName = screensaverOption ? screensaverOption.textContent : 'Unknown';
            
            // Fetch the image URL from the server with cache-busting timestamp
            const response = await fetch(`/api/image/${settings.screensaver}/url?w=${w}&t=${Date.now()}`);
            if (!response.ok) {
                throw new Error('Failed to fetch screensaver image URL');
            }
            
            const data = await response.json();
            const imgUrl = data.url;

            // Load the image and draw it on the canvas
            const img = new Image();
            img.onload = function () {
                drawImageContain(previewCtx, img, previewCanvas.width, previewCanvas.height);
            };
            img.src = imgUrl;

            previewStatus.textContent = `Showing screensaver: ${screensaverName}`;
        } catch (error) {
            console.error('Error fetching screensaver image URL:', error);
            previewStatus.textContent = 'Error loading screensaver preview';
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

// Set an image as the screensaver
async function setAsScreensaver(imageId) {
    // Find the image name for the confirmation dialog
    const imageElement = document.querySelector(`#image-${imageId} .gallery-title`);
    const imageName = imageElement ? imageElement.textContent : 'this image';

    // Show confirmation dialog
    const confirmed = await showConfirm(`Set "${imageName}" as the screensaver?`);

    if (!confirmed) {
        return;
    }

    try {
        showBackdrop('Setting screensaver...');

        // Update the hidden select element
        screensaverSelect.value = imageId;

        // Save the settings
        const settings = {
            screensaver: imageId
        };

        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        hideBackdrop();

        if (!response.ok) {
            throw new Error('Failed to set screensaver');
        }

        // Update the UI
        updateSettings(settings);

    } catch (error) {
        hideBackdrop();
        showAlert(`Error: ${error.message}`, 'Error');
    }
}

async function deleteImage(imageId) {
    try {
        const confirmed = await showConfirm('Are you sure you want to delete this image?', 'Delete Image');

        if (!confirmed) {
            return;
        }

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
        // Handle any unexpected errors
        console.error('Error in delete confirmation:', err);
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
        cropPreviewCtx.clearRect(0, 0, cropPreviewCanvas.width, cropPreviewCanvas.height);

        setTimeout(() => {
            cropPreviewContainer.style.width = '95%';
            cropPreviewContainer.style.aspectRatio = '16/9';
            cropPreviewContainer.style.height = ((cropPreviewContainer.clientWidth / 16) * 9) + 'px';

            // Set up event listeners for crop selection dragging
            setupCropDragListeners();

            currentCropImageId = imageId;

            // Load the image into the crop preview
            const imgUrl = `/img/${currentImageData.path}?t=${Date.now()}&w=${cropPreviewContainer.clientWidth}`;

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

        }, 10);


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
        if (flip_wh) {
            ([drawHeight, drawWidth] = [drawWidth, drawHeight]);
        }
        offsetX = 0;
        offsetY = (canvasHeight - drawHeight) / 2;
    } else {
        // Image is taller than canvas (relative to width)
        drawHeight = canvasHeight;
        drawWidth = drawHeight * imgAspect;
        if (flip_wh) {
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
    // Helper function to get position from mouse or touch event
    function getEventPosition(e) {
        // For touch events, use the first touch point
        if (e.touches && e.touches.length > 0) {
            return {
                clientX: e.touches[0].clientX,
                clientY: e.touches[0].clientY
            };
        }
        // For mouse events
        return {
            clientX: e.clientX,
            clientY: e.clientY
        };
    }

    // Mouse/Touch down on crop selection (for dragging)
    function handleDragStart(e) {
        // Ignore if clicked on a resize handle
        if (e.target.classList.contains('resize-handle')) return;

        const pos = getEventPosition(e);
        cropDragging = true;
        cropStartX = pos.clientX - cropSelectionX;
        cropStartY = pos.clientY - cropSelectionY;
        e.preventDefault();
    }

    cropSelection.addEventListener('mousedown', handleDragStart);
    cropSelection.addEventListener('touchstart', handleDragStart, {passive: false});

    // Mouse/Touch down on resize handles
    const resizeHandles = cropSelection.querySelectorAll('.resize-handle');
    resizeHandles.forEach(handle => {
        function handleResizeStart(e) {
            const pos = getEventPosition(e);
            cropResizing = true;
            currentResizeHandle = e.target.classList[1]; // Get the position class (top-left, etc.)
            cropStartX = pos.clientX;
            cropStartY = pos.clientY;
            e.preventDefault();
            e.stopPropagation(); // Prevent dragging from starting
        }

        handle.addEventListener('mousedown', handleResizeStart);
        handle.addEventListener('touchstart', handleResizeStart, {passive: false});
    });

    // Mouse/Touch move (drag or resize)
    function handleMove(e) {
        const pos = getEventPosition(e);

        // Handle dragging
        if (cropDragging) {
            // Calculate new position
            let newX = pos.clientX - cropStartX;
            let newY = pos.clientY - cropStartY;

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
            const deltaX = pos.clientX - cropStartX;
            const deltaY = pos.clientY - cropStartY;

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
            cropStartX = pos.clientX;
            cropStartY = pos.clientY;
        }
    }

    document.addEventListener('mousemove', handleMove);
    document.addEventListener('touchmove', handleMove, {passive: false});

    // Mouse/Touch up (end drag or resize)
    function handleEnd() {
        cropDragging = false;
        cropResizing = false;
        currentResizeHandle = null;
    }

    document.addEventListener('mouseup', handleEnd);
    document.addEventListener('touchend', handleEnd);

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

document.addEventListener('DOMContentLoaded', () => {
    if (wifiDisconnectBtn) {
        wifiDisconnectBtn.addEventListener('click', async () => {
            try {
                await showConfirm('Disconnect from current WiFi and forget it?', 'Disconnect WiFi');
            } catch (_) {
                return; // cancelled
            }
            try {
                showBackdrop('Disconnecting...');
                const resp = await fetch('/api/wifi/disconnect', { method: 'POST' });
                hideBackdrop();
                const data = await resp.json();
                if (resp.ok && data.success) {
                    const ssidText = data.ssid ? ` from: ${data.ssid}` : '';
                    showAlert(data.message || `Disconnected${ssidText}.`);
                    setTimeout(checkWifiStatus, 2000);
                } else {
                    showAlert('Failed to disconnect WiFi');
                }
            } catch (err) {
                hideBackdrop();
                showAlert(`Error: ${err.message}`);
            }
        });
    }
});
