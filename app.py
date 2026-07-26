import os
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
PORT = int(os.getenv("PORT", "10000"))


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
    "XOM": ["XOM"],
    "CVX": ["CVX"],
    "JPM": ["JPM"],
    "BAC": ["BAC"],
    "TSM": ["TSM"],
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
        response = requests.get(url, params=request_params, timeout=15)
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


def normalize_percent_value(value):
    number = to_float(value)

    if number is None:
        return None

    if abs(number) <= 1:
        return number * 100

    return number


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

    number = normalize_percent_value(value)

    if number is None:
        return "Unbekannt"

    return f"{number:.2f}%".replace(".", ",")


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


def get_stock_news(symbol, limit=5):
    data = fmp_request(
        "news/stock",
        {
            "symbols": symbol,
            "limit": limit,
