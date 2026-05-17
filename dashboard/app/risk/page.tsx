"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import MetricCard from "@/components/MetricCard";
import { AlertTriangle, ShieldCheck, ShieldX } from "lucide-react";

const FACTORS = ["Momentum","Quality","Value","Growth","Liquidity","Leverage","Beta","Size"];

function ProgressBar({ value, limit, label, sublabel }: { value: number; limit: number; label: string; sublabel: string }) {
  const pct = Math.min(100, Math.abs(value / limit) * 100);
  const color = pct > 85 ? "#f43f5e" : pct > 60 ? "#f59e0b" : "#10b981";
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>{label}</span>
        <span style={{ fontSize: 12, fontFamily: "monospace", color }}>
          {(value * 100).toFixed(2)}% / {(limit * 100).toFixed(1)}%
        </span>
      </div>
      <div style={{ background: "#1e2a45", borderRadius: 6, height: 10 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 6, transition: "width 0.4s" }} />
      </div>
      <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 3 }}>{sublabel}</div>
    </div>
  );
}

function FactorBar({ factor, exposure }: { factor: string; exposure: number }) {
  const isPos = exposure >= 0;
  const pct = Math.min(100, Math.abs(exposure) * 100);
  const color = isPos ? "#6366f1" : "#f43f5e";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <div style={{ width: 80, fontSize: 11, color: "var(--muted)", textAlign: "right", flexShrink: 0 }}>{factor}</div>
      <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
        {!isPos && <div style={{ flex: `0 0 ${pct}%`, height: 8, background: color, borderRadius: "4px 0 0 4px" }} />}
        <div style={{ width: 2, height: 12, background: "#1e2a45", flexShrink: 0 }} />
        {isPos && <div style={{ flex: `0 0 ${pct}%`, height: 8, background: color, borderRadius: "0 4px 4px 0" }} />}
      </div>
      <div style={{ width: 52, fontSize: 11, fontFamily: "monospace", color, flexShrink: 0 }}>
        {isPos ? "+" : ""}{exposure.toFixed(3)}
      </div>
    </div>
  );
}

