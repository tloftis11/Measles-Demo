"""
Fetch county GeoJSON boundaries from Census TIGER for each supported state.

Uses the Census Bureau's CartographicBoundary GeoJSON (500k resolution).
Output files are written to data/geojson/ with two properties per feature:
  fips        — 5-digit FIPS string  (e.g. "48169")
  county_name — county name without suffix (e.g. "Gaines")

Run:
    uv run python scripts/fetch_geojson.py
"""

import json
import sys
from pathlib import Path

import httpx

GEOJSON_DIR = Path(__file__).parent.parent.parent / "data" / "geojson"
GEOJSON_DIR.mkdir(parents=True, exist_ok=True)

# Census CartographicBoundary 500k county files by state FIPS
STATES = {
    "tx": ("48", "tx_counties.geojson"),
    "id": ("16", "id_counties.geojson"),
    "pa": ("42", "pa_counties.geojson"),
}

# Census Bureau national county GeoJSON (20m simplified, all states)
NATIONAL_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
)


def fetch_national(client: httpx.Client) -> dict:
    print("Downloading national county GeoJSON from Census/Plotly…")
    r = client.get(NATIONAL_URL, timeout=120, follow_redirects=True)
    r.raise_for_status()
    print(f"  Downloaded {len(r.content):,} bytes")
    return r.json()


def normalize_feature(feature: dict, state_fips: str) -> dict | None:
    """Return a normalized feature with only fips + county_name, or None to skip."""
    props = feature.get("properties", {})

    # Plotly dataset uses STATE + COUNTY numeric fields and NAME
    state_f = str(props.get("STATE", "")).zfill(2)
    county_f = str(props.get("COUNTY", "")).zfill(3)
    name = props.get("NAME", "")

    if state_f != state_fips:
        return None

    fips = state_f + county_f
    # Strip common suffixes from Census name (County, Parish, Borough, etc.)
    county_name = (
        name.replace(" County", "")
            .replace(" Parish", "")
            .replace(" Borough", "")
            .replace(" Census Area", "")
            .replace(" Municipality", "")
            .strip()
    )

    return {
        "type": "Feature",
        "properties": {"fips": fips, "county_name": county_name},
        "geometry": feature["geometry"],
    }


def build_state_geojson(national: dict, state_abbr: str, state_fips: str) -> dict:
    features = []
    for feat in national["features"]:
        normalized = normalize_feature(feat, state_fips)
        if normalized:
            features.append(normalized)
    print(f"  {state_abbr.upper()}: {len(features)} counties")
    return {"type": "FeatureCollection", "name": f"{state_abbr}_counties", "features": features}


def main():
    with httpx.Client() as client:
        national = fetch_national(client)

    for state_abbr, (state_fips, filename) in STATES.items():
        out_path = GEOJSON_DIR / filename
        if out_path.exists():
            print(f"  {filename} already exists — skipping (delete to re-fetch)")
            continue
        print(f"Building {filename}…")
        fc = build_state_geojson(national, state_abbr, state_fips)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, separators=(",", ":"))
        size_kb = out_path.stat().st_size // 1024
        print(f"  Wrote {out_path.name} ({size_kb} KB, {len(fc['features'])} features)")

    print("Done.")


if __name__ == "__main__":
    main()
