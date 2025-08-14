import json
import os
import uuid
import socket
import time
import threading
import concurrent.futures
from datetime import datetime
import hashlib

import dotenv

dotenv.load_dotenv()

# Generate unique server instance ID based on current timestamp
SERVER_INSTANCE_ID = hashlib.md5(str(time.time()).encode()).hexdigest()

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    redirect,
    url_for,
    send_file,
)
from werkzeug.utils import secure_filename
from PIL import Image

# Import the background caching system
from dmScreen.cache_worker import (
    init_cache_system,
    shutdown_cache_system,
    queue_image_for_caching,
    is_image_cached
)


def get_lan_ip():
    try:
        p = run_cmd("ifconfig | grep -A 1 wlan0 | grep -o 'inet [0-9]*\.[0-9]*\.[0-9]*\.[0-9]*' | grep -o '[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*' | head -n 1", shell=True)
        print(p.stdout)
        return p.stdout.strip()
    except Exception as e:
        print(f"Error getting LAN IP address: {e}")
        return "127.0.0.1"

from dmScreen.updater import check_for_update

check_for_update("dmScreen", "Marcinkowski-D/dmScreen")

from dmScreen.database import Database
# Import refactored modules
from dmScreen.wifi import start_wifi_monitor, configure_wifi, add_known_network, current_ssid, disconnect_and_forget_current, set_target_wifi, set_change_callback, check_adhoc_network, check_wifi_connection, \
    run_cmd

# Global variables
admin_connected = False  # Track if admin has connected
last_network_change = 0  # Track when network configuration last changed
wifi_reconcile_event = threading.Event()  # Event-driven monitor trigger

# Cached network status to avoid frequent system calls on polling endpoints
NETWORK_STATUS_CACHE = {
    'connected': False,
    'ssid': None,
    'adhoc_active': False,
    'admin_url': None,
}


def recompute_network_status():
    """Recompute and cache network status: connected, ssid, adhoc_active, and admin_url."""
    ssid = None
    try:
        connected, ssid = check_wifi_connection()
    except Exception:
        connected = False
    adhoc_active = False
    if not connected:
        try:
            adhoc_active = check_adhoc_network()
        except Exception:
            adhoc_active = False
    # Choose IP depending on mode
    ip_address = get_lan_ip()
    port = int(os.getenv('PORT', '80'))
    port_part = '' if port == 80 else f':{port}'
    admin_url = f"http://{ip_address}{port_part}/admin"
    NETWORK_STATUS_CACHE.update({
        'connected': connected,
        'ssid': ssid,
        'adhoc_active': adhoc_active,
        'admin_url': admin_url,
    })

def reset_admin_connection():
    """Reset the admin_connected flag when network configuration changes"""
    global admin_connected, last_network_change
    admin_connected = False
    last_network_change = time.time()
    print("Network configuration changed, reset admin connection status")
    try:
        update_timestamp()
    except Exception:
        pass

# Wrapper functions for WiFi operations that reset admin connection status
def configure_wifi_wrapper(ssid, password):
    """Configure WiFi and reset admin connection status"""
    result = configure_wifi(ssid, password)
    if result:
        reset_admin_connection()
    return result

def create_adhoc_network_wrapper():
    """Create ad-hoc network and reset admin connection status"""
    result = create_adhoc_network()
    if result:
        reset_admin_connection()
    return result


# Configuration
BASE_DIR = os.getcwd()
DATA_FOLDER = os.path.join(BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(DATA_FOLDER, 'uploads')
CACHE_FOLDER = os.path.join(DATA_FOLDER, 'cache')
WWW_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'www')
DATABASE_FILE = os.path.join(DATA_FOLDER, 'database.json')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Create necessary directories
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CACHE_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__, static_folder=WWW_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

db: Database = None
last_update_timestamp = time.time()
last_cache_cleanup = time.time()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_timestamp():
    global last_update_timestamp
    print('setting timestamp')
    last_update_timestamp = time.time()
    
