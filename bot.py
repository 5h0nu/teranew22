import os
import requests
import asyncio
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
BOT_TOKEN = "7785735935:AAHIRxqdtRanVQk19QarpY-bzlGY5wqEGQo"
TERABOX_SECRET = "pk_b8eedlxe5bhn2xyapd8kwi"
LOG_CHANNEL_ID = -1003462659720  # Replace with your Private Channel ID
BASE_URL = "https://api.playterabox.com/api/proxy"

# --- AUTO MAKEUP / KEEP-ALIVE SERVER ---
server = Flask(__name__)
@server.route('/')
def ping(): return "Bot is Alive!", 200

def run_server():
    # Railway/Render provide a PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- CORE LOGIC ---

async def send_log(context, message):
    try:
        await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=f"📋 **LOG:**\n{message}", parse_mode="Markdown")
    except Exception as e:
        print(f"Logging Error: {e}")

async def get_terabox_data(url):
    params = {"secret": TERABOX_SECRET, "url": url}
    try:
        response = requests.get(BASE_URL, params=params, timeout=20)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "terabox" not in url and "1024tera" not in url:
        return

    main_status = await update.message.reply_text("🔎 Fetching folder contents...")
    data = await get_terabox_data(url)

    if not data or "list" not in data or not data["list"]:
        await main_status.edit_text("❌ Failed to fetch data. Link might be broken.")
        return

    file_list = data["list"]
    total_files = len(file_list)
    await main_status.edit_text(f"📦 Found {total_files} file(s). Starting sequence...")

    for index, file_info in enumerate(file_list):
        original_name = file_info.get("filename", f"file_{index}.mp4")
        filename = original_name if original_name.lower().endswith(".mp4") else f"{original_name}.mp4"
        direct_link = file_info.get("download_link")
        thumb_url = file_info.get("image")
        size_mb = int(file_info.get("size", 0)) / (1024 * 1024)

        current_info = f"File {index+1}/{total_files}: `{filename}` ({size_mb:.1f} MB)"
        await main_status.edit_text(f"⏳ **Processing**\n{current_info}")

        # 1. Size Check
        if size_mb > 400:
            err_msg = f"⚠️ Skipped: {filename} (Too large: {size_mb:.1f}MB)"
            await update.message.reply_text(err_msg)
            await send_log(context, err_msg)
            continue

        video_path = f"vid_{index}_{filename}"
        thumb_path = f"thumb_{index}.jpg"

        try:
            # 2. Download
            with requests.get(direct_link, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(video_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        f.write(chunk)

            # 3. Thumbnail
            if thumb_url:
                t_res = requests.get(thumb_url)
                with open(thumb_path, 'wb') as f: f.write(t_res.content)

            # 4. Upload
            with open(video_path, 'rb') as v_file:
                t_file = open(thumb_path, 'rb') if os.path.exists(thumb_path) else None
                await update.message.reply_video(
                    video=v_file,
                    caption=f"✅ **Part {index+1}**: {original_name}",
                    thumbnail=t_file,
                    supports_streaming=True
                )
                if t_file: t_file.close()

            # 5. Success Log
            log_text = (f"✅ **Success**\nFile: `{filename}`\nStatus: Downloaded & Uploaded\n"
                        f"Cleanup: Local file deleted\nLink: [Source]({url})")
            await send_log(context, log_text)

        except Exception as e:
            err_log = f"❌ **Error on File {index+1}**\nFile: `{filename}`\nError: `{str(e)}`"
            await send_log(context, err_log)
            await update.message.reply_text(f"❌ Error processing file {index+1}")

        finally:
            if os.path.exists(video_path): os.remove(video_path)
            if os.path.exists(thumb_path): os.remove(thumb_path)

    await main_status.edit_text(f"🏁 Task Complete! Processed {total_files} files.")

def main():
    # Start Keep-Alive Server in background
    threading.Thread(target=run_server, daemon=True).start()
    
    # Start Telegram Bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is active and Keep-Alive server is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

