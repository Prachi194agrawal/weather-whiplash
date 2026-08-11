import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const SEVERITY = { Dry: 0, Drying: 1, Damp: 2, Wet: 3 };

export default function TrendChart({ frames }) {
  const data = frames.map((f) => ({
    time: new Date(f.timestamp).toLocaleTimeString(),
    severity: SEVERITY[f.label] ?? 0,
    label: f.label,
  }));

  return (
    <div className="card">
      <h2>Trend (last 15 min)</h2>
      {data.length === 0 ? (
        <p>No frames yet — upload one to start the trend.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2e38" />
            <XAxis dataKey="time" stroke="#888" fontSize={12} />
            <YAxis
              domain={[0, 3]}
              ticks={[0, 1, 2, 3]}
              tickFormatter={(v) => ["Dry", "Drying", "Damp", "Wet"][v]}
              stroke="#888"
              fontSize={12}
            />
            <Tooltip
              formatter={(_, __, props) => props.payload.label}
              contentStyle={{ background: "#171a21", border: "1px solid #2a2e38" }}
            />
            <Line type="monotone" dataKey="severity" stroke="#4c6ef5" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
