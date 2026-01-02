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
    client = request.app['client'] # Get the bot client we passed earlier
    
    try:
        # Decode the Hash to get Message ID
        base64_string = hash_id
        string = await decode(base64_string)
        argument = string.split("-")
        msg_id = int(int(argument[1]) / abs(client.db_channel.id))
    except:
        raise web.HTTPNotFound()

    # Get the Message from Telegram
    try:
        message = await client.get_messages(client.db_channel.id, msg_id)
        if not message or not message.document:
             raise web.HTTPNotFound()
    except:
        raise web.HTTPNotFound()

    # Prepare the File for Streaming
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size

    # Set Headers so Browser knows it's a download
    headers = {
        'Content-Type': message.document.mime_type,
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Length': str(file_size)
    }

    # Stream the file (Directly from Telegram to Browser)
    resp = web.StreamResponse(status=200, headers=headers)
    await resp.prepare(request)

    async for chunk in client.stream_media(message, limit=0, offset=0):
        await resp.write(chunk)
    
    return resp
