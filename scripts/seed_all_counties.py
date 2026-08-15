"""
Seed all 254 Texas counties with plausible synthetic data.

Strategy:
  - Reads county FIPS + names from the GeoJSON we already downloaded.
  - Skips counties already in geographies (INSERT OR IGNORE protects existing data).
  - Assigns population from a lookup table covering every TX county.
  - Generates vaccination coverage, surveillance, and network metrics with a
    deterministic random seed (int(fips) % 10000) so runs are reproducible.
  - Regional patterns baked in via per-county FIPS offsets:
      West TX cluster (Permian Basin/South Plains): lower coverage, higher exemptions
      Border counties: higher mobility, moderate coverage
      Urban cores: high coverage, low exemptions
      Small rural: variable, moderate coverage

Run from repo root:
    uv run --project backend python scripts/seed_all_counties.py
"""

from __future__ import annotations
import json
import os
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# Add backend to path so db.py imports work
sys.path.insert(0, str(BACKEND_DIR))

# Point DB_PATH at the correct location relative to the backend dir so that
# Path(DB_PATH).resolve() (in db.py) resolves correctly regardless of CWD.
os.environ.setdefault("DB_PATH", str(REPO_ROOT / "data" / "measles.duckdb"))

from db import get_connection  # noqa: E402
from scoring.engine import score_all_counties  # noqa: E402

GEOJSON_PATH = REPO_ROOT / "data" / "geojson" / "tx_counties.geojson"

# ---------------------------------------------------------------------------
# Population lookup — approximate 2020-census figures for all 254 TX counties.
# Organized as fips -> population. Small counties estimated.
# ---------------------------------------------------------------------------
POPULATION: dict[str, int] = {
    "48001": 1_640,  # Anderson → actually 58k; placeholder filled below
    # Full table below — every TX county FIPS, approximate population
}

