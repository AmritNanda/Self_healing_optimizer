import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { jsPDF } from 'jspdf';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts';
import {
  Activity, Cpu, HardDrive, ShieldAlert, ServerCrash,
  Network, RefreshCw, Globe, AlertTriangle, Radio, Shield,
  TrendingUp, Database, Layers, Wifi, WifiOff,
  CheckCircle2, XCircle, Loader2, Target, FileDown, BarChart3
} from 'lucide-react';

const API_BASE_URL = 'http://localhost:8081/api/v1';
const REFRESH_INTERVAL_MS = 2000;
const BOUTIQUE_URL = 'http://localhost:8888';

const MICROSERVICES = [
  { id: 'frontend', label: 'Frontend', tier: 'edge' },
  { id: 'cartservice', label: 'Cart', tier: 'core' },
  { id: 'productcatalogservice', label: 'Catalog', tier: 'core' },
  { id: 'currencyservice', label: 'Currency', tier: 'core' },
  { id: 'paymentservice', label: 'Payment', tier: 'core' },
  { id: 'shippingservice', label: 'Shipping', tier: 'core' },
  { id: 'emailservice', label: 'Email', tier: 'core' },
  { id: 'checkoutservice', label: 'Checkout', tier: 'core' },
  { id: 'recommendationservice', label: 'Recommend', tier: 'core' },
  { id: 'adservice', label: 'Ads', tier: 'aux' },
  { id: 'redis-cart', label: 'Redis', tier: 'data' },
];

const TIER_ICONS = {
  edge: Globe,
  core: Layers,
  aux: Radio,
  data: Database,
};

const DEPENDENCY_GRAPH = {
  frontend: [['productcatalogservice', 0.9], ['cartservice', 0.85], ['recommendationservice', 0.6], ['currencyservice', 0.75], ['adservice', 0.3]],
  checkoutservice: [['cartservice', 0.95], ['paymentservice', 0.99], ['emailservice', 0.5], ['currencyservice', 0.8], ['shippingservice', 0.85], ['productcatalogservice', 0.7]],
  cartservice: [['redis-cart', 0.98]],
  recommendationservice: [['productcatalogservice', 0.9]],
  productcatalogservice: [],
  paymentservice: [],
  shippingservice: [],
  emailservice: [],
  currencyservice: [],
  adservice: [['productcatalogservice', 0.4]],
  'redis-cart': [],
};

const HEALTH_COLORS = {
  HEALTHY: '#22c55e',
  DEGRADED: '#f59e0b',
  CRITICAL: '#f97316',
  FAILED: '#ef4444',
  RECOVERING: '#f97316',
};

// Cortex brand colors - Dark theme with orange accents
const C = {
  bg: '#0a0a0a',
  bgAlt: '#111111',
  surface: '#171717',
  surfaceHover: '#1f1f1f',
  border: '#262626',
  borderHover: '#404040',
  primary: '#f97316',
  primaryLight: '#fed7aa',
  primaryDark: '#c2410c',
  text: '#fafafa',
  textSub: '#a3a3a3',
  textMuted: '#525252',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
};

// ─── Keyframes ───────────────────────────────────────────────
const KEYFRAMES = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: #0a0a0a; color: #fafafa; font-family: 'Inter', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0%,100%{opacity:0.5;transform:scale(0.95)} 50%{opacity:1;transform:scale(1.05)} }
@keyframes fadeSlideUp { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
@keyframes stripeRotate { from{transform:translateY(-50%) rotate(-20deg)} to{transform:translateY(-50%) rotate(340deg)} }
@keyframes stripeOpen { 
  0%{transform:translateY(-50%) rotate(90deg) translateX(0)}
  100%{transform:translateY(-50%) rotate(90deg) translateX(var(--offset))}
}
`;

// ─── Boot Animation with 3 Orange Stripes ────────────────────
function BootLoader({ onComplete }) {
  const [phase, setPhase] = useState('loading'); // loading | rotating | opening | done
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const loadInterval = setInterval(() => {
      setProgress(p => {
        if (p >= 100) {
          clearInterval(loadInterval);
          setPhase('rotating');
          return 100;
        }
        return p + Math.random() * 15 + 5;
      });
    }, 80);
    return () => clearInterval(loadInterval);
  }, []);

  useEffect(() => {
    if (phase === 'rotating') {
      const timer = setTimeout(() => setPhase('opening'), 1200);
      return () => clearTimeout(timer);
    }
    if (phase === 'opening') {
      const timer = setTimeout(() => {
        setPhase('done');
        onComplete();
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [phase, onComplete]);

  const getStripeStyle = (i) => {
    const baseStyle = {
      position: 'absolute',
      width: 14,
      height: 80,
      borderRadius: 10,
      background: 'linear-gradient(180deg, #f97316 0%, #ea580c 100%)',
      left: 28 + i * 24,
      top: '50%',
      transformOrigin: 'center center',
      boxShadow: '0 0 40px rgba(249, 115, 22, 0.6)',
    };

    if (phase === 'loading') {
      return { ...baseStyle, transform: `translateY(-50%) rotate(${-20 + i * 5}deg)` };
    }
    if (phase === 'rotating') {
      return {
        ...baseStyle,
        transform: `translateY(-50%) rotate(${360 + i * 120}deg)`,
        transition: 'transform 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
      };
    }
    // opening
    const offsets = [-120, 0, 120];
    return {
      ...baseStyle,
      transform: `translateY(-50%) rotate(90deg) translateX(${offsets[i]}px)`,
      transition: 'transform 0.8s cubic-bezier(0.22, 1, 0.36, 1)',
    };
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0a0a0a 0%, #171717 50%, #1a1408 100%)',
      opacity: phase === 'done' ? 0 : 1,
      pointerEvents: phase === 'done' ? 'none' : 'auto',
      transition: 'opacity 0.5s ease',
    }}>
      {/* Stripes */}
      <div style={{ position: 'relative', width: 140, height: 140 }}>
        {[0, 1, 2].map(i => <div key={i} style={getStripeStyle(i)} />)}
      </div>

      {/* Brand + Progress */}
      <div style={{
        position: 'absolute', bottom: 100,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
        opacity: phase === 'opening' ? 0 : 1,
        transform: phase === 'opening' ? 'translateY(20px)' : 'translateY(0)',
        transition: 'all 0.4s ease',
      }}>
        <span style={{ fontSize: 28, fontWeight: 600, letterSpacing: -1, color: '#fafafa' }}>
          Corte<span style={{ color: '#f97316' }}>X</span>
        </span>
        <div style={{ width: 200, height: 4, background: '#262626', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: 4,
            background: 'linear-gradient(90deg, #f97316, #f59e0b)',
            width: `${Math.min(progress, 100)}%`,
            transition: 'width 0.2s ease',
          }} />
        </div>
        <span style={{ fontSize: 12, color: '#525252', fontWeight: 500, letterSpacing: 1 }}>
          {phase === 'loading' ? 'Initializing systems...' : 'Launching dashboard'}
        </span>
      </div>
    </div>
  );
}

// ─── Status Badge ────────────────────────────────────────────
function StatusBadge({ status, pulse }) {
  const configs = {
    NOMINAL: { bg: 'rgba(34,197,94,0.1)', color: '#22c55e' },
    INJECTING: { bg: 'rgba(245,158,11,0.1)', color: '#f59e0b' },
    DEGRADED: { bg: 'rgba(239,68,68,0.1)', color: '#ef4444' },
    HEALING: { bg: 'rgba(249,115,22,0.1)', color: '#f97316' },
    RECOVERED: { bg: 'rgba(34,197,94,0.1)', color: '#22c55e' },
  };
  const cfg = configs[status] || configs.NOMINAL;

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '6px 14px', borderRadius: 20,
      background: cfg.bg, border: `1px solid ${cfg.color}30`,
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: '50%',
        background: cfg.color,
        boxShadow: `0 0 8px ${cfg.color}`,
        animation: pulse ? 'pulse 1.5s ease-in-out infinite' : 'none',
      }} />
      <span style={{ fontSize: 12, fontWeight: 500, color: cfg.color }}>{status}</span>
    </div>
  );
}

// ─── KPI Card ────────────────────────────────────────────────
function KpiCard({ title, value, unit, accent, icon: Icon, sub, delay = 0 }) {
  const isAlert = accent === C.error;
  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${isAlert ? 'rgba(239,68,68,0.3)' : C.border}`,
      borderRadius: 12, padding: '18px 20px',
      animation: `fadeSlideUp 0.4s ease ${delay}ms both`,
      transition: 'border-color 0.2s, transform 0.2s',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: C.textSub, fontWeight: 500 }}>{title}</span>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: isAlert ? 'rgba(239,68,68,0.1)' : 'rgba(249,115,22,0.1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon size={18} color={accent} strokeWidth={1.8} />
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontSize: 32, fontWeight: 600, color: isAlert ? C.error : C.text, letterSpacing: -1 }}>{value}</span>
        <span style={{ fontSize: 13, color: C.textMuted }}>{unit}</span>
      </div>
      {sub && <p style={{ marginTop: 8, fontSize: 12, color: C.textMuted }}>{sub}</p>}
    </div>
  );
}

