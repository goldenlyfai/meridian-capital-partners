"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import MetricCard from "@/components/MetricCard";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, Cell, ReferenceLine,
} from "recharts";

const ATTR_COLORS: Record<string, string> = { Beta: "#6366f1", Sector: "#a78bfa", Factor: "#818cf8", Alpha: "#10b981" };

function MonthGrid({ data }: { data: Record<string, Record<string, number>> }) {
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const years = Object.keys(data).sort();
  if (!years.length) return <div style={{ color: "var(--muted)", fontSize: 12 }}>No monthly data available.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
        <thead>
          <tr>
            <th style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "left" }}>Year</th>
            {months.map(m => <th key={m} style={{ color: "var(--muted)", padding: "5px 6px", textAlign: "center", minWidth: 52 }}>{m}</th>)}
            <th style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "center" }}>YTD</th>
          </tr>
        </thead>
        <tbody>
          {years.map(yr => {
            const row = data[yr] ?? {};
            const vals = Object.values(row).filter((v): v is number => typeof v === "number");
            const ytd = vals.reduce((a, b) => a + b, 0);
            return (
              <tr key={yr}>
                <td style={{ padding: "5px 8px", fontWeight: 700 }}>{yr}</td>
                {months.map((m) => {
                  const v = row[m] ?? row[m.toLowerCase()];
                  const pct = typeof v === "number" ? v * 100 : null;
                  const bg = pct == null ? "transparent" : pct >= 0 ? `rgba(16,185,129,${Math.min(0.6, Math.abs(pct) / 5)})` : `rgba(244,63,94,${Math.min(0.6, Math.abs(pct) / 5)})`;
                  return (
                    <td key={m} style={{ padding: "5px 6px", textAlign: "center", background: bg, borderRadius: 4, color: pct == null ? "var(--muted)" : pct >= 0 ? "var(--long)" : "var(--short)", fontFamily: "monospace" }}>
                      {pct == null ? "—" : `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`}
                    </td>
                  );
                })}
                <td style={{ padding: "5px 8px", textAlign: "center", fontWeight: 700, fontFamily: "monospace", color: ytd >= 0 ? "var(--long)" : "var(--short)" }}>
                  {ytd >= 0 ? "+" : ""}{(ytd * 100).toFixed(1)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function PerformancePage() {
  const [attribution, setAttribution] = useState<any>(null);
  const [equityCurve, setEquityCurve] = useState<any[]>([]);
  const [commentary, setCommentary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.performance.attribution(90).then((d) => setAttribution(d.attribution ?? d)),
      api.performance.equityCurve().then((d) => {
        // API returns {fund: [{date, value}], spy: [{date, value}]} — merge by date
        const fundArr: any[] = d.fund ?? [];
        const spyArr: any[] = d.spy ?? [];
        if (fundArr.length === 0 && spyArr.length === 0) { setEquityCurve([]); return; }
        const byDate: Record<string, any> = {};
        fundArr.forEach((p: any) => { byDate[p.date] = { date: p.date, fund: p.value }; });
        spyArr.forEach((p: any) => {
          if (byDate[p.date]) byDate[p.date].spy = p.value;
          else byDate[p.date] = { date: p.date, spy: p.value };
        });
        setEquityCurve(Object.values(byDate).sort((a, b) => String(a.date).localeCompare(String(b.date))));
      }),
      api.letter.weeklyCommentary().then(setCommentary).catch(() => {}),
    ]).catch(() => setError(true)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>Loading performance data…</div>;
  if (error) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>No data available — run backend layers first.</div>;

  const summary = attribution.summary ?? {};
  const sectorAlpha: any[] = attribution.sector_alpha ?? [];
  const bestWorst = attribution.best_worst ?? {};
  const best5: any[] = bestWorst.best ?? [];
  const worst5: any[] = bestWorst.worst ?? [];
  const monthlyReturns: Record<string, Record<string, number>> = attribution.monthly_returns ?? {};
  const turnover = attribution.turnover ?? {};
  const winStats = attribution.win_stats ?? {};

  const attrBars = [
    { name: "Beta", value: Number(summary.beta_return ?? 0) },
    { name: "Sector", value: Number(summary.sector_return ?? 0) },
    { name: "Factor", value: Number(summary.factor_return ?? 0) },
    { name: "Alpha", value: Number(summary.alpha ?? summary.alpha_return ?? 0) },
  ];

  const sharpeSeries: any[] = (attribution.rolling_sharpe ?? []).map((v: any, i: number) => ({ i, sharpe: typeof v === "number" ? v : v.sharpe }));
  const rollingSharpeLast: number = sharpeSeries.length > 0 ? (sharpeSeries[sharpeSeries.length - 1]?.sharpe ?? 0) : (summary.sharpe ?? 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-0.5px" }}>Performance Attribution</h1>
        <div style={{ fontSize: 12, color: "var(--muted)" }}>90-day window</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
        <MetricCard label="Total Return" value={`${(Number(summary.total_return ?? 0) * 100).toFixed(2)}%`} color={Number(summary.total_return ?? 0) >= 0 ? "var(--long)" : "var(--short)"} />
        <MetricCard label="Alpha" value={`${(Number(summary.alpha ?? 0) * 100).toFixed(2)}%`} color="var(--long)" />
        <MetricCard label="Sharpe (Rolling)" value={rollingSharpeLast.toFixed(2)} />
        <MetricCard label="Win Rate" value={`${(Number(winStats.win_rate ?? 0) * 100).toFixed(1)}%`} color={Number(winStats.win_rate ?? 0) > 0.5 ? "var(--long)" : "var(--short)"} />
        <MetricCard label="30d Turnover" value={`${(Number(turnover.turnover_30d ?? 0) * 100).toFixed(1)}%`} sub={`Budget: ${(Number(turnover.budget ?? 0.3) * 100).toFixed(0)}%`} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24 }}>
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>EQUITY CURVE — FUND vs SPY (rebased 100)</div>
          {equityCurve.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 12 }}>No equity curve data available.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={equityCurve} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={false} width={42} />
                <Tooltip contentStyle={{ background: "#131827", border: "1px solid #1e2a45", borderRadius: 8, fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="fund" stroke="#6366f1" strokeWidth={2} dot={false} name="Fund" />
                <Line type="monotone" dataKey="spy" stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="SPY" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>P&L ATTRIBUTION</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={attrBars} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={false} width={36} tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} />
              <Tooltip formatter={(v) => typeof v === "number" ? `${(v * 100).toFixed(2)}%` : v} contentStyle={{ background: "#131827", border: "1px solid #1e2a45", borderRadius: 8, fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#1e2a45" />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {attrBars.map((b) => <Cell key={b.name} fill={ATTR_COLORS[b.name] ?? "#6366f1"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 6 }}>WIN / LOSS STATS</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: 12 }}>
              <div><div style={{ color: "var(--muted)", fontSize: 10 }}>Win Rate</div><div style={{ fontWeight: 700, color: "var(--long)" }}>{(Number(winStats.win_rate ?? 0) * 100).toFixed(1)}%</div></div>
              <div><div style={{ color: "var(--muted)", fontSize: 10 }}>Avg Win</div><div style={{ fontWeight: 700, color: "var(--long)" }}>{(Number(winStats.avg_win ?? 0) * 100).toFixed(2)}%</div></div>
              <div><div style={{ color: "var(--muted)", fontSize: 10 }}>Avg Loss</div><div style={{ fontWeight: 700, color: "var(--short)" }}>{(Number(winStats.avg_loss ?? 0) * 100).toFixed(2)}%</div></div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>MONTHLY RETURNS GRID</div>
        <MonthGrid data={monthlyReturns} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>SECTOR ALPHA</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Sector", "Fund", "ETF", "Alpha"].map(h => <th key={h} style={{ color: "var(--muted)", padding: "5px 8px", textAlign: "left", fontSize: 10, fontWeight: 600 }}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {sectorAlpha.map((s: any) => (
                <tr key={s.sector} style={{ borderBottom: "1px solid #1e2a4533" }}>
                  <td style={{ padding: "7px 8px", fontSize: 11 }}>{s.sector}</td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace", color: s.fund_return >= 0 ? "var(--long)" : "var(--short)" }}>{(s.fund_return * 100).toFixed(2)}%</td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace", color: "var(--muted)" }}>{(s.etf_return * 100).toFixed(2)}%</td>
                  <td style={{ padding: "7px 8px", fontFamily: "monospace", fontWeight: 700, color: s.alpha >= 0 ? "var(--long)" : "var(--short)" }}>
                    {s.alpha >= 0 ? "+" : ""}{(s.alpha * 100).toFixed(2)}%
                  </td>
                </tr>
              ))}
              {sectorAlpha.length === 0 && <tr><td colSpan={4} style={{ padding: "12px 8px", color: "var(--muted)" }}>No sector data available.</td></tr>}
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 12 }}>BEST 5 POSITIONS</div>
            {best5.map((p: any) => (
              <div key={p.ticker} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #1e2a4533", fontSize: 12 }}>
                <span style={{ fontWeight: 700 }}>{p.ticker}</span>
                <span style={{ color: "var(--long)", fontFamily: "monospace" }}>+{(Number(p.contribution ?? p.return ?? 0) * 100).toFixed(2)}%</span>
              </div>
            ))}
            {best5.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>No data.</div>}
          </div>
          <div className="card">
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 12 }}>WORST 5 POSITIONS</div>
            {worst5.map((p: any) => (
              <div key={p.ticker} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #1e2a4533", fontSize: 12 }}>
                <span style={{ fontWeight: 700 }}>{p.ticker}</span>
                <span style={{ color: "var(--short)", fontFamily: "monospace" }}>{(Number(p.contribution ?? p.return ?? 0) * 100).toFixed(2)}%</span>
              </div>
            ))}
            {worst5.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>No data.</div>}
          </div>
        </div>
      </div>

      {commentary && (
        <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#6366f1", letterSpacing: "0.1em", marginBottom: 10 }}>WEEKLY COMMENTARY</div>
          <div style={{ fontSize: 13, lineHeight: 1.8, color: "var(--text)", whiteSpace: "pre-wrap" }}>
            {commentary.text ?? commentary.commentary ?? JSON.stringify(commentary)}
          </div>
        </div>
      )}
    </div>
  );
}
