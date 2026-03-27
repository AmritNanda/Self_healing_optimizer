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
 