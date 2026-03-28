"""
cascade.py — Cascading Failure Engine
Autonomous Chaos Engineering & Self-Healing Platform

Models the Online Boutique service dependency graph and simulates
realistic chain-reaction failures. When a root service is injected
with a fault, downstream dependents degrade proportionally based on
dependency weight and current health scores.

Usage:
    from cascade import CascadeEngine, ServiceState, CascadeEvent
    engine = CascadeEngine()
    events = engine.inject("cartservice")
    map_data = engine.get_blast_radius_map()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("chaos.cascade")


# ---------------------------------------------------------------------------
# Service health states
# ---------------------------------------------------------------------------
class ServiceHealth(str, Enum):
    HEALTHY   = "HEALTHY"
    DEGRADED  = "DEGRADED"
    CRITICAL  = "CRITICAL"
    FAILED    = "FAILED"
    RECOVERING = "RECOVERING"


# ---------------------------------------------------------------------------
# Online Boutique dependency graph
# Each entry: service → list of (dependency, weight 0–1)
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

# Human-readable display names
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

# Approximate layout coordinates for the blast radius map (x%, y%)
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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ServiceState:
    name:         str
    health:       ServiceHealth = ServiceHealth.HEALTHY
    health_score: float         = 100.0   # 0–100
    failure_reason: str         = ""
    affected_by:  list[str]     = field(default_factory=list)
    recovery_eta_s: Optional[int] = None
    last_updated: float         = field(default_factory=time.time)

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
    triggered_by: str   # root cause service
    depth:        int   # hops from root cause


@dataclass
class BlastRadiusMap:
    """Full snapshot for the live blast radius visualisation."""
    root_cause:       str
    affected_count:   int
    total_services:   int
    events:           list[CascadeEvent]
    states:           dict[str, ServiceState]
    propagation_path: list[str]   # ordered chain from root to deepest affected
    estimated_user_impact_pct: float


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------
class CascadeEngine:
    """
    Simulates cascading failures across the Online Boutique service mesh.

    When inject(service) is called:
      1. The root service is set to FAILED.
      2. A BFS traversal propagates degradation through dependents,
         weighted by dependency strength.
      3. Health scores decay exponentially with distance.
      4. Autonomous recovery re-heals services in reverse-BFS order.
    """

    def __init__(self) -> None:
        self._states: dict[str, ServiceState] = {
            svc: ServiceState(name=svc)
            for svc in DEPENDENCY_GRAPH
        }
        self._events:       list[CascadeEvent] = []
        self._active_root:  Optional[str]      = None
        self._recovery_queue: list[tuple[float, str]] = []   # (recover_at_ts, service)
        self._reverse_graph = self._build_reverse_graph()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def inject(self, root_service: str) -> list[CascadeEvent]:
        """
        Inject a cascading failure starting at root_service.
        Returns all cascade events generated.
        """
        if root_service not in self._states:
            logger.error("Unknown service: %s", root_service)
            return []

        logger.warning("CASCADING FAILURE INJECTED → root=%s", root_service)
        self._active_root = root_service
        new_events: list[CascadeEvent] = []

        # BFS propagation
        visited:  set[str]             = set()
        queue:    list[tuple[str, int, str]] = [(root_service, 0, root_service)]

        while queue:
            service, depth, triggered_by = queue.pop(0)
            if service in visited:
                continue
            visited.add(service)

            prev_state = self._states[service]
            prev_health = prev_state.health

            # Compute new health score
            if depth == 0:
                new_score  = 0.0
                new_health = ServiceHealth.FAILED
                reason     = "Direct fault injection"
                eta        = 30
            else:
                # Decay: each hop attenuates by the max incoming dependency weight
                max_weight = max(
                    (w for dep, w in DEPENDENCY_GRAPH.get(triggered_by, [])
                     if dep == service or service == triggered_by),
                    default=0.5,
                )
                decay        = max_weight * (0.85 ** depth)
                new_score    = max(0.0, prev_state.health_score - decay * 100)
                new_health   = self._score_to_health(new_score)
                reason       = f"Cascade from {SERVICE_DISPLAY.get(triggered_by, triggered_by)}"
                eta          = 15 + depth * 10

            # Record state change
            self._states[service] = ServiceState(
                name           = service,
                health         = new_health,
                health_score   = round(new_score, 1),
                failure_reason = reason,
                affected_by    = list(visited - {service}),
                recovery_eta_s = eta,
                last_updated   = time.time(),
            )

            if new_health != prev_health:
                event = CascadeEvent(
                    timestamp    = time.time(),
                    service      = service,
                    previous     = prev_health,
                    current      = new_health,
                    health_score = new_score,
                    triggered_by = triggered_by,
                    depth        = depth,
                )
                new_events.append(event)
                self._events.append(event)
                logger.warning(
                    "CASCADE  depth=%d  %s → %s  (%.0f%%)",
                    depth, service, new_health.value, new_score,
                )

            # Schedule auto-recovery
            recover_at = time.time() + eta
            self._recovery_queue.append((recover_at, service))

            # Propagate to dependents (services that depend ON this service)
            for dependent in self._reverse_graph.get(service, []):
                if dependent not in visited:
                    queue.append((dependent, depth + 1, service))

        return new_events

    def tick_recovery(self) -> list[CascadeEvent]:
        """
        Call every second. Heals services whose recovery_eta has elapsed.
        Returns recovery events.
        """
        now = time.time()
        recovered: list[CascadeEvent] = []
        remaining: list[tuple[float, str]] = []

        for recover_at, service in self._recovery_queue:
            if now >= recover_at:
                state = self._states[service]
                if state.health != ServiceHealth.HEALTHY:
                    prev = state.health
                    self._states[service] = ServiceState(
                        name           = service,
                        health         = ServiceHealth.HEALTHY,
                        health_score   = 100.0,
                        failure_reason = "",
                        last_updated   = now,
                    )
                    event = CascadeEvent(
                        timestamp    = now,
                        service      = service,
                        previous     = prev,
                        current      = ServiceHealth.HEALTHY,
                        health_score = 100.0,
                        triggered_by = "auto-recovery",
                        depth        = 0,
                    )
                    recovered.append(event)
                    self._events.append(event)
                    logger.info("RECOVERED  %s → HEALTHY", service)
            else:
                remaining.append((recover_at, service))

        self._recovery_queue = remaining
        return recovered

    def get_blast_radius_map(self) -> BlastRadiusMap:
        """Return a full snapshot for the live visualisation."""
        affected = [
            s for s in self._states.values()
            if s.health != ServiceHealth.HEALTHY
        ]
        # Build propagation path (root → deepest affected)
        path: list[str] = []
        if self._active_root and self._events:
            seen: set[str] = set()
            path.append(self._active_root)
            seen.add(self._active_root)
            for evt in sorted(self._events, key=lambda e: e.depth):
                if evt.service not in seen and evt.current != ServiceHealth.HEALTHY:
                    path.append(evt.service)
                    seen.add(evt.service)

        # Estimate user impact — frontend + checkout are user-facing
        user_facing = {"frontend", "checkoutservice"}
        impacted_uf = sum(
            1 for s in user_facing
            if self._states[s].health != ServiceHealth.HEALTHY
        )
        user_impact = (impacted_uf / len(user_facing)) * 100.0

        return BlastRadiusMap(
            root_cause                = self._active_root or "none",
            affected_count            = len(affected),
            total_services            = len(self._states),
            events                    = list(self._events[-20:]),
            states                    = dict(self._states),
            propagation_path          = path,
            estimated_user_impact_pct = round(user_impact, 1),
        )

    def reset(self) -> None:
        """Restore all services to HEALTHY."""
        for svc in self._states:
            self._states[svc] = ServiceState(name=svc)
        self._events.clear()
        self._recovery_queue.clear()
        self._active_root = None
        logger.info("CascadeEngine reset — all services HEALTHY")

    def get_states(self) -> dict[str, ServiceState]:
        return dict(self._states)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_reverse_graph(self) -> dict[str, list[str]]:
        """Build a graph of: service → list of services that DEPEND ON IT."""
        rev: dict[str, list[str]] = {s: [] for s in DEPENDENCY_GRAPH}
        for svc, deps in DEPENDENCY_GRAPH.items():
            for dep, _ in deps:
                rev.setdefault(dep, []).append(svc)
        return rev

    @staticmethod
    def _score_to_health(score: float) -> ServiceHealth:
        if score >= 80:
            return ServiceHealth.HEALTHY
        if score >= 55:
            return ServiceHealth.DEGRADED
        if score >= 25:
            return ServiceHealth.CRITICAL
        return ServiceHealth.FAILED