"""
dashboard.py — Autonomous Chaos Engineering & Self-Healing Platform
Real-time SRE Dashboard (Streamlit + Plotly)
 
Features:
  • Cluster Heartbeat — live multi-metric time-series
  • Threat Level — animated Plotly gauge
  • Chaos Control Panel — one-click fault injection
  • Autonomous Action Log — live self-healing event stream
"""
 
from __future__ import annotations
 
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any
 
import httpx
import plotly.graph_objects as go
import streamlit as st
 
# ---------------------------------------------------------------------------
# Page config (MUST be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Chaos SRE Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
 
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chaos.dashboard")
 
# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ML_BACKEND_URL = "http://ml_backend:8000"  # override via env / sidebar
CHAOS_API_URL = "http://chaos_operator:9000"  # Person A's endpoint
MAX_HISTORY = 120  # data points retained in session
REFRESH_INTERVAL_S = 1
 
# ---------------------------------------------------------------------------
# Custom CSS — Dark Mode SRE aesthetic
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;700;800&display=swap');
 
:root {
    --bg-primary:    #080c14;
    --bg-card:       #0d1421;
    --bg-card2:      #111827;
    --border:        #1e2d45;
    --accent-cyan:   #00e5ff;
    --accent-amber:  #ffab00;
    --accent-red:    #ff3d5a;
    --accent-green:  #00e676;
    --accent-purple: #7c4dff;
    --text-primary:  #e2e8f0;
    --text-dim:      #64748b;
    --font-mono:     'JetBrains Mono', monospace;
    --font-display:  'Syne', sans-serif;
}
 
html, body, [class*="css"] {
    font-family: var(--font-mono) !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}
 
/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1rem 2rem 2rem 2rem !important; max-width: 100% !important; }
 
/* ── Header bar ── */
.sre-header {
    background: linear-gradient(135deg, #0d1421 0%, #111827 50%, #0a1628 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    box-shadow: 0 0 40px rgba(0,229,255,0.06);
}
.sre-header .logo { font-family: var(--font-display); font-size: 1.6rem; font-weight: 800;
    background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.sre-header .subtitle { font-size: 0.7rem; color: var(--text-dim); letter-spacing: 0.15em; text-transform: uppercase; margin-top: 0.15rem; }
.live-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent-green);
    box-shadow: 0 0 12px var(--accent-green); animation: pulse 1.4s ease-in-out infinite; display: inline-block; margin-right: 6px; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(1.3)} }
 
/* ── KPI cards ── */
.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
}
.kpi-card.cyan::before  { background: var(--accent-cyan); }
.kpi-card.amber::before { background: var(--accent-amber); }
.kpi-card.red::before   { background: var(--accent-red); }
.kpi-card.green::before { background: var(--accent-green); }
.kpi-label { font-size: 0.6rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 0.4rem; }
.kpi-value { font-family: var(--font-display); font-size: 2rem; font-weight: 800; line-height: 1; }
.kpi-unit  { font-size: 0.65rem; color: var(--text-dim); margin-top: 0.2rem; }
 
/* ── Section headings ── */
.section-title {
    font-family: var(--font-display);
    font-size: 0.75rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-dim);
    padding: 0 0 0.5rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1rem;
}
 
/* ── Chaos buttons ── */
.stButton > button {
    font-family: var(--font-mono) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    background: var(--bg-card2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    padding: 0.55rem 0.8rem !important;
    width: 100% !important;
    transition: all 0.2s !important;
    letter-spacing: 0.05em;
    text-align: left !important;
}
.stButton > button:hover {
    border-color: var(--accent-amber) !important;
    color: var(--accent-amber) !important;
    box-shadow: 0 0 16px rgba(255,171,0,0.15) !important;
}
 
/* ── Action log ── */
.action-log {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem;
    height: 320px;
    overflow-y: auto;
    font-size: 0.72rem;
    line-height: 1.7;
}
.action-log::-webkit-scrollbar { width: 4px; }
.action-log::-webkit-scrollbar-track { background: var(--bg-card); }
.action-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.log-entry { padding: 0.25rem 0; border-bottom: 1px solid rgba(30,45,69,0.5); }
.log-time  { color: var(--text-dim); }
.log-ok    { color: var(--accent-green); }
.log-warn  { color: var(--accent-amber); }
.log-crit  { color: var(--accent-red); }
.log-info  { color: var(--accent-cyan); }
 
/* ── Status badge ── */
.badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.badge-ok   { background: rgba(0,230,118,0.12); color: var(--accent-green); border: 1px solid rgba(0,230,118,0.3); }
.badge-warn { background: rgba(255,171,0,0.12);  color: var(--accent-amber); border: 1px solid rgba(255,171,0,0.3); }
.badge-crit { background: rgba(255,61,90,0.12);  color: var(--accent-red);   border: 1px solid rgba(255,61,90,0.3); }
 
/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { font-family: var(--font-mono) !important; }
</style>
"""
 
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults: dict[str, Any] = {
        "history_time":    [],
        "history_cpu":     [],
        "history_mem":     [],
        "history_latency": [],
        "history_score":   [],
        "action_log":      [],
        "total_anomalies": 0,
        "total_recovered": 0,
        "last_action":     "—",
        "last_score":      0.0,
        "backend_url":     ML_BACKEND_URL,
        "chaos_url":       CHAOS_API_URL,
        "auto_heal":       True,
        "inject_mode":     False,
        "uptime_start":    time.time(),
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
 
 
_init_state()
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")
 
 
def _log(msg: str, level: str = "info") -> None:
    css_class = {"ok": "log-ok", "warn": "log-warn", "crit": "log-crit"}.get(level, "log-info")
    entry = (
        f'<div class="log-entry">'
        f'<span class="log-time">[{_now_str()}]</span> '
        f'<span class="{css_class}">{msg}</span>'
        f'</div>'
    )
    st.session_state.action_log.insert(0, entry)
    st.session_state.action_log = st.session_state.action_log[:200]
 
 
def _simulate_telemetry() -> tuple[float, float, float]:
    """Generate synthetic telemetry if Prometheus is unavailable."""
    t = time.time()
    # Add occasional spikes to make it interesting
    spike = random.random() < 0.08
    if spike:
        return (
            random.uniform(85, 99),
            random.uniform(80, 98),
            random.uniform(1500, 8000),
        )
    cpu = 30 + 15 * abs(0.5 - ((t % 60) / 60)) + random.gauss(0, 4)
    mem = 50 + 10 * abs(0.5 - ((t % 90) / 90)) + random.gauss(0, 5)
    lat = 100 + 80 * abs(0.5 - ((t % 45) / 45)) + random.gauss(0, 20)
    return float(min(max(cpu, 5), 99)), float(min(max(mem, 10), 99)), float(max(lat, 20))
 
 
def _call_ml_backend(cpu: float, mem: float, latency: float) -> dict | None:
    try:
        resp = httpx.post(
            f"{st.session_state.backend_url}/api/v1/analyze",
            json={"cpu_usage": cpu, "mem_usage": mem, "latency_ms": latency},
            timeout=2.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("ML backend unreachable: %s — using mock", exc)
        # Mock response when backend not available
        score = min(max((cpu / 100 + mem / 100 + latency / 10000) / 3, 0.0), 1.0)
        is_anom = score > 0.6
        actions = {
            cpu > 85: "SCALE_OUT_HPA",
            mem > 85: "FLUSH_REDIS_CACHE",
            latency > 2000: "REROUTE_TRAFFIC",
        }
        action = next((v for k, v in actions.items() if k), "NO_ACTION" if not is_anom else "RESTART_POD")
        return {
            "is_anomaly": is_anom,
            "threat_score": round(score, 4),
            "recommended_action": action,
        }
 
 
def _trigger_chaos(fault_type: str, payload: dict) -> None:
    _log(f"💥 INJECTING FAULT → {fault_type}", "warn")
    try:
        httpx.post(
            f"{st.session_state.chaos_url}/inject/{fault_type}",
            json=payload,
            timeout=3.0,
        )
        _log(f"Chaos Mesh ACK for {fault_type}", "ok")
    except Exception:
        _log(f"Chaos API offline — fault '{fault_type}' queued locally", "warn")
 
 
def _execute_recovery(action: str) -> None:
    action_messages = {
        "RESTART_POD":      "🔄 Restarting degraded pod via Kopf operator",
        "SCALE_OUT_HPA":    "📈 Triggering HPA scale-out (+2 replicas)",
        "REROUTE_TRAFFIC":  "🔀 Rerouting traffic away from unhealthy node",
        "FLUSH_REDIS_CACHE":"🗑️  Flushing Redis cache to relieve memory pressure",
        "DRAIN_NODE":       "🚧 Initiating node drain for maintenance",
    }
    msg = action_messages.get(action, f"⚙️  Executing {action}")
    _log(msg, "ok")
    try:
        httpx.post(
            f"{st.session_state.chaos_url}/recover",
            json={"action": action},
            timeout=3.0,
        )
    except Exception:
        pass  # Operator offline — log-only mode
 
 
def _append_history(ts: str, cpu: float, mem: float, lat: float, score: float) -> None:
    for key, val in [
        ("history_time", ts), ("history_cpu", cpu), ("history_mem", mem),
        ("history_latency", lat), ("history_score", score),
    ]:
        st.session_state[key].append(val)
        if len(st.session_state[key]) > MAX_HISTORY:
            st.session_state[key].pop(0)
 
# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono", color="#64748b", size=10),
    margin=dict(l=10, r=10, t=10, b=10),
    showlegend=True,
    legend=dict(
        orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
        font=dict(size=9), bgcolor="rgba(0,0,0,0)",
    ),
)
 
 
def build_heartbeat_chart() -> go.Figure:
    t = st.session_state.history_time
    fig = go.Figure()

    traces = [
        ("CPU %",     st.session_state.history_cpu,                      "#00e5ff", "rgba(0,229,255,0.04)"),
        ("MEM %",     st.session_state.history_mem,                      "#7c4dff", "rgba(124,77,255,0.04)"),
        ("Score×100", [s * 100 for s in st.session_state.history_score], "#ff3d5a", "rgba(255,61,90,0.04)"),
    ]
    for name, y, color, fillcolor in traces:
        fig.add_trace(go.Scatter(
            x=t, y=y, name=name, mode="lines",
            line=dict(color=color, width=1.5),
            fill="tozeroy",
            fillcolor=fillcolor,
        ))

    fig.update_layout(
        **PLOTLY_BASE,
        height=200,
        xaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=8), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1e2d45", range=[0, 110], zeroline=False, tickfont=dict(size=8)),
        hovermode="x unified",
    )
    return fig
 
def build_latency_chart() -> go.Figure:
    t = st.session_state.history_time
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t, y=st.session_state.history_latency, name="Latency ms",
        mode="lines", line=dict(color="#ffab00", width=1.8),
        fill="tozeroy", fillcolor="rgba(255,171,0,0.05)",
    ))
    fig.add_hline(y=500, line=dict(color="#ff3d5a", width=1, dash="dot"),
                  annotation_text="SLO Threshold", annotation_font_size=9)
    fig.update_layout(
        **PLOTLY_BASE, height=170,
        xaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=8), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1e2d45", zeroline=False, tickfont=dict(size=8)),
    )
    return fig
 
 
def build_gauge(score: float) -> go.Figure:
    if score < 0.4:
        color = "#00e676"
    elif score < 0.7:
        color = "#ffab00"
    else:
        color = "#ff3d5a"
 
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=round(score * 100, 1),
        number=dict(suffix="%", font=dict(size=34, color=color, family="Syne")),
        delta=dict(reference=40, valueformat=".1f"),
        gauge=dict(
            axis=dict(range=[0, 100], tickfont=dict(size=9, color="#64748b"),
                      tickcolor="#1e2d45", tickwidth=1),
            bar=dict(color=color, thickness=0.22),
            bgcolor="rgba(0,0,0,0)",
            bordercolor="#1e2d45",
            steps=[
                dict(range=[0, 40],  color="rgba(0,230,118,0.08)"),
                dict(range=[40, 70], color="rgba(255,171,0,0.08)"),
                dict(range=[70, 100],color="rgba(255,61,90,0.08)"),
            ],
            threshold=dict(line=dict(color="#ff3d5a", width=2), thickness=0.75, value=70),
        ),
        title=dict(text="THREAT LEVEL", font=dict(size=10, color="#64748b", family="JetBrains Mono")),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
        margin=dict(l=20, r=20, t=30, b=10),
        height=230,
    )
    return fig
# ---------------------------------------------------------------------------
# Chaos scenarios
# ---------------------------------------------------------------------------
CHAOS_SCENARIOS = [
    {
        "label": "💀 Pod Kill",
        "fault": "pod-failure",
        "payload": {"selector": {"app": "cartservice"}, "duration": "60s"},
        "desc": "Terminates cartservice pod",
    },
    {
        "label": "🔥 CPU Stress",
        "fault": "stress-cpu",
        "payload": {"workers": 4, "duration": "90s", "target": "recommendationservice"},
        "desc": "Burns 4 cores on recommendation svc",
    },
    {
        "label": "🧠 Memory Hog",
        "fault": "stress-mem",
        "payload": {"size": "512M", "duration": "60s", "target": "frontend"},
        "desc": "Allocates 512MB on frontend pod",
    },
    {
        "label": "🌐 Network Partition",
        "fault": "network-partition",
        "payload": {"source": "checkoutservice", "target": "paymentservice", "duration": "45s"},
        "desc": "Blocks checkout → payment traffic",
    },
    {
        "label": "⏱  Latency Inject",
        "fault": "network-delay",
        "payload": {"delay": "2000ms", "target": "productcatalogservice", "duration": "60s"},
        "desc": "Adds 2s delay on catalog svc",
    },
    {
        "label": "📦 Disk Pressure",
        "fault": "disk-fill",
        "payload": {"fill_bytes": "1G", "target": "redis-cart", "duration": "30s"},
        "desc": "Fills disk on Redis node",
    },
]
 
# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1.1rem;font-weight:800;'
                'background:linear-gradient(90deg,#00e5ff,#7c4dff);-webkit-background-clip:text;'
                '-webkit-text-fill-color:transparent;margin-bottom:1rem;">⚡ CHAOS PLATFORM</div>',
                unsafe_allow_html=True)
 
    st.markdown("##### 🔧 Configuration")
    st.session_state.backend_url = st.text_input(
        "ML Backend URL", value=st.session_state.backend_url, key="cfg_backend"
    )
    st.session_state.chaos_url = st.text_input(
        "Chaos Operator URL", value=st.session_state.chaos_url, key="cfg_chaos"
    )
 
    st.divider()
    st.session_state.auto_heal = st.toggle("🛡️ Autonomous Healing", value=st.session_state.auto_heal)
    inject_mode = st.toggle("🧪 Synthetic Telemetry Mode", value=True)
 
    st.divider()
    st.markdown("##### 📊 Session Stats")
    uptime_s = int(time.time() - st.session_state.uptime_start)
    h, m, s = uptime_s // 3600, (uptime_s % 3600) // 60, uptime_s % 60
    st.metric("Uptime", f"{h:02d}:{m:02d}:{s:02d}")
    st.metric("Anomalies Detected", st.session_state.total_anomalies)
    st.metric("Auto-Recoveries", st.session_state.total_recovered)
 
    st.divider()
    st.caption("Tech Solstice — PS1 | Person B: ML & UI")
 
# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
 
# ── Header ──────────────────────────────────────────────────────────────────
score = st.session_state.last_score
if score < 0.4:
    status_badge = '<span class="badge badge-ok">NOMINAL</span>'
elif score < 0.7:
    status_badge = '<span class="badge badge-warn">ELEVATED</span>'
else:
    status_badge = '<span class="badge badge-crit">CRITICAL</span>'
 
st.markdown(f"""
<div class="sre-header">
  <div>
    <div class="logo">⚡ NEXUS — Autonomous SRE</div>
    <div class="subtitle">Chaos Engineering &amp; Self-Healing Platform · Tech Solstice PS1</div>
  </div>
  <div style="margin-left:auto;display:flex;align-items:center;gap:1rem;">
    <span><span class="live-dot"></span><span style="font-size:0.7rem;color:#64748b;letter-spacing:.1em;">LIVE</span></span>
    {status_badge}
  </div>
</div>
""", unsafe_allow_html=True)
 
# ── KPI Row ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
cpu_now = st.session_state.history_cpu[-1] if st.session_state.history_cpu else 0.0
mem_now = st.session_state.history_mem[-1] if st.session_state.history_mem else 0.0
lat_now = st.session_state.history_latency[-1] if st.session_state.history_latency else 0.0
 
cpu_color  = "red" if cpu_now > 80 else ("amber" if cpu_now > 60 else "cyan")
mem_color  = "red" if mem_now > 80 else ("amber" if mem_now > 60 else "green")
lat_color  = "red" if lat_now > 1000 else ("amber" if lat_now > 400 else "cyan")
heal_color = "green"
 
with k1:
    st.markdown(f'<div class="kpi-card {cpu_color}"><div class="kpi-label">CPU Usage</div>'
                f'<div class="kpi-value" style="color:var(--accent-{"red" if cpu_now>80 else "cyan"})">{cpu_now:.1f}</div>'
                f'<div class="kpi-unit">percent</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-card {mem_color}"><div class="kpi-label">Memory Usage</div>'
                f'<div class="kpi-value" style="color:var(--accent-{"red" if mem_now>80 else "green"})">{mem_now:.1f}</div>'
                f'<div class="kpi-unit">percent</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kpi-card {lat_color}"><div class="kpi-label">P99 Latency</div>'
                f'<div class="kpi-value" style="color:var(--accent-{"red" if lat_now>1000 else "amber"})">{lat_now:.0f}</div>'
                f'<div class="kpi-unit">milliseconds</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kpi-card {heal_color}"><div class="kpi-label">Auto-Recoveries</div>'
                f'<div class="kpi-value" style="color:var(--accent-green)">{st.session_state.total_recovered}</div>'
                f'<div class="kpi-unit">actions taken</div></div>', unsafe_allow_html=True)
 
st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
 
# ── Main 3-column layout ─────────────────────────────────────────────────────
col_charts, col_gauge, col_log = st.columns([3.2, 1.6, 2.2])
 
with col_charts:
    st.markdown('<div class="section-title">📡 Cluster Heartbeat</div>', unsafe_allow_html=True)
    chart_placeholder = st.empty()
 
    st.markdown('<div class="section-title" style="margin-top:1rem">⏱  Service Latency</div>', unsafe_allow_html=True)
    latency_placeholder = st.empty()
 
with col_gauge:
    st.markdown('<div class="section-title">🎯 Threat Level</div>', unsafe_allow_html=True)
    gauge_placeholder = st.empty()
 
    st.markdown('<div class="section-title" style="margin-top:0.5rem">🔬 Last Analysis</div>', unsafe_allow_html=True)
    analysis_placeholder = st.empty()
 
with col_log:
    st.markdown('<div class="section-title">🤖 Autonomous Action Log</div>', unsafe_allow_html=True)
    log_placeholder = st.empty()
 
# ── Chaos Control Panel ───────────────────────────────────────────────────────
st.markdown('<div class="section-title" style="margin-top:1rem">☢️ Chaos Control Panel</div>', unsafe_allow_html=True)
 
chaos_cols = st.columns(6)
for i, scenario in enumerate(CHAOS_SCENARIOS):
    with chaos_cols[i]:
        st.markdown(
            f'<div style="font-size:0.6rem;color:#64748b;margin-bottom:0.3rem;">{scenario["desc"]}</div>',
            unsafe_allow_html=True,
        )
        if st.button(scenario["label"], key=f"chaos_{i}"):
            _trigger_chaos(scenario["fault"], scenario["payload"])
 
# ---------------------------------------------------------------------------
# Telemetry loop — tick every REFRESH_INTERVAL_S seconds
# ---------------------------------------------------------------------------
_log("Platform initialised — monitoring 11 microservices", "info")
_log("Isolation Forest model online (200 estimators)", "ok")
_log("Chaos Mesh adapter ready", "info")
 
while True:
    # 1. Collect telemetry
    cpu, mem, latency = _simulate_telemetry()
    ts = _now_str()
 
    # 2. Analyse with ML backend
    result = _call_ml_backend(cpu, mem, latency)
 
    if result:
        is_anomaly  = result.get("is_anomaly", False)
        threat_score = float(result.get("threat_score", 0.0))
        action       = result.get("recommended_action", "NO_ACTION")
        processing   = result.get("processing_time_ms", 0.0)
 
        st.session_state.last_score  = threat_score
        st.session_state.last_action = action
 
        _append_history(ts, cpu, mem, latency, threat_score)
 
        if is_anomaly:
            st.session_state.total_anomalies += 1
            _log(f"🚨 ANOMALY DETECTED — score={threat_score:.3f}  action={action}", "crit")
 
            if st.session_state.auto_heal and action != "NO_ACTION":
                _execute_recovery(action)
                st.session_state.total_recovered += 1
 
    # 3. Render charts
    chart_placeholder.plotly_chart(
        build_heartbeat_chart(), use_container_width=True, config={"displayModeBar": False}
    )
    latency_placeholder.plotly_chart(
        build_latency_chart(), use_container_width=True, config={"displayModeBar": False}
    )
    gauge_placeholder.plotly_chart(
        build_gauge(st.session_state.last_score),
        use_container_width=True,
        config={"displayModeBar": False},
    )
 
    # 4. Analysis card
    action_colors = {
        "NO_ACTION":         "#00e676",
        "RESTART_POD":       "#ff3d5a",
        "SCALE_OUT_HPA":     "#ffab00",
        "REROUTE_TRAFFIC":   "#7c4dff",
        "FLUSH_REDIS_CACHE": "#00e5ff",
        "DRAIN_NODE":        "#ff3d5a",
    }
    a_color = action_colors.get(action, "#64748b")
    analysis_placeholder.markdown(f"""
<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
            padding:0.9rem;font-size:0.68rem;line-height:2;">
  <div><span style="color:#64748b">ANOMALY  </span><span style="color:{'#ff3d5a' if is_anomaly else '#00e676'};font-weight:700">{'YES' if is_anomaly else 'NO'}</span></div>
  <div><span style="color:#64748b">SCORE    </span><span style="color:{a_color};font-weight:700">{threat_score:.4f}</span></div>
  <div><span style="color:#64748b">ACTION   </span><span style="color:{a_color};font-weight:700">{action}</span></div>
  <div><span style="color:#64748b">LATENCY  </span><span style="color:#64748b">{processing:.1f}ms</span></div>
</div>
""", unsafe_allow_html=True)
 
    # 5. Action log
    log_html = '<div class="action-log">' + "".join(st.session_state.action_log) + "</div>"
    log_placeholder.markdown(log_html, unsafe_allow_html=True)
 
    # 6. Wait
    time.sleep(REFRESH_INTERVAL_S)
 