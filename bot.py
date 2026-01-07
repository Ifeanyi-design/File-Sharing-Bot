#(©)Codexbotz

from aiohttp import web
from plugins import web_server

import pyromod.listen
from pyrogram import Client
from pyrogram.enums import ParseMode
import sys
from datetime import datetime

from config import API_HASH, APP_ID, LOGGER, TG_BOT_TOKEN, TG_BOT_WORKERS, FORCE_SUB_CHANNEL, CHANNEL_ID, PORT

ascii_art = """
░█████╗░░█████╗░██████╗░███████╗██╗░░██╗██████╗░░█████╗░████████╗███████╗
██╔══██╗██╔══██╗██╔══██╗██╔════╝╚██╗██╔╝██╔══██╗██╔══██╗╚══██╔══╝╚════██║
██║░░╚═╝██║░░██║██║░░██║█████╗░░░╚███╔╝░██████╦╝██║░░██║░░░██║░░░░░███╔═╝
██║░░██╗██║░░██║██║░░██║██╔══╝░░░██╔██╗░██╔══██╗██║░░██║░░░██║░░░██╔══╝░░
╚█████╔╝╚█████╔╝██████╔╝███████╗██╔╝╚██╗██████╦╝╚█████╔╝░░░██║░░░███████╗
░╚════╝░░╚════╝░╚═════╝░╚══════╝╚═╝░░╚═╝╚═════╝░░╚════╝░░░░╚═╝░░░╚══════╝
"""

# --- 1. THE MAIN BOT (Runs the Website) ---
class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Main_Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
            ipv6=False
        )
        self.LOGGER = LOGGER
        self.username = "Unknown_Bot" # Default to prevent crash

    async def start(self):
        # Initialize Web Server runner early so we can access it if needed
        self.web_runner = web.AppRunner(await web_server(self))
        await self.web_runner.setup()
        
        # Start Pyrogram
        await super().start()
        
        # Safe Get Me
        try:
            usr_bot_me = await self.get_me()
            self.username = usr_bot_me.username
            self.LOGGER(__name__).info(f"Main Bot Running: @{self.username}")
        except Exception as e:
            self.LOGGER(__name__).warning(f"Failed to fetch bot username: {e}")

        self.uptime = datetime.now()
        await self.setup_permissions()
        self.set_parse_mode(ParseMode.HTML)
        
        # START WEB SERVER
        # We start this AFTER successful login
        bind_address = "0.0.0.0"
        await web.TCPSite(self.web_runner, bind_address, PORT).start()
        print(f"🌍 Web Server Active on Port {PORT}")

    async def stop(self, *args):
        await super().stop()
    
    async def setup_permissions(self):
        if FORCE_SUB_CHANNEL:
            try:
                if isinstance(FORCE_SUB_CHANNEL, str) and FORCE_SUB_CHANNEL.startswith("@"):
                    self.invitelink = f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}"
                else:
                    self.invitelink = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
            except: pass

        try:
            self.db_channel = await self.get_chat(CHANNEL_ID)
        except: pass

# --- 2. THE WORKER BOT ---
class Worker(Client):
    def __init__(self, token, name):
        super().__init__(
            name=name,
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=token,
            ipv6=False
        )
        self.LOGGER = LOGGER
        self.username = "Unknown_Worker"

    async def start(self):
        await super().start()
        try:
            usr_bot_me = await self.get_me()
            self.username = usr_bot_me.username
            print(f"Worker Started: @{self.username}")
        except: pass
        
        self.set_parse_mode(ParseMode.HTML)
        
        # Manual DB Setup
        try:
            self.db_channel = await self.get_chat(CHANNEL_ID)
        except: pass

    async def stop(self, *args):
        await super().stop()