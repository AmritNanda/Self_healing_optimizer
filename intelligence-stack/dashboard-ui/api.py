"""
api.py — Dashboard Backend API (FastAPI)
Bridges the React Frontend with Prometheus, Kubernetes, and the ML Stack.
"""

import os
import asyncio
import random
import time
import logging
import subprocess
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chaos.api")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
ML_BACKEND_URL = os.getenv("ML_BACKEND_URL", "http://localhost:8000")

# Chaos YAML file paths
CHAOS_DIR = os.getenv("CHAOS_DIR", r"E:\Self-healing-system\k8s-infrastructure\chaos-scenarios")
CHAOS_FILES = {
    "pod_kill":       os.path.join(CHAOS_DIR, "pod-kill.yaml"),
    "cpu_stress":     os.path.join(CHAOS_DIR, "cpu-stress.yaml"),
    "memory_stress":  os.path.join(CHAOS_DIR, "memory-stress.yaml"),
    "network_delay":  os.path.join(CHAOS_DIR, "network-delay.yaml"),
    "network_loss":   os.path.join(CHAOS_DIR, "http-abort.yaml"),
}

app = FastAPI(title="SRE Dashboard API")

# Enable CORS for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TelemetryResponse(BaseModel):
    cpu: float
    mem: float
    latency: float
    timestamp: float

class ChaosRequest(BaseModel):
    type: str

class MLAnalysisRequest(BaseModel):
    cpu_usage: float
    mem_usage: float
    latency_ms: float

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def query_prometheus(query: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=3.0)
            r.raise_for_status()
            return r.json()["data"]["result"]
        except Exception as e:
            logger.warning("Prometheus query failed: %s", e)
            return []

def simulate_telemetry():
    """Fallback if Prometheus is unavailable."""
    spike = random.random() < 0.05
    if spike:
        return 85.0 + random.random() * 10, 80.0 + random.random() * 10, 1500.0 + random.random() * 2000
    t = time.time()
    cpu = 30 + 15 * abs(0.5 - ((t % 60) / 60)) + random.gauss(0, 4)
    mem = 50 + 10 * abs(0.5 - ((t % 90) / 90)) + random.gauss(0, 5)
    lat = 100 + 80 * abs(0.5 - ((t % 45) / 45)) + random.gauss(0, 20)
    return float(min(max(cpu, 5), 99)), float(min(max(mem, 10), 99)), float(max(lat, 20))

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/v1/telemetry", response_model=TelemetryResponse)
async def get_telemetry():
    """
    Fetches real metrics from Prometheus or falls back to simulation.
    """
    try:
        # Sum CPU across the target namespace
        cpu_query = 'sum(rate(container_cpu_usage_seconds_total{namespace="applications",container!="",container!="POD"}[2m]))'
        # Total Memory working set
        mem_query = 'sum(container_memory_working_set_bytes{namespace="applications",container!="",container!="POD"})'

        cpu_data, mem_data = await asyncio.gather(
            query_prometheus(cpu_query),
            query_prometheus(mem_query)
        )

        cpu = float(cpu_data[0]["value"][1]) * 100 if cpu_data else None
        mem_bytes = float(mem_data[0]["value"][1]) if mem_data else None
        # Assume 6GB cluster for normalization as in legacy dashboard
        mem = (mem_bytes / (6 * 1024 ** 3)) * 100 if mem_bytes else None

        if cpu is None or mem is None:
            c, m, l = simulate_telemetry()
        else:
            c, m = round(cpu, 2), round(mem, 2)
            l = round(random.uniform(80, 200), 2) # Latency simulation if not in Prom
        
        return {
            "cpu": c,
            "mem": m,
            "latency": l,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error("Telemetry fetch error: %s", e)
        c, m, l = simulate_telemetry()
        return {"cpu": c, "mem": m, "latency": l, "timestamp": time.time()}

@app.post("/api/v1/chaos")
async def trigger_chaos(payload: ChaosRequest):
    """
    Executes kubectl commands to inject chaos into the cluster.
    """
    if payload.type not in CHAOS_FILES:
        raise HTTPException(status_code=400, detail="Invalid chaos type")
    
    path = CHAOS_FILES[payload.type]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Chaos file not found at {path}")

    try:
        # Cleanup first, then apply
        subprocess.run(["kubectl", "delete", "-f", path, "--ignore-not-found"], capture_output=True, timeout=10)
        result = subprocess.run(["kubectl", "apply", "-f", path], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            logger.error("Kubectl apply failed: %s", result.stderr)
            raise HTTPException(status_code=500, detail=f"Kubectl error: {result.stderr}")
            
        logger.info("Chaos injected: %s", payload.type)
        return {"status": "success", "message": f"Chaos {payload.type} injected."}
    except Exception as e:
        logger.error("Chaos injection error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/analyze")
async def analyze_telemetry(payload: MLAnalysisRequest):
    """
    Bridge to the ML Backend for anomaly detection.
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{ML_BACKEND_URL}/api/v1/analyze", 
                json=payload.dict(), 
                timeout=5.0
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("ML Backend bridge failed: %s", e)
            # Simple fallback heuristic if ML is down
            score = min(max((payload.cpu_usage / 100 + payload.mem_usage / 100) / 2, 0.0), 1.0)
            return {
                "is_anomaly": score > 0.6,
                "threat_score": round(score, 4),
                "recommended_action": "RESTART_POD" if score > 0.6 else "NO_ACTION",
                "processing_time_ms": 0.0
            }

if __name__ == "__main__":
    import uvicorn
    import asyncio
    uvicorn.run(app, host="0.0.0.0", port=8080)