def cleanup_cache(max_age=86400, max_size=500*1024*1024):  # Default: 1 day, 500MB
    """Clean up old cache files to prevent the cache from growing too large"""
    global last_cache_cleanup
    
    # Only run cleanup once per hour
    current_time = time.time()
    if current_time - last_cache_cleanup < 3600:
        return
        
    last_cache_cleanup = current_time
    
    try:
        print("Running cache cleanup...")
        if not os.path.exists(CACHE_FOLDER):
            return
            
        # Get all files in cache directory with their modification times
        cache_files = []
        total_size = 0
        
        for filename in os.listdir(CACHE_FOLDER):
            file_path = os.path.join(CACHE_FOLDER, filename)
            if os.path.isfile(file_path):
                file_stat = os.stat(file_path)
                cache_files.append((file_path, file_stat.st_mtime, file_stat.st_size))
                total_size += file_stat.st_size
                
        # If total size is under the limit and no old files, return
        if total_size < max_size and all(current_time - mtime < max_age for _, mtime, _ in cache_files):
            return
            
        # Sort by modification time (oldest first)
        cache_files.sort(key=lambda x: x[1])
        
        # Remove old files and/or reduce cache size
        for file_path, mtime, size in cache_files:
            # Remove if older than max_age or if we need to reduce cache size
            if current_time - mtime > max_age or total_size > max_size:
                os.remove(file_path)
                total_size -= size
                print(f"Removed cache file: {file_path}")
                
            # Stop if we're under the size limit
            if total_size <= max_size * 0.8:  # 80% of max to provide buffer
                break
                
        print("Cache cleanup completed")
    except Exception as e:
        print(f"Error during cache cleanup: {e}")

# Routes
@app.route('/')
def index():
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    global admin_connected
    # Set admin_connected to True when admin page is accessed
    # admin_connected = True ## DEBUG
    update_timestamp()
    
    admin_path = os.path.join(WWW_FOLDER, 'admin.html')
    if os.path.exists(admin_path):
        return send_from_directory(WWW_FOLDER, 'admin.html')
    else:
        return f"File not found: {admin_path}", 404

@app.route('/view')
def view():
    global admin_connected
    view_path = os.path.join(WWW_FOLDER, 'view.html')
    
    if os.path.exists(view_path):
        # If admin hasn't connected, inject the IP address into the HTML
        if not admin_connected:
            with open(view_path, 'r') as file:
                html_content = file.read()

            # Return the modified HTML
            return html_content
        else:
            # Admin has connected, serve the original file
            return send_from_directory(WWW_FOLDER, 'view.html')
    else:
        return f"File not found: {view_path}", 404



