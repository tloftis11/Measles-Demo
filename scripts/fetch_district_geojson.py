"""
Download Census TIGER/Line 2023 school district boundaries for Texas.

Tries unified districts first, then adds elementary/secondary if unified is
sparse. Saves to data/geojson/tx_districts.geojson with fields:
  lea_geoid, district_name, county_fips, fips (full 5-digit), state_abbr, geometry

Run from repo root (geopandas is an optional extra, not installed by default):
    uv run --project backend --extra scripts python scripts/fetch_district_geojson.py
"""
from __future__ import annotations
import io, os, sys, tempfile, zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
os.environ.setdefault("DB_PATH", str(REPO_ROOT / "data" / "measles.duckdb"))

import geopandas as gpd
import pandas as pd

OUT_DIR  = REPO_ROOT / "data" / "geojson"
OUT_PATH = OUT_DIR / "tx_districts.geojson"

TIGER_URLS = [
    # Unified school districts for TX (state FIPS 48)
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_48_unsd_500k.zip",
    # Elementary school districts
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_48_elsd_500k.zip",
    # Secondary school districts
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_48_scsd_500k.zip",
]


def fetch_one(url: str) -> gpd.GeoDataFrame | None:
    import httpx
    print(f"  Downloading {url.split('/')[-1]} …", end=" ", flush=True)
    try:
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        print(f"FAILED ({exc})")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(tmp)
        shp_files = list(Path(tmp).glob("*.shp"))
        if not shp_files:
            print("no .shp found")
            return None
        gdf = gpd.read_file(str(shp_files[0]))

    gdf = gdf.to_crs("EPSG:4326")
    print(f"OK ({len(gdf)} features)")
    return gdf


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    parts: list[gpd.GeoDataFrame] = []
    for url in TIGER_URLS:
        gdf = fetch_one(url)
        if gdf is not None:
            parts.append(gdf)

    if not parts:
        print("All downloads failed.")
        raise SystemExit(1)

    combined = pd.concat(parts, ignore_index=True)

    # Normalize to a stable schema regardless of which TIGER variant
    # Census TIGER school district columns: GEOID, NAME, STATEFP, COUNTYFP (or COUSUBFP)
    rename = {}
    for src, dst in [("GEOID","lea_geoid"), ("NAME","district_name"),
                     ("COUNTYFP","county_fips"), ("STATEFP","state_fips")]:
        if src in combined.columns:
            rename[src] = dst
    combined = combined.rename(columns=rename)

    keep = [c for c in ["lea_geoid","district_name","county_fips","state_fips","geometry"]
            if c in combined.columns]
    combined = combined[keep].copy()

    # Ensure county_fips is 3-char and build full 5-digit FIPS
    if "county_fips" in combined.columns:
        combined["county_fips"] = combined["county_fips"].astype(str).str.zfill(3)
        combined["fips"] = "48" + combined["county_fips"]
    combined["state_abbr"] = "TX"

    # Drop duplicates (same district appearing in both ELSD and SCSD files)
    if "lea_geoid" in combined.columns:
        combined = combined.drop_duplicates(subset=["lea_geoid"])

    combined = combined.reset_index(drop=True)

    # --- Spatial join: assign each district to its primary county ---
    # We can't rely on COUNTYFP (absent from UNSD). Instead we overlay district
    # polygons onto county polygons and pick the county with the greatest overlap.
    county_path = REPO_ROOT / "data" / "geojson" / "tx_counties.geojson"
    if county_path.exists():
        print("Spatial-joining districts → counties …")
        counties = gpd.read_file(str(county_path))
        # Compute intersection area for every (district × county) pair
        # Use overlay to find overlaps, then pick the county with the largest area
        # for each district. This handles multi-county districts correctly.
        districts_proj = combined.to_crs("EPSG:3082")   # TX-centric equal-area
        counties_proj  = counties[["fips","county_name","geometry"]].to_crs("EPSG:3082")

        overlay = gpd.overlay(
            districts_proj.reset_index().rename(columns={"index":"dist_idx"}),
            counties_proj,
            how="intersection",
        )
        overlay["overlap_area"] = overlay.geometry.area
        # Pick the county with the largest overlap for each district
        best = (
            overlay.sort_values("overlap_area", ascending=False)
            .drop_duplicates(subset=["dist_idx"])
            .set_index("dist_idx")[["fips","county_name"]]
        )
        combined = combined.copy()
        combined["fips"]        = combined.index.map(best["fips"])
        combined["county_name"] = combined.index.map(best["county_name"])
        combined["county_fips"] = combined["fips"].str[2:]  # last 3 digits
        matched = combined["fips"].notna().sum()
        print(f"  Matched {matched}/{len(combined)} districts to a county")
    else:
        print("County GeoJSON not found — skipping spatial join (fips will be empty)")

    combined = combined.reset_index(drop=True)

    # Convert to GeoDataFrame and write
    gdf_out = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")
    gdf_out.to_file(str(OUT_PATH), driver="GeoJSON")
    print(f"Saved {len(gdf_out)} district polygons → {OUT_PATH}")

    # Quick county distribution check
    if "fips" in gdf_out.columns:
        counts = gdf_out[gdf_out["fips"].notna()].groupby("fips").size().sort_values(ascending=False)
        print(f"Districts per county: max={counts.max()}, median={counts.median():.0f}, counties covered={len(counts)}")


if __name__ == "__main__":
    main()
