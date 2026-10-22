import streamlit as st

st.set_page_config(
    page_title="Commodity Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("Commodity Dashboard")
st.caption("Your daily view of commodity prices and trends.")

st.info(
    "The dashboard layout is ready. Prices are not connected yet, "
    "so the dashes below are placeholders."
)

commodities = [
    "Cocoa futures — beans",
    "Raw sugar futures",
    "White sugar futures",
    "Crude palm oil futures",
    "GDT Whole Milk Powder",
    "GDT Skim Milk Powder",
]

for start in range(0, len(commodities), 3):
    columns = st.columns(3)
    for column, commodity in zip(columns, commodities[start:start + 3]):
        with column:
            st.metric(label=commodity, value="—")

st.divider()
st.caption(
    "We will add price history and trend charts next. "
    "Each commodity will show the date of its latest available price."
)
