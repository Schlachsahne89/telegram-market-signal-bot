import os
import json
import time
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
PORT = int(os.getenv("PORT", "10000"))

ALERT_INTERVAL_SECONDS = int(os.getenv("ALERT_INTERVAL_SECONDS", "900"))

WATCHLIST_FILE = "watchlists.json"
SEEN_ALERTS_FILE = "seen_alerts.json"
SYMBOL_CACHE_FILE = "symbol_cache.json"


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
    "SHELL": ["SHEL", "SHEL.L"],
    "SHEL": ["SHEL", "SHEL.L"],
    "TOTAL": ["TTE", "TTE.PA", "TOTB.DE"],
    "TOTALENERGIES": ["TTE", "TTE.PA", "TOTB.DE"],
    "TTE": ["TTE", "TTE.PA"],
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


def load_json_file(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_watchlists():
    return load_json_file(WATCHLIST_FILE, {})


def save_watchlists(data):
    save_json_file(WATCHLIST_FILE, data)


def load_seen_alerts():
    return load_json_file(SEEN_ALERTS_FILE, {})


def save_seen_alerts(data):
    save_json_file(SEEN_ALERTS_FILE, data)


def load_symbol_cache():
    return load_json_file(
        SYMBOL_CACHE_FILE,
        {
            "synced_at": None,
            "items": [],
        },
    )


def save_symbol_cache(data):
    save_json_file(SYMBOL_CACHE_FILE, data)


def first_available(*values):
    for value in values:
        if value is not None and value != "" and value != 0 and value != "Unbekannt":
            return value
    return "Unbekannt"


def to_float(value):
    if value is None or value == "" or value == "Unbekannt":
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "."))
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
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def format_percent(value):
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


def fmp_request(endpoint, params):
    if not FMP_API_KEY:
        return None

    url = f"https://financialmodelingprep.com/stable/{endpoint}"
    request_params = dict(params)
    request_params["apikey"] = FMP_API_KEY

    try:
        response = requests.get(url, params=request_params, timeout=25)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def first_item(data):
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def fmp_get(endpoint, params):
    return first_item(fmp_request(endpoint, params))


def get_symbol_name(item):
    return first_available(
        item.get("name"),
        item.get("companyName"),
        item.get("companyNameLong"),
    )


def get_symbol_exchange(item):
    return first_available(
        item.get("exchange"),
        item.get("exchangeShortName"),
        item.get("stockExchange"),
    )


def get_symbol_currency(item):
    return first_available(item.get("currency"))


def get_symbol_type(item):
    return first_available(
        item.get("type"),
        item.get("securityType"),
    )


def score_symbol_result(item, query):
    query_text = str(query).lower().strip()
    symbol = str(item.get("symbol", "")).lower().strip()
    name = str(get_symbol_name(item)).lower().strip()
    exchange = str(get_symbol_exchange(item)).lower().strip()

    score = 0

    if symbol == query_text:
        score += 100
    if symbol.startswith(query_text):
        score += 60
    if query_text in symbol:
        score += 30
    if name == query_text:
        score += 80
    if name.startswith(query_text):
        score += 50
    if query_text in name:
        score += 25
    if exchange in ["nasdaq", "nyse", "xetra", "lse", "tsx", "tokyo", "hkse", "euronext"]:
        score += 5

    return score


def sync_symbol_cache():
    data = fmp_request("stock-list", {})

    if not isinstance(data, list):
        return 0

    cleaned_items = []
    seen_symbols = set()

    for item in data:
        symbol = item.get("symbol")

        if not symbol:
            continue

        symbol_key = str(symbol).upper().strip()

        if symbol_key in seen_symbols:
            continue

        seen_symbols.add(symbol_key)

        cleaned_items.append(
            {
                "symbol": symbol,
                "companyName": first_available(item.get("companyName"), item.get("name"), symbol),
                "name": first_available(item.get("name"), item.get("companyName"), symbol),
                "exchange": first_available(
                    item.get("exchange"),
                    item.get("exchangeShortName"),
                    item.get("stockExchange"),
                ),
                "currency": first_available(item.get("currency")),
                "type": first_available(item.get("type"), item.get("securityType")),
            }
        )

    cache = {
        "synced_at": int(time.time()),
        "items": cleaned_items,
    }

    save_symbol_cache(cache)

    return len(cleaned_items)


def get_symbol_cache_count():
    cache = load_symbol_cache()
    items = cache.get("items", [])

    if isinstance(items, list):
        return len(items)

    return 0


def get_symbol_cache_synced_at():
    cache = load_symbol_cache()
    return cache.get("synced_at")


def search_symbol_catalog(query, limit=50):
    cache = load_symbol_cache()
    items = cache.get("items", [])

    if not isinstance(items, list):
        return []

    query_text = str(query).lower().strip()

    if not query_text:
        return []

    results = []

    for item in items:
        symbol = str(item.get("symbol", "")).lower().strip()
        name = str(first_available(item.get("companyName"), item.get("name"))).lower().strip()

        if query_text in symbol or query_text in name:
            results.append(item)

    results.sort(
        key=lambda item: score_symbol_result(item, query),
        reverse=True,
    )

    return results[:limit]


def get_possible_symbols(user_input):
    symbol = user_input.upper().strip()

    if symbol in TICKER_FALLBACKS:
        return TICKER_FALLBACKS[symbol]

    return [symbol]