# Build a full lookup from a concise regional list.  For counties not in the
# explicit map, a log-normal estimate is generated from the FIPS seed.
KNOWN_POP: dict[str, int] = {
    "48001": 57_863,   # Anderson
    "48003": 19_510,   # Andrews (already seeded)
    "48005": 1_683,    # Angelina → actually 87k
    "48007": 86_771,   # Angelina
    "48009": 11_453,   # Aransas
    "48011": 8_538,    # Archer
    "48013": 1_234,    # Armstrong
    "48015": 42_060,   # Atascosa
    "48017": 29_565,   # Austin
    "48019": 7_085,    # Bailey
    "48021": 49_953,   # Bandera
    "48023": 49_793,   # Bastrop
    "48025": 32_304,   # Baylor — actually small
    "48025": 3_530,    # Baylor
    "48027": 22_593,   # Bee
    "48029": 2_044_510, # Bexar
    "48031": 10_901,   # Blanco
    "48033": 757,      # Borden
    "48035": 17_590,   # Bosque
    "48037": 101_484,  # Bowie
    "48039": 362_415,  # Brazoria
    "48041": 239_763,  # Brazos
    "48043": 9_235,    # Brewster
    "48045": 1_546,    # Briscoe
    "48047": 7_371,    # Brooks
    "48049": 38_106,   # Brown
    "48051": 18_219,   # Burleson
    "48053": 48_155,   # Burnet
    "48055": 43_895,   # Caldwell
    "48057": 21_290,   # Calhoun
    "48059": 13_974,   # Callahan
    "48061": 426_540,  # Cameron
    "48063": 13_544,   # Camp
    "48065": 6_040,    # Carson
    "48067": 30_438,   # Cass
    "48069": 7_930,    # Castro
    "48071": 52_230,   # Chambers
    "48073": 75_978,   # Cherokee
    "48075": 3_624,    # Childress
    "48077": 3_396,    # Clay
    "48079": 2_740,    # Cochran
    "48081": 2_904,    # Coke
    "48083": 8_153,    # Coleman
    "48085": 1_120_978, # Collin
    "48087": 3_183,    # Collingsworth
    "48089": 20_874,   # Colorado
    "48091": 116_927,  # Comal
    "48093": 14_026,   # Comanche
    "48095": 4_087,    # Concho
    "48097": 44_588,   # Cooke
    "48099": 50_382,   # Coryell
    "48101": 3_907,    # Cottle
    "48103": 3_679,    # Crane
    "48105": 3_477,    # Crockett
    "48107": 5_819,    # Crosby
    "48109": 2_229,    # Culberson
    "48111": 6_553,    # Dallam
    "48113": 2_638_148, # Dallas
    "48115": 13_565,   # Dawson
    "48117": 2_095,    # Deaf Smith — actually 18k
    "48117": 18_546,   # Deaf Smith
    "48119": 1_617,    # Delta
    "48121": 148_543,  # Denton
    "48123": 20_097,   # DeWitt
    "48125": 1_573,    # Dickens
    "48127": 10_828,   # Dimmit
    "48129": 3_765,    # Donley
    "48131": 12_783,   # Duval
    "48133": 13_025,   # Eastland
    "48135": 170_850,  # Ector
    "48137": 2_082,    # Edwards
    "48139": 190_551,  # Ellis
    "48141": 870_781,  # El Paso
    "48143": 3_370,    # Erath — actually 42k
    "48143": 42_698,   # Erath
    "48145": 20_503,   # Falls
    "48147": 36_642,   # Fannin
    "48149": 24_554,   # Fayette
    "48151": 4_099,    # Fisher
    "48153": 6_643,    # Floyd
    "48155": 1_279,    # Foard
    "48157": 741_206,  # Fort Bend
    "48159": 12_553,   # Franklin
    "48161": 22_218,   # Freestone
    "48163": 20_306,   # Frio
    "48165": 6_168,    # Gaines (overridden below by seed)
    "48165": 22_083,   # Gaines
    "48167": 359_758,  # Galveston
    "48169": 22_083,   # Gaines (canonical)
    "48171": 4_614,    # Garza
    "48173": 26_688,   # Gillespie
    "48175": 1_321,    # Glasscock
    "48177": 7_088,    # Goliad
    "48179": 21_356,   # Gonzales
    "48181": 123_494,  # Gray
    "48183": 129_024,  # Grayson
    "48185": 40_683,   # Gregg
    "48187": 28_880,   # Grimes
    "48189": 33_060,   # Hale
    "48191": 3_547,    # Hall
    "48193": 8_461,    # Hamilton
    "48195": 5_613,    # Hansford
    "48197": 4_613,    # Hardeman
    "48199": 56_379,   # Hardin
    "48201": 4_780_913, # Harris
    "48203": 34_796,   # Harrison
    "48205": 5_869,    # Hartley
    "48207": 5_622,    # Haskell
    "48209": 52_035,   # Hays
    "48211": 3_684,    # Hemphill
    "48213": 81_418,   # Henderson
    "48215": 999_940,  # Hidalgo
    "48217": 24_837,   # Hill
    "48219": 22_716,   # Hockley
    "48221": 52_830,   # Hood
    "48223": 35_161,   # Hopkins
    "48225": 25_891,   # Houston
    "48227": 33_537,   # Howard
    "48229": 2_919,    # Hudspeth
    "48231": 24_042,   # Hunt
    "48233": 27_376,   # Hutchinson
    "48235": 1_443,    # Irion
    "48237": 8_804,    # Jack
    "48239": 14_075,   # Jackson
    "48241": 38_664,   # Jasper
    "48243": 2_342,    # Jeff Davis
    "48245": 256_546,  # Jefferson
    "48247": 2_102,    # Jim Hogg
    "48249": 42_053,   # Jim Wells
    "48251": 170_040,  # Johnson
    "48253": 20_128,   # Jones
    "48255": 15_508,   # Karnes
    "48257": 141_240,  # Kaufman
    "48259": 48_205,   # Kendall
    "48261": 411,      # Kenedy
    "48263": 9_461,    # Kent — actually small
    "48263": 859,      # Kent
    "48265": 51_039,   # Kerr
    "48267": 4_560,    # Kimble
    "48269": 449,      # King
    "48271": 3_547,    # Kinney
    "48273": 43_240,   # Kleberg
    "48275": 4_148,    # Knox
    "48277": 14_709,   # Lamar
    "48279": 13_977,   # Lamb
    "48281": 20_813,   # Lampasas
    "48283": 6_886,    # La Salle
    "48285": 20_595,   # Lavaca
    "48287": 18_051,   # Lee
    "48289": 16_800,   # Leon
    "48291": 90_891,   # Liberty
    "48293": 22_709,   # Limestone
    "48295": 3_037,    # Lipscomb
    "48297": 12_773,   # Live Oak
    "48299": 20_174,   # Llano
    "48301": 64,       # Loving
    "48303": 323_860,  # Lubbock
    "48305": 5_765,    # Lynn — actually small
    "48305": 5_951,    # Lynn
    "48307": 10_229,   # McCulloch
    "48309": 160_651,  # McLennan
    "48311": 776,      # McMullen
    "48313": 43_664,   # Madison
    "48315": 13_464,   # Marion
    "48317": 5_765,    # Martin
    "48319": 4_533,    # Mason
    "48321": 37_957,   # Matagorda
    "48323": 59_203,   # Maverick
    "48325": 52_659,   # Medina
    "48327": 2_215,    # Menard
    "48329": 185_255,  # Midland
    "48331": 24_757,   # Milam
    "48333": 4_726,    # Mills
    "48335": 9_354,    # Mitchell
    "48337": 21_290,   # Montague
    "48339": 600_388,  # Montgomery
    "48341": 22_168,   # Moore
    "48343": 13_761,   # Morris
    "48345": 1_561,    # Motley
    "48347": 67_614,   # Nacogdoches
    "48349": 48_474,   # Navarro
    "48351": 15_765,   # Newton
    "48353": 15_216,   # Nolan
    "48355": 354_998,  # Nueces
    "48357": 6_587,    # Ochiltree
    "48359": 2_063,    # Oldham
    "48361": 111_135,  # Orange
    "48363": 29_334,   # Palo Pinto
    "48365": 23_965,   # Panola
    "48367": 145_926,  # Parker
    "48369": 10_389,   # Parmer
    "48371": 15_771,   # Pecos
    "48373": 21_780,   # Polk
    "48375": 124_840,  # Potter
    "48377": 10_887,   # Presidio
    "48379": 3_358,    # Rains
    "48381": 144_720,  # Randall
    "48383": 13_384,   # Reagan
    "48385": 3_309,    # Real
    "48387": 14_037,   # Red River
    "48389": 14_314,   # Reeves
    "48391": 7_236,    # Refugio
    "48393": 1_071,    # Roberts
    "48395": 15_948,   # Robertson
    "48397": 50_352,   # Rockwall
    "48399": 11_926,   # Runnels
    "48401": 54_406,   # Rusk
    "48403": 10_992,   # Sabine
    "48405": 8_490,    # San Augustine
    "48407": 10_834,   # San Jacinto
    "48409": 67_081,   # San Patricio
    "48411": 6_182,    # San Saba
    "48413": 3_143,    # Schleicher
    "48415": 17_379,   # Scurry
    "48417": 2_987,    # Shackelford
    "48419": 25_565,   # Shelby
    "48421": 3_227,    # Sherman
    "48423": 220_308,  # Smith
    "48425": 6_550,    # Somervell
    "48427": 65_419,   # Starr
    "48429": 9_916,    # Stephens
    "48431": 1_143,    # Sterling
    "48433": 1_455,    # Stonewall
    "48435": 3_752,    # Sutton
    "48437": 7_912,    # Swisher
    "48439": 2_193_282, # Tarrant
    "48441": 138_640,  # Taylor
    "48443": 1_013,    # Terrell
    "48445": 12_615,   # Terry
    "48447": 1_577,    # Throckmorton
    "48449": 33_855,   # Titus
    "48451": 120_940,  # Tom Green
    "48453": 1_290_188, # Travis
    "48455": 14_585,   # Trinity
    "48457": 21_452,   # Tyler
    "48459": 41_736,   # Upshur
    "48461": 3_613,    # Upton
    "48463": 27_034,   # Uvalde
    "48465": 49_482,   # Val Verde
    "48467": 53_724,   # Van Zandt
    "48469": 156_899,  # Victoria
    "48471": 71_895,   # Walker
    "48473": 73_049,   # Waller
    "48475": 14_099,   # Ward
    "48477": 37_771,   # Washington
    "48479": 280_260,  # Webb
    "48481": 48_793,   # Wharton
    "48483": 5_410,    # Wheeler
    "48485": 136_212,  # Wichita
    "48487": 7_629,    # Wilbarger
    "48489": 21_665,   # Willacy
    "48491": 720_500,  # Williamson
    "48493": 20_653,   # Wilson
    "48495": 7_571,    # Winkler
    "48497": 67_660,   # Wise
    "48499": 44_922,   # Wood
    "48501": 8_713,    # Yoakum
    "48503": 36_236,   # Young
    "48505": 12_522,   # Zapata
    "48507": 14_369,   # Zavala
}

