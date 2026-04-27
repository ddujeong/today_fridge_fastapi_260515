from redis.asyncio import Redis, ConnectionPool
from app.core.config import settings

redis_pool = ConnectionPool.from_url(
    f"redis://{settings.redis_host}:{settings.redis_port}/0",
    max_connections=50,
    decode_responses=True,
)


async def get_redis() -> Redis:
    return Redis(connection_pool=redis_pool)
