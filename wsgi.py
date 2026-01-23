"""
WSGI entry point for PythonAnywhere
"""
import sys
import os

# Add your project directory to the sys.path
project_home = '/home/DITT_ANVÄNDARNAMN/orchard-monitoring'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set up environment
os.environ['FLASK_ENV'] = 'production'

# Import the Flask app
from src.webhook_server import app as application
