"use client";
import { useEffect, useState, useRef } from "react";
import MetricCard from "@/components/MetricCard";
import { api } from "@/lib/api";

interface ChatMsg { role: "user" | "jarvis"; text: string }

function VixBadge({ vix }: { vix: number }) {
  const regime = vix < 15 ? "LOW VOL" : vix > 25 ? "HIGH VOL" : "NORMAL";
  const color = vix < 15 ? "#10b981" : vix > 25 ? "#f43f5e" : "#6366f1";
  return (
    <span style={{ background: `${color}22`, color, border: `1px solid ${color}`,
      borderRadius: 6, padding: "3px 10px", fontSize: 11, fontWeight: 700 }}>
      VIX {vix.toFixed(1)} · {regime}
    </span>
  );
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

async function adminPost(path: string) {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text().catch(() => "")}`);
  return res.json();
}
async function adminGet(path: string) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function DataStatusBanner() {
  const [status, setStatus] = useState<any>(null);
  const [triggering, setTriggering] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    adminGet("/api/admin/status").then(setStatus).catch(() => {});
    const t = setInterval(() => adminGet("/api/admin/status").then(setStatus).catch(() => {}), 8000);
    return () => clearInterval(t);
  }, []);

  async function runRefresh() {
    setTriggering(true);
    setMsg("");
    try {
      const r = await adminPost("/api/admin/run-data?no_filings=true&no_13f=true");
      setMsg(r.message ?? "Pipeline started.");
    } catch (e: any) {
      setMsg(`Error: ${e?.message ?? "Could not reach backend"}`);
    } finally {
      setTriggering(false);
    }
  }

  // API not reachable yet — show setup instructions
  if (!status) {
    return (
      <div style={{
        background: "#6366f118", border: "1px solid #6366f1",
        borderRadius: 10, padding: "12px 18px", marginBottom: 8,
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#a78bfa" }}>
            ⚙ Backend not connected — add environment variables in Vercel to activate data
          </div>
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 3 }}>
            Go to Vercel → dashboard project → Settings → Environment Variables → add ANTHROPIC_API_KEY, DATABASE_URL, ALPACA_API_KEY, ALPACA_SECRET_KEY, MERIDIAN_DB_PATH=/tmp/meridian.db → Redeploy
          </div>
          {msg && <div style={{ fontSize: 11, color: "#f43f5e", marginTop: 3 }}>{msg}</div>}
        </div>
        <button
          onClick={runRefresh}
          disabled={triggering}
          style={{
            background: "linear-gradient(135deg, #4f46e5, #6366f1)", border: "none",
            borderRadius: 8, padding: "8px 16px", color: "#fff",
            fontWeight: 600, cursor: "pointer", fontSize: 12, whiteSpace: "nowrap",
          }}
        >
          {triggering ? "Trying…" : "Try Fetch Data"}
        </button>
      </div>
    );
  }

  const isEmpty = (status.universe_size ?? 0) === 0;
  const isRunning = status.pipeline_running;

  return (
    <div style={{
      background: isEmpty ? "#f43f5e18" : isRunning ? "#6366f118" : "#10b98118",
      border: `1px solid ${isEmpty ? "#f43f5e" : isRunning ? "#6366f1" : "#10b981"}`,
      borderRadius: 10, padding: "12px 18px", marginBottom: 8,
      display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
    }}>
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: isEmpty ? "#f43f5e" : isRunning ? "#a78bfa" : "#10b981" }}>
          {isEmpty ? "⚠ Database empty — no data yet" : isRunning ? "⏳ Data pipeline running…" : `✓ ${status.universe_size} tickers · ${(status.price_bars ?? 0).toLocaleString()} price bars`}
        </div>
        {msg && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 3 }}>{msg}</div>}
        {isRunning && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 3 }}>Fetching S&P 500 data in background (~20 min first time). Refresh this page when done.</div>}
      </div>
      <button
        onClick={runRefresh}
        disabled={triggering || isRunning}
        style={{
          background: isRunning ? "#1e2a45" : "linear-gradient(135deg, #4f46e5, #6366f1)",
          border: "none", borderRadius: 8, padding: "8px 16px",
          color: isRunning ? "#64748b" : "#fff", fontWeight: 600,
          cursor: isRunning ? "not-allowed" : "pointer", fontSize: 12, whiteSpace: "nowrap",
        }}
      >
        {triggering ? "Starting…" : isRunning ? "Running…" : isEmpty ? "Fetch Data Now" : "Refresh Data"}
      </button>
    </div>
  );
}

function WatchTickerWidget({ onAdded }: { onAdded: () => void }) {
  const [ticker, setTicker] = useState("");
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleAdd() {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await api.universe.addTicker(t);
      if (res.status === "already_exists") {
        setStatus({ msg: `${t} is already in the universe${res.in_sp500 ? " (S&P 500)" : " (custom)"}`, ok: true });
      } else {
        setStatus({ msg: `✓ ${t} (${res.company_name}) added — run data refresh to pull prices`, ok: true });
        setTicker("");
        onAdded();
      }
    } catch (e: any) {
      setStatus({ msg: `Failed: ${e?.message ?? "unknown error"}`, ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", letterSpacing: "0.08em", marginBottom: 10 }}>WATCH TICKER</div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="e.g. NVDA, PLTR…"
          maxLength={10}
          style={{ flex: 1, background: "#0b0e17", border: "1px solid #1e2a45", borderRadius: 8, padding: "8px 12px", color: "#e2e8f0", fontSize: 13, outline: "none", fontFamily: "monospace", textTransform: "uppercase" }}
        />
        <button
          onClick={handleAdd}
          disabled={busy || !ticker.trim()}
          style={{ background: busy || !ticker.trim() ? "#1e2a45" : "linear-gradient(135deg,#4f46e5,#6366f1)", border: "none", borderRadius: 8, padding: "8px 16px", color: busy || !ticker.trim() ? "#64748b" : "#fff", fontWeight: 700, cursor: busy || !ticker.trim() ? "not-allowed" : "pointer", fontSize: 12, whiteSpace: "nowrap" }}>
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
      {status && (
        <div style={{ marginTop: 8, fontSize: 11, color: status.ok ? "#10b981" : "#f43f5e" }}>{status.msg}</div>
      )}
      <div style={{ marginTop: 6, fontSize: 10, color: "#475569" }}>
        Add any ticker not in S&P 500 — it will be scored and tracked going forward.
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  const [stats, setStats] = useState<any>(null);
  const [positions, setPositions] = useState<any>(null);
  const [vixData, setVixData] = useState<any>(null);
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.universe.stats().then(setStats).catch(() => {});
    api.portfolio.positions().then(setPositions).catch(() => {});
    api.research.vix().then(setVixData).catch(() => {});
    const interval = setInterval(() => {
      const h = new Date().getHours();
      if (h >= 9 && h < 16) {
        api.portfolio.positions().then(setPositions).catch(() => {});
        api.research.vix().then(setVixData).catch(() => {});
      }
    }, 300_000);
    return () => clearInterval(interval);
  }, []);

  async function sendMessage() {
    if (!input.trim()) return;
    const msg = input.trim();
    setInput("");
    setChat((c) => [...c, { role: "user", text: msg }]);
    setThinking(true);
    try {
      const res = await api.jarvis.chat(msg, chat.slice(-6).map(m => ({ role: m.role, content: m.text })));
      setChat((c) => [...c, { role: "jarvis", text: res.response }]);
    } catch {
      setChat((c) => [...c, { role: "jarvis", text: "System error — please try again." }]);
    } finally {
      setThinking(false);
    }
    setTimeout(() => { if (chatRef.current) chatRef.current.scrollTop = 99999; }, 100);
  }

  const summary = positions?.summary ?? {};

  return (
    <div>
      <DataStatusBanner />
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, minHeight: "80vh" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <div>
          <div style={{ fontSize: 82, fontWeight: 900, letterSpacing: "-3px",
            background: "linear-gradient(135deg, #6366f1, #a78bfa)", WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent", lineHeight: 1 }}>JARVIS</div>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#64748b",
            textTransform: "uppercase", marginTop: 4 }}>LONG / SHORT HEDGE FUND ANALYST</div>
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          {vixData && <VixBadge vix={vixData.vix} />}
          <span style={{ fontSize: 11, color: "#64748b" }}>Data: yfinance + SEC EDGAR</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          <MetricCard label="Universe" value={stats?.universe_size ?? "—"} />
          <MetricCard label="Positions" value={summary.total_positions ?? "—"} />
          <MetricCard label="Long / Short" value={`${summary.long_count ?? 0} / ${summary.short_count ?? 0}`} />
          <MetricCard label="VIX" value={vixData?.vix?.toFixed(1) ?? "—"} color={vixData?.vix > 25 ? "#f43f5e" : "#10b981"} />
          <MetricCard label="Earnings 7d" value={stats?.earnings_next_7d ?? "—"} />
          <MetricCard label="CEO Buys 30d" value={stats?.ceo_buys_30d ?? "—"} color="#10b981" />
          <MetricCard label="Cluster Buys" value={stats?.cluster_buys ?? "—"} />
          <MetricCard label="Regime" value={vixData?.regime?.replace("_", " ")?.toUpperCase() ?? "—"} />
          <MetricCard label="Unrlzd P&L" value={summary.total_unrealized_pnl != null ? `$${(summary.total_unrealized_pnl/1000).toFixed(0)}K` : "—"} color={summary.total_unrealized_pnl >= 0 ? "#10b981" : "#f43f5e"} />
        </div>

        <WatchTickerWidget onAdded={() => api.universe.stats().then(setStats).catch(() => {})} />

        <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#6366f1", letterSpacing: "0.1em" }}>ASK JARVIS</div>
          <div ref={chatRef} style={{ flex: 1, overflowY: "auto", maxHeight: 260, display: "flex", flexDirection: "column", gap: 10 }}>
            {chat.length === 0 && <div style={{ color: "#475569", fontSize: 13, fontStyle: "italic" }}>Ask about the portfolio, risk, or market conditions…</div>}
            {chat.map((m, i) => (
              <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                background: m.role === "user" ? "#1e2a45" : "#131827", borderRadius: 8,
                padding: "10px 14px", maxWidth: "90%", fontSize: 13, lineHeight: 1.6,
                border: m.role === "jarvis" ? "1px solid #6366f133" : "1px solid #1e2a45" }}>
                {m.role === "jarvis" && <div style={{ color: "#6366f1", fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", marginBottom: 4 }}>JARVIS</div>}
                <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
              </div>
            ))}
            {thinking && <div style={{ color: "#6366f1", fontSize: 13, fontStyle: "italic" }}>JARVIS thinking…</div>}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
              placeholder="Ask JARVIS anything…"
              style={{ flex: 1, background: "#0b0e17", border: "1px solid #1e2a45", borderRadius: 8,
                padding: "10px 14px", color: "#e2e8f0", fontSize: 13, outline: "none" }} />
            <button onClick={sendMessage}
              style={{ background: "linear-gradient(135deg, #4f46e5, #6366f1)", border: "none",
                borderRadius: 8, padding: "10px 18px", color: "#fff", fontWeight: 600, cursor: "pointer", fontSize: 13 }}>
              Send
            </button>
          </div>
        </div>
      </div>

      <div className="card" style={{ overflow: "auto" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", marginBottom: 16 }}>CURRENT POSITIONS</div>
        {!positions?.positions?.length ? (
          <div style={{ color: "#475569", fontSize: 13 }}>No positions. Run portfolio construction first.</div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e2a45" }}>
                {["Ticker", "Signal", "Shares", "Entry", "Current", "P&L", "Sector"].map(h => (
                  <th key={h} style={{ color: "#64748b", fontWeight: 600, padding: "6px 10px", textAlign: "left", fontSize: 11 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.positions.map((p: any) => (
                <tr key={p.ticker} style={{ borderBottom: "1px solid #1e2a4522" }}>
                  <td style={{ padding: "8px 10px", fontWeight: 700 }}>{p.ticker}</td>
                  <td style={{ padding: "8px 10px" }}><span className={p.signal === "LONG" ? "badge-long" : "badge-short"}>{p.signal}</span></td>
                  <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>{Number(p.shares).toLocaleString()}</td>
                  <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>${Number(p.entry_price).toFixed(2)}</td>
                  <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>${Number(p.current_price ?? p.entry_price).toFixed(2)}</td>
                  <td style={{ padding: "8px 10px", fontFamily: "monospace", color: p.unrealized_pnl >= 0 ? "#10b981" : "#f43f5e" }}>
                    {p.unrealized_pnl >= 0 ? "+" : ""}${Number(p.unrealized_pnl).toFixed(0)}
                  </td>
                  <td style={{ padding: "8px 10px", color: "#64748b", fontSize: 11 }}>{p.sector}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
    </div>
  );
}
