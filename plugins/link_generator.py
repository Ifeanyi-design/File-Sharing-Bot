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
    # 1. Ask for START Message
    while True:
        try:
            start_msg = await client.ask(
                text="Forward the **FIRST Episode** from DB Channel (with Quotes)..\nor Send the Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        
        start_id = await get_message_id(client, start_msg)
        if start_id:
            break
        else:
            await start_msg.reply("❌ Error\n\nCould not find this post ID.", quote=True)
            continue

    # 2. Ask for END Message
    while True:
        try:
            end_msg = await client.ask(
                text="Forward the **LAST Episode** from DB Channel (with Quotes)..\nor Send the Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        
        end_id = await get_message_id(client, end_msg)
        if end_id:
            break
        else:
            await end_msg.reply("❌ Error\n\nCould not find this post ID.", quote=True)
            continue

    # 3. Validation
    if start_id > end_id:
        await message.reply("❌ Error: Start ID cannot be bigger than End ID!", quote=True)
        return

    # 4. Generate the List
    processing_msg = await message.reply("⚡ Generating links...", quote=True)
    
    links_list = []
    total_count = 0

    # Calculate the channel ID part of the hash once
    # Note: Your bot uses this math: msg_id * abs(channel_id)
    # We must match that exactly.
    channel_int = abs(client.db_channel.id)

    for msg_id in range(start_id, end_id + 1):
        # Generate the unique hash for this message
        string = f"get-{msg_id * channel_int}"
        base64_string = await encode(string)
        
        # Create Direct Link
        # Note: 'URL' variable must be defined at the top of your file (your Koyeb URL)
        direct_link = f"{URL}/watch/{base64_string}"
        
        links_list.append(direct_link)
        total_count += 1

    # 5. Save to File
    file_name = f"links_{start_id}_to_{end_id}.txt"
    with open(file_name, "w") as f:
        f.write("\n".join(links_list))

    # 6. Send File
    await message.reply_document(
        document=file_name,
        caption=f"✅ **Generated {total_count} Links!**\n\nRange: `{start_id}` to `{end_id}`\n\n📂 Open this file and paste the links into your Website Admin Panel.",
        quote=True
    )
    
    # Cleanup
    await processing_msg.delete()
    os.remove(file_name)
