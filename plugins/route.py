#(©)Codexbotz
from aiohttp import web
import math
from helper_func import decode, get_messages

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("MaxCinema Server is Running!")

@routes.get(r"/watch/{hash}", allow_head=True)
async def stream_handler(request):
    hash_id = request.match_info['hash']
    client = request.app['client'] 
    
    try:
        string = await decode(hash_id)
        argument = string.split("-")
        msg_id = int(int(argument[1]) / abs(client.db_channel.id))
    except:
        raise web.HTTPNotFound()

    # 1. Get the Message
    try:
        message = await client.get_messages(client.db_channel.id, msg_id)
    except:
        raise web.HTTPNotFound()

    # 2. Identify if it's a Document or a Video (The Fix)
    media = message.document or message.video
    
    if not message or not media:
        raise web.HTTPNotFound()

    # 3. Use the 'media' object (works for both MP4 and MKV)
    file_name = media.file_name or f"video_{msg_id}.mp4" # Fallback name
    file_size = media.file_size
    mime_type = media.mime_type or "video/mp4"

    # Set Headers
    headers = {
        'Content-Type': mime_type,
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Length': str(file_size)
    }

    # Stream the file
    resp = web.StreamResponse(status=200, headers=headers)
    await resp.prepare(request)

    async for chunk in client.stream_media(message, limit=0, offset=0):
        await resp.write(chunk)
    
    return resp
