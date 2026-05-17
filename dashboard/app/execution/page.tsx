"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import MetricCard from "@/components/MetricCard";
import { Info, Wifi, WifiOff } from "lucide-react";

function StatRow({ label, value, mono = true }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #1e2a4533", fontSize: 12 }}>
      <span style={{ color: "var(--muted)" }}>{label}</span>
      <span style={{ fontFamily: mono ? "monospace" : "inherit", color: "var(--text)", fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export default function ExecutionPage() {
  const [slippage, setSlippage] = useState<any>(null);
  const [account, setAccount] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [noAccount, setNoAccount] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.execution.slippage().then(setSlippage).catch(() => {}),
      api.execution.account().then(setAccount).catch(() => { setNoAccount(true); }),
    ]).catch(() => setError(true)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>Loading execution data…</div>;
  if (error && !slippage && !account) return <div style={{ color: "var(--muted)", padding: 48, fontSize: 14 }}>No data available — run backend layers first.</div>;

  const stats = slippage?.stats ?? {};
  const fills: any[] = slippage?.fills ?? [];
  const worst5: any[] = slippage?.worst_fills ?? fills.slice(0, 5);
  const openOrders: number = slippage?.open_orders ?? 0;
  const filledOrders30d: number = slippage?.filled_orders_30d ?? fills.length;
  const avgSlippageBps: number = stats.avg_bps ?? 0;
  const totalSlippageUsd: number = stats.total_usd ?? 0;
  const medianBps: number = stats.median_bps ?? 0;
  const p95Bps: number = stats.p95_bps ?? 0;
  const dailyNotional: number = slippage?.daily_notional_estimate ?? 0;

  const shortPositions: any[] = slippage?.short_positions ?? [];

  const acct = account ?? {};
  const equity: number = acct.equity ?? acct.portfolio_value ?? 0;
  const cash: number = acct.cash ?? 0;
  const buyingPower: number = acct.buying_power ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-0.5px" }}>Execution Analytics</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: noAccount ? "var(--short)" : "var(--long)" }}>
          {noAccount ? <WifiOff size={14} /> : <Wifi size={14} />}
          {noAccount ? "Alpaca: Disconnected" : "Alpaca: Connected"}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <MetricCard label="Filled Orders 30d" value={filledOrders30d.toLocaleString()} />
        <MetricCard label="Avg Slippage" value={`${avgSlippageBps.toFixed(1)} bps`} color={avgSlippageBps > 10 ? "var(--short)" : "var(--long)"} />
        <MetricCard label="Total Slippage $" value={`$${totalSlippageUsd.toLocaleString("en-US", { maximumFractionDigits: 0 })}`} color="var(--short)" />
        <MetricCard label="Open Orders" value={openOrders} color={openOrders > 0 ? "#f59e0b" : "var(--muted)"} />
      </div>

      {noAccount && (
        <div style={{ background: "#f59e0b15", border: "1px solid #f59e0b", borderRadius: 10, padding: "12px 16px", display: "flex", alignItems: "center", gap: 10 }}>
          <Info size={15} color="#fbbf24" />
          <span style={{ fontSize: 12, color: "#fde68a" }}>Open orders require a live Alpaca connection. Account data is unavailable — configure <code style={{ background: "#0b0e17", padding: "1px 4px", borderRadius: 3 }}>ALPACA_API_KEY</code> and <code style={{ background: "#0b0e17", padding: "1px 4px", borderRadius: 3 }}>ALPACA_SECRET_KEY</code> in the backend.</span>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>SLIPPAGE STATISTICS</div>
          <StatRow label="Average slippage" value={`${avgSlippageBps.toFixed(2)} bps`} />
          <StatRow label="Median slippage" value={`${medianBps.toFixed(2)} bps`} />
          <StatRow label="95th percentile" value={`${p95Bps.toFixed(2)} bps`} />
          <StatRow label="Daily notional est." value={`$${dailyNotional.toLocaleString("en-US", { maximumFractionDigits: 0 })}`} />
          <div style={{ marginTop: 18, fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.08em", marginBottom: 10 }}>WORST 5 FILLS</div>
          {worst5.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 12 }}>No fill data available.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Ticker", "Side", "Slippage bps", "Notional", "Date"].map(h => (
                    <th key={h} style={{ color: "var(--muted)", padding: "4px 6px", textAlign: "left", fontSize: 10, fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {worst5.map((f: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid #1e2a4533" }}>
                    <td style={{ padding: "6px 6px", fontWeight: 700 }}>{f.ticker ?? f.symbol}</td>
                    <td style={{ padding: "6px 6px" }}><span className={f.side === "buy" ? "badge-long" : "badge-short"}>{f.side?.toUpperCase()}</span></td>
                    <td style={{ padding: "6px 6px", fontFamily: "monospace", color: "var(--short)" }}>{Number(f.slippage_bps ?? f.bps ?? 0).toFixed(2)}</td>
                    <td style={{ padding: "6px 6px", fontFamily: "monospace" }}>${Number(f.notional ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td>
                    <td style={{ padding: "6px 6px", color: "var(--muted)", fontSize: 10 }}>{f.date ?? f.filled_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>
              ACCOUNT — ALPACA
              {noAccount && <span style={{ marginLeft: 8, fontSize: 10, color: "var(--short)", fontWeight: 600 }}>OFFLINE</span>}
            </div>
            <StatRow label="Portfolio equity" value={equity > 0 ? `$${equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—"} />
            <StatRow label="Cash" value={cash > 0 ? `$${cash.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—"} />
            <StatRow label="Buying power" value={buyingPower > 0 ? `$${buyingPower.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—"} />
            {acct.daytrade_count != null && <StatRow label="Day trades (5d)" value={acct.daytrade_count} />}
            {acct.pattern_day_trader != null && <StatRow label="PDT status" value={acct.pattern_day_trader ? "YES" : "NO"} />}
          </div>

          <div className="card">
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.1em", marginBottom: 14 }}>SHORT AVAILABILITY</div>
            {shortPositions.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: 12 }}>No short positions in portfolio.</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Ticker", "Shares Short", "Shortable", "Borrow Rate"].map(h => (
                      <th key={h} style={{ color: "var(--muted)", padding: "4px 6px", textAlign: "left", fontSize: 10, fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shortPositions.map((p: any) => (
                    <tr key={p.ticker} style={{ borderBottom: "1px solid #1e2a4533" }}>
                      <td style={{ padding: "6px 6px", fontWeight: 700 }}>{p.ticker}</td>
                      <td style={{ padding: "6px 6px", fontFamily: "monospace" }}>{Number(p.shares).toLocaleString()}</td>
                      <td style={{ padding: "6px 6px" }}>
                        <span style={{ color: p.shortable ? "var(--long)" : "var(--short)", fontWeight: 700, fontSize: 11 }}>
                          {p.shortable ? "YES" : "NO"}
                        </span>
                      </td>
                      <td style={{ padding: "6px 6px", fontFamily: "monospace", color: "var(--muted)" }}>
                        {p.borrow_rate != null ? `${(p.borrow_rate * 100).toFixed(2)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
