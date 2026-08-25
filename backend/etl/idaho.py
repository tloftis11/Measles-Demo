"""
Idaho IDHW Vaccination Coverage ETL.

Downloads and ingests school-year MMR coverage data from:
  https://healthandwelfare.idaho.gov/health-wellness/immunizations/immunization-data

The Idaho Division of Public Health, Immunization Program publishes an annual
Excel or PDF report with county-level immunization data (not district-level in
publicly available files). The URL pattern changes each year, so this ETL
attempts the download and falls back gracefully to seed data already loaded by
db._seed_idaho() if the download fails.

Run:
    uv run python -m etl.idaho

On first run this will attempt to download the live IDHW file. If the
download fails (no network, URL changed, PDF format, etc.) it falls back to
the seed data already loaded by db._seed_idaho().
"""

import io
import logging
from pathlib import Path

import httpx
import pandas as pd
import duckdb

from db import get_connection

logger = logging.getLogger(__name__)

# IDHW publishes the current school year file; URL changes annually — update each year.
IDHW_URL = (
    "https://healthandwelfare.idaho.gov/sites/default/files/2024-01/"
    "2023-2024_SchoolImmunizationReport.xlsx"
)

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
SCHOOL_YEAR = "2023-2024"


def download_idhw_excel(url: str = IDHW_URL) -> bytes | None:
    """Attempt to download the IDHW Excel file; return bytes or None on failure."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        logger.info("Downloaded IDHW file: %d bytes", len(resp.content))
        return resp.content
    except Exception as exc:
        logger.warning("IDHW download failed (%s); will use existing seed data.", exc)
        return None


def parse_idhw_excel(raw_bytes: bytes) -> pd.DataFrame:
    """Parse the IDHW Excel into a normalized DataFrame.

    Idaho public files are county-level aggregates with expected columns:
      County | Enrolled | MMR Vaccinated | Medical Exempt | Non-Medical Exempt
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=0)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # Adjust column mapping if IDHW changes their format:
    rename = {
        "county_name": "county",
        "total_enrolled": "enrolled",
        "mmr_vaccinated": "mmr_vaccinated",
        "students_with_mmr": "mmr_vaccinated",
        "medical_exemption": "medical_exempt",
        "medical_exemptions": "medical_exempt",
        "non-medical_exemption": "nonmedical_exempt",
        "non-medical_exemptions": "nonmedical_exempt",
        "nonmedical_exemption": "nonmedical_exempt",
        "nonmedical_exemptions": "nonmedical_exempt",
        "personal_belief_exemption": "nonmedical_exempt",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df = df.dropna(subset=["county", "enrolled"])
    df["enrolled"] = pd.to_numeric(df["enrolled"], errors="coerce").fillna(0).astype(int)
    df["mmr_vaccinated"] = pd.to_numeric(df.get("mmr_vaccinated", 0), errors="coerce").fillna(0)
    df["medical_exempt"] = pd.to_numeric(df.get("medical_exempt", 0), errors="coerce").fillna(0)
    df["nonmedical_exempt"] = pd.to_numeric(
        df.get("nonmedical_exempt", 0), errors="coerce"
    ).fillna(0)
    return df


def compute_county_pcts(df: pd.DataFrame) -> pd.DataFrame:
    """Compute coverage and exemption percentages from county-level counts."""
    df = df.copy()
    df["mmr_coverage_pct"] = (df["mmr_vaccinated"] / df["enrolled"] * 100).round(1)
    df["medical_exempt_pct"] = (df["medical_exempt"] / df["enrolled"] * 100).round(2)
    df["nonmedical_exempt_pct"] = (df["nonmedical_exempt"] / df["enrolled"] * 100).round(2)
    return df


def _county_name_to_fips(con: duckdb.DuckDBPyConnection, county: str) -> str | None:
    row = con.execute(
        "SELECT fips FROM geographies WHERE state_abbr = 'ID' AND county_name = ?",
        [county.strip().title()],
    ).fetchone()
    return row[0] if row else None


def ingest(con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Download and ingest IDHW data. Returns number of rows upserted."""
    if con is None:
        con = get_connection()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached_path = RAW_DIR / f"id_idhw_{SCHOOL_YEAR.replace('-', '_')}.xlsx"

    raw_bytes: bytes | None = None
    if cached_path.exists():
        logger.info("Using cached file: %s", cached_path)
        raw_bytes = cached_path.read_bytes()
    else:
        raw_bytes = download_idhw_excel()
        if raw_bytes:
            cached_path.write_bytes(raw_bytes)

    if raw_bytes is None:
        logger.info("No live data available — seed data remains in place.")
        return 0

    df = parse_idhw_excel(raw_bytes)
    county_df = compute_county_pcts(df)

    inserted = 0
    for _, row in county_df.iterrows():
        fips = _county_name_to_fips(con, row["county"])
        if fips is None:
            logger.debug("No FIPS match for Idaho county: %s", row["county"])
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
                "ID-IDHW-live",
            ],
        )
        inserted += 1

    logger.info("Upserted %d ID county coverage rows.", inserted)
    return inserted


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    n = ingest()
    print(f"Done — {n} rows ingested.")


if __name__ == "__main__":
    run()
