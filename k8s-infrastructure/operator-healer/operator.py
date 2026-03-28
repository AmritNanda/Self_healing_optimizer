import os
import asyncio
import logging
import zlib
import kopf
import kubernetes
import httpx

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
ML_API_URL = os.getenv("ML_API_URL", "http://ml-api-service.online-boutique.svc.cluster.local:8000")

# Sharding config for horizontally scaling the operator
SHARD_ID = int(os.getenv("SHARD_ID", "0"))
TOTAL_SHARDS = int(os.getenv("TOTAL_SHARDS", "1"))

# Global clients (Initialized in startup)
v1 = None
apps_v1 = None
httpx_client = None

# Track pods currently undergoing healing to avoid race conditions between timer and handlers
HEALING_LOCKS = set()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("self-healer")

def is_pod_in_shard(pod_name: str) -> bool:
    """Deterministic sharding based on pod name."""
    if TOTAL_SHARDS <= 1:
        return True
    return (zlib.adler32(pod_name.encode()) % TOTAL_SHARDS) == SHARD_ID

# ---------------------------------------------------------------------------
# Kopf Startup: Initialize global clients once
# ---------------------------------------------------------------------------
@kopf.on.startup()
async def configure(settings: kopf.OperatorSettings, **kwargs):
    global v1, apps_v1, httpx_client
    try:
        kubernetes.config.load_incluster_config()
        logger.info("☸️ Using In-Cluster Config")
    except Exception:
        kubernetes.config.load_kube_config()
        logger.info("🏡 Using Local Kube Config")
    
    v1 = kubernetes.client.CoreV1Api()
    apps_v1 = kubernetes.client.AppsV1Api()
    httpx_client = httpx.AsyncClient()

@kopf.on.cleanup()
async def cleanup(**kwargs):
    global httpx_client
    if httpx_client:
        await httpx_client.aclose()
        logger.info("🧹 Shared HTTP client closed.")

# ---------------------------------------------------------------------------
# Helper: Query Prometheus for a pod's CPU usage
# ---------------------------------------------------------------------------
async def get_pod_metrics(pod_name: str, namespace: str) -> dict:
    if not httpx_client:
        return {"cpu_usage": 10.0, "mem_usage": 50.0, "latency_ms": 120.0}
    try:
        # Use a narrower 30s window for faster detection of sudden spikes
        cpu_query = f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}",namespace="{namespace}"}}[30s])'
        mem_query = f'container_memory_usage_bytes{{pod="{pod_name}",namespace="{namespace}"}}'

        # Run queries in parallel for maximum speed
        cpu_task = httpx_client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": cpu_query}, timeout=3)
        mem_task = httpx_client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": mem_query}, timeout=3)
        
        cpu_resp, mem_resp = await asyncio.gather(cpu_task, mem_task)

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
async def analyze_with_ml(metrics: dict) -> dict:
    if not httpx_client:
        return {"is_anomaly": False, "threat_score": 0.0, "recommended_action": "NO_ACTION"}
    try:
        resp = await httpx_client.post(f"{ML_API_URL}/api/v1/analyze", json=metrics, timeout=3)
        return resp.json()
    except Exception as e:
        logger.warning("ML API call failed: %s", e)
        return {"is_anomaly": False, "threat_score": 0.0, "recommended_action": "NO_ACTION"}


# ---------------------------------------------------------------------------
# Helper: Restart a pod
# ---------------------------------------------------------------------------
async def restart_pod(pod_name: str, namespace: str):
    if not v1:
        return
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        logger.info("✅ Restarted pod: %s", pod_name)
    except Exception as e:
        logger.error("Failed to restart pod %s: %s", pod_name, e)