@app.route('/img/<path:path>')
def serve_img(path):
    # Run cache cleanup periodically
    cleanup_cache()
    
    # Get query parameters
    w = request.args.get("w", None)
    if w is not None:
        w = int(w)

    crop = False
    if path.startswith('crop_'):
        crop = True
        path = path[5:]
    is_thumb = path.startswith('thumb_')
    file_path = os.path.join(UPLOAD_FOLDER, path)

    images = db.get_database().get('images')
    image_meta = next((img for img in images if img['path'] == path or img['thumb_path'] == path), None)
    img_hash = hashlib.md5(json.dumps(image_meta).encode()).hexdigest()
    
    # Create a cache key based on the path and width
    cache_key = f"{path}_{w}_{'crop' if crop else 'nocrop'}_{img_hash}"
    cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
    cache_path = os.path.join(CACHE_FOLDER, f"{cache_hash}.webp")
    
    # Function to generate thumbnail in a separate thread
    def generate_thumbnail(original_path, file_path):
        try:
            original_file_path = os.path.join(UPLOAD_FOLDER, original_path)
            with Image.open(original_file_path) as img:
                # Convert to RGB if image has transparency
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                    img = background
                
                # Get original dimensions
                width, height = img.size
                
                # Calculate new dimensions while maintaining aspect ratio
                if width > height:
                    new_width = 250
                    new_height = int(height * (250 / width))
                else:
                    new_height = 250
                    new_width = int(width * (250 / height))
                
                # Resize using BILINEAR filter (faster than default)
                img = img.resize((new_width, new_height), Image.BILINEAR)
                
                # Save as WebP with optimized settings
                if file_path.lower().endswith('.webp'):
                    img.save(file_path, format="WebP", quality=85)
                    new_path = path
                else:
                    # Get the filename without extension
                    base_name = os.path.splitext(file_path)[0]
                    new_file_path = f"{base_name}.webp"
                    img.save(new_file_path, format="WebP", quality=85)
                    file_path = new_file_path
                    new_path = os.path.basename(new_file_path)
                
                # Update database to include thumb_path
                db.updateImageThumbnail(original_path, new_path)
                return file_path
        except Exception as e:
            print(f"Error creating thumbnail on-demand: {e}")
            return None
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        # Check if a cached version exists
        if os.path.exists(cache_path) and os.path.isfile(cache_path):
            # Use cached image
            print(f"Using cached image: {cache_path}")
            
            # If this is a width-specific request, trigger background caching of other images
            if w is not None and not is_thumb:
                # Start background caching for other images with the same width
                threading.Thread(
                    target=queue_image_for_caching,
                    args=(path, w, crop, db, UPLOAD_FOLDER),
                    daemon=True
                ).start()
            
            response = send_file(
                cache_path,
                mimetype='image/webp',
                as_attachment=False
            )
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
            
        # Check if this is a thumbnail request
        if is_thumb:
            # If thumbnail doesn't exist but original image does, generate it
            original_path = path[6:]  # Remove 'thumb_' prefix
            original_file_path = os.path.join(UPLOAD_FOLDER, original_path)
            if not os.path.exists(file_path) and os.path.exists(original_file_path):
                # Start thumbnail generation in a separate thread
                # For on-demand thumbnails, we'll wait for the result since we need it immediately
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(generate_thumbnail, original_path, file_path)
                    try:
                        new_file_path = future.result(timeout=10)  # Wait up to 10 seconds
                        if new_file_path:
                            file_path = new_file_path
                            path = os.path.basename(new_file_path)
                    except concurrent.futures.TimeoutError:
                        print("Thumbnail generation timed out")
        
        # search database entry
        image_meta = next((img for img in db.get_database()['images'] if img['path'] == path or img['thumb_path'] == path), None)

        if crop:
            crop_path = os.path.join(UPLOAD_FOLDER, 'crop_'+path)
            if os.path.exists(crop_path) and os.path.isfile(crop_path):
                response = send_from_directory(directory=UPLOAD_FOLDER, path='crop_'+path)
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                return response

            img = Image.open(os.path.join(UPLOAD_FOLDER, path))

            if image_meta.get("mirror", None) is not None:
                if image_meta["mirror"].get("h", False):
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                if image_meta["mirror"].get("v", False):
                    img = img.transpose(Image.FLIP_TOP_BOTTOM)

            flip_wh = False
            if image_meta.get("rotate", None) is not None:
                r = image_meta["rotate"]
                if r == 270:
                    img = img.rotate(90, expand=True)
                elif r == 180:
                    img = img.rotate(180, expand=True)
                elif r == 90:
                    img = img.rotate(-90, expand=True)

            screen_size = (1920, 1080)
            crop_data = image_meta['crop']
            img_size = img.size
            img_pos = [0, 0]
            t_size = [0, 0]
            scale = 1
            if img_size[0] / img_size[1] < 16/9:
                scale = screen_size[1] / img_size[1]
                tw = img_size[0] * scale
                th = screen_size[1]
                t_size = [tw, th]
                img_pos[0] = int((screen_size[0] - tw) / 2)
            else:
                scale = screen_size[0] / img_size[0]
                th = img_size[1] * scale
                tw = screen_size[0]
                t_size = [tw, th]
                img_pos[1] = int((screen_size[1] - th) / 2)

            c_x = crop_data.get("x")
            c_y = crop_data.get("y")
            c_w = crop_data.get("w")
            c_h = int(c_w / 16 * 9)

            x1 = max(img_pos[0], c_x) - img_pos[0]
            y1 = max(img_pos[1], c_y) - img_pos[1]
            x2 = min(img_pos[0] + t_size[0], c_x + c_w) - img_pos[0]
            y2 = min(img_pos[1] + t_size[1], c_y + c_h) - img_pos[1]

            x1 /= scale
            y1 /= scale
            y2 /= scale
            x2 /= scale

            img = img.crop((x1, y1, x2, y2))
        else:
            # Create a response with cache control headers to prevent caching
            img = Image.open(os.path.join(UPLOAD_FOLDER, path))

        w = w if w is not None else 1920

        # Use BILINEAR filter for faster resizing
        if img.size[0] > w:
            h = int(w / (img.size[0]/img.size[1]))
            img = img.resize((w, h), Image.BILINEAR)
        if img.size[1] > 1080:
            w = int(1080 * (img.size[0]/img.size[1]))
            img = img.resize((w, 1080), Image.BILINEAR)

        # Save to cache
        img.save(cache_path, format="WebP", quality=85)
        
        # If this is a width-specific request, trigger background caching of other images
        if w is not None and not is_thumb and not crop:
            # Start background caching for other images with the same width
            threading.Thread(
                target=queue_image_for_caching,
                args=(path, w, crop, db, UPLOAD_FOLDER),
                daemon=True
            ).start()
        
        # Return the image
        response = send_file(
            cache_path,
            mimetype='image/webp',
            as_attachment=False
        )
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    else:
        return f"File not found: {file_path}", 404

