import os
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.getenv("TELEGRAM_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot läuft!\n\n"
        "Test erfolgreich."
    )


async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/analyse AAPL"
        )
        return

    ticker = context.args[0].upper()

    await update.message.reply_text(
        f"Analyse für {ticker}\n\n"
        "Signal: NEUTRAL\n"
        "Score: 0\n\n"
        "Dies ist aktuell nur ein Test."
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN fehlt in den Render Environment Variables."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyse", analyse))

    print("Bot gestartet...")
    app.run_polling()


if __name__ == "__main__":
    main()
