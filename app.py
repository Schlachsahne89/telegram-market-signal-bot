import os
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
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

stock = get_stock_data(ticker)

if not stock:
    await update.message.reply_text(
        "❌ Ticker nicht gefunden."
    )
    return

price = stock.get("price")
change = stock.get("change")
change_percent = stock.get("changePercentage")
volume = stock.get("volume")

await update.message.reply_text(
    f"📈 Analyse für {ticker}\n\n"
    f"Kurs: {price} USD\n"
    f"Änderung: {change}\n"
    f"Änderung %: {change_percent}%\n"
    f"Volumen: {volume}\n\n"
    "Signal: NEUTRAL"

    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Verfügbare Befehle:\n\n"
        "/start - Bot starten\n"
        "/analyse AAPL - Aktie analysieren\n"
        "/analyse NVDA - Aktie analysieren\n"
        "/help - Hilfe anzeigen"
    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Verfügbare Befehle:\n\n"
        "/start - Bot starten\n"
        "/analyse AAPL - Aktie analysieren\n"
        "/analyse NVDA - Aktie analysieren\n"
        "/help - Hilfe anzeigen"
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Telegram Market Signal Bot\n\n"
        "Aktuell in Entwicklung.\n\n"
        "Verfügbare Befehle:\n"
        "/start\n"
        "/help\n"
        "/analyse TICKER\n"
        "/info"
    )
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Telegram Market Signal Bot"
    )


def get_stock_data(symbol):
    url = (
        f"https://financialmodelingprep.com/stable/quote"
        f"?symbol={symbol}"
        f"&apikey={FMP_API_KEY}"
    )

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if not data:
            return None

        return data[0]

    except Exception:
        return None

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
    app.add_handler(CommandHandler("info", info))
    print("Bot gestartet")
    app.run_polling()


if __name__ == "__main__":
    main()
