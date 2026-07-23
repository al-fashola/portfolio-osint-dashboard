# Reading this dashboard — the About pack

*Why each piece exists, what it signals, and what it deliberately does not tell you.*

---

## The idea

This tracker is built on one premise, borrowed from how professional OSINT shops
(like SemiAnalysis's ChipBook) operate: **public signals move before the narrative
does.** Insider filings, export statistics, filing patterns, and volume anomalies
are all public — the edge isn't secret data, it's *watching systematically* and
noticing **change**. Every table in the database exists to answer one question:
*what changed since yesterday?*

The second premise: **a signal is an attention trigger, not an instruction.**
Nothing here says buy or sell. Signals tell you *where to look today*; what you do
with that depends on your thesis for the position (see "Theses" below).

---

## The signals, and how to read them

### ▲▼ Price move ≥ ±3% (1 day)
The crudest but most immediate trigger. A 3% single-session move in a liquid name
means *something* repriced. **Read it with the volume signal**: a big move on quiet
volume often fades; a big move on heavy volume has participation behind it.

### 📊 Volume ≥ 2× its 30-day average
Volume is conviction. The most interesting version is **volume without price** —
heavy turnover on a flat day can mean accumulation or distribution, and often
precedes the move. When both fire together (like AEHR's +22% on 5.9× volume, July 14),
the event is real; the question becomes whether it's fully priced.

### 📄 Material SEC filing (last 7 days)
- **8-K** — "something happened": an acquisition, an executive change, a material
  contract, restated guidance. Always worth opening; the filing itself says what.
- **10-K / 10-Q** — the quarterly/annual report. The alpha is rarely the numbers
  (already covered by earnings); it's **changes in the risk-factor language**.
- **S-1 / 424B5** — shelf registrations and offerings. This is *dilution*: the
  company is selling shares. Frequent 424B5s (TeraWulf-style names live on them)
  mean your ownership share is shrinking.
- **6-K / 20-F** — the foreign-issuer equivalents (TSM files these).

### 💰👤 Insider transactions (parsed Form 4s)
The most misread public signal, which is why this dashboard **parses the XML**
rather than counting filings:
- **Open-market buys (code P) are rare and load-bearing.** Insiders sell for a
  hundred reasons (taxes, diversification, divorce); they buy on the open market
  for one. Any P transaction alerts, at any size. Across your whole portfolio,
  90 days of filings produced exactly *one* US-listed P (an AVGO director, $373k)
  plus a cluster of small TSM buys before earnings — that scarcity is the point.
- **Sells alert only above $10M aggregate** because routine RSU-vest-and-sell
  programs would otherwise drown you. Codes A (award), M (exercise), F (tax
  withholding), G (gift) are excluded from alerts entirely — they're compensation
  mechanics, not opinions.
- **Clusters beat singles.** Three executives buying the same week is a signal;
  one is an anecdote. Watch the *title* column: a CFO or CEO trade outweighs a
  director's.

### 📅 Earnings within 7 days
Not a prediction — a **volatility calendar**. Implied vol rises into the print;
moves after it are structurally larger. If a position is oversized, the window
before earnings is when that matters. The estimate shown is the consensus the
market will judge the print against.

### 🎯 Analyst actions (upgrades / downgrades / target moves)
Alerts fire on any upgrade/downgrade in the last 7 days, and on price-target
changes ≥10%. Two honest caveats: analysts **herd** (revisions cluster after
moves, not before), and consensus targets **lag** — a huge "upside to target"
gap often means analysts haven't marked down yet, not that the stock is cheap.
The revision *direction and clustering* is the signal; the target level is
almost never.

### 🩳 Short interest (FINRA bi-monthly)
Alerts on a ≥20% month-over-month change, or any name with ≥15% of float short.
Rising short interest is borrowed-money conviction against you — take the bear
case seriously enough to name it. But high short interest cuts both ways:
**days-to-cover** is squeeze fuel if good news lands. Data settles bi-monthly,
so this moves slowly by nature.

### 💬 StockTwits skew
A daily ~30-message sample per ticker; users self-tag Bullish/Bearish. Alerts
only when the sample is both **big enough** (≥8 tagged) and **extreme** (≥85%
one way). Retail sentiment is mostly a *contrarian* or *crowding* indicator —
a 95%-bullish board after a run-up is a warning about positioning, not
confirmation. Treat it as "who's on this trade," never as research.

### 📰 GDELT news volume & tone
Counts English-language articles worldwide mentioning the company and averages
their tone (−10…+10). Alerts when yesterday's volume ran ≥3× the weekly
average — that's "the narrative is moving," often *before* the story reaches
your usual feeds. Volume spikes matter more than tone; tone matters most when
it *diverges* from price (price up, tone collapsing = check why).

### 🔎 Google Trends attention
Search interest, 0–100, weekly refresh. Retail attention proxy: spikes
coincide with tops more often than bottoms. This source is best-effort —
Google throttles unofficial access, so gaps are expected and it degrades
silently rather than blocking the pipeline.

### 🏦 Institutional holders (13F via Yahoo)
Quarterly top-10 holders per name with QoQ position change, shown in Company
detail. 13Fs lag by up to 45 days after quarter-end — this is *confirmation*
data ("who accumulated last quarter"), never timing data.

### 🎤 Industry events & conferences
A curated calendar of semiconductor/AI events that move the watchlist through
product launches, roadmap disclosures, or competitive read-through — kept in
`conferences.json` and refreshed by the morning routine (dates verified,
anticipated announcements updated, new events added via web search). Each event
lists which of *your* names it touches and what to watch for. An alert fires
when a relevant event is within 14 days. The optics events (ECOC, OFC, GTC's
CPO track) are the ones that matter most for the small-caps — Sivers and Soitec
progress often surfaces there before it hits a filing. Read a conference as a
*scheduled volatility window*, like earnings: it tells you when to pay
attention, not what will happen.

### 🌍 Macro & market considerations
Your holdings don't trade in a vacuum — the macro strip (S&P, Nasdaq, SOX
semiconductor index, VIX, 10Y yield, USD/KRW) answers "is today's move my
stock or the whole market?" before you over-read any single alert. The SOX
index is the beta for most of the list; USD/KRW matters for EWY's translation;
VIX ≥ 30 alerts because gap risk in the small caps explodes in stressed
regimes. Macro headlines (Fed, export controls, tariffs, AI capex) proxy the
@DeItaone-style headline flow that X keeps behind login.

### 🚢 Comtrade export flows ± 30% YoY
The ChipBook-style upstream signal. Monthly customs data for:
- **HS 8542 (integrated circuits)** — broad chip demand.
- **HS 854232 (memory ICs)** — *the* cycle signal. Korea's memory exports are a
  direct read on the DRAM/NAND cycle (relevant to EWY and the whole complex).
- **HS 8486 (semi manufacturing equipment)** — capex: relevant to the equipment
  chain (Aehr, LPKF, and the fabs that buy from them).

Caveats built into the design: **Taiwan doesn't report to UN Comtrade** (Korea,
China, Japan, Netherlands are the available proxies), and data lags 3–6 months —
each country's line simply stops at its last reported month. The signal is the
*trend and the YoY rate*, never freshness.

