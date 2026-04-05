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

from cascade import CascadeEngine
from blast_radius import BlastRadiusRenderer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chaos.api")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
ML_BACKEND_URL = os.getenv("ML_BACKEND_URL", "http://localhost:8000")

CHAOS_DIR = os.getenv("CHAOS_DIR", r"d:\trasnfer\codes\Self_healing_optimizer\k8s-infrastructure\chaos-scenarios")
CHAOS_FILES = {
    "pod_kill":      os.path.join(CHAOS_DIR, "pod-kill.yaml"),
    "cpu_stress":    os.path.join(CHAOS_DIR, "cpu-stress.yaml"),
    "memory_stress": os.path.join(CHAOS_DIR, "memory-stress.yaml"),
    "network_delay": os.path.join(CHAOS_DIR, "network-partition.yaml"),
    "network_loss":  os.path.join(CHAOS_DIR, "http-abort.yaml"),
}

app = FastAPI(title="SRE Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    try:
        cpu_query = 'sum(rate(container_cpu_usage_seconds_total{namespace="online-boutique",container!="",container!="POD"}[2m]))'
        mem_query = 'sum(container_memory_working_set_bytes{namespace="online-boutique",container!="",container!="POD"})'

        cpu_data, mem_data = await asyncio.gather(
            query_prometheus(cpu_query),
            query_prometheus(mem_query)
        )

        cpu = float(cpu_data[0]["value"][1]) * 100 if cpu_data else None
        mem_bytes = float(mem_data[0]["value"][1]) if mem_data else None
        mem = (mem_bytes / (6 * 1024 ** 3)) * 100 if mem_bytes else None

        if cpu is None or mem is None:
            c, m, l = simulate_telemetry()
        else:
            c, m = round(cpu, 2), round(mem, 2)
            l = round(random.uniform(80, 200), 2)

        return {"cpu": c, "mem": m, "latency": l, "timestamp": time.time()}
    except Exception as e:
        logger.error("Telemetry fetch error: %s", e)
        c, m, l = simulate_telemetry()
        return {"cpu": c, "mem": m, "latency": l, "timestamp": time.time()}


@app.post("/api/v1/chaos")
async def trigger_chaos(payload: ChaosRequest):
    if payload.type not in CHAOS_FILES:
        raise HTTPException(status_code=400, detail="Invalid chaos type")

    path = CHAOS_FILES[payload.type]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Chaos file not found at {path}")

    try:
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


@app.post("/api/v1/chaos/frontend-down")
async def frontend_down():
    """Scale frontend to 0 replicas — causes real 503 in browser."""
    try:
        result = subprocess.run(
            ["kubectl", "scale", "deployment", "frontend",
             "-n", "online-boutique", "--replicas=0"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr)
        logger.info("Frontend scaled to 0 replicas")
        return {"status": "ok", "message": "Frontend scaled to 0 — site is down"}
    except Exception as e:
        logger.error("Scale-down error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chaos/frontend-up")
async def frontend_up():
    """Scale frontend back to 1 replica — recovers the site."""
    try:
        result = subprocess.run(
            ["kubectl", "scale", "deployment", "frontend",
             "-n", "online-boutique", "--replicas=1"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr)
        logger.info("Frontend scaled back to 1 replica")
        return {"status": "ok", "message": "Frontend scaled to 1 — site recovering"}
    except Exception as e:
        logger.error("Scale-up error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/analyze")
async def analyze_telemetry(payload: MLAnalysisRequest):
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
            score = min(max((payload.cpu_usage / 100 + payload.mem_usage / 100) / 2, 0.0), 1.0)
            return {
                "is_anomaly": score > 0.6,
                "threat_score": round(score, 4),
                "recommended_action": "RESTART_POD" if score > 0.6 else "NO_ACTION",
                "processing_time_ms": 0.0
            }


# ---------------------------------------------------------------------------
# Blast Radius / Cascade Engine
# ---------------------------------------------------------------------------
cascade_engine = CascadeEngine()
blast_renderer = BlastRadiusRenderer()


async def _cascade_sync_loop():
    """Background task: sync cascade engine from live cluster every 3s."""
    while True:
        try:
            events = await cascade_engine.sync_from_cluster()
            if events:
                logger.info("Cascade sync: %d state change(s)", len(events))
        except Exception as e:
            logger.warning("Cascade sync error: %s", e)
        await asyncio.sleep(3)


@app.on_event("startup")
async def _start_cascade_sync():
    asyncio.create_task(_cascade_sync_loop())
    logger.info("Cascade background sync started")


@app.get("/api/v1/blast-radius")
async def get_blast_radius():
    """Return the full blast radius map as JSON for the React frontend."""
    try:
        blast_map = cascade_engine.get_blast_radius_map()
        legend_table = blast_renderer.build_legend_table(blast_map)

        # Serialize states for the frontend
        states = {}
        for svc, state in blast_map.states.items():
            s = {
                "name": state.name,
                "display_name": state.display_name,
                "health": state.health.value,
                "health_score": round(state.health_score, 1),
                "failure_reason": state.failure_reason or "",
                "affected_by": state.affected_by,
                "recovery_eta_s": state.recovery_eta_s,
                "position": list(state.position),
                "color": state.color,
            }
            if state.metrics:
                m = state.metrics
                s["metrics"] = {
                    "cpu_percent": round(m.cpu_percent, 1),
                    "memory_mb": round(m.memory_mb, 1),
                    "restart_count": m.restart_count,
                    "replicas_available": m.replicas_available,
                    "replicas_desired": m.replicas_desired,
                    "pod_ready": m.pod_ready,
                    "pod_phase": m.pod_phase,
                }
            states[svc] = s

        # Serialize events
        events = []
        for ev in blast_map.events[-20:]:
            events.append({
                "timestamp": ev.timestamp,
                "service": ev.service,
                "previous": ev.previous.value,
                "current": ev.current.value,
                "health_score": round(ev.health_score, 1),
                "triggered_by": ev.triggered_by,
                "depth": ev.depth,
            })

        return {
            "root_cause": blast_map.root_cause,
            "affected_count": blast_map.affected_count,
            "total_services": blast_map.total_services,
            "estimated_user_impact_pct": round(blast_map.estimated_user_impact_pct, 1),
            "propagation_path": blast_map.propagation_path,
            "states": states,
            "events": events,
            "legend_table": legend_table,
        }
    except Exception as e:
        logger.error("Blast radius error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/blast-radius/inject")
async def inject_blast_root(payload: ChaosRequest):
    """Mark a service as the chaos root for blast radius tracking."""
    svc = payload.type
    from cascade import DEPENDENCY_GRAPH
    if svc not in DEPENDENCY_GRAPH:
        raise HTTPException(status_code=400, detail=f"Unknown service: {svc}")
    cascade_engine.inject(svc)
    return {"status": "ok", "root": svc}


@app.post("/api/v1/blast-radius/reset")
async def reset_blast_radius():
    """Reset all services to healthy state."""
    cascade_engine.reset()
    return {"status": "ok", "message": "Cascade engine reset"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
