import pyromod.listen 
from pyrogram import idle
from pyrogram.errors import FloodWait
from bot import Bot, Worker
from config import WORKER_TOKENS, PORT
from aiohttp import web
import asyncio

# --- DUMMY SERVER (The Life Saver) ---
async def start_dummy_server(reason="Unknown"):
    print(f"🏥 STARTING DUMMY SERVER (Reason: {reason})")
    dummy_app = web.Application()
    dummy_app.router.add_get('/', lambda r: web.Response(text=f"❄️ Server Cooling Down. Reason: {reason}"))
    runner = web.AppRunner(dummy_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"✅ Dummy Health Check running on Port {PORT}")
    return runner

async def start_cluster():
    main_bot = Bot()
    main_bot.name = "Main_Bot"
    
    workers = []
    for i, token in enumerate(WORKER_TOKENS):
        worker_name = f"Worker_{i+1}"
        workers.append(Worker(token=token, name=worker_name))
    
    all_apps = [main_bot] + workers
    print(f"🚀 Starting Cluster with {len(all_apps)} Bots...")
    
    main_bot_started = False

    for app in all_apps:
        try:
            await app.start()
            print(f"✅ {app.name} Started Successfully!")
            if app.name == "Main_Bot":
                main_bot_started = True
            
        except FloodWait as e:
            wait_time = e.value + 10
            print(f"⚠️ FLOOD WAIT for {app.name}. Sleeping {wait_time}s...")
            
            # If Main Bot is banned, START DUMMY SERVER
            if app.name == "Main_Bot" and not main_bot_started:
                await start_dummy_server("FloodWait")
                main_bot_started = True # Fake it so we don't start it twice
            
            await asyncio.sleep(wait_time)
            # We don't retry here to avoid complexity. The dummy server keeps us alive.
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR starting {app.name}: {e}")
            # If Main Bot crashes (AttributeError, etc), START DUMMY SERVER
            if app.name == "Main_Bot" and not main_bot_started:
                await start_dummy_server(f"Crash: {e}")
                main_bot_started = True

    print("⚡ Cluster Loop Finished. Staying Awake...")
    await idle()

if __name__ == "__main__":
    asyncio.run(start_cluster())