def search_symbols(query):
    results = []

    for endpoint in ["search-name", "search-symbol"]:
        data = fmp_request(endpoint, {"query": query})

        if isinstance(data, list):
            for item in data[:20]:
                symbol = item.get("symbol")

                if symbol and symbol not in results:
                    results.append(symbol)

    return results


def search_symbol_details(query):
    raw_results = []

    raw_results.extend(search_symbol_catalog(query, limit=50))

    for endpoint in ["search-name", "search-symbol"]:
        data = fmp_request(endpoint, {"query": query})

        if isinstance(data, list):
            raw_results.extend(data[:20])

    results = []
    seen_symbols = set()

    for item in raw_results:
        symbol = item.get("symbol")

        if not symbol:
            continue

        symbol_key = str(symbol).upper().strip()

        if symbol_key in seen_symbols:
            continue

        seen_symbols.add(symbol_key)
        results.append(item)

    results.sort(
        key=lambda item: score_symbol_result(item, query),
        reverse=True,
    )

    return results[:25]


def find_best_symbol(user_input):
    requested = user_input.upper().strip()
    candidates = get_possible_symbols(requested)

    for symbol in search_symbols(requested):
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
        },
    )

    if isinstance(data, list):
        return data[:limit]

    return []


def get_geopolitical_news(query):
    url = "https://api.gdeltproject.org/api/v2/doc/doc"

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 10,
        "timespan": "7d",
    }

    headers = {
        "User-Agent": "TelegramMarketSignalBot/1.0"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        articles = data.get("articles", [])

        if isinstance(articles, list):
            return articles[:10]

        return []

    except Exception:
        return []


def calculate_pe_ratio(stock, metrics, ratios):
    values = []

    if stock:
        values.extend(
            [
                stock.get("pe"),
                stock.get("peRatio"),
                stock.get("priceEarningsRatio"),
            ]
        )

    if metrics:
        values.extend(
            [
                metrics.get("peRatio"),
                metrics.get("priceEarningsRatio"),
                metrics.get("priceToEarningsRatio"),
            ]
        )

    if ratios:
        values.extend(
            [
                ratios.get("peRatio"),
                ratios.get("priceEarningsRatio"),
                ratios.get("priceToEarningsRatio"),
            ]
        )

    for value in values:
        if value is not None and value != "" and value != 0:
            return value

    price = stock.get("price") if stock else None
    eps = stock.get("eps") if stock else None

    try:
        if price and eps and float(eps) != 0:
            return float(price) / float(eps)
    except Exception:
        pass

    return "Unbekannt"


def calculate_roe(metrics, ratios):
    values = []

    if ratios:
        values.extend(
            [
                ratios.get("returnOnEquity"),
                ratios.get("roe"),
                ratios.get("returnOnEquityRatio"),
            ]
        )

    if metrics:
        values.extend(
            [
                metrics.get("returnOnEquity"),
                metrics.get("roe"),
            ]
        )

    for value in values:
        if value is not None and value != "" and value != 0:
            return value

    return "Unbekannt"


def calculate_debt_to_equity(ratios, metrics):
    values = []

    if ratios:
        values.extend(
            [
                ratios.get("debtEquityRatio"),
                ratios.get("debtToEquity"),
                ratios.get("debtToEquityRatio"),
            ]
        )

    if metrics:
        values.extend(
            [
                metrics.get("debtToEquity"),
                metrics.get("debtEquityRatio"),
            ]
        )

    for value in values:
        if value is not None and value != "" and value != 0:
            return value

    return "Unbekannt"


def extract_growth_data(growth):
    if not growth:
        return {
            "revenue_growth": "Unbekannt",
            "net_income_growth": "Unbekannt",
            "free_cash_flow_growth": "Unbekannt",
            "eps_growth": "Unbekannt",
        }

    return {
        "revenue_growth": first_available(
            growth.get("revenueGrowth"),
            growth.get("growthRevenue"),
        ),
        "net_income_growth": first_available(
            growth.get("netIncomeGrowth"),
            growth.get("growthNetIncome"),
        ),
        "free_cash_flow_growth": first_available(
            growth.get("freeCashFlowGrowth"),
            growth.get("growthFreeCashFlow"),
        ),
        "eps_growth": first_available(
            growth.get("epsgrowth"),
            growth.get("epsGrowth"),
            growth.get("growthEPS"),
        ),
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


def detect_sector_profile(sector, industry):
    text = f"{sector} {industry}".lower()

    if "financial" in text or "bank" in text or "insurance" in text:
        return "financial"

    if "technology" in text or "software" in text or "semiconductor" in text:
        return "technology"

    if "energy" in text or "oil" in text or "gas" in text:
        return "energy"

    if "utility" in text or "utilities" in text:
        return "utilities"

    if "health" in text or "pharma" in text or "biotech" in text:
        return "healthcare"

    if "industrial" in text:
        return "industrial"

    return "default"


def get_sector_thresholds(sector_profile):
    profiles = {
        "technology": {
            "pe_good": 35,
            "pe_bad": 70,
            "roe_good": 15,
            "roe_bad": 5,
            "growth_good": 10,
            "debt_good": 1,
            "debt_bad": 2,
            "weights": {
                "valuation": 0.11,
                "profitability": 0.17,
                "growth": 0.27,
                "leverage": 0.10,
                "momentum": 0.10,
                "news": 0.13,
                "geopolitics": 0.12,
            },
        },
        "financial": {
            "pe_good": 15,
            "pe_bad": 30,
            "roe_good": 12,
            "roe_bad": 5,
            "growth_good": 5,
            "debt_good": None,
            "debt_bad": None,
            "weights": {
                "valuation": 0.20,
                "profitability": 0.28,
                "growth": 0.18,
                "leverage": 0.00,
                "momentum": 0.12,
                "news": 0.12,
                "geopolitics": 0.10,
            },
        },
        "energy": {
            "pe_good": 15,
            "pe_bad": 35,
            "roe_good": 12,
            "roe_bad": 4,
            "growth_good": 3,
            "debt_good": 1.5,
            "debt_bad": 3,
            "weights": {
                "valuation": 0.20,
                "profitability": 0.17,
                "growth": 0.15,
                "leverage": 0.15,
                "momentum": 0.08,
                "news": 0.12,
                "geopolitics": 0.13,
            },
        },
        "default": {
            "pe_good": 25,
            "pe_bad": 50,
            "roe_good": 15,
            "roe_bad": 5,
            "growth_good": 5,
            "debt_good": 1,
            "debt_bad": 2,
            "weights": {
                "valuation": 0.16,
                "profitability": 0.20,
                "growth": 0.20,
                "leverage": 0.12,
                "momentum": 0.09,
                "news": 0.12,
                "geopolitics": 0.11,
            },
        },
    }

    return profiles.get(sector_profile, profiles["default"])


def score_valuation(pe_ratio, thresholds):
    value = to_float(pe_ratio)

    if value is None or value <= 0:
        return None, "Bewertung: keine belastbare KGV-Bewertung moeglich"

    if value <= thresholds["pe_good"]:
        return 85, "Bewertung: KGV wirkt im Branchenkontext attraktiv/moderat"

    if value <= thresholds["pe_bad"]:
        return 55, "Bewertung: KGV wirkt im Branchenkontext neutral bis ambitioniert"

    return 25, "Bewertung: KGV wirkt im Branchenkontext hoch"


def score_profitability(roe, thresholds):
    value = normalize_percent_value(roe)

    if value is None:
        return None, "Profitabilitaet: ROE nicht verfuegbar"

    if value >= thresholds["roe_good"]:
        return 85, "Profitabilitaet: ROE stark"

    if value >= thresholds["roe_bad"]:
        return 55, "Profitabilitaet: ROE solide"

    return 25, "Profitabilitaet: ROE schwach"


def score_growth(revenue_growth, net_income_growth, thresholds):
    scores = []

    for raw_value in [revenue_growth, net_income_growth]:
        value = normalize_percent_value(raw_value)

        if value is None:
            continue

        if value > thresholds["growth_good"]:
            scores.append(85)
        elif value >= 0:
            scores.append(60)
        else:
            scores.append(25)

    if not scores:
        return None, "Wachstum: Umsatz- und Gewinnwachstum nicht verfuegbar"

    average_score = sum(scores) / len(scores)

    if average_score >= 75:
        return average_score, "Wachstum: Umsatz/Gewinn entwickeln sich stark"

    if average_score >= 50:
        return average_score, "Wachstum: Umsatz/Gewinn wirken stabil bis moderat"

    return average_score, "Wachstum: Umsatz/Gewinn wirken schwach oder ruecklaeufig"


def score_leverage(debt_to_equity, thresholds, sector_profile):
    if sector_profile == "financial":
        return None, "Verschuldung: bei Finanzwerten nicht ueber Standard-Debt/Equity bewertet"

    value = to_float(debt_to_equity)

    if value is None:
        return None, "Verschuldung: Debt/Equity nicht verfuegbar"

    if thresholds["debt_good"] is not None and value <= thresholds["debt_good"]:
        return 80, "Verschuldung: wirkt kontrolliert"

    if thresholds["debt_bad"] is not None and value <= thresholds["debt_bad"]:
        return 55, "Verschuldung: wirkt beobachtenswert, aber nicht extrem"

    return 25, "Verschuldung: wirkt erhoeht"


def score_momentum(change_percent):
    value = normalize_percent_value(change_percent)

    if value is None:
        return None, "Momentum: Tagesveraenderung nicht verfuegbar"

    if value >= 2:
        return 75, "Momentum: kurzfristig positiv"

    if value <= -2:
        return 35, "Momentum: kurzfristig negativ"

    return 55, "Momentum: kurzfristig neutral"


def analyze_news_sentiment(news_items):
    positive_keywords = [
        "beat",
        "beats",
        "upgrade",
        "upgraded",
        "outperform",
        "bullish",
        "growth",
        "record",
        "strong",
        "surge",
        "rally",
        "profit",
        "profits",
        "raises guidance",
        "strong demand",
        "partnership",
        "approval",
        "buy rating",
        "positive",
        "optimistic",
        "expands",
        "launches",
        "uebertrifft",
        "stark",
        "steigt",
        "gewinnsprung",
        "angehoben",
        "positive prognose",
        "kooperation",
    ]

    negative_keywords = [
        "miss",
        "misses",
        "downgrade",
        "downgraded",
        "underperform",
        "bearish",
        "lawsuit",
        "probe",
        "investigation",
        "weak",
        "decline",
        "falls",
        "drops",
        "plunge",
        "loss",
        "losses",
        "cuts guidance",
        "weak demand",
        "layoffs",
        "recall",
        "sell rating",
        "negative",
        "concern",
        "concerns",
        "risk",
        "risks",
        "verfehlt",
        "faellt",
        "gewinnwarnung",
        "schwach",
        "klage",
        "ermittlungen",
        "risiko",
        "stellenabbau",
        "senkt prognose",
    ]

    score = 0
    headlines = []

    for item in news_items:
        title = first_available(
            item.get("title"),
            item.get("headline"),
        )

        text = first_available(
            item.get("text"),
            item.get("snippet"),
            item.get("summary"),
        )

        combined = f"{title} {text}".lower()
        item_score = 0

        for keyword in positive_keywords:
            if keyword in combined:
                item_score += 1

        for keyword in negative_keywords:
            if keyword in combined:
                item_score -= 1

        if item_score > 0:
            score += 1
        elif item_score < 0:
            score -= 1

        if title != "Unbekannt":
            headlines.append(title)

    if score >= 2:
        sentiment = "positiv"
    elif score <= -2:
        sentiment = "negativ"
    else:
        sentiment = "neutral"

    return {
        "score": score,
        "sentiment": sentiment,
        "headlines": headlines[:3],
    }


def build_geopolitical_queries(company, used_symbol):
    sector = str(company.get("sector", "")).lower()
    industry = str(company.get("industry", "")).lower()
    company_name = str(company.get("company_name", used_symbol))

    if "technology" in sector or "semiconductor" in industry or "software" in industry:
        return [
            f'"{company_name}" "export controls"',
            f'"{company_name}" "supply chain"',
            f'{used_symbol} "China"',
            f'{used_symbol} "Taiwan"',
            '"semiconductor" "export controls"',
            '"chips" "Taiwan" "China"',
            '"AI chips" "China restrictions"',
            '"Halbleiter" "China" "Taiwan"',
        ]

    if "energy" in sector or "oil" in industry or "gas" in industry:
        return [
            f'"{company_name}" "oil sanctions"',
            f'"{company_name}" "energy security"',
            f'{used_symbol} "Middle East"',
            f'{used_symbol} "Russia sanctions"',
            '"oil" "Middle East conflict"',
            '"OPEC" "supply disruption"',
            '"energy security" "sanctions"',
        ]

    if "financial" in sector or "bank" in industry:
        return [
            f'"{company_name}" "banking risk"',
            f'"{company_name}" "sanctions"',
            f'{used_symbol} "financial stability"',
            '"banking crisis" "interest rates"',
            '"sanctions" "financial markets"',
        ]

    return [
        f'"{company_name}" "geopolitical risk"',
        f'"{company_name}" "sanctions"',
        f'{used_symbol} "supply chain"',
        '"geopolitical risk" "stocks"',
        '"sanctions" "global markets"',
    ]


def get_geopolitical_articles_with_fallback(company, used_symbol):
    articles_all = []
    seen_titles = set()

    for query in build_geopolitical_queries(company, used_symbol):
        articles = get_geopolitical_news(query)

        for article in articles:
            title = article.get("title")

            if title and title not in seen_titles:
                articles_all.append(article)
                seen_titles.add(title)

        if len(articles_all) >= 5:
            break

    return articles_all[:10]


def analyze_geopolitical_risk(articles):
    high_keywords = [
        "war",
        "invasion",
        "sanctions",
        "export controls",
        "military",
        "blockade",
        "conflict",
        "tariffs",
        "trade war",
        "supply disruption",
        "escalation",
        "krieg",
        "sanktionen",
        "exportkontrollen",
        "militaer",
        "konflikt",
        "zoelle",
        "handelskrieg",
        "lieferkettenstoerung",
        "eskalation",
    ]

    medium_keywords = [
        "tensions",
        "restrictions",
        "regulation",
        "probe",
        "investigation",
        "political risk",
        "supply chain",
        "uncertainty",
        "spannungen",
        "beschraenkungen",
        "regulierung",
        "ermittlung",
        "politisches risiko",
        "lieferkette",
        "unsicherheit",
    ]

    score = 50
    risk_hits = []
    headlines = []

    for article in articles:
        title = first_available(
            article.get("title"),
            article.get("seendate"),
        )

        domain = first_available(
            article.get("domain"),
            article.get("sourceCountry"),
        )

        combined = f"{title} {domain}".lower()

        for keyword in high_keywords:
            if keyword in combined:
                score -= 10
                risk_hits.append(keyword)

        for keyword in medium_keywords:
            if keyword in combined:
                score -= 5
                risk_hits.append(keyword)

        if title != "Unbekannt":
            headlines.append(title)

    score = max(0, min(100, score))

    if score >= 70:
        level = "niedrig"
    elif score >= 40:
        level = "mittel"
    else:
        level = "hoch"

    unique_risks = []

    for item in risk_hits:
        if item not in unique_risks:
            unique_risks.append(item)

    return {
        "score": score,
        "risk_level": level,
        "risk_terms": unique_risks[:5],
        "headlines": headlines[:3],
    }


def score_news_sentiment(news_score):
    value = to_float(news_score)

    if value is None:
        return None, "News: keine auswertbaren Nachrichten verfuegbar"

    if value >= 2:
        return 80, "News: Sentiment ueberwiegend positiv"

    if value <= -2:
        return 30, "News: Sentiment ueberwiegend negativ"

    return 55, "News: Sentiment neutral bis gemischt"


def score_geopolitics(geopolitical_score):
    value = to_float(geopolitical_score)

    if value is None:
        return None, "Geopolitik: keine auswertbaren Daten verfuegbar"

    if value >= 70:
        return 80, "Geopolitik: Risiko wirkt aktuell niedrig"

    if value >= 40:
        return 55, "Geopolitik: Risiko wirkt moderat"

    return 25, "Geopolitik: Risiko wirkt erhoeht"


def calculate_professional_research_score(
    company,
    change_percent,
    pe_ratio,
    roe,
    revenue_growth,
    net_income_growth,
    debt_to_equity,
    news_score,
    geopolitical_score,
):
    sector_profile = detect_sector_profile(
        company["sector"],
        company["industry"],
    )

    thresholds = get_sector_thresholds(sector_profile)
    weights = thresholds["weights"]

    factor_results = {
        "valuation": score_valuation(pe_ratio, thresholds),
        "profitability": score_profitability(roe, thresholds),
        "growth": score_growth(revenue_growth, net_income_growth, thresholds),
        "leverage": score_leverage(debt_to_equity, thresholds, sector_profile),
        "momentum": score_momentum(change_percent),
        "news": score_news_sentiment(news_score),
        "geopolitics": score_geopolitics(geopolitical_score),
    }

    weighted_sum = 0
    used_weight = 0
    notes = []
    factor_scores = {}

    for factor, result in factor_results.items():
        factor_score, note = result
        notes.append(note)

        if factor_score is None:
            factor_scores[factor] = "Unbekannt"
            continue

        weight = weights.get(factor, 0)

        if weight <= 0:
            factor_scores[factor] = "Nicht gewichtet"
            continue

        weighted_sum += factor_score * weight
        used_weight += weight
        factor_scores[factor] = round(factor_score, 1)

    if used_weight == 0:
        final_score = 50
    else:
        final_score = weighted_sum / used_weight

    available_factors = sum(
        1
        for value in factor_scores.values()
        if value != "Unbekannt" and value != "Nicht gewichtet"
    )

    if available_factors >= 6:
        data_quality = "hoch"
    elif available_factors >= 4:
        data_quality = "mittel"
    else:
        data_quality = "niedrig"

    if final_score >= 70:
        signal = "LONG-KANDIDAT"
    elif final_score <= 40:
        signal = "SHORT-/RISIKO-KANDIDAT"
    else:
        signal = "NEUTRAL"

    return {
        "score": round(final_score, 1),
        "signal": signal,
        "notes": notes,
        "sector_profile": sector_profile,
        "data_quality": data_quality,
        "available_factors": available_factors,
        "factor_scores": factor_scores,
    }


def build_analysis(requested_ticker):
    used_symbol, stock, tried_symbols = find_best_symbol(requested_ticker)

    if not stock:
        return {
            "found": False,
            "requested_ticker": requested_ticker,
            "tried_symbols": tried_symbols,
        }

    profile = get_company_profile(used_symbol)
    metrics = get_key_metrics(used_symbol)
    ratios = get_ratios(used_symbol)
    growth = get_financial_growth(used_symbol)

    news_items = get_stock_news(used_symbol)
    news_sentiment = analyze_news_sentiment(news_items)

    company = extract_company_data(profile, metrics)
    growth_data = extract_growth_data(growth)

    geo_articles = get_geopolitical_articles_with_fallback(company, used_symbol)
    geo_risk = analyze_geopolitical_risk(geo_articles)

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

    research = calculate_professional_research_score(
        company=company,
        change_percent=change_percent,
        pe_ratio=pe_ratio,
        roe=roe,
        revenue_growth=growth_data["revenue_growth"],
        net_income_growth=growth_data["net_income_growth"],
        debt_to_equity=debt_to_equity,
        news_score=news_sentiment["score"],
        geopolitical_score=geo_risk["score"],
    )

    return {
        "found": True,
        "requested_ticker": requested_ticker,
        "used_symbol": used_symbol,
        "company": company,
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "volume": volume,
        "pe_ratio": pe_ratio,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "revenue_growth": growth_data["revenue_growth"],
        "net_income_growth": growth_data["net_income_growth"],
        "free_cash_flow_growth": growth_data["free_cash_flow_growth"],
        "eps_growth": growth_data["eps_growth"],
        "news_sentiment": news_sentiment,
        "geopolitical_risk": geo_risk,
        "research": research,
    }


def format_symbol_search_result(index, item):
    symbol = first_available(item.get("symbol"))
    name = get_symbol_name(item)
    exchange = get_symbol_exchange(item)
    currency = get_symbol_currency(item)
    result_type = get_symbol_type(item)

    details = []

    if exchange != "Unbekannt":
        details.append(f"Boerse: {exchange}")

    if currency != "Unbekannt":
        details.append(f"Waehrung: {currency}")

    if result_type != "Unbekannt":
        details.append(f"Typ: {result_type}")

    text = f"{index}. {symbol} - {name}\n"

    if details:
        text += f"   {' | '.join(details)}\n"

    text += f"   Analyse: /analyse {symbol}\n"

    return text


def render_not_found(data):
    requested_ticker = data["requested_ticker"]
    tried_symbols = data.get("tried_symbols", [])
    tried_text = ", ".join(tried_symbols) if tried_symbols else requested_ticker

    suggestions = search_symbol_details(requested_ticker)
    suggestion_text = ""

    if suggestions:
        suggestion_text += "\nMoegliche Treffer:\n\n"

        for index, item in enumerate(suggestions[:5], start=1):
            suggestion_text += format_symbol_search_result(index, item)
            suggestion_text += "\n"

        suggestion_text += (
            "Tipp:\n"
            "Kopiere das passende Symbol exakt in /analyse.\n"
            "Beispiel: /analyse TTE\n\n"
        )

    return (
        f"Kein Boersendatensatz fuer {requested_ticker} gefunden.\n\n"
        f"Gepruefte Symbole: {tried_text}\n\n"
        f"{suggestion_text}"
        "Du kannst auch direkt suchen:\n"
        f"/suche {requested_ticker}\n\n"
        "Hinweis: Manche Aktien werden je nach Datenanbieter oder Boerse unter anderen Kuerzeln gefuehrt."
    )


def render_compact_analysis(data):
    company = data["company"]
    research = data["research"]
    news = data["news_sentiment"]
    geo = data["geopolitical_risk"]

    used_symbol_note = ""

    if data["used_symbol"] != data["requested_ticker"]:
        used_symbol_note = f"Symbol: {data['used_symbol']}\n"

    top_reasons = ""

    for note in research["notes"][:3]:
        top_reasons += f"- {note}\n"

    return (
        f"{data['requested_ticker']} Kurz-Analyse\n\n"
        f"{used_symbol_note}"
        f"Unternehmen: {company['company_name']}\n"
        f"Branche: {company['sector']}\n\n"
        f"Signal: {research['signal']}\n"
        f"Score: {research['score']} / 100\n"
        f"Datenqualitaet: {research['data_quality']} ({research['available_factors']} Faktoren)\n"
        f"News: {news['sentiment']} ({news['score']})\n"
        f"Geopolitik: {geo['risk_level']} ({geo['score']} / 100)\n\n"
        f"Kurs: {format_number(data['price'])} USD\n"
        f"Aenderung: {format_percent(data['change_percent'])}\n\n"
        f"Top-Gruende:\n"
        f"{top_reasons}\n"
        f"Fuer Details:\n"
        f"/details {data['requested_ticker']}\n\n"
        "Hinweis: Keine Anlageberatung."
    )


def render_detailed_analysis(data):
    company = data["company"]
    research = data["research"]
    news = data["news_sentiment"]
    geo = data["geopolitical_risk"]

    used_symbol_note = ""

    if data["used_symbol"] != data["requested_ticker"]:
        used_symbol_note = f"Verwendetes FMP-Symbol: {data['used_symbol']}\n\n"

    notes_text = ""

    for note in research["notes"][:8]:
        notes_text += f"- {note}\n"

    headline_text = ""

    if news["headlines"]:
        for headline in news["headlines"]:
            headline_text += f"- {headline}\n"
    else:
        headline_text = "- Keine aktuellen Headlines verfuegbar\n"

    geo_headline_text = ""

    if geo["headlines"]:
        for headline in geo["headlines"]:
            geo_headline_text += f"- {headline}\n"
    else:
        geo_headline_text = "- Keine geopolitischen Headlines verfuegbar\n"

    if geo["risk_terms"]:
        risk_terms_text = ", ".join(geo["risk_terms"])
    else:
        risk_terms_text = "Keine auffaelligen Begriffe"

    factor_text = (
        f"Bewertung: {research['factor_scores']['valuation']}\n"
        f"Profitabilitaet: {research['factor_scores']['profitability']}\n"
        f"Wachstum: {research['factor_scores']['growth']}\n"
        f"Verschuldung: {research['factor_scores']['leverage']}\n"
        f"Momentum: {research['factor_scores']['momentum']}\n"
        f"News: {research['factor_scores']['news']}\n"
        f"Geopolitik: {research['factor_scores']['geopolitics']}\n"
    )

    return (
        f"Detailanalyse fuer {data['requested_ticker']}\n\n"
        f"{used_symbol_note}"
        f"Unternehmen: {company['company_name']}\n"
        f"Branche: {company['sector']}\n"
        f"Industrie: {company['industry']}\n"
        f"Land: {company['country']}\n"
        f"Marktkapitalisierung: {format_market_cap(company['market_cap'])}\n\n"
        f"Fundamentaldaten\n"
        f"KGV: {format_number(data['pe_ratio'])}\n"
        f"ROE: {format_percent(data['roe'])}\n"
        f"Debt/Equity: {format_number(data['debt_to_equity'])}\n"
        f"Umsatzwachstum: {format_percent(data['revenue_growth'])}\n"
        f"Gewinnwachstum: {format_percent(data['net_income_growth'])}\n"
        f"Free-Cashflow-Wachstum: {format_percent(data['free_cash_flow_growth'])}\n"
        f"EPS-Wachstum: {format_percent(data['eps_growth'])}\n\n"
        f"Marktdaten\n"
        f"Kurs: {format_number(data['price'])} USD\n"
        f"Aenderung: {format_number(data['change'])}\n"
        f"Aenderung %: {format_percent(data['change_percent'])}\n"
        f"Volumen: {data['volume']}\n\n"
        f"News-Sentiment\n"
        f"News-Score: {news['score']}\n"
        f"Sentiment: {news['sentiment']}\n"
        f"Aktuelle Headlines:\n"
        f"{headline_text}"
        f"Geopolitik-Risiko\n"
        f"Risiko: {geo['risk_level']}\n"
        f"Score: {geo['score']} / 100\n"
        f"Risikobegriffe: {risk_terms_text}\n"
        f"Geopolitische Headlines:\n"
        f"{geo_headline_text}"
        f"Professioneller Research-Score\n"
        f"Sektorprofil: {research['sector_profile']}\n"
        f"Datenqualitaet: {research['data_quality']} ({research['available_factors']} Faktoren)\n"
        f"Score: {research['score']} / 100\n"
        f"Signal: {research['signal']}\n\n"
        f"Teilbewertungen:\n"
        f"{factor_text}\n"
        f"Gruende:\n"
        f"{notes_text}\n"
        "Hinweis: Keine Anlageberatung. Dieses Signal ist nur ein automatisierter Research-Hinweis."
    )


def make_alert_id(source, symbol, title):
    raw = f"{source}|{symbol}|{title}"
    return raw.lower().strip()


def send_telegram_message(chat_id, text):
    if not TOKEN:
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def build_news_alert(symbol, title):
    return (
        f"Neue Aktienmeldung zu {symbol}\n\n"
        f"{title}\n\n"
        f"Analyse:\n"
        f"/analyse {symbol}\n\n"
        f"Details:\n"
        f"/details {symbol}\n\n"
        "Hinweis: Keine Anlageberatung."
    )


def build_geo_alert(symbol, title):
    return (
        f"Neue geopolitische Meldung zu {symbol}\n\n"
        f"{title}\n\n"
        f"Analyse:\n"
        f"/analyse {symbol}\n\n"
        f"Details:\n"
        f"/details {symbol}\n\n"
        "Hinweis: Keine Anlageberatung."
    )


def check_alerts_once():
    watchlists = load_watchlists()
    seen = load_seen_alerts()
    changed = False

    for chat_id, symbols in watchlists.items():
        for requested_symbol in symbols:
            used_symbol, stock, _ = find_best_symbol(requested_symbol)

            if not stock:
                continue

            profile = get_company_profile(used_symbol)
            metrics = get_key_metrics(used_symbol)
            company = extract_company_data(profile, metrics)

            stock_news = get_stock_news(used_symbol, limit=3)

            for item in stock_news:
                title = first_available(
                    item.get("title"),
                    item.get("headline"),
                )

                if title == "Unbekannt":
                    continue

                alert_id = make_alert_id("fmp_news", used_symbol, title)

                if alert_id not in seen:
                    seen[alert_id] = int(time.time())
                    changed = True
                    send_telegram_message(
                        chat_id,
                        build_news_alert(requested_symbol, title),
                    )

            geo_articles = get_geopolitical_articles_with_fallback(
                company,
                used_symbol,
            )

            for article in geo_articles[:3]:
                title = first_available(
                    article.get("title"),
                    article.get("seendate"),
                )

                if title == "Unbekannt":
                    continue

                alert_id = make_alert_id("gdelt_geo", used_symbol, title)

                if alert_id not in seen:
                    seen[alert_id] = int(time.time())
                    changed = True
                    send_telegram_message(
                        chat_id,
                        build_geo_alert(requested_symbol, title),
                    )

    if changed:
        save_seen_alerts(seen)


def alert_worker():
    while True:
        try:
            check_alerts_once()
        except Exception:
            pass

        time.sleep(ALERT_INTERVAL_SECONDS)


async def send_text(update, text):
    max_length = 3900

    if len(text) <= max_length:
        await update.message.reply_text(text)
        return

    parts = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            parts.append(current)
            current = line
        else:
            current += "\n" + line if current else line

    if current:
        parts.append(current)

    for part in parts:
        await update.message.reply_text(part)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot laeuft erfolgreich auf Render!\n\n"
        "Nutze /help fuer alle Befehle."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Verfuegbare Befehle:\n\n"
        "/start - Bot starten\n"
        "/analyse AAPL - kompakte Analyse\n"
        "/details AAPL - vollstaendige Detailanalyse\n"
        "/watch AAPL - Ticker beobachten\n"
        "/unwatch AAPL - Ticker entfernen\n"
        "/watchlist - beobachtete Ticker anzeigen\n"
        "/alerttest - Alert-Pruefung manuell starten\n"
        "/stocksync - Symbolkatalog von FMP laden\n"
        "/symbolcount - Anzahl gespeicherter Symbole anzeigen\n"
        "/suche Toyota - Symbol weltweit suchen\n"
        "/info - Informationen zum Bot\n"
        "/help - Hilfe anzeigen"
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Telegram Market Signal Bot\n\n"
        "Der Bot kann aktuell:\n"
        "- kompakte Analyse mit /analyse liefern\n"
        "- ausfuehrliche Detailanalyse mit /details liefern\n"
        "- Kursdaten, Fundamentaldaten und News-Sentiment auswerten\n"
        "- Geopolitik-Risiko ueber GDELT einbeziehen\n"
        "- branchenspezifischen Research-Score berechnen\n"
        "- Ticker mit /watch beobachten\n"
        "- automatische News- und Geopolitik-Alerts senden\n"
        "- globale Symbolsuche mit /suche nutzen\n"
        "- Symbolkatalog mit /stocksync laden\n"
        "- Anzahl gespeicherter Symbole mit /symbolcount anzeigen\n\n"
        "Hinweis: Keine Anlageberatung."
    )


async def suche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n"
            "/suche SAP\n\n"
            "Beispiele:\n"
            "/suche Toyota\n"
            "/suche Samsung\n"
            "/suche Shell\n"
            "/suche Nvidia"
        )
        return

    query = " ".join(context.args).strip()
    results = search_symbol_details(query)

    if not results:
        await update.message.reply_text(
            f"Keine Symbole fuer '{query}' gefunden.\n\n"
            "Tipps:\n"
            "- Suche nach dem Unternehmensnamen, z. B. /suche Toyota\n"
            "- Suche nach dem bekannten Ticker, z. B. /suche AAPL\n"
            "- Bei Auslandsaktien ist oft ein Boersen-Suffix noetig, z. B. .DE, .T, .HK oder .L"
        )
        return

    text = f"Suchergebnisse fuer '{query}':\n\n"

    for index, item in enumerate(results[:15], start=1):
        text += format_symbol_search_result(index, item)
        text += "\n"

    text += (
        "Tipp:\n"
        "Kopiere das passende Symbol exakt in /analyse.\n"
        "Beispiel: /analyse 7203.T"
    )

    await send_text(update, text)