### ⚖️ Asymmetry — the risk-reward discipline field

> **Asymmetry = (Bull value − Current price) ÷ (Current price − Bear value)**

You define two numbers per ticker in `valuations.json`: what the company is
worth in the best *realistic* scenario (bull) and the worst *realistic*
scenario (bear). The pipeline recomputes asymmetry daily against the latest
close — it appears in the snapshot table, the Overview range chart, the digest,
and fires alerts when it crosses your bars (≥3 attractive for high-risk growth,
<1 downside-exceeds-upside, both in `config.py`).

Why the bear case is the whole model:
- It measures **how much capital is actually at risk** — the denominator.
- A 100% potential gain means little against a realistic 70% loss.
- Writing it down forces you to argue the strongest case *against* yourself.

How the machine treats the edges, deliberately:
- **Price at/below your bear case** → no number, an alert instead. The formula
  breaking down is information: either the market found a scenario worse than
  your "worst realistic," or the opportunity got dramatically better. Only
  re-examining the thesis says which — recalculating doesn't.
- **Price at/above your bull case** → asymmetry 0. Upside exhausted per your
  own model; drifting your bull value up *after* a run is the failure mode
  this field exists to prevent.
- **Base case is absent on purpose** — asymmetry only weighs the two extremes.
- The **street asym** column (analyst high/low targets) is a mechanical
  reference so the field is never empty, but analyst extremes are herded and
  lagged — they are not honest scenario work, and the model is only as good
  as the honesty of its inputs.

