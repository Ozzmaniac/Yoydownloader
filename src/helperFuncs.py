from functools import lru_cache
import sys
import os
from PIL import Image, ImageFont

# === Utility functions ===
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# LRU cache for images and fonts
@lru_cache(maxsize=256)
def load_image(path):
    return Image.open(path).convert("RGBA")

@lru_cache(maxsize=64)
def get_font(size):
    return ImageFont.truetype(resource_path("assets/HyliaSerif.otf"), size)