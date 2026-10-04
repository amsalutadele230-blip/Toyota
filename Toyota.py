"""
Auto Sales Dashboard (Streamlit + Plotly), built for Auto_Sales_data.csv

Install:
    pip install streamlit pandas plotly

Run (put Auto_Sales_data.csv in the same folder):
    streamlit run auto_sales_dashboard.py

Data notes (checked against your file):
  * ORDERDATE is day/month/year (24/02/2018), so it is parsed with dayfirst.
  * The data covers Jan 2018 to 31 May 2020. 2020 is only 5 months, so
    year-vs-year totals would be misleading. The dashboard therefore also
    shows a like-for-like Jan-May comparison.
  * One row = one order line. Orders are counted with unique ORDERNUMBER.
"""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
CSV_PATH = Path(__file__).with_name("Auto_Sales_data.csv")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

st.set_page_config(page_title="Auto Sales Dashboard", page_icon="🚗", layout="wide")


# ------------------------------------------------------------------
# DATA
# ------------------------------------------------------------------
@st.cache_data
def load_data(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    df["ORDERDATE"] = pd.to_datetime(df["ORDERDATE"], format="%d/%m/%Y")
    df["year"] = df["ORDERDATE"].dt.year
    df["month"] = df["ORDERDATE"].dt.month
    df["year_month"] = df["ORDERDATE"].dt.to_period("M").dt.to_timestamp()
    df["quarter"] = df["ORDERDATE"].dt.to_period("Q").astype(str)
    return df


# --- Option: load from MySQL instead of the CSV -------------------
# pip install sqlalchemy pymysql, then replace load_data(...) below with:
#
# from sqlalchemy import create_engine
# engine = create_engine("mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME")
# raw = pd.read_sql("SELECT * FROM auto_sales", engine)
# raw.to_csv("Auto_Sales_data.csv", index=False)   # or adapt load_data to take a DataFrame
# -------------------------------------------------------------------

if CSV_PATH.exists():
    df = load_data(CSV_PATH)
else:
    up = st.sidebar.file_uploader("Upload Auto_Sales_data.csv", type="csv")
    if up is None:
        st.info("Place Auto_Sales_data.csv next to this script, or upload it in the sidebar.")
        st.stop()
    df = load_data(up)

# ------------------------------------------------------------------
# FILTERS
# ------------------------------------------------------------------
st.sidebar.header("Filters")


def multi(label, col):
    opts = sorted(df[col].unique())
    return st.sidebar.multiselect(label, opts, default=opts)


years = multi("Year", "year")
lines = multi("Product line", "PRODUCTLINE")
countries = multi("Country", "COUNTRY")
statuses = multi("Order status", "STATUS")
sizes = multi("Deal size", "DEALSIZE")

f = df[
    df["year"].isin(years)
    & df["PRODUCTLINE"].isin(lines)
    & df["COUNTRY"].isin(countries)
    & df["STATUS"].isin(statuses)
    & df["DEALSIZE"].isin(sizes)
]

st.title("🚗 Auto Sales Dashboard")
if f.empty:
    st.warning("No data for the selected filters.")
    st.stop()

st.caption(f"Data range: {f['ORDERDATE'].min():%d %b %Y} to {f['ORDERDATE'].max():%d %b %Y}")

# ------------------------------------------------------------------
# KPIs
# ------------------------------------------------------------------
orders = f["ORDERNUMBER"].nunique()
total_sales = f["SALES"].sum()
units = int(f["QUANTITYORDERED"].sum())

# Like-for-like window: months present in the latest selected year
last_year = int(f["year"].max())
cutoff = int(f.loc[f["year"] == last_year, "month"].max())
lfl = f[f["month"] <= cutoff].groupby("year")["SALES"].sum().sort_index()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Sales", f"${total_sales:,.0f}")
k2.metric("Orders", f"{orders:,}")
k3.metric("Units Sold", f"{units:,}")
k4.metric("Avg Order Value", f"${total_sales / orders:,.0f}")
if len(lfl) >= 2:
    prev, curr = lfl.iloc[-2], lfl.iloc[-1]
    k5.metric(
        f"{last_year} vs {lfl.index[-2]} (Jan-{MONTHS[cutoff - 1]})",
        f"${curr:,.0f}",
        f"{(curr / prev - 1) * 100:+.1f}%",
    )
else:
    k5.metric("Customers", f["CUSTOMERNAME"].nunique())

st.divider()

# ------------------------------------------------------------------
# TRENDS
# ------------------------------------------------------------------
c1, c2 = st.columns((2, 1))

monthly = f.groupby("year_month", as_index=False)["SALES"].sum()
c1.subheader("Monthly Sales")
c1.plotly_chart(
    px.line(monthly, x="year_month", y="SALES", markers=True, labels={"year_month": "", "SALES": "Sales ($)"}),
    use_container_width=True,
)

c2.subheader(f"Like-for-like: Jan-{MONTHS[cutoff - 1]} by Year")
lfl_df = lfl.reset_index()
fig = px.bar(lfl_df, x="year", y="SALES", text_auto=".3s", labels={"year": "", "SALES": "Sales ($)"})
fig.update_xaxes(type="category")
c2.plotly_chart(fig, use_container_width=True)
c2.caption("Same months in every year, so the partial 2020 is compared fairly.")

# Seasonality
c3, c4 = st.columns(2)
season = f.pivot_table(index="year", columns="month", values="SALES", aggfunc="sum").reindex(columns=range(1, 13))
season.columns = MONTHS
c3.subheader("Seasonality Heatmap (Sales)")
c3.plotly_chart(
    px.imshow(season, aspect="auto", color_continuous_scale="Blues", labels={"color": "Sales ($)"}),
    use_container_width=True,
)

quarterly = f.groupby("quarter", as_index=False)["SALES"].sum()
c4.subheader("Quarterly Sales")
c4.plotly_chart(px.bar(quarterly, x="quarter", y="SALES", labels={"quarter": "", "SALES": "Sales ($)"}),
                use_container_width=True)

# ------------------------------------------------------------------
# PRODUCT, GEOGRAPHY, CUSTOMERS
# ------------------------------------------------------------------
c5, c6 = st.columns(2)

by_line = f.groupby("PRODUCTLINE", as_index=False)["SALES"].sum().sort_values("SALES")
c5.subheader("Sales by Product Line")
c5.plotly_chart(
    px.bar(by_line, x="SALES", y="PRODUCTLINE", orientation="h", text_auto=".3s",
           labels={"SALES": "Sales ($)", "PRODUCTLINE": ""}),
    use_container_width=True,
)

by_country = f.groupby("COUNTRY", as_index=False)["SALES"].sum().sort_values("SALES", ascending=False)
c6.subheader("Top 10 Countries")
c6.plotly_chart(
    px.bar(by_country.head(10), x="COUNTRY", y="SALES", text_auto=".3s",
           labels={"SALES": "Sales ($)", "COUNTRY": ""}),
    use_container_width=True,
)

st.subheader("Sales Map")
map_df = by_country.assign(COUNTRY=by_country["COUNTRY"].replace({"UK": "United Kingdom"}))
st.plotly_chart(
    px.choropleth(map_df, locations="COUNTRY", locationmode="country names", color="SALES",
                  color_continuous_scale="Blues", labels={"SALES": "Sales ($)"}),
    use_container_width=True,
)

c7, c8 = st.columns(2)

top_cust = (
    f.groupby("CUSTOMERNAME", as_index=False)["SALES"].sum().sort_values("SALES", ascending=False).head(10)
)
c7.subheader("Top 10 Customers")
c7.plotly_chart(
    px.bar(top_cust, x="SALES", y="CUSTOMERNAME", orientation="h", text_auto=".3s",
           labels={"SALES": "Sales ($)", "CUSTOMERNAME": ""}).update_yaxes(autorange="reversed"),
    use_container_width=True,
)

c8.subheader("Deal Size Mix")
deal = f.groupby("DEALSIZE", as_index=False)["SALES"].sum()
c8.plotly_chart(px.pie(deal, names="DEALSIZE", values="SALES", hole=0.45), use_container_width=True)

# ------------------------------------------------------------------
# ORDER STATUS + PRODUCT LINE OVER TIME
# ------------------------------------------------------------------
c9, c10 = st.columns(2)

status = f.groupby("STATUS", as_index=False).agg(orders=("ORDERNUMBER", "nunique"), sales=("SALES", "sum"))
c9.subheader("Orders by Status")
c9.plotly_chart(px.bar(status, x="STATUS", y="orders", text_auto=True, labels={"STATUS": "", "orders": "Orders"}),
                use_container_width=True)

line_year = f.groupby(["year", "PRODUCTLINE"], as_index=False)["SALES"].sum()
c10.subheader("Product Line by Year")
fig = px.bar(line_year, x="year", y="SALES", color="PRODUCTLINE", labels={"year": "", "SALES": "Sales ($)"})
fig.update_xaxes(type="category")
c10.plotly_chart(fig, use_container_width=True)
