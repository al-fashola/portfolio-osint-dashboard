"""SQLite storage for the portfolio OSINT pipeline."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,          -- YYYY-MM-DD
    close  REAL,
    volume INTEGER,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS filings (
    accession TEXT NOT NULL,
    ticker    TEXT NOT NULL,
    form      TEXT,
    filed     TEXT,                -- YYYY-MM-DD
    doc       TEXT,                -- primary document description/name
    url       TEXT,
    PRIMARY KEY (accession, ticker)
);

CREATE TABLE IF NOT EXISTS news (
    url       TEXT NOT NULL,
    ticker    TEXT NOT NULL,
    published TEXT,                -- ISO timestamp
    title     TEXT,
    source    TEXT,
    PRIMARY KEY (url, ticker)
);

CREATE TABLE IF NOT EXISTS runs (
    ts TEXT NOT NULL               -- ISO timestamp of pipeline run
);

CREATE TABLE IF NOT EXISTS insider_tx (
    accession TEXT NOT NULL,
    ticker    TEXT NOT NULL,
    owner     TEXT,
    title     TEXT,
    tx_date   TEXT,                -- YYYY-MM-DD
    code      TEXT,                -- P=buy, S=sale, A=award, M=exercise, F=tax, G=gift, ...
    acquired  TEXT,                -- A or D
    shares    REAL,
    price     REAL,
    value     REAL,                -- shares * price (0 when no price, e.g. awards)
    PRIMARY KEY (accession, ticker, owner, tx_date, code, shares, price)
);

-- Every Form 4 accession we attempted to parse (incl. failures), so we never refetch
CREATE TABLE IF NOT EXISTS form4_parsed (
    accession TEXT PRIMARY KEY,
    status    TEXT                 -- ok | error:<reason>
);

CREATE TABLE IF NOT EXISTS earnings (
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,         -- YYYY-MM-DD
    eps_est REAL,
    eps_act REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS trade_flows (
    reporter TEXT NOT NULL,        -- e.g. "Korea", "China"
    flow     TEXT NOT NULL,        -- X (export) / M (import)
    hs_code  TEXT NOT NULL,
    period   TEXT NOT NULL,        -- YYYYMM
    value_usd REAL,
    PRIMARY KEY (reporter, flow, hs_code, period)
);

CREATE TABLE IF NOT EXISTS alerts (
    run_ts  TEXT NOT NULL,
    ticker  TEXT,
    kind    TEXT,                  -- price | volume | filing | insider | earnings | trade
    message TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS analyst_actions (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,         -- YYYY-MM-DD HH:MM
    firm        TEXT NOT NULL,
    action      TEXT,                  -- up | down | main | init | reit
    from_grade  TEXT,
    to_grade    TEXT,
    pt_action   TEXT,                  -- Raises | Lowers | Maintains | Announces
    pt_current  REAL,
    pt_prior    REAL,
    PRIMARY KEY (ticker, date, firm)
);

CREATE TABLE IF NOT EXISTS analyst_summary (
    ticker      TEXT NOT NULL,
    fetched     TEXT NOT NULL,         -- YYYY-MM-DD
    price       REAL,
    target_mean REAL, target_high REAL, target_low REAL, target_median REAL,
    strong_buy INTEGER, buy INTEGER, hold INTEGER, sell INTEGER, strong_sell INTEGER,
    PRIMARY KEY (ticker, fetched)
);

CREATE TABLE IF NOT EXISTS short_interest (
    ticker       TEXT NOT NULL,
    date         TEXT NOT NULL,        -- FINRA settlement date, YYYY-MM-DD
    shares_short REAL,
    shares_prior REAL,
    ratio        REAL,                 -- days to cover
    pct_float    REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS inst_holders (
    ticker     TEXT NOT NULL,
    reported   TEXT NOT NULL,          -- 13F quarter date
    holder     TEXT NOT NULL,
    shares     REAL,
    value      REAL,
    pct_held   REAL,
    pct_change REAL,                   -- QoQ position change from Yahoo
    PRIMARY KEY (ticker, reported, holder)
);

CREATE TABLE IF NOT EXISTS social_sentiment (
    ticker   TEXT NOT NULL,
    date     TEXT NOT NULL,            -- YYYY-MM-DD
    source   TEXT NOT NULL,            -- stocktwits
    messages INTEGER,                  -- sampled message count
    bullish  INTEGER,
    bearish  INTEGER,
    PRIMARY KEY (ticker, date, source)
);

CREATE TABLE IF NOT EXISTS news_metrics (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,              -- YYYY-MM-DD
    volume REAL,                       -- GDELT article count
    tone   REAL,                       -- GDELT average tone
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS attention (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,              -- week start, YYYY-MM-DD
    score  REAL,                       -- Google Trends 0-100
    PRIMARY KEY (ticker, date)
);
"""


