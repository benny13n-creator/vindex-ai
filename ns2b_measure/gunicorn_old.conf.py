import os

# Workers: Render sets $WEB_CONCURRENCY based on instance type; default 4
workers = int(os.getenv("WEB_CONCURRENCY", 4))
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts — AI pozivi mogu trajati do 90s
timeout = 120
graceful_timeout = 30
keepalive = 5

# Sprečava memory leak — restart workera posle 1000 zahteva
max_requests = 1000
max_requests_jitter = 100

bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
accesslog = "-"
errorlog  = "-"
loglevel  = "info"
