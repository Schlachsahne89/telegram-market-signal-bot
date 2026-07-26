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


def get_financial_growth(symbol):
    return fmp_get(
        "financial-growth",
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


def to_float(value):
    if value is None or value == "" or value == "Unbekannt":
        return None

    try:
        value_as_text = str(value).replace("%", "").replace(",", ".")
        return float(value_as_text)
    except Exception:
        return None


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
        number = to_float(value)

        if number is None:
            return "Unbekannt"

        if abs(number) <= 1:
            number = number * 100

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


def calculate_roe(metrics, ratios):
    possible_values = []

    if ratios:
        possible_values.extend(
            [
                ratios.get("returnOnEquity"),
                ratios.get("roe"),
                ratios.get("returnOnEquityRatio"),
            ]
        )

    if metrics:
        possible_values.extend(
            [
                metrics.get("returnOnEquity"),
                metrics.get("roe"),
            ]
        )

    for value in possible_values:
        if value is not None and value != "" and value != 0:
            return value

    return "Unbekannt"


def calculate_debt_to_equity(ratios, metrics):
    possible_values = []

    if ratios:
        possible_values.extend(
            [
                ratios.get("debtEquityRatio"),
                ratios.get("debtToEquity"),
                ratios.get("debtToEquityRatio"),
            ]
        )

    if metrics:
        possible_values.extend(
            [
                metrics.get("debtToEquity"),
                metrics.get("debtEquityRatio"),
            ]
        )

    for value in possible_values:
        if value is not None and value != "" and value != 0:
            return value

    return "Unbekannt"


def extract_growth_data(growth):
    revenue_growth = "Unbekannt"
    net_income_growth = "Unbekannt"
    free_cash_flow_growth = "Unbekannt"
    eps_growth = "Unbekannt"

    if growth:
        revenue_growth = first_available(
            growth.get("revenueGrowth"),
            growth.get("growthRevenue"),
        )

        net_income_growth = first_available(
            growth.get("netIncomeGrowth"),
            growth.get("growthNetIncome"),
        )

        free_cash_flow_growth = first_available(
            growth.get("freeCashFlowGrowth"),
            growth.get("growthFreeCashFlow"),
        )

        eps_growth = first_available(
            growth.get("epsgrowth"),
            growth.get("epsGrowth"),
            growth.get("growthEPS"),
        )

    return {
        "revenue_growth": revenue_growth,
        "net_income_growth": net_income_growth,
        "free_cash_flow_growth": free_cash_flow_growth,
        "eps_growth": eps_growth,
    }


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


def basic_momentum_note(change_percent):
    value = to_float(change_percent)

    if value is None:
        return "Kurzfristiges Momentum: nicht bewertbar"

    if value >= 2:
        return "Kurzfristiges Momentum: positiv"
    if value <= -2:
        return "Kurzfristiges Momentum: negativ"

    return "Kurzfristiges Momentum: neutral"


def calculate_research_score(change_percent, pe_ratio, roe, revenue_growth, net_income_growth, debt_to_equity):
    score = 0
    notes = []

    change_value = to_float(change_percent)
    pe_value = to_float(str(pe_ratio).replace(".", "").replace(",", "."))
    roe_value = to_float(roe)
    revenue_growth_value = to_float(revenue_growth)
    net_income_growth_value = to_float(net_income_growth)
    debt_to_equity_value = to_float(debt_to_equity)

    if change_value is not None:
        if change_value >= 2:
            score += 1
            notes.append("Momentum positiv")
        elif change_value <= -2:
            score -= 1
            notes.append("Momentum negativ")

    if pe_value is not None:
        if 0 < pe_value <= 25:
            score += 1
            notes.append("KGV wirkt moderat")
        elif pe_value > 50:
            score -= 1
            notes.append("KGV wirkt hoch")

    if roe_value is not None:
        if abs(roe_value) <= 1:
            roe_value = roe_value * 100

        if roe_value >= 15:
            score += 1
            notes.append("ROE stark")
        elif roe_value < 5:
            score -= 1
            notes.append("ROE schwach")

    if revenue_growth_value is not None:
        if abs(revenue_growth_value) <= 1:
            revenue_growth_value = revenue_growth_value * 100

        if revenue_growth_value > 5:
            score += 1
            notes.append("Umsatzwachstum positiv")
        elif revenue_growth_value < 0:
            score -= 1
            notes.append("Umsatzwachstum negativ")

    if net_income_growth_value is not None:
        if abs(net_income_growth_value) <= 1:
            net_income_growth_value = net_income_growth_value * 100

        if net_income_growth_value > 5:
            score += 1
            notes.append("Gewinnwachstum positiv")
        elif net_income_growth_value < 0:
            score -= 1
            notes.append("Gewinnwachstum negativ")

    if debt_to_equity_value is not None:
        if debt_to_equity_value <= 1:
            score += 1
            notes.append("Verschuldung wirkt kontrolliert")
        elif debt_to_equity_value > 2:
            score -= 1
            notes.append("Verschuldung erhöht")

    if score >= 3:
        signal = "LONG-KANDIDAT"
    elif score <= -2:
        signal = "SHORT-/RISIKO-KANDIDAT"
    else:
        signal = "NEUTRAL"

    if not notes:
        notes.append("Zu wenige Fundamentaldaten für Score verfügbar")

    return {
        "score": score,
        "signal": signal,
        "notes": notes,
    }


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
        "✅ ROE anzeigen\n"
        "✅ Umsatzwachstum anzeigen\n"
        "✅ Gewinnwachstum anzeigen\n"
        "✅ Debt/Equity anzeigen\n"
        "✅ einfachen Research-Score berechnen\n"
        "✅ Ticker-Fallbacks und Symbolsuche nutzen\n\n"
        "Nächster Ausbau:\n"
        "News, Geopolitik, ETF-Daten und KI-Zusammenfassung.\n\n"
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
    growth = get_financial_growth(used_symbol)

    company = extract_company_data(profile, metrics)
    growth_data = extract_growth_data(growth)

    price = stock.get("price", "Unbekannt")
    change = stock.get("change", "Unbekannt")
    change_percent = first_available(
        stock.get("changePercentage"),
        stock.get("changesPercentage"),
    )
    volume = stock.get("volume", "Unbekannt")

    pe_ratio = calculate_pe_ratio(stock, metrics, ratios)
    roe = calculate_roe(metrics, ratios)
    debt_to_equity = calculate_debt_to_equity(ratios, metrics)

    revenue_growth = growth_data["revenue_growth"]
    net_income_growth = growth_data["net_income_growth"]
    free_cash_flow_growth = growth_data["free_cash_flow_growth"]
    eps_growth = growth_data["eps_growth"]

    momentum_note = basic_momentum_note(change_percent)

    research = calculate_research_score(
        change_percent=change_percent,
        pe_ratio=pe_ratio,
        roe=roe,
        revenue_growth=revenue_growth,
        net_income_growth=net_income_growth,
        debt_to_equity=debt_to_equity,
    )

    used_symbol_note = ""
    if used_symbol != requested_ticker:
        used_symbol_note = f"Verwendetes FMP-Symbol: {used_symbol}\n\n"

    notes_text = ""
    for note in research["notes"][:5]:
        notes_text += f"- {note}\n"

    await update.message.reply_text(
        f"📈 Analyse für {requested_ticker}\n\n"
        f"{used_symbol_note}"
        f"Unternehmen: {company['company_name']}\n"
        f"Branche: {company['sector']}\n"
        f"Industrie: {company['industry']}\n"
        f"Land: {company['country']}\n"
        f"Marktkapitalisierung: {format_market_cap(company['market_cap'])}\n\n"
        f"📊 Bewertung & Fundamentaldaten\n"
        f"KGV: {pe_ratio}\n"
        f"ROE: {format_percent(roe)}\n"
        f"Debt/Equity: {format_number(debt_to_equity)}\n"
        f"Umsatzwachstum: {format_percent(revenue_growth)}\n"
        f"Gewinnwachstum: {format_percent(net_income_growth)}\n"
        f"Free-Cashflow-Wachstum: {format_percent(free_cash_flow_growth)}\n"
        f"EPS-Wachstum: {format_percent(eps_growth)}\n\n"
        f"💵 Marktdaten\n"
        f"Kurs: {format_number(price)} USD\n"
        f"Änderung: {format_number(change)}\n"
        f"Änderung %: {format_percent(change_percent)}\n"
        f"Volumen: {volume}\n\n"
        f"🧭 Einschätzung\n"
        f"{momentum_note}\n"
        f"Research-Score: {research['score']}\n"
        f"Signal: {research['signal']}\n\n"
        f"Gründe:\n"
        f"{notes_text}\n"
        "Hinweis: Keine Anlageberatung. Dieses Signal ist nur ein automatisierter Research-Hinweis."
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