@app.route('/<path:path>')
def static_files(path):
    file_path = os.path.join(WWW_FOLDER, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(WWW_FOLDER, path)
    else:
        return f"File not found: {file_path}", 404

# API Endpoints
@app.route('/api/current_state', methods=['GET'])
def get_current_state():
    global last_update_timestamp, admin_connected
    database = db.get_database()
    
    # Sort images alphabetically by name
    images = sorted(database['images'], key=lambda x: x['name'].lower())
    
    # Sort folders alphabetically by name
    folders = sorted(database['folders'], key=lambda x: x['name'].lower())
    
    return jsonify({
        'settings': database['settings'],
        'images': images,
        'folders': folders,
        'timestamp': last_update_timestamp,
        'admin_connected': admin_connected
    })

@app.route('/api/updates', methods=['GET'])
def check_updates():
    global last_update_timestamp, admin_connected, SERVER_INSTANCE_ID, NETWORK_STATUS_CACHE
    # Use cached network status to avoid frequent system calls during steady state
    try:
        recompute_network_status()
        cache = NETWORK_STATUS_CACHE if isinstance(NETWORK_STATUS_CACHE, dict) else {}
    except Exception:
        recompute_network_status()
        cache = NETWORK_STATUS_CACHE
    print(f"Network status cache: {cache}")
    return jsonify({
        'timestamp': last_update_timestamp,
        'instance_id': SERVER_INSTANCE_ID,
        'admin_connected': admin_connected,
        'ip': cache.get('admin_url'),
        'wifi_connected': cache.get('connected'),
        'ssid': cache.get('ssid'),
        'adhoc_active': cache.get('adhoc_active'),
        'adhoc_ssid': 'dmscreen' if cache.get('adhoc_active') else None,
        'adhoc_password': 'dmscreen' if cache.get('adhoc_active') else None
    })

@app.route('/api/images', methods=['GET'])
def get_images():
    # Get query parameters
    folder_id = request.args.get('folder', None)
    
    # Get all images
    images = db.get_database()['images']
    
    # Filter by folder if specified
    if folder_id:
        images = [img for img in images if img.get('parent') == folder_id]
    else:
        # If no folder specified, return only root images (parent is None)
        images = [img for img in images if img.get('parent') is None]
    
    # Sort images alphabetically by name
    images = sorted(images, key=lambda x: x['name'].lower())
    
    return jsonify(images)
    
@app.route('/api/folders', methods=['GET'])
def get_folders():
    # Get query parameters
    parent_id = request.args.get('parent', None)
    
    # Get all folders
    folders = db.get_database()['folders']
    
    # Filter by parent if specified
    if parent_id:
        folders = [folder for folder in folders if folder.get('parent') == parent_id]
    else:
        # If no parent specified, return only root folders (parent is None)
        folders = [folder for folder in folders if folder.get('parent') is None]
    
    # Sort folders alphabetically by name
    folders = sorted(folders, key=lambda x: x['name'].lower())
    
    return jsonify(folders)

@app.route('/api/folders', methods=['POST'])
def create_folder():
    # Get folder data from request
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    
    # Create folder data
    folder_data = {
        'id': str(uuid.uuid4()),
        'name': data['name'],
        'parent': data.get('parent'),
        'created_at': datetime.now().isoformat()
    }
    
    # Add folder to database
    result = db.createFolder(folder_data)
    
    # Check if there was an error
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[0], dict) and 'error' in result[0]:
        return jsonify(result[0]), result[1]
    
    return jsonify(result), 201

