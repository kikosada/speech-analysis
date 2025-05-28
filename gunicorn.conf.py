# gunicorn.conf.py
# Configuración para aumentar el timeout a 300 segundos

bind = "0.0.0.0:10000"
timeout = 300
workers = 1  # Puedes aumentar si tu servidor tiene más CPU/RAM 