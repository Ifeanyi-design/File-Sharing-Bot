#(©)Codexbotz
from aiohttp import web
from .route import routes

async def web_server(client):
    web_app = web.Application(client_max_size=30000000)
    # This is the Secret Sauce: We attach the client to the app
    web_app['client'] = client 
    web_app.add_routes(routes)
    return web_app
