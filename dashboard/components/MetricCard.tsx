interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

export default function MetricCard({ label, value, sub, color }: MetricCardProps) {
  return (
    <div className="card" style={{ minWidth: 120 }}>
      <div className="metric-label">{label}</div>
      <div
        className="metric-value"
        style={{ color: color ?? "var(--text)", marginTop: 6 }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{sub}</div>
      )}
    </div>
  );
}
