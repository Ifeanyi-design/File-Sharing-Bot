#(©)CodeXBotz

import os
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, AUTO_DELETE_MSG, JOIN_REQUEST_ENABLE,FORCE_SUB_CHANNEL
from helper_func import subscribed,decode, get_messages, delete_file
from database.database import add_user, del_user, full_userbase, present_user


@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    id = message.from_user.id
    if not await present_user(id):
        try:
            await add_user(id)
        except:
            pass
    text = message.text
    if len(text)>7:
        try:
            base64_string = text.split(" ", 1)[1]
        except:
            return
        string = await decode(base64_string)
        argument = string.split("-")
        if len(argument) == 3:
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
            except:
                return
            if start <= end:
                ids = range(start,end+1)
            else:
                ids = []
                i = start
                while True:
                    ids.append(i)
                    i -= 1
                    if i < end:
                        break
        elif len(argument) == 2:
            try:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            except:
                return
        temp_msg = await message.reply("Please wait...")
        try:
            messages = await get_messages(client, ids)
        except:
            await message.reply_text("Something went wrong..!")
            return
        await temp_msg.delete()

        track_msgs = []

        for msg in messages:
            # 1. Identify the media type (Fix: Support both Document and Video)
            media = msg.document or msg.video
            
            if not media:
                continue # Skip if there's no supported media

            # 2. Handle Captioning
            if bool(CUSTOM_CAPTION):
                # We use getattr or a simple check because 'file_name' might not exist on all video objects
                file_name = getattr(media, "file_name", f"video_{msg.id}.mp4")
                caption = CUSTOM_CAPTION.format(
                    previouscaption = "" if not msg.caption else msg.caption.html, 
                    filename = file_name
                )
            else:
                caption = "" if not msg.caption else msg.caption.html

            # 3. Handle Reply Markup
            reply_markup = msg.reply_markup if DISABLE_CHANNEL_BUTTON else None

            # 4. Copying Logic
            if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
                try:
                    # Use copy_message or copy to handle any media type
                    copied_msg = await msg.copy(
                        chat_id=message.from_user.id, 
                        caption=caption, 
                        parse_mode=ParseMode.HTML, 
                        reply_markup=reply_markup, 
                        protect_content=PROTECT_CONTENT
                    )
                    if copied_msg:
                        track_msgs.append(copied_msg)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    # Retry logic...
                except Exception as e:
                    print(f"Error copying: {e}")
            else:
                try:
                    await msg.copy(
                        chat_id=message.from_user.id, 
                        caption=caption, 
                        parse_mode=ParseMode.HTML, 
                        reply_markup=reply_markup, 
                        protect_content=PROTECT_CONTENT
                    )
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Error copying: {e}")
                    
        if track_msgs:
            delete_data = await client.send_message(
                chat_id=message.from_user.id,
                text=AUTO_DELETE_MSG.format(time=AUTO_DELETE_TIME)
            )
            # Schedule the file deletion task after all messages have been copied
            asyncio.create_task(delete_file(track_msgs, client, delete_data))
        else:
            print("No messages to track for deletion.")

        return
    else:
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("😊 About Me", callback_data = "about"),
                    InlineKeyboardButton("🔒 Close", callback_data = "close")
                ]
            ]
        )
        if START_PIC:  # Check if START_PIC has a value
            await message.reply_photo(
                photo=START_PIC,
                caption=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                quote=True
            )
        else:  # If START_PIC is empty, send only the text
            await message.reply_text(
                text=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                quote=True
            )
        return

    
#=====================================================================================##

WAIT_MSG = """"<b>Processing ...</b>"""

REPLY_ERROR = """<code>Use this command as a replay to any telegram message with out any spaces.</code>"""

#=====================================================================================##


@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    
    # --- SMART LOGIC FIX START ---
    # Only use Join Requests if enabled AND it is NOT a public username.
    # If it is a Username (@...), we force the simple link to prevent errors.
    # 1. Check if we should generate a "Join Request" link
    # We ONLY do this if it is enabled AND the channel is an ID (not a username)
    if bool(JOIN_REQUEST_ENABLE) and not str(FORCE_SUB_CHANNEL).startswith("@"):
        try:
            # We wrap it in int() just to be 100% safe against string IDs like "-100..."
            invite = await client.create_chat_invite_link(
                chat_id=int(FORCE_SUB_CHANNEL), 
                creates_join_request=True
            )
            ButtonUrl = invite.invite_link
        except Exception as e:
            # If anything fails (permissions, wrong ID), we just use the basic link
            print(f"Join Request Error: {e}")
            ButtonUrl = client.invitelink
    else:
        # If it is a Username (@MaxCinema), we ALWAYS use the basic link
        ButtonUrl = client.invitelink
    # --- SMART LOGIC FIX END ---

    buttons = [
        [
            InlineKeyboardButton(
                "Join Channel",
                url = ButtonUrl)
        ]
    ]

    try:
        buttons.append(
            [
                InlineKeyboardButton(
                    text = 'Try Again',
                    url = f"https://t.me/{client.username}?start={message.command[1]}"
                )
            ]
        )
    except IndexError:
        pass

    await message.reply(
        text = FORCE_MSG.format(
                first = message.from_user.first_name,
                last = message.from_user.last_name,
                username = None if not message.from_user.username else '@' + message.from_user.username,
                mention = message.from_user.mention,
                id = message.from_user.id
            ),
        reply_markup = InlineKeyboardMarkup(buttons),
        quote = True,
        disable_web_page_preview = True
    )
    
@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()