async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/analyse AAPL"
        )
        return

    requested_ticker = context.args[0].upper().strip()
    data = build_analysis(requested_ticker)

    if not data["found"]:
        await send_text(update, render_not_found(data))
        return

    await send_text(update, render_compact_analysis(data))


async def details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/details AAPL"
        )
        return

    requested_ticker = context.args[0].upper().strip()
    data = build_analysis(requested_ticker)

    if not data["found"]:
        await send_text(update, render_not_found(data))
        return

    await send_text(update, render_detailed_analysis(data))


async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/watch AAPL"
        )
        return

    chat_id = str(update.effective_chat.id)
    ticker = context.args[0].upper().strip()

    watchlists = load_watchlists()
    symbols = watchlists.get(chat_id, [])

    if ticker not in symbols:
        symbols.append(ticker)

    watchlists[chat_id] = symbols
    save_watchlists(watchlists)

    await update.message.reply_text(
        f"{ticker} wird jetzt beobachtet.\n\n"
        "Du erhaeltst Alerts bei neuen Aktien-News oder geopolitischen Meldungen."
    )


async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Bitte nutze:\n/unwatch AAPL"
        )
        return

    chat_id = str(update.effective_chat.id)
    ticker = context.args[0].upper().strip()

    watchlists = load_watchlists()
    symbols = watchlists.get(chat_id, [])

    if ticker in symbols:
        symbols.remove(ticker)

    watchlists[chat_id] = symbols
    save_watchlists(watchlists)

    await update.message.reply_text(
        f"{ticker} wurde aus deiner Watchlist entfernt."
    )


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    watchlists = load_watchlists()
    symbols = watchlists.get(chat_id, [])

    if not symbols:
        await update.message.reply_text(
            "Deine Watchlist ist leer.\n\n"
            "Nutze zum Beispiel:\n/watch AAPL"
        )
        return

    text = "Deine Watchlist:\n\n"

    for symbol in symbols:
        text += f"- {symbol}\n"

    await update.message.reply_text(text)


