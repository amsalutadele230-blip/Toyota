"""
Sales Dashboard (Streamlit + Plotly), built for Auto Sales data
Supports direct connection to MySQL Database or CSV file.

Install requirements:
    py -m pip install -r requirements.txt

Run dashboard:
    py -m streamlit run Toyota.py
"""
import json
from pathlib import Path
import urllib.parse

import pandas as pd
import plotly.express as px
import streamlit as st

# Safe import of database drivers
try:
    from sqlalchemy import create_engine, text
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

# File paths
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH_SPACE = BASE_DIR / "Auto Sales data.csv"
CSV_PATH_UNDERSCORE = BASE_DIR / "Auto_Sales_data.csv"
CSV_PATH = CSV_PATH_SPACE if CSV_PATH_SPACE.exists() else CSV_PATH_UNDERSCORE
CONFIG_PATH = BASE_DIR / "db_config.json"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

st.set_page_config(page_title="Auto Sales Dashboard", page_icon="🚗", layout="wide")


# ------------------------------------------------------------------
# HELPERS & DATA PREPARATION
# ------------------------------------------------------------------
def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize date and period columns regardless of source."""
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["ORDERDATE"]):
        df["ORDERDATE"] = pd.to_datetime(df["ORDERDATE"], dayfirst=True, errors="coerce")
    else:
        df["ORDERDATE"] = pd.to_datetime(df["ORDERDATE"])

    df["year"] = df["ORDERDATE"].dt.year
    df["month"] = df["ORDERDATE"].dt.month
    df["year_month"] = df["ORDERDATE"].dt.to_period("M").dt.to_timestamp()
    df["quarter"] = df["ORDERDATE"].dt.to_period("Q").astype(str)
    return df


@st.cache_data
def load_csv_data(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    return prepare_dataframe(df)


def get_db_engine(user, password, host, port, dbname=None):
    safe_password = urllib.parse.quote_plus(password)
    db_part = f"/{dbname}" if dbname else ""
    url = f"mysql+pymysql://{user}:{safe_password}@{host}:{port}{db_part}?charset=utf8mb4&connect_timeout=4"
    return create_engine(url)


def load_db_config():
    # 1. Check Streamlit Cloud secrets first if available
    try:
        if hasattr(st, "secrets") and "mysql" in st.secrets:
            sec = st.secrets["mysql"]
            return {
                "host": sec.get("host", "localhost"),
                "port": int(sec.get("port", 3306)),
                "user": sec.get("user", "root"),
                "password": sec.get("password", ""),
                "dbname": sec.get("dbname", "toyotadb"),
                "table_name": sec.get("table_name", "auto sales data"),
            }
    except Exception:
        pass

    # 2. Check local db_config.json
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 3. Default fallback values
    return {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "",
        "dbname": "toyotadb",
        "table_name": "auto sales data",
    }


def save_db_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        st.sidebar.warning(f"Could not save config: {e}")


# ------------------------------------------------------------------
# SIDEBAR - DATA SOURCE & DATABASE CONNECTION
# ------------------------------------------------------------------
st.sidebar.title("Data Source Settings")
saved_cfg = load_db_config()

# If sqlalchemy is not installed, default to CSV File
default_source_idx = 0 if (HAS_SQLALCHEMY and saved_cfg.get("password")) else 1

source_mode = st.sidebar.radio(
    "Select Data Source:",
    ("MySQL Database", "CSV File"),
    index=default_source_idx,
)

df = None

if source_mode == "MySQL Database":
    if not HAS_SQLALCHEMY:
        st.sidebar.warning("⚠️ `sqlalchemy` or `pymysql` is not installed in this environment.")
        st.info("💡 To connect to MySQL, add `sqlalchemy`, `pymysql`, and `cryptography` to your `requirements.txt`. Falling back to CSV file.")
        if CSV_PATH.exists():
            df = load_csv_data(CSV_PATH)
        else:
            st.error("CSV file not found.")
            st.stop()
    else:
        with st.sidebar.expander("🔌 MySQL Connection Details", expanded=True):
            db_host = st.text_input("Host", value=saved_cfg.get("host", "localhost"))
            db_port = st.number_input("Port", value=int(saved_cfg.get("port", 3306)), step=1)
            db_user = st.text_input("Username", value=saved_cfg.get("user", "root"))
            db_pass = st.text_input("Password", value=saved_cfg.get("password", ""), type="password")
            db_name = st.text_input("Database Name", value=saved_cfg.get("dbname", "toyotadb"))
            db_table = st.text_input("Table Name", value=saved_cfg.get("table_name", "auto sales data"))

            save_creds = st.checkbox("Remember configuration locally", value=True)
            col_btn1, col_btn2 = st.columns(2)
            connect_pressed = col_btn1.button("Connect")
            refresh_pressed = col_btn2.button("Clear Cache")

            if refresh_pressed:
                st.cache_data.clear()
                st.rerun()

        # Attempt database connection
        try:
            engine = get_db_engine(db_user, db_pass, db_host, db_port, db_name)
            # Check connection and table existence
            with engine.connect() as conn:
                check_table = conn.execute(text(f"SHOW TABLES LIKE '{db_table}';")).fetchall()

            if not check_table:
                st.sidebar.warning(f"Table `{db_table}` does not exist in database `{db_name}`.")
                if CSV_PATH.exists():
                    if st.sidebar.button(f"📥 Import {CSV_PATH.name} into MySQL"):
                        with st.spinner("Importing CSV data to MySQL..."):
                            raw_csv = pd.read_csv(CSV_PATH)
                            raw_csv.to_sql(db_table, engine, if_exists="replace", index=False)
                            st.sidebar.success(f"Imported {len(raw_csv):,} rows into `{db_table}`!")
                            st.cache_data.clear()
                            st.rerun()
                st.info(f"Database `{db_name}` is connected, but table `{db_table}` needs data. Use the import button above or select CSV File.")
                st.stop()
            else:
                @st.cache_data(ttl=300)
                def fetch_from_db(_eng, table):
                    query = f"SELECT * FROM `{table}`"
                    data = pd.read_sql(query, _eng)
                    return prepare_dataframe(data)

                df = fetch_from_db(engine, db_table)
                st.sidebar.success(f"Connected to MySQL! Loaded {len(df):,} rows.")

                if save_creds and (connect_pressed or not CONFIG_PATH.exists()):
                    save_db_config({
                        "host": db_host,
                        "port": int(db_port),
                        "user": db_user,
                        "password": db_pass,
                        "dbname": db_name,
                        "table_name": db_table,
                    })

        except Exception as e:
            err_msg = str(e)
            st.sidebar.error("Database connection failed.")
            st.error(f"### ❌ Database Connection Error\n\n**Details:** `{err_msg}`")

            # Specific user-friendly diagnostics
            if "Access denied" in err_msg:
                st.warning("👉 **Password or Username incorrect:** Please check your MySQL password and username in the sidebar.")
            elif "Can't connect to MySQL server" in err_msg or "2003" in err_msg:
                st.warning(
                    "👉 **MySQL server not reachable:**\n\n"
                    "- If running **locally**: verify that the `MySQL80` Windows service is running.\n"
                    "- If running on **Streamlit Cloud**: a database on `localhost` cannot be reached from the cloud. Deploy your database to a cloud provider (such as TiDB Cloud, Aiven, or Supabase), or switch to the CSV File option."
                )
            elif "Unknown database" in err_msg:
                st.warning(f"👉 **Database `{db_name}` does not exist yet:**")
                if st.button(f"Create database `{db_name}` now"):
                    try:
                        server_eng = get_db_engine(db_user, db_pass, db_host, db_port)
                        with server_eng.connect() as conn:
                            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`;"))
                            conn.commit()
                        st.success(f"Database `{db_name}` created successfully! Please refresh.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Failed to create database: {ex}")

            # Fallback option
            if CSV_PATH.exists():
                st.info("💡 You can view the dashboard using the local CSV file while database settings are being checked.")
                if st.button("Use CSV File for now"):
                    df = load_csv_data(CSV_PATH)
            else:
                st.stop()

            if df is None:
                st.stop()

else:
    # CSV file loading mode
    if CSV_PATH.exists():
        df = load_csv_data(CSV_PATH)
        st.sidebar.info(f"Loaded local data from `{CSV_PATH.name}` ({len(df):,} rows).")
    else:
        up = st.sidebar.file_uploader("Upload Auto Sales data CSV", type="csv")
        if up is None:
            st.info("Place Auto Sales data.csv next to this script, or upload it in the sidebar.")
            st.stop()
        df = load_csv_data(up)


# ------------------------------------------------------------------
# FILTERS
# ------------------------------------------------------------------
st.sidebar.header("Filters")


def multi(label, col):
    opts = sorted(df[col].dropna().unique())
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

st.caption(f"Data range: {f['ORDERDATE'].min():%d %b %Y} to {f['ORDERDATE'].max():%d %b %Y} | Total Records: {len(f):,}")

# ------------------------------------------------------------------
# KPIS
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
