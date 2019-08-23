import os

class Photos:
    def __init__(self):
        pass
    """
    Read photos from photo folder
    """
    def get_photos(self):
        photos = [name for name in os.listdir("static/images/gallery")]
        return photos
