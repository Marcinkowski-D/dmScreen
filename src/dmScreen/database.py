# Database functions
import os
import json


from flask import jsonify

DEFAULT_DATABASE = {
    "images": [],
    "settings": {
        "screensaver": None,
        "current_image": None
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
        self.init_database()


    def init_database(self):
        if not os.path.exists(self.db_file):
            with open(self.db_file, 'w') as f:
                json.dump(DEFAULT_DATABASE, f, indent=4)

    def get_database(self ):
        with open(self.db_file, 'r') as f:
            return json.load(f)

    def save_database(self, data):
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
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, 'crop_'+image['path']))
        except OSError:
            pass  # File might not exist
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, 'crop_'+image['thumb_path']))
        except OSError:
            pass  # File might not exist
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
        # Update settings
        for key, value in config:
            if key in db['settings']:
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