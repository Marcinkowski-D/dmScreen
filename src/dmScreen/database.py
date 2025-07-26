# Database functions
import os
import json

from PIL import Image

from flask import jsonify

DEFAULT_DATABASE = {
    "images": [],
    "settings": {
        "screensaver": None,
        "current_image": None
    }
}
db_file = None

class Database:

    def __init__(self, db_file):
        self.db_file = db_file

        ## TODO SOMEHOW DATABASE FILE IS NOT CREATED

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

    def rotateImage(self, image_id, angle, UPLOAD_FOLDER):
        db = self.get_database()
        # Find the image
        image = next((img for img in db['images'] if img['id'] == image_id), None)
        if not image:
            return jsonify({'error': 'Image not found'}), 404

        # Get rotation angle
        # Open and rotate the image
        path = os.path.join(UPLOAD_FOLDER, image['path'])
        img = Image.open(path)
        rotated_img = img.rotate(-angle, expand=True)  # Negative angle for clockwise rotation
        rotated_img.save(path)

        thumb_path = os.path.join(UPLOAD_FOLDER, image['thumb_path'])
        img = Image.open(thumb_path)
        rotated_img = img.rotate(-angle, expand=True)  # Negative angle for clockwise rotation
        rotated_img.save(thumb_path)

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