import asyncio
import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("APP_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("TG_BOT_TOKEN", "123:ABC")
os.environ.setdefault("OWNER_ID", "1")
os.environ.setdefault("CHANNEL_ID", "-1001234567890")
os.environ.setdefault("FORCE_SUB_CHANNEL", "0")
os.environ.setdefault("DATABASE_URL", "mongodb://localhost:27017")

from aiohttp import web
from pyrogram.errors import FloodWait

import plugins.route as route


def encode_hash(msg_id: int, channel_id: int) -> str:
    value = f"get-{msg_id * abs(channel_id)}"
    return base64.urlsafe_b64encode(value.encode("ascii")).decode("ascii").rstrip("=")


class FakeMedia:
    def __init__(self, file_size, file_name="video.mp4", mime_type="video/mp4", file_unique_id="uniq"):
        self.file_size = file_size
        self.file_name = file_name
        self.mime_type = mime_type
        self.file_unique_id = file_unique_id


class FakeMessage:
    def __init__(self, media, chunks):
        self.document = media
        self.video = None
        self.empty = False
        self._chunks = chunks


class FakeClient:
    def __init__(self, name, channel_id):
        self.name = name
        self.db_channel = SimpleNamespace(id=channel_id)
        self.messages = {}
        self.get_messages_calls = 0
        self.stream_media_calls = 0
        self.raise_floodwait = False
        self.stream_delay = 0

    async def get_messages(self, chat_id, msg_id):
        self.get_messages_calls += 1
        return self.messages.get(msg_id)

    async def stream_media(self, message, offset=0, limit=1):
        self.stream_media_calls += 1
        if self.raise_floodwait:
            raise FloodWait(value=2)

        for chunk_index in range(offset, offset + limit):
            if self.stream_delay:
                await asyncio.sleep(self.stream_delay)
            yield message._chunks.get(chunk_index, b"")


class FakeRequest:
    def __init__(self, hash_id, app, method="GET", range_header=None, query=None):
        self.match_info = {"hash": hash_id}
        self.app = app
        self.method = method
        self.query = query or {}
        self.headers = {}
        if range_header:
            self.headers["Range"] = range_header


class FakeStreamResponse:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.body = b""
        self.prepared = False

    async def prepare(self, request):
        self.prepared = True
        return self

    async def write(self, data):
        self.body += data


class StreamingArchitectureSimulationTests(unittest.IsolatedAsyncioTestCase):
    CHANNEL_ID = -1001234567890

    async def asyncSetUp(self):
        route.META_CACHE._data.clear()
        route.CHUNK_CACHE._data.clear()
        route.IN_FLIGHT_CHUNKS.clear()

    def _build_app(self, clients):
        return {
            "client": clients[0],
            "stream_clients": clients,
            "client_semaphores": {c.name: asyncio.Semaphore(2) for c in clients},
            "client_cooldowns": {},
            "stream_settings": {"per_client_limit": 2},
            "now": route.time.monotonic,
        }

    async def test_consistent_hash_returns_stable_order(self):
        clients = [FakeClient("main", self.CHANNEL_ID), FakeClient("w1", self.CHANNEL_ID), FakeClient("w2", self.CHANNEL_ID)]
        app = self._build_app(clients)
        first = [c.name for c in route._pick_clients(app, shard_key=42)]
        second = [c.name for c in route._pick_clients(app, shard_key=42)]
        self.assertEqual(first, second)

    async def test_per_client_semaphore_limits_concurrency(self):
        client = FakeClient("main", self.CHANNEL_ID)
        app = self._build_app([client])
        sem = route._get_semaphore(app, client)
        max_seen = 0
        active = 0

        async def worker():
            nonlocal max_seen, active
            async with sem:
                active += 1
                max_seen = max(max_seen, active)
                await asyncio.sleep(0.05)
                active -= 1

        app["client_semaphores"][client.name] = asyncio.Semaphore(1)
        sem = route._get_semaphore(app, client)
        await asyncio.gather(worker(), worker(), worker())
        self.assertEqual(max_seen, 1)

    async def test_metadata_cache_hit_and_miss(self):
        client = FakeClient("main", self.CHANNEL_ID)
        media = FakeMedia(file_size=route.CHUNK_SIZE)
        client.messages[1] = FakeMessage(media, {0: b"a" * route.CHUNK_SIZE})

        await route._get_message(client, 1)
        await route._get_message(client, 1)
        self.assertEqual(client.get_messages_calls, 1)

    async def test_singleflight_deduplicates_chunk_fetch(self):
        client = FakeClient("main", self.CHANNEL_ID)
        client.stream_delay = 0.05
        media = FakeMedia(file_size=route.CHUNK_SIZE)
        message = FakeMessage(media, {0: b"x" * route.CHUNK_SIZE})
        key = ("uniq", 0)

        result1, result2 = await asyncio.gather(
            route._fetch_chunk_singleflight(client, message, key, 0, True),
            route._fetch_chunk_singleflight(client, message, key, 0, True),
        )
        self.assertEqual(result1, result2)
        self.assertEqual(client.stream_media_calls, 1)

    async def test_head_request_short_circuits_streaming(self):
        client = FakeClient("main", self.CHANNEL_ID)
        media = FakeMedia(file_size=2 * route.CHUNK_SIZE)
        client.messages[5] = FakeMessage(media, {0: b"a" * route.CHUNK_SIZE})
        app = self._build_app([client])
        hash_id = encode_hash(5, self.CHANNEL_ID)
        request = FakeRequest(hash_id, app, method="HEAD")

        response = await route.stream_handler(request)
        self.assertIsInstance(response, web.Response)
        self.assertEqual(response.status, 200)
        self.assertEqual(client.stream_media_calls, 0)

    async def test_range_request_streams_expected_bytes(self):
        client = FakeClient("main", self.CHANNEL_ID)
        chunk0 = b"a" * route.CHUNK_SIZE
        chunk1 = b"b" * route.CHUNK_SIZE
        media = FakeMedia(file_size=2 * route.CHUNK_SIZE)
        client.messages[7] = FakeMessage(media, {0: chunk0, 1: chunk1})
        app = self._build_app([client])
        hash_id = encode_hash(7, self.CHANNEL_ID)
        request = FakeRequest(hash_id, app, method="GET", range_header=f"bytes={route.CHUNK_SIZE//2}-{route.CHUNK_SIZE + 9}")

        with patch.object(route.web, "StreamResponse", FakeStreamResponse):
            response = await route.stream_handler(request)

        expected_len = (route.CHUNK_SIZE + 9) - (route.CHUNK_SIZE // 2) + 1
        self.assertEqual(response.status, 206)
        self.assertEqual(len(response.body), expected_len)
        self.assertTrue(response.body.startswith(b"a"))
        self.assertTrue(response.body.endswith(b"b"))

    async def test_floodwait_fallback_uses_next_worker(self):
        worker1 = FakeClient("w1", self.CHANNEL_ID)
        worker2 = FakeClient("w2", self.CHANNEL_ID)
        worker1.raise_floodwait = True

        media = FakeMedia(file_size=3 * route.CHUNK_SIZE)
        msg = FakeMessage(media, {2: b"a" * route.CHUNK_SIZE})
        worker1.messages[9] = msg
        worker2.messages[9] = msg

        app = self._build_app([worker1, worker2])
        hash_id = encode_hash(9, self.CHANNEL_ID)
        request = FakeRequest(hash_id, app, method="GET", range_header=f"bytes={2 * route.CHUNK_SIZE}-{2 * route.CHUNK_SIZE + 99}")

        with (
            patch.object(route, "_pick_clients", return_value=[worker1, worker2]),
            patch.object(route, "STREAM_HOT_CACHE_BYTES", route.CHUNK_SIZE),
            patch.object(route.web, "StreamResponse", FakeStreamResponse),
        ):
            response = await route.stream_handler(request)

        self.assertEqual(response.status, 206)
        self.assertGreater(worker1.stream_media_calls, 0)
        self.assertGreater(worker2.stream_media_calls, 0)
        self.assertIn("w1", app["client_cooldowns"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
