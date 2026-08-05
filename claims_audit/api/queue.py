"""Redis/RQ queue setup. Long-running ingestion and report jobs must run
as background jobs with visible progress/status, not inside a single
blocking HTTP request — see build prompt, "Handling very large data
volumes". RQ (backed by Redis, both declared in docker-compose.yml) gives
us that without requiring a separately-hosted queue service."""
from redis import Redis
from rq import Queue

from api.config import settings

redis_conn = Redis.from_url(settings.REDIS_URL)
default_queue = Queue("default", connection=redis_conn)
