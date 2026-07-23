"""Portfolio ticker configuration.

Each entry: yahoo symbol -> metadata.
  name        display name
  query       news search query (company name, quoted phrases help precision)
  us_ticker   ticker as registered with SEC EDGAR (None = not a US filer, skip EDGAR)

Positions synced from IBKR (sync_ibkr.py -> tickers_ibkr.json) are merged in
below the hand-curated list; hand-curated entries win on conflicts.
"""
import json
from pathlib import Path

TICKERS = {
    "SIVE.ST":  {"name": "Sivers Semiconductors (Stockholm)", "query": '"Sivers Semiconductors"', "us_ticker": None},
    "SIVEF":    {"name": "Sivers Semiconductors (OTC)",       "query": '"Sivers Semiconductors"', "us_ticker": None},
    "LPKFF":    {"name": "LPKF Laser & Electronics (OTC)",    "query": '"LPKF Laser"',            "us_ticker": None},
    "NBIS":     {"name": "Nebius Group",                      "query": '"Nebius"',                "us_ticker": "NBIS"},
    "VPG":      {"name": "Vishay Precision Group",            "query": '"Vishay Precision"',      "us_ticker": "VPG"},
    "EWY":      {"name": "iShares MSCI South Korea ETF",      "query": '"iShares South Korea" OR "EWY ETF"', "us_ticker": None},
    "META":     {"name": "Meta Platforms",                    "query": '"Meta Platforms"',        "us_ticker": "META"},
    "NVDA":     {"name": "NVIDIA",                            "query": '"NVIDIA"',                "us_ticker": "NVDA"},
    "MP1.AX":   {"name": "Megaport (ASX)",                    "query": '"Megaport"',              "us_ticker": None},
    # Confirmed by user: 2x daily leveraged SpaceX exposure — news signal is the underlying
    "SPCH":     {"name": "Leverage Shares 2X Long SPCX ETP",  "query": '"SpaceX"',                "us_ticker": None},
    "XFAB.PA":  {"name": "X-FAB Silicon Foundries (Paris)",   "query": '"X-FAB"',                 "us_ticker": None},
    "MRVL":     {"name": "Marvell Technology",                "query": '"Marvell Technology"',    "us_ticker": "MRVL"},
    "GFS":      {"name": "GlobalFoundries",                   "query": '"GlobalFoundries"',       "us_ticker": "GFS"},
    "SOI.PA":   {"name": "Soitec (Paris)",                    "query": '"Soitec"',                "us_ticker": None},
    "SLOIF":    {"name": "Soitec (OTC)",                      "query": '"Soitec"',                "us_ticker": None},
    "AEHR":     {"name": "Aehr Test Systems",                 "query": '"Aehr Test Systems"',     "us_ticker": "AEHR"},
    "WULF":     {"name": "TeraWulf",                          "query": '"TeraWulf"',              "us_ticker": "WULF"},
    "AVGO":     {"name": "Broadcom",                          "query": '"Broadcom"',              "us_ticker": "AVGO"},
    "TSM":      {"name": "Taiwan Semiconductor Manufacturing", "query": '"Taiwan Semiconductor"',  "us_ticker": "TSM"},
    "SPCX":     {"name": "Space Exploration Technologies (SpaceX)", "query": '"SpaceX"',           "us_ticker": "SPCX"},
    "INTC":     {"name": "Intel",                            "query": '"Intel"',                 "us_ticker": "INTC"},
}

# Macro context instruments — tracked for the digest/dashboard "considerations"
# section, NOT part of the watchlist (no filings/theses/asymmetry for these)
MACRO_TICKERS = {
    "^GSPC":  "S&P 500",
    "^IXIC":  "Nasdaq Composite",
    "^SOX":   "PHLX Semiconductor Index",
    "^VIX":   "VIX (fear gauge)",
    "^TNX":   "US 10Y Treasury yield (x10)",
    "KRW=X":  "USD/KRW (Korea FX, EWY translation)",
}

# Standing macro news queries (Google News RSS), stored under pseudo-ticker _MACRO.
# These proxy the DeItaone-style headline flow that is otherwise X-login-walled.
MACRO_NEWS_QUERIES = [
    'Federal Reserve rates decision',
    'semiconductor export controls China',
    'AI datacenter capex spending',
    'tariffs trade policy technology',
    'South Korea memory chips policy',
]

MACRO_MOVE_ALERT_PCT = 2.0      # 1-day index move that triggers a macro alert
VIX_ALERT_LEVEL = 30.0          # VIX close at/above this triggers a macro alert

CONFERENCE_ALERT_DAYS = 14      # alert when a watchlist-relevant event is this close
CONFERENCE_DIGEST_DAYS = 120    # events shown in the digest/dashboard calendar

# Merge IBKR-synced positions (additive only — manual entries above take precedence)
_ibkr_file = Path(__file__).parent / "tickers_ibkr.json"
if _ibkr_file.exists():
    for _sym, _meta in json.loads(_ibkr_file.read_text()).items():
        TICKERS.setdefault(_sym, _meta)

# SEC EDGAR requires a descriptive User-Agent with contact info
EDGAR_USER_AGENT = "Personal Portfolio Research alameenfashola@gmail.com"

# Signal thresholds
PRICE_MOVE_ALERT_PCT = 3.0      # 1-day move that triggers an alert
VOLUME_RATIO_ALERT = 2.0        # volume vs 30-day average
FILING_LOOKBACK_DAYS = 7        # "new filing" window for digest alerts
INSIDER_CLUSTER_DAYS = 14       # window for insider transaction alerts
INSIDER_SELL_ALERT_USD = 10_000_000  # aggregate open-market sells to trigger an alert
INSIDER_LOOKBACK_DAYS = 30      # insider activity shown in digest/dashboard detail
EARNINGS_ALERT_DAYS = 7         # alert when earnings are within this many days
TRADE_YOY_ALERT_PCT = 30.0      # Comtrade YoY export change that triggers an alert
ANALYST_LOOKBACK_DAYS = 7       # grade/PT actions considered "recent" for alerts
SHORT_MOM_ALERT_PCT = 20.0      # month-over-month short interest change alert
SHORT_FLOAT_ALERT_PCT = 15.0    # % of float short worth flagging outright
SOCIAL_SKEW_MIN_TAGGED = 8      # min tagged messages before skew alert can fire
SOCIAL_SKEW_ALERT = 0.85        # bull/(bull+bear) above this (or below 1-this) alerts
GDELT_VOLUME_SPIKE = 3.0        # yesterday's article volume vs trailing-week avg
ASYM_MIN_ATTRACTIVE = 3.0       # user-defined asymmetry at/above this is flagged attractive
ASYM_POOR = 1.0                 # below this, downside exceeds upside — flagged
NEWS_LOOKBACK_HOURS = 48        # headlines considered "fresh"
NEWS_PER_TICKER = 3             # headlines per ticker in digest

# Which EDGAR forms we care about
FORMS_OF_INTEREST = {"8-K", "10-K", "10-Q", "4", "SC 13D", "SC 13G", "6-K", "20-F", "S-1", "424B5"}
