"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RefreshCw, FileText, Lock } from "lucide-react";

const TODAY = new Date();
const YYYY = TODAY.getFullYear();
const MMDD = String(TODAY.getMonth() + 1).padStart(2, "0") + String(TODAY.getDate()).padStart(2, "0");
const DOC_ID = `MCP-IM-${YYYY}-${MMDD}`;
const DISPLAY_DATE = TODAY.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

function Skeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {[180, 120, 160, 100, 140].map((w, i) => (
        <div key={i} style={{ height: 14, borderRadius: 6, background: "linear-gradient(90deg, #1e2a45 25%, #253350 50%, #1e2a45 75%)", backgroundSize: "200% 100%", animation: "shimmer 1.4s infinite", width: `${w * 4}px`, maxWidth: "100%" }} />
      ))}
      <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>
    </div>
  );
}

export default function LetterPage() {
  const [letter, setLetter] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.letter.daily(false)
      .then(setLetter)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  async function handleRegenerate() {
    setRegenerating(true);
    try {
      const refreshed = await api.letter.daily(true);
      setLetter(refreshed);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setRegenerating(false);
    }
  }

  const body: string = letter?.letter ?? letter?.text ?? letter?.body ?? "";
  const aum: string = letter?.aum ?? "$100,000,000";
  const inception: string = letter?.inception ?? "January 1, 2023";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 880, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <FileText size={18} color="#6366f1" />
          <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "monospace" }}>{DOC_ID}</span>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          style={{ display: "flex", alignItems: "center", gap: 7, background: "transparent", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 14px", color: regenerating ? "var(--muted)" : "var(--text)", fontSize: 12, fontWeight: 600, cursor: regenerating ? "not-allowed" : "pointer" }}>
          <RefreshCw size={13} style={{ animation: regenerating ? "spin 0.8s linear infinite" : "none" }} />
          {regenerating ? "Regenerating…" : "Regenerate Letter"}
        </button>
      </div>
      <style>{`@keyframes spin { 100%{transform:rotate(360deg)} }`}</style>

      <div className="card" style={{ padding: "40px 48px" }}>
        {/* Letterhead */}
        <div style={{ borderBottom: "2px solid var(--border)", paddingBottom: 24, marginBottom: 28 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ fontSize: 28, fontWeight: 900, letterSpacing: "-0.5px", background: "linear-gradient(135deg,#6366f1,#a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Meridian Capital Partners
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, letterSpacing: "0.05em" }}>
                Domicile: Delaware &nbsp;·&nbsp; Inception: {inception} &nbsp;·&nbsp; AUM: {aum}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, background: "#f43f5e22", border: "1px solid var(--short)", borderRadius: 6, padding: "5px 12px" }}>
                <Lock size={11} color="var(--short)" />
                <span style={{ fontSize: 10, fontWeight: 800, color: "var(--short)", letterSpacing: "0.1em" }}>CONFIDENTIAL · LIMITED PARTNERS ONLY</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>{DISPLAY_DATE}</div>
            </div>
          </div>
        </div>

        {/* Salutation */}
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 20 }}>Dear Limited Partners,</div>

        {/* Body */}
        {loading ? (
          <Skeleton />
        ) : error && !body ? (
          <div style={{ padding: "24px 0", color: "var(--muted)", fontSize: 13 }}>
            No letter available — run backend layers first, or click <strong>Regenerate Letter</strong> above.
          </div>
        ) : (
          <div style={{ fontSize: 13.5, lineHeight: 1.95, color: "var(--text)", whiteSpace: "pre-wrap", fontFamily: "'Georgia', 'Times New Roman', serif" }}>
            {body}
          </div>
        )}

        {/* Signature block */}
        {!loading && (body || !error) && (
          <div style={{ marginTop: 40, paddingTop: 24, borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 2 }}>Respectfully submitted,</div>
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#6366f1", letterSpacing: "0.04em" }}>JARVIS</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>AI Portfolio Intelligence</div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>Meridian Capital Partners</div>
            </div>
          </div>
        )}

        {/* Compliance footer */}
        <div style={{ marginTop: 40, paddingTop: 16, borderTop: "1px solid #1e2a4566" }}>
          <p style={{ fontSize: 9.5, color: "#334155", lineHeight: 1.7, margin: 0 }}>
            This document is prepared solely for the use of the limited partners of Meridian Capital Partners and is strictly confidential.
            It may not be reproduced, distributed, or disclosed to any third party without the prior written consent of the General Partner.
            Past performance is not necessarily indicative of future results. All investments involve risk, including possible loss of principal.
            This communication does not constitute an offer to sell or a solicitation of an offer to buy any securities.
            The information contained herein is believed to be accurate as of the date shown but is subject to change without notice.
            Meridian Capital Partners is an exempt reporting adviser. This document is for informational purposes only.
          </p>
        </div>
      </div>
    </div>
  );
}
