"""
Fetch school district GeoJSON boundaries from Census TIGER for each supported state.

Downloads Census CartographicBoundary unified school district shapefiles (500k),
converts to GeoJSON with our standard schema, and writes to data/geojson/.

Output properties per feature:
  fips          — 5-digit county FIPS the district is primarily in
  lea_geoid     — 7-digit LEAID (state FIPS + 5-digit district code)
  district_name — district name
  county_name   — county name (from county GeoJSON)
  county_fips   — 3-digit county FIPS

Run:
    uv run python scripts/fetch_district_geojson.py
"""

import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import httpx
from shapely.geometry import mapping

GEOJSON_DIR = Path(__file__).parent.parent.parent / "data" / "geojson"
GEOJSON_DIR.mkdir(parents=True, exist_ok=True)

# Census CartographicBoundary unified school districts by state FIPS
# Format: cb_2022_{state_fips}_unsd_500k.zip
CENSUS_BASE = "https://www2.census.gov/geo/tiger/GENZ2022/shp"

STATES = {
    "16": ("id", "id_districts.geojson"),
    "42": ("pa", "pa_districts.geojson"),
}


def load_county_names(state_abbr: str) -> dict[str, str]:
    path = GEOJSON_DIR / f"{state_abbr}_counties.geojson"
    if not path.exists():
        return {}
    with open(path) as f:
        fc = json.load(f)
    return {feat["properties"]["fips"]: feat["properties"]["county_name"]
            for feat in fc["features"]}


def fetch_state_districts(client: httpx.Client, state_fips: str) -> gpd.GeoDataFrame:
    url = f"{CENSUS_BASE}/cb_2022_{state_fips}_unsd_500k.zip"
    print(f"  Downloading {url}…")
    r = client.get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    print(f"  Downloaded {len(r.content):,} bytes")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        # Read shapefile from zip using geopandas
        shp_name = next(n for n in zf.namelist() if n.endswith(".shp"))
        # Extract all related files to a temp buffer approach via geopandas
        tmp_dir = Path(__file__).parent / "_tmp_shp"
        tmp_dir.mkdir(exist_ok=True)
        zf.extractall(tmp_dir)
    gdf = gpd.read_file(tmp_dir / shp_name)
    # Clean up temp files
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return gdf


def gdf_to_geojson(gdf: gpd.GeoDataFrame, state_fips: str, state_abbr: str,
                   county_names: dict[str, str]) -> dict:
    # Reproject to WGS84 if needed
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    features = []
    for _, row in gdf.iterrows():
        geoid = str(row.get("GEOID", "")).zfill(7)
        lea_id = geoid  # 7-digit LEAID
        name = str(row.get("NAME", "Unknown District"))
        county_fp = str(row.get("COUNTYFP", "")).zfill(3)
        county_fips = state_fips.zfill(2) + county_fp
        county_name = county_names.get(county_fips, "")

        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        features.append({
            "type": "Feature",
            "properties": {
                "fips": county_fips,
                "lea_geoid": lea_id,
                "district_name": name,
                "state_fips": state_fips.zfill(2),
                "state_abbr": state_abbr.upper(),
                "county_name": county_name,
                "county_fips": county_fp,
            },
            "geometry": mapping(geom),
        })

    return {
        "type": "FeatureCollection",
        "name": f"{state_abbr}_districts",
        "features": features,
    }


def main():
    with httpx.Client() as client:
        for state_fips, (state_abbr, filename) in STATES.items():
            out_path = GEOJSON_DIR / filename
            if out_path.exists() and out_path.stat().st_size > 1000:
                print(f"  {filename} already exists — skipping (delete to re-fetch)")
                continue

            print(f"Building {filename} for {state_abbr.upper()}…")
            county_names = load_county_names(state_abbr)

            try:
                gdf = fetch_state_districts(client, state_fips)
                print(f"  {len(gdf)} districts loaded from shapefile")
                fc = gdf_to_geojson(gdf, state_fips, state_abbr, county_names)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(fc, f, separators=(",", ":"))
                size_kb = out_path.stat().st_size // 1024
                print(f"  Wrote {filename} ({size_kb} KB, {len(fc['features'])} features)")
            except Exception as exc:
                print(f"  ERROR: {exc}")
                import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
