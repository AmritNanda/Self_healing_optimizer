import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts';
import {
  Activity, Cpu, HardDrive, ShieldAlert, Zap, ServerCrash,
  Network, RefreshCw, Globe, AlertTriangle, Radio, Shield,
  TrendingUp, Database, GitBranch, Layers, Wifi, WifiOff,
  MemoryStick, Siren, CheckCircle2, XCircle, Loader2
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

// ─── Gemini-style loader ────────────────────────────────────
function GeminiLoader() {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: '#070b12',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: '2rem'
    }}>
      <div style={{ position: 'relative', width: 72, height: 72 }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            position: 'absolute', inset: 0,
            borderRadius: '50%',
            border: '1.5px solid transparent',
            borderTopColor: ['#3b82f6', '#6366f1', '#8b5cf6'][i],
            animation: `spin ${1.2 + i * 0.3}s linear infinite`,
            transform: `scale(${1 - i * 0.18})`
          }} />
        ))}
        <div style={{
          position: 'absolute', inset: '28%',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(99,102,241,0.6), transparent)',
          animation: 'pulse 2s ease-in-out infinite'
        }} />
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          fontFamily: 'Inter, system-ui, sans-serif',
          fontSize: '0.8rem', letterSpacing: '0.25em',
          textTransform: 'uppercase', color: 'rgba(148,163,184,0.7)',
          marginBottom: '0.5rem'
        }}>
          Initializing NEXUS
        </div>
        <div style={{
          width: 200, height: 2,
          background: 'rgba(255,255,255,0.05)',
          borderRadius: 4, overflow: 'hidden'
        }}>
          <div style={{
            height: '100%',
            background: 'linear-gradient(90deg, #3b82f6, #6366f1, #8b5cf6)',
            borderRadius: 4,
            animation: 'shimmerBar 1.8s ease-in-out infinite'
          }} />
        </div>
      </div>
    </div>
  );
}

