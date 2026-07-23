# Portfolio OSINT — Dashboard (deploy mirror)

Hosted Streamlit dashboard for the Portfolio OSINT tracker. This is a **deploy
mirror**: it contains only the dashboard code + a snapshot of `data.sqlite`
(public-source market data). It deliberately excludes the owner's private
analysis — `theses/`, `valuations.json`, and daily digests live only in the
private source repo. Bull/bear scenario values are injected at runtime via a
Streamlit secret (`valuations_json`), never stored here.

Data is refreshed by the owner's pipeline pushing an updated `data.sqlite`.
