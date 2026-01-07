import pyromod.listen 
from pyrogram import idle
from pyrogram.errors import FloodWait
from bot import Bot, Worker
from config import WORKER_TOKENS
import asyncio

async def start_cluster():
    # 1. Initialize Main Bot
    main_bot = Bot()
    main_bot.name = "Main_Bot" # Name it for logs
    
    # 2. Initialize Worker Bots
    workers = []
    for i, token in enumerate(WORKER_TOKENS):
        worker_name = f"Worker_{i+1}"
        worker = Worker(token=token, name=worker_name)
        worker.name = worker_name # Explicitly set name attribute
        workers.append(worker)
    
    # 3. Combine List
    all_apps = [main_bot] + workers
    
    print(f"🚀 Starting Cluster with {len(all_apps)} Bots...")
    
    # 4. ROBUST STARTUP LOOP (Fixes the Crash)
    for app in all_apps:
        try:
            await app.start()
            print(f"✅ {app.name} Started Successfully!")
            
        except FloodWait as e:
            wait_time = e.value
            print(f"⚠️ FLOOD WAIT DETECTED for {app.name}!")
            print(f"⏳ Sleeping for {wait_time} seconds (approx {wait_time // 60} mins). Do not stop the server...")
            
            # Sleep the script without crashing
            await asyncio.sleep(wait_time)
            
            # Retry after sleep
            await app.start()
            print(f"✅ {app.name} Started after waiting!")
            
        except Exception as e:
            print(f"❌ Critical Error starting {app.name}: {e}")
            # We continue to the next bot instead of crashing everything
            continue

    print("⚡ Cluster is Fully Active & Idling...")
    await idle()

if __name__ == "__main__":
    asyncio.run(start_cluster())