// ─── Phase Tracker ───────────────────────────────────────────
function PhaseTracker({ phase, activeChaos }) {
  const steps = [
    { id: 'NOMINAL', label: 'Nominal', Icon: CheckCircle2 },
    { id: 'INJECTING', label: 'Injecting', Icon: AlertTriangle },
    { id: 'DEGRADED', label: 'Degraded', Icon: XCircle },
    { id: 'HEALING', label: 'Healing', Icon: Loader2 },
    { id: 'RECOVERED', label: 'Recovered', Icon: Shield },
  ];
  const activeIdx = steps.findIndex(s => s.id === phase);
  const phaseColor = { NOMINAL: C.success, INJECTING: C.warning, DEGRADED: C.error, HEALING: C.primary, RECOVERED: C.success };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {steps.map(({ id, label, Icon }, i) => {
        const isActive = id === phase;
        const isPast = i < activeIdx;
        const col = isActive ? phaseColor[id] : isPast ? C.success : C.textMuted;

        return (
          <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: isActive ? `${col}15` : isPast ? `${C.success}10` : C.bgAlt,
              border: `1px solid ${isActive ? col : 'transparent'}`,
              boxShadow: isActive ? `0 0 0 3px ${col}20` : 'none',
              transition: 'all 0.25s',
            }}>
              <Icon size={14} color={col} strokeWidth={1.8}
                style={isActive && id === 'HEALING' ? { animation: 'spin 1.2s linear infinite' } : {}}
              />
            </div>
            <span style={{ fontSize: 13, fontWeight: isActive ? 600 : 400, color: col, transition: 'all 0.25s' }}>{label}</span>
            {isActive && <div style={{ flex: 1, height: 2, background: `linear-gradient(90deg, ${col}, transparent)`, borderRadius: 2 }} />}
          </div>
        );
      })}
      {activeChaos && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
          <p style={{ fontSize: 11, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Active Experiment</p>
          <p style={{ fontSize: 13, fontWeight: 600, color: C.primary }}>{activeChaos.replace(/_/g, ' ').toUpperCase()}</p>
        </div>
      )}
    </div>
  );
}

// ─── Service Node ────────────────────────────────────────────
function ServiceNode({ service, health }) {
  const Icon = TIER_ICONS[service.tier] || Layers;
  const cfg = {
    healthy: { bg: C.bgAlt, border: `${C.success}30`, dot: C.success },
    degraded: { bg: `${C.error}08`, border: `${C.error}50`, dot: C.error },
    healing: { bg: `${C.primary}08`, border: `${C.primary}50`, dot: C.primary },
  }[health] || { bg: C.bgAlt, border: `${C.success}30`, dot: C.success };

  return (
    <div style={{
      background: cfg.bg, border: `1px solid ${cfg.border}`,
      borderRadius: 10, padding: '12px 10px', textAlign: 'center',
      transition: 'all 0.3s',
    }}>
      <Icon size={16} color={C.textSub} strokeWidth={1.5} style={{ marginBottom: 6 }} />
      <p style={{ fontSize: 11, fontWeight: 500, color: C.textSub, marginBottom: 6 }}>{service.label}</p>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: cfg.dot, margin: '0 auto',
        boxShadow: `0 0 8px ${cfg.dot}`,
      }} />
    </div>
  );
}

