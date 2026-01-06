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
    
    # 👇 1. CATCH THE CUSTOM NAME FROM URL (e.g. ?name=The-Flash-S01E01)
    custom_name = request.query.get('name')

    try:
        string = await decode(hash_id)
        argument = string.split("-")
        msg_id = int(int(argument[1]) / abs(client.db_channel.id))
    except:
        raise web.HTTPNotFound()

    # Get the Message from Telegram
    try:
        message = await client.get_messages(client.db_channel.id, msg_id)
    except:
        raise web.HTTPNotFound()

    # Identify if it's a Document or a Video
    media = message.document or message.video
    
    if not message or not media:
        raise web.HTTPNotFound()

    # 👇 2. SMART RENAMING LOGIC
    # Get the original filename from Telegram to find the extension (mp4/mkv/avi)
    # We use getattr() because sometimes 'file_name' might be missing on video objects
    original_name = getattr(media, "file_name", f"video_{msg_id}.mp4") or f"video_{msg_id}.mp4"

    if custom_name:
        # Determine extension from the REAL file on Telegram
        if "." in original_name:
            ext = original_name.split(".")[-1]
        else:
            ext = "mp4" # Fallback if Telegram file has no extension

        # Combine Flask's clean name + Real extension
        # If custom_name is "The-Flash-S01E01" and ext is "mkv" -> "The-Flash-S01E01.mkv"
        if not custom_name.endswith(f".{ext}"):
            file_name = f"{custom_name}.{ext}"
        else:
            file_name = custom_name
    else:
        # If no name provided in URL, use the original filename
        file_name = original_name

    file_size = media.file_size
    mime_type = media.mime_type or "video/mp4"

    # Set Headers with the NEW Name
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
