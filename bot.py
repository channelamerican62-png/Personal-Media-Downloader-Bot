import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv
import telebot
from telebot import types, apihelper
import downloader

# Load Environment Variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN:
    print("XATOLIK: BOT_TOKEN topilmadi!")
    sys.exit(1)

# CRUCIAL FIX: EXTEND TELEGRAM API TIMEOUTS TO 10 MINUTES (600s) FOR LARGE VIDEOS
apihelper.READ_TIMEOUT = 600
apihelper.CONNECT_TIMEOUT = 300
apihelper.SESSION_TIME_TO_LIVE = 600

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

pending_urls = {}

def format_duration(seconds):
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def format_size(bytes_size):
    if not bytes_size:
        return "0 MB"
    return f"{bytes_size / (1024 * 1024):.1f} MB"

def is_authorized(user_id):
    if not ADMIN_CHAT_ID:
        return True
    return str(user_id) == str(ADMIN_CHAT_ID)

# ===================================================
# 1. RENDER.COM HEALTH CHECK SERVER (RUNS IN BACKGROUND)
# ===================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Abdulaziz aka Media Downloader Bot is RUNNING 24/7 on Render!\n")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    print(f"Health server listening on port {PORT} for Render.com...")
    server.serve_forever()

# ===================================================
# 2. COMMAND: /START
# ===================================================
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Abdulaziz aka"

    if not is_authorized(user_id):
        bot.reply_to(message, "⛔ <b>Kechirasiz!</b> Bu bot <b>Abdulaziz aka</b> uchun shaxsiy bot hisoblanadi.")
        return

    welcome_text = f"""
🌟 <b>Assalomu alaykum, {user_name}!</b>

Sizning shaxsiy <b>Turbo Media Yuklovchi Botingiz</b> tayyor! ⚡👑

🛡 <b>Bu botda:</b>
• ❌ 0% Reklama
• ❌ 0% Majburiy kanal obunalari
• ⚡ 100% Maksimal tezlik (8x Turbo Chunks)

📥 <b>Qo'llab-quvvatlanadigan tarmoqlar:</b>
• 🎬 <b>YouTube</b> (Uzun videolar & Shorts)
• 📸 <b>Instagram</b> (Reels, Postlar, Stories)
• 🎵 <b>TikTok</b> (Suv belgisiz / No watermark)
• 📌 <b>Pinterest</b>, ✖️ <b>Twitter / X</b>, 📘 <b>Facebook</b>

🚀 <b>Foydalanish:</b>
Shunchaki menga istalgan video havolasini yuboring!
"""
    bot.reply_to(message, welcome_text)

