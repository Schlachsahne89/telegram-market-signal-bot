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


def format_market_cap(value):
    if value is None or value == "Unbekannt":
        return "Unbekannt"

    try:
        value = float(value)

        if value >= 1_000_000_000_000:
            return f"{value / 1_000_000_000_000:.2f} Bio. USD"
        elif value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f} Mrd. USD"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.2f} Mio. USD"
        else:
            return f"{value:.0f} USD"

    except Exception:
        return str(value)


def get_stock_data(symbol):
    url = (
        "https://financialmodelingprep.com/stable/quote"
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


def get_company_profile(symbol):
    url = (
        "https://financialmodelingprep.com/stable/profile"
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot läuft erfolgreich auf Render!\n\n"
        "Nutze /help für alle Befehle."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Verfügbare Befehle:\n\n"
        "/start - Bot starten\n"
        "/analyse AAPL - Aktie analysieren\n"
        "/analyse NVDA - Aktie analysieren\n"
        "/analyse MSFT - Aktie analysieren\n"
        "/info - Informationen zum Bot\n"
        "/help - Hilfe anzeigen"
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Telegram Market Signal Bot\n\n"
        "Aktuell in Entwicklung.\n\n"
        "Der Bot kann bereits:\n"
        "✅ echte Kursdaten abrufen\n"
        "✅ Kursänderung anzeigen\n"
        "✅ Volumen anzeigen\n"
        "✅ Unternehmensprofil anzeigen\n"
        "✅ Branche, Land und Marktkapitalisierung anzeigen\n\n"
        "Nächster Ausbau:\n"
        "Fundamentalanalyse, News, Geopolitik und Long/Short-Signale.\n\n"
        "Hinweis: Keine Anlageberatung."
    )


async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/analyse AAPL"
        )
        return

    ticker = context.args[0].upper()

    stock = get_stock_data(ticker)
    profile = get_company_profile(ticker)

    if not stock:
        await update.message.reply_text(
            "❌ Ticker nicht gefunden.\n\n"
            "Teste zum Beispiel:\n"
            "/analyse AAPL\n"
            "/analyse NVDA\n"
            "/analyse MSFT"
        )
        return

    price = stock.get("price", "Unbekannt")
    change = stock.get("change", "Unbekannt")
    change_percent = stock.get("changePercentage", "Unbekannt")
    volume = stock.get("volume", "Unbekannt")

    company_name = "Unbekannt"
    sector = "Unbekannt"
    country = "Unbekannt"
    market_cap = "Unbekannt"

    if profile:
        company_name = profile.get("companyName", "Unbekannt")
        sector = profile.get("sector", "Unbekannt")
        country = profile.get("country", "Unbekannt")
        market_cap = format_market_cap(profile.get("marketCap", "Unbekannt"))

    await update.message.reply_text(
        f"📈 Analyse für {ticker}\n\n"
        f"Unternehmen: {company_name}\n"
        f"Branche: {sector}\n"
        f"Land: {country}\n"
        f"Marktkapitalisierung: {market_cap}\n\n"
        f"Kurs: {price} USD\n"
        f"Änderung: {change}\n"
        f"Änderung %: {change_percent}%\n"
        f"Volumen: {volume}\n\n"
        "Signal: NEUTRAL\n\n"
        "Hinweis: Keine Anlageberatung."
    )


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN fehlt.")

    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY fehlt.")

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
