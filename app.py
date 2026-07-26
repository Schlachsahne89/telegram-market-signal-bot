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
    "SAP": ["SAP.DE", "SAPGY", "SAP"],
    "BMW": ["BMW.DE", "BMWYY", "BMW"],
    "VOW": ["VOW.DE", "VWAGY", "VOW"],
    "BAS": ["BAS.DE", "BASFY", "BAS"],
    "SIE": ["SIE.DE", "SIEGY", "SIE"],
    "ALV": ["ALV.DE", "ALIZY", "ALV"],
    "DTE": ["DTE.DE", "DTEGY", "DTE"],
    "AAPL": ["AAPL"],
    "NVDA": ["NVDA"],
    "MSFT": ["MSFT"],
    "AMZN": ["AMZN"],
    "GOOGL": ["GOOGL", "GOOG"],
    "META": ["META"],
    "TSLA": ["TSLA"],
}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return


def start_webserver():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


def fmp_request(endpoint, params):
    if not FMP_API_KEY:
        return None

    url = f"https://financialmodelingprep.com/stable/{endpoint}"

    request_params = dict(params)
    request_params["apikey"] = FMP_API_KEY

    try:
        response = requests.get(url, params=request_params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def first_item(data):
    if not data:
        return None

    if isinstance(data, list):
        if len(data) == 0:
            return None
        return data[0]

    if isinstance(data, dict):
        return data

    return None


def fmp_get(endpoint, params):
    return first_item(fmp_request(endpoint, params))


def get_possible_symbols(user_input):
    symbol = user_input.upper().strip()

    if symbol in TICKER_FALLBACKS:
        return TICKER_FALLBACKS[symbol]

    return [symbol]


def search_symbols(query):
    results = []

    search_name_data = fmp_request("search-name", {"query": query})
    if isinstance(search_name_data, list):
        for item in search_name_data[:10]:
            symbol = item.get("symbol")
            if symbol and symbol not in results:
                results.append(symbol)

    search_symbol_data = fmp_request("search-symbol", {"query": query})
    if isinstance(search_symbol_data, list):
        for item in search_symbol_data[:10]:
            symbol = item.get("symbol")
            if symbol and symbol not in results:
                results.append(symbol)

    return results


def search_symbol_details(query):
    details = []

    search_name_data = fmp_request("search-name", {"query": query})
    if isinstance(search_name_data, list):
        details.extend(search_name_data[:10])

    search_symbol_data = fmp_request("search-symbol", {"query": query})
    if isinstance(search_symbol_data, list):
        existing_symbols = {
            item.get("symbol") for item in details if item.get("symbol")
        }

        for item in search_symbol_data[:10]:
            symbol = item.get("symbol")
            if symbol and symbol not in existing_symbols:
                details.append(item)

    return details[:10]


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
            "limit": 1,
        },
    )


def get_ratios(symbol):
    return fmp_get(
        "ratios",
        {
            "symbol": symbol,
            "period": "annual",
            "limit": 1,
        },
    )


def find_best_symbol(user_input):
    requested = user_input.upper().strip()

    candidates = get_possible_symbols(requested)

    searched_symbols = search_symbols(requested)
    for symbol in searched_symbols:
        if symbol not in candidates:
            candidates.append(symbol)

    for symbol in candidates:
        stock = get_stock_data(symbol)
        if stock:
            return symbol, stock, candidates

    return requested, None, candidates