def connect(check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_prices(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO prices (ticker, date, close, volume) VALUES (?,?,?,?)", rows
    )
    conn.commit()


def upsert_filings(conn, rows):
    conn.executemany(
        "INSERT OR IGNORE INTO filings (accession, ticker, form, filed, doc, url) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def upsert_news(conn, rows):
    conn.executemany(
        "INSERT OR IGNORE INTO news (url, ticker, published, title, source) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def record_run(conn, ts: str):
    conn.execute("INSERT INTO runs (ts) VALUES (?)", (ts,))
    conn.commit()


def upsert_insider_tx(conn, rows):
    conn.executemany(
        "INSERT OR IGNORE INTO insider_tx "
        "(accession, ticker, owner, title, tx_date, code, acquired, shares, price, value) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def mark_form4(conn, accession: str, status: str):
    conn.execute("INSERT OR REPLACE INTO form4_parsed (accession, status) VALUES (?,?)", (accession, status))
    conn.commit()


def upsert_earnings(conn, rows):
    conn.executemany("INSERT OR REPLACE INTO earnings (ticker, date, eps_est, eps_act) VALUES (?,?,?,?)", rows)
    conn.commit()


def upsert_trade_flows(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO trade_flows (reporter, flow, hs_code, period, value_usd) VALUES (?,?,?,?,?)", rows
    )
    conn.commit()


def record_alerts(conn, run_ts: str, alerts):
    # Dedupe within a day: with multiple runs/day, only log an alert the first
    # time it appears that day, so the alert-history log isn't inflated by
    # re-runs. (run_ts date is the dedup key alongside ticker/kind/message.)
    day = run_ts[:10]
    for a in alerts:
        exists = conn.execute(
            "SELECT 1 FROM alerts WHERE substr(run_ts,1,10)=? AND IFNULL(ticker,'')=IFNULL(?,'') "
            "AND kind=? AND message=? LIMIT 1",
            (day, a["ticker"], a["kind"], a["message"]),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO alerts (run_ts, ticker, kind, message) VALUES (?,?,?,?)",
                (run_ts, a["ticker"], a["kind"], a["message"]),
            )
    conn.commit()


def upsert_analyst_actions(conn, rows):
    conn.executemany(
        "INSERT OR IGNORE INTO analyst_actions "
        "(ticker, date, firm, action, from_grade, to_grade, pt_action, pt_current, pt_prior) "
        "VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def upsert_analyst_summary(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO analyst_summary "
        "(ticker, fetched, price, target_mean, target_high, target_low, target_median, "
        " strong_buy, buy, hold, sell, strong_sell) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def upsert_short_interest(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO short_interest "
        "(ticker, date, shares_short, shares_prior, ratio, pct_float) VALUES (?,?,?,?,?,?)", rows)
    conn.commit()


def upsert_inst_holders(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO inst_holders "
        "(ticker, reported, holder, shares, value, pct_held, pct_change) VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()


def upsert_social(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO social_sentiment "
        "(ticker, date, source, messages, bullish, bearish) VALUES (?,?,?,?,?,?)", rows)
    conn.commit()


def upsert_news_metrics(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO news_metrics (ticker, date, volume, tone) VALUES (?,?,?,?)", rows)
    conn.commit()


def upsert_attention(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO attention (ticker, date, score) VALUES (?,?,?)", rows)
    conn.commit()


def get_meta(conn, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key: str, value: str):
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
    conn.commit()
