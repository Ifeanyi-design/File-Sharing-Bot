import pyromod.listen 
from pyrogram import idle
from pyrogram.errors import FloodWait
from bot import Bot, Worker
from config import WORKER_TOKENS, PORT
from aiohttp import web
import asyncio

# --- DUMMY SERVER TO TRICK KOYEB ---
async def start_dummy_server():
    # This creates a fake website so Koyeb thinks we are healthy
    dummy_app = web.Application()
    dummy_app.router.add_get('/', lambda r: web.Response(text="❄️ Cooling down Telegram Ban... Please wait."))
    runner = web.AppRunner(dummy_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🏥 Dummy Health Check Server started on Port {PORT}")
    return runner

async def start_cluster():
    main_bot = Bot()
    main_bot.name = "Main_Bot"
    
    workers = []
    for i, token in enumerate(WORKER_TOKENS):
        worker_name = f"Worker_{i+1}"
        worker = Worker(token=token, name=worker_name)
        worker.name = worker_name
        workers.append(worker)
    
    all_apps = [main_bot] + workers
    print(f"🚀 Starting Cluster with {len(all_apps)} Bots...")
    
    for app in all_apps:
        try:
            await app.start()
            print(f"✅ {app.name} Started Successfully!")
            
        except FloodWait as e:
            wait_time = e.value + 10 # Add 10s buffer
            print(f"⚠️ FLOOD WAIT DETECTED for {app.name}!")
            print(f"⏳ Sleeping for {wait_time} seconds...")
            
            # CRITICAL: If Main Bot fails, start dummy server so Koyeb doesn't kill us
            dummy_runner = None
            if app.name == "Main_Bot":
                dummy_runner = await start_dummy_server()
            
            # Sleep safely
            await asyncio.sleep(wait_time)
            
            # Cleanup dummy server before retrying
            if dummy_runner:
                print("🏥 Stopping Dummy Server...")
                await dummy_runner.cleanup()
            
            # Retry
            print(f"🔄 Retrying {app.name}...")
            await app.start()
            print(f"✅ {app.name} Started after waiting!")
            
        except Exception as e:
            print(f"❌ Critical Error starting {app.name}: {e}")
            continue

    print("⚡ Cluster is Fully Active & Idling...")
    await idle()

if __name__ == "__main__":
    asyncio.run(start_cluster())
