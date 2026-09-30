PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cities (
    city_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_name TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_hourly (
    city_id INTEGER NOT NULL,
    forecast_time TEXT NOT NULL,
    temperature_c REAL,
    rain_probability_pct REAL,
    PRIMARY KEY (city_id, forecast_time),
    FOREIGN KEY (city_id) REFERENCES cities(city_id)
);

CREATE INDEX IF NOT EXISTS idx_weather_city_time
ON weather_hourly(city_id, forecast_time);
