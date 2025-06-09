import multiprocessing

# Número de workers
workers = multiprocessing.cpu_count() * 2 + 1

# Configuración del servidor
bind = "0.0.0.0:10000"
timeout = 300  # 5 minutos
keepalive = 5

# Configuración de logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Configuración de workers
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50 