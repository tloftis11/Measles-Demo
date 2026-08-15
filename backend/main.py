import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.scores import router as scores_router
from api.simulation import router as simulation_router
from api.ai import router as ai_router
from api.geojson import router as geojson_router
from api.query import router as query_router
from api.districts import router as districts_router

app = FastAPI(
    title="Measles Hotspot API",
    description="Hotspot scoring, SEIR simulation, and AI analyst for measles outbreak detection.",
    version="0.1.0",
)

_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
origins = [o.strip() for o in _origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scores_router)
app.include_router(simulation_router)
app.include_router(ai_router)
app.include_router(geojson_router)
app.include_router(query_router)
app.include_router(districts_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the React build in production. Must come last — it's a catch-all.
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


@app.get("/api/sources")
def get_sources():
    return {
        "sources": [
            {
                "layer": "Vaccination Coverage",
                "name": "TX DSHS School Vaccination Coverage",
                "tier": "Public",
                "url": "https://www.dshs.texas.gov/immunize/coverage/",
                "grain": "School district",
                "refresh": "Annual (school year)",
                "current_year": "2023-2024",
            },
            {
                "layer": "Surveillance",
                "name": "CDC NNDSS Measles Reports",
                "tier": "Public",
                "url": "https://wonder.cdc.gov/nndss/",
                "grain": "County",
                "refresh": "Weekly",
            },
            {
                "layer": "Network",
                "name": "SafeGraph Mobility Patterns",
                "tier": "Purchasable",
                "url": "https://www.safegraph.com/",
                "grain": "County",
                "refresh": "Monthly",
            },
        ]
    }
