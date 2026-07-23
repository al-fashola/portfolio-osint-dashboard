"""UN Comtrade monthly trade flows for semiconductor-relevant HS codes.

Uses the free public preview API (no key). Its quirks, learned empirically:
  - exactly ONE period per request (multi-period returns 400/"Maximum
    number of periods for preview is 1")
  - reporters and commodity codes CAN be combined in a single call
  - aggressive rate limiting -> generous sleep + one retry on 429

So we fetch one month per request and work incrementally: months already in
the DB are skipped except the trailing RECHECK_MONTHS (countries publish
late and revise). Taiwan is not a UN reporter — Korea/China/Japan/
Netherlands are the available semi-supply-chain proxies. Data lags ~3-6
months; the signal is the trend and YoY surges, not freshness.

Refreshes at most once every REFRESH_DAYS (tracked in the meta table).
"""
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"

REPORTERS = {
    410: "Korea",
    156: "China",
    392: "Japan",
    528: "Netherlands",
}

HS_CODES = {
    "8542": "Integrated circuits",
    "8486": "Semiconductor mfg equipment",
    "854232": "Memory ICs",
}

MONTHS_BACK = 24        # history window (enough for YoY comparison)
RECHECK_MONTHS = 4      # trailing months to refetch (late publication/revisions)
REFRESH_DAYS = 7
REQUEST_GAP_S = 6


def _periods(n: int = MONTHS_BACK) -> list[str]:
    """Last n complete months as YYYYMM, oldest first."""
    cur = datetime.now(timezone.utc).replace(day=1)
    out = []
    for _ in range(n):
        cur = (cur - timedelta(days=1)).replace(day=1)
        out.append(cur.strftime("%Y%m"))
    return list(reversed(out))


def _fetch_period(period: str) -> list[tuple]:
    params = {
        "reporterCode": ",".join(str(c) for c in REPORTERS),
        "cmdCode": ",".join(HS_CODES),
        "flowCode": "X",
        "period": period,
        "partnerCode": "0",   # World
    }
    resp = requests.get(BASE, params=params, timeout=60)
    if resp.status_code == 429:   # back off once, then give up on this period
        time.sleep(30)
        resp = requests.get(BASE, params=params, timeout=60)
    resp.raise_for_status()
    rows = []
    for d in resp.json().get("data", []):
        name = REPORTERS.get(d.get("reporterCode"))
        if name:
            rows.append((name, d.get("flowCode", "X"), str(d.get("cmdCode")),
                         str(d.get("period")), d.get("primaryValue")))
    return rows


def fetch_trade_flows(conn) -> list[tuple]:
    """Fetch periods missing from the DB (plus the trailing recheck window)."""
    have = {r["period"] for r in conn.execute(
        "SELECT DISTINCT period FROM trade_flows"
    )}
    wanted = _periods()
    recheck = set(wanted[-RECHECK_MONTHS:])
    todo = [p for p in wanted if p not in have or p in recheck]
    print(f"  {len(todo)} period(s) to fetch ({len(have)} already stored)")
    rows = []
    for i, period in enumerate(todo):
        if i:
            time.sleep(REQUEST_GAP_S)
        try:
            got = _fetch_period(period)
            rows.extend(got)
            print(f"  {period}: {len(got)} records")
        except Exception as e:
            print(f"  ! {period}: {e}")
    return rows


def maybe_refresh(conn, db) -> bool:
    """Fetch if stale; returns True when a fetch happened."""
    last = db.get_meta(conn, "comtrade_last_fetch")
    if last:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last)
        if age < timedelta(days=REFRESH_DAYS):
            print(f"  Comtrade data is {age.days}d old — skipping (refreshes every {REFRESH_DAYS}d)")
            return False
    rows = fetch_trade_flows(conn)
    if rows:
        db.upsert_trade_flows(conn, rows)
        db.set_meta(conn, "comtrade_last_fetch", datetime.now(timezone.utc).isoformat())
    return bool(rows)
