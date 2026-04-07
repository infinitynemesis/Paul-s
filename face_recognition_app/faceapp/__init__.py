"""Face recognition app — train it on people you know, recognize them anywhere."""

from .database import FaceDatabase
from .recognizer import Recognizer

__all__ = ["FaceDatabase", "Recognizer"]
