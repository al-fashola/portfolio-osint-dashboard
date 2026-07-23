"""Signal computation shared by the digest generator and the dashboard."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import (
    TICKERS,
    PRICE_MOVE_ALERT_PCT,
    VOLUME_RATIO_ALERT,
    FILING_LOOKBACK_DAYS,
    INSIDER_CLUSTER_DAYS,
    INSIDER_SELL_ALERT_USD,
    EARNINGS_ALERT_DAYS,
    TRADE_YOY_ALERT_PCT,
    ANALYST_LOOKBACK_DAYS,
    SHORT_MOM_ALERT_PCT,
    SHORT_FLOAT_ALERT_PCT,
    SOCIAL_SKEW_MIN_TAGGED,
    SOCIAL_SKEW_ALERT,
    GDELT_VOLUME_SPIKE,
    ASYM_MIN_ATTRACTIVE,
    ASYM_POOR,
    MACRO_TICKERS,
    MACRO_MOVE_ALERT_PCT,
    VIX_ALERT_LEVEL,
    CONFERENCE_ALERT_DAYS,
    CONFERENCE_DIGEST_DAYS,
    NEWS_LOOKBACK_HOURS,
    NEWS_PER_TICKER,
)

# Human labels for SEC Form 4 transaction codes
TX_CODES = {
    "P": "open-market buy", "S": "open-market sale", "A": "award/grant",
    "M": "option exercise", "F": "tax withholding", "G": "gift",
    "D": "disposition to issuer", "C": "conversion",
}


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def ticker_snapshot(conn, ticker: str) -> dict:
    """Latest close, 1d/5d change, volume vs 30-day average for one ticker."""
    rows = conn.execute(
        "SELECT date, close, volume FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date DESC LIMIT 31",
        (ticker,),
    ).fetchall()
    snap = {"ticker": ticker, "name": TICKERS[ticker]["name"], "close": None, "date": None,
            "pct_1d": None, "pct_5d": None, "vol_ratio": None}
    if not rows:
        return snap
    latest = rows[0]
    snap["close"], snap["date"] = latest["close"], latest["date"]
    if len(rows) > 1 and rows[1]["close"]:
        snap["pct_1d"] = (latest["close"] / rows[1]["close"] - 1) * 100
    if len(rows) > 5 and rows[5]["close"]:
        snap["pct_5d"] = (latest["close"] / rows[5]["close"] - 1) * 100
    vols = [r["volume"] for r in rows[1:31] if r["volume"]]
    if vols and latest["volume"]:
        snap["vol_ratio"] = latest["volume"] / (sum(vols) / len(vols))
    return snap


def recent_filings(conn, ticker: str, days: int = FILING_LOOKBACK_DAYS):
    return conn.execute(
        "SELECT form, filed, doc, url FROM filings WHERE ticker=? AND filed>=? ORDER BY filed DESC",
        (ticker, _days_ago(days)),
    ).fetchall()


def insider_summary(conn, ticker: str, days: int = INSIDER_CLUSTER_DAYS) -> dict:
    """Aggregate parsed open-market activity (P buys / S sells) in the window."""
    out = {"buys": 0, "buy_value": 0.0, "sells": 0, "sell_value": 0.0}
    for r in conn.execute(
        "SELECT code, COUNT(*) n, SUM(value) v FROM insider_tx "
        "WHERE ticker=? AND tx_date>=? AND code IN ('P','S') GROUP BY code",
        (ticker, _days_ago(days)),
    ):
        if r["code"] == "P":
            out["buys"], out["buy_value"] = r["n"], r["v"] or 0.0
        else:
            out["sells"], out["sell_value"] = r["n"], r["v"] or 0.0
    return out


def insider_transactions(conn, ticker: str = None, days: int = 30, codes=("P", "S")):
    """Individual parsed transactions, newest first."""
    q = ("SELECT ticker, owner, title, tx_date, code, shares, price, value FROM insider_tx "
         "WHERE tx_date>=? AND code IN (%s)" % ",".join("?" * len(codes)))
    args = [_days_ago(days), *codes]
    if ticker:
        q += " AND ticker=?"
        args.append(ticker)
    q += " ORDER BY tx_date DESC, value DESC"
    return conn.execute(q, args).fetchall()


def next_earnings(conn, ticker: str):
    """Next known earnings date (row or None)."""
    return conn.execute(
        "SELECT date, eps_est FROM earnings WHERE ticker=? AND date >= date('now') ORDER BY date LIMIT 1",
        (ticker,),
    ).fetchone()


def upcoming_earnings(conn, days: int = 45):
    return conn.execute(
        "SELECT ticker, date, eps_est FROM earnings "
        "WHERE date >= date('now') AND date <= date('now', ?) ORDER BY date",
        (f"+{days} days",),
    ).fetchall()


def trade_flow_series(conn, hs_code: str):
    """Monthly export series per reporter for one HS code."""
    return conn.execute(
        "SELECT reporter, period, value_usd FROM trade_flows "
        "WHERE hs_code=? AND value_usd IS NOT NULL ORDER BY period",
        (hs_code,),
    ).fetchall()


def trade_yoy(conn):
    """Latest-month YoY change per reporter/hs_code. Returns list of dicts."""
    out = []
    combos = conn.execute(
        "SELECT reporter, hs_code, MAX(period) latest FROM trade_flows "
        "WHERE value_usd IS NOT NULL GROUP BY reporter, hs_code"
    ).fetchall()
    for c in combos:
        latest = conn.execute(
            "SELECT value_usd FROM trade_flows WHERE reporter=? AND hs_code=? AND period=?",
            (c["reporter"], c["hs_code"], c["latest"]),
        ).fetchone()
        prior_period = str(int(c["latest"]) - 100)  # same month, prior year
        prior = conn.execute(
            "SELECT value_usd FROM trade_flows WHERE reporter=? AND hs_code=? AND period=?",
            (c["reporter"], c["hs_code"], prior_period),
        ).fetchone()
        yoy = None
        if prior and prior["value_usd"]:
            yoy = (latest["value_usd"] / prior["value_usd"] - 1) * 100
        out.append({"reporter": c["reporter"], "hs_code": c["hs_code"],
                    "period": c["latest"], "value": latest["value_usd"], "yoy": yoy})
    return out


_VALUATIONS_FILE = Path(__file__).parent / "valuations.json"
_CONFERENCES_FILE = Path(__file__).parent / "conferences.json"


def load_conferences() -> list[dict]:
    """Curated industry events from conferences.json (empty list if absent)."""
    if not _CONFERENCES_FILE.exists():
        return []
    return json.loads(_CONFERENCES_FILE.read_text()).get("events", [])


def upcoming_conferences(days: int = CONFERENCE_DIGEST_DAYS) -> list[dict]:
    """Events currently running or starting within `days`, each annotated with
    days_out (negative while an event is in progress) and only the watchlist
    tickers it touches. Sorted soonest-first.
    """
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=days)
    out = []
    for e in load_conferences():
        try:
            start = datetime.strptime(e["start"], "%Y-%m-%d").date()
            end = datetime.strptime(e.get("end", e["start"]), "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if end < today or start > horizon:
            continue  # already over, or beyond the window
        relevant = [t for t in e.get("tickers", []) if t in TICKERS]
        out.append({**e, "days_out": (start - today).days,
                    "in_progress": start <= today <= end,
                    "watchlist_tickers": relevant})
    return sorted(out, key=lambda x: x["start"])


def load_valuations() -> dict:
    """User-defined bull/bear scenario values ({ticker: {bull, bear, note}}).

    Resolution order:
      1. Streamlit secret `valuations_json` (a JSON string) — used by the public
         hosted dashboard so the values never live in that public repo.
      2. Local valuations.json file (private repo / local runs).
    """
    try:
        import streamlit as st  # only present in the dashboard runtime
        raw = st.secrets.get("valuations_json") if hasattr(st, "secrets") else None
        if raw:
            data = json.loads(raw)
            return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        pass  # not running under Streamlit, or no secret set — fall through
    if not _VALUATIONS_FILE.exists():
        return {}
    data = json.loads(_VALUATIONS_FILE.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def asymmetry(bull, bear, price) -> dict:
    """Asymmetry = (bull - price) / (price - bear).

    status: ok | above_bull (upside exhausted) | at_or_below_bear (downside
    'used up' — the formula breaks down; the thesis needs review, not math) |
    undefined (missing inputs or bear >= bull).
    """
    if bull is None or bear is None or price is None or bear >= bull:
        return {"value": None, "status": "undefined"}
    if price <= bear:
        return {"value": None, "status": "at_or_below_bear"}
    if price >= bull:
        return {"value": 0.0, "status": "above_bull"}
    return {"value": (bull - price) / (price - bear), "status": "ok"}


def ticker_asymmetry(conn, ticker: str) -> dict:
    """User asymmetry (valuations.json) + street asymmetry (analyst high/low)
    against the latest close. Street is a mechanical reference only — analyst
    extremes are not honest scenario work.
    """
    snap = ticker_snapshot(conn, ticker)
    price = snap["close"]
    vals = load_valuations().get(ticker, {})
    mine = asymmetry(vals.get("bull"), vals.get("bear"), price)
    street = {"value": None, "status": "undefined"}
    s = analyst_summary(conn, ticker)
    if s and s["target_high"] and s["target_low"]:
        street = asymmetry(s["target_high"], s["target_low"], price)
    return {"ticker": ticker, "price": price,
            "bull": vals.get("bull"), "bear": vals.get("bear"), "note": vals.get("note", ""),
            "mine": mine, "street": street,
            "t_high": s["target_high"] if s else None, "t_low": s["target_low"] if s else None}


def recent_analyst_actions(conn, ticker: str = None, days: int = ANALYST_LOOKBACK_DAYS):
    """Grade/price-target actions, newest first."""
    q = ("SELECT ticker, date, firm, action, from_grade, to_grade, pt_action, pt_current, pt_prior "
         "FROM analyst_actions WHERE date >= ?")
    args = [_days_ago(days)]
    if ticker:
        q += " AND ticker=?"
        args.append(ticker)
    return conn.execute(q + " ORDER BY date DESC", args).fetchall()


def analyst_summary(conn, ticker: str):
    """Latest consensus snapshot (price targets + recommendation counts)."""
    return conn.execute(
        "SELECT * FROM analyst_summary WHERE ticker=? ORDER BY fetched DESC LIMIT 1", (ticker,)
    ).fetchone()


def latest_short_interest(conn, ticker: str):
    row = conn.execute(
        "SELECT * FROM short_interest WHERE ticker=? ORDER BY date DESC LIMIT 1", (ticker,)
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["mom_pct"] = ((row["shares_short"] / row["shares_prior"] - 1) * 100
                      if row["shares_prior"] else None)
    return out


def top_holders(conn, ticker: str):
    return conn.execute(
        "SELECT holder, reported, shares, value, pct_held, pct_change FROM inst_holders "
        "WHERE ticker=? AND reported=(SELECT MAX(reported) FROM inst_holders WHERE ticker=?) "
        "ORDER BY value DESC", (ticker, ticker)
    ).fetchall()


def social_snapshot(conn, ticker: str):
    """Latest StockTwits sample + skew (bull/(bull+bear)); None when no data."""
    row = conn.execute(
        "SELECT date, messages, bullish, bearish FROM social_sentiment "
        "WHERE ticker=? AND source='stocktwits' ORDER BY date DESC LIMIT 1", (ticker,)
    ).fetchone()
    if not row:
        return None
    tagged = row["bullish"] + row["bearish"]
    return {"date": row["date"], "messages": row["messages"], "bullish": row["bullish"],
            "bearish": row["bearish"], "tagged": tagged,
            "skew": row["bullish"] / tagged if tagged else None}


def gdelt_spike(conn, ticker: str):
    """Yesterday's article volume vs trailing-week average. None without data."""
    rows = conn.execute(
        "SELECT date, volume, tone FROM news_metrics WHERE ticker=? ORDER BY date DESC LIMIT 8",
        (ticker,),
    ).fetchall()
    if len(rows) < 4:
        return None
    latest, rest = rows[0], rows[1:]
    baseline = sum(r["volume"] for r in rest) / len(rest)
    return {"date": latest["date"], "volume": latest["volume"], "tone": latest["tone"],
            "baseline": baseline,
            "ratio": latest["volume"] / baseline if baseline else None}