async def alerttest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Alert-Pruefung wird jetzt einmal ausgefuehrt."
    )

    check_alerts_once()

    await update.message.reply_text(
        "Alert-Pruefung abgeschlossen."
    )


async def stocksync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Symbolkatalog wird jetzt von FMP geladen."
    )

    count = sync_symbol_cache()

    if count <= 0:
        await update.message.reply_text(
            "Symbolkatalog konnte nicht geladen werden.\n"
            "Bitte pruefe FMP_API_KEY und ob dein FMP-Tarif den stock-list Endpoint erlaubt."
        )
        return

    await update.message.reply_text(
        f"Symbolkatalog wurde aktualisiert.\n\n"
        f"Gespeicherte Symbole: {count}\n\n"
        "Teste jetzt z. B.:\n"
        "/suche Shell\n"
        "/suche TotalEnergies\n"
        "/suche Toyota\n"
        "/suche Samsung"
    )


async def symbolcount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_symbol_cache_count()
    synced_at = get_symbol_cache_synced_at()

    if not synced_at:
        await update.message.reply_text(
            "Es ist noch kein Symbolkatalog gespeichert.\n\n"
            "Starte zuerst:\n/stocksync"
        )
        return

    await update.message.reply_text(
        f"Aktueller Symbolkatalog:\n\n"
        f"Gespeicherte Symbole: {count}\n"
        f"Sync-Zeitstempel: {synced_at}"
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

    threading.Thread(
        target=alert_worker,
        daemon=True,
    ).start()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyse", analyse))
    app.add_handler(CommandHandler("details", details))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("unwatch", unwatch))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("alerttest", alerttest))
    app.add_handler(CommandHandler("stocksync", stocksync))
    app.add_handler(CommandHandler("symbolcount", symbolcount))
    app.add_handler(CommandHandler("suche", suche))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info))

    print("Bot gestartet")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
