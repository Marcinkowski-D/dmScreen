import os
import uuid
import socket
import time
from datetime import datetime
from io import BytesIO

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


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

from dmScreen.updater import check_for_update

check_for_update("dmScreen", "Marcinkowski-D/dmScreen")

from dmScreen.database import Database
# Import refactored modules
from dmScreen.wifi import register_wifi_routes, start_wifi_monitor

# Configuration
BASE_DIR = os.getcwd()
DATA_FOLDER = os.path.join(BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(DATA_FOLDER, 'uploads')
WWW_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'www')
DATABASE_FILE = os.path.join(DATA_FOLDER, 'database.json')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Create necessary directories
os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__, static_folder=WWW_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

db: Database = None
last_update_timestamp = time.time()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_timestamp():
    global last_update_timestamp
    print('setting timestamp')
    last_update_timestamp = time.time()

# Routes
@app.route('/')
def index():
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    admin_path = os.path.join(WWW_FOLDER, 'admin.html')
    if os.path.exists(admin_path):
        return send_from_directory(WWW_FOLDER, 'admin.html')
    else:
        return f"File not found: {admin_path}", 404

@app.route('/view')
def view():
    view_path = os.path.join(WWW_FOLDER, 'view.html')
    if os.path.exists(view_path):
        return send_from_directory(WWW_FOLDER, 'view.html')
    else:
        return f"File not found: {view_path}", 404



@app.route('/img/<path:path>')
def serve_img(path):
    crop = False
    if path.startswith('crop_'):
        crop = True
        path = path[5:]
    is_thumb = path.startswith('thumb_')
    file_path = os.path.join(UPLOAD_FOLDER, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        # Check if this is a thumbnail request
        if is_thumb:
            # If thumbnail doesn't exist but original image does, generate it
            original_path = path[6:]  # Remove 'thumb_' prefix
            original_file_path = os.path.join(UPLOAD_FOLDER, original_path)
            if not os.path.exists(file_path) and os.path.exists(original_file_path):
                try:
                    # Generate thumbnail using the same logic as in upload_image
                    with Image.open(original_file_path) as img:
                        # Convert to RGB if image has transparency
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                            img = background
                        
                        # Create thumbnail
                        img.thumbnail((250, 250))
                        
                        # Save as WebP
                        if file_path.lower().endswith('.webp'):
                            img.save(file_path, format="WebP", interlace=1)
                        else:
                            # Get the filename without extension
                            base_name = os.path.splitext(file_path)[0]
                            new_file_path = f"{base_name}.webp"
                            img.save(new_file_path, format="WebP", interlace=1)
                            file_path = new_file_path
                            path = os.path.basename(new_file_path)
                        
                        # Update database to include thumb_path
                        db.updateImageThumbnail(original_path, path)
                except Exception as e:
                    print(f"Error creating thumbnail on-demand: {e}")
        # search database enty
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


        if img.size[0] > 1920:
            h = int(1920 / (img.size[0]/img.size[1]))
            img = img.resize((1920, h))
        if img.size[1] > 1080:
            w = int(1080 * (img.size[0]/img.size[1]))
            img = img.resize((w, 1080))

        img_io = BytesIO()
        img.save(img_io, 'WebP', interlace=1)
        img_io.seek(0)

        response = send_file(
            img_io,
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
    global last_update_timestamp
    database = db.get_database()
    
    # Sort images alphabetically by name
    images = sorted(database['images'], key=lambda x: x['name'].lower())
    
    # Sort folders alphabetically by name
    folders = sorted(database['folders'], key=lambda x: x['name'].lower())
    
    return jsonify({
        'settings': database['settings'],
        'images': images,
        'folders': folders,
        'timestamp': last_update_timestamp
    })

@app.route('/api/updates', methods=['GET'])
def check_updates():
    global last_update_timestamp
    return jsonify({
        'timestamp': last_update_timestamp
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
    
    for i, file in enumerate(files):
        print('processing file', file.filename)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to avoid conflicts
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

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
            name = names[i] if i < len(names) else os.path.splitext(file.filename)[0]
            
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
            
            # Add to database
            db.appendImage(image_data)
            
            # Update timestamp to notify clients about changes
            # update_timestamp()
            
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
        
        # Update timestamp to notify clients about changes
        
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

def main():
    global db
    # Initialize database
    print('initializing database')
    db = Database(DATABASE_FILE)

    # Register WiFi routes
    register_wifi_routes(app)

    print('looking if linux')
    # Start WiFi monitoring in background (only on Raspberry Pi)
    if hasattr(os, 'uname'):
        if "Raspbian" in os.uname().version:
            print('is linux!')
            start_wifi_monitor()
        else:
            print('not Raspberry Pi!')
    else:
        print('not linux!')
    
    # Start the server
    lan_ip = get_lan_ip()
    print('running server on port 5000')
    print('Local admin URL: http://127.0.0.1:5000/admin')
    print('Local view URL: http://127.0.0.1:5000/view')
    print(f'Network admin URL: http://{lan_ip}:5000/admin')
    print(f'Network view URL: http://{lan_ip}:5000/view')
    print('server listening...')
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    main()