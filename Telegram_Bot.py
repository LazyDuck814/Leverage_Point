import os
import asyncio
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from Leverage_Point import get_leverage_point, build_message, TICKERS, PERIOD

load_dotenv("token.env")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# --- Render용 가짜 웹 서버 세팅 ---
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)
# ----------------------------------

async def point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /point 명령어 수신 완료! (요청자: {update.message.from_user.first_name})", flush=True)
    status_msg = await update.message.reply_text("데이터 수집 및 분석 중입니다...")

    try:
        results = await asyncio.to_thread(get_leverage_point, tickers=TICKERS, period=PERIOD)
        message = build_message(results)
        await status_msg.edit_text(message)

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        await status_msg.edit_text(f"⚠️ 처리 중 오류가 발생했습니다. 나중에 다시 시도해주세요.\n(에러: {e})")

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    app.add_handler(CommandHandler("point", point))
    print("Bot Started")
    app.run_polling()
