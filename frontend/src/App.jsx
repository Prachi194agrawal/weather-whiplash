import { useEffect, useRef, useState, useCallback } from "react";
import Chart from "chart.js/auto";
import { predict, getTrend, getHealth } from "./api.js";

const SESSION = "default";

// status color language shared with the CSS
const COLOR = {
  Dry: "#4ade80", Damp: "#fbbf24", Wet: "#38bdf8",
  Drying: "#a3e635", Unknown: "#8b98a6",
};
const COMPOUND = { Dry: "SLICK", Damp: "INTER", Wet: "WET", Drying: "X-OVER", Unknown: "—" };

export default function App() {
  const [readout, setReadout] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState({ ok: false, backend: "…" });
  const [frameScores, setFrameScores] = useState(null);
  const fileRef = useRef(null);
  const canvasRef = useRef(null);
  const chartRef = useRef(null);
  const previewUrlRef = useRef(null);

  // ---- polling loop: refresh the trend every 3s so the graph is "live" ----
  const refresh = useCallback(async () => {
    try {
      const [t, h] = await Promise.all([getTrend(SESSION, 900), getHealth()]);
      setReadout(t);
      setHealth({ ok: h.inference_reachable, backend: h.model_backend || "unknown" });
    } catch {
      setHealth((h) => ({ ...h, ok: false }));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (readout?.series?.length) drawChart(readout.series);
  }, [readout]);

  useEffect(() => () => {
    chartRef.current?.destroy();
    chartRef.current = null;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  function drawChart(series) {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const labels = series.map((p) =>
      new Date(p.ts * 1000).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })
    );
    const data = series.map((p) => p.wetness);

    if (!chartRef.current) {
      chartRef.current = new Chart(ctx, {
        type: "line",
        data: { labels, datasets: [{
          data, borderColor: "#38bdf8", borderWidth: 2, tension: 0.35,
          pointRadius: 0, fill: true,
          backgroundColor: (c) => {
            const { ctx, chartArea } = c.chart;
            if (!chartArea) return "rgba(56,189,248,.1)";
            const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            g.addColorStop(0, "rgba(56,189,248,.28)");
            g.addColorStop(1, "rgba(56,189,248,0)");
            return g;
          },
        }]},
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { min: 0, max: 2, ticks: {
                color: "#7d8da0", font: { family: "Roboto Mono", size: 10 },
                callback: (v) => ({ 0: "DRY", 1: "DAMP", 2: "WET" }[v] ?? ""),
                stepSize: 1 },
              grid: { color: "#1c2733" } },
            x: { ticks: { color: "#7d8da0", font: { family: "Roboto Mono", size: 9 }, maxTicksLimit: 8 },
              grid: { display: false } },
          },
        },
      });
    } else {
      chartRef.current.data.labels = labels;
      chartRef.current.data.datasets[0].data = data;
      chartRef.current.update("none");
    }
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Choose a JPG, PNG, or other image file to analyze.");
      return;
    }
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const objectUrl = URL.createObjectURL(file);
    previewUrlRef.current = objectUrl;
    setPreview(objectUrl);
    setError("");
    setBusy(true);
    try {
      const res = await predict(file, SESSION);
      if (res.error) throw new Error(res.error);
      setFrameScores(res.frame?.scores || null);
      setReadout(res);
      const t = await getTrend(SESSION, 900);
      setReadout(t);
    } catch (err) {
      setError(`Prediction failed: ${err.message}`);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  const condition = readout?.condition || "Unknown";
  const color = COLOR[condition] || COLOR.Unknown;
  const sug = readout?.suggestion;
  const scores = frameScores;
  const count = readout?.count ?? 0;
  const dir = readout?.trend?.direction || "—";

  return (
    <main className="wrap">
      <div className="masthead">
        <div>
          <div className="eyebrow">Race Strategy · Live Track Read</div>
          <h1 className="title">Pit Wall</h1>
        </div>
        <div className="backend-tag" aria-live="polite">
          <span className={"dot " + (health.ok ? "live" : "dead")} />
          {health.ok ? "LIVE" : "OFFLINE"} · model:{health.backend}
        </div>
      </div>

      <div className="grid">
        {/* LEFT: condition + suggestion + confidence */}
        <div>
          <div className="panel">
            <h2>Track Condition</h2>
            <div className="readout">
              <div className="compound" style={{ background: color }} aria-label={`${condition} tyre recommendation`}>{COMPOUND[condition]}</div>
              <div>
                <div className="condition-name" style={{ color }}>{condition}</div>
                <div className="condition-sub">
                  trend: {dir} · {count} frame{count === 1 ? "" : "s"}
                </div>
              </div>
            </div>

            {sug && (
              <div className={"suggestion " + (sug.level || "info")}>
                <span className="lead">Strategy call</span>
                {sug.message}
              </div>
            )}
          </div>

          <div className="panel" style={{ marginTop: 18 }}>
            <h2>Per-frame Confidence</h2>
            {scores ? (
              <div className="bars">
                {["Dry", "Damp", "Wet"].map((k) => (
                  <div className="bar-row" key={k}>
                    <span>{k}</span>
                    <span className="track">
                      <span className="fill" style={{ width: `${(scores[k] || 0) * 100}%`, background: COLOR[k] }} />
                    </span>
                    <span>{Math.round((scores[k] || 0) * 100)}%</span>
                  </div>
                ))}
              </div>
            ) : <div className="hint">Upload a frame to see class confidence.</div>}
          </div>
        </div>

        {/* RIGHT: live trace + upload */}
        <div>
          <div className="panel">
            <h2>Wetness Trace · last 15 min</h2>
            {count > 0 ? (
              <div className="chart-wrap"><canvas ref={canvasRef} /></div>
            ) : (
              <div className="empty">No frames yet. Upload trackside frames to build the trend.</div>
            )}
            <div className="stat-row">
              <div className="stat"><div className="k">Current</div><div className="v" style={{ color }}>{condition}</div></div>
              <div className="stat"><div className="k">Direction</div><div className="v">{dir}</div></div>
              <div className="stat"><div className="k">Frames</div><div className="v">{count}</div></div>
            </div>
          </div>

          <div className="panel feed" style={{ marginTop: 18 }}>
            <h2>Camera Frame</h2>
            {preview && <img className="preview" src={preview} alt="latest frame" />}
            {!preview && <div className="camera-placeholder" aria-hidden="true"><span>▣</span><p>Awaiting trackside frame</p></div>}
            {error && <p className="error" role="alert">{error}</p>}
            <div className="controls">
              <button className="btn primary" disabled={busy} onClick={() => fileRef.current?.click()}>
                {busy ? "Analyzing…" : "Upload frame"}
              </button>
              <span className="hint">JPG/PNG trackside or onboard frame</span>
              <input ref={fileRef} type="file" accept="image/*" onChange={onFile} style={{ display: "none" }} />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
