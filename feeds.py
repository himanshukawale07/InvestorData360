
import os
import csv
import math
import json
import time

from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import requests


# ============================================================
# FINANCIAL INSTRUMENT MASTER
# ============================================================

SYMBOLS = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com Inc.",
    "IBM": "International Business Machines",
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}


# ============================================================
# MAIN MARKET DATA EXTRACTION FUNCTION
# ============================================================

def fetch(data):

    import yfinance as yf

    # Ensure correct directory path
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)

    raw = data / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    today = date.today()
    start_date = today - timedelta(days=90)

    prices = []
    actions = []
    issues = []
    securities = []

    # --------------------------------------------------------
    # API CONFIGURATION
    # --------------------------------------------------------

    alpha_key = os.getenv(
        "ALPHA_VANTAGE_API_KEY", ""
    ).strip()

    twelve_key = os.getenv(
        "TWELVE_DATA_API_KEY", ""
    ).strip()

    alpaca_key = os.getenv(
        "APCA_API_KEY_ID", ""
    ).strip()

    alpaca_secret = os.getenv(
        "APCA_API_SECRET_KEY", ""
    ).strip()

    # --------------------------------------------------------
    # PROCESS FINANCIAL INSTRUMENTS
    # --------------------------------------------------------

    for sid, name in SYMBOLS.items():

        asset_class = (
            "ETF" if sid in ("SPY", "QQQ") else "Equity"
        )

        securities.append(
            (sid, asset_class, "USD", name)
        )

        # ====================================================
        # PROVIDER 1 — YAHOO FINANCE
        # ====================================================

        try:

            ticker = yf.Ticker(sid)

            history = ticker.history(
                period="3mo",
                interval="1d",
                auto_adjust=False,
                actions=True,
                raise_errors=True
            )

            if history.empty:
                raise ValueError(
                    "Yahoo Finance returned empty price history"
                )

            history.to_csv(
                raw / f"{sid}_yahoo.csv"
            )

            for dt, row in history.iterrows():

                trading_date = dt.date()

                if not (
                    start_date <= trading_date < today
                ):
                    continue

                d = trading_date.isoformat()

                # Closing price
                price = float(row["Close"])

                if math.isfinite(price) and price > 0:

                    prices.append(
                        (
                            sid,
                            d,
                            "Vendor A",
                            price
                        )
                    )

                # Corporate actions
                corporate_columns = [
                    ("Dividends", "DIVIDEND"),
                    ("Stock Splits", "SPLIT")
                ]

                for column, event_type in corporate_columns:

                    value = float(
                        row.get(column, 0)
                    )

                    if (
                        math.isfinite(value)
                        and value != 0
                    ):

                        actions.append(
                            (
                                f"{sid}-{d}-{event_type}",
                                sid,
                                event_type,
                                d,
                                value
                            )
                        )

        except Exception as e:

            issues.append(
                (
                    sid,
                    "Yahoo Finance",
                    f"{type(e).__name__}: {str(e)[:150]}"
                )
            )

        # ====================================================
        # PROVIDER 2 — ALPHA VANTAGE
        # ====================================================

        if alpha_key:

            try:

                response = requests.get(
                    "https://www.alphavantage.co/query",
                    params={
                        "function": "TIME_SERIES_DAILY",
                        "symbol": sid,
                        "apikey": alpha_key
                    },
                    timeout=30
                )

                response.raise_for_status()

                payload = response.json()

                # Keep source data for auditability
                (
                    raw / f"{sid}_alpha.json"
                ).write_text(
                    json.dumps(payload, indent=2),
                    encoding="utf-8"
                )

                series = payload.get(
                    "Time Series (Daily)"
                )

                if not series:

                    message = (
                        payload.get("Note")
                        or payload.get("Information")
                        or payload.get("Error Message")
                        or "No daily price data returned"
                    )

                    raise ValueError(message)

                for d, row in series.items():

                    if not (
                        start_date.isoformat()
                        <= d
                        < today.isoformat()
                    ):
                        continue

                    price = float(
                        row["4. close"]
                    )

                    if math.isfinite(price) and price > 0:

                        prices.append(
                            (
                                sid,
                                d,
                                "Vendor B",
                                price
                            )
                        )

            except Exception as e:

                issues.append(
                    (
                        sid,
                        "Alpha Vantage",
                        f"{type(e).__name__}: {str(e)[:150]}"
                    )
                )

            # Respect provider request limits
            time.sleep(1)

        # ====================================================
        # PROVIDER 3 — TWELVE DATA
        # ====================================================

        if twelve_key:

            try:

                response = requests.get(
                    "https://api.twelvedata.com/time_series",
                    params={
                        "symbol": sid,
                        "interval": "1day",
                        "outputsize": 100,
                        "adjust": "splits",
                        "apikey": twelve_key
                    },
                    timeout=30
                )

                response.raise_for_status()

                payload = response.json()

                (
                    raw / f"{sid}_twelve.json"
                ).write_text(
                    json.dumps(payload, indent=2),
                    encoding="utf-8"
                )

                series = payload.get("values", [])
                metadata = payload.get("meta", {})

                if not series:

                    raise ValueError(
                        payload.get(
                            "message",
                            "Twelve Data returned no prices"
                        )
                    )

                if metadata.get("currency") != "USD":

                    raise ValueError(
                        "Twelve Data did not return USD prices"
                    )

                valid_rows = []

                for row in series:

                    d = row["datetime"][:10]

                    if not (
                        start_date.isoformat()
                        <= d
                        < today.isoformat()
                    ):
                        continue

                    price = float(row["close"])

                    if math.isfinite(price) and price > 0:

                        valid_rows.append(
                            (
                                sid,
                                d,
                                "Vendor C",
                                price
                            )
                        )

                if not valid_rows:

                    raise ValueError(
                        "No eligible Twelve Data prices"
                    )

                prices.extend(valid_rows)

            except Exception as e:

                issues.append(
                    (
                        sid,
                        "Twelve Data",
                        f"{type(e).__name__}: {str(e)[:150]}"
                    )
                )

        # ====================================================
        # PROVIDER 4 — ALPACA SIP
        # ====================================================

        if alpaca_key and alpaca_secret:

            try:

                response = requests.get(
                    "https://data.alpaca.markets/v2/stocks/bars",
                    params={
                        "symbols": sid,
                        "timeframe": "1Day",
                        "start": start_date.isoformat(),
                        "end": today.isoformat(),
                        "adjustment": "split",
                        "feed": "sip",
                        "limit": 1000,
                        "currency": "USD"
                    },
                    headers={
                        "APCA-API-KEY-ID": alpaca_key,
                        "APCA-API-SECRET-KEY": alpaca_secret
                    },
                    timeout=30
                )

                response.raise_for_status()

                payload = response.json()

                (
                    raw / f"{sid}_alpaca.json"
                ).write_text(
                    json.dumps(payload, indent=2),
                    encoding="utf-8"
                )

                series = (
                    payload.get("bars", {})
                    .get(sid, [])
                )

                if not series:

                    raise ValueError(
                        "Alpaca returned no eligible SIP bars"
                    )

                valid_rows = []

                for row in series:

                    d = row["t"][:10]

                    if not (
                        start_date.isoformat()
                        <= d
                        < today.isoformat()
                    ):
                        continue

                    price = float(row["c"])

                    if math.isfinite(price) and price > 0:

                        valid_rows.append(
                            (
                                sid,
                                d,
                                "Vendor D",
                                price
                            )
                        )

                if not valid_rows:

                    raise ValueError(
                        "No eligible Alpaca prices"
                    )

                prices.extend(valid_rows)

            except Exception as e:

                issues.append(
                    (
                        sid,
                        "Alpaca SIP",
                        f"{type(e).__name__}: {str(e)[:150]}"
                    )
                )

    # ========================================================
    # CHECK MARKET DATA AVAILABILITY
    # ========================================================

    if not prices:

        raise RuntimeError(
            "No actual financial market prices retrieved. "
            "Check network connectivity and API access. "
            "No mock data will be generated."
        )

    # Latest available pricing date
    asof = max(
        d for _, d, _, _ in prices
    )

    # ========================================================
    # OPTIONAL PORTFOLIO HOLDINGS
    # ========================================================

    positions = []

    holdings_file = (
        data / "holdings_input.csv"
    )

    if holdings_file.is_file():

        with holdings_file.open(
            newline="",
            encoding="utf-8-sig"
        ) as f:

            reader = csv.DictReader(f)

            required_columns = {
                "portfolio",
                "security_id",
                "quantity"
            }

            if not required_columns.issubset(
                reader.fieldnames or []
            ):

                raise ValueError(
                    "Holdings CSV must contain: "
                    "portfolio, security_id, quantity"
                )

            for row in reader:

                portfolio = (
                    row["portfolio"].strip()
                )

                sid = (
                    row["security_id"]
                    .strip()
                    .upper()
                )

                quantity = float(
                    row["quantity"]
                )

                if (
                    not portfolio
                    or sid not in SYMBOLS
                    or not math.isfinite(quantity)
                    or quantity < 0
                ):

                    raise ValueError(
                        "Invalid portfolio holding. "
                        "Check portfolio, security ID and quantity."
                    )

                positions.append(
                    (
                        portfolio,
                        sid,
                        asof,
                        quantity
                    )
                )

    else:

        print(
            "No holdings_input.csv supplied. "
            "Continuing with an empty portfolio."
        )

    # ========================================================
    # DATA LINEAGE / API MANIFEST
    # ========================================================

    manifest = {
        "retrieved_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "sources": {
            "Vendor A": "Yahoo Finance via yfinance",
            "Vendor B": "Alpha Vantage",
            "Vendor C": "Twelve Data",
            "Vendor D": "Alpaca SIP"
        },

        "alpha_enabled": bool(alpha_key),

        "twelve_enabled": bool(twelve_key),

        "alpaca_enabled": bool(
            alpaca_key and alpaca_secret
        ),

        "issues": issues,

        "valuation_date": asof
    }

    (
        raw / "manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2
        ),
        encoding="utf-8"
    )

    # ========================================================
    # RETURN DATA TO PIPELINE
    # ========================================================

    return (
        date.fromisoformat(asof),
        securities,
        prices,
        positions,
        actions,
        issues
    )
