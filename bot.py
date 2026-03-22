import os
import re
import requests
import asyncio
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- CONFIGURATION (Set these in Railway Variables) ---
BOT_TOKEN = "7785735935:AAHIRxqdtRanVQk19QarpY-bzlGY5wqEGQo"
TERABOX_SECRET = "pk_b8eedlxe5bhn2xyapd8kwi"
LOG_CHANNEL_ID = -1003462659720  # Replace with your Private Channel ID
BASE_URL = "https://api.playterabox.com/api/proxy"
# --- KEEP-ALIVE SERVER (For Railway/Render) ---
server = Flask(__name__)
@server.route('/')
def ping(): return "Bot is running!", 200

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- HELPER: LOGGING ---
async def send_log(context, message):
    if LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(
                chat_id=int(LOG_CHANNEL_ID), 
                text=f"📝 **BOT LOG**\n{message}", 
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Logging Error: {e}")

# --- CORE LOGIC ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    # Find all Terabox/1024tera links in the message
    links = re.findall(r'(https?://[^\s]+terabox[^\s]+|https?://[^\s]+1024tera[^\s]+)', text)
    
    if not links:
        return

    main_status = await update.message.reply_text(f"🚀 Found {len(links)} link(s). Starting sequence...")

    for link_idx, url in enumerate(links):
        # 1. Fetch Data for each link
        try:
            response = requests.get(BASE_URL, params={"secret": TERABOX_SECRET, "url": url}, timeout=30)
            data = response.json()
        except Exception as e:
            err_msg = f"❌ API Error on Link {link_idx+1}\nLink: {url}\nError: {e}"
            await send_log(context, err_msg)
            continue

        if not data or "list" not in data or not data["list"]:
            await update.message.reply_text(f"❌ Link {link_idx+1} failed: No files found.")
            await send_log(context, f"❌ Empty Link: {url}")
            continue

        file_list = data["list"]
        total_files = len(file_list)
        
        # 2. Process each file in the link
        for file_idx, file_info in enumerate(file_list):
            orig_name = file_info.get("filename", "video.mp4")
            # Force .mp4 extension for Telegram Player compatibility
            filename = orig_name if orig_name.lower().endswith(".mp4") else f"{orig_name}.mp4"
            dl_link = file_info.get("download_link")
            size_mb = int(file_info.get("size", 0)) / (1024 * 1024)

            # Skip if over 400MB
            if size_mb > 400:
                skip_msg = f"⚠️ Skipped: `{filename}`\nReason: Too large ({size_mb:.1f}MB)"
                await update.message.reply_text(skip_msg)
                await send_log(context, skip_msg)
                continue

            await main_status.edit_text(
                f"📂 **Link {link_idx+1}/{len(links)}**\n"
                f"📄 **File {file_idx+1}/{total_files}**\n"
                f"📥 Downloading: `{filename}`"
            )
            
            v_path, t_path = f"vid_{link_idx}_{file_idx}.mp4", f"thumb_{link_idx}_{file_idx}.jpg"

            try:
                # 3. Download Video
                with requests.get(dl_link, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(v_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024*1024): f.write(chunk)

                # 4. Download Thumbnail
                t_url = file_info.get("image")
                if t_url:
                    t_res = requests.get(t_url, timeout=10)
                    with open(t_path, 'wb') as f: f.write(t_res.content)

                # 5. Upload to Telegram
                await main_status.edit_text(f"📤 Uploading: `{filename}`...")
                with open(v_path, 'rb') as vf:
                    tf = open(t_path, 'rb') if os.path.exists(t_path) else None
                    await update.message.reply_video(
                        video=vf, 
                        caption=f"✅ **Part {file_idx+1}**: {orig_name}\n📦 Size: {size_mb:.1f} MB", 
                        thumbnail=tf, 
                        supports_streaming=True
                    )
                    if tf: tf.close()

                # 6. Success Log
                await send_log(context, f"✅ **Success**\nFile: `{filename}`\nLink: {url}")

            except Exception as e:
                await send_log(context, f"❌ **Error**\nFile: `{filename}`\nError: {str(e)}")
                await update.message.reply_text(f"❌ Failed to process: {filename}")

            finally:
                # Local Cleanup
                if os.path.exists(v_path): os.remove(v_path)
                if os.path.exists(t_path): os.remove(t_path)

    await main_status.edit_text(f"🏁 Task Complete! Processed {len(links)} link(s).")

def main():
    # Start server thread
    threading.Thread(target=run_server, daemon=True).start()
    
    # Start Bot
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not found in environment!")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
