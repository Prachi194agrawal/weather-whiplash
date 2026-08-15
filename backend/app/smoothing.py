"""
Turns a noisy stream of per-frame moisture labels into a stable, trustworthy readout.

Three jobs:
  1. smooth_current()  -> a stable current state (Dry/Damp/Wet), resisting single-frame flicker
  2. trend_direction() -> is the track Drying, Wetting, or Stable? (this is where "Drying" is born)
  3. make_suggestion()  -> a plain-language tire message a race engineer can act on

Why not just take the latest frame? Because one frame of windshield spray or glare would flip
the readout. We weight recent frames by confidence and require a sustained change before we
declare a direction (hysteresis). This is deliberately rule-based and explainable — a race
engineer can understand exactly why it said what it said.
"""
from typing import List, Dict

# numeric moisture scale so we can average and compare directions
STATE_TO_NUM = {"Dry": 0.0, "Damp": 1.0, "Wet": 2.0}
NUM_TO_STATE = {0: "Dry", 1: "Damp", 2: "Wet"}


def _wetness_value(scores: Dict[str, float]) -> float:
    """Expected moisture on the 0..2 scale from the class probabilities (smoother than argmax)."""
    return sum(STATE_TO_NUM[c] * p for c, p in scores.items() if c in STATE_TO_NUM)


def smooth_current(points: List[dict], window: int = 8) -> dict:
    """Confidence-weighted average moisture over the last `window` frames -> stable state."""
    if not points:
        return {"state": "Unknown", "wetness": None, "n": 0}
    recent = points[-window:]
    num = sum(_wetness_value(p["scores"]) * p["confidence"] for p in recent)
    den = sum(p["confidence"] for p in recent) or 1.0
    wetness = num / den
    return {
        "state": NUM_TO_STATE[round(min(2, max(0, wetness)))],
        "wetness": round(wetness, 3),
        "n": len(recent),
    }


def trend_direction(points: List[dict], window: int = 6, min_delta: float = 0.25) -> dict:
    """
    Compare the average wetness of the most recent window against the window before it.
    A sustained DROP in wetness = Drying. A sustained RISE = Wetting. Otherwise Stable.
    `min_delta` is the hysteresis threshold that prevents noise from triggering a direction.
    """
    if len(points) < window * 2:
        return {"direction": "Stable", "delta": 0.0, "confident": False}

    prev = points[-2 * window : -window]
    curr = points[-window:]

    def avg(ps):
        num = sum(_wetness_value(p["scores"]) * p["confidence"] for p in ps)
        den = sum(p["confidence"] for p in ps) or 1.0
        return num / den

    delta = avg(curr) - avg(prev)  # positive = getting wetter, negative = drying

    if delta <= -min_delta:
        direction = "Drying"
    elif delta >= min_delta:
        direction = "Wetting"
    else:
        direction = "Stable"

    return {"direction": direction, "delta": round(delta, 3), "confident": True}


def make_suggestion(points: List[dict]) -> dict:
    """Rule-based tire-change guidance from current state + direction."""
    cur = smooth_current(points)
    trend = trend_direction(points)
    state, direction = cur["state"], trend["direction"]

    if state == "Unknown":
        return {"level": "info", "message": "Waiting for enough frames to assess the track."}

    # worsening conditions — urgent
    if direction == "Wetting" and state in ("Damp", "Wet"):
        return {"level": "warning",
                "message": "Track getting wetter — prepare wet/intermediate tyres."}
    if state == "Wet" and direction != "Drying":
        return {"level": "warning",
                "message": "Track is wet — wet tyres recommended."}

    # improving conditions — the money signal
    if direction == "Drying" and state == "Wet":
        return {"level": "info",
                "message": "Track drying but still wet — hold wets, watch for the crossover."}
    if direction == "Drying" and state == "Damp":
        return {"level": "success",
                "message": "Track drying: tyre change window approaching — ready slicks/inters."}
    if direction == "Drying" and state == "Dry":
        return {"level": "success",
                "message": "Track has dried out — slicks are the call."}

    # stable
    if state == "Dry":
        return {"level": "success", "message": "Track dry and stable — slicks."}
    if state == "Damp":
        return {"level": "info", "message": "Track damp and stable — monitor closely."}
    return {"level": "info", "message": "Monitoring track condition."}


def display_condition(points: List[dict]) -> str:
    """The single headline label for the UI: folds direction into the 4 challenge classes."""
    cur = smooth_current(points)
    trend = trend_direction(points)
    if cur["state"] == "Unknown":
        return "Unknown"
    if trend["direction"] == "Drying" and cur["state"] in ("Damp", "Wet"):
        return "Drying"
    return cur["state"]
