import os
import duckdb
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "../data/measles.duckdb")

_conn: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        db_file = Path(DB_PATH).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(str(db_file))
        _ensure_schema(_conn)
    return _conn


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS geographies (
            fips        VARCHAR PRIMARY KEY,
            state_fips  VARCHAR NOT NULL,
            state_abbr  VARCHAR NOT NULL,
            county_name VARCHAR NOT NULL,
            full_name   VARCHAR NOT NULL,
            population  INTEGER
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS vaccination_coverage (
            fips                 VARCHAR NOT NULL,
            school_year          VARCHAR NOT NULL,
            mmr_coverage_pct     DOUBLE,
            medical_exempt_pct   DOUBLE,
            nonmedical_exempt_pct DOUBLE,
            enrolled             INTEGER,
            source               VARCHAR,
            updated_at           TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (fips, school_year)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS surveillance (
            fips                  VARCHAR NOT NULL,
            report_date           DATE NOT NULL,
            confirmed_cases       INTEGER DEFAULT 0,
            suspect_cases         INTEGER DEFAULT 0,
            wastewater_signal     DOUBLE,
            lab_specimens_tested  INTEGER,
            lab_positivity_pct    DOUBLE,
            source                VARCHAR,
            PRIMARY KEY (fips, report_date)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS network_metrics (
            fips                    VARCHAR NOT NULL,
            metric_date             DATE NOT NULL,
            school_district_count   INTEGER,
            total_k12_enrollment    INTEGER,
            mobility_index          DOUBLE,
            border_adjacent         BOOLEAN DEFAULT FALSE,
            religious_community_idx DOUBLE,
            PRIMARY KEY (fips, metric_date)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS hotspot_scores (
            fips               VARCHAR NOT NULL,
            score_date         DATE NOT NULL,
            coverage_score     DOUBLE,
            surveillance_score DOUBLE,
            network_score      DOUBLE,
            composite_score    DOUBLE,
            risk_tier          VARCHAR,
            score_components   JSON,
            PRIMARY KEY (fips, score_date)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS school_districts (
            lea_id                VARCHAR NOT NULL,
            fips                  VARCHAR NOT NULL,
            state_abbr            VARCHAR NOT NULL,
            district_name         VARCHAR NOT NULL,
            enrollment            INTEGER,
            mmr_coverage_pct      DOUBLE,
            nonmedical_exempt_pct DOUBLE,
            medical_exempt_pct    DOUBLE,
            school_year           VARCHAR NOT NULL,
            source                VARCHAR,
            PRIMARY KEY (lea_id, school_year)
        )
    """)

    # Seed if empty
    row = con.execute("SELECT COUNT(*) FROM geographies").fetchone()
    if row and row[0] == 0:
        _seed_texas(con)


def _seed_texas(con: duckdb.DuckDBPyConnection) -> None:
    """Seed realistic Texas county data for Phase 1 development."""

    geo_rows = [
        # fips, state_fips, state_abbr, county_name, full_name, population
        ("48169", "48", "TX", "Gaines",    "Gaines County, TX",    22_083),
        ("48501", "48", "TX", "Yoakum",    "Yoakum County, TX",     8_713),
        ("48079", "48", "TX", "Cochran",   "Cochran County, TX",    2_740),
        ("48445", "48", "TX", "Terry",     "Terry County, TX",     12_615),
        ("48317", "48", "TX", "Martin",    "Martin County, TX",     5_765),
        ("48115", "48", "TX", "Dawson",    "Dawson County, TX",    13_565),
        ("48003", "48", "TX", "Andrews",   "Andrews County, TX",   19_510),
        ("48303", "48", "TX", "Lubbock",   "Lubbock County, TX",  323_860),
        ("48329", "48", "TX", "Midland",   "Midland County, TX",  185_255),
        ("48135", "48", "TX", "Ector",     "Ector County, TX",    170_850),
        ("48451", "48", "TX", "Tom Green", "Tom Green County, TX", 120_940),
        ("48375", "48", "TX", "Potter",    "Potter County, TX",   124_840),
        ("48381", "48", "TX", "Randall",   "Randall County, TX",  144_720),
        ("48189", "48", "TX", "Hale",      "Hale County, TX",      33_060),
        ("48453", "48", "TX", "Travis",    "Travis County, TX", 1_290_188),
        ("48201", "48", "TX", "Harris",    "Harris County, TX", 4_780_913),
        ("48113", "48", "TX", "Dallas",    "Dallas County, TX", 2_638_148),
        ("48439", "48", "TX", "Tarrant",   "Tarrant County, TX",2_193_282),
        ("48029", "48", "TX", "Bexar",     "Bexar County, TX",  2_044_510),
        ("48085", "48", "TX", "Collin",    "Collin County, TX", 1_120_978),
        ("48491", "48", "TX", "Williamson","Williamson County, TX",720_500),
        ("48141", "48", "TX", "El Paso",   "El Paso County, TX",  870_781),
        ("48479", "48", "TX", "Webb",      "Webb County, TX",     280_260),
        ("48215", "48", "TX", "Hidalgo",   "Hidalgo County, TX",  999_940),
        ("48061", "48", "TX", "Cameron",   "Cameron County, TX",  426_540),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO geographies VALUES (?,?,?,?,?,?)", geo_rows
    )

    # vaccination_coverage: (fips, school_year, mmr_pct, med_pct, nonmed_pct, enrolled, source)
    cov_rows = [
        ("48169", "2023-2024", 79.2, 0.3, 6.8,   1_850, "TX-DSHS-sample"),
        ("48501", "2023-2024", 77.5, 0.2, 7.2,     620, "TX-DSHS-sample"),
        ("48079", "2023-2024", 80.1, 0.4, 5.9,     490, "TX-DSHS-sample"),
        ("48445", "2023-2024", 82.3, 0.3, 5.1,   1_120, "TX-DSHS-sample"),
        ("48317", "2023-2024", 81.5, 0.4, 5.4,     680, "TX-DSHS-sample"),
        ("48115", "2023-2024", 83.7, 0.2, 4.8,   1_380, "TX-DSHS-sample"),
        ("48003", "2023-2024", 85.2, 0.3, 4.2,   2_100, "TX-DSHS-sample"),
        ("48303", "2023-2024", 91.8, 0.4, 2.9,  52_800, "TX-DSHS-sample"),
        ("48329", "2023-2024", 90.5, 0.5, 3.1,  23_400, "TX-DSHS-sample"),
        ("48135", "2023-2024", 89.3, 0.4, 3.4,  30_200, "TX-DSHS-sample"),
        ("48451", "2023-2024", 92.4, 0.3, 2.6,  19_800, "TX-DSHS-sample"),
        ("48375", "2023-2024", 88.6, 0.5, 3.8,  16_700, "TX-DSHS-sample"),
        ("48381", "2023-2024", 93.1, 0.3, 2.3,  22_400, "TX-DSHS-sample"),
        ("48189", "2023-2024", 87.4, 0.3, 4.1,   6_800, "TX-DSHS-sample"),
        ("48453", "2023-2024", 96.8, 0.5, 1.8, 128_000, "TX-DSHS-sample"),
        ("48201", "2023-2024", 95.3, 0.6, 2.1, 620_000, "TX-DSHS-sample"),
        ("48113", "2023-2024", 94.8, 0.5, 2.3, 380_000, "TX-DSHS-sample"),
        ("48439", "2023-2024", 94.2, 0.4, 2.5, 290_000, "TX-DSHS-sample"),
        ("48029", "2023-2024", 95.7, 0.6, 1.9, 230_000, "TX-DSHS-sample"),
        ("48085", "2023-2024", 96.1, 0.4, 1.7, 125_000, "TX-DSHS-sample"),
        ("48491", "2023-2024", 95.4, 0.3, 2.0,  95_000, "TX-DSHS-sample"),
        ("48141", "2023-2024", 94.1, 0.8, 1.4, 145_000, "TX-DSHS-sample"),
        ("48479", "2023-2024", 93.8, 0.9, 1.2,  58_000, "TX-DSHS-sample"),
        ("48215", "2023-2024", 94.5, 0.7, 1.3, 175_000, "TX-DSHS-sample"),
        ("48061", "2023-2024", 93.2, 0.8, 1.5,  95_000, "TX-DSHS-sample"),
    ]
    con.executemany(
        """INSERT OR IGNORE INTO vaccination_coverage
           (fips, school_year, mmr_coverage_pct, medical_exempt_pct,
            nonmedical_exempt_pct, enrolled, source)
           VALUES (?,?,?,?,?,?,?)""",
        cov_rows,
    )

    # surveillance: (fips, report_date, confirmed, suspect, wastewater, specimens, positivity, source)
    surv_rows = [
        ("48169", "2024-10-01", 12, 4, 0.85, 18,  2.1,  "CDC-NNDSS-sample"),
        ("48501", "2024-10-01",  4, 2, 0.00,  0,  0.8,  "CDC-NNDSS-sample"),
        ("48079", "2024-10-01",  2, 1, 0.00,  0,  0.0,  "CDC-NNDSS-sample"),
        ("48445", "2024-10-01",  3, 1, 0.00,  0,  0.0,  "CDC-NNDSS-sample"),
        ("48317", "2024-10-01",  1, 0, 0.00,  0,  0.0,  "CDC-NNDSS-sample"),
        ("48115", "2024-10-01",  0, 0, 0.00,  0,  0.0,  "CDC-NNDSS-sample"),
        ("48003", "2024-10-01",  1, 0, 0.15,  8,  0.0,  "CDC-NNDSS-sample"),
        ("48303", "2024-10-01",  2, 1, 0.20, 42,  0.1,  "CDC-NNDSS-sample"),
        ("48329", "2024-10-01",  1, 0, 0.10, 20,  0.0,  "CDC-NNDSS-sample"),
        ("48135", "2024-10-01",  0, 0, 0.08, 18,  0.0,  "CDC-NNDSS-sample"),
        ("48451", "2024-10-01",  0, 0, 0.05, 12,  0.0,  "CDC-NNDSS-sample"),
        ("48375", "2024-10-01",  0, 0, 0.12, 15,  0.0,  "CDC-NNDSS-sample"),
        ("48381", "2024-10-01",  0, 0, 0.08, 18,  0.0,  "CDC-NNDSS-sample"),
        ("48189", "2024-10-01",  0, 0, 0.00,  0,  0.0,  "CDC-NNDSS-sample"),
        ("48453", "2024-10-01",  1, 0, 0.18, 85,  0.0,  "CDC-NNDSS-sample"),
        ("48201", "2024-10-01",  3, 1, 0.22,380,  0.1,  "CDC-NNDSS-sample"),
        ("48113", "2024-10-01",  2, 0, 0.20,240,  0.0,  "CDC-NNDSS-sample"),
        ("48439", "2024-10-01",  1, 0, 0.15,180,  0.0,  "CDC-NNDSS-sample"),
        ("48029", "2024-10-01",  0, 0, 0.12,145,  0.0,  "CDC-NNDSS-sample"),
        ("48085", "2024-10-01",  0, 0, 0.10, 80,  0.0,  "CDC-NNDSS-sample"),
        ("48491", "2024-10-01",  0, 0, 0.08, 60,  0.0,  "CDC-NNDSS-sample"),
        ("48141", "2024-10-01",  0, 0, 0.15, 92,  0.0,  "CDC-NNDSS-sample"),
        ("48479", "2024-10-01",  0, 0, 0.10, 38,  0.0,  "CDC-NNDSS-sample"),
        ("48215", "2024-10-01",  1, 0, 0.18,115,  0.1,  "CDC-NNDSS-sample"),
        ("48061", "2024-10-01",  0, 0, 0.12, 62,  0.0,  "CDC-NNDSS-sample"),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO surveillance VALUES (?,?,?,?,?,?,?,?)",
        surv_rows,
    )

    # network_metrics: (fips, metric_date, district_count, enrollment, mobility, border, religious_idx)
    net_rows = [
        ("48169", "2024-10-01",  1,  1_850, 0.45, False, 0.72),
        ("48501", "2024-10-01",  1,    620, 0.40, False, 0.68),
        ("48079", "2024-10-01",  1,    490, 0.35, False, 0.65),
        ("48445", "2024-10-01",  2,  1_120, 0.38, False, 0.61),
        ("48317", "2024-10-01",  1,    680, 0.36, False, 0.58),
        ("48115", "2024-10-01",  2,  1_380, 0.42, False, 0.55),
        ("48003", "2024-10-01",  2,  2_100, 0.44, False, 0.52),
        ("48303", "2024-10-01", 12, 52_800, 0.72, False, 0.45),
        ("48329", "2024-10-01",  5, 23_400, 0.68, False, 0.43),
        ("48135", "2024-10-01",  6, 30_200, 0.65, False, 0.42),
        ("48451", "2024-10-01",  8, 19_800, 0.60, False, 0.38),
        ("48375", "2024-10-01",  6, 16_700, 0.62, False, 0.44),
        ("48381", "2024-10-01",  4, 22_400, 0.58, False, 0.35),
        ("48189", "2024-10-01",  3,  6_800, 0.50, False, 0.50),
        ("48453", "2024-10-01", 22,128_000, 0.85, False, 0.31),
        ("48201", "2024-10-01", 48,620_000, 0.92, False, 0.35),
        ("48113", "2024-10-01", 32,380_000, 0.91, False, 0.33),
        ("48439", "2024-10-01", 28,290_000, 0.89, False, 0.34),
        ("48029", "2024-10-01", 20,230_000, 0.87, False, 0.29),
        ("48085", "2024-10-01", 14,125_000, 0.82, False, 0.28),
        ("48491", "2024-10-01", 12, 95_000, 0.78, False, 0.27),
        ("48141", "2024-10-01", 14,145_000, 0.75, True,  0.32),
        ("48479", "2024-10-01",  6, 58_000, 0.78, True,  0.28),
        ("48215", "2024-10-01", 22,175_000, 0.80, True,  0.30),
        ("48061", "2024-10-01", 12, 95_000, 0.76, True,  0.31),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO network_metrics VALUES (?,?,?,?,?,?,?)",
        net_rows,
    )