def attention_series(conn, ticker: str):
    return conn.execute(
        "SELECT date, score FROM attention WHERE ticker=? ORDER BY date", (ticker,)
    ).fetchall()


def macro_snapshot(conn) -> list[dict]:
    """Latest close + 1d/5d change for the macro context instruments."""
    out = []
    for ticker, name in MACRO_TICKERS.items():
        rows = conn.execute(
            "SELECT date, close FROM prices WHERE ticker=? AND close IS NOT NULL ORDER BY date DESC LIMIT 6",
            (ticker,),
        ).fetchall()
        snap = {"ticker": ticker, "name": name, "close": None, "pct_1d": None, "pct_5d": None}
        if rows:
            snap["close"] = rows[0]["close"]
            if len(rows) > 1 and rows[1]["close"]:
                snap["pct_1d"] = (rows[0]["close"] / rows[1]["close"] - 1) * 100
            if len(rows) > 5 and rows[5]["close"]:
                snap["pct_5d"] = (rows[0]["close"] / rows[5]["close"] - 1) * 100
        out.append(snap)
    return out


def macro_news(conn, hours: int = 48, limit: int = 8):
    """Fresh macro-topic headlines (stored under pseudo-ticker _MACRO)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return conn.execute(
        "SELECT published, title, source, url FROM news WHERE ticker='_MACRO' AND published>=? "
        "ORDER BY published DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()


def fresh_news(conn, ticker: str, hours: int = NEWS_LOOKBACK_HOURS, limit: int = NEWS_PER_TICKER):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return conn.execute(
        "SELECT published, title, source, url FROM news WHERE ticker=? AND published>=? "
        "ORDER BY published DESC LIMIT ?",
        (ticker, cutoff, limit),
    ).fetchall()


def build_alerts(conn) -> list[dict]:
    """Cross-ticker alerts: [{ticker, kind, message}], digest/dashboard render message."""
    alerts = []

    def add(ticker, kind, message):
        alerts.append({"ticker": ticker, "kind": kind, "message": message})

    for ticker in TICKERS:
        snap = ticker_snapshot(conn, ticker)
        if snap["pct_1d"] is not None and abs(snap["pct_1d"]) >= PRICE_MOVE_ALERT_PCT:
            arrow = "▲" if snap["pct_1d"] > 0 else "▼"
            add(ticker, "price", f"{arrow} **{ticker}** moved {snap['pct_1d']:+.1f}% on the last session")
        if snap["vol_ratio"] is not None and snap["vol_ratio"] >= VOLUME_RATIO_ALERT:
            add(ticker, "volume", f"📊 **{ticker}** volume {snap['vol_ratio']:.1f}x its 30-day average")

        for f in recent_filings(conn, ticker):
            if f["form"] != "4":
                add(ticker, "filing", f"📄 **{ticker}** filed {f['form']} on {f['filed']} ([doc]({f['url']}))")

        ins = insider_summary(conn, ticker)
        if ins["buys"]:
            add(ticker, "insider",
                f"💰 **{ticker}**: {ins['buys']} open-market insider buy(s) totaling "
                f"${ins['buy_value']:,.0f} in the last {INSIDER_CLUSTER_DAYS} days")
        if ins["sell_value"] >= INSIDER_SELL_ALERT_USD:
            add(ticker, "insider",
                f"👤 **{ticker}**: {ins['sells']} open-market insider sale(s) totaling "
                f"${ins['sell_value']:,.0f} in the last {INSIDER_CLUSTER_DAYS} days")

        e = next_earnings(conn, ticker)
        if e:
            days_out = (datetime.strptime(e["date"], "%Y-%m-%d").date()
                        - datetime.now(timezone.utc).date()).days
            if 0 <= days_out <= EARNINGS_ALERT_DAYS:
                when = "today" if days_out == 0 else f"in {days_out} day(s)"
                est = f" (est EPS {e['eps_est']})" if e["eps_est"] is not None else ""
                add(ticker, "earnings", f"📅 **{ticker}** reports earnings {when} — {e['date']}{est}")

        for a in recent_analyst_actions(conn, ticker):
            if a["action"] in ("up", "down"):
                arrow = "⬆️" if a["action"] == "up" else "⬇️"
                add(ticker, "analyst",
                    f"{arrow} **{ticker}**: {a['firm']} {'upgraded' if a['action'] == 'up' else 'downgraded'} "
                    f"to {a['to_grade']}" + (f" (from {a['from_grade']})" if a["from_grade"] else ""))
            elif a["pt_action"] in ("Raises", "Lowers") and a["pt_prior"]:
                chg = (a["pt_current"] / a["pt_prior"] - 1) * 100
                if abs(chg) >= 10:
                    add(ticker, "analyst",
                        f"🎯 **{ticker}**: {a['firm']} {a['pt_action'].lower()} target "
                        f"{a['pt_prior']:.0f} → {a['pt_current']:.0f} ({chg:+.0f}%)")

        si = latest_short_interest(conn, ticker)
        if si:
            if si["mom_pct"] is not None and abs(si["mom_pct"]) >= SHORT_MOM_ALERT_PCT:
                arrow = "▲" if si["mom_pct"] > 0 else "▼"
                add(ticker, "short",
                    f"🩳 {arrow} **{ticker}** short interest {si['mom_pct']:+.0f}% MoM "
                    f"({100 * (si['pct_float'] or 0):.1f}% of float, {si['ratio']:.1f} days to cover)")
            elif si["pct_float"] and si["pct_float"] * 100 >= SHORT_FLOAT_ALERT_PCT:
                add(ticker, "short",
                    f"🩳 **{ticker}**: {100 * si['pct_float']:.1f}% of float is short "
                    f"({si['ratio']:.1f} days to cover)")

        soc = social_snapshot(conn, ticker)
        if soc and soc["tagged"] >= SOCIAL_SKEW_MIN_TAGGED and soc["skew"] is not None:
            if soc["skew"] >= SOCIAL_SKEW_ALERT or soc["skew"] <= 1 - SOCIAL_SKEW_ALERT:
                mood = "bullish" if soc["skew"] >= 0.5 else "bearish"
                add(ticker, "social",
                    f"💬 **{ticker}** StockTwits sample is {soc['skew']*100 if mood == 'bullish' else (1-soc['skew'])*100:.0f}% "
                    f"{mood} ({soc['bullish']}🐂/{soc['bearish']}🐻 of {soc['messages']} recent messages)")

        g = gdelt_spike(conn, ticker)
        if g and g["ratio"] is not None and g["ratio"] >= GDELT_VOLUME_SPIKE:
            tone = f", avg tone {g['tone']:+.1f}" if g["tone"] is not None else ""
            add(ticker, "narrative",
                f"📰 **{ticker}** news volume {g['ratio']:.1f}x its weekly average "
                f"({g['volume']:.0f} articles{tone})")

        asym = ticker_asymmetry(conn, ticker)
        m = asym["mine"]
        if m["status"] == "ok":
            if m["value"] >= ASYM_MIN_ATTRACTIVE:
                add(ticker, "asymmetry",
                    f"⚖️ **{ticker}** asymmetry {m['value']:.1f} — at/above your {ASYM_MIN_ATTRACTIVE:.0f} bar "
                    f"(bull {asym['bull']:g} / bear {asym['bear']:g} vs {asym['price']:.2f})")
            elif m["value"] < ASYM_POOR:
                add(ticker, "asymmetry",
                    f"⚖️ **{ticker}** asymmetry {m['value']:.1f} — downside now exceeds upside "
                    f"(bull {asym['bull']:g} / bear {asym['bear']:g} vs {asym['price']:.2f})")
        elif m["status"] == "at_or_below_bear":
            add(ticker, "asymmetry",
                f"⚖️ **{ticker}** trades at/below your bear case ({asym['bear']:g}) — thesis review, not math")
        elif m["status"] == "above_bull":
            add(ticker, "asymmetry",
                f"⚖️ **{ticker}** trades at/above your bull case ({asym['bull']:g}) — upside exhausted per your model")

    for e in upcoming_conferences(days=CONFERENCE_ALERT_DAYS):
        if not e["watchlist_tickers"]:
            continue
        names = ", ".join(e["watchlist_tickers"])
        when = ("in progress now" if e["in_progress"]
                else "today" if e["days_out"] == 0
                else f"in {e['days_out']} day(s)")
        add(None, "conference",
            f"🎤 **{e['name']}** {when} ({e['start']}) — watch {names}")

    for m in macro_snapshot(conn):
        if m["ticker"] == "^VIX":
            if m["close"] is not None and m["close"] >= VIX_ALERT_LEVEL:
                add(None, "macro", f"🌍 **VIX at {m['close']:.0f}** — stressed regime; expect gap risk in the small caps")
            continue  # VIX % moves are noise; level is the signal
        if m["pct_1d"] is not None and abs(m["pct_1d"]) >= MACRO_MOVE_ALERT_PCT:
            arrow = "▲" if m["pct_1d"] > 0 else "▼"
            add(None, "macro", f"🌍 {arrow} **{m['name']}** {m['pct_1d']:+.1f}% on the last session")

    for t in trade_yoy(conn):
        if t["yoy"] is not None and abs(t["yoy"]) >= TRADE_YOY_ALERT_PCT:
            arrow = "▲" if t["yoy"] > 0 else "▼"
            add(None, "trade",
                f"🚢 {arrow} **{t['reporter']}** HS {t['hs_code']} exports {t['yoy']:+.0f}% YoY "
                f"({fmt_usd(t['value'])} in {t['period']})")

    return alerts


def fmt_usd(v: float) -> str:
    """$3.7B / $412M / $122k depending on magnitude."""
    if v >= 1e9:
        return f"${v/1e9:,.1f}B"
    if v >= 1e6:
        return f"${v/1e6:,.0f}M"
    return f"${v/1e3:,.0f}k"
