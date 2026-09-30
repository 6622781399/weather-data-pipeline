import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path("weather.db")

st.set_page_config(
    page_title="Thailand Weather Dashboard",
    layout="wide",
)

st.title("Thailand 7-Day Weather Dashboard")
st.caption("Data source: Open-Meteo | Data is read from SQLite")

if not DB_PATH.exists():
    st.error("weather.db not found. Run `python ingestion.py` first.")
    st.stop()

conn = sqlite3.connect(DB_PATH)

cities = pd.read_sql_query(
    "SELECT city_id, city_name FROM cities ORDER BY city_name",
    conn,
)

weather = pd.read_sql_query(
    """
    SELECT
        c.city_name,
        w.forecast_time,
        w.temperature_c,
        w.rain_probability_pct
    FROM weather_hourly AS w
    JOIN cities AS c ON c.city_id = w.city_id
    ORDER BY w.forecast_time, c.city_name
    """,
    conn,
)

conn.close()

weather["forecast_time"] = pd.to_datetime(weather["forecast_time"])
weather["forecast_date"] = weather["forecast_time"].dt.date

col1, col2, col3 = st.columns(3)
col1.metric("Cities", len(cities))
col2.metric("Hourly observations", len(weather))
col3.metric(
    "Forecast days",
    weather["forecast_date"].nunique(),
)

st.subheader("Temperature by City")

selected_cities = st.multiselect(
    "Select cities",
    options=cities["city_name"].tolist(),
    default=cities["city_name"].tolist(),
)

filtered = weather[weather["city_name"].isin(selected_cities)].copy()

if filtered.empty:
    st.info("Select at least one city.")
    st.stop()

chart_data = (
    filtered
    .pivot(index="forecast_time", columns="city_name", values="temperature_c")
)

st.line_chart(chart_data)

st.subheader("Daily Temperature Summary")

daily = (
    filtered
    .groupby(["city_name", "forecast_date"], as_index=False)
    .agg(
        avg_temperature_c=("temperature_c", "mean"),
        max_temperature_c=("temperature_c", "max"),
        min_temperature_c=("temperature_c", "min"),
    )
)

daily["temperature_range_c"] = (
    daily["max_temperature_c"] - daily["min_temperature_c"]
)

daily_display = daily.copy()
for col in [
    "avg_temperature_c",
    "max_temperature_c",
    "min_temperature_c",
    "temperature_range_c",
]:
    daily_display[col] = daily_display[col].round(2)

st.dataframe(
    daily_display.sort_values(["forecast_date", "city_name"]),
    use_container_width=True,
)

st.subheader("Highest Rain Probability by City and Day")

rain = filtered.dropna(subset=["rain_probability_pct"]).copy()

if not rain.empty:
    rain["rank"] = rain.groupby(
        ["city_name", "forecast_date"]
    )["rain_probability_pct"].rank(
        method="first",
        ascending=False,
    )

    rain_max = rain[rain["rank"] == 1].copy()
    rain_max["time"] = rain_max["forecast_time"].dt.strftime("%H:%M")
    rain_max["rain_probability_pct"] = rain_max[
        "rain_probability_pct"
    ].round(0)

    st.dataframe(
        rain_max[
            [
                "city_name",
                "forecast_date",
                "time",
                "rain_probability_pct",
            ]
        ].sort_values(["forecast_date", "city_name"]),
        use_container_width=True,
    )
else:
    st.info("No rain-probability values available.")
