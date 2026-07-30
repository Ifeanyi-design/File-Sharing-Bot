import asyncio
import hashlib
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
        return message

    message = await client.get_messages(client.db_channel.id, msg_id)
    if not message or message.empty:
        raise web.HTTPNotFound()

    META_CACHE.set(cache_key, message)
    return message


async def _fetch_chunk_singleflight(client, message, chunk_key, chunk_index: int, cache_enabled: bool):
    if cache_enabled:
        cached_chunk = CHUNK_CACHE.get(chunk_key)
        if cached_chunk is not None:
            return cached_chunk

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


@routes.get(r"/watch/{hash}", allow_head=True)
async def stream_handler(request):
    hash_id = request.match_info["hash"]

    try:
        string = await decode(hash_id)
        argument = string.split("-")
        main_client = request.app["client"]
        msg_id = int(int(argument[1]) / abs(main_client.db_channel.id))
    except Exception:
        raise web.HTTPNotFound()

    selected_clients = _pick_clients(request.app, shard_key=msg_id)
    if not selected_clients:
        raise web.HTTPServiceUnavailable(text="No streaming clients available")

    last_error = None

    for client in selected_clients:
        semaphore = _get_semaphore(request.app, client)

        async with semaphore:
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
                            await response.write(chunk[:remaining])
                            remaining = 0
                            break

                        await response.write(chunk)
                        remaining -= len(chunk)
                except Exception:
                    pass

                return response

            except FloodWait as flood_wait:
                last_error = flood_wait
                _mark_cooldown(request.app, client.name, getattr(flood_wait, "value", 3))
                continue
            except web.HTTPNotFound:
                raise
            except Exception as exc:
                last_error = exc
                continue

    if isinstance(last_error, FloodWait):
        raise web.HTTPTooManyRequests(text="All streaming workers are rate-limited, please retry soon.")
    raise web.HTTPServiceUnavailable(text="Unable to stream media right now.")
