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

    con.execute("""
        CREATE TABLE IF NOT EXISTS news_cache (
            id           INTEGER PRIMARY KEY,
            fetched_at   TEXT NOT NULL,
            briefing     TEXT NOT NULL,
            sources_json TEXT DEFAULT '[]'
        )
    """)

    # Seed each state independently so adding a new state never requires wiping the DB
    def _state_missing(abbr: str) -> bool:
        r = con.execute("SELECT COUNT(*) FROM geographies WHERE state_abbr = ?", [abbr]).fetchone()
        return not r or r[0] == 0

    if _state_missing("TX"):
        _seed_texas(con)
    if _state_missing("ID"):
        _seed_idaho(con)
    if _state_missing("PA"):
        _seed_pennsylvania(con)


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


def _seed_idaho(con: duckdb.DuckDBPyConnection) -> None:
    """Seed realistic Idaho county data — all 44 counties, FIPS prefix 16."""

    geo_rows = [
        # fips, state_fips, state_abbr, county_name, full_name, population
        ("16001", "16", "ID", "Ada",        "Ada County, ID",          503_000),
        ("16003", "16", "ID", "Adams",      "Adams County, ID",          4_020),
        ("16005", "16", "ID", "Bannock",    "Bannock County, ID",       88_200),
        ("16007", "16", "ID", "Bear Lake",  "Bear Lake County, ID",      6_100),
        ("16009", "16", "ID", "Benewah",    "Benewah County, ID",        9_100),
        ("16011", "16", "ID", "Bingham",    "Bingham County, ID",       46_000),
        ("16013", "16", "ID", "Blaine",     "Blaine County, ID",        23_100),
        ("16015", "16", "ID", "Boise",      "Boise County, ID",          7_300),
        ("16017", "16", "ID", "Bonner",     "Bonner County, ID",        46_400),
        ("16019", "16", "ID", "Bonneville", "Bonneville County, ID",   119_000),
        ("16021", "16", "ID", "Boundary",   "Boundary County, ID",      12_300),
        ("16023", "16", "ID", "Butte",      "Butte County, ID",          2_500),
        ("16025", "16", "ID", "Camas",      "Camas County, ID",          1_100),
        ("16027", "16", "ID", "Canyon",     "Canyon County, ID",       241_000),
        ("16029", "16", "ID", "Caribou",    "Caribou County, ID",        7_100),
        ("16031", "16", "ID", "Cassia",     "Cassia County, ID",        24_100),
        ("16033", "16", "ID", "Clark",      "Clark County, ID",            820),
        ("16035", "16", "ID", "Clearwater", "Clearwater County, ID",     9_200),
        ("16037", "16", "ID", "Custer",     "Custer County, ID",         4_100),
        ("16039", "16", "ID", "Elmore",     "Elmore County, ID",        26_100),
        ("16041", "16", "ID", "Franklin",   "Franklin County, ID",      14_100),
        ("16043", "16", "ID", "Fremont",    "Fremont County, ID",       13_100),
        ("16045", "16", "ID", "Gem",        "Gem County, ID",           18_100),
        ("16047", "16", "ID", "Gooding",    "Gooding County, ID",       15_100),
        ("16049", "16", "ID", "Idaho",      "Idaho County, ID",         16_300),
        ("16051", "16", "ID", "Jefferson",  "Jefferson County, ID",     29_100),
        ("16053", "16", "ID", "Jerome",     "Jerome County, ID",        24_200),
        ("16055", "16", "ID", "Kootenai",   "Kootenai County, ID",     182_000),
        ("16057", "16", "ID", "Latah",      "Latah County, ID",         40_100),
        ("16059", "16", "ID", "Lemhi",      "Lemhi County, ID",          8_100),
        ("16061", "16", "ID", "Lewis",      "Lewis County, ID",          3_700),
        ("16063", "16", "ID", "Lincoln",    "Lincoln County, ID",        5_200),
        ("16065", "16", "ID", "Madison",    "Madison County, ID",       39_100),
        ("16067", "16", "ID", "Minidoka",   "Minidoka County, ID",      21_100),
        ("16069", "16", "ID", "Nez Perce",  "Nez Perce County, ID",     43_200),
        ("16071", "16", "ID", "Oneida",     "Oneida County, ID",         4_600),
        ("16073", "16", "ID", "Owyhee",     "Owyhee County, ID",        12_100),
        ("16075", "16", "ID", "Payette",    "Payette County, ID",       24_100),
        ("16077", "16", "ID", "Power",      "Power County, ID",          8_100),
        ("16079", "16", "ID", "Shoshone",   "Shoshone County, ID",      12_200),
        ("16081", "16", "ID", "Teton",      "Teton County, ID",         12_300),
        ("16083", "16", "ID", "Twin Falls", "Twin Falls County, ID",    89_100),
        ("16085", "16", "ID", "Valley",     "Valley County, ID",        11_200),
        ("16087", "16", "ID", "Washington", "Washington County, ID",    10_100),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO geographies VALUES (?,?,?,?,?,?)", geo_rows
    )

    # vaccination_coverage: (fips, school_year, mmr_pct, med_pct, nonmed_pct, enrolled, source)
    # Urban (Ada/Canyon/Kootenai): 90-93% MMR, 2-5% nonmed
    # High-risk resort (Blaine/Teton): 76-82% MMR, 9-12% nonmed
    # Cluster (Gem): 79% MMR, 8% nonmed
    # Border panhandle (Bonner/Boundary): 83-85% MMR, border_adjacent=True
    # Most rural: 82-88% MMR, 4-14% nonmed
    cov_rows = [
        ("16001", "2023-2024", 91.5, 0.4,  3.2, 75_450, "ID-IDHW-sample"),
        ("16003", "2023-2024", 85.0, 0.3,  7.5,    603, "ID-IDHW-sample"),
        ("16005", "2023-2024", 87.4, 0.3,  4.8, 13_230, "ID-IDHW-sample"),
        ("16007", "2023-2024", 84.0, 0.3,  8.2,    915, "ID-IDHW-sample"),
        ("16009", "2023-2024", 83.5, 0.2,  7.8,  1_365, "ID-IDHW-sample"),
        ("16011", "2023-2024", 86.1, 0.3,  5.6,  6_900, "ID-IDHW-sample"),
        ("16013", "2023-2024", 78.3, 0.5, 11.2,  3_465, "ID-IDHW-sample"),
        ("16015", "2023-2024", 84.5, 0.3,  7.0,  1_095, "ID-IDHW-sample"),
        ("16017", "2023-2024", 83.4, 0.3,  6.8,  6_960, "ID-IDHW-sample"),
        ("16019", "2023-2024", 87.8, 0.3,  4.5, 17_850, "ID-IDHW-sample"),
        ("16021", "2023-2024", 84.6, 0.2,  6.5,  1_845, "ID-IDHW-sample"),
        ("16023", "2023-2024", 84.0, 0.2,  8.0,    375, "ID-IDHW-sample"),
        ("16025", "2023-2024", 83.0, 0.3,  9.0,    165, "ID-IDHW-sample"),
        ("16027", "2023-2024", 90.2, 0.4,  4.1, 36_150, "ID-IDHW-sample"),
        ("16029", "2023-2024", 85.2, 0.3,  7.0,  1_065, "ID-IDHW-sample"),
        ("16031", "2023-2024", 86.0, 0.3,  6.2,  3_615, "ID-IDHW-sample"),
        ("16033", "2023-2024", 82.0, 0.2, 10.0,    123, "ID-IDHW-sample"),
        ("16035", "2023-2024", 83.5, 0.2,  7.5,  1_380, "ID-IDHW-sample"),
        ("16037", "2023-2024", 84.0, 0.3,  8.5,    615, "ID-IDHW-sample"),
        ("16039", "2023-2024", 86.5, 0.3,  5.8,  3_915, "ID-IDHW-sample"),
        ("16041", "2023-2024", 86.8, 0.3,  5.5,  2_115, "ID-IDHW-sample"),
        ("16043", "2023-2024", 85.5, 0.3,  6.5,  1_965, "ID-IDHW-sample"),
        ("16045", "2023-2024", 79.2, 0.4,  8.3,  2_715, "ID-IDHW-sample"),
        ("16047", "2023-2024", 85.5, 0.3,  6.0,  2_265, "ID-IDHW-sample"),
        ("16049", "2023-2024", 84.8, 0.2,  7.2,  2_445, "ID-IDHW-sample"),
        ("16051", "2023-2024", 86.4, 0.3,  5.8,  4_365, "ID-IDHW-sample"),
        ("16053", "2023-2024", 86.2, 0.3,  5.9,  3_630, "ID-IDHW-sample"),
        ("16055", "2023-2024", 92.1, 0.4,  2.8, 27_300, "ID-IDHW-sample"),
        ("16057", "2023-2024", 88.5, 0.4,  4.2,  6_015, "ID-IDHW-sample"),
        ("16059", "2023-2024", 84.2, 0.2,  8.0,  1_215, "ID-IDHW-sample"),
        ("16061", "2023-2024", 83.8, 0.2,  7.8,    555, "ID-IDHW-sample"),
        ("16063", "2023-2024", 84.5, 0.3,  7.5,    780, "ID-IDHW-sample"),
        ("16065", "2023-2024", 86.0, 0.3,  5.5,  5_865, "ID-IDHW-sample"),
        ("16067", "2023-2024", 85.8, 0.3,  6.0,  3_165, "ID-IDHW-sample"),
        ("16069", "2023-2024", 88.3, 0.3,  4.5,  6_480, "ID-IDHW-sample"),
        ("16071", "2023-2024", 85.0, 0.3,  7.0,    690, "ID-IDHW-sample"),
        ("16073", "2023-2024", 84.0, 0.3,  7.5,  1_815, "ID-IDHW-sample"),
        ("16075", "2023-2024", 85.5, 0.3,  6.5,  3_615, "ID-IDHW-sample"),
        ("16077", "2023-2024", 84.8, 0.3,  6.8,  1_215, "ID-IDHW-sample"),
        ("16079", "2023-2024", 83.8, 0.2,  7.0,  1_830, "ID-IDHW-sample"),
        ("16081", "2023-2024", 77.2, 0.5,  9.1,  1_845, "ID-IDHW-sample"),
        ("16083", "2023-2024", 88.1, 0.3,  4.8, 13_365, "ID-IDHW-sample"),
        ("16085", "2023-2024", 83.5, 0.4,  7.5,  1_680, "ID-IDHW-sample"),
        ("16087", "2023-2024", 85.0, 0.3,  7.0,  1_515, "ID-IDHW-sample"),
    ]
    con.executemany(
        """INSERT OR IGNORE INTO vaccination_coverage
           (fips, school_year, mmr_coverage_pct, medical_exempt_pct,
            nonmedical_exempt_pct, enrolled, source)
           VALUES (?,?,?,?,?,?,?)""",
        cov_rows,
    )

    # network_metrics: (fips, metric_date, district_count, enrollment, mobility, border, religious_idx)
    # border_adjacent=True for Bonner (16017) and Boundary (16021) — Canadian border
    # religious_community_idx: Madison 0.65 (LDS), Gem/Teton/Blaine 0.58-0.65, most rural 0.40-0.52
    net_rows = [
        ("16001", "2024-10-01", 12, 75_450, 0.82, False, 0.38),
        ("16003", "2024-10-01",  1,    603, 0.32, False, 0.48),
        ("16005", "2024-10-01",  4, 13_230, 0.68, False, 0.43),
        ("16007", "2024-10-01",  1,    915, 0.34, False, 0.50),
        ("16009", "2024-10-01",  1,  1_365, 0.36, False, 0.45),
        ("16011", "2024-10-01",  3,  6_900, 0.48, False, 0.48),
        ("16013", "2024-10-01",  2,  3_465, 0.55, False, 0.58),
        ("16015", "2024-10-01",  1,  1_095, 0.36, False, 0.44),
        ("16017", "2024-10-01",  4,  6_960, 0.50, True,  0.42),
        ("16019", "2024-10-01",  5, 17_850, 0.72, False, 0.44),
        ("16021", "2024-10-01",  1,  1_845, 0.38, True,  0.41),
        ("16023", "2024-10-01",  1,    375, 0.30, False, 0.46),
        ("16025", "2024-10-01",  1,    165, 0.28, False, 0.44),
        ("16027", "2024-10-01",  8, 36_150, 0.78, False, 0.40),
        ("16029", "2024-10-01",  1,  1_065, 0.34, False, 0.50),
        ("16031", "2024-10-01",  2,  3_615, 0.44, False, 0.46),
        ("16033", "2024-10-01",  1,    123, 0.26, False, 0.47),
        ("16035", "2024-10-01",  1,  1_380, 0.36, False, 0.43),
        ("16037", "2024-10-01",  1,    615, 0.30, False, 0.45),
        ("16039", "2024-10-01",  2,  3_915, 0.50, False, 0.42),
        ("16041", "2024-10-01",  2,  2_115, 0.40, False, 0.55),
        ("16043", "2024-10-01",  2,  1_965, 0.40, False, 0.48),
        ("16045", "2024-10-01",  2,  2_715, 0.42, False, 0.62),
        ("16047", "2024-10-01",  2,  2_265, 0.40, False, 0.44),
        ("16049", "2024-10-01",  2,  2_445, 0.38, False, 0.45),
        ("16051", "2024-10-01",  3,  4_365, 0.46, False, 0.52),
        ("16053", "2024-10-01",  2,  3_630, 0.44, False, 0.44),
        ("16055", "2024-10-01",  7, 27_300, 0.80, False, 0.36),
        ("16057", "2024-10-01",  3,  6_015, 0.60, False, 0.40),
        ("16059", "2024-10-01",  1,  1_215, 0.32, False, 0.44),
        ("16061", "2024-10-01",  1,    555, 0.32, False, 0.43),
        ("16063", "2024-10-01",  1,    780, 0.34, False, 0.46),
        ("16065", "2024-10-01",  3,  5_865, 0.52, False, 0.65),
        ("16067", "2024-10-01",  2,  3_165, 0.44, False, 0.44),
        ("16069", "2024-10-01",  3,  6_480, 0.58, False, 0.40),
        ("16071", "2024-10-01",  1,    690, 0.32, False, 0.50),
        ("16073", "2024-10-01",  1,  1_815, 0.38, False, 0.43),
        ("16075", "2024-10-01",  2,  3_615, 0.44, False, 0.44),
        ("16077", "2024-10-01",  1,  1_215, 0.34, False, 0.44),
        ("16079", "2024-10-01",  1,  1_830, 0.38, False, 0.43),
        ("16081", "2024-10-01",  1,  1_845, 0.52, False, 0.60),
        ("16083", "2024-10-01",  4, 13_365, 0.70, False, 0.42),
        ("16085", "2024-10-01",  1,  1_680, 0.40, False, 0.44),
        ("16087", "2024-10-01",  1,  1_515, 0.38, False, 0.44),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO network_metrics VALUES (?,?,?,?,?,?,?)",
        net_rows,
    )


