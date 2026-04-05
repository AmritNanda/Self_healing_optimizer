"""
blast_radius.py — Live Blast Radius Map Renderer
Autonomous Chaos Engineering & Self-Healing Platform

Renders an interactive Plotly network graph showing real-time service
health, cascade propagation paths, and estimated user impact.
Powered by live cluster data from cascade.py.

Usage:
    from blast_radius import BlastRadiusRenderer
    renderer = BlastRadiusRenderer()
    fig = renderer.build_figure(blast_map)
    fig_json = renderer.build_json(blast_map)   # for API responses
"""

from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go

from cascade import (
    BlastRadiusMap,
    CascadeEngine,
    ServiceHealth,
    ServiceMetrics,
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

EDGE_COLOR_NORMAL  = "rgba(30,45,69,0.6)"
EDGE_COLOR_ACTIVE  = "rgba(255,61,90,0.7)"
EDGE_COLOR_RECOVER = "rgba(124,77,255,0.5)"


class BlastRadiusRenderer:
    """
    Builds a Plotly figure representing the live blast radius map.

    Node size   = service health score (bigger = healthier)
    Node color  = health state (green/amber/red/purple)
    Edge color  = red if cascade path, purple if recovering, gray otherwise
    Pulse ring  = animated ring around failed/critical nodes
    """

    def __init__(self) -> None:
        # Convert SERVICE_POSITIONS (x%, y%) to plot coords — flip Y so top is high
        self._pos = {
            svc: (x, 100.0 - y)
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

        self._add_edges(fig, blast_map)
        self._add_pulse_rings(fig, blast_map.states)
        self._add_nodes(fig, blast_map)
        self._add_propagation_arrows(fig, blast_map)

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

    def build_json(
        self,
        blast_map: BlastRadiusMap,
        height:    int = 480,
    ) -> str:
        """Build figure and return as Plotly JSON string for API responses."""
        return self.build_figure(blast_map, height).to_json()

    def build_legend_table(self, blast_map: BlastRadiusMap) -> list[dict]:
        """
        Returns a list of dicts for rendering a status table alongside the map.
        Includes real cluster metrics (CPU, Memory, Replicas, Restarts) when available.
        """
        rows = []
        for svc, state in sorted(
            blast_map.states.items(), key=lambda x: x[1].health_score
        ):
            row: dict = {
                "service":    state.display_name,
                "service_id": state.name,
                "health":     state.health.value,
                "score":      f"{state.health_score:.0f}%",
                "reason":     state.failure_reason or "—",
                "eta":        f"{state.recovery_eta_s}s" if state.recovery_eta_s else "—",
                "color":      HEALTH_COLORS[state.health],
            }
            # Attach live cluster metrics when available
            if state.metrics is not None:
                m = state.metrics
                row["cpu_percent"] = f"{m.cpu_percent:.1f}%"
                row["memory_mb"]   = f"{m.memory_mb:.0f} MB"
                row["restarts"]    = m.restart_count
                row["replicas"]    = f"{m.replicas_available}/{m.replicas_desired}"
                row["pod_ready"]   = m.pod_ready
                row["pod_phase"]   = m.pod_phase
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------
    def _add_edges(self, fig: go.Figure, blast_map: BlastRadiusMap) -> None:
        """Draw dependency edges as lines; highlight cascade path in red."""
        cascade_edges: set[tuple[str, str]] = set()
        path = blast_map.propagation_path
        for i in range(len(path) - 1):
            cascade_edges.add((path[i], path[i + 1]))

        for src, deps in DEPENDENCY_GRAPH.items():
            x0, y0 = self._pos.get(src, (50, 50))
            for dep, _weight in deps:
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
        fig:    go.Figure,
        states: dict[str, ServiceState],
    ) -> None:
        """Add outer rings around failed/critical nodes."""
        ring_x, ring_y, ring_colors = [], [], []
        for svc, state in states.items():
            if state.health in (ServiceHealth.FAILED, ServiceHealth.CRITICAL):
                x, y = self._pos.get(svc, (50, 50))
                ring_x.append(x)
                ring_y.append(y)
                ring_colors.append(HEALTH_COLORS[state.health])

        if ring_x:
            fig.add_trace(go.Scatter(
                x=ring_x, y=ring_y,
                mode="markers",
                marker=dict(
                    size=48,
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
                sizes.append(max(18, int(state.health_score * 0.32 + 14)))
                texts.append(state.display_name)

                # Build hover text — include real metrics when available
                root_tag     = " ← ROOT CAUSE" if state.name == blast_map.root_cause else ""
                hover_parts  = [
                    f"<b>{state.display_name}</b>{root_tag}",
                    f"Health: {state.health.value}",
                    f"Score: {state.health_score:.0f}%",
                ]
                if state.failure_reason:
                    hover_parts.append(f"Reason: {state.failure_reason}")

                # Live cluster metrics block
                if state.metrics is not None:
                    m = state.metrics
                    hover_parts.append(f"CPU: {m.cpu_percent:.1f}%")
                    hover_parts.append(f"Memory: {m.memory_mb:.0f} MB")
                    hover_parts.append(
                        f"Replicas: {m.replicas_available}/{m.replicas_desired}"
                    )
                    if m.restart_count > 0:
                        hover_parts.append(f"Restarts: {m.restart_count}")
                    hover_parts.append(
                        f"Pod: {m.pod_phase} ({'ready' if m.pod_ready else 'not ready'})"
                    )

                if state.recovery_eta_s:
                    hover_parts.append(f"ETA: {state.recovery_eta_s}s")

                hovers.append("<br>".join(hover_parts))

            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="markers+text",
                name=legend_labels[health],
                marker=dict(
                    size=sizes,
                    color=HEALTH_COLORS[health],
                    symbol=HEALTH_SYMBOLS[health],
                    line=dict(color="rgba(8,12,20,0.8)", width=2),
                ),
                text=texts,
                textposition="bottom center",
                textfont=dict(size=9, color="#94a3b8", family="JetBrains Mono"),
                hovertext=hovers,
                hovertemplate="%{hovertext}<extra></extra>",
            ))

    def _add_propagation_arrows(
        self,
        fig:      go.Figure,
        blast_map: BlastRadiusMap,
    ) -> None:
        """Add depth labels along cascade path edges."""
        path = blast_map.propagation_path
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            x0, y0   = self._pos.get(src, (50, 50))
            x1, y1   = self._pos.get(dst, (50, 50))
            fig.add_annotation(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                text=f"→ depth {i + 1}",
                showarrow=False,
                font=dict(size=8, color="#ff3d5a", family="JetBrains Mono"),
                bgcolor="rgba(8,12,20,0.7)",
                borderpad=2,
            )

    def _build_annotations(self, blast_map: BlastRadiusMap) -> list[dict]:
        anns: list[dict] = []

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
            impact_color = (
                "#ff3d5a" if blast_map.estimated_user_impact_pct >= 50 else "#ffab00"
            )
            anns.append(dict(
                x=50, y=105,
                text=(
                    f"BLAST RADIUS: {blast_map.affected_count}/{blast_map.total_services}"
                    f" services affected  ·  "
                    f"User Impact: {blast_map.estimated_user_impact_pct:.0f}%"
                    f"  ·  LIVE CLUSTER DATA"
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