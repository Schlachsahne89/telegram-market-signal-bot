import os
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

from openai import OpenAI

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.getenv("TELEGRAM_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")
PORT = int(os.getenv("PORT", 10000))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


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


def get_stock_news(symbol):
    data = fmp_request(
        "news/stock",
        {
            "symbols": symbol,
            "limit": 5,
        },
    )

    if isinstance(data, list):
        return data[:5]

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


def normalize_percent_value(value):
    number = to_float(value)

    if number is None:
        return None

    if abs(number) <= 1:
        return number * 100

    return number


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

    number = normalize_percent_value(value)

    if number is None:
        return "Unbekannt"

    return f"{number:.2f}%".replace(".", ",")


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
    if "consumer defensive" in text or "staples" in text:
        return "defensive"
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
        "utilities": {
            "pe_good": 25,
            "pe_bad": 45,
            "roe_good": 10,
            "roe_bad": 4,
            "growth_good": 3,
            "debt_good": 2,
            "debt_bad": 4,
            "weights": {
                "valuation": 0.17,
                "profitability": 0.17,
                "growth": 0.10,
                "leverage": 0.25,
                "momentum": 0.08,
                "news": 0.11,
                "geopolitics": 0.12,
            },
        },
        "healthcare": {
            "pe_good": 30,
            "pe_bad": 60,
            "roe_good": 12,
            "roe_bad": 4,
            "growth_good": 7,
            "debt_good": 1.2,
            "debt_bad": 2.5,
            "weights": {
                "valuation": 0.17,
                "profitability": 0.17,
                "growth": 0.25,
                "leverage": 0.10,
                "momentum": 0.08,
                "news": 0.13,
                "geopolitics": 0.10,
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
    pe_value = to_float(pe_ratio)

    if pe_value is None or pe_value <= 0:
        return None, "Bewertung: keine belastbare KGV-Bewertung möglich"

    if pe_value <= thresholds["pe_good"]:
        return 85, "Bewertung: KGV wirkt im Branchenkontext attraktiv/moderat"

    if pe_value <= thresholds["pe_bad"]:
        return 55, "Bewertung: KGV wirkt im Branchenkontext neutral bis ambitioniert"

    return 25, "Bewertung: KGV wirkt im Branchenkontext hoch"


def score_profitability(roe, thresholds):
    roe_value = normalize_percent_value(roe)

    if roe_value is None:
        return None, "Profitabilität: ROE nicht verfügbar"

    if roe_value >= thresholds["roe_good"]:
        return 85, "Profitabilität: ROE stark"

    if roe_value >= thresholds["roe_bad"]:
        return 55, "Profitabilität: ROE solide"

    return 25, "Profitabilität: ROE schwach"


def score_growth(revenue_growth, net_income_growth, thresholds):
    values = []

    revenue_value = normalize_percent_value(revenue_growth)
    income_value = normalize_percent_value(net_income_growth)

    for value in [revenue_value, income_value]:
        if value is None:
            continue

        if value > thresholds["growth_good"]:
            values.append(85)
        elif value >= 0:
            values.append(60)
        else:
            values.append(25)

    if not values:
        return None, "Wachstum: Umsatz- und Gewinnwachstum nicht verfügbar"

    avg_score = sum(values) / len(values)

    if avg_score >= 75:
        return avg_score, "Wachstum: Umsatz/Gewinn entwickeln sich stark"

    if avg_score >= 50:
        return avg_score, "Wachstum: Umsatz/Gewinn wirken stabil bis moderat"

    return avg_score, "Wachstum: Umsatz/Gewinn wirken schwach oder rückläufig"


def score_leverage(debt_to_equity, thresholds, sector_profile):
    if sector_profile == "financial":
        return None, "Verschuldung: bei Finanzwerten nicht über Standard-Debt/Equity bewertet"

    debt_value = to_float(debt_to_equity)

    if debt_value is None:
        return None, "Verschuldung: Debt/Equity nicht verfügbar"

    debt_good = thresholds["debt_good"]
    debt_bad = thresholds["debt_bad"]

    if debt_good is not None and debt_value <= debt_good:
        return 80, "Verschuldung: wirkt kontrolliert"

    if debt_bad is not None and debt_value <= debt_bad:
        return 55, "Verschuldung: wirkt beobachtenswert, aber nicht extrem"

    return 25, "Verschuldung: wirkt erhöht"


def score_momentum(change_percent):
    value = normalize_percent_value(change_percent)

    if value is None:
        return None, "Momentum: Tagesveränderung nicht verfügbar"

    if value >= 2:
        return 75, "Momentum: kurzfristig positiv"

    if value <= -2:
        return 35, "Momentum: kurzfristig negativ"

    return 55, "Momentum: kurzfristig neutral"


def analyze_news_sentiment(news_items):
    positive_keywords = [
        "beat", "beats", "upgrade", "upgraded", "outperform",
        "bullish", "growth", "record", "strong", "surge",
        "rally", "profit", "profits", "revenue growth",
        "raises guidance", "strong demand", "partnership",
        "approval", "buy rating", "positive", "optimistic",
        "expands", "launches",
        "übertrifft", "stark", "steigt", "gewinnsprung",
        "angehoben", "positive prognose", "kooperation",
    ]

    negative_keywords = [
        "miss", "misses", "downgrade", "downgraded", "underperform",
        "bearish", "lawsuit", "probe", "investigation", "weak",
        "decline", "falls", "drops", "plunge", "loss", "losses",
        "revenue decline", "cuts guidance", "weak demand", "layoffs",
        "recall", "sell rating", "negative", "concern", "concerns",
        "risk", "risks", "verfehlt", "fällt", "gewinnwarnung",
        "schwach", "klage", "ermittlungen", "risiko",
        "stellenabbau", "senkt prognose",
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
            item.get("site"),
        )

        combined_text = f"{title} {text}".lower()

        item_score = 0

        for word in positive_keywords:
            if word in combined_text:
                item_score += 1

        for word in negative_keywords:
            if word in combined_text:
                item_score -= 1

        api_sentiment = first_available(
            item.get("sentiment"),
            item.get("sentimentScore"),
        )

        api_sentiment_text = str(api_sentiment).lower()

        if "positive" in api_sentiment_text:
            item_score += 1
        elif "negative" in api_sentiment_text:
            item_score -= 1

        api_sentiment_number = to_float(api_sentiment)

        if api_sentiment_number is not None:
            if api_sentiment_number >= 0.25:
                item_score += 1
            elif api_sentiment_number <= -0.25:
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
    country = str(company.get("country", "")).lower()
    company_name = str(company.get("company_name", used_symbol))

    if "technology" in sector or "semiconductor" in industry or "software" in industry:
        queries = [
            f'"{company_name}" "export controls"',
            f'"{company_name}" "supply chain"',
            f'{used_symbol} "China"',
            f'{used_symbol} "Taiwan"',
            '"semiconductor" "export controls"',
            '"chips" "Taiwan" "China"',
            '"AI chips" "China restrictions"',
            '"Halbleiter" "China" "Taiwan"',
            '"Exportkontrollen" "Halbleiter"',
        ]

    elif "energy" in sector or "oil" in industry or "gas" in industry:
        queries = [
            f'"{company_name}" "oil sanctions"',
            f'"{company_name}" "energy security"',
            f'{used_symbol} "Middle East"',
            f'{used_symbol} "Russia sanctions"',
            '"oil" "Middle East conflict"',
            '"OPEC" "supply disruption"',
            '"energy security" "sanctions"',
            '"Energieversorgung" "Sanktionen"',
            '"Öl" "Nahost"',
        ]

    elif "financial" in sector or "bank" in industry:
        queries = [
            f'"{company_name}" "banking risk"',
            f'"{company_name}" "sanctions"',
            f'{used_symbol} "financial stability"',
            '"banking crisis" "interest rates"',
            '"sanctions" "financial markets"',
            '"Bankenkrise" "Zinsen"',
        ]

    elif "industrial" in sector or "industrial" in industry:
        queries = [
            f'"{company_name}" "supply chain"',
            f'"{company_name}" "tariffs"',
            f'{used_symbol} "China"',
            '"trade war" "supply chain"',
            '"tariffs" "industrial companies"',
            '"Lieferkette" "Zölle"',
        ]

    elif "health" in sector or "pharma" in industry or "biotech" in industry:
        queries = [
            f'"{company_name}" "drug regulation"',
            f'"{company_name}" "supply chain"',
            f'{used_symbol} "health policy"',
            '"pharma" "regulation"',
            '"biotech" "geopolitical risk"',
            '"Pharma" "Regulierung"',
        ]

    else:
        queries = [
            f'"{company_name}" "geopolitical risk"',
            f'"{company_name}" "sanctions"',
            f'{used_symbol} "supply chain"',
            '"geopolitical risk" "stocks"',
            '"sanctions" "global markets"',
            '"Sanktionen" "Aktienmärkte"',
        ]

    if country and country not in ["unbekannt", "unknown"]:
        queries.append(f'"{company_name}" "{country}" "political risk"')

    return queries


def get_geopolitical_articles_with_fallback(company, used_symbol):
    queries = build_geopolitical_queries(company, used_symbol)

    all_articles = []
    seen_titles = set()

    for query in queries:
        articles = get_geopolitical_news(query)

        for article in articles:
            title = article.get("title")

            if title and title not in seen_titles:
                all_articles.append(article)
                seen_titles.add(title)

        if len(all_articles) >= 5:
            break

    return all_articles[:10]


def analyze_geopolitical_risk(articles):
    high_risk_keywords = [
        "war", "invasion", "sanctions", "export controls",
        "military", "blockade", "conflict", "tariffs",
        "trade war", "supply disruption", "escalation",
        "krieg", "invasion", "sanktionen", "exportkontrollen",
        "militär", "blockade", "konflikt", "zölle",
        "handelskrieg", "lieferkettenstörung", "eskalation",
    ]

    medium_risk_keywords = [
        "tensions", "restrictions", "regulation", "probe",
        "investigation", "political risk", "supply chain",
        "uncertainty", "spannungen", "beschränkungen",
        "regulierung", "ermittlung", "politisches risiko",
        "lieferkette", "unsicherheit",
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

        combined_text = f"{title} {domain}".lower()

        for keyword in high_risk_keywords:
            if keyword in combined_text:
                score -= 10
                risk_hits.append(keyword)

        for keyword in medium_risk_keywords:
            if keyword in combined_text:
                score -= 5
                risk_hits.append(keyword)

        if title != "Unbekannt":
            headlines.append(title)

    score = max(0, min(100, score))

    if score >= 70:
        risk_level = "niedrig"
    elif score >= 40:
        risk_level = "mittel"
    else:
        risk_level = "hoch"

    unique_risks = []
    for item in risk_hits:
        if item not in unique_risks:
            unique_risks.append(item)

    return {
        "score": score,
        "risk_level": risk_level,
        "risk_terms": unique_risks[:5],
        "headlines": headlines[:3],
    }


def score_news_sentiment(news_score):
    value = to_float(news_score)

    if value is None:
        return None, "News: keine auswertbaren Nachrichten verfügbar"

    if value >= 2:
        return 80, "News: Sentiment überwiegend positiv"

    if value <= -2:
        return 30, "News: Sentiment überwiegend negativ"

    return 55, "News: Sentiment neutral bis gemischt"


def score_geopolitics(geopolitical_score):
    value = to_float(geopolitical_score)

    if value is None:
        return None, "Geopolitik: keine auswertbaren Daten verfügbar"

    if value >= 70:
        return 80, "Geopolitik: Risiko wirkt aktuell niedrig"

    if value >= 40:
        return 55, "Geopolitik: Risiko wirkt moderat"

    return 25, "Geopolitik: Risiko wirkt erhöht"


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
    sector_profile = detect_sector_profile(company["sector"], company["industry"])
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
        1 for value in factor_scores.values()
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


def build_ai_prompt(data):
    company = data["company"]
    research = data["research"]
    news = data["news_sentiment"]
    geo = data["geopolitical_risk"]

    headlines = news.get("headlines", [])
    geo_headlines = geo.get("headlines", [])

    news_text = "\n".join([f"- {headline}" for headline in headlines]) if headlines else "Keine aktuellen Aktien-News verfügbar."
    geo_text = "\n".join([f"- {headline}" for headline in geo_headlines]) if geo_headlines else "Keine geopolitischen Headlines verfügbar."

    prompt = f"""
Du bist ein vorsichtiger deutschsprachiger Finanz-Research-Assistent.

Wichtig:
- Keine Anlageberatung geben.
- Keine sicheren Kauf- oder Verkaufsempfehlungen formulieren.
- Nur die gelieferten Daten verwenden.
- Wenn Daten fehlen, klar darauf hinweisen.
- Kurz, präzise und verständlich schreiben.
- Ausgabe auf Deutsch.

Analysiere folgende Aktie:

Ticker: {data["requested_ticker"]}
Verwendetes Symbol: {data["used_symbol"]}

Unternehmen:
Name: {company["company_name"]}
Branche: {company["sector"]}
Industrie: {company["industry"]}
Land: {company["country"]}
Marktkapitalisierung: {format_market_cap(company["market_cap"])}

Fundamentaldaten:
KGV: {format_number(data["pe_ratio"])}
ROE: {format_percent(data["roe"])}
Debt/Equity: {format_number(data["debt_to_equity"])}
Umsatzwachstum: {format_percent(data["revenue_growth"])}
Gewinnwachstum: {format_percent(data["net_income_growth"])}
Free-Cashflow-Wachstum: {format_percent(data["free_cash_flow_growth"])}
EPS-Wachstum: {format_percent(data["eps_growth"])}

Marktdaten:
Kurs: {format_number(data["price"])} USD
Tagesänderung: {format_percent(data["change_percent"])}
Volumen: {data["volume"]}

News:
News-Sentiment: {news["sentiment"]}
News-Score: {news["score"]}
Headlines:
{news_text}

Geopolitik:
Risiko-Level: {geo["risk_level"]}
Geopolitik-Score: {geo["score"]} / 100
Risikobegriffe: {", ".join(geo["risk_terms"]) if geo["risk_terms"] else "Keine auffälligen Begriffe"}
Geopolitische Headlines:
{geo_text}

Quantitativer Research-Score:
Sektorprofil: {research["sector_profile"]}
Datenqualität: {research["data_quality"]}
Score: {research["score"]} / 100
Signal: {research["signal"]}

Aufgabe:
Erstelle ein kurzes KI-Fazit mit:
1. Gesamtbild
2. wichtigste positive Faktoren
3. wichtigste Risikofaktoren
4. Einordnung des Signals
5. Hinweis, dass es keine Anlageberatung ist

Maximal 7 Bulletpoints.
"""
    return prompt.strip()


def generate_ai_summary(data):
    if not OPENAI_API_KEY:
        return (
            "KI-Fazit: Nicht aktiv.\n"
            "Grund: OPENAI_API_KEY ist nicht in Render gesetzt."
        )

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=(
                "Du bist ein vorsichtiger deutschsprachiger Finanz-Research-Assistent. "
                "Du gibst keine Anlageberatung, sondern nur strukturierte Research-Hinweise."
            ),
            input=build_ai_prompt(data),
            max_output_tokens=600,
        )

        text = response.output_text.strip()

        if not text:
            return "KI-Fazit: Keine verwertbare KI-Antwort erhalten."

        return text

    except Exception as exc:
        return f"KI-Fazit konnte nicht erstellt werden: {exc}"


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

    geopolitical_articles = get_geopolitical_articles_with_fallback(company, used_symbol)
    geopolitical_risk = analyze_geopolitical_risk(geopolitical_articles)

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

    research = calculate_professional_research_score(
        company=company,
        change_percent=change_percent,
        pe_ratio=pe_ratio,
        roe=roe,
        revenue_growth=revenue_growth,
        net_income_growth=net_income_growth,
        debt_to_equity=debt_to_equity,
        news_score=news_sentiment["score"],
        geopolitical_score=geopolitical_risk["score"],
    )

    result = {
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
        "revenue_growth": revenue_growth,
        "net_income_growth": net_income_growth,
        "free_cash_flow_growth": free_cash_flow_growth,
        "eps_growth": eps_growth,
        "news_sentiment": news_sentiment,
        "geopolitical_risk": geopolitical_risk,
        "research": research,
    }

    result["ai_summary"] = generate_ai_summary(result)

    return result


def render_not_found(data):
    requested_ticker = data["requested_ticker"]
    tried_symbols = data.get("tried_symbols", [])
    tried_text = ", ".join(tried_symbols) if tried_symbols else requested_ticker

    return (
        f"❌ Kein Börsendatensatz für {requested_ticker} gefunden.\n\n"
        f"Geprüfte Symbole: {tried_text}\n\n"
        "Nutze die Symbolsuche:\n"
        f"/suche {requested_ticker}\n\n"
        "Oder teste direkt:\n"
        "/analyse AAPL\n"
        "/analyse NVDA\n"
        "/analyse MSFT\n\n"
        "Hinweis: Manche Aktien werden je nach Datenpaket oder Börse unter anderen Kürzeln geführt."
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
        f"📈 {data['requested_ticker']} Kurz-Analyse\n\n"
        f"{used_symbol_note}"
        f"Unternehmen: {company['company_name']}\n"
        f"Branche: {company['sector']}\n\n"
        f"Signal: {research['signal']}\n"
        f"Score: {research['score']} / 100\n"
        f"Datenqualität: {research['data_quality']} ({research['available_factors']} Faktoren)\n"
        f"News: {news['sentiment']} ({news['score']})\n"
        f"Geopolitik: {geo['risk_level']} ({geo['score']} / 100)\n\n"
        f"Kurs: {format_number(data['price'])} USD\n"
        f"Änderung: {format_percent(data['change_percent'])}\n\n"
        f"Top-Gründe:\n"
        f"{top_reasons}\n"
        f"🤖 KI-Fazit:\n"
        f"{data['ai_summary']}\n\n"
        f"Für Details:\n"
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
        headline_text = "- Keine aktuellen Headlines verfügbar\n"

    geo_headline_text = ""
    if geo["headlines"]:
        for headline in geo["headlines"]:
            geo_headline_text += f"- {headline}\n"
    else:
        geo_headline_text = "- Keine geopolitischen Headlines verfügbar\n"

    risk_terms_text = ", ".join(geo["risk_terms"]) if geo["risk_terms"] else "Keine auffälligen Begriffe"

    factor_text = (
        f"Bewertung: {research['factor_scores']['valuation']}\n"
        f"Profitabilität: {research['factor_scores']['profitability']}\n"
        f"Wachstum: {research['factor_scores']['growth']}\n"
        f"Verschuldung: {research['factor_scores']['leverage']}\n"
        f"Momentum: {research['factor_scores']['momentum']}\n"
        f"News: {research['factor_scores']['news']}\n"
        f"Geopolitik: {research['factor_scores']['geopolitics']}\n"
    )

    return (
        f"📊 Detailanalyse für {data['requested_ticker']}\n\n"
        f"{used_symbol_note}"
        f"Unternehmen: {company['company_name']}\n"
        f"Branche: {company['sector']}\n"
        f"Industrie: {company['industry']}\n"
        f"Land: {company['country']}\n"
        f"Marktkapitalisierung: {format_market_cap(company['market_cap'])}\n\n"
        f"📊 Fundamentaldaten\n"
        f"KGV: {format_number(data['pe_ratio'])}\n"
        f"ROE: {format_percent(data['roe'])}\n"
        f"Debt/Equity: {format_number(data['debt_to_equity'])}\n"
        f"Umsatzwachstum: {format_percent(data['revenue_growth'])}\n"
        f"Gewinnwachstum: {format_percent(data['net_income_growth'])}\n"
        f"Free-Cashflow-Wachstum: {format_percent(data['free_cash_flow_growth'])}\n"
        f"EPS-Wachstum: {format_percent(data['eps_growth'])}\n\n"
        f"💵 Marktdaten\n"
        f"Kurs: {format_number(data['price'])} USD\n"
        f"Änderung: {format_number(data['change'])}\n"
        f"Änderung %: {format_percent(data['change_percent'])}\n"
        f"Volumen: {data['volume']}\n\n"
        f"🗞 News-Sentiment\n"
        f"News-Score: {news['score']}\n"
        f"Sentiment: {news['sentiment']}\n"
        f"Aktuelle Headlines:\n"
        f"{headline_text}\n"
        f"🌍 Geopolitik-Risiko\n"
        f"Risiko: {geo['risk_level']}\n"
        f"Score: {geo['score']} / 100\n"
        f"Risikobegriffe: {risk_terms_text}\n"
        f"Geopolitische Headlines:\n"
        f"{geo_headline_text}\n"
        f"🧠 Professioneller Research-Score\n"
        f"Sektorprofil: {research['sector_profile']}\n"
        f"Datenqualität: {research['data_quality']} ({research['available_factors']} Faktoren)\n"
        f"Score: {research['score']} / 100\n"
        f"Signal: {research['signal']}\n\n"
        f"Teilbewertungen:\n"
        f"{factor_text}\n"
        f"Gründe:\n"
        f"{notes_text}\n"
        f"🤖 KI-Fazit:\n"
        f"{data['ai_summary']}\n\n"
        "Hinweis: Keine Anlageberatung. Dieses Signal ist nur ein automatisierter Research-Hinweis."
    )


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
        "✅ Bot läuft erfolgreich auf Render!\n\n"
        "Nutze /help für alle Befehle."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Verfügbare Befehle:\n\n"
        "/start - Bot starten\n"
        "/analyse AAPL - kompakte Analyse mit KI-Fazit\n"
        "/details AAPL - vollständige Detailanalyse\n"
        "/analyse NVDA - kompakte Analyse mit KI-Fazit\n"
        "/details NVDA - vollständige Detailanalyse\n"
        "/suche SAP - Symbolsuche starten\n"
        "/info - Informationen zum Bot\n"
        "/help - Hilfe anzeigen"
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Telegram Market Signal Bot\n\n"
        "Der Bot kann aktuell:\n"
        "✅ kompakte Analyse mit /analyse liefern\n"
        "✅ ausführliche Detailanalyse mit /details liefern\n"
        "✅ Kursdaten, Fundamentaldaten und News-Sentiment auswerten\n"
        "✅ Geopolitik-Risiko über GDELT einbeziehen\n"
        "✅ branchenspezifischen Research-Score berechnen\n"
        "✅ KI-Fazit aus FMP + GDELT + News erzeugen\n"
        "✅ Ticker-Fallbacks und Symbolsuche nutzen\n\n"
        "Nächster Ausbau:\n"
        "ETF-Daten, Watchlist und Alerts.\n\n"
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
    app.add_handler(CommandHandler("details", details))
    app.add_handler(CommandHandler("suche", suche))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info))

    print("Bot gestartet")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
