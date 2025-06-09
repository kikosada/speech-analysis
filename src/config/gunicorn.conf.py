# gunicorn.conf.py
# Configuración para aumentar el timeout a 300 segundos
 
bind = "0.0.0.0:10000"
workers = 4
timeout = 120
pythonpath = "src"
wsgi_app = "app.app:app" 