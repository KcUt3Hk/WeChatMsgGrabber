"""
Image deduplication service using dHash (Difference Hash).
Implemented without external 'imagehash' dependency.
"""
import logging
import cv2
import numpy as np
from PIL import Image
from typing import Set, Dict, List

class ImageDeduplicator:
    """
    Handles image deduplication using perceptual hashing (dHash).
    Maintains a session-level registry of seen image hashes.
    """
    
    def __init__(self, threshold: int = 5):
        """
        Initialize the deduplicator.
        
        Args:
            threshold: Hamming distance threshold for declaring a duplicate.
                       Default is 5 (approx 95% similarity for 64-bit hash).
                       Lower value means stricter matching.
        """
        self.logger = logging.getLogger(__name__)
        self.threshold = threshold
        # Store hashes as integers
        self.seen_hashes: List[int] = []
        self.seen_paths: Dict[int, str] = {} 

    def _compute_dhash(self, image: Image.Image) -> int:
        """
        Compute dHash of the image.
        1. Resize to 9x8.
        2. Convert to grayscale.
        3. Compare adjacent pixels.
        """
        # Resize to 9x8 (width=9, height=8)
        # We need 8 rows and 8 differences per row -> 64 bits
        img = image.resize((9, 8), Image.Resampling.LANCZOS).convert('L')
        pixels = list(img.getdata())
        
        diff = []
        for row in range(8):
            for col in range(8):
                # pixel index
                left = row * 9 + col
                right = left + 1
                diff.append(pixels[left] > pixels[right])
        
        # Convert boolean list to integer
        decimal_value = 0
        for index, value in enumerate(diff):
            if value:
                decimal_value += 2**index
        
        return decimal_value

    def _hamming_distance(self, h1: int, h2: int) -> int:
        """Calculate Hamming distance between two 64-bit integers."""
        x = h1 ^ h2
        return bin(x).count('1')

    def is_duplicate(self, image: Image.Image) -> bool:
        """
        Check if the image is a duplicate of a previously seen image.
        
        Args:
            image: PIL Image object.
            
        Returns:
            True if duplicate, False otherwise.
        """
        if image is None:
            return False
            
        try:
            current_hash = self._compute_dhash(image)
            
            # Check against seen hashes
            for seen_h in self.seen_hashes:
                dist = self._hamming_distance(current_hash, seen_h)
                if dist <= self.threshold:
                    self.logger.info(f"Duplicate found: dist={dist} (threshold={self.threshold})")
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"Deduplication check failed: {e}")
            return False

    def add_image(self, image: Image.Image, file_path: str = ""):
        """
        Register an image as seen.
        
        Args:
            image: PIL Image object.
            file_path: Optional path where the image was saved.
        """
        try:
            h = self._compute_dhash(image)
            # Avoid adding if it's already very close to an existing one?
            # Or just add it. Adding it is safer for "seen" history.
            self.seen_hashes.append(h)
            if file_path:
                self.seen_paths[h] = file_path
        except Exception as e:
            self.logger.error(f"Failed to register image hash: {e}")

    def clear(self):
        """Clear the seen images history."""
        self.seen_hashes.clear()
        self.seen_paths.clear()
