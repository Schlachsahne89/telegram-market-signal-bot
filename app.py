import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.getenv("PORT", 10000))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")


def start_webserver():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot läuft erfolgreich auf Render!"
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
        "Score: 0\n"
        "Testversion"
    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Verfügbare Befehle:\n\n"
        "/start - Bot starten\n"
        "/analyse AAPL - Aktie analysieren\n"
        "/analyse NVDA - Aktie analysieren\n"
        "/help - Hilfe anzeigen"
    )

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN fehlt.")

    threading.Thread(
        target=start_webserver,
        daemon=True
    ).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyse", analyse))
    app.add_handler(CommandHandler("help", help_command))
    print("Bot gestartet")
    app.run_polling()


if __name__ == "__main__":
    main()
