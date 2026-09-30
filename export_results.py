import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("weather.db")
SQL_DIR = Path("sql")
RESULTS_DIR = Path("results")

QUERIES = {
    "01_daily_temperature": "01_daily_temperature.sql",
    "02_widest_temperature_range": "02_widest_temperature_range.sql",
    "03_highest_rain_probability": "03_highest_rain_probability.sql",
    "04_daily_temperature_change": "04_daily_temperature_change.sql",
}


def main():
    RESULTS_DIR.mkdir(exist_ok=True)

    if not DB_PATH.exists():
        raise SystemExit(
            "weather.db does not exist. Run `python ingestion.py` first."
        )

    conn = sqlite3.connect(DB_PATH)

    try:
        for name, filename in QUERIES.items():
            sql = (SQL_DIR / filename).read_text(encoding="utf-8")
            df = pd.read_sql_query(sql, conn)
            output = RESULTS_DIR / f"{name}.csv"
            df.to_csv(output, index=False)
            print(f"{output}: {len(df)} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
