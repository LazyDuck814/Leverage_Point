import os
import asyncio
import threading
from flask import Flask
from dotenv import load_dotenv

load_dotenv("token.env")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from Leverage_Point import get_leverage_point, build_message, TICKERS, PERIOD
from Leverage_List import load_watchlist, save_watchlist, get_watchlist_text

# --- Render용 가짜 웹 서버 세팅 ---
web_app = Flask(__name__)
@web_app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)
# ---------------------------------


async def point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[/point 명령어 수신] 요청자: {update.message.from_user.first_name}", flush=True)
    status_msg = await update.message.reply_text("데이터 수집 및 분석 중입니다...")

    try:
        results = await asyncio.to_thread(get_leverage_point, tickers=TICKERS, period=PERIOD)
        message = build_message(results)
        await status_msg.edit_text(message)
        print("✅ [성공] /point 분석 및 전송 완료", flush=True)

    except Exception as e:
        print(f"❌ [/point 오류 발생] {e}", flush=True)
        await status_msg.edit_text(f"⚠️ 처리 중 오류가 발생했습니다. 나중에 다시 시도해주세요.\n(에러: {e})")


async def list_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[/list_add 명령어 수신] 요청자: {update.message.from_user.first_name}", flush=True)
    
    if not context.args:
        await update.message.reply_text("종목명을 입력해주세요. (예: /list_add AAPL)")
        return
    ticker = context.args[0].upper()
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if ticker not in wl:
            wl.append(ticker)
            await asyncio.to_thread(save_watchlist, wl)
            await update.message.reply_text(f"[{ticker}] 관심종목에 추가되었습니다.")
            print(f"✅ [성공] {ticker} 관심종목 추가 완료", flush=True)
        else:
            await update.message.reply_text(f"[{ticker}] 이미 관심종목에 있습니다.")
            print(f"ℹ️ [안내] {ticker} 이미 리스트에 존재함", flush=True)
            
    except Exception as e:
        print(f"❌ [/list_add 오류 발생] {e}", flush=True)
        await update.message.reply_text(f"⚠️ 처리 중 오류가 발생했습니다.\n(에러: {e})")


async def list_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[/list_del 명령어 수신] 요청자: {update.message.from_user.first_name}", flush=True)
    
    if not context.args:
        await update.message.reply_text("종목명을 입력해주세요. (예: /list_del AAPL)")
        return
    ticker = context.args[0].upper()
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if ticker in wl:
            wl.remove(ticker)
            await asyncio.to_thread(save_watchlist, wl)
            await update.message.reply_text(f"[{ticker}] 관심종목에서 삭제되었습니다.")
            print(f"✅ [성공] {ticker} 관심종목 삭제 완료", flush=True)
        else:
            await update.message.reply_text(f"[{ticker}] 관심종목에 존재하지 않습니다.")
            print(f"ℹ️ [안내] {ticker} 리스트에 없음", flush=True)
            
    except Exception as e:
        print(f"❌ [/list_del 오류 발생] {e}", flush=True)
        await update.message.reply_text(f"⚠️ 처리 중 오류가 발생했습니다.\n(에러: {e})")


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[/list 명령어 수신] 요청자: {update.message.from_user.first_name}", flush=True)
    status_msg = await update.message.reply_text("관심종목 조회 중...")
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        
        if not wl:
            await status_msg.edit_text("관심종목이 비어있습니다. /list_add 명령어로 추가해주세요.")
            print("✅ [성공] 관심종목 조회 완료 (빈 리스트)", flush=True)
            return
        
        msg = await asyncio.to_thread(get_watchlist_text, wl)
        await status_msg.edit_text(msg)
        print("✅ [성공] 관심종목 조회 및 전송 완료", flush=True)
        
    except Exception as e:
        print(f"❌ [/list 오류 발생] {e}", flush=True)
        await status_msg.edit_text(f"⚠️ 처리 중 오류가 발생했습니다.\n(에러: {e})")


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    
    app.add_handler(CommandHandler("point", point))
    app.add_handler(CommandHandler("list", show_list))
    app.add_handler(CommandHandler("list_add", list_add))
    app.add_handler(CommandHandler("list_del", list_del))
    
    print("Bot Started", flush=True)
    app.run_polling()
