"""Short-horizon trade-desk layer.

Records the DIRECTIONAL CALLS published by the trade-tier accounts in
sources/analysts.md (@__Con_, @Brownmoose) and cross-references them against the
research-tier stances in valuations.json.

The point is NOT to generate trade ideas. It is to do three things the research
layer cannot:

  1. MAKE CALLS FALSIFIABLE. A recorded call with a date and a level can be scored.
     "It cost nothing to follow me" cannot. Recording is how a claimed track record
     becomes a measured one.
  2. SURFACE CONFLICT. The highest-value output is where a short-horizon trader is
     positioned AGAINST your research stance on the same name (right now:
     @Brownmoose short NBIS while your book is Bullish NBIS). That tension is
     information; the resolution is yours.
  3. SEPARATE HORIZONS. A 2-week level test and a 2029 CPO ramp are not the same
     claim and must never be blended into one "view".

Nothing here is advice, and none of it is this system's opinion. Every line is
attributed to a named account with a date.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
CALLS_FILE = HERE / "trade_calls.json"

# Research stances that mean "constructive" vs "negative", for conflict detection
_POS = {"Bullish", "Constructive"}
_NEG = {"Cautious"}


def calls(open_only: bool = False) -> list[dict]:
    if not CALLS_FILE.exists():
        return []
    data = json.loads(CALLS_FILE.read_text()).get("calls", [])
    if open_only:
        data = [c for c in data if c.get("status") == "open"]
    return sorted(data, key=lambda c: c.get("date", ""), reverse=True)


def _direction_sign(d: str) -> int:
    d = (d or "").upper()
    if d.startswith("SHORT"):
        return -1
    if d.startswith("LONG"):
        return 1
    return 0


def conflicts(stances: dict) -> list[dict]:
    """Calls that point against the research stance on the same ticker."""
    out = []
    for c in calls(open_only=True):
        t = c.get("ticker", "")
        if t.startswith("_"):
            continue
        s = stances.get(t)
        if not s:
            continue
        sign = _direction_sign(c.get("direction", ""))
        stance = s.get("stance", "")
        if sign == -1 and stance in _POS:
            out.append({**c, "stance": stance, "kind": "trader short vs research constructive"})
        elif sign == 1 and stance in _NEG:
            out.append({**c, "stance": stance, "kind": "trader long vs research cautious"})
    return out


def scoreboard() -> dict:
    """Measured, not claimed. Counts by status per account."""
    tally = {}
    for c in calls():
        a = c.get("account", "?")
        tally.setdefault(a, {"open": 0, "hit": 0, "invalidated": 0, "expired": 0})
        st = c.get("status", "open")
        if st in tally[a]:
            tally[a][st] += 1
    return tally


def summary(stances: dict) -> dict:
    return {"calls": calls(), "open": calls(open_only=True),
            "conflicts": conflicts(stances), "scoreboard": scoreboard()}