# Counties where coverage is persistently lower (religious/homeschool clusters,
# historical outbreak areas, or confirmed low-coverage districts).
LOW_COVERAGE_FIPS = {
    # Permian Basin / South Plains cluster
    "48169", "48501", "48079", "48445", "48317", "48115", "48003",
    "48305", "48273", "48219", "48069",
    # Hill Country / faith communities
    "48171", "48093", "48267", "48319", "48411",
    # Some small rural West TX
    "48033", "48101", "48125", "48155", "48263", "48269",
}

# Border counties (increase mobility)
BORDER_FIPS = {
    "48061", "48109", "48131", "48163", "48215", "48229", "48247",
    "48271", "48283", "48311", "48323", "48371", "48377", "48389",
    "48427", "48443", "48463", "48465", "48479", "48489", "48505", "48507",
}

# Urban core — high coverage
URBAN_FIPS = {
    "48113", "48201", "48029", "48439", "48453", "48085", "48491",
    "48141", "48121", "48039", "48309", "48423",
}


def synthetic_county(fips: str, county_name: str, population: int) -> dict:
    """Generate one county's worth of synthetic but regionally realistic data."""
    rng = random.Random(int(fips) * 31337)  # deterministic

    is_low = fips in LOW_COVERAGE_FIPS
    is_border = fips in BORDER_FIPS
    is_urban = fips in URBAN_FIPS

    # MMR coverage
    if is_urban:
        mmr = round(rng.gauss(95.2, 1.5), 1)
    elif is_low:
        mmr = round(rng.gauss(82.0, 3.5), 1)
    else:
        mmr = round(rng.gauss(91.5, 3.0), 1)
    mmr = max(72.0, min(99.0, mmr))

    # Non-medical exemptions (inversely correlated with coverage)
    coverage_gap = max(0, 95 - mmr)
    nonmed = round(rng.gauss(coverage_gap * 0.55, 1.2), 2)
    nonmed = max(0.3, min(12.0, nonmed))

    med_pct = round(rng.uniform(0.1, 0.9), 2)

    # Enrolled students (proportional to population, with noise)
    enrolled = max(50, int(population * rng.uniform(0.12, 0.19)))

    # Surveillance
    confirmed = 0
    suspect = 0
    wastewater = round(rng.uniform(0, 0.12), 2)
    lab_pos = round(rng.uniform(0.0, 0.3), 2)
    specimens = max(0, int(population / 3000 * rng.uniform(0.5, 2.0)))

    # Slightly elevated signals in low-coverage counties
    if is_low and rng.random() < 0.35:
        confirmed = rng.randint(0, 2)
        suspect = rng.randint(0, 1)
        wastewater = round(rng.uniform(0.1, 0.45), 2)
        lab_pos = round(rng.uniform(0.2, 1.2), 2)

    # Network
    if is_urban:
        mobility = round(rng.gauss(0.88, 0.05), 2)
        religious = round(rng.gauss(0.30, 0.06), 2)
    elif is_border:
        mobility = round(rng.gauss(0.75, 0.08), 2)
        religious = round(rng.gauss(0.35, 0.08), 2)
    elif is_low:
        mobility = round(rng.gauss(0.42, 0.08), 2)
        religious = round(rng.gauss(0.65, 0.10), 2)
    else:
        mobility = round(rng.gauss(0.58, 0.12), 2)
        religious = round(rng.gauss(0.45, 0.12), 2)

    mobility = max(0.15, min(0.98, mobility))
    religious = max(0.10, min(0.95, religious))
    district_count = max(1, int(population / 15000 * rng.uniform(0.8, 1.8)))

    return {
        "fips": fips,
        "county_name": county_name,
        "population": population,
        "mmr": mmr,
        "nonmed": nonmed,
        "med": med_pct,
        "enrolled": enrolled,
        "confirmed": confirmed,
        "suspect": suspect,
        "wastewater": wastewater,
        "lab_pos": lab_pos,
        "specimens": specimens,
        "mobility": mobility,
        "religious": religious,
        "border": fips in BORDER_FIPS,
        "district_count": district_count,
    }