def _seed_pennsylvania(con: duckdb.DuckDBPyConnection) -> None:
    """Seed realistic Pennsylvania county data — all 67 counties, FIPS prefix 42."""

    geo_rows = [
        # fips, state_fips, state_abbr, county_name, full_name, population
        ("42001", "42", "PA", "Adams",          "Adams County, PA",          104_000),
        ("42003", "42", "PA", "Allegheny",      "Allegheny County, PA",    1_260_000),
        ("42005", "42", "PA", "Armstrong",      "Armstrong County, PA",       65_000),
        ("42007", "42", "PA", "Beaver",         "Beaver County, PA",         166_000),
        ("42009", "42", "PA", "Bedford",        "Bedford County, PA",         49_000),
        ("42011", "42", "PA", "Berks",          "Berks County, PA",          432_000),
        ("42013", "42", "PA", "Blair",          "Blair County, PA",          123_000),
        ("42015", "42", "PA", "Bradford",       "Bradford County, PA",        62_000),
        ("42017", "42", "PA", "Bucks",          "Bucks County, PA",          646_000),
        ("42019", "42", "PA", "Butler",         "Butler County, PA",         202_000),
        ("42021", "42", "PA", "Cambria",        "Cambria County, PA",        130_000),
        ("42023", "42", "PA", "Cameron",        "Cameron County, PA",          5_100),
        ("42025", "42", "PA", "Carbon",         "Carbon County, PA",          66_000),
        ("42027", "42", "PA", "Centre",         "Centre County, PA",         162_000),
        ("42029", "42", "PA", "Chester",        "Chester County, PA",        545_000),
        ("42031", "42", "PA", "Clarion",        "Clarion County, PA",         39_000),
        ("42033", "42", "PA", "Clearfield",     "Clearfield County, PA",      81_000),
        ("42035", "42", "PA", "Clinton",        "Clinton County, PA",         38_000),
        ("42037", "42", "PA", "Columbia",       "Columbia County, PA",        67_000),
        ("42039", "42", "PA", "Crawford",       "Crawford County, PA",        86_000),
        ("42041", "42", "PA", "Cumberland",     "Cumberland County, PA",     262_000),
        ("42043", "42", "PA", "Dauphin",        "Dauphin County, PA",        286_000),
        ("42045", "42", "PA", "Delaware",       "Delaware County, PA",       576_000),
        ("42047", "42", "PA", "Elk",            "Elk County, PA",             30_000),
        ("42049", "42", "PA", "Erie",           "Erie County, PA",           269_000),
        ("42051", "42", "PA", "Fayette",        "Fayette County, PA",        130_000),
        ("42053", "42", "PA", "Forest",         "Forest County, PA",           7_100),
        ("42055", "42", "PA", "Franklin",       "Franklin County, PA",       155_000),
        ("42057", "42", "PA", "Fulton",         "Fulton County, PA",          15_000),
        ("42059", "42", "PA", "Greene",         "Greene County, PA",          37_000),
        ("42061", "42", "PA", "Huntingdon",     "Huntingdon County, PA",      45_000),
        ("42063", "42", "PA", "Indiana",        "Indiana County, PA",         85_000),
        ("42065", "42", "PA", "Jefferson",      "Jefferson County, PA",       44_000),
        ("42067", "42", "PA", "Juniata",        "Juniata County, PA",         24_000),
        ("42069", "42", "PA", "Lackawanna",     "Lackawanna County, PA",     215_000),
        ("42071", "42", "PA", "Lancaster",      "Lancaster County, PA",      552_000),
        ("42073", "42", "PA", "Lawrence",       "Lawrence County, PA",        88_000),
        ("42075", "42", "PA", "Lebanon",        "Lebanon County, PA",        142_000),
        ("42077", "42", "PA", "Lehigh",         "Lehigh County, PA",         374_000),
        ("42079", "42", "PA", "Luzerne",        "Luzerne County, PA",        319_000),
        ("42081", "42", "PA", "Lycoming",       "Lycoming County, PA",       116_000),
        ("42083", "42", "PA", "McKean",         "McKean County, PA",          42_000),
        ("42085", "42", "PA", "Mercer",         "Mercer County, PA",         112_000),
        ("42087", "42", "PA", "Mifflin",        "Mifflin County, PA",         46_000),
        ("42089", "42", "PA", "Monroe",         "Monroe County, PA",         175_000),
        ("42091", "42", "PA", "Montgomery",     "Montgomery County, PA",     870_000),
        ("42093", "42", "PA", "Montour",        "Montour County, PA",         19_000),
        ("42095", "42", "PA", "Northampton",    "Northampton County, PA",    313_000),
        ("42097", "42", "PA", "Northumberland", "Northumberland County, PA",  93_000),
        ("42099", "42", "PA", "Perry",          "Perry County, PA",           46_000),
        ("42101", "42", "PA", "Philadelphia",   "Philadelphia County, PA", 1_600_000),
        ("42103", "42", "PA", "Pike",           "Pike County, PA",            57_000),
        ("42105", "42", "PA", "Potter",         "Potter County, PA",          16_000),
        ("42107", "42", "PA", "Schuylkill",     "Schuylkill County, PA",     142_000),
        ("42109", "42", "PA", "Snyder",         "Snyder County, PA",          40_000),
        ("42111", "42", "PA", "Somerset",       "Somerset County, PA",        73_000),
        ("42113", "42", "PA", "Sullivan",       "Sullivan County, PA",         6_200),
        ("42115", "42", "PA", "Susquehanna",    "Susquehanna County, PA",     42_000),
        ("42117", "42", "PA", "Tioga",          "Tioga County, PA",           41_000),
        ("42119", "42", "PA", "Union",          "Union County, PA",           44_000),
        ("42121", "42", "PA", "Venango",        "Venango County, PA",         52_000),
        ("42123", "42", "PA", "Warren",         "Warren County, PA",          40_000),
        ("42125", "42", "PA", "Washington",     "Washington County, PA",     208_000),
        ("42127", "42", "PA", "Wayne",          "Wayne County, PA",           52_000),
        ("42129", "42", "PA", "Westmoreland",   "Westmoreland County, PA",   349_000),
        ("42131", "42", "PA", "Wyoming",        "Wyoming County, PA",         28_000),
        ("42133", "42", "PA", "York",           "York County, PA",           456_000),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO geographies VALUES (?,?,?,?,?,?)", geo_rows
    )

    # vaccination_coverage: (fips, school_year, mmr_pct, med_pct, nonmed_pct, enrolled, source)
    # PA allows religious exemptions ONLY — nonmed rates 0.5-3% statewide
    # Amish belt (Lancaster/Mifflin/Juniata/Snyder): historically very low MMR;
    #   low official exemption pcts because many Amish children are not in the school system
    # Urban SE collar: Philadelphia 97%, Montgomery/Delaware/Chester 96%, Bucks 95%, Allegheny 94%
    # enrolled = ~15% of county population
    cov_rows = [
        ("42001", "2023-2024", 90.2, 0.3, 1.6,  15_600, "PA-DOH-sample"),
        ("42003", "2023-2024", 94.1, 0.5, 1.0, 189_000, "PA-DOH-sample"),
        ("42005", "2023-2024", 89.5, 0.2, 1.8,   9_750, "PA-DOH-sample"),
        ("42007", "2023-2024", 91.1, 0.3, 1.4,  24_900, "PA-DOH-sample"),
        ("42009", "2023-2024", 89.2, 0.2, 2.0,   7_350, "PA-DOH-sample"),
        ("42011", "2023-2024", 92.3, 0.3, 1.4,  64_800, "PA-DOH-sample"),
        ("42013", "2023-2024", 90.4, 0.3, 1.6,  18_450, "PA-DOH-sample"),
        ("42015", "2023-2024", 89.3, 0.2, 2.0,   9_300, "PA-DOH-sample"),
        ("42017", "2023-2024", 95.4, 0.4, 0.9,  96_900, "PA-DOH-sample"),
        ("42019", "2023-2024", 92.1, 0.4, 1.3,  30_300, "PA-DOH-sample"),
        ("42021", "2023-2024", 90.1, 0.3, 1.6,  19_500, "PA-DOH-sample"),
        ("42023", "2023-2024", 88.5, 0.2, 2.2,     765, "PA-DOH-sample"),
        ("42025", "2023-2024", 89.4, 0.3, 1.9,   9_900, "PA-DOH-sample"),
        ("42027", "2023-2024", 91.3, 0.4, 1.5,  24_300, "PA-DOH-sample"),
        ("42029", "2023-2024", 96.1, 0.3, 0.8,  81_750, "PA-DOH-sample"),
        ("42031", "2023-2024", 89.1, 0.2, 2.0,   5_850, "PA-DOH-sample"),
        ("42033", "2023-2024", 89.3, 0.2, 2.0,  12_150, "PA-DOH-sample"),
        ("42035", "2023-2024", 89.0, 0.2, 2.1,   5_700, "PA-DOH-sample"),
        ("42037", "2023-2024", 90.2, 0.3, 1.7,  10_050, "PA-DOH-sample"),
        ("42039", "2023-2024", 89.4, 0.2, 1.9,  12_900, "PA-DOH-sample"),
        ("42041", "2023-2024", 93.2, 0.4, 1.2,  39_300, "PA-DOH-sample"),
        ("42043", "2023-2024", 92.5, 0.4, 1.3,  42_900, "PA-DOH-sample"),
        ("42045", "2023-2024", 96.0, 0.4, 0.9,  86_400, "PA-DOH-sample"),
        ("42047", "2023-2024", 89.2, 0.2, 1.9,   4_500, "PA-DOH-sample"),
        ("42049", "2023-2024", 91.4, 0.3, 1.5,  40_350, "PA-DOH-sample"),
        ("42051", "2023-2024", 89.5, 0.3, 1.8,  19_500, "PA-DOH-sample"),
        ("42053", "2023-2024", 88.0, 0.2, 2.3,   1_065, "PA-DOH-sample"),
        ("42055", "2023-2024", 90.3, 0.3, 1.7,  23_250, "PA-DOH-sample"),
        ("42057", "2023-2024", 89.1, 0.2, 2.2,   2_250, "PA-DOH-sample"),
        ("42059", "2023-2024", 88.4, 0.2, 2.2,   5_550, "PA-DOH-sample"),
        ("42061", "2023-2024", 89.2, 0.2, 2.1,   6_750, "PA-DOH-sample"),
        ("42063", "2023-2024", 89.4, 0.3, 1.9,  12_750, "PA-DOH-sample"),
        ("42065", "2023-2024", 89.1, 0.2, 2.0,   6_600, "PA-DOH-sample"),
        ("42067", "2023-2024", 74.2, 0.2, 2.0,   3_600, "PA-DOH-sample"),
        ("42069", "2023-2024", 92.0, 0.3, 1.4,  32_250, "PA-DOH-sample"),
        ("42071", "2023-2024", 72.1, 0.3, 2.1,  82_800, "PA-DOH-sample"),
        ("42073", "2023-2024", 90.3, 0.3, 1.6,  13_200, "PA-DOH-sample"),
        ("42075", "2023-2024", 91.0, 0.3, 1.6,  21_300, "PA-DOH-sample"),
        ("42077", "2023-2024", 93.1, 0.4, 1.2,  56_100, "PA-DOH-sample"),
        ("42079", "2023-2024", 91.2, 0.3, 1.6,  47_850, "PA-DOH-sample"),
        ("42081", "2023-2024", 90.1, 0.3, 1.7,  17_400, "PA-DOH-sample"),
        ("42083", "2023-2024", 89.3, 0.2, 2.0,   6_300, "PA-DOH-sample"),
        ("42085", "2023-2024", 90.2, 0.3, 1.6,  16_800, "PA-DOH-sample"),
        ("42087", "2023-2024", 68.4, 0.2, 1.8,   6_900, "PA-DOH-sample"),
        ("42089", "2023-2024", 90.5, 0.3, 1.8,  26_250, "PA-DOH-sample"),
        ("42091", "2023-2024", 96.2, 0.4, 0.8, 130_500, "PA-DOH-sample"),
        ("42093", "2023-2024", 90.5, 0.3, 1.5,   2_850, "PA-DOH-sample"),
        ("42095", "2023-2024", 93.3, 0.4, 1.1,  46_950, "PA-DOH-sample"),
        ("42097", "2023-2024", 89.4, 0.3, 1.8,  13_950, "PA-DOH-sample"),
        ("42099", "2023-2024", 89.1, 0.2, 2.1,   6_900, "PA-DOH-sample"),
        ("42101", "2023-2024", 97.0, 0.4, 0.6, 240_000, "PA-DOH-sample"),
        ("42103", "2023-2024", 89.3, 0.3, 1.9,   8_550, "PA-DOH-sample"),
        ("42105", "2023-2024", 88.2, 0.2, 2.3,   2_400, "PA-DOH-sample"),
        ("42107", "2023-2024", 89.5, 0.3, 1.8,  21_300, "PA-DOH-sample"),
        ("42109", "2023-2024", 76.3, 0.2, 1.5,   6_000, "PA-DOH-sample"),
        ("42111", "2023-2024", 88.3, 0.2, 2.2,  10_950, "PA-DOH-sample"),
        ("42113", "2023-2024", 88.1, 0.2, 2.4,     930, "PA-DOH-sample"),
        ("42115", "2023-2024", 89.2, 0.2, 2.0,   6_300, "PA-DOH-sample"),
        ("42117", "2023-2024", 89.0, 0.2, 2.1,   6_150, "PA-DOH-sample"),
        ("42119", "2023-2024", 89.3, 0.3, 1.9,   6_600, "PA-DOH-sample"),
        ("42121", "2023-2024", 89.2, 0.2, 2.0,   7_800, "PA-DOH-sample"),
        ("42123", "2023-2024", 89.1, 0.2, 2.1,   6_000, "PA-DOH-sample"),
        ("42125", "2023-2024", 92.2, 0.4, 1.3,  31_200, "PA-DOH-sample"),
        ("42127", "2023-2024", 89.2, 0.3, 1.9,   7_800, "PA-DOH-sample"),
        ("42129", "2023-2024", 91.5, 0.3, 1.5,  52_350, "PA-DOH-sample"),
        ("42131", "2023-2024", 89.0, 0.2, 2.0,   4_200, "PA-DOH-sample"),
        ("42133", "2023-2024", 92.0, 0.3, 1.4,  68_400, "PA-DOH-sample"),
    ]
    con.executemany(
        """INSERT OR IGNORE INTO vaccination_coverage
           (fips, school_year, mmr_coverage_pct, medical_exempt_pct,
            nonmedical_exempt_pct, enrolled, source)
           VALUES (?,?,?,?,?,?,?)""",
        cov_rows,
    )

    # network_metrics: (fips, metric_date, district_count, enrollment, mobility, border, religious_idx)
    # border_adjacent=False for all PA counties (no international border)
    # religious_community_idx: Lancaster 0.90, Mifflin 0.88, Juniata 0.82, Snyder 0.75, Somerset 0.65
    #   urban SE: 0.25-0.32; suburban: 0.30-0.45; rural: 0.40-0.55
    net_rows = [
        ("42001", "2024-10-01",  4,  15_600, 0.65, False, 0.45),
        ("42003", "2024-10-01", 42, 189_000, 0.88, False, 0.28),
        ("42005", "2024-10-01",  4,   9_750, 0.52, False, 0.44),
        ("42007", "2024-10-01",  8,  24_900, 0.68, False, 0.40),
        ("42009", "2024-10-01",  3,   7_350, 0.50, False, 0.60),
        ("42011", "2024-10-01", 18,  64_800, 0.80, False, 0.40),
        ("42013", "2024-10-01",  6,  18_450, 0.62, False, 0.42),
        ("42015", "2024-10-01",  4,   9_300, 0.52, False, 0.48),
        ("42017", "2024-10-01", 13,  96_900, 0.85, False, 0.32),
        ("42019", "2024-10-01", 12,  30_300, 0.76, False, 0.38),
        ("42021", "2024-10-01",  8,  19_500, 0.60, False, 0.42),
        ("42023", "2024-10-01",  1,     765, 0.38, False, 0.46),
        ("42025", "2024-10-01",  4,   9_900, 0.58, False, 0.44),
        ("42027", "2024-10-01",  6,  24_300, 0.70, False, 0.36),
        ("42029", "2024-10-01", 14,  81_750, 0.84, False, 0.32),
        ("42031", "2024-10-01",  3,   5_850, 0.48, False, 0.44),
        ("42033", "2024-10-01",  4,  12_150, 0.52, False, 0.44),
        ("42035", "2024-10-01",  3,   5_700, 0.48, False, 0.46),
        ("42037", "2024-10-01",  4,  10_050, 0.55, False, 0.44),
        ("42039", "2024-10-01",  6,  12_900, 0.55, False, 0.44),
        ("42041", "2024-10-01",  8,  39_300, 0.82, False, 0.38),
        ("42043", "2024-10-01", 12,  42_900, 0.80, False, 0.38),
        ("42045", "2024-10-01", 18,  86_400, 0.85, False, 0.30),
        ("42047", "2024-10-01",  2,   4_500, 0.48, False, 0.44),
        ("42049", "2024-10-01",  8,  40_350, 0.76, False, 0.35),
        ("42051", "2024-10-01",  8,  19_500, 0.60, False, 0.42),
        ("42053", "2024-10-01",  1,   1_065, 0.36, False, 0.46),
        ("42055", "2024-10-01",  6,  23_250, 0.68, False, 0.45),
        ("42057", "2024-10-01",  1,   2_250, 0.42, False, 0.60),
        ("42059", "2024-10-01",  3,   5_550, 0.48, False, 0.44),
        ("42061", "2024-10-01",  4,   6_750, 0.50, False, 0.55),
        ("42063", "2024-10-01",  6,  12_750, 0.55, False, 0.44),
        ("42065", "2024-10-01",  3,   6_600, 0.50, False, 0.44),
        ("42067", "2024-10-01",  2,   3_600, 0.45, False, 0.82),
        ("42069", "2024-10-01",  8,  32_250, 0.74, False, 0.35),
        ("42071", "2024-10-01", 16,  82_800, 0.72, False, 0.90),
        ("42073", "2024-10-01",  6,  13_200, 0.62, False, 0.40),
        ("42075", "2024-10-01",  6,  21_300, 0.72, False, 0.45),
        ("42077", "2024-10-01",  8,  56_100, 0.82, False, 0.38),
        ("42079", "2024-10-01", 14,  47_850, 0.75, False, 0.36),
        ("42081", "2024-10-01",  6,  17_400, 0.60, False, 0.44),
        ("42083", "2024-10-01",  3,   6_300, 0.50, False, 0.44),
        ("42085", "2024-10-01",  8,  16_800, 0.60, False, 0.40),
        ("42087", "2024-10-01",  3,   6_900, 0.48, False, 0.88),
        ("42089", "2024-10-01",  6,  26_250, 0.72, False, 0.38),
        ("42091", "2024-10-01", 22, 130_500, 0.86, False, 0.30),
        ("42093", "2024-10-01",  2,   2_850, 0.55, False, 0.42),
        ("42095", "2024-10-01",  8,  46_950, 0.80, False, 0.37),
        ("42097", "2024-10-01",  4,  13_950, 0.55, False, 0.44),
        ("42099", "2024-10-01",  3,   6_900, 0.50, False, 0.50),
        ("42101", "2024-10-01",  1, 240_000, 0.92, False, 0.25),
        ("42103", "2024-10-01",  3,   8_550, 0.58, False, 0.42),
        ("42105", "2024-10-01",  2,   2_400, 0.40, False, 0.46),
        ("42107", "2024-10-01",  6,  21_300, 0.58, False, 0.44),
        ("42109", "2024-10-01",  3,   6_000, 0.50, False, 0.75),
        ("42111", "2024-10-01",  4,  10_950, 0.55, False, 0.65),
        ("42113", "2024-10-01",  1,     930, 0.36, False, 0.46),
        ("42115", "2024-10-01",  3,   6_300, 0.50, False, 0.46),
        ("42117", "2024-10-01",  4,   6_150, 0.50, False, 0.46),
        ("42119", "2024-10-01",  3,   6_600, 0.52, False, 0.58),
        ("42121", "2024-10-01",  4,   7_800, 0.52, False, 0.44),
        ("42123", "2024-10-01",  3,   6_000, 0.50, False, 0.44),
        ("42125", "2024-10-01", 14,  31_200, 0.75, False, 0.38),
        ("42127", "2024-10-01",  3,   7_800, 0.55, False, 0.44),
        ("42129", "2024-10-01", 16,  52_350, 0.78, False, 0.38),
        ("42131", "2024-10-01",  2,   4_200, 0.48, False, 0.46),
        ("42133", "2024-10-01", 16,  68_400, 0.78, False, 0.45),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO network_metrics VALUES (?,?,?,?,?,?,?)",
        net_rows,
    )
