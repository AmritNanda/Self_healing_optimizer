"""
blast_radius.py — Live Blast Radius Map Renderer
Autonomous Chaos Engineering & Self-Healing Platform

Renders an interactive Plotly network graph showing real-time service
health, cascade propagation paths, and estimated user impact.

Usage:
    from blast_radius import BlastRadiusRenderer
    renderer = BlastRadiusRenderer()
    fig = renderer.build_figure(blast_map)
"""

from __future__ import annotations

import math
from typing import Optional

import plotly.graph_objects as go

from cascade import (
    BlastRadiusMap,
    CascadeEngine,
    ServiceHealth,
    ServiceState,
    DEPENDENCY_GRAPH,
    SERVICE_DISPLAY,
    SERVICE_POSITIONS,
)

# ---------------------------------------------------------------------------
# Health → visual mapping
# ---------------------------------------------------------------------------
HEALTH_COLORS = {
    ServiceHealth.HEALTHY:    "#00e676",
    ServiceHealth.DEGRADED:   "#ffab00",
    ServiceHealth.CRITICAL:   "#ff6b35",
    ServiceHealth.FAILED:     "#ff3d5a",
    ServiceHealth.RECOVERING: "#7c4dff",
}

HEALTH_SYMBOLS = {
    ServiceHealth.HEALTHY:    "circle",
    ServiceHealth.DEGRADED:   "diamond",
    ServiceHealth.CRITICAL:   "diamond",
    ServiceHealth.FAILED:     "x",
    ServiceHealth.RECOVERING: "circle",
}

EDGE_COLOR_NORMAL   = "rgba(30,45,69,0.6)"
EDGE_COLOR_ACTIVE   = "rgba(255,61,90,0.7)"
EDGE_COLOR_RECOVER  = "rgba(124,77,255,0.5)"


