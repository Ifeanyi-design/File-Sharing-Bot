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
    web_app['now'] = time.monotonic
    web_app.add_routes(routes)
    return web_app
