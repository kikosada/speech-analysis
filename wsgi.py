import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from app.app import app

if __name__ == "__main__":
    app.run() 