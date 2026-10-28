from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

SOURCE_URL = "https://www.icco.org/statistics/"
SERIES = {
    "ICCO daily price (USD/tonne)": ("iccodailypriceustonne", "$", "USD per metric tonne"),
    "New York futures (USD/tonne)": ("newyorkfuturesustonne", "$", "USD per metric tonne"),
    "London futures (GBP/tonne)": ("prueba", "£", "GBP per metric tonne"),
    "ICCO daily price (EUR/tonne)": ("iccodailypriceeurotonne", "€", "EUR per metric tonne"),
}
BENCHMARK = "iccodailypriceustonne"


class PageInputs(HTMLParser):
    """Read the public table configuration and request token from ICCO's page."""
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and "id" in attrs:
            self.values[attrs["id"]] = attrs.get("value", "")


def table_configuration(html):
    page = PageInputs()
    page.feed(html)
    for key, value in page.values.items():
        if not key.endswith("_desc"):
            continue
        try:
            config = json.loads(value)
            columns = config["dataTableParams"]["columnDefs"]
        except (ValueError, KeyError, TypeError):
            continue
        names = {column["name"] for column in columns}
        if {"date", BENCHMARK}.issubset(names):
            table_id = int(config["tableWpId"])
            nonce = page.values.get(f"wdtNonceFrontendServerSide_{table_id}")
            if not nonce:
                raise ValueError("ICCO's public table token was not found. Try refreshing later.")
            return table_id, columns, nonce
    raise ValueError("ICCO's daily price table was not found. Its page layout may have changed.")


