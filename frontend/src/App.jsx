import { useCallback, useEffect, useState } from "react";
import SuggestionBanner from "./components/SuggestionBanner.jsx";
import TrendChart from "./components/TrendChart.jsx";
import UploadPanel from "./components/UploadPanel.jsx";
import { getSuggestion, getTrend } from "./api.js";

const POLL_MS = 5000;

export default function App() {
  const [frames, setFrames] = useState([]);
  const [suggestion, setSuggestion] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [trendData, suggestionData] = await Promise.all([
        getTrend(),
        getSuggestion(),
      ]);
      setFrames(trendData);
      setSuggestion(suggestionData);
    } catch {
      // backend unreachable — leave last known state on screen
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div>
      <h1>Track Condition AI</h1>
      <p style={{ color: "#999", marginTop: -8 }}>
        Upload trackside frames to see condition, trend, and tire-change guidance.
      </p>

      <UploadPanel onPredicted={refresh} />
      <SuggestionBanner suggestion={suggestion} />
      <TrendChart frames={frames} />
    </div>
  );
}
