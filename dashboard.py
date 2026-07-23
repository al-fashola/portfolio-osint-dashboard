"""Streamlit dashboard over the portfolio OSINT SQLite store.

Run:  venv/bin/streamlit run dashboard.py

Chart colors follow the validated reference palette (dataviz skill):
categorical slots are assigned to entities in fixed order and never repainted;
signed values use the blue<->red diverging pair, not green/red.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import db
from config import TICKERS, INSIDER_LOOKBACK_DAYS
from fetch_comtrade import HS_CODES
from signals import (
    ticker_snapshot, recent_filings, fresh_news, build_alerts,
    insider_transactions, insider_summary, next_earnings, upcoming_earnings,
    trade_flow_series, trade_yoy, TX_CODES,
    recent_analyst_actions, analyst_summary, latest_short_interest, top_holders,
    social_snapshot, gdelt_spike, attention_series, ticker_asymmetry,
    macro_snapshot, macro_news, upcoming_conferences,
    financial_summary, financials as financials_q, fmt_mag,
)
from config import ASYM_MIN_ATTRACTIVE


def asym_display(a: dict) -> str:
    return {"ok": lambda: f"{a['value']:.1f}", "above_bull": lambda: "0 (≥bull)",
            "at_or_below_bear": lambda: "⚠️ ≤bear", "undefined": lambda: "—"}[a["status"]]()

st.set_page_config(page_title="Portfolio OSINT", page_icon="🛰️", layout="wide")

# Validated categorical palette (light mode), fixed slot order
SLOTS = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
POS, NEG = "#2a78d6", "#e34948"          # diverging pair poles (blue <-> red)
MUTED, GRID = "#898781", "#e1e0d9"
DELTA_UP, DELTA_DOWN = "#006300", "#c62828"   # text-token deltas for tables

# Fixed entity->slot assignment for Comtrade reporters (alphabetical, never cycled)
REPORTER_COLORS = {"China": SLOTS[0], "Japan": SLOTS[1], "Korea": SLOTS[2], "Netherlands": SLOTS[3]}

ALERT_KIND_COLORS = {"price": SLOTS[0], "volume": SLOTS[1], "filing": SLOTS[2],
                     "trade": SLOTS[3], "insider": SLOTS[4], "analyst": SLOTS[5],
                     "short": SLOTS[6], "earnings": SLOTS[7],
                     # 9th+ kinds take neutral inks (legend carries identity)
                     "social": "#52514e", "narrative": "#898781",
                     "macro": "#4a3aa7", "conference": "#eb6834"}

HS_LABELS = {"8542": "Integrated circuits", "8486": "Semi mfg equipment", "854232": "Memory ICs"}

PLOT_LAYOUT = dict(
    margin=dict(t=24, b=24, l=8, r=8),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'),
    xaxis=dict(gridcolor=GRID, zeroline=False),
    yaxis=dict(gridcolor=GRID, zeroline=False),
    hovermode="x unified",
)


def layout(**overrides) -> dict:
    """PLOT_LAYOUT with overrides; nested axis dicts are merged, not replaced."""
    merged = {**PLOT_LAYOUT, **overrides}
    for axis in ("xaxis", "yaxis"):
        if axis in overrides:
            merged[axis] = {**PLOT_LAYOUT[axis], **overrides[axis]}
    return merged

# Fresh connection per rerun — Streamlit runs each rerun on a different
# thread, and SQLite connections are not shareable across threads.
conn = db.connect(check_same_thread=False)

st.title("🛰️ Portfolio OSINT")
last_run = conn.execute("SELECT ts FROM runs ORDER BY ts DESC LIMIT 1").fetchone()
st.caption(f"Last pipeline run: {last_run['ts'][:19] if last_run else 'never — run run_daily.py'} UTC")


def style_snapshot(df):
    return (
        df.style.format({"Close": "{:.2f}", "1d %": "{:+.1f}", "5d %": "{:+.1f}", "Vol/30d": "{:.1f}x"}, na_rep="—")
        .map(lambda v: f"color: {DELTA_UP}" if isinstance(v, float) and v > 0
             else (f"color: {DELTA_DOWN}" if isinstance(v, float) and v < 0 else ""),
             subset=["1d %", "5d %"])
    )


(tab_overview, tab_company, tab_financials, tab_insiders, tab_sentiment,
 tab_trade, tab_history, tab_about) = st.tabs(
    ["📊 Overview", "🏢 Company detail", "💰 Financials", "👤 Insiders", "🧠 Sentiment",
     "🚢 Trade flows", "🕘 Alert history", "ℹ️ About"]
)

# ══════════════════════════════ OVERVIEW ══════════════════════════════
with tab_overview:
    alerts = build_alerts(conn)
    with st.expander(f"🚨 Alerts ({len(alerts)})", expanded=bool(alerts)):
        for a in alerts:
            st.markdown(f"- {a['message']}")
        if not alerts:
            st.write("No alerts triggered.")

    st.subheader("🌍 Macro & market considerations")
    mcols = st.columns(len(macro_snapshot(conn)))
    for col, m in zip(mcols, macro_snapshot(conn)):
        with col:
            delta = f"{m['pct_1d']:+.1f}%" if m["pct_1d"] is not None else None
            val = f"{m['close']:,.1f}" if m["close"] is not None else "—"
            st.metric(m["name"], val, delta, delta_color="off" if m["ticker"] == "^VIX" else "normal")
    with st.expander("Macro headlines (48h)"):
        mn = macro_news(conn, limit=10)
        if mn:
            for n in mn:
                src = f" — *{n['source']}*" if n["source"] else ""
                st.markdown(f"- [{n['title']}]({n['url']}){src}")
        else:
            st.write("No fresh macro headlines stored — run run_daily.py.")

    events = upcoming_conferences()
    if events:
        st.subheader("🎤 Industry events & conferences")
        for e in events:
            when = ("🔴 in progress now" if e["in_progress"]
                    else f"in {e['days_out']} days · {e['start']}")
            names = ", ".join(e["watchlist_tickers"]) or "broad"
            approx = " · ⚠️ date approximate" if e.get("confidence") == "approx" else ""
            with st.expander(f"**{e['name']}** — {when} — watch {names}{approx}"):
                st.markdown(f"**Location:** {e['location']}  \n"
                            f"**Watch for:** {e['watch']}  \n"
                            f"[source]({e['source']})")

    snaps = [ticker_snapshot(conn, t) for t in TICKERS]
    asyms = {t: ticker_asymmetry(conn, t) for t in TICKERS}
    snap_df = pd.DataFrame(snaps)[["ticker", "name", "date", "close", "pct_1d", "pct_5d", "vol_ratio"]]
    snap_df.columns = ["Ticker", "Name", "As of", "Close", "1d %", "5d %", "Vol/30d"]
    snap_df["Asym"] = snap_df["Ticker"].map(lambda t: asym_display(asyms[t]["mine"]))

    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.subheader("Snapshot")
        st.dataframe(style_snapshot(snap_df), width="stretch", hide_index=True, height=420)
    with col_r:
        st.subheader("1-day move")
        bars = snap_df.dropna(subset=["1d %"]).sort_values("1d %")
        fig = go.Figure(go.Bar(
            x=bars["1d %"], y=bars["Ticker"], orientation="h",
            marker_color=[POS if v > 0 else NEG for v in bars["1d %"]],
            marker_line_width=0, text=[f"{v:+.1f}%" for v in bars["1d %"]],
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
        ))
        fig.update_layout(**layout(hovermode="y", yaxis=dict(gridcolor="rgba(0,0,0,0)")),
                          height=420, showlegend=False)
        st.plotly_chart(fig, config={"displayModeBar": False})

    st.subheader("⚖️ Asymmetry — (bull − price) ÷ (price − bear)")
    have_own = [a for a in asyms.values() if a["mine"]["status"] != "undefined"
                or a["bull"] is not None or a["bear"] is not None]
    chart_rows = []
    using_street = False
    for a in asyms.values():
        if a["bull"] is not None and a["bear"] is not None and a["price"]:
            chart_rows.append(a | {"lo": a["bear"], "hi": a["bull"]})
    if not chart_rows:
        using_street = True
        for a in asyms.values():
            if a["t_low"] and a["t_high"] and a["price"]:
                chart_rows.append(a | {"lo": a["t_low"], "hi": a["t_high"]})
    if chart_rows:
        if using_street:
            st.caption("Your `valuations.json` is empty, so this shows **street** ranges "
                       "(analyst low → high targets) as a mechanical placeholder. Fill in your own "
                       "bull/bear values to make this panel yours — that's the whole model.")
        fig = go.Figure()
        # normalize each range to % vs current price so mixed currencies share one axis
        for i, a in enumerate(sorted(chart_rows, key=lambda x: -(x["hi"] / x["price"]))):
            dn = (a["lo"] / a["price"] - 1) * 100
            up = (a["hi"] / a["price"] - 1) * 100
            asym = a["mine"] if not using_street else a["street"]
            label = asym_display(asym)
            fig.add_trace(go.Scatter(x=[dn, 0, up], y=[a["ticker"]] * 3, mode="lines",
                                     line=dict(color=GRID, width=2), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=[dn], y=[a["ticker"]], mode="markers",
                                     marker=dict(color=NEG, size=9), showlegend=(i == 0), name="bear",
                                     hovertemplate=f"bear: {a['lo']:g} ({dn:+.0f}%)<extra>{a['ticker']}</extra>"))
            fig.add_trace(go.Scatter(x=[up], y=[a["ticker"]], mode="markers",
                                     marker=dict(color=POS, size=9), showlegend=(i == 0), name="bull",
                                     hovertemplate=f"bull: {a['hi']:g} ({up:+.0f}%)<extra>{a['ticker']}</extra>"))
            fig.add_trace(go.Scatter(x=[0], y=[a["ticker"]], mode="markers+text",
                                     marker=dict(color="#0b0b0b", size=8, symbol="diamond"),
                                     text=[f"  {label}"], textposition="middle right",
                                     textfont=dict(size=11), showlegend=(i == 0), name="price (asym)",
                                     hovertemplate=f"price {a['price']:.2f} · asym {label}<extra>{a['ticker']}</extra>"))
        fig.update_layout(**layout(hovermode="closest",
                                   xaxis=dict(title="% from current price (◆ = today, label = asymmetry)")),
                          height=100 + 32 * len(chart_rows), legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, config={"displayModeBar": False})
        st.caption(f"Discipline rule of thumb from your framework: high-risk growth wants asymmetry ≥ {ASYM_MIN_ATTRACTIVE:.0f}. "
                   "The bear case determines the quality of the opportunity — a big bull case can't fix a bad denominator.")

    col_e, col_f = st.columns(2)
    with col_e:
        st.subheader("📅 Upcoming earnings")
        ue = upcoming_earnings(conn, days=45)
        if ue:
            edf = pd.DataFrame([dict(r) for r in ue])
            edf.columns = ["Ticker", "Date", "Est. EPS"]
            edf = edf[["Date", "Ticker", "Est. EPS"]]
            st.dataframe(edf, width="stretch", hide_index=True)
        else:
            st.write("No earnings dates in the next 45 days.")
    with col_f:
        st.subheader("📄 Material filings (14 days)")
        shown = 0
        for t in TICKERS:
            for f in recent_filings(conn, t, days=14):
                if f["form"] != "4":
                    st.markdown(f"- {f['filed']} · **{t}** {f['form']} — [{f['doc']}]({f['url']})")
                    shown += 1
        if not shown:
            st.write("None.")

# ══════════════════════════════ COMPANY DETAIL ══════════════════════════════
with tab_company:
    ticker = st.selectbox("Ticker", list(TICKERS), format_func=lambda t: f"{t} — {TICKERS[t]['name']}")
    e = next_earnings(conn, ticker)
    if e:
        est = f" · est EPS {e['eps_est']}" if e["eps_est"] is not None else ""
        st.info(f"📅 Next earnings: **{e['date']}**{est}")

    prices = pd.read_sql_query(
        "SELECT date, close, volume FROM prices WHERE ticker=? ORDER BY date", conn, params=(ticker,)
    )
    if not prices.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        fig.add_trace(go.Scatter(x=prices["date"], y=prices["close"], name="Close",
                                 line=dict(width=2, color=SLOTS[0])), row=1, col=1)
        fig.add_trace(go.Bar(x=prices["date"], y=prices["volume"], name="Volume",
                             marker_color=MUTED, marker_line_width=0), row=2, col=1)
        fig.update_layout(**layout(), height=430, showlegend=False)
        fig.update_yaxes(gridcolor=GRID)
        fig.update_xaxes(gridcolor=GRID)
        st.plotly_chart(fig, config={"displayModeBar": False})
    else:
        st.info("No price history stored (news-only entry or not yet fetched).")

    ins = insider_transactions(conn, ticker=ticker, days=90)
    if ins:
        st.markdown("#### 👤 Insider open-market activity (90 days)")
        idf = pd.DataFrame([dict(r) for r in ins])
        idf["action"] = idf["code"].map(TX_CODES)
        idf = idf[["tx_date", "owner", "title", "action", "shares", "price", "value"]]
        idf.columns = ["Date", "Insider", "Title", "Action", "Shares", "Price", "Value $"]
        st.dataframe(
            idf.style.format({"Shares": "{:,.0f}", "Price": "{:.2f}", "Value $": "{:,.0f}"}),
            width="stretch", hide_index=True,
        )

    hold = top_holders(conn, ticker)
    if hold:
        st.markdown("#### 🏦 Top institutional holders (latest 13F quarter, Yahoo-aggregated)")
        hdf = pd.DataFrame([dict(r) for r in hold])
        hdf["pct_held"] = hdf["pct_held"] * 100
        hdf["pct_change"] = hdf["pct_change"] * 100
        hdf = hdf[["holder", "reported", "shares", "value", "pct_held", "pct_change"]]
        hdf.columns = ["Holder", "Reported", "Shares", "Value $", "% held", "QoQ %"]
        st.dataframe(
            hdf.style.format({"Shares": "{:,.0f}", "Value $": "{:,.0f}", "% held": "{:.2f}", "QoQ %": "{:+.1f}"}, na_rep="—")
            .map(lambda v: f"color: {DELTA_UP}" if isinstance(v, float) and v > 0
                 else (f"color: {DELTA_DOWN}" if isinstance(v, float) and v < 0 else ""), subset=["QoQ %"]),
            width="stretch", hide_index=True,
        )

    col_f, col_n = st.columns(2)
    with col_f:
        st.markdown("#### 📄 SEC filings (30 days)")
        filings = recent_filings(conn, ticker, days=30)
        if filings:
            for f in filings:
                st.markdown(f"- {f['filed']} · **{f['form']}** — [{f['doc']}]({f['url']})")
        else:
            st.write("None (or not a US SEC filer).")
    with col_n:
        st.markdown("#### 📰 Headlines (7 days)")
        news = fresh_news(conn, ticker, hours=168, limit=10)
        if news:
            for n in news:
                src = f" — *{n['source']}*" if n["source"] else ""
                st.markdown(f"- [{n['title']}]({n['url']}){src}")
        else:
            st.write("No stored headlines in the last 7 days.")

# ══════════════════════════════ INSIDERS ══════════════════════════════
with tab_insiders:
    st.subheader("Open-market insider activity across the portfolio")
    days = st.slider("Lookback (days)", 7, 180, INSIDER_LOOKBACK_DAYS, step=7)

    # Net open-market value per ticker (buys - sells): polarity -> diverging pair
    nets = []
    for t in TICKERS:
        s = insider_summary(conn, t, days=days)
        net = s["buy_value"] - s["sell_value"]
        if s["buys"] or s["sells"]:
            nets.append({"ticker": t, "net": net, "buys": s["buys"], "sells": s["sells"]})
    if nets:
        ndf = pd.DataFrame(nets).sort_values("net")
        fig = go.Figure(go.Bar(
            x=ndf["net"], y=ndf["ticker"], orientation="h",
            marker_color=[POS if v > 0 else NEG for v in ndf["net"]], marker_line_width=0,
            customdata=ndf[["buys", "sells"]],
            hovertemplate="%{y}: net $%{x:,.0f}<br>%{customdata[0]} buy(s), %{customdata[1]} sell(s)<extra></extra>",
        ))
        fig.update_layout(**layout(hovermode="y"), height=80 + 40 * len(ndf),
                          showlegend=False, xaxis_title="Net open-market value (buys − sells), $")
        st.plotly_chart(fig, config={"displayModeBar": False})
        st.caption("Blue = net buying, red = net selling. Awards, exercises, tax withholding and gifts excluded.")
    else:
        st.write("No open-market insider transactions in the window.")

    txs = insider_transactions(conn, days=days)
    if txs:
        tdf = pd.DataFrame([dict(r) for r in txs])
        tdf["action"] = tdf["code"].map(TX_CODES)
        tdf = tdf[["tx_date", "ticker", "owner", "title", "action", "shares", "price", "value"]]
        tdf.columns = ["Date", "Ticker", "Insider", "Title", "Action", "Shares", "Price", "Value $"]
        st.dataframe(
            tdf.style.format({"Shares": "{:,.0f}", "Price": "{:.2f}", "Value $": "{:,.0f}"}),
            width="stretch", hide_index=True,
        )

# ══════════════════════════════ FINANCIALS ══════════════════════════════
with tab_financials:
    st.subheader("💰 Financials — latest reported quarter")
    st.caption("Absolute figures are in each company's reporting currency (TSM=TWD, SIVE=SEK, "
               "SOI=EUR); margins and growth are currency-neutral. Full analyst commentary "
               "is in your private daily brief.")
    frows = [financial_summary(conn, t) for t in TICKERS]
    frows = [f for f in frows if f]
    if frows:
        fdf = pd.DataFrame([{
            "Ticker": f["ticker"], "Qtr": f["period"][:7],
            "Revenue": fmt_mag(f["revenue"]), "Rev YoY %": f["rev_yoy"],
            "Gross %": f["gross_margin"], "Op %": f["op_margin"], "Net %": f["net_margin"],
            "FCF": fmt_mag(f["fcf"]) if f["fcf"] is not None else "—",
            "Net cash": fmt_mag(f["net_cash"]) if f["net_cash"] is not None else "—",
            "Shares YoY %": f["shares_yoy"],
        } for f in frows])
        st.dataframe(
            fdf.style.format({"Rev YoY %": "{:+.0f}", "Gross %": "{:.0f}", "Op %": "{:.0f}",
                              "Net %": "{:.0f}", "Shares YoY %": "{:+.1f}"}, na_rep="—")
            .map(lambda v: f"color: {DELTA_UP}" if isinstance(v, float) and v > 0
                 else (f"color: {DELTA_DOWN}" if isinstance(v, float) and v < 0 else ""),
                 subset=["Rev YoY %"])
            .map(lambda v: f"color: {DELTA_DOWN}" if isinstance(v, float) and v > 2 else "", subset=["Shares YoY %"]),
            width="stretch", hide_index=True, height=560)
        st.caption("Shares YoY highlighted red above +2% (dilution).")

        st.markdown("#### Revenue trend")
        ft = st.selectbox("Company", [f["ticker"] for f in frows], key="fin_ticker")
        qs = financials_q(conn, ft, limit=5)
        if qs:
            qdf = pd.DataFrame([{"period": q["period"], "revenue": q["revenue"]} for q in reversed(qs)])
            fig = go.Figure(go.Bar(x=qdf["period"], y=qdf["revenue"], marker_color=SLOTS[0], marker_line_width=0,
                                   hovertemplate="%{y:,.0f}<extra></extra>"))
            fig.update_layout(**layout(), height=300, yaxis_title="Revenue (reporting currency)")
            st.plotly_chart(fig, config={"displayModeBar": False})
    else:
        st.info("No financials stored yet — run run_daily.py.")

# ══════════════════════════════ SENTIMENT ══════════════════════════════
with tab_sentiment:
    st.subheader("Analyst consensus — upside to mean price target")
    ups = []
    for t in TICKERS:
        s = analyst_summary(conn, t)
        if s and s["target_mean"] and s["price"]:
            ups.append({"ticker": t, "upside": (s["target_mean"] / s["price"] - 1) * 100,
                        "price": s["price"], "target": s["target_mean"],
                        "buys": (s["strong_buy"] or 0) + (s["buy"] or 0),
                        "holds": s["hold"] or 0,
                        "sells": (s["sell"] or 0) + (s["strong_sell"] or 0)})
    if ups:
        udf = pd.DataFrame(ups).sort_values("upside")
        fig = go.Figure(go.Bar(
            x=udf["upside"], y=udf["ticker"], orientation="h",
            marker_color=[POS if v > 0 else NEG for v in udf["upside"]], marker_line_width=0,
            customdata=udf[["price", "target", "buys", "holds", "sells"]],
            hovertemplate=("%{y}: %{x:+.0f}% to mean target<br>price %{customdata[0]:.2f} → target "
                           "%{customdata[1]:.2f}<br>%{customdata[2]} buy / %{customdata[3]} hold / "
                           "%{customdata[4]} sell<extra></extra>"),
        ))
        fig.update_layout(**layout(hovermode="y"), height=80 + 30 * len(udf), showlegend=False,
                          xaxis_title="Implied % to consensus mean target")
        st.plotly_chart(fig, config={"displayModeBar": False})
        st.caption("Consensus targets lag price — read big positive gaps as either opportunity "
                   "or analysts not yet marked down, never as a forecast.")
    else:
        st.info("No analyst summaries stored yet — run run_daily.py.")

    col_a, col_s = st.columns(2)
    with col_a:
        st.markdown("#### 🎯 Analyst actions (30 days)")
        acts = recent_analyst_actions(conn, days=30)
        if acts:
            adf = pd.DataFrame([dict(r) for r in acts])
            adf["when"] = adf["date"].str[:10]
            adf["grade"] = adf.apply(
                lambda r: r["to_grade"] + (f" ← {r['from_grade']}" if r["from_grade"] else ""), axis=1)
            adf["target"] = adf.apply(
                lambda r: (f"{r['pt_prior']:.0f} → {r['pt_current']:.0f}"
                           if r["pt_prior"] and r["pt_current"]
                           else (f"{r['pt_current']:.0f}" if r["pt_current"] else "—")), axis=1)
            st.dataframe(adf[["when", "ticker", "firm", "action", "grade", "target"]].rename(columns={
                "when": "Date", "ticker": "Ticker", "firm": "Firm", "action": "Action",
                "grade": "Grade", "target": "Target"}), width="stretch", hide_index=True, height=360)
        else:
            st.write("None stored.")
    with col_s:
        st.markdown("#### 🩳 Short interest (latest settlement)")
        srows = []
        for t in TICKERS:
            si = latest_short_interest(conn, t)
            if si and si.get("shares_short"):
                srows.append({"Ticker": t, "As of": si["date"],
                              "% float": 100 * si["pct_float"] if si["pct_float"] is not None else None,
                              "Days to cover": si["ratio"], "MoM %": si["mom_pct"]})
        if srows:
            sdf = pd.DataFrame(srows).sort_values("% float", ascending=False)
            st.dataframe(
                sdf.style.format({"% float": "{:.1f}", "Days to cover": "{:.1f}", "MoM %": "{:+.0f}"}, na_rep="—")
                .map(lambda v: f"color: {DELTA_DOWN}" if isinstance(v, float) and v > 0
                     else (f"color: {DELTA_UP}" if isinstance(v, float) and v < 0 else ""), subset=["MoM %"]),
                width="stretch", hide_index=True, height=360)
            st.caption("Rising short interest colored red (pressure), falling green. FINRA settles bi-monthly.")
        else:
            st.write("No short data (US names only).")

    col_soc, col_g = st.columns(2)
    with col_soc:
        st.markdown("#### 💬 StockTwits skew (latest ~30-message sample)")
        socs = []
        for t in TICKERS:
            s = social_snapshot(conn, t)
            if s and s["tagged"]:
                socs.append({"ticker": t, "skew": (s["skew"] - 0.5) * 200,
                             "bull": s["bullish"], "bear": s["bearish"]})
        if socs:
            sdf = pd.DataFrame(socs).sort_values("skew")
            fig = go.Figure(go.Bar(
                x=sdf["skew"], y=sdf["ticker"], orientation="h",
                marker_color=[POS if v > 0 else NEG for v in sdf["skew"]], marker_line_width=0,
                customdata=sdf[["bull", "bear"]],
                hovertemplate="%{y}: %{customdata[0]}🐂 / %{customdata[1]}🐻<extra></extra>",
            ))
            fig.update_layout(
                **layout(hovermode="y",
                         xaxis=dict(title="← bearish · tagged-message skew · bullish →",
                                    range=[-100, 100])),
                height=80 + 28 * len(sdf), showlegend=False)
            st.plotly_chart(fig, config={"displayModeBar": False})
        else:
            st.write("No StockTwits samples stored yet.")
    with col_g:
        st.markdown("#### 📰 News volume vs weekly average (GDELT)")
        grows = []
        for t in TICKERS:
            g = gdelt_spike(conn, t)
            if g and g["ratio"] is not None:
                grows.append({"Ticker": t, "Day": g["date"], "Articles": g["volume"],
                              "vs week avg": g["ratio"], "Tone": g["tone"]})
        if grows:
            gdf = pd.DataFrame(grows).sort_values("vs week avg", ascending=False)
            st.dataframe(
                gdf.style.format({"Articles": "{:.0f}", "vs week avg": "{:.1f}x", "Tone": "{:+.1f}"}, na_rep="—"),
                width="stretch", hide_index=True, height=360)
            st.caption("Tone is GDELT's average sentiment score across articles (−10 very negative, +10 very positive).")
        else:
            st.write("No GDELT data stored yet (rate-limited source — accrues daily).")

    st.markdown("#### 🔎 Attention — Google Trends (weekly refresh, best-effort)")
    att_ticker = st.selectbox("Company", list(TICKERS),
                              format_func=lambda t: f"{t} — {TICKERS[t]['name']}", key="att")
    att = attention_series(conn, att_ticker)
    if att:
        atdf = pd.DataFrame([dict(r) for r in att])
        fig = go.Figure(go.Scatter(x=atdf["date"], y=atdf["score"],
                                   line=dict(width=2, color=SLOTS[0]),
                                   hovertemplate="%{y:.0f}<extra></extra>"))
        fig.update_layout(**layout(), height=240, yaxis_title="Search interest (0–100)")
        st.plotly_chart(fig, config={"displayModeBar": False})
    else:
        st.write("No Trends data for this name yet — Google throttles this source; it fills in weekly.")

# ══════════════════════════════ TRADE FLOWS ══════════════════════════════
with tab_trade:
    st.subheader("Semiconductor exports — UN Comtrade monthly")
    st.caption("Taiwan does not report to UN Comtrade; Korea/China/Japan/Netherlands are the "
               "available supply-chain proxies. Data lags 3–6 months — the signal is the trend.")
    hs = st.selectbox("Commodity", list(HS_CODES), format_func=lambda c: f"HS {c} — {HS_LABELS.get(c, HS_CODES[c])}")

    series = trade_flow_series(conn, hs)
    if series:
        sdf = pd.DataFrame([dict(r) for r in series])
        sdf["month"] = pd.to_datetime(sdf["period"], format="%Y%m")
        fig = go.Figure()
        for reporter in sorted(sdf["reporter"].unique()):
            sub = sdf[sdf["reporter"] == reporter]
            fig.add_trace(go.Scatter(
                x=sub["month"], y=sub["value_usd"] / 1e9, name=reporter,
                line=dict(width=2, color=REPORTER_COLORS.get(reporter, SLOTS[7])),
                hovertemplate="%{y:.2f}B USD<extra>" + reporter + "</extra>",
            ))
        fig.update_layout(**layout(), height=420, yaxis_title="Exports, $B/month",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, config={"displayModeBar": False})

        yoy = [t for t in trade_yoy(conn) if t["hs_code"] == hs]
        if yoy:
            ydf = pd.DataFrame(yoy)[["reporter", "period", "value", "yoy"]]
            ydf["value"] = ydf["value"] / 1e9
            ydf.columns = ["Reporter", "Latest month", "Exports $B", "YoY %"]
            st.dataframe(
                ydf.style.format({"Exports $B": "{:,.2f}", "YoY %": "{:+.0f}"}, na_rep="—")
                .map(lambda v: f"color: {DELTA_UP}" if isinstance(v, float) and v > 0
                     else (f"color: {DELTA_DOWN}" if isinstance(v, float) and v < 0 else ""), subset=["YoY %"]),
                width="stretch", hide_index=True,
            )
    else:
        st.info("No trade-flow data stored yet — run run_daily.py (Comtrade refreshes weekly).")

# ══════════════════════════════ ALERT HISTORY ══════════════════════════════
with tab_history:
    st.subheader("Alert history")
    hist = pd.read_sql_query(
        "SELECT run_ts, ticker, kind, message FROM alerts ORDER BY run_ts DESC", conn
    )
    if hist.empty:
        st.info("No alerts recorded yet — history accrues with each pipeline run.")
    else:
        hist["day"] = hist["run_ts"].str[:10]
        counts = hist.groupby(["day", "kind"]).size().reset_index(name="n")
        fig = go.Figure()
        for kind in sorted(counts["kind"].unique()):
            sub = counts[counts["kind"] == kind]
            fig.add_trace(go.Bar(x=sub["day"], y=sub["n"], name=kind,
                                 marker_color=ALERT_KIND_COLORS.get(kind, MUTED), marker_line_width=0))
        fig.update_layout(**layout(), barmode="stack", height=260,
                          bargap=0.4, legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, config={"displayModeBar": False})

        kinds = st.multiselect("Filter by kind", sorted(hist["kind"].unique()))
        view = hist[hist["kind"].isin(kinds)] if kinds else hist
        # strip markdown bold for table display
        view = view.assign(message=view["message"].str.replace("**", "", regex=False))
        st.dataframe(view[["day", "ticker", "kind", "message"]].rename(
            columns={"day": "Date", "ticker": "Ticker", "kind": "Kind", "message": "Alert"}),
            width="stretch", hide_index=True, height=400)

# ══════════════════════════════ ABOUT ══════════════════════════════
with tab_about:
    from pathlib import Path
    about = Path(__file__).parent / "ABOUT.md"
    if about.exists():
        st.markdown(about.read_text())
    else:
        st.info("ABOUT.md not found.")