class BlastRadiusRenderer:
    """
    Builds a Plotly figure representing the live blast radius map.

    Node size   = service health score (bigger = healthier)
    Node color  = health state (green/amber/red/purple)
    Edge color  = red if cascade path, purple if recovering, gray otherwise
    Pulse ring  = animated ring around failed/critical nodes
    """

    def __init__(self) -> None:
        # Convert SERVICE_POSITIONS (x%, y%) to plot coords (0–100)
        self._pos = {
            svc: (x, 100.0 - y)   # flip Y so top is high
            for svc, (x, y) in SERVICE_POSITIONS.items()
        }

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def build_figure(
        self,
        blast_map: BlastRadiusMap,
        height:    int = 480,
    ) -> go.Figure:
        fig = go.Figure()

        # 1. Draw edges
        self._add_edges(fig, blast_map)

        # 2. Draw pulse rings for failed/critical nodes
        self._add_pulse_rings(fig, blast_map.states)

        # 3. Draw nodes
        self._add_nodes(fig, blast_map)

        # 4. Draw propagation path arrows
        self._add_propagation_arrows(fig, blast_map)

        # 5. Layout
        fig.update_layout(
            paper_bgcolor = "rgba(0,0,0,0)",
            plot_bgcolor  = "rgba(0,0,0,0)",
            height        = height,
            margin        = dict(l=0, r=0, t=30, b=0),
            showlegend    = True,
            legend        = dict(
                orientation = "h",
                yanchor     = "bottom",
                y           = -0.08,
                xanchor     = "center",
                x           = 0.5,
                font        = dict(size=10, color="#64748b", family="JetBrains Mono"),
                bgcolor     = "rgba(0,0,0,0)",
            ),
            xaxis = dict(
                showgrid=False, zeroline=False, showticklabels=False,
                range=[-5, 105],
            ),
            yaxis = dict(
                showgrid=False, zeroline=False, showticklabels=False,
                range=[-5, 108],
            ),
            font        = dict(family="JetBrains Mono", color="#64748b", size=10),
            annotations = self._build_annotations(blast_map),
            hovermode   = "closest",
        )
        return fig

    def build_legend_table(self, blast_map: BlastRadiusMap) -> list[dict]:
        """
        Returns a list of dicts for rendering a status table alongside the map.
        """
        rows = []
        for svc, state in sorted(blast_map.states.items(),
                                  key=lambda x: x[1].health_score):
            rows.append({
                "service":  state.display_name,
                "health":   state.health.value,
                "score":    f"{state.health_score:.0f}%",
                "reason":   state.failure_reason or "—",
                "eta":      f"{state.recovery_eta_s}s" if state.recovery_eta_s else "—",
                "color":    HEALTH_COLORS[state.health],
            })
        return rows

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------
    def _add_edges(self, fig: go.Figure, blast_map: BlastRadiusMap) -> None:
        """Draw dependency edges as lines."""
        cascade_edges: set[tuple[str, str]] = set()
        path = blast_map.propagation_path
        for i in range(len(path) - 1):
            cascade_edges.add((path[i], path[i + 1]))

        for src, deps in DEPENDENCY_GRAPH.items():
            x0, y0 = self._pos.get(src, (50, 50))
            for dep, weight in deps:
                x1, y1 = self._pos.get(dep, (50, 50))
                is_cascade = (dep, src) in cascade_edges or (src, dep) in cascade_edges
                color = EDGE_COLOR_ACTIVE if is_cascade else EDGE_COLOR_NORMAL
                width = 2.0 if is_cascade else 0.8

                fig.add_trace(go.Scatter(
                    x=[x0, x1, None],
                    y=[y0, y1, None],
                    mode="lines",
                    line=dict(color=color, width=width),
                    hoverinfo="skip",
                    showlegend=False,
                ))

    def _add_pulse_rings(
        self,
        fig: go.Figure,
        states: dict[str, ServiceState],
    ) -> None:
        """Add outer rings around unhealthy nodes."""
        ring_x, ring_y, ring_sizes, ring_colors = [], [], [], []
        for svc, state in states.items():
            if state.health in (ServiceHealth.FAILED, ServiceHealth.CRITICAL):
                x, y = self._pos.get(svc, (50, 50))
                ring_x.append(x)
                ring_y.append(y)
                ring_sizes.append(48)
                ring_colors.append(HEALTH_COLORS[state.health])

        if ring_x:
            fig.add_trace(go.Scatter(
                x=ring_x, y=ring_y,
                mode="markers",
                marker=dict(
                    size=ring_sizes,
                    color="rgba(0,0,0,0)",
                    line=dict(color=ring_colors, width=2),
                    symbol="circle",
                ),
                hoverinfo="skip",
                showlegend=False,
            ))

    def _add_nodes(self, fig: go.Figure, blast_map: BlastRadiusMap) -> None:
        """Add service nodes grouped by health state for the legend."""
        grouped: dict[ServiceHealth, list[ServiceState]] = {}
        for state in blast_map.states.values():
            grouped.setdefault(state.health, []).append(state)

        legend_order = [
            ServiceHealth.FAILED,
            ServiceHealth.CRITICAL,
            ServiceHealth.DEGRADED,
            ServiceHealth.RECOVERING,
            ServiceHealth.HEALTHY,
        ]
        legend_labels = {
            ServiceHealth.HEALTHY:    "Healthy",
            ServiceHealth.DEGRADED:   "Degraded",
            ServiceHealth.CRITICAL:   "Critical",
            ServiceHealth.FAILED:     "Failed",
            ServiceHealth.RECOVERING: "Recovering",
        }

        for health in legend_order:
            states_in_group = grouped.get(health, [])
            if not states_in_group:
                continue
            xs, ys, sizes, texts, hovers = [], [], [], [], []
            for state in states_in_group:
                x, y = self._pos.get(state.name, (50, 50))
                xs.append(x)
                ys.append(y)
                # Node size scales with health score
                sizes.append(max(18, int(state.health_score * 0.32 + 14)))
                texts.append(state.display_name)
                root_tag = " ← ROOT CAUSE" if state.name == blast_map.root_cause else ""
                hovers.append(
                    f"<b>{state.display_name}</b>{root_tag}<br>"
                    f"Health: {state.health.value}<br>"
                    f"Score: {state.health_score:.0f}%<br>"
                    f"Reason: {state.failure_reason or 'OK'}<br>"
                    f"ETA: {state.recovery_eta_s}s" if state.recovery_eta_s else
                    f"<b>{state.display_name}</b>{root_tag}<br>"
                    f"Health: {state.health.value}<br>"
                    f"Score: {state.health_score:.0f}%"
                )

            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="markers+text",
                name=legend_labels[health],
                marker=dict(
                    size=sizes,
                    color=HEALTH_COLORS[health],
                    symbol=HEALTH_SYMBOLS[health],
                    line=dict(
                        color="rgba(8,12,20,0.8)",
                        width=2,
                    ),
                ),
                text=texts,
                textposition="bottom center",
                textfont=dict(
                    size=9,
                    color="#94a3b8",
                    family="JetBrains Mono",
                ),
                hovertext=hovers,
                hovertemplate="%{hovertext}<extra></extra>",
            ))

    def _add_propagation_arrows(
        self,
        fig: go.Figure,
        blast_map: BlastRadiusMap,
    ) -> None:
        """Add depth labels along cascade path edges."""
        path = blast_map.propagation_path
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            x0, y0 = self._pos.get(src, (50, 50))
            x1, y1 = self._pos.get(dst, (50, 50))
            mx = (x0 + x1) / 2
            my = (y0 + y1) / 2
            fig.add_annotation(
                x=mx, y=my,
                text=f"→ depth {i + 1}",
                showarrow=False,
                font=dict(size=8, color="#ff3d5a", family="JetBrains Mono"),
                bgcolor="rgba(8,12,20,0.7)",
                borderpad=2,
            )

    def _build_annotations(self, blast_map: BlastRadiusMap) -> list[dict]:
        anns = []

        # Root cause label
        if blast_map.root_cause and blast_map.root_cause != "none":
            x, y = self._pos.get(blast_map.root_cause, (50, 50))
            anns.append(dict(
                x=x, y=y + 7,
                text="⚠ ROOT",
                showarrow=False,
                font=dict(size=9, color="#ff3d5a", family="JetBrains Mono"),
                bgcolor="rgba(255,61,90,0.15)",
                bordercolor="#ff3d5a",
                borderwidth=1,
                borderpad=3,
            ))

        # Impact banner at top
        if blast_map.affected_count > 0:
            impact_color = "#ff3d5a" if blast_map.estimated_user_impact_pct >= 50 else "#ffab00"
            anns.append(dict(
                x=50, y=105,
                text=(
                    f"BLAST RADIUS: {blast_map.affected_count}/{blast_map.total_services} services affected  ·  "
                    f"User Impact: {blast_map.estimated_user_impact_pct:.0f}%"
                ),
                showarrow=False,
                font=dict(size=10, color=impact_color, family="JetBrains Mono"),
                bgcolor="rgba(8,12,20,0.8)",
                bordercolor=impact_color,
                borderwidth=1,
                borderpad=5,
                xanchor="center",
            ))
        return anns