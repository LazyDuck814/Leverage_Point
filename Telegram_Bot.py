import os
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from Leverage_Point import get_leverage_point, build_message, TICKERS, PERIOD

# --- Render용 가짜 웹 서버 세팅 ---
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)
# ----------------------------------

load_dotenv("token.env")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

async def point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /point 명령어 수신 완료! (요청자: {update.message.from_user.first_name})", flush=True)

    results = get_leverage_point(tickers=TICKERS, period=PERIOD)
    message = build_message(results)
    await update.message.reply_text(message)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start() # 봇이 켜질 때 가짜 웹 서버도 백그라운드에서 같이 실행시킴

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("", ))
    print("Bot Started")
    app.run_polling()
