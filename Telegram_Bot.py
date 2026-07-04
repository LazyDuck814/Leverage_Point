import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from Leverage_Pint import get_leverage_pint, build_message, TICKERS, PERIOD

load_dotenv("token.env")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


async def pint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = get_leverage_pint(tickers=TICKERS, period=PERIOD)
    message = build_message(results)
    await update.message.reply_text(message)


if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("pint", pint))
    print("Bot Started")
    app.run_polling()