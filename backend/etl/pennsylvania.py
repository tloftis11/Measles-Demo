"""
Pennsylvania DOH Vaccination Coverage ETL.

Downloads and ingests school-year MMR coverage data from:
  https://www.health.pa.gov/topics/healthstatistics/VitalStatistics/Pages/school-immunization.aspx

The Pennsylvania Department of Health, Bureau of Communicable Diseases publishes
annual district-level immunization data. This ETL attempts the download, parses
district rows, and upserts into both:
  - vaccination_coverage  (aggregated to county level)
  - school_districts      (one row per district)

Falls back gracefully to seed data already loaded by db._seed_pennsylvania()
if the download fails, which is expected — the PA DOH URL changes annually and
typically requires page navigation to locate the current Excel file.

Run:
    uv run python -m etl.pennsylvania

Important PA data characteristics
----------------------------------
* Amish communities in Lancaster, Mifflin, Juniata, and Snyder counties have
  very low reported MMR rates (~65–75%), but many unvaccinated children are
  homeschooled and not captured in school enrollment data, so the true
  population-level coverage is lower than reported figures suggest.
* Pennsylvania allows only religious exemptions (not philosophical/personal
  belief). The nonmedical_exempt column in this ETL reflects religious
  exemptions only.
* Download failure is expected and normal — seed data in db.py covers PA.
"""

import io
import logging
from pathlib import Path

import httpx
import pandas as pd
import duckdb

from db import get_connection

logger = logging.getLogger(__name__)

# PA DOH publishes immunization data at a URL that changes annually; update each year.
# The landing page requires navigation to locate the current Excel download link.
PA_DOH_URL = (
    "https://www.health.pa.gov/topics/healthstatistics/VitalStatistics/"
    "Documents/SchoolImmunization2023-2024.xlsx"
)

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
SCHOOL_YEAR = "2023-2024"


def download_pa_excel(url: str = PA_DOH_URL) -> bytes | None:
    """Attempt to download the PA DOH Excel file; return bytes or None on failure.

    Failure is expected and normal — the URL changes annually and the DOH site
    requires navigation. Seed data in db.py covers PA when this returns None.
    """
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        logger.info("Downloaded PA DOH file: %d bytes", len(resp.content))
        return resp.content
    except Exception as exc:
        logger.warning(
            "PA DOH download failed (%s); will use existing seed data. "
            "This is expected — PA URL changes annually.",
            exc,
        )
        return None


def parse_pa_excel(raw_bytes: bytes) -> pd.DataFrame:
    """Parse the PA DOH Excel into a normalized district-level DataFrame.

    PA DOH files include district-level rows with expected columns:
      County | School District | Enrolled | MMR Vaccinated |
      Medical Exemptions | Religious Exemptions
    """
    df = pd.read_excel(io.BytesIO(raw_bytes), header=1)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # Adjust column mapping if PA DOH changes their format:
    rename = {
        "county_name": "county",
        "district_name": "district",
        "school_district": "district",
        "total_enrolled": "enrolled",
        "students_enrolled": "enrolled",
        "mmr_vaccinated": "mmr_vaccinated",
        "students_with_mmr": "mmr_vaccinated",
        "medical_exemptions": "medical_exempt",
        "medical_exemption": "medical_exempt",
        "religious_exemptions": "nonmedical_exempt",
        "religious_exemption": "nonmedical_exempt",
        "nonmedical_exemptions": "nonmedical_exempt",
        "nonmedical_exemption": "nonmedical_exempt",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "district" not in df.columns:
        df["district"] = ""
    df = df.dropna(subset=["county", "enrolled"])
    df["enrolled"] = pd.to_numeric(df["enrolled"], errors="coerce").fillna(0).astype(int)
    df["mmr_vaccinated"] = pd.to_numeric(df.get("mmr_vaccinated", 0), errors="coerce").fillna(0)
    df["medical_exempt"] = pd.to_numeric(df.get("medical_exempt", 0), errors="coerce").fillna(0)
    df["nonmedical_exempt"] = pd.to_numeric(
        df.get("nonmedical_exempt", 0), errors="coerce"
    ).fillna(0)
    return df


def aggregate_to_county(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate district-level rows to county level."""
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


def compute_district_pcts(df: pd.DataFrame) -> pd.DataFrame:
    """Compute coverage and exemption percentages for district-level rows."""
    df = df.copy()
    df["mmr_coverage_pct"] = (df["mmr_vaccinated"] / df["enrolled"] * 100).round(1)
    df["medical_exempt_pct"] = (df["medical_exempt"] / df["enrolled"] * 100).round(2)
    df["nonmedical_exempt_pct"] = (df["nonmedical_exempt"] / df["enrolled"] * 100).round(2)
    return df


def _county_name_to_fips(con: duckdb.DuckDBPyConnection, county: str) -> str | None:
    row = con.execute(
        "SELECT fips FROM geographies WHERE state_abbr = 'PA' AND county_name = ?",
        [county.strip().title()],
    ).fetchone()
    return row[0] if row else None


def ingest(con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Download and ingest PA DOH data. Returns number of county rows upserted.

    Upserts into vaccination_coverage (county-level) and school_districts
    (district-level). Download failure is expected and handled gracefully.
    """
    if con is None:
        con = get_connection()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached_path = RAW_DIR / f"pa_doh_{SCHOOL_YEAR.replace('-', '_')}.xlsx"

    raw_bytes: bytes | None = None
    if cached_path.exists():
        logger.info("Using cached file: %s", cached_path)
        raw_bytes = cached_path.read_bytes()
    else:
        raw_bytes = download_pa_excel()
        if raw_bytes:
            cached_path.write_bytes(raw_bytes)

    if raw_bytes is None:
        logger.info("No live data available — seed data remains in place.")
        return 0

    district_df = parse_pa_excel(raw_bytes)
    district_df = compute_district_pcts(district_df)
    county_df = aggregate_to_county(district_df)

    # Upsert district-level rows into school_districts table.
    districts_inserted = 0
    for _, row in district_df.iterrows():
        fips = _county_name_to_fips(con, row["county"])
        if fips is None:
            logger.debug("No FIPS match for PA county: %s", row["county"])
            continue
        con.execute(
            """
            INSERT OR REPLACE INTO school_districts
            (fips, school_year, district_name, mmr_coverage_pct,
             medical_exempt_pct, nonmedical_exempt_pct, enrolled, source)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                fips,
                SCHOOL_YEAR,
                str(row.get("district", "")).strip(),
                row["mmr_coverage_pct"],
                row["medical_exempt_pct"],
                row["nonmedical_exempt_pct"],
                int(row["enrolled"]),
                "PA-DOH-live",
            ],
        )
        districts_inserted += 1
    logger.info("Upserted %d PA district rows.", districts_inserted)

    # Upsert county-level aggregates into vaccination_coverage table.
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
                "PA-DOH-live",
            ],
        )
        inserted += 1

    logger.info("Upserted %d PA county coverage rows.", inserted)
    return inserted


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    n = ingest()
    print(f"Done — {n} rows ingested.")


if __name__ == "__main__":
    run()
