import sys
import os

# Añadir el directorio src al PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .app.app import app

if __name__ == "__main__":
    app.run() 