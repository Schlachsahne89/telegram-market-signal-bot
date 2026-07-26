import os
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
PORT = int(os.getenv("PORT", 10000))


TICKER_FALLBACKS = {
    "SAP": ["SAP", "SAP.DE", "SAPGY"],
    "BMW": ["BMW.DE", "BMWYY"],
    "VOW": ["VOW.DE", "VWAGY"],
    "BAS": ["BAS.DE", "BASFY"],
    "SIE": ["SIE.DE", "SIEGY"],
    "ALV": ["ALV.DE", "ALIZY"],
    "DTE": ["DTE.DE", "DTEGY"],
}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")


def start_webserver():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


def fmp_get(endpoint, params):
    if not FMP_API_KEY:
        return None

    url = f"https://financialmodelingprep.com/stable/{endpoint}"

    request_params = dict(params)
    request_params["apikey"] = FMP_API_KEY

    try:
        response = requests.get(url, params=request_params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            return None

        if isinstance(data, list):
            if len(data) == 0:
                return None
            return data[0]

        if isinstance(data, dict):
            return data

        return None

    except Exception:
        return None


def get_possible_symbols(symbol):
    symbol = symbol.upper().strip()

    if symbol in TICKER_FALLBACKS:
        return TICKER_FALLBACKS[symbol]

    return [symbol]


def get_stock_data(symbol):
    return fmp_get("quote", {"symbol": symbol})


def get_company_profile(symbol):
    return fmp_get("profile", {"symbol": symbol})


def get_key_metrics(symbol):
    return fmp_get(
        "key-metrics",
        {
            "symbol": symbol,
            "period": "annual",
            "limit": 1
        }
    )


def get_ratios(symbol):
    return fmp_get(
        "ratios",
        {
            "symbol": symbol,
            "period": "annual",
            "limit": 1
        }
    )


def find_best_symbol(user_symbol):
    possible_symbols = get_possible_symbols(user_symbol)

    for symbol in possible_symbols:
        stock = get_stock_data(symbol)

        if stock:
            return symbol, stock

    return user_symbol.upper(), None


def format_market_cap(value):
    if value is None or value == "Unbekannt":
        return "Unbekannt"

    try:
        value = float(value)

        if value >= 1_000_000_000_000:
            return f"{value / 1_000_000_000_000:.2f} Bio. USD"
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f} Mrd. USD"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f} Mio. USD"

        return f"{value:.0f} USD"

    except Exception:
        return str(value)


def format_number(value):
    if value is None or value == "Unbekannt":
        return "Unbekannt"

    try:
        number = float(value)
        return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def format_percent(value):
    if value is None or value == "Unbekannt":
        return "Unbekannt"

    try:
        value_as_text = str(value).replace("%", "")
        number = float(value_as_text)
        return f"{number:.2f}%".replace(".", ",")
    except Exception:
        return str(value)


def calculate_pe_ratio(stock, metrics, ratios):
    possible_values = []

    if stock:
        possible_values.append(stock.get("pe"))
        possible_values.append(stock.get("peRatio"))

    if metrics:
        possible_values.append(metrics.get("peRatio"))
        possible_values.append(metrics.get("priceEarningsRatio"))
        possible_values.append(metrics.get("priceToEarningsRatio"))

    if ratios:
        possible_values.append(ratios.get("peRatio"))
        possible_values.append(ratios.get("priceEarningsRatio"))
        possible_values.append(ratios.get("priceToEarningsRatio"))

    for value in possible_values:
        if value is not None and value != "" and value != 0:
            return format_number(value)

    price = None
    eps = None

    if stock:
        price = stock.get("price")
        eps = stock.get("eps")

    try:
        if price and eps and float(eps) != 0:
            calculated_pe = float(price) / float(eps)
            return format_number(calculated_pe)
    except Exception:
        pass

    return "Unbekannt"


def extract_company_data(profile, metrics):
    company_name = "Unbekannt"
    sector = "Unbekannt"
    industry = "Unbekannt"
    country = "Unbekannt"
    market_cap = "Unbekannt"

    if profile:
        company_name = profile.get("companyName", "Unbekannt")
        sector = profile.get("sector", "Unbekannt")
        industry = profile.get("industry", "Unbekannt")
        country = profile.get("country", "Unbekannt")
        market_cap = profile.get("marketCap", "Unbekannt")

    if market_cap == "Unbekannt" and metrics:
        market_cap = metrics.get("marketCap", "Unbekannt")

    return {
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "country": country,
        "market_cap": market_cap,
    }


def basic_research_note(change_percent):
    try:
        value = float(str(change_percent).replace("%", ""))

        if value >= 2:
            return "Kurzfristiges Momentum: positiv"
        if value <= -2:
            return "Kurzfristiges Momentum: negativ"

        return "Kurzfristiges Momentum: neutral"

    except Exception:
        return "Kurzfristiges Momentum: nicht bewertbar"


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
        "/analyse SAP - Aktie analysieren, inklusive Fallbacks\n"
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
        "✅ Unternehmensdaten anzeigen\n"
        "✅ Branche, Industrie, Land und Marktkapitalisierung anzeigen\n"
        "✅ KGV mit mehreren Fallbacks anzeigen\n"
        "✅ einfache Momentum-Einschätzung anzeigen\n\n"
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

    requested_ticker = context.args[0].upper().strip()

    used_symbol, stock = find_best_symbol(requested_ticker)

    if not stock:
        await update.message.reply_text(
            "❌ Ticker nicht gefunden.\n\n"
            "Teste zum Beispiel:\n"
            "/analyse AAPL\n"
            "/analyse NVDA\n"
            "/analyse MSFT\n"
            "/analyse SAP\n\n"
            "Für manche deutsche Aktien braucht FMP andere Kürzel, z. B. SAP.DE oder SAPGY."
        )
        return

    profile = get_company_profile(used_symbol)
    metrics = get_key_metrics(used_symbol)
    ratios = get_ratios(used_symbol)

    company = extract_company_data(profile, metrics)

    price = stock.get("price", "Unbekannt")
    change = stock.get("change", "Unbekannt")
    change_percent = stock.get("changePercentage", "Unbekannt")
    volume = stock.get("volume", "Unbekannt")
    pe_ratio = calculate_pe_ratio(stock, metrics, ratios)

    momentum_note = basic_research_note(change_percent)

    used_symbol_note = ""
    if used_symbol != requested_ticker:
        used_symbol_note = f"\nVerwendetes FMP-Symbol: {used_symbol}\n"

    await update.message.reply_text(
        f"📈 Analyse für {requested_ticker}\n"
        f"{used_symbol_note}\n"
        f"Unternehmen: {company['company_name']}\n"
        f"Branche: {company['sector']}\n"
        f"Industrie: {company['industry']}\n"
        f"Land: {company['country']}\n"
        f"Marktkapitalisierung: {format_market_cap(company['market_cap'])}\n"
        f"KGV: {pe_ratio}\n\n"
        f"Kurs: {format_number(price)} USD\n"
        f"Änderung: {format_number(change)}\n"
        f"Änderung %: {format_percent(change_percent)}\n"
        f"Volumen: {volume}\n\n"
        f"{momentum_note}\n"
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