The discipline half you can't automate: set the numbers *before* the market
tests them, update them only on new fundamental information (never on price),
and act when the field tells you what you don't want to hear.

---

## Why these five tabs

| Tab | Job | The question it answers |
|---|---|---|
| **📊 Overview** | Morning triage | *What needs my attention today?* Alerts first, snapshot table, the 1-day move chart (blue = up, red = down), earnings coming, and every material filing in one feed. |
| **🏢 Company detail** | The drill-down | *OK, why?* Price/volume history, that name's insider tape, filings, and headlines in one place, so you never investigate a mover from five browser tabs. |
| **👤 Insiders** | Who's voting with their wallets | *Across everything I own, where is real insider money moving?* The net buy/sell chart makes 90 days of Form 4s legible in one glance. |
| **🧠 Sentiment** | What the crowd thinks | *Where do analysts, shorts, retail, and the news cycle stand on my names?* Consensus upside, revisions, short interest, StockTwits skew, GDELT narrative volume, and search attention — the positioning picture around each stock. |
| **🚢 Trade flows** | Cycle context | *Is the upstream tide rising or falling under my semi names?* Slow-moving by design — check weekly, not daily. |
| **🕘 Alert history** | Pattern memory | *Do these alerts actually precede moves?* Alerts are persisted every run, so over months you can audit which signal types earned attention and recalibrate thresholds in `config.py`. |

The design system choice worth knowing: **blue/red replaces green/red** for
up/down everywhere marks are colored (charts). It's deliberate — red/green is
the most common form of colorblindness, and blue↔red survives it.

---

## Theses — the "does this break my view?" layer

A signal only means something relative to **why you own the position**. The
`theses/` folder holds one markdown file per ticker stating: what you believe,
what would strengthen it, and — most important — **what evidence would falsify
it**. The daily scheduled run reads today's digest against those files and flags
each thesis as *intact / challenged / broken-watch*, citing the specific evidence.

Writing the falsifiers **before** the evidence arrives is the entire value: it
keeps future-you from rationalizing. Copy `theses/_TEMPLATE.md` per ticker.

---

## What this tracker does NOT do

- **No buy/sell recommendations.** It surfaces evidence; the decision framework
  (thesis files) is yours. Nothing here is investment advice.
- **No intraday anything.** Prices are daily closes; one honest look per day.
- **Sentiment is context, not signal-of-record.** The sentiment sources
  (StockTwits, GDELT, Trends) are noisy, sampled, and throttled by their
  providers; they earn attention only when several agree or one is extreme.
- **Leveraged-ETP awareness**: SPCH is a *2× daily-reset* product on SPCX.
  Daily reset means it decays in choppy markets even if the underlying round-trips
  — its 5-day return can diverge badly from 2× SPCX's. Treat its price alerts as
  amplified SPCX noise; the real signal for it lives in SPCX's own row.

## Glossary

**Form 4 codes**: P open-market buy · S open-market sale · A award/grant ·
M option exercise · F shares withheld for tax · G gift · C conversion ·
D disposition to issuer.
**HS codes**: harmonized-system customs categories (8542 ICs · 854232 memory ·
8486 semi equipment).
**Vol/30d**: yesterday's volume ÷ its trailing 30-session average.
**YoY**: latest reported month vs the same month one year earlier.