# ===================================================
# 3. TEXT & LINK LISTENER
# ===================================================
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        bot.reply_to(message, "⛔ Bu shaxsiy bot.")
        return

    urls = downloader.extract_urls(message.text)
    if not urls:
        bot.reply_to(message, "⚠️ Iltimos, menga haqiqiy video havolasini yuboring.")
        return

    url = urls[0]
    pending_urls[user_id] = url

    status_msg = bot.reply_to(message, "🔍 <i>Video tahlil qilinmoqda...</i>")

    try:
        info = downloader.get_media_info(url)
        if 'error' in info:
            bot.edit_message_text(f"❌ <b>Xatolik:</b> Havolani o'qib bo'lmadi.\nSabab: <code>{info['error'][:120]}</code>", message.chat.id, status_msg.message_id)
            return

        title = info.get('title', 'Media')
        duration_sec = info.get('duration', 0)
        duration = format_duration(duration_sec)
        uploader = info.get('uploader', 'Nomalum')

        caption = f"""
🎬 <b>{title}</b>

👤 <b>Muallif:</b> {uploader}
⏱ <b>Davomiyligi:</b> {duration}
🔗 <b>Manba:</b> <a href="{url}">Havolani ko'rish</a>

<i>Qaysi formatda yuklamoqchisiz?</i>
"""
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn_video_hd = types.InlineKeyboardButton("🎬 Video (HD 720p)", callback_data="dl_720")
        btn_video_fast = types.InlineKeyboardButton("📱 Video (Tezkor 480p)", callback_data="dl_480")
        btn_audio = types.InlineKeyboardButton("🎧 Musiqa (MP3)", callback_data="dl_aud")
        
        keyboard.add(btn_video_hd, btn_video_fast)
        keyboard.add(btn_audio)

        bot.edit_message_text(caption, message.chat.id, status_msg.message_id, reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        bot.edit_message_text(f"❌ Kutilmagan xatolik: {str(e)}", message.chat.id, status_msg.message_id)

# ===================================================
# 4. CALLBACK QUERY (BUTTON CLICK)
# ===================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def handle_callback(call):
    user_id = call.from_user.id
    action = call.data
    url = pending_urls.get(user_id)

    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "Ruxsat berilmagan.", show_alert=True)
        return

    if not url:
        bot.answer_callback_query(call.id, "⚠️ Havola eskirgan. Iltimos, linkni qaytadan yuboring.", show_alert=True)
        return

    bot.answer_callback_query(call.id, "Turbo yuklash boshlandi...")

    if action in ["dl_720", "dl_480"]:
        quality = "720p" if action == "dl_720" else "480p"
        bot.edit_message_text(f"⏳ <b>1/2 Video yuklab olinmoqda ({quality})...</b> (Iltimos, ozgina kuting)", call.message.chat.id, call.message.message_id)
        
        res = downloader.download_video(url, user_id, quality=quality)
        if res.get('success'):
            bot.edit_message_text("📤 <b>2/2 Telegramga yuborilmoqda...</b>", call.message.chat.id, call.message.message_id)
            
            file_path = res['file_path']
            title = res.get('title', 'Video')
            size_str = format_size(res.get('filesize', 0))
            caption = f"🎬 <b>{title}</b>\n📦 Hajmi: {size_str}\n\n🛡 <i>Abdulaziz aka uchun 0% reklamasiz bot</i>"

            try:
                with open(file_path, 'rb') as video_file:
                    bot.send_video(
                        call.message.chat.id,
                        video_file,
                        caption=caption,
                        supports_streaming=True,
                        timeout=600,
                        reply_to_message_id=call.message.reply_to_message.message_id if call.message.reply_to_message else None
                    )
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ Telegramga yuborishda xatolik: {str(e)}", call.message.chat.id, call.message.message_id)
            finally:
                downloader.cleanup_user_files(user_id)
        else:
            bot.edit_message_text(f"❌ Videoni yuklab bo'lmadi: {res.get('error', 'Xatolik yuz berdi')}", call.message.chat.id, call.message.message_id)
            downloader.cleanup_user_files(user_id)

    elif action == "dl_aud":
        bot.edit_message_text("⏳ <b>1/2 Musiqa ajratib olinmoqda (MP3)...</b>", call.message.chat.id, call.message.message_id)
        
        res = downloader.download_audio(url, user_id)
        if res.get('success'):
            bot.edit_message_text("📤 <b>2/2 Telegramga yuborilmoqda...</b>", call.message.chat.id, call.message.message_id)
            
            file_path = res['file_path']
            title = res.get('title', 'Audio')
            uploader = res.get('uploader', 'Musiqa')
            size_str = format_size(res.get('filesize', 0))
            caption = f"🎧 <b>{title}</b>\n👤 {uploader}\n📦 {size_str}"

            try:
                with open(file_path, 'rb') as audio_file:
                    bot.send_audio(
                        call.message.chat.id,
                        audio_file,
                        caption=caption,
                        title=title,
                        performer=uploader,
                        timeout=600,
                        reply_to_message_id=call.message.reply_to_message.message_id if call.message.reply_to_message else None
                    )
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ Musiqani yuborishda xatolik: {str(e)}", call.message.chat.id, call.message.message_id)
            finally:
                downloader.cleanup_user_files(user_id)
        else:
            bot.edit_message_text(f"❌ Musiqani yuklab bo'lmadi: {res.get('error', 'Xatolik yuz berdi')}", call.message.chat.id, call.message.message_id)
            downloader.cleanup_user_files(user_id)

# ===================================================
# 5. START SERVER & POLLING
# ===================================================
if __name__ == '__main__':
    print("====================================================")
    print("🤖 SHAXSIY TURBO MEDIA DOWNLOADER BOT ISHGA TUSHDI!")
    print(f"👤 Egasining Chat ID raqami: {ADMIN_CHAT_ID}")
    print("🛡 0% Reklama | 0% Majburiy Obuna | 100% Maxfiy")
    print("====================================================")
    
    # Start Health Check Server in Background Thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling xatosi: {e}")
            time.sleep(5)
