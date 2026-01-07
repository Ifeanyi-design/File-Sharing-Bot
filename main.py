import pyromod.listen 
from pyrogram import compose
from bot import Bot, Worker
from config import WORKER_TOKENS
import asyncio

async def start_cluster():
    # 1. Main Bot
    main_bot = Bot()
    
    # 2. Worker Bots
    workers = []
    for i, token in enumerate(WORKER_TOKENS):
        worker_name = f"Worker_{i+1}"
        workers.append(Worker(token=token, name=worker_name))
    
    # 3. Combine List
    all_apps = [main_bot] + workers
    
    print(f"🚀 Starting Cluster with {len(all_apps)} Bots...")
    await compose(all_apps)

if __name__ == "__main__":
    asyncio.run(start_cluster())