# ---------------------------------------------------------------------------
# Helper: Scale a deployment
# ---------------------------------------------------------------------------
async def scale_deployment(deployment_name: str, namespace: str, replicas: int = 2):
    if not apps_v1:
        return
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
# ---------------------------------------------------------------------------
# Helper: Logic for analyzing and healing a single pod
# ---------------------------------------------------------------------------
async def analyze_and_heal_pod(name: str, namespace: str, trigger_source: str = "Event"):
    """
    Core detection & healing logic. Used by both async events and proactive timers.
    """
    if name in HEALING_LOCKS:
        return

    # Add lock immediately to prevent double-healing during long ML/K8s operations
    HEALING_LOCKS.add(name)
    try:
        logger.info("🔭 [%s] Analyzing pod: %s/%s", trigger_source, namespace, name)

        # 1. Fetch telemetry
        metrics = await get_pod_metrics(name, namespace)
        
        # 2. ML Inference
        result = await analyze_with_ml(metrics)

        # 3. Decision making
        if result.get("is_anomaly"):
            action = result.get("recommended_action")
            logger.info("🚨 Anomaly detected on %s via %s: action=%s score=%.3f", 
                        name, trigger_source, action, result.get("threat_score"))

            if action == "RESTART_POD":
                await restart_pod(name, namespace)
            elif action == "SCALE_OUT_HPA":
                # Scale the deployment (assumes standard naming pattern: deployment-suffix)
                deployment_name = name.rsplit("-", 2)[0]
                await scale_deployment(deployment_name, namespace, replicas=3)
            else:
                await restart_pod(name, namespace)
        else:
            # Special Case: Safety fallback for event-based triggers where pod is already Failed
            if trigger_source == "PhaseEvent":
                 logger.info("🛡️ Safety Fallback: Restarting Failed pod %s despite no ML anomaly verdict", name)
                 await restart_pod(name, namespace)

    except Exception as e:
        logger.error("Error during analysis of %s: %s", name, e)
    finally:
        # Hold lock for a few seconds to let K8s state settle
        await asyncio.sleep(8)
        HEALING_LOCKS.discard(name)


# ---------------------------------------------------------------------------
# Kopf Handler: Watch pod failures (Phase Changes)
# ---------------------------------------------------------------------------
@kopf.on.field("pods", field="status.phase")
async def pod_phase_changed(old, new, name, namespace, **kwargs):
    if namespace not in ["online-boutique"] or not is_pod_in_shard(name):
        return

    if new in ["Failed", "Unknown"]:
        await analyze_and_heal_pod(name, namespace, trigger_source="PhaseEvent")


# ---------------------------------------------------------------------------
# Kopf Handler: Watch for high restart counts (CrashLoopBackOff)
# ---------------------------------------------------------------------------
@kopf.on.field("pods", field="status.containerStatuses")
async def container_status_changed(old, new, name, namespace, **kwargs):
    if namespace not in ["online-boutique"] or not is_pod_in_shard(name):
        return

    if not new or name in HEALING_LOCKS:
        return

    for container in new:
        restart_count = container.get("restartCount", 0)
        if restart_count >= 3:
            logger.info("🔁 CrashLoop detected on %s (restarts=%d)", name, restart_count)
            
            # FAST TRACK: Instant restart if loop is severe (>=5)
            if restart_count >= 5:
                HEALING_LOCKS.add(name)
                try:
                    await restart_pod(name, namespace)
                finally:
                    await asyncio.sleep(5)
                    HEALING_LOCKS.discard(name)
                return

            await analyze_and_heal_pod(name, namespace, trigger_source="RestartEvent")


# ---------------------------------------------------------------------------
# Timer: Cluster-Wide Batch Proactive Metric Scan (Every 15s)
# ---------------------------------------------------------------------------
@kopf.on.timer("pods", interval=15.0)
async def batch_proactive_metric_scan(**kwargs):
    """
    Scans ALL running pods in parallel using asyncio.gather.
    This is significantly more efficient than individual timers per pod.
    """
    if not v1:
        return

    try:
        # List all pods in the target namespace
        # In a real production system, use labels like 'monitored=true'
        ret = v1.list_namespaced_pod(namespace="online-boutique")
        active_pods = [p.metadata.name for p in ret.items if p.status.phase == "Running"]

        # Filter for pods assigned to this shard
        sharded_pods = [p for p in active_pods if is_pod_in_shard(p)]
        
        # Filter for pods not currently being healed
        pods_to_scan = [p for p in sharded_pods if p not in HEALING_LOCKS]

        if not pods_to_scan:
            return

        logger.info("🕒 Batch Timer: Scanning %d pods in parallel (%d total in shard)", 
                    len(pods_to_scan), len(sharded_pods))

        # Parallel Execution: asyncio.gather treats each pod analysis as a concurrent task
        tasks = [analyze_and_heal_pod(p, "online-boutique", trigger_source="BatchTimer") for p in pods_to_scan]
        await asyncio.gather(*tasks)

    except Exception as e:
        logger.error("Batch scan failed: %s", e)

