"""
Texas DSHS Vaccination Coverage ETL.

Downloads and ingests school-year MMR coverage data from:
  https://www.dshs.texas.gov/immunize/coverage/default.shtm

The DSHS publishes an Excel file per school year with columns:
  School District | County | Enrolled | Vaccinated (MMR) | Medical Exemptions | Non-Medical Exemptions

Run:
    uv run python -m etl.texas

On first run this will attempt to download the live DSHS file. If the
download fails (no network, URL changed) it falls back to the seed data
already loaded by db._seed_texas().
"""

import io
import logging
from pathlib import Path

import httpx
import pandas as pd
import duckdb

from db import get_connection

logger = logging.getLogger(__name__)

# DSHS publishes the current school year file at a stable pattern; update URL each year.
DSHS_URL = (
    "https://www.dshs.texas.gov/sites/default/files/immunize/coverage/"
    "2023-2024_SchoolCoverage.xlsx"
)

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
SCHOOL_YEAR = "2023-2024"


def download_dshs_excel(url: str = DSHS_URL) -> bytes | None:
    """Attempt to download the DSHS Excel file; return bytes or None on failure."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        logger.info("Downloaded DSHS file: %d bytes", len(resp.content))
        return resp.content
    except Exception as exc:
        logger.warning("DSHS download failed (%s); will use existing seed data.", exc)
        return None


def parse_dshs_excel(raw_bytes: bytes) -> pd.DataFrame:
    """Parse the DSHS Excel into a normalized DataFrame."""
    df = pd.read_excel(io.BytesIO(raw_bytes), header=2)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # Expected columns after normalization:
    #   county, school_district, enrolled, mmr_vaccinated, medical_exempt, nonmedical_exempt
    # Adjust column mapping if DSHS changes their format:
    rename = {
        "county_name": "county",
        "students_enrolled": "enrolled",
        "students_with_mmr": "mmr_vaccinated",
        "medical_exemptions": "medical_exempt",
        "nonmedical_exemptions": "nonmedical_exempt",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df = df.dropna(subset=["county", "enrolled"])
    df["enrolled"] = pd.to_numeric(df["enrolled"], errors="coerce").fillna(0).astype(int)
    df["mmr_vaccinated"] = pd.to_numeric(df["mmr_vaccinated"], errors="coerce").fillna(0)
    df["medical_exempt"] = pd.to_numeric(df["medical_exempt"], errors="coerce").fillna(0)
    df["nonmedical_exempt"] = pd.to_numeric(df["nonmedical_exempt"], errors="coerce").fillna(0)
    return df


def aggregate_to_county(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate school-district rows to county level."""
    agg = df.groupby("county", as_index=False).agg(
        enrolled=("enrolled", "sum"),
        mmr_vaccinated=("mmr_vaccinated", "sum"),
        medical_exempt=("medical_exempt", "sum"),
        nonmedical_exempt=("nonmedical_exempt", "sum"),
    )
    agg["mmr_coverage_pct"] = (agg["mmr_vaccinated"] / agg["enrolled"] * 100).round(1)
    agg["medical_exempt_pct"] = (agg["medical_exempt"] / agg["enrolled"] * 100).round(2)
    agg["nonmedical_exempt_pct"] = (agg["nonmedical_exempt"] / agg["enrolled"] * 100).round(2)
    return agg


def _county_name_to_fips(con: duckdb.DuckDBPyConnection, county: str) -> str | None:
    row = con.execute(
        "SELECT fips FROM geographies WHERE state_abbr = 'TX' AND county_name = ?",
        [county.strip().title()],
    ).fetchone()
    return row[0] if row else None


def ingest(con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Download and ingest DSHS data. Returns number of rows upserted."""
    if con is None:
        con = get_connection()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached_path = RAW_DIR / f"tx_dshs_{SCHOOL_YEAR.replace('-', '_')}.xlsx"

    raw_bytes: bytes | None = None
    if cached_path.exists():
        logger.info("Using cached file: %s", cached_path)
        raw_bytes = cached_path.read_bytes()
    else:
        raw_bytes = download_dshs_excel()
        if raw_bytes:
            cached_path.write_bytes(raw_bytes)

    if raw_bytes is None:
        logger.info("No live data available — seed data remains in place.")
        return 0

    df = parse_dshs_excel(raw_bytes)
    county_df = aggregate_to_county(df)

    inserted = 0
    for _, row in county_df.iterrows():
        fips = _county_name_to_fips(con, row["county"])
        if fips is None:
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO vaccination_coverage
            (fips, school_year, mmr_coverage_pct, medical_exempt_pct,
             nonmedical_exempt_pct, enrolled, source)
            VALUES (?,?,?,?,?,?,?)
            """,
            [
                fips,
                SCHOOL_YEAR,
                row["mmr_coverage_pct"],
                row["medical_exempt_pct"],
                row["nonmedical_exempt_pct"],
                int(row["enrolled"]),
                "TX-DSHS-live",
            ],
        )
        inserted += 1

    logger.info("Upserted %d TX county coverage rows.", inserted)
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = ingest()
    print(f"Done — {n} rows ingested.")
