import json
import logging
import sqlite3
import time
from pathlib import Path

import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"
DB_PATH = Path("weather.db")
RAW_DIR = Path("raw")
SCHEMA_PATH = Path("schema.sql")

CITIES = [
    {"name": "Bangkok", "latitude": 13.7563, "longitude": 100.5018},
    {"name": "Chiang Mai", "latitude": 18.7883, "longitude": 98.9853},
    {"name": "Phuket", "latitude": 7.8804, "longitude": 98.3923},
    {"name": "Khon Kaen", "latitude": 16.4322, "longitude": 102.8236},
    {"name": "Hat Yai", "latitude": 7.0084, "longitude": 100.4747},
]

REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
EXPECTED_HOURS = 7 * 24

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("weather_pipeline")


def init_db(conn: sqlite3.Connection) -> None:
    """Create the database schema and seed city metadata."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    for city in CITIES:
        conn.execute(
            """
            INSERT INTO cities (city_name, latitude, longitude, timezone)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(city_name) DO UPDATE SET
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                timezone = excluded.timezone
            """,
            (city["name"], city["latitude"], city["longitude"], "Asia/Bangkok"),
        )
    conn.commit()


def fetch_weather(city: dict) -> dict:
    """Fetch one city's 7-day hourly forecast with retry handling."""
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": "temperature_2m,precipitation_probability",
        "forecast_days": 7,
        "timezone": "Asia/Bangkok",
        "temperature_unit": "celsius",
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                raise requests.HTTPError(
                    f"HTTP {response.status_code}: {response.text[:300]}"
                )

            payload = response.json()

            if payload.get("error"):
                raise ValueError(payload.get("reason", "API returned an error"))

            return payload

        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "%s attempt %s/%s failed: %s",
                city["name"],
                attempt,
                MAX_RETRIES,
                exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(2 ** (attempt - 1))

    raise RuntimeError(f"Failed to fetch {city['name']}: {last_error}")


def transform(payload: dict) -> list[tuple]:
    """Convert Open-Meteo's parallel hourly arrays into database rows."""
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temperatures = hourly.get("temperature_2m", [])
    rain_probs = hourly.get("precipitation_probability", [])

    if not (len(times) == len(temperatures) == len(rain_probs)):
        raise ValueError("Hourly arrays have different lengths")

    if len(times) != EXPECTED_HOURS:
        logger.warning(
            "Expected %s hourly observations, received %s",
            EXPECTED_HOURS,
            len(times),
        )

    rows = []
    for timestamp, temp, rain_prob in zip(times, temperatures, rain_probs):
        rows.append(
            (
                timestamp,
                None if temp is None else float(temp),
                None if rain_prob is None else float(rain_prob),
            )
        )

    return rows


def load_city(
    conn: sqlite3.Connection,
    city: dict,
    rows: list[tuple],
) -> int:
    """Atomically replace/update one city's forecast observations."""
    city_id = conn.execute(
        "SELECT city_id FROM cities WHERE city_name = ?",
        (city["name"],),
    ).fetchone()[0]

    with conn:
        conn.executemany(
            """
            INSERT INTO weather_hourly (
                city_id,
                forecast_time,
                temperature_c,
                rain_probability_pct
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(city_id, forecast_time) DO UPDATE SET
                temperature_c = excluded.temperature_c,
                rain_probability_pct = excluded.rain_probability_pct
            """,
            [
                (city_id, timestamp, temp, rain_prob)
                for timestamp, temp, rain_prob in rows
            ],
        )

    return len(rows)


def main() -> None:
    start = time.perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    processed_cities = 0
    processed_rows = 0
    failures = []

    try:
        init_db(conn)

        for city in CITIES:
            try:
                payload = fetch_weather(city)

                # Save raw response before transformation.
                raw_path = RAW_DIR / f"{city['name'].lower().replace(' ', '_')}.json"
                raw_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

                rows = transform(payload)
                loaded = load_city(conn, city, rows)

                processed_cities += 1
                processed_rows += loaded
                logger.info(
                    "%s processed: %s rows",
                    city["name"],
                    loaded,
                )

            except Exception as exc:
                failures.append((city["name"], str(exc)))
                logger.error("%s failed: %s", city["name"], exc)

    finally:
        conn.close()

    elapsed = time.perf_counter() - start

    logger.info(
        "Pipeline finished | cities=%s | rows=%s | failures=%s | elapsed=%.2fs",
        processed_cities,
        processed_rows,
        len(failures),
        elapsed,
    )

    if failures:
        logger.error("Failed cities: %s", failures)


if __name__ == "__main__":
    main()
