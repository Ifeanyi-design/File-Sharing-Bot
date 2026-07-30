import asyncio
import hashlib
import json
import logging
import math
import re
import time
from collections import OrderedDict

from aiohttp import web
from pyrogram.errors import FloodWait

from config import (
    STREAM_CHUNK_CACHE_CHUNKS,
    STREAM_CHUNK_CACHE_TTL,
    STREAM_HOT_CACHE_BYTES,
    STREAM_META_CACHE_SIZE,
    STREAM_META_CACHE_TTL,
)
from helper_func import decode

routes = web.RouteTableDef()
CHUNK_SIZE = 1048576
STREAM_LOGGER = logging.getLogger("stream.observability")


class TTLCacheLRU:
    def __init__(self, max_size: int, ttl: int):
        self.max_size = max(1, max_size)
        self.ttl = max(1, ttl)
        self._data = OrderedDict()

    def get(self, key):
        item = self._data.get(key)
        if not item:
            return None
        expires_at, value = item
        now = time.monotonic()
        if expires_at <= now:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key, value):
        expires_at = time.monotonic() + self.ttl
        if key in self._data:
            self._data.pop(key, None)
        self._data[key] = (expires_at, value)
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)


META_CACHE = TTLCacheLRU(STREAM_META_CACHE_SIZE, STREAM_META_CACHE_TTL)
CHUNK_CACHE = TTLCacheLRU(STREAM_CHUNK_CACHE_CHUNKS, STREAM_CHUNK_CACHE_TTL)
IN_FLIGHT_CHUNKS = {}
IN_FLIGHT_LOCK = asyncio.Lock()


def _pick_clients(app, shard_key):
    clients = app.get("stream_clients") or [app["client"]]
    if not clients:
        return []

    now = app.get("now", time.monotonic)()
    cooldowns = app.get("client_cooldowns", {})
    healthy_clients = [c for c in clients if cooldowns.get(c.name, 0) <= now]
    if not healthy_clients:
        healthy_clients = clients

    digest = hashlib.md5(str(shard_key).encode("utf-8")).hexdigest()
    start_index = int(digest, 16) % len(healthy_clients)
    return healthy_clients[start_index:] + healthy_clients[:start_index]


def _metrics(app):
    if app is None or not hasattr(app, "get"):
        return None
    return app.get("stream_metrics")


def _inc(app, key, delta=1):
    metrics = _metrics(app)
    if metrics is not None:
        metrics[key] = metrics.get(key, 0) + delta


def _inc_nested(app, parent_key, child_key, delta=1):
    metrics = _metrics(app)
    if metrics is None:
        return
    parent = metrics.setdefault(parent_key, {})
    parent[child_key] = parent.get(child_key, 0) + delta


def _get_semaphore(app, client):
    semaphores = app["client_semaphores"]
    semaphore = semaphores.get(client.name)
    if semaphore is None:
        limit = app.get("stream_settings", {}).get("per_client_limit", 3)
        semaphore = asyncio.Semaphore(limit)
        semaphores[client.name] = semaphore
    return semaphore


def _mark_cooldown(app, client_name, seconds):
    wait_seconds = max(1, int(seconds))
    app["client_cooldowns"][client_name] = app.get("now", time.monotonic)() + wait_seconds


async def _get_message(client, msg_id: int):
    cache_key = (client.name, client.db_channel.id, msg_id)
    message = META_CACHE.get(cache_key)
    if message is not None:
        _inc_nested(getattr(client, "stream_app", None), "meta_cache", "hits")
        return message

    _inc_nested(getattr(client, "stream_app", None), "meta_cache", "misses")
    message = await client.get_messages(client.db_channel.id, msg_id)
    if not message or message.empty:
        raise web.HTTPNotFound()

    META_CACHE.set(cache_key, message)
    return message


async def _fetch_chunk_singleflight(client, message, chunk_key, chunk_index: int, cache_enabled: bool):
    if cache_enabled:
        cached_chunk = CHUNK_CACHE.get(chunk_key)
        if cached_chunk is not None:
            _inc_nested(getattr(client, "stream_app", None), "chunk_cache", "hits")
            return cached_chunk
        _inc_nested(getattr(client, "stream_app", None), "chunk_cache", "misses")

    if not cache_enabled:
        async for chunk in client.stream_media(message, offset=chunk_index, limit=1):
            return chunk
        return b""

    created = False
    async with IN_FLIGHT_LOCK:
        future = IN_FLIGHT_CHUNKS.get(chunk_key)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            IN_FLIGHT_CHUNKS[chunk_key] = future
            created = True

    if not created:
        return await future

    try:
        chunk_data = b""
        async for chunk in client.stream_media(message, offset=chunk_index, limit=1):
            chunk_data = chunk
            break

        if chunk_data:
            CHUNK_CACHE.set(chunk_key, chunk_data)
        future.set_result(chunk_data)
        return chunk_data
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        async with IN_FLIGHT_LOCK:
            IN_FLIGHT_CHUNKS.pop(chunk_key, None)