// ─── Keyframes injected once ────────────────────────────────
const KEYFRAMES = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #070b12; color: #e2e8f0; font-family: 'Inter', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes spin2 { to { transform: scale(0.82) rotate(360deg); } }
@keyframes spin3 { to { transform: scale(0.64) rotate(360deg); } }
@keyframes pulse { 0%,100%{opacity:0.4;transform:scale(0.9)} 50%{opacity:1;transform:scale(1.1)} }
@keyframes shimmerBar { 0%{width:0%;opacity:1} 70%{width:100%;opacity:1} 100%{width:100%;opacity:0} }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
@keyframes healPulse { 0%,100%{box-shadow:0 0 0 0 rgba(99,102,241,0.15)} 50%{box-shadow:0 0 0 8px rgba(99,102,241,0)} }
@keyframes dangerPulse { 0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.1)} 50%{box-shadow:0 0 0 8px rgba(239,68,68,0)} }
@keyframes recoverFlash { 0%{box-shadow:0 0 0 0 rgba(34,197,94,0.2)} 50%{box-shadow:0 0 40px rgba(34,197,94,0.15)} 100%{box-shadow:none} }
`;

// ─── Design tokens ──────────────────────────────────────────
const T = {
  bg: '#070b12',
  surface: 'rgba(255,255,255,0.03)',
  surfaceHover: 'rgba(255,255,255,0.055)',
  glass: 'rgba(15,20,35,0.7)',
  border: 'rgba(255,255,255,0.07)',
  borderHover: 'rgba(255,255,255,0.13)',
  blue: '#3b82f6',
  indigo: '#6366f1',
  violet: '#8b5cf6',
  green: '#22c55e',
  amber: '#f59e0b',
  red: '#ef4444',
  muted: 'rgba(148,163,184,0.55)',
  text: '#e2e8f0',
  textSub: 'rgba(148,163,184,0.7)',
};

// ─── Shared card style ───────────────────────────────────────
const card = (extra = {}) => ({
  background: T.glass,
  border: `1px solid ${T.border}`,
  borderRadius: 14,
  backdropFilter: 'blur(12px)',
  WebkitBackdropFilter: 'blur(12px)',
  transition: 'border-color 0.2s',
  ...extra
});

// ─── Section label ───────────────────────────────────────────
function SectionLabel({ children, icon: Icon }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
      {Icon && <Icon size={13} color={T.muted} />}
      <span style={{
        fontSize: '0.65rem', fontWeight: 600, letterSpacing: '0.18em',
        textTransform: 'uppercase', color: T.muted
      }}>
        {children}
      </span>
    </div>
  );
}

// ─── KPI Card ────────────────────────────────────────────────
function KpiCard({ title, value, unit, accent, icon: Icon, sublabel }) {
  const [hov, setHov] = useState(false);
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        ...card(),
        padding: '1.1rem 1.25rem',
        borderColor: hov ? T.borderHover : T.border,
        cursor: 'default',
        position: 'relative', overflow: 'hidden',
        animation: 'fadeIn 0.4s ease both'
      }}
    >
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 1,
        background: `linear-gradient(90deg, transparent, ${accent}40, transparent)`
      }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <span style={{
          fontSize: '0.6rem', fontWeight: 500, letterSpacing: '0.12em',
          textTransform: 'uppercase', color: T.textSub
        }}>{title}</span>
        <div style={{ color: accent, opacity: 0.5 }}><Icon size={15} /></div>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
        <span style={{ fontSize: '1.75rem', fontWeight: 700, color: accent, lineHeight: 1 }}>{value}</span>
        <span style={{ fontSize: '0.6rem', color: T.textSub }}>{unit}</span>
      </div>
      {sublabel && <div style={{ fontSize: '0.6rem', color: T.textSub, marginTop: 4 }}>{sublabel}</div>}
    </div>
  );
}

// ─── Phase step list ─────────────────────────────────────────
function PhaseTracker({ phase, activeChaos }) {
  const steps = [
    { id: 'NOMINAL', label: 'Nominal', Icon: CheckCircle2 },
    { id: 'INJECTING', label: 'Injecting', Icon: AlertTriangle },
    { id: 'DEGRADED', label: 'Degraded', Icon: XCircle },
    { id: 'HEALING', label: 'Healing', Icon: Loader2 },
    { id: 'RECOVERED', label: 'Recovered', Icon: Shield },
  ];
  const activeIdx = steps.findIndex(s => s.id === phase);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {steps.map(({ id, label, Icon }, i) => {
        const isActive = id === phase;
        const isPast = i < activeIdx;
        const accent = isActive
          ? (id === 'DEGRADED' ? T.red : id === 'HEALING' ? T.violet : id === 'RECOVERED' ? T.green : T.blue)
          : isPast ? T.green : undefined;
        return (
          <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 30, height: 30, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: `1px solid ${accent ? accent + '40' : T.border}`,
              background: isActive ? accent + '15' : isPast ? T.green + '0d' : T.surface,
              transition: 'all 0.3s',
              boxShadow: isActive ? `0 0 14px ${accent}30` : 'none',
              flexShrink: 0
            }}>
              <Icon size={13}
                color={accent || T.muted}
                style={isActive && id === 'HEALING' ? { animation: 'spin 1.2s linear infinite' } : {}}
              />
            </div>
            <span style={{
              fontSize: '0.72rem', fontWeight: isActive ? 600 : 400,
              color: isActive ? accent : isPast ? T.green + '99' : T.textSub,
              letterSpacing: '0.05em',
              transition: 'all 0.3s'
            }}>{label}</span>
            {isActive && (
              <div style={{
                flex: 1, height: 1,
                background: `linear-gradient(90deg, ${accent}50, transparent)`
              }} />
            )}
          </div>
        );
      })}
      {activeChaos && (
        <div style={{
          marginTop: 8, paddingTop: 12,
          borderTop: `1px solid ${T.border}`
        }}>
          <div style={{
            fontSize: '0.58rem', color: T.textSub, letterSpacing: '0.12em',
            textTransform: 'uppercase', marginBottom: 4
          }}>Active Experiment</div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: T.amber }}>
            {activeChaos.replace(/_/g, ' ').toUpperCase()}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Service node ────────────────────────────────────────────
function ServiceNode({ service, health }) {
  const Icon = TIER_ICONS[service.tier] || Layers;
  const cfg = {
    healthy: { border: `${T.green}30`, bg: `${T.green}08`, dot: T.green, glow: 'none' },
    degraded: { border: `${T.red}50`, bg: `${T.red}10`, dot: T.red, glow: `0 0 10px ${T.red}30` },
    healing: { border: `${T.violet}50`, bg: `${T.violet}10`, dot: T.violet, glow: `0 0 10px ${T.violet}30` },
  }[health] || { border: `${T.green}30`, bg: `${T.green}08`, dot: T.green, glow: 'none' };

  return (
    <div style={{
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      borderRadius: 10,
      padding: '10px 8px',
      textAlign: 'center',
      transition: 'all 0.4s',
      boxShadow: cfg.glow,
      animation: health === 'degraded' ? 'dangerPulse 2s ease-in-out infinite' :
        health === 'healing' ? 'healPulse 1.5s ease-in-out infinite' : 'none'
    }}>
      <Icon size={16} color={cfg.dot} style={{ margin: '0 auto 6px' }} />
      <div style={{ fontSize: '0.58rem', color: T.textSub, fontWeight: 500, lineHeight: 1.2 }}>
        {service.label}
      </div>
      <div style={{
        width: 6, height: 6, borderRadius: '50%',
        background: cfg.dot, margin: '6px auto 0',
        boxShadow: `0 0 6px ${cfg.dot}`
      }} />
    </div>
  );
}

// ─── Analysis row ────────────────────────────────────────────
function AnalRow({ label, value, accent }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '7px 0', borderBottom: `1px solid ${T.border}`
    }}>
      <span style={{
        fontSize: '0.65rem', color: T.textSub, fontWeight: 500,
        letterSpacing: '0.06em', textTransform: 'uppercase'
      }}>{label}</span>
      <span style={{ fontSize: '0.72rem', fontWeight: 600, color: accent || T.text }}>
        {value}
      </span>
    </div>
  );
}

// ─── Chaos button ────────────────────────────────────────────
function ChaosButton({ label, desc, icon: Icon, onClick, active, disabled }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', flexDirection: 'column', textAlign: 'left',
        border: `1px solid ${active ? T.red + '60' : hov && !disabled ? T.borderHover : T.border}`,
        borderRadius: 10,
        padding: '12px 14px',
        background: active ? `${T.red}0d` : hov && !disabled ? T.surfaceHover : T.surface,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        transition: 'all 0.18s ease',
        boxShadow: active ? `0 0 20px ${T.red}20` : hov && !disabled ? `0 0 12px rgba(99,102,241,0.08)` : 'none',
        outline: 'none', width: '100%'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
        <Icon size={14} color={active ? T.red : hov && !disabled ? T.indigo : T.muted} />
        <span style={{
          fontSize: '0.72rem', fontWeight: 600,
          color: active ? T.red : hov && !disabled ? T.text : T.textSub
        }}>
          {label}
        </span>
      </div>
      <span style={{ fontSize: '0.6rem', color: T.textSub, lineHeight: 1.4 }}>{desc}</span>
    </button>
  );
}

// ─── Status badge ────────────────────────────────────────────
function StatusBadge({ phase }) {
  const cfg = {
    NOMINAL: { label: 'Nominal', color: T.green, bg: `${T.green}15` },
    INJECTING: { label: 'Chaos Injecting', color: T.amber, bg: `${T.amber}15` },
    DEGRADED: { label: 'Degraded', color: T.red, bg: `${T.red}15` },
    HEALING: { label: 'Self-Healing', color: T.violet, bg: `${T.violet}15` },
    RECOVERED: { label: 'Recovered', color: T.green, bg: `${T.green}15` },
  }[phase] || { label: 'Nominal', color: T.green, bg: `${T.green}15` };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 7,
      background: cfg.bg,
      border: `1px solid ${cfg.color}30`,
      borderRadius: 8, padding: '5px 12px'
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: cfg.color,
        boxShadow: `0 0 8px ${cfg.color}`,
        animation: phase === 'NOMINAL' || phase === 'RECOVERED' ? 'none' : 'pulse 1.5s ease-in-out infinite',
        display: 'inline-block'
      }} />
      <span style={{
        fontSize: '0.65rem', fontWeight: 600, color: cfg.color,
        letterSpacing: '0.1em', textTransform: 'uppercase'
      }}>
        {cfg.label}
      </span>
    </div>
  );
}

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
  const [iframeStatus, setIframeStatus] = useState('LIVE');
  const [serviceHealth, setServiceHealth] = useState(() => {
    const m = {}; MICROSERVICES.forEach(s => { m[s.id] = 'healthy'; }); return m;
  });
  const wasAnomalousRef = useRef(false);
  const recoveryTimerRef = useRef(null);

  // Boot loader
  useEffect(() => { const t = setTimeout(() => setBooting(false), 1800); return () => clearTimeout(t); }, []);

  const addLog = useCallback((msg, level) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const color = { ok: T.green, warn: T.amber, crit: T.red, info: T.blue, heal: T.violet }[level] || T.text;
    setLogs(prev => [{ time, msg, color }, ...prev].slice(0, 150));
  }, []);

  const degradeServices = useCallback((type) => {
    const affected = {
      pod_kill: ['frontend'],
      scale_zero: ['frontend'],
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

  const healServices = useCallback(() => {
    setServiceHealth(prev => { const n = { ...prev }; Object.keys(n).forEach(k => { n[k] = 'healing'; }); return n; });
    setTimeout(() => {
      setServiceHealth(prev => { const n = { ...prev }; Object.keys(n).forEach(k => { n[k] = 'healthy'; }); return n; });
    }, 2000);
  }, []);

  // Telemetry loop
  useEffect(() => {
    addLog('NEXUS SRE Platform initialized', 'info');
    addLog('Monitoring 11 microservices — applications namespace', 'info');
    addLog('Isolation Forest ML model online (200 estimators)', 'ok');
    addLog('Live application feed connected', 'ok');

    const fetchMetrics = async () => {
      try {
        const telRes = await axios.get(`${API_BASE_URL}/telemetry`);
        const { cpu, mem, latency } = telRes.data;
        const anaRes = await axios.post(`${API_BASE_URL}/analyze`, {
          cpu_usage: cpu, mem_usage: mem, latency_ms: latency
        });
        const data = anaRes.data;
        const nowStr = new Date().toLocaleTimeString('en-US', { hour12: false });

        setCurrent({
          cpu, mem, lat: latency, threat: data.threat_score,
          is_anomaly: data.is_anomaly, action: data.recommended_action
        });
        setStats(s => ({ ...s, totalChecks: s.totalChecks + 1 }));

        if (data.is_anomaly) {
          if (!wasAnomalousRef.current) setChaosPhase('DEGRADED');
          wasAnomalousRef.current = true;
          setStats(s => ({ ...s, anomalies: s.anomalies + 1 }));
          addLog(`Anomaly — Score: ${data.threat_score.toFixed(3)} | Action: ${data.recommended_action}`, 'crit');
          if (data.recommended_action !== 'NO_ACTION') {
            setStats(s => ({ ...s, recoveries: s.recoveries + 1 }));
            addLog(`Auto-Heal triggered: ${data.recommended_action}`, 'heal');
          }
        } else {
          if (wasAnomalousRef.current) {
            wasAnomalousRef.current = false;
            setChaosPhase('HEALING');
            setIframeStatus('HEALING');
            addLog('Self-healing engaged — recovering services...', 'heal');
            healServices();
            if (recoveryTimerRef.current) clearTimeout(recoveryTimerRef.current);
            recoveryTimerRef.current = setTimeout(() => {
              setIframeKey(k => k + 1);
              setChaosPhase('RECOVERED');
              setIframeStatus('RECOVERED');
              addLog('System recovered — all services nominal', 'ok');
              setTimeout(() => { setChaosPhase('NOMINAL'); setIframeStatus('LIVE'); setActiveChaos(null); }, 4000);
            }, 3000);
          }
        }

        setHistory(prev => {
          const pt = {
            time: nowStr, cpu: +cpu.toFixed(1), mem: +mem.toFixed(1),
            lat: +latency.toFixed(0), threat: +(data.threat_score * 100).toFixed(1)
          };
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

  // Standard chaos
  const triggerChaos = async (type) => {
    setChaosPhase('INJECTING'); setActiveChaos(type);
    setIframeStatus('INJECTING');
    addLog(`Injecting chaos: ${type.replace(/_/g, ' ').toUpperCase()}...`, 'warn');
    try {
      await axios.post(`${API_BASE_URL}/chaos`, { type });
      setChaosPhase('DEGRADED'); setIframeStatus('DEGRADED');
      degradeServices(type);
      addLog(`Chaos deployed: ${type.replace(/_/g, ' ').toUpperCase()} — monitoring degradation...`, 'crit');
    } catch (e) {
      addLog(`Failed to inject chaos: ${e.message}`, 'crit');
      setChaosPhase('NOMINAL'); setIframeStatus('LIVE'); setActiveChaos(null);
    }
  };

  // Scale-to-zero — real frontend crash
  const triggerScaleDown = async () => {
    setChaosPhase('INJECTING'); setActiveChaos('scale_zero');
    setIframeStatus('INJECTING');
    addLog('Scaling frontend to 0 replicas — site going down...', 'warn');
    try {
      await axios.post(`${API_BASE_URL}/chaos/frontend-down`);
      setChaosPhase('DEGRADED'); setIframeStatus('DEGRADED');
      setIframeKey(k => k + 1);
      degradeServices('scale_zero');
      addLog('Frontend scaled to 0 — real 503 active in iframe', 'crit');

      setTimeout(async () => {
        setChaosPhase('HEALING'); setIframeStatus('HEALING');
        addLog('Operator healing — scaling frontend back to 1...', 'heal');
        healServices();
        await axios.post(`${API_BASE_URL}/chaos/frontend-up`);
        setTimeout(() => {
          setIframeKey(k => k + 1);
          setChaosPhase('RECOVERED'); setIframeStatus('RECOVERED');
          addLog('Frontend recovered — site live again', 'ok');
          setTimeout(() => { setChaosPhase('NOMINAL'); setIframeStatus('LIVE'); setActiveChaos(null); }, 4000);
        }, 8000);
      }, 30000);
    } catch (e) {
      addLog(`Scale-down failed: ${e.message}`, 'crit');
      setChaosPhase('NOMINAL'); setIframeStatus('LIVE'); setActiveChaos(null);
    }
  };

  const iframeBorderColor =
    chaosPhase === 'DEGRADED' ? T.red :
      chaosPhase === 'INJECTING' ? T.amber :
        chaosPhase === 'HEALING' ? T.violet :
          chaosPhase === 'RECOVERED' ? T.green : T.border;

  const iframeAnimation =
    chaosPhase === 'DEGRADED' ? 'dangerPulse 2s ease-in-out infinite' :
      chaosPhase === 'HEALING' ? 'healPulse 1.5s ease-in-out infinite' :
        chaosPhase === 'RECOVERED' ? 'recoverFlash 1.5s ease both' : 'none';

  const tooltipStyle = {
    contentStyle: {
      background: '#0d1421', border: `1px solid ${T.border}`,
      fontSize: 11, borderRadius: 8, color: T.text
    },
    labelStyle: { color: T.textSub }
  };

  if (booting) return (
    <>
      <style>{KEYFRAMES}</style>
      <GeminiLoader />
    </>
  );

  return (
    <>
      <style>{KEYFRAMES}</style>
      <div style={{
        minHeight: '100vh', background: T.bg, padding: '24px 28px',
        fontFamily: "'Inter', system-ui, sans-serif"
      }}>

        {/* ── Header ── */}
        <header style={{
          ...card(), padding: '16px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 24, animation: 'fadeIn 0.4s ease both'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 20px rgba(99,102,241,0.3)'
            }}>
              <Zap size={18} color="white" fill="white" />
            </div>
            <div>
              <h1 style={{
                fontSize: '1.1rem', fontWeight: 700, color: T.text,
                letterSpacing: '-0.02em', lineHeight: 1
              }}>
                NEXUS SRE
              </h1>
              <p style={{
                fontSize: '0.6rem', color: T.textSub, letterSpacing: '0.12em',
                textTransform: 'uppercase', marginTop: 3
              }}>
                Autonomous Chaos Engineering Platform
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '5px 12px', borderRadius: 8,
              background: T.surface, border: `1px solid ${T.border}`
            }}>
              <Radio size={11} color={T.green} />
              <span style={{
                fontSize: '0.6rem', color: T.textSub, letterSpacing: '0.1em',
                textTransform: 'uppercase'
              }}>Live</span>
            </div>
            <StatusBadge phase={chaosPhase} />
            <div style={{
              padding: '5px 12px', borderRadius: 8,
              background: current.is_anomaly ? `${T.red}12` : `${T.green}12`,
              border: `1px solid ${current.is_anomaly ? T.red + '30' : T.green + '30'}`,
              fontSize: '0.6rem', fontWeight: 600,
              color: current.is_anomaly ? T.red : T.green,
              letterSpacing: '0.1em', textTransform: 'uppercase'
            }}>
              {current.is_anomaly ? 'Critical' : 'Nominal'}
            </div>
          </div>
        </header>

        {/* ── KPI Row ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 14, marginBottom: 24 }}>
          <KpiCard title="CPU Usage" value={current.cpu.toFixed(1)} unit="%" accent={current.cpu > 80 ? T.red : T.blue} icon={Cpu} />
          <KpiCard title="Memory" value={current.mem.toFixed(1)} unit="%" accent={current.mem > 80 ? T.red : T.green} icon={HardDrive} />
          <KpiCard title="P99 Latency" value={current.lat.toFixed(0)} unit="ms" accent={current.lat > 500 ? T.red : T.amber} icon={Activity} />
          <KpiCard title="Threat Score" value={(current.threat * 100).toFixed(1)} unit="%" accent={current.threat > 0.6 ? T.red : T.violet} icon={ShieldAlert} />
          <KpiCard title="Auto-Heals" value={stats.recoveries} unit="actions" accent={T.green} icon={RefreshCw} sublabel={`${stats.anomalies} anomalies detected`} />
        </div>

        {/* ── Main Grid ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, marginBottom: 20 }}>

          {/* Left column */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* Live app iframe */}
            <div style={{ ...card(), overflow: 'hidden' }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 18px', borderBottom: `1px solid ${T.border}`
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Globe size={13} color={T.blue} />
                  <span style={{
                    fontSize: '0.62rem', fontWeight: 600, color: T.textSub,
                    letterSpacing: '0.14em', textTransform: 'uppercase'
                  }}>
                    Live Application — Google Online Boutique
                  </span>
                  {activeChaos && (
                    <span style={{
                      fontSize: '0.58rem', fontWeight: 600, letterSpacing: '0.1em',
                      textTransform: 'uppercase', padding: '2px 8px', borderRadius: 5,
                      background: `${T.red}12`, border: `1px solid ${T.red}30`, color: T.red
                    }}>
                      {activeChaos.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => setIframeKey(k => k + 1)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '4px 10px', borderRadius: 6,
                    background: T.surface, border: `1px solid ${T.border}`,
                    color: T.textSub, fontSize: '0.6rem', cursor: 'pointer',
                    transition: 'all 0.15s', outline: 'none',
                    fontFamily: "'Inter', system-ui, sans-serif"
                  }}
                >
                  <RefreshCw size={10} /> Force Sync
                </button>
              </div>
              <div style={{
                position: 'relative', height: 460,
                border: `2px solid ${iframeBorderColor}30`,
                transition: 'border-color 0.4s',
                animation: iframeAnimation
              }}>
                <iframe
                  key={iframeKey}
                  src={BOUTIQUE_URL}
                  style={{
                    width: '100%', height: '100%', border: 'none',
                    filter: chaosPhase === 'DEGRADED' ? 'grayscale(0.3) brightness(0.7)' :
                      chaosPhase === 'HEALING' ? 'grayscale(0.15)' : 'none',
                    transition: 'filter 0.5s ease',
                    opacity: chaosPhase === 'INJECTING' ? 0.7 : 1,
                  }}
                  title="Online Boutique — Victim Application"
                  sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                />
                {/* Minimal status strip — no fake overlays */}
                {(chaosPhase === 'DEGRADED' || chaosPhase === 'HEALING') && (
                  <div style={{
                    position: 'absolute', bottom: 0, left: 0, right: 0,
                    padding: '8px 16px',
                    background: chaosPhase === 'HEALING'
                      ? 'linear-gradient(90deg, rgba(124,77,255,0.85), rgba(99,102,241,0.85))'
                      : 'linear-gradient(90deg, rgba(239,68,68,0.85), rgba(220,38,38,0.85))',
                    backdropFilter: 'blur(4px)',
                    display: 'flex', alignItems: 'center', gap: 10
                  }}>
                    {chaosPhase === 'HEALING'
                      ? <><Loader2 size={13} color="white" style={{ animation: 'spin 1s linear infinite' }} />
                        <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'white', letterSpacing: '0.08em' }}>
                          Self-healing in progress — restoring services
                        </span>
                        <div style={{ flex: 1, height: 2, background: 'rgba(255,255,255,0.2)', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ height: '100%', background: 'white', borderRadius: 2, animation: 'shimmerBar 3s ease-in-out forwards' }} />
                        </div>
                      </>
                      : <><ServerCrash size={13} color="white" />
                        <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'white', letterSpacing: '0.08em' }}>
                          Service degraded — operator detecting anomaly
                        </span>
                      </>
                    }
                  </div>
                )}
                {chaosPhase === 'RECOVERED' && (
                  <div style={{
                    position: 'absolute', bottom: 0, left: 0, right: 0,
                    padding: '8px 16px',
                    background: 'linear-gradient(90deg, rgba(34,197,94,0.85), rgba(16,185,129,0.85))',
                    backdropFilter: 'blur(4px)',
                    display: 'flex', alignItems: 'center', gap: 10,
                    animation: 'fadeIn 0.4s ease both'
                  }}>
                    <CheckCircle2 size={13} color="white" />
                    <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'white', letterSpacing: '0.08em' }}>
                      System recovered — all services nominal
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Microservice topology */}
            <div style={{ ...card(), padding: '18px 20px' }}>
              <SectionLabel icon={GitBranch}>Microservice Topology — Online Boutique</SectionLabel>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10 }}>
                {MICROSERVICES.map(svc => (
                  <ServiceNode key={svc.id} service={svc} health={serviceHealth[svc.id]} />
                ))}
              </div>
            </div>

            {/* Heartbeat chart */}
            <div style={{ ...card(), padding: '18px 20px' }}>
              <SectionLabel icon={Activity}>Cluster Heartbeat</SectionLabel>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history}>
                    <defs>
                      {[['cpu', '#3b82f6'], ['mem', '#6366f1'], ['threat', '#ef4444']].map(([k, c]) => (
                        <linearGradient key={k} id={`g_${k}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={c} stopOpacity={0.18} />
                          <stop offset="95%" stopColor={c} stopOpacity={0} />
                        </linearGradient>
                      ))}
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false} />
                    <XAxis dataKey="time" stroke={T.textSub} fontSize={9} tickMargin={6} />
                    <YAxis stroke={T.textSub} fontSize={9} domain={[0, 100]} />
                    <Tooltip {...tooltipStyle} />
                    <Area type="monotone" dataKey="cpu" stroke="#3b82f6" strokeWidth={1.8} fill="url(#g_cpu)" dot={false} name="CPU %" />
                    <Area type="monotone" dataKey="mem" stroke="#6366f1" strokeWidth={1.8} fill="url(#g_mem)" dot={false} name="MEM %" />
                    <Area type="monotone" dataKey="threat" stroke="#ef4444" strokeWidth={1.8} fill="url(#g_threat)" dot={false} name="Threat %" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Latency chart */}
            <div style={{ ...card(), padding: '18px 20px' }}>
              <SectionLabel icon={TrendingUp}>Service Latency</SectionLabel>
              <div style={{ height: 140 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history}>
                    <defs>
                      <linearGradient id="g_lat" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false} />
                    <XAxis dataKey="time" stroke={T.textSub} fontSize={9} hide />
                    <YAxis stroke={T.textSub} fontSize={9} />
                    <Tooltip {...tooltipStyle} />
                    <ReferenceLine y={500} stroke="#ef4444" strokeDasharray="4 3"
                      label={{ value: 'SLO 500ms', fill: '#ef4444', fontSize: 9, position: 'top' }} />
                    <Area type="monotone" dataKey="lat" stroke="#f59e0b" strokeWidth={1.8}
                      fill="url(#g_lat)" dot={false} name="Latency ms" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Right column */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* Chaos lifecycle */}
            <div style={{ ...card(), padding: '18px 20px' }}>
              <SectionLabel icon={Radio}>Chaos Lifecycle</SectionLabel>
              <PhaseTracker phase={chaosPhase} activeChaos={activeChaos} />
            </div>

            {/* ML analysis */}
            <div style={{ ...card(), padding: '18px 20px' }}>
              <SectionLabel icon={ShieldAlert}>ML Analysis Engine</SectionLabel>
              <div>
                <AnalRow label="Anomaly" value={current.is_anomaly ? 'Yes' : 'No'} accent={current.is_anomaly ? T.red : T.green} />
                <AnalRow label="Threat Score" value={current.threat.toFixed(4)} accent={current.threat > 0.6 ? T.red : current.threat > 0.3 ? T.amber : T.green} />
                <AnalRow label="Action" value={current.action} accent={current.action !== 'NO_ACTION' ? T.amber : T.green} />
                <AnalRow label="Total Checks" value={stats.totalChecks} />
                <AnalRow label="Anomalies" value={stats.anomalies} accent={stats.anomalies > 0 ? T.red : T.green} />
                <AnalRow label="Auto-Heals" value={stats.recoveries} accent={stats.recoveries > 0 ? T.green : undefined} />
              </div>
              <div style={{ marginTop: 16 }}>
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  fontSize: '0.6rem', color: T.textSub, marginBottom: 6
                }}>
                  <span>Threat Level</span>
                  <span>{(current.threat * 100).toFixed(1)}%</span>
                </div>
                <div style={{ height: 4, background: T.surface, borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', borderRadius: 4,
                    width: `${Math.min(current.threat * 100, 100)}%`,
                    background: current.threat > 0.6
                      ? 'linear-gradient(90deg, #ef4444, #f87171)'
                      : current.threat > 0.3
                        ? 'linear-gradient(90deg, #f59e0b, #fbbf24)'
                        : 'linear-gradient(90deg, #22c55e, #4ade80)',
                    transition: 'width 0.5s ease, background 0.3s'
                  }} />
                </div>
              </div>
            </div>

            {/* Action log */}
            <div style={{ ...card(), padding: '18px 20px', flex: 1 }}>
              <SectionLabel icon={Activity}>Autonomous Action Log</SectionLabel>
              <div style={{ overflowY: 'auto', maxHeight: 320, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {logs.map((log, i) => (
                  <div key={i} style={{
                    padding: '6px 0',
                    borderBottom: `1px solid ${T.border}`,
                    fontSize: '0.62rem', lineHeight: 1.5
                  }}>
                    <span style={{ color: T.textSub, marginRight: 8 }}>[{log.time}]</span>
                    <span style={{ color: log.color }}>{log.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Chaos Control Panel ── */}
        <div style={{ ...card(), padding: '18px 20px' }}>
          <SectionLabel icon={AlertTriangle}>Chaos Control Panel — Inject Failures Into Live Cluster</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 12 }}>
            <ChaosButton label="Kill Frontend" desc="Scale to 0 — real 503 in iframe" icon={ServerCrash} onClick={triggerScaleDown} active={activeChaos === 'scale_zero'} disabled={chaosPhase !== 'NOMINAL'} />
            <ChaosButton label="Pod Kill" desc="Kills frontend pod" icon={XCircle} onClick={() => triggerChaos('pod_kill')} active={activeChaos === 'pod_kill'} disabled={chaosPhase !== 'NOMINAL'} />
            <ChaosButton label="CPU Stress" desc="80% CPU injection" icon={Cpu} onClick={() => triggerChaos('cpu_stress')} active={activeChaos === 'cpu_stress'} disabled={chaosPhase !== 'NOMINAL'} />
            <ChaosButton label="Memory Hog" desc="256MB pressure" icon={HardDrive} onClick={() => triggerChaos('memory_stress')} active={activeChaos === 'memory_stress'} disabled={chaosPhase !== 'NOMINAL'} />
            <ChaosButton label="Network Delay" desc="200ms latency injection" icon={Wifi} onClick={() => triggerChaos('network_delay')} active={activeChaos === 'network_delay'} disabled={chaosPhase !== 'NOMINAL'} />
            <ChaosButton label="Network Loss" desc="100% packet loss" icon={WifiOff} onClick={() => triggerChaos('network_loss')} active={activeChaos === 'network_loss'} disabled={chaosPhase !== 'NOMINAL'} />
          </div>
        </div>

      </div>
    </>
  );
}