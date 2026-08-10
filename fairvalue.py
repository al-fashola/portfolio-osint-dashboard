"""Fair-value + discipline engine — the time-value-of-money layer.

Built 2026-08-07 from the five-equation framework the user supplied
(@lumenxbt, "The Five Equations That Quietly Run Your Entire Financial Life"):

  1. Compound growth   FV = PV x (1+r)^n
  2. Rule of 72        doubling years ~= 72 / r%
  3. Present value     PV = FV / (1+r)^n
  4. Geometric mean    the honest average return (never the arithmetic one)
  5. Real return       (1+nominal)/(1+inflation) - 1

WHAT THIS IS
------------
It converts the bull/bear scenario values you already maintain in valuations.json
into time-aware questions:

  * fair_value_today  = PV of YOUR bull case, discounted at your required rate over
                        your horizon. If price > this, the discounted best case is
                        already in the price.
  * required_cagr     = the annual return the CURRENT price must compound at to
                        reach your bull value inside the horizon.
  * doubling_years    = Rule of 72 applied to that required rate (sanity check:
                        does the implied doubling time pass a smell test?).
  * real_cagr         = required_cagr after inflation — what you actually keep.
  * downside_cagr     = the annualised loss to the bear value (the symmetric question
                        nobody asks).

WHAT THIS IS NOT
----------------
Not advice, not a recommendation, not a price target. Every number here is a
mechanical transform of values YOU set. The engine has no view. Where it prints a
"flag" it is restating your own arithmetic back to you — exactly like the existing
asymmetry engine — so that a decision is made against numbers instead of vibes.
"""
from __future__ import annotations

# Defaults — override per-ticker in valuations.json via "horizon_years"
DEFAULT_HORIZON_Y = 3.0
DEFAULT_DISCOUNT = 0.10      # required annual return (opportunity cost / hurdle)
DEFAULT_INFLATION = 0.03

# Flag thresholds
CAGR_HEROIC = 0.35           # required CAGR above this = demanding a lot of the future
CAGR_MODEST = 0.10           # below this = you are underwriting little growth


def present_value(fv: float, r: float, n: float) -> float:
    """Equation 3. What a future value is worth today at rate r over n years."""
    return fv / ((1.0 + r) ** n)


def future_value(pv: float, r: float, n: float) -> float:
    """Equation 1."""
    return pv * ((1.0 + r) ** n)


def rule_of_72(rate_pct: float) -> float | None:
    """Equation 2. Years to double at rate_pct (percent, not decimal)."""
    if not rate_pct or rate_pct <= 0:
        return None
    return 72.0 / rate_pct


def cagr(start: float, end: float, n: float) -> float | None:
    """Equation 4 in spirit — the geometric (compound) rate, not an arithmetic average."""
    if not start or start <= 0 or end is None or end <= 0 or n <= 0:
        return None
    return (end / start) ** (1.0 / n) - 1.0


def real_return(nominal: float, inflation: float = DEFAULT_INFLATION) -> float:
    """Equation 5. The Fisher-exact version, not the lazy subtraction."""
    return (1.0 + nominal) / (1.0 + inflation) - 1.0


def evaluate(price: float, bull: float | None, bear: float | None,
             horizon_years: float = DEFAULT_HORIZON_Y,
             discount: float = DEFAULT_DISCOUNT,
             inflation: float = DEFAULT_INFLATION) -> dict:
    """Run the full five-equation view on one holding.

    Returns {} when inputs are missing — callers should treat that as "not evaluated"
    rather than as a neutral verdict.
    """
    if not price or price <= 0 or bull is None or bull <= 0:
        return {}

    fv_today = present_value(bull, discount, horizon_years)
    req = cagr(price, bull, horizon_years)
    dbl = rule_of_72(req * 100.0) if req else None
    real = real_return(req, inflation) if req is not None else None
    down = cagr(price, bear, horizon_years) if bear else None

    # premium/discount of price vs the discounted bull case
    gap = (fv_today / price - 1.0) if price else None

    flags = []
    if gap is not None and gap < 0:
        flags.append(
            f"price is {abs(gap)*100:.0f}% ABOVE the present value of your own bull case "
            f"({fv_today:,.2f}) at a {discount*100:.0f}% hurdle over {horizon_years:g}y — "
            f"the discounted best case is already in the price")
    if req is not None and req >= CAGR_HEROIC:
        flags.append(
            f"reaching your bull needs {req*100:.0f}%/yr for {horizon_years:g}y "
            f"(doubling every {dbl:.1f}y) — check that against what your sources actually model")
    if req is not None and req < CAGR_MODEST:
        flags.append(
            f"only {req*100:.0f}%/yr is required to reach bull — either the bull is "
            f"conservative or the upside is largely realised")
    if real is not None and real < 0:
        flags.append(
            f"after {inflation*100:.0f}% inflation the required path is NEGATIVE in real "
            f"terms ({real*100:.1f}%/yr) — you would be losing purchasing power at the bull case")
    if down is not None and req is not None and abs(down) > req:
        flags.append(
            f"the annualised path to bear ({down*100:.0f}%/yr) is steeper than the path to "
            f"bull ({req*100:.0f}%/yr) — the downside compounds faster than the upside")

    return {
        "price": price, "bull": bull, "bear": bear,
        "horizon_years": horizon_years, "discount": discount, "inflation": inflation,
        "fair_value_today": fv_today,
        "gap_vs_price": gap,
        "required_cagr": req,
        "doubling_years": dbl,
        "real_cagr": real,
        "downside_cagr": down,
        "flags": flags,
    }


def evaluate_all(valuations: dict, prices: dict,
                 horizon_years: float = DEFAULT_HORIZON_Y,
                 discount: float = DEFAULT_DISCOUNT,
                 inflation: float = DEFAULT_INFLATION) -> dict:
    """{ticker: evaluate(...)} for every ticker with a price and a bull value."""
    out = {}
    for t, v in valuations.items():
        if t.startswith("_"):
            continue
        px = prices.get(t)
        h = v.get("horizon_years", horizon_years)
        r = evaluate(px, v.get("bull"), v.get("bear"), h, discount, inflation)
        if r:
            out[t] = r
    return out
