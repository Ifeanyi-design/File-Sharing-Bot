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
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
            ipv6=False
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()
        await self.setup_permissions() # Shared logic

        self.set_parse_mode(ParseMode.HTML)
        self.LOGGER(__name__).info(f"Main Bot Running: @{self.username}")
        self.username = usr_bot_me.username
        
        # START WEB SERVER (Only Main Bot does this)
        app = web.AppRunner(await web_server(self)) 
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")
    
    # Helper to setup DB/ForceSub for both classes
    async def setup_permissions(self):
        # Force Sub
        if FORCE_SUB_CHANNEL:
            try:
                if isinstance(FORCE_SUB_CHANNEL, str) and FORCE_SUB_CHANNEL.startswith("@"):
                    self.invitelink = f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}"
                else:
                    try:
                        link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                        if not link:
                            await self.export_chat_invite_link(FORCE_SUB_CHANNEL)
                            link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                        self.invitelink = link
                    except:
                        self.LOGGER(__name__).warning("Force Sub Error")
            except Exception as e:
                pass

        # DB Channel
        try:
            self.db_channel = await self.get_chat(CHANNEL_ID)
            # Test message to confirm Admin access
            msg = await self.send_message(chat_id=self.db_channel.id, text=".")
            await msg.delete()
        except Exception as e:
            self.LOGGER(__name__).warning(f"DB Channel Error: {e}")

# --- 2. THE WORKER BOT (Runs Background Tasks) ---
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

    async def start(self):
        await super().start()
        usr_bot_me = await self.get_me()
        print(f"Worker Started: @{usr_bot_me.username}")
        self.username = usr_bot_me.username
        self.set_parse_mode(ParseMode.HTML)
        
        # Manual Permission Setup (Copy of logic above)
        if FORCE_SUB_CHANNEL:
            try:
                if isinstance(FORCE_SUB_CHANNEL, str) and FORCE_SUB_CHANNEL.startswith("@"):
                    self.invitelink = f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}"
                else:
                    try:
                        self.invitelink = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                    except:
                        pass # Worker might not be admin in FSub, ignore
            except: pass

        try:
            self.db_channel = await self.get_chat(CHANNEL_ID)
        except:
            print(f"Worker {self.username} failed to connect to DB Channel")

    async def stop(self, *args):
        await super().stop()