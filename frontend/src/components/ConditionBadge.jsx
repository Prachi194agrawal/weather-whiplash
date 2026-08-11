const CLASS_BY_LABEL = {
  Dry: "badge-dry",
  Damp: "badge-damp",
  Drying: "badge-drying",
  Wet: "badge-wet",
};

export default function ConditionBadge({ label, confidence }) {
  if (!label) return null;
  const cls = CLASS_BY_LABEL[label] || "badge-dry";
  return (
    <span className={`badge ${cls}`}>
      {label} {confidence != null && `· ${Math.round(confidence * 100)}%`}
    </span>
  );
}
