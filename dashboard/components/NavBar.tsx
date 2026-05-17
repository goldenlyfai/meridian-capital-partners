"use client";
import { usePathname, useRouter } from "next/navigation";

const pages = [
  { path: "/", label: "I  PORTFOLIO" },
  { path: "/research", label: "II  RESEARCH" },
  { path: "/risk", label: "III  RISK" },
  { path: "/performance", label: "IV  PERFORMANCE" },
  { path: "/execution", label: "V  EXECUTION" },
  { path: "/letter", label: "VI  LETTER" },
];

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav
      style={{
        background: "linear-gradient(90deg, #0f1422, #131827)",
        borderBottom: "1px solid #1e2a45",
        padding: "12px 32px",
        display: "flex",
        alignItems: "center",
        gap: "8px",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}
    >
      <span
        style={{
          fontSize: 13,
          fontWeight: 800,
          color: "#6366f1",
          letterSpacing: "0.12em",
          marginRight: 24,
          whiteSpace: "nowrap",
        }}
      >
        MERIDIAN
      </span>
      {pages.map((p) => {
        const active = pathname === p.path;
        return (
          <button
            key={p.path}
            onClick={() => router.push(p.path)}
            style={{
              background: active
                ? "linear-gradient(135deg, #4f46e5, #6366f1)"
                : "transparent",
              color: active ? "#fff" : "#64748b",
              border: "none",
              borderRadius: 20,
              padding: "6px 14px",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              letterSpacing: "0.04em",
              transition: "all 0.2s",
              whiteSpace: "nowrap",
            }}
          >
            {p.label}
          </button>
        );
      })}
    </nav>
  );
}