@app.route('/api/folders/<folder_id>', methods=['DELETE'])
def delete_folder(folder_id):
    # Delete folder
    result = db.deleteFolder(folder_id)
    
    # Check if there was an error
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[0], dict) and 'error' in result[0]:
        return jsonify(result[0]), result[1]
    
    return jsonify(result)

@app.route('/api/folders/<folder_id>/rename', methods=['POST'])
def rename_folder(folder_id):
    # Get new name from request
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    
    new_name = data.get('name')
    
    # Get the folder from database
    db_data = db.get_database()
    folder = next((f for f in db_data['folders'] if f['id'] == folder_id), None)
    
    if not folder:
        return jsonify({'error': 'Folder not found'}), 404
    
    # Update folder name
    folder['name'] = new_name
    db.save_database(db_data)
    
    return jsonify(folder)

@app.route('/api/folders/<folder_id>/move', methods=['POST'])
def move_folder(folder_id):
    # Get new parent ID from request
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    new_parent_id = data.get('parent')
    
    # Move folder
    result = db.moveFolder(folder_id, new_parent_id)
    
    # Check if there was an error
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[0], dict) and 'error' in result[0]:
        return jsonify(result[0]), result[1]
    
    return jsonify(result)

@app.route('/api/images/<image_id>/move', methods=['POST'])
def move_image(image_id):
    # Get folder ID from request
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    folder_id = data.get('folder')
    
    # Move image
    result = db.moveImage(image_id, folder_id)
    
    # Check if there was an error
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[0], dict) and 'error' in result[0]:
        return jsonify(result[0]), result[1]
    
    return jsonify(result)

