#(©)Codexbotz

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaDocument
from config import ADMINS
from helper_func import encode, get_message_id
import os
import asyncio
from bot import Bot
from pyrogram import Client, filters
# ---------------------------------------------------------
# 👇 THIS IS THE NEW PART
# PASTE YOUR KOYEB LINK HERE (No trailing slash)
URL = "https://concrete-gypsy-maxcinema-e2407faf.koyeb.app"
# ---------------------------------------------------------

@Client.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
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


@Client.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
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


@Client.on_message(filters.private & filters.user(ADMINS) & filters.command('range'))
async def range_generator(client: Client, message: Message):
    # 1. Check if user sent the links
    if len(message.command) < 3:
        await message.reply(
            "❌ **Usage Error**\n\n"
            "Don't just click the command. Type it like this:\n"
            "`/range [Start_Link] [End_Link]`\n\n"
            "**Example:**\n"
            "`/range https://t.me/c/1234/10 https://t.me/c/1234/20`"
        )
        return

    # 2. Extract IDs from Links
    try:
        # Get the text after /range
        link1 = message.command[1]
        link2 = message.command[2]

        # Extract the number at the end of the link
        start_id = int(link1.split("/")[-1])
        end_id = int(link2.split("/")[-1])
    except:
        await message.reply("❌ **Error:** Could not read those links. Make sure they are standard Telegram post links.")
        return

    # Swap if start is bigger than end
    if start_id > end_id:
        start_id, end_id = end_id, start_id

    processing_msg = await message.reply(f"⚡ Fetching episodes {start_id} to {end_id}...", quote=True)
    
    # 3. Fetch Messages from DB
    try:
        messages = await client.get_messages(client.db_channel.id, range(start_id, end_id + 1))
    except Exception as e:
        await processing_msg.edit(f"❌ Error fetching from DB: {e}")
        return

    clean_links = []
    check_list = []
    
    channel_int = abs(client.db_channel.id)

    # 4. Build the Lists
    if not messages:
        await processing_msg.edit("❌ No messages found in that range.")
        return

    for i, msg in enumerate(messages):
        if not msg or msg.empty: continue

        # Create Link
        string = f"get-{msg.id * channel_int}"
        base64_string = await encode(string)
        link = f"{URL}/watch/{base64_string}"
        
        # Get Name
        media = msg.document or msg.video
        if media and media.file_name:
            fname = media.file_name
        elif msg.caption:
            fname = msg.caption[:40] 
        else:
            fname = "No Name Found"

        clean_links.append(link)
        check_list.append(f"Link {i+1}: {fname}")

    # 5. Create the File
    file_content = ""
    file_content += "\n".join(clean_links)
    file_content += "\n\n" + "="*30 + "\n"
    file_content += "🛑 STOP COPYING HERE 🛑\n"
    file_content += "Check the order below before pasting!\n"
    file_content += "="*30 + "\n\n"
    file_content += "\n".join(check_list)

    file_name = f"verify_links_{start_id}.txt"
    try:
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(file_content)

        await message.reply_document(
            document=file_name,
            caption="✅ **List Generated!**\n\nOpen the file. Copy the **TOP** part. Check the **BOTTOM** part to verify order.",
            quote=True
        )
    except Exception as e:
        await message.reply(f"❌ Error sending file: {e}")
    
    await processing_msg.delete()
    if os.path.exists(file_name):
        os.remove(file_name)
