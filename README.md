# Telegram Market Signal Bot

Telegram Bot für Aktien- und ETF-Signale basierend auf:

- Geopolitischen Ereignissen
- News-Sentiment
- Fundamentalanalyse
- Risiko- und Marktbewertung

## Funktionen

### Analyse von Aktien

Beispiel:

```text
/analyse NVDA
/analyse AAPL
/analyse SAP
```

Ausgabe:

```text
Signal: LONG
Score: +3

Begründung:
- Positive Fundamentaldaten
- Positives News-Sentiment
- Moderates geopolitisches Risiko
```

### Analyse von ETFs

Beispiel:

```text
/analyse ETF MSCI WORLD
```

Berücksichtigt:

- Regionale Risiken
- Sektorengewichtung
- Makroökonomische Entwicklungen
- Geopolitische Ereignisse

---

## Installation

Repository klonen:

```bash
git clone https://github.com/DEINNAME/telegram-market-signal-bot.git
cd telegram-market-signal-bot
```

Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

Bot starten:

```bash
python app.py
```

---

## Environment Variablen

Folgende Variablen müssen gesetzt werden:

```env
TELEGRAM_TOKEN=xxxxxxxx
```

Optional:

```env
NEWS_API_KEY=xxxxxxxx
MARKET_API_KEY=xxxxxxxx
```

---

## Deployment auf Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
python app.py
```

---

## Projektstruktur

```text
telegram-market-signal-bot/
├── app.py
├── requirements.txt
├── README.md
├── services/
│   ├── geopolitics.py
│   ├── fundamentals.py
│   ├── news.py
│   └── scoring.py
```

---

## Haftungsausschluss

Dieser Bot stellt keine Anlageberatung dar.

Alle Analysen dienen ausschließlich Forschungs- und Informationszwecken.
Investitionsentscheidungen erfolgen auf eigenes Risiko.