@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("MaxCinema Server is Running!")


@routes.get("/metrics", allow_head=True)
async def metrics_handler(request):
    metrics = request.app.get("stream_metrics", {})
    worker_active = metrics.get("worker_active_streams", {})
    worker_requests = metrics.get("worker_requests", {})
    worker_success = metrics.get("worker_success", {})
    worker_fallbacks = metrics.get("worker_fallbacks", {})
    streams_completed = metrics.get("streams_completed", 0)

    response = {
        "active_streams": metrics.get("active_streams", 0),
        "requests_total": metrics.get("requests_total", 0),
        "workers": {
            "active_streams": worker_active,
            "requests": worker_requests,
            "success": worker_success,
            "fallbacks": worker_fallbacks,
        },
        "meta_cache": metrics.get("meta_cache", {"hits": 0, "misses": 0}),
        "chunk_cache": metrics.get("chunk_cache", {"hits": 0, "misses": 0}),
        "fallbacks": metrics.get("fallbacks", 0),
        "floodwaits": metrics.get("floodwaits", 0),
        "streams_completed": streams_completed,
        "streams_failed": metrics.get("streams_failed", 0),
        "bytes_streamed_total": metrics.get("bytes_streamed_total", 0),
        "avg_first_byte_seconds": (
            metrics.get("first_byte_seconds_sum", 0.0) / streams_completed if streams_completed else 0.0
        ),
        "avg_stream_duration_seconds": (
            metrics.get("stream_duration_seconds_sum", 0.0) / streams_completed if streams_completed else 0.0
        ),
        "avg_throughput_bytes_per_sec": (
            metrics.get("throughput_bytes_per_sec_sum", 0.0) / streams_completed if streams_completed else 0.0
        ),
        "avg_semaphore_wait_seconds": (
            metrics.get("semaphore_wait_seconds_sum", 0.0) / metrics.get("semaphore_acquires", 1)
            if metrics.get("semaphore_acquires", 0)
            else 0.0
        ),
    }
    return web.json_response(response)


