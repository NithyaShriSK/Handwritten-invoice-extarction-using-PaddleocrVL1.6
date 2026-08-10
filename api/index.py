import sys
import os

# Append the parent directory to sys.path so we can import backend_app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_app import app