@app.route('/api/images', methods=['POST'])
def upload_image():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No selected files'}), 400
    
    uploaded_images = []
    names = request.form.getlist('names[]') if 'names[]' in request.form else []
    
    # Get folder ID from form data
    folder_id = request.form.get('folder', None)
    
    # Validate folder exists if specified
    if folder_id:
        db_data = db.get_database()
        folder_exists = any(folder['id'] == folder_id for folder in db_data['folders'])
        if not folder_exists:
            return jsonify({'error': 'Folder not found'}), 404
    
    # Function to process a single image in a separate thread
    def process_image(file_index, file):
        print('processing file', file.filename)
        if not file or not allowed_file(file.filename):
            return None
            
        filename = secure_filename(file.filename)
        # Add timestamp to filename to avoid conflicts
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        thumb_filename = filename  # Default in case of failure
        
        try:
            with Image.open(filepath) as img:
                processed_img = img.copy()
                if filepath.lower().endswith('.webp'):
                    processed_img.save(filepath, format="WebP")
                else:
                    # Get the filename without extension
                    base_name = os.path.splitext(filepath)[0]
                    new_filepath = f"{base_name}.webp"
                    processed_img.save(new_filepath, format="WebP")
                    # Update the filepath and filename
                    os.remove(filepath)  # Remove the original file
                    filepath = new_filepath
                    filename = os.path.basename(new_filepath)

                print(f"Saved image {filename} as WebP")
        except Exception as e:
            print(f"Error processing image: {e}")
            return None
        
        # Create thumbnail
        thumb_filename = f"thumb_{filename}"
        thumb_filepath = os.path.join(app.config['UPLOAD_FOLDER'], thumb_filename)
        try:
            # Open the image and create a thumbnail
            with Image.open(filepath) as img:
                # Calculate new dimensions while maintaining aspect ratio
                img.thumbnail((250, 250))

                if thumb_filepath.lower().endswith('.webp'):
                    img.save(thumb_filepath, format="WebP")
                else:
                    # Get the filename without extension
                    base_name = os.path.splitext(thumb_filepath)[0]
                    new_thumb_filepath = f"{base_name}.webp"
                    img.save(new_thumb_filepath, format="WebP")
                    # Update the thumbnail filepath and filename
                    thumb_filename = os.path.basename(new_thumb_filepath)
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            # If thumbnail creation fails, use the original image path
            thumb_filename = filename
        
        # Get name from the names list if available, otherwise use filename without extension
        name = names[file_index] if file_index < len(names) else os.path.splitext(file.filename)[0]
        
        # Create image entry
        image_id = str(uuid.uuid4())
        image_data = {
            'id': image_id,
            'name': name,
            'path': filename,
            'thumb_path': thumb_filename,
            'uploaded_at': datetime.now().isoformat(),
            'parent': folder_id  # Set the parent folder ID
        }
        
        return image_data
    
    # Process images in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit all image processing tasks to the executor
        future_to_index = {executor.submit(process_image, i, file): i for i, file in enumerate(files)}
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_index):
            image_data = future.result()
            if image_data:
                # Add to database (this needs to be thread-safe)
                db.appendImage(image_data)
                uploaded_images.append(image_data)
    
    if uploaded_images:
        return jsonify(uploaded_images), 201
    
    return jsonify({'error': 'No valid files uploaded'}), 400

@app.route('/api/images/<image_id>', methods=['DELETE'])
def delete_image(image_id):
    image = db.removeImage(image_id)

    if image is not None:
        # Delete the original file
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, image['path']))
        except OSError:
            pass  # File might not exist
            
        # Delete the thumbnail if it exists
        if 'thumb_path' in image:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, image['thumb_path']))
            except OSError:
                pass  # Thumbnail might not exist
    
    # Update timestamp to notify clients about changes
    update_timestamp()
    
    return jsonify({'success': True})

@app.route('/api/images/<image_id>/transform', methods=['POST'])
def transform_image(image_id):
    """Combined endpoint for updating multiple transformation properties at once"""
    try:
        data = request.get_json()
        transform_data = {}
        
        # Extract transformation data from request
        if 'rotate' in data:
            transform_data['rotate'] = data['rotate']
        if 'mirror' in data:
            transform_data['mirror'] = data['mirror']
        if 'crop' in data:
            transform_data['crop'] = data['crop']

        if not transform_data:
            return jsonify({'error': 'No transformation data provided'}), 400

        # Use the updateImageTransform method to update all provided transformation data
        result = db.updateImageTransform(image_id, transform_data, UPLOAD_FOLDER)
        update_timestamp()
        
        # Check if there was an error
        if isinstance(result, tuple) and len(result) > 1 and 'error' in result[0]:
            return jsonify(result[0]), result[1]
        
        # Get the image path to trigger cache regeneration
        db_data = db.get_database()
        image = next((img for img in db_data['images'] if img['id'] == image_id), None)
        
        if image and 'path' in image:
            # Trigger background caching for common image sizes with both crop settings
            # This ensures all cached versions are updated after transformation
            widths = [None, 250, 500, 1000, 1920]
            for width in widths:
                for crop_setting in [True, False]:
                    threading.Thread(
                        target=queue_image_for_caching,
                        args=(image['path'], width, crop_setting, db, UPLOAD_FOLDER),
                        daemon=True
                    ).start()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/images/<image_id>/rename', methods=['POST'])
