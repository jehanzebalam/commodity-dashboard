from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Commodity Dashboard", page_icon="📊", layout="wide")
st.title("Commodity Dashboard")
st.caption("Latest available commodity prices and trends · Free data sources")


@st.cache_data(ttl=3600, show_spinner=False)
def load_cocoa():
    history = yf.Ticker("CC=F").history(
        period="1y", interval="1d", auto_adjust=False,
        actions=False, timeout=20, raise_errors=True,
    )
    if history.empty or "Close" not in history.columns:
        raise ValueError("The source returned no cocoa prices.")
    prices = history[["Close"]].dropna().sort_index()
    prices = prices[prices["Close"] > 0]
    if len(prices) < 2:
        raise ValueError("At least two observations are needed.")
    # Preserve the exchange calendar date when removing the timezone.
    if prices.index.tz is not None:
        prices.index = prices.index.tz_localize(None)
    prices = prices[~prices.index.duplicated(keep="last")]
    prices.index.name = "Date"
    return prices, datetime.now(timezone.utc)


if st.button("Refresh cocoa data"):
    load_cocoa.clear()

prices = None
fetched_at = None
try:
    with st.spinner("Checking cocoa prices…"):
        prices, fetched_at = load_cocoa()
    st.session_state["last_cocoa"] = (prices, fetched_at)
except Exception as error:
    if "last_cocoa" in st.session_state:
        prices, fetched_at = st.session_state["last_cocoa"]
        st.warning("Refresh failed. Showing the last successful data from this session.")
    else:
        st.warning("Cocoa data is temporarily unavailable. Please try refreshing later.")
    with st.expander("Connection details"):
        st.text(str(error))

commodities = [
    "Cocoa futures — beans", "Raw sugar futures", "White sugar futures",
    "Crude palm oil futures", "GDT Whole Milk Powder", "GDT Skim Milk Powder",
]
for start in range(0, len(commodities), 3):
    columns = st.columns(3)
    for column, commodity in zip(columns, commodities[start:start + 3]):
        with column:
            if commodity == commodities[0] and prices is not None:
                latest = float(prices["Close"].iloc[-1])
                previous = float(prices["Close"].iloc[-2])
                change = (latest / previous - 1) * 100
                st.metric(commodity, f"${latest:,.0f}/tonne", f"{change:+.2f}%", delta_color="inverse")
                st.caption(f"Observation: {prices.index[-1]:%d %b %Y}")
            else:
                st.metric(commodity, "—")
                st.caption("Awaiting data" if commodity == commodities[0] else "Not connected yet")

st.divider()
st.subheader("Cocoa price trend")
st.markdown("Source: [Yahoo Finance — CC=F](https://finance.yahoo.com/quote/CC%3DF/history/) · ICE cocoa futures · USD per metric tonne")

if prices is not None:
    period = st.selectbox("Chart period", ["3 months", "6 months", "12 months"], index=1)
    months = {"3 months": 3, "6 months": 6, "12 months": 12}[period]
    cutoff = prices.index[-1] - pd.DateOffset(months=months)
    chart = prices.loc[prices.index >= cutoff].rename(columns={"Close": "USD/tonne"})
    st.line_chart(chart, y_label="USD per metric tonne")
    st.caption(f"Data retrieved: {fetched_at:%d %b %Y, %H:%M} UTC. Cached for up to one hour; use Refresh to check again.")
    st.caption("Daily observations from Yahoo's Close field; the current session's value may still change. The percentage compares the latest two available observations.")
    with st.expander("View price history"):
        st.dataframe(chart.sort_index(ascending=False))
    st.download_button("Download displayed prices (CSV)", chart.to_csv().encode("utf-8"), "cocoa_prices.csv", "text/csv")
else:
    st.info("The chart will appear when the first successful price download completes.")

st.caption("Cocoa futures track beans, not powder. CC=F switches contract months over time, so some chart movements can reflect a contract change.")
