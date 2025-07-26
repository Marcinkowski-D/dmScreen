import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, redirect, url_for
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from PIL import Image
import requests

import importlib.metadata

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
socketio = SocketIO(app, cors_allowed_origins="*")

db: Database = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    print('Searching for admin.html')
    print(os.getcwd())
    print(os.path.exists('data/www/admin.html'))
    print(os.path.isabs(WWW_FOLDER))
    print(os.path.exists(WWW_FOLDER))

    admin_path = os.path.join(WWW_FOLDER, 'admin.html')
    if os.path.exists(admin_path):
        print('found admin.html')
        return send_from_directory(WWW_FOLDER, 'admin.html')
    else:
        return f"File not found: {admin_path}", 404

@app.route('/view')
def view():
    print('Searching for view.html')
    view_path = os.path.join(WWW_FOLDER, 'view.html')
    if os.path.exists(view_path):
        print('found view.html')
        return send_from_directory(WWW_FOLDER, 'view.html')
    else:
        return f"File not found: {view_path}", 404



@app.route('/img/<path:path>')
def serve_img(path):
    file_path = os.path.join(UPLOAD_FOLDER, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        # Check if this is a thumbnail request
        if path.startswith('thumb_'):
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
                        img.save(file_path)
                        
                        # Update database to include thumb_path
                        db.updateImageThumbnail(original_path, path)
                except Exception as e:
                    print(f"Error creating thumbnail on-demand: {e}")
                    # If thumbnail creation fails, serve the original
                    return send_from_directory(UPLOAD_FOLDER, original_path)
        
        return send_from_directory(UPLOAD_FOLDER, path)
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
@app.route('/api/images', methods=['GET'])
def get_images():
    return jsonify(db.get_database()['images'])

@app.route('/api/images', methods=['POST'])
def upload_image():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No selected files'}), 400
    
    uploaded_images = []
    names = request.form.getlist('names[]') if 'names[]' in request.form else []
    
    for i, file in enumerate(files):
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to filename to avoid conflicts
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Create thumbnail
            thumb_filename = f"thumb_{filename}"
            thumb_filepath = os.path.join(app.config['UPLOAD_FOLDER'], thumb_filename)
            try:
                # Open the image and create a thumbnail
                with Image.open(filepath) as img:
                    # Convert to RGB if image has transparency (like PNG)
                    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                        img = background
                    
                    # Calculate new dimensions while maintaining aspect ratio
                    img.thumbnail((250, 250))
                    
                    # Save the thumbnail
                    img.save(thumb_filepath)
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
                'uploaded_at': datetime.now().isoformat()
            }
            
            # Add to database
            db.appendImage(image_data)
            
            # Notify clients about new image
            socketio.emit('image_added', image_data)
            
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
    
    # Notify clients
    socketio.emit('image_deleted', {'id': image_id})
    
    return jsonify({'success': True})

@app.route('/api/images/<image_id>/rotate', methods=['POST'])
def rotate_image(image_id):
    try:
        data = request.get_json()
        angle = data.get('angle', 90)  # Default to 90 degrees
        db.rotateImage(image_id, angle, UPLOAD_FOLDER)
        # Notify clients
        socketio.emit('image_updated', {'id': image_id})
        
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
        
        # Notify clients
        socketio.emit('image_updated', {'id': image_id})
        
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

    # Notify clients
    socketio.emit('settings_updated', database['settings'])
    
    return jsonify(database['settings'])

@app.route('/api/display', methods=['POST'])
def set_display_image():
    data = request.get_json()
    image_id = data.get('image_id')
    try:
        settings = db.setDisplayImage(image_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    
    # Notify clients
    socketio.emit('display_changed', {'image_id': image_id})
    socketio.emit('settings_updated', settings)
    
    return jsonify({'success': True})

@app.route('/api/display/reset', methods=['POST'])
def reset_display():
    # Set current_image to None to show screensaver
    try:
        db.setDisplayImage(None)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    
    # Notify clients
    socketio.emit('display_changed', {'image_id': None})
    
    return jsonify({'success': True})

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('request_current_state')
def handle_current_state():
    database = db.get_database()
    emit('current_state', {
        'settings': database['settings'],
        'images': database['images']
    })


def main():
    global db
    # Initialize database
    print('initializing database')
    db = Database(DATABASE_FILE)


    # Register WiFi routes
    register_wifi_routes(app)

    print('looking if linux')
    # Start WiFi monitoring in background (only on Raspberry Pi)
    if os.path.exists('/etc/raspbian-release'):
        print('is linux!')
        start_wifi_monitor()
    else:
        print('not linux!')
    
    # Start the server
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    main()