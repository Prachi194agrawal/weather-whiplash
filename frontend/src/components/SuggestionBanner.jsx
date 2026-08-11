const COLOR_BY_DIRECTION = {
  improving: "#8fe38f",
  worsening: "#ff9b9b",
  stable: "#e6e6e6",
  unknown: "#999",
};

export default function SuggestionBanner({ suggestion }) {
  if (!suggestion) return null;
  const color = COLOR_BY_DIRECTION[suggestion.direction] || "#e6e6e6";
  return (
    <div className="card">
      <h2>Suggestion</h2>
      <p className="suggestion-banner" style={{ color }}>
        {suggestion.suggestion}
      </p>
    </div>
  );
}
