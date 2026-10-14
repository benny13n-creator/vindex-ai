import os

# Workers: tacno $WEB_CONCURRENCY ako je postavljen, inace JEDAN radnik.
# NS2 (2026-10-14): na 512 MiB instanci izmereno -- 4 radnika ne mogu ni da miruju
# (OOM petlja), 2 radnika padaju na paru OCR poslova, 1 radnik prezivljava.
# Podrazumevana vrednost je zato 1 (ista kao `workers` polje u /health u api.py),
# da izostanak promenljive nikad ne udvostruci/ucetvorostruci memoriju.
# Vise radnika = svesna odluka: WEB_CONCURRENCY na vecoj instanci.
workers = int(os.getenv("WEB_CONCURRENCY", 1))
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