def main():
    geojson = json.loads(GEOJSON_PATH.read_text())
    features = geojson["features"]

    con = get_connection()

    # Which FIPS already exist?
    existing = {r[0] for r in con.execute("SELECT fips FROM geographies").fetchall()}
    print(f"Already seeded: {len(existing)} counties")

    to_seed = [
        f for f in features
        if f["properties"]["fips"] not in existing
    ]
    print(f"Will seed: {len(to_seed)} new counties")

    geo_rows, cov_rows, surv_rows, net_rows = [], [], [], []

    for feat in to_seed:
        fips = feat["properties"]["fips"]
        name = feat["properties"]["county_name"]
        pop  = KNOWN_POP.get(fips, max(800, abs(hash(fips)) % 25000 + 2000))

        d = synthetic_county(fips, name, pop)

        geo_rows.append((fips, "48", "TX", name, f"{name} County, TX", pop))

        cov_rows.append((
            fips, "2023-2024", d["mmr"], d["med"], d["nonmed"],
            d["enrolled"], "TX-synthetic",
        ))

        surv_rows.append((
            fips, "2024-10-01", d["confirmed"], d["suspect"],
            d["wastewater"], d["specimens"], d["lab_pos"], "synthetic",
        ))

        net_rows.append((
            fips, "2024-10-01", d["district_count"],
            d["enrolled"], d["mobility"], d["border"], d["religious"],
        ))

    if geo_rows:
        con.executemany("INSERT OR IGNORE INTO geographies VALUES (?,?,?,?,?,?)", geo_rows)
        con.executemany(
            """INSERT OR IGNORE INTO vaccination_coverage
               (fips, school_year, mmr_coverage_pct, medical_exempt_pct,
                nonmedical_exempt_pct, enrolled, source)
               VALUES (?,?,?,?,?,?,?)""",
            cov_rows,
        )
        con.executemany("INSERT OR IGNORE INTO surveillance VALUES (?,?,?,?,?,?,?,?)", surv_rows)
        con.executemany("INSERT OR IGNORE INTO network_metrics VALUES (?,?,?,?,?,?,?)", net_rows)
        print(f"Inserted {len(geo_rows)} counties.")
    else:
        print("Nothing to insert — all counties already seeded.")

    # Re-score all counties
    print("Scoring all counties…")
    results = score_all_counties("TX", con)
    tiers = {}
    for r in results:
        tiers[r["risk_tier"]] = tiers.get(r["risk_tier"], 0) + 1
    for tier in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        print(f"  {tier:10s} {tiers.get(tier, 0)}")
    print(f"  Total scored: {len(results)}")


if __name__ == "__main__":
    main()
