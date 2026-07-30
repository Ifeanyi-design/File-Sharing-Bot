#(©)Codexbotz
import asyncio
import time
from aiohttp import web
from .route import routes
from config import STREAM_CONCURRENCY_PER_CLIENT

async def web_server(client):
    web_app = web.Application(client_max_size=30000000)
    web_app['client'] = client
    web_app['stream_clients'] = [client]
    web_app['client_semaphores'] = {client.name: asyncio.Semaphore(STREAM_CONCURRENCY_PER_CLIENT)}
    web_app['client_cooldowns'] = {}
    web_app['stream_settings'] = {"per_client_limit": STREAM_CONCURRENCY_PER_CLIENT}
    web_app['stream_metrics'] = {
        "requests_total": 0,
        "active_streams": 0,
        "worker_requests": {},
        "worker_success": {},
        "worker_active_streams": {},
        "worker_fallbacks": {},
        "meta_cache": {"hits": 0, "misses": 0},
        "chunk_cache": {"hits": 0, "misses": 0},
        "fallbacks": 0,
        "floodwaits": 0,
        "streams_completed": 0,
        "streams_failed": 0,
        "bytes_streamed_total": 0,
        "first_byte_seconds_sum": 0.0,
        "stream_duration_seconds_sum": 0.0,
        "throughput_bytes_per_sec_sum": 0.0,
        "semaphore_wait_seconds_sum": 0.0,
        "semaphore_acquires": 0,
    }
    web_app['now'] = time.monotonic
    web_app.add_routes(routes)
    return web_app
