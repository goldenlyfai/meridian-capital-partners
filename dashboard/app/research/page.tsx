"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ChevronDown, ChevronUp, AlertTriangle, CheckCircle } from "lucide-react";

const FACTOR_COLS = ["momentum","quality","value","growth","estimate_revisions","short_interest","insider_activity","institutional_flow","composite"];
const FACTOR_LABELS = ["MOM","QUAL","VAL","GRWTH","EST","SI","INSDR","INST","COMP"];

function ScoreBar({ value }: { value: number }) {
  // value is 0–100 percentile
  const pct = Math.max(0, Math.min(100, value));
  const color = pct > 65 ? "#10b981" : pct < 35 ? "#f43f5e" : "#6366f1";
  return (
    <div style={{ background: "#1e2a45", borderRadius: 4, height: 6, width: "100%" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.4s" }} />
    </div>
  );
}

function HeatCell({ value }: { value: number }) {
  const v = value ?? 50;
  // centre on 50: positive = above neutral, negative = below
  const delta = (v - 50) / 50;
  const bg = delta > 0
    ? `rgba(16,185,129,${Math.min(0.8, Math.abs(delta))})`
    : `rgba(244,63,94,${Math.min(0.8, Math.abs(delta))})`;
  return (
    <td style={{ background: bg, textAlign: "center", padding: "5px 6px", fontSize: 11, color: "#e2e8f0", fontFamily: "monospace", border: "1px solid #0b0e1766" }}>
      {v.toFixed(0)}
    </td>
  );
}

function CandidateCard({ c, onApprove }: { c: any; onApprove: (ticker: string, action: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const isLong = c.signal === "LONG";

  async function handleExpand() {
    const next = !expanded;
    setExpanded(next);
    if (next && !analysis) {
      setLoadingAnalysis(true);
      try {
        const res = await api.research.analysis(c.ticker);
        setAnalysis(res.analysis ?? res.text ?? JSON.stringify(res));
      } catch {
        setAnalysis("Analysis unavailable — run backend research layer first.");
      } finally {
        setLoadingAnalysis(false);
      }
    }
  }

  return (
    <div className="card" style={{ borderLeft: `3px solid ${isLong ? "var(--long)" : "var(--short)"}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.5px" }}>{c.ticker}</span>
            <span className={isLong ? "badge-long" : "badge-short"}>{c.signal}</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{c.company_name ?? "—"} · {c.sector ?? "—"}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: isLong ? "var(--long)" : "var(--short)", marginBottom: 8 }}>
            {(c.composite ?? 0).toFixed(1)}
            <span style={{ fontSize: 11, fontWeight: 400, color: "var(--muted)", marginLeft: 4 }}>/ 100</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {[["MOM", c.momentum], ["QUAL", c.quality], ["VAL", c.value]].map(([lbl, val]) => (
              <div key={lbl as string}>
                <div style={{ fontSize: 9, color: "var(--muted)", marginBottom: 2 }}>{lbl}</div>
                <ScoreBar value={Number(val) || 50} />
                <div style={{ fontSize: 10, color: "var(--text)", marginTop: 2 }}>{(Number(val) || 50).toFixed(0)}</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
          <button
            onClick={() => onApprove(c.ticker, c.signal)}
            style={{ background: isLong ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)", color: isLong ? "var(--long)" : "var(--short)", border: `1px solid ${isLong ? "var(--long)" : "var(--short)"}`, borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
            Approve
          </button>
          <button
            onClick={handleExpand}
            style={{ background: "transparent", color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />} AI
          </button>
        </div>
      </div>
      {expanded && (
        <div style={{ marginTop: 12, padding: 12, background: "#0b0e1780", borderRadius: 8, fontSize: 12, lineHeight: 1.7, color: "var(--text)", whiteSpace: "pre-wrap" }}>
          {loadingAnalysis ? <span style={{ color: "#6366f1", fontStyle: "italic" }}>JARVIS analyzing {c.ticker}…</span> : analysis}
        </div>
      )}
    </div>
  );
}

export default function ResearchPage() {
  const [longs, setLongs] = useState<any[]>([]);
  const [shorts, setShorts] = useState<any[]>([]);
  const [crowding, setCrowding] = useState<any>(null);
  const [vix, setVix] = useState<any>(null);
  const [approveMsg, setApproveMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.research.candidates(60),
      api.research.crowding(),
      api.research.vix(),
    ])
      .then(([cands, crowd, v]) => {
        setLongs(cands.longs ?? []);
        setShorts(cands.shorts ?? []);
        setCrowding(crowd);
        setVix(v);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function handleApprove(ticker: string, action: string) {
    try {
      await api.execution.approve(ticker, action);
      setApproveMsg(`${ticker} (${action}) approved for execution`);
      setTimeout(() => setApproveMsg(null), 4000);
    } catch {
      setApproveMsg(`Failed to approve ${ticker} — check backend`);
      setTimeout(() => setApproveMsg(null), 4000);
    }
  }

  if (loading) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>Loading research data…</div>;
  if (error) return <div style={{ color: "var(--short)", padding: 48, fontSize: 14 }}>Error: {error}</div>;

  const heatmap = [...longs.slice(0, 30), ...shorts.slice(0, 30)];
  const alerts: any[] = crowding?.alerts ?? [];
  const vixLevel: number = vix?.vix ?? 0;
  const regime: string = vix?.regime ?? "unknown";
  const factorWeights: Record<string, number> = vix?.weights ?? {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-0.5px" }}>Research Candidates</h1>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>{longs.length + shorts.length} candidates · {longs.length} long · {shorts.length} short</div>
        </div>
      </div>

      {approveMsg && (
        <div style={{ background: "#10b98122", border: "1px solid var(--long)", borderRadius: 8, padding: "10px 16px", color: "var(--long)", fontSize: 13, fontWeight: 600 }}>
          {approveMsg}
        </div>
      )}

      {alerts.length > 0 && (
        <div style={{ background: "#f43f5e15", border: "1px solid var(--short)", borderRadius: 10, padding: "12px 16px", display: "flex", alignItems: "flex-start", gap: 10 }}>
          <AlertTriangle size={16} color="var(--short)" style={{ marginTop: 2, flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--short)", marginBottom: 6, letterSpacing: "0.05em" }}>CROWDING WARNINGS</div>
            {alerts.map((a: any, i: number) => (
              <div key={i} style={{ fontSize: 12, color: "#fca5a5", lineHeight: 1.8 }}>
                [{a.severity}] {a.factor_pair}: corr={a.actual_corr?.toFixed(2)} (baseline={a.baseline_corr?.toFixed(2)})
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ padding: "14px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.08em" }}>VIX REGIME</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: vixLevel > 25 ? "var(--short)" : vixLevel < 15 ? "var(--long)" : "#6366f1", marginTop: 2 }}>
              {vixLevel.toFixed(1)} · {regime.replace(/_/g, " ").toUpperCase()}
            </div>
          </div>
          {Object.keys(factorWeights).length > 0 && (
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {Object.entries(factorWeights).map(([f, w]) => (
                <div key={f} style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 10, color: "var(--muted)" }}>{f.toUpperCase().slice(0, 4)}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>{((w as number) * 100).toFixed(0)}%</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--long)", letterSpacing: "0.1em", marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <CheckCircle size={14} /> TOP 10 LONG
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {longs.length === 0
              ? <div style={{ color: "var(--muted)", fontSize: 13 }}>No long candidates available.</div>
              : longs.slice(0, 10).map((c: any) => <CandidateCard key={c.ticker} c={c} onApprove={handleApprove} />)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--short)", letterSpacing: "0.1em", marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <CheckCircle size={14} /> TOP 10 SHORT
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {shorts.length === 0
              ? <div style={{ color: "var(--muted)", fontSize: 13 }}>No short candidates available.</div>
              : shorts.slice(0, 10).map((c: any) => <CandidateCard key={c.ticker} c={c} onApprove={handleApprove} />)}
          </div>
        </div>
      </div>

      {heatmap.length > 0 && (
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>FACTOR HEATMAP — TOP 30 LONG / BOTTOM 30 SHORT</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>Ticker</th>
                  <th style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "center", fontWeight: 600 }}>Signal</th>
                  {FACTOR_LABELS.map(f => <th key={f} style={{ color: "var(--muted)", padding: "5px 6px", textAlign: "center", fontWeight: 600, fontSize: 10 }}>{f}</th>)}
                </tr>
              </thead>
              <tbody>
                {heatmap.map((c: any) => (
                  <tr key={c.ticker}>
                    <td style={{ padding: "5px 8px", fontWeight: 700, whiteSpace: "nowrap", color: "var(--text)" }}>{c.ticker}</td>
                    <td style={{ padding: "5px 8px", textAlign: "center" }}>
                      <span className={c.signal === "LONG" ? "badge-long" : "badge-short"}>{c.signal}</span>
                    </td>
                    {FACTOR_COLS.map(col => <HeatCell key={col} value={c[col] ?? 50} />)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
