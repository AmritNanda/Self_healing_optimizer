"""
operator.py — Self-Healing Kubernetes Operator using Kopf.
Watches for chaos events, queries ML API, and auto-heals.
"""

import kopf
import kubernetes
import requests
import logging
import os

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
ML_API_URL = os.getenv("ML_API_URL", "http://ml-api-service.default.svc.cluster.local:8000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("self-healer")

# ---------------------------------------------------------------------------
# Helper: Query Prometheus for a pod's CPU usage
# ---------------------------------------------------------------------------
def get_pod_metrics(pod_name: str, namespace: str) -> dict:
    try:
        cpu_query = f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}",namespace="{namespace}"}}[2m])'
        mem_query = f'container_memory_usage_bytes{{pod="{pod_name}",namespace="{namespace}"}}'

        cpu_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": cpu_query}, timeout=5)
        mem_resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": mem_query}, timeout=5)

        cpu_data = cpu_resp.json()["data"]["result"]
        mem_data = mem_resp.json()["data"]["result"]

        cpu_usage = float(cpu_data[0]["value"][1]) * 100 if cpu_data else 10.0
        mem_bytes = float(mem_data[0]["value"][1]) if mem_data else 100 * 1024 * 1024
        mem_usage = (mem_bytes / (512 * 1024 * 1024)) * 100

        return {"cpu_usage": round(cpu_usage, 2), "mem_usage": round(mem_usage, 2), "latency_ms": 120.0}
    except Exception as e:
        logger.warning("Metrics fetch failed: %s", e)
        return {"cpu_usage": 10.0, "mem_usage": 50.0, "latency_ms": 120.0}


# ---------------------------------------------------------------------------
# Helper: Call ML API for anomaly analysis
# ---------------------------------------------------------------------------
def analyze_with_ml(metrics: dict) -> dict:
    try:
        resp = requests.post(f"{ML_API_URL}/api/v1/analyze", json=metrics, timeout=5)
        return resp.json()
    except Exception as e:
        logger.warning("ML API call failed: %s", e)
        return {"is_anomaly": False, "threat_score": 0.0, "recommended_action": "NO_ACTION"}


# ---------------------------------------------------------------------------
# Helper: Restart a pod
# ---------------------------------------------------------------------------
def restart_pod(pod_name: str, namespace: str):
    kubernetes.config.load_incluster_config()
    v1 = kubernetes.client.CoreV1Api()
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        logger.info("✅ Restarted pod: %s", pod_name)
    except Exception as e:
        logger.error("Failed to restart pod %s: %s", pod_name, e)


# ---------------------------------------------------------------------------
# Helper: Scale a deployment
# ---------------------------------------------------------------------------
def scale_deployment(deployment_name: str, namespace: str, replicas: int = 2):
    kubernetes.config.load_incluster_config()
    apps_v1 = kubernetes.client.AppsV1Api()
    try:
        apps_v1.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace=namespace,
            body={"spec": {"replicas": replicas}}
        )
        logger.info("✅ Scaled %s to %d replicas", deployment_name, replicas)
    except Exception as e:
        logger.error("Failed to scale %s: %s", deployment_name, e)


# ---------------------------------------------------------------------------
# Kopf Handler: Watch pod failures
# ---------------------------------------------------------------------------
@kopf.on.field("pods", field="status.phase")
def pod_phase_changed(old, new, name, namespace, **kwargs):
    if namespace not in ["applications"]:
        return

    if new in ["Failed", "Unknown"]:
        logger.info("🚨 Pod %s in %s entered phase: %s", name, namespace, new)

        metrics = get_pod_metrics(name, namespace)
        result = analyze_with_ml(metrics)

        logger.info("🧠 ML Result: anomaly=%s score=%.3f action=%s",
                    result["is_anomaly"], result["threat_score"], result["recommended_action"])

        if result["is_anomaly"]:
            action = result["recommended_action"]
            if action == "RESTART_POD":
                restart_pod(name, namespace)
            elif action == "SCALE_OUT_HPA":
                scale_deployment(name.rsplit("-", 2)[0], namespace, replicas=3)
            else:
                restart_pod(name, namespace)


# ---------------------------------------------------------------------------
# Kopf Handler: Watch for high restart counts (CrashLoopBackOff)
# ---------------------------------------------------------------------------
@kopf.on.field("pods", field="status.containerStatuses")
def container_status_changed(old, new, name, namespace, **kwargs):
    if namespace not in ["applications"]:
        return

    if not new:
        return

    for container in new:
        restart_count = container.get("restartCount", 0)
        if restart_count >= 3:
            logger.info("🔁 CrashLoop detected on %s (restarts=%d)", name, restart_count)
            metrics = get_pod_metrics(name, namespace)
            result = analyze_with_ml(metrics)

            if result["is_anomaly"] or restart_count >= 5:
                restart_pod(name, namespace)

