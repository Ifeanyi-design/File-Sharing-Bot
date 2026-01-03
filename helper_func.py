#(©)Codexbotz

import base64
import re
import asyncio
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from config import FORCE_SUB_CHANNEL, ADMINS, AUTO_DELETE_TIME, AUTO_DEL_SUCCESS_MSG
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait

async def is_subscribed(filter, client, update):
    if not FORCE_SUB_CHANNEL:
        return True
    
    user_id = update.from_user.id
    if user_id in ADMINS:
        return True

    # --- SAFETY FIX START ---
    # Create a local variable to hold the channel ID/Username
    fs_channel = FORCE_SUB_CHANNEL

    # If it is a string that looks like a number (e.g. "-10012345"), convert it to INT.
    # This prevents errors if your config loaded the ID as a string.
    if isinstance(fs_channel, str) and (fs_channel.isdigit() or fs_channel.startswith("-")):
        try:
            fs_channel = int(fs_channel)
        except ValueError:
            pass # If conversion fails, keep it as a string (Username)
    # --- SAFETY FIX END ---

    try:
        # Pyrogram accepts both int and str here, so 'fs_channel' works either way.
        member = await client.get_chat_member(chat_id=fs_channel, user_id=user_id)
    except UserNotParticipant:
        return False
    except Exception as e:
        # Failsafe: If the bot isn't an admin or the channel is invalid,
        # let the user pass so the bot doesn't look broken.
        print(f"Force Sub Error: {e}")
        return True

    if not member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
        return False
    else:
        return True

async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = (base64_bytes.decode("ascii")).strip("=")
    return base64_string

async def decode(base64_string):
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes) 
    string = string_bytes.decode("ascii")
    return string

async def get_messages(client, message_ids):
    messages = []
    total_messages = 0
    while total_messages != len(message_ids):
        temb_ids = message_ids[total_messages:total_messages+200]
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temb_ids
            )
        except FloodWait as e:
            await asyncio.sleep(e.x)
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temb_ids
            )
        except:
            pass
        total_messages += len(temb_ids)
        messages.extend(msgs)
    return messages

async def get_message_id(client, message):
    # METHOD 1: If you Forwarded a message
    if message.forward_from_message_id:
        return message.forward_from_message_id
    
    # METHOD 2: If you Sent a Link
    elif message.text:
        # This simply grabs the LAST number in the text. 
        # Example: https://t.me/any/link/here/1234 -> Returns 1234
        try:
            # Split by '/' and find the last part that is a number
            parts = message.text.split('/')
            if parts[-1].isdigit():
                return int(parts[-1])
        except:
            return 0
            
    # Fallback
    return 0

def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time

async def delete_file(messages, client, process):
    await asyncio.sleep(AUTO_DELETE_TIME)
    for msg in messages:
        try:
            await client.delete_messages(chat_id=msg.chat.id, message_ids=[msg.id])
        except Exception as e:
            await asyncio.sleep(e.x)
            print(f"The attempt to delete the media {msg.id} was unsuccessful: {e}")

    await process.edit_text(AUTO_DEL_SUCCESS_MSG)


subscribed = filters.create(is_subscribed)