@routes.get(r"/watch/{hash}", allow_head=True)
async def stream_handler(request):
    request_start = time.monotonic()
    _inc(request.app, "requests_total")
    _inc(request.app, "active_streams")
    hash_id = request.match_info["hash"]

    try:
        string = await decode(hash_id)
        argument = string.split("-")
        main_client = request.app["client"]
        msg_id = int(int(argument[1]) / abs(main_client.db_channel.id))
    except Exception:
        _inc(request.app, "active_streams", -1)
        raise web.HTTPNotFound()

    selected_clients = _pick_clients(request.app, shard_key=msg_id)
    if not selected_clients:
        _inc(request.app, "active_streams", -1)
        raise web.HTTPServiceUnavailable(text="No streaming clients available")

    last_error = None
    first_byte_time = None
    selected_worker_name = None
    bytes_streamed = 0
    stream_interrupted = False
    selected_clients_count = len(selected_clients)

    for index, client in enumerate(selected_clients):
        client.stream_app = request.app
        semaphore = _get_semaphore(request.app, client)
        _inc_nested(request.app, "worker_requests", client.name)
        wait_started = time.monotonic()

        async with semaphore:
            wait_time = time.monotonic() - wait_started
            _inc(request.app, "semaphore_acquires")
            _inc(request.app, "semaphore_wait_seconds_sum", wait_time)
            _inc_nested(request.app, "worker_active_streams", client.name)
            try:
                message = await _get_message(client, msg_id)
                media = message.document or message.video
                if not media:
                    raise web.HTTPNotFound()

                file_size = media.file_size
                mime_type = media.mime_type or "video/mp4"

                custom_name = request.query.get("name")
                original_name = getattr(media, "file_name", f"video_{msg_id}.mp4") or f"video_{msg_id}.mp4"

                if custom_name:
                    ext = original_name.split(".")[-1] if "." in original_name else "mp4"
                    file_name = custom_name if custom_name.endswith(f".{ext}") else f"{custom_name}.{ext}"
                else:
                    file_name = original_name

                range_header = request.headers.get("Range")
                from_bytes = 0
                until_bytes = file_size - 1
                status_code = 200

                if range_header:
                    range_match = re.search(r"(\d+)-(\d*)", range_header)
                    if range_match:
                        from_bytes = int(range_match.group(1))
                        if range_match.group(2):
                            until_bytes = int(range_match.group(2))

                    if from_bytes >= file_size:
                        return web.Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})

                    until_bytes = min(until_bytes, file_size - 1)
                    status_code = 206

                content_length = until_bytes - from_bytes + 1

                headers = {
                    "Content-Type": mime_type,
                    "Content-Disposition": f'attachment; filename="{file_name}"',
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
                    "Content-Length": str(content_length),
                }

                if request.method == "HEAD":
                    _inc_nested(request.app, "worker_active_streams", client.name, -1)
                    _inc(request.app, "active_streams", -1)
                    return web.Response(status=status_code, headers=headers)

                response = web.StreamResponse(status=status_code, headers=headers)
                await response.prepare(request)

                chunk_start_index = from_bytes // CHUNK_SIZE
                chunk_end_index = until_bytes // CHUNK_SIZE
                offset_in_first_chunk = from_bytes % CHUNK_SIZE
                remaining = content_length
                hot_cache_chunks = max(1, math.ceil(STREAM_HOT_CACHE_BYTES / CHUNK_SIZE))
                file_key = getattr(media, "file_unique_id", None) or getattr(media, "file_id", str(msg_id))

                try:
                    for chunk_index in range(chunk_start_index, chunk_end_index + 1):
                        cache_enabled = chunk_index < hot_cache_chunks
                        chunk_key = (file_key, chunk_index)
                        chunk = await _fetch_chunk_singleflight(
                            client=client,
                            message=message,
                            chunk_key=chunk_key,
                            chunk_index=chunk_index,
                            cache_enabled=cache_enabled,
                        )

                        if not chunk:
                            break

                        if chunk_index == chunk_start_index and offset_in_first_chunk:
                            chunk = chunk[offset_in_first_chunk:]

                        if remaining <= 0:
                            break

                        if len(chunk) >= remaining:
                            to_write = chunk[:remaining]
                            if first_byte_time is None and to_write:
                                first_byte_time = time.monotonic()
                            await response.write(to_write)
                            bytes_streamed += len(to_write)
                            remaining = 0
                            break

                        if first_byte_time is None and chunk:
                            first_byte_time = time.monotonic()
                        await response.write(chunk)
                        bytes_streamed += len(chunk)
                        remaining -= len(chunk)
                except FloodWait:
                    raise
                except Exception:
                    stream_interrupted = True
                    pass

                selected_worker_name = client.name
                _inc_nested(request.app, "worker_success", client.name)
                _inc_nested(request.app, "worker_active_streams", client.name, -1)
                _inc(request.app, "active_streams", -1)
                duration = max(time.monotonic() - request_start, 1e-6)
                throughput = bytes_streamed / duration
                if first_byte_time is not None:
                    _inc(request.app, "first_byte_seconds_sum", first_byte_time - request_start)
                _inc(request.app, "stream_duration_seconds_sum", duration)
                _inc(request.app, "bytes_streamed_total", bytes_streamed)
                _inc(request.app, "throughput_bytes_per_sec_sum", throughput)
                _inc(request.app, "streams_completed")
                STREAM_LOGGER.info(
                    json.dumps(
                        {
                            "event": "stream_complete",
                            "hash": hash_id,
                            "worker": selected_worker_name,
                            "status": status_code,
                            "bytes_streamed": bytes_streamed,
                            "first_byte_seconds": (first_byte_time - request_start) if first_byte_time else None,
                            "duration_seconds": duration,
                            "throughput_bps": throughput,
                            "semaphore_wait_seconds": wait_time,
                            "selected_clients": selected_clients_count,
                            "stream_interrupted": stream_interrupted,
                            "range": bool(range_header),
                        }
                    )
                )
                return response

            except FloodWait as flood_wait:
                last_error = flood_wait
                _inc(request.app, "floodwaits")
                _mark_cooldown(request.app, client.name, getattr(flood_wait, "value", 3))
                _inc_nested(request.app, "worker_active_streams", client.name, -1)
                if index < selected_clients_count - 1:
                    _inc(request.app, "fallbacks")
                    _inc_nested(request.app, "worker_fallbacks", client.name)
                continue
            except web.HTTPNotFound:
                _inc_nested(request.app, "worker_active_streams", client.name, -1)
                _inc(request.app, "active_streams", -1)
                raise
            except Exception as exc:
                last_error = exc
                _inc_nested(request.app, "worker_active_streams", client.name, -1)
                if index < selected_clients_count - 1:
                    _inc(request.app, "fallbacks")
                    _inc_nested(request.app, "worker_fallbacks", client.name)
                continue

    _inc(request.app, "active_streams", -1)
    _inc(request.app, "streams_failed")
    STREAM_LOGGER.warning(
        json.dumps(
            {
                "event": "stream_failed",
                "hash": hash_id,
                "error": type(last_error).__name__ if last_error else "UnknownError",
                "selected_clients": selected_clients_count,
            }
        )
    )
    if isinstance(last_error, FloodWait):
        raise web.HTTPTooManyRequests(text="All streaming workers are rate-limited, please retry soon.")
    raise web.HTTPServiceUnavailable(text="Unable to stream media right now.")
