"""Real-world wire — fetches actual market data + headlines at midnight so
agents grade their predictions against reality, not just the simulation.

Sources (no API keys needed):
  - Brent crude futures quote: stooq.com CSV endpoint
  - Top conflict headlines: Google News RSS search

Every call fails soft: no network / bad payload -> empty output, and the
learning cycle simply runs without the wire. Nothing here can crash a day.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

YF_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/"
            "{sym}?interval=1d&range=5d")
SYMBOLS = (("BZ=F", "Brent"), ("CL=F", "WTI"), ("GC=F", "Gold"))
NEWS_RSS = (
    "https://news.google.com/rss/search?"
    "q=Iran%20Israel%20war%20OR%20Strait%20of%20Hormuz%20OR%20Brent%20crude"
    "%20when:1d&hl=en-US&gl=US&ceid=US:en"
)
FR_FUEL_URL = "https://www.fuel-prices.eu/France/"
TIMEOUT = 12
HEADLINE_COUNT = 8


def _get(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (simulation)"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_quote(symbol: str, label: str) -> str:
    """Return 'LABEL $price (+x.xx%)' or '' on failure."""
    try:
        url = YF_CHART.format(sym=urllib.parse.quote(symbol))
        meta = json.loads(_get(url))["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        pct = meta.get("regularMarketChangePercent")
        if price is None:
            return ""
        move = f" ({pct:+.2f}%)" if pct is not None else ""
        return f"{label} ${price:.2f}{move}"
    except Exception:
        return ""


def fetch_fr_fuel() -> str:
    """Real French pump prices — 'FR petrol €2.219/L | diesel €2.383/L'."""
    import re
    try:
        html = _get(FR_FUEL_URL)
        pet = re.search(r'95-price"\s+content="([\d.]+)', html)
        dsl = re.search(r'diesel-price"\s+content="([\d.]+)', html)
        if pet and dsl:
            return (f"FR petrol €{float(pet.group(1)):.3f}/L | "
                    f"FR diesel €{float(dsl.group(1)):.3f}/L "
                    "(fuel-prices.eu)")
    except Exception:
        pass
    return ""


def fetch_headlines(n: int = HEADLINE_COUNT) -> list[str]:
    try:
        root = ET.fromstring(_get(NEWS_RSS))
    except Exception:
        return []
    out = []
    for item in root.iter("item"):
        title = item.findtext("title")
        if title:
            out.append(title.strip())
        if len(out) >= n:
            break
    return out


def fetch_day(day_no: int, out_dir: str = "real_events") -> str:
    """Fetch the wire, persist it to real_events/dayN.txt, return the text."""
    parts = [f"AUTO-FETCHED REAL-WORLD WIRE — {datetime.now():%Y-%m-%d %H:%M}"]

    for symbol, label in SYMBOLS:
        q = fetch_quote(symbol, label)
        if q:
            parts.append(f"MARKET: {q}")

    fuel = fetch_fr_fuel()
    if fuel:
        parts.append(f"MARKET: {fuel}")

    heads = fetch_headlines()
    if heads:
        parts.append("HEADLINES:")
        parts += [f"  - {h}" for h in heads]

    if len(parts) == 1:                      # nothing fetched at all
        return ""

    text = "\n".join(parts)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"day{day_no}.txt")
    with open(path, "w") as f:
        f.write(text + "\n")
    return text