def first_available(*values):
    for value in values:
        if value is not None and value != "" and value != 0 and value != "Unbekannt":
            return value
    return "Unbekannt"


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
        possible_values.extend(
            [
                stock.get("pe"),
                stock.get("peRatio"),
                stock.get("priceEarningsRatio"),
            ]
        )

    if metrics:
        possible_values.extend(
            [
                metrics.get("peRatio"),
                metrics.get("priceEarningsRatio"),
                metrics.get("priceToEarningsRatio"),
            ]
        )

    if ratios:
        possible_values.extend(
            [
                ratios.get("peRatio"),
                ratios.get("priceEarningsRatio"),
                ratios.get("priceToEarningsRatio"),
            ]
        )

    for value in possible_values:
        if value is not None and value != "" and value != 0:
            return format_number(value)

    price = stock.get("price") if stock else None
    eps = stock.get("eps") if stock else None

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
        company_name = first_available(
            profile.get("companyName"),
            profile.get("companyNameLong"),
            profile.get("name"),
        )
        sector = first_available(profile.get("sector"))
        industry = first_available(profile.get("industry"))
        country = first_available(profile.get("country"))
        market_cap = first_available(profile.get("marketCap"))

    if market_cap == "Unbekannt" and metrics:
        market_cap = first_available(metrics.get("marketCap"))

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
        "/analyse AAPL - Apple analysieren\n"
        "/analyse NVDA - Nvidia analysieren\n"
        "/analyse MSFT - Microsoft analysieren\n"
        "/analyse SAP - SAP analysieren\n"
        "/analyse SAP.DE - SAP Xetra testen\n"
        "/analyse SAPGY - SAP ADR testen\n"
        "/suche SAP - Symbolsuche starten\n"
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
        "✅ einfache Momentum-Einschätzung anzeigen\n"
        "✅ Ticker-Fallbacks und Symbolsuche nutzen\n\n"
        "Nächster Ausbau:\n"
        "Fundamentalanalyse, News, Geopolitik und Long/Short-Signale.\n\n"
        "Hinweis: Keine Anlageberatung."
    )


async def suche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/suche SAP"
        )
        return

    query = " ".join(context.args).strip()

    results = search_symbol_details(query)

    if not results:
        await update.message.reply_text(
            f"❌ Keine Symbole für '{query}' gefunden."
        )
        return

    text = f"🔎 Gefundene Symbole für '{query}':\n\n"

    for item in results[:10]:
        symbol = item.get("symbol", "?")
        name = first_available(
            item.get("name"),
            item.get("companyName"),
            item.get("companyNameLong"),
        )
        exchange = first_available(
            item.get("exchange"),
            item.get("exchangeShortName"),
            item.get("stockExchange"),
        )
        currency = first_available(item.get("currency"))

        text += f"{symbol} - {name}"
        if exchange != "Unbekannt":
            text += f" | {exchange}"
        if currency != "Unbekannt":
            text += f" | {currency}"
        text += "\n"

    text += "\nNutze dann z. B.:\n/analyse SYMBOL"

    await update.message.reply_text(text)


async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/analyse AAPL"
        )
        return

    requested_ticker = context.args[0].upper().strip()

    used_symbol, stock, tried_symbols = find_best_symbol(requested_ticker)

    if not stock:
        tried_text = ", ".join(tried_symbols) if tried_symbols else requested_ticker

        await update.message.reply_text(
            f"❌ Kein Börsendatensatz für {requested_ticker} gefunden.\n\n"
            f"Geprüfte Symbole: {tried_text}\n\n"
            "Nutze die Symbolsuche:\n"
            f"/suche {requested_ticker}\n\n"
            "Oder teste direkt:\n"
            "/analyse AAPL\n"
            "/analyse NVDA\n"
            "/analyse MSFT\n"
            "/analyse SAP.DE\n"
            "/analyse SAPGY\n\n"
            "Hinweis: Manche Aktien werden bei FMP je nach Datenpaket oder Börse unter anderen Kürzeln geführt."
        )
        return

    profile = get_company_profile(used_symbol)
    metrics = get_key_metrics(used_symbol)
    ratios = get_ratios(used_symbol)

    company = extract_company_data(profile, metrics)

    price = stock.get("price", "Unbekannt")
    change = stock.get("change", "Unbekannt")
    change_percent = first_available(
        stock.get("changePercentage"),
        stock.get("changesPercentage"),
    )
    volume = stock.get("volume", "Unbekannt")

    pe_ratio = calculate_pe_ratio(stock, metrics, ratios)
    momentum_note = basic_research_note(change_percent)

    used_symbol_note = ""
    if used_symbol != requested_ticker:
        used_symbol_note = f"Verwendetes FMP-Symbol: {used_symbol}\n\n"

    await update.message.reply_text(
        f"📈 Analyse für {requested_ticker}\n\n"
        f"{used_symbol_note}"
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
        daemon=True,
    ).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyse", analyse))
    app.add_handler(CommandHandler("suche", suche))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info))

    print("Bot gestartet")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
