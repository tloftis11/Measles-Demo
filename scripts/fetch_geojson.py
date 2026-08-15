"""
Download Texas county boundaries from Census TIGER/Line (cartographic boundary, 500k scale)
and save as GeoJSON to data/geojson/tx_counties.geojson.

Run from repo root:  uv run python scripts/fetch_geojson.py
"""
import json
import sys
from pathlib import Path

import geopandas as gpd

OUT = Path(__file__).parent.parent / "data" / "geojson" / "tx_counties.geojson"
URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading county boundaries from Census... ({URL})")
    gdf = gpd.read_file(URL)

    tx = gdf[gdf["STATEFP"] == "48"].copy()
    tx["fips"] = tx["STATEFP"] + tx["COUNTYFP"]
    tx = tx.to_crs("EPSG:4326")

    out_gdf = tx[["fips", "NAME", "geometry"]].rename(columns={"NAME": "county_name"})
    out_gdf.to_file(str(OUT), driver="GeoJSON")
    print(f"Saved {len(out_gdf)} TX counties → {OUT}")

if __name__ == "__main__":
    main()
