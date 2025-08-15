# Database functions
import os
import json
import threading
import glob
import hashlib
from datetime import datetime

from flask import jsonify

DEFAULT_DATABASE = {
    "images": [],
    "folders": [],
    "settings": {
        "screensaver": None,
        "current_image": None,
        "theme": "dark",
        "admin_title": "DM Screen Admin"
    }
}

# Default values for image transformation properties
DEFAULT_ROTATE = 0
DEFAULT_MIRROR = {"h": False, "v": False}
DEFAULT_CROP = {"w": 1920, "x": 0, "y": 0}
db_file = None

class Database:

    def __init__(self, db_file):
        self.db_file = db_file
        self.lock = threading.RLock()  # Reentrant lock for thread safety
        self.init_database()


    def init_database(self):
        with self.lock:
            if not os.path.exists(self.db_file):
                with open(self.db_file, 'w') as f:
                    json.dump(DEFAULT_DATABASE, f, indent=4)

    def get_database(self):
        with self.lock:
            with open(self.db_file, 'r') as f:
                data = json.load(f)
            # Migrate/ensure default structure and settings keys
            changed = False
            if 'images' not in data or not isinstance(data.get('images'), list):
                data['images'] = []
                changed = True
            if 'folders' not in data or not isinstance(data.get('folders'), list):
                data['folders'] = []
                changed = True
            if 'settings' not in data or not isinstance(data.get('settings'), dict):
                # Start from defaults
                data['settings'] = DEFAULT_DATABASE['settings'].copy()
                changed = True
            else:
                # Ensure all default settings keys exist
                for key, default_val in DEFAULT_DATABASE['settings'].items():
                    if key not in data['settings']:
                        data['settings'][key] = default_val
                        changed = True
            if changed:
                # Persist migration so future reads are consistent
                self.save_database(data)
            return data

    def save_database(self, data):
        with self.lock:
            with open(self.db_file, 'w') as f:
                json.dump(data, f, indent=4)

    def appendImage(self, image_data):
        # Add default transformation properties if not present
        if 'rotate' not in image_data:
            image_data['rotate'] = DEFAULT_ROTATE
        if 'mirror' not in image_data:
            image_data['mirror'] = DEFAULT_MIRROR.copy()
        if 'crop' not in image_data:
            image_data['crop'] = DEFAULT_CROP
        if 'parent' not in image_data:
            image_data['parent'] = None
            
        db = self.get_database()
        db["images"].append(image_data)
        self.save_database(db)

    def removeImage(self, image_id):

        db = self.get_database()

        # Find the image
        image = next((img for img in db['images'] if img['id'] == image_id), None)
        if not image:
            return jsonify({'error': 'Image not found'}), 404

        # Remove from database
        db['images'] = [img for img in db['images'] if img['id'] != image_id]

        # If this image was the screensaver or current image, reset those settings
        if db['settings']['screensaver'] == image_id:
            db['settings']['screensaver'] = None
        if db['settings']['current_image'] == image_id:
            db['settings']['current_image'] = None

        self.save_database(db)
        return image

    def updateImageTransform(self, image_id, transform_data, UPLOAD_FOLDER):
        """
        Update image transformation metadata (rotate, mirror, crop)
        
        Args:
            image_id: The ID of the image to update
            transform_data: Dictionary containing transformation data
                - rotate: Rotation angle (0, 90, 180, -90)
                - mirror: Dictionary with h and v boolean values
                - crop: Dictionary with w, x, y values
        
        Returns:
            Updated image data or error response
        """
        db = self.get_database()
        # Find the image
        image = next((img for img in db['images'] if img['id'] == image_id), None)
        if not image:
            return {'error': 'Image not found'}, 404
            
        # Update rotation if provided
        if 'rotate' in transform_data:
            # Ensure rotation is one of the allowed values
            allowed_rotations = [0, 90, 180, 270]
            rotation = transform_data['rotate']
            if rotation in allowed_rotations:
                image['rotate'] = rotation
            else:
                return {'error': 'Invalid rotation value'}, 400
                
        # Update mirror if provided
        if 'mirror' in transform_data:
            mirror_data = transform_data['mirror']
            if isinstance(mirror_data, dict) and 'h' in mirror_data and 'v' in mirror_data:
                image['mirror'] = {
                    'h': bool(mirror_data['h']),
                    'v': bool(mirror_data['v'])
                }
            else:
                return {'error': 'Invalid mirror data'}, 400
                
        # Update crop if provided
        if 'crop' in transform_data:
            crop_data = transform_data['crop']
            if isinstance(crop_data, dict) and 'w' in crop_data and 'x' in crop_data and 'y' in crop_data:
                image['crop'] = {
                    'w': int(crop_data['w']),
                    'x': int(crop_data['x']),
                    'y': int(crop_data['y'])
                }
            else:
                return {'error': 'Invalid crop data'}, 400
                
        # Save the updated database
        self.save_database(db)
        
        # Remove cropped versions of the image
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, 'crop_'+image['path']))
        except OSError:
            pass  # File might not exist
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, 'crop_'+image['thumb_path']))
        except OSError:
            pass  # File might not exist
            
        # Invalidate cache for this image
        self._invalidate_image_cache(image['path'])
        if 'thumb_path' in image:
            self._invalidate_image_cache(image['thumb_path'])
            
        return image
        
    # Keep the old method for backward compatibility, but make it use the new approach
    def rotateImage(self, image_id, angle, UPLOAD_FOLDER=None):
        """Legacy method that now uses the metadata approach instead of physical rotation"""
        # Convert angle to one of the allowed values (0, 90, 180, -90)
        allowed_angles = [0, 90, 180, -90]
        closest_angle = min(allowed_angles, key=lambda x: abs(x - angle % 360))
        
        # Update the rotation metadata
        return self.updateImageTransform(image_id, {'rotate': closest_angle})

    def update_settings(self, config):
        db = self.get_database()
        # Update settings (allow adding new keys as well)
        for key, value in config:
            db['settings'][key] = value

        self.save_database(db)

    def setDisplayImage(self, image_id):
        db = self.get_database()

        # Validate image exists
        if image_id is not None and not any(img['id'] == image_id for img in db['images']):
            raise ValueError('Image not found')

        # Update current image
        db['settings']['current_image'] = image_id
        self.save_database(db)
        return db['settings']
        
    def updateImageThumbnail(self, image_path, thumb_path):
        """Update an image entry with a thumbnail path"""
        with self.lock:
            db = self.get_database()
            updated = False
            
            for image in db['images']:
                if image['path'] == image_path and 'thumb_path' not in image:
                    image['thumb_path'] = thumb_path
                    updated = True
                    break
                    
            if updated:
                self.save_database(db)
                
            return updated
            
    def createFolder(self, folder_data):
        """Create a new folder
        
        Args:
            folder_data: Dictionary containing folder data
                - id: Unique identifier
                - name: Folder name
                - parent: Parent folder ID or None for root
                - created_at: Creation timestamp
        
        Returns:
            The created folder data
        """
        # Ensure required fields are present
        if 'id' not in folder_data or 'name' not in folder_data:
            return {'error': 'Missing required fields'}, 400
            
        # Set default values if not provided
        if 'parent' not in folder_data:
            folder_data['parent'] = None
        if 'created_at' not in folder_data:
            folder_data['created_at'] = datetime.now().isoformat()
            
        db = self.get_database()
        
        # Validate parent folder exists if specified
        if folder_data['parent'] is not None:
            parent_exists = any(folder['id'] == folder_data['parent'] for folder in db['folders'])
            if not parent_exists:
                return {'error': 'Parent folder not found'}, 404
                
        db['folders'].append(folder_data)
        self.save_database(db)
        return folder_data
        
    def moveFolder(self, folder_id, new_parent_id):
        """Move a folder to a different parent
        
        Args:
            folder_id: ID of the folder to move
            new_parent_id: ID of the new parent folder, or None for root
            
        Returns:
            Updated folder data or error response
        """
        db = self.get_database()
        
        # Find the folder
        folder = next((f for f in db['folders'] if f['id'] == folder_id), None)
        if not folder:
            return {'error': 'Folder not found'}, 404
            
        # Validate new parent exists if not None
        if new_parent_id is not None:
            parent_exists = any(f['id'] == new_parent_id for f in db['folders'])
            if not parent_exists:
                return {'error': 'Parent folder not found'}, 404
                
            # Prevent circular references
            current_parent = new_parent_id
            while current_parent is not None:
                if current_parent == folder_id:
                    return {'error': 'Cannot move a folder inside itself or its children'}, 400
                parent_folder = next((f for f in db['folders'] if f['id'] == current_parent), None)
                if not parent_folder:
                    break
                current_parent = parent_folder['parent']
                
        # Update the folder's parent
        folder['parent'] = new_parent_id
        self.save_database(db)
        return folder
        
    def deleteFolder(self, folder_id):
        """Delete a folder and optionally its contents
        
        Args:
            folder_id: ID of the folder to delete
            
        Returns:
            Success message or error response
        """
        db = self.get_database()
        
        # Find the folder
        folder = next((f for f in db['folders'] if f['id'] == folder_id), None)
        if not folder:
            return {'error': 'Folder not found'}, 404
            
        # Check if folder has children
        has_child_folders = any(f['parent'] == folder_id for f in db['folders'])
        has_child_images = any(img['parent'] == folder_id for img in db['images'])
        
        if has_child_folders or has_child_images:
            # Move children to parent folder
            parent_id = folder['parent']
            
            # Update child folders
            for f in db['folders']:
                if f['parent'] == folder_id:
                    f['parent'] = parent_id
                    
            # Update child images
            for img in db['images']:
                if img['parent'] == folder_id:
                    img['parent'] = parent_id
        
        # Remove the folder
        db['folders'] = [f for f in db['folders'] if f['id'] != folder_id]
        self.save_database(db)
        
        return {'message': 'Folder deleted successfully'}
        
    def moveImage(self, image_id, folder_id):
        """Move an image to a different folder
        
        Args:
            image_id: ID of the image to move
            folder_id: ID of the destination folder, or None for root
            
        Returns:
            Updated image data or error response
        """
        db = self.get_database()
        
        # Find the image
        image = next((img for img in db['images'] if img['id'] == image_id), None)
        if not image:
            return {'error': 'Image not found'}, 404
            
        # Validate folder exists if not None
        if folder_id is not None:
            folder_exists = any(f['id'] == folder_id for f in db['folders'])
            if not folder_exists:
                return {'error': 'Folder not found'}, 404
                
        # Update the image's parent
        image['parent'] = folder_id
        self.save_database(db)
        return image
        
    def _invalidate_image_cache(self, image_path):
        """
        Delete all cache files related to a specific image path
        
        This is called when an image is transformed to ensure users see the updated version
        """
        try:
            # Get the cache folder path from the server module
            import os
            from pathlib import Path
            
            # Find the cache folder (should be in data/cache relative to the current working directory)
            base_dir = os.getcwd()
            cache_folder = os.path.join(base_dir, 'data', 'cache')
            
            if not os.path.exists(cache_folder):
                return
                
            # Find all cache files that contain this image path in their hash
            # Since we can't reverse the hash, we'll need to check all cache files
            # by creating potential cache keys and checking if their hashes exist
            
            # List all files in the cache directory
            cache_files = os.listdir(cache_folder)
            
            # Generate possible cache keys for different widths and crop settings
            # Common widths used in the application
            widths = [None, 250, 500, 1000, 1920]
            crop_settings = [True, False]
            
            # Check each possible combination
            for width in widths:
                for crop in crop_settings:
                    # Create the cache key as done in server.py
                    w_str = f"_{width}" if width else ""
                    cache_key = f"{image_path}{w_str}_{'crop' if crop else 'nocrop'}"
                    cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
                    cache_file = f"{cache_hash}.webp"
                    
                    # If this cache file exists, delete it
                    cache_path = os.path.join(cache_folder, cache_file)
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                        print(f"Invalidated cache for transformed image: {cache_path}")
        except Exception as e:
            print(f"Error invalidating image cache: {e}")
            # Don't raise the exception - cache invalidation should not block the main operation