from app.models import Frame

SEVERITY = {"Dry": 0, "Drying": 1, "Damp": 2, "Wet": 3}


def build_suggestion(frames: list[Frame]) -> dict:
    """Rule-based trend + tire-change suggestion from recent frames (oldest first)."""
    if len(frames) < 2:
        return {
            "suggestion": "Not enough data yet — keep uploading frames.",
            "direction": "unknown",
            "latest_label": frames[-1].label if frames else None,
            "window_size": len(frames),
        }

    mid = len(frames) // 2
    first_half = frames[:mid]
    second_half = frames[mid:]

    avg_first = sum(SEVERITY[f.label] for f in first_half) / len(first_half)
    avg_second = sum(SEVERITY[f.label] for f in second_half) / len(second_half)

    latest_label = frames[-1].label
    delta = avg_second - avg_first

    if latest_label == "Drying" and delta <= 0:
        suggestion = "Track drying: tire change window approaching."
        direction = "improving"
    elif delta < -0.15:
        suggestion = "Track improving — conditions drying out."
        direction = "improving"
    elif delta > 0.15:
        suggestion = "Track worsening — consider wet-weather tires."
        direction = "worsening"
    else:
        suggestion = f"Track holding steady at {latest_label}."
        direction = "stable"

    return {
        "suggestion": suggestion,
        "direction": direction,
        "latest_label": latest_label,
        "window_size": len(frames),
    }
