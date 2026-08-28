import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import time
import logging
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv
import telebot
from telebot import types, apihelper
import downloader

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", 10000))
SERVICE_URL = os.getenv("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}")

if not BOT_TOKEN:
    print("XATOLIK: BOT_TOKEN topilmadi!")
    sys.exit(1)

apihelper.READ_TIMEOUT = 600
apihelper.CONNECT_TIMEOUT = 300
apihelper.SESSION_TIME_TO_LIVE = 600

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=False)
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
# HEALTH CHECK SERVER - keeps Render awake
# ===================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - Bot is running 24/7\n")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logging.info(f"Health server started on port {PORT}")
    server.serve_forever()

# ===================================================
# ANTI-SLEEP: self-ping every 10 minutes
# ===================================================
def self_ping():
    """Ping our own health endpoint every 10 min to prevent Render free-tier sleep."""
    time.sleep(30)  # Wait for server to start first
    while True:
        try:
            ping_url = SERVICE_URL if SERVICE_URL.startswith("http") else f"https://{SERVICE_URL}"
            req = urllib.request.Request(ping_url, headers={"User-Agent": "bot-keepalive"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                logging.info(f"Self-ping OK: {resp.getcode()}")
        except Exception as e:
            logging.warning(f"Self-ping error: {e}")
        time.sleep(600)  # every 10 minutes

# ===================================================
# BOT COMMANDS
# ===================================================
@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "Abdulaziz aka"
    if not is_authorized(user_id):
        bot.reply_to(message, "Kechirasiz! Bu bot shaxsiy.")
        return
    text = (
        "Assalomu alaykum, <b>" + name + "</b>!\n\n"
        "Shaxsiy <b>Turbo Media Yuklovchi Botingiz</b> tayyor!\n\n"
        "<b>Imkoniyatlar:</b>\n"
        "YouTube, Instagram, TikTok, Pinterest, Twitter, Facebook\n\n"
        "0% Reklama | 0% Majburiy obuna\n\n"
        "Havola yuboring, yuklab beraman!"
    )
    bot.reply_to(message, text)

@bot.message_handler(func=lambda msg: True, content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        bot.reply_to(message, "Bu shaxsiy bot.")
        return

    urls = downloader.extract_urls(message.text)
    if not urls:
        bot.reply_to(message, "Iltimos, haqiqiy video havolasini yuboring.")
        return

    url = urls[0]
    pending_urls[user_id] = url
    status_msg = bot.reply_to(message, "<i>Video tahlil qilinmoqda...</i>")

    try:
        info = downloader.get_media_info(url)
        if "error" in info:
            bot.edit_message_text(
                "Xatolik: " + info["error"][:150],
                message.chat.id, status_msg.message_id
            )
            return

        title = info.get("title", "Media")
        duration = format_duration(info.get("duration", 0))
        uploader = info.get("uploader", "Nomalum")

        caption = (
            "<b>" + title + "</b>\n\n"
            "Muallif: " + uploader + "\n"
            "Davomiyligi: " + duration + "\n\n"
            "Qaysi formatda yuklamoqchisiz?"
        )

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("Video HD 720p", callback_data="dl_720"),
            types.InlineKeyboardButton("Video 480p", callback_data="dl_480"),
        )
        kb.add(types.InlineKeyboardButton("MP3 Musiqa", callback_data="dl_aud"))

        bot.edit_message_text(
            caption, message.chat.id, status_msg.message_id,
            reply_markup=kb, disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"handle_text error: {e}")
        bot.edit_message_text(f"Xatolik: {str(e)[:200]}", message.chat.id, status_msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dl_"))
def handle_callback(call):
    user_id = call.from_user.id
    action = call.data
    url = pending_urls.get(user_id)

    if not is_authorized(user_id):
        bot.answer_callback_query(call.id, "Ruxsat berilmagan.", show_alert=True)
        return
    if not url:
        bot.answer_callback_query(call.id, "Havola eskirgan. Linkni qayta yuboring.", show_alert=True)
        return

    bot.answer_callback_query(call.id, "Yuklash boshlandi...")

    if action in ["dl_720", "dl_480"]:
        quality = "720p" if action == "dl_720" else "480p"
        bot.edit_message_text(
            f"Yuklab olinmoqda ({quality})... Iltimos kuting.",
            call.message.chat.id, call.message.message_id
        )
        res = downloader.download_video(url, user_id, quality=quality)
        if res.get("success"):
            bot.edit_message_text(
                "Telegramga yuborilmoqda...",
                call.message.chat.id, call.message.message_id
            )
            fp = res["file_path"]
            title = res.get("title", "Video")
            sz = format_size(res.get("filesize", 0))
            cap = f"<b>{title}</b>\n{sz}"
            try:
                with open(fp, "rb") as vf:
                    bot.send_video(
                        call.message.chat.id, vf,
                        caption=cap, supports_streaming=True, timeout=600
                    )
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception as e:
                logging.error(f"send_video error: {e}")
                bot.edit_message_text(f"Yuborishda xatolik: {str(e)[:200]}", call.message.chat.id, call.message.message_id)
            finally:
                downloader.cleanup_user_files(user_id)
        else:
            bot.edit_message_text(
                "Yuklab bolmadi: " + res.get("error", "Xatolik")[:200],
                call.message.chat.id, call.message.message_id
            )
            downloader.cleanup_user_files(user_id)

    elif action == "dl_aud":
        bot.edit_message_text("MP3 ajratib olinmoqda...", call.message.chat.id, call.message.message_id)
        res = downloader.download_audio(url, user_id)
        if res.get("success"):
            bot.edit_message_text("Telegramga yuborilmoqda...", call.message.chat.id, call.message.message_id)
            fp = res["file_path"]
            title = res.get("title", "Musiqa")
            uploader = res.get("uploader", "Nomalum")
            cap = f"<b>{title}</b>\n{uploader}"
            try:
                with open(fp, "rb") as af:
                    bot.send_audio(
                        call.message.chat.id, af,
                        caption=cap, title=title, performer=uploader, timeout=600
                    )
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception as e:
                logging.error(f"send_audio error: {e}")
                bot.edit_message_text(f"Yuborishda xatolik: {str(e)[:200]}", call.message.chat.id, call.message.message_id)
            finally:
                downloader.cleanup_user_files(user_id)
        else:
            bot.edit_message_text(
                "Yuklab bolmadi: " + res.get("error", "Xatolik")[:200],
                call.message.chat.id, call.message.message_id
            )
            downloader.cleanup_user_files(user_id)

# ===================================================
# MAIN
# ===================================================
if __name__ == "__main__":
    logging.info("Bot starting up...")
    logging.info(f"PORT: {PORT}")
    logging.info(f"ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
    logging.info(f"SERVICE_URL: {SERVICE_URL}")

    # 1. Start health check HTTP server (required for Render not to kill the service)
    t1 = threading.Thread(target=run_health_server, daemon=True)
    t1.start()

    # 2. Start self-ping to prevent Render free-tier sleep after 15 min
    t2 = threading.Thread(target=self_ping, daemon=True)
    t2.start()

    # 3. Delete webhook to ensure clean polling (fixes 409 Conflict)
    try:
        bot.remove_webhook()
        time.sleep(1)
        logging.info("Webhook removed OK")
    except Exception as e:
        logging.warning(f"remove_webhook: {e}")

    logging.info("Starting bot polling...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            time.sleep(10)
