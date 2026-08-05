"""
Background job worker. Runs as a separate process/container from the API
(see docker-compose.yml's `worker` service) so long-running ingestion and
report generation never block request handling, and survive an API
process restart.

Run directly with: python worker.py
"""
from rq import Worker

from api.queue import redis_conn, default_queue
from api.db import wait_for_db, apply_schema

if __name__ == "__main__":
    wait_for_db()
    apply_schema()
    worker = Worker([default_queue], connection=redis_conn)
    worker.work()
