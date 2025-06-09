import multiprocessing
import os

port = int(os.environ.get("PORT", 10000))
bind = f"0.0.0.0:{port}"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 120
keepalive = 5
errorlog = '-'
loglevel = 'info'
accesslog = '-'

# Configuración de workers
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50 