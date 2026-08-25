"""
Fetch school district GeoJSON boundaries from Census TIGER for each supported state.

Downloads Census CartographicBoundary unified school district shapefiles (500k),
assigns each district to its primary county via spatial intersection (largest overlap
area), and writes to data/geojson/.

Output properties per feature:
  fips          — 5-digit county FIPS the district overlaps most
  lea_geoid     — 7-digit LEAID (GEOID from shapefile)
  district_name — district name
  county_name   — county name (from county GeoJSON spatial join)
  county_fips   — 3-digit county FIPS suffix
  state_fips    — 2-digit state FIPS
  state_abbr    — state abbreviation

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

CENSUS_BASE = "https://www2.census.gov/geo/tiger/GENZ2022/shp"

STATES = {
    "16": ("id", "id_districts.geojson"),
    "42": ("pa", "pa_districts.geojson"),
}


def load_county_gdf(state_abbr: str) -> gpd.GeoDataFrame | None:
    path = GEOJSON_DIR / f"{state_abbr}_counties.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    return gdf[["geometry", "fips", "county_name"]].copy()


def fetch_state_districts(client: httpx.Client, state_fips: str) -> gpd.GeoDataFrame:
    url = f"{CENSUS_BASE}/cb_2022_{state_fips}_unsd_500k.zip"
    print(f"  Downloading {url}…")
    r = client.get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    print(f"  Downloaded {len(r.content):,} bytes")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        shp_name = next(n for n in zf.namelist() if n.endswith(".shp"))
        tmp_dir = Path(__file__).parent / "_tmp_shp"
        tmp_dir.mkdir(exist_ok=True)
        zf.extractall(tmp_dir)
    gdf = gpd.read_file(tmp_dir / shp_name)
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return gdf


def assign_counties_spatial(
    districts_gdf: gpd.GeoDataFrame,
    counties_gdf: gpd.GeoDataFrame,
) -> list[tuple[str, str]]:
    """
    For each district, find the county with the largest intersection area.
    Returns a list of (5-digit county fips, county_name) tuples, one per district row.
    """
    # Ensure matching CRS
    if counties_gdf.crs != districts_gdf.crs:
        counties_gdf = counties_gdf.to_crs(districts_gdf.crs)

    county_geoms = list(counties_gdf.itertuples(index=False))
    results = []
    total = len(districts_gdf)

    for i, (_, dist_row) in enumerate(districts_gdf.iterrows(), 1):
        if i % 50 == 0 or i == total:
            print(f"    Spatial join: {i}/{total}…")

        dist_geom = dist_row.geometry
        if dist_geom is None or dist_geom.is_empty:
            results.append(("", ""))
            continue

        # Buffer by zero to fix any topology issues
        try:
            dist_geom = dist_geom.buffer(0)
        except Exception:
            pass

        best_area = 0.0
        best_fips = ""
        best_name = ""

        for county_row in county_geoms:
            try:
                county_geom = county_row.geometry
                if county_geom is None or county_geom.is_empty:
                    continue
                inter = dist_geom.intersection(county_geom.buffer(0))
                area = inter.area
                if area > best_area:
                    best_area = area
                    best_fips = str(county_row.fips)
                    best_name = str(county_row.county_name)
            except Exception:
                continue

        results.append((best_fips, best_name))

    return results


def gdf_to_geojson(
    gdf: gpd.GeoDataFrame,
    state_fips: str,
    state_abbr: str,
    counties_gdf: gpd.GeoDataFrame | None,
) -> dict:
    # Reproject to WGS84
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    if counties_gdf is not None:
        print("  Running spatial county assignment…")
        county_assignments = assign_counties_spatial(gdf, counties_gdf)
    else:
        county_assignments = [("", "")] * len(gdf)

    features = []
    for i, (_, row) in enumerate(gdf.iterrows()):
        geoid = str(row.get("GEOID", "")).strip()
        # Pad GEOID to 7 chars (SSUUUUU format)
        if len(geoid) < 7:
            geoid = geoid.zfill(7)
        name = str(row.get("NAME", "Unknown District"))

        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        county_fips_full, county_name = county_assignments[i]
        if county_fips_full and len(county_fips_full) == 5:
            county_fp = county_fips_full[2:]  # 3-digit suffix
        else:
            county_fp = "000"
            county_fips_full = state_fips.zfill(2) + "000"

        features.append({
            "type": "Feature",
            "properties": {
                "fips": county_fips_full,
                "lea_geoid": geoid,
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
            print(f"\nBuilding {filename} for {state_abbr.upper()}…")

            counties_gdf = load_county_gdf(state_abbr)
            if counties_gdf is None:
                print(f"  WARNING: {state_abbr}_counties.geojson not found; no county assignment possible")

            try:
                gdf = fetch_state_districts(client, state_fips)
                print(f"  {len(gdf)} districts loaded from shapefile")
                fc = gdf_to_geojson(gdf, state_fips, state_abbr, counties_gdf)

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(fc, f, separators=(",", ":"))

                size_kb = out_path.stat().st_size // 1024
                assigned = sum(
                    1 for feat in fc["features"]
                    if feat["properties"]["county_fips"] != "000"
                )
                print(f"  Wrote {filename}: {size_kb} KB, {len(fc['features'])} features, "
                      f"{assigned} with county assignment")

            except Exception as exc:
                print(f"  ERROR: {exc}")
                import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
