import math
import re
from aiohttp import web
from helper_func import decode, get_messages

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("MaxCinema Server is Running!")

@routes.get(r"/watch/{hash}", allow_head=True)
async def stream_handler(request):
    hash_id = request.match_info['hash']
    client = request.app['client'] 

    # 1. Decode Hash
    try:
        string = await decode(hash_id)
        argument = string.split("-")
        msg_id = int(int(argument[1]) / abs(client.db_channel.id))
    except:
        raise web.HTTPNotFound()

    # 2. Get Message
    try:
        message = await client.get_messages(client.db_channel.id, msg_id)
    except:
        raise web.HTTPNotFound()

    media = message.document or message.video
    if not message or not media:
        raise web.HTTPNotFound()

    # 3. File Details
    file_size = media.file_size
    mime_type = media.mime_type or "video/mp4"
    
    # Custom Name Logic
    custom_name = request.query.get('name')
    original_name = getattr(media, "file_name", f"video_{msg_id}.mp4") or f"video_{msg_id}.mp4"

    if custom_name:
        if "." in original_name:
            ext = original_name.split(".")[-1]
        else:
            ext = "mp4"
        if not custom_name.endswith(f".{ext}"):
            file_name = f"{custom_name}.{ext}"
        else:
            file_name = custom_name
    else:
        file_name = original_name

    # ==============================
    # 🛑 RESUME SUPPORT (Range Header)
    # ==============================
    range_header = request.headers.get("Range")
    
    # Defaults
    from_bytes = 0
    until_bytes = file_size - 1
    status_code = 200

    if range_header:
        try:
            # Better Regex parsing for stability
            range_match = re.search(r'(\d+)-(\d*)', range_header)
            if range_match:
                from_bytes = int(range_match.group(1))
                if range_match.group(2):
                    until_bytes = int(range_match.group(2))
            
            # Sanity Check
            if from_bytes >= file_size:
                return web.Response(status=416, headers={'Content-Range': f'bytes */{file_size}'})

            status_code = 206 # Partial Content
        except Exception:
            pass

    # Calculate exact length to send
    content_length = until_bytes - from_bytes + 1
    
    # Pyrogram Chunk Size (1MB)
    CHUNK_SIZE = 1048576 
    
    # Calculate Start Index & Offset
    chunk_start_index = from_bytes // CHUNK_SIZE
    offset_in_first_chunk = from_bytes % CHUNK_SIZE
    
    # ⚠️ OPTIMIZATION: Calculate how many chunks we actally need
    # This prevents Pyrogram from downloading the whole file if we only need a small part
    bytes_needed = content_length + offset_in_first_chunk
    chunks_needed = math.ceil(bytes_needed / CHUNK_SIZE)

    # Headers
    headers = {
        'Content-Type': mime_type,
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Accept-Ranges': 'bytes',
        'Content-Range': f'bytes {from_bytes}-{until_bytes}/{file_size}',
        'Content-Length': str(content_length)
    }

    resp = web.StreamResponse(status=status_code, headers=headers)
    
    # ⬇️ ADD THIS LINE HERE ⬇️
    resp.enable_chunked_encoding() 
    # ⬆️ THIS KEEPS THE CONNECTION ALIVE ⬆️
    
    await resp.prepare(request)

    try:
        # We pass 'limit=chunks_needed' to stop Pyrogram from over-fetching
        async for chunk in client.stream_media(message, offset=chunk_start_index, limit=chunks_needed):
            
            # Handle first chunk offset (Resume logic)
            if offset_in_first_chunk > 0:
                chunk = chunk[offset_in_first_chunk:]
                offset_in_first_chunk = 0 

            # Write only what is requested
            if content_length > 0:
                if len(chunk) >= content_length:
                    await resp.write(chunk[:content_length])
                    break
                else:
                    await resp.write(chunk)
                    content_length -= len(chunk)
            else:
                break
                
    except Exception:
        # Connection dropped by user (normal behavior)
        pass

    return resp
