"""
Database Setup & CSV Import Script for Auto Sales
Use this script to connect Python to MySQL, create the database, and import the CSV data.

Run:
    py setup_database.py
"""
import getpass
import json
from pathlib import Path
import urllib.parse
import pandas as pd
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH_SPACE = BASE_DIR / "Auto Sales data.csv"
CSV_PATH_UNDERSCORE = BASE_DIR / "Auto_Sales_data.csv"
CSV_PATH = CSV_PATH_SPACE if CSV_PATH_SPACE.exists() else CSV_PATH_UNDERSCORE
CONFIG_PATH = BASE_DIR / "db_config.json"


def get_engine(user, password, host, port, dbname=None):
    safe_password = urllib.parse.quote_plus(password)
    db_part = f"/{dbname}" if dbname else ""
    url = f"mysql+pymysql://{user}:{safe_password}@{host}:{port}{db_part}?charset=utf8mb4"
    return create_engine(url)


def main():
    print("=" * 60)
    print("🚗 Auto Sales MySQL Database Setup & Connector")
    print("=" * 60)

    # Load defaults from config if available
    defaults = {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "dbname": "auto_sales",
        "table_name": "auto_sales",
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update({k: v for k, v in saved.items() if k in defaults})
        except Exception:
            pass

    host = input(f"MySQL Host [{defaults['host']}]: ").strip() or defaults["host"]
    port_in = input(f"MySQL Port [{defaults['port']}]: ").strip() or str(defaults["port"])
    port = int(port_in)
    user = input(f"MySQL User [{defaults['user']}]: ").strip() or defaults["user"]
    password = getpass.getpass("MySQL Password: ")
    dbname = input(f"Database Name to use/create [{defaults['dbname']}]: ").strip() or defaults["dbname"]
    table_name = input(f"Table Name to use/create [{defaults['table_name']}]: ").strip() or defaults["table_name"]

    print("\n⏳ Step 1: Testing connection to MySQL server...")
    try:
        server_engine = get_engine(user, password, host, port)
        with server_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{dbname}`;"))
            conn.commit()
        print(f"✅ Successfully connected! Database `{dbname}` is ready.")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nTroubleshooting tips:")
        print("  1. Verify MySQL service is running (`MySQL80` service).")
        print("  2. Check if the password or username is correct.")
        print("  3. Ensure port 3306 is not blocked.")
        return

    print(f"\n⏳ Step 2: Checking table `{table_name}` in database `{dbname}`...")
    db_engine = get_engine(user, password, host, port, dbname)

    table_exists = False
    row_count = 0
    try:
        with db_engine.connect() as conn:
            res = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
            row_count = res.scalar()
            table_exists = True
        print(f"ℹ️ Table `{table_name}` exists with {row_count:,} records.")
    except Exception:
        print(f"ℹ️ Table `{table_name}` does not exist yet.")

    should_import = False
    if not table_exists or row_count == 0:
        should_import = True
    else:
        choice = input(f"Do you want to re-import CSV data and overwrite `{table_name}`? (y/N): ").strip().lower()
        if choice in ("y", "yes"):
            should_import = True

    if should_import:
        if not CSV_PATH.exists():
            print(f"❌ Could not find CSV file at {CSV_PATH}")
            return

        print(f"⏳ Step 3: Loading data from {CSV_PATH.name}...")
        df = pd.read_csv(CSV_PATH)
        print(f"   Found {len(df):,} rows and {len(df.columns)} columns.")

        print(f"⏳ Step 4: Importing {len(df):,} rows into `{dbname}`.`{table_name}`...")
        df.to_sql(table_name, db_engine, if_exists="replace", index=False)
        print(f"✅ Successfully imported {len(df):,} rows into table `{table_name}`!")

    # Save configuration
    save_config = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
        "table_name": table_name,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(save_config, f, indent=4)
    print(f"✅ Configuration saved to `{CONFIG_PATH.name}` for Toyota.py.")
    print("\n🎉 All set! Now you can run your Streamlit dashboard:")
    print("   py -m streamlit run Toyota.py")


if __name__ == "__main__":
    main()

