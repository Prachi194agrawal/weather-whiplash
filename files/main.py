"""
Backend API. This is the only service the frontend talks to.

Flow for each frame:
  frontend --(image)--> POST /predict --> inference service /infer --> store in SQLite
                                                                 --> return label + live trend

Endpoints:
  POST /predict        accept an image, classify it, persist, return current readout
  GET  /trend          time series + smoothed current state + Drying/Wetting direction
  GET  /suggestion     plain-language tyre suggestion
  GET  /health         liveness + whether inference is reachable
"""
import base64
import os
import time

import httpx
from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db, insert_prediction, get_window
from .smoothing import (
    smooth_current, trend_direction, make_suggestion, display_condition,
)

INFERENCE_URL = os.getenv("INFERENCE_URL", "http://localhost:8500")

app = FastAPI(title="Track Condition API", version="1.0")

# open CORS so a Vite dev server (or any local frontend) can call it directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


def _call_inference(image_bytes: bytes) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{INFERENCE_URL}/infer", json={"image_b64": b64})
        r.raise_for_status()
        return r.json()


def _readout(session: str) -> dict:
    """Assemble the live readout the UI wants, from what's stored for this session."""
    pts = get_window(session, window_s=float(os.getenv("READOUT_WINDOW_S", "900")))
    return {
        "condition": display_condition(pts),   # headline: Dry/Damp/Wet/Drying/Unknown
        "current": smooth_current(pts),
        "trend": trend_direction(pts),
        "suggestion": make_suggestion(pts),
        "count": len(pts),
    }


@app.get("/health")
def health():
    inf_ok = False
    try:
        with httpx.Client(timeout=5) as client:
            inf_ok = client.get(f"{INFERENCE_URL}/health").status_code == 200
    except Exception:
        inf_ok = False
    return {"status": "ok", "inference_reachable": inf_ok}


@app.post("/predict")
async def predict(file: UploadFile = File(...), session: str = Query("default")):
    image_bytes = await file.read()
    try:
        result = _call_inference(image_bytes)
    except Exception as e:
        # Fail safe: never show a confident wrong label if inference is down.
        return {"error": f"inference unavailable: {e}",
                "condition": "Unknown",
                "suggestion": {"level": "warning",
                               "message": "Condition unknown — check the track visually."}}

    insert_prediction(session, result["label"], result["confidence"],
                      result["scores"], result.get("backend", "?"))

    return {
        "frame": {"label": result["label"], "confidence": result["confidence"],
                  "scores": result["scores"], "backend": result.get("backend")},
        **_readout(session),
    }


@app.get("/trend")
def trend(session: str = Query("default"), window_s: float = Query(900)):
    pts = get_window(session, window_s=window_s)
    series = [
        {"ts": p["ts"],
         "wetness": sum({"Dry": 0, "Damp": 1, "Wet": 2}[c] * v
                        for c, v in p["scores"].items()),
         "label": p["label"], "confidence": p["confidence"]}
        for p in pts
    ]
    return {"series": series, **_readout(session)}


@app.get("/suggestion")
def suggestion(session: str = Query("default")):
    pts = get_window(session, window_s=float(os.getenv("READOUT_WINDOW_S", "900")))
    return make_suggestion(pts)
