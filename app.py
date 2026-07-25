import asyncio
import log*ing
import os
from http import HTT*Status

import requests
import uvi*orn
from starlette.applications im*ort Starlette
from starlette.reque*ts import Request
from starlette.r*sponses import PlainTextResponse, *esponse
from starlette.routing imp*rt Route

from telegram import Upd*te
from telegram.ext import Applic*tion, CommandHandler, ContextTypes*

logging.basicConfig(
    format=*%(asctime)s - %(name)s - %(levelna*e)s - %(message)s",
    level=logg*ng.INFO,
)

logging.getLogger("htt*x").setLevel(logging.WARNING)
logg*r = logging.getLogger(__name__)


*ELEGRAM_TOKEN = os.environ.get("TE*EGRAM_TOKEN")
BASE_URL = os.enviro*.get("RENDER_EXTERNAL_URL") or os.*nviron.get("BASE_URL")
PORT = int(*s.environ.get("PORT", "8000"))

DI*CLAIMER = (
    "Hinweis: Dies ist*keine Anlageberatung, sondern ein *utomatisiertes "
    "Research-Sig*al. Prüfe Quellen, Risiko, Zeithor*zont und deine eigene Strategie."
*

COUNTRY_MAP = {
    "AAPL": "USA*,
    "MSFT": "USA",
    "AMZN": "*SA",
    "GOOGL": "USA",
    "META*: "USA",
    "NVDA": "USA",
    "T*LA": "USA",
    "AMD": "USA",
    *INTC": "USA",
    "LMT": "USA",
  * "RTX": "USA",
    "NOC": "USA",
 *  "XOM": "USA",
    "CVX": "USA",
*   "JPM": "USA",
    "BAC": "USA",*    "GS": "USA",
    "MS": "USA",
*   "BABA": "China",
    "JD": "Chi*a",
    "NIO": "China",
    "PDD":*"China",
    "TCEHY": "China",
   *"SAP": "Germany",
    "DTE": "Germ*ny",
    "BMW": "Germany",
    "VO*": "Germany",
    "BAS": "Germany"*
    "SIE": "Germany",
    "ALV": *Germany",
    "AIR": "France",
   *"BNP": "France",
    "BP": "UK",
 *  "SONY": "Japan",
    "TM": "Japa*",
    "SHOP": "Canada",
    "NESN*: "Switzerland",
    "ROG": "Switz*rland",
    "TCS": "India",
    "I*FY": "India",
}


def get_geopolit*cal_events(country: str) -> list[d*ry_url = "https://api.gdeltproject.org/api/v2/events"
    params = {
        "query": country,
        "format": "json",
        "maxrecords": 10,
    }

    try:
        response = requests.get(query_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("events", [])[:5]
    except Exception as exc:
        logger.exception("Fehler bei GDELT-Abfrage: %s", exc)
        return []


def get_fundamental_placeholder(ticker: str) -> dict:
    """
    Platzhalter für Fundamentaldaten.
    Später ersetzen durch echte Datenquelle, z. B. Financial Modeling Prep,
    Alpha Vantage, Polygon, Twelve Data oder eigene Datenbank.
    """
    return {
        "valuation": "neutral",
        "growth": "unknown",
        "debt_risk": "unknown",
        "quality": "unknown",
    }


def score_signal(ticker: str, events: list[dict], fundamentals: dict) -> dict:
    """
    Einfache, transparente Startlogik.
    Später ersetzen durch gewichtetes Scoring.
    """
    geopolitical_risk = min(len(events), 5)

    score = 0

    if fundamentals.get("valuation") == "cheap":
        score += 2
    elif fundamentals.get("valuation") == "expensive":
        score -= 2

    if fundamentals.get("quality") == "high":
        score += 1

    if geopolitical_risk >= 4:
        score -= 1

    if score >= 2:
        signal = "LONG"
    elif score <= -2:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    return {
        "signal": signal,
        "score": score,
        "geopolitical_risk": geopolitical_risk,
    }


def format_events(events: list[dict]) -> str:
    if not events:
        return "Keine aktuellen geopolitischen Ereignisse gefunden."

    lines = []
    for event in events[:3]:
        description = (
            event.get("EventDescription")
            or event.get("ActionGeo_FullName")
            or "Ereignis ohne Beschreibung"
        )
        lines.append(f"- {description}")

    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Bot läuft.\n\n"
        "Befehle:\n"
        "/analyse AAPL\n"
        "/analyse NVDA\n"
        "/analyse SAP\n\n"
        f"{DISCLAIMER}"
    )
    await update.message.reply_text(text)


async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Bitte nutze: /analyse AAPL")
        return

    ticker = context.args[0].upper()
    country = COUNTRY_MAP.get(ticker, "USA")

    events = get_geopolitical_events(country)
    fundamentals = get_fundamental_placeholder(ticker)
    result = score_signal(ticker, events, fundamentals)

    text = (
        f"Analyse für {ticker}\n\n"
        f"Signal: {result['signal']}\n"
        f"Score: {result['score']}\n"
        f"Geopolitisches Risiko: {result['geopolitical_risk']}/5\n"
        f"Land/Region: {country}\n\n"
        "Geopolitische Ereignisse:\n"
        f"{format_events(events)}\n\n"
        "Fundamentalcheck:\n"
        f"- Bewertung: {fundamentals['valuation']}\n"
        f"- Wachstum: {fundamentals['growth']}\n"
        f"- Verschuldungsrisiko: {fundamentals['debt_risk']}\n"
        f"- Qualität: {fundamentals['quality']}\n\n"
        f"{DISCLAIMER}"
    )

    await update.message.reply_text(text)


async def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN fehlt in den Environment Variables.")

    if not BASE_URL:
        raise RuntimeError("BASE_URL oder RENDER_EXTERNAL_URL fehlt.")

    application = Application.builder().token(TELEGRAM_TOKEN).updater(None).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analyse", analyse))

    await application.bot.set_webhook(
        url=f"{BASE_URL}/telegram",
        allowed_updates=Update.ALL_TYPES,
    )

    async def telegram_webhook(request: Request) -> Response:
        await application.update_queue.put(
            Update.de_json(data=await request.json(), bot=application.bot)
        )
        return Response(status_code=HTTPStatus.OK)

    async def healthcheck(_: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    starlette_app = Starlette(
        routes=[
            Route("/telegram", telegram_webhook, methods=["POST"]),
            Route("/healthcheck", healthcheck, methods=["GET"]),
        ]
    )

    webserver = uvicorn.Server(
        config=uvicorn.Config(
            app=starlette_app,
            host="0.0.0.0",
            port=PORT,
            use_colors=False,
        )
    )

    async with application:
        await application.start()
        await webserver.serve()
        await application.stop()


if __name__ == "__main__":
    asyncio.run(main())
