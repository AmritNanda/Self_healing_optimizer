import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { Activity, Cpu, HardDrive, AlertOctagon, ShieldAlert, Zap, ServerCrash, PowerOff, Network } from 'lucide-react';

const API_BASE_URL = 'http://localhost:8080/api/v1';
const REFRESH_INTERVAL_MS = 2000;

export default function App() {
  const [history, setHistory] = useState([]);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState({ anomalies: 0, recoveries: 0 });
  
  const [current, setCurrent] = useState({
    cpu: 0, mem: 0, lat: 0, threat: 0, is_anomaly: false, action: 'NO_ACTION'
  });

  // Keep track of time for the X-axis
  const timeRef = useRef(new Date());

  // 1. The Core Telemetry Engine
  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        // 1. Fetch REAL telemetry from your new API_BASE_URL
        const telResponse = await axios.get(`${API_BASE_URL}/telemetry`);
        const { cpu, mem, latency } = telResponse.data;

        // 2. Call ML Analysis bridge
        const analysisResponse = await axios.post(`${API_BASE_URL}/analyze`, {
          cpu_usage: cpu, 
          mem_usage: mem, 
          latency_ms: latency
        });

        const data = analysisResponse.data;
        const nowStr = new Date().toLocaleTimeString('en-US', { hour12: false });
        
        setCurrent({
          cpu: cpu, 
          mem: mem, 
          lat: latency,
          threat: data.threat_score, 
          is_anomaly: data.is_anomaly, 
          action: data.recommended_action
        });

        // Update Charts
        setHistory(prev => {
          const newPoint = { 
            time: nowStr, 
            cpu: Number(cpu.toFixed(1)), 
            mem: Number(mem.toFixed(1)), 
            lat: Number(latency.toFixed(0)), 
            threat: Number((data.threat_score * 100).toFixed(1)) 
          };
          const updated = [...prev, newPoint];
          return updated.length > 60 ? updated.slice(-60) : updated;
        });

        // Handle Anomaly Stats
        if (data.is_anomaly) {
          setStats(s => ({ ...s, anomalies: s.anomalies + 1 }));
          addLog(`🚨 ANOMALY DETECTED — Score: ${data.threat_score.toFixed(3)} | Action: ${data.recommended_action}`, 'crit');
          
          if (data.recommended_action !== 'NO_ACTION' && data.recommended_action !== 'NO_ACTION') {
             setStats(s => ({ ...s, recoveries: s.recoveries + 1 }));
             addLog(`✅ Executing Recovery: ${data.recommended_action}`, 'ok');
          }
        }

      } catch (error) {
        console.error("Dashboard error:", error);
        addLog("⚠️ API Connectivity Lost. Check backend status.", "warn");
      }
    };

    // Initial log
    addLog("Platform initialised — monitoring 11 microservices", "info");
    addLog("Isolation Forest model online (200 estimators)", "ok");

    const interval = setInterval(fetchMetrics, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  const addLog = (msg, level) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const colors = { ok: 'text-sre-green', warn: 'text-sre-amber', crit: 'text-sre-red', info: 'text-sre-cyan' };
    setLogs(prev => [{ time, msg, color: colors[level] || 'text-slate-300' }, ...prev].slice(0, 100));
  };

  const triggerChaos = async (type) => {
    addLog(`☢️ INJECTING CHAOS: ${type.toUpperCase()}...`, 'warn');
    try {
      await axios.post(`${API_BASE_URL}/chaos`, { type: type });
      addLog(`🔥 CHAOS DEPLOYED: ${type.toUpperCase()}`, 'crit');
    } catch (e) {
      addLog(`❌ FAILED to inject chaos: ${e.message}`, 'crit');
    }
  };

  return (
    <div className="min-h-screen bg-sre-bg p-6 lg:p-10 font-mono">
      
      {/* --- Header --- */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center bg-sre-card border border-sre-border rounded-2xl p-6 mb-8 shadow-[0_0_40px_rgba(0,229,255,0.06)]">
        <div>
          <h1 className="text-3xl font-display font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-sre-cyan to-sre-purple flex items-center gap-3">
            <Zap className="text-sre-cyan" fill="currentColor" /> NEXUS SRE
          </h1>
          <p className="text-slate-500 text-xs tracking-[0.15em] uppercase mt-2">Autonomous Chaos Engineering & Self-Healing</p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs tracking-widest text-slate-400">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sre-green opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-sre-green"></span>
            </span>
            LIVE
          </div>
          <div className={`px-4 py-1.5 rounded-md text-xs font-bold tracking-widest uppercase border ${current.is_anomaly ? 'bg-sre-red/10 border-sre-red/30 text-sre-red' : 'bg-sre-green/10 border-sre-green/30 text-sre-green'}`}>
            {current.is_anomaly ? 'CRITICAL' : 'NOMINAL'}
          </div>
        </div>
      </header>

      {/* --- Top KPIs --- */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <KpiCard title="CPU Usage" value={current.cpu.toFixed(1)} unit="%" color={current.cpu > 80 ? 'sre-red' : 'sre-cyan'} icon={<Cpu />} />
        <KpiCard title="Memory Usage" value={current.mem.toFixed(1)} unit="%" color={current.mem > 80 ? 'sre-red' : 'sre-green'} icon={<HardDrive />} />
        <KpiCard title="P99 Latency" value={current.lat.toFixed(0)} unit="ms" color={current.lat > 500 ? 'sre-red' : 'sre-amber'} icon={<Activity />} />
        <KpiCard title="Auto-Recoveries" value={stats.recoveries} unit="actions" color="sre-green" icon={<ShieldAlert />} />
      </div>

      {/* --- Main Dashboard Grid --- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8">
        
        {/* Left Column: Charts */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          
          {/* Heartbeat Chart */}
          <div className="bg-sre-card border border-sre-border rounded-xl p-6">
            <h2 className="text-xs font-display tracking-[0.18em] uppercase text-slate-500 border-b border-sre-border pb-2 mb-4">📡 Cluster Heartbeat</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickMargin={10} />
                  <YAxis stroke="#64748b" fontSize={10} domain={[0, 100]} />
                  <Tooltip contentStyle={{ backgroundColor: '#0d1421', borderColor: '#1e2d45', fontSize: '12px' }} />
                  <Line type="monotone" dataKey="cpu" stroke="#00e5ff" strokeWidth={2} dot={false} name="CPU %" />
                  <Line type="monotone" dataKey="mem" stroke="#7c4dff" strokeWidth={2} dot={false} name="MEM %" />
                  <Line type="monotone" dataKey="threat" stroke="#ff3d5a" strokeWidth={2} dot={false} name="Threat Level" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Latency Chart */}
          <div className="bg-sre-card border border-sre-border rounded-xl p-6">
            <h2 className="text-xs font-display tracking-[0.18em] uppercase text-slate-500 border-b border-sre-border pb-2 mb-4">⏱ Service Latency</h2>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} hide />
                  <YAxis stroke="#64748b" fontSize={10} />
                  <Tooltip contentStyle={{ backgroundColor: '#0d1421', borderColor: '#1e2d45', fontSize: '12px' }} />
                  <ReferenceLine y={500} label={{ position: 'top', value: 'SLO Threshold', fill: '#ff3d5a', fontSize: 10 }} stroke="#ff3d5a" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="lat" stroke="#ffab00" strokeWidth={2} dot={false} name="Latency (ms)" fill="rgba(255,171,0,0.1)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Right Column: AI Analysis & Logs */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          
          {/* Last Analysis Box */}
          <div className="bg-sre-card border border-sre-border rounded-xl p-6">
            <h2 className="text-xs font-display tracking-[0.18em] uppercase text-slate-500 border-b border-sre-border pb-2 mb-4">🔬 Last ML Analysis</h2>
            <div className="space-y-4 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">ANOMALY</span>
                <span className={`font-bold ${current.is_anomaly ? 'text-sre-red' : 'text-sre-green'}`}>{current.is_anomaly ? 'YES' : 'NO'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">SCORE</span>
                <span className="font-bold text-slate-200">{current.threat.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">ACTION</span>
                <span className={`font-bold ${current.action !== 'NO_ACTION' ? 'text-sre-red' : 'text-sre-green'}`}>{current.action}</span>
              </div>
            </div>
          </div>

          {/* Action Log */}
          <div className="bg-sre-card border border-sre-border rounded-xl p-6 flex-1 flex flex-col h-[400px]">
             <h2 className="text-xs font-display tracking-[0.18em] uppercase text-slate-500 border-b border-sre-border pb-2 mb-4">🤖 Autonomous Action Log</h2>
             <div className="overflow-y-auto flex-1 space-y-2 text-xs">
                {logs.map((log, i) => (
                  <div key={i} className="border-b border-sre-border/50 pb-2">
                    <span className="text-slate-600 mr-2">[{log.time}]</span>
                    <span className={`${log.color}`}>{log.msg}</span>
                  </div>
                ))}
             </div>
          </div>
        </div>
      </div>

      {/* --- Chaos Control Panel --- */}
      <div className="bg-sre-card border border-sre-border rounded-xl p-6">
        <h2 className="text-xs font-display tracking-[0.18em] uppercase text-slate-500 border-b border-sre-border pb-4 mb-4 flex items-center gap-2">
          <AlertOctagon className="text-sre-amber" size={16} /> Chaos Control Panel
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <ChaosButton label="💀 Pod Kill" desc="Kills frontend pod" onClick={() => triggerChaos('pod_kill')} />
          <ChaosButton label="🔥 CPU Stress" desc="80% CPU injection" onClick={() => triggerChaos('cpu_stress')} />
          <ChaosButton label="🧠 Memory Hog" desc="256MB pressure" onClick={() => triggerChaos('memory_stress')} />
          <ChaosButton label="🌐 Net Delay" desc="200ms latency" onClick={() => triggerChaos('network_delay')} />
          <ChaosButton label="📡 Net Loss" desc="100% packet loss" onClick={() => triggerChaos('network_loss')} />
        </div>
      </div>
    </div>
  );
}

// Reusable Components
function KpiCard({ title, value, unit, color, icon }) {
  // Map our custom string colors to actual tailwind classes for the top border and text
  const colorMap = {
    'sre-cyan': 'border-t-[#00e5ff] text-[#00e5ff]',
    'sre-red': 'border-t-[#ff3d5a] text-[#ff3d5a]',
    'sre-green': 'border-t-[#00e676] text-[#00e676]',
    'sre-amber': 'border-t-[#ffab00] text-[#ffab00]',
  };
  
  const styling = colorMap[color] || 'border-t-slate-500 text-slate-200';

  return (
    <div className={`bg-sre-card border border-sre-border border-t-2 rounded-xl p-5 relative overflow-hidden ${styling.split(' ')[0]}`}>
      <div className="flex justify-between items-start mb-2">
        <span className="text-[0.65rem] tracking-[0.12em] uppercase text-slate-500">{title}</span>
        <div className="text-slate-600 opacity-50">{icon}</div>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`font-display text-4xl font-bold ${styling.split(' ')[1]}`}>{value}</span>
        <span className="text-[0.65rem] text-slate-500">{unit}</span>
      </div>
    </div>
  );
}

function ChaosButton({ label, desc, onClick }) {
  return (
    <button 
      onClick={onClick}
      className="flex flex-col text-left bg-[#111827] border border-sre-border hover:border-sre-amber hover:shadow-[0_0_15px_rgba(255,171,0,0.15)] transition-all duration-300 rounded-lg p-3 group"
    >
      <span className="font-bold text-slate-200 group-hover:text-sre-amber text-sm mb-1">{label}</span>
      <span className="text-[0.6rem] text-slate-500">{desc}</span>
    </button>
  );
}