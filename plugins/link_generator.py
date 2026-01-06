#(©)Codexbotz

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaDocument
from config import ADMINS
from helper_func import encode, get_message_id
import os
import asyncio
from bot import Bot

# ---------------------------------------------------------
# 👇 THIS IS THE NEW PART
# PASTE YOUR KOYEB LINK HERE (No trailing slash)
URL = "https://concrete-gypsy-maxcinema-e2407faf.koyeb.app"
# ---------------------------------------------------------

@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
async def batch(client: Client, message: Message):
    while True:
        try:
            first_message = await client.ask(text = "Forward the First Message from DB Channel (with Quotes)..\n\nor Send the DB Channel Post Link", chat_id = message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        f_msg_id = await get_message_id(client, first_message)
        if f_msg_id:
            break
        else:
            await first_message.reply("❌ Error\n\nCould not find this post in the DB Channel.", quote = True)
            continue

    while True:
        try:
            second_message = await client.ask(text = "Forward the Last Message from DB Channel (with Quotes)..\nor Send the DB Channel Post link", chat_id = message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        s_msg_id = await get_message_id(client, second_message)
        if s_msg_id:
            break
        else:
            await second_message.reply("❌ Error\n\nCould not find this post in the DB Channel.", quote = True)
            continue


    string = f"get-{f_msg_id * abs(client.db_channel.id)}-{s_msg_id * abs(client.db_channel.id)}"
    base64_string = await encode(string)
    
    # 👇 GENERATING BOTH LINKS HERE
    tg_link = f"https://t.me/{client.username}?start={base64_string}"
    direct_link = f"{URL}/watch/{base64_string}"
    
    text_message = (
        f"✅ **Batch Link Created!**\n\n"
        f"✈️ **Telegram Link:**\n{tg_link}\n\n"
        f"🌐 **Direct Download Link:**\n{direct_link}"
    )

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={tg_link}')]])
    await second_message.reply_text(text_message, quote=True, reply_markup=reply_markup)


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator(client: Client, message: Message):
    while True:
        try:
            channel_message = await client.ask(text = "Forward Message from the DB Channel (with Quotes)..\nor Send the DB Channel Post link", chat_id = message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            break
        else:
            await channel_message.reply("❌ Error\n\nCould not find this post in the DB Channel.", quote = True)
            continue

    base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
    
    # 👇 GENERATING BOTH LINKS HERE
    tg_link = f"https://t.me/{client.username}?start={base64_string}"
    direct_link = f"{URL}/watch/{base64_string}"

    text_message = (
        f"✅ **Link Generated!**\n\n"
        f"✈️ **Telegram Link:**\n{tg_link}\n\n"
        f"🌐 **Direct Download Link:**\n{direct_link}"
    )

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={tg_link}')]])
    await channel_message.reply_text(text_message, quote=True, reply_markup=reply_markup)



@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('range'))
async def range_generator(client: Client, message: Message):
    # --- 1. Ask for Start/End Messages (Standard) ---
    while True:
        try:
            start_msg = await client.ask(
                text="Forward the **FIRST Episode**...",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except: return
        start_id = await get_message_id(client, start_msg)
        if start_id: break

    while True:
        try:
            end_msg = await client.ask(
                text="Forward the **LAST Episode**...",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except: return
        end_id = await get_message_id(client, end_msg)
        if end_id: break

    if start_id > end_id:
        start_id, end_id = end_id, start_id

    processing_msg = await message.reply("⚡ Fetching list...", quote=True)
    
    # --- 2. Fetch Messages ---
    try:
        messages = await client.get_messages(client.db_channel.id, range(start_id, end_id + 1))
    except Exception as e:
        await processing_msg.edit(f"Error: {e}")
        return

    clean_links = []
    check_list = []
    
    channel_int = abs(client.db_channel.id)

    # --- 3. Build the Lists ---
    for i, msg in enumerate(messages):
        if not msg or msg.empty: continue

        # Create Link
        string = f"get-{msg.id * channel_int}"
        base64_string = await encode(string)
        link = f"{URL}/watch/{base64_string}"
        
        # Get Name (For your eyes only)
        media = msg.document or msg.video
        if media and media.file_name:
            fname = media.file_name
        elif msg.caption:
            fname = msg.caption[:40] # First 40 chars of caption
        else:
            fname = "No Name Found"

        clean_links.append(link)
        check_list.append(f"Link {i+1}: {fname}")

    # --- 4. Create the 'Cheat Sheet' File ---
    file_content = ""
    
    # PART A: The Links (Clean)
    file_content += "\n".join(clean_links)
    
    # PART B: The Separator
    file_content += "\n\n" + "="*30 + "\n"
    file_content += "🛑 STOP COPYING HERE 🛑\n"
    file_content += "Check the order below before pasting!\n"
    file_content += "="*30 + "\n\n"
    
    # PART C: The Names (For Checking)
    file_content += "\n".join(check_list)

    # Save and Send
    file_name = f"verify_links_{start_id}.txt"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(file_content)

    await message.reply_document(
        document=file_name,
        caption="✅ **List Generated!**\n\nOpen the file. Copy the **TOP** part. Check the **BOTTOM** part to verify order.",
        quote=True
    )
    
    await processing_msg.delete()
    os.remove(file_name)
