import os
import asyncio
import threading

from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from Leverage_Point import get_leverage_point, build_point_message, TICKERS, PERIOD
from Leverage_LOC import get_leverage_loc, build_loc_message
from Leverage_List import load_watchlist, save_watchlist, get_watchlist_text, get_stock_name
from Leverage_Scan import build_scan_message
from Leverage_USD import build_usd_message

load_dotenv("token.env")

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
    
    if context.args and context.args[0].upper() == "LIST":
        wl = await asyncio.to_thread(load_watchlist)
        if not wl:
            await status_msg.edit_text("ℹ️ 리스트가 비어있습니다. /list_add 명령어로 추가해주세요.")
            return
        
        target_ticker = {}
        for t, name in wl.items():
            if t.isdigit() and len(t) == 6:
                target_ticker[t + ".KS"] = name
            else:
                target_ticker[t] = name

    elif context.args:
        ticker = context.args[0].upper()
        if ticker.isdigit() and len(ticker) == 6:
            ticker += ".KS"
        target_ticker = ticker

    else:
        target_ticker = TICKERS
    
    try:
        point_results = await asyncio.to_thread(get_leverage_point, ticker=target_ticker, period=PERIOD)
        message = build_point_message(point_results)
        await status_msg.edit_text(message)
        print(f"✅ [성공] /point 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)

    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /point 처리 실패 {e}", flush=True)


async def loc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("LOC 주문가 계산 중...")

    if context.args and context.args[0].upper() == "LIST":
        wl = await asyncio.to_thread(load_watchlist)
        if not wl:
            await status_msg.edit_text("리스트가 비어있습니다. /list_add 명령어로 추가해주세요.")
            return

        target_ticker = {}
        for t, name in wl.items():
            if t.isdigit() and len(t) == 6:
                target_ticker[t + ".KS"] = name
            else:
                target_ticker[t] = name

    elif context.args:
        ticker = context.args[0].upper()
        if ticker.isdigit() and len(ticker) == 6:
            ticker += ".KS"
        target_ticker = ticker

    else:
        target_ticker = TICKERS

    period = PERIOD
    if len(context.args) > 1:
        period = f"{context.args[1]}y"

    try:
        loc_results = await asyncio.to_thread(get_leverage_loc, ticker=target_ticker, period=period)
        message = build_loc_message(loc_results)
        await status_msg.edit_text(message)
        print(f"✅ [성공] /loc 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)

    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /loc 처리 실패 {e}", flush=True)


async def list_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("리스트에 종목 추가 중...")

    if not context.args:
        await status_msg.edit_text("종목명을 입력해주세요. (예: /list_add 005930)")
        return
        
    ticker = context.args[0].upper()
    display_ticker = ticker.replace(".KS", "") if ticker.endswith(".KS") else ticker
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if display_ticker not in wl:
            add_results = await asyncio.to_thread(get_stock_name, ticker=display_ticker)
            wl[display_ticker] = add_results
            await asyncio.to_thread(save_watchlist, wl)
            await status_msg.edit_text(f"✅ [{add_results}({display_ticker})] 리스트에 추가되었습니다.")
            print(f"✅ [성공] /list_add 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)

        else:
            await status_msg.edit_text(f"ℹ️ [{wl[display_ticker]}] 이미 리스트에 존재합니다.")
            print(f"ℹ️ [안내] /list_add 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /list_add 처리 실패 {e}", flush=True)


async def list_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("리스트에 종목 삭제 중...")

    if not context.args:
        await status_msg.edit_text("종목명을 입력해주세요. (예: /list_del 005930)")
        return
    
    ticker = context.args[0].upper()
    display_ticker = ticker.replace(".KS", "") if ticker.endswith(".KS") else ticker
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if display_ticker in wl:
            del_results = wl.pop(display_ticker)
            await asyncio.to_thread(save_watchlist, wl)
            await status_msg.edit_text(f"✅ [{del_results}] 리스트에서 삭제되었습니다.")
            print(f"✅ [성공] /list_del 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            
        else:
            await status_msg.edit_text(f"ℹ️ [{ticker}] 리스트에 존재하지 않습니다.")
            print(f"ℹ️ [안내] /list_del 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /list_del 처리 실패 {e}", flush=True)


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("리스트 조회 중...")
    
    try:
        wl = await asyncio.to_thread(load_watchlist)
        if not wl:
            await status_msg.edit_text("ℹ️ 리스트가 비어있습니다. /list_add 명령어로 추가해주세요.")
            print(f"ℹ️ [성공] /list 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
            return
        
        list_results = await asyncio.to_thread(get_watchlist_text, wl=wl)
        await status_msg.edit_text(list_results)
        print(f"✅ [성공] /list 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /list 처리 실패 {e}", flush=True)


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text(f"과거 타점 스캔 중...")

    if not context.args:
        await status_msg.edit_text("종목명을 입력해주세요. (예: /scan 005930)")
        return
        
    ticker = context.args[0].upper()
    if ticker.isdigit() and len(ticker) == 6:
        ticker += ".KS"
    
    period = PERIOD
    if len(context.args) > 1:
        period = f"{context.args[1]}y"

    try:
        scan_results = await asyncio.to_thread(build_scan_message, ticker=ticker, period=period)
        
        if len(scan_results) > 4000:
            scan_results = scan_results[:4000] + "\n\n... (데이터가 너무 길어 생략됨)"
        await status_msg.edit_text(scan_results)
        print(f"✅ [성공] /scan 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)

    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /scan 처리 실패 {e}", flush=True)


async def usd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("환율 매수 타점 분석 중...")
    
    try:
        usd_results = await asyncio.to_thread(build_usd_message)
        await status_msg.edit_text(usd_results)
        print(f"✅ [성공] /usd 처리 완료 (요청자: {update.message.from_user.first_name})", flush=True)

    except Exception as e:
        await status_msg.edit_text(f"❌ 오류가 발생했습니다.\n(에러: {e})")
        print(f"❌ [실패] /usd 처리 실패 {e}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    app = ApplicationBuilder().token(token).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    app.add_handler(CommandHandler("point", point))
    app.add_handler(CommandHandler("loc", loc))
    app.add_handler(CommandHandler("list", show_list))
    app.add_handler(CommandHandler("list_add", list_add))
    app.add_handler(CommandHandler("list_del", list_del))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("usd", usd))
    
    print("Bot Started", flush=True)
    app.run_polling()