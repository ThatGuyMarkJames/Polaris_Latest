"""
POLARIS — AI Polar Energy Digital Twin
FastAPI Backend Application Entrypoint
Smart India Hackathon 2026 Problem Statement PS26061
"""

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import station, weather, forecast, optimization, simulation, agents, telemetry, resilience
from backend.database.db import get_db_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and tables
    conn = get_db_connection()
    conn.close()
    yield


app = FastAPI(
    title="POLARIS — AI Polar Energy Resilience Platform",
    description="AI-Driven Smart Energy Management System & Digital Twin for Polar Research Stations",
    version="2.6.0",
    lifespan=lifespan
)

# CORS configuration for development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(station.router)
app.include_router(weather.router)
app.include_router(forecast.router)
app.include_router(optimization.router)
app.include_router(simulation.router)
app.include_router(agents.router)
app.include_router(telemetry.router)
app.include_router(resilience.router)


@app.get("/")
async def root():
    return {
        "system": "POLARIS AI Polar Energy Digital Twin",
        "problem_statement": "PS26061",
        "status": "OPERATIONAL",
        "version": "2.6.0",
        "concept": "DATA -> VALIDATION -> FEATURE ENGINEERING -> HYBRID FORECAST -> UNCERTAINTY -> MATHEMATICAL OPTIMIZATION -> SAFETY -> AGENT/EXPLANATION",
        "endpoints": {
            "station": "/api/station/presets",
            "weather": "/api/weather/live?lat=-69.4072&lon=76.1872",
            "telemetry_current": "/api/telemetry/current/bharati",
            "telemetry_history": "/api/telemetry/history/bharati",
            "forecast": "/api/forecast/run",
            "hybrid_forecast": "/api/forecast/hybrid/bharati",
            "resilience": "/api/resilience/p0-horizon/bharati",
            "optimization": "/api/optimization/solve",
            "simulation": "/api/simulation/run",
            "agents": "/api/agents/orchestrate"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "polaris-backend", "version": "2.6.0"}


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
