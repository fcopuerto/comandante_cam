"""Add detection_service/ to sys.path so flat imports work when running pytest
from the project root (outside Docker). Inside Docker PYTHONPATH=/app already
covers this."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