def parse_prices(payload, columns):
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("ICCO returned no daily price rows.")
    expected = payload.get("recordsFiltered")
    if expected is not None and int(expected) > len(rows):
        raise ValueError("ICCO returned only part of the table. The history needs checking.")
    positions = {c["name"]: int(c["aTargets"][0]) for c in columns}
    needed = ["date"] + [spec[0] for spec in SERIES.values()]
    if not set(needed).issubset(positions):
        raise ValueError("ICCO's price columns have changed.")
    frame = pd.DataFrame({name: [row[positions[name]] for row in rows] for name in needed})
    frame["date"] = pd.to_datetime(frame["date"], format="%d/%m/%Y", errors="coerce")
    for name in needed[1:]:
        frame[name] = pd.to_numeric(
            frame[name].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
        frame.loc[frame[name] <= 0, name] = float("nan")
    frame = frame.dropna(subset=["date"]).dropna(subset=needed[1:], how="all")
    frame = frame.drop_duplicates("date", keep="first").set_index("date").sort_index()
    frame.index.name = "Date"
    if len(frame[BENCHMARK].dropna()) < 2:
        raise ValueError("ICCO returned fewer than two valid benchmark prices.")
    return frame


def fetch_icco():
    headers = {"User-Agent": "CommodityDashboard/1.0", "Referer": SOURCE_URL}
    with urlopen(Request(SOURCE_URL, headers=headers), timeout=30) as response:
        html = response.read().decode("utf-8")
    table_id, columns, nonce = table_configuration(html)
    positions = {c["name"]: int(c["aTargets"][0]) for c in columns}
    # Same read-only table request as the public page's "All" option.
    params = {
        "draw": 1, "start": 0, "length": -1,
        "order[0][column]": positions["date"], "order[0][dir]": "desc",
        "search[value]": "", "search[regex]": "false", "wdtNonce": nonce,
    }
    for column in columns:
        index = int(column["aTargets"][0])
        values = {
            "data": index, "name": column["name"], "searchable": "true",
            "orderable": "true", "search[value]": "", "search[regex]": "false",
        }
        for key, value in values.items():
            params[f"columns[{index}][{key}]"] = value
    endpoint = f"https://www.icco.org/wp-admin/admin-ajax.php?action=get_wdtable&table_id={table_id}"
    request = Request(endpoint, data=urlencode(params).encode("utf-8"), headers=headers)
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return parse_prices(payload, columns), datetime.now(timezone.utc)


st.set_page_config(page_title="Commodity Dashboard", page_icon="📊", layout="wide")
st.title("Commodity Dashboard")
st.caption("Latest available commodity prices and trends · Free public data")


@st.cache_data(ttl=3600, show_spinner=False)
def load_cocoa():
    return fetch_icco()


if st.button("Refresh ICCO data"):
    load_cocoa.clear()

prices = None
fetched_at = None
try:
    with st.spinner("Checking ICCO cocoa prices…"):
        prices, fetched_at = load_cocoa()
    st.session_state["last_icco_daily"] = (prices, fetched_at)
except Exception as error:
    if "last_icco_daily" in st.session_state:
        prices, fetched_at = st.session_state["last_icco_daily"]
        st.warning("Refresh failed. Showing the last successful ICCO data from this session.")
    else:
        st.warning("ICCO data is temporarily unavailable. Please try refreshing later.")
    with st.expander("Connection details"):
        st.text(str(error))

selection = st.selectbox("Price series", list(SERIES), key="cocoa_price_series")
name, symbol, unit = SERIES[selection]
values = prices[name].dropna() if prices is not None else pd.Series(dtype=float)

commodities = [
    f"Cocoa — {selection}", "Raw sugar futures", "White sugar futures",
    "Crude palm oil futures", "GDT Whole Milk Powder", "GDT Skim Milk Powder",
]
for start in range(0, len(commodities), 3):
    columns = st.columns(3)
    for column, commodity in zip(columns, commodities[start:start + 3]):
        with column:
            if commodity == commodities[0] and not values.empty:
                latest = float(values.iloc[-1])
                delta = None
                if len(values) >= 2:
                    previous = float(values.iloc[-2])
                    change = (latest / previous - 1) * 100
                    delta = f"{change:+.2f}%"
                st.metric(commodity, f"{symbol}{latest:,.2f}/tonne", delta, delta_color="inverse")
                st.caption(f"Observation: {values.index[-1]:%d %b %Y}")
            else:
                st.metric(commodity, "—")
                st.caption("Awaiting data" if commodity == commodities[0] else "Not connected yet")

st.divider()
st.subheader("Cocoa price trend")
st.markdown(f"Source: [International Cocoa Organization (ICCO)]({SOURCE_URL})")
st.caption("The cocoa card and chart show the selected price series. ICCO's daily benchmark combines the nearest three active futures months in London and New York. These are cocoa bean prices, not cocoa powder prices.")

if prices is not None:
    if values.empty:
        st.info("No valid observations were returned for this series.")
    else:
        period = st.selectbox("Chart period", ["3 months", "6 months", "12 months", "All available"], index=2)
        if period == "All available":
            visible = values
        else:
            months = {"3 months": 3, "6 months": 6, "12 months": 12}[period]
            visible = values.loc[values.index >= values.index[-1] - pd.DateOffset(months=months)]
        st.caption(f"Selected series: {symbol}{values.iloc[-1]:,.2f}/tonne · Latest observation: {values.index[-1]:%d %b %Y}")
        st.line_chart(visible.to_frame(name=unit), y_label=unit)
        st.caption(f"Displayed history: {visible.index[0]:%d %b %Y} to {visible.index[-1]:%d %b %Y} · {len(visible):,} observations")
        if (pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - values.index[-1]).days > 7:
            st.warning("The latest observation is more than seven days old. Check ICCO's source page for newer publications.")
        with st.expander("View daily price history"):
            table = prices.loc[visible.index].rename(columns={spec[0]: label for label, spec in SERIES.items()})
            st.dataframe(table.sort_index(ascending=False))
            st.download_button("Download displayed history (CSV)", table.to_csv().encode("utf-8-sig"), "icco_cocoa_prices.csv", "text/csv")
    st.caption(f"Last successful retrieval: {fetched_at:%d %b %Y, %H:%M} UTC. Cached for up to one hour; use Refresh to check again.")
else:
    st.info("The chart will appear when the first successful ICCO download completes.")

st.caption("Changes compare the latest two available observations. ICCO publishes trading-day data; missing prices are left blank. London is quoted in GBP, New York in USD, and the ICCO benchmark is available in USD and EUR.")
with st.expander("How ICCO calculates its benchmark"):
    st.write("ICCO averages quotations for the nearest three active futures trading months on ICE Futures Europe (London) and ICE Futures US (New York) at London close. London quotations are converted to US dollars using the six-month forward exchange rate. The active-month selection rolls on ICCO's published schedule.")