def rename_image(image_id):
    try:
        data = request.get_json()
        new_name = data.get('name')
        
        if not new_name:
            return jsonify({'error': 'Name is required'}), 400
            
        # Update the image name in the database
        db_data = db.get_database()
        image = next((img for img in db_data['images'] if img['id'] == image_id), None)
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
            
        image['name'] = new_name
        db.save_database(db_data)
        
        # Update timestamp to notify clients about changes
        update_timestamp()
        
        return jsonify({'success': True, 'name': new_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify(db.get_database()['settings'])

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    config = data.items()

    db.update_settings(config)
    database = db.get_database()

    # Update timestamp to notify clients about changes
    update_timestamp()
    
    return jsonify(database['settings'])

@app.route('/api/display', methods=['POST'])
def set_display_image():
    data = request.get_json()
    image_id = data.get('image_id')
    try:
        settings = db.setDisplayImage(image_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    
    # Update timestamp to notify clients about changes
    update_timestamp()
    
    return jsonify({'success': True})

@app.route('/api/display/reset', methods=['POST'])
def reset_display():
    # Set current_image to None to show screensaver
    try:
        db.setDisplayImage(None)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    
    # Update timestamp to notify clients about changes
    update_timestamp()
    
    return jsonify({'success': True})

@app.route('/api/image/<image_id>/url', methods=['GET'])
def get_image_url(image_id):
    """Get the URL for an image by its ID"""
    # Get query parameters
    w = request.args.get("w", None)
    crop = request.args.get("crop", "true").lower() == "true"
    thumb = request.args.get("thumb", "false").lower() == "true"
    
    # Find the image in the database
    database = db.get_database()
    image = next((img for img in database['images'] if img['id'] == image_id), None)

    if not image:
        return jsonify({'error': 'Image not found'}), 404

    img_hash = hashlib.md5(json.dumps(image).encode()).hexdigest()
    # Construct the URL
    path = image['path']
    if thumb:
        path = image['thumb_path'] if 'thumb_path' in image else f"thumb_{path}"
    
    # Add crop prefix if needed
    url_prefix = 'crop_' if crop else ''
    
    # Construct the base URL
    base_url = f"/img/{url_prefix}{path}"
    
    # Add width parameter if specified
    url = f"{base_url}?t={int(time.time())}"
    if w:
        url += f"&w={w}"
        
        # If this is a width-specific request and not a thumbnail, check if we should trigger background caching
        if not thumb and not crop and w.isdigit():
            w_int = int(w)
            # Check if the image is already cached
            if not is_image_cached(path, w_int, img_hash, crop, CACHE_FOLDER):
                # Start background caching for other images with the same width
                threading.Thread(
                    target=queue_image_for_caching,
                    args=(path, w_int, crop, db, UPLOAD_FOLDER),
                    daemon=True
                ).start()
    
    return jsonify({
        'url': url,
        'name': image['name']
    })



# Flask route handlers for WiFi functionality
def register_wifi_routes(app, on_change=None):

    set_change_callback(on_change)

    # Debug logging for WiFi
    _DM_WIFI_DEBUG_ENV = os.getenv('DM_WIFI_DEBUG', '1')
    _DEBUG_WIFI = not (_DM_WIFI_DEBUG_ENV.lower() in ('0', 'false', 'no', 'off', ''))

    def _ts():
        try:
            return time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return ''

    def _dbg(msg: str):
        if _DEBUG_WIFI:
            try:
                print(f"[WiFi][{_ts()}] {msg}")
            except Exception:
                pass

    @app.route('/api/wifi/status', methods=['GET'])
    def get_wifi_status():
        _dbg("API GET /api/wifi/status aufgerufen ...")
        connected, ssid = check_wifi_connection()
        adhoc_active = False
        adhoc_ssid = None
        if not connected:
            adhoc_active = check_adhoc_network()
            if adhoc_active:
                adhoc_ssid = 'dmscreen'
        ssid_val = current_ssid() if connected else None
        _dbg(f"API /api/wifi/status Antwort: connected={connected} | ssid={ssid_val} | adhoc_active={adhoc_active} | adhoc_ssid={adhoc_ssid}")
        return jsonify({
            'connected': connected,
            'ssid': ssid_val,
            'adhoc_active': adhoc_active,
            'adhoc_ssid': adhoc_ssid
        })

    @app.route('/api/wifi/configure', methods=['POST'])
    def set_wifi_config():
        data = request.get_json() or {}
        ssid = data.get('ssid')
        password = data.get('password')
        _dbg(f"API POST /api/wifi/configure: ssid='{ssid}' password='****'")
        if not ssid or not password:
            _dbg("API /api/wifi/configure: fehlende Felder -> 400")
            return jsonify({'error': 'SSID and password are required'}), 400
        success = configure_wifi(ssid, password)
        _dbg(f"API /api/wifi/configure Ergebnis: success={success}")
        return jsonify({
            'success': success,
            'message': (
                "Connected. The new IP address is shown on the device's screen. You can close this tab."
                if success else 'Failed to configure WiFi'
            )
        })

    @app.route('/api/wifi/known', methods=['GET'])
    def api_list_known():
        _dbg("API GET /api/wifi/known ...")
        nets = list_known_networks()
        _dbg(f"API /api/wifi/known -> {len(nets)} Netzwerke: {[n.get('ssid') for n in nets]}")
        return jsonify({'networks': nets})

    @app.route('/api/wifi/disconnect', methods=['POST'])
    def api_disconnect():
        _dbg("API POST /api/wifi/disconnect ...")
        connected, ssid = check_wifi_connection()
        set_target_wifi(None)
        _dbg(f"API /api/wifi/disconnect")
        msg = (
            'Wifi disconnected, use AP "dmscreen" (password "dmscreen") and navigate to 192.168.4.1 to continue. You can close this tab.'
        )
        return jsonify({'success': True, 'ssid': ssid, 'message': msg})



def main():
    global db
    # Initialize database
    print('initializing database')
    db = Database(DATABASE_FILE)

    # Initialize background caching system
    print('initializing background caching system')
    init_cache_system(CACHE_FOLDER, UPLOAD_FOLDER)

    
    # Add custom route for WiFi configuration that resets admin connection


    print('looking if linux')
    # Start WiFi monitoring in background (only on Raspberry Pi)
    if hasattr(os, 'uname'):
        if "Raspbian" in os.uname().version:
            print('is linux!')
            # Register WiFi routes with on_change callback to reset admin connection
            register_wifi_routes(app, on_change=reset_admin_connection)

            # Start monitor thread that waits for GUI-triggered changes
            start_wifi_monitor()
        else:
            print('not Raspberry Pi!')
    else:
        print('not linux!')
    
    try:
        PORT = int(os.getenv('PORT', '80'))
        # Start the server
        lan_ip = get_lan_ip()
        print(f'running server on port {PORT}')
        port_part = '' if PORT == 80 else f':{PORT}'
        print(f'Local admin URL: http://127.0.0.1{port_part}/admin')
        print(f'Local view URL: http://127.0.0.1{port_part}/view')
        print(f'Network admin URL: http://{lan_ip}{port_part}/admin')
        print(f'Network view URL: http://{lan_ip}{port_part}/view')
        print('server listening...')
        app.run(host='0.0.0.0', port=PORT, debug=False)
    finally:
        # Shutdown background caching system when server stops
        print('shutting down background caching system')
        shutdown_cache_system()

if __name__ == "__main__":
    main()