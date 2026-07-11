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
    status_msg = await update.message.reply_text("데이터 수집 및 분석 중...")
    
    if context.args:
        ticker = context.args[0].upper()
        if ticker.isdigit() and len(ticker) == 6:
            ticker += ".KS"
        target_tickers = [ticker]
    else:
        target_tickers = TICKERS
    
    try:
        results = await asyncio.to_thread(get_leverage_point, tickers=target_tickers, period=PERIOD)
        message = build_message(results)
        await status_msg.edit_text(message)
        print(f"✅ [성공] /point 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /point 처리 실패 {e}", flush=True)


async def list_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("종목명을 입력해주세요. (예: /list_add AAPL)")
        return
    ticker = context.args[0].upper()
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if ticker not in wl:
            wl.append(ticker)
            await asyncio.to_thread(save_watchlist, wl)
            await update.message.reply_text(f"✅ [{ticker}] 리스트에 추가되었습니다.")
            print(f"✅ [성공] /list_add 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
        else:
            await update.message.reply_text(f"ℹ️ [{ticker}] 이미 리스트에 존재합니다.")
            print(f"ℹ️ [안내] /list_add 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            
    except Exception as e:
        await update.message.reply_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /list_add 처리 실패 {e}", flush=True)


async def list_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("종목명을 입력해주세요. (예: /list_del AAPL)")
        return
    ticker = context.args[0].upper()
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if ticker in wl:
            wl.remove(ticker)
            await asyncio.to_thread(save_watchlist, wl)
            await update.message.reply_text(f"✅ [{ticker}] 리스트에서 삭제되었습니다.")
            print(f"✅ [성공] /list_del 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
        else:
            await update.message.reply_text(f"ℹ️ [{ticker}] 리스트에 존재하지 않습니다.")
            print(f"ℹ️ [안내] /list_del 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            
    except Exception as e:
        await update.message.reply_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /list_del 처리 실패 {e}", flush=True)


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("리스트 조회 중...")
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        
        if not wl:
            await status_msg.edit_text("ℹ️ 리스트가 비어있습니다. /list_add 명령어로 추가해주세요.")
            print(f"ℹ️ [성공] /list 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            return
        
        msg = await asyncio.to_thread(get_watchlist_text, wl)
        await status_msg.edit_text(msg)
        print(f"✅ [성공] /list 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /list 처리 실패 {e}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    app.add_handler(CommandHandler("point", point))
    app.add_handler(CommandHandler("list", show_list))
    app.add_handler(CommandHandler("list_add", list_add))
    app.add_handler(CommandHandler("list_del", list_del))
    
    print("Bot Started", flush=True)
    app.run_polling()
