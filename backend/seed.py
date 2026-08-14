"""
CSV seeding script for ObRail Europe.

Reads eu_trips_v2.csv, applies data-quality fixes, and bulk-inserts
rows into the PostgreSQL 'trips' table. Idempotent: rows whose trip_id
already exists in the database are silently skipped.

Usage:
    python seed.py

Environment variables:
    DATABASE_URL  — PostgreSQL connection string (required)
    CSV_PATH      — path to the CSV file (default: ./data/eu_trips_v2.csv)
"""

import logging
import os
import sys

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports that depend on DATABASE_URL being present
# ---------------------------------------------------------------------------
from app.database import SessionLocal, engine  # noqa: E402
from app.models import Base, Trip  # noqa: E402

CSV_PATH = os.getenv("CSV_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "eu_trips_v2.csv"))
BATCH_SIZE = 1_000
CO2_WARNING_THRESHOLD = 2_000_000

# Columns that arrive as mixed types in the raw CSV
MIXED_TYPE_COLS = {
    "destination_stop_id": str,
    "origin_stop_id": str,
    "route_id": str,
    "trip_id": str,
}


def load_csv(path: str) -> pd.DataFrame:
    """Read the CSV, forcing mixed-type columns to str from the start."""
    if not os.path.exists(path):
        logger.error("CSV file not found: %s", path)
        sys.exit(1)

    logger.info("Reading CSV from %s …", path)
    df = pd.read_csv(path, dtype=MIXED_TYPE_COLS, low_memory=False)
    logger.info("Rows read: %d", len(df))
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all data-quality fixes and return the cleaned DataFrame."""
    initial_count = len(df)

    # Filter out aberrant zero-duration trips
    df = df[df["duration_minutes"] != 0].copy()
    filtered_count = initial_count - len(df)
    if filtered_count:
        logger.info("Rows dropped (duration_minutes == 0): %d", filtered_count)

    # Normalise route_long_name: NaN → None (Python None → SQL NULL)
    df["route_long_name"] = df["route_long_name"].where(
        df["route_long_name"].notna(), other=None
    )

    # Warn on extreme CO2 outliers (kept in the dataset as-is)
    outliers = df[df["co2_estime"] > CO2_WARNING_THRESHOLD]
    for _, row in outliers.iterrows():
        logger.warning(
            "co2_estime outlier detected — trip_id=%s, co2_estime=%.2f",
            row["trip_id"],
            row["co2_estime"],
        )

    return df


def fetch_existing_trip_ids(session) -> set:
    """Return the set of trip_ids already present in the database."""
    rows = session.query(Trip.trip_id).all()
    return {r[0] for r in rows}


def build_mapping(row: pd.Series) -> dict:
    """Convert a DataFrame row into a dict ready for bulk_insert_mappings."""
    return {
        "trip_id": row["trip_id"],
        "route_id": row["route_id"] if pd.notna(row["route_id"]) else None,
        "route_long_name": row["route_long_name"],
        "route_type": int(row["route_type"]),
        "service_id": str(row["service_id"]),
        "country": row["country"],
        "origin_stop_id": row["origin_stop_id"],
        "origin_stop_name": row["origin_stop_name"],
        "origin_stop_lat": float(row["origin_stop_lat"]),
        "origin_stop_lon": float(row["origin_stop_lon"]),
        "destination_stop_id": row["destination_stop_id"],
        "destination_stop_name": row["destination_stop_name"],
        "destination_stop_lat": float(row["destination_stop_lat"]),
        "destination_stop_lon": float(row["destination_stop_lon"]),
        "departure_minutes": float(row["departure_minutes"]),
        "arrival_minutes": float(row["arrival_minutes"]),
        "duration_minutes": float(row["duration_minutes"]),
        "n_stops": float(row["n_stops"]),
        "distance_km": float(row["distance_km"]),
        "type_train": row["type_train"],
        "consommation_energy": float(row["consommation_energy"]),
        "gco2_per_kwh": float(row["gco2_per_kwh"]),
        "consommation_totale": float(row["consommation_totale"]),
        "co2_estime": float(row["co2_estime"]),
    }


def seed(df: pd.DataFrame) -> int:
    """Insert new rows into the database; return the number of rows inserted."""
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    inserted_total = 0

    try:
        existing_ids = fetch_existing_trip_ids(session)
        logger.info("Existing trip_ids in DB: %d", len(existing_ids))

        batch: list[dict] = []
        skipped = 0

        for _, row in df.iterrows():
            tid = row["trip_id"]
            if tid in existing_ids:
                skipped += 1
                continue

            batch.append(build_mapping(row))
            existing_ids.add(tid)  # prevent duplicates within the same CSV

            if len(batch) >= BATCH_SIZE:
                session.bulk_insert_mappings(Trip, batch)
                session.commit()
                inserted_total += len(batch)
                logger.info("Inserted batch — cumulative: %d rows", inserted_total)
                batch = []

        # Flush remaining rows
        if batch:
            session.bulk_insert_mappings(Trip, batch)
            session.commit()
            inserted_total += len(batch)

        if skipped:
            logger.info("Rows skipped (already in DB): %d", skipped)

    except Exception:
        session.rollback()
        logger.exception("Seed failed — transaction rolled back")
        raise
    finally:
        session.close()

    return inserted_total


def main() -> None:
    df_raw = load_csv(CSV_PATH)
    rows_read = len(df_raw)

    df_clean = clean(df_raw)
    rows_after_filter = len(df_clean)
    rows_filtered = rows_read - rows_after_filter

    rows_inserted = seed(df_clean)

    logger.info(
        "Seed complete — read: %d | filtered: %d | inserted: %d",
        rows_read,
        rows_filtered,
        rows_inserted,
    )


if __name__ == "__main__":
    main()
