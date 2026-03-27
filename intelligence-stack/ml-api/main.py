"""
main.py — Chaos Engineering ML Backend (FastAPI).
 
Endpoints:
  POST /api/v1/analyze  — telemetry anomaly analysis
  GET  /health          — liveness probe
  GET  /metrics         — Prometheus-style text metrics
"""
 
from __future__ import annotations
 
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
 
import joblib
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
 
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("chaos.ml_backend")
 
# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "chaos_ml_requests_total",
    "Total inference requests",
    ["status"],
)
INFERENCE_LATENCY = Histogram(
    "chaos_ml_inference_duration_seconds",
    "Inference latency histogram",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)
ANOMALY_SCORE_GAUGE = Gauge(
    "chaos_ml_last_threat_score",
    "Most recent threat score (0–1)",
)
ANOMALY_COUNTER = Counter(
    "chaos_ml_anomalies_detected_total",
    "Total anomaly events detected",
)
 
# ---------------------------------------------------------------------------
# Model state (loaded at startup via lifespan)
# ---------------------------------------------------------------------------
MODEL_PATH = Path(os.getenv("MODEL_PATH", "isolation_forest.joblib"))
_model = None  # sklearn Pipeline (scaler + IsolationForest)
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup; release on shutdown."""
    global _model
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"Model not found at '{MODEL_PATH}'. "
            "Run train_model.py first."
        )
    logger.info("Loading model from '%s' …", MODEL_PATH)
    _model = joblib.load(MODEL_PATH)
    logger.info("Model loaded — type: %s", type(_model).__name__)
    yield
    logger.info("Shutting down ML backend.")
 
 
# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Chaos ML Intelligence Backend",
    description="Autonomous Chaos Engineering — Anomaly Detection Engine",
    version="1.0.0",
    lifespan=lifespan,
)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------------------------------------------------
# Middleware — per-request latency logging
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    logger.info(
        "%s %s → %d  (%.3fs)",
        request.method, request.url.path, response.status_code, elapsed,
    )
    return response
 
 
# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class TelemetryInput(BaseModel):
    cpu_usage: float = Field(
        ..., ge=0.0, le=100.0, description="CPU utilisation percentage (0–100)"
    )
    mem_usage: float = Field(
        ..., ge=0.0, le=100.0, description="Memory utilisation percentage (0–100)"
    )
    latency_ms: float = Field(
        ..., ge=0.0, description="P99 service latency in milliseconds"
    )
 
    @field_validator("latency_ms")
    @classmethod
    def latency_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("latency_ms must be non-negative")
        return v
 
 
class AnalysisResult(BaseModel):
    is_anomaly: bool
    threat_score: float = Field(..., ge=0.0, le=1.0)
    recommended_action: str
    raw_score: float
    processing_time_ms: float
 
 
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_loaded: bool
    version: str
 
 
# ---------------------------------------------------------------------------
# Business logic
# ---------------------------------------------------------------------------
_ACTION_MAP = {
    "restart_pod": "RESTART_POD",
    "scale_out": "SCALE_OUT_HPA",
    "reroute_traffic": "REROUTE_TRAFFIC",
    "flush_cache": "FLUSH_REDIS_CACHE",
    "drain_node": "DRAIN_NODE",
}
 
 
def compute_threat_score(raw_score: float) -> float:
    """
    Isolation Forest returns scores in roughly (-0.5, 0.5).
    Map to [0, 1] where 1 = maximum threat.
    """
    # IF negative scores = anomalies. Invert and normalise.
    normalised = (-raw_score + 0.5) / 1.0
    return float(np.clip(normalised, 0.0, 1.0))
 
 
def choose_action(
    threat_score: float,
    cpu: float,
    mem: float,
    latency: float,
) -> str:
    """Heuristic action selection based on telemetry profile."""
    if threat_score < 0.4:
        return "NO_ACTION"
    if cpu > 85:
        return _ACTION_MAP["scale_out"]
    if mem > 85:
        return _ACTION_MAP["flush_cache"]
    if latency > 2000:
        return _ACTION_MAP["reroute_traffic"]
    if threat_score > 0.80:
        return _ACTION_MAP["restart_pod"]
    return _ACTION_MAP["restart_pod"]
 
 
# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["Ops"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if _model is not None else "degraded",
        model_loaded=_model is not None,
        version="1.0.0",
    )
 
 
@app.get("/metrics", response_class=PlainTextResponse, tags=["Ops"])
async def metrics() -> PlainTextResponse:
    """Expose Prometheus-compatible metrics."""
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
 
 
@app.post("/api/v1/analyze", response_model=AnalysisResult, tags=["Intelligence"])
async def analyze(payload: TelemetryInput) -> AnalysisResult:
    """
    Run anomaly detection on a single telemetry snapshot.
 
    - **cpu_usage**: CPU utilisation %
    - **mem_usage**: Memory utilisation %
    - **latency_ms**: P99 service latency in ms
    """
    if _model is None:
        REQUEST_COUNT.labels(status="error").inc()
        raise HTTPException(status_code=503, detail="Model not loaded")
 
    t_start = time.perf_counter()
 
    feature_vector = np.array(
        [[payload.cpu_usage, payload.mem_usage, payload.latency_ms]]
    )
 
    with INFERENCE_LATENCY.time():
        raw_score: float = float(_model.decision_function(feature_vector)[0])
        prediction: int = int(_model.predict(feature_vector)[0])  # 1 or -1
 
    elapsed_ms = (time.perf_counter() - t_start) * 1000
 
    is_anomaly = prediction == -1
    threat_score = compute_threat_score(raw_score)
    action = choose_action(
        threat_score, payload.cpu_usage, payload.mem_usage, payload.latency_ms
    )
 
    # Update Prometheus metrics
    ANOMALY_SCORE_GAUGE.set(threat_score)
    REQUEST_COUNT.labels(status="ok").inc()
    if is_anomaly:
        ANOMALY_COUNTER.inc()
 
    logger.info(
        "Analyzed — cpu=%.1f mem=%.1f lat=%.0fms | anomaly=%s score=%.3f action=%s",
        payload.cpu_usage, payload.mem_usage, payload.latency_ms,
        is_anomaly, threat_score, action,
    )
 
    return AnalysisResult(
        is_anomaly=is_anomaly,
        threat_score=round(threat_score, 4),
        recommended_action=action,
        raw_score=round(raw_score, 6),
        processing_time_ms=round(elapsed_ms, 3),
    )
 
 
# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )