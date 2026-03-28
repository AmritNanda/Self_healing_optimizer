"""
dashboard.py — Autonomous Chaos Engineering & Self-Healing Platform
Real-time SRE Dashboard (Streamlit + Plotly) — v3

Features:
  - Core: heartbeat charts, threat gauge, chaos panel, action log
  - Cascading Failure injection
  - Live Blast Radius Map
"""

from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import plotly.graph_objects as go
import streamlit as st

from cascade      import CascadeEngine, ServiceHealth, DEPENDENCY_GRAPH, SERVICE_DISPLAY
from blast_radius import BlastRadiusRenderer

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NEXUS — Chaos SRE Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chaos.dashboard")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ML_BACKEND_URL = "http://localhost:8000"
CHAOS_API_URL  = "http://localhost:9000"
MAX_HISTORY    = 120
REFRESH_S      = 1

# ---------------------------------------------------------------------------
# CSS
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
    --accent-orange: #ff6b35;
    --text-primary:  #e2e8f0;
    --text-dim:      #64748b;
    --font-mono:     'JetBrains Mono', monospace;
    --font-display:  'Syne', sans-serif;
}
html, body, [class*="css"] { font-family: var(--font-mono) !important; background-color: var(--bg-primary) !important; color: var(--text-primary) !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1rem 2rem 2rem 2rem !important; max-width: 100% !important; }

.sre-header { background: linear-gradient(135deg, #0d1421 0%, #111827 50%, #0a1628 100%); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem 2rem; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 1.5rem; box-shadow: 0 0 40px rgba(0,229,255,0.06); }
.sre-header .logo { font-family: var(--font-display); font-size: 1.6rem; font-weight: 800; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.sre-header .subtitle { font-size: 0.7rem; color: var(--text-dim); letter-spacing: 0.15em; text-transform: uppercase; margin-top: 0.15rem; }
.live-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent-green); box-shadow: 0 0 12px var(--accent-green); animation: pulse 1.4s ease-in-out infinite; display: inline-block; margin-right: 6px; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(1.3)} }

.kpi-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.2rem; text-align: center; position: relative; overflow: hidden; }
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.kpi-card.cyan::before   { background: var(--accent-cyan); }
.kpi-card.amber::before  { background: var(--accent-amber); }
.kpi-card.red::before    { background: var(--accent-red); }
.kpi-card.green::before  { background: var(--accent-green); }
.kpi-card.purple::before { background: var(--accent-purple); }
.kpi-card.orange::before { background: var(--accent-orange); }
.kpi-label { font-size: 0.6rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 0.4rem; }
.kpi-value { font-family: var(--font-display); font-size: 2rem; font-weight: 800; line-height: 1; }
.kpi-unit  { font-size: 0.65rem; color: var(--text-dim); margin-top: 0.2rem; }

.section-title { font-family: var(--font-display); font-size: 0.75rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--text-dim); padding: 0 0 0.5rem 0; border-bottom: 1px solid var(--border); margin-bottom: 1rem; }

.cascade-banner { background: rgba(255,107,53,0.08); border: 1px solid var(--accent-orange); border-radius: 10px; padding: 0.8rem 1.2rem; margin-bottom: 0.75rem; font-size: 0.75rem; line-height: 1.8; animation: borderPulse 1.2s ease-in-out infinite; }
@keyframes borderPulse { 0%,100%{opacity:1} 50%{opacity:0.5} }

.svc-table { width: 100%; border-collapse: collapse; font-size: 0.68rem; }
.svc-table th { color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.1em; font-size: 0.6rem; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); text-align: left; }
.svc-table td { padding: 0.35rem 0.5rem; border-bottom: 1px solid rgba(30,45,69,0.4); }
.svc-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }

.stButton > button { font-family: var(--font-mono) !important; font-size: 0.72rem !important; font-weight: 600 !important; background: var(--bg-card2) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; color: var(--text-primary) !important; padding: 0.55rem 0.8rem !important; width: 100% !important; transition: all 0.2s !important; }
.stButton > button:hover { border-color: var(--accent-amber) !important; color: var(--accent-amber) !important; }

.action-log { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; height: 280px; overflow-y: auto; font-size: 0.72rem; line-height: 1.7; }
.action-log::-webkit-scrollbar { width: 4px; }
.action-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.log-entry { padding: 0.25rem 0; border-bottom: 1px solid rgba(30,45,69,0.5); }
.log-time    { color: var(--text-dim); }
.log-ok      { color: var(--accent-green); }
.log-warn    { color: var(--accent-amber); }
.log-crit    { color: var(--accent-red); }
.log-info    { color: var(--accent-cyan); }
.log-cascade { color: var(--accent-orange); }

.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 4px; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
.badge-ok   { background: rgba(0,230,118,0.12);  color: var(--accent-green);  border: 1px solid rgba(0,230,118,0.3); }
.badge-warn { background: rgba(255,171,0,0.12);  color: var(--accent-amber);  border: 1px solid rgba(255,171,0,0.3); }
.badge-crit { background: rgba(255,61,90,0.12);  color: var(--accent-red);    border: 1px solid rgba(255,61,90,0.3); }

[data-testid="stSidebar"] { background: var(--bg-card) !important; border-right: 1px solid var(--border) !important; }
[data-testid="stSidebar"] * { font-family: var(--font-mono) !important; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults: dict[str, Any] = {
        "history_time":    [], "history_cpu":      [],
        "history_mem":     [], "history_latency":  [],
        "history_score":   [], "action_log":       [],
        "total_anomalies": 0,  "total_recoveries": 0,
        "cascade_count":   0,  "chaos_experiments":[],
        "last_score":      0.0,"backend_url":      ML_BACKEND_URL,
        "chaos_url":       CHAOS_API_URL,
        "auto_heal":       True,
        "show_blast_map":  True,
        "uptime_start":    time.time(),
        "peak_cpu":        0.0, "peak_mem":        0.0,
        "peak_latency":    0.0, "recovery_times":  [],
        "last_anomaly_ts": None,
        "cascade_active":  False,
        "cascade_root":    "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

@st.cache_resource
def get_cascade_engine()  -> CascadeEngine:      return CascadeEngine()
@st.cache_resource
def get_blast_renderer()  -> BlastRadiusRenderer: return BlastRadiusRenderer()

cascade_engine = get_cascade_engine()
blast_renderer = get_blast_renderer()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def _log(msg: str, level: str = "info") -> None:
    css_map = {"ok":"log-ok","warn":"log-warn","crit":"log-crit","cascade":"log-cascade"}
    css = css_map.get(level, "log-info")
    ts  = _now_str()
    st.session_state.action_log.insert(0,
        f'<div class="log-entry"><span class="log-time">[{ts}]</span> '
        f'<span class="{css}">{msg}</span></div>'
    )
    st.session_state.action_log = st.session_state.action_log[:200]

def _simulate_telemetry() -> tuple[float, float, float]:
    t = time.time()
    cascade_boost = 35.0 if st.session_state.cascade_active else 0.0
    if random.random() < 0.08:
        return random.uniform(85,99), random.uniform(80,98), random.uniform(1500,8000)
    cpu = min(30 + 15*abs(0.5-((t%60)/60))  + random.gauss(0,4)  + cascade_boost,      99)
    mem = min(50 + 10*abs(0.5-((t%90)/90))  + random.gauss(0,5)  + cascade_boost*0.7,  99)
    lat = max(100+ 80*abs(0.5-((t%45)/45))  + random.gauss(0,20) + cascade_boost*50,   20)
    return float(cpu), float(mem), float(lat)

def _call_ml_backend(cpu: float, mem: float, latency: float) -> dict:
    try:
        r = httpx.post(
            f"{st.session_state.backend_url}/api/v1/analyze",
            json={"cpu_usage": cpu, "mem_usage": mem, "latency_ms": latency},
            timeout=2.0,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        score   = min(max((cpu/100 + mem/100 + latency/10000)/3, 0.0), 1.0)
        is_anom = score > 0.6
        action  = ("SCALE_OUT_HPA" if cpu>85 else "FLUSH_REDIS_CACHE" if mem>85
                   else "REROUTE_TRAFFIC" if latency>2000
                   else ("RESTART_POD" if is_anom else "NO_ACTION"))
        return {"is_anomaly": is_anom, "threat_score": round(score,4),
                "recommended_action": action, "processing_time_ms": 0.0}

def _trigger_chaos(fault_type: str, payload: dict) -> None:
    _log(f"💥 INJECTING FAULT → {fault_type}", "warn")
    if fault_type not in st.session_state.chaos_experiments:
        st.session_state.chaos_experiments.append(fault_type)
    try:
        httpx.post(f"{st.session_state.chaos_url}/inject/{fault_type}", json=payload, timeout=3.0)
        _log(f"Chaos Mesh ACK for {fault_type}", "ok")
    except Exception:
        _log(f"Chaos API offline — '{fault_type}' queued locally", "warn")

def _trigger_cascade(root_service: str) -> None:
    _log(f"🌊 CASCADING FAILURE → root={root_service}", "cascade")
    st.session_state.cascade_active = True
    st.session_state.cascade_root   = root_service
    st.session_state.cascade_count += 1
    events = cascade_engine.inject(root_service)
    for evt in events:
        if evt.current != ServiceHealth.HEALTHY:
            _log(
                f"  ↳ depth={evt.depth}  "
                f"{SERVICE_DISPLAY.get(evt.service, evt.service)} "
                f"→ {evt.current.value}  ({evt.health_score:.0f}%)",
                "cascade",
            )
    try:
        httpx.post(f"{st.session_state.chaos_url}/inject/cascading-failure",
                   json={"root": root_service}, timeout=3.0)
    except Exception:
        pass

def _execute_recovery(action: str) -> None:
    msgs = {
        "RESTART_POD":       "🔄 Restarting degraded pod",
        "SCALE_OUT_HPA":     "📈 HPA scale-out (+2 replicas)",
        "REROUTE_TRAFFIC":   "🔀 Rerouting traffic",
        "FLUSH_REDIS_CACHE": "🗑️  Flushing Redis cache",
        "DRAIN_NODE":        "🚧 Draining node",
    }
    _log(f"🛡️ REACTIVE — {msgs.get(action, action)}", "ok")
    if st.session_state.last_anomaly_ts:
        st.session_state.recovery_times.append(time.time() - st.session_state.last_anomaly_ts)
    try:
        httpx.post(f"{st.session_state.chaos_url}/recover",
                   json={"action": action}, timeout=3.0)
    except Exception:
        pass

def _append_history(ts, cpu, mem, lat, score) -> None:
    for key, val in [("history_time",ts),("history_cpu",cpu),
                     ("history_mem",mem),("history_latency",lat),
                     ("history_score",score)]:
        st.session_state[key].append(val)
        if len(st.session_state[key]) > MAX_HISTORY:
            st.session_state[key].pop(0)
    st.session_state.peak_cpu     = max(st.session_state.peak_cpu,     cpu)
    st.session_state.peak_mem     = max(st.session_state.peak_mem,     mem)
    st.session_state.peak_latency = max(st.session_state.peak_latency, lat)

# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------
PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono", color="#64748b", size=10),
    margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.01,
                xanchor="right", x=1, font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
)

def build_heartbeat_chart() -> go.Figure:
    t   = st.session_state.history_time
    fig = go.Figure()
    for name, y, color, fill in [
        ("CPU %",     st.session_state.history_cpu,                      "#00e5ff", "rgba(0,229,255,0.04)"),
        ("MEM %",     st.session_state.history_mem,                      "#7c4dff", "rgba(124,77,255,0.04)"),
        ("Score×100", [s*100 for s in st.session_state.history_score],   "#ff3d5a", "rgba(255,61,90,0.04)"),
    ]:
        fig.add_trace(go.Scatter(x=t, y=y, name=name, mode="lines",
                                  line=dict(color=color, width=1.5),
                                  fill="tozeroy", fillcolor=fill))
    fig.update_layout(**PLOTLY_BASE, height=180,
        xaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=8), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1e2d45", range=[0,110], zeroline=False, tickfont=dict(size=8)),
        hovermode="x unified")
    return fig

def build_latency_chart() -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=st.session_state.history_time, y=st.session_state.history_latency,
        name="Latency ms", mode="lines", line=dict(color="#ffab00", width=1.8),
        fill="tozeroy", fillcolor="rgba(255,171,0,0.05)"))
    fig.add_hline(y=500, line=dict(color="#ff3d5a", width=1, dash="dot"),
                  annotation_text="SLO Threshold", annotation_font_size=9)
    fig.update_layout(**PLOTLY_BASE, height=160,
        xaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=8), zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1e2d45", zeroline=False, tickfont=dict(size=8)))
    return fig

def build_gauge(score: float) -> go.Figure:
    color = "#00e676" if score < 0.4 else ("#ffab00" if score < 0.7 else "#ff3d5a")
    fig   = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=round(score*100, 1),
        number=dict(suffix="%", font=dict(size=30, color=color, family="Syne")),
        delta=dict(reference=40, valueformat=".1f"),
        gauge=dict(
            axis=dict(range=[0,100], tickfont=dict(size=9, color="#64748b")),
            bar=dict(color=color, thickness=0.22),
            bgcolor="rgba(0,0,0,0)", bordercolor="#1e2d45",
            steps=[dict(range=[0,40],   color="rgba(0,230,118,0.08)"),
                   dict(range=[40,70],  color="rgba(255,171,0,0.08)"),
                   dict(range=[70,100], color="rgba(255,61,90,0.08)")],
            threshold=dict(line=dict(color="#ff3d5a", width=2), thickness=0.75, value=70),
        ),
        title=dict(text="THREAT LEVEL", font=dict(size=10, color="#64748b", family="JetBrains Mono")),
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"),
                      margin=dict(l=20, r=20, t=30, b=10), height=210)
    return fig

# ---------------------------------------------------------------------------
# Chaos scenarios
# ---------------------------------------------------------------------------
CHAOS_SCENARIOS = [
    {"label": "💀 Pod Kill",         "fault": "pod-failure",       "payload": {"selector": {"app": "cartservice"}, "duration": "60s"}},
    {"label": "🔥 CPU Stress",       "fault": "stress-cpu",        "payload": {"workers": 4, "duration": "90s", "target": "recommendationservice"}},
    {"label": "🧠 Memory Hog",       "fault": "stress-mem",        "payload": {"size": "512M", "duration": "60s", "target": "frontend"}},
    {"label": "🌐 Net Partition",    "fault": "network-partition",  "payload": {"source": "checkoutservice", "target": "paymentservice", "duration": "45s"}},
    {"label": "⏱  Latency Inject",  "fault": "network-delay",     "payload": {"delay": "2000ms", "target": "productcatalogservice", "duration": "60s"}},
    {"label": "📦 Disk Pressure",    "fault": "disk-fill",         "payload": {"fill_bytes": "1G", "target": "redis-cart", "duration": "30s"}},
]

CASCADE_ROOTS = list(DEPENDENCY_GRAPH.keys())

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div style="font-family:\'Syne\',sans-serif;font-size:1.1rem;font-weight:800;'
                'background:linear-gradient(90deg,#00e5ff,#7c4dff);-webkit-background-clip:text;'
                '-webkit-text-fill-color:transparent;margin-bottom:1rem;">⚡ NEXUS v3</div>',
                unsafe_allow_html=True)

    st.markdown("##### 🔧 Configuration")
    st.session_state.backend_url = st.text_input("ML Backend URL",     value=st.session_state.backend_url)
    st.session_state.chaos_url   = st.text_input("Chaos Operator URL", value=st.session_state.chaos_url)

    st.divider()
    st.session_state.auto_heal      = st.toggle("🛡️ Autonomous Healing",   value=st.session_state.auto_heal)
    st.session_state.show_blast_map = st.toggle("🗺️ Live Blast Radius Map", value=st.session_state.show_blast_map)

    st.divider()
    st.markdown("##### 🌊 Cascade Failure")
    cascade_root = st.selectbox(
        "Root service",
        options=CASCADE_ROOTS,
        format_func=lambda s: SERVICE_DISPLAY.get(s, s),
        index=CASCADE_ROOTS.index("redis-cart"),
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💥 Inject", use_container_width=True):
            _trigger_cascade(cascade_root)
    with c2:
        if st.button("✅ Reset", use_container_width=True):
            cascade_engine.reset()
            st.session_state.cascade_active = False
            st.session_state.cascade_root   = ""
            _log("🔄 Cascade engine reset — all services HEALTHY", "ok")

    st.divider()
    st.markdown("##### 📊 Session Stats")
    uptime_s = int(time.time() - st.session_state.uptime_start)
    h, m, s  = uptime_s//3600, (uptime_s%3600)//60, uptime_s%60
    st.metric("Uptime",          f"{h:02d}:{m:02d}:{s:02d}")
    st.metric("Anomalies",       st.session_state.total_anomalies)
    st.metric("Auto-Recoveries", st.session_state.total_recoveries)
    st.metric("Cascade Events",  st.session_state.cascade_count)
    st.caption("Tech Solstice — PS1 | Person B: ML & UI")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
score = st.session_state.last_score
status_badge = (
    '<span class="badge badge-ok">NOMINAL</span>'    if score < 0.4 else
    '<span class="badge badge-warn">ELEVATED</span>' if score < 0.7 else
    '<span class="badge badge-crit">CRITICAL</span>'
)
cascade_tag = (
    '<span class="badge" style="background:rgba(255,107,53,0.15);color:#ff6b35;'
    'border:1px solid rgba(255,107,53,0.4);">🌊 CASCADE ACTIVE</span>'
    if st.session_state.cascade_active else ""
)
st.markdown(f"""
<div class="sre-header">
  <div>
    <div class="logo">⚡ NEXUS — Autonomous SRE v3</div>
    <div class="subtitle">Cascading Failure · Blast Radius · Self-Healing · Tech Solstice PS1</div>
  </div>
  <div style="margin-left:auto;display:flex;align-items:center;gap:0.75rem;">
    <span><span class="live-dot"></span><span style="font-size:0.7rem;color:#64748b;letter-spacing:.1em;">LIVE</span></span>
    {cascade_tag}{status_badge}
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
cpu_now = st.session_state.history_cpu[-1]     if st.session_state.history_cpu     else 0.0
mem_now = st.session_state.history_mem[-1]     if st.session_state.history_mem     else 0.0
lat_now = st.session_state.history_latency[-1] if st.session_state.history_latency else 0.0
blast   = cascade_engine.get_blast_radius_map()
aff_pct = round(blast.affected_count / blast.total_services * 100) if blast.total_services else 0

for col, label, val, unit, accent in [
    (k1, "CPU Usage",       f"{cpu_now:.1f}", "percent",  "red"    if cpu_now>80  else "cyan"),
    (k2, "Memory Usage",    f"{mem_now:.1f}", "percent",  "red"    if mem_now>80  else "green"),
    (k3, "P99 Latency",     f"{lat_now:.0f}", "ms",       "red"    if lat_now>1000 else "amber"),
    (k4, "Auto-Recoveries", str(st.session_state.total_recoveries), "actions", "green"),
    (k5, "Blast Radius",    f"{aff_pct}%",   "services", "orange" if aff_pct>0   else "cyan"),
]:
    with col:
        st.markdown(
            f'<div class="kpi-card {accent}"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value" style="color:var(--accent-{accent})">{val}</div>'
            f'<div class="kpi-unit">{unit}</div></div>',
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
cascade_banner_ph = st.empty()

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
col_charts, col_gauge, col_log = st.columns([3.2, 1.6, 2.2])

with col_charts:
    st.markdown('<div class="section-title">📡 Cluster Heartbeat</div>', unsafe_allow_html=True)
    chart_placeholder   = st.empty()
    st.markdown('<div class="section-title" style="margin-top:0.75rem">⏱  Service Latency</div>', unsafe_allow_html=True)
    latency_placeholder = st.empty()

with col_gauge:
    st.markdown('<div class="section-title">🎯 Threat Level</div>', unsafe_allow_html=True)
    gauge_placeholder    = st.empty()
    st.markdown('<div class="section-title" style="margin-top:0.5rem">🔬 Last Analysis</div>', unsafe_allow_html=True)
    analysis_placeholder = st.empty()

with col_log:
    st.markdown('<div class="section-title">🤖 Autonomous Action Log</div>', unsafe_allow_html=True)
    log_placeholder = st.empty()

# Blast radius map
if st.session_state.show_blast_map:
    st.markdown('<div class="section-title" style="margin-top:1rem">🗺️ Live Blast Radius Map</div>', unsafe_allow_html=True)
    blast_cols = st.columns([2.8, 1.2])
    with blast_cols[0]:
        blast_map_placeholder = st.empty()
    with blast_cols[1]:
        st.markdown('<div class="section-title">📋 Service Health</div>', unsafe_allow_html=True)
        blast_table_placeholder = st.empty()

# Chaos control panel
st.markdown('<div class="section-title" style="margin-top:0.75rem">☢️ Chaos Control Panel</div>', unsafe_allow_html=True)
chaos_cols = st.columns(6)
for i, sc in enumerate(CHAOS_SCENARIOS):
    with chaos_cols[i]:
        if st.button(sc["label"], key=f"chaos_{i}"):
            _trigger_chaos(sc["fault"], sc["payload"])

# ---------------------------------------------------------------------------
# Bootstrap log
# ---------------------------------------------------------------------------
_log("Platform v3 initialised — monitoring 11 microservices", "info")
_log("Isolation Forest model online (200 estimators)", "ok")
_log("Cascading Failure Engine online — 11 services mapped", "ok")
_log("Live Blast Radius Map renderer ready", "ok")

# ---------------------------------------------------------------------------
# Telemetry loop
# ---------------------------------------------------------------------------
ACTION_COLORS = {
    "NO_ACTION":"#00e676","RESTART_POD":"#ff3d5a",
    "SCALE_OUT_HPA":"#ffab00","REROUTE_TRAFFIC":"#7c4dff",
    "FLUSH_REDIS_CACHE":"#00e5ff","DRAIN_NODE":"#ff3d5a",
}

is_anomaly = False; threat_score = 0.0; action = "NO_ACTION"; processing = 0.0

while True:
    cpu, mem, latency = _simulate_telemetry()
    ts = _now_str()

    # 1. ML analysis
    result       = _call_ml_backend(cpu, mem, latency)
    is_anomaly   = result.get("is_anomaly", False)
    threat_score = float(result.get("threat_score", 0.0))
    action       = result.get("recommended_action", "NO_ACTION")
    processing   = result.get("processing_time_ms", 0.0)
    st.session_state.last_score = threat_score
    _append_history(ts, cpu, mem, latency, threat_score)

    if is_anomaly:
        st.session_state.total_anomalies   += 1
        st.session_state.last_anomaly_ts    = time.time()
        _log(f"🚨 ANOMALY — score={threat_score:.3f} action={action}", "crit")
        if st.session_state.auto_heal and action != "NO_ACTION":
            _execute_recovery(action)
            st.session_state.total_recoveries += 1

    # 2. Cascade recovery tick
    recovered = cascade_engine.tick_recovery()
    for evt in recovered:
        _log(f"✅ CASCADE-HEALED — {SERVICE_DISPLAY.get(evt.service, evt.service)} → HEALTHY", "ok")
        st.session_state.total_recoveries += 1
    if st.session_state.cascade_active:
        all_healthy = all(s.health == ServiceHealth.HEALTHY
                          for s in cascade_engine.get_states().values())
        if all_healthy:
            st.session_state.cascade_active = False
            _log("🌊 CASCADE RESOLVED — all services HEALTHY", "ok")

    # 3. Cascade banner
    if st.session_state.cascade_active:
        blast = cascade_engine.get_blast_radius_map()
        cascade_banner_ph.markdown(f"""
<div class="cascade-banner">
  🌊 <strong style="color:#ff6b35">CASCADING FAILURE ACTIVE</strong> —
  Root: <strong>{SERVICE_DISPLAY.get(blast.root_cause, blast.root_cause)}</strong> ·
  Affected: <strong>{blast.affected_count}/{blast.total_services} services</strong> ·
  User Impact: <strong style="color:#ff3d5a">{blast.estimated_user_impact_pct:.0f}%</strong> ·
  Path: <strong>{" → ".join(SERVICE_DISPLAY.get(s,s) for s in blast.propagation_path[:4])}</strong>
</div>""", unsafe_allow_html=True)
    else:
        cascade_banner_ph.empty()

    # 4. Charts
    chart_placeholder.plotly_chart(build_heartbeat_chart(),   use_container_width=True, config={"displayModeBar": False})
    latency_placeholder.plotly_chart(build_latency_chart(),   use_container_width=True, config={"displayModeBar": False})
    gauge_placeholder.plotly_chart(build_gauge(threat_score), use_container_width=True, config={"displayModeBar": False})

    # 5. Analysis card
    a_color = ACTION_COLORS.get(action, "#64748b")
    analysis_placeholder.markdown(f"""
<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
padding:0.9rem;font-size:0.68rem;line-height:2;">
  <div><span style="color:#64748b">ANOMALY  </span><span style="color:{'#ff3d5a' if is_anomaly else '#00e676'};font-weight:700">{'YES' if is_anomaly else 'NO'}</span></div>
  <div><span style="color:#64748b">SCORE    </span><span style="color:{a_color};font-weight:700">{threat_score:.4f}</span></div>
  <div><span style="color:#64748b">ACTION   </span><span style="color:{a_color};font-weight:700">{action}</span></div>
  <div><span style="color:#64748b">CASCADE  </span><span style="color:{'#ff6b35' if st.session_state.cascade_active else '#00e676'};font-weight:700">{'ACTIVE' if st.session_state.cascade_active else 'NONE'}</span></div>
  <div><span style="color:#64748b">INF·TIME </span><span style="color:#64748b">{processing:.1f}ms</span></div>
</div>""", unsafe_allow_html=True)

    # 6. Log
    log_placeholder.markdown(
        '<div class="action-log">'+"".join(st.session_state.action_log)+"</div>",
        unsafe_allow_html=True,
    )

    # 7. Blast radius map
    if st.session_state.show_blast_map:
        blast = cascade_engine.get_blast_radius_map()
        blast_map_placeholder.plotly_chart(
            blast_renderer.build_figure(blast, height=460),
            use_container_width=True, config={"displayModeBar": False},
        )
        rows = blast_renderer.build_legend_table(blast)
        table_html = (
            '<table class="svc-table">'
            '<tr><th>Service</th><th>Health</th><th>Score</th><th>Reason</th></tr>'
        )
        for row in rows:
            table_html += (
                f'<tr>'
                f'<td><span class="svc-dot" style="background:{row["color"]}"></span>{row["service"]}</td>'
                f'<td style="color:{row["color"]};font-weight:700">{row["health"]}</td>'
                f'<td>{row["score"]}</td>'
                f'<td style="color:var(--text-dim)">{row["reason"][:30]}</td>'
                f'</tr>'
            )
        table_html += "</table>"
        blast_table_placeholder.markdown(table_html, unsafe_allow_html=True)

    time.sleep(REFRESH_S)