export default function RiskPage() {
  const [riskState, setRiskState] = useState<any>(null);
  const [stressTests, setStressTests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.risk.state().then(setRiskState),
      api.risk.stressTests().then((d) => setStressTests(d.scenarios ?? d ?? [])),
    ]).catch(() => setError(true)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>Loading risk data…</div>;
  if (error || !riskState) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>No data available — run backend layers first.</div>;

  const cb = riskState.circuit_breakers ?? {};
  const tail = riskState.tail_risk ?? {};
  const decomp = riskState.variance_decomposition ?? {};
  const mctr: any[] = riskState.mctr ?? [];
  const factorExp: Record<string, number> = riskState.factor_exposures ?? {};
  const alerts: any[] = riskState.alert_log ?? riskState.alerts ?? [];
  const haltLocked: boolean = riskState.halt_locked ?? false;
  const effectiveBets: number = riskState.effective_bets ?? 0;
  const activeAlerts: number = riskState.active_alerts ?? alerts.filter((a: any) => !a.resolved).length;

  const dailyPnl = cb.daily_pnl ?? 0;
  const weeklyPnl = cb.weekly_pnl ?? 0;
  const drawdown = cb.drawdown ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-0.5px" }}>Risk Monitor</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {haltLocked ? (
            <div style={{ background: "#f43f5e22", border: "1px solid var(--short)", borderRadius: 8, padding: "8px 18px", display: "flex", alignItems: "center", gap: 8 }}>
              <ShieldX size={16} color="var(--short)" />
              <span style={{ fontSize: 13, fontWeight: 800, color: "var(--short)", letterSpacing: "0.08em" }}>HALT LOCK ACTIVE</span>
            </div>
          ) : (
            <div style={{ background: "#10b98122", border: "1px solid var(--long)", borderRadius: 8, padding: "8px 18px", display: "flex", alignItems: "center", gap: 8 }}>
              <ShieldCheck size={16} color="var(--long)" />
              <span style={{ fontSize: 13, fontWeight: 800, color: "var(--long)", letterSpacing: "0.08em" }}>CLEAR</span>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <MetricCard label="VIX" value={tail.vix?.toFixed(1) ?? "—"} color={tail.vix > 25 ? "var(--short)" : "var(--long)"} />
        <MetricCard label="Credit Spread Z" value={tail.credit_spread_z?.toFixed(2) ?? "—"} color={Math.abs(tail.credit_spread_z ?? 0) > 2 ? "var(--short)" : "var(--text)"} />
        <MetricCard label="Active Alerts" value={activeAlerts} color={activeAlerts > 0 ? "var(--short)" : "var(--long)"} />
        <MetricCard label="Effective Bets" value={effectiveBets.toFixed(1)} sub="Bai-Perron" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 16 }}>CIRCUIT BREAKERS</div>
          <ProgressBar value={Math.abs(dailyPnl)} limit={0.025} label="Daily P&L" sublabel="Limit: 2.5% NAV" />
          <ProgressBar value={Math.abs(weeklyPnl)} limit={0.04} label="Weekly P&L" sublabel="Limit: 4% NAV" />
          <ProgressBar value={Math.abs(drawdown)} limit={0.08} label="Max Drawdown" sublabel="Limit: 8% NAV" />
        </div>

        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 16 }}>VARIANCE DECOMPOSITION</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 44, fontWeight: 900, color: "#6366f1", letterSpacing: "-2px" }}>
                {((decomp.factor_pct ?? 0) * 100).toFixed(0)}%
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>FACTOR VARIANCE</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 44, fontWeight: 900, color: "#a78bfa", letterSpacing: "-2px" }}>
                {((decomp.specific_pct ?? 0) * 100).toFixed(0)}%
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>SPECIFIC VARIANCE</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>FACTOR EXPOSURES</div>
        {FACTORS.map((f) => (
          <FactorBar key={f} factor={f} exposure={factorExp[f.toLowerCase()] ?? factorExp[f] ?? 0} />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>MCTR — TOP 10 POSITIONS</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Ticker", "Signal", "MCTR %", "Weight %", "Flag"].map(h => (
                  <th key={h} style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "left", fontSize: 10, fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {mctr.slice(0, 10).map((m: any) => (
                <tr key={m.ticker} style={{ borderBottom: "1px solid #1e2a4533" }}>
                  <td style={{ padding: "7px 8px", fontWeight: 700 }}>{m.ticker}</td>
                  <td style={{ padding: "7px 8px" }}><span className={m.signal === "LONG" ? "badge-long" : "badge-short"}>{m.signal}</span></td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace", color: "#a78bfa" }}>{((m.mctr ?? 0) * 100).toFixed(2)}%</td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace" }}>{((m.weight ?? 0) * 100).toFixed(2)}%</td>
                  <td style={{ padding: "7px 8px" }}>{m.disproportionate && <span style={{ fontSize: 10, color: "var(--short)", fontWeight: 700 }}>⚠ DISPROPORTIONATE</span>}</td>
                </tr>
              ))}
              {mctr.length === 0 && <tr><td colSpan={5} style={{ padding: "12px 8px", color: "var(--muted)", fontSize: 12 }}>No MCTR data available.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>STRESS TESTS</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Scenario", "Type", "Return", "P&L"].map(h => (
                  <th key={h} style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "left", fontSize: 10, fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stressTests.slice(0, 6).map((s: any, i: number) => (
                <tr key={i} style={{ borderBottom: "1px solid #1e2a4533" }}>
                  <td style={{ padding: "7px 8px", fontWeight: 600, fontSize: 11 }}>{s.scenario ?? s.name}</td>
                  <td style={{ padding: "7px 8px" }}><span className="badge-neutral">{s.type ?? "HIST"}</span></td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace", color: (s.return_pct ?? s.return ?? 0) >= 0 ? "var(--long)" : "var(--short)" }}>
                    {((s.return_pct ?? s.return ?? 0) * 100).toFixed(2)}%
                  </td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace", color: (s.pnl ?? 0) >= 0 ? "var(--long)" : "var(--short)" }}>
                    {(s.pnl ?? 0) >= 0 ? "+" : ""}${Number(s.pnl ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}
                  </td>
                </tr>
              ))}
              {stressTests.length === 0 && <tr><td colSpan={4} style={{ padding: "12px 8px", color: "var(--muted)", fontSize: 12 }}>No stress test data available.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
          <AlertTriangle size={13} /> ALERT LOG — LAST 10
        </div>
        {alerts.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>No alerts on record.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {alerts.slice(-10).reverse().map((a: any, i: number) => (
              <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "8px 10px", background: "#0b0e1760", borderRadius: 6, borderLeft: `3px solid ${a.severity === "critical" ? "var(--short)" : a.severity === "warning" ? "#f59e0b" : "#6366f1"}` }}>
                <div style={{ fontSize: 10, color: "var(--muted)", whiteSpace: "nowrap", marginTop: 1 }}>{a.timestamp ? new Date(a.timestamp).toLocaleString() : "—"}</div>
                <div style={{ flex: 1, fontSize: 12, color: "var(--text)" }}>{a.message ?? JSON.stringify(a)}</div>
                {a.resolved && <span style={{ fontSize: 10, color: "var(--long)", fontWeight: 700, whiteSpace: "nowrap" }}>RESOLVED</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
