"""
train_model.py — Baseline Isolation Forest trainer for Chaos Engineering Platform.
Generates synthetic telemetry data and trains a model saved as 'isolation_forest.joblib'.

Usage:
    python train_model.py
"""

import logging
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("model_trainer")

# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------
RANDOM_SEED = 42
N_NORMAL = 8_000
N_ANOMALY = 500
FEATURES = ["cpu_usage", "mem_usage", "latency_ms"]


def generate_normal_data(n: int) -> np.ndarray:
    """Simulate healthy cluster telemetry."""
    rng = np.random.default_rng(RANDOM_SEED)
    cpu = rng.normal(loc=35.0, scale=8.0, size=n).clip(5, 80)
    mem = rng.normal(loc=55.0, scale=10.0, size=n).clip(20, 85)
    latency = rng.normal(loc=120.0, scale=30.0, size=n).clip(20, 400)
    return np.column_stack([cpu, mem, latency])


def generate_anomaly_data(n: int) -> np.ndarray:
    """Simulate failure scenarios: CPU spike, OOM, latency explosion."""
    rng = np.random.default_rng(RANDOM_SEED + 1)
    scenarios = rng.integers(0, 3, size=n)
    samples = []
    for s in scenarios:
        if s == 0:  # CPU spike (pod crash / tight loop)
            cpu = rng.uniform(88, 100)
            mem = rng.uniform(50, 75)
            latency = rng.uniform(300, 900)
        elif s == 1:  # OOM pressure
            cpu = rng.uniform(40, 70)
            mem = rng.uniform(88, 100)
            latency = rng.uniform(500, 2000)
        else:  # Network partition / latency explosion
            cpu = rng.uniform(20, 50)
            mem = rng.uniform(40, 65)
            latency = rng.uniform(2000, 10000)
        samples.append([cpu, mem, latency])
    return np.array(samples)


# ---------------------------------------------------------------------------
# Train and persist
# ---------------------------------------------------------------------------
def train() -> None:
    logger.info("Generating synthetic telemetry data …")
    X_normal = generate_normal_data(N_NORMAL)
    X_anomaly = generate_anomaly_data(N_ANOMALY)
    X_train = np.vstack([X_normal, X_anomaly])

    logger.info(
        "Dataset shape: %s  (normal=%d, anomaly=%d)",
        X_train.shape, N_NORMAL, N_ANOMALY,
    )

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("iforest", IsolationForest(
            n_estimators=200,
            max_samples="auto",
            contamination=N_ANOMALY / (N_NORMAL + N_ANOMALY),
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )),
    ])

    logger.info("Training Isolation Forest pipeline …")
    pipeline.fit(X_train)

    output_path = "isolation_forest.joblib"
    joblib.dump(pipeline, output_path, compress=3)
    logger.info("Model saved → %s", output_path)

    # Quick sanity check
    sample_normal = np.array([[35.0, 55.0, 120.0]])
    sample_anomaly = np.array([[97.0, 95.0, 5000.0]])
    pred_n = pipeline.predict(sample_normal)[0]
    pred_a = pipeline.predict(sample_anomaly)[0]
    logger.info(
        "Sanity check — normal prediction: %d (expect 1),  anomaly prediction: %d (expect -1)",
        pred_n, pred_a,
    )


if __name__ == "__main__":
    train()