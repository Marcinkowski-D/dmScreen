"""
Background caching system for dmScreen.

This module implements a job queue and worker threads to proactively cache
images in the background when a specific image is requested with a width parameter.
"""
import json
import os
import time
import threading
import queue
import hashlib
from typing import Dict, List, Set, Tuple, Optional
from PIL import Image

# Global variables
cache_queue = queue.PriorityQueue()
active_workers = 0
max_workers = 3
worker_threads = []
cached_images = set()  # Set to track which images have been cached
cache_lock = threading.RLock()  # Lock for thread-safe operations
shutdown_event = threading.Event()  # Event to signal worker threads to shut down

# Job priority levels (lower number = higher priority)
PRIORITY_SAME_FOLDER = 10
PRIORITY_OTHER_IMAGES = 20

class CacheJob:
    """Represents a job to cache an image with specific parameters."""
    
    def __init__(self, image_path: str, width: Optional[int], img_hash:str, crop: bool, priority: int):
        self.image_path = image_path
        self.width = width
        self.crop = crop
        self.priority = priority

        # Create a cache key based on the path and width
        self.cache_key = f"{image_path}_{width}_{'crop' if crop else 'nocrop'}_{img_hash}"
        
    def __lt__(self, other):
        """Compare jobs based on priority for the priority queue."""
        return self.priority < other.priority

def init_cache_system(cache_folder: str, upload_folder: str):
    """Initialize the background caching system."""
    global worker_threads, shutdown_event
    
    # Create cache directory if it doesn't exist
    os.makedirs(cache_folder, exist_ok=True)
    
    # Start worker threads
    for i in range(max_workers):
        thread = threading.Thread(
            target=cache_worker,
            args=(cache_folder, upload_folder),
            name=f"CacheWorker-{i}",
            daemon=True
        )
        thread.start()
        worker_threads.append(thread)
    
    print(f"Background caching system initialized with {max_workers} workers")

def shutdown_cache_system():
    """Shutdown the background caching system."""
    global shutdown_event, worker_threads
    
    # Signal all worker threads to shut down
    shutdown_event.set()
    
    # Wait for all worker threads to finish
    for thread in worker_threads:
        thread.join(timeout=2.0)
    
    print("Background caching system shut down")

def cache_worker(cache_folder: str, upload_folder: str):
    """Worker thread that processes cache jobs from the queue."""
    global active_workers, cached_images, cache_lock
    
    while not shutdown_event.is_set():
        try:
            # Get a job from the queue with a timeout
            job = cache_queue.get(timeout=1.0)
            
            with cache_lock:
                active_workers += 1
            
            try:
                # Check if this image is already cached
                cache_hash = hashlib.md5(job.cache_key.encode()).hexdigest()
                cache_path = os.path.join(cache_folder, f"{cache_hash}.webp")
                
                # Skip if already cached
                if os.path.exists(cache_path) or job.cache_key in cached_images:
                    print(f"Skipping already cached image: {job.image_path}")
                    continue
                
                # Add to cached_images set to prevent duplicate processing
                with cache_lock:
                    cached_images.add(job.cache_key)
                
                # Process the image
                file_path = os.path.join(upload_folder, job.image_path)
                if not os.path.exists(file_path):
                    print(f"Image file not found: {file_path}")
                    continue
                
                print(f"Background caching: {job.image_path} (width={job.width}, crop={job.crop})")
                
                # Open and process the image
                with Image.open(file_path) as img:
                    # Handle crop if needed (simplified - actual cropping would use the same logic as in server.py)
                    if job.crop:
                        # In a real implementation, we would apply the same crop logic as in server.py
                        # For now, we'll just use the original image
                        pass
                    
                    # Resize the image if width is specified
                    if job.width and img.size[0] > job.width:
                        h = int(job.width / (img.size[0]/img.size[1]))
                        img = img.resize((job.width, h), Image.BILINEAR)
                    
                    # Ensure height is not too large
                    if img.size[1] > 1080:
                        w = int(1080 * (img.size[0]/img.size[1]))
                        img = img.resize((w, 1080), Image.BILINEAR)
                    
                    # Save to cache
                    img.save(cache_path, format="WebP", quality=85)
                    print(f"Cached image saved: {cache_path}")
            
            except Exception as e:
                print(f"Error caching image {job.image_path}: {e}")
            
            finally:
                # Mark job as done and decrease active worker count
                cache_queue.task_done()
                with cache_lock:
                    active_workers -= 1
        
        except queue.Empty:
            # No jobs in the queue, just continue
            pass
        except Exception as e:
            print(f"Error in cache worker: {e}")

def queue_image_for_caching(image_path: str, width: Optional[int], img_hash:str, crop: bool,
                           db, upload_folder: str):
    """
    Queue an image for background caching and also queue related images.
    
    Args:
        image_path: Path to the image file
        width: Width to resize the image to
        crop: Whether to crop the image
        db: Database instance to get related images
        upload_folder: Path to the upload folder
    """
    # Skip if we already have too many active workers
    global active_workers, cache_lock
    with cache_lock:
        if active_workers >= max_workers:
            return
    
    try:
        # Get all images from the database
        database = db.get_database()
        all_images = database['images']
        
        # Find the current image in the database
        current_image = next((img for img in all_images if img['path'] == image_path), None)
        if not current_image:
            return
        
        # Get the folder ID of the current image
        folder_id = current_image.get('parent')
        
        # First, queue images in the same folder
        same_folder_images = [img for img in all_images 
                             if img['path'] != image_path and img.get('parent') == folder_id]
        
        for img in same_folder_images:
            img_hash = hashlib.md5(json.dumps(img).encode()).hexdigest()
            job = CacheJob(img['path'], width, img_hash, crop, PRIORITY_SAME_FOLDER)
            if job.cache_key not in cached_images:
                cache_queue.put(job)
        
        # Then, queue other images with the same width parameter
        other_images = [img for img in all_images 
                       if img['path'] != image_path and img.get('parent') != folder_id]
        
        for img in other_images:
            img_hash = hashlib.md5(json.dumps(img).encode()).hexdigest()
            job = CacheJob(img['path'], width, img_hash, crop, PRIORITY_OTHER_IMAGES)
            if job.cache_key not in cached_images:
                cache_queue.put(job)
                
    except Exception as e:
        print(f"Error queueing images for caching: {e}")

def is_image_cached(image_path: str, width: Optional[int], img_hash:str, crop: bool, cache_folder: str) -> bool:
    """Check if an image is already cached."""
    cache_key = f"{image_path}_{width}_{'crop' if crop else 'nocrop'}_{img_hash}"
    cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
    cache_path = os.path.join(cache_folder, f"{cache_hash}.webp")
    return os.path.exists(cache_path)

def clear_cached_images_tracking():
    """Clear the set of cached images (used for testing)."""
    global cached_images, cache_lock
    with cache_lock:
        cached_images.clear()