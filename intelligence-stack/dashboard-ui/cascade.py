"""
cascade.py — Cascading Failure Engine (Live Cluster Mode)
Autonomous Chaos Engineering & Self-Healing Platform

Connects to Prometheus and Kubernetes to monitor real service health
across the Online Boutique deployment. Detects cascading failures
in real-time when chaos is injected.

Usage:
    from cascade import CascadeEngine
    engine = CascadeEngine()
    await engine.sync_from_cluster()
    map_data = engine.get_blast_radius_map()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx
import kubernetes
import kubernetes.client

logger = logging.getLogger("chaos.cascade")


# ---------------------------------------------------------------------------
# Service health states
# ---------------------------------------------------------------------------
class ServiceHealth(str, Enum):
    HEALTHY    = "HEALTHY"
    DEGRADED   = "DEGRADED"
    CRITICAL   = "CRITICAL"
    FAILED     = "FAILED"
    RECOVERING = "RECOVERING"


# ---------------------------------------------------------------------------
# Online Boutique dependency graph (architecturally accurate)
# Each entry: service -> list of (dependency, weight 0-1)
# Weight = how badly this service suffers if the dependency fails
# ---------------------------------------------------------------------------
DEPENDENCY_GRAPH: dict[str, list[tuple[str, float]]] = {
    "frontend":              [("productcatalogservice", 0.9),
                              ("cartservice",           0.85),
                              ("recommendationservice", 0.6),
                              ("currencyservice",       0.75),
                              ("adservice",             0.3)],
    "checkoutservice":       [("cartservice",           0.95),
                              ("paymentservice",        0.99),
                              ("emailservice",          0.5),
                              ("currencyservice",       0.8),
                              ("shippingservice",       0.85),
                              ("productcatalogservice", 0.7)],
    "cartservice":           [("redis-cart",            0.98)],
    "recommendationservice": [("productcatalogservice", 0.9)],
    "productcatalogservice": [],
    "paymentservice":        [],
    "shippingservice":       [],
    "emailservice":          [],
    "currencyservice":       [],
    "adservice":             [("productcatalogservice", 0.4)],
    "redis-cart":            [],
}

SERVICE_DISPLAY: dict[str, str] = {
    "frontend":              "Frontend",
    "checkoutservice":       "Checkout",
    "cartservice":           "Cart",
    "recommendationservice": "Recommend",
    "productcatalogservice": "Catalog",
    "paymentservice":        "Payment",
    "shippingservice":       "Shipping",
    "emailservice":          "Email",
    "currencyservice":       "Currency",
    "adservice":             "Ads",
    "redis-cart":            "Redis Cache",
}

# Container name → service key mapping (where they differ)
CONTAINER_TO_SERVICE: dict[str, str] = {
    "server":       "redis-cart",   # redis container name in some versions
    "redis":        "redis-cart",
    "redis-cart":   "redis-cart",
}

SERVICE_POSITIONS: dict[str, tuple[float, float]] = {
    "frontend":              (50.0, 8.0),
    "checkoutservice":       (25.0, 30.0),
    "cartservice":           (50.0, 30.0),
    "recommendationservice": (75.0, 30.0),
    "productcatalogservice": (62.0, 55.0),
    "paymentservice":        (12.0, 55.0),
    "shippingservice":       (30.0, 55.0),
    "emailservice":          (10.0, 78.0),
    "currencyservice":       (45.0, 78.0),
    "adservice":             (82.0, 55.0),
    "redis-cart":            (55.0, 55.0),
}

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
K8S_NAMESPACE  = os.getenv("K8S_NAMESPACE", "online-boutique")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ServiceMetrics:
    """Raw metrics collected from the live cluster."""
    pod_ready:          bool  = True
    pod_phase:          str   = "Running"
    cpu_percent:        float = 0.0
    memory_mb:          float = 0.0
    restart_count:      int   = 0
    replicas_available: int   = 1
    replicas_desired:   int   = 1


@dataclass
class ServiceState:
    name:           str
    health:         ServiceHealth = ServiceHealth.HEALTHY
    health_score:   float         = 100.0
    failure_reason: str           = ""
    affected_by:    list[str]     = field(default_factory=list)
    recovery_eta_s: Optional[int] = None
    last_updated:   float         = field(default_factory=time.time)
    metrics:        Optional[ServiceMetrics] = None

    @property
    def display_name(self) -> str:
        return SERVICE_DISPLAY.get(self.name, self.name)

    @property
    def color(self) -> str:
        return {
            ServiceHealth.HEALTHY:    "#00e676",
            ServiceHealth.DEGRADED:   "#ffab00",
            ServiceHealth.CRITICAL:   "#ff6b35",
            ServiceHealth.FAILED:     "#ff3d5a",
            ServiceHealth.RECOVERING: "#7c4dff",
        }[self.health]

    @property
    def position(self) -> tuple[float, float]:
        return SERVICE_POSITIONS.get(self.name, (50.0, 50.0))


@dataclass
class CascadeEvent:
    timestamp:    float
    service:      str
    previous:     ServiceHealth
    current:      ServiceHealth
    health_score: float
    triggered_by: str
    depth:        int


@dataclass
class BlastRadiusMap:
    """Full snapshot for the live blast radius visualisation."""
    root_cause:                str
    affected_count:            int
    total_services:            int
    events:                    list[CascadeEvent]
    states:                    dict[str, ServiceState]
    propagation_path:          list[str]
    estimated_user_impact_pct: float


# ---------------------------------------------------------------------------
# Core engine — live cluster mode
# ---------------------------------------------------------------------------
class CascadeEngine:
    """
    Live cascading failure engine that reads real K8s + Prometheus data.

    - sync_from_cluster() polls real metrics and updates all service states
    - inject() marks a service as the chaos target for blast radius tracking
    - get_blast_radius_map() returns a snapshot for visualization
    """

    def __init__(
        self,
        prometheus_url: str = PROMETHEUS_URL,
        namespace:      str = K8S_NAMESPACE,
    ) -> None:
        self._prometheus_url = prometheus_url
        self._namespace      = namespace
        self._states: dict[str, ServiceState] = {
            svc: ServiceState(name=svc) for svc in DEPENDENCY_GRAPH
        }
        self._events:       list[CascadeEvent] = []
        self._active_root:  Optional[str]      = None
        self._prev_restarts: dict[str, int]    = {}
        self._reverse_graph                    = self._build_reverse_graph()

        # Initialize Kubernetes client (works both in-cluster and local)
        self._k8s_ready = False
        self._v1:      Optional[kubernetes.client.CoreV1Api]  = None
        self._apps_v1: Optional[kubernetes.client.AppsV1Api] = None
        self._init_k8s()

    def _init_k8s(self) -> None:
        """Initialize Kubernetes client, preferring in-cluster config."""
        try:
            kubernetes.config.load_incluster_config()
            logger.info("☸️  K8s: using in-cluster config")
        except Exception:
            try:
                kubernetes.config.load_kube_config()
                logger.info("🏡  K8s: using local kubeconfig")
            except Exception as e:
                logger.warning("K8s config unavailable: %s", e)
                return
        self._v1      = kubernetes.client.CoreV1Api()
        self._apps_v1 = kubernetes.client.AppsV1Api()
        self._k8s_ready = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def sync_from_cluster(self) -> list[CascadeEvent]:
        """
        Poll real metrics from K8s/Prometheus, update service states.
        Returns list of CascadeEvent for any state transitions detected.
        """
        # Gather all data sources in parallel
        deploys, pods, cpu_map, mem_map, restart_map = await asyncio.gather(
            self._get_deployments(),
            self._get_pod_statuses(),
            self._get_cpu_by_service(),
            self._get_memory_by_service(),
            self._get_restart_counts(),
        )

        now        = time.time()
        new_events: list[CascadeEvent] = []

        for svc in DEPENDENCY_GRAPH:
            prev_state = self._states[svc]
            dep_info   = deploys.get(svc, {})
            pod_info   = pods.get(svc, {})

            desired   = dep_info.get("desired", 1)
            available = dep_info.get("available", desired)

            metrics = ServiceMetrics(
                pod_ready          = pod_info.get("ready", available > 0),
                pod_phase          = pod_info.get("phase", "Running" if available > 0 else "Unknown"),
                cpu_percent        = cpu_map.get(svc, 0.0),
                memory_mb          = mem_map.get(svc, 0.0),
                restart_count      = restart_map.get(svc, pod_info.get("restarts", 0)),
                replicas_available = available,
                replicas_desired   = desired,
            )

            base_score  = self._compute_health_score(metrics, svc)
            final_score = self._apply_dependency_penalty(svc, base_score)
            new_health  = self._score_to_health(final_score)
            reason      = self._determine_reason(metrics, svc)

            # Detect recovery transition
            if (prev_state.health in (ServiceHealth.FAILED, ServiceHealth.CRITICAL,
                                       ServiceHealth.DEGRADED)
                    and final_score >= 80.0):
                new_health = ServiceHealth.RECOVERING
                reason     = "Recovering — metrics normalizing"

            # Determine affected_by
            affected_by: list[str] = []
            if new_health != ServiceHealth.HEALTHY:
                for dep_name, _ in DEPENDENCY_GRAPH.get(svc, []):
                    dep_st = self._states.get(dep_name)
                    if dep_st and dep_st.health != ServiceHealth.HEALTHY:
                        affected_by.append(dep_name)

            eta = {
                ServiceHealth.FAILED:     30,
                ServiceHealth.CRITICAL:   20,
                ServiceHealth.DEGRADED:   10,
                ServiceHealth.RECOVERING:  5,
            }.get(new_health)

            self._states[svc] = ServiceState(
                name           = svc,
                health         = new_health,
                health_score   = round(final_score, 1),
                failure_reason = reason,
                affected_by    = affected_by,
                recovery_eta_s = eta,
                last_updated   = now,
                metrics        = metrics,
            )

            if new_health != prev_state.health:
                depth = self._compute_cascade_depth(svc)
                event = CascadeEvent(
                    timestamp    = now,
                    service      = svc,
                    previous     = prev_state.health,
                    current      = new_health,
                    health_score = final_score,
                    triggered_by = self._active_root or "cluster",
                    depth        = depth,
                )
                new_events.append(event)
                self._events.append(event)
                logger.info(
                    "STATE CHANGE  %s: %s -> %s  (%.0f%%)",
                    svc, prev_state.health.value, new_health.value, final_score,
                )

        self._prev_restarts = {
            svc: restart_map.get(svc, 0) for svc in DEPENDENCY_GRAPH
        }

        # Auto-clear root if all services recovered
        if self._active_root:
            if all(s.health_score >= 80 for s in self._states.values()):
                logger.info("All services recovered — clearing root: %s", self._active_root)
                self._active_root = None

        return new_events

    def inject(self, root_service: str) -> None:
        """Mark a service as the chaos injection target for blast radius tracking."""
        if root_service not in self._states:
            logger.error("Unknown service: %s", root_service)
            return
        self._active_root = root_service
        logger.warning("CHAOS TARGET MARKED → root=%s", root_service)

    def get_blast_radius_map(self) -> BlastRadiusMap:
        """Return a full snapshot for the live visualisation."""
        affected = [s for s in self._states.values()
                    if s.health != ServiceHealth.HEALTHY]

        path = self._build_propagation_path()

        user_facing = {"frontend", "checkoutservice"}
        impacted    = sum(1 for s in user_facing
                         if self._states[s].health != ServiceHealth.HEALTHY)
        user_impact = (impacted / len(user_facing)) * 100.0

        return BlastRadiusMap(
            root_cause                = self._active_root or "none",
            affected_count            = len(affected),
            total_services            = len(self._states),
            events                    = list(self._events[-30:]),
            states                    = dict(self._states),
            propagation_path          = path,
            estimated_user_impact_pct = round(user_impact, 1),
        )

    def reset(self) -> None:
        """Restore all services to HEALTHY and clear event history."""
        for svc in self._states:
            self._states[svc] = ServiceState(name=svc)
        self._events.clear()
        self._active_root = None
        self._prev_restarts.clear()
        logger.info("CascadeEngine reset — all services HEALTHY")

    def get_states(self) -> dict[str, ServiceState]:
        return dict(self._states)

    # ------------------------------------------------------------------
    # Kubernetes data collection (uses kubernetes Python client)
    # ------------------------------------------------------------------
    async def _get_deployments(self) -> dict[str, dict]:
        """
        Fetch deployment replica counts from Kubernetes API.
        Returns: {service_name: {desired: int, available: int}}
        """
        if not self._k8s_ready or not self._apps_v1:
            return {}
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self._apps_v1.list_namespaced_deployment(namespace=self._namespace)
            )
            result: dict[str, dict] = {}
            for dep in resp.items:
                name = dep.metadata.name
                if name in DEPENDENCY_GRAPH:
                    desired   = dep.spec.replicas or 1
                    available = dep.status.available_replicas or 0
                    result[name] = {"desired": desired, "available": available}
            return result
        except Exception as e:
            logger.warning("K8s deployments fetch failed: %s", e)
            return {}

    async def _get_pod_statuses(self) -> dict[str, dict]:
        """
        Fetch pod phase, readiness, and restart counts from Kubernetes API.
        Returns: {service_name: {phase, ready, restarts}}
        """
        if not self._k8s_ready or not self._v1:
            return {}
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self._v1.list_namespaced_pod(namespace=self._namespace)
            )
            result: dict[str, dict] = {}
            for pod in resp.items:
                svc = self._pod_to_service(pod.metadata.name)
                if not svc:
                    continue
                phase    = pod.status.phase or "Unknown"
                ready    = False
                restarts = 0
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        ready     = cs.ready or False
                        restarts += cs.restart_count or 0
                # Prefer the unhealthy pod entry if multiple pods exist
                if svc not in result or not ready:
                    result[svc] = {
                        "phase":    phase,
                        "ready":    ready,
                        "restarts": restarts,
                    }
            return result
        except Exception as e:
            logger.warning("K8s pods fetch failed: %s", e)
            return {}

    # ------------------------------------------------------------------
    # Prometheus data collection
    # ------------------------------------------------------------------
    async def _get_cpu_by_service(self) -> dict[str, float]:
        """
        Query Prometheus for CPU usage % per container in the namespace.
        Uses container label (not pod) for accurate per-service matching.
        """
        query = (
            f'sum by (container) ('
            f'rate(container_cpu_usage_seconds_total{{'
            f'namespace="{self._namespace}",'
            f'container!="",'
            f'container!="POD"'
            f'}}[2m])'
            f') * 100'
        )
        results = await self._query_prometheus(query)
        out: dict[str, float] = {}
        for r in results:
            container = r["metric"].get("container", "")
            svc       = self._container_to_service(container)
            if svc:
                out[svc] = max(out.get(svc, 0.0), float(r["value"][1]))

        # Fallback: try pod-level query if container query returns nothing
        if not out:
            query2 = (
                f'sum by (pod) ('
                f'rate(container_cpu_usage_seconds_total{{'
                f'namespace="{self._namespace}",'
                f'container!="",'
                f'container!="POD"'
                f'}}[2m])'
                f') * 100'
            )
            results2 = await self._query_prometheus(query2)
            for r in results2:
                pod = r["metric"].get("pod", "")
                svc = self._pod_to_service(pod)
                if svc:
                    out[svc] = max(out.get(svc, 0.0), float(r["value"][1]))
        return out

    async def _get_memory_by_service(self) -> dict[str, float]:
        """
        Query Prometheus for memory usage (MB) per container in the namespace.
        """
        query = (
            f'sum by (container) ('
            f'container_memory_working_set_bytes{{'
            f'namespace="{self._namespace}",'
            f'container!="",'
            f'container!="POD"'
            f'}}'
            f') / 1024 / 1024'
        )
        results = await self._query_prometheus(query)
        out: dict[str, float] = {}
        for r in results:
            container = r["metric"].get("container", "")
            svc       = self._container_to_service(container)
            if svc:
                out[svc] = max(out.get(svc, 0.0), float(r["value"][1]))

        # Fallback: try pod-level query
        if not out:
            query2 = (
                f'sum by (pod) ('
                f'container_memory_working_set_bytes{{'
                f'namespace="{self._namespace}",'
                f'container!="",'
                f'container!="POD"'
                f'}}'
                f') / 1024 / 1024'
            )
            results2 = await self._query_prometheus(query2)
            for r in results2:
                pod = r["metric"].get("pod", "")
                svc = self._pod_to_service(pod)
                if svc:
                    out[svc] = max(out.get(svc, 0.0), float(r["value"][1]))
        return out

    async def _get_restart_counts(self) -> dict[str, int]:
        """
        Query Prometheus for total restart counts per pod in the namespace.
        Falls back to pod status data if kube-state-metrics is unavailable.
        """
        query = (
            f'sum by (pod) ('
            f'kube_pod_container_status_restarts_total{{'
            f'namespace="{self._namespace}"'
            f'}}'
            f')'
        )
        results = await self._query_prometheus(query)
        out: dict[str, int] = {}
        for r in results:
            pod = r["metric"].get("pod", "")
            svc = self._pod_to_service(pod)
            if svc:
                out[svc] = max(out.get(svc, 0), int(float(r["value"][1])))
        return out

    async def _query_prometheus(self, query: str) -> list:
        """Execute a Prometheus instant query and return result list."""
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(
                    f"{self._prometheus_url}/api/v1/query",
                    params={"query": query},
                    timeout=5.0,
                )
                r.raise_for_status()
                return r.json().get("data", {}).get("result", [])
            except Exception as e:
                logger.debug("Prometheus query failed [%s]: %s", query[:60], e)
                return []

    # ------------------------------------------------------------------
    # Health computation
    # ------------------------------------------------------------------
    def _compute_health_score(self, m: ServiceMetrics, svc: str) -> float:
        """Compute 0–100 health score from real cluster metrics."""
        # Hard failures
        if m.replicas_desired > 0 and m.replicas_available == 0:
            return 0.0
        if m.pod_phase in ("Failed", "Unknown"):
            return 0.0
        if not m.pod_ready and m.pod_phase not in ("Running", "Pending"):
            return 5.0

        score = 100.0

        # Pod not ready (health check failing)
        if not m.pod_ready:
            score -= 30

        # CPU penalties
        if m.cpu_percent > 90:
            score -= 35
        elif m.cpu_percent > 70:
            score -= 20
        elif m.cpu_percent > 50:
            score -= 10

        # Memory penalties (Online Boutique services typically 30–200 MB)
        if m.memory_mb > 500:
            score -= 30
        elif m.memory_mb > 300:
            score -= 15

        # Recent restart penalties (delta since last sync)
        prev   = self._prev_restarts.get(svc, 0)
        recent = max(0, m.restart_count - prev)
        if recent > 3:
            score -= 40
        elif recent > 1:
            score -= 25
        elif recent > 0:
            score -= 15

        # Chronic restart penalties
        if m.restart_count > 10:
            score -= 15
        elif m.restart_count > 5:
            score -= 8

        return max(0.0, min(100.0, score))

    def _apply_dependency_penalty(self, svc: str, base_score: float) -> float:
        """Penalize services whose dependencies are unhealthy."""
        deps = DEPENDENCY_GRAPH.get(svc, [])
        if not deps:
            return base_score
        penalty = 0.0
        for dep_name, weight in deps:
            dep_st = self._states.get(dep_name)
            if dep_st and dep_st.health_score < 80:
                dep_loss = (100.0 - dep_st.health_score) / 100.0
                penalty += dep_loss * weight * 40
        return max(0.0, base_score - penalty)

    def _determine_reason(self, m: ServiceMetrics, svc: str) -> str:
        """Build a human-readable failure reason string."""
        reasons: list[str] = []
        if m.replicas_available == 0 and m.replicas_desired > 0:
            reasons.append("No replicas available")
        elif not m.pod_ready:
            reasons.append(f"Pod not ready ({m.pod_phase})")
        if m.cpu_percent > 70:
            reasons.append(f"High CPU: {m.cpu_percent:.1f}%")
        if m.memory_mb > 300:
            reasons.append(f"High memory: {m.memory_mb:.0f}MB")
        prev   = self._prev_restarts.get(svc, 0)
        recent = max(0, m.restart_count - prev)
        if recent > 0:
            reasons.append(f"{recent} recent restart(s)")
        for dep_name, _ in DEPENDENCY_GRAPH.get(svc, []):
            dep_st = self._states.get(dep_name)
            if dep_st and dep_st.health != ServiceHealth.HEALTHY:
                reasons.append(f"Dep {dep_st.display_name} {dep_st.health.value.lower()}")
                break
        return "; ".join(reasons[:3]) if reasons else ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pod_to_service(self, pod_name: str) -> Optional[str]:
        """Map a pod name (e.g. 'frontend-759775d795-tw8wp') to a service key."""
        pod_lower = pod_name.lower()
        # Match longest service name first to avoid prefix collisions
        for svc in sorted(DEPENDENCY_GRAPH.keys(), key=len, reverse=True):
            if pod_lower.startswith(svc):
                return svc
        return None

    def _container_to_service(self, container: str) -> Optional[str]:
        """Map a container name to a service key (handles aliases like 'redis')."""
        if container in DEPENDENCY_GRAPH:
            return container
        return CONTAINER_TO_SERVICE.get(container)

    def _build_reverse_graph(self) -> dict[str, list[str]]:
        """Build graph of service → services that depend ON it."""
        rev: dict[str, list[str]] = {s: [] for s in DEPENDENCY_GRAPH}
        for svc, deps in DEPENDENCY_GRAPH.items():
            for dep, _ in deps:
                rev.setdefault(dep, []).append(svc)
        return rev

    def _compute_cascade_depth(self, svc: str) -> int:
        """BFS distance from active root to svc."""
        if not self._active_root or svc == self._active_root:
            return 0
        visited: set[str]              = set()
        queue:   list[tuple[str, int]] = [(self._active_root, 0)]
        while queue:
            cur, depth = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            if cur == svc:
                return depth
            for dep in self._reverse_graph.get(cur, []):
                if dep not in visited:
                    queue.append((dep, depth + 1))
        return -1

    def _build_propagation_path(self) -> list[str]:
        """Build ordered list of affected services from root outward."""
        if not self._active_root:
            return [
                s.name for s in sorted(
                    (s for s in self._states.values() if s.health != ServiceHealth.HEALTHY),
                    key=lambda x: x.health_score,
                )
            ]
        path:    list[str] = []
        visited: set[str]  = set()
        queue   = [self._active_root]
        while queue:
            svc = queue.pop(0)
            if svc in visited:
                continue
            visited.add(svc)
            if self._states.get(svc, ServiceState(name=svc)).health != ServiceHealth.HEALTHY:
                path.append(svc)
            for dep in self._reverse_graph.get(svc, []):
                if dep not in visited:
                    queue.append(dep)
        return path

    @staticmethod
    def _score_to_health(score: float) -> ServiceHealth:
        if score >= 80:
            return ServiceHealth.HEALTHY
        if score >= 55:
            return ServiceHealth.DEGRADED
        if score >= 25:
            return ServiceHealth.CRITICAL
        return ServiceHealth.FAILED