// ─── Blast Radius Map ────────────────────────────────────────
function BlastRadiusMap({ blastData }) {
  const svgRef = useRef(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  if (!blastData || !blastData.states) return (
    <div style={{ padding: 60, textAlign: 'center', color: C.textMuted, fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
      <Loader2 size={20} style={{ animation: 'spin 1.2s linear infinite' }} color={C.textMuted} />
      <span>Connecting to cascade engine...</span>
    </div>
  );

  const W = 700, H = 380, pad = 44;
  const toSvg = (px, py) => [pad + (px / 100) * (W - 2 * pad), pad + ((100 - py) / 100) * (H - 2 * pad)];
  const states = blastData.states;
  const path = blastData.propagation_path || [];
  const cascadeEdges = new Set();
  for (let i = 0; i < path.length - 1; i++) {
    cascadeEdges.add(`${path[i]}|${path[i + 1]}`);
    cascadeEdges.add(`${path[i + 1]}|${path[i]}`);
  }

  const edges = [];
  for (const [src, deps] of Object.entries(DEPENDENCY_GRAPH)) {
    const sState = states[src]; if (!sState) continue;
    const [x0, y0] = toSvg(sState.position[0], sState.position[1]);
    for (const [dep] of deps) {
      const dState = states[dep]; if (!dState) continue;
      const [x1, y1] = toSvg(dState.position[0], dState.position[1]);
      const isCascade = cascadeEdges.has(`${src}|${dep}`) || cascadeEdges.has(`${dep}|${src}`);
      edges.push({ x0, y0, x1, y1, isCascade });
    }
  }

  const handleMouseMove = (e, svc) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (rect) setTooltipPos({ x: e.clientX - rect.left + 14, y: e.clientY - rect.top - 8 });
    setHoveredNode(svc);
  };
  const hovState = hoveredNode ? states[hoveredNode] : null;

  return (
    <div style={{ position: 'relative' }}>
      <svg ref={svgRef} width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        <defs>
          <filter id="glowNode">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {edges.map((e, i) => (
          <line key={i} x1={e.x0} y1={e.y0} x2={e.x1} y2={e.y1}
            stroke={e.isCascade ? '#ef4444' : '#404040'}
            strokeWidth={e.isCascade ? 2 : 1}
            strokeDasharray={e.isCascade ? '6 4' : 'none'}
          >
            {e.isCascade && <animate attributeName="stroke-dashoffset" from="20" to="0" dur="1s" repeatCount="indefinite" />}
          </line>
        ))}

        {Object.values(states).map(s => {
          const [cx, cy] = toSvg(s.position[0], s.position[1]);
          const r = Math.max(14, s.health_score * 0.12 + 10);
          const col = HEALTH_COLORS[s.health] || C.success;
          const isHov = hoveredNode === s.name;
          const isRoot = blastData.root_cause === s.name;

          return (
            <g key={s.name} onMouseMove={(e) => handleMouseMove(e, s.name)} onMouseLeave={() => setHoveredNode(null)} style={{ cursor: 'default' }}>
              <circle cx={cx} cy={cy} r={isHov ? r + 4 : r}
                fill={`${col}20`} stroke={col} strokeWidth={isHov ? 2.5 : 1.5}
                filter={isHov ? 'url(#glowNode)' : undefined} style={{ transition: 'all 0.2s' }}
              />
              <circle cx={cx} cy={cy} r={4} fill={col} />
              <text x={cx} y={cy + r + 16} textAnchor="middle" fill={C.textSub} fontSize="11" fontWeight="500" fontFamily="Inter, sans-serif">{s.display_name}</text>
              {isRoot && s.name !== 'none' && (
                <text x={cx} y={cy - r - 8} textAnchor="middle" fill="#ef4444" fontSize="10" fontWeight="600" fontFamily="Inter, sans-serif">ROOT CAUSE</text>
              )}
            </g>
          );
        })}
      </svg>

      {hovState && (
        <div style={{
          position: 'absolute', left: tooltipPos.x, top: tooltipPos.y, zIndex: 10,
          background: C.bgAlt, border: `1px solid ${C.border}`,
          borderRadius: 10, padding: '14px 16px', minWidth: 200, pointerEvents: 'none',
          boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: HEALTH_COLORS[hovState.health] || C.success }} />
            <span style={{ fontWeight: 600, fontSize: 14, color: C.text }}>{hovState.display_name}</span>
          </div>
          <div style={{ fontSize: 12, color: C.textSub, lineHeight: 1.8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Health</span><span style={{ color: HEALTH_COLORS[hovState.health] }}>{hovState.health}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Score</span><span style={{ color: C.text }}>{hovState.health_score}%</span>
            </div>
            {hovState.failure_reason && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Reason</span><span style={{ color: C.warning }}>{hovState.failure_reason}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {blastData.affected_count > 0 && (
        <div style={{
          position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)',
          background: C.bgAlt, border: `1px solid ${C.border}`,
          borderRadius: 20, padding: '6px 16px',
          fontSize: 12, fontWeight: 500,
          color: blastData.estimated_user_impact_pct >= 50 ? C.error : C.warning,
        }}>
          {blastData.affected_count}/{blastData.total_services} services affected - {blastData.estimated_user_impact_pct}% user impact
        </div>
      )}
    </div>
  );
}

// ─── Chaos Button ────────────────────────────────────────────
function ChaosButton({ label, desc, icon: Icon, onClick, active, disabled }) {
  const [hov, setHov] = useState(false);
  return (
    <button onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', flexDirection: 'column', textAlign: 'left', width: '100%',
        border: `1px solid ${active ? `${C.error}50` : hov && !disabled ? C.borderHover : C.border}`,
        borderRadius: 12, padding: '14px 16px',
        background: active ? `${C.error}08` : hov && !disabled ? C.surfaceHover : C.surface,
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.4 : 1,
        transition: 'all 0.15s', outline: 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Icon size={14} color={active ? C.error : hov && !disabled ? C.text : C.textSub} strokeWidth={1.8} />
        <span style={{ fontSize: 13, fontWeight: 600, color: active ? C.error : hov && !disabled ? C.text : C.textSub }}>{label}</span>
      </div>
      <span style={{ fontSize: 11, color: C.textMuted }}>{desc}</span>
    </button>
  );
}

// ─── Analysis Row ────────────────────────────────────────────
function AnalRow({ label, value, accent }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
      <span style={{ fontSize: 12, color: C.textSub, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 500, color: accent || C.text }}>{value}</span>
    </div>
  );
}

// ─── Tooltip style for charts ────────────────────────────────
const tooltipStyle = {
  contentStyle: { background: C.bgAlt, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12, color: C.text, padding: '10px 14px' },
};

// ═══════════════════════════════════════════════════════════
// Main App
// ═══════════════════════════════════════════════════════════
export default function App() {
  const [booting, setBooting] = useState(true);
  const [history, setHistory] = useState([]);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState({ anomalies: 0, recoveries: 0, totalChecks: 0 });
  const [current, setCurrent] = useState({ cpu: 0, mem: 0, lat: 0, threat: 0, is_anomaly: false, action: 'NO_ACTION' });
  const [activeChaos, setActiveChaos] = useState(null);
  const [chaosPhase, setChaosPhase] = useState('NOMINAL');
  const [iframeKey, setIframeKey] = useState(0);
  const [serviceHealth, setServiceHealth] = useState(() => {
    const m = {}; MICROSERVICES.forEach(s => { m[s.id] = 'healthy'; }); return m;
  });
  const [blastData, setBlastData] = useState(null);
  const [blastTab, setBlastTab] = useState('map');
  const wasAnomalousRef = useRef(false);
  const recoveryTimerRef = useRef(null);

  const addLog = useCallback((msg, level) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const colors = { ok: C.success, warn: C.warning, crit: C.error, info: C.primary, heal: C.primary };
    setLogs(prev => [{ time, msg, color: colors[level] || C.text }, ...prev].slice(0, 150));
  }, []);

  const degradeServices = useCallback((type) => {
    const affected = {
      pod_kill: ['frontend'], scale_zero: ['frontend'],
      cpu_stress: ['frontend', 'cartservice', 'checkoutservice'],
      memory_stress: ['frontend', 'productcatalogservice', 'redis-cart'],
      network_delay: ['frontend', 'cartservice', 'paymentservice', 'shippingservice'],
      network_loss: ['frontend', 'checkoutservice', 'emailservice'],
    };
    setServiceHealth(prev => {
      const next = { ...prev };
      (affected[type] || ['frontend']).forEach(s => { next[s] = 'degraded'; });
      return next;
    });
  }, []);

  const healServices = useCallback((resetBlast = false) => {
    setServiceHealth(prev => { const n = { ...prev }; Object.keys(n).forEach(k => { n[k] = 'healing'; }); return n; });
    setTimeout(() => {
      setServiceHealth(prev => { const n = { ...prev }; Object.keys(n).forEach(k => { n[k] = 'healthy'; }); return n; });
      if (resetBlast) axios.post(`${API_BASE_URL}/blast-radius/reset`).catch(() => { });
    }, 2000);
  }, []);

  useEffect(() => {
    addLog('Cortex SRE platform initialized', 'info');
    addLog('Monitoring 11 microservices', 'info');
    addLog('Isolation Forest ML model online', 'ok');

    const fetchMetrics = async () => {
      try {
        const telRes = await axios.get(`${API_BASE_URL}/telemetry`);
        const { cpu, mem, latency } = telRes.data;
        const anaRes = await axios.post(`${API_BASE_URL}/analyze`, { cpu_usage: cpu, mem_usage: mem, latency_ms: latency });
        const data = anaRes.data;
        const nowStr = new Date().toLocaleTimeString('en-US', { hour12: false });

        setCurrent({ cpu, mem, lat: latency, threat: data.threat_score, is_anomaly: data.is_anomaly, action: data.recommended_action });
        setStats(s => ({ ...s, totalChecks: s.totalChecks + 1 }));

        if (data.is_anomaly) {
          if (!wasAnomalousRef.current) setChaosPhase('DEGRADED');
          wasAnomalousRef.current = true;
          setStats(s => ({ ...s, anomalies: s.anomalies + 1 }));
          addLog(`Anomaly — Score: ${data.threat_score.toFixed(3)} | Action: ${data.recommended_action}`, 'crit');
          if (data.recommended_action !== 'NO_ACTION') {
            setStats(s => ({ ...s, recoveries: s.recoveries + 1 }));
            addLog(`Auto-heal triggered: ${data.recommended_action}`, 'heal');
          }
        } else {
          if (wasAnomalousRef.current) {
            wasAnomalousRef.current = false;
            setChaosPhase('HEALING');
            addLog('Self-healing engaged — recovering services', 'heal');
            healServices(true);
            if (recoveryTimerRef.current) clearTimeout(recoveryTimerRef.current);
            recoveryTimerRef.current = setTimeout(() => {
              setIframeKey(k => k + 1);
              setChaosPhase('RECOVERED');
              addLog('System recovered — all services nominal', 'ok');
              setTimeout(() => { setChaosPhase('NOMINAL'); setActiveChaos(null); }, 4000);
            }, 3000);
          }
        }

        setHistory(prev => {
          const pt = { time: nowStr, cpu: +cpu.toFixed(1), mem: +mem.toFixed(1), lat: +latency.toFixed(0), threat: +(data.threat_score * 100).toFixed(1) };
          const updated = [...prev, pt];
          return updated.length > 60 ? updated.slice(-60) : updated;
        });
      } catch (err) {
        addLog('API connectivity lost — check backend status', 'warn');
      }
    };

    const iv = setInterval(fetchMetrics, REFRESH_INTERVAL_MS);
    return () => { clearInterval(iv); if (recoveryTimerRef.current) clearTimeout(recoveryTimerRef.current); };
  }, [addLog, healServices]);

  useEffect(() => {
    let alive = true;
    const fetchBlast = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/blast-radius`);
        if (alive) setBlastData(res.data);
      } catch { }
    };
    fetchBlast();
    const iv2 = setInterval(fetchBlast, 3000);
    return () => { alive = false; clearInterval(iv2); };
  }, []);

  useEffect(() => {
    const handleKey = (e) => {
      if (e.target.tagName === 'INPUT') return;
      if (e.key === 'r' || e.key === 'R') setIframeKey(k => k + 1);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  const CHAOS_ROOT_SERVICE = {
    pod_kill: 'frontend', scale_zero: 'frontend', cpu_stress: 'frontend',
    memory_stress: 'redis-cart', network_delay: 'cartservice', network_loss: 'checkoutservice',
  };

  const triggerChaos = async (type) => {
    setChaosPhase('INJECTING'); setActiveChaos(type);
    addLog(`Injecting chaos: ${type.replace(/_/g, ' ').toUpperCase()}`, 'warn');
    try {
      await axios.post(`${API_BASE_URL}/chaos`, { type });
      setChaosPhase('DEGRADED');
      degradeServices(type);
      addLog(`Chaos deployed: ${type.replace(/_/g, ' ').toUpperCase()}`, 'crit');
      const rootSvc = CHAOS_ROOT_SERVICE[type] || 'frontend';
      await axios.post(`${API_BASE_URL}/blast-radius/inject`, { type: rootSvc });
    } catch (e) {
      addLog(`Failed to inject chaos: ${e.message}`, 'crit');
      setChaosPhase('NOMINAL'); setActiveChaos(null);
    }
  };

  const triggerScaleDown = async () => {
    setChaosPhase('INJECTING'); setActiveChaos('scale_zero');
    addLog('Scaling frontend to 0 replicas', 'warn');
    try {
      await axios.post(`${API_BASE_URL}/chaos/frontend-down`);
      setChaosPhase('DEGRADED');
      setIframeKey(k => k + 1);
      degradeServices('scale_zero');
      addLog('Frontend scaled to 0 — 503 active', 'crit');
      await axios.post(`${API_BASE_URL}/blast-radius/inject`, { type: 'frontend' });

      setTimeout(async () => {
        setChaosPhase('HEALING');
        addLog('Operator healing — scaling frontend back', 'heal');
        healServices();
        await axios.post(`${API_BASE_URL}/chaos/frontend-up`);
        setTimeout(async () => {
          setIframeKey(k => k + 1);
          setChaosPhase('RECOVERED');
          addLog('Frontend recovered — site live', 'ok');
          await axios.post(`${API_BASE_URL}/blast-radius/reset`);
          setTimeout(() => { setChaosPhase('NOMINAL'); setActiveChaos(null); }, 4000);
        }, 8000);
      }, 30000);
    } catch (e) {
      addLog(`Scale-down failed: ${e.message}`, 'crit');
      setChaosPhase('NOMINAL'); setActiveChaos(null);
    }
  };

  const exportPdf = () => {
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    const pw = doc.internal.pageSize.getWidth();
    const ph = doc.internal.pageSize.getHeight();
    const ml = 14, mr = 14, mt = 16;
    const usable = pw - ml - mr;
    const now = new Date();

    doc.setFillColor(10, 10, 10);
    doc.rect(0, 0, pw, ph, 'F');
    doc.setFontSize(16);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(250, 250, 250);
    doc.text('CORTEX SRE', ml, mt + 4);
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(100, 116, 139);
    doc.text(`Incident Report ��� ${now.toISOString()}`, ml, mt + 10);
    doc.setDrawColor(38, 38, 38);
    doc.line(ml, mt + 13, pw - mr, mt + 13);

    let y = mt + 20;
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(163, 163, 163);
    doc.text('Event Log', ml, y);
    y += 8;

    logs.slice(0, 80).forEach((log) => {
      if (y > ph - 16) { doc.addPage(); y = mt; }
      doc.setFontSize(7.5);
      doc.setFont('courier', 'normal');
      doc.setTextColor(100, 116, 139);
      doc.text(`[${log.time}]`, ml, y);
      doc.setTextColor(200, 200, 200);
      const msgLines = doc.splitTextToSize(log.msg, usable - 28);
      doc.text(msgLines[0], ml + 24, y);
      y += 6;
    });

    const filename = `cortex-sre-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}.pdf`;
    doc.save(filename);
  };

  const logColors = { ok: C.success, warn: C.warning, crit: C.error, info: C.primary, heal: C.primary };

  if (booting) return (
    <>
      <style>{KEYFRAMES}</style>
      <BootLoader onComplete={() => setBooting(false)} />
    </>
  );

  const kpis = [
    { title: 'CPU Usage', value: current.cpu.toFixed(1), unit: '%', accent: current.cpu > 80 ? C.error : C.primary, icon: Cpu, delay: 0 },
    { title: 'Memory', value: current.mem.toFixed(1), unit: '%', accent: current.mem > 80 ? C.error : C.success, icon: HardDrive, delay: 50 },
    { title: 'P99 Latency', value: current.lat.toFixed(0), unit: 'ms', accent: current.lat > 500 ? C.error : C.warning, icon: Activity, delay: 100 },
    { title: 'Threat Score', value: (current.threat * 100).toFixed(1), unit: '%', accent: current.threat > 0.6 ? C.error : C.primary, icon: ShieldAlert, delay: 150 },
    { title: 'Auto-Heals', value: stats.recoveries, unit: 'actions', accent: C.success, icon: RefreshCw, sub: `${stats.anomalies} anomalies detected`, delay: 200 },
  ];

  const iframeBorderColor = { DEGRADED: C.error, INJECTING: C.warning, HEALING: C.primary, RECOVERED: C.success }[chaosPhase] || 'transparent';

  return (
    <>
      <style>{KEYFRAMES}</style>
      <div style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #0a0a0a 0%, #171717 50%, #1a1408 100%)',
        fontFamily: "'Inter', system-ui, sans-serif",
        display: 'flex', flexDirection: 'column',
      }}>

        {/* Header - Centered */}
        <header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '0 28px', height: 60,
          background: 'rgba(17,17,17,0.8)',
          backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
          borderBottom: `1px solid ${C.border}`,
          position: 'sticky', top: 0, zIndex: 50,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Logo stripes */}
            <div style={{ display: 'flex', alignItems: 'center' }}>
              {[0, 1, 2].map(i => (
                <div key={i} style={{
                  width: 6, height: 28, borderRadius: 4,
                  background: 'linear-gradient(180deg, #f97316, #ea580c)',
                  transform: `rotate(-15deg) translateX(${i * 3}px)`,
                  marginLeft: i === 0 ? 0 : -2,
                  boxShadow: '0 0 12px rgba(249,115,22,0.4)',
                }} />
              ))}
            </div>
            <span style={{ fontSize: 22, fontWeight: 600, color: C.text, marginLeft: 4 }}>
              Corte<span style={{ color: '#f97316' }}>X</span>
            </span>
            <div style={{ width: 1, height: 24, background: C.border }} />
            <span style={{ fontSize: 14, fontWeight: 500, color: C.textSub }}>SRE Dashboard</span>
            <div style={{ width: 1, height: 24, background: C.border }} />
            <StatusBadge status={chaosPhase} pulse={chaosPhase !== 'NOMINAL' && chaosPhase !== 'RECOVERED'} />
          </div>
        </header>

        {/* Stats Bar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 28px', height: 40,
          background: 'rgba(17,17,17,0.5)',
          borderBottom: `1px solid ${C.border}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24, fontSize: 13 }}>
            <span style={{ color: C.textSub }}><span style={{ fontWeight: 600, color: C.text }}>{stats.totalChecks.toLocaleString()}</span> checks</span>
            <span style={{ color: C.textSub }}><span style={{ fontWeight: 600, color: C.text }}>{stats.anomalies}</span> anomalies</span>
            <span style={{ color: C.textSub }}><span style={{ fontWeight: 600, color: C.text }}>{stats.recoveries}</span> heals</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20, fontSize: 13 }}>
            <span style={{ color: C.textMuted }}>CPU <span style={{ fontWeight: 500, color: current.cpu > 80 ? C.error : C.text }}>{current.cpu.toFixed(1)}%</span></span>
            <span style={{ color: C.textMuted }}>Memory <span style={{ fontWeight: 500, color: current.mem > 80 ? C.error : C.text }}>{current.mem.toFixed(1)}%</span></span>
            <span style={{ color: C.textMuted }}>P99 <span style={{ fontWeight: 500, color: current.lat > 500 ? C.error : C.text }}>{current.lat.toFixed(0)}ms</span></span>
          </div>
        </div>

        {/* Main Content */}
        <div style={{ flex: 1, padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* KPI Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16 }}>
            {kpis.map(k => <KpiCard key={k.title} {...k} />)}
          </div>

          {/* Main Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20 }}>

            {/* Left Column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Live Preview */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: `1px solid ${C.border}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Globe size={16} color={C.textSub} />
                    <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Live Application Preview</span>
                    {activeChaos && (
                      <span style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, background: `${C.error}10`, border: `1px solid ${C.error}30`, color: C.error }}>
                        {activeChaos.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 12, color: C.textMuted, background: C.bgAlt, padding: '4px 10px', borderRadius: 6 }}>{BOUTIQUE_URL}</span>
                    <button onClick={() => setIframeKey(k => k + 1)} style={{
                      display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8,
                      background: C.bgAlt, border: `1px solid ${C.border}`, color: C.textSub, cursor: 'pointer', fontSize: 12, fontWeight: 500,
                    }}>
                      <RefreshCw size={14} /> Reload
                    </button>
                  </div>
                </div>
                <div style={{ borderTop: `4px solid ${iframeBorderColor}`, transition: 'border-color 0.4s' }}>
                  <iframe key={iframeKey} src={BOUTIQUE_URL} title="Live App" style={{ width: '100%', height: 400, border: 'none', display: 'block', background: '#fff' }} />
                  {chaosPhase === 'HEALING' && (
                    <div style={{ position: 'absolute', inset: 0, background: `${C.primary}08`, pointerEvents: 'none', display: 'flex', alignItems: 'flex-end', padding: 16 }}>
                      <div style={{ background: C.bgAlt, border: `1px solid ${C.primary}30`, borderRadius: 8, padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: C.primary }}>
                        <Loader2 size={14} style={{ animation: 'spin 1.2s linear infinite' }} /> Self-healing in progress...
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Charts */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <TrendingUp size={16} color={C.textSub} />
                  <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Telemetry</span>
                  <span style={{ fontSize: 12, color: C.textMuted, marginLeft: 8 }}>Last 2 minutes</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                  <div>
                    <p style={{ fontSize: 12, color: C.textSub, marginBottom: 10 }}>CPU / Memory (%)</p>
                    <ResponsiveContainer width="100%" height={140}>
                      <AreaChart data={history} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="gCpu" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#f97316" stopOpacity={0.3} />
                            <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="gMem" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#22c55e" stopOpacity={0.2} />
                            <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={C.border} strokeDasharray="3 0" vertical={false} />
                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: C.textMuted }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 10, fill: C.textMuted }} tickLine={false} axisLine={false} domain={[0, 100]} />
                        <Tooltip {...tooltipStyle} />
                        <ReferenceLine y={80} stroke="#7f1d1d" strokeDasharray="3 3" />
                        <Area type="monotone" dataKey="cpu" stroke="#f97316" strokeWidth={2} fill="url(#gCpu)" dot={false} name="CPU" />
                        <Area type="monotone" dataKey="mem" stroke="#22c55e" strokeWidth={2} fill="url(#gMem)" dot={false} name="Memory" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                  <div>
                    <p style={{ fontSize: 12, color: C.textSub, marginBottom: 10 }}>P99 Latency (ms)</p>
                    <ResponsiveContainer width="100%" height={140}>
                      <AreaChart data={history} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                        <defs>
                          <linearGradient id="gLat" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.3} />
                            <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={C.border} strokeDasharray="3 0" vertical={false} />
                        <XAxis dataKey="time" tick={{ fontSize: 10, fill: C.textMuted }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 10, fill: C.textMuted }} tickLine={false} axisLine={false} />
                        <Tooltip {...tooltipStyle} />
                        <ReferenceLine y={500} stroke="#7f1d1d" strokeDasharray="3 3" />
                        <Area type="monotone" dataKey="lat" stroke="#f59e0b" strokeWidth={2} fill="url(#gLat)" dot={false} name="P99" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Blast Radius */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Target size={16} color={C.textSub} />
                    <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Blast Radius</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: C.bgAlt, borderRadius: 8, padding: 4 }}>
                    {[{ id: 'map', label: 'Graph' }, { id: 'table', label: 'Table' }, { id: 'events', label: 'Events' }].map(t => (
                      <button key={t.id} onClick={() => setBlastTab(t.id)} style={{
                        padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500,
                        background: blastTab === t.id ? C.surfaceHover : 'transparent',
                        color: blastTab === t.id ? C.text : C.textMuted, transition: 'all 0.15s',
                      }}>{t.label}</button>
                    ))}
                  </div>
                </div>
                {blastTab === 'map' && <BlastRadiusMap blastData={blastData} />}

                {/* ── Table Tab: Service Status Table ── */}
                {blastTab === 'table' && (
                  !blastData || !blastData.states ? (
                    <div style={{ padding: 40, textAlign: 'center', color: C.textMuted, fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                      <Loader2 size={20} style={{ animation: 'spin 1.2s linear infinite' }} color={C.textMuted} />
                      <span>Loading service data...</span>
                    </div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ borderBottom: `2px solid ${C.border}` }}>
                            {['Service', 'Health', 'Score', 'CPU %', 'Memory', 'Restarts', 'Replicas', 'Reason'].map(h => (
                              <th key={h} style={{
                                padding: '10px 10px', textAlign: 'left', fontWeight: 600,
                                color: C.textSub, textTransform: 'uppercase', letterSpacing: 0.5,
                                fontSize: 10, whiteSpace: 'nowrap',
                              }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {Object.values(blastData.states)
                            .sort((a, b) => a.health_score - b.health_score)
                            .map(s => {
                              const hCol = HEALTH_COLORS[s.health] || C.success;
                              const m = s.metrics || {};
                              return (
                                <tr key={s.name} style={{
                                  borderBottom: `1px solid ${C.border}`,
                                  transition: 'background 0.15s',
                                  background: s.health !== 'HEALTHY' ? `${hCol}06` : 'transparent',
                                }}>
                                  <td style={{ padding: '10px 10px', fontWeight: 500, color: C.text, whiteSpace: 'nowrap' }}>
                                    {s.display_name}
                                  </td>
                                  <td style={{ padding: '10px 10px' }}>
                                    <span style={{
                                      display: 'inline-flex', alignItems: 'center', gap: 6,
                                      padding: '3px 10px', borderRadius: 12,
                                      background: `${hCol}15`, color: hCol, fontSize: 11, fontWeight: 600,
                                    }}>
                                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: hCol, boxShadow: `0 0 6px ${hCol}` }} />
                                      {s.health}
                                    </span>
                                  </td>
                                  <td style={{ padding: '10px 10px', fontWeight: 600, color: s.health_score >= 80 ? C.success : s.health_score >= 50 ? C.warning : C.error }}>
                                    {s.health_score}%
                                  </td>
                                  <td style={{ padding: '10px 10px', color: (m.cpu_percent || 0) > 70 ? C.error : C.textSub }}>
                                    {m.cpu_percent != null ? `${m.cpu_percent.toFixed(1)}%` : '—'}
                                  </td>
                                  <td style={{ padding: '10px 10px', color: (m.memory_mb || 0) > 300 ? C.warning : C.textSub }}>
                                    {m.memory_mb != null ? `${m.memory_mb.toFixed(0)} MB` : '—'}
                                  </td>
                                  <td style={{ padding: '10px 10px', color: (m.restart_count || 0) > 0 ? C.warning : C.textMuted }}>
                                    {m.restart_count != null ? m.restart_count : '—'}
                                  </td>
                                  <td style={{ padding: '10px 10px', color: C.textSub }}>
                                    {m.replicas_available != null ? `${m.replicas_available}/${m.replicas_desired}` : '—'}
                                  </td>
                                  <td style={{ padding: '10px 10px', color: s.failure_reason ? C.warning : C.textMuted, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {s.failure_reason || '—'}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 10px', borderTop: `1px solid ${C.border}`, marginTop: 4 }}>
                        <span style={{ fontSize: 11, color: C.textMuted }}>
                          {Object.values(blastData.states).filter(s => s.health !== 'HEALTHY').length} of {Object.keys(blastData.states).length} services affected
                        </span>
                        <span style={{ fontSize: 11, color: blastData.estimated_user_impact_pct > 0 ? C.error : C.textMuted }}>
                          User Impact: {blastData.estimated_user_impact_pct}%
                        </span>
                      </div>
                    </div>
                  )
                )}

                {/* ── Events Tab: Cascade Events Timeline ── */}
                {blastTab === 'events' && (
                  !blastData ? (
                    <div style={{ padding: 40, textAlign: 'center', color: C.textMuted, fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                      <Loader2 size={20} style={{ animation: 'spin 1.2s linear infinite' }} color={C.textMuted} />
                      <span>Loading events...</span>
                    </div>
                  ) : !blastData.events || blastData.events.length === 0 ? (
                    <div style={{ padding: 40, textAlign: 'center', color: C.textMuted, fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                      <Activity size={20} color={C.textMuted} />
                      <span>No cascade events — inject chaos to see propagation</span>
                    </div>
                  ) : (
                    <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                      {blastData.events.slice().reverse().map((ev, i) => {
                        const prevColor = HEALTH_COLORS[ev.previous] || C.textMuted;
                        const curColor = HEALTH_COLORS[ev.current] || C.success;
                        const ts = new Date(ev.timestamp * 1000);
                        const timeStr = ts.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
                        const svcDisplay = (blastData.states[ev.service] || {}).display_name || ev.service;

                        return (
                          <div key={i} style={{
                            display: 'flex', alignItems: 'flex-start', gap: 12,
                            padding: '10px 8px', borderBottom: `1px solid ${C.border}`,
                            animation: `fadeSlideUp 0.3s ease ${Math.min(i * 40, 400)}ms both`,
                          }}>
                            {/* Depth indicator + timeline dot */}
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 24, paddingTop: 2 }}>
                              <div style={{
                                width: 10, height: 10, borderRadius: '50%',
                                background: curColor, boxShadow: `0 0 8px ${curColor}60`,
                              }} />
                              {i < blastData.events.length - 1 && (
                                <div style={{ width: 2, height: 20, background: C.border }} />
                              )}
                            </div>

                            {/* Event content */}
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                                <span style={{ fontWeight: 600, fontSize: 13, color: C.text }}>{svcDisplay}</span>
                                <span style={{ fontSize: 11, color: prevColor, fontWeight: 500 }}>{ev.previous}</span>
                                <span style={{ fontSize: 11, color: C.textMuted }}>→</span>
                                <span style={{ fontSize: 11, color: curColor, fontWeight: 600 }}>{ev.current}</span>
                                {ev.depth > 0 && (
                                  <span style={{
                                    fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                    background: `${C.primary}15`, color: C.primary, fontWeight: 500,
                                  }}>
                                    depth {ev.depth}
                                  </span>
                                )}
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: C.textMuted }}>
                                <span style={{ fontFamily: 'monospace' }}>{timeStr}</span>
                                <span>Score: <span style={{ color: ev.health_score >= 80 ? C.success : ev.health_score >= 50 ? C.warning : C.error, fontWeight: 500 }}>{ev.health_score}%</span></span>
                                {ev.triggered_by && ev.triggered_by !== 'cluster' && (
                                  <span>via <span style={{ color: C.primary }}>{ev.triggered_by}</span></span>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )
                )}
              </div>

              {/* Chaos Control */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <AlertTriangle size={16} color={C.textSub} />
                  <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Chaos Control Panel</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12 }}>
                  <ChaosButton label="Kill Frontend" desc="Scale to 0 — real 503" icon={ServerCrash} onClick={triggerScaleDown} active={activeChaos === 'scale_zero'} disabled={chaosPhase !== 'NOMINAL'} />
                  <ChaosButton label="Pod Kill" desc="Kills frontend pod" icon={XCircle} onClick={() => triggerChaos('pod_kill')} active={activeChaos === 'pod_kill'} disabled={chaosPhase !== 'NOMINAL'} />
                  <ChaosButton label="CPU Stress" desc="80% CPU injection" icon={Cpu} onClick={() => triggerChaos('cpu_stress')} active={activeChaos === 'cpu_stress'} disabled={chaosPhase !== 'NOMINAL'} />
                  <ChaosButton label="Memory Hog" desc="256MB pressure" icon={HardDrive} onClick={() => triggerChaos('memory_stress')} active={activeChaos === 'memory_stress'} disabled={chaosPhase !== 'NOMINAL'} />
                  <ChaosButton label="Net Delay" desc="200ms latency" icon={Wifi} onClick={() => triggerChaos('network_delay')} active={activeChaos === 'network_delay'} disabled={chaosPhase !== 'NOMINAL'} />
                  <ChaosButton label="Net Loss" desc="100% packet drop" icon={WifiOff} onClick={() => triggerChaos('network_loss')} active={activeChaos === 'network_loss'} disabled={chaosPhase !== 'NOMINAL'} />
                </div>
              </div>
            </div>

            {/* Right Column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Phase Tracker */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <Activity size={16} color={C.textSub} />
                  <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Chaos Lifecycle</span>
                </div>
                <PhaseTracker phase={chaosPhase} activeChaos={activeChaos} />
              </div>

              {/* ML Analysis */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <Shield size={16} color={C.textSub} />
                  <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>ML Analysis</span>
                </div>
                <AnalRow label="Status" value={current.is_anomaly ? 'ANOMALY' : 'NOMINAL'} accent={current.is_anomaly ? C.error : C.success} />
                <AnalRow label="Threat Score" value={`${(current.threat * 100).toFixed(1)}%`} accent={current.threat > 0.6 ? C.error : undefined} />
                <AnalRow label="Action" value={current.action} accent={current.action !== 'NO_ACTION' ? C.primary : undefined} />
                <AnalRow label="Anomalies" value={stats.anomalies} />
                <AnalRow label="Auto Heals" value={stats.recoveries} accent={C.success} />
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: C.textSub, marginBottom: 8 }}>
                    <span>Model</span><span style={{ color: C.text }}>Isolation Forest</span>
                  </div>
                  <div style={{ height: 6, background: C.bgAlt, borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: 4, transition: 'width 0.4s',
                      width: `${current.threat * 100}%`,
                      background: current.threat > 0.6 ? 'linear-gradient(90deg, #f59e0b, #ef4444)' : 'linear-gradient(90deg, #f97316, #f59e0b)',
                    }} />
                  </div>
                </div>
              </div>

              {/* Service Mesh */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                  <Network size={16} color={C.textSub} />
                  <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Service Mesh</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                  {MICROSERVICES.map(s => <ServiceNode key={s.id} service={s} health={serviceHealth[s.id]} />)}
                </div>
              </div>

              {/* Event Log */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: '18px 20px', flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Radio size={16} color={C.textSub} />
                    <span style={{ fontSize: 14, fontWeight: 500, color: C.text }}>Event Log</span>
                  </div>
                  <button onClick={exportPdf} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 6, cursor: 'pointer',
                    background: C.bgAlt, border: `1px solid ${C.border}`, color: C.textSub, fontSize: 11, fontWeight: 500,
                  }}>
                    <FileDown size={12} /> PDF
                  </button>
                </div>
                <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                  {logs.map((log, i) => (
                    <div key={i} style={{ display: 'flex', gap: 12, padding: '8px 0', borderBottom: `1px solid ${C.border}` }}>
                      <span style={{ fontSize: 11, color: C.textMuted, flexShrink: 0, fontFamily: 'monospace' }}>{log.time}</span>
                      <span style={{ fontSize: 12, color: log.color }}>{log.msg}</span>
                    </div>
                  ))}
                  {logs.length === 0 && <p style={{ fontSize: 12, color: C.textMuted, padding: 16, textAlign: 'center' }}>No events yet</p>}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 28px',
          background: 'rgba(17,17,17,0.8)',
          backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
          borderTop: `1px solid ${C.border}`,
        }}>
          <span style={{ fontSize: 12, color: C.textMuted }}>Cortex v1.0.0 - {stats.totalChecks.toLocaleString()} health checks performed</span>
          <span style={{ fontSize: 12, color: C.textMuted }}>Press <kbd style={{ padding: '2px 6px', background: C.bgAlt, border: `1px solid ${C.border}`, borderRadius: 4, fontSize: 10 }}>R</kbd> to reload preview</span>
        </footer>
      </div>
    </>
  );